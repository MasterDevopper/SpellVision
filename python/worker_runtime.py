"""Worker runtime cache: diffusers pipes, CUDA cleanup, video-runtime affinity.

Extracted from worker_service.py. Comfy /free stays in comfy_prompt_client.
"""
from __future__ import annotations

from comfy_endpoint import comfy_endpoint

import gc
import logging
import threading
import time
from typing import Any

import torch

from comfy_graph_helpers import _first_nonempty_text
from comfy_prompt_client import request_comfy_free_memory
from memory_optimization import auto_select_memory_profile, build_paired_pipelines
from worker_service_state import utc_now_iso
from vram import worker_vram

CAST_FP32_TO_FP16 = True


def _ws():
    import worker_service as ws
    return ws


MODEL_CACHE: dict[str, Any] = {
    "key": None,
    "pipe": None,
    "img2img_pipe": None,
    "device": None,
    "dtype": None,
    "detected": None,
    "active_lora_path_t2i": None,
    "active_lora_scale_t2i": None,
    "active_lora_path_i2i": None,
    "active_lora_scale_i2i": None,
    "lora_adapters": {},
}
CACHE_LOCK = threading.Lock()
# Serializes heavyweight model swap/load/unload operations. It must be
# re-entrant because cleanup_for_model_swap() can call unload while a load
# transaction already owns the operation lock.
MODEL_LOAD_LOCK = threading.RLock()


VIDEO_RUNTIME_LOCK = threading.Lock()
VIDEO_RUNTIME_CACHE: dict[str, Any] = {
    "active_command": None,
    "active_signature": None,
    "active_summary": None,
    "active_family": None,
    "active_stack_kind": None,
    "active_backend_type": None,
    "active_backend_name": None,
    "updated_at": None,
    "reset_reason": None,
    "last_success_at": None,
    "last_prompt_id": None,
    "last_output": None,
    "last_error": None,
    "last_failure_code": None,
    "invalidated_at": None,
    "invalidation_reason": None,
    "comfy_runtime_endpoint": None,
    "comfy_runtime_pid": None,
    "comfy_runtime_detected_pid": None,
    "comfy_runtime_started_at": None,
    "comfy_runtime_state": None,
    "comfy_runtime_ownership": None,
    "comfy_runtime_running": False,
    "comfy_runtime_healthy": False,
    "comfy_runtime_endpoint_alive": False,
    "comfy_runtime_checked_at": None,
}


def cuda_memory_snapshot() -> dict[str, float | None]:
    """Never zeros for "no CUDA".

    The early return used to hardcode four zeros, which is the same defect as the native payloads:
    a machine with no GPU and a GPU holding nothing reported identically. The reader answers both
    cases and says which one it was.
    """
    reading = worker_vram()
    return {
        "allocated_gb": reading.allocated_gb,
        "reserved_gb": reading.reserved_gb,
        "max_allocated_gb": reading.max_allocated_gb,
        "max_reserved_gb": reading.max_reserved_gb,
        "free_gb": reading.free_gb,
        "total_gb": reading.total_gb,
        "source": reading.source,
    }


def clear_cuda_memory() -> dict[str, float]:
    gc.collect()

    if torch.cuda.is_available():
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass
        try:
            torch.cuda.ipc_collect()
        except Exception:
            pass

    return cuda_memory_snapshot()


def _unload_cached_pipelines_locked() -> dict[str, Any]:
    before = cuda_memory_snapshot()
    start = time.perf_counter()

    with CACHE_LOCK:
        old_key = MODEL_CACHE.get("key")
        old_t2i = MODEL_CACHE.get("pipe")
        old_i2i = MODEL_CACHE.get("img2img_pipe")

        MODEL_CACHE["key"] = None
        MODEL_CACHE["pipe"] = None
        MODEL_CACHE["img2img_pipe"] = None
        MODEL_CACHE["device"] = None
        MODEL_CACHE["dtype"] = None
        MODEL_CACHE["detected"] = None
        MODEL_CACHE["active_lora_path_t2i"] = None
        MODEL_CACHE["active_lora_scale_t2i"] = None
        MODEL_CACHE["active_lora_path_i2i"] = None
        MODEL_CACHE["active_lora_scale_i2i"] = None
        MODEL_CACHE["lora_adapters"] = {}

    try:
        if old_t2i is not None:
            del old_t2i
    except Exception:
        pass

    try:
        if old_i2i is not None:
            del old_i2i
    except Exception:
        pass

    after = clear_cuda_memory()
    elapsed = round(time.perf_counter() - start, 3)

    return {
        "old_key": old_key,
        "cleanup_time_sec": elapsed,
        "memory_before": before,
        "memory_after": after,
    }


