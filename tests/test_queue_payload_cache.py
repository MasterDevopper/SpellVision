"""Guards for the QueueItem payload derivation cache.

snapshot_payload() runs on every UI poll over up to 100 items, and profiling put ~60% of that
build in video_request_metadata_from_request -- re-derived roughly five times per item per
snapshot. The derivations are cached off request_snapshot, which makes staleness the new failure
mode: request_snapshot is rewritten once, when the item starts, and result is reassigned on every
job update. These tests pin that the cache turns over at both points and that the payload stays
identical to an uncached rebuild.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from worker_queue import QueueItem, QueueItemState  # noqa: E402


def _item(**overrides) -> QueueItem:
    request = {
        "command": "t2i",
        "prompt": "a lighthouse",
        "model": "sdxl.safetensors",
        "output": "C:/out/base.png",
        "metadata_output": "C:/out/base.json",
    }
    request.update(overrides.pop("request", {}))
    return QueueItem(
        queue_item_id="q-1",
        command="t2i",
        request_snapshot=request,
        **overrides,
    )


def test_derived_is_computed_once_and_reused():
    item = _item()
    first = item.derived()
    assert item.derived() is first, "derived() should hand back the same cached mapping"


def test_invalidate_derived_picks_up_a_rewritten_request_snapshot():
    item = _item()
    assert item.payload()["output"] == "C:/out/base.png"

    # _run_queue_item() rewrites these when the item starts -- the one mutation of request_snapshot
    # after enqueue.
    item.request_snapshot["output"] = "C:/out/base__q-1.png"
    item.request_snapshot["prompt"] = "a lighthouse at dusk"
    item.invalidate_derived()

    payload = item.payload()
    assert payload["output"] == "C:/out/base__q-1.png"
    assert payload["prompt"] == "a lighthouse at dusk"


def test_result_copy_turns_over_when_result_is_reassigned():
    item = _item(state=QueueItemState.RUNNING)
    assert item.payload()["result"] is None

    item.result = {"output": "C:/out/first.png"}
    assert item.payload()["result"] == {"output": "C:/out/first.png"}

    # update_from_job() builds a fresh dict every time, so identity turns the cache over.
    item.result = {"output": "C:/out/second.png"}
    assert item.payload()["result"] == {"output": "C:/out/second.png"}

    item.result = None
    assert item.payload()["result"] is None


def test_result_payload_does_not_expose_the_live_result_dict():
    item = _item(state=QueueItemState.COMPLETED)
    item.result = {"output": "C:/out/final.png", "nested": {"seed": 7}}

    payload = item.payload()
    assert payload["result"] is not item.result
    assert payload["result"]["nested"] is not item.result["nested"]


def test_snapshot_result_drops_video_runtime_cache_but_keeps_the_flag():
    item = _item(state=QueueItemState.COMPLETED)
    item.result = {
        "output": "C:/out/clip.mp4",
        "video_runtime_cache_updated": True,
        "video_runtime_cache": {"family": "ltx", "stack": ["a"] * 200},
    }

    payload = item.payload()
    assert "video_runtime_cache" not in payload["result"]
    assert payload["result"]["video_runtime_cache_updated"] is True
    assert payload["result"]["output"] == "C:/out/clip.mp4"
    # trimming is snapshot-only -- the item keeps the full result for the manifest and archive
    assert "video_runtime_cache" in item.result


def test_payload_matches_an_uncached_rebuild():
    """A cached payload must equal what a cold item would produce from the same state."""
    item = _item(state=QueueItemState.COMPLETED)
    item.result = {"output": "C:/out/final.png"}
    item.progress.current = 20
    item.progress.total = 20
    item.progress.percent = 100.0
    item.progress.message = "done"

    warm = item.payload()

    cold = _item(state=QueueItemState.COMPLETED)
    cold.result = {"output": "C:/out/final.png"}
    cold.progress.current = 20
    cold.progress.total = 20
    cold.progress.percent = 100.0
    cold.progress.message = "done"
    cold.timestamps = item.timestamps
    cold_payload = cold.payload()

    assert warm == cold_payload


def test_progress_and_timestamps_stay_live_across_polls():
    """progress/timestamps are NOT part of the cached derivation -- they must still update."""
    item = _item(state=QueueItemState.RUNNING)
    assert item.payload()["progress"]["percent"] == 0.0

    item.progress.percent = 42.0
    item.progress.message = "sampling"
    item.timestamps.updated_at = "2026-08-25T12:00:00Z"

    payload = item.payload()
    assert payload["progress"]["percent"] == 42.0
    assert payload["progress"]["message"] == "sampling"
    assert payload["timestamps"]["updated_at"] == "2026-08-25T12:00:00Z"


def test_progress_payload_is_a_copy_not_the_live_dataclass_dict():
    item = _item()
    payload = item.payload()
    payload["progress"]["percent"] = 99.0
    assert item.progress.percent == 0.0


@pytest.mark.parametrize("field_name", ["_derived", "_result_copy", "_result_copy_src"])
def test_cache_fields_are_excluded_from_equality(field_name):
    """The cache must not leak into dataclass comparison."""
    left = _item()
    right = _item()
    left.payload()  # populates left's caches only
    assert getattr(left, field_name) is not None or field_name != "_derived"
    assert left == right
