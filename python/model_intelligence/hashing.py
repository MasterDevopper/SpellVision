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

    def _load(self) -> None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        entries = payload.get("entries") if isinstance(payload, dict) else None
        if isinstance(entries, dict):
            self._entries = {str(k): v for k, v in entries.items() if isinstance(v, dict)}

    @staticmethod
    def _key(file: str | Path) -> str:
        return str(Path(str(file))).replace("\\", "/").lower()

    @staticmethod
    def _stamp(file: str | Path) -> tuple[int, int] | None:
        try:
            info = os.stat(file)
        except OSError:
            return None
        return int(info.st_size), int(info.st_mtime_ns)

    def get(self, file: str | Path) -> str | None:
        entry = self._entries.get(self._key(file))
        if not entry:
            return None
        stamp = self._stamp(file)
        if stamp is None:
            return None
        if int(entry.get("size", -1)) != stamp[0] or int(entry.get("mtime_ns", -1)) != stamp[1]:
            return None
        digest = str(entry.get("sha256") or "")
        return digest or None

    def put(self, file: str | Path, digest: str) -> None:
        stamp = self._stamp(file)
        if stamp is None or not digest:
            return
        self._entries[self._key(file)] = {
            "sha256": digest,
            "size": stamp[0],
            "mtime_ns": stamp[1],
        }
        self._dirty = True

    def save(self) -> None:
        if not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(
            json.dumps({"version": 1, "entries": self._entries}, indent=1),
            encoding="utf-8",
        )
        os.replace(temp, self.path)
        self._dirty = False
