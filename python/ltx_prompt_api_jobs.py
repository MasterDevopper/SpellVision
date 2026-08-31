"""LTX Prompt-API job normalize / payload / queued runner.

Extracted from worker_service.py. Worker-owned helpers resolve lazily.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

from ltx_prompt_api_submission import ltx_prompt_api_gated_submission_snapshot
from comfy_root import comfy_user_workflow
from worker_service_state import (
    ActiveJobHandle,
    JobEmitter,
    JobRecord,
    JobState,
    complete_job,
    raise_if_cancelled,
    transition_job,
    update_job_progress,
)


def _ws():
    import worker_service as ws
    return ws


def _normalize_ltx_prompt_api_request(req: dict[str, Any]) -> dict[str, Any]:
    ltx_req = copy.deepcopy(req)
    ltx_req["command"] = "ltx_prompt_api_gated_submission"
    ltx_req["worker_command"] = "ltx_prompt_api_gated_submission"
    ltx_req["execution_command"] = "ltx_prompt_api_gated_submission"
    ltx_req["dispatch_command"] = "ltx_prompt_api_gated_submission"
    ltx_req["task_command"] = "ltx_prompt_api_gated_submission"
    ltx_req["workflow_task_command"] = "ltx_prompt_api_gated_submission"

    ltx_req["queue_display_command"] = ltx_req.get("queue_display_command") or ltx_req.get("mode") or "t2v"
    ltx_req["source_generation_mode"] = ltx_req.get("source_generation_mode") or ltx_req["queue_display_command"]
    ltx_req["generation_mode"] = ltx_req.get("generation_mode") or ltx_req["queue_display_command"]
    ltx_req["mode"] = ltx_req.get("mode") or ltx_req["queue_display_command"]

    ltx_req["family"] = "ltx"
    ltx_req["model_family"] = "ltx"
    ltx_req["video_family"] = "ltx"
    ltx_req["resolved_native_video_family"] = "ltx"
    ltx_req["backend"] = "comfy_prompt_api"
    ltx_req["video_backend_route"] = "prompt_api"
    ltx_req["video_backend_type"] = "comfy_prompt_api"
    ltx_req["video_backend_name"] = "LTX Prompt API"
    ltx_req["video_uses_prompt_api_backend"] = True
    ltx_req["video_validated_prompt_api_family"] = True
    ltx_req["video_validated_backend"] = True
    ltx_req["video_readiness_ok"] = True

    # Sprint 15C Pass 29L:
    # Qt may queue an LTX request without carrying the Prompt API export path.
    # The LTX backend is Prompt-API-template based, so preserve any explicit
    # path and otherwise fall back to the standard exported LTX API graph.
    ltx_prompt_api_export_path = str(
        ltx_req.get("prompt_api_export_path")
        or ltx_req.get("ltx_prompt_api_export_path")
        or ltx_req.get("api_workflow_path")
        or ltx_req.get("workflow_prompt_api_path")
        or os.environ.get("SPELLVISION_LTX_PROMPT_API_EXPORT")
        # Derived from the resolved install rather than a literal into the rollback tree.
        or str(comfy_user_workflow("ltx_api.json"))
        or ""
    ).strip()
    if ltx_prompt_api_export_path:
        ltx_req["prompt_api_export_path"] = ltx_prompt_api_export_path
        ltx_req["ltx_prompt_api_export_path"] = ltx_prompt_api_export_path
        ltx_req["api_workflow_path"] = ltx_prompt_api_export_path
        ltx_req["workflow_prompt_api_path"] = ltx_prompt_api_export_path
    ltx_req["submit_to_comfy"] = True
    ltx_req["dry_run"] = False
    ltx_req["wait_for_result"] = True
    ltx_req["capture_metadata"] = True
    ltx_req["register_result"] = True
    ltx_req["request_register_result"] = True
    ltx_req["status"] = "submitting LTX Prompt API graph"
    ltx_req["status_text"] = "submitting LTX Prompt API graph"

    return ltx_req



def _queue_ltx_execution_command(req: dict[str, Any], fallback: str = "") -> str:
    """Return the execution command for queued jobs without losing display mode."""
    ltx_command = "ltx_prompt_api_gated_submission"

    for key in ("worker_command", "execution_command", "dispatch_command", "command", "task_command", "workflow_task_command"):
        command = str(req.get(key) or "").strip().lower()
        if command == ltx_command:
            return ltx_command

    if "LTX_PROMPT_API_DISPATCH_COMMANDS" in globals():
        for key in ("worker_command", "execution_command", "dispatch_command", "command", "task_command", "workflow_task_command"):
            command = str(req.get(key) or "").strip().lower()
            if command in globals()["LTX_PROMPT_API_DISPATCH_COMMANDS"]:
                return ltx_command

    # Native-LTX migration (Step 4): the old broad "ltx-in-haystack" auto-promotion
    # was removed. A fresh t2v/i2v LTX request now flows to the native path + gate
    # (run_native_video -> _infer_native_video_family -> gate), exactly like Wan.
    # Only an EXPLICIT ltx_prompt_api_* command (history requeue / fallback) routes
    # to the prompt-api engine. Family decisions live in resolved_native_video_family,
    # never a substring haystack (that haystack also matched Wan — the entanglement).
    return str(fallback or "").strip().lower()


def _ltx_prompt_api_job_payload(snapshot: dict[str, Any], req: dict[str, Any], job: "JobRecord") -> dict[str, Any]:
    result = snapshot.get("spellvision_result") if isinstance(snapshot.get("spellvision_result"), dict) else {}
    model_stack = result.get("model_stack") if isinstance(result.get("model_stack"), dict) else {}
    if not model_stack and isinstance(snapshot.get("model_stack"), dict):
        model_stack = snapshot.get("model_stack") or {}

    def _preferred_ltx_output_role() -> str:
        raw = str(
            req.get("ltx_preferred_output")
            or req.get("ltx_output_variant")
            or req.get("video_output_variant")
            or req.get("preferred_output_variant")
            or req.get("video_ltx_preferred_output")
            or req.get("preferred_ltx_output")
            or req.get("video_preferred_output")
            or req.get("preferred_output")
            or req.get("ltx_output_preference")
            or req.get("video_output_preference")
            or req.get("ltx_primary_output_role")
            or req.get("primary_output_role")
            or ""
        ).strip().lower()

        normalized = raw.replace("-", "_").replace(" ", "_")

        if normalized in {"distilled", "d", "output_d", "ltx_distilled", "distilled_output"}:
            return "distilled"

        if normalized in {"full", "f", "output_f", "ltx_full", "full_output"}:
            return "full"

        # Sprint 15C Pass 29P v5:
        # Match the visible UI default. The LTX Launch Options panel defaults
        # Preferred output to "distilled", so missing request fields should not
        # silently promote Full.
        return "distilled"

    def _infer_ltx_output_role(item: dict[str, Any]) -> str:
        role = str(item.get("role") or "").strip().lower()
        if role:
            return role

        filename = str(item.get("filename") or item.get("path") or item.get("uri") or "").lower()
        if "output_f" in filename or "_f_" in filename:
            return "full"
        if "output_d" in filename or "_d_" in filename:
            return "distilled"
        return "video"

    def _label_for_role(role: str) -> str:
        if role == "full":
            return "LTX Full"
        if role == "distilled":
            return "LTX Distilled"
        return "LTX Video"

    def _normalize_ltx_output(item: dict[str, Any], index: int) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None

        filename = str(item.get("filename") or "").strip()
        path = str(item.get("path") or item.get("uri") or item.get("preview_path") or "").strip()

        if not path and filename:
            root = str(snapshot.get("output_root") or result.get("output_root") or "").strip()
            subfolder = str(item.get("subfolder") or "").strip()
            if root:
                path_obj = Path(root)
                if subfolder:
                    path_obj = path_obj / subfolder
                path = str(path_obj / filename)

        if not path:
            return None

        if not filename:
            filename = Path(path).name

        role = _infer_ltx_output_role(item)
        metadata_path = str(item.get("metadata_path") or f"{path}.spellvision.json").strip()

        return {
            "id": str(item.get("id") or f"ltx-{snapshot.get('prompt_id') or result.get('prompt_id') or job.job_id}-{index}"),
            "kind": str(item.get("kind") or item.get("media_type") or "video"),
            "role": role,
            "family": "ltx",
            "label": str(item.get("label") or _label_for_role(role)),
            "node_id": str(item.get("node_id") or ""),
            "bucket": str(item.get("bucket") or ""),
            "filename": filename,
            "path": path,
            "uri": path,
            "exists": bool(item.get("exists", Path(path).exists())),
            "size_bytes": int(item.get("size_bytes") or (_ws()._file_size_bytes(path) if Path(path).exists() else 0)),
            "animated": bool(item.get("animated", True)),
            "metadata_path": metadata_path,
            "metadata_exists": bool(Path(metadata_path).exists()) if metadata_path else False,
            "preview_path": path,
            "openable": True,
            "requeue_supported": True,
            "send_to_mode": "t2v",
        }

    raw_outputs: list[Any] = []
    for candidate in (
        result.get("outputs"),
        snapshot.get("ui_outputs"),
        snapshot.get("outputs"),
    ):
        if isinstance(candidate, list) and candidate:
            raw_outputs = candidate
            break

    video_outputs: list[dict[str, Any]] = []
    for index, item in enumerate(raw_outputs):
        normalized = _normalize_ltx_output(item, index)
        if normalized:
            video_outputs.append(normalized)

    preferred_role = _preferred_ltx_output_role()

    primary = snapshot.get("primary_output") if isinstance(snapshot.get("primary_output"), dict) else {}
    if not primary and isinstance(result.get("primary_output"), dict):
        primary = result.get("primary_output") or {}

    primary_variant = None
    if video_outputs:
        # Sprint 15C Pass 29P: preferred output controls primary preview/result.
        primary_variant = next((item for item in video_outputs if item.get("role") == preferred_role), None)

        # Fallback: Full remains the default final-quality candidate.
        if primary_variant is None:
            primary_variant = next((item for item in video_outputs if item.get("role") == "full"), None)

        if primary_variant is None and primary:
            primary_path = str(primary.get("path") or primary.get("uri") or "").strip()
            primary_variant = next((item for item in video_outputs if str(item.get("path") or "") == primary_path), None)

        if primary_variant is None:
            primary_variant = video_outputs[0]

    if primary_variant:
        primary = primary_variant

    if not primary and isinstance(snapshot.get("ui_outputs"), list) and snapshot.get("ui_outputs"):
        first = snapshot.get("ui_outputs", [])[0]
        if isinstance(first, dict):
            primary = first

    output_path = str(
        primary.get("path")
        or primary.get("uri")
        or snapshot.get("primary_output_path")
        or result.get("primary_output_path")
        or req.get("output")
        or ""
    ).strip()

    metadata_path = str(
        primary.get("metadata_path")
        or snapshot.get("primary_metadata_path")
        or result.get("primary_metadata_path")
        or req.get("metadata_output")
        or ""
    ).strip()

    prompt_id = str(snapshot.get("prompt_id") or result.get("prompt_id") or "").strip()

    full_output = next((item for item in video_outputs if item.get("role") == "full"), None)
    distilled_output = next((item for item in video_outputs if item.get("role") == "distilled"), None)
    secondary_output = next((item for item in video_outputs if item.get("path") != output_path), None)

    frames = _ws()._safe_int(
        req.get("frames")
        or req.get("video_frames")
        or req.get("frame_count")
        or req.get("video_frame_count")
        or model_stack.get("frames"),
        0,
    )
    fps = _ws()._safe_int(req.get("fps") or req.get("video_fps") or model_stack.get("fps"), 0)
    width = _ws()._safe_int(req.get("width") or req.get("video_width") or model_stack.get("width"), 0)
    height = _ws()._safe_int(req.get("height") or req.get("video_height") or model_stack.get("height"), 0)
    duration_seconds = round(float(frames) / float(fps), 3) if frames > 0 and fps > 0 else 0.0

    payload = {
        "ok": bool(snapshot.get("ok", False)),
        "output": output_path,
        "metadata_output": metadata_path,
        "video_output": output_path,
        "output_video": output_path,
        "video_path": output_path,
        "video_metadata_output": metadata_path,
        "backend_name": "LTX Prompt API",
        "detected_pipeline": "ltx_prompt_api_gated_submission",
        "task_type": str(req.get("queue_display_command") or req.get("source_generation_mode") or req.get("mode") or "t2v"),
        "source_job_id": req.get("retry_of"),
        "retry_count": int(req.get("retry_count") or 0),
        "video_backend_type": "comfy_prompt_api",
        "video_backend_name": "LTX Prompt API",
        "video_request_kind": str(req.get("queue_display_command") or req.get("mode") or "t2v"),
        "video_stack_kind": "ltx_prompt_api",
        "video_stack_mode": str(req.get("video_stack_mode") or "single_model"),
        "video_stack_ready": True,
        "video_prompt_id": prompt_id,
        "prompt_id": prompt_id,
        "submission_status": snapshot.get("submission_status"),
        "video_family": "ltx",
        "video_family_display_name": "LTX-Video",
        "video_family_validation_status": "experimental",
        "video_family_validated": False,
        "video_family_production_ready": False,
        "video_family_backend_route": "comfy_prompt_api",
        "video_family_contract_stack_kind": "single_transformer_or_workflow",
        "video_family_required_components": ["model", "vae", "text_encoder"],
        "video_family_optional_components": ["image_encoder", "lora", "scheduler_profile"],
        "video_family_history_label_style": "single_model_stack",
        "video_family_runtime_affinity_fields": ["family", "stack_kind", "model", "vae", "text_encoder", "workflow_or_template", "backend_route"],
        "video_family_readiness_notes": ["LTX Prompt API path completed through Comfy workflow export."],
        "video_family_contract_version": 1,
        "video_model_stack_summary": _ws()._video_stack_basename(model_stack.get("model") or req.get("video_primary_model") or req.get("model")),
        "video_primary_model": str(req.get("video_primary_model") or model_stack.get("model") or ""),
        "video_primary_model_name": _ws()._video_stack_basename(req.get("video_primary_model") or model_stack.get("model")),
        "video_vae": str(req.get("video_vae") or model_stack.get("video_vae") or model_stack.get("audio_vae") or ""),
        "video_vae_name": _ws()._video_stack_basename(req.get("video_vae") or model_stack.get("video_vae") or model_stack.get("audio_vae")),
        "video_text_encoder": str(req.get("video_text_encoder") or model_stack.get("text_encoder") or model_stack.get("text_projection") or ""),
        "video_text_encoder_name": _ws()._video_stack_basename(req.get("video_text_encoder") or model_stack.get("text_encoder") or model_stack.get("text_projection")),
        "video_width": width,
        "video_height": height,
        "video_resolution": f"{width}x{height}" if width > 0 and height > 0 else "",
        "video_frames": frames,
        "video_frame_count": frames,
        "video_fps": fps,
        "video_duration_seconds": duration_seconds,
        "_ws().video_duration_label": _ws().video_duration_label(frames, fps) if frames > 0 and fps > 0 else None,
        "video_has_input_image": bool(req.get("video_has_input_image", False)),
        "video_input_image": req.get("video_input_image") or req.get("input_image"),
        "video_input_name": req.get("video_input_name"),
        "video_completion_summary": "LTX Prompt API video generation complete",
        "video_outputs": video_outputs,
        "video_output_count": len(video_outputs),
        "video_primary_output_role": str(primary.get("role") or ""),
        "video_preferred_output_role": preferred_role,
        "ltx_preferred_output": preferred_role,
        "video_secondary_output": secondary_output.get("path") if secondary_output else None,
        "video_secondary_metadata_output": secondary_output.get("metadata_path") if secondary_output else None,
        "ltx_full_output": full_output.get("path") if full_output else None,
        "ltx_full_metadata_output": full_output.get("metadata_path") if full_output else None,
        "ltx_distilled_output": distilled_output.get("path") if distilled_output else None,
        "ltx_distilled_metadata_output": distilled_output.get("metadata_path") if distilled_output else None,
    }

    try:
        payload.update(_ws().output_finalization_contract(
            output_path,
            metadata_path,
            original_output=str(req.get("original_output") or req.get("output") or ""),
            media_type="video",
            metadata_write_status="written" if metadata_path and Path(metadata_path).exists() else "unknown",
        ))
    except Exception as exc:
        payload["output_contract_ok"] = False
        payload["output_contract_warnings"] = ["output_contract_build_failed"]
        payload["metadata_write_error"] = str(exc)

    return payload


def run_ltx_prompt_api_queued_job(req: dict[str, Any], emitter: JobEmitter, job: "JobRecord", active_job: ActiveJobHandle) -> dict[str, Any]:
    ltx_req = _normalize_ltx_prompt_api_request(req)

    transition_job(job, JobState.STARTING)
    emitter.status(job, "submitting LTX Prompt API graph")
    emitter.emit_job_update(job)
    raise_if_cancelled(active_job, emitter, "ltx prompt api submission")

    runtime_status: dict[str, Any] = {}
    try:
        runtime_status = _ws().handle_comfy_runtime_status_command({})
    except Exception as exc:
        runtime_status = {"ok": False, "error": str(exc)}

    transition_job(job, JobState.RUNNING)
    emitter.status(job, "running LTX Prompt API submission")
    emitter.emit_job_update(job)

    # Registered here rather than after the call returns: the snapshot submits AND polls to
    # completion internally, so anything downstream of it runs after the render has finished.
    from comfy_prompt_client import track_comfy_prompt

    snapshot = ltx_prompt_api_gated_submission_snapshot(
        ltx_req,
        runtime_status=runtime_status,
        on_submitted=lambda endpoint, prompt_id: track_comfy_prompt(active_job, endpoint, prompt_id),
    )
    emitter.emit(snapshot)

    raise_if_cancelled(active_job, emitter, "ltx prompt api completion")

    ok = bool(snapshot.get("ok", False))
    submitted = bool(snapshot.get("submitted", False))
    completed = bool(snapshot.get("result_completed", False) or snapshot.get("completed", False))

    if not ok or not submitted:
        reasons = snapshot.get("blocked_submit_reasons") or snapshot.get("adapter_blocked_submit_reasons") or []
        submit_error = str(snapshot.get("submit_error") or snapshot.get("error") or "").strip()
        reason_text = ", ".join(str(reason) for reason in reasons) if reasons else ""
        message = submit_error or reason_text or str(snapshot.get("submission_status") or "LTX Prompt API submission failed")
        raise RuntimeError(message)

    payload = _ltx_prompt_api_job_payload(snapshot, ltx_req, job)

    if completed:
        update_job_progress(job, 1, 1, "LTX Prompt API completed")

    complete_job(job, payload)
    emitter.emit_job_update(job)
    return payload


