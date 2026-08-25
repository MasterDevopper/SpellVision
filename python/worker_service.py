from __future__ import annotations

import copy
import gc
import hashlib
import importlib
import inspect
import io
import json
import logging
import os
import re
import sys
import threading
import time
import traceback
import warnings
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Protocol
from queue import Queue
from pathlib import Path
import uuid

from comfy_bootstrap import bootstrap_comfy_runtime, default_comfy_python
from runtime_identity import resolve_comfy_python_from_request, resolve_comfy_root as resolve_identity_comfy_root
from comfy_runtime_manager import ComfyRuntimeManager
from memory_optimization import auto_select_memory_profile, build_paired_pipelines
from model_classification import classify_model, detect_image_pipeline_type
from family_operating_points import (
    family_operating_points_payload,
    operating_point_params,
    resolve_family_defaults,
    resolve_operating_point,
)
from history_schema import attach_mode_payload
from upscale_engine import graft_pixel_upscale, resolve_upscale_route
from model_registry import MODEL_FAMILIES
from video_family_contracts import (
    infer_video_family_from_text,
    normalize_video_family_id,
    video_family_contract,
    video_family_contracts_snapshot,
    video_family_pipeline_candidates,
)
from video_family_readiness import ltx_readiness_snapshot
from ltx_workflow_contract import ltx_test_workflow_contract_snapshot
from ltx_smoke_test_route import ltx_t2v_smoke_test_snapshot
from ltx_workflow_materialization import ltx_workflow_materialization_dry_run_snapshot
from ltx_workflow_graph_inspection import ltx_workflow_graph_inspection_snapshot
from ltx_prompt_api_adapter import ltx_prompt_api_conversion_adapter_snapshot
from ltx_requeue_draft_submission import ltx_requeue_draft_gated_submission_snapshot
from ltx_prompt_api_submission import ltx_prompt_api_gated_submission_snapshot
from ltx_queue_history_registry import read_recent_ltx_history, read_recent_ltx_queue_events
from ltx_ui_queue_history_contract import ltx_ui_queue_history_snapshot
from comfy_graph_converter import convert_ui_graph_to_api_prompt, is_ui_graph
from flux3_video import Flux3Cancelled, generate_flux3_video as submit_flux3_video

from comfy_graph_helpers import (
    _add_node,
    _build_clip_loader_node,
    _clip_loader_type_for_family,
    _comfy_ckpt_name_for_model,
    _comfy_class_inputs,
    _comfy_clip_name,
    _comfy_input_bucket,
    _comfy_input_choices,
    _comfy_input_info,
    _comfy_required_inputs,
    _comfy_unet_name,
    _comfy_unet_name_for_model,
    _comfy_vae_name,
    _emit_wan_lora_chain,
    _filename_prefix_from_output,
    _first_available_class,
    _int_or_default,
    _path_after_named_dir,
    _set_if_allowed,
    _sv_basename,
    _sv_choice_or_default,
    _sv_choose_comfy_choice,
    _sv_comfy_input_choices,
    _sv_is_fp8_scaled_name,
    _sv_set_default_required_inputs,
    _sv_video_lora_name,
    _first_nonempty_text,
    _video_stack_basename,
    _video_stack_first,
    _video_model_stack_from_request,
    _first_stack_value,
    _stack_missing_parts,
    _video_family_from_request_parts,
    _input_default_choice,
    _wan_lora_stack_entries,
)
from native_image_graphs import (
    _build_anima_image_prompt,
    _build_flux_image_prompt,
    _build_krea2_image_prompt,
    _build_lumina_image_prompt,
    _build_native_image_prompt,
    _build_pixart_image_prompt,
    _build_zimage_image_prompt,
    _flux_checkpoint_incompatible_reason,
    _flux_denoise_from_request,
    _flux_guidance_from_request,
    _native_image_family,
    _resolve_native_image_stack,
    _should_route_native_image,
    NATIVE_IMAGE_FAMILIES,
)
from ltx_prompt_api_jobs import (
    _ltx_prompt_api_job_payload,
    _normalize_ltx_prompt_api_request,
    _queue_ltx_execution_command,
    run_ltx_prompt_api_queued_job,
)
from worker_metadata import (
    _file_size_bytes,
    build_history_entry,
    build_metadata_payload,
    output_finalization_contract,
    output_media_type_for_metadata,
    persist_video_history_entry,
    save_metadata,
    video_history_snapshot,
)
from worker_durable_state import atomic_write_json, worker_state_root
from worker_runtime import (
    CACHE_LOCK,
    MODEL_CACHE,
    VIDEO_RUNTIME_CACHE,
    VIDEO_RUNTIME_LOCK,
    active_video_runtime_signature_for_command,
    build_pipelines,
    cleanup_for_model_swap,
    clear_cuda_memory,
    cuda_memory_snapshot,
    get_or_load_pipelines,
    handle_runtime_memory_control_command,
    invalidate_video_runtime_cache_for_failure,
    prepare_runtime_for_request,
    reset_video_runtime_cache,
    runtime_memory_ack,
    runtime_memory_status_snapshot,
    runtime_prep_metadata,
    unload_cached_pipelines,
    update_video_runtime_cache_from_result,
)
from workflow_library_commands import (
    handle_check_workflow_launch_readiness_command,
    handle_delete_workflow_profile_command,
    handle_discover_comfy_workflows_command,
    handle_import_workflow_command,
    handle_list_workflow_profiles_command,
    handle_retry_workflow_dependencies_command,
)
from image_runners import (
    apply_sampler_and_scheduler,
    attach_progress_callback,
    build_generation_kwargs,
    ensure_lora_adapter_loaded,
    get_cached_lora_state,
    maybe_apply_ipadapter,
    maybe_apply_request_upscale,
    maybe_load_lora,
    reset_lora_state,
    run_i2i,
    run_t2i,
)
from comfy_prompt_client import (
    _apply_common_comfy_overrides,
    _apply_workflow_slot_bindings,
    _comfy_image_ref,
    _comfy_object_info,
    _comfy_status_is_completed,
    _download_comfy_asset,
    _extract_comfy_asset,
    _native_prompt_debug_path,
    _poll_comfy_history,
    _read_http_error_body,
    _submit_comfy_prompt,
    _upload_comfy_image,
    invalidate_comfy_object_info,
    _validate_comfy_prompt_against_object_info,
    _write_native_prompt_debug_file,
    request_comfy_free_memory,
    run_comfy_workflow,
)
from native_runners import (
    _load_native_video_pipeline,
    _native_video_kwargs,
    run_flux3_video,
    run_native_image,
    run_native_split_stack_video,
    run_native_video,
)
from native_video_graphs import (
    NATIVE_VIDEO_FAMILY_PLUGINS,
    NativeFamilyPlugin,
    VIDEO_HIGH_MODEL_KEYS,
    VIDEO_LOW_MODEL_KEYS,
    VIDEO_PRIMARY_MODEL_KEYS,
    _build_native_hunyuan_video_prompt,
    _build_native_hunyuan_wrapper_i2v_prompt,
    _build_native_ltx_two_stage_prompt,
    _build_native_ltx_video_prompt,
    _build_native_mochi_video_prompt,
    _build_native_split_video_prompt,
    _build_native_wan_core_video_prompt,
    _build_native_wan_dual_noise_video_prompt,
    _build_native_wan_split_video_prompt,
    _canonical_native_video_family,
    _hunyuan_video_build,
    _infer_native_video_family,
    _infer_native_video_family_key,
    _is_kijai_hunyuan_format,
    _is_split_video_stack_request,
    _is_wan_dual_noise_request,
    _ltx_route_for,
    _ltx_video_build,
    _mochi_video_build,
    _native_video_model_reference,
    _native_video_pipeline_candidates,
    _native_video_plugin_for,
    _path_looks_high_noise,
    _path_looks_low_noise,
    _preferred_video_vae_name,
    _prepare_native_video_adapter_request,
    _raise_if_unvalidated_native_video_family,
    _resolve_native_video_stack,
    _should_use_native_wan_core_route,
    _sv_add_wan_empty_embeds_node,
    _sv_core_choice_or_default,
    _sv_core_wan_choice,
    _sv_core_wan_clip_name,
    _sv_core_wan_clip_vision_name,
    _sv_core_wan_vae_name,
    _sv_video_primary_name,
    _sv_video_text_encoder_name,
    _sv_video_vae_name,
    _wan_dual_expert_path,
    _wan_expert_task_variant,
    _wan_vae_preference,
    _wan_vae_preference_for_version,
    _wan_vae_version_marker,
    _wan_video_build,
)

from worker_service_state import (
    ACTIVE_JOBS,
    ACTIVE_JOBS_LOCK,
    ActiveJobHandle,
    JobCancelledError,
    JobEmitter,
    JobError,
    JobProgress,
    JobRecord,
    JobResult,
    JobState,
    JobTimestamps,
    QUEUE_TERMINAL_STATES,
    QueueItemState,
    TERMINAL_STATES,
    VALID_TRANSITIONS,
    cancel_job,
    complete_job,
    create_job,
    fail_job,
    get_active_job,
    queue_state_from_job_state,
    raise_if_cancelled,
    register_active_job,
    request_job_cancel,
    set_job_message,
    transition_job,
    unregister_active_job,
    update_job_progress,
    utc_now_iso,
)
import urllib.error
import urllib.parse
import urllib.request

warnings.filterwarnings("ignore", message="A matching Triton is not available*")
warnings.filterwarnings("ignore", category=FutureWarning, module="diffusers")
try:
    from requests.exceptions import RequestsDependencyWarning
except Exception:
    RequestsDependencyWarning = None
if RequestsDependencyWarning is not None:
    warnings.filterwarnings("ignore", category=RequestsDependencyWarning)

import torch
from PIL import Image


JOB_ARCHIVE: dict[str, dict[str, Any]] = {}
JOB_ARCHIVE_ORDER: list[str] = []
JOB_ARCHIVE_LOCK = threading.Lock()
MAX_ARCHIVED_JOBS = 200
JOB_ARCHIVE_PATH = worker_state_root() / "job_archive.json"


