"""Producer B: a subscriber gets progress, and the poll still moves if it dies."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import worker_service as ws
import worker_subscribe


class _FakeEmitter:
    def __init__(self, *, dead: bool = False) -> None:
        self.client_disconnected = dead
        self.payloads: list[dict] = []

    def emit(self, payload: dict) -> None:
        if self.client_disconnected:
            raise AssertionError("dead subscriber must not be written")
        self.payloads.append(payload)


def test_a_subscriber_receives_progress_payloads(tmp_path):
    worker_subscribe.reset_for_tests()
    live = _FakeEmitter()
    worker_subscribe.register(live)
    qm = ws.QueueManager(manifest_path=tmp_path / "q.json")
    qm.pause()
    qm.enqueue({"task_command": "t2i", "queue_item_id": "q-sub", "prompt": "x"})
    emitter = ws.QueueEmitter(qm, "q-sub")
    emitter.emit({"type": "progress", "step": 3, "total": 10, "message": "3/10"})
    assert live.payloads[-1]["step"] == 3
    assert live.payloads[-1]["total"] == 10
    item = qm.snapshot_payload()["items"][0]
    assert item["progress"]["current"] == 3
    assert live.payloads[-1]["queue_item_id"] == "q-sub"


def test_a_dead_subscriber_is_dropped_and_the_item_still_moves(tmp_path):
    worker_subscribe.reset_for_tests()
    dead = _FakeEmitter(dead=True)
    worker_subscribe.register(dead)
    qm = ws.QueueManager(manifest_path=tmp_path / "q.json")
    qm.pause()
    qm.enqueue({"task_command": "t2i", "queue_item_id": "q-dead", "prompt": "x"})
    emitter = ws.QueueEmitter(qm, "q-dead")
    emitter.emit({"type": "progress", "step": 4, "total": 8, "message": "4/8"})
    item = qm.snapshot_payload()["items"][0]
    assert item["progress"]["current"] == 4
    assert item["progress"]["total"] == 8


def test_progress_keeps_moving_when_nobody_is_subscribed(tmp_path):
    worker_subscribe.reset_for_tests()
    qm = ws.QueueManager(manifest_path=tmp_path / "q.json")
    qm.pause()
    qm.enqueue({"task_command": "t2i", "queue_item_id": "q-poll", "prompt": "x"})
    emitter = ws.QueueEmitter(qm, "q-poll")
    seen = []
    for i in range(1, 6):
        emitter.emit({"type": "progress", "step": i, "total": 10})
        seen.append(qm.items["q-poll"].progress.current)
    assert seen == [1, 2, 3, 4, 5]
