"""Native image/video run entrypoints (Comfy template + FLUX.3).

Extracted from worker_service.py. Graph builders live in native_*_graphs;
this module only orchestrates runtime, submit, poll, and metadata.
"""
from __future__ import annotations

from comfy_endpoint import comfy_endpoint

import os
import time
from pathlib import Path
from typing import Any

import torch
from PIL import Image

from request_payload import bounded_option
from comfy_graph_helpers import task_of
from comfy_prompt_client import resolve_comfy_output_path
from family_operating_points import operating_point_params
from memory_optimization import MemoryProfile, auto_select_memory_profile
from flux3_video import Flux3Cancelled, generate_flux3_video as submit_flux3_video
from native_image_graphs import (
    _build_native_image_prompt,
    _native_image_family,
    _resolve_native_image_stack,
)
from native_video_graphs import (
    _build_native_split_video_prompt,
    _native_video_model_reference,
    _native_video_pipeline_candidates,
    _prepare_native_video_adapter_request,
)
from comfy_graph_helpers import _stack_missing_parts
from worker_service_state import (
    ActiveJobHandle,
    JobCancelledError,
    JobEmitter,
    JobRecord,
    JobState,
    complete_job,
    raise_if_cancelled,
    transition_job,
)
from vram import reading_for, remote_vram, worker_vram


def _ws():
    import worker_service as ws
    return ws


