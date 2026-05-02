from __future__ import annotations

from pathlib import Path


def patch_file(path: Path, replacements: list[tuple[str, str]]) -> None:
    text = path.read_text(encoding="utf-8")
    original = text
    for old, new in replacements:
        if old not in text:
            raise SystemExit(f"Pattern not found in {path}: {old[:120]!r}")
        text = text.replace(old, new, 1)
    if text != original:
        path.write_text(text, encoding="utf-8")


worker_client = Path("python/worker_client.py")
patch_file(worker_client, [
    (
        'LTX_MATERIALIZATION_MESSAGE_TYPES = {"ltx_workflow_materialization_dry_run", "video_family_materialization_dry_run"}\n',
        'LTX_MATERIALIZATION_MESSAGE_TYPES = {"ltx_workflow_materialization_dry_run", "video_family_materialization_dry_run"}\nLTX_GRAPH_INSPECTION_MESSAGE_TYPES = {"ltx_workflow_graph_inspection", "ltx_prompt_api_normalization_preview", "video_family_graph_inspection", "video_family_prompt_api_normalization_preview"}\n',
    ),
    (
        '"ltx_workflow_materialization_dry_run", "ltx_materialize_workflow", "ltx_t2v_materialize_dry_run", "video_family_materialization_dry_run"}',
        '"ltx_workflow_materialization_dry_run", "ltx_materialize_workflow", "ltx_t2v_materialize_dry_run", "video_family_materialization_dry_run", "ltx_workflow_graph_inspection", "ltx_prompt_api_normalization_preview", "video_family_graph_inspection", "video_family_prompt_api_normalization_preview"}',
    ),
    (
        '    if message_type in LTX_MATERIALIZATION_MESSAGE_TYPES:\n        normalized = dict(payload)\n        if last_job_id and "job_id" not in normalized:\n            normalized["job_id"] = last_job_id\n        return normalized, normalized.get("job_id", last_job_id)\n\n    return (\n',
        '    if message_type in LTX_MATERIALIZATION_MESSAGE_TYPES:\n        normalized = dict(payload)\n        if last_job_id and "job_id" not in normalized:\n            normalized["job_id"] = last_job_id\n        return normalized, normalized.get("job_id", last_job_id)\n\n    if message_type in LTX_GRAPH_INSPECTION_MESSAGE_TYPES:\n        normalized = dict(payload)\n        if last_job_id and "job_id" not in normalized:\n            normalized["job_id"] = last_job_id\n        return normalized, normalized.get("job_id", last_job_id)\n\n    return (\n',
    ),
])

worker_service = Path("python/worker_service.py")
patch_file(worker_service, [
    (
        'from ltx_workflow_materialization import ltx_workflow_materialization_dry_run_snapshot\n',
        'from ltx_workflow_materialization import ltx_workflow_materialization_dry_run_snapshot\nfrom ltx_workflow_graph_inspection import ltx_workflow_graph_inspection_snapshot\n',
    ),
    (
        '        if command in {"runtime_memory_status", "runtime_diagnostics", "unload_image_runtime", "unload_video_runtime", "unload_all_runtimes", "clear_cuda_cache"}:\n',
        '        if command in {"ltx_workflow_graph_inspection", "ltx_prompt_api_normalization_preview", "video_family_graph_inspection", "video_family_prompt_api_normalization_preview"}:\n            family = normalize_video_family_id(req.get("family") or req.get("video_family") or "ltx")\n            if family != "ltx":\n                contract = video_family_contract(family)\n                emitter.emit({\n                    "type": "video_family_graph_inspection",\n                    "ok": False,\n                    "family": family,\n                    "display_name": contract.display_name,\n                    "validation_status": contract.validation_status,\n                    "readiness": "unsupported_graph_inspection_family",\n                    "ready_to_test": False,\n                    "generation_enabled": False,\n                    "submitted": False,\n                    "message": "Workflow graph inspection is implemented for LTX in Sprint 15C Pass 6.",\n                })\n                return\n            runtime_status = {}\n            try:\n                runtime_status = handle_comfy_runtime_status_command({})\n            except Exception as exc:\n                runtime_status = {"ok": False, "error": str(exc)}\n            emitter.emit(ltx_workflow_graph_inspection_snapshot(req, runtime_status=runtime_status))\n            return\n        if command in {"runtime_memory_status", "runtime_diagnostics", "unload_image_runtime", "unload_video_runtime", "unload_all_runtimes", "clear_cuda_cache"}:\n',
    ),
])

print("Sprint 15C Pass 6 LTX graph inspection applied.")