def unload_cached_pipelines() -> dict[str, Any]:
    with MODEL_LOAD_LOCK:
        return _unload_cached_pipelines_locked()


def cache_identity(model_name_or_path: str, requested_family: str | None = None) -> str:
    """What makes two pipeline loads the same load.

    The path alone is NOT it. ``requested_family`` reaches ``detect_pipeline_type`` and outranks
    directory and filename in ``classify_model`` (a 0.90-confidence signal), so it decides which
    pipeline CLASS gets built. Keying on the path alone meant loading X.safetensors tagged ``sdxl``
    and then requesting the same path tagged ``sd`` returned the pipeline built for the first tag --
    silently the wrong architecture, with a picture at the end. Only an actual model SWAP reset it,
    and that comparison used the same path-only key.

    A composite string rather than a tuple so the existing reporting callers
    (``image_runtime_cache_key``, the runtime status snapshot) keep working unchanged.
    """
    family = str(requested_family or "").strip().lower()
    path = str(model_name_or_path or "")
    return f"{path}|{family}" if family else path


def cleanup_for_model_swap(requested_key: str) -> dict[str, Any] | None:
    with CACHE_LOCK:
        active_key = MODEL_CACHE.get("key")

    if not active_key or active_key == requested_key:
        return None

    stats = unload_cached_pipelines()
    stats["requested_key"] = requested_key
    return stats


def image_runtime_cache_key() -> str:
    with CACHE_LOCK:
        return str(MODEL_CACHE.get("key") or "").strip()


def image_runtime_cache_active() -> bool:
    with CACHE_LOCK:
        return bool(MODEL_CACHE.get("key") and (MODEL_CACHE.get("pipe") is not None or MODEL_CACHE.get("img2img_pipe") is not None))


def _video_runtime_cache_snapshot() -> dict[str, Any]:
    with VIDEO_RUNTIME_LOCK:
        return dict(VIDEO_RUNTIME_CACHE)


def active_video_runtime_signature_for_command(command: str) -> str | None:
    command = str(command or "").strip().lower()
    if command not in {"t2v", "i2v"}:
        return None
    with VIDEO_RUNTIME_LOCK:
        active_command = str(VIDEO_RUNTIME_CACHE.get("active_command") or "").strip().lower()
        active_signature = str(VIDEO_RUNTIME_CACHE.get("active_signature") or "").strip()
    if active_command == command and active_signature:
        return active_signature
    return None



