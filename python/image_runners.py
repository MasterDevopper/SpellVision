"""Diffusers image runners: t2i/i2i plus LoRA, IP-Adapter, and upscale.

Extracted from worker_service.py. Pipeline cache and Comfy native graphs
stay elsewhere; this module only runs the local image path.
"""
from __future__ import annotations

import hashlib
import importlib
import inspect
import logging
import os
import time
from pathlib import Path
from typing import Any

import torch
from PIL import Image

from worker_service_state import (
    ActiveJobHandle,
    JobCancelledError,
    JobEmitter,
    JobRecord,
    JobState,
    cancel_job,
    complete_job,
    raise_if_cancelled,
    transition_job,
)
from request_payload import resolve_request_lora
from native_image_graphs import _should_route_native_image
from worker_runtime import CACHE_LOCK, MODEL_CACHE


def _ws():
    import worker_service as ws
    return ws


def _lora_cache_keys(pipe_role: str) -> tuple[str, str]:
    role = pipe_role.lower().strip()
    if role not in {"t2i", "i2i"}:
        raise ValueError(f"Unknown LoRA pipe role: {pipe_role}")
    return (f"active_lora_path_{role}", f"active_lora_scale_{role}")


def get_cached_lora_state(pipe_role: str) -> tuple[str | None, float | None]:
    path_key, scale_key = _lora_cache_keys(pipe_role)
    with CACHE_LOCK:
        return MODEL_CACHE.get(path_key), MODEL_CACHE.get(scale_key)


def set_cached_lora_state(pipe_role: str, lora_path: str | None, lora_scale: float | None) -> None:
    path_key, scale_key = _lora_cache_keys(pipe_role)
    with CACHE_LOCK:
        MODEL_CACHE[path_key] = lora_path
        MODEL_CACHE[scale_key] = lora_scale


def _lora_adapter_name(normalized_path: str) -> str:
    # peft adapter names must be simple identifiers; derive a stable,
    # collision-free name from the LoRA's absolute path.
    digest = hashlib.sha1(normalized_path.encode("utf-8")).hexdigest()[:12]
    return f"lora_{digest}"


def _lora_adapter_registry() -> dict[str, str]:
    # normalized LoRA path -> adapter name, for adapters already loaded onto the
    # current model's (shared) pipelines. Reset on model swap; kept across
    # t2i<->i2i role switches within a model. Call under CACHE_LOCK.
    registry = MODEL_CACHE.get("lora_adapters")
    if not isinstance(registry, dict):
        registry = {}
        MODEL_CACHE["lora_adapters"] = registry
    return registry


def active_adapter_names(pipe: Any) -> list[str]:
    try:
        if hasattr(pipe, "get_active_adapters"):
            return [str(name) for name in pipe.get_active_adapters()]
    except Exception:
        pass
    return []


def _disable_pipe_adapters(pipe: Any) -> None:
    # Run pristine base weights for THIS generation without unloading any
    # adapters -- they stay resident on the shared modules for the other role.
    try:
        if hasattr(pipe, "disable_lora"):
            pipe.disable_lora()
            return
    except Exception:
        pass
    try:
        if hasattr(pipe, "set_adapters"):
            pipe.set_adapters([])
    except Exception:
        pass


def ensure_lora_adapter_loaded(pipe: Any, normalized_path: str) -> tuple[str, bool]:
    # Load the LoRA exactly once as a NAMED adapter (never fused, so the base
    # UNet weights -- shared between the t2i/i2i pipes -- are never mutated).
    # Returns (adapter_name, newly_loaded).
    adapter_name = _lora_adapter_name(normalized_path)
    with CACHE_LOCK:
        existing = _lora_adapter_registry().get(normalized_path)
    if existing:
        return existing, False

    pipe.load_lora_weights(normalized_path, adapter_name=adapter_name)
    with CACHE_LOCK:
        _lora_adapter_registry()[normalized_path] = adapter_name
    return adapter_name, True


def reset_lora_state(pipe: Any, pipe_role: str | None = None) -> None:
    # Non-destructive no-LoRA path: DISABLE adapters for this pipe's next
    # generation, but do NOT unload -- the other role's adapter must stay
    # resident on the shared UNet. Base weights are never mutated (we never
    # fuse), so disabling == clean base output.
    _disable_pipe_adapters(pipe)
    if pipe_role:
        set_cached_lora_state(pipe_role, None, None)