def run_native_split_stack_video(req: dict[str, Any], emitter: JobEmitter, job: JobRecord, active_job: ActiveJobHandle) -> dict[str, Any]:
    command = task_of(req)
    family = _ws()._infer_native_video_family(req)
    _ws()._raise_if_unvalidated_native_video_family(family, command=command)
    if command not in {"t2v", "i2v"}:
        raise RuntimeError(f"Native split-stack video only supports t2v/i2v, got {command!r}.")
    if command == "i2v" and not (str(family).lower().startswith("ltx") or str(family).lower().startswith("wan") or str(family).lower().startswith("hunyuan")):
        # LTX i2v, native single-model Wan i2v, and HunyuanVideo i2v ARE wired: LTX via its embedded
        # LoadImage->...->LTXVImgToVideoConditionOnly chain; Wan via the core builder's WanImageToVideo
        # branch; Hunyuan via the kijai HunyuanVideoWrapper (HyVideoI2VEncode + image_cond_latents, which
        # sidesteps the core CLIPVisionEncode llava-768 bug). All use the keyframe upload bridge below.
        # Other families have no native image-conditioning graph, so they stay blocked.
        raise RuntimeError("Native split-stack I2V templates are not wired yet for this family. Use a compiled I2V Comfy workflow for now.")

    transition_job(job, JobState.STARTING)
    emitter.status(job, "starting Comfy runtime for native split-stack video")
    emitter.emit_job_update(job)
    runtime_prep = _ws().prepare_runtime_for_request(req, emitter, job)

    runtime_status = _ws().handle_ensure_comfy_runtime_command(req)
    if not runtime_status.get("healthy"):
        raise RuntimeError(runtime_status.get("message") or "Managed Comfy runtime is not ready")
    # A LIVE detected endpoint still beats configuration -- comfy_endpoint() supplies only the
    # tail of the chain (env, then the default), so the precedence here is unchanged.
    api_url = str(
        req.get("comfy_api_url")
        or runtime_status.get("endpoint")
        or comfy_endpoint()
    ).rstrip("/")

    raise_if_cancelled(active_job, emitter, "Comfy runtime startup")
    emitter.status(job, "building native Wan split-stack Comfy template")
    object_info = _ws()._comfy_object_info(api_url)
    req = _prepare_native_video_adapter_request(req, object_info, command=command, family=family)

    family = str(req.get("resolved_native_video_family") or req.get("video_family") or req.get("model_family") or family)

    # Native i2v (LTX + Wan + Hunyuan): the keyframe must live in ComfyUI's input dir for LoadImage
    # (a COMBO of input-dir files) to reference it. Upload it now and stash the Comfy-side
    # name for the builder. Only families carved-in above reach here; if i2v is requested
    # but no image resolves, the builder falls back to t2v rather than emitting a 400.
    if command == "i2v" and (str(family).lower().startswith("ltx") or str(family).lower().startswith("wan") or str(family).lower().startswith("hunyuan")):
        local_image = _ws().video_input_image_for_request(req)
        if local_image:
            raise_if_cancelled(active_job, emitter, "i2v keyframe upload")
            uploaded = _ws()._upload_comfy_image(api_url, local_image)
            req["input_image_comfy_name"] = _ws()._comfy_image_ref(uploaded)
            emitter.status(job, f"uploaded i2v keyframe to ComfyUI: {req['input_image_comfy_name']}")
        else:
            raise RuntimeError(
                "i2v requested but no input image resolved; refusing t2v fallback."
            )

    workflow = _build_native_split_video_prompt(req, object_info, command=command, family=family, job_id=job.job_id)
    debug_prompt_path = _ws()._native_prompt_debug_path(req, job.job_id)
    _ws()._write_native_prompt_debug_file(debug_prompt_path, workflow)
    req["native_prompt_api_path"] = debug_prompt_path

    validation_issues = _ws()._validate_comfy_prompt_against_object_info(workflow, object_info)
    if validation_issues:
        raise RuntimeError(
            "Generated native split-stack Comfy prompt failed local validation before submit. "
            f"Debug prompt: {debug_prompt_path}. Issues: "
            + "; ".join(validation_issues[:30])
        )

    transition_job(job, JobState.RUNNING)
    emitter.status(job, "submitting native split-stack video template")
    start = time.perf_counter()
    prompt_id = _ws()._submit_comfy_prompt(api_url, workflow, active_job)
    emitter.status(job, f"ComfyUI native template submitted: {prompt_id}")

    history = _ws()._poll_comfy_history(api_url, prompt_id, req, emitter, job, active_job)
    asset = _ws()._extract_comfy_asset(history, ["videos", "gifs", "images", "audio"])
    if asset is None:
        raise RuntimeError("ComfyUI completed the native split-stack template but produced no output asset")

    output_path = resolve_comfy_output_path(req, asset, default_stem=f"native_split_{prompt_id}")
    output_path = _ws()._download_comfy_asset(api_url, asset, output_path)

    elapsed = time.perf_counter() - start
    steps_per_sec = float(req.get("steps") or 0) / elapsed if elapsed > 0 and req.get("steps") else 0.0
    asset_kind = str(asset.get("_asset_kind") or "").strip()
    resolved_media_type = "video" if asset_kind in {"videos", "gifs"} else ("audio" if asset_kind == "audio" else "image")
    req["resolved_media_type"] = resolved_media_type
    req["comfy_asset_kind"] = "native_split_stack_" + (asset_kind or "asset")

    metadata_output = str(req.get("metadata_output") or "").strip() or str(Path(output_path).with_suffix(".json"))
    metadata_payload = _ws().save_metadata(
        req=req,
        image_path=output_path,
        metadata_output=metadata_output,
        backend_name="SpellVisionNativeComfyTemplate",
        device="comfy",
        dtype="n/a",
        detected_pipeline=f"{family}_split_stack_template",
        lora_used=bool(req.get("lora")),
        elapsed=elapsed,
        steps_per_sec=steps_per_sec,
        job=job,
        cache_hit=False,
        model_swap_cleanup=None,
        lora_cache_hit=False,
        lora_reloaded=False,
        queue_warm_reuse_expected=bool(req.get("queue_warm_reuse_expected")),
        queue_warm_reuse_source=req.get("queue_warm_reuse_source"),
        queue_affinity_signature=req.get("queue_affinity_signature"),
        # Read off the graph that was submitted. Without this the sidecar asserted
        # sampler_applied=false on every native render, including ones whose sampler demonstrably
        # ran. See worker_metadata.sampling_provenance_from_graph.
        scheduler_stats=_ws().sampling_provenance_from_graph(workflow),
    )

    payload = {
        "ok": True,
        "cache_hit": False,
        "output": output_path,
        "output_path": output_path,
        "metadata_output": metadata_output,
        "backend_name": "SpellVisionNativeComfyTemplate",
        "detected_pipeline": f"{family}_split_stack_template",
        "task_type": command,
        "generation_time_sec": round(elapsed, 2),
        "steps_per_sec": round(steps_per_sec, 2),
        # Was a literal 0.0. On this route the weights are in ComfyUI's process, so torch in the
        # worker sees nothing -- and a zero in a field every other route fills with a measurement
        # reads as "used no memory" rather than "not measured here".
        **reading_for(api_url).payload(),
        **(active_job.submit_vram if active_job is not None else {}),
        "media_type": resolved_media_type,
        "video_path": output_path if resolved_media_type == "video" else "",
        "asset_kind": "native_split_stack",
        "model_family": family,
        "video_model_stack": _ws()._video_model_stack_from_request(req) or None,
        "workflow_media_output": output_path,
        "prompt_id": prompt_id,
        "metadata": metadata_payload,
        "metadata_write_deferred": False,
        **_ws().output_finalization_contract(output_path if 'output_path' in locals() else req.get("output"), metadata_output if 'metadata_output' in locals() else req.get("metadata_output"), original_output=str(req.get("original_output") or ""), media_type=_ws().output_media_type_for_metadata(req, output_path if 'output_path' in locals() else req.get("output")), metadata_write_status=str(metadata_payload.get("metadata_write_status") or "written"), metadata_write_error=metadata_payload.get("metadata_write_error")),
        **_ws().runtime_prep_metadata(req),
        "comfy_runtime_endpoint": runtime_status.get("endpoint"),
        "comfy_runtime_pid": runtime_status.get("pid"),
        "native_template": True,
    }
    payload.update(_ws().video_completion_diagnostics(
        req,
        backend_type="native_video",
        backend_name=str(payload.get("backend_name") or "SpellVisionNativeComfyTemplate"),
        output_path=output_path,
        metadata_output=metadata_output,
        prompt_id=prompt_id,
    ))
    video_cache_update = _ws().update_video_runtime_cache_from_result(req, payload)
    if video_cache_update:
        payload["video_runtime_cache_updated"] = True
        payload["video_runtime_cache"] = video_cache_update
    complete_job(job, payload)
    emitter.emit_job_update(job)
    return payload


