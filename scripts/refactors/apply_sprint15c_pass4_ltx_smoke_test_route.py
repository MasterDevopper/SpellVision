from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"Could not find expected block for {label}")
    return text.replace(old, new, 1)


def patch_worker_service() -> None:
    path = Path("python/worker_service.py")
    text = path.read_text(encoding="utf-8")

    if "from ltx_smoke_test_route import ltx_t2v_smoke_test_snapshot" not in text:
        text = replace_once(
            text,
            "from ltx_workflow_contract import ltx_test_workflow_contract_snapshot\n",
            "from ltx_workflow_contract import ltx_test_workflow_contract_snapshot\nfrom ltx_smoke_test_route import ltx_t2v_smoke_test_snapshot\n",
            "worker_service import",
        )

    command_block = '''        if command in {"ltx_t2v_smoke_test", "ltx_smoke_test_route", "video_family_smoke_test_route"}:
            family = normalize_video_family_id(req.get("family") or req.get("video_family") or "ltx")
            if family != "ltx":
                contract = video_family_contract(family)
                emitter.emit({
                    "type": "video_family_smoke_test_route",
                    "ok": False,
                    "family": family,
                    "display_name": contract.display_name,
                    "validation_status": contract.validation_status,
                    "readiness": "unsupported_smoke_test_family",
                    "ready_to_test": False,
                    "generation_enabled": False,
                    "submitted": False,
                    "message": "Gated smoke-test route is implemented for LTX in Sprint 15C Pass 4.",
                })
                return
            runtime_status = {}
            try:
                runtime_status = handle_comfy_runtime_status_command({})
            except Exception as exc:
                runtime_status = {"ok": False, "error": str(exc)}
            emitter.emit(ltx_t2v_smoke_test_snapshot(req, runtime_status=runtime_status))
            return
'''

    if "ltx_t2v_smoke_test_snapshot" in text and '"ltx_t2v_smoke_test"' in text:
        path.write_text(text, encoding="utf-8")
        return

    anchor = '''        if command in {"runtime_memory_status", "runtime_diagnostics", "unload_image_runtime", "unload_video_runtime", "unload_all_runtimes", "clear_cuda_cache"}:
            emitter.emit(handle_runtime_memory_control_command(req))
            return
'''
    text = replace_once(text, anchor, command_block + anchor, "worker_service smoke command block")
    path.write_text(text, encoding="utf-8")


def patch_worker_client() -> None:
    path = Path("python/worker_client.py")
    text = path.read_text(encoding="utf-8")

    if "LTX_SMOKE_TEST_MESSAGE_TYPES" not in text:
        text = replace_once(
            text,
            'VIDEO_WORKFLOW_CONTRACT_MESSAGE_TYPES = {"ltx_test_workflow_contract", "video_family_workflow_contract"}\n',
            'VIDEO_WORKFLOW_CONTRACT_MESSAGE_TYPES = {"ltx_test_workflow_contract", "video_family_workflow_contract"}\nLTX_SMOKE_TEST_MESSAGE_TYPES = {"ltx_t2v_smoke_test", "video_family_smoke_test_route"}\n',
            "worker_client message type set",
        )

    if '"ltx_t2v_smoke_test"' not in text.split("STREAMING_COMMANDS", 1)[0]:
        text = replace_once(
            text,
            '"ltx_test_workflow_contract", "ltx_workflow_contract", "video_family_test_workflow_contract", "video_family_workflow_contract"}',
            '"ltx_test_workflow_contract", "ltx_workflow_contract", "video_family_test_workflow_contract", "video_family_workflow_contract", "ltx_t2v_smoke_test", "ltx_smoke_test_route", "video_family_smoke_test_route"}',
            "worker_client CONTROL_COMMANDS",
        )

    text = text.replace(
        '{"ltx_readiness_status", "ltx_runtime_readiness", "video_family_readiness", "video_family_readiness_status", "ltx_test_workflow_contract", "ltx_workflow_contract", "video_family_test_workflow_contract", "video_family_workflow_contract"}',
        '{"ltx_readiness_status", "ltx_runtime_readiness", "video_family_readiness", "video_family_readiness_status", "ltx_test_workflow_contract", "ltx_workflow_contract", "video_family_test_workflow_contract", "video_family_workflow_contract", "ltx_t2v_smoke_test", "ltx_smoke_test_route", "video_family_smoke_test_route"}',
    )

    if "message_type in LTX_SMOKE_TEST_MESSAGE_TYPES" not in text:
        anchor = '''    if message_type in VIDEO_WORKFLOW_CONTRACT_MESSAGE_TYPES:
        normalized = dict(payload)
        if last_job_id and "job_id" not in normalized:
            normalized["job_id"] = last_job_id
        return normalized, normalized.get("job_id", last_job_id)

'''
        insert = anchor + '''    if message_type in LTX_SMOKE_TEST_MESSAGE_TYPES:
        normalized = dict(payload)
        if last_job_id and "job_id" not in normalized:
            normalized["job_id"] = last_job_id
        return normalized, normalized.get("job_id", last_job_id)

'''
        text = replace_once(text, anchor, insert, "worker_client smoke message normalization")

    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_worker_service()
    patch_worker_client()
    print("Sprint 15C Pass 4 LTX smoke-test route applied.")


if __name__ == "__main__":
    main()
