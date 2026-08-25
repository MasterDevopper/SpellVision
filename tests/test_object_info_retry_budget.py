"""/object_info retries against a TIME BUDGET, not a fixed attempt count.

The old form slept 0.5*(attempt+1) across 4 gaps -- five tries inside ~5 seconds. That is the
wrong shape for the failure it actually hits: ComfyUI stops serving HTTP while it swaps a large
model, and the socket refuses immediately, so all five attempts burn in about two seconds and
the job dies while ComfyUI is merely busy. Observed killing a Wan render outright when a 43GB
LTX checkpoint was being evicted.

These tests drive a fake clock and a fake sleep so they assert the retry SHAPE without waiting.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))
import comfy_prompt_client as cpc  # noqa: E402


@pytest.fixture
def fake_clock(monkeypatch):
    """Virtual time: sleeps advance the clock instead of blocking."""
    state = {"now": 0.0, "sleeps": []}
    monkeypatch.setattr(cpc.time, "monotonic", lambda: state["now"])

    def sleep(sec):
        state["sleeps"].append(sec)
        state["now"] += sec

    monkeypatch.setattr(cpc.time, "sleep", sleep)
    return state


def _always_reset(monkeypatch, counter):
    def boom(request, timeout=None):  # noqa: ARG001
        counter.append(1)
        raise ConnectionResetError(10054, "An existing connection was forcibly closed")

    monkeypatch.setattr(cpc.urllib.request, "urlopen", boom)


def test_retries_span_the_full_budget_not_a_few_seconds(fake_clock, monkeypatch):
    calls: list[int] = []
    _always_reset(monkeypatch, calls)

    with pytest.raises(RuntimeError) as exc:
        cpc._fetch_comfy_object_info("http://127.0.0.1:8188")

    assert "after" in str(exc.value)
    # The whole point: it must keep trying for ~the budget, not ~5 seconds.
    assert sum(fake_clock["sleeps"]) >= cpc._OBJECT_INFO_RETRY_BUDGET_SEC - cpc._OBJECT_INFO_RETRY_MAX_DELAY_SEC
    assert len(calls) > 5, "should outlast the old 5-attempt behaviour"


def test_backoff_is_exponential_and_capped(fake_clock, monkeypatch):
    _always_reset(monkeypatch, [])
    with pytest.raises(RuntimeError):
        cpc._fetch_comfy_object_info("http://127.0.0.1:8188")

    sleeps = fake_clock["sleeps"]
    assert sleeps[0] == 1.0
    assert sleeps[1] == 2.0
    assert sleeps[2] == 4.0
    assert max(sleeps) <= cpc._OBJECT_INFO_RETRY_MAX_DELAY_SEC
    # Cap must actually engage, otherwise the budget is spent in a handful of long sleeps.
    assert sleeps.count(cpc._OBJECT_INFO_RETRY_MAX_DELAY_SEC) >= 2


def test_recovery_mid_budget_returns_the_payload(fake_clock, monkeypatch):
    """A swap that finishes partway through must yield a normal success, not a late failure."""
    calls: list[int] = []

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"KSampler": {"input": {}}}'

    def flaky(request, timeout=None):  # noqa: ARG001
        calls.append(1)
        if len(calls) < 4:
            raise ConnectionResetError(10054, "busy swapping a model")
        return _Resp()

    monkeypatch.setattr(cpc.urllib.request, "urlopen", flaky)
    payload = cpc._fetch_comfy_object_info("http://127.0.0.1:8188")
    assert payload == {"KSampler": {"input": {}}}
    assert len(calls) == 4


def test_a_non_dict_body_still_raises(fake_clock, monkeypatch):
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'"not an object"'

    monkeypatch.setattr(cpc.urllib.request, "urlopen", lambda *a, **k: _Resp())
    with pytest.raises(RuntimeError):
        cpc._fetch_comfy_object_info("http://127.0.0.1:8188")
