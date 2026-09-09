"""Producer A: the queue item carries real step/total, and the snapshot shows them moving."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))

import worker_service as ws  # noqa: E402


def test_queue_emitter_progress_moves_at_least_five_times_and_is_monotonic(tmp_path):
    """QueueEmitter.emit used to return. The poll then had nothing to show but the 12 % floor.

    Drive emit() directly: that is the method the plant puts back to `return`, and the
    movement count is what must fail when it does.
    """
    qm = ws.QueueManager(manifest_path=tmp_path / "queue_manifest.json")
    ok, _ = qm.pause()
    assert ok
    ack = qm.enqueue({"task_command": "t2i", "queue_item_id": "q-prog", "prompt": "progress"})
    assert ack["ok"] is True

    emitter = ws.QueueEmitter(qm, "q-prog")
    seen = []
    for i in range(1, 8):
        emitter.emit({"type": "progress", "step": i, "total": 10, "message": f"{i}/10"})
        snap = qm.snapshot_payload()
        item = next(row for row in snap["items"] if row["queue_item_id"] == "q-prog")
        seen.append(item["progress"]["current"])
        assert item["progress"]["total"] == 10
        assert item["progress"]["message"] == f"{i}/10"

    assert len(seen) >= 5
    assert seen == sorted(seen)
    assert seen == list(range(1, 8))


def test_queue_emitter_ignores_payloads_with_no_progress(tmp_path):
    qm = ws.QueueManager(manifest_path=tmp_path / "q.json")
    emitter = ws.QueueEmitter(qm, "missing")
    emitter.emit({"type": "queue_ack", "ok": True})
    emitter.emit("not a dict")  # type: ignore[arg-type]