def _persist_job_archive_unlocked() -> None:
    entries = [
        copy.deepcopy(JOB_ARCHIVE[job_id])
        for job_id in JOB_ARCHIVE_ORDER
        if job_id in JOB_ARCHIVE
    ][-MAX_ARCHIVED_JOBS:]
    atomic_write_json(
        JOB_ARCHIVE_PATH,
        {
            "type": "spellvision_job_archive",
            "schema_version": 1,
            "updated_at": utc_now_iso(),
            "entries": entries,
        },
    )


def load_job_archive() -> None:
    with JOB_ARCHIVE_LOCK:
        JOB_ARCHIVE.clear()
        JOB_ARCHIVE_ORDER.clear()
        if not JOB_ARCHIVE_PATH.is_file():
            return
        try:
            payload = json.loads(JOB_ARCHIVE_PATH.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return
        entries = payload.get("entries") if isinstance(payload, dict) else None
        if not isinstance(entries, list):
            return
        for raw_entry in entries[-MAX_ARCHIVED_JOBS:]:
            if not isinstance(raw_entry, dict):
                continue
            job_id = str(raw_entry.get("job_id") or "").strip()
            request = raw_entry.get("request")
            if not job_id or not isinstance(request, dict):
                continue
            JOB_ARCHIVE[job_id] = copy.deepcopy(raw_entry)
            JOB_ARCHIVE_ORDER.append(job_id)


load_job_archive()


COMFY_RUNTIME_MANAGER: ComfyRuntimeManager | None = None
COMFY_RUNTIME_MANAGER_LOCK = threading.Lock()






def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return fallback



LTX_PROMPT_API_DISPATCH_COMMANDS = {
    "ltx_prompt_api_gated_submission",
    "ltx_prompt_api_submit",
    "ltx_submit_prompt_api",
    "ltx_prompt_api_submit_and_capture",
    "ltx_prompt_api_submit_wait",
    "video_family_prompt_api_gated_submission",
}


# _looks_like_ltx_prompt_api_request was removed in the native-LTX migration (Step 4).
# Its only caller -- the run_native_video redirect -- is gone, so LTX requests now flow
# to the native gate. Explicit prompt-api dispatch is matched by exact command name via
# LTX_PROMPT_API_DISPATCH_COMMANDS, never by a broad substring predicate (which also
# matched Wan, given the unconditional LTX field injection from the UI).




def _queue_display_command_for_execution(req: dict[str, Any], execution_command: str, fallback: str = "") -> str:
    display_commands = {"t2i", "i2i", "t2v", "i2v", "comfy_workflow"}

    for key in ("queue_display_command", "source_generation_mode", "generation_mode", "source_command", "task_type", "mode", "video_request_kind"):
        command = str(req.get(key) or "").strip().lower()
        if command in display_commands:
            return command

    fallback = str(fallback or "").strip().lower()
    if fallback in display_commands:
        return fallback

    if execution_command == "ltx_prompt_api_gated_submission":
        return "t2v"

    return execution_command


def canonical_command(req: dict[str, Any]) -> str:
    """Single accessor for the PLAIN dispatch reads (Doc 21 C3, scope narrowed on live inspection).

    Encodes EXACTLY the TCP-direct dispatcher's current read -- ``req["command"]`` else
    ``req["action"]``, ``.strip()`` (NOT lowercased, matching ``WorkerTCPHandler.handle`` today).
    That is the only precedence the plain dispatch reads observe; the six-key aliasing and the LTX
    detection heuristic (``_queue_ltx_execution_command``, an ordered-precedence membership +
    substring-haystack check a key accessor cannot replace) are deliberately NOT folded in here --
    each is its own later pass. The QUEUE dispatcher reads ``item.command`` (a QueueItem field, equal
    to ``req["command"]`` only post-enqueue) and is intentionally NOT routed through this accessor:
    doing so would change behavior when the two differ (pinned by test_dispatch_characterization's
    ``test_queue_reads_item_command_not_req_command``), so it stays as-is and is flagged at the call site.
    """
    return str(req.get("command") or req.get("action") or "").strip()


def first_unencodable_prompt_field(req: dict[str, Any]) -> str | None:
    """Return a LOUD error message if any prompt-bearing field carries text that is not
    UTF-8-encodable (lone UTF-16 surrogates = encoding corruption), else None.

    This is the request-path backstop for the worker_client.py stdin-UTF-8 fix. A mangled CJK
    prompt must FAIL the job with a clear message -- never be silently stripped (a silently-mangled
    negative renders subtly wrong and the user never knows) and never be allowed to reach the umt5
    SentencePiece tokenizer, which dies with the opaque 'TypeError: not a string' mid-render.
    Checked once here, not per-builder.
    """
    def bad(value: Any) -> bool:
        if not isinstance(value, str):
            return False
        try:
            value.encode("utf-8")
            return False
        except UnicodeEncodeError:
            return True

    for key in ("prompt", "negative_prompt", "prompt_2", "negative_prompt_2"):
        if bad(req.get(key)):
            return (
                f"The {key.replace('_', ' ')} contains invalid characters (encoding corruption -- "
                "lone UTF-16 surrogates, not valid UTF-8). This is a text-encoding bug, not your "
                "input. Re-enter the prompt; if it persists, report it."
            )
    for value in req.get("prompts") or []:
        if bad(value):
            return (
                "A batch prompt contains invalid characters (encoding corruption -- lone UTF-16 "
                "surrogates, not valid UTF-8). This is a text-encoding bug, not your input."
            )
    return None


def dispatch_generation(command: str, req: dict[str, Any], emitter: JobEmitter, job: JobRecord, active_job: ActiveJobHandle) -> Any:
    """The single generation dispatcher (Doc 21 C1). BOTH entry points route here with an
    ALREADY-RESOLVED command -- the queue passes ``item.command``, the TCP handler passes
    ``canonical_command(req)`` -- it does NOT re-derive the command (the two sources are distinct and
    must stay distinct; pinned by test_dispatch_characterization). Encodes the UNION of the correct forks:
      t2i / i2i        -> _should_route_native_image(req) ? run_native_image : run_t2i / run_i2i
      comfy_workflow   -> run_comfy_workflow
      t2v / i2v        -> explicit FLUX.3 API ? run_flux3_video : workflow binding ? run_comfy_workflow : run_native_video
    The t2i/i2i native-image fork is the branch the TCP-direct path historically LACKED -- collapsing
    onto this function fixes that divergence (behavior-fixing for the TCP path, identical for the queue).
    noop_slow (a non-generation test command) and ltx_prompt_api_gated_submission (resolved from
    execution_command) are NOT part of generation dispatch and stay at their call sites.
    """
    if command == "t2i":
        # A workflow launch keeps its display command (t2i) but must run through ComfyUI, not the
        # native diffusers path -- mirror the t2v/i2v workflow-binding fork below. Without this a
        # t2i workflow "Use workflow"/Flows Launch dispatches to run_t2i and dies on KeyError('model').
        if request_has_workflow_binding(req):
            return run_comfy_workflow(req, emitter, job, active_job)
        if _should_route_native_image(req):
            return run_native_image(req, emitter, job, active_job)
        return run_t2i(req, emitter, job, active_job)
    if command == "i2i":
        if request_has_workflow_binding(req):
            return run_comfy_workflow(req, emitter, job, active_job)
        if _should_route_native_image(req):
            return run_native_image(req, emitter, job, active_job)
        return run_i2i(req, emitter, job, active_job)
    if command == "comfy_workflow":
        return run_comfy_workflow(req, emitter, job, active_job)
    if command in {"t2v", "i2v"}:
        if _infer_native_video_family(req) == "flux3":
            return run_flux3_video(req, emitter, job, active_job)
        if request_has_workflow_binding(req):
            return run_comfy_workflow(req, emitter, job, active_job)
        return run_native_video(req, emitter, job, active_job)
    if command in {"i23d", "t23d", "gen3d"}:
        # Image/Text-to-3D: ComfyUI workflow only. Never spawn external Pixal/Trellis CLIs
        # (they OOM/crash the host). Require an explicit workflow binding.
        if request_has_workflow_binding(req):
            return run_comfy_workflow(req, emitter, job, active_job)
        raise RuntimeError(
            "i23d requires a ComfyUI workflow binding (import a Trellis.2 / Pixal3D / Hunyuan3D "
            "workflow in Flows, then launch it). External spike processes are disabled for stability."
        )
    if command == "clothes_only":
        from clothes_only import run_clothes_only_job

        return run_clothes_only_job(req, emitter, job, active_job)
    if command == "garment_shrinkwrap":
        from garment_shrinkwrap import run_garment_shrinkwrap_job

        return run_garment_shrinkwrap_job(req, emitter, job, active_job)
    if command == "krea2_regional_inpaint":
        try:
            import krea2_regional_inpaint as _krea2_regional_inpaint  # noqa: F401
        except ImportError as exc:
            raise RuntimeError("krea2_regional_inpaint module missing") from exc
        inpaint_req = dict(req)
        inpaint_req["command"] = "i2i"
        mask = str(
            inpaint_req.get("inpaint_mask_comfy_name")
            or inpaint_req.get("mask")
            or inpaint_req.get("mask_image")
            or ""
        ).strip()
        if not mask:
            raise RuntimeError("krea2_regional_inpaint requires a mask")
        if not inpaint_req.get("inpaint_mask_comfy_name"):
            inpaint_req["inpaint_mask_comfy_name"] = mask
        return run_native_image(inpaint_req, emitter, job, active_job)
    if command == "look_complete":
        try:
            from look_completion import run_look_complete_job
        except ImportError as exc:
            raise RuntimeError("look_completion module missing") from exc
        return run_look_complete_job(req, emitter, job, active_job)
    raise RuntimeError(f"Unsupported generation command: {command!r}")



def _video_request_command(req: dict[str, Any]) -> str:
    return str(
        req.get("worker_command")
        or req.get("execution_command")
        or req.get("dispatch_command")
        or req.get("command")
        or req.get("task_command")
        or req.get("task_type")
        or req.get("workflow_task_command")
        or ""
    ).strip().lower()



def is_video_request(req: dict[str, Any], output_path: str | None = None) -> bool:
    command = _video_request_command(req)
    media_type = str(req.get("workflow_media_type") or req.get("media_type") or "").strip().lower()
    stack_kind = str(req.get("native_video_stack_kind") or req.get("video_stack_kind") or "").strip().lower()
    output = str(output_path or req.get("output") or req.get("workflow_media_output") or "").strip().lower()
    return (
        command in {"t2v", "i2v"}
        or media_type == "video"
        or bool(stack_kind)
        or output.endswith((".mp4", ".mov", ".webm", ".mkv", ".avi", ".gif"))
    )


def video_duration_label(frames: int, fps: int) -> str:
    if frames <= 0 or fps <= 0:
        return "unknown"
    seconds = float(frames) / float(fps)
    return f"{frames} frames @ {fps} fps ({seconds:.1f}s)"


def video_input_image_for_request(req: dict[str, Any]) -> str:
    return _first_nonempty_text(
        req.get("video_input_image"),
        req.get("input_keyframe"),
        req.get("keyframe_image"),
        req.get("source_image"),
        req.get("input_image"),
    )




VIDEO_VAE_KEYS = ("vae", "vae_path", "vae_name")
VIDEO_TEXT_ENCODER_KEYS = ("text_encoder", "text_encoder_path", "clip", "clip_path", "text_encoder_2_path")


def _video_stack_summary_for_details(stack: dict[str, Any]) -> str:
    if not stack:
        return ""

    low = _video_stack_basename(_video_stack_first(stack, *VIDEO_LOW_MODEL_KEYS))
    high = _video_stack_basename(_video_stack_first(stack, *VIDEO_HIGH_MODEL_KEYS))
    primary = _video_stack_basename(_video_stack_first(stack, *VIDEO_PRIMARY_MODEL_KEYS))

    if low and high:
        return f"low={low} • high={high}"
    if high:
        return f"high={high}"
    if low:
        return f"low={low}"
    if primary:
        return primary
    return "configured"



def _video_family_contract_payload(family: str) -> dict[str, Any]:
    contract = video_family_contract(family)
    # Phase 3a: ship the family's operating points so the UI can render a fast/quality selector
    # GENERICALLY (no family names in the UI). Keyed to the CANONICAL/flagship route per family
    # (dual-noise for Wan, where fast/quality live); route-specific single-point configs stay internal.
    # Empty for a family with no table row (LTX is template-driven; cogvideox/mochi/workflow have none).
    ops = family_operating_points_payload(normalize_video_family_id(family))
    return {
        "video_family_display_name": contract.display_name,
        "video_family_validation_status": contract.validation_status,
        "video_family_validated": contract.validated,
        "video_family_production_ready": contract.production_ready,
        "video_family_backend_route": contract.backend_route,
        "video_family_contract_stack_kind": contract.stack_kind,
        "video_family_required_components": list(contract.required_components),
        "video_family_optional_components": list(contract.optional_components),
        "video_family_history_label_style": contract.history_label_style,
        "video_family_runtime_affinity_fields": list(contract.runtime_affinity_fields),
        "video_family_readiness_notes": list(contract.readiness_notes),
        "video_family_contract_version": contract.to_payload().get("schema_version", 1),
        "video_family_operating_points": ops["operating_points"],
        "video_family_default_operating_point": ops["default_operating_point"],
        "video_family_samplers": ops.get("samplers", []),
        "video_family_schedulers": ops.get("schedulers", []),
        "video_family_default_sampler": ops.get("default_sampler", ""),
        "video_family_default_scheduler": ops.get("default_scheduler", ""),
    }


def video_request_metadata_from_request(req: dict[str, Any]) -> dict[str, Any]:
    stack = req.get("video_model_stack") or req.get("model_stack") or {}
    if not isinstance(stack, dict):
        stack = {}

    frames = _safe_int(req.get("frames") or req.get("num_frames") or req.get("frame_count"), 0)
    fps = _safe_int(req.get("fps"), 0)
    width = _safe_int(req.get("width"), 0)
    height = _safe_int(req.get("height"), 0)
    family = _video_family_from_request_parts(req, stack)
    family_contract = video_family_contract(family)
    stack_kind = _first_nonempty_text(
        req.get("native_video_stack_kind"),
        req.get("video_stack_kind"),
        stack.get("stack_kind"),
        stack.get("stack_mode"),
        family_contract.stack_kind,
    )
    stack_mode = _first_nonempty_text(req.get("video_stack_mode"), stack.get("stack_mode"), stack_kind)
    low_model = _video_stack_first(stack, *VIDEO_LOW_MODEL_KEYS)
    high_model = _video_stack_first(stack, *VIDEO_HIGH_MODEL_KEYS)
    primary_model = _video_stack_first(stack, *VIDEO_PRIMARY_MODEL_KEYS)
    vae_model = _video_stack_first(stack, *VIDEO_VAE_KEYS)
    text_encoder = _video_stack_first(stack, *VIDEO_TEXT_ENCODER_KEYS)
    input_image = video_input_image_for_request(req)
    duration_seconds = round(float(frames) / float(fps), 3) if frames > 0 and fps > 0 else 0.0

    return {
        "video_request_kind": _video_request_command(req) or str(req.get("video_request_kind") or "video"),
        "video_family": family,
        "video_stack_kind": stack_kind,
        "video_stack_mode": stack_mode,
        "video_stack_ready": bool(req.get("video_stack_ready", stack.get("stack_ready", False))),
        "video_model_stack_summary": _video_stack_summary_for_details(stack),
        "video_low_model": low_model,
        "video_low_model_name": _video_stack_basename(low_model),
        "video_high_model": high_model,
        "video_high_model_name": _video_stack_basename(high_model),
        "video_primary_model": primary_model,
        "video_primary_model_name": _video_stack_basename(primary_model),
        "video_vae": vae_model,
        "video_vae_name": _video_stack_basename(vae_model),
        "video_text_encoder": text_encoder,
        "video_text_encoder_name": _video_stack_basename(text_encoder),
        "video_width": width,
        "video_height": height,
        "video_resolution": f"{width}x{height}" if width > 0 and height > 0 else "",
        "video_frames": frames,
        "video_frame_count": frames,
        "video_fps": fps,
        "video_duration_seconds": duration_seconds,
        "video_duration_label": video_duration_label(frames, fps),
        "video_has_input_image": bool(input_image),
        "video_input_image": input_image,
        "video_input_name": os.path.basename(input_image) if input_image else "",
        **_video_family_contract_payload(family),
    }


def video_completion_diagnostics(
    req: dict[str, Any],
    *,
    backend_type: str,
    backend_name: str,
    output_path: str | None = None,
    metadata_output: str | None = None,
    prompt_id: str | None = None,
) -> dict[str, Any]:
    if not is_video_request(req, output_path):
        return {}

    details = video_request_metadata_from_request(req)
    output = _first_nonempty_text(output_path, req.get("output"), req.get("workflow_media_output"))
    metadata_path = _first_nonempty_text(metadata_output, req.get("metadata_output"))
    request_kind = str(details.get("video_request_kind") or _video_request_command(req) or "video").strip().lower()
    input_name = str(details.get("video_input_name") or "").strip()
    family = str(details.get("video_family") or "").strip()

    details.update({
        "video_backend_type": backend_type,
        "video_backend_name": backend_name,
        "video_validated_backend": video_family_contract(family).production_ready if family else backend_type == "comfy_workflow",
        "video_output": output,
        "output_video": output,
        "video_path": output,
        "video_metadata_output": metadata_path,
        "video_completion_summary": (f"Image-to-video complete from keyframe {input_name}" if request_kind == "i2v" and input_name else ("Text-to-video complete" if request_kind == "t2v" else "Video generation complete")),
        "video_prompt_id": prompt_id or "",
    })
    return details


def comfy_waiting_message(req: dict[str, Any], elapsed_seconds: float) -> str:
    if is_video_request(req):
        frames = _safe_int(req.get("frames") or req.get("num_frames") or req.get("frame_count"), 0)
        fps = _safe_int(req.get("fps"), 0)
        timing = video_duration_label(frames, fps)
        stack_kind = _first_nonempty_text(
            req.get("native_video_stack_kind"),
            req.get("video_stack_kind"),
            (req.get("video_model_stack") or {}).get("stack_kind") if isinstance(req.get("video_model_stack"), dict) else "",
        )
        stack_text = f" • {stack_kind}" if stack_kind else ""
        input_image = video_input_image_for_request(req)
        input_name = os.path.basename(input_image) if input_image else ""
        source_text = f" • keyframe {input_name}" if input_name else ""
        request_kind = str(req.get("video_request_kind") or _video_request_command(req) or "video").strip().lower()
        mode_text = "image-to-video" if request_kind == "i2v" or input_name else "text-to-video"
        return f"waiting for ComfyUI {mode_text} render ({int(elapsed_seconds)}s • {timing}{stack_text}{source_text})"
    return f"waiting for ComfyUI ({int(elapsed_seconds)}s)"





from worker_queue import (
    QueueItem,
    QueueItemProgress,
    QueueItemTimestamps,
    QueueManager,
)



QUEUE_MANAGER = QueueManager()




def normalize_video_input_fields(req: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(req, dict):
        return req

    def _first(*keys: str) -> str:
        for key in keys:
            value = str(req.get(key) or "").strip()
            if value:
                return value
        return ""

    command = str(
        req.get("command")
        or req.get("task_command")
        or req.get("task_type")
        or req.get("workflow_task_command")
        or ""
    ).strip().lower()
    media_type = str(req.get("workflow_media_type") or req.get("media_type") or "").strip().lower()
    stack_kind = str(req.get("native_video_stack_kind") or req.get("video_stack_kind") or "").strip().lower()
    is_video_context = command in {"t2v", "i2v", "comfy_workflow"} or media_type == "video" or bool(stack_kind)

    input_image = _first(
        "video_input_image",
        "input_keyframe",
        "keyframe_image",
        "source_image",
        "i2v_source_image",
        "input_image",
    )

    if input_image:
        for key in ("input_image", "video_input_image", "input_keyframe", "keyframe_image", "source_image", "i2v_source_image"):
            req[key] = input_image
        req["video_has_input_image"] = True
        req.setdefault("video_input_name", os.path.basename(input_image))
        req.setdefault("video_request_kind", "i2v" if is_video_context else str(req.get("video_request_kind") or ""))
    elif command == "i2v" or str(req.get("video_request_kind") or "").strip().lower() == "i2v":
        req.setdefault("video_has_input_image", False)
        req.setdefault("video_request_kind", "i2v")

    return req

def clone_request_snapshot(req: dict[str, Any]) -> dict[str, Any]:
    return normalize_video_input_fields(copy.deepcopy(req))


_GENERATED_SUFFIX_RE = re.compile(
    r"(?:_queue_[A-Za-z0-9_-]+|_retry\d{2,}|_retry_\d{8}_\d{6}|_job_[A-Za-z0-9_-]+)+$"
)


def strip_generated_suffixes(stem: str) -> str:
    return _GENERATED_SUFFIX_RE.sub("", stem)



def normalized_lora_path(lora_path: str | None) -> str:
    value = str(lora_path or "").strip()
    return os.path.abspath(value) if value else ""


def _video_affinity_model_token(req: dict[str, Any]) -> str:
    details = video_request_metadata_from_request(req)
    parts = [
        f"family={details.get('video_family') or 'unknown'}",
        f"kind={details.get('video_stack_kind') or 'unknown'}",
    ]
    for label, key in (
        ("low", "video_low_model_name"),
        ("high", "video_high_model_name"),
        ("primary", "video_primary_model_name"),
        ("vae", "video_vae_name"),
        ("text", "video_text_encoder_name"),
    ):
        value = str(details.get(key) or "").strip()
        if value:
            parts.append(f"{label}={value}")
    return ";".join(parts)


def affinity_signature_for_request(req: dict[str, Any]) -> str:
    command = str(req.get("command") or req.get("task_command") or "").strip().lower()
    lora = normalized_lora_path(req.get("lora"))
    try:
        lora_scale = float(req.get("lora_scale", 1.0))
    except Exception:
        lora_scale = 1.0

    if is_video_request(req):
        return f"{command}|video:{_video_affinity_model_token(req)}|{lora}|{lora_scale:.4f}"

    model = str(req.get("model") or "").strip()
    return f"{command}|{model}|{lora}|{lora_scale:.4f}"


def affinity_summary_for_request(req: dict[str, Any]) -> str:
    command = str(req.get("command") or req.get("task_command") or "").strip().lower()
    lora = normalized_lora_path(req.get("lora"))
    lora_scale = float(req.get("lora_scale", 1.0) or 1.0)
    lora_name = os.path.basename(lora) if lora else "none"

    if is_video_request(req):
        details = video_request_metadata_from_request(req)
        family = str(details.get("video_family") or "Video").strip() or "Video"
        stack = str(details.get("video_model_stack_summary") or _video_affinity_model_token(req)).strip()
        duration = str(details.get("video_duration_label") or "").strip()
        duration_part = f" | {duration}" if duration and duration != "unknown" else ""
        return f"{command.upper()} | {family} | {stack}{duration_part} | LoRA {lora_name} @ {lora_scale:.2f}"

    model = str(req.get("model") or "").strip()
    model_name = os.path.basename(model) if os.path.exists(model) else model
    return f"{command.upper()} | {model_name} | LoRA {lora_name} @ {lora_scale:.2f}"


def active_affinity_signature_for_command(command: str) -> str | None:
    command = str(command or "").strip().lower()
    if command in {"t2v", "i2v"}:
        return active_video_runtime_signature_for_command(command)

    with CACHE_LOCK:
        model_key = MODEL_CACHE.get("key")
    if not model_key:
        return None

    cached_path, cached_scale = get_cached_lora_state(command if command in {"t2i", "i2i"} else "t2i")
    lora_path = normalized_lora_path(cached_path)
    scale = float(cached_scale) if cached_scale is not None else 1.0
    return f"{command}|{model_key}|{lora_path}|{scale:.4f}"


def queue_warm_reuse_prediction(req: dict[str, Any], previous_signature: str | None = None) -> tuple[bool, str | None, str]:
    item_signature = affinity_signature_for_request(req)
    command = str(req.get("command") or req.get("task_command") or "").strip().lower()
    active_signature = active_affinity_signature_for_command(command)
    is_video = is_video_request(req)

    if active_signature and active_signature == item_signature:
        return True, "video-warm-cache" if is_video else "warm-cache", item_signature
    if previous_signature and previous_signature == item_signature:
        return True, "adjacent-video-stack" if is_video else "adjacent-queue", item_signature
    return False, None, item_signature


def safe_unique_output_paths(
    base_output: str,
    *,
    queue_item_id: str | None = None,
    retry_count: int = 0,
    original_metadata_output: str | None = None,
) -> tuple[str, str]:
    output_path = Path(base_output)
    parent = output_path.parent
    suffix = output_path.suffix or ".png"

    clean_stem = strip_generated_suffixes(output_path.stem)

    suffix_parts: list[str] = []
    if queue_item_id:
        suffix_parts.append(queue_item_id)
    if retry_count > 0:
        suffix_parts.append(f"retry{retry_count:02d}")

    new_stem = clean_stem
    if suffix_parts:
        new_stem = f"{clean_stem}_{'_'.join(suffix_parts)}"

    if len(new_stem) > 120:
        new_stem = new_stem[:120]

    image_output = str(parent / f"{new_stem}{suffix}")

    if original_metadata_output:
        metadata_parent = Path(original_metadata_output).parent
    else:
        metadata_parent = parent
    metadata_output = str(metadata_parent / f"{new_stem}.json")

    return image_output, metadata_output


def build_retry_output_path(base_output: str) -> str:
    retry_output, _ = safe_unique_output_paths(
        base_output,
        retry_count=1,
    )
    return retry_output


def build_retry_metadata_path(metadata_output: str | None, retry_output: str) -> str:
    _, retry_metadata = safe_unique_output_paths(
        retry_output,
        original_metadata_output=metadata_output,
    )
    return retry_metadata


def _file_mtime_iso(path: str) -> str | None:
    try:
        stat = os.stat(path)
    except Exception:
        return None
    return datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()


def archive_job(job: "JobRecord", request_snapshot: dict[str, Any]) -> None:
    entry = {
        "job_id": job.job_id,
        "command": job.command,
        "state": job.state.value,
        "request": clone_request_snapshot(request_snapshot),
        "result": asdict(job.result) if job.result else None,
        "error": asdict(job.error) if job.error else None,
        "timestamps": asdict(job.timestamps),
        "source_job_id": job.source_job_id,
        "retry_count": job.retry_count,
    }
    with JOB_ARCHIVE_LOCK:
        JOB_ARCHIVE[job.job_id] = entry
        if job.job_id in JOB_ARCHIVE_ORDER:
            JOB_ARCHIVE_ORDER.remove(job.job_id)
        JOB_ARCHIVE_ORDER.append(job.job_id)
        while len(JOB_ARCHIVE_ORDER) > MAX_ARCHIVED_JOBS:
            stale_id = JOB_ARCHIVE_ORDER.pop(0)
            JOB_ARCHIVE.pop(stale_id, None)
        _persist_job_archive_unlocked()

    try:
        persist_video_history_entry(build_history_entry(job, request_snapshot))
    except Exception as exc:
        print(f"[history] failed to persist history entry: {exc}", file=sys.stderr, flush=True)


def get_archived_job(job_id: str) -> dict[str, Any] | None:
    with JOB_ARCHIVE_LOCK:
        entry = JOB_ARCHIVE.get(job_id)
        return copy.deepcopy(entry) if entry is not None else None


def build_retry_request(source_job_id: str, req: dict[str, Any]) -> dict[str, Any] | None:
    source_entry = get_archived_job(source_job_id)
    if not source_entry:
        return None

    new_req = clone_request_snapshot(source_entry["request"])
    new_req["job_id"] = str(req.get("job_id") or f"job_{uuid.uuid4().hex[:12]}")
    new_req["retry_of"] = source_job_id
    new_req["retry_count"] = int(source_entry.get("retry_count") or 0) + 1

    original_output = str(
        new_req.get("original_output") or new_req.get("output") or ""
    ).strip()
    original_metadata_output = str(
        new_req.get("original_metadata_output") or new_req.get("metadata_output") or ""
    ).strip()

    if original_output:
        retry_output, retry_metadata_output = safe_unique_output_paths(
            original_output,
            retry_count=int(new_req["retry_count"]),
            original_metadata_output=original_metadata_output or None,
        )
        new_req["output"] = retry_output
        new_req["metadata_output"] = retry_metadata_output
        new_req["original_output"] = original_output
        new_req["original_metadata_output"] = original_metadata_output

    return new_req


def is_local_file(path: str) -> bool:
    return os.path.isfile(path)


def torch_dtype_and_device() -> tuple[torch.dtype, str]:
    if torch.cuda.is_available():
        return torch.float16, "cuda"
    return torch.float32, "cpu"


def detect_pipeline_type(model_name_or_path: str, requested_family: str | None = None) -> str:
    # Delegates to the ONE layered classifier (model_classification): safetensors
    # metadata -> request tag -> directory -> filename. This subsumes the old
    # Pony/Illustrious filename carve-out --
    # SDXL finetunes route to the SDXL pipeline via directory + registry family
    # rather than an "xl" filename token. The classifier's shim clamps to a valid
    # image pipeline type (sd/sdxl/sd3/flux) and falls back to the legacy substring
    # for anything non-image, so this contract is unchanged.
    return detect_image_pipeline_type(model_name_or_path, requested_family)


def handle_classify_models_command(req: dict[str, Any]) -> dict[str, Any]:
    # Batch classification for the Qt catalog scanner (option A of the detection
    # accelerator's Qt-consumption follow-up): the UI stops guessing families with
    # its own substring matcher and instead consults THIS -- the one classifier --
    # so the family Qt DISPLAYS matches the family the worker ROUTES. No
    # requested_family is passed: the scan wants the classifier's own verdict.
    paths = req.get("paths") or []
    classifications: list[dict[str, Any]] = []
    for raw in paths:
        path = str(raw)
        try:
            c = classify_model(path)
            spec = MODEL_FAMILIES.get(c.family)
            classifications.append({
                "path": path,
                "family": c.family,
                "display": spec.display_name if spec is not None else c.family.replace("_", " ").title(),
                "sub_family": c.sub_family,
                "pipeline_type": c.pipeline_type,
                "task_family": c.task_family,
                "confidence": c.confidence,
                "source_layer": c.source_layer,
                "model_type": c.model_type,
            })
        except Exception as exc:  # never fail the whole batch on one bad file
            classifications.append({"path": path, "family": "unknown", "error": str(exc)})
    # No "type" key -> worker_client passes this through unwrapped (ok-based branch).
    return {"ok": True, "classifications": classifications}


def handle_resolve_component_stack_command(req: dict[str, Any]) -> dict[str, Any]:
    # Component Auto-Population (Doc 19 §6 A2): the cockpit's producer. On model select the UI
    # sends the chosen primary + task + the file basenames it can offer per component; we run the
    # proven A1 engine (component_resolver.resolve_stack -- byte-equivalent to the worker-side
    # resolvers) and return the per-slot {tier, value, valid_options, required}. The engine is the
    # single source of truth; the worker-side resolvers remain the runtime backstop. No "type" key.
    try:
        from component_resolver import resolve_stack
        from video_family_contracts import VIDEO_FAMILY_CONTRACTS
    except Exception as exc:
        return {"ok": False, "error": f"component resolver unavailable: {exc}"}

    primary = str(req.get("primary") or req.get("model") or "").strip()
    task = str(req.get("task") or req.get("command") or "").strip().lower()
    family = str(req.get("family") or "").strip().lower() or None
    stack = req.get("stack") if isinstance(req.get("stack"), dict) else {}
    # choices: {comfy_class: {comfy_input: [filename, ...]}} -- the cockpit's own combo file set,
    # so value/valid_options come back aligned to what the UI can display.
    choices = req.get("choices") if isinstance(req.get("choices"), dict) else {}

    def choices_for(cls: str, inp: str) -> list[str]:
        bucket = choices.get(cls)
        if not isinstance(bucket, dict):
            return []
        vals = bucket.get(inp)
        return [str(x) for x in vals] if isinstance(vals, (list, tuple)) else []

    contract = VIDEO_FAMILY_CONTRACTS.get(family) if family else None
    try:
        resolved = resolve_stack(
            primary,
            family=family,
            requested_family=family,
            stack=stack,
            req=req,
            task=task or None,
            choices_for=choices_for,
            contract_required=contract.required_components if contract else None,
        )
    except Exception as exc:
        return {"ok": False, "error": f"resolve_stack failed: {exc}"}

    slots = [
        {
            "component": s.component,
            "tier": s.tier,
            "value": s.value,
            "valid_options": list(s.valid_options),
            "required": bool(s.required),
        }
        for s in resolved.slots
    ]
    return {"ok": True, "family": resolved.family, "slots": slots}


def optimize_pipeline(pipe: Any, device: str, *, profile: Any = None) -> Any:
    """Attention/VAE optimizations for a pipeline. Must run BEFORE any CPU-offload hooks are
    installed -- slicing interacts poorly with them (see apply_attention_optimizations).

    Does NOT move the pipeline to a device; the caller decides between offload and .to(device).
    """
    try:
        if hasattr(pipe, "set_progress_bar_config"):
            pipe.set_progress_bar_config(disable=True)
    except Exception:
        pass

    # Slicing trades ~5-10% of the denoise loop for peak VRAM. Skip it when the card has
    # headroom; mirrors the gate in build_paired_pipelines. profile=None keeps the old
    # unconditional behaviour for any caller that has not been updated.
    slice_attention = True
    try:
        if profile is not None:
            from memory_optimization import MemoryProfile as _MemoryProfile

            slice_attention = profile != _MemoryProfile.PERFORMANCE
    except Exception:
        slice_attention = True

    try:
        if slice_attention and hasattr(pipe, "enable_attention_slicing"):
            pipe.enable_attention_slicing()
    except Exception:
        pass

    try:
        if hasattr(pipe, "vae") and hasattr(pipe.vae, "enable_slicing"):
            pipe.vae.enable_slicing()
    except Exception:
        pass

    try:
        if device == "cuda" and hasattr(pipe, "enable_xformers_memory_efficient_attention"):
            pipe.enable_xformers_memory_efficient_attention()
    except Exception:
        pass

    return pipe




# Kill switch for the CPU-side fp32->fp16 cast applied during pipeline load.
# Set False to keep whatever dtype the checkpoint carries on disk (much higher
# VRAM for fp32 single-file SDXL checkpoints). See
# memory_optimization.build_paired_pipelines.
CAST_FP32_TO_FP16 = True




VIDEO_OUTPUT_EXTENSIONS = {".mp4", ".webm", ".mov", ".mkv", ".avi", ".gif"}
VIDEO_COMMANDS = {"t2v", "i2v", "v2v", "ti2v", "video"}






# Long-prompt / weighting support (design doc 12). The SDXL CLIP tokenizer truncates at 77 tokens
# (silently dropping the tail) and ignores civitai (word:1.2) weighting. sd_embed's
# get_weighted_text_embeddings_sdxl chunks past 77 and honors that weighting. A same-seed A/B (short
# weight-free prompt, string path vs sd_embed) showed sd_embed's encoding drifts MEANINGFULLY from
# diffusers' native encode_prompt (MAE ~24-35, a visibly different -- though coherent -- image), so we
# use OPTION B: keep the native prompt= path (byte-identical, preserves reproducibility) for simple
# prompts and route through sd_embed ONLY when it's actually needed -- i.e. >77 tokens OR weighting
# syntax present (the cases that were truncated/ignored before, where there is no old output to keep).
# Escape literal parens as \( \) so they aren't read as weighting.
_WEIGHTING_SYNTAX_RE = re.compile(r"(?<!\\)[()\[\]]")


def _has_weighting_syntax(text: str) -> bool:
    return bool(text) and _WEIGHTING_SYNTAX_RE.search(text) is not None


def _exceeds_clip_window(pipe: Any, text: str) -> bool:
    if not text:
        return False
    tokenizer = getattr(pipe, "tokenizer", None)
    if tokenizer is None:
        return False
    try:
        # verbose=False silences transformers' "Token indices sequence length is longer than 77"
        # notice -- this is a deliberate length PROBE (we never feed this untruncated sequence to the
        # model; sd_embed chunks it), so the warning would be misleading log noise.
        ids = tokenizer(text, truncation=False, padding=False, add_special_tokens=True, verbose=False)["input_ids"]
    except Exception:
        return False
    return len(ids) > 77  # CLIP window incl. BOS/EOS; >77 => the native path would truncate the tail


def _prompt_needs_weighted_embeds(pipe: Any, prompt: str, negative: str) -> bool:
    return (
        _has_weighting_syntax(prompt)
        or _has_weighting_syntax(negative)
        or _exceeds_clip_window(pipe, prompt)
        or _exceeds_clip_window(pipe, negative)
    )




def _load_json_file(path_value: str) -> dict[str, Any]:
    path = Path(path_value)
    if not path.exists():
        raise RuntimeError(f"File not found: {path_value}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected JSON object in {path_value}")
    return payload


def _workflow_slot_values_from_request(req: dict[str, Any]) -> dict[str, Any]:
    return {
        "prompt": req.get("prompt"),
        "negative_prompt": req.get("negative_prompt"),
        "seed": req.get("seed"),
        "steps": req.get("steps"),
        "cfg": req.get("cfg"),
        "width": req.get("width"),
        "height": req.get("height"),
        "input_image": req.get("input_image"),
        "strength": req.get("strength"),
        "checkpoint": req.get("model"),
        "model": req.get("model"),
        "lora": req.get("lora"),
        "lora_scale": req.get("lora_scale"),
    }


def _set_workflow_path(root: dict[str, Any], path_expr: str, value: Any) -> None:
    if value is None or path_expr is None:
        return
    parts = [part for part in str(path_expr).split('.') if part]
    cursor: Any = root
    for part in parts[:-1]:
        if isinstance(cursor, dict):
            if part not in cursor:
                return
            cursor = cursor[part]
        elif isinstance(cursor, list):
            try:
                cursor = cursor[int(part)]
            except Exception:
                return
        else:
            return
    leaf = parts[-1] if parts else ""
    if isinstance(cursor, dict):
        cursor[leaf] = value
    elif isinstance(cursor, list):
        try:
            idx = int(leaf)
        except Exception:
            return
        if 0 <= idx < len(cursor):
            cursor[idx] = value


# Slots whose value names a model file: a full path / bare name from the UI must be resolved to the
# EXACT string ComfyUI's loader lists (subfolder-relative, ComfyUI's separator) or /prompt rejects it
# with value_not_in_list. Other slots (prompt, seed, dims...) are set verbatim.
_MODEL_SLOTS_TO_RESOLVE = {"checkpoint", "model", "lora"}






def request_has_workflow_binding(req: dict[str, Any]) -> bool:
    for key in ("compiled_prompt_path", "workflow_path", "profile_path", "workflow_profile_path"):
        if str(req.get(key) or "").strip():
            return True
    return False


def _import_diffusers_symbol(name: str) -> Any | None:
    try:
        import diffusers  # type: ignore
    except Exception:
        return None
    return getattr(diffusers, name, None)






def _stack_summary(stack: dict[str, Any]) -> str:
    if not stack:
        return "no video model stack"
    family = str(stack.get("family") or "unknown").strip()
    kind = str(stack.get("stack_kind") or stack.get("role") or "stack").strip()
    primary = _first_stack_value(stack, ("diffusers_path", "primary_path", "transformer_path", "unet_path", "model_path"))
    missing = _stack_missing_parts(stack)
    bits = [f"family={family}", f"kind={kind}"]
    if primary:
        bits.append(f"primary={primary}")
    if missing:
        bits.append("missing=" + ", ".join(missing))
    return "; ".join(bits)









































































# ---------------------------------------------------------------------------
# Native-image family registry. Each build is the existing per-family image
# builder; "flux" is the default when no family key matches.
# ---------------------------------------------------------------------------
NATIVE_IMAGE_FAMILY_PLUGINS: dict[str, NativeFamilyPlugin] = {
    "flux": NativeFamilyPlugin(family="flux", kind="image", build=_build_flux_image_prompt),
    "pixart": NativeFamilyPlugin(family="pixart", kind="image", build=_build_pixart_image_prompt),
    "lumina": NativeFamilyPlugin(family="lumina", kind="image", build=_build_lumina_image_prompt),
    "z_image": NativeFamilyPlugin(family="z_image", kind="image", build=_build_zimage_image_prompt),
    "anima": NativeFamilyPlugin(family="anima", kind="image", build=_build_anima_image_prompt),
    "krea2": NativeFamilyPlugin(family="krea2", kind="image", build=_build_krea2_image_prompt),
}








def _native_video_frames_from_result(result: Any) -> Any:
    frames = getattr(result, "frames", None)
    if frames is not None:
        if isinstance(frames, (list, tuple)) and frames and isinstance(frames[0], (list, tuple)):
            return frames[0]
        if isinstance(frames, (list, tuple)) and frames:
            return frames[0] if not hasattr(frames[0], "save") else frames
        return frames

    videos = getattr(result, "videos", None)
    if videos is not None:
        if isinstance(videos, (list, tuple)) and videos:
            return videos[0]
        return videos

    images = getattr(result, "images", None)
    if images is not None:
        if isinstance(images, (list, tuple)) and images and isinstance(images[0], (list, tuple)):
            return images[0]
        return images

    if isinstance(result, dict):
        for key in ("frames", "videos", "images"):
            if key in result:
                value = result[key]
                if isinstance(value, (list, tuple)) and value and isinstance(value[0], (list, tuple)):
                    return value[0]
                return value

    raise RuntimeError("Native video pipeline completed but did not return frames/videos/images.")









class QueueEmitter:
    def __init__(self, queue_manager: QueueManager, queue_item_id: str):
        self.queue_manager = queue_manager
        self.queue_item_id = queue_item_id

    def emit(self, payload: dict[str, Any]) -> None:
        return

    def emit_job_update(self, job: JobRecord) -> None:
        self.queue_manager.update_from_job(self.queue_item_id, job)

    def status(self, job: JobRecord, message: str) -> None:
        set_job_message(job, message)
        self.emit_job_update(job)

    def progress(self, job: JobRecord, step: int, total: int, message: str | None = None) -> None:
        update_job_progress(job, step, total, message)
        self.emit_job_update(job)

    def result(self, job: JobRecord) -> None:
        self.emit_job_update(job)

    def error(self, job: JobRecord, error_text: str, tb: str | None = None, code: str = "generation_error") -> None:
        runtime_failure = invalidate_video_runtime_cache_for_failure(job, code, error_text)
        fail_job(job, error_text, code=code, tb=tb, details=runtime_failure)
        self.emit_job_update(job)


def imported_workflows_root() -> str:
    return str(Path(__file__).resolve().parent.parent / "runtime" / "imported_workflows")


def default_comfy_root() -> str:
    return str(resolve_identity_comfy_root())


def starter_node_catalog_path() -> str:
    return str(Path(__file__).resolve().parent / "starter_node_catalog.json")




def _managed_comfy_host(req: dict[str, Any] | None = None) -> str:
    req = req or {}
    return str(req.get("comfy_host") or os.environ.get("SPELLVISION_COMFY_HOST") or "127.0.0.1").strip() or "127.0.0.1"


def _managed_comfy_port(req: dict[str, Any] | None = None) -> int:
    req = req or {}
    raw = req.get("comfy_port") or os.environ.get("SPELLVISION_COMFY_PORT") or 8188
    try:
        return int(raw)
    except Exception:
        return 8188


def _managed_comfy_python(req: dict[str, Any] | None = None) -> str:
    req = req or {}
    resolved = resolve_comfy_python_from_request(req)
    if resolved:
        return resolved
    # Last resort: bootstrap helper, still never the worker python_executable key.
    comfy_root = str(req.get("comfy_root") or default_comfy_root()).strip()
    return str(default_comfy_python(comfy_root)).strip()


def get_comfy_runtime_manager(req: dict[str, Any] | None = None) -> ComfyRuntimeManager:
    global COMFY_RUNTIME_MANAGER
    req = req or {}
    comfy_root = str(req.get("comfy_root") or default_comfy_root()).strip()
    host = _managed_comfy_host(req)
    port = _managed_comfy_port(req)
    python_executable = _managed_comfy_python(req)
    with COMFY_RUNTIME_MANAGER_LOCK:
        if (
            COMFY_RUNTIME_MANAGER is None
            or COMFY_RUNTIME_MANAGER.comfy_root != comfy_root
            or COMFY_RUNTIME_MANAGER.host != host
            or COMFY_RUNTIME_MANAGER.port != port
            or COMFY_RUNTIME_MANAGER.python_executable != python_executable
        ):
            COMFY_RUNTIME_MANAGER = ComfyRuntimeManager(
                comfy_root,
                python_executable=python_executable,
                host=host,
                port=port,
            )
        return COMFY_RUNTIME_MANAGER


def _runtime_message(message_type: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized["type"] = message_type
    normalized["action"] = action
    normalized.setdefault("endpoint", normalized.get("endpoint") or f"http://{normalized.get('host', '127.0.0.1')}:{normalized.get('port', 8188)}")
    return normalized


def handle_comfy_runtime_status_command(req: dict[str, Any] | None = None) -> dict[str, Any]:
    req = req or {}
    manager = get_comfy_runtime_manager(req)
    payload = manager.status()
    return _runtime_message("comfy_runtime_status", "comfy_runtime_status", payload)


def handle_ensure_comfy_runtime_command(req: dict[str, Any] | None = None) -> dict[str, Any]:
    req = req or {}
    manager = get_comfy_runtime_manager(req)
    payload = manager.ensure_running(timeout_sec=float(req.get("startup_timeout_sec") or 60.0))
    return _runtime_message("comfy_runtime_ack", "ensure_comfy_runtime", payload)


def handle_start_comfy_runtime_command(req: dict[str, Any] | None = None) -> dict[str, Any]:
    req = req or {}
    manager = get_comfy_runtime_manager(req)
    payload = manager.start(timeout_sec=float(req.get("startup_timeout_sec") or 60.0))
    # A fresh ComfyUI process can expose a different node set; drop the cached /object_info.
    invalidate_comfy_object_info("comfy runtime started")
    return _runtime_message("comfy_runtime_ack", "start_comfy_runtime", payload)


def handle_stop_comfy_runtime_command(req: dict[str, Any] | None = None) -> dict[str, Any]:
    req = req or {}
    manager = get_comfy_runtime_manager(req)
    payload = manager.stop(graceful_timeout_sec=float(req.get("graceful_timeout_sec") or 8.0))
    invalidate_comfy_object_info("comfy runtime stopped")
    return _runtime_message("comfy_runtime_ack", "stop_comfy_runtime", payload)


def handle_restart_comfy_runtime_command(req: dict[str, Any] | None = None) -> dict[str, Any]:
    req = req or {}
    manager = get_comfy_runtime_manager(req)
    payload = manager.restart(timeout_sec=float(req.get("startup_timeout_sec") or 60.0))
    invalidate_comfy_object_info("comfy runtime restarted")
    return _runtime_message("comfy_runtime_ack", "restart_comfy_runtime", payload)




def handle_prepare_model_swap_command(req: dict[str, Any]) -> dict[str, Any]:
    requested_key = str(req.get("requested_key") or "").strip()

    if not requested_key:
        return {
            "type": "model_cache",
            "ok": False,
            "action": "prepare_model_swap",
            "error": "requested_key is required",
        }

    stats = cleanup_for_model_swap(requested_key)

    return {
        "type": "model_cache",
        "ok": True,
        "action": "prepare_model_swap",
        "requested_key": requested_key,
        "cleanup_performed": stats is not None,
        "cleanup_stats": stats,
        "memory": cuda_memory_snapshot(),
    }



# --- SPELLVISION SPRINT 13 PASS 2 TEACACHE WORKER HELPERS ---
def _spellvision_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "enable", "enabled"}:
        return True
    if text in {"0", "false", "no", "off", "disable", "disabled"}:
        return False
    return default


def _spellvision_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _spellvision_clamped_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, _spellvision_float(value, default)))