def maybe_load_lora(pipe: Any, lora_path: str, lora_scale: float, pipe_role: str) -> tuple[bool, dict[str, Any]]:
    normalized_path = os.path.abspath(lora_path).strip() if lora_path else ""
    cached_path, cached_scale = get_cached_lora_state(pipe_role)

    if not normalized_path:
        cleared = bool(cached_path)
        reset_lora_state(pipe, pipe_role)
        return False, {
            "lora_cache_hit": False,
            "lora_reloaded": False,
            "lora_cleared": cleared,
            "active_lora_path": None,
            "active_lora_scale": None,
        }

    if not os.path.exists(normalized_path):
        raise FileNotFoundError(f"LoRA file not found: {normalized_path}")

    try:
        import peft  # noqa: F401
    except Exception as exc:
        raise RuntimeError("LoRA support requires 'peft' in the venv.") from exc

    adapter_name, newly_loaded = ensure_lora_adapter_loaded(pipe, normalized_path)

    # ALWAYS (re)select + scale this role's adapter right before generating. The
    # UNet is shared between the t2i/i2i pipes, so the active adapter is global
    # state the other role may have changed -- selecting every time is what makes
    # the two roles independent. set_adapters is a cheap toggle (no reload, no
    # fuse), so there is deliberately no cache-hit short-circuit that skips it.
    try:
        if hasattr(pipe, "enable_lora"):
            pipe.enable_lora()
    except Exception:
        pass
    pipe.set_adapters([adapter_name], adapter_weights=[float(lora_scale)])

    same_as_cached = (
        cached_path == normalized_path
        and cached_scale is not None
        and abs(float(cached_scale) - float(lora_scale)) < 1e-9
    )
    set_cached_lora_state(pipe_role, normalized_path, float(lora_scale))

    return True, {
        "lora_cache_hit": (not newly_loaded) and same_as_cached,
        "lora_reloaded": newly_loaded,
        "lora_cleared": False,
        "active_lora_path": normalized_path,
        "active_lora_scale": float(lora_scale),
    }


def _scheduler_from_config(scheduler_cls: Any, base_config: Any, **kwargs: Any) -> Any:
    if scheduler_cls is None:
        return None
    try:
        return scheduler_cls.from_config(base_config, **kwargs)
    except TypeError:
        return scheduler_cls.from_config(base_config)


_SCHEDULER_IMPORTS: dict[str, tuple[str, str]] = {
    "euler": ("diffusers.schedulers.scheduling_euler_discrete", "EulerDiscreteScheduler"),
    "euler_ancestral": ("diffusers.schedulers.scheduling_euler_ancestral_discrete", "EulerAncestralDiscreteScheduler"),
    "heun": ("diffusers.schedulers.scheduling_heun_discrete", "HeunDiscreteScheduler"),
    "dpm_2": ("diffusers.schedulers.scheduling_k_dpm_2_discrete", "KDPM2DiscreteScheduler"),
    "dpm_2_ancestral": ("diffusers.schedulers.scheduling_k_dpm_2_ancestral_discrete", "KDPM2AncestralDiscreteScheduler"),
    "lms": ("diffusers.schedulers.scheduling_lms_discrete", "LMSDiscreteScheduler"),
    "dpmpp_2m": ("diffusers.schedulers.scheduling_dpmsolver_multistep", "DPMSolverMultistepScheduler"),
    "dpmpp_sde": ("diffusers.schedulers.scheduling_dpmsolver_singlestep", "DPMSolverSinglestepScheduler"),
    "ddpm": ("diffusers.schedulers.scheduling_ddpm", "DDPMScheduler"),
    "ddim": ("diffusers.schedulers.scheduling_ddim", "DDIMScheduler"),
    "deis": ("diffusers.schedulers.scheduling_deis_multistep", "DEISMultistepScheduler"),
    "pndm": ("diffusers.schedulers.scheduling_pndm", "PNDMScheduler"),
    "lcm": ("diffusers.schedulers.scheduling_lcm", "LCMScheduler"),
    "uni_pc": ("diffusers.schedulers.scheduling_unipc_multistep", "UniPCMultistepScheduler"),
}


