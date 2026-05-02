from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any

from ltx_prompt_api_adapter import ltx_prompt_api_conversion_adapter_snapshot


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _endpoint_from_runtime(runtime_status: dict[str, Any] | None) -> str:
    runtime_status = runtime_status or {}
    endpoint = str(runtime_status.get("endpoint") or "").strip()
    if endpoint:
        return endpoint.rstrip("/")

    host = str(runtime_status.get("host") or "127.0.0.1").strip() or "127.0.0.1"
    port = int(runtime_status.get("port") or 8188)
    return f"http://{host}:{port}"


def _post_prompt(endpoint: str, prompt: dict[str, Any], client_id: str) -> tuple[bool, dict[str, Any], str]:
    payload = {
        "prompt": prompt,
        "client_id": client_id,
    }

    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{endpoint.rstrip('/')}/prompt",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response_text = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        error_text = exc.read().decode("utf-8", errors="replace")
        return False, {}, f"HTTP {exc.code}: {error_text}"
    except Exception as exc:
        return False, {}, str(exc)

    try:
        data = json.loads(response_text)
    except Exception:
        data = {"raw_response": response_text}

    return True, data if isinstance(data, dict) else {"response": data}, ""


def ltx_prompt_api_gated_submission_snapshot(
    req: dict[str, Any] | None = None,
    runtime_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    req = req or {}
    runtime_status = runtime_status or {}

    adapter = ltx_prompt_api_conversion_adapter_snapshot(req, runtime_status=runtime_status)

    requested_submit = bool(req.get("submit") or req.get("execute") or req.get("submit_to_comfy"))
    dry_run = bool(req.get("dry_run", not requested_submit))
    client_id = str(req.get("client_id") or f"spellvision-ltx-{uuid.uuid4().hex}")

    endpoint = _endpoint_from_runtime(runtime_status)
    prompt_api_preview = adapter.get("prompt_api_preview") if isinstance(adapter.get("prompt_api_preview"), dict) else {}

    diagnostics = adapter.get("diagnostics") if isinstance(adapter.get("diagnostics"), dict) else {}
    comfy_running = bool(runtime_status.get("running", diagnostics.get("comfy_running", False)))
    comfy_healthy = bool(runtime_status.get("healthy", diagnostics.get("comfy_healthy", False)))
    endpoint_alive = bool(runtime_status.get("endpoint_alive", diagnostics.get("comfy_endpoint_alive", False)))

    blocked_reasons: list[str] = []

    if not bool(adapter.get("ok", False)):
        blocked_reasons.append("adapter_not_ok")

    if not bool(adapter.get("safe_to_submit", False)):
        blocked_reasons.append("adapter_not_safe_to_submit")

    if adapter.get("blocked_submit_reasons"):
        blocked_reasons.append("adapter_blocked_submit_reasons_present")

    if adapter.get("unresolved_roles"):
        blocked_reasons.append("adapter_unresolved_roles_present")

    if not prompt_api_preview:
        blocked_reasons.append("prompt_api_preview_missing")

    if not comfy_running:
        blocked_reasons.append("comfy_not_running")

    if not comfy_healthy:
        blocked_reasons.append("comfy_not_healthy")

    if not endpoint_alive:
        blocked_reasons.append("comfy_endpoint_not_alive")

    can_submit = not blocked_reasons

    response_payload: dict[str, Any] = {}
    submit_error = ""
    submitted = False
    prompt_id = ""

    if can_submit and requested_submit and not dry_run:
        submitted, response_payload, submit_error = _post_prompt(endpoint, prompt_api_preview, client_id)
        if submitted:
            prompt_id = str(response_payload.get("prompt_id") or "")
        else:
            blocked_reasons.append("comfy_prompt_post_failed")

    if blocked_reasons:
        submission_status = "blocked"
    elif dry_run or not requested_submit:
        submission_status = "dry_run_ready_to_submit"
    elif submitted:
        submission_status = "submitted_to_comfy"
    else:
        submission_status = "not_submitted"

    return {
        "type": "ltx_prompt_api_gated_submission",
        "ok": not blocked_reasons or submitted,
        "family": "ltx",
        "display_name": "LTX-Video",
        "validation_status": "experimental",
        "execution_mode": "submit" if requested_submit and not dry_run else "dry_run",
        "checked_at": _utc_now_iso(),

        "requested_submit": requested_submit,
        "dry_run": dry_run,
        "can_submit": can_submit,
        "submitted": submitted,
        "submission_status": submission_status,
        "prompt_id": prompt_id,
        "client_id": client_id,

        "endpoint": endpoint,
        "comfy_running": comfy_running,
        "comfy_healthy": comfy_healthy,
        "comfy_endpoint_alive": endpoint_alive,

        "safe_to_submit": bool(adapter.get("safe_to_submit", False)),
        "normalization_ready": bool(adapter.get("normalization_ready", False)),
        "prompt_api_export_validation_status": adapter.get("prompt_api_export_validation_status"),
        "blocked_submit_reasons": blocked_reasons,
        "adapter_blocked_submit_reasons": adapter.get("blocked_submit_reasons", []),
        "unresolved_roles": adapter.get("unresolved_roles", []),

        "prompt_api_node_count": len(prompt_api_preview),
        "prompt_api_preview": prompt_api_preview if bool(req.get("include_prompt_api_preview", False)) else {},
        "comfy_response": response_payload,
        "submit_error": submit_error,
        "adapter": adapter if bool(req.get("include_adapter", False)) else {},
        "notes": [
            "This route submits only when the Pass 8 adapter reports safe_to_submit=True.",
            "Default behavior is dry-run unless submit_to_comfy=true and dry_run=false are provided.",
            "No Wan production routing is changed by this LTX experimental route.",
        ],
    }
