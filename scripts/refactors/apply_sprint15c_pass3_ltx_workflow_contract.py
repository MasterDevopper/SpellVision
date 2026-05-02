from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"Could not find expected block for {label}.")
    return text.replace(old, new, 1)


def patch_worker_service() -> None:
    path = Path("python/worker_service.py")
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "from video_family_readiness import ltx_readiness_snapshot\n",
        "from video_family_readiness import ltx_readiness_snapshot\nfrom ltx_workflow_contract import ltx_test_workflow_contract_snapshot\n",
        "worker_service import",
    )

    marker = '''        if command in {"ltx_readiness_status", "ltx_runtime_readiness", "video_family_readiness", "video_family_readiness_status"}:
            family = normalize_video_family_id(req.get("family") or req.get("video_family") or "ltx")
            if family != "ltx":
                contract = video_family_contract(family)
                emitter.emit({
                    "type": "video_family_readiness_status",
                    "ok": False,
                    "family": family,
                    "display_name": contract.display_name,
                    "validation_status": contract.validation_status,
                    "readiness": "unsupported_readiness_family",
                    "ready_to_test": False,
                    "message": "Readiness probing is implemented for LTX in Sprint 15C Pass 2.",
                })
                return
            runtime_status = {}
            try:
                runtime_status = handle_comfy_runtime_status_command({})
            except Exception as exc:
                runtime_status = {"ok": False, "error": str(exc)}
            emitter.emit(ltx_readiness_snapshot(runtime_status=runtime_status))
            return
'''
    addition = marker + '''        if command in {"ltx_test_workflow_contract", "ltx_workflow_contract", "video_family_test_workflow_contract", "video_family_workflow_contract"}:
            family = normalize_video_family_id(req.get("family") or req.get("video_family") or "ltx")
            if family != "ltx":
                contract = video_family_contract(family)
                emitter.emit({
                    "type": "video_family_workflow_contract",
                    "ok": False,
                    "family": family,
                    "display_name": contract.display_name,
                    "validation_status": contract.validation_status,
                    "readiness": "unsupported_workflow_contract_family",
                    "ready_to_test": False,
                    "generation_enabled": False,
                    "message": "Test workflow contract selection is implemented for LTX in Sprint 15C Pass 3.",
                })
                return
            runtime_status = {}
            try:
                runtime_status = handle_comfy_runtime_status_command({})
            except Exception as exc:
                runtime_status = {"ok": False, "error": str(exc)}
            emitter.emit(ltx_test_workflow_contract_snapshot(runtime_status=runtime_status))
            return
'''
    text = replace_once(text, marker, addition, "worker_service LTX workflow command handler")
    path.write_text(text, encoding="utf-8")


def patch_worker_client() -> None:
    path = Path("python/worker_client.py")
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        'VIDEO_READINESS_MESSAGE_TYPES = {"ltx_readiness_status", "video_family_readiness_status"}\n',
        'VIDEO_READINESS_MESSAGE_TYPES = {"ltx_readiness_status", "video_family_readiness_status"}\nVIDEO_WORKFLOW_CONTRACT_MESSAGE_TYPES = {"ltx_test_workflow_contract", "video_family_workflow_contract"}\n',
        "worker_client message types",
    )

    text = replace_once(
        text,
        '"ltx_readiness_status", "ltx_runtime_readiness", "video_family_readiness", "video_family_readiness_status"}',
        '"ltx_readiness_status", "ltx_runtime_readiness", "video_family_readiness", "video_family_readiness_status", "ltx_test_workflow_contract", "ltx_workflow_contract", "video_family_test_workflow_contract", "video_family_workflow_contract"}',
        "worker_client control commands",
    )

    text = replace_once(
        text,
        '    if action in {"ltx_readiness_status", "ltx_runtime_readiness", "video_family_readiness", "video_family_readiness_status"}:\n',
        '    if action in {"ltx_readiness_status", "ltx_runtime_readiness", "video_family_readiness", "video_family_readiness_status", "ltx_test_workflow_contract", "ltx_workflow_contract", "video_family_test_workflow_contract", "video_family_workflow_contract"}:\n',
        "worker_client action normalization",
    )

    marker = '''    if message_type in VIDEO_READINESS_MESSAGE_TYPES:
        normalized = dict(payload)
        if last_job_id and "job_id" not in normalized:
            normalized["job_id"] = last_job_id
        return normalized, normalized.get("job_id", last_job_id)
'''
    addition = marker + '''
    if message_type in VIDEO_WORKFLOW_CONTRACT_MESSAGE_TYPES:
        normalized = dict(payload)
        if last_job_id and "job_id" not in normalized:
            normalized["job_id"] = last_job_id
        return normalized, normalized.get("job_id", last_job_id)
'''
    text = replace_once(text, marker, addition, "worker_client workflow contract message normalization")
    path.write_text(text, encoding="utf-8")


def patch_readiness_regex() -> None:
    path = Path("python/video_family_readiness.py")
    text = path.read_text(encoding="utf-8")
    old = '''    video_vae_candidates = _find_candidates(
        vae_root,
        (r"ltx.*video.*vae", r"video.*vae.*ltx", r"ltx.*vae"),
        max_items=30,
    )
'''
    new = '''    video_vae_candidates = _find_candidates(
        vae_root,
        (r"ltx.*video.*vae", r"video.*vae.*ltx", r"ltx23_video"),
        max_items=30,
    )
'''
    text = replace_once(text, old, new, "video/audio VAE candidate separation")
    path.write_text(text, encoding="utf-8")


def main() -> int:
    patch_worker_service()
    patch_worker_client()
    patch_readiness_regex()
    print("Sprint 15C Pass 3 LTX workflow contract applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