def run_native_image(req: dict[str, Any], emitter: JobEmitter, job: JobRecord, active_job: ActiveJobHandle) -> dict[str, Any]:
    """Render an image through a ComfyUI-native graph (route B). Flux t2i + i2i."""
    command = task_of(req, "t2i")
    if command not in {"t2i", "i2i"}:
        raise RuntimeError(f"Native image path supports t2i/i2i only, got {command!r}.")

    transition_job(job, JobState.STARTING)
    emitter.status(job, "starting Comfy runtime for native image")
    emitter.emit_job_update(job)
    _ws().prepare_runtime_for_request(req, emitter, job)
    # The transformer + T5 render inside ComfyUI's process; free any diffusers pipeline the worker
    # holds so the two don't contend for VRAM.
    _ws().unload_cached_pipelines()

    runtime_status = _ws().handle_ensure_comfy_runtime_command(req)
    if not runtime_status.get("healthy"):
        raise RuntimeError(runtime_status.get("message") or "Managed Comfy runtime is not ready")
    # A LIVE detected endpoint still beats configuration -- comfy_endpoint() supplies only the
    # tail of the chain (env, then the default), so the precedence here is unchanged.
    api_url = str(
        req.get("comfy_api_url")
        or runtime_status.get("endpoint")
        or comfy_endpoint()
    ).rstrip("/")

    raise_if_cancelled(active_job, emitter, "Comfy runtime startup")
    # i2i: the input image must live in ComfyUI's input dir for LoadImage (a COMBO of input-dir files)
    # to reference it -- an arbitrary local path can't be passed. Upload it now and stash the
    # Comfy-side name for the builder (the exact keyframe bridge native i2v uses).
    if command == "i2i":
        input_image = str(req.get("input_image") or "").strip()
        if not input_image:
            raise RuntimeError("Native i2i requires an input image (req['input_image']).")
        uploaded = _ws()._upload_comfy_image(api_url, input_image)
        req["input_image_comfy_name"] = _ws()._comfy_image_ref(uploaded)
        emitter.status(job, f"uploaded i2i input to ComfyUI: {req['input_image_comfy_name']}")
        mask_path = str(
            req.get("mask")
            or req.get("mask_image")
            or req.get("inpaint_mask")
            or ""
        ).strip()
        if mask_path and not str(req.get("inpaint_mask_comfy_name") or "").strip():
            mask_uploaded = _ws()._upload_comfy_image(api_url, mask_path)
            req["inpaint_mask_comfy_name"] = _ws()._comfy_image_ref(mask_uploaded)
            emitter.status(job, f"uploaded inpaint mask to ComfyUI: {req['inpaint_mask_comfy_name']}")
    family = _native_image_family(req) or "flux"
    emitter.status(job, f"building native {family} image template")
    object_info = _ws()._comfy_object_info(api_url)
    # Producer-side companion resolution (Doc 19 §6): resolve_stack drives the family's companions
    # (precision-matched where applicable) from the on-disk ComfyUI choices, not fixed strings.
    resolved = _resolve_native_image_stack(req, object_info, family)
    missing = [s.component for s in resolved.missing_required()]
    if missing:
        # Image analog of the video readiness gate: surface a T3-missing companion as a clear block
        # BEFORE submitting the graph, never a mid-render ComfyUI failure.
        raise RuntimeError(
            f"{family} stack incomplete -- missing required component(s): " + ", ".join(missing)
            + ". The resolver found no valid on-disk file for them; resolve or download before generating."
        )
    workflow = _build_native_image_prompt(family, req, object_info, job.job_id, resolved)
    # The submitted graph is written to the native-prompt debug file below (always) -- that JSON is the
    # authoritative record of the resolver-driven companions (clip_l / precision-matched T5 / ae) and
    # the cfg->guidance mapping, the same observability the native video path relies on.
    debug_prompt_path = _ws()._native_prompt_debug_path(req, job.job_id)
    _ws()._write_native_prompt_debug_file(debug_prompt_path, workflow)
    req["native_prompt_api_path"] = debug_prompt_path

    validation_issues = _ws()._validate_comfy_prompt_against_object_info(workflow, object_info)
    if validation_issues:
        raise RuntimeError(
            f"Generated native {family} image prompt failed local validation before submit. "
            f"Debug prompt: {debug_prompt_path}. Issues: " + "; ".join(validation_issues[:30])
        )

    transition_job(job, JobState.RUNNING)
    emitter.status(job, f"submitting native {family} image template")
    start = time.perf_counter()
    prompt_id = _ws()._submit_comfy_prompt(api_url, workflow, active_job)
    emitter.status(job, f"ComfyUI native {family} template submitted: {prompt_id}")

    history = _ws()._poll_comfy_history(api_url, prompt_id, req, emitter, job, active_job)
    asset = _ws()._extract_comfy_asset(history, ["images"])
    if asset is None:
        raise RuntimeError(f"ComfyUI completed the native {family} template but produced no image asset")

    output_path = resolve_comfy_output_path(req, asset, default_stem=f"flux_native_{prompt_id}")
    output_path = _ws()._download_comfy_asset(api_url, asset, output_path)

    elapsed = time.perf_counter() - start
    steps_per_sec = float(req.get("steps") or 0) / elapsed if elapsed > 0 and req.get("steps") else 0.0
    req["resolved_media_type"] = "image"
    req["comfy_asset_kind"] = f"native_{family}_image"

    metadata_output = str(req.get("metadata_output") or "").strip() or str(Path(output_path).with_suffix(".json"))
    metadata_payload = _ws().save_metadata(
        req=req,
        image_path=output_path,
        metadata_output=metadata_output,
        backend_name="SpellVisionNativeComfyTemplate",
        device="comfy",
        dtype="n/a",
        detected_pipeline=f"{family}_native_image_template",
        lora_used=bool(req.get("lora")),
        elapsed=elapsed,
        steps_per_sec=steps_per_sec,
        job=job,
        cache_hit=False,
        model_swap_cleanup=None,
        lora_cache_hit=False,
        lora_reloaded=False,
        queue_warm_reuse_expected=bool(req.get("queue_warm_reuse_expected")),
        queue_warm_reuse_source=req.get("queue_warm_reuse_source"),
        queue_affinity_signature=req.get("queue_affinity_signature"),
        # Read off the graph that was submitted. Without this the sidecar asserted
        # sampler_applied=false on every native render, including ones whose sampler demonstrably
        # ran. See worker_metadata.sampling_provenance_from_graph.
        scheduler_stats=_ws().sampling_provenance_from_graph(workflow),
    )

    payload = {
        "ok": True,
        "cache_hit": False,
        "output": output_path,
        "output_path": output_path,
        "metadata_output": metadata_output,
        "backend_name": "SpellVisionNativeComfyTemplate",
        "detected_pipeline": f"{family}_native_image_template",
        "task_type": command,
        "generation_time_sec": round(elapsed, 2),
        "steps_per_sec": round(steps_per_sec, 2),
        # Was a literal 0.0. On this route the weights are in ComfyUI's process, so torch in the
        # worker sees nothing -- and a zero in a field every other route fills with a measurement
        # reads as "used no memory" rather than "not measured here".
        **reading_for(api_url).payload(),
        **(active_job.submit_vram if active_job is not None else {}),
        "media_type": "image",
        "model_family": family,
        "prompt_id": prompt_id,
        "metadata": metadata_payload,
        "metadata_write_deferred": False,
        "native_template": True,
        **_ws().output_finalization_contract(
            output_path,
            metadata_output,
            original_output=str(req.get("original_output") or ""),
            media_type=_ws().output_media_type_for_metadata(req, output_path),
            metadata_write_status=str(metadata_payload.get("metadata_write_status") or "written"),
            metadata_write_error=metadata_payload.get("metadata_write_error"),
        ),
        **_ws().runtime_prep_metadata(req),
        "comfy_runtime_endpoint": runtime_status.get("endpoint"),
        "comfy_runtime_pid": runtime_status.get("pid"),
    }
    complete_job(job, payload)
    emitter.emit_job_update(job)
    return payload