def _load_scheduler_class(sampler_name: str) -> Any:
    import_spec = _SCHEDULER_IMPORTS.get(sampler_name)
    if import_spec is None:
        return None
    module_name, class_name = import_spec
    try:
        return getattr(importlib.import_module(module_name), class_name)
    except Exception:
        return None


def apply_sampler_and_scheduler(pipe: Any, req: dict[str, Any]) -> dict[str, Any]:
    if pipe is None or not hasattr(pipe, "scheduler"):
        return {"applied": False, "sampler": None, "scheduler": None}

    sampler_name = str(req.get("sampler") or "").strip().lower()
    scheduler_name = str(req.get("scheduler") or "").strip().lower()

    scheduler_cls = _load_scheduler_class(sampler_name)
    if scheduler_cls is None:
        return {"applied": False, "sampler": sampler_name or None, "scheduler": scheduler_name or None}

    extra_config: dict[str, Any] = {}
    if scheduler_name == "karras":
        extra_config["use_karras_sigmas"] = True
    elif scheduler_name == "exponential":
        extra_config["use_exponential_sigmas"] = True
    elif scheduler_name == "beta":
        extra_config["use_beta_sigmas"] = True

    try:
        new_scheduler = _scheduler_from_config(scheduler_cls, pipe.scheduler.config, **extra_config)
        if new_scheduler is not None:
            pipe.scheduler = new_scheduler
            return {
                "applied": True,
                "sampler": sampler_name or None,
                "scheduler": scheduler_name or None,
                "scheduler_class": scheduler_cls.__name__,
            }
    except Exception as exc:
        return {
            "applied": False,
            "sampler": sampler_name or None,
            "scheduler": scheduler_name or None,
            "error": str(exc),
        }

    return {"applied": False, "sampler": sampler_name or None, "scheduler": scheduler_name or None}


def build_generation_kwargs(
    req: dict[str, Any],
    generator: torch.Generator,
    extra: dict[str, Any] | None = None,
    pipe: Any = None,
) -> dict[str, Any]:
    prompt = req["prompt"]
    negative = req.get("negative_prompt") or ""

    kwargs: dict[str, Any] = {
        "num_inference_steps": int(req["steps"]),
        "guidance_scale": float(req["cfg"]),
        "generator": generator,
    }

    # OPTION B routing (see note above): native string path unless the prompt needs sd_embed.
    if pipe is not None and _ws()._prompt_needs_weighted_embeds(pipe, prompt, negative):
        from sd_embed.embedding_funcs import get_weighted_text_embeddings_sdxl

        pe, npe, ppe, nppe = get_weighted_text_embeddings_sdxl(pipe, prompt=prompt, neg_prompt=negative)
        # MUST NOT also pass prompt=/negative_prompt= -- diffusers rejects string + embeds together.
        kwargs["prompt_embeds"] = pe
        kwargs["pooled_prompt_embeds"] = ppe
        kwargs["negative_prompt_embeds"] = npe
        kwargs["negative_pooled_prompt_embeds"] = nppe
        logging.warning(
            "[long-prompt] sd_embed embed path: prompt_chars=%d weighting=%s (>77 tokens or (word:w) syntax)",
            len(prompt),
            _ws()._has_weighting_syntax(prompt) or _ws()._has_weighting_syntax(negative),
        )
    else:
        kwargs["prompt"] = prompt
        if req.get("negative_prompt"):
            kwargs["negative_prompt"] = req["negative_prompt"]

    if extra:
        kwargs.update(extra)

    return kwargs


def attach_progress_callback(
    pipe: Any,
    kwargs: dict[str, Any],
    req: dict[str, Any],
    emitter: JobEmitter,
    job: JobRecord,
    active_job: ActiveJobHandle,
) -> None:
    total_steps = int(req["steps"])
    signature = inspect.signature(pipe.__call__)

    def step_end_callback(_pipe: Any, step_index: int, _timestep: Any, callback_kwargs: dict[str, Any]) -> dict[str, Any]:
        if active_job.cancel_event.is_set() or job.cancel_requested:
            cancel_job(job, f"Generation cancelled during step {step_index + 1}/{total_steps}")
            emitter.emit_job_update(job)
            raise JobCancelledError(job.error.message if job.error else "Generation cancelled")
        emitter.progress(job, step_index + 1, total_steps, f"running step {step_index + 1}/{total_steps}")
        return callback_kwargs

    def legacy_callback(step: int, _timestep: Any, _latents: Any) -> None:
        if active_job.cancel_event.is_set() or job.cancel_requested:
            cancel_job(job, f"Generation cancelled during step {step + 1}/{total_steps}")
            emitter.emit_job_update(job)
            raise JobCancelledError(job.error.message if job.error else "Generation cancelled")
        emitter.progress(job, step + 1, total_steps, f"running step {step + 1}/{total_steps}")

    if "callback_on_step_end" in signature.parameters:
        kwargs["callback_on_step_end"] = step_end_callback
    elif "callback" in signature.parameters:
        kwargs["callback"] = legacy_callback
        kwargs["callback_steps"] = 1


