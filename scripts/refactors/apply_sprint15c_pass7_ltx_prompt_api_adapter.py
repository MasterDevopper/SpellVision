from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        if new in text:
            return text
        raise SystemExit(f"Could not find expected block for {label}")
    return text.replace(old, new, 1)


def patch_worker_service() -> None:
    path = Path("python/worker_service.py")
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "from ltx_workflow_graph_inspection import ltx_workflow_graph_inspection_snapshot\n",
        "from ltx_workflow_graph_inspection import ltx_workflow_graph_inspection_snapshot\n"
        "from ltx_prompt_api_adapter import ltx_prompt_api_conversion_adapter_snapshot\n",
        "worker_service import",
    )

    old = """        if command in {"ltx_workflow_graph_inspection", "ltx_prompt_api_normalization_preview", "video_family_graph_inspection", "video_family_prompt_api_normalization_preview"}:
            family = normalize_video_family_id(req.get("family") or req.get("video_family") or "ltx")
            if family != "ltx":
                contract = video_family_contract(family)
                emitter.emit({
                    "type": "video_family_graph_inspection",
                    "ok": False,
                    "family": family,
                    "display_name": contract.display_name,
                    "validation_status": contract.validation_status,
                    "readiness": "unsupported_graph_inspection_family",
                    "ready_to_test": False,
                    "generation_enabled": False,
                    "submitted": False,
                    "message": "Workflow graph inspection is implemented for LTX in Sprint 15C Pass 6.",
                })
                return
            runtime_status = {}
            try:
                runtime_status = handle_comfy_runtime_status_command({})
            except Exception as exc:
                runtime_status = {"ok": False, "error": str(exc)}
            emitter.emit(ltx_workflow_graph_inspection_snapshot(req, runtime_status=runtime_status))
            return
"""
    new = old + """        if command in {"ltx_prompt_api_conversion_adapter", "ltx_prompt_api_export_adapter", "ltx_prompt_api_conversion_preview", "video_family_prompt_api_conversion_adapter"}:
            family = normalize_video_family_id(req.get("family") or req.get("video_family") or "ltx")
            if family != "ltx":
                contract = video_family_contract(family)
                emitter.emit({
                    "type": "video_family_prompt_api_conversion_adapter",
                    "ok": False,
                    "family": family,
                    "display_name": contract.display_name,
                    "validation_status": contract.validation_status,
                    "readiness": "unsupported_prompt_api_adapter_family",
                    "ready_to_test": False,
                    "generation_enabled": False,
                    "submitted": False,
                    "message": "Prompt API conversion adapter is implemented for LTX in Sprint 15C Pass 7.",
                })
                return
            runtime_status = {}
            try:
                runtime_status = handle_comfy_runtime_status_command({})
            except Exception as exc:
                runtime_status = {"ok": False, "error": str(exc)}
            emitter.emit(ltx_prompt_api_conversion_adapter_snapshot(req, runtime_status=runtime_status))
            return
"""
    text = replace_once(text, old, new, "worker_service command route")
    path.write_text(text, encoding="utf-8")


def patch_worker_client() -> None:
    path = Path("python/worker_client.py")
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        'LTX_GRAPH_INSPECTION_MESSAGE_TYPES = {"ltx_workflow_graph_inspection", "ltx_prompt_api_normalization_preview", "video_family_graph_inspection", "video_family_prompt_api_normalization_preview"}\n',
        'LTX_GRAPH_INSPECTION_MESSAGE_TYPES = {"ltx_workflow_graph_inspection", "ltx_prompt_api_normalization_preview", "video_family_graph_inspection", "video_family_prompt_api_normalization_preview"}\n'
        'LTX_PROMPT_API_ADAPTER_MESSAGE_TYPES = {"ltx_prompt_api_conversion_adapter", "video_family_prompt_api_conversion_adapter"}\n',
        "worker_client message type set",
    )

    text = replace_once(
        text,
        '"ltx_workflow_graph_inspection", "ltx_prompt_api_normalization_preview", "video_family_graph_inspection", "video_family_prompt_api_normalization_preview"}:',
        '"ltx_workflow_graph_inspection", "ltx_prompt_api_normalization_preview", "video_family_graph_inspection", "video_family_prompt_api_normalization_preview", "ltx_prompt_api_conversion_adapter", "ltx_prompt_api_export_adapter", "ltx_prompt_api_conversion_preview", "video_family_prompt_api_conversion_adapter"}:',
        "worker_client action normalization",
    )

    old = """    if message_type in LTX_GRAPH_INSPECTION_MESSAGE_TYPES:
        normalized = dict(payload)
        if last_job_id and "job_id" not in normalized:
            normalized["job_id"] = last_job_id
        return normalized, normalized.get("job_id", last_job_id)

"""
    new = old + """    if message_type in LTX_PROMPT_API_ADAPTER_MESSAGE_TYPES:
        normalized = dict(payload)
        if last_job_id and "job_id" not in normalized:
            normalized["job_id"] = last_job_id
        return normalized, normalized.get("job_id", last_job_id)

"""
    text = replace_once(text, old, new, "worker_client normalize message")
    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_worker_service()
    patch_worker_client()
    print("Sprint 15C Pass 7 LTX Prompt API adapter applied.")


if __name__ == "__main__":
    main()
