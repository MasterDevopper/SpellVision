"""C13: client-supplied queue_item_id must not run twice while live."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))

import worker_service as ws  # noqa: E402


def _paused_queue() -> ws.QueueManager:
    qm = ws.QueueManager()
    ok, _message = qm.pause()
    assert ok
    return qm


def test_enqueue_rejects_duplicate_live_queue_item_id():
    """A second enqueue with a still-live id must fail and must not re-append pending."""
    qm = _paused_queue()
    req = {"task_command": "t2i", "queue_item_id": "q-dup", "prompt": "first"}

    ack = qm.enqueue(req)
    assert ack["ok"] is True
    assert ack["queue_item_id"] == "q-dup"
    assert list(qm.pending).count("q-dup") == 1

    with pytest.raises(ValueError, match="duplicate"):
        qm.enqueue({"task_command": "t2i", "queue_item_id": "q-dup", "prompt": "second"})

    assert list(qm.pending).count("q-dup") == 1
    assert qm.items["q-dup"].request_snapshot.get("prompt") == "first"


def test_enqueue_reuses_terminal_history_queue_item_id():
    """History ingest / retry may reuse a completed id; only live ids are rejected."""
    qm = _paused_queue()
    first = qm.enqueue({"task_command": "t2i", "queue_item_id": "q-hist", "prompt": "done"})
    assert first["ok"] is True

    item = qm.items["q-hist"]
    item.state = ws.QueueItemState.COMPLETED
    qm.pending = type(qm.pending)(qid for qid in qm.pending if qid != "q-hist")

    ack = qm.enqueue({"task_command": "t2i", "queue_item_id": "q-hist", "prompt": "again"})
    assert ack["ok"] is True
    assert ack["queue_item_id"] == "q-hist"
    assert list(qm.pending).count("q-hist") == 1
    assert qm.items["q-hist"].state == ws.QueueItemState.QUEUED
    assert qm.items["q-hist"].request_snapshot.get("prompt") == "again"


def test_snapshot_payload_resolves_affinity_without_globals():
    qm = _paused_queue()
    snap = qm.snapshot_payload()
    assert snap["ok"] is True
    assert snap["type"] == "queue_snapshot"
    assert "active_affinity_t2i" in snap
