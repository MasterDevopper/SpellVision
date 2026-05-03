from pathlib import Path

root = Path(".")
ui_contract_path = root / "python" / "ltx_ui_queue_history_contract.py"
worker_service_path = root / "python" / "worker_service.py"
worker_client_path = root / "python" / "worker_client.py"
doc_path = root / "docs" / "sprints" / "SPRINT15C_PASS13_LTX_UI_QUEUE_HISTORY_CONTRACT_README.md"
script_path = root / "scripts" / "refactors" / "apply_sprint15c_pass13_ltx_ui_queue_history_contract.py"

ui_contract_source = r'''from __future__ import annotations

from pathlib import Path
from typing import Any

from ltx_queue_history_registry import read_recent_ltx_history, read_recent_ltx_queue_events


def _as_bool(value: Any) -> bool:
    return bool(value)


def _safe_str(value: Any) -> str:
    return str(value or "")


def _primary_output_from_item(item: dict[str, Any]) -> dict[str, Any]:
    primary_path = _safe_str(item.get("primary_output_path"))
    primary_metadata_path = _safe_str(item.get("primary_metadata_path"))

    outputs = item.get("outputs")
    if isinstance(outputs, list):
        for output in outputs:
            if not isinstance(output, dict):
                continue
            if output.get("role") == "full":
                return output
        for output in outputs:
            if isinstance(output, dict):
                return output

    if primary_path:
        return {
            "kind": "video",
            "role": "video",
            "label": "LTX Video",
            "filename": Path(primary_path).name,
            "path": primary_path,
            "preview_path": primary_path,
            "metadata_path": primary_metadata_path,
            "exists": Path(primary_path).exists(),
            "openable": Path(primary_path).exists(),
        }

    return {}


def _compact_outputs(outputs: Any) -> list[dict[str, Any]]:
    if not isinstance(outputs, list):
        return []

    compact: list[dict[str, Any]] = []

    for output in outputs:
        if not isinstance(output, dict):
            continue

        path = _safe_str(output.get("path"))
        compact.append(
            {
                "kind": _safe_str(output.get("kind") or "video"),
                "role": _safe_str(output.get("role") or "video"),
                "label": _safe_str(output.get("label") or "LTX Video"),
                "filename": _safe_str(output.get("filename") or Path(path).name),
                "path": path,
                "preview_path": _safe_str(output.get("preview_path") or path),
                "metadata_path": _safe_str(output.get("metadata_path")),
                "exists": _as_bool(output.get("exists")),
                "openable": _as_bool(output.get("openable", output.get("exists"))),
                "size_bytes": int(output.get("size_bytes") or 0),
                "animated": _as_bool(output.get("animated")),
                "send_to_mode": _safe_str(output.get("send_to_mode") or "t2v"),
                "requeue_supported": _as_bool(output.get("requeue_supported", True)),
            }
        )

    return compact


def _queue_card(event: dict[str, Any], index: int) -> dict[str, Any]:
    primary = _primary_output_from_item(event)
    outputs = _compact_outputs(event.get("outputs"))

    prompt_id = _safe_str(event.get("prompt_id") or event.get("registry_prompt_id"))

    return {
        "id": f"ltx-queue-{prompt_id or index}",
        "source": "ltx_registry_queue",
        "family": "ltx",
        "task_type": _safe_str(event.get("task_type") or "t2v"),
        "backend": _safe_str(event.get("backend") or "comfy_prompt_api"),
        "state": _safe_str(event.get("state") or "completed"),
        "title": _safe_str(event.get("title") or "LTX Prompt API generation"),
        "summary": _safe_str(event.get("summary") or f"{len(outputs)} video output(s) captured"),
        "prompt_id": prompt_id,
        "registered_at": _safe_str(event.get("registered_at")),
        "primary_output_path": _safe_str(event.get("primary_output_path") or primary.get("path")),
        "primary_metadata_path": _safe_str(event.get("primary_metadata_path") or primary.get("metadata_path")),
        "primary_output": primary,
        "outputs": outputs,
        "output_count": len(outputs),
        "preview_ready": bool(primary),
        "openable": bool(primary.get("openable")),
        "requeue_supported": True,
        "ui_actions": ["open_output", "open_folder", "open_metadata", "requeue"],
    }


def _history_card(record: dict[str, Any], index: int) -> dict[str, Any]:
    primary = _primary_output_from_item(record)
    outputs = _compact_outputs(record.get("outputs"))

    prompt = _safe_str(record.get("prompt"))
    prompt_id = _safe_str(record.get("registry_prompt_id"))

    return {
        "id": f"ltx-history-{prompt_id or index}",
        "source": "ltx_registry_history",
        "family": "ltx",
        "task_type": _safe_str(record.get("task_type") or "t2v"),
        "backend": _safe_str(record.get("backend") or "comfy_prompt_api"),
        "state": "completed",
        "title": _safe_str(record.get("title") or "LTX Prompt API generation"),
        "prompt": prompt,
        "negative_prompt": _safe_str(record.get("negative_prompt")),
        "model": _safe_str(record.get("model")),
        "seed": record.get("seed"),
        "width": record.get("width"),
        "height": record.get("height"),
        "frames": record.get("frames"),
        "fps": record.get("fps"),
        "registered_at": _safe_str(record.get("registered_at") or record.get("created_at")),
        "primary_output_path": _safe_str(record.get("primary_output_path") or primary.get("path")),
        "primary_metadata_path": _safe_str(record.get("primary_metadata_path") or primary.get("metadata_path")),
        "primary_output": primary,
        "outputs": outputs,
        "output_count": len(outputs),
        "preview_ready": bool(primary),
        "openable": bool(primary.get("openable")),
        "requeue_supported": True,
        "ui_actions": ["open_output", "open_folder", "open_metadata", "requeue", "copy_prompt"],
    }


def ltx_ui_queue_history_snapshot(
    *,
    runtime_status: dict[str, Any] | None = None,
    limit: int = 20,
    include_queue: bool = True,
    include_history: bool = True,
) -> dict[str, Any]:
    runtime_status = runtime_status or {}
    limit = max(1, int(limit or 20))

    queue_registry: dict[str, Any] = {"events": [], "count": 0}
    history_registry: dict[str, Any] = {"records": [], "count": 0}

    if include_queue:
        queue_registry = read_recent_ltx_queue_events(runtime_status=runtime_status, limit=limit)

    if include_history:
        history_registry = read_recent_ltx_history(runtime_status=runtime_status, limit=limit)

    queue_events = queue_registry.get("events")
    if not isinstance(queue_events, list):
        queue_events = []

    history_records = history_registry.get("records")
    if not isinstance(history_records, list):
        history_records = []

    queue_items = [_queue_card(event, index) for index, event in enumerate(queue_events) if isinstance(event, dict)]
    history_items = [_history_card(record, index) for index, record in enumerate(history_records) if isinstance(record, dict)]

    latest_history = history_items[-1] if history_items else {}
    latest_queue = queue_items[-1] if queue_items else {}

    return {
        "type": "spellvision_ltx_ui_queue_history_contract",
        "ok": True,
        "family": "ltx",
        "task_type": "t2v",
        "backend": "comfy_prompt_api",
        "schema_version": 1,
        "limit": limit,

        "queue_ready": True,
        "history_ready": True,
        "preview_ready": bool(latest_history.get("preview_ready") or latest_queue.get("preview_ready")),

        "queue_count": len(queue_items),
        "history_count": len(history_items),
        "queue_items": queue_items,
        "history_items": history_items,
        "latest_queue_item": latest_queue,
        "latest_history_item": latest_history,

        "queue_events_path": queue_registry.get("queue_events_path", ""),
        "history_records_path": history_registry.get("history_records_path", ""),

        "ui_contract": {
            "queue_item_fields": [
                "id",
                "state",
                "title",
                "summary",
                "primary_output_path",
                "outputs",
                "ui_actions",
            ],
            "history_item_fields": [
                "id",
                "prompt",
                "model",
                "seed",
                "primary_output_path",
                "outputs",
                "ui_actions",
            ],
            "recommended_queue_surface": "QueueManager completed/result row",
            "recommended_history_surface": "HistoryPage video result grid/detail pane",
        },
    }
'''
ui_contract_path.write_text(ui_contract_source, encoding="utf-8")

