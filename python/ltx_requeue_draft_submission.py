from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from ltx_prompt_api_submission import ltx_prompt_api_gated_submission_snapshot


REQUEUE_ROOT = Path(os.environ.get(
    "SPELLVISION_LTX_REQUEUE_ROOT",
    r"D:\AI_ASSETS\comfy_runtime\spellvision_registry\requeue\ltx",
))

PROMPT_API_EXPORT = Path(os.environ.get(
    "SPELLVISION_LTX_PROMPT_API_EXPORT",
    r"D:\AI_ASSETS\comfy_runtime\ComfyUI\user\default\workflows\ltx_api.json",
))


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return default


def _latest_draft(root: Path) -> Optional[Path]:
    if not root.exists():
        return None
    drafts = [p for p in root.glob("*.requeue.json") if p.is_file()]
    if not drafts:
        return None
    return max(drafts, key=lambda p: p.stat().st_mtime)


def _draft_path(request: Dict[str, Any]) -> Optional[Path]:
    explicit = str(request.get("draft_path") or request.get("requeue_draft_path") or "").strip()
    if explicit:
        return Path(explicit)
    root = Path(str(request.get("draft_root") or REQUEUE_ROOT))
    return _latest_draft(root)


def _load_draft(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Requeue draft must be a JSON object.")
    return data


def _prompt_api_path(request: Dict[str, Any], draft: Dict[str, Any]) -> Path:
    explicit = str(request.get("prompt_api_export_path") or "").strip()
    if explicit:
        return Path(explicit)

    from_draft = str(draft.get("prompt_api_export_path") or draft.get("workflow_prompt_api_path") or "").strip()
    if from_draft:
        return Path(from_draft)

    return PROMPT_API_EXPORT


def _validate(draft: Dict[str, Any], draft_path: Path, prompt_api_path: Path) -> List[str]:
    reasons: List[str] = []

    if draft.get("type") != "spellvision_ltx_history_requeue_draft":
        reasons.append("draft_type_not_supported")
    if str(draft.get("family") or "").lower() != "ltx":
        reasons.append("draft_family_not_ltx")
    if str(draft.get("task_type") or "").lower() != "t2v":
        reasons.append("draft_task_type_not_t2v")
    if str(draft.get("backend") or "").lower() != "comfy_prompt_api":
        reasons.append("draft_backend_not_comfy_prompt_api")
    if not _as_bool(draft.get("safe_to_requeue"), False):
        reasons.append("draft_not_marked_safe_to_requeue")
    if _as_bool(draft.get("submit_immediately"), False):
        reasons.append("draft_requests_immediate_submit")
    if not str(draft.get("prompt") or "").strip():
        reasons.append("draft_prompt_missing")
    if not str(draft.get("model") or "").strip():
        reasons.append("draft_model_missing")
    if not draft_path.exists():
        reasons.append("draft_path_missing")
    if not prompt_api_path.exists():
        reasons.append("prompt_api_export_path_missing")

    return reasons


def _runtime_status(request: Dict[str, Any]) -> Dict[str, Any]:
    comfy_root = str(request.get("comfy_root") or os.environ.get("SPELLVISION_COMFY_ROOT") or r"D:\AI_ASSETS\comfy_runtime\ComfyUI")
    return {
        "running": True,
        "healthy": True,
        "endpoint_alive": True,
        "endpoint": str(request.get("endpoint") or os.environ.get("SPELLVISION_COMFY_ENDPOINT") or "http://127.0.0.1:8188"),
        "host": "127.0.0.1",
        "port": 8188,
        "comfy_root": comfy_root,
        "output_root": str(request.get("output_root") or os.environ.get("SPELLVISION_COMFY_OUTPUT_ROOT") or str(Path(comfy_root) / "output")),
    }


def ltx_requeue_draft_gated_submission_snapshot(request: Dict[str, Any], runtime_status: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    path = _draft_path(request)
    if path is None:
        return {
            "type": "spellvision_ltx_requeue_gated_submission",
            "ok": False,
            "submission_status": "blocked_no_requeue_draft_found",
            "blocked_submit_reasons": ["no_requeue_draft_found"],
            "submitted": False,
            "result_completed": False,
        }

    path = path.resolve()

    try:
        draft = _load_draft(path)
    except Exception as exc:
        return {
            "type": "spellvision_ltx_requeue_gated_submission",
            "ok": False,
            "submission_status": "blocked_requeue_draft_load_failed",
            "draft_path": str(path),
            "blocked_submit_reasons": ["requeue_draft_load_failed"],
            "error": str(exc),
            "submitted": False,
            "result_completed": False,
        }

    prompt_api_path = _prompt_api_path(request, draft)
    blocked = _validate(draft, path, prompt_api_path)

    requested_submit = _as_bool(request.get("submit_to_comfy"), False)
    dry_run = _as_bool(request.get("dry_run"), True)

    if requested_submit and dry_run:
        blocked.append("submit_requested_but_dry_run_true")

    can_submit = not blocked
    should_submit = can_submit and requested_submit and not dry_run

    if not can_submit:
        return {
            "type": "spellvision_ltx_requeue_gated_submission",
            "ok": False,
            "execution_mode": "blocked",
            "submission_status": "blocked_requeue_draft_not_safe",
            "draft_path": str(path),
            "prompt_api_export_path": str(prompt_api_path),
            "blocked_submit_reasons": blocked,
            "can_submit": False,
            "submitted": False,
            "result_completed": False,
            "draft": draft,
        }

    gated_request = {
        "command": "ltx_prompt_api_gated_submission",
        "prompt_api_export_path": str(prompt_api_path),
        "submit_to_comfy": should_submit,
        "dry_run": not should_submit,
        "wait_for_result": _as_bool(request.get("wait_for_result"), False),
        "capture_metadata": _as_bool(request.get("capture_metadata"), True),
        "poll_timeout_seconds": int(request.get("poll_timeout_seconds") or 900),
        "poll_interval_seconds": float(request.get("poll_interval_seconds") or 5),
        "requeue_source": "history",
        "requeue_draft_path": str(path),
        "requeue_registry_prompt_id": draft.get("registry_prompt_id", ""),
    }

    gated = ltx_prompt_api_gated_submission_snapshot(gated_request, runtime_status=runtime_status or _runtime_status(request))

    submitted = bool(gated.get("submitted"))
    completed = bool(gated.get("result_completed"))

    if should_submit and submitted and completed:
        status = "requeue_submitted_completed"
    elif should_submit and submitted:
        status = "requeue_submitted"
    elif should_submit:
        status = "requeue_submit_failed"
    else:
        status = "requeue_dry_run_ready_to_submit"

    return {
        "type": "spellvision_ltx_requeue_gated_submission",
        "ok": bool(gated.get("ok", True)) if should_submit else True,
        "execution_mode": "submit" if should_submit else "dry_run",
        "submission_status": status,
        "draft_path": str(path),
        "prompt_api_export_path": str(prompt_api_path),
        "can_submit": True,
        "requested_submit": requested_submit,
        "dry_run": not should_submit,
        "submitted": submitted,
        "result_completed": completed,
        "prompt_id": str(gated.get("prompt_id") or ""),
        "submit_error": gated.get("submit_error", ""),
        "blocked_submit_reasons": [],
        "draft": {
            "registry_prompt_id": draft.get("registry_prompt_id", ""),
            "prompt": draft.get("prompt", ""),
            "model": draft.get("model", ""),
            "duration": draft.get("duration", ""),
            "resolution": draft.get("resolution", ""),
            "safe_to_requeue": draft.get("safe_to_requeue", False),
            "submit_immediately": draft.get("submit_immediately", False),
        },
        "gated_submission": gated,
        "spellvision_result": gated.get("spellvision_result", {}),
        "queue_result_event": gated.get("queue_result_event", {}),
        "history_record": gated.get("history_record", {}),
        "primary_output": gated.get("primary_output", {}),
        "ui_outputs": gated.get("ui_outputs", []),
    }