def _spellvision_teacache_enabled(req: dict[str, Any]) -> bool:
    if _spellvision_bool(req.get("teacache_enabled"), False):
        return True
    accel = req.get("video_acceleration")
    if isinstance(accel, dict):
        return _spellvision_bool(accel.get("enabled"), False)
    return False


def _spellvision_teacache_settings(req: dict[str, Any]) -> dict[str, Any]:
    raw_accel = req.get("video_acceleration")
    accel: dict[str, Any] = raw_accel if isinstance(raw_accel, dict) else {}

    profile = str(req.get("teacache_profile") or accel.get("profile") or "off").strip().lower() or "off"
    model_type = str(req.get("teacache_model_type") or accel.get("model_type") or "wan2.1_t2v_14b").strip() or "wan2.1_t2v_14b"
    cache_device = str(req.get("teacache_cache_device") or accel.get("cache_device") or "cpu").strip().lower() or "cpu"
    if cache_device not in {"cpu", "cuda"}:
        cache_device = "cpu"

    rel_l1 = _spellvision_clamped_float(
        req.get("teacache_rel_l1_thresh", accel.get("rel_l1_thresh", 0.20)),
        0.20,
        0.0,
        2.0,
    )
    start = _spellvision_clamped_float(
        req.get("teacache_start_percent", accel.get("start_percent", 0.0)),
        0.0,
        0.0,
        1.0,
    )
    end = _spellvision_clamped_float(
        req.get("teacache_end_percent", accel.get("end_percent", 1.0)),
        1.0,
        0.0,
        1.0,
    )
    if end < start:
        start, end = end, start
    return {
        "enabled": _spellvision_teacache_enabled(req),
        "profile": profile,
        "model_type": model_type,
        "rel_l1_thresh": rel_l1,
        "start_percent": start,
        "end_percent": end,
        "cache_device": cache_device,
    }