service = worker_service_path.read_text(encoding="utf-8")

if "from ltx_ui_queue_history_contract import ltx_ui_queue_history_snapshot" not in service:
    service = service.replace(
        "from ltx_queue_history_registry import read_recent_ltx_history, read_recent_ltx_queue_events",
        "from ltx_queue_history_registry import read_recent_ltx_history, read_recent_ltx_queue_events\n"
        "from ltx_ui_queue_history_contract import ltx_ui_queue_history_snapshot",
    )

handler_marker = 'if command in {"ltx_ui_queue_history_contract", "ltx_ui_registry_snapshot", "ltx_ui_results_contract", "video_family_ltx_ui_contract"}:'

if handler_marker not in service:
    insertion_point = '''        if command in {"ltx_registry_history", "ltx_history_registry", "ltx_recent_history", "video_family_ltx_history_registry"}:
'''
    handler = '''        if command in {"ltx_ui_queue_history_contract", "ltx_ui_registry_snapshot", "ltx_ui_results_contract", "video_family_ltx_ui_contract"}:
            runtime_status = {}
            try:
                runtime_status = handle_comfy_runtime_status_command({})
            except Exception as exc:
                runtime_status = {"ok": False, "error": str(exc)}
            emitter.emit(ltx_ui_queue_history_snapshot(
                runtime_status=runtime_status,
                limit=int(req.get("limit") or 20),
                include_queue=bool(req.get("include_queue", True)),
                include_history=bool(req.get("include_history", True)),
            ))
            return
'''
    if insertion_point not in service:
        raise SystemExit("Could not find insertion point before LTX registry history handler.")
    service = service.replace(insertion_point, handler + insertion_point, 1)