def maybe_apply_ipadapter(pipe, req: dict[str, Any], weight: float, emitter=None, job=None) -> tuple[bool, str]:
    """Best-effort IP-Adapter attach for pose/style-flexible I2I.

    Returns (applied, note). Never raises for missing files/APIs — Character Studio
    still works via pure denoise when adapters are absent.
    """
    if pipe is None or not hasattr(pipe, "load_ip_adapter"):
        return False, "pipeline has no load_ip_adapter"

    candidates: list[str] = []
    for key in ("ipadapter_file", "ip_adapter_path", "ipadapter_path"):
        raw = str(req.get(key) or "").strip()
        if raw:
            candidates.append(raw)

    roots: list[Path] = []
    for env_key in ("SPELLVISION_MODELS_ROOT", "SPELLVISION_ASSETS_ROOT"):
        v = os.environ.get(env_key, "").strip()
        if v:
            roots.append(Path(v))
    roots.extend(
        [
            Path(os.environ.get("SPELLVISION_MODELS", "").strip())
            if os.environ.get("SPELLVISION_MODELS", "").strip()
            else None,
        ]
    )
    roots = [r for r in roots if r is not None]
    subdirs = ("ipadapter", "ip_adapter", "IP-Adapter", "ip-adapter")
    name_hints = (
        "ip-adapter-plus_sdxl_vit-h",
        "ip-adapter-plus-face_sdxl_vit-h",
        "ip-adapter_sdxl",
        "ip-adapter-plus_sd15",
        "ip-adapter_sd15",
    )
    if not candidates:
        for root in roots:
            if not root.exists():
                continue
            for sub in subdirs:
                folder = root / sub
                if not folder.exists():
                    continue
                for hint in name_hints:
                    for ext in (".safetensors", ".bin"):
                        hit = folder / f"{hint}{ext}"
                        if hit.exists():
                            candidates.append(str(hit))
                for p in folder.rglob("*"):
                    if p.is_file() and "ip-adapter" in p.name.lower() and p.suffix.lower() in {".safetensors", ".bin"}:
                        candidates.append(str(p))
            if candidates:
                break

    if not candidates:
        return False, "no ip-adapter weights found under models/ipadapter"

    seen: set[str] = set()
    unique: list[str] = []
    for c in candidates:
        key = os.path.normcase(os.path.abspath(c))
        if key in seen:
            continue
        seen.add(key)
        if os.path.isfile(c):
            unique.append(c)

    if not unique:
        return False, "ip-adapter candidates missing on disk"

    weight = max(0.05, min(1.0, float(weight)))
    last_err = ""
    for path in unique[:6]:
        try:
            folder = str(Path(path).parent)
            name = Path(path).name
            try:
                pipe.load_ip_adapter(folder, subfolder="", weight_name=name)
            except TypeError:
                pipe.load_ip_adapter(folder, weight_name=name)
            if hasattr(pipe, "set_ip_adapter_scale"):
                try:
                    pipe.set_ip_adapter_scale(weight)
                except Exception:
                    pipe.set_ip_adapter_scale([weight])
            note = f"loaded {name} @ {weight:.2f}"
            logging.warning("IP-Adapter applied: %s", note)
            if emitter is not None and job is not None:
                try:
                    emitter.status(job, f"ip-adapter: {note}")
                except Exception:
                    pass
            return True, note
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            continue
    return False, f"load failed: {last_err[:160]}"


