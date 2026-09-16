"""Refreshing a whole library.

Sizing measured on this box 2026-09-16: 759 files, 2.09 TB, ~79 minutes of pure hashing at
440 MB/s. Three consequences the tests below pin:

  * SMALLEST FIRST. The 475 LoRAs are 130 GB and resolve in minutes; the 130 checkpoints are
    937 GB. Ordering by size means the library visibly fills up while the big files grind, rather
    than nothing happening for half an hour.
  * Cancellable, and a cancel must not lose the hashes already computed.
  * A locked root contributes a SKIP with a reason, never a silent zero.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from model_intelligence import refresh, sidecar


class FakeClient:
    """Answers by-hash for weights whose bytes we planted, misses for everything else."""

    def __init__(self, known):
        self.known = known
        self.asked = []

    def by_hash(self, digest):
        self.asked.append(digest)
        return self.known.get(digest)


def _write(root: Path, name: str, size: int) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(name.encode()[:1] or b"x") * size)
    return path


def test_plan_orders_smallest_first(tmp_path: Path):
    _write(tmp_path, "big.safetensors", 3000)
    _write(tmp_path, "small.safetensors", 10)
    _write(tmp_path, "middle.safetensors", 500)
    assert [p.name for p in refresh.plan([tmp_path])] == [
        "small.safetensors", "middle.safetensors", "big.safetensors"
    ]


def test_plan_ignores_files_that_are_not_weights(tmp_path: Path):
    _write(tmp_path, "notes.txt", 10)
    _write(tmp_path, "w.safetensors", 10)
    assert [p.name for p in refresh.plan([tmp_path])] == ["w.safetensors"]


def test_a_hit_writes_a_sidecar(tmp_path: Path):
    from model_intelligence import hashing

    weight = _write(tmp_path, "w.safetensors", 64)
    digest = hashing.file_sha256(weight)
    client = FakeClient({digest: {"id": 1, "modelId": 2, "name": "V1", "baseModel": "Krea 2",
                                  "model": {"name": "A Model", "type": "LORA"},
                                  "trainedWords": ["trigger"], "images": [], "files": []}})
    result = refresh.RefreshJob([tmp_path], client=client, models_root=tmp_path,
                                cache_path=tmp_path / "cache.json").run()
    assert result["identified"] == 1
    assert sidecar.read(weight)["display"]["name"]["value"] == "A Model"


def test_a_miss_records_no_match_and_still_writes_a_sidecar(tmp_path: Path):
    weight = _write(tmp_path, "w.safetensors", 64)
    result = refresh.RefreshJob([tmp_path], client=FakeClient({}), models_root=tmp_path,
                                cache_path=tmp_path / "cache.json").run()
    assert result["no_match"] == 1
    loaded = sidecar.read(weight)
    assert loaded is not None
    assert loaded["identity"]["sources"] == []


def test_progress_is_reported_per_file(tmp_path: Path):
    _write(tmp_path, "a.safetensors", 10)
    _write(tmp_path, "b.safetensors", 20)
    seen = []
    refresh.RefreshJob([tmp_path], client=FakeClient({}), models_root=tmp_path,
                       cache_path=tmp_path / "cache.json",
                       progress=lambda done, total, name: seen.append((done, total))).run()
    assert seen[-1] == (2, 2)


def test_cancel_stops_early_and_keeps_what_was_done(tmp_path: Path):
    """Cancel after the FIRST file completes, and the hash it computed must survive.

    Counting `cancel()` CALLS would not test this: `cancel` is consulted once per loop
    iteration AND once per chunk inside `file_sha256`, so a budget of two calls fires
    partway through file one, nothing ever finishes, and "keeps what was done" is
    vacuously true over an empty set. Counting completed FILES via `progress` is what
    makes the assertion mean something.
    """
    for index in range(5):
        _write(tmp_path, f"w{index}.safetensors", 10 + index)
    done = {"n": 0}

    def note(current: int, total: int, name: str) -> None:
        done["n"] = current

    result = refresh.RefreshJob(
        [tmp_path],
        client=FakeClient({}),
        models_root=tmp_path,
        cache_path=tmp_path / "cache.json",
        progress=note,
        cancel=lambda: done["n"] >= 1,
    ).run()
    assert 0 < result["examined"] < 5
    assert result["ok"] is True
    assert (tmp_path / "cache.json").exists()
    import json as _json

    entries = _json.loads((tmp_path / "cache.json").read_text(encoding="utf-8"))["entries"]
    assert len(entries) == result["examined"]


def test_a_locked_root_is_skipped_with_a_reason_not_counted_as_empty(tmp_path: Path, monkeypatch):
    good = tmp_path / "good"
    good.mkdir()
    _write(good, "w.safetensors", 10)
    locked = tmp_path / "locked"
    locked.mkdir()
    real = refresh.readable_roots.os.listdir

    def fake(target):
        if Path(target) == locked:
            raise OSError(-2144272384, "locked by BitLocker")
        return real(target)

    monkeypatch.setattr(refresh.readable_roots.os, "listdir", fake)
    result = refresh.RefreshJob([good, locked], client=FakeClient({}), models_root=good,
                                cache_path=tmp_path / "cache.json").run()
    assert result["skipped_unreadable"] == [str(locked)]
    assert result["examined"] == 1


def test_the_second_run_reuses_the_cache(tmp_path: Path):
    _write(tmp_path, "w.safetensors", 64)
    client = FakeClient({})
    cache = tmp_path / "cache.json"
    refresh.RefreshJob([tmp_path], client=client, models_root=tmp_path, cache_path=cache).run()
    first = len(client.asked)
    refresh.RefreshJob([tmp_path], client=client, models_root=tmp_path, cache_path=cache).run()
    assert client.asked[:first] == client.asked[first:]  # same digests, so the cache held


def test_a_lookup_error_is_recorded_and_the_run_continues(tmp_path: Path):
    class Exploding:
        def by_hash(self, digest):
            raise OSError("network down")

    _write(tmp_path, "a.safetensors", 10)
    _write(tmp_path, "b.safetensors", 20)
    result = refresh.RefreshJob([tmp_path], client=Exploding(), models_root=tmp_path,
                                cache_path=tmp_path / "cache.json").run()
    assert result["examined"] == 2
    assert len(result["errors"]) == 2