worker_service_path.write_text(service, encoding="utf-8")

client = worker_client_path.read_text(encoding="utf-8")

client_aliases = [
    '"ltx_ui_queue_history_contract"',
    '"ltx_ui_registry_snapshot"',
    '"ltx_ui_results_contract"',
    '"video_family_ltx_ui_contract"',
    '"spellvision_ltx_ui_queue_history_contract"',
]

for alias in client_aliases:
    if alias not in client:
        client = client.replace(
            '"ltx_prompt_api_gated_submission"',
            '"ltx_prompt_api_gated_submission", ' + alias,
            1,
        )

worker_client_path.write_text(client, encoding="utf-8")

doc_path.parent.mkdir(parents=True, exist_ok=True)
doc_path.write_text(
'''# Sprint 15C Pass 13 — LTX UI Queue/History Consumption Contract

## Goal

Expose completed LTX registry records as a Qt-friendly worker payload.

## New command

`ltx_ui_queue_history_contract`

Aliases:

- `ltx_ui_registry_snapshot`
- `ltx_ui_results_contract`
- `video_family_ltx_ui_contract`

## Response type

`spellvision_ltx_ui_queue_history_contract`

## Main response fields

- `queue_items`
- `history_items`
- `latest_queue_item`
- `latest_history_item`
- `queue_count`
- `history_count`
- `ui_contract`

## Why this pass exists

The UI should consume compact, stable objects instead of raw Comfy history or raw registry files.

## Intended Qt consumers

- `QueueManager`
- `HistoryPage`
- future video result detail/preview pane

## Not included yet

This pass does not directly modify Qt widgets. The next pass should wire these fields into Queue/History UI models.
''',
    encoding="utf-8",
)

script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Sprint 15C Pass 13 LTX UI queue/history consumption contract.")
