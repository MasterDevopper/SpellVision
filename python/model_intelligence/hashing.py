"""Streaming sha256 for model weights, and a cache so it happens once.

Measured on this box 2026-09-16: 375-442 MB/s, disk-bound, with a 4-8 MB buffer. The library is
759 files and 2.09 TB, so a full first pass costs about 79 minutes. That single number decides
three things: the cache below is load-bearing rather than an optimisation, the work has to be
cancellable, and `refresh` must order small files first so the 475 LoRAs (130 GB) resolve in
minutes while the checkpoints grind.

The cache key is (size, mtime_ns). Not the digest of a sample -- a truncated download and a
finished one can share a prefix -- and not the path alone, because a re-download reuses it.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable

CHUNK_BYTES = 8 * 1024 * 1024

MODEL_EXTENSIONS: frozenset[str] = frozenset(
    {".safetensors", ".ckpt", ".pt", ".pth", ".sft", ".gguf", ".bin"}
)


def file_sha256(
    path: str | Path,
    *,
    chunk: int = CHUNK_BYTES,
    cancel: Callable[[], bool] | None = None,
) -> str | None:
    """Hex sha256 of a file, or None if `cancel()` went true partway through."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            if cancel is not None and cancel():
                return None
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def autov2(sha256_hex: str) -> str:
    """CivitAI's AutoV2: the first ten hex characters of the sha256."""
    return str(sha256_hex or "")[:10]


class HashCache:
    """(size, mtime_ns) -> sha256, persisted as JSON.

    Never raises on a damaged file: a cache that cannot be read is a cache miss, which costs time.
    A cache that raises would cost the whole refresh.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(str(path))
        self._entries: dict[str, dict[str, Any]] = {}
        self._dirty = False
        self._load()

    @staticmethod
    def _parse_entries(payload: Any) -> dict[str, dict[str, Any]]:
        entries = payload.get("entries") if isinstance(payload, dict) else None
        if not isinstance(entries, dict):
            return {}
        return {str(k): v for k, v in entries.items() if isinstance(v, dict)}

    def _read_disk(self) -> dict[str, dict[str, Any]]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return self._parse_entries(payload)

    def _load(self) -> None:
        self._entries = self._read_disk()

    @staticmethod
    def _key(file: str | Path) -> str:
        return str(Path(str(file))).replace("\\", "/").lower()

    @staticmethod
    def stamp(file: str | Path) -> tuple[int, int] | None:
        """The (size, mtime_ns) identity `get`/`put` key on, or None if `file` can't be stat'd."""
        try:
            info = os.stat(file)
        except OSError:
            return None
        return int(info.st_size), int(info.st_mtime_ns)

    def get(self, file: str | Path) -> str | None:
        entry = self._entries.get(self._key(file))
        if not entry:
            return None
        current = self.stamp(file)
        if current is None:
            return None
        if int(entry.get("size", -1)) != current[0] or int(entry.get("mtime_ns", -1)) != current[1]:
            return None
        digest = str(entry.get("sha256") or "")
        return digest or None

    def put(self, file: str | Path, digest: str, stamp: tuple[int, int] | None) -> bool:
        """Cache `digest` for `file` under `stamp` -- the (size, mtime_ns) taken BEFORE hashing.

        `stamp` must be the identity read before `file_sha256` started, not read here. Caching
        only when that stamp still matches the file's CURRENT stamp is what stops a file that
        changed mid-hash from having its OLD digest stored under its NEW identity -- a digest
        computed from bytes that no longer exist at that size/mtime, handed back by a later
        `get()` as if it were still valid. Returns whether the entry was actually cached.
        """
        if not digest or stamp is None:
            return False
        current = self.stamp(file)
        if current is None or current != stamp:
            return False
        self._entries[self._key(file)] = {
            "sha256": digest,
            "size": stamp[0],
            "mtime_ns": stamp[1],
        }
        self._dirty = True
        return True

    def save(self) -> None:
        """Write the in-memory entries to disk, merged with whatever is there right now.

        Re-reading and merging (instead of overwriting) is what lets two `HashCache` instances on
        the same path -- a foreground refresh and a post-download hook's own cache, say -- coexist:
        without it, the second `save()` would silently drop every entry the first one added.
        In-memory entries win a key collision, since they reflect this instance's most recent
        `put()`.
        """
        if not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        merged = {**self._read_disk(), **self._entries}
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(
            json.dumps({"version": 1, "entries": merged}, indent=1),
            encoding="utf-8",
        )
        os.replace(temp, self.path)
        self._entries = merged
        self._dirty = False


def hash_and_cache(
    cache: HashCache,
    path: str | Path,
    *,
    chunk: int = CHUNK_BYTES,
    cancel: Callable[[], bool] | None = None,
) -> str | None:
    """Hash `path` and cache the result -- owning the stamp-before/hash/stamp-after sequence so
    callers cannot reproduce the mid-hash race `HashCache.put` guards against by forgetting the
    pre-hash stamp. Returns the digest (whether or not it got cached), or None if cancelled."""
    before = HashCache.stamp(path)
    digest = file_sha256(path, chunk=chunk, cancel=cancel)
    if digest is None:
        return None
    cache.put(path, digest, before)
    return digest
