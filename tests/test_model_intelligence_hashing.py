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
    digest = hashing.file_sha256(blob)
    cache.put(blob, digest)
    assert cache.get(blob) == digest


def test_cache_misses_when_the_file_changed(tmp_path: Path):
    blob = tmp_path / "w.safetensors"
    blob.write_bytes(b"one")
    cache = hashing.HashCache(tmp_path / "index.json")
    cache.put(blob, hashing.file_sha256(blob))
    blob.write_bytes(b"two different bytes")
    assert cache.get(blob) is None


def test_cache_survives_a_reload(tmp_path: Path):
    blob = tmp_path / "w.safetensors"
    blob.write_bytes(b"one")
    index = tmp_path / "index.json"
    first = hashing.HashCache(index)
    digest = hashing.file_sha256(blob)
    first.put(blob, digest)
    first.save()
    assert hashing.HashCache(index).get(blob) == digest


def test_a_corrupt_cache_file_is_not_fatal(tmp_path: Path):
    index = tmp_path / "index.json"
    index.write_text("{ this is not json", encoding="utf-8")
    assert hashing.HashCache(index).get(tmp_path / "missing.safetensors") is None


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
