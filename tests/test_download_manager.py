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


# --- ambiguous Civitai model ------------------------------------------------------------


def test_an_ambiguous_model_page_becomes_a_choice_not_just_a_red_error():
    """A Civitai model-page link naming no version, on a model with six spanning five
    architectures, is a decision the user has to make. The lane carries the variants so the UI
    can present them."""
    from model_sources import AmbiguousCivitaiModel, model_variants

    payload = {"modelVersions": [
        {"id": 1, "name": "SDXL v1", "baseModel": "SDXL 1.0",
         "files": [{"name": "a.safetensors", "sizeKB": 100.0, "primary": True,
                    "downloadUrl": "https://civitai.test/1"}]},
        {"id": 2, "name": "Flux.1 D v2", "baseModel": "Flux.1 D",
         "files": [{"name": "b.safetensors", "sizeKB": 100.0, "primary": True,
                    "downloadUrl": "https://civitai.test/2"}]},
    ]}
    variants = model_variants(payload)

    def materializer(reference, **kw):
        raise AmbiguousCivitaiModel("2842735", variants)

    mgr = DownloadManager(materializer=materializer)
    record = mgr.start("https://civitai.com/models/2842735/vintage-mix-by-ak")
    assert wait_for(lambda: record.state == FAILED)

    assert record.error_code == "AmbiguousCivitaiModel"
    assert record.context.get("needs_variant_choice") is True
    assert [v["base_model"] for v in record.context["variants"]] == ["SDXL 1.0", "Flux.1 D"]
    assert [v["architecture"] for v in record.context["variants"]] == ["sdxl", "flux"]
    assert "choose which version" in record.progress.message
    assert record.payload()["context"]["needs_variant_choice"] is True


def test_an_ordinary_failure_still_reads_as_a_failure_not_a_choice():
    def materializer(reference, **kw):
        raise RuntimeError("connection refused")

    mgr = DownloadManager(materializer=materializer)
    record = mgr.start("x.safetensors")
    assert wait_for(lambda: record.state == FAILED)
    assert "needs_variant_choice" not in record.context
    assert record.progress.message.startswith("failed:")


# --- the post-download hook -----------------------------------------------------------------
#
# This section did not exist. The hook placed files, evicted the asset cache, ran a whole-library
# refresh and held the manager's RLock while doing it, and nothing in the suite touched any of it:
# grepping models_root / model_kind / placed_path / placement across the download tests returned
# nothing. Every test below fails against the shipped hook.


@pytest.fixture
def stub_identification(monkeypatch):
    """The hook's second step makes HTTPS requests. These tests are about the first step, so the
    identification is stubbed -- and the stub records WHAT it was asked to identify, which is the
    other half of C1: one file landed, so one file is refreshed, not its whole directory."""
    from model_intelligence import refresh as mi_refresh

    asked: list[Path] = []

    def fake_refresh_one(path, **kwargs):
        asked.append(Path(str(path)))
        return {"ok": True, "examined": 1}

    monkeypatch.setattr(mi_refresh, "refresh_one", fake_refresh_one)
    return asked


def _asset_materializer(source: Path, *, cache_hit: bool = False):
    def _materialize(reference, *, asset_type="model", progress_cb=None, cancel_cb=None, **kw):
        if progress_cb:
            progress_cb(1, 1)
        return FakeAsset(local_path=str(source), cache_hit=cache_hit)

    return _materialize


def test_the_hook_places_the_download_where_the_library_can_see_it(tmp_path, stub_identification):
    source = tmp_path / "cache" / "model.safetensors"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"weights")
    models_root = tmp_path / "models"

    mgr = DownloadManager(materializer=_asset_materializer(source))
    record = mgr.start("model.safetensors", models_root=str(models_root),
                       model_kind="checkpoint")
    assert wait_for(lambda: record.state == COMPLETED)

    placed = models_root / "checkpoints" / "model.safetensors"
    assert placed.exists(), "a weight left in the asset cache is invisible to the Models page"
    assert record.placed_path == str(placed)
    assert record.local_path == str(placed)
    # The FILE that landed, not the directory it landed in.
    assert stub_identification == [placed]


