from pathlib import Path
import re

root = Path(".")
submission_path = root / "python" / "ltx_prompt_api_submission.py"
worker_service_path = root / "python" / "worker_service.py"
worker_client_path = root / "python" / "worker_client.py"
doc_path = root / "docs" / "sprints" / "SPRINT15C_PASS10_LTX_RESULT_POLLING_METADATA_README.md"
script_path = root / "scripts" / "refactors" / "apply_sprint15c_pass10_ltx_result_polling_metadata.py"

submission_source = r'''from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
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


def _comfy_output_root(runtime_status: dict[str, Any] | None) -> Path:
    runtime_status = runtime_status or {}

    output_root = str(runtime_status.get("output_root") or "").strip()
    if output_root:
        return Path(output_root)

    comfy_root = str(runtime_status.get("comfy_root") or "").strip()
    if comfy_root:
        return Path(comfy_root) / "output"

    return Path("D:/AI_ASSETS/comfy_runtime/ComfyUI/output")


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

    if not isinstance(data, dict):
        return True, {"response": data}, ""

    return True, data, ""


def _get_json(endpoint: str, path: str, timeout: int = 30) -> tuple[bool, Any, str]:
    url = f"{endpoint.rstrip('/')}/{path.lstrip('/')}"
    request = urllib.request.Request(url, method="GET")

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_text = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        error_text = exc.read().decode("utf-8", errors="replace")
        return False, None, f"HTTP {exc.code}: {error_text}"
    except Exception as exc:
        return False, None, str(exc)

    try:
        return True, json.loads(response_text), ""
    except Exception as exc:
        return False, None, f"Invalid JSON from {url}: {exc}"


def _history_entry_for_prompt(history_payload: Any, prompt_id: str) -> dict[str, Any]:
    if not prompt_id:
        return {}

    if isinstance(history_payload, dict):
        direct = history_payload.get(prompt_id)
        if isinstance(direct, dict):
            return direct

        # Some Comfy variants return a singleton history object or nested maps.
        for value in history_payload.values():
            if not isinstance(value, dict):
                continue
            nested = value.get(prompt_id)
            if isinstance(nested, dict):
                return nested

    return {}


def _poll_history_for_prompt(
    endpoint: str,
    prompt_id: str,
    timeout_seconds: float,
    interval_seconds: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    started = time.monotonic()
    attempts = 0
    last_error = ""
    last_status = ""

    while True:
        attempts += 1

        ok, payload, error = _get_json(endpoint, f"history/{prompt_id}", timeout=30)
        if not ok:
            last_error = error
        else:
            entry = _history_entry_for_prompt(payload, prompt_id)
            if entry:
                status = entry.get("status") if isinstance(entry.get("status"), dict) else {}
                last_status = str(status.get("status_str") or "")
                completed = bool(status.get("completed", False))

                if completed:
                    return entry, {
                        "attempts": attempts,
                        "elapsed_seconds": round(time.monotonic() - started, 3),
                        "timed_out": False,
                        "last_error": last_error,
                        "last_status": last_status,
                    }

        elapsed = time.monotonic() - started
        if elapsed >= timeout_seconds:
            return {}, {
                "attempts": attempts,
                "elapsed_seconds": round(elapsed, 3),
                "timed_out": True,
                "last_error": last_error,
                "last_status": last_status,
            }

        time.sleep(max(0.25, interval_seconds))


def _extract_prompt_node_inputs(prompt_api_preview: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(prompt_api_preview, dict):
        return {}

    def node_inputs(node_id: str) -> dict[str, Any]:
        node = prompt_api_preview.get(node_id)
        if not isinstance(node, dict):
            return {}
        inputs = node.get("inputs")
        return inputs if isinstance(inputs, dict) else {}

    checkpoint = node_inputs("3940")
    audio_vae = node_inputs("4010")
    text_encoder = node_inputs("4960")
    video_vae = node_inputs("4986")
    positive = node_inputs("2483")
    negative = node_inputs("2612")
    seed = node_inputs("4814")
    distilled_seed = node_inputs("4832")
    latent = node_inputs("3059")
    fps = node_inputs("4978")
    frames = node_inputs("4979")

    return {
        "prompt": positive.get("text", ""),
        "negative_prompt": negative.get("text", ""),
        "model": checkpoint.get("ckpt_name", ""),
        "audio_vae": audio_vae.get("ckpt_name", ""),
        "video_vae": video_vae.get("vae_name", ""),
        "text_encoder": text_encoder.get("text_encoder", ""),
        "text_projection": text_encoder.get("ckpt_name", ""),
        "seed": seed.get("noise_seed"),
        "distilled_seed": distilled_seed.get("noise_seed"),
        "width": latent.get("width"),
        "height": latent.get("height"),
        "frames": latent.get("length") or frames.get("value"),
        "fps": fps.get("value"),
    }


def _extract_history_outputs(history_entry: dict[str, Any], output_root: Path) -> list[dict[str, Any]]:
    outputs = history_entry.get("outputs")
    if not isinstance(outputs, dict):
        return []

    extracted: list[dict[str, Any]] = []

    for node_id, node_outputs in outputs.items():
        if not isinstance(node_outputs, dict):
            continue

        for bucket_name in ("images", "gifs", "videos", "audio"):
            items = node_outputs.get(bucket_name)
            if not isinstance(items, list):
                continue

            animated_flags = node_outputs.get("animated")
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    continue

                filename = str(item.get("filename") or "").strip()
                if not filename:
                    continue

                subfolder = str(item.get("subfolder") or "").strip()
                output_type = str(item.get("type") or "").strip()
                full_path = output_root / subfolder / filename if subfolder else output_root / filename

                animated = None
                if isinstance(animated_flags, list) and index < len(animated_flags):
                    animated = bool(animated_flags[index])

                extracted.append(
                    {
                        "node_id": str(node_id),
                        "bucket": bucket_name,
                        "filename": filename,
                        "subfolder": subfolder,
                        "type": output_type,
                        "path": str(full_path),
                        "exists": full_path.exists(),
                        "size_bytes": full_path.stat().st_size if full_path.exists() else 0,
                        "animated": animated,
                    }
                )

    return extracted


def _write_metadata_sidecars(
    outputs: list[dict[str, Any]],
    metadata: dict[str, Any],
    enabled: bool,
) -> list[dict[str, Any]]:
    if not enabled:
        return []

    sidecars: list[dict[str, Any]] = []

    for output in outputs:
        output_path = Path(str(output.get("path") or ""))
        if not output_path.name:
            continue

        sidecar_path = output_path.with_suffix(output_path.suffix + ".spellvision.json")
        payload = dict(metadata)
        payload["output"] = output

        try:
            sidecar_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            sidecars.append(
                {
                    "output_path": str(output_path),
                    "metadata_path": str(sidecar_path),
                    "ok": True,
                    "error": "",
                }
            )
        except Exception as exc:
            sidecars.append(
                {
                    "output_path": str(output_path),
                    "metadata_path": str(sidecar_path),
                    "ok": False,
                    "error": str(exc),
                }
            )

    return sidecars


def ltx_prompt_api_gated_submission_snapshot(
    req: dict[str, Any] | None = None,
    runtime_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    req = req or {}
    runtime_status = runtime_status or {}

    adapter = ltx_prompt_api_conversion_adapter_snapshot(req, runtime_status=runtime_status)

    requested_submit = bool(req.get("submit") or req.get("execute") or req.get("submit_to_comfy"))
    dry_run = bool(req.get("dry_run", not requested_submit))
    wait_for_result = bool(req.get("wait_for_result") or req.get("poll_result") or req.get("capture_metadata"))
    capture_metadata = bool(req.get("capture_metadata", wait_for_result))
    client_id = str(req.get("client_id") or f"spellvision-ltx-{uuid.uuid4().hex}")

    endpoint = _endpoint_from_runtime(runtime_status)
    output_root = _comfy_output_root(runtime_status)
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

    history_entry: dict[str, Any] = {}
    result_polling: dict[str, Any] = {
        "requested": wait_for_result,
        "attempts": 0,
        "elapsed_seconds": 0.0,
        "timed_out": False,
        "last_error": "",
        "last_status": "",
    }
    outputs: list[dict[str, Any]] = []
    metadata_sidecars: list[dict[str, Any]] = []
    result_completed = False

    if can_submit and requested_submit and not dry_run:
        submitted, response_payload, submit_error = _post_prompt(endpoint, prompt_api_preview, client_id)
        if submitted:
            prompt_id = str(response_payload.get("prompt_id") or "")
        else:
            blocked_reasons.append("comfy_prompt_post_failed")

    if submitted and wait_for_result and prompt_id:
        timeout_seconds = float(req.get("poll_timeout_seconds") or req.get("result_timeout_seconds") or 900)
        interval_seconds = float(req.get("poll_interval_seconds") or 5)
        history_entry, result_polling = _poll_history_for_prompt(endpoint, prompt_id, timeout_seconds, interval_seconds)

        status = history_entry.get("status") if isinstance(history_entry.get("status"), dict) else {}
        result_completed = bool(status.get("completed", False))
        outputs = _extract_history_outputs(history_entry, output_root)

        if result_completed and capture_metadata:
            model_metadata = _extract_prompt_node_inputs(prompt_api_preview)
            metadata_payload = {
                "type": "spellvision_ltx_result_metadata",
                "schema_version": 1,
                "created_at": _utc_now_iso(),
                "family": "ltx",
                "display_name": "LTX-Video",
                "validation_status": "experimental",
                "prompt_id": prompt_id,
                "client_id": client_id,
                "endpoint": endpoint,
                "output_root": str(output_root),
                "workflow_api_path": str(req.get("prompt_api_export_path") or ""),
                "submission_status": "completed",
                "model_stack": model_metadata,
                "request": {
                    "prompt": req.get("prompt"),
                    "negative_prompt": req.get("negative_prompt"),
                    "seed": req.get("seed"),
                    "steps": req.get("steps"),
                    "cfg": req.get("cfg"),
                    "width": req.get("width"),
                    "height": req.get("height"),
                    "frames": req.get("frames"),
                    "fps": req.get("fps"),
                },
                "result_polling": result_polling,
            }
            metadata_sidecars = _write_metadata_sidecars(outputs, metadata_payload, enabled=True)

    if blocked_reasons:
        submission_status = "blocked"
    elif dry_run or not requested_submit:
        submission_status = "dry_run_ready_to_submit"
    elif submitted and wait_for_result and result_completed:
        submission_status = "submitted_completed_captured"
    elif submitted and wait_for_result and result_polling.get("timed_out"):
        submission_status = "submitted_wait_timeout"
    elif submitted:
        submission_status = "submitted_to_comfy"
    else:
        submission_status = "not_submitted"

    ok = not blocked_reasons or submitted
    if wait_for_result and submitted:
        ok = ok and (result_completed or bool(result_polling.get("timed_out")))

    return {
        "type": "ltx_prompt_api_gated_submission",
        "ok": ok,
        "family": "ltx",
        "display_name": "LTX-Video",
        "validation_status": "experimental",
        "execution_mode": "submit" if requested_submit and not dry_run else "dry_run",
        "checked_at": _utc_now_iso(),

        "requested_submit": requested_submit,
        "dry_run": dry_run,
        "wait_for_result": wait_for_result,
        "capture_metadata": capture_metadata,
        "can_submit": can_submit,
        "submitted": submitted,
        "result_completed": result_completed,
        "submission_status": submission_status,
        "prompt_id": prompt_id,
        "client_id": client_id,

        "endpoint": endpoint,
        "output_root": str(output_root),
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

        "result_polling": result_polling,
        "history_status": history_entry.get("status", {}) if isinstance(history_entry, dict) else {},
        "outputs": outputs,
        "metadata_sidecars": metadata_sidecars,
        "model_stack": _extract_prompt_node_inputs(prompt_api_preview),
        "adapter": adapter if bool(req.get("include_adapter", False)) else {},
        "notes": [
            "This route submits only when the Pass 8 adapter reports safe_to_submit=True.",
            "Pass 10 can poll Comfy history, resolve output files, and write SpellVision metadata sidecars.",
            "Default behavior is dry-run unless submit_to_comfy=true and dry_run=false are provided.",
            "No Wan production routing is changed by this LTX experimental route.",
        ],
    }
'''
submission_path.write_text(submission_source, encoding="utf-8")

