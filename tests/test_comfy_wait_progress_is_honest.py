"""The ComfyUI wait reports a heartbeat, never a fake percentage.

`_poll_comfy_history` has no step count to offer: ComfyUI's history endpoint says done or not
done. It used to emit a 1..95 tick as `step/100`, and the status bar extrapolated an ETA from it
that hit "6s" at 99 s of a 305 s Wan render and then climbed for three minutes (2026-09-02). A
heartbeat is `progress(job, 0, 0, message)`: total 0 marks it indeterminate, the UI shows elapsed
time and a busy indicator, and the message still says what is being waited for.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import comfy_prompt_client as cpc  # noqa: E402

ERROR_STATUS = {
    "status_str": "error",
    "completed": False,
    "messages": [
        ["execution_error", {"node_id": "4", "node_type": "CLIPTextEncode",
                             "exception_type": "MemoryError", "exception_message": "out of memory"}],
    ],
}


class _Job:
    def __init__(self):
        self.progress = type("P", (), {"current": 0, "total": 0, "percent": 0.0, "message": ""})()


class _RecordingEmitter:
    def __init__(self):
        self.progress_calls: list[tuple] = []

    def progress(self, job, step, total, message=None):
        self.progress_calls.append((step, total, message))

    def status(self, *args, **kwargs):
        pass


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self._payload).encode()


def test_every_wait_heartbeat_is_indeterminate(monkeypatch):
    # Three polls with nothing in history yet, then the recorded failure ends the loop.
    answers = [{}, {}, {}, {"p1": {"status": ERROR_STATUS, "outputs": {}}}]

    def urlopen(url, timeout=None):
        return _Resp(answers.pop(0) if len(answers) > 1 else answers[0])

    monkeypatch.setattr(cpc.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(cpc.time, "sleep", lambda _s: None)
    monkeypatch.setattr(cpc, "raise_if_cancelled", lambda *a, **k: None)
    monkeypatch.setattr(cpc, "_ws", lambda: type("W", (), {
        "comfy_waiting_message": staticmethod(lambda req, elapsed: f"waiting {elapsed:.0f}s")})())

    emitter = _RecordingEmitter()
    with pytest.raises(RuntimeError):
        cpc._poll_comfy_history("http://x", "p1", {}, emitter, _Job(), object())

    assert len(emitter.progress_calls) >= 3, "the wait must keep reporting while nothing is in history"
    for step, total, message in emitter.progress_calls:
        assert total == 0, f"a heartbeat reported total={total}: that becomes a fake ETA"
        assert step == 0
        assert message and message.startswith("waiting")


def test_the_worker_records_a_heartbeat_as_indeterminate_not_zero_percent_of_something():
    import worker_service_state as wss

    job = wss.JobRecord(job_id="j", command="t2v")
    wss.update_job_progress(job, 0, 0, "waiting")
    assert job.progress.total == 0
    assert job.progress.current == 0
    assert job.progress.percent == 0.0
    assert job.progress.message == "waiting"