# Wrapper-family TeaCache nodes (WanVideoWrapper's WanVideoTeaCache, HunyuanVideoWrapper's
# HyVideoTeaCache) output TEACACHEARGS, NOT MODEL -- they belong to those wrappers' own sampler
# topology, not the native-core UNETLoader -> ModelSamplingSD3 -> KSamplerAdvanced graph the video
# builders emit. Inserting one into the model chain makes ComfyUI reject the WHOLE graph
# (return_type_mismatch: received TEACACHEARGS, expected MODEL -- verified live). The substring
# fallback below MUST skip them so the enable flag degrades to "no TeaCache" (a valid, unaccelerated
# graph) rather than a broken HTTP-400 graph. The normalized token "videoteacache" catches the
# *VideoTeaCache wrapper family (wan/hy and any future sibling); the explicit set is belt-and-suspenders.
_TEACACHE_WRAPPER_INCOMPATIBLE = ("wanvideoteacache", "hyvideoteacache")


def _spellvision_teacache_class(object_info: dict[str, Any]) -> str | None:
    # Explicit standalone model-wrapper nodes (MODEL in -> MODEL out) -- the compatible ones.
    for class_name in ("TeaCache", "TeaCacheForVidGen", "TeaCacheForImgGen"):
        if class_name in object_info:
            return class_name
    for class_name in object_info:
        normalized = str(class_name).lower().replace("_", "")
        if "teacache" not in normalized:
            continue
        if "videoteacache" in normalized or normalized in _TEACACHE_WRAPPER_INCOMPATIBLE:
            continue  # wrapper-topology node (TEACACHEARGS output) -- incompatible with the native graph
        return str(class_name)
    return None