def maybe_apply_request_upscale(
    req: dict[str, Any],
    image_path: str,
    emitter: JobEmitter | None = None,
    job: JobRecord | None = None,
) -> str:
    """Optional post-gen upscale driven by UI payload (algorithmic or model).

    Algorithmic path uses PIL. Model path tries RealESRGAN/basicsr when present; otherwise
    falls back to lanczos with a warning. Never fabricates success.
    """
    enabled = bool(req.get("upscale_enabled"))
    method = str(req.get("upscale_method") or "none").strip().lower()
    if not enabled or method in {"", "none", "off", "false", "0"}:
        return image_path

    try:
        scale = float(req.get("upscale_scale") or 2.0)
    except (TypeError, ValueError):
        scale = 2.0
    scale = max(1.0, min(scale, 4.0))
    if scale <= 1.01 and method != "model":
        return image_path

    path = Path(image_path)
    if not path.is_file():
        return image_path

    if emitter is not None and job is not None:
        try:
            emitter.status(job, f"upscaling ×{scale:g} ({method})")
        except Exception:
            pass

    try:
        from PIL import Image as PILImage  # type: ignore
    except Exception as exc:  # pragma: no cover
        logging.warning("[upscale] PIL unavailable: %s", exc)
        return image_path

    try:
        with PILImage.open(path) as im:
            im = im.convert("RGB")
            w, h = im.size
            tw, th = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
            out = im

            if method == "model":
                model_name = str(req.get("upscale_model_name") or req.get("upscale_model") or "").strip()
                used_model = False
                # Best-effort RealESRGAN path; fall back cleanly.
                try:
                    # Optional dependency — many installs lack it.
                    from basicsr.archs.rrdbnet_arch import RRDBNet  # type: ignore
                    from realesrgan import RealESRGANer  # type: ignore

                    models_root = str(req.get("models_root") or "").strip()
                    model_path = model_name
                    if model_path and not Path(model_path).is_file() and models_root:
                        cand = Path(models_root) / "upscale_models" / model_path
                        if cand.is_file():
                            model_path = str(cand)
                    if model_path and Path(model_path).is_file():
                        net = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)
                        upsampler = RealESRGANer(scale=4, model_path=model_path, model=net, tile=0, half=False)
                        import numpy as np  # type: ignore

                        arr = np.array(im)[:, :, ::-1]  # RGB->BGR
                        output, _ = upsampler.enhance(arr, outscale=scale)
                        out = PILImage.fromarray(output[:, :, ::-1])
                        used_model = True
                except Exception as exc:
                    logging.warning("[upscale] model path failed (%s); falling back to lanczos", exc)

                if not used_model:
                    method = "lanczos"

            if method != "model":
                resample = {
                    "nearest": PILImage.Resampling.NEAREST,
                    "bilinear": PILImage.Resampling.BILINEAR,
                    "bicubic": PILImage.Resampling.BICUBIC,
                    "lanczos": PILImage.Resampling.LANCZOS,
                }.get(method, PILImage.Resampling.LANCZOS)
                out = im.resize((tw, th), resample)

            out_path = path.with_name(f"{path.stem}_up{scale:g}{path.suffix}")
            out.save(out_path, "PNG")
            # Prefer replacing original output so UI/history still point at the final asset.
            try:
                out_path.replace(path)
                final = str(path)
            except Exception:
                final = str(out_path)
                req["output"] = final
            logging.warning("[upscale] wrote %s via %s ×%s", final, method, scale)
            return final
    except Exception as exc:
        logging.warning("[upscale] failed: %s", exc)
        return image_path


