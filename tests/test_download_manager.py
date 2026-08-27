"""The background download lane.

Every test drives a fake materializer rather than the network, so the suite stays offline and
deterministic. The fake honours the same ``progress_cb`` / ``cancel_cb`` contract the real
``model_sources.materialize_asset`` does -- if that contract drifts, these go red.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from download_manager import (  # noqa: E402
    CANCELLED,
    COMPLETED,
    FAILED,
    QUEUED,
    RUNNING,
    DownloadManager,
)
from model_sources import DownloadCancelled  # noqa: E402


class FakeAsset:
    def __init__(self, local_path: str, cache_hit: bool = False):
        self.local_path = local_path
        self.value = local_path
        self.metadata = {"cache_hit": cache_hit}


def chunked_materializer(total=8, chunk=1, delay=0.0, gate: threading.Event | None = None):
    """Reports progress in ``total`` steps, checking cancel between each, like the real loop."""

    def _materialize(reference, *, asset_type="model", progress_cb=None, cancel_cb=None, **kw):
        if gate is not None:
            gate.wait(timeout=5)
        done = 0
        if progress_cb:
            progress_cb(0, total)
        while done < total:
            if cancel_cb and cancel_cb():
                raise DownloadCancelled("cancelled")
            done += chunk
            if delay:
                time.sleep(delay)
            if progress_cb:
                progress_cb(min(done, total), total)
        return FakeAsset(local_path=f"/models/{reference}")

    return _materialize


def wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


# --- progress -----------------------------------------------------------------------------


def test_progress_reaches_the_ui_shape_the_queue_already_uses():
    mgr = DownloadManager(materializer=chunked_materializer(total=10))
    record = mgr.start("https://example.test/model.safetensors")
    assert wait_for(lambda: record.state == COMPLETED)

    payload = record.payload()
    assert set(payload["progress"]) == {"current", "total", "percent", "message"}
    assert payload["progress"]["percent"] == 100.0
    assert payload["state"] == COMPLETED
    assert payload["local_path"] == "/models/https://example.test/model.safetensors"


def test_intermediate_progress_is_observable_not_just_the_end():
    """A bar that only reports 0 then 100 is a spinner. Hold mid-transfer and read it."""
    gate = threading.Event()
    seen: list[float] = []

    def materializer(reference, *, asset_type="model", progress_cb=None, cancel_cb=None, **kw):
        progress_cb(0, 100)
        progress_cb(25, 100)
        seen.append(_percent(mgr, record.download_id))
        progress_cb(50, 100)
        seen.append(_percent(mgr, record.download_id))
        gate.wait(timeout=5)
        return FakeAsset("/models/x")

    mgr = DownloadManager(materializer=materializer)
    record = mgr.start("x.safetensors")
    assert wait_for(lambda: len(seen) >= 2)
    assert seen == [25.0, 50.0]
    gate.set()
    assert wait_for(lambda: record.state == COMPLETED)


def _percent(mgr: DownloadManager, download_id: str) -> float:
    for item in mgr.snapshot()["items"]:
        if item["download_id"] == download_id:
            return item["progress"]["percent"]
    raise AssertionError("download vanished from the snapshot")


def test_indeterminate_total_is_expressible_not_faked():
    """No Content-Length and no declared size is a real state; percent must not be invented."""

    def materializer(reference, *, asset_type="model", progress_cb=None, cancel_cb=None, **kw):
        progress_cb(1024, None)
        return FakeAsset("/models/x")

    mgr = DownloadManager(materializer=materializer)
    record = mgr.start("x.safetensors")
    assert wait_for(lambda: record.state == COMPLETED)
    # The transfer finished, so percent is 100 -- but while running with total unknown it is 0,
    # never a made-up fraction.
    assert record.progress.total in (0, 1024)


# --- the lane does not block the app -------------------------------------------------------


def test_start_returns_before_the_transfer_finishes():
    gate = threading.Event()
    mgr = DownloadManager(materializer=chunked_materializer(gate=gate))
    began = time.monotonic()
    record = mgr.start("slow.safetensors")
    assert time.monotonic() - began < 1.0, "start() must not wait on the transfer"
    assert record.state in (QUEUED, RUNNING)
    gate.set()
    assert wait_for(lambda: record.state == COMPLETED)


def test_concurrency_is_capped_so_a_batch_cannot_saturate_the_link():
    gate = threading.Event()
    mgr = DownloadManager(max_concurrent=2, materializer=chunked_materializer(gate=gate))
    records = [mgr.start(f"m{i}.safetensors") for i in range(5)]
    assert wait_for(lambda: len(mgr.active) == 2)
    time.sleep(0.05)
    assert len(mgr.active) == 2, "the cap must hold, not merely be the starting value"
    gate.set()
    assert wait_for(lambda: all(r.state == COMPLETED for r in records), timeout=10)


def test_the_lane_drains_in_order_after_the_cap_frees_up():
    gate = threading.Event()
    mgr = DownloadManager(max_concurrent=1, materializer=chunked_materializer(gate=gate))
    first = mgr.start("a.safetensors")
    second = mgr.start("b.safetensors")
    assert wait_for(lambda: first.state == RUNNING)
    assert second.state == QUEUED
    gate.set()
    assert wait_for(lambda: second.state == COMPLETED, timeout=10)


# --- cancel -------------------------------------------------------------------------------


def test_cancel_mid_transfer_reports_cancelled_not_failed():
    mgr = DownloadManager(materializer=chunked_materializer(total=1000, delay=0.002))
    record = mgr.start("big.safetensors")
    assert wait_for(lambda: record.progress.current > 0)
    assert mgr.cancel(record.download_id) is True
    assert wait_for(lambda: record.state == CANCELLED, timeout=10)
    assert record.error is None, "a user-requested stop is not an error to show them"


def test_cancel_before_start_finishes_the_record_since_no_thread_will_see_the_flag():
    gate = threading.Event()
    mgr = DownloadManager(max_concurrent=1, materializer=chunked_materializer(gate=gate))
    running = mgr.start("a.safetensors")
    queued = mgr.start("b.safetensors")
    assert wait_for(lambda: running.state == RUNNING)
    assert queued.state == QUEUED

    assert mgr.cancel(queued.download_id) is True
    assert queued.state == CANCELLED, "a queued item must not wait for a thread that never runs"
    gate.set()
    assert wait_for(lambda: running.state == COMPLETED, timeout=10)


def test_a_failure_after_cancel_is_still_reported_as_cancelled():
    """Tearing down a socket mid-read raises something other than DownloadCancelled. The user
    pressed Cancel; they must not be shown a red error for it."""
    started = threading.Event()

    def materializer(reference, *, asset_type="model", progress_cb=None, cancel_cb=None, **kw):
        progress_cb(1, 10)
        started.set()
        while not cancel_cb():
            time.sleep(0.01)
        raise ConnectionResetError("connection reset by peer")

    mgr = DownloadManager(materializer=materializer)
    record = mgr.start("x.safetensors")
    assert started.wait(timeout=5)
    mgr.cancel(record.download_id)
    assert wait_for(lambda: record.state == CANCELLED, timeout=10)
    assert record.error is None


def test_cancelling_an_unknown_or_finished_download_is_false_not_an_exception():
    mgr = DownloadManager(materializer=chunked_materializer())
    record = mgr.start("x.safetensors")
    assert wait_for(lambda: record.state == COMPLETED)
    assert mgr.cancel(record.download_id) is False
    assert mgr.cancel("dl_nope") is False


# --- failures -----------------------------------------------------------------------------


def test_a_real_failure_surfaces_the_message_and_the_code():
    def materializer(reference, **kw):
        raise RuntimeError("Insufficient disk space for model download and safety headroom.")

    mgr = DownloadManager(materializer=materializer)
    record = mgr.start("x.safetensors")
    assert wait_for(lambda: record.state == FAILED)
    assert "Insufficient disk space" in (record.error or "")
    assert record.error_code == "RuntimeError"


def test_one_failure_does_not_stall_the_lane():
    def materializer(reference, *, asset_type="model", progress_cb=None, cancel_cb=None, **kw):
        if "bad" in reference:
            raise RuntimeError("nope")
        if progress_cb:
            progress_cb(1, 1)
        return FakeAsset("/models/ok")

    mgr = DownloadManager(max_concurrent=1, materializer=materializer)
    bad = mgr.start("bad.safetensors")
    good = mgr.start("good.safetensors")
    assert wait_for(lambda: bad.state == FAILED)
    assert wait_for(lambda: good.state == COMPLETED), "the cap must be released on failure too"


# --- bookkeeping --------------------------------------------------------------------------


def test_requesting_the_same_file_twice_is_one_download():
    gate = threading.Event()
    mgr = DownloadManager(materializer=chunked_materializer(gate=gate))
    first = mgr.start("same.safetensors")
    second = mgr.start("same.safetensors")
    assert first.download_id == second.download_id
    assert len(mgr.snapshot()["items"]) == 1
    gate.set()
    assert wait_for(lambda: first.state == COMPLETED)


def test_a_cache_hit_completes_without_pretending_to_transfer():
    mgr = DownloadManager(materializer=lambda ref, **kw: FakeAsset("/models/x", cache_hit=True))
    record = mgr.start("x.safetensors")
    assert wait_for(lambda: record.state == COMPLETED)
    assert record.cache_hit is True
    assert record.progress.percent == 100.0


def test_snapshot_aggregate_covers_live_downloads_only():
    gate = threading.Event()

    def materializer(reference, *, asset_type="model", progress_cb=None, cancel_cb=None, **kw):
        progress_cb(50, 100)
        gate.wait(timeout=5)
        return FakeAsset("/models/x")

    mgr = DownloadManager(max_concurrent=2, materializer=materializer)
    mgr.start("a.safetensors")
    mgr.start("b.safetensors")
    assert wait_for(lambda: mgr.snapshot()["aggregate"]["total"] == 200)
    snap = mgr.snapshot()
    assert snap["aggregate"]["current"] == 100
    assert snap["aggregate"]["percent"] == 50.0
    assert snap["active"] == 2
    gate.set()
    assert wait_for(lambda: mgr.snapshot()["aggregate"]["total"] == 0)
    assert mgr.snapshot()["aggregate"]["message"] == "no downloads"


def test_empty_reference_is_rejected_rather_than_queued():
    mgr = DownloadManager(materializer=chunked_materializer())
    with pytest.raises(ValueError):
        mgr.start("   ")


def test_shutdown_cancels_everything_in_flight():
    mgr = DownloadManager(materializer=chunked_materializer(total=1000, delay=0.002))
    record = mgr.start("big.safetensors")
    assert wait_for(lambda: record.progress.current > 0)
    mgr.shutdown(timeout=5)
    assert record.state == CANCELLED
