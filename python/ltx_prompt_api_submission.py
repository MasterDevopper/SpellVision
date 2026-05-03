from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ltx_prompt_api_adapter import ltx_prompt_api_conversion_adapter_snapshot
from ltx_queue_history_registry import register_ltx_queue_history_result


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


def _sidecar_for_output(output_path: str, sidecars: list[dict[str, Any]]) -> str:
    normalized = str(Path(str(output_path or "")))
    for sidecar in sidecars:
        if str(Path(str(sidecar.get("output_path") or ""))) == normalized:
            return str(sidecar.get("metadata_path") or "")
    return ""


def _classify_output_role(output: dict[str, Any]) -> str:
    filename = str(output.get("filename") or "").lower()
    node_id = str(output.get("node_id") or "")

    if filename.startswith("output_f") or node_id == "4823":
        return "full"
    if filename.startswith("output_d") or node_id == "4852":
        return "distilled"
    return "video"


def _build_spellvision_output_records(
    outputs: list[dict[str, Any]],
    sidecars: list[dict[str, Any]],
    prompt_id: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    for index, output in enumerate(outputs):
        path = str(output.get("path") or "")
        filename = str(output.get("filename") or "")
        role = _classify_output_role(output)

        records.append(
            {
                "id": f"ltx-{prompt_id}-{index}",
                "kind": "video",
                "role": role,
                "family": "ltx",
                "label": "LTX Full" if role == "full" else ("LTX Distilled" if role == "distilled" else "LTX Video"),
                "node_id": str(output.get("node_id") or ""),
                "filename": filename,
                "path": path,
                "uri": path,
                "exists": bool(output.get("exists", False)),
                "size_bytes": int(output.get("size_bytes") or 0),
                "animated": bool(output.get("animated", False)),
                "metadata_path": _sidecar_for_output(path, sidecars),
                "preview_path": path,
                "openable": bool(output.get("exists", False)),
                "requeue_supported": True,
                "send_to_mode": "t2v",
            }
        )

    return records


def _build_spellvision_result_contract(
    *,
    prompt_id: str,
    client_id: str,
    endpoint: str,
    output_root: Path,
    submission_status: str,
    result_completed: bool,
    outputs: list[dict[str, Any]],
    metadata_sidecars: list[dict[str, Any]],
    model_stack: dict[str, Any],
    result_polling: dict[str, Any],
    workflow_api_path: str,
) -> dict[str, Any]:
    output_records = _build_spellvision_output_records(outputs, metadata_sidecars, prompt_id)

    primary_output = output_records[0] if output_records else {}
    full_outputs = [item for item in output_records if item.get("role") == "full"]
    distilled_outputs = [item for item in output_records if item.get("role") == "distilled"]

    if full_outputs:
        primary_output = full_outputs[0]
    elif distilled_outputs:
        primary_output = distilled_outputs[0]

    return {
        "type": "spellvision_generation_result",
        "schema_version": 1,
        "family": "ltx",
        "display_name": "LTX-Video",
        "validation_status": "experimental",
        "task_type": "t2v",
        "backend": "comfy_prompt_api",
        "prompt_id": prompt_id,
        "client_id": client_id,
        "endpoint": endpoint,
        "output_root": str(output_root),
        "workflow_api_path": workflow_api_path,
        "status": "completed" if result_completed else submission_status,
        "completed": bool(result_completed),
        "primary_output": primary_output,
        "outputs": output_records,
        "output_count": len(output_records),
        "metadata_sidecars": metadata_sidecars,
        "model_stack": model_stack,
        "result_polling": result_polling,
        "history_ready": bool(result_completed and output_records),
        "queue_ready": True,
        "preview_ready": bool(primary_output),
        "retry_supported": True,
        "requeue_request": {
            "command": "ltx_prompt_api_gated_submission",
            "prompt_api_export_path": workflow_api_path,
            "submit_to_comfy": True,
            "dry_run": False,
            "wait_for_result": True,
            "capture_metadata": True,
        },
    }


def _build_spellvision_queue_event(
    result_contract: dict[str, Any],
    *,
    submission_status: str,
    prompt_id: str,
) -> dict[str, Any]:
    primary = result_contract.get("primary_output") if isinstance(result_contract.get("primary_output"), dict) else {}

    return {
        "type": "spellvision_queue_result_event",
        "schema_version": 1,
        "family": "ltx",
        "task_type": "t2v",
        "backend": "comfy_prompt_api",
        "prompt_id": prompt_id,
        "state": "completed" if result_contract.get("completed") else submission_status,
        "title": "LTX Prompt API generation",
        "summary": f"{result_contract.get('output_count', 0)} video output(s) captured",
        "primary_output_path": primary.get("path", ""),
        "primary_metadata_path": primary.get("metadata_path", ""),
        "outputs": result_contract.get("outputs", []),
        "result_ref": {
            "type": result_contract.get("type", ""),
            "prompt_id": result_contract.get("prompt_id", ""),
            "status": result_contract.get("status", ""),
            "completed": result_contract.get("completed", False),
            "output_count": result_contract.get("output_count", 0),
            "primary_output": result_contract.get("primary_output", {}),
        },
    }


def _build_spellvision_history_record(
    result_contract: dict[str, Any],
    *,
    model_stack: dict[str, Any],
    created_at: str,
) -> dict[str, Any]:
    primary = result_contract.get("primary_output") if isinstance(result_contract.get("primary_output"), dict) else {}

    return {
        "type": "spellvision_history_record",
        "schema_version": 1,
        "created_at": created_at,
        "family": "ltx",
        "task_type": "t2v",
        "backend": "comfy_prompt_api",
        "title": "LTX Prompt API generation",
        "prompt": model_stack.get("prompt", ""),
        "negative_prompt": model_stack.get("negative_prompt", ""),
        "model": model_stack.get("model", ""),
        "seed": model_stack.get("seed"),
        "width": model_stack.get("width"),
        "height": model_stack.get("height"),
        "frames": model_stack.get("frames"),
        "fps": model_stack.get("fps"),
        "primary_output_path": primary.get("path", ""),
        "primary_metadata_path": primary.get("metadata_path", ""),
        "outputs": result_contract.get("outputs", []),
        "result_ref": {
            "type": result_contract.get("type", ""),
            "prompt_id": result_contract.get("prompt_id", ""),
            "status": result_contract.get("status", ""),
            "completed": result_contract.get("completed", False),
            "output_count": result_contract.get("output_count", 0),
            "primary_output": result_contract.get("primary_output", {}),
        },
    }


def ltx_prompt_api_gated_submission_snapshot(
    req: dict[str, Any] | None = None,
    runtime_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    req = req or {}
    runtime_status = runtime_status or {}

    # The Pass 8 adapter is a safety/normalization validator. It intentionally
    # blocks requests containing live submit flags. For this gated submission
    # route, validate a sanitized copy of the request, then apply submission
    # intent only after safe_to_submit is true.
    adapter_req = dict(req)
    for submit_key in ("submit", "execute", "submit_to_comfy"):
        adapter_req.pop(submit_key, None)
    adapter_req["dry_run"] = True

    adapter = ltx_prompt_api_conversion_adapter_snapshot(adapter_req, runtime_status=runtime_status)

    requested_submit = bool(req.get("submit") or req.get("execute") or req.get("submit_to_comfy"))
    dry_run = bool(req.get("dry_run", not requested_submit))
    wait_for_result = bool(req.get("wait_for_result") or req.get("poll_result") or req.get("capture_metadata"))
    capture_metadata = bool(req.get("capture_metadata", wait_for_result))
    client_id = str(req.get("client_id") or f"spellvision-ltx-{uuid.uuid4().hex}")

    endpoint = _endpoint_from_runtime(runtime_status)
    output_root = _comfy_output_root(runtime_status)
    prompt_api_preview = adapter.get("prompt_api_preview") if isinstance(adapter.get("prompt_api_preview"), dict) else {}
    model_stack = _extract_prompt_node_inputs(prompt_api_preview)
    created_at = _utc_now_iso()

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
                "model_stack": model_stack,
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

    model_stack = _extract_prompt_node_inputs(prompt_api_preview)
    created_at = _utc_now_iso()

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

    result_contract = _build_spellvision_result_contract(
        prompt_id=prompt_id,
        client_id=client_id,
        endpoint=endpoint,
        output_root=output_root,
        submission_status=submission_status,
        result_completed=result_completed,
        outputs=outputs,
        metadata_sidecars=metadata_sidecars,
        model_stack=model_stack,
        result_polling=result_polling,
        workflow_api_path=str(req.get("prompt_api_export_path") or ""),
    )

    queue_result_event = _build_spellvision_queue_event(
        result_contract,
        submission_status=submission_status,
        prompt_id=prompt_id,
    )

    history_record = _build_spellvision_history_record(
        result_contract,
        model_stack=model_stack,
        created_at=created_at,
    )

    should_register_result = bool(req.get("register_result", result_completed))
    result_registration: dict[str, Any] = {
        "type": "spellvision_result_registration",
        "ok": True,
        "registered": False,
        "reason": "registration_not_requested_or_result_not_completed",
    }

    if should_register_result and result_completed:
        try:
            result_registration = register_ltx_queue_history_result(
                result_contract=result_contract,
                queue_result_event=queue_result_event,
                history_record=history_record,
                runtime_status=runtime_status,
                request=req,
            )
        except Exception as exc:
            result_registration = {
                "type": "spellvision_result_registration",
                "ok": False,
                "registered": False,
                "error": str(exc),
            }

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
        "model_stack": model_stack,
        "spellvision_result": result_contract,
        "queue_result_event": queue_result_event,
        "history_record": history_record,
        "result_registration": result_registration,
        "registered_result": bool(result_registration.get("registered", False)),
        "primary_output": result_contract.get("primary_output", {}),
        "ui_outputs": result_contract.get("outputs", []),
        "adapter": adapter if bool(req.get("include_adapter", False)) else {},
        "notes": [
            "This route submits only when the Pass 8 adapter reports safe_to_submit=True.",
            "Pass 10 can poll Comfy history, resolve output files, and write SpellVision metadata sidecars.",
            "Default behavior is dry-run unless submit_to_comfy=true and dry_run=false are provided.",
            "Pass 12 registers completed LTX results into SpellVision queue/history registry files.",
            "No Wan production routing is changed by this LTX experimental route.",
        ],
    }