def _load_native_video_pipeline(req: dict[str, Any], command: str, family: str) -> tuple[Any, str, str, str]:
    stack = _ws()._video_model_stack_from_request(req)
    model_ref = _native_video_model_reference(req)
    model_path = Path(model_ref)
    suffix = model_path.suffix.lower()
    stack_kind = str(stack.get("stack_kind") or req.get("native_video_stack_kind") or "").strip().lower()

    if suffix in {".safetensors", ".ckpt", ".bin", ".gguf"}:
        stack_summary = _ws()._stack_summary(stack)
        raise RuntimeError(
            "SpellVision resolved this selection as a native video model stack, but split-stack execution is not wired into "
            "Diffusers yet. Native execution currently needs a Diffusers-format folder/repo with model_index.json. "
            f"Selected stack: {stack_summary}. "
            "Use a compiled Comfy workflow for split WAN/LTX/Hunyuan assets for now, or select a Diffusers-format video model folder."
        )

    if stack and stack_kind == "split_stack":
        missing = _stack_missing_parts(stack)
        if missing:
            raise RuntimeError(
                "The selected native video stack is incomplete: missing "
                + ", ".join(missing)
                + ". Add the missing assets or use an imported Comfy workflow that already binds them."
            )

    dtype, device = _ws().torch_dtype_and_device()
    if device == "cuda" and dtype == torch.float16:
        # Many modern video transformer pipelines prefer bfloat16 on Ada/Blackwell when available.
        try:
            if torch.cuda.is_bf16_supported():
                dtype = torch.bfloat16
        except Exception:
            pass

    errors: list[str] = []
    for class_name in _native_video_pipeline_candidates(command, family):
        pipe_cls = _ws()._import_diffusers_symbol(class_name)
        if pipe_cls is None:
            errors.append(f"{class_name}: not available in installed diffusers")
            continue

        try:
            pipe = pipe_cls.from_pretrained(model_ref, torch_dtype=dtype)
        except Exception as exc:
            errors.append(f"{class_name}: {exc}")
            continue

        # ORDER IS LOAD-BEARING, and the previous order was self-defeating: it did
        # `.to(device)` first and then called enable_model_cpu_offload(). apply_memory_profile's
        # contract (memory_optimization.py) spells out why that is wrong -- the offload hooks
        # accelerate installs own device placement, so pre-moving to CUDA defeats them. The
        # pipeline ended up resident on the GPU *and* paying the hook overhead: the worst of both.
        #
        # Correct sequence:
        #   1. attention/VAE optimizations, which must run BEFORE any offload hooks exist
        #      (apply_attention_optimizations documents that slicing interacts poorly with them),
        #   2. THEN either offload (which places the modules itself) or an explicit .to(device).
        profile = auto_select_memory_profile()
        try:
            pipe = _ws().optimize_pipeline(pipe, device, profile=profile)
        except Exception:
            pass

        requested_offload = req.get("enable_cpu_offload")
        if requested_offload is None:
            # Was hardcoded True. On a PERFORMANCE-profile card there is no VRAM pressure to
            # trade against, so offload only bought a ~10-20% throughput loss. Decide by profile
            # and let the request override either way.
            use_offload = profile != MemoryProfile.PERFORMANCE
        else:
            use_offload = bool(requested_offload)

        placed = False
        if use_offload and hasattr(pipe, "enable_model_cpu_offload"):
            try:
                pipe.enable_model_cpu_offload()  # owns placement -- do NOT .to(device) as well
                placed = True
            except Exception:
                placed = False
        if not placed:
            try:
                pipe.to(device)
            except Exception:
                pass

        return pipe, device, str(dtype), class_name

    raise RuntimeError(
        "No native video Diffusers pipeline could load this model. Tried: "
        + "; ".join(errors[:8])
    )


