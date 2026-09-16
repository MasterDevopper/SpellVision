"""Hashing and the readable-roots guard.

The guard is not hypothetical: on 2026-09-16 the D: model root was BitLocker-locked mid-session
while the running ComfyUI still advertised 131 checkpoints from it. `os.listdir` raises
WinError -2144272384 there, and the three stdlib behaviours recorded in memory turn "unreadable"
into "empty" if you let them: Path.resolve raises, Path.is_dir swallows, os.walk discards.
An empty inventory is the dangerous answer because it looks like a successful scan.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from model_intelligence import hashing, readable_roots


def test_sha256_matches_hashlib(tmp_path: Path):
    blob = tmp_path / "w.safetensors"
    blob.write_bytes(b"spellvision" * 5000)
    assert hashing.file_sha256(blob, chunk=1024) == hashlib.sha256(blob.read_bytes()).hexdigest()


def test_autov2_is_the_first_ten_hex_characters():
    assert hashing.autov2("c25a00f94e1b117770291364f6431e21") == "c25a00f94e"


def test_cancel_stops_hashing_and_returns_none(tmp_path: Path):
    blob = tmp_path / "w.safetensors"
    blob.write_bytes(b"x" * 100_000)
    assert hashing.file_sha256(blob, chunk=1024, cancel=lambda: True) is None


def test_cache_returns_the_digest_without_rereading(tmp_path: Path):
    blob = tmp_path / "w.safetensors"
    blob.write_bytes(b"one")
    cache = hashing.HashCache(tmp_path / "index.json")
    digest = hashing.hash_and_cache(cache, blob)
    assert cache.get(blob) == digest


def test_cache_misses_when_the_file_changed(tmp_path: Path):
    blob = tmp_path / "w.safetensors"
    blob.write_bytes(b"one")
    cache = hashing.HashCache(tmp_path / "index.json")
    hashing.hash_and_cache(cache, blob)
    blob.write_bytes(b"two different bytes")
    assert cache.get(blob) is None


def test_cache_survives_a_reload(tmp_path: Path):
    blob = tmp_path / "w.safetensors"
    blob.write_bytes(b"one")
    index = tmp_path / "index.json"
    first = hashing.HashCache(index)
    digest = hashing.hash_and_cache(first, blob)
    first.save()
    assert hashing.HashCache(index).get(blob) == digest


def test_save_merges_instead_of_overwriting_another_instances_entries(tmp_path: Path):
    """Two `HashCache` objects on the SAME path -- a foreground refresh and a post-download hook's
    own cache building concurrently, say -- must not stomp each other. `save()` used to write the
    whole in-memory `_entries` dict over the file, so the second instance to save discarded
    everything the first one had written. A third instance opened afterwards must see both."""
    index = tmp_path / "index.json"
    blob_a = tmp_path / "a.safetensors"
    blob_b = tmp_path / "b.safetensors"
    blob_a.write_bytes(b"aaa")
    blob_b.write_bytes(b"bbbbb")

    # Both open on an empty cache file, before EITHER has saved -- so neither's in-memory entries
    # know about the other's, which is what makes a plain overwrite in save() lossy.
    cache_one = hashing.HashCache(index)
    cache_two = hashing.HashCache(index)

    digest_a = hashing.hash_and_cache(cache_one, blob_a)
    cache_one.save()

    digest_b = hashing.hash_and_cache(cache_two, blob_b)
    cache_two.save()

    third = hashing.HashCache(index)
    assert third.get(blob_a) == digest_a
    assert third.get(blob_b) == digest_b


def test_a_corrupt_cache_file_is_not_fatal(tmp_path: Path):
    index = tmp_path / "index.json"
    index.write_text("{ this is not json", encoding="utf-8")
    assert hashing.HashCache(index).get(tmp_path / "missing.safetensors") is None


def test_put_refuses_a_stale_pre_hash_stamp(tmp_path: Path):
    """`put` takes the STAMP READ BEFORE HASHING, not one it takes itself. Passing a stamp that no
    longer matches the file's current identity -- the situation a file-changed-mid-hash produces --
    must be refused, not silently accepted."""
    blob = tmp_path / "w.safetensors"
    blob.write_bytes(b"one")
    cache = hashing.HashCache(tmp_path / "index.json")
    stale_stamp = (999_999, 1)
    assert cache.put(blob, "deadbeef", stale_stamp) is False
    assert cache.get(blob) is None


def test_a_file_that_changes_mid_hash_is_not_cached(tmp_path: Path, monkeypatch):
    """The defect this fix closes: `put()` used to stat the file AFTER hashing finished and store
    the digest beside that stamp, regardless of what the file looked like when hashing STARTED. A
    write that lands between the last read and the eventual `put()` -- exactly what a post-download
    hashing hook can race against -- meant the OLD content's digest got cached under the NEW
    content's (size, mtime_ns), and a later `get()` would hand back a digest that does not belong
    to what is on disk now.

    Reproduced here with a `cancel` callback used as an interleaving hook: after hashing has
    already consumed one real chunk, the file is overwritten with different-sized content (so the
    stamp changes) before hashing runs to completion in the SAME `file_sha256` call -- mirroring a
    concurrent writer finishing mid-hash rather than a clean cancel.
    """
    blob = tmp_path / "w.safetensors"
    blob.write_bytes(b"a" * 20_000)
    cache = hashing.HashCache(tmp_path / "index.json")

    before = hashing.HashCache.stamp(blob)
    calls = {"n": 0}

    def rewrite_after_first_real_chunk():
        calls["n"] += 1
        if calls["n"] == 2:  # the first block has already been read and hashed by now
            blob.write_bytes(b"b" * 55_000)
        return False

    digest = hashing.file_sha256(blob, chunk=1024, cancel=rewrite_after_first_real_chunk)
    assert digest is not None
    assert hashing.HashCache.stamp(blob) != before  # the file changed during that hash

    cached = cache.put(blob, digest, before)

    assert cached is False, "a digest computed across a mid-hash rewrite must not be cached"
    assert cache.get(blob) is None


def test_readable_roots_drops_a_root_that_raises(tmp_path: Path, monkeypatch):
    good = tmp_path / "good"
    good.mkdir()
    locked = tmp_path / "locked"
    locked.mkdir()
    real_listdir = readable_roots.os.listdir

    def fake_listdir(target):
        if Path(target) == locked:
            raise OSError(-2144272384, "This drive is locked by BitLocker Drive Encryption")
        return real_listdir(target)

    monkeypatch.setattr(readable_roots.os, "listdir", fake_listdir)
    assert readable_roots.readable_models_roots([good, locked]) == [good]
    assert readable_roots.root_status(locked)["reason"] == "locked"
    assert readable_roots.root_status(good)["readable"] is True


def test_a_root_with_an_embedded_null_byte_does_not_abort_the_others(tmp_path: Path):
    """`os.listdir` raises ValueError ("embedded null character"), not OSError, for a path
    containing chr(0). `root_status` promises never to raise, and the except chain only caught
    FileNotFoundError/NotADirectoryError/OSError -- so this ValueError used to escape
    `readable_models_roots` and abort enumeration of every other root in the same call."""
    good = tmp_path / "good"
    good.mkdir()
    poisoned = str(tmp_path / "bad") + chr(0) + "root"

    status = readable_roots.root_status(poisoned)
    assert status["readable"] is False
    assert status["reason"] == "error"

    assert readable_roots.readable_models_roots([good, poisoned]) == [good]


def test_a_missing_root_is_missing_not_locked(tmp_path: Path):
    status = readable_roots.root_status(tmp_path / "nope")
    assert status["readable"] is False
    assert status["reason"] == "missing"


def test_an_unreadable_root_is_never_reported_as_empty(tmp_path: Path, monkeypatch):
    """The failure that matters: a locked root must not read as a root with no models."""
    locked = tmp_path / "locked"
    locked.mkdir()
    monkeypatch.setattr(
        readable_roots.os,
        "listdir",
        lambda _t: (_ for _ in ()).throw(OSError(-2144272384, "locked")),
    )
    assert readable_roots.readable_models_roots([locked]) == []
    assert readable_roots.root_status(locked)["readable"] is False


# --- two HashCache instances on one path ------------------------------------------------------
#
# Ruling E5 made save() MERGE with disk precisely because the post-download hook constructs a
# second HashCache on the same path while a foreground refresh may be running. The merge fixed the
# sequential case; the temp file did not move with it.


def test_each_hash_cache_writes_its_own_temp_file(tmp_path, monkeypatch):
    """`path.with_suffix(suffix + ".tmp")` is the same string for every writer. Interleave two:
    A writes the temp, B writes the temp, A's os.replace consumes it, and B's raises
    FileNotFoundError out of a completed run."""
    import os as _os

    cache_path = tmp_path / ".spellvision" / "hash_index.json"
    weights = []
    for index in range(2):
        weight = tmp_path / f"w{index}.safetensors"
        weight.write_bytes(b"x" * (index + 1))
        weights.append(weight)

    temps: list[str] = []
    real_replace = hashing.os.replace

    def spy(src, dst):
        temps.append(str(src))
        return real_replace(src, dst)

    monkeypatch.setattr(hashing.os, "replace", spy)

    first = hashing.HashCache(cache_path)
    second = hashing.HashCache(cache_path)
    hashing.hash_and_cache(first, weights[0])
    first.save()
    hashing.hash_and_cache(second, weights[1])
    second.save()

    assert len(temps) == 2
    assert temps[0] != temps[1], (
        f"both writers used {temps[0]}; one os.replace consumes the other's file"
    )
    assert not list(cache_path.parent.glob("*.tmp")), "a temp file was left behind"
    assert _os.path.exists(cache_path)


def test_two_hash_caches_saving_at_once_never_lose_their_temp_file(tmp_path):
    """The race the shared temp name makes reachable, driven for real.

    What is asserted is the STOLEN TEMP FILE specifically: A writes the temp, B writes the temp,
    A's os.replace consumes it, B's raises FileNotFoundError. A unique name per writer removes
    that entirely.

    What is NOT asserted is that concurrent saving cannot fail at all, because on Windows it can
    and no naming scheme fixes it: `os.replace` onto a destination another thread currently has
    open for reading raises PermissionError. That residual is why `refresh._save_cache` wraps the
    call -- a cache write is an optimisation for the NEXT run and must never cost this one, which
    `test_a_cache_save_failure_is_recorded_not_raised` pins.
    """
    import threading

    cache_path = tmp_path / ".spellvision" / "hash_index.json"
    weights = []
    for index in range(60):
        weight = tmp_path / f"w{index}.safetensors"
        weight.write_bytes(b"x" * (index + 1))
        weights.append(weight)

    caches = [hashing.HashCache(cache_path), hashing.HashCache(cache_path)]
    failures: list[str] = []
    barrier = threading.Barrier(2)

    def worker(cache, mine):
        barrier.wait()
        for weight in mine:
            try:
                hashing.hash_and_cache(cache, weight)
                cache.save()
            except Exception as exc:  # noqa: BLE001 -- the failure IS the finding
                failures.append(repr(exc))

    threads = [
        threading.Thread(target=worker, args=(caches[0], weights[0::2])),
        threading.Thread(target=worker, args=(caches[1], weights[1::2])),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    stolen = [f for f in failures if "FileNotFoundError" in f]
    assert stolen == [], f"a writer lost its temp file to the other: {stolen[:3]}"