doc_path.parent.mkdir(parents=True, exist_ok=True)
doc_path.write_text(
    """# Sprint 15C Pass 10 — LTX Submission Result Polling and SpellVision Metadata Capture

## Goal

Extend the gated LTX Prompt API route so it can wait for Comfy completion, collect output paths, and write SpellVision metadata sidecars.

## Existing command

`ltx_prompt_api_gated_submission`

## New request flags

- `wait_for_result=true`
- `capture_metadata=true`
- `poll_timeout_seconds=900`
- `poll_interval_seconds=5`

## Behavior

The route still defaults to dry-run mode. Live submission still requires:

- `submit_to_comfy=true`
- `dry_run=false`

Result polling only happens when `wait_for_result=true`.

## Captured result fields

- `prompt_id`
- `history_status`
- `outputs`
- `metadata_sidecars`
- `model_stack`
- `result_polling`

## Sidecar naming

For each output file, SpellVision writes:

`<output filename>.spellvision.json`

Example:

`output_F_00003_.mp4.spellvision.json`

## Safety

This remains experimental LTX routing and does not change Wan or production queue behavior.
""",
    encoding="utf-8",
)

# Worker service aliases: the existing handler already calls ltx_prompt_api_gated_submission_snapshot.
service = worker_service_path.read_text(encoding="utf-8")
old_set = '{"ltx_prompt_api_gated_submission", "ltx_prompt_api_submit", "ltx_submit_prompt_api", "video_family_prompt_api_gated_submission"}'
new_set = '{"ltx_prompt_api_gated_submission", "ltx_prompt_api_submit", "ltx_submit_prompt_api", "ltx_prompt_api_submit_and_capture", "ltx_prompt_api_submit_wait", "video_family_prompt_api_gated_submission"}'
if old_set in service:
    service = service.replace(old_set, new_set)
worker_service_path.write_text(service, encoding="utf-8")

# Worker client aliases.
client = worker_client_path.read_text(encoding="utf-8")
if '"ltx_prompt_api_submit_and_capture"' not in client:
    client = client.replace(
        '"ltx_prompt_api_gated_submission"',
        '"ltx_prompt_api_gated_submission", "ltx_prompt_api_submit_and_capture", "ltx_prompt_api_submit_wait"',
        1,
    )
worker_client_path.write_text(client, encoding="utf-8")

script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Sprint 15C Pass 10 LTX result polling and metadata capture.")
