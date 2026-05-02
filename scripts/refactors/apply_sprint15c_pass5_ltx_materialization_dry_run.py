from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f"Could not find insertion point for {label}")
    return text.replace(old, new, 1)


def patch_worker_service() -> None:
    path = ROOT / "python" / "worker_service.py"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "from ltx_smoke_test_route import ltx_t2v_smoke_test_snapshot\n",
        "from ltx_smoke_test_route import ltx_t2v_smoke_test_snapshot\nfrom ltx_workflow_materialization import ltx_workflow_materialization_dry_run_snapshot\n",
        "worker_service import",
    )
    marker = '''        if command in {"ltx_t2v_smoke_test", "ltx_smoke_test_route", "video_family_smoke_test_route"}:
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
    insertion = marker + '''        if command in {"ltx_workflow_materialization_dry_run", "ltx_materialize_workflow", "ltx_t2v_materialize_dry_run", "video_family_materialization_dry_run"}:
            family = normalize_video_family_id(req.get("family") or req.get("video_family") or "ltx")
            if family != "ltx":
                contract = video_family_contract(family)
                emitter.emit({
                    "type": "video_family_materialization_dry_run",
                    "ok": False,
                    "family": family,
                    "display_name": contract.display_name,
                    "validation_status": contract.validation_status,
                    "readiness": "unsupported_materialization_family",
                    "ready_to_test": False,
                    "generation_enabled": False,
                    "submitted": False,
                    "message": "Workflow materialization dry run is implemented for LTX in Sprint 15C Pass 5.",
                })
                return
            runtime_status = {}
            try:
                runtime_status = handle_comfy_runtime_status_command({})
            except Exception as exc:
                runtime_status = {"ok": False, "error": str(exc)}
            emitter.emit(ltx_workflow_materialization_dry_run_snapshot(req, runtime_status=runtime_status))
            return
'''
    text = replace_once(text, marker, insertion, "worker_service materialization handler")
    path.write_text(text, encoding="utf-8")


def patch_worker_client() -> None:
    path = ROOT / "python" / "worker_client.py"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        'LTX_SMOKE_TEST_MESSAGE_TYPES = {"ltx_t2v_smoke_test", "video_family_smoke_test_route"}\n',
        'LTX_SMOKE_TEST_MESSAGE_TYPES = {"ltx_t2v_smoke_test", "video_family_smoke_test_route"}\nLTX_MATERIALIZATION_MESSAGE_TYPES = {"ltx_workflow_materialization_dry_run", "video_family_materialization_dry_run"}\n',
        "worker_client message type",
    )
    text = text.replace(
        '"ltx_t2v_smoke_test", "ltx_smoke_test_route", "video_family_smoke_test_route"}',
        '"ltx_t2v_smoke_test", "ltx_smoke_test_route", "video_family_smoke_test_route", "ltx_workflow_materialization_dry_run", "ltx_materialize_workflow", "ltx_t2v_materialize_dry_run", "video_family_materialization_dry_run"}',
    )
    marker = '''    if message_type in LTX_SMOKE_TEST_MESSAGE_TYPES:
        normalized = dict(payload)
        if last_job_id and "job_id" not in normalized:
            normalized["job_id"] = last_job_id
        return normalized, normalized.get("job_id", last_job_id)
'''
    insertion = marker + '''
    if message_type in LTX_MATERIALIZATION_MESSAGE_TYPES:
        normalized = dict(payload)
        if last_job_id and "job_id" not in normalized:
            normalized["job_id"] = last_job_id
        return normalized, normalized.get("job_id", last_job_id)
'''
    text = replace_once(text, marker, insertion, "worker_client materialization normalization")
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_worker_service()
    patch_worker_client()
    print("Sprint 15C Pass 5 LTX workflow materialization dry run applied.")