def _spellvision_choice_casefold(choices: list[str], requested: str) -> str | None:
    normalized_requested = requested.strip().lower().replace("-", "_").replace(" ", "_")
    for choice in choices:
        normalized_choice = str(choice).strip().lower().replace("-", "_").replace(" ", "_")
        if normalized_choice == normalized_requested:
            return str(choice).strip()
    return None


def _spellvision_teacache_model_type(object_info: dict[str, Any], class_name: str, requested: str) -> str:
    choices = _comfy_input_choices(object_info, class_name, "model_type")
    if not choices:
        return requested
    found = _spellvision_choice_casefold(choices, requested)
    if found:
        return found
    wanted = requested.lower().replace("-", "_").replace(" ", "_")
    for choice in choices:
        candidate = str(choice).lower().replace("-", "_").replace(" ", "_")
        if "wan" in wanted and "wan" in candidate and "14" in candidate and "t2v" in candidate:
            return str(choice).strip()
    for choice in choices:
        candidate = str(choice).lower()
        if "wan" in candidate:
            return str(choice).strip()
    return str(choices[0]).strip()


def _spellvision_teacache_metadata(req: dict[str, Any]) -> dict[str, Any]:
    settings = _spellvision_teacache_settings(req)
    return {
        "teacache_enabled": bool(settings.get("enabled")),
        "teacache_applied": bool(req.get("teacache_applied", False)),
        "teacache_available": bool(req.get("teacache_available", False)),
        "teacache_node_count": int(req.get("teacache_node_count") or 0),
        "teacache_profile": settings.get("profile"),
        "teacache_model_type": settings.get("model_type"),
        "teacache_rel_l1_thresh": settings.get("rel_l1_thresh"),
        "teacache_start_percent": settings.get("start_percent"),
        "teacache_end_percent": settings.get("end_percent"),
        "teacache_cache_device": settings.get("cache_device"),
        "teacache_warning": req.get("teacache_warning"),
        "video_acceleration": {
            "backend": "ComfyUI-TeaCache",
            **settings,
            "available": bool(req.get("teacache_available", False)),
            "applied": bool(req.get("teacache_applied", False)),
            "node_count": int(req.get("teacache_node_count") or 0),
            "warning": req.get("teacache_warning"),
        },
    }


