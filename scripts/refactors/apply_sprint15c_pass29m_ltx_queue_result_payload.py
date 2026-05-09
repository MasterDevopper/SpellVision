from pathlib import Path

path = Path("python/worker_service.py")
text = path.read_text(encoding="utf-8")

start_marker = 'def _ltx_prompt_api_job_payload(snapshot: dict[str, Any], req: dict[str, Any], job: "JobRecord") -> dict[str, Any]:'
end_marker = '\ndef run_ltx_prompt_api_queued_job('

start = text.find(start_marker)
if start < 0:
    raise SystemExit("Could not find _ltx_prompt_api_job_payload start.")

end = text.find(end_marker, start)
if end < 0:
    raise SystemExit("Could not find run_ltx_prompt_api_queued_job after payload function.")

replacement = r'''def _ltx_prompt_api_job_payload(snapshot: dict[str, Any], req: dict[str, Any], job: "JobRecord") -> dict[str, Any]:
    result = snapshot.get("spellvision_result") if isinstance(snapshot.get("spellvision_result"), dict) else {}
    model_stack = result.get("model_stack") if isinstance(result.get("model_stack"), dict) else {}
    if not model_stack and isinstance(snapshot.get("model_stack"), dict):
        model_stack = snapshot.get("model_stack") or {}

    primary = snapshot.get("primary_output") if isinstance(snapshot.get("primary_output"), dict) else {}
    if not primary and isinstance(result.get("primary_output"), dict):
        primary = result.get("primary_output") or {}

    if not primary and isinstance(snapshot.get("ui_outputs"), list) and snapshot.get("ui_outputs"):
        first = snapshot.get("ui_outputs", [])[0]
        if isinstance(first, dict):
            primary = first

    if not primary and isinstance(result.get("outputs"), list) and result.get("outputs"):
        for item in result.get("outputs", []):
            if isinstance(item, dict) and item.get("role") == "full":
                primary = item
                break
        if not primary:
            first = result.get("outputs", [])[0]
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

    frames = _safe_int(
        req.get("frames")
        or req.get("video_frames")
        or req.get("frame_count")
        or req.get("video_frame_count")
        or model_stack.get("frames"),
        0,
    )
    fps = _safe_int(req.get("fps") or req.get("video_fps") or model_stack.get("fps"), 0)
    width = _safe_int(req.get("width") or req.get("video_width") or model_stack.get("width"), 0)
    height = _safe_int(req.get("height") or req.get("video_height") or model_stack.get("height"), 0)
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
        "video_model_stack_summary": _video_stack_basename(model_stack.get("model") or req.get("video_primary_model") or req.get("model")),
        "video_primary_model": str(req.get("video_primary_model") or model_stack.get("model") or ""),
        "video_primary_model_name": _video_stack_basename(req.get("video_primary_model") or model_stack.get("model")),
        "video_vae": str(req.get("video_vae") or model_stack.get("video_vae") or model_stack.get("audio_vae") or ""),
        "video_vae_name": _video_stack_basename(req.get("video_vae") or model_stack.get("video_vae") or model_stack.get("audio_vae")),
        "video_text_encoder": str(req.get("video_text_encoder") or model_stack.get("text_encoder") or model_stack.get("text_projection") or ""),
        "video_text_encoder_name": _video_stack_basename(req.get("video_text_encoder") or model_stack.get("text_encoder") or model_stack.get("text_projection")),
        "video_width": width,
        "video_height": height,
        "video_resolution": f"{width}x{height}" if width > 0 and height > 0 else "",
        "video_frames": frames,
        "video_frame_count": frames,
        "video_fps": fps,
        "video_duration_seconds": duration_seconds,
        "video_duration_label": video_duration_label(frames, fps) if frames > 0 and fps > 0 else None,
        "video_has_input_image": bool(req.get("video_has_input_image", False)),
        "video_input_image": req.get("video_input_image") or req.get("input_image"),
        "video_input_name": req.get("video_input_name"),
        "video_completion_summary": "LTX Prompt API video generation complete",
    }

    try:
        payload.update(output_finalization_contract(
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

'''

text = text[:start] + replacement + text[end:]
path.write_text(text, encoding="utf-8")

print("Applied Sprint 15C Pass 29M: normalized LTX queue result payload into JobResult-compatible fields.")