def _native_video_kwargs(req: dict[str, Any], command: str) -> dict[str, Any]:
    frames = bounded_option(req, "frames", 81)
    fps = bounded_option(req, "fps", 16)
    _defaults = operating_point_params("wan_diffusers", "default")  # Phase 2a: defaults lifted to the table
    steps = bounded_option(req, "steps", 30, table=_defaults)
    cfg = bounded_option(req, "cfg", 5.0, table=_defaults)

    kwargs: dict[str, Any] = {
        "prompt": str(req.get("prompt") or ""),
        "num_frames": frames,
        "num_inference_steps": steps,
        "guidance_scale": cfg,
    }

    negative_prompt = str(req.get("negative_prompt") or "").strip()
    if negative_prompt:
        kwargs["negative_prompt"] = negative_prompt

    width = int(req.get("width") or 0)
    height = int(req.get("height") or 0)
    if width > 0:
        kwargs["width"] = width
    if height > 0:
        kwargs["height"] = height

    # Zero is a seed, the same as it is in every graph builder (comfy_graph_helpers.resolve_seed).
    # `if seed > 0` meant a request for seed 0 got NO generator at all, so the diffusers route
    # rendered nondeterministically while the native route rendered seed 0 -- the same request,
    # two different meanings, neither of them stated.
    from comfy_graph_helpers import resolve_seed

    seed = resolve_seed(req, "seed")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    kwargs["generator"] = torch.Generator(device=device).manual_seed(seed)

    if command == "i2v":
        input_image = str(req.get("input_image") or "").strip()
        if not input_image:
            raise RuntimeError("Native I2V requires input_image.")
        try:
            from diffusers.utils import load_image  # type: ignore
            kwargs["image"] = load_image(input_image)
        except Exception:
            kwargs["image"] = Image.open(input_image).convert("RGB")

    return kwargs