def _spellvision_apply_teacache_to_native_video_prompt(
    prompt: dict[str, Any],
    req: dict[str, Any],
    object_info: dict[str, Any],
) -> dict[str, Any]:
    settings = _spellvision_teacache_settings(req)
    if not settings["enabled"] or settings["profile"] == "off":
        req["teacache_applied"] = False
        req["teacache_available"] = bool(_spellvision_teacache_class(object_info))
        req["teacache_node_count"] = 0
        return prompt

    tea_class = _spellvision_teacache_class(object_info)
    req["teacache_available"] = bool(tea_class)
    if not tea_class:
        req["teacache_applied"] = False
        req["teacache_node_count"] = 0
        req["teacache_warning"] = "ComfyUI-TeaCache node is not installed; generated without TeaCache."
        return prompt

    if any(str(node.get("class_type") or "").lower().replace("_", "") == str(tea_class).lower().replace("_", "") for node in prompt.values() if isinstance(node, dict)):
        req["teacache_applied"] = True
        req["teacache_node_count"] = sum(1 for node in prompt.values() if isinstance(node, dict) and str(node.get("class_type") or "").lower().replace("_", "") == str(tea_class).lower().replace("_", ""))
        return prompt

    model_node_ids: list[str] = []
    for node_id, node in list(prompt.items()):
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "")
        if class_type in {"UNETLoader", "DiffusionModelLoader", "LoadDiffusionModel"}:
            model_node_ids.append(str(node_id))

    if not model_node_ids:
        req["teacache_applied"] = False
        req["teacache_node_count"] = 0
        req["teacache_warning"] = "TeaCache enabled, but no native diffusion model loader was found in the generated prompt."
        return prompt

    allowed = _comfy_class_inputs(object_info, tea_class)
    inserted: dict[str, str] = {}
    for model_node_id in model_node_ids:
        tea_node_id = f"tc_{model_node_id}"
        while tea_node_id in prompt:
            tea_node_id = f"tc_{tea_node_id}"
        inputs: dict[str, Any] = {}
        _set_if_allowed(inputs, allowed, ("model",), [model_node_id, 0])
        _set_if_allowed(inputs, allowed, ("model_type",), _spellvision_teacache_model_type(object_info, tea_class, str(settings["model_type"])))
        _set_if_allowed(inputs, allowed, ("rel_l1_thresh",), float(settings["rel_l1_thresh"]))
        _set_if_allowed(inputs, allowed, ("start_percent",), float(settings["start_percent"]))
        _set_if_allowed(inputs, allowed, ("end_percent",), float(settings["end_percent"]))
        _set_if_allowed(inputs, allowed, ("cache_device",), str(settings["cache_device"]))
        _sv_set_default_required_inputs(inputs, object_info, tea_class)
        _add_node(prompt, tea_node_id, tea_class, inputs)
        inserted[model_node_id] = tea_node_id

    # Route downstream model consumers through TeaCache. Leave the TeaCache node's own input untouched.
    for node_id, node in prompt.items():
        if str(node_id).startswith("tc_") or not isinstance(node, dict):
            continue

        node_inputs_any = node.get("inputs")
        if not isinstance(node_inputs_any, dict):
            continue

        node_inputs: dict[str, Any] = node_inputs_any
        for input_name, value in list(node_inputs.items()):
            if not (isinstance(value, list) and len(value) >= 2):
                continue

            source_id = str(value[0])
            tea_node_id = inserted.get(source_id)
            if not tea_node_id:
                continue

            if input_name not in {"model", "diffusion_model"}:
                continue

            node_inputs[input_name] = [tea_node_id, value[1]]

    req["teacache_applied"] = bool(inserted)
    req["teacache_node_count"] = len(inserted)
    req["teacache_warning"] = None
    req["video_acceleration_backend"] = "ComfyUI-TeaCache"
    return prompt
