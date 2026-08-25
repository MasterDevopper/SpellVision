"""Diffusers model loading is single-flight across concurrent requests."""
from __future__ import annotations

import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "python"))

import worker_runtime as runtime


def test_same_model_concurrent_load_is_single_flight(monkeypatch) -> None:
    snapshot = dict(runtime.MODEL_CACHE)
    calls = 0
    calls_lock = threading.Lock()
    start = threading.Event()

    def fake_build(model: str, family: str | None = None):
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.08)
        return object(), object(), "cpu", "float32", family or "sdxl"

    monkeypatch.setattr(runtime, "build_pipelines", fake_build)
    monkeypatch.setattr(runtime, "cleanup_for_model_swap", lambda _key: None)
    with runtime.CACHE_LOCK:
        runtime.MODEL_CACHE.update(snapshot)
        runtime.MODEL_CACHE["key"] = None
        runtime.MODEL_CACHE["pipe"] = None
        runtime.MODEL_CACHE["img2img_pipe"] = None

    results = []

    def run() -> None:
        start.wait()
        results.append(runtime.get_or_load_pipelines("same-model", "sdxl"))

    threads = [threading.Thread(target=run) for _ in range(6)]
    for thread in threads:
        thread.start()
    start.set()
    for thread in threads:
        thread.join(timeout=3)

    try:
        assert all(not thread.is_alive() for thread in threads)
        assert len(results) == 6
        assert calls == 1
        assert sum(result[5] is False for result in results) == 1
        assert sum(result[5] is True for result in results) == 5
    finally:
        with runtime.CACHE_LOCK:
            runtime.MODEL_CACHE.clear()
            runtime.MODEL_CACHE.update(snapshot)
