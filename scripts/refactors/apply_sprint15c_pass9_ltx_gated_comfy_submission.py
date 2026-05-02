from pathlib import Path
import re

root = Path(".")
submission_path = root / "python" / "ltx_prompt_api_submission.py"
worker_service_path = root / "python" / "worker_service.py"
worker_client_path = root / "python" / "worker_client.py"
doc_path = root / "docs" / "sprints" / "SPRINT15C_PASS9_LTX_GATED_COMFY_SUBMISSION_README.md"
script_path = root / "scripts" / "refactors" / "apply_sprint15c_pass9_ltx_gated_comfy_submission.py"

submission_source = r'''from __future__ import annotations

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
'''

submission_path.write_text(submission_source, encoding="utf-8")

doc_path.parent.mkdir(parents=True, exist_ok=True)
doc_path.write_text(
    """# Sprint 15C Pass 9 — LTX Prompt API Gated Comfy Submission

## Goal

Add a guarded submission route for the validated LTX Prompt API payload.

## Command

`ltx_prompt_api_gated_submission`

## Safety rules

The route only submits to ComfyUI when all conditions are true:

- Pass 8 adapter reports `safe_to_submit=true`
- no blocked submit reasons
- no unresolved roles
- Comfy runtime is running
- Comfy runtime is healthy
- Comfy endpoint is alive
- Prompt API preview exists
- caller explicitly passes `submit_to_comfy=true`
- caller explicitly passes `dry_run=false`

## Default behavior

The command defaults to dry-run mode.

## Notes

This is still experimental LTX support and does not alter Wan production routing.
""",
    encoding="utf-8",
)

# --- worker_service integration ---
service = worker_service_path.read_text(encoding="utf-8")

if "from ltx_prompt_api_submission import ltx_prompt_api_gated_submission_snapshot" not in service:
    if "from ltx_prompt_api_adapter import ltx_prompt_api_conversion_adapter_snapshot" in service:
        service = service.replace(
            "from ltx_prompt_api_adapter import ltx_prompt_api_conversion_adapter_snapshot",
            "from ltx_prompt_api_adapter import ltx_prompt_api_conversion_adapter_snapshot\nfrom ltx_prompt_api_submission import ltx_prompt_api_gated_submission_snapshot",
        )
    else:
        # Keep this near the other local imports. If import style changes later, this is still safe.
        service = "from ltx_prompt_api_submission import ltx_prompt_api_gated_submission_snapshot\n" + service

if '"ltx_prompt_api_gated_submission"' not in service:
    # Prefer inserting after the existing adapter command handler.
    pattern = re.compile(
        r'(?P<block>(?:if|elif)\s+command\s*==\s*["\']ltx_prompt_api_conversion_adapter["\']\s*:\s*\n(?P<body>(?:[ \t]+.*\n)+?))(?=(?:[ \t]*(?:if|elif|else)\s+)|(?:[ \t]*raise\s+)|(?:[ \t]*return\s+)|\Z)',
        re.MULTILINE,
    )
    match = pattern.search(service)

    if match:
        body = match.group("body")
        indent_match = re.match(r"([ \t]+)", body)
        indent = indent_match.group(1) if indent_match else "        "

        runtime_arg = "runtime_status=runtime_status"
        if "runtime_status=runtime_status" not in body:
            runtime_arg = "runtime_status=comfy_runtime_status()"

        insert = (
            match.group("block")
            + f'\nelif command == "ltx_prompt_api_gated_submission":\n'
            + f'{indent}return ltx_prompt_api_gated_submission_snapshot(req, {runtime_arg})\n'
        )
        service = service[:match.start()] + insert + service[match.end():]
    else:
        # Fallback for dictionary-based command registration.
        dict_pattern = re.compile(r'(["\']ltx_prompt_api_conversion_adapter["\']\s*:\s*ltx_prompt_api_conversion_adapter_snapshot\s*,?)')
        dict_match = dict_pattern.search(service)
        if dict_match:
            replacement = dict_match.group(1) + '\n    "ltx_prompt_api_gated_submission": ltx_prompt_api_gated_submission_snapshot,'
            service = service[:dict_match.start()] + replacement + service[dict_match.end():]
        else:
            raise SystemExit(
                "Could not auto-insert worker_service command handler. "
                "Open python/worker_service.py and add command ltx_prompt_api_gated_submission "
                "returning ltx_prompt_api_gated_submission_snapshot(req, runtime_status=runtime_status)."
            )

worker_service_path.write_text(service, encoding="utf-8")

# --- worker_client integration ---
client = worker_client_path.read_text(encoding="utf-8")
if "ltx_prompt_api_gated_submission" not in client:
    if '"ltx_prompt_api_conversion_adapter"' in client:
        client = client.replace(
            '"ltx_prompt_api_conversion_adapter"',
            '"ltx_prompt_api_conversion_adapter", "ltx_prompt_api_gated_submission"',
            1,
        )
    elif "'ltx_prompt_api_conversion_adapter'" in client:
        client = client.replace(
            "'ltx_prompt_api_conversion_adapter'",
            "'ltx_prompt_api_conversion_adapter', 'ltx_prompt_api_gated_submission'",
            1,
        )
    else:
        raise SystemExit(
            "Could not auto-insert worker_client command allowlist. "
            "Add ltx_prompt_api_gated_submission wherever ltx_prompt_api_conversion_adapter is registered."
        )

worker_client_path.write_text(client, encoding="utf-8")

print("Applied Sprint 15C Pass 9 gated LTX Comfy submission route.")