def run_t2i(req: dict[str, Any], emitter: JobEmitter, job: JobRecord, active_job: ActiveJobHandle) -> dict[str, Any]:
    if _should_route_native_image({**req, "command": "t2i"}):
        raise RuntimeError(
            "This checkpoint is a native Comfy family (Krea 2 / Flux / …) and cannot load through "
            "diffusers from_single_file. Restart SpellVision so the worker picks up native routing."
        )
    emitter.status(job, "loading pipeline")
    transition_job(job, JobState.STARTING)
    emitter.emit_job_update(job)
    runtime_prep = _ws().prepare_runtime_for_request(req, emitter, job)

    pipe, _, device, dtype, detected, cache_hit, model_swap_cleanup = _ws().get_or_load_pipelines(req["model"], req.get("model_family"))
    raise_if_cancelled(active_job, emitter, "pipeline loading")

    lora_used = False
    lora_stats = {
        "lora_cache_hit": False,
        "lora_reloaded": False,
        "lora_cleared": False,
        "active_lora_path": None,
        "active_lora_scale": None,
    }
    lora_path, lora_scale = resolve_request_lora(req)
    if lora_path:
        emitter.status(job, "loading lora")
        lora_used, lora_stats = maybe_load_lora(pipe, lora_path, lora_scale, "t2i")
        raise_if_cancelled(active_job, emitter, "lora loading")
    else:
        reset_lora_state(pipe, "t2i")

    scheduler_stats = apply_sampler_and_scheduler(pipe, req)

    if device == "cuda":
        generator = torch.Generator(device="cuda").manual_seed(int(req["seed"]))
    else:
        generator = torch.Generator().manual_seed(int(req["seed"]))

    kwargs = build_generation_kwargs(
        req,
        generator,
        {
            "width": int(req["width"]),
            "height": int(req["height"]),
        },
        pipe=pipe,
    )
    attach_progress_callback(pipe, kwargs, req, emitter, job, active_job)

    transition_job(job, JobState.RUNNING)
    emitter.status(job, "running pipeline")
    raise_if_cancelled(active_job, emitter, "pipeline startup")

    start = time.perf_counter()
    result = pipe(**kwargs)
    elapsed = time.perf_counter() - start

    raise_if_cancelled(active_job, emitter, "pipeline completion")

    image = result.images[0]
    os.makedirs(os.path.dirname(req["output"]), exist_ok=True)
    if len(req["output"]) > 240:
        raise RuntimeError(f"Output path too long after queue/retry naming: {req['output']}")
    image.save(req["output"], "PNG")
    maybe_apply_request_upscale(req, req["output"], emitter, job)

    steps_per_sec = int(req["steps"]) / elapsed if elapsed > 0 else 0.0

    raise_if_cancelled(active_job, emitter, "metadata handoff")

    lora_cache_hit = bool(lora_stats.get("lora_cache_hit", False))
    lora_reloaded = bool(lora_stats.get("lora_reloaded", False))

    metadata_payload = _ws().save_metadata(
        req=req,
        image_path=req["output"],
        metadata_output=req["metadata_output"],
        backend_name=pipe.__class__.__name__,
        device=device,
        dtype=dtype,
        detected_pipeline=detected,
        lora_used=lora_used,
        elapsed=elapsed,
        steps_per_sec=steps_per_sec,
        job=job,
        cache_hit=cache_hit,
        model_swap_cleanup=model_swap_cleanup,
        lora_cache_hit=lora_cache_hit,
        lora_reloaded=lora_reloaded,
        queue_warm_reuse_expected=bool(req.get("queue_warm_reuse_expected")),
        queue_warm_reuse_source=req.get("queue_warm_reuse_source"),
        queue_affinity_signature=req.get("queue_affinity_signature"),
    )

    payload = {
        "ok": True,
        "cache_hit": cache_hit,
        "output": req["output"],
        "metadata_output": req["metadata_output"],
        "backend_name": pipe.__class__.__name__,
        "detected_pipeline": detected,
        "task_type": req.get("task_type", req.get("command", "unknown")),
        "generation_time_sec": round(elapsed, 2),
        "steps_per_sec": round(steps_per_sec, 2),
        "cuda_allocated_gb": round(torch.cuda.memory_allocated() / (1024 ** 3), 2) if torch.cuda.is_available() else 0.0,
        "cuda_reserved_gb": round(torch.cuda.memory_reserved() / (1024 ** 3), 2) if torch.cuda.is_available() else 0.0,
        "model_swap_cleanup": model_swap_cleanup,
        "model_cleanup_time_sec": model_swap_cleanup.get("cleanup_time_sec") if model_swap_cleanup else 0.0,
        "model_load_time_sec": model_swap_cleanup.get("model_load_time_sec") if model_swap_cleanup else None,
        "memory_after_load": model_swap_cleanup.get("memory_after_load") if model_swap_cleanup else None,
        "lora_cache_hit": lora_cache_hit,
        "lora_reloaded": lora_reloaded,
        "queue_warm_reuse_expected": bool(req.get("queue_warm_reuse_expected")),
        "queue_warm_reuse_source": req.get("queue_warm_reuse_source"),
        "queue_affinity_signature": req.get("queue_affinity_signature"),
        "sampler": req.get("sampler"),
        "scheduler": req.get("scheduler"),
        "scheduler_applied": bool(scheduler_stats.get("applied")),
        "scheduler_class": scheduler_stats.get("scheduler_class"),
        "active_adapters": active_adapter_names(pipe),
        "metadata": metadata_payload,
        "metadata_write_deferred": False,
        **_ws().output_finalization_contract(output_path if 'output_path' in locals() else req.get("output"), metadata_output if 'metadata_output' in locals() else req.get("metadata_output"), original_output=str(req.get("original_output") or ""), media_type=_ws().output_media_type_for_metadata(req, output_path if 'output_path' in locals() else req.get("output")), metadata_write_status=str(metadata_payload.get("metadata_write_status") or "written"), metadata_write_error=metadata_payload.get("metadata_write_error")),
        **_ws().runtime_prep_metadata(req),
    }

    complete_job(job, payload)
    emitter.emit_job_update(job)
    return payload