# --- END SPELLVISION SPRINT 13 PASS 2 TEACACHE WORKER HELPERS ---


# --- SPELLVISION MANAGER FOUNDATION V1 ---
def _load_starter_node_catalog_payload() -> dict[str, Any]:
    path = Path(starter_node_catalog_path())
    if not path.exists():
        return {"packages": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {"packages": []}
    except Exception:
        return {"packages": []}


def _package_looks_installed(entry: dict[str, Any], installed_names: set[str], custom_nodes_root: str) -> tuple[bool, str]:
    package_name = str(entry.get("package_name") or "").strip()
    repo_url = str(entry.get("repo_url") or "").strip()
    aliases = [str(item).strip() for item in entry.get("aliases") or [] if str(item).strip()]
    candidates = [package_name, *aliases]
    if repo_url:
        candidates.append(Path(repo_url.rstrip("/").replace(".git", "")).name)

    normalized_installed = {name.lower() for name in installed_names}
    for candidate in candidates:
        if candidate.lower() in normalized_installed:
            return True, f"matched installed node '{candidate}'"

    root = Path(custom_nodes_root)
    for candidate in candidates:
        if candidate and (root / candidate).exists():
            return True, f"folder exists: {candidate}"

    return False, "not detected"


def _recommended_node_entries(installed_names: set[str], custom_nodes_root: str) -> list[dict[str, Any]]:
    catalog = _load_starter_node_catalog_payload()
    entries: list[dict[str, Any]] = []
    video_families = {"wan", "ltx", "hunyuan_video", "cogvideox", "mochi"}
    for raw_entry in catalog.get("packages") or []:
        if not isinstance(raw_entry, dict):
            continue
        package_name = str(raw_entry.get("package_name") or "").strip()
        if not package_name:
            continue
        model_families = [str(item) for item in raw_entry.get("model_families") or []]
        is_video_related = bool(set(model_families).intersection(video_families)) or "teacache" in package_name.lower()
        if not is_video_related:
            continue
        installed, note = _package_looks_installed(raw_entry, installed_names, custom_nodes_root)
        entry = dict(raw_entry)
        entry["installed"] = installed
        entry["notes"] = note
        entries.append(entry)
    entries.sort(key=lambda item: (bool(item.get("installed")), str(item.get("package_name") or "").lower()))
    return entries


def _manager_python_executable(req: dict[str, Any] | None = None) -> str:
    req = req or {}
    return str(req.get("python_executable") or _managed_comfy_python(req) or sys.executable).strip() or sys.executable


def handle_comfy_manager_status_command(req: dict[str, Any] | None = None) -> dict[str, Any]:
    req = req or {}
    try:
        from comfy_manager_bridge import detect_manager_paths, list_installed_nodes
    except Exception as exc:
        return {
            "type": "comfy_manager_status",
            "ok": False,
            "action": "comfy_manager_status",
            "error": f"comfy_manager_bridge import failed: {exc}",
        }

    comfy_root = str(req.get("comfy_root") or default_comfy_root()).strip()
    python_executable = _manager_python_executable(req)
    paths = detect_manager_paths(comfy_root)
    installed_snapshot = list_installed_nodes(comfy_root, python_executable=python_executable)
    installed_names = {str(name).lower() for name in installed_snapshot.get("names") or []}
    recommended = _recommended_node_entries(installed_names, paths.custom_nodes_root)

    try:
        runtime_status = handle_comfy_runtime_status_command(req)
    except Exception as exc:
        runtime_status = {"ok": False, "error": str(exc)}

    return {
        "type": "comfy_manager_status",
        "ok": True,
        "action": "comfy_manager_status",
        "comfy_root": comfy_root,
        "python_executable": python_executable,
        "manager_paths": paths.to_dict(),
        "manager_present": bool(paths.exists),
        "installed_nodes": sorted(installed_names),
        "installed_snapshot": installed_snapshot,
        "recommended_nodes": recommended,
        "recommended_missing_count": sum(1 for item in recommended if not item.get("installed")),
        "starter_node_catalog": starter_node_catalog_path(),
        "runtime_status": runtime_status,
    }


def handle_install_comfy_manager_command(req: dict[str, Any] | None = None) -> dict[str, Any]:
    req = req or {}
    try:
        from comfy_manager_bridge import ensure_manager_installed
    except Exception as exc:
        return {
            "type": "comfy_manager_ack",
            "ok": False,
            "action": "install_comfy_manager",
            "error": f"comfy_manager_bridge import failed: {exc}",
        }

    comfy_root = str(req.get("comfy_root") or default_comfy_root()).strip()
    python_executable = _manager_python_executable(req)
    try:
        paths, logs = ensure_manager_installed(
            comfy_root,
            python_executable=python_executable,
            install_requirements=True,
            timeout_sec=int(req.get("timeout_sec") or 1800),
        )
        return {
            "type": "comfy_manager_ack",
            "ok": all(log.ok for log in logs) if logs else bool(paths.exists),
            "action": "install_comfy_manager",
            "manager_paths": paths.to_dict(),
            "logs": [log.to_dict() for log in logs],
            "message": "ComfyUI Manager is installed or repaired." if paths.exists else "ComfyUI Manager install did not complete.",
        }
    except Exception as exc:
        return {
            "type": "comfy_manager_ack",
            "ok": False,
            "action": "install_comfy_manager",
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


def _find_catalog_node_entry(package_name: str) -> dict[str, Any] | None:
    target = package_name.strip().lower()
    if not target:
        return None
    catalog = _load_starter_node_catalog_payload()
    for entry in catalog.get("packages") or []:
        if not isinstance(entry, dict):
            continue
        names = [str(entry.get("package_name") or "").strip().lower()]
        names.extend(str(alias).strip().lower() for alias in entry.get("aliases") or [])
        if target in names:
            return dict(entry)
    return None


def handle_install_custom_node_command(req: dict[str, Any]) -> dict[str, Any]:
    try:
        from comfy_manager_bridge import clone_custom_node_repo, install_registered_nodes
    except Exception as exc:
        return {
            "type": "comfy_manager_ack",
            "ok": False,
            "action": "install_custom_node",
            "error": f"comfy_manager_bridge import failed: {exc}",
        }

    package_name = str(req.get("package_name") or "").strip()
    if not package_name:
        return {"type": "comfy_manager_ack", "ok": False, "action": "install_custom_node", "error": "package_name is required"}

    catalog_entry = _find_catalog_node_entry(package_name) or {}
    repo_url = str(req.get("repo_url") or catalog_entry.get("repo_url") or "").strip()
    install_method = str(req.get("install_method") or catalog_entry.get("install_method") or "git").strip().lower()
    comfy_root = str(req.get("comfy_root") or default_comfy_root()).strip()
    python_executable = _manager_python_executable(req)

    try:
        outcomes: list[dict[str, Any]] = []
        if install_method == "manager":
            results = install_registered_nodes(comfy_root, [package_name], python_executable=python_executable, timeout_sec=int(req.get("timeout_sec") or 1800))
            outcomes = [result.to_dict() for result in results]
            ok = all(result.ok for result in results)
        else:
            if not repo_url:
                return {"type": "comfy_manager_ack", "ok": False, "action": "install_custom_node", "error": f"No repo_url is known for {package_name}"}
            result = clone_custom_node_repo(
                comfy_root,
                repo_url,
                package_name=package_name,
                python_executable=python_executable,
                timeout_sec=int(req.get("timeout_sec") or 1800),
                install_requirements=True,
            )
            outcomes = [result.to_dict()]
            ok = result.ok
        # A new node pack only reaches /object_info after a Comfy restart (which invalidates on its
        # own), but drop the cache here too so a hot-reloading manager path can't serve a stale
        # node set. Also covers install_recommended_video_nodes, which delegates here.
        invalidate_comfy_object_info("custom node install")
        return {
            "type": "comfy_manager_ack",
            "ok": ok,
            "action": "install_custom_node",
            "package_name": package_name,
            "install_method": install_method,
            "repo_url": repo_url,
            "outcomes": outcomes,
        }
    except Exception as exc:
        return {
            "type": "comfy_manager_ack",
            "ok": False,
            "action": "install_custom_node",
            "package_name": package_name,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


def handle_install_recommended_video_nodes_command(req: dict[str, Any] | None = None) -> dict[str, Any]:
    req = req or {}
    status = handle_comfy_manager_status_command(req)
    if not status.get("ok"):
        return {"type": "comfy_manager_ack", "ok": False, "action": "install_recommended_video_nodes", "error": status.get("error") or "manager status failed"}

    selected_names = [str(item).strip() for item in req.get("package_names") or [] if str(item).strip()]
    recommended = status.get("recommended_nodes") or []
    if selected_names:
        install_entries = [item for item in recommended if str(item.get("package_name") or "") in selected_names]
    else:
        install_entries = [item for item in recommended if not item.get("installed")]

    outcomes: list[dict[str, Any]] = []
    errors: list[str] = []
    for entry in install_entries:
        package_name = str(entry.get("package_name") or "").strip()
        if not package_name:
            continue
        payload = dict(req)
        payload.update({
            "package_name": package_name,
            "install_method": entry.get("install_method"),
            "repo_url": entry.get("repo_url"),
        })
        result = handle_install_custom_node_command(payload)
        outcomes.append(result)
        if not result.get("ok"):
            errors.append(str(result.get("error") or f"Failed to install {package_name}"))

    return {
        "type": "comfy_manager_ack",
        "ok": not errors,
        "action": "install_recommended_video_nodes",
        "requested_count": len(install_entries),
        "outcomes": outcomes,
        "errors": errors,
    }
# --- END SPELLVISION MANAGER FOUNDATION V1 ---

# --- TEST-ONLY: noop_slow command ----------------------------------------
# Exercises the queue / cancellation / progress paths of worker_service from
# pytest without requiring a real generation backend. Production code never
# emits this command. See tests/test_worker_queue.py.
def run_noop_slow(
    req: dict[str, Any],
    emitter: EventEmitter,
    job: JobRecord,
    active_job: ActiveJobHandle,
) -> None:
    try:
        duration_sec = float(req.get("duration_sec") or 0.5)
    except (TypeError, ValueError):
        duration_sec = 0.5
    try:
        steps = int(req.get("steps") or 5)
    except (TypeError, ValueError):
        steps = 5

    # Clamp to sane bounds. The upper bound on duration_sec protects against
    # a runaway test holding a worker thread for minutes.
    duration_sec = max(0.0, min(duration_sec, 30.0))
    steps = max(1, min(steps, 200))

    transition_job(job, JobState.STARTING)
    transition_job(job, JobState.RUNNING)
    update_job_progress(job, 0, steps, "noop_slow starting")
    emitter.emit_job_update(job)

    per_step = duration_sec / steps if steps > 0 else 0.0

    for i in range(1, steps + 1):
        raise_if_cancelled(active_job, emitter, f"noop_slow step {i}/{steps}")
        if per_step > 0:
            # cancel_event.wait acts as an interruptible sleep that returns
            # early when a cancel is requested. We re-check immediately after.
            active_job.cancel_event.wait(timeout=per_step)
            raise_if_cancelled(active_job, emitter, f"noop_slow step {i}/{steps}")
        update_job_progress(job, i, steps, f"noop_slow step {i}/{steps}")
        emitter.emit_job_update(job)

    job.result = JobResult(task_type="noop_slow")
    transition_job(job, JobState.COMPLETED)
    emitter.emit_job_update(job)
# --- END TEST-ONLY block --------------------------------------------------

from worker_tcp import EventEmitter, ThreadedTCPServer, WorkerTCPHandler



def main() -> None:
    host = os.environ.get("SPELLVISION_WORKER_HOST", "127.0.0.1").strip() or "127.0.0.1"
    try:
        port = int(os.environ.get("SPELLVISION_WORKER_PORT", "8765"))
    except ValueError:
        port = 8765
    with ThreadedTCPServer((host, port), WorkerTCPHandler) as server:
        QUEUE_MANAGER.start_recovered()
        print(f"[service] SpellVision worker service listening on {host}:{port}", flush=True)
        server.serve_forever()

if __name__ == "__main__":
    main()