def run_flux3_video(req: dict[str, Any], emitter: JobEmitter, job: JobRecord, active_job: ActiveJobHandle) -> dict[str, Any]:
    command = task_of(req)
    if command not in {"t2v", "i2v"}:
        raise RuntimeError(f"FLUX.3 only supports t2v/i2v in this cockpit, got {command!r}.")

    transition_job(job, JobState.STARTING)
    req["resolved_native_video_family"] = "flux3"
    req["backend_route"] = "bfl_api"
    req["video_backend_type"] = "bfl_api"
    req["resolved_media_type"] = "video"
    req["comfy_asset_kind"] = "remote_video"
    emitter.status(job, "preparing FLUX.3 BFL API preview")
    emitter.emit_job_update(job)
    raise_if_cancelled(active_job, emitter, "FLUX.3 request preparation")

    output_path = str(req.get("output") or "").strip()
    if not output_path:
        output_path = str(Path.cwd() / f"{job.job_id}.mp4")
    if Path(output_path).suffix.lower() != ".mp4":
        output_path = str(Path(output_path).with_suffix(".mp4"))
    metadata_output = str(req.get("metadata_output") or "").strip() or str(Path(output_path).with_suffix(".json"))

    transition_job(job, JobState.RUNNING)
    emitter.status(job, "submitting paid preview to the BFL API")
    emitter.emit_job_update(job)
    start = time.perf_counter()
    try:
        remote_result = submit_flux3_video(
            req,
            output_path,
            should_cancel=active_job.cancel_event.is_set,
            on_status=lambda status: emitter.status(job, f"FLUX.3: {status}"),
        )
    except Flux3Cancelled as exc:
        raise JobCancelledError(str(exc)) from exc
    elapsed = time.perf_counter() - start
    raise_if_cancelled(active_job, emitter, "FLUX.3 completion")

    metadata_payload = _ws().save_metadata(
        req=req,
        image_path=output_path,
        metadata_output=metadata_output,
        backend_name="BFL FLUX.3 API",
        device="external",
        dtype="n/a",
        detected_pipeline="flux3",
        lora_used=False,
        elapsed=elapsed,
        steps_per_sec=0.0,
        job=job,
        cache_hit=False,
        model_swap_cleanup=None,
        lora_cache_hit=False,
        lora_reloaded=False,
        queue_warm_reuse_expected=False,
        queue_warm_reuse_source=None,
        queue_affinity_signature=req.get("queue_affinity_signature"),
    )

    payload = {
        "ok": True,
        "cache_hit": False,
        "output": output_path,
        "output_path": output_path,
        "video_output": output_path,
        "output_video": output_path,
        "video_path": output_path,
        "metadata_output": metadata_output,
        "video_metadata_output": metadata_output,
        "backend_name": "BFL FLUX.3 API",
        "detected_pipeline": "flux3",
        "task_type": command,
        "generation_time_sec": round(elapsed, 2),
        "steps_per_sec": 0.0,
        # FLUX.3 renders on the BFL API, so there is no local GPU to read. The old literal 0.0
        # was nearly true here and still wrong: it is the same zero the ComfyUI routes wrote when
        # they had not looked, and no reader could tell the two apart.
        **remote_vram().payload(),
        "media_type": "video",
        "asset_kind": "remote_video",
        "model_family": "flux3",
        "backend_route": "bfl_api",
        "flux3_request_id": remote_result.get("request_id"),
        "metadata": metadata_payload,
        "metadata_write_deferred": False,
        **_ws().output_finalization_contract(
            output_path,
            metadata_output,
            original_output=str(req.get("original_output") or ""),
            media_type="video",
            metadata_write_status=str(metadata_payload.get("metadata_write_status") or "written"),
            metadata_write_error=metadata_payload.get("metadata_write_error"),
        ),
    }
    payload.update(_ws().video_completion_diagnostics(
        req,
        backend_type="bfl_api",
        backend_name="BFL FLUX.3 API",
        output_path=output_path,
        metadata_output=metadata_output,
        prompt_id=str(remote_result.get("request_id") or ""),
    ))
    video_cache_update = _ws().update_video_runtime_cache_from_result(req, payload)
    if video_cache_update:
        payload["video_runtime_cache_updated"] = True
        payload["video_runtime_cache"] = video_cache_update
    complete_job(job, payload)
    emitter.emit_job_update(job)
    return payload


