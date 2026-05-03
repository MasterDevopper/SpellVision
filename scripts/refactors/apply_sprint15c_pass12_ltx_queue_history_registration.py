from pathlib import Path

root = Path(".")
registry_path = root / "python" / "ltx_queue_history_registry.py"
submission_path = root / "python" / "ltx_prompt_api_submission.py"
worker_service_path = root / "python" / "worker_service.py"
worker_client_path = root / "python" / "worker_client.py"
doc_path = root / "docs" / "sprints" / "SPRINT15C_PASS12_LTX_QUEUE_HISTORY_REGISTRATION_README.md"
script_path = root / "scripts" / "refactors" / "apply_sprint15c_pass12_ltx_queue_history_registration.py"

registry_source = r'''from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _runtime_root(runtime_status: dict[str, Any] | None = None) -> Path:
    runtime_status = runtime_status or {}

    raw_runtime_root = str(runtime_status.get("runtime_root") or "").strip()
    if raw_runtime_root:
        return Path(raw_runtime_root)

    comfy_root = str(runtime_status.get("comfy_root") or "").strip()
    if comfy_root:
        comfy_path = Path(comfy_root)
        if comfy_path.name.lower() == "comfyui":
            return comfy_path.parent

    return Path("D:/AI_ASSETS/comfy_runtime")


def registry_root(runtime_status: dict[str, Any] | None = None) -> Path:
    return _runtime_root(runtime_status) / "spellvision_registry"


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _safe_prompt_id(result_contract: dict[str, Any]) -> str:
    prompt_id = str(result_contract.get("prompt_id") or "").strip()
    return prompt_id or f"unsubmitted-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"


def register_ltx_queue_history_result(
    *,
    result_contract: dict[str, Any],
    queue_result_event: dict[str, Any],
    history_record: dict[str, Any],
    runtime_status: dict[str, Any] | None = None,
    request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request = request or {}
    root = registry_root(runtime_status)
    prompt_id = _safe_prompt_id(result_contract)
    created_at = _utc_now_iso()

    result_payload = {
        "type": "spellvision_registered_result",
        "schema_version": 1,
        "registered_at": created_at,
        "family": "ltx",
        "task_type": "t2v",
        "prompt_id": prompt_id,
        "result": result_contract,
    }

    queue_payload = dict(queue_result_event)
    queue_payload["registered_at"] = created_at
    queue_payload["registry_prompt_id"] = prompt_id

    history_payload = dict(history_record)
    history_payload["registered_at"] = created_at
    history_payload["registry_prompt_id"] = prompt_id

    result_path = root / "results" / "ltx" / f"{prompt_id}.json"
    queue_events_path = root / "queue" / "events.jsonl"
    history_events_path = root / "history" / "records.jsonl"
    latest_ltx_result_path = root / "results" / "ltx" / "latest.json"

    _write_json(result_path, result_payload)
    _write_json(latest_ltx_result_path, result_payload)
    _append_jsonl(queue_events_path, queue_payload)
    _append_jsonl(history_events_path, history_payload)

    return {
        "type": "spellvision_result_registration",
        "schema_version": 1,
        "ok": True,
        "registered": True,
        "registered_at": created_at,
        "family": "ltx",
        "task_type": "t2v",
        "prompt_id": prompt_id,
        "registry_root": str(root),
        "result_path": str(result_path),
        "latest_ltx_result_path": str(latest_ltx_result_path),
        "queue_events_path": str(queue_events_path),
        "history_records_path": str(history_events_path),
        "request_register_result": bool(request.get("register_result", True)),
    }


def read_recent_ltx_history(
    *,
    runtime_status: dict[str, Any] | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    root = registry_root(runtime_status)
    history_events_path = root / "history" / "records.jsonl"

    if not history_events_path.exists():
        return {
            "type": "spellvision_ltx_history_registry",
            "ok": True,
            "records": [],
            "history_records_path": str(history_events_path),
        }

    lines = history_events_path.read_text(encoding="utf-8").splitlines()
    records: list[dict[str, Any]] = []

    for line in lines[-max(1, limit):]:
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            records.append(item)

    return {
        "type": "spellvision_ltx_history_registry",
        "ok": True,
        "records": records,
        "history_records_path": str(history_events_path),
        "count": len(records),
    }


def read_recent_ltx_queue_events(
    *,
    runtime_status: dict[str, Any] | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    root = registry_root(runtime_status)
    queue_events_path = root / "queue" / "events.jsonl"

    if not queue_events_path.exists():
        return {
            "type": "spellvision_ltx_queue_registry",
            "ok": True,
            "events": [],
            "queue_events_path": str(queue_events_path),
        }

    lines = queue_events_path.read_text(encoding="utf-8").splitlines()
    events: list[dict[str, Any]] = []

    for line in lines[-max(1, limit):]:
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            events.append(item)

    return {
        "type": "spellvision_ltx_queue_registry",
        "ok": True,
        "events": events,
        "queue_events_path": str(queue_events_path),
        "count": len(events),
    }
'''
registry_path.write_text(registry_source, encoding="utf-8")

text = submission_path.read_text(encoding="utf-8")

