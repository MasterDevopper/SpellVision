"""Persistent queue manifest and restart reconciliation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PYTHON_ROOT = ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from worker_queue import QueueManager


def test_paused_pending_queue_survives_restart_in_order(tmp_path: Path) -> None:
    manifest = tmp_path / "queue_manifest.json"
    first = QueueManager(manifest_path=manifest)
    assert first.pause()[0]
    first.enqueue({"command": "enqueue", "task_command": "t2i", "job_id": "job_a", "prompt": "a"})
    first.enqueue({"command": "enqueue", "task_command": "t2i", "job_id": "job_b", "prompt": "b"})

    restored = QueueManager(manifest_path=manifest)
    restored.recover_from_manifest()
    snapshot = restored.snapshot_payload()

    assert snapshot["queue_paused"] is True
    assert snapshot["pending_count"] == 2
    assert [item["prompt"] for item in snapshot["items"][:2]] == ["a", "b"]
    assert [item["state"] for item in snapshot["items"][:2]] == ["queued", "queued"]


def test_running_item_becomes_interrupted_and_retryable(tmp_path: Path) -> None:
    manifest = tmp_path / "queue_manifest.json"
    manifest.write_text(json.dumps({
        "type": "spellvision_queue_manifest",
        "schema_version": 1,
        "paused": True,
        "order": ["queue_running"],
        "active_queue_item_id": "queue_running",
        "items": [{
            "queue_item_id": "queue_running",
            "command": "t2i",
            "request_snapshot": {"command": "t2i", "job_id": "job_running", "prompt": "resume me"},
            "state": "running",
            "worker_job_id": "job_running",
            "source_job_id": None,
            "retry_count": 0,
            "progress": {"current": 2, "total": 10, "percent": 20.0, "message": "running"},
            "result": None,
            "error": None,
            "timestamps": {"created_at": "2026-01-01T00:00:00Z", "started_at": "2026-01-01T00:00:01Z", "finished_at": None, "updated_at": "2026-01-01T00:00:02Z"},
        }],
    }), encoding="utf-8")

    restored = QueueManager(manifest_path=manifest)
    restored.recover_from_manifest()
    item = restored.snapshot_payload()["items"][0]

    assert item["state"] == "failed"
    assert item["error"]["code"] == "worker_restart_interrupted"
    assert item["error"]["retryable"] is True
    ack = restored.retry_from_archive("job_running", {})
    assert ack["ok"] is True
    assert restored.items[ack["queue_item_id"]].request_snapshot["retry_of"] == "job_running"


def test_corrupt_queue_manifest_fails_closed_without_overwrite(tmp_path: Path) -> None:
    manifest = tmp_path / "queue_manifest.json"
    manifest.write_text("{truncated", encoding="utf-8")

    restored = QueueManager(manifest_path=manifest)
    restored.recover_from_manifest()

    assert restored.snapshot_payload()["total_count"] == 0
    assert manifest.read_text(encoding="utf-8") == "{truncated"
