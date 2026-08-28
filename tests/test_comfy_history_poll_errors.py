"""Waiting on a ComfyUI prompt: transient transport failures retry, real failures are named.

Both cases here come from one live run of the workflow acceptance test. ComfyUI hit a MemoryError
on a CLIPTextEncode node and recorded it in /history; the worker reported the job as **"timed
out"** and the real cause never reached the user.
"""
from __future__ import annotations

import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

import comfy_prompt_client as cpc  # noqa: E402


ERROR_STATUS = {
    "status_str": "error",
    "completed": False,
    "messages": [
        ["execution_start", {"prompt_id": "p1"}],
        ["execution_cached", {"nodes": []}],
        ["execution_error", {
            "prompt_id": "p1", "node_id": "11", "node_type": "CLIPTextEncode",
            "exception_type": "MemoryError",
            "exception_message": "VBAR allocation failed\n\n  File \"model_patcher.py\", line 1799",
        }],
    ],
}


def test_a_failed_prompt_names_the_node_and_the_exception():
    text = cpc._describe_comfy_execution_error("p1", ERROR_STATUS)
    assert "node 11" in text
    assert "CLIPTextEncode" in text
    assert "MemoryError" in text
    assert "VBAR allocation failed" in text
    assert "File \"model_patcher.py\"" not in text, "the first line only, not the traceback"


def test_a_failure_with_no_execution_error_entry_still_says_something_useful():
    text = cpc._describe_comfy_execution_error("p2", {"status_str": "failed", "messages": []})
    assert "p2" in text and "failed" in text


def test_a_malformed_message_list_does_not_raise():
    status = {"status_str": "error", "messages": [None, ["execution_error"], ["execution_error", "x"]]}
    assert "p3" in cpc._describe_comfy_execution_error("p3", status)


# --- the transport gap ----------------------------------------------------------------------


class _Job:
    def __init__(self):
        self.progress = type("P", (), {"current": 0, "total": 0, "percent": 0.0, "message": ""})()


class _Emitter:
    def progress(self, *args, **kwargs):
        pass

    def status(self, *args, **kwargs):
        pass


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("timed out"),            # a READ timeout -- an OSError, NOT a URLError
        OSError("connection reset by peer"),
        urllib.error.URLError("unreachable"),
        ValueError("Expecting value: line 1 column 1"),  # truncated body
    ],
)
def test_a_transient_history_failure_is_retried_not_fatal(monkeypatch, error):
    """The bug: only URLError was caught, so a read timeout escaped and killed the job with the
    bare message "timed out" -- while ComfyUI had already written the real error into /history."""
    calls = {"n": 0}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            import json

            return json.dumps({"p1": {"status": ERROR_STATUS, "outputs": {}}}).encode()

    def flaky_urlopen(url, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise error
        return _Resp()

    monkeypatch.setattr(cpc.urllib.request, "urlopen", flaky_urlopen)
    monkeypatch.setattr(cpc.time, "sleep", lambda _s: None)
    monkeypatch.setattr(cpc, "raise_if_cancelled", lambda *a, **k: None)
    monkeypatch.setattr(cpc, "_ws", lambda: type("W", (), {
        "comfy_waiting_message": staticmethod(lambda req, elapsed: "waiting")})())

    with pytest.raises(RuntimeError) as excinfo:
        cpc._poll_comfy_history("http://x", "p1", {}, _Emitter(), _Job(), object())

    assert calls["n"] == 2, "the first failure must be retried, not fatal"
    # And having retried, the loop reaches the error ComfyUI actually recorded.
    assert "CLIPTextEncode" in str(excinfo.value)
    assert "MemoryError" in str(excinfo.value)


def test_the_timeout_message_carries_the_transport_error_that_caused_it(monkeypatch):
    def always_timeout(url, timeout=None):
        raise TimeoutError("timed out")

    monkeypatch.setattr(cpc.urllib.request, "urlopen", always_timeout)
    monkeypatch.setattr(cpc.time, "sleep", lambda _s: None)
    monkeypatch.setattr(cpc, "raise_if_cancelled", lambda *a, **k: None)
    monkeypatch.setattr(cpc, "_ws", lambda: type("W", (), {
        "comfy_waiting_message": staticmethod(lambda req, elapsed: "waiting")})())

    with pytest.raises(RuntimeError) as excinfo:
        cpc._poll_comfy_history("http://x", "p9", {"comfy_timeout_sec": 0.0}, _Emitter(), _Job(), object())

    text = str(excinfo.value)
    assert "p9" in text
    assert "TimeoutError" in text, "a bare 'timed out' says nothing about what timed out"


def test_a_zero_timeout_means_zero_not_the_default(monkeypatch):
    """`float(req.get(key) or default)` turns an explicit 0 into the default. Here that meant a
    0s timeout waited 1800s -- the same falsy-zero trap as the object_info budget."""
    def always_timeout(url, timeout=None):
        raise TimeoutError("timed out")

    monkeypatch.setattr(cpc.urllib.request, "urlopen", always_timeout)
    monkeypatch.setattr(cpc.time, "sleep", lambda _s: None)
    monkeypatch.setattr(cpc, "raise_if_cancelled", lambda *a, **k: None)
    monkeypatch.setattr(cpc, "_ws", lambda: type("W", (), {
        "comfy_waiting_message": staticmethod(lambda req, elapsed: "waiting")})())

    import time as _time
    began = _time.monotonic()
    with pytest.raises(RuntimeError):
        cpc._poll_comfy_history("http://x", "p0", {"comfy_timeout_sec": 0},
                                _Emitter(), _Job(), object())
    assert _time.monotonic() - began < 5.0, "a zero timeout must not fall back to 1800s"