# 1) Add import.
if "from ltx_queue_history_registry import register_ltx_queue_history_result" not in text:
    text = text.replace(
        "from ltx_prompt_api_adapter import ltx_prompt_api_conversion_adapter_snapshot",
        "from ltx_prompt_api_adapter import ltx_prompt_api_conversion_adapter_snapshot\n"
        "from ltx_queue_history_registry import register_ltx_queue_history_result",
    )

# 2) Add registration after queue/history contracts are built.
needle = '''    history_record = _build_spellvision_history_record(
        result_contract,
        model_stack=model_stack,
        created_at=created_at,
    )

    ok = not blocked_reasons or submitted
'''

insert = '''    history_record = _build_spellvision_history_record(
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
'''

if needle not in text:
    raise SystemExit("Could not find queue/history contract insertion point in ltx_prompt_api_submission.py.")
text = text.replace(needle, insert, 1)

# 3) Return registration fields.
needle = '''        "queue_result_event": queue_result_event,
        "history_record": history_record,
        "primary_output": result_contract.get("primary_output", {}),
'''

insert = '''        "queue_result_event": queue_result_event,
        "history_record": history_record,
        "result_registration": result_registration,
        "registered_result": bool(result_registration.get("registered", False)),
        "primary_output": result_contract.get("primary_output", {}),
'''

if needle not in text:
    raise SystemExit("Could not find return block for queue/history registration fields.")
text = text.replace(needle, insert, 1)

# 4) Update notes.
text = text.replace(
    '"No Wan production routing is changed by this LTX experimental route.",',
    '"Pass 12 registers completed LTX results into SpellVision queue/history registry files.",\n            "No Wan production routing is changed by this LTX experimental route.",',
)

submission_path.write_text(text, encoding="utf-8")

# 5) Wire worker_service read commands.
service = worker_service_path.read_text(encoding="utf-8")

if "from ltx_queue_history_registry import read_recent_ltx_history, read_recent_ltx_queue_events" not in service:
    service = service.replace(
        "from ltx_prompt_api_submission import ltx_prompt_api_gated_submission_snapshot",
        "from ltx_prompt_api_submission import ltx_prompt_api_gated_submission_snapshot\n"
        "from ltx_queue_history_registry import read_recent_ltx_history, read_recent_ltx_queue_events",
    )

handler_marker = 'if command in {"ltx_registry_history", "ltx_history_registry", "ltx_recent_history", "video_family_ltx_history_registry"}:'
if handler_marker not in service:
    insertion_point = '''        if command in {"runtime_memory_status", "runtime_diagnostics", "unload_image_runtime", "unload_video_runtime", "unload_all_runtimes", "clear_cuda_cache"}:
'''
    registry_handlers = '''        if command in {"ltx_registry_history", "ltx_history_registry", "ltx_recent_history", "video_family_ltx_history_registry"}:
            runtime_status = {}
            try:
                runtime_status = handle_comfy_runtime_status_command({})
            except Exception as exc:
                runtime_status = {"ok": False, "error": str(exc)}
            emitter.emit(read_recent_ltx_history(runtime_status=runtime_status, limit=int(req.get("limit") or 20)))
            return
        if command in {"ltx_registry_queue", "ltx_queue_registry", "ltx_recent_queue", "video_family_ltx_queue_registry"}:
            runtime_status = {}
            try:
                runtime_status = handle_comfy_runtime_status_command({})
            except Exception as exc:
                runtime_status = {"ok": False, "error": str(exc)}
            emitter.emit(read_recent_ltx_queue_events(runtime_status=runtime_status, limit=int(req.get("limit") or 20)))
            return
'''
    if insertion_point not in service:
        raise SystemExit("Could not find worker_service runtime insertion point.")
    service = service.replace(insertion_point, registry_handlers + insertion_point, 1)

worker_service_path.write_text(service, encoding="utf-8")

# 6) Wire worker_client allowlist entries if present.
client = worker_client_path.read_text(encoding="utf-8")
if '"ltx_registry_history"' not in client:
    client = client.replace(
        '"ltx_prompt_api_gated_submission"',
        '"ltx_prompt_api_gated_submission", "ltx_registry_history", "ltx_registry_queue"',
        1,
    )
worker_client_path.write_text(client, encoding="utf-8")

doc_path.parent.mkdir(parents=True, exist_ok=True)
doc_path.write_text(
'''# Sprint 15C Pass 12 — LTX Queue Job Integration and History Registration

## Goal

Register completed LTX Prompt API results into stable SpellVision queue/history/result registry files.

## Builds on

Pass 11 surfaced:

- `spellvision_result`
- `queue_result_event`
- `history_record`
- `primary_output`
- `ui_outputs`

Pass 12 persists those contracts so UI layers can consume them without parsing raw Comfy history.

## Registry location

Default:

`D:\\AI_ASSETS\\comfy_runtime\\spellvision_registry`

## Written files

- `results/ltx/<prompt_id>.json`
- `results/ltx/latest.json`
- `queue/events.jsonl`
- `history/records.jsonl`

## Updated response fields

- `result_registration`
- `registered_result`

## New read commands

- `ltx_registry_history`
- `ltx_registry_queue`

## Safety

This pass does not alter Wan routing or production queue behavior. It registers only completed LTX experimental results.
''',
    encoding="utf-8",
)

script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Sprint 15C Pass 12 LTX queue/history registration.")
