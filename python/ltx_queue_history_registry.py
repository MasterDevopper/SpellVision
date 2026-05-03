from __future__ import annotations

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