def comfy_runtime_identity_snapshot(result_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    result_payload = result_payload or {}
    status: dict[str, Any] = {}
    try:
        status = _ws().handle_comfy_runtime_status_command({})
        if not isinstance(status, dict):
            status = {}
    except Exception as exc:
        status = {
            "ok": False,
            "running": False,
            "healthy": False,
            "endpoint_alive": False,
            "error": str(exc),
        }

    endpoint = _first_nonempty_text(
        result_payload.get("comfy_runtime_endpoint"),
        status.get("endpoint"),
        comfy_endpoint(),
    )
    pid = _ws()._safe_int(result_payload.get("comfy_runtime_pid") or status.get("pid"), 0)
    detected_pid = _ws()._safe_int(result_payload.get("comfy_runtime_detected_pid") or status.get("detected_pid"), 0)
    healthy = bool(status.get("healthy", False))
    running = bool(status.get("running", False))
    endpoint_alive = bool(status.get("endpoint_alive", False))
    return {
        "ok": bool(status.get("ok", False)),
        "endpoint": endpoint or None,
        "pid": pid or None,
        "detected_pid": detected_pid or None,
        "started_at": status.get("started_at"),
        "state": status.get("state"),
        "ownership": status.get("ownership"),
        "running": running,
        "healthy": healthy,
        "endpoint_alive": endpoint_alive,
        "checked_at": utc_now_iso(),
        "error": status.get("error"),
    }


def _runtime_identity_value(value: Any) -> str:
    return str(value or "").strip()


def video_runtime_truth_for_snapshot(video_snapshot: dict[str, Any], request_signature: str = "") -> dict[str, Any]:
    active_signature = _runtime_identity_value(video_snapshot.get("active_signature"))
    if not active_signature:
        return {
            "ok": False,
            "reason": "no_active_video_runtime",
            "same_signature": False,
            "same_process": False,
            "same_endpoint": False,
            "healthy": False,
        }

    identity = comfy_runtime_identity_snapshot()
    same_signature = not request_signature or active_signature == request_signature

    cached_endpoint = _runtime_identity_value(video_snapshot.get("comfy_runtime_endpoint"))
    current_endpoint = _runtime_identity_value(identity.get("endpoint"))
    same_endpoint = bool(cached_endpoint and current_endpoint and cached_endpoint == current_endpoint)

    cached_pid = _runtime_identity_value(video_snapshot.get("comfy_runtime_pid") or video_snapshot.get("comfy_runtime_detected_pid"))
    current_pid = _runtime_identity_value(identity.get("pid") or identity.get("detected_pid"))
    same_process = bool(cached_pid and current_pid and cached_pid == current_pid)

    healthy = bool(identity.get("running") and identity.get("healthy") and identity.get("endpoint_alive"))
    if not same_signature:
        reason = "video_affinity_changed"
    elif not healthy:
        reason = "comfy_runtime_not_healthy"
    elif not same_endpoint:
        reason = "comfy_endpoint_changed_or_unknown"
    elif not same_process:
        reason = "comfy_process_changed_or_unknown"
    else:
        reason = "same_healthy_comfy_runtime"

    return {
        "ok": bool(same_signature and healthy and same_endpoint and same_process),
        "reason": reason,
        "same_signature": same_signature,
        "same_process": same_process,
        "same_endpoint": same_endpoint,
        "healthy": healthy,
        "identity": identity,
        "cached_signature": active_signature,
        "cached_endpoint": cached_endpoint or None,
        "current_endpoint": current_endpoint or None,
        "cached_pid": cached_pid or None,
        "current_pid": current_pid or None,
    }


def update_video_runtime_cache_from_result(req: dict[str, Any], result_payload: dict[str, Any]) -> dict[str, Any]:
    if not _ws().is_video_request(req, str(result_payload.get("output") or result_payload.get("video_path") or "")):
        return {}

    command = str(req.get("command") or req.get("task_command") or result_payload.get("task_type") or "video").strip().lower()
    if command not in {"t2v", "i2v"}:
        command = str(result_payload.get("video_request_kind") or command or "video").strip().lower()

    details = _ws().video_request_metadata_from_request(req)
    signature = _ws().affinity_signature_for_request(req)
    summary = _ws().affinity_summary_for_request(req)
    runtime_identity = comfy_runtime_identity_snapshot(result_payload)
    cache_entry = {
        "active_command": command,
        "active_signature": signature,
        "active_summary": summary,
        "active_family": result_payload.get("video_family") or details.get("video_family"),
        "active_stack_kind": result_payload.get("video_stack_kind") or details.get("video_stack_kind"),
        "active_backend_type": result_payload.get("video_backend_type") or result_payload.get("backend_name"),
        "active_backend_name": result_payload.get("video_backend_name") or result_payload.get("backend_name"),
        "updated_at": utc_now_iso(),
        "reset_reason": None,
        "last_success_at": utc_now_iso(),
        "last_prompt_id": result_payload.get("video_prompt_id") or result_payload.get("prompt_id"),
        "last_output": _first_nonempty_text(result_payload.get("output_video"), result_payload.get("video_path"), result_payload.get("output")),
        "last_error": None,
        "last_failure_code": None,
        "invalidated_at": None,
        "invalidation_reason": None,
        "comfy_runtime_endpoint": runtime_identity.get("endpoint"),
        "comfy_runtime_pid": runtime_identity.get("pid"),
        "comfy_runtime_detected_pid": runtime_identity.get("detected_pid"),
        "comfy_runtime_started_at": runtime_identity.get("started_at"),
        "comfy_runtime_state": runtime_identity.get("state"),
        "comfy_runtime_ownership": runtime_identity.get("ownership"),
        "comfy_runtime_running": bool(runtime_identity.get("running", False)),
        "comfy_runtime_healthy": bool(runtime_identity.get("healthy", False)),
        "comfy_runtime_endpoint_alive": bool(runtime_identity.get("endpoint_alive", False)),
        "comfy_runtime_checked_at": runtime_identity.get("checked_at"),
    }
    with VIDEO_RUNTIME_LOCK:
        VIDEO_RUNTIME_CACHE.update(cache_entry)
    return dict(cache_entry)


def runtime_prep_metadata(req: dict[str, Any]) -> dict[str, Any]:
    return {
        "runtime_transition": req.get("runtime_transition"),
        "runtime_target": req.get("runtime_target"),
        "runtime_previous": req.get("runtime_previous"),
        "runtime_notes": req.get("runtime_notes") or [],
        "image_cache_active_before_runtime": bool(req.get("image_cache_active_before_runtime", False)),
        "image_cache_unloaded_before_video": bool(req.get("image_cache_unloaded_before_video", False)),
        "image_cache_key_before_runtime": req.get("image_cache_key_before_runtime"),
        "video_runtime_signature_before": req.get("video_runtime_signature_before"),
        "video_runtime_reused": bool(req.get("video_runtime_reused", False)),
        "video_warm_reuse_candidate": bool(req.get("video_warm_reuse_candidate", False)),
        "video_warm_reuse_source": req.get("video_warm_reuse_source"),
        "video_runtime_affinity_signature": req.get("video_runtime_affinity_signature"),
        "video_runtime_transition": req.get("video_runtime_transition"),
        "video_runtime_truth_checked": bool(req.get("video_runtime_truth_checked", False)),
        "video_runtime_truth_ok": bool(req.get("video_runtime_truth_ok", False)),
        "video_runtime_truth_reason": req.get("video_runtime_truth_reason"),
        "video_runtime_same_process": bool(req.get("video_runtime_same_process", False)),
        "video_runtime_same_endpoint": bool(req.get("video_runtime_same_endpoint", False)),
        "video_runtime_comfy_pid_before": req.get("video_runtime_comfy_pid_before"),
        "video_runtime_comfy_pid_current": req.get("video_runtime_comfy_pid_current"),
        "video_runtime_comfy_endpoint_before": req.get("video_runtime_comfy_endpoint_before"),
        "video_runtime_comfy_endpoint_current": req.get("video_runtime_comfy_endpoint_current"),
        "runtime_cleanup": req.get("runtime_cleanup"),
    }


def prepare_runtime_for_request(req: dict[str, Any], emitter: "JobEmitter | None" = None, job: "JobRecord | None" = None) -> dict[str, Any]:
    command = str(req.get("command") or req.get("task_command") or req.get("task_type") or "").strip().lower()
    target = "video" if _ws().is_video_request(req) else ("image" if command in {"t2i", "i2i"} else "workflow")
    active_image_key = image_runtime_cache_key()
    image_active = image_runtime_cache_active()
    video_snapshot = _video_runtime_cache_snapshot()
    video_signature = str(video_snapshot.get("active_signature") or "").strip()
    request_signature = _ws().affinity_signature_for_request(req) if target == "video" else ""

    notes: list[str] = []
    cleanup: dict[str, Any] | None = None
    video_truth: dict[str, Any] = {}

    if target == "video" and video_signature:
        video_truth = video_runtime_truth_for_snapshot(video_snapshot, request_signature)
        if not video_truth.get("ok"):
            reset_video_runtime_cache(f"stale_video_runtime:{video_truth.get('reason') or 'unknown'}")
            notes.append(f"Video warm cache invalidated: {video_truth.get('reason') or 'unknown'}")
            video_snapshot = _video_runtime_cache_snapshot()
            video_signature = ""
        elif emitter is not None and job is not None:
            emitter.status(job, "reusing healthy Comfy video runtime for matching Wan stack")

    previous = "image" if image_active else ("video" if video_signature else "cold")
    transition = f"{previous}_to_{target}" if previous != target else f"{target}_reuse_check"

    video_reused = bool(target == "video" and video_signature and video_signature == request_signature and video_truth.get("ok"))
    # "workflow" (an imported Comfy graph) is grouped with "video" on purpose: it also renders
    # inside ComfyUI's process, so a resident diffusers pipeline here is pure contention. It used
    # to match NEITHER branch, so an image-output custom workflow ran with ~7GB of SDXL still
    # held on a 32GB card. is_video_request() rescued only the cases with a video output path.
    if target in {"video", "workflow"} and image_active:
        if emitter is not None and job is not None:
            emitter.status(job, f"freeing image VRAM before {target} generation")
        cleanup = unload_cached_pipelines()
        notes.append(f"Unloaded image pipeline cache before {target} generation")
    elif target == "image" and video_signature:
        # clear_cuda_memory only frees THIS process's allocator. The video weights are resident in
        # ComfyUI's separate process, so without the /free handshake a 22B video model stays put
        # while diffusers tries to load a checkpoint into what's left.
        memory_before = cuda_memory_snapshot()
        comfy_free = request_comfy_free_memory()  # best-effort, never raises
        cleanup = {
            "memory_before": memory_before,
            "comfy_free": comfy_free,
            "memory_after": clear_cuda_memory(),
        }
        notes.append("Cleared local CUDA allocator state before image generation after video runtime")
        notes.append(
            "Asked ComfyUI to unload video models before image generation"
            if comfy_free.get("ok")
            else f"ComfyUI /free unavailable before image generation: {comfy_free.get('error')}"
        )

    metadata = {
        "runtime_transition": transition,
        "runtime_target": target,
        "runtime_previous": previous,
        "runtime_notes": notes,
        "image_cache_active_before_runtime": image_active,
        # Field name predates the workflow case; it means "we dropped the image cache for a
        # ComfyUI-side render", which now covers imported workflows too.
        "image_cache_unloaded_before_video": bool(target in {"video", "workflow"} and image_active),
        "image_cache_key_before_runtime": active_image_key,
        "video_runtime_signature_before": video_truth.get("cached_signature") or video_signature or None,
        "video_runtime_reused": video_reused,
        "video_warm_reuse_candidate": video_reused,
        "video_warm_reuse_source": "video-warm-cache" if video_reused else None,
        "video_runtime_affinity_signature": request_signature or None,
        "video_runtime_transition": transition if target == "video" else None,
        "video_runtime_truth_checked": bool(target == "video" and bool(video_truth)),
        "video_runtime_truth_ok": bool(video_truth.get("ok", False)),
        "video_runtime_truth_reason": video_truth.get("reason"),
        "video_runtime_same_process": bool(video_truth.get("same_process", False)),
        "video_runtime_same_endpoint": bool(video_truth.get("same_endpoint", False)),
        "video_runtime_comfy_pid_before": video_truth.get("cached_pid"),
        "video_runtime_comfy_pid_current": video_truth.get("current_pid"),
        "video_runtime_comfy_endpoint_before": video_truth.get("cached_endpoint"),
        "video_runtime_comfy_endpoint_current": video_truth.get("current_endpoint"),
        "runtime_cleanup": cleanup,
    }
    req.update(metadata)
    return metadata


def reset_video_runtime_cache(reason: str = "manual") -> dict[str, Any]:
    before = _video_runtime_cache_snapshot()
    reset_entry = {
        "active_command": None,
        "active_signature": None,
        "active_summary": None,
        "active_family": None,
        "active_stack_kind": None,
        "active_backend_type": None,
        "active_backend_name": None,
        "updated_at": utc_now_iso(),
        "reset_reason": reason,
        "last_success_at": before.get("last_success_at"),
        "last_prompt_id": before.get("last_prompt_id"),
        "last_output": before.get("last_output"),
        "last_error": before.get("last_error"),
        "last_failure_code": before.get("last_failure_code"),
        "invalidated_at": utc_now_iso(),
        "invalidation_reason": reason,
        "comfy_runtime_endpoint": None,
        "comfy_runtime_pid": None,
        "comfy_runtime_detected_pid": None,
        "comfy_runtime_started_at": None,
        "comfy_runtime_state": None,
        "comfy_runtime_ownership": None,
        "comfy_runtime_running": False,
        "comfy_runtime_healthy": False,
        "comfy_runtime_endpoint_alive": False,
        "comfy_runtime_checked_at": None,
    }
    with VIDEO_RUNTIME_LOCK:
        VIDEO_RUNTIME_CACHE.update(reset_entry)
    return {
        "previous": before,
        "current": _video_runtime_cache_snapshot(),
        "reason": reason,
    }


def invalidate_video_runtime_cache_for_failure(job: "JobRecord", code: str, message: str) -> dict[str, Any] | None:
    command = str(job.command or "").strip().lower()
    if command not in {"t2v", "i2v"}:
        return None

    reason = f"job_failed:{code or 'generation_error'}"
    reset = reset_video_runtime_cache(reason)
    with VIDEO_RUNTIME_LOCK:
        VIDEO_RUNTIME_CACHE["last_error"] = str(message or "")[:500]
        VIDEO_RUNTIME_CACHE["last_failure_code"] = code or "generation_error"
        VIDEO_RUNTIME_CACHE["invalidated_at"] = utc_now_iso()
        VIDEO_RUNTIME_CACHE["invalidation_reason"] = reason

    cleanup: dict[str, Any] | None = None
    lowered = str(message or "").lower()
    if "out of memory" in lowered or ("cuda" in lowered and "memory" in lowered):
        cleanup = {"memory_before": cuda_memory_snapshot(), "memory_after": clear_cuda_memory()}

    return {
        "video_runtime_invalidated": True,
        "reason": reason,
        "reset": reset,
        "cleanup": cleanup,
    }


def runtime_memory_status_snapshot(action: str = "runtime_memory_status") -> dict[str, Any]:
    image_active = image_runtime_cache_active()
    image_key = image_runtime_cache_key()
    video_cache = _video_runtime_cache_snapshot()
    memory = cuda_memory_snapshot()
    comfy_status: dict[str, Any] | None = None
    try:
        comfy_status = _ws().handle_comfy_runtime_status_command({})
    except Exception as exc:
        comfy_status = {
            "type": "comfy_runtime_status",
            "ok": False,
            "error": str(exc),
        }

    return {
        "type": "runtime_memory_status",
        "ok": True,
        "action": action,
        "timestamp": utc_now_iso(),
        "image_runtime": {
            "active": image_active,
            "model_key": image_key or None,
            "affinity_t2i": _ws().active_affinity_signature_for_command("t2i"),
            "affinity_i2i": _ws().active_affinity_signature_for_command("i2i"),
        },
        "video_runtime": {
            "active": bool(video_cache.get("active_signature")),
            "active_command": video_cache.get("active_command"),
            "active_signature": video_cache.get("active_signature"),
            "active_summary": video_cache.get("active_summary"),
            "active_family": video_cache.get("active_family"),
            "active_stack_kind": video_cache.get("active_stack_kind"),
            "active_backend_type": video_cache.get("active_backend_type"),
            "active_backend_name": video_cache.get("active_backend_name"),
            "updated_at": video_cache.get("updated_at"),
            "reset_reason": video_cache.get("reset_reason"),
            "last_success_at": video_cache.get("last_success_at"),
            "last_prompt_id": video_cache.get("last_prompt_id"),
            "last_output": video_cache.get("last_output"),
            "last_error": video_cache.get("last_error"),
            "last_failure_code": video_cache.get("last_failure_code"),
            "invalidated_at": video_cache.get("invalidated_at"),
            "invalidation_reason": video_cache.get("invalidation_reason"),
            "comfy_runtime_endpoint": video_cache.get("comfy_runtime_endpoint"),
            "comfy_runtime_pid": video_cache.get("comfy_runtime_pid"),
            "comfy_runtime_detected_pid": video_cache.get("comfy_runtime_detected_pid"),
            "comfy_runtime_started_at": video_cache.get("comfy_runtime_started_at"),
            "comfy_runtime_state": video_cache.get("comfy_runtime_state"),
            "comfy_runtime_ownership": video_cache.get("comfy_runtime_ownership"),
            "comfy_runtime_running": bool(video_cache.get("comfy_runtime_running", False)),
            "comfy_runtime_healthy": bool(video_cache.get("comfy_runtime_healthy", False)),
            "comfy_runtime_endpoint_alive": bool(video_cache.get("comfy_runtime_endpoint_alive", False)),
            "comfy_runtime_checked_at": video_cache.get("comfy_runtime_checked_at"),
            "affinity_t2v": _ws().active_affinity_signature_for_command("t2v"),
            "affinity_i2v": _ws().active_affinity_signature_for_command("i2v"),
        },
        "memory": memory,
        "comfy_runtime": comfy_status,
    }


def runtime_memory_ack(action: str, ok: bool = True, **fields: Any) -> dict[str, Any]:
    payload = runtime_memory_status_snapshot(action)
    payload["type"] = "runtime_memory_ack"
    payload["ok"] = ok
    payload.update(fields)
    return payload


def handle_runtime_memory_control_command(req: dict[str, Any]) -> dict[str, Any]:
    command = str(req.get("command") or "").strip().lower()

    if command in {"runtime_memory_status", "runtime_diagnostics"}:
        return runtime_memory_status_snapshot(command)

    if command == "unload_image_runtime":
        cleanup = unload_cached_pipelines()
        return runtime_memory_ack(
            command,
            image_runtime_unloaded=True,
            cleanup=cleanup,
            message="Image runtime cache unloaded and local CUDA cache cleared.",
        )

    if command == "unload_video_runtime":
        reset = reset_video_runtime_cache("manual_unload_video_runtime")
        memory_before = cuda_memory_snapshot()
        memory_after = clear_cuda_memory()
        return runtime_memory_ack(
            command,
            video_runtime_unloaded=True,
            video_runtime_reset=reset,
            cleanup={"memory_before": memory_before, "memory_after": memory_after},
            message="Video runtime affinity cache reset and local CUDA cache cleared. ComfyUI process was not stopped.",
        )

    if command == "unload_all_runtimes":
        image_cleanup = unload_cached_pipelines()
        video_reset = reset_video_runtime_cache("manual_unload_all_runtimes")
        comfy_free = request_comfy_free_memory()
        memory_after = clear_cuda_memory()
        comfy_ok = bool(comfy_free.get("ok"))
        return runtime_memory_ack(
            command,
            ok=comfy_ok,
            image_runtime_unloaded=True,
            video_runtime_unloaded=True,
            image_cleanup=image_cleanup,
            video_runtime_reset=video_reset,
            comfy_free=comfy_free,
            cleanup={"memory_after": memory_after},
            message=(
                "Image runtime cache unloaded, video runtime affinity cache reset, Comfy /free requested, and local CUDA cache cleared."
                if comfy_ok
                else "Image/video caches cleared, but Comfy /free failed — adopted models may still be resident."
            ),
        )

    if command == "clear_cuda_cache":
        memory_before = cuda_memory_snapshot()
        memory_after = clear_cuda_memory()
        return runtime_memory_ack(
            command,
            cuda_cache_cleared=True,
            cleanup={"memory_before": memory_before, "memory_after": memory_after},
            message="Local Python CUDA cache cleared.",
        )

    return {
        "type": "runtime_memory_ack",
        "ok": False,
        "action": command,
        "error": f"Unknown runtime memory command: {command}",
    }


def build_pipelines(model_name_or_path: str, requested_family: str | None = None) -> tuple[Any, Any, str, str, str]:
    # ONE shared-weight load (t2i + a from_pipe i2i companion) instead of two
    # independent from_single_file copies on the GPU, plus a CPU-side
    # fp32->fp16 cast for fp32-on-disk checkpoints. This is the drop-in
    # integration documented in memory_optimization.build_paired_pipelines.
    #
    # Return shape and the MODEL_CACHE contract are preserved EXACTLY: callers
    # (run_t2i, run_i2i, cleanup_for_model_swap) still receive
    # (t2i_pipe, i2i_pipe, device, dtype_str, detected). The i2i pipe stays
    # reachable as a weight-sharing companion rather than a second full GPU copy.
    #
    # On a >=16GB card auto_select_memory_profile returns PERFORMANCE, so no CPU
    # offload is enabled -- full speed, just deduplicated + fp16.
    profile = auto_select_memory_profile()
    result = build_paired_pipelines(
        model_name_or_path,
        detect_pipeline_type=_ws().detect_pipeline_type,
        profile=profile,
        cast_fp32_to_fp16=CAST_FP32_TO_FP16,
        requested_family=requested_family,
    )

    report = result.report
    # WARNING (not INFO): the root logger defaults to WARNING, so INFO is
    # filtered. This line finally makes the actually-resident dtype and the
    # post-load VRAM visible in the worker log.
    logging.warning(
        "[t2i] pipeline ready: detected=%s requested_dtype=%s resident_dtype=%s "
        "profile=%s cuda_allocated_gb=%.2f cuda_reserved_gb=%.2f total_gb=%.2f "
        "cast_fp32_to_fp16=%s notes=%s",
        result.detected,
        result.dtype_str,
        report.resident_dtype,
        report.profile,
        report.allocated_gb,
        report.reserved_gb,
        report.total_gb,
        CAST_FP32_TO_FP16,
        ",".join(report.notes),
    )

    return (
        result.t2i_pipe,
        result.i2i_pipe,
        result.device,
        result.dtype_str,
        result.detected,
    )


def _get_or_load_pipelines_locked(model_name_or_path: str, requested_family: str | None = None) -> tuple[Any, Any, str, str, str, bool, dict[str, Any] | None]:
    with CACHE_LOCK:
        identity = cache_identity(model_name_or_path, requested_family)
        if MODEL_CACHE["key"] == identity and MODEL_CACHE["pipe"] is not None:
            return (
                MODEL_CACHE["pipe"],
                MODEL_CACHE["img2img_pipe"],
                MODEL_CACHE["device"],
                MODEL_CACHE["dtype"],
                MODEL_CACHE["detected"],
                True,
                None,
            )

    swap_cleanup_stats = cleanup_for_model_swap(cache_identity(model_name_or_path, requested_family))

    load_start = time.perf_counter()
    t2i_pipe, i2i_pipe, device, dtype, detected = build_pipelines(model_name_or_path, requested_family)
    load_time_sec = round(time.perf_counter() - load_start, 3)
    memory_after_load = cuda_memory_snapshot()

    with CACHE_LOCK:
        MODEL_CACHE["key"] = cache_identity(model_name_or_path, requested_family)
        MODEL_CACHE["pipe"] = t2i_pipe
        MODEL_CACHE["img2img_pipe"] = i2i_pipe
        MODEL_CACHE["device"] = device
        MODEL_CACHE["dtype"] = dtype
        MODEL_CACHE["detected"] = detected

    if swap_cleanup_stats is None:
        current_memory = cuda_memory_snapshot()
        swap_cleanup_stats = {
            "old_key": None,
            "requested_key": model_name_or_path,
            "cleanup_time_sec": 0.0,
            "memory_before": current_memory,
            "memory_after": current_memory,
        }

    swap_cleanup_stats["model_load_time_sec"] = load_time_sec
    swap_cleanup_stats["memory_after_load"] = memory_after_load

    return t2i_pipe, i2i_pipe, device, dtype, detected, False, swap_cleanup_stats


def get_or_load_pipelines(model_name_or_path: str, requested_family: str | None = None) -> tuple[Any, Any, str, str, str, bool, dict[str, Any] | None]:
    with MODEL_LOAD_LOCK:
        return _get_or_load_pipelines_locked(model_name_or_path, requested_family)