def run_native_video(req: dict[str, Any], emitter: JobEmitter, job: JobRecord, active_job: ActiveJobHandle) -> dict[str, Any]:
    command = task_of(req)
    if command not in {"t2v", "i2v"}:
        raise RuntimeError(f"Native video backend only supports t2v/i2v, got {command!r}.")

    transition_job(job, JobState.STARTING)

    # Native-LTX migration (Step 4): the LTX -> prompt-api redirect that used to sit
    # here is gone. Every t2v/i2v request (LTX included) now proceeds to family
    # inference + the native gate below. LTX's contract is production (see
    # video_family_contracts), so it PASSES the gate and renders natively; only
    # families still marked non-production (hunyuan/cogvideox/mochi) are blocked by
    # the gate until theirs flip. The prompt-api engine remains reachable only via the
    # explicit ltx_prompt_api_gated_submission command (history requeue / fallback).
    emitter.status(job, "loading native video pipeline")
    emitter.emit_job_update(job)

    family = _ws()._infer_native_video_family(req)
    _ws()._raise_if_unvalidated_native_video_family(family, command=command)
    if _ws()._is_split_video_stack_request(req):
        return run_native_split_stack_video(req, emitter, job, active_job)
    runtime_prep = _ws().prepare_runtime_for_request(req, emitter, job)

    pipe, device, dtype, pipeline_class = _load_native_video_pipeline(req, command, family)
    raise_if_cancelled(active_job, emitter, "native video pipeline loading")

    kwargs = _native_video_kwargs(req, command)
    transition_job(job, JobState.RUNNING)
    emitter.status(job, f"running native {pipeline_class}")
    raise_if_cancelled(active_job, emitter, "native video startup")

    start = time.perf_counter()
    result = pipe(**kwargs)
    elapsed = time.perf_counter() - start
    raise_if_cancelled(active_job, emitter, "native video completion")

    frames = _ws()._native_video_frames_from_result(result)
    output_path = str(req.get("output") or "").strip()
    if not output_path:
        output_path = str(Path.cwd() / f"{job.job_id}.mp4")
    if Path(output_path).suffix.lower() not in {".mp4", ".webm", ".gif"}:
        output_path = str(Path(output_path).with_suffix(".mp4"))
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    try:
        from diffusers.utils import export_to_video  # type: ignore
    except Exception as exc:
        raise RuntimeError("Native video generation requires diffusers.utils.export_to_video.") from exc

    export_to_video(frames, output_path, fps=bounded_option(req, "fps", 16))

    metadata_output = str(req.get("metadata_output") or "").strip() or str(Path(output_path).with_suffix(".json"))
    req["resolved_media_type"] = "video"
    req["comfy_asset_kind"] = "native_video"

    steps_per_sec = float(req.get("steps") or 0) / elapsed if elapsed > 0 and req.get("steps") else 0.0
    metadata_payload = _ws().save_metadata(
        req=req,
        image_path=output_path,
        metadata_output=metadata_output,
        backend_name=pipeline_class,
        device=device,
        dtype=dtype,
        detected_pipeline=family,
        lora_used=bool(req.get("lora")),
        elapsed=elapsed,
        steps_per_sec=steps_per_sec,
        job=job,
        cache_hit=False,
        model_swap_cleanup=None,
        lora_cache_hit=False,
        lora_reloaded=False,
        queue_warm_reuse_expected=bool(req.get("queue_warm_reuse_expected")),
        queue_warm_reuse_source=req.get("queue_warm_reuse_source"),
        queue_affinity_signature=req.get("queue_affinity_signature"),
    )

    payload = {
        "ok": True,
        "cache_hit": False,
        "output": output_path,
        "output_path": output_path,
        "metadata_output": metadata_output,
        "backend_name": pipeline_class,
        "detected_pipeline": family,
        "task_type": command,
        "generation_time_sec": round(elapsed, 2),
        "steps_per_sec": round(steps_per_sec, 2),
        **worker_vram().payload(),
        "media_type": "video",
        "asset_kind": "native_video",
        "model_family": family,
        "video_model_stack": _ws()._video_model_stack_from_request(req) or None,
        "metadata": metadata_payload,
        "metadata_write_deferred": False,
        **_ws().output_finalization_contract(output_path if 'output_path' in locals() else req.get("output"), metadata_output if 'metadata_output' in locals() else req.get("metadata_output"), original_output=str(req.get("original_output") or ""), media_type=_ws().output_media_type_for_metadata(req, output_path if 'output_path' in locals() else req.get("output")), metadata_write_status=str(metadata_payload.get("metadata_write_status") or "written"), metadata_write_error=metadata_payload.get("metadata_write_error")),
        **_ws().runtime_prep_metadata(req),
    }

    payload.update(_ws().video_completion_diagnostics(
        req,
        backend_type="native_video",
        backend_name=str(payload.get("backend_name") or "Native Video"),
        output_path=str(payload.get("output") or req.get("output") or ""),
        metadata_output=str(payload.get("metadata_output") or req.get("metadata_output") or ""),
    ))
    video_cache_update = _ws().update_video_runtime_cache_from_result(req, payload)
    if video_cache_update:
        payload["video_runtime_cache_updated"] = True
        payload["video_runtime_cache"] = video_cache_update
    complete_job(job, payload)
    emitter.emit_job_update(job)
    return payload