def run_i2i(req: dict[str, Any], emitter: JobEmitter, job: JobRecord, active_job: ActiveJobHandle) -> dict[str, Any]:
    emitter.status(job, "loading pipeline")
    transition_job(job, JobState.STARTING)
    emitter.emit_job_update(job)
    runtime_prep = _ws().prepare_runtime_for_request(req, emitter, job)

    _, pipe, device, dtype, detected, cache_hit, model_swap_cleanup = _ws().get_or_load_pipelines(req["model"], req.get("model_family"))
    raise_if_cancelled(active_job, emitter, "pipeline loading")

    lora_used = False
    lora_stats = {
        "lora_cache_hit": False,
        "lora_reloaded": False,
        "lora_cleared": False,
        "active_lora_path": None,
        "active_lora_scale": None,
    }
    lora_path, lora_scale = resolve_request_lora(req)
    if lora_path:
        emitter.status(job, "loading lora")
        lora_used, lora_stats = maybe_load_lora(pipe, lora_path, lora_scale, "i2i")
        raise_if_cancelled(active_job, emitter, "lora loading")
    else:
        reset_lora_state(pipe, "i2i")

    scheduler_stats = apply_sampler_and_scheduler(pipe, req)

    if device == "cuda":
        generator = torch.Generator(device="cuda").manual_seed(int(req["seed"]))
    else:
        generator = torch.Generator().manual_seed(int(req["seed"]))

    input_image = Image.open(req["input_image"]).convert("RGB")
    raise_if_cancelled(active_job, emitter, "input image preparation")

    # Resolve I2I strength / denoise. Character Studio "Reference freedom" sends
    # denoise_strength (higher = freer pose). Prefer explicit strength, then denoise_strength.
    strength_raw = req.get("strength", None)
    if strength_raw is None or str(strength_raw).strip() in {"", "None"}:
        strength_raw = req.get("denoise_strength", req.get("denoise", 0.6))
    try:
        strength = float(strength_raw)
    except Exception:
        strength = 0.6
    strength = max(0.05, min(0.99, strength))

    # pose_flexible: never clamp so hard that the photo locks the pose (floor 0.55).
    ref_mode = str(req.get("reference_mode") or "").strip().lower()
    if ref_mode in {"pose_flexible", "ipadapter_soft", "style"}:
        strength = max(strength, 0.55)

    ipadapter_weight = None
    try:
        if req.get("ipadapter_weight") is not None:
            ipadapter_weight = max(0.05, min(1.0, float(req.get("ipadapter_weight"))))
    except Exception:
        ipadapter_weight = None

    # Soft IP-Adapter path when available (diffusers IPAdapterMixin + ip_adapter weights on disk).
    # Never fails the job if missing — falls back to pure I2I denoise.
    ipadapter_applied = False
    ipadapter_note = ""
    if ref_mode in {"pose_flexible", "ipadapter_soft", "style"} or ipadapter_weight is not None:
        try:
            ipadapter_applied, ipadapter_note = maybe_apply_ipadapter(
                pipe,
                req,
                weight=ipadapter_weight if ipadapter_weight is not None else max(0.2, 1.0 - strength),
                emitter=emitter,
                job=job,
            )
        except Exception as exc:  # noqa: BLE001
            logging.warning("IP-Adapter soft path skipped: %s", exc)
            ipadapter_note = f"skipped: {exc}"

    kwargs = build_generation_kwargs(
        req,
        generator,
        {
            "image": input_image,
            "strength": strength,
        },
        pipe=pipe,
    )
    try:
        import inspect

        sig = inspect.signature(pipe.__call__)
        if ipadapter_applied and "ip_adapter_image" in sig.parameters:
            kwargs["ip_adapter_image"] = input_image
            if "ip_adapter_scale" in sig.parameters and ipadapter_weight is not None:
                kwargs["ip_adapter_scale"] = ipadapter_weight
    except Exception:
        pass

    attach_progress_callback(pipe, kwargs, req, emitter, job, active_job)

    transition_job(job, JobState.RUNNING)
    emitter.status(
        job,
        f"running pipeline (i2i strength={strength:.2f}"
        + (f", ipadapter={ipadapter_note}" if ipadapter_note else "")
        + ")",
    )
    raise_if_cancelled(active_job, emitter, "pipeline startup")

    start = time.perf_counter()
    result = pipe(**kwargs)
    elapsed = time.perf_counter() - start

    raise_if_cancelled(active_job, emitter, "pipeline completion")

    image = result.images[0]
    os.makedirs(os.path.dirname(req["output"]), exist_ok=True)
    if len(req["output"]) > 240:
        raise RuntimeError(f"Output path too long after queue/retry naming: {req['output']}")
    image.save(req["output"], "PNG")
    maybe_apply_request_upscale(req, req["output"], emitter, job)

    steps_per_sec = int(req["steps"]) / elapsed if elapsed > 0 else 0.0

    raise_if_cancelled(active_job, emitter, "metadata handoff")

    lora_cache_hit = bool(lora_stats.get("lora_cache_hit", False))
    lora_reloaded = bool(lora_stats.get("lora_reloaded", False))

    metadata_payload = _ws().save_metadata(
        req=req,
        image_path=req["output"],
        metadata_output=req["metadata_output"],
        backend_name=pipe.__class__.__name__,
        device=device,
        dtype=dtype,
        detected_pipeline=detected,
        lora_used=lora_used,
        elapsed=elapsed,
        steps_per_sec=steps_per_sec,
        job=job,
        cache_hit=cache_hit,
        model_swap_cleanup=model_swap_cleanup,
        lora_cache_hit=lora_cache_hit,
        lora_reloaded=lora_reloaded,
        queue_warm_reuse_expected=bool(req.get("queue_warm_reuse_expected")),
        queue_warm_reuse_source=req.get("queue_warm_reuse_source"),
        queue_affinity_signature=req.get("queue_affinity_signature"),
    )

    payload = {
        "ok": True,
        "cache_hit": cache_hit,
        "output": req["output"],
        "metadata_output": req["metadata_output"],
        "backend_name": pipe.__class__.__name__,
        "detected_pipeline": detected,
        "task_type": req.get("task_type", req.get("command", "unknown")),
        "generation_time_sec": round(elapsed, 2),
        "steps_per_sec": round(steps_per_sec, 2),
        "cuda_allocated_gb": round(torch.cuda.memory_allocated() / (1024 ** 3), 2) if torch.cuda.is_available() else 0.0,
        "cuda_reserved_gb": round(torch.cuda.memory_reserved() / (1024 ** 3), 2) if torch.cuda.is_available() else 0.0,
        "model_swap_cleanup": model_swap_cleanup,
        "model_cleanup_time_sec": model_swap_cleanup.get("cleanup_time_sec") if model_swap_cleanup else 0.0,
        "model_load_time_sec": model_swap_cleanup.get("model_load_time_sec") if model_swap_cleanup else None,
        "memory_after_load": model_swap_cleanup.get("memory_after_load") if model_swap_cleanup else None,
        "lora_cache_hit": lora_cache_hit,
        "lora_reloaded": lora_reloaded,
        "queue_warm_reuse_expected": bool(req.get("queue_warm_reuse_expected")),
        "queue_warm_reuse_source": req.get("queue_warm_reuse_source"),
        "queue_affinity_signature": req.get("queue_affinity_signature"),
        "sampler": req.get("sampler"),
        "scheduler": req.get("scheduler"),
        "scheduler_applied": bool(scheduler_stats.get("applied")),
        "scheduler_class": scheduler_stats.get("scheduler_class"),
        "active_adapters": active_adapter_names(pipe),
        **_ws().runtime_prep_metadata(req),
    }

    complete_job(job, payload)
    emitter.emit_job_update(job)
    return payload