def test_a_failure_in_the_hook_never_fails_a_download_that_succeeded(tmp_path, monkeypatch):
    from model_intelligence import placement

    def boom(*args, **kwargs):
        raise OSError("the models root is BitLocker-locked")

    monkeypatch.setattr(placement, "place", boom)
    source = tmp_path / "cache" / "model.safetensors"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"weights")

    mgr = DownloadManager(materializer=_asset_materializer(source))
    record = mgr.start("model.safetensors", models_root=str(tmp_path / "models"),
                       model_kind="checkpoint")
    assert wait_for(lambda: record.state == COMPLETED)
    assert record.error is None
    assert record.placed_path is None


def test_an_identification_failure_still_leaves_the_weight_placed(tmp_path, monkeypatch):
    from model_intelligence import refresh as mi_refresh

    def boom(path, **kwargs):
        raise ValueError("unknown url type")

    monkeypatch.setattr(mi_refresh, "refresh_one", boom)
    source = tmp_path / "cache" / "model.safetensors"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"weights")
    models_root = tmp_path / "models"

    mgr = DownloadManager(materializer=_asset_materializer(source))
    record = mgr.start("model.safetensors", models_root=str(models_root),
                       model_kind="checkpoint")
    assert wait_for(lambda: record.state == COMPLETED)
    assert record.placed_path == str(models_root / "checkpoints" / "model.safetensors")


def test_the_post_download_hook_does_not_hold_the_manager_lock(tmp_path, monkeypatch):
    """The hook is not a file move: it hashes, makes an HTTPS round trip that retries a 429 four
    times with backoff, fetches previews and writes a sidecar. Run inside `with self.lock:` that
    blocked every other download's progress callback, start(), snapshot() and cancel -- about 35
    minutes over a 937 GB checkpoints directory, with nothing able to stop it.

    The probe runs on ANOTHER thread on purpose. self.lock is an RLock, so a probe on the hook's
    own thread would re-enter it and pass while the lock was held against the whole world.
    """
    from model_intelligence import refresh as mi_refresh

    observed: list[bool] = []
    holder: dict[str, DownloadManager] = {}

    def probing_refresh(path, **kwargs):
        reached = threading.Event()

        def probe():
            holder["mgr"].snapshot()
            reached.set()

        threading.Thread(target=probe, daemon=True).start()
        observed.append(reached.wait(timeout=2.0))
        return {"ok": True}

    monkeypatch.setattr(mi_refresh, "refresh_one", probing_refresh)
    source = tmp_path / "cache" / "model.safetensors"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"weights")

    mgr = DownloadManager(materializer=_asset_materializer(source))
    holder["mgr"] = mgr
    record = mgr.start("model.safetensors", models_root=str(tmp_path / "models"),
                       model_kind="checkpoint")
    assert wait_for(lambda: record.state == COMPLETED, timeout=15)
    assert observed == [True], (
        "snapshot() blocked for 2s while the hook ran: the manager lock is held across it"
    )


def test_a_cache_hit_is_copied_out_not_evicted_from_the_cache(tmp_path, stub_identification):
    """`move=True` on a cache hit pulled the file OUT of python/.cache/assets. The next request
    for the same asset then found nothing, re-downloaded the whole thing, and `place`'s
    never-overwrite rule landed it as X_1.safetensors."""
    source = tmp_path / "cache" / "model.safetensors"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"weights")
    models_root = tmp_path / "models"

    mgr = DownloadManager(materializer=_asset_materializer(source, cache_hit=True))
    record = mgr.start("model.safetensors", models_root=str(models_root),
                       model_kind="checkpoint")
    assert wait_for(lambda: record.state == COMPLETED)
    assert record.cache_hit is True
    assert source.exists(), "the asset cache lost its copy, so the next request re-downloads it"
    assert (models_root / "checkpoints" / "model.safetensors").exists()


def test_downloading_the_same_asset_twice_does_not_accumulate_copies(tmp_path,
                                                                    stub_identification):
    source = tmp_path / "cache" / "model.safetensors"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"weights")
    models_root = tmp_path / "models"
    mgr = DownloadManager(materializer=_asset_materializer(source, cache_hit=True))

    first = mgr.start("one.safetensors", models_root=str(models_root), model_kind="checkpoint")
    assert wait_for(lambda: first.state == COMPLETED)
    second = mgr.start("two.safetensors", models_root=str(models_root), model_kind="checkpoint")
    assert wait_for(lambda: second.state == COMPLETED)

    landed = sorted(p.name for p in (models_root / "checkpoints").iterdir())
    assert landed == ["model.safetensors"], f"duplicated multi-GB weights: {landed}"
