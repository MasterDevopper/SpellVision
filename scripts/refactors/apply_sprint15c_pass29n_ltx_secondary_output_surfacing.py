from pathlib import Path

path = Path("python/worker_service.py")
text = path.read_text(encoding="utf-8")

# ------------------------------------------------------------
# Patch 1: Extend JobResult with LTX/video multi-output fields.
# ------------------------------------------------------------
if "video_outputs: list[dict[str, Any]] | None = None" not in text:
    needle = '''    metadata_write_error: str | None = None
'''
    insert = '''    metadata_write_error: str | None = None
    video_outputs: list[dict[str, Any]] | None = None
    video_output_count: int = 0
    video_primary_output_role: str | None = None
    video_secondary_output: str | None = None
    video_secondary_metadata_output: str | None = None
    ltx_full_output: str | None = None
    ltx_full_metadata_output: str | None = None
    ltx_distilled_output: str | None = None
    ltx_distilled_metadata_output: str | None = None
'''
    if needle not in text:
        raise SystemExit("Could not find JobResult metadata_write_error field.")
    text = text.replace(needle, insert, 1)

# ------------------------------------------------------------
# Patch 2: complete_job must copy the new payload fields.
# ------------------------------------------------------------
if "video_outputs=payload.get(\"video_outputs\")" not in text:
    needle = '''        metadata_write_error=payload.get("metadata_write_error"),
    )
'''
    insert = '''        metadata_write_error=payload.get("metadata_write_error"),
        video_outputs=payload.get("video_outputs") if isinstance(payload.get("video_outputs"), list) else None,
        video_output_count=int(payload.get("video_output_count") or 0),
        video_primary_output_role=payload.get("video_primary_output_role"),
        video_secondary_output=payload.get("video_secondary_output"),
        video_secondary_metadata_output=payload.get("video_secondary_metadata_output"),
        ltx_full_output=payload.get("ltx_full_output"),
        ltx_full_metadata_output=payload.get("ltx_full_metadata_output"),
        ltx_distilled_output=payload.get("ltx_distilled_output"),
        ltx_distilled_metadata_output=payload.get("ltx_distilled_metadata_output"),
    )
'''
    if needle not in text:
        raise SystemExit("Could not find complete_job JobResult constructor ending.")
    text = text.replace(needle, insert, 1)

# ------------------------------------------------------------
# Patch 3: Replace LTX payload builder with multi-output surfacing.
# ------------------------------------------------------------
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
            "size_bytes": int(item.get("size_bytes") or (_file_size_bytes(path) if Path(path).exists() else 0)),
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

    primary = snapshot.get("primary_output") if isinstance(snapshot.get("primary_output"), dict) else {}
    if not primary and isinstance(result.get("primary_output"), dict):
        primary = result.get("primary_output") or {}

    primary_variant = None
    if video_outputs:
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
        "video_outputs": video_outputs,
        "video_output_count": len(video_outputs),
        "video_primary_output_role": str(primary.get("role") or ""),
        "video_secondary_output": secondary_output.get("path") if secondary_output else None,
        "video_secondary_metadata_output": secondary_output.get("metadata_path") if secondary_output else None,
        "ltx_full_output": full_output.get("path") if full_output else None,
        "ltx_full_metadata_output": full_output.get("metadata_path") if full_output else None,
        "ltx_distilled_output": distilled_output.get("path") if distilled_output else None,
        "ltx_distilled_metadata_output": distilled_output.get("metadata_path") if distilled_output else None,
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

# ------------------------------------------------------------
# Patch 4: Carry multi-output metadata into video history entries.
# ------------------------------------------------------------
if '"video_outputs": result.get("video_outputs")' not in text:
    needle = '''        "output_video": output_path,
        "video_path": output_path,
'''
    insert = '''        "output_video": output_path,
        "video_path": output_path,
        "video_outputs": result.get("video_outputs") if isinstance(result.get("video_outputs"), list) else [],
        "video_output_count": int(result.get("video_output_count") or 0),
        "video_primary_output_role": result.get("video_primary_output_role"),
        "video_secondary_output": result.get("video_secondary_output"),
        "video_secondary_metadata_output": result.get("video_secondary_metadata_output"),
        "ltx_full_output": result.get("ltx_full_output"),
        "ltx_full_metadata_output": result.get("ltx_full_metadata_output"),
        "ltx_distilled_output": result.get("ltx_distilled_output"),
        "ltx_distilled_metadata_output": result.get("ltx_distilled_metadata_output"),
'''
    if needle not in text:
        raise SystemExit("Could not find video history insertion point.")
    text = text.replace(needle, insert, 1)

path.write_text(text, encoding="utf-8")
print("Applied Sprint 15C Pass 29N: LTX secondary/full output surfacing.")
