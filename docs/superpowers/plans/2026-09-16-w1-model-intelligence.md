# W1 Model Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every local model file learns who it is from the site that hosts it — name, pictures, trigger words, licence and the settings its author actually uses — and stores that in a per-model sidecar the rest of the app can read.

**Architecture:** A new Python package `python/model_intelligence/` hashes a weight, looks the hash up on CivitAI (public, no key needed) and HuggingFace (local sha256 index), merges a `recommended` settings block with explicit provenance per field, and writes `<stem>.spellvision.json` beside the weight. Four worker commands expose it. Nothing in the UI changes in this wave — W2 (defaults on the pages) and W5 (the Models page) consume it.

**Tech Stack:** Python 3.12 stdlib only (`hashlib`, `urllib.request`, `json`, `threading`) — no new dependencies. Existing `credential_store` (DPAPI) for keys, existing worker TCP protocol, pytest.

**Spec:** `docs/superpowers/specs/2026-09-15-t2-t6-completion-design.md` §1. Supporting research: `docs/superpowers/specs/2026-09-15-t2-t6-research/t3-t5-context.md` (code inventory), `t3-t5-metadata-research.md` (API desk research), **`live-api-validation-2026-09-16.md` (what was actually measured on this box — read this one first; it corrects the desk research).**

## Global Constraints

- **Python 3.12+, stdlib only.** No `requests`, no `huggingface_hub`, no `blake3`. The repo's HTTP lesson applies: `urllib` always sends `Connection: close`, which is fine for these small JSON bodies but **never** use `urllib` for `/object_info`-sized payloads.
- **Every new module < 300 lines.** Doc 50. A module that grows past it gets split, not excused.
- **`worker_service.py` gains nothing but an import.** Doc 50 / spec R0.5.
- **A new worker command trips three ratchets:** `python/worker_command_audience.py` classification, the wire-type registry, and the protocol-doc counts in `docs/SPELLVISION_WORKER_PROTOCOL.md`. Budget for all three in Task 9.
- **Secrets never reach a tracked file.** The owner's keys live in `%LOCALAPPDATA%\DarkDuck\SpellVision\credentials.json` (DPAPI). No key, token or `Authorization` header value may appear in source, tests, fixtures, logs or commit messages.
- **Tests that reach the network MUST use the `needs_network` marker.** `tests/conftest.py::_forbid_undeclared_ambient_dependencies` raises on an undeclared outbound connection, so forgetting is a failure, not a flake. Default `pytest` excludes `smoke` only — `needs_network` tests DO run by default, so keep them to one or two and make them skip cleanly when offline.
- **Never invent a value.** Every field in `recommended` carries `provenance`; a field with no source is absent, not defaulted silently.
- **Measured facts this plan is built on** (`live-api-validation-2026-09-16.md`): by-hash hit 4/4 on local files anonymously; hash throughput 375–442 MB/s; the library is **759 files / 2.09 TB → ~79 min** for a full first pass; `images[].meta` carries the sampler in **two different shapes**; D: was BitLocker-locked mid-session.

---

## File Structure

| File | Responsibility |
|---|---|
| `python/model_intelligence/__init__.py` | Public re-exports only. |
| `python/model_intelligence/readable_roots.py` | Which model roots can be read right now (BitLocker / unplugged guard). |
| `python/model_intelligence/hashing.py` | Streaming sha256 + AutoV2, with a `(path,size,mtime)` cache. |
| `python/model_intelligence/meta_parse.py` | Turn one `images[].meta` dict into normalised sampling fields. The sampler/scheduler splitter lives here. |
| `python/model_intelligence/civitai_lookup.py` | by-hash (single + bulk), host setting, backoff, raw-JSON cache. |
| `python/model_intelligence/hf_lookup.py` | `/api/models/{repo}?blobs=true`, README fetch, sha256→repo index. |
| `python/model_intelligence/family_seed_table.py` | Published per-family defaults as data (the floor). |
| `python/model_intelligence/recommended.py` | Merge site + card + table into one provenance-carrying block. |
| `python/model_intelligence/sidecar.py` | Read/write `<stem>.spellvision.json`, preserve `user_override` and unknown fields. |
| `python/model_intelligence/previews.py` | Download preview images; set a user picture. |
| `python/model_intelligence/placement.py` | Which models subdir a downloaded weight belongs in. |
| `python/model_intelligence/refresh.py` | Orchestration: order, resume, progress, cancel. |
| `python/model_intelligence_commands.py` | The four worker command handlers. |
| `tests/fixtures/model_intelligence/*.json` | **Already captured** from the live APIs on 2026-09-16. |

---

## Task 1: Readable roots and hashing

**Files:**
- Create: `python/model_intelligence/__init__.py`, `python/model_intelligence/readable_roots.py`, `python/model_intelligence/hashing.py`
- Test: `tests/test_model_intelligence_hashing.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `readable_roots.readable_models_roots(roots: Sequence[str | Path]) -> list[Path]`
  - `readable_roots.root_status(root) -> dict` → `{"path": str, "readable": bool, "reason": str}` where reason is `""`, `"locked"`, `"missing"` or `"error"`
  - `hashing.file_sha256(path: Path, *, chunk: int = 8 * 1024 * 1024, cancel: Callable[[], bool] | None = None) -> str | None` (None when cancelled)
  - `hashing.autov2(sha256_hex: str) -> str`
  - `hashing.HashCache(path: Path)` with `.get(file: Path) -> str | None`, `.put(file: Path, digest: str) -> None`, `.save() -> None`
  - `hashing.MODEL_EXTENSIONS: frozenset[str]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_model_intelligence_hashing.py`:

```python
"""Hashing and the readable-roots guard.

The guard is not hypothetical: on 2026-09-16 the D: model root was BitLocker-locked mid-session
while the running ComfyUI still advertised 131 checkpoints from it. `os.listdir` raises
WinError -2144272384 there, and the three stdlib behaviours recorded in memory turn "unreadable"
into "empty" if you let them: Path.resolve raises, Path.is_dir swallows, os.walk discards.
An empty inventory is the dangerous answer because it looks like a successful scan.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/test_model_intelligence_hashing.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'model_intelligence'`

- [ ] **Step 3: Write `python/model_intelligence/__init__.py`**

```python
"""Model intelligence: who a local weight is, according to the site that hosts it.

A weight on disk is a filename and some bytes. This package turns it into an identity -- name,
pictures, trigger words, licence -- and, the part the rest of the app cares about, the settings
its author actually renders with.

Measured on this box 2026-09-16: a by-hash lookup hit 4 of 4 local files ANONYMOUSLY, and the
owner's own house checkpoint publishes 10 steps / CFG 1 across 10 of 10 example images while
SpellVision was rendering it at 52 / 3.5 from the family table. Per-model settings are not a
convenience here; they are a correctness fix.
"""
from __future__ import annotations

from .hashing import HashCache, autov2, file_sha256
from .readable_roots import readable_models_roots, root_status

__all__ = [
    "HashCache",
    "autov2",
    "file_sha256",
    "readable_models_roots",
    "root_status",
]
```

- [ ] **Step 4: Write `python/model_intelligence/readable_roots.py`**

```python
"""Which model roots can be read RIGHT NOW.

D:/AI_ASSETS can come up BitLocker-locked. When it does, `os.listdir` raises WinError
-2144272384 -- and the three stdlib behaviours that matter all turn that into silence:
`Path.resolve(strict=True)` raises, `Path.is_dir()` swallows the error and answers False, and
`os.walk` discards the failing directory without a word. Every one of them converts "I could not
read this" into "there is nothing here", which is the dangerous answer: an empty inventory looks
exactly like a successful scan of an empty folder.

So readability is ASKED, once, explicitly, and a root that cannot answer is dropped by name with
a reason rather than contributing zero models to a total.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable, Sequence

# WinError for a BitLocker-locked volume, as raised by os.listdir on this box.
_BITLOCKER_ERRNOS = {-2144272384, 2144272384}


def root_status(root: str | Path) -> dict[str, Any]:
    """Report one root's readability without ever raising."""
    path = Path(str(root))
    try:
        os.listdir(path)
    except FileNotFoundError:
        return {"path": str(path), "readable": False, "reason": "missing"}
    except NotADirectoryError:
        return {"path": str(path), "readable": False, "reason": "error"}
    except OSError as exc:
        winerror = getattr(exc, "winerror", None)
        locked = winerror in _BITLOCKER_ERRNOS or "BitLocker" in str(exc)
        return {"path": str(path), "readable": False, "reason": "locked" if locked else "error"}
    return {"path": str(path), "readable": True, "reason": ""}


def readable_models_roots(roots: Sequence[str | Path] | Iterable[str | Path]) -> list[Path]:
    """The subset of roots that can be listed, in the order given, de-duplicated."""
    seen: set[str] = set()
    out: list[Path] = []
    for root in roots:
        text = str(root or "").strip()
        if not text:
            continue
        path = Path(text)
        key = str(path).rstrip("\\/").lower()
        if key in seen:
            continue
        seen.add(key)
        if root_status(path)["readable"]:
            out.append(path)
    return out
```

- [ ] **Step 5: Write `python/model_intelligence/hashing.py`**

```python
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
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/test_model_intelligence_hashing.py -q`
Expected: PASS, 10 passed

- [ ] **Step 7: Prove the guard bites**

Temporarily change `readable_models_roots` to `return [Path(str(r)) for r in roots]` (no filtering). Re-run. Expected: `test_readable_roots_drops_a_root_that_raises` and `test_an_unreadable_root_is_never_reported_as_empty` FAIL. Revert the change and re-run: PASS. Record both outcomes in the task report — a guard nobody has seen fail is a comment.

- [ ] **Step 8: Commit**

```bash
git add python/model_intelligence/ tests/test_model_intelligence_hashing.py
git commit -m "feat(models): hash a weight once, and never read a locked root as empty

759 files / 2.09 TB measured on this box: a full sha256 pass is ~79 min at
440 MB/s, so the (size,mtime_ns) cache and cancellation are load-bearing.
D: was BitLocker-locked mid-session while Comfy still advertised its 131
checkpoints, so readability is asked explicitly rather than inferred from
an empty listing."
```

---

## Task 2: Parse one `images[].meta` into sampling fields

**Files:**
- Create: `python/model_intelligence/meta_parse.py`
- Test: `tests/test_model_intelligence_meta_parse.py`
- Read (do not modify): `python/family_operating_points.py:365-392` (`COMFY_KSAMPLER_CATALOG`, `COMFY_SCHEDULER_CATALOG`)

**Interfaces:**
- Consumes: `hashing` (nothing yet).
- Produces:
  - `meta_parse.split_sampler(text: str) -> tuple[str | None, str | None]` → `(sampler, scheduler)`
  - `meta_parse.parse_meta(meta: dict) -> dict[str, Any]` → keys among `steps, cfg, sampler, scheduler, clip_skip, width, height, seed` (absent when unknown)
  - `meta_parse.mode_over(metas: Sequence[dict]) -> dict[str, dict[str, Any]]` → `{field: {"value": v, "n": int, "total": int}}`

**Why this is its own task:** the live capture proved CivitAI publishes the sampler in **two incompatible shapes**, and a wrong split silently produces a sampler ComfyUI will reject or, worse, a plausible-but-wrong scheduler. This is the highest-risk pure function in the wave and it has real fixtures.

- [ ] **Step 1: Write the failing test**

Create `tests/test_model_intelligence_meta_parse.py`:

```python
"""Turning a CivitAI example image's `meta` into settings.

Captured live 2026-09-16 (tests/fixtures/model_intelligence/): CivitAI publishes the sampler in
TWO shapes and the desk research only knew about one.

  1. Split, A1111-style   -- "sampler": "Euler",          "scheduler": "beta"
  2. Combined, Comfy-style -- "sampler": "er_sde_simple",  and no scheduler key at all

Getting (2) wrong is the expensive case: "er_sde_simple" is not a sampler ComfyUI will accept, and
a naive split on the last underscore yields "er_sde" + "simple" by luck while yielding
"dpmpp_2m_sde" -> "dpmpp_2m" + "sde" -- a real sampler and a scheduler that does not exist. So the
split is resolved against the live catalogues, longest sampler first.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from model_intelligence import meta_parse

FIXTURES = Path(__file__).parent / "fixtures" / "model_intelligence"


def _metas(name: str) -> list[dict]:
    payload = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return [image["meta"] for image in payload.get("images", []) if image.get("meta")]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("er_sde_simple", ("er_sde", "simple")),
        ("euler", ("euler", None)),
        ("Euler", ("euler", None)),
        ("euler_ancestral_beta", ("euler_ancestral", "beta")),
        ("dpmpp_2m_sde_karras", ("dpmpp_2m_sde", "karras")),
        ("dpmpp_2m_sde", ("dpmpp_2m_sde", None)),
        ("DPM++ 2M Karras", ("dpmpp_2m", "karras")),
        ("DPM++ 2M SDE Karras", ("dpmpp_2m_sde", "karras")),
        ("Euler a", ("euler_ancestral", None)),
        ("", (None, None)),
        ("something nobody ships", (None, None)),
    ],
)
def test_split_sampler(text, expected):
    assert meta_parse.split_sampler(text) == expected


def test_the_naive_last_underscore_split_would_be_wrong():
    """dpmpp_2m_sde is a whole sampler name; 'sde' is not a scheduler."""
    sampler, scheduler = meta_parse.split_sampler("dpmpp_2m_sde")
    assert sampler == "dpmpp_2m_sde"
    assert scheduler is None


def test_parse_meta_reads_size_and_numbers():
    parsed = meta_parse.parse_meta(
        {"steps": 10, "cfgScale": 1, "sampler": "er_sde_simple", "clipSkip": 2, "Size": "832x1216"}
    )
    assert parsed["steps"] == 10
    assert parsed["cfg"] == 1.0
    assert parsed["sampler"] == "er_sde"
    assert parsed["scheduler"] == "simple"
    assert parsed["clip_skip"] == 2
    assert parsed["width"] == 832
    assert parsed["height"] == 1216


def test_parse_meta_prefers_an_explicit_scheduler_key():
    parsed = meta_parse.parse_meta({"sampler": "Euler", "scheduler": "beta"})
    assert parsed["sampler"] == "euler"
    assert parsed["scheduler"] == "beta"


def test_parse_meta_omits_what_it_cannot_read():
    parsed = meta_parse.parse_meta({"prompt": "a cat", "steps": "not a number"})
    assert "steps" not in parsed
    assert "sampler" not in parsed


def test_the_house_checkpoint_fixture_yields_ten_steps_cfg_one_er_sde_simple():
    """The owner's own model. SpellVision renders it at 52/3.5 today; its author uses 10/1."""
    modes = meta_parse.mode_over(_metas("civitai_checkpoint_combined_sampler"))
    assert modes["steps"]["value"] == 10
    assert modes["steps"]["n"] == 10
    assert modes["cfg"]["value"] == 1.0
    assert modes["sampler"]["value"] == "er_sde"
    assert modes["scheduler"]["value"] == "simple"


def test_the_lora_fixture_yields_the_split_shape():
    modes = meta_parse.mode_over(_metas("civitai_lora_split_sampler"))
    assert modes["sampler"]["value"] == "euler"
    assert modes["scheduler"]["value"] == "beta"
    assert modes["steps"]["value"] == 8
    assert modes["steps"]["n"] == 8
    assert modes["steps"]["total"] == 10


def test_mode_reports_how_many_examples_agreed():
    modes = meta_parse.mode_over(
        [{"steps": 8}, {"steps": 8}, {"steps": 30}, {"prompt": "no settings here"}]
    )
    assert modes["steps"] == {"value": 8, "n": 2, "total": 4}


def test_mode_over_nothing_is_empty():
    assert meta_parse.mode_over([]) == {}
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/test_model_intelligence_meta_parse.py -q`
Expected: FAIL — `ImportError: cannot import name 'meta_parse'`

- [ ] **Step 3: Write `python/model_intelligence/meta_parse.py`**

```python
"""One CivitAI example image's `meta` -> normalised sampling fields.

`meta` is uploader-supplied and undocumented. Captured live on 2026-09-16, it arrives in two
shapes that need different handling:

    {"sampler": "Euler", "scheduler": "beta", "steps": 8, "cfgScale": 1}      # split
    {"sampler": "er_sde_simple", "steps": 10, "cfgScale": 1, "clipSkip": 1}   # combined

For the combined shape the split is resolved against the live ComfyUI catalogues rather than by
string surgery: the LONGEST catalogue sampler that prefixes the text wins, and the remainder only
becomes a scheduler if it is one. Splitting on the last underscore instead would turn
"dpmpp_2m_sde" into "dpmpp_2m" + "sde" -- a real sampler paired with a scheduler that does not
exist, which is worse than not parsing it at all.

A1111 spellings ("DPM++ 2M Karras", "Euler a") are mapped explicitly; anything unrecognised
returns None so the caller can fall through to a lower-provenance source.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, Sequence

from family_operating_points import COMFY_KSAMPLER_CATALOG, COMFY_SCHEDULER_CATALOG

# A1111 display spellings -> ComfyUI sampler names. Only what is actually seen in the wild.
_A1111_SAMPLERS: dict[str, str] = {
    "euler a": "euler_ancestral",
    "euler": "euler",
    "lms": "lms",
    "heun": "heun",
    "dpm2": "dpm_2",
    "dpm2 a": "dpm_2_ancestral",
    "dpm++ 2s a": "dpmpp_2s_ancestral",
    "dpm++ 2m": "dpmpp_2m",
    "dpm++ sde": "dpmpp_sde",
    "dpm++ 2m sde": "dpmpp_2m_sde",
    "dpm++ 3m sde": "dpmpp_3m_sde",
    "ddim": "ddim",
    "plms": "plms",
    "lcm": "lcm",
    "uni_pc": "uni_pc",
    "unipc": "uni_pc",
    "restart": "restart",
}

_SIZE_RE = re.compile(r"^\s*(\d{2,5})\s*[x×]\s*(\d{2,5})\s*$")


def _norm(text: Any) -> str:
    return str(text or "").strip().lower()


def split_sampler(text: Any) -> tuple[str | None, str | None]:
    """(sampler, scheduler) from either shape, or (None, None) when unrecognised."""
    raw = _norm(text)
    if not raw:
        return None, None

    schedulers = {_norm(s) for s in COMFY_SCHEDULER_CATALOG}

    # A1111 display form: "DPM++ 2M Karras" -- words, with an optional trailing scheduler.
    if " " in raw and "_" not in raw:
        words = raw.split()
        for cut in range(len(words), 0, -1):
            head = " ".join(words[:cut])
            if head in _A1111_SAMPLERS:
                tail = " ".join(words[cut:]).strip()
                scheduler = tail if tail in schedulers else None
                return _A1111_SAMPLERS[head], scheduler
        return None, None

    # Comfy form: an exact sampler, or sampler + "_" + scheduler.
    samplers = sorted({_norm(s) for s in COMFY_KSAMPLER_CATALOG}, key=len, reverse=True)
    if raw in samplers:
        return raw, None
    for sampler in samplers:
        if raw.startswith(sampler + "_"):
            tail = raw[len(sampler) + 1 :]
            if tail in schedulers:
                return sampler, tail
    return (raw, None) if raw in samplers else (None, None)


def _as_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def parse_meta(meta: dict[str, Any] | None) -> dict[str, Any]:
    """Normalised fields from one example image's meta. Unknown fields are ABSENT, never guessed."""
    if not isinstance(meta, dict):
        return {}
    out: dict[str, Any] = {}

    steps = _as_int(meta.get("steps"))
    if steps is not None and steps > 0:
        out["steps"] = steps

    cfg = _as_float(meta.get("cfgScale", meta.get("cfg_scale", meta.get("cfg"))))
    if cfg is not None and cfg >= 0:
        out["cfg"] = cfg

    clip_skip = _as_int(meta.get("clipSkip", meta.get("clip_skip")))
    if clip_skip is not None and clip_skip > 0:
        out["clip_skip"] = clip_skip

    seed = _as_int(meta.get("seed"))
    if seed is not None:
        out["seed"] = seed

    sampler, scheduler = split_sampler(meta.get("sampler"))
    explicit = _norm(meta.get("scheduler"))
    if explicit and explicit in {_norm(s) for s in COMFY_SCHEDULER_CATALOG}:
        scheduler = explicit
    if sampler:
        out["sampler"] = sampler
    if scheduler:
        out["scheduler"] = scheduler

    match = _SIZE_RE.match(str(meta.get("Size") or meta.get("size") or ""))
    if match:
        out["width"] = int(match.group(1))
        out["height"] = int(match.group(2))
    else:
        width = _as_int(meta.get("width"))
        height = _as_int(meta.get("height"))
        if width and height:
            out["width"] = width
            out["height"] = height

    return out


def mode_over(metas: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Most common value per field across example images.

    `n` is how many examples carried that winning value and `total` is how many were examined --
    both travel with the answer, because "8 steps in 8 of 10 examples" and "8 steps in 1 of 10"
    are different claims and the caller has to be able to tell them apart.
    """
    parsed = [parse_meta(meta) for meta in metas or []]
    total = len(parsed)
    if not total:
        return {}
    fields = {key for row in parsed for key in row}
    out: dict[str, dict[str, Any]] = {}
    for field in sorted(fields):
        if field == "seed":
            continue  # a seed is never a recommendation
        values = [row[field] for row in parsed if field in row]
        if not values:
            continue
        value, count = Counter(values).most_common(1)[0]
        out[field] = {"value": value, "n": count, "total": total}
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/test_model_intelligence_meta_parse.py -q`
Expected: PASS

- [ ] **Step 5: Prove the catalogue-based split bites**

Replace the Comfy branch of `split_sampler` with the naive version:

```python
    if "_" in raw:
        head, _, tail = raw.rpartition("_")
        return head, tail
```

Re-run. Expected: `test_split_sampler[dpmpp_2m_sde-expected8]` and `test_the_naive_last_underscore_split_would_be_wrong` FAIL. Revert; re-run: PASS. Record both in the report.

- [ ] **Step 6: Commit**

```bash
git add python/model_intelligence/meta_parse.py tests/test_model_intelligence_meta_parse.py tests/fixtures/model_intelligence/
git commit -m "feat(models): read a CivitAI example's settings, in both sampler shapes

Captured live: CivitAI publishes either split A1111 fields (Euler + beta)
or a combined Comfy string (er_sde_simple) with no scheduler key. The desk
research only knew the first. The split resolves against the live catalogues
longest-first, because rpartition('_') turns dpmpp_2m_sde into a real sampler
plus a scheduler that does not exist."
```

---

## Task 3: CivitAI lookup

**Files:**
- Create: `python/model_intelligence/civitai_lookup.py`
- Test: `tests/test_model_intelligence_civitai.py`
- Read: `python/credential_store.py:229` (`get_credential`)

**Interfaces:**
- Consumes: `credential_store.get_credential`.
- Produces:
  - `civitai_lookup.CivitaiClient(host: str = "civitai.com", api_key: str | None = None, opener=None)`
  - `.by_hash(sha256_hex: str) -> dict | None` (None on 404)
  - `.by_hashes(hashes: Sequence[str]) -> dict[str, dict]` (bulk, ≤100 per call)
  - `.model(model_id: int) -> dict | None`
  - `civitai_lookup.DEFAULT_HOST: str`, `.ALLOWED_HOSTS: frozenset[str]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_model_intelligence_civitai.py`:

```python
"""The CivitAI client.

Verified live on 2026-09-16 with the owner's read-only key:
  * by-hash hit 4 of 4 local weights, and the ANONYMOUS response was identical to the keyed one.
    Reads do not need a key; downloads and mature previews do. So a missing key must never be
    treated as an error.
  * civitai.red returned byte-identical JSON for the same hash. The host is a setting.
  * an all-zero hash returns HTTP 404, which is a MISS and not a failure.

The unit tests drive a fake opener so they neither need the network nor a key. One live test at
the end carries `needs_network` and skips cleanly when offline.
"""
from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path

import pytest

from model_intelligence import civitai_lookup

FIXTURES = Path(__file__).parent / "fixtures" / "model_intelligence"
HOUSE = json.loads((FIXTURES / "index.json").read_text(encoding="utf-8"))


class FakeResponse(io.BytesIO):
    status = 200

    def __init__(self, payload):
        super().__init__(json.dumps(payload).encode("utf-8"))


class FakeOpener:
    """Records every request and replays canned responses."""

    def __init__(self, responses):
        self.responses = responses
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        entry = self.responses.pop(0)
        if isinstance(entry, Exception):
            raise entry
        return FakeResponse(entry)


def _payload(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def test_by_hash_returns_the_version():
    opener = FakeOpener([_payload("civitai_checkpoint_combined_sampler")])
    client = civitai_lookup.CivitaiClient(opener=opener)
    version = client.by_hash("c25a00f94e1b117770291364f6431e21b4e1d7a83890ddb68b1396ec3a1db808")
    assert version["model"]["name"].startswith("Lox's Utopic World")
    assert version["baseModel"] == "Krea 2"


def test_a_404_is_a_miss_not_an_error():
    error = urllib.error.HTTPError("u", 404, "Not Found", {}, io.BytesIO(b"{}"))
    client = civitai_lookup.CivitaiClient(opener=FakeOpener([error]))
    assert client.by_hash("0" * 64) is None


def test_no_key_sends_no_authorization_header():
    opener = FakeOpener([_payload("civitai_controlnet_sparse_meta")])
    civitai_lookup.CivitaiClient(api_key=None, opener=opener).by_hash("a" * 64)
    assert opener.requests[0].get_header("Authorization") is None


def test_a_key_is_sent_as_a_bearer_token():
    opener = FakeOpener([_payload("civitai_controlnet_sparse_meta")])
    civitai_lookup.CivitaiClient(api_key="secret", opener=opener).by_hash("a" * 64)
    assert opener.requests[0].get_header("Authorization") == "Bearer secret"


def test_the_host_is_configurable_and_validated():
    opener = FakeOpener([_payload("civitai_controlnet_sparse_meta")])
    civitai_lookup.CivitaiClient(host="civitai.red", opener=opener).by_hash("a" * 64)
    assert opener.requests[0].full_url.startswith("https://civitai.red/api/v1/")
    with pytest.raises(ValueError):
        civitai_lookup.CivitaiClient(host="evil.example.com")


def test_a_429_is_retried_then_gives_up():
    throttled = urllib.error.HTTPError("u", 429, "Too Many", {}, io.BytesIO(b"{}"))
    opener = FakeOpener([throttled, throttled, throttled, throttled])
    client = civitai_lookup.CivitaiClient(opener=opener, sleep=lambda _s: None)
    with pytest.raises(civitai_lookup.CivitaiThrottled):
        client.by_hash("a" * 64)
    assert len(opener.requests) == 4


def test_a_429_that_clears_returns_the_version():
    throttled = urllib.error.HTTPError("u", 429, "Too Many", {}, io.BytesIO(b"{}"))
    opener = FakeOpener([throttled, _payload("civitai_controlnet_sparse_meta")])
    client = civitai_lookup.CivitaiClient(opener=opener, sleep=lambda _s: None)
    assert client.by_hash("a" * 64) is not None


def test_by_hashes_batches_and_keys_the_result_by_hash():
    one = _payload("civitai_lora_split_sampler")
    opener = FakeOpener([[one]])
    client = civitai_lookup.CivitaiClient(opener=opener)
    found = client.by_hashes([HOUSE["civitai_lora_split_sampler"]["sha256"]])
    assert list(found) == [HOUSE["civitai_lora_split_sampler"]["sha256"].lower()]


@pytest.mark.needs_network
def test_live_by_hash_hits_the_house_checkpoint():
    """The real API, anonymously. Skips when the network is not there."""
    import socket

    try:
        socket.create_connection(("civitai.com", 443), timeout=4).close()
    except OSError:
        pytest.skip("civitai.com unreachable")
    client = civitai_lookup.CivitaiClient()
    version = client.by_hash(HOUSE["civitai_checkpoint_combined_sampler"]["sha256"])
    assert version is not None
    assert version["model"]["name"].startswith("Lox's Utopic World")
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/test_model_intelligence_civitai.py -q`
Expected: FAIL — cannot import `civitai_lookup`

- [ ] **Step 3: Write `python/model_intelligence/civitai_lookup.py`**

```python
"""CivitAI reads. Identification by hash, no key required.

Measured 2026-09-16 against the live API with the owner's read-only key:

  * `GET /api/v1/model-versions/by-hash/{sha256}` hit 4 of 4 local weights, and the ANONYMOUS
    response was identical to the keyed one. A key buys downloads and mature previews, nothing
    here. So an absent key is a normal state, never an error.
  * `civitai.red` -- Civitai's official NSFW front door since 2026-04-15 -- served byte-identical
    JSON for the same hash. The host is therefore a setting, defaulting to civitai.com, and
    restricted to the two official spellings so a typo cannot send the owner's key elsewhere.
  * an all-zero hash answers 404. That is a MISS. Most local weights will miss, and a miss must
    cost nothing.

No published rate limit exists, so 429 is retried with jittered backoff and then surfaced rather
than swallowed: a silent give-up would look exactly like "this model is not on CivitAI".
"""
from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Sequence

DEFAULT_HOST = "civitai.com"
ALLOWED_HOSTS = frozenset({"civitai.com", "civitai.red"})
USER_AGENT = "SpellVision/1.0 (+https://github.com/MasterDevopper)"
MAX_BULK = 100
MAX_ATTEMPTS = 4


class CivitaiThrottled(RuntimeError):
    """429 survived every retry."""


class CivitaiClient:
    def __init__(
        self,
        host: str = DEFAULT_HOST,
        api_key: str | None = None,
        *,
        opener: Any = None,
        timeout: float = 25.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        cleaned = str(host or DEFAULT_HOST).strip().lower().removeprefix("https://").strip("/")
        if cleaned not in ALLOWED_HOSTS:
            raise ValueError(f"host must be one of {sorted(ALLOWED_HOSTS)}, got {host!r}")
        self.host = cleaned
        self.api_key = str(api_key or "").strip() or None
        self._opener = opener or urllib.request
        self._timeout = timeout
        self._sleep = sleep

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _request(self, path: str, *, data: bytes | None = None) -> Any:
        url = f"https://{self.host}/api/v1/{path.lstrip('/')}"
        headers = self._headers()
        if data is not None:
            headers["Content-Type"] = "application/json"
        last: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            request = urllib.request.Request(url, data=data, headers=headers)
            try:
                with self._opener.open(request, timeout=self._timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    return None
                if exc.code != 429:
                    raise
                last = exc
                if attempt < MAX_ATTEMPTS - 1:
                    self._sleep(min(8.0, 2**attempt) + random.random())
        raise CivitaiThrottled(f"429 from {self.host} after {MAX_ATTEMPTS} attempts") from last

    def by_hash(self, sha256_hex: str) -> dict[str, Any] | None:
        digest = str(sha256_hex or "").strip().lower()
        if not digest:
            return None
        payload = self._request(f"model-versions/by-hash/{digest}")
        return payload if isinstance(payload, dict) else None

    def by_hashes(self, hashes: Sequence[str]) -> dict[str, dict[str, Any]]:
        """Bulk by-hash. Returns only the hashes that matched, keyed by the hash we asked for."""
        wanted = [str(h or "").strip().lower() for h in hashes if str(h or "").strip()]
        found: dict[str, dict[str, Any]] = {}
        for start in range(0, len(wanted), MAX_BULK):
            batch = wanted[start : start + MAX_BULK]
            payload = self._request(
                "model-versions/by-hash", data=json.dumps(batch).encode("utf-8")
            )
            for version in payload or []:
                if not isinstance(version, dict):
                    continue
                for file_entry in version.get("files") or []:
                    for value in (file_entry.get("hashes") or {}).values():
                        key = str(value or "").lower()
                        if key in batch:
                            found[key] = version
        return found

    def model(self, model_id: int) -> dict[str, Any] | None:
        payload = self._request(f"models/{int(model_id)}")
        return payload if isinstance(payload, dict) else None
```

- [ ] **Step 4: Run to verify it passes**

Run: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/test_model_intelligence_civitai.py -q`
Expected: PASS (the `needs_network` test runs; it skips only when CivitAI is unreachable)

- [ ] **Step 5: Prove the host allowlist bites**

Delete the `if cleaned not in ALLOWED_HOSTS: raise` lines. Re-run. Expected: `test_the_host_is_configurable_and_validated` FAILS on the `pytest.raises` half. Revert; re-run: PASS.

- [ ] **Step 6: Commit**

```bash
git add python/model_intelligence/civitai_lookup.py tests/test_model_intelligence_civitai.py
git commit -m "feat(models): identify a weight on CivitAI by hash, without a key

Measured: by-hash hit 4 of 4 local files and the anonymous response equalled
the keyed one, so a missing key is a normal state rather than an error, and
404 is a miss rather than a failure. civitai.red serves identical JSON, so
the host is a setting -- restricted to the two official spellings so a typo
cannot post the owner's key to someone else's server."
```

---

## Task 4: HuggingFace lookup and the sha256 index

**Files:**
- Create: `python/model_intelligence/hf_lookup.py`
- Test: `tests/test_model_intelligence_hf.py`

**Interfaces:**
- Consumes: `credential_store.get_credential`.
- Produces:
  - `hf_lookup.HfClient(token: str | None = None, opener=None)` with `.model_info(repo: str) -> dict | None` and `.readme(repo: str) -> str`
  - `hf_lookup.sha256_index(info: dict) -> dict[str, str]` → `{sha256: rfilename}`
  - `hf_lookup.settings_from_readme(text: str) -> dict[str, dict[str, Any]]` → `{field: {"value": v, "provenance": "card:snippet-regex"|"card:prose-regex"}}`
  - `hf_lookup.card_identity(info: dict) -> dict[str, Any]` → `{"license", "base_model", "library_name", "pipeline_tag", "instance_prompt", "gated"}`

- [ ] **Step 1: Write the failing test**

Create `tests/test_model_intelligence_hf.py`:

```python
"""HuggingFace metadata.

Verified live 2026-09-16: `GET /api/models/{repo}` returns cardData/siblings, and `?blobs=true`
is REQUIRED for `siblings[].lfs.sha256` -- without it there is no lfs block at all, so the flag is
what makes a sha256 -> repo index possible. HF has no by-hash endpoint, so identification only
works for repos we already know about.

The most machine-readable settings on a model card are the diffusers snippet kwargs
(`num_inference_steps=50`, `guidance_scale=3.5`), which is why they outrank prose.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from model_intelligence import hf_lookup

FIXTURES = Path(__file__).parent / "fixtures" / "model_intelligence"


class FakeResponse(io.BytesIO):
    status = 200


class FakeOpener:
    def __init__(self, bodies):
        self.bodies = bodies
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        body = self.bodies.pop(0)
        if isinstance(body, (dict, list)):
            body = json.dumps(body)
        return FakeResponse(body.encode("utf-8"))


def _flux():
    return json.loads((FIXTURES / "hf_flux1_dev_blobs.json").read_text(encoding="utf-8"))


def test_model_info_asks_for_blobs():
    opener = FakeOpener([_flux()])
    hf_lookup.HfClient(opener=opener).model_info("black-forest-labs/FLUX.1-dev")
    assert "blobs=true" in opener.requests[0].full_url


def test_a_token_is_sent_as_a_bearer():
    opener = FakeOpener([_flux()])
    hf_lookup.HfClient(token="secret", opener=opener).model_info("x/y")
    assert opener.requests[0].get_header("Authorization") == "Bearer secret"


def test_sha256_index_maps_digests_to_filenames():
    index = hf_lookup.sha256_index(_flux())
    assert index
    assert all(len(digest) == 64 for digest in index)
    assert "ae.safetensors" in index.values()


def test_sha256_index_is_empty_without_blobs():
    assert hf_lookup.sha256_index({"siblings": [{"rfilename": "a.safetensors"}]}) == {}


def test_card_identity_reads_the_frontmatter():
    identity = hf_lookup.card_identity(_flux())
    assert identity["license"] == "other"
    assert identity["pipeline_tag"] == "text-to-image"
    assert identity["library_name"] == "diffusers"


def test_settings_from_a_diffusers_snippet():
    readme = """
    ```python
    image = pipe(prompt, num_inference_steps=50, guidance_scale=3.5, max_sequence_length=512).images[0]
    ```
    """
    found = hf_lookup.settings_from_readme(readme)
    assert found["steps"]["value"] == 50
    assert found["steps"]["provenance"] == "card:snippet-regex"
    assert found["guidance"]["value"] == 3.5


def test_settings_from_prose_when_there_is_no_snippet():
    found = hf_lookup.settings_from_readme("We recommend 8 steps and a CFG of 1.0 with shift 5.")
    assert found["steps"]["value"] == 8
    assert found["steps"]["provenance"] == "card:prose-regex"
    assert found["cfg"]["value"] == 1.0
    assert found["shift"]["value"] == 5.0


def test_a_snippet_outranks_prose():
    readme = """
    Community reports say 30 steps works well.
    ```python
    pipe(prompt, num_inference_steps=8)
    ```
    """
    assert hf_lookup.settings_from_readme(readme)["steps"]["value"] == 8


def test_nothing_found_is_empty_not_defaulted():
    assert hf_lookup.settings_from_readme("A model card with no numbers in it.") == {}
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/test_model_intelligence_hf.py -q`
Expected: FAIL — cannot import `hf_lookup`

- [ ] **Step 3: Write `python/model_intelligence/hf_lookup.py`**

```python
"""HuggingFace model metadata, and the local sha256 index that stands in for a by-hash API.

HF has NO by-hash endpoint (verified 2026-09-16), so a local weight can only be identified here if
we already know which repo it might belong to. `?blobs=true` is what makes even that possible: the
flag adds `siblings[].lfs.sha256`, and without it `siblings` carries filenames only.

For settings, the diffusers snippet in a card is the most reliable machine-readable source --
`num_inference_steps=50, guidance_scale=3.5` is what the authors actually run -- so it outranks
the prose regexes, which are a genuine guess.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

API = "https://huggingface.co/api/models"
RESOLVE = "https://huggingface.co"
USER_AGENT = "SpellVision/1.0"

_SNIPPET_KEYS = {
    "num_inference_steps": "steps",
    "guidance_scale": "guidance",
    "true_cfg_scale": "cfg",
    "shift": "shift",
    "num_frames": "frames",
    "fps": "fps",
    "height": "height",
    "width": "width",
}
_SNIPPET_RE = re.compile(
    r"\b(num_inference_steps|guidance_scale|true_cfg_scale|shift|num_frames|fps|height|width)"
    r"\s*=\s*([0-9]+(?:\.[0-9]+)?)"
)
_PROSE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("steps", re.compile(r"(\d{1,3})\s*(?:inference\s*)?steps\b", re.I)),
    ("cfg", re.compile(r"\bcfg(?:\s*scale)?\s*(?:of|=|:)?\s*([0-9]+(?:\.[0-9]+)?)", re.I)),
    ("guidance", re.compile(r"\bguidance(?:\s*scale)?\s*(?:of|=|:)?\s*([0-9]+(?:\.[0-9]+)?)", re.I)),
    ("shift", re.compile(r"\bshift\s*(?:of|=|:)?\s*([0-9]+(?:\.[0-9]+)?)", re.I)),
)


class HfClient:
    def __init__(self, token: str | None = None, *, opener: Any = None, timeout: float = 25.0):
        self.token = str(token or "").strip() or None
        self._opener = opener or urllib.request
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _get(self, url: str) -> str | None:
        request = urllib.request.Request(url, headers=self._headers())
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                return response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403, 404):
                return None
            raise

    def model_info(self, repo: str) -> dict[str, Any] | None:
        body = self._get(f"{API}/{str(repo).strip('/')}?blobs=true")
        if not body:
            return None
        try:
            payload = json.loads(body)
        except ValueError:
            return None
        return payload if isinstance(payload, dict) else None

    def readme(self, repo: str) -> str:
        return self._get(f"{RESOLVE}/{str(repo).strip('/')}/raw/main/README.md") or ""


def sha256_index(info: dict[str, Any] | None) -> dict[str, str]:
    """{sha256: rfilename} for every LFS sibling. Empty without `?blobs=true`."""
    out: dict[str, str] = {}
    for sibling in (info or {}).get("siblings") or []:
        lfs = sibling.get("lfs") if isinstance(sibling, dict) else None
        digest = str((lfs or {}).get("sha256") or "").lower()
        if len(digest) == 64:
            out[digest] = str(sibling.get("rfilename") or "")
    return out


def card_identity(info: dict[str, Any] | None) -> dict[str, Any]:
    card = (info or {}).get("cardData") or {}
    base = card.get("base_model")
    if isinstance(base, list):
        base = base[0] if base else None
    return {
        "license": card.get("license"),
        "license_name": card.get("license_name"),
        "base_model": base,
        "library_name": (info or {}).get("library_name") or card.get("library_name"),
        "pipeline_tag": (info or {}).get("pipeline_tag") or card.get("pipeline_tag"),
        "instance_prompt": card.get("instance_prompt"),
        "gated": (info or {}).get("gated"),
    }


def settings_from_readme(text: str) -> dict[str, dict[str, Any]]:
    """Settings a card states. Snippet kwargs outrank prose; nothing found means nothing returned."""
    body = str(text or "")
    out: dict[str, dict[str, Any]] = {}

    for match in _SNIPPET_RE.finditer(body):
        field = _SNIPPET_KEYS[match.group(1)]
        raw = match.group(2)
        value = float(raw) if "." in raw else int(raw)
        out[field] = {"value": value, "provenance": "card:snippet-regex"}

    for field, pattern in _PROSE_PATTERNS:
        if field in out:
            continue
        match = pattern.search(body)
        if not match:
            continue
        raw = match.group(1)
        value = float(raw) if "." in raw else int(raw)
        out[field] = {"value": value, "provenance": "card:prose-regex"}

    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/test_model_intelligence_hf.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add python/model_intelligence/hf_lookup.py tests/test_model_intelligence_hf.py
git commit -m "feat(models): HuggingFace card metadata and a sha256 index

HF has no by-hash endpoint, so identification needs a local index, and
?blobs=true is what makes one possible -- without it siblings carry
filenames only. Diffusers snippet kwargs outrank card prose because they
are what the authors actually run."
```

---

## Task 5: The family seed table and the recommended merge

**Files:**
- Create: `python/model_intelligence/family_seed_table.py`, `python/model_intelligence/recommended.py`
- Test: `tests/test_model_intelligence_recommended.py`

**Interfaces:**
- Consumes: `meta_parse.mode_over`, `hf_lookup.settings_from_readme`, `family_operating_points`.
- Produces:
  - `family_seed_table.seed_for(family: str, variant: str | None = None) -> dict[str, Any]`
  - `recommended.PROVENANCE_ORDER: tuple[str, ...]`
  - `recommended.build(*, civitai_version: dict | None, card_settings: dict | None, family: str | None, existing_user: dict | None = None) -> dict[str, dict[str, Any]]`

**Fields carried:** `steps, cfg, guidance, shift, sampler, scheduler, clip_skip, width, height, frames, fps, lora_strength, prompt_prefix`. Each value is `{"value": …, "provenance": …, "confidence": float, "n": int|None, "total": int|None}`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_model_intelligence_recommended.py`:

```python
"""Merging every source of "what settings does this model want" into one answer.

Precedence, strongest first:
    user  >  site:image-meta-mode  >  card:snippet-regex  >  card:prose-regex  >  table:family-default

The site mode wins over a card snippet because it is what the model's OWN author rendered with,
repeatedly, rather than a generic family example. But it only wins when enough examples agree --
a single example carrying a setting is recorded with its n and given low confidence, not treated
as a recommendation.

Nothing is ever defaulted silently: a field with no source is ABSENT.
"""
from __future__ import annotations

import json
from pathlib import Path

from model_intelligence import recommended

FIXTURES = Path(__file__).parent / "fixtures" / "model_intelligence"


def _version(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def test_the_house_checkpoint_recommends_what_its_author_renders():
    """Lox's Utopic World v2.0 Quants: 10 steps / cfg 1, unanimous over 10 examples."""
    block = recommended.build(
        civitai_version=_version("civitai_checkpoint_combined_sampler"),
        card_settings=None,
        family="krea2",
    )
    assert block["steps"]["value"] == 10
    assert block["steps"]["provenance"] == "site:image-meta-mode"
    assert block["steps"]["n"] == 10
    assert block["cfg"]["value"] == 1.0
    assert block["sampler"]["value"] == "er_sde"
    assert block["scheduler"]["value"] == "simple"


def test_the_family_table_fills_only_what_the_site_did_not_say():
    block = recommended.build(
        civitai_version=_version("civitai_checkpoint_combined_sampler"),
        card_settings=None,
        family="krea2",
    )
    # The site said nothing about canvas size for this model, so the family floor supplies it.
    assert block["width"]["provenance"] == "table:family-default"
    assert block["steps"]["provenance"] == "site:image-meta-mode"


def test_a_card_snippet_beats_the_family_table_but_loses_to_the_site():
    block = recommended.build(
        civitai_version=_version("civitai_checkpoint_combined_sampler"),
        card_settings={"steps": {"value": 50, "provenance": "card:snippet-regex"},
                       "guidance": {"value": 3.5, "provenance": "card:snippet-regex"}},
        family="krea2",
    )
    assert block["steps"]["value"] == 10           # site wins
    assert block["guidance"]["value"] == 3.5       # card fills what the site lacked
    assert block["guidance"]["provenance"] == "card:snippet-regex"


def test_a_user_value_beats_everything():
    block = recommended.build(
        civitai_version=_version("civitai_checkpoint_combined_sampler"),
        card_settings=None,
        family="krea2",
        existing_user={"steps": {"value": 24, "provenance": "user"}},
    )
    assert block["steps"]["value"] == 24
    assert block["steps"]["provenance"] == "user"


def test_a_lone_example_is_low_confidence_not_a_recommendation():
    block = recommended.build(
        civitai_version=_version("civitai_controlnet_sparse_meta"),
        card_settings=None,
        family=None,
    )
    assert block["steps"]["n"] == 1
    assert block["steps"]["confidence"] < 0.5


def test_unanimous_examples_are_high_confidence():
    block = recommended.build(
        civitai_version=_version("civitai_checkpoint_combined_sampler"),
        card_settings=None,
        family=None,
    )
    assert block["steps"]["confidence"] >= 0.9


def test_an_unknown_family_and_no_site_data_yields_nothing():
    assert recommended.build(civitai_version=None, card_settings=None, family="not_a_family") == {}


def test_trained_words_become_a_prompt_prefix():
    block = recommended.build(
        civitai_version=_version("civitai_lora_split_sampler"), card_settings=None, family="krea2"
    )
    assert block["prompt_prefix"]["value"] == "Character design"
    assert block["prompt_prefix"]["provenance"] == "site:trainedWords"


def test_every_value_declares_its_provenance():
    block = recommended.build(
        civitai_version=_version("civitai_lora_split_sampler"), card_settings=None, family="krea2"
    )
    assert block
    for field, entry in block.items():
        assert entry["provenance"] in recommended.PROVENANCE_ORDER, field
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/test_model_intelligence_recommended.py -q`
Expected: FAIL — cannot import `recommended`

- [ ] **Step 3: Write `python/model_intelligence/family_seed_table.py`**

```python
"""Published per-family defaults -- the floor under every model.

These come from official model cards and the ComfyUI workflow templates (sources recorded in
docs/superpowers/specs/2026-09-15-t2-t6-research/t3-t5-metadata-research.md section 5). They are
the WEAKEST source in `recommended`: anything a specific model says about itself wins.

This table is deliberately separate from `family_operating_points.FAMILY_OPERATING_POINTS`, which
is what the app RENDERS with and is tuned by our own render comparisons. This one is what the
model's publisher SAYS. W2 reconciles them; conflating them here would erase the distinction
between a measured choice and a published one.
"""
from __future__ import annotations

from typing import Any

SEED_TABLE: dict[str, dict[str, Any]] = {
    "sdxl": {"steps": 30, "cfg": 7.0, "sampler": "dpmpp_2m", "scheduler": "karras",
             "width": 1024, "height": 1024},
    "flux": {"steps": 20, "cfg": 1.0, "guidance": 3.5, "sampler": "euler", "scheduler": "simple",
             "width": 1024, "height": 1024},
    "krea2": {"steps": 52, "cfg": 3.5, "sampler": "er_sde", "scheduler": "simple",
              "width": 1024, "height": 1024},
    "krea2:turbo": {"steps": 8, "cfg": 1.0, "sampler": "er_sde", "scheduler": "simple",
                    "width": 1024, "height": 1024},
    "z_image": {"steps": 9, "cfg": 1.0, "shift": 3.0, "sampler": "res_multistep",
                "scheduler": "simple", "width": 1024, "height": 1024},
    "sd3": {"steps": 28, "cfg": 4.0, "sampler": "euler", "scheduler": "simple",
            "width": 1024, "height": 1024},
    "pixart": {"steps": 20, "cfg": 4.5, "sampler": "dpmpp_2m", "scheduler": "karras",
               "width": 1024, "height": 1024},
    "lumina": {"steps": 40, "cfg": 4.0, "shift": 6.0, "sampler": "euler", "scheduler": "simple",
               "width": 1024, "height": 1024},
    "anima": {"steps": 30, "cfg": 4.5, "sampler": "er_sde", "scheduler": "simple",
              "width": 1024, "height": 1024},
    "wan": {"steps": 20, "cfg": 3.5, "shift": 5.0, "sampler": "euler", "scheduler": "simple",
            "width": 832, "height": 480, "frames": 81, "fps": 16},
    "ltx": {"steps": 8, "cfg": 1.0, "sampler": "euler", "width": 832, "height": 480,
            "frames": 97, "fps": 24},
    "hunyuan_video": {"steps": 20, "cfg": 1.0, "guidance": 6.0, "shift": 7.0, "sampler": "euler",
                      "scheduler": "simple", "width": 720, "height": 1280, "frames": 129, "fps": 24},
    "mochi": {"steps": 64, "cfg": 4.5, "width": 848, "height": 480, "frames": 84, "fps": 30},
}

_ALIASES = {
    "krea-2": "krea2", "krea_2": "krea2", "pony": "sdxl", "illustrious": "sdxl",
    "stable_diffusion": "sdxl", "sd": "sdxl", "sd2": "sdxl", "zimage": "z_image",
    "z-image": "z_image", "hunyuan": "hunyuan_video", "ltxv": "ltx", "flux3": "flux",
}


def seed_for(family: str | None, variant: str | None = None) -> dict[str, Any]:
    """Published defaults for a family (and optional variant), or {} when unknown."""
    key = str(family or "").strip().lower()
    key = _ALIASES.get(key, key)
    if variant:
        specific = SEED_TABLE.get(f"{key}:{str(variant).strip().lower()}")
        if specific:
            return dict(specific)
    return dict(SEED_TABLE.get(key, {}))
```

- [ ] **Step 4: Write `python/model_intelligence/recommended.py`**

```python
"""One answer for "what settings does this model want", with its provenance attached.

Four sources disagree, so the order is declared once, here:

    user  >  site:image-meta-mode  >  card:snippet-regex  >  card:prose-regex  >  table:family-default

The site's own example images outrank a card snippet because they are what THIS model's author
renders with, repeatedly. That ordering is not theoretical: the owner's house checkpoint publishes
10 steps / CFG 1 unanimously across ten examples while the family table says 52 / 3.5, and the
app has been rendering it at 52.

Confidence is agreement, not certainty: unanimous over ten examples is 1.0, one example out of
four is 0.25. It travels with the value so a caller can show "n=10" rather than implying the
number is authoritative.

A field with no source is ABSENT. Nothing here invents a value.
"""
from __future__ import annotations

from typing import Any

from . import family_seed_table, meta_parse

PROVENANCE_ORDER: tuple[str, ...] = (
    "user",
    "site:image-meta-mode",
    "site:trainedWords",
    "card:frontmatter",
    "card:snippet-regex",
    "card:prose-regex",
    "table:family-default",
)

_RANK = {name: index for index, name in enumerate(PROVENANCE_ORDER)}

FIELDS = (
    "steps", "cfg", "guidance", "shift", "sampler", "scheduler", "clip_skip",
    "width", "height", "frames", "fps", "lora_strength", "prompt_prefix",
)


def _entry(value: Any, provenance: str, *, n: int | None = None, total: int | None = None,
           confidence: float | None = None) -> dict[str, Any]:
    if confidence is None:
        confidence = (n / total) if (n and total) else 1.0
    return {
        "value": value,
        "provenance": provenance,
        "confidence": round(float(confidence), 3),
        "n": n,
        "total": total,
    }


def _offer(out: dict[str, dict[str, Any]], field: str, candidate: dict[str, Any]) -> None:
    """Keep the candidate only if its provenance outranks what is already there."""
    if field not in FIELDS:
        return
    current = out.get(field)
    if current is None or _RANK[candidate["provenance"]] < _RANK[current["provenance"]]:
        out[field] = candidate


def build(
    *,
    civitai_version: dict[str, Any] | None,
    card_settings: dict[str, dict[str, Any]] | None,
    family: str | None,
    existing_user: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}

    for field, entry in (existing_user or {}).items():
        if field in FIELDS:
            out[field] = _entry(entry.get("value"), "user", confidence=1.0)

    version = civitai_version or {}
    metas = [image["meta"] for image in version.get("images") or [] if image.get("meta")]
    for field, mode in meta_parse.mode_over(metas).items():
        _offer(out, field, _entry(mode["value"], "site:image-meta-mode",
                                  n=mode["n"], total=mode["total"]))

    words = [str(w).strip() for w in version.get("trainedWords") or [] if str(w).strip()]
    if words:
        _offer(out, "prompt_prefix", _entry(", ".join(words), "site:trainedWords"))

    for field, entry in (card_settings or {}).items():
        provenance = str(entry.get("provenance") or "card:prose-regex")
        if provenance in _RANK:
            _offer(out, field, _entry(entry.get("value"), provenance))

    variant = None
    base = str(version.get("baseModel") or "")
    name = f"{version.get('name') or ''} {base}".lower()
    if "turbo" in name:
        variant = "turbo"
    for field, value in family_seed_table.seed_for(family, variant).items():
        _offer(out, field, _entry(value, "table:family-default"))

    return out
```

- [ ] **Step 5: Run to verify it passes**

Run: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/test_model_intelligence_recommended.py -q`
Expected: PASS

- [ ] **Step 6: Prove the precedence bites**

Reverse two entries in `PROVENANCE_ORDER` so `table:family-default` outranks `site:image-meta-mode`. Re-run. Expected: `test_the_house_checkpoint_recommends_what_its_author_renders` FAILS with `52 != 10`. Revert; re-run: PASS. Record it — this is the wave's headline behaviour and the test must be seen to catch its inversion.

- [ ] **Step 7: Commit**

```bash
git add python/model_intelligence/family_seed_table.py python/model_intelligence/recommended.py tests/test_model_intelligence_recommended.py
git commit -m "feat(models): one recommended block, with provenance per field

user > site example-image mode > card snippet > card prose > family table.
The site's own examples outrank a generic card because they are what THIS
model's author renders with: the house checkpoint says 10 steps / CFG 1
across ten of ten examples while the family table says 52 / 3.5.
Confidence is agreement (n over total), and a field with no source is absent."
```

---

## Task 6: The sidecar

**Files:**
- Create: `python/model_intelligence/sidecar.py`
- Test: `tests/test_model_intelligence_sidecar.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `sidecar.SCHEMA: str` (`"spellvision.model-sidecar/1"`)
  - `sidecar.sidecar_path(weight: Path) -> Path`
  - `sidecar.read(weight: Path) -> dict | None`
  - `sidecar.write(weight: Path, payload: dict) -> Path` (atomic)
  - `sidecar.merge(existing: dict | None, fresh: dict) -> dict` — preserves anything `user_override`, preserves `_unknown_fields`
  - `sidecar.user_values(existing: dict | None) -> dict[str, dict]` — the `recommended` entries whose provenance is `user`, for feeding back into `recommended.build`
  - `sidecar.build_payload(...) -> dict`

- [ ] **Step 1: Write the failing test**

Create `tests/test_model_intelligence_sidecar.py`:

```python
"""The per-model sidecar.

Two properties matter more than the schema itself:

  1. A refresh must never silently discard what the USER set. If someone renamed a model or fixed
     its step count, a later metadata refresh that overwrote it would be a data-loss bug that
     looks like a feature working.
  2. An unknown field written by a NEWER version of SpellVision must survive a round-trip through
     an older one, or a rollback quietly strips data.
"""
from __future__ import annotations

import json
from pathlib import Path

from model_intelligence import sidecar


def _weight(tmp_path: Path) -> Path:
    path = tmp_path / "model.safetensors"
    path.write_bytes(b"weights")
    return path


def test_the_sidecar_sits_beside_the_weight(tmp_path: Path):
    assert sidecar.sidecar_path(_weight(tmp_path)).name == "model.spellvision.json"


def test_round_trip(tmp_path: Path):
    weight = _weight(tmp_path)
    payload = sidecar.build_payload(weight=weight, sha256="a" * 64, kind="checkpoint",
                                    family="krea2", civitai_version=None, hf=None,
                                    recommended={"steps": {"value": 10, "provenance": "user",
                                                           "confidence": 1.0, "n": None,
                                                           "total": None}})
    sidecar.write(weight, payload)
    loaded = sidecar.read(weight)
    assert loaded["schema"] == sidecar.SCHEMA
    assert loaded["identity"]["hashes"]["sha256"] == "a" * 64
    assert loaded["recommended"]["steps"]["value"] == 10


def test_reading_a_missing_sidecar_is_none(tmp_path: Path):
    assert sidecar.read(_weight(tmp_path)) is None


def test_reading_a_corrupt_sidecar_is_none_not_an_exception(tmp_path: Path):
    weight = _weight(tmp_path)
    sidecar.sidecar_path(weight).write_text("{ not json", encoding="utf-8")
    assert sidecar.read(weight) is None


def test_a_user_name_survives_a_refresh(tmp_path: Path):
    existing = {
        "schema": sidecar.SCHEMA,
        "display": {"name": {"value": "My Favourite Model", "user_override": True}},
        "recommended": {},
        "identity": {},
    }
    fresh = {
        "schema": sidecar.SCHEMA,
        "display": {"name": {"value": "Site Name", "user_override": False}},
        "recommended": {},
        "identity": {},
    }
    merged = sidecar.merge(existing, fresh)
    assert merged["display"]["name"]["value"] == "My Favourite Model"


def test_a_site_name_replaces_a_non_overridden_one(tmp_path: Path):
    existing = {"schema": sidecar.SCHEMA, "display": {"name": {"value": "old", "user_override": False}},
                "recommended": {}, "identity": {}}
    fresh = {"schema": sidecar.SCHEMA, "display": {"name": {"value": "new", "user_override": False}},
             "recommended": {}, "identity": {}}
    assert sidecar.merge(existing, fresh)["display"]["name"]["value"] == "new"


def test_a_user_setting_survives_a_refresh():
    existing = {"schema": sidecar.SCHEMA, "identity": {}, "display": {},
                "recommended": {"steps": {"value": 24, "provenance": "user", "confidence": 1.0}}}
    fresh = {"schema": sidecar.SCHEMA, "identity": {}, "display": {},
             "recommended": {"steps": {"value": 10, "provenance": "site:image-meta-mode",
                                       "confidence": 1.0}}}
    assert sidecar.merge(existing, fresh)["recommended"]["steps"]["value"] == 24


def test_user_values_extracts_only_user_entries():
    payload = {"recommended": {"steps": {"value": 24, "provenance": "user"},
                               "cfg": {"value": 1.0, "provenance": "site:image-meta-mode"}}}
    assert list(sidecar.user_values(payload)) == ["steps"]


def test_unknown_fields_survive_a_round_trip(tmp_path: Path):
    weight = _weight(tmp_path)
    sidecar.sidecar_path(weight).write_text(
        json.dumps({"schema": sidecar.SCHEMA, "identity": {}, "display": {}, "recommended": {},
                    "something_from_the_future": {"a": 1}}),
        encoding="utf-8",
    )
    existing = sidecar.read(weight)
    merged = sidecar.merge(existing, {"schema": sidecar.SCHEMA, "identity": {}, "display": {},
                                      "recommended": {}})
    sidecar.write(weight, merged)
    assert sidecar.read(weight)["something_from_the_future"] == {"a": 1}


def test_the_write_is_atomic_and_leaves_no_temp_file(tmp_path: Path):
    weight = _weight(tmp_path)
    sidecar.write(weight, sidecar.build_payload(weight=weight, sha256="b" * 64, kind="lora",
                                                family=None, civitai_version=None, hf=None,
                                                recommended={}))
    assert not list(tmp_path.glob("*.tmp"))
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/test_model_intelligence_sidecar.py -q`
Expected: FAIL — cannot import `sidecar`

- [ ] **Step 3: Write `python/model_intelligence/sidecar.py`**

```python
"""`<stem>.spellvision.json` -- what SpellVision knows about one weight.

Beside the weight rather than in a central database, for three reasons: it moves with the file,
it survives a reinstall, and the existing sidecar conventions (`<stem>.metadata.json`,
`<stem>.preview.png`) already live there, so a user who understands one understands this.

Two rules the merge exists to enforce:

  * anything the USER set is never overwritten by a refresh (`user_override: true` on a display
    field, `provenance: "user"` on a recommended one). A refresh that silently reverted a rename
    would be data loss wearing the costume of a working feature.
  * unknown top-level keys are preserved. A sidecar written by a newer build must survive a
    round-trip through an older one.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

SCHEMA = "spellvision.model-sidecar/1"
SUFFIX = ".spellvision.json"

_KNOWN_TOP_LEVEL = {"schema", "identity", "display", "recommended", "user"}


def sidecar_path(weight: str | Path) -> Path:
    path = Path(str(weight))
    return path.with_name(path.stem + SUFFIX)


def read(weight: str | Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(sidecar_path(weight).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def write(weight: str | Path, payload: dict[str, Any]) -> Path:
    target = sidecar_path(weight)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, target)
    return target


def user_values(existing: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """The recommended entries the user set, for feeding back into `recommended.build`."""
    out: dict[str, dict[str, Any]] = {}
    for field, entry in ((existing or {}).get("recommended") or {}).items():
        if isinstance(entry, dict) and entry.get("provenance") == "user":
            out[field] = entry
    return out


def merge(existing: dict[str, Any] | None, fresh: dict[str, Any]) -> dict[str, Any]:
    """Fresh data wins, except where the user has spoken."""
    if not existing:
        return dict(fresh)

    merged = dict(fresh)

    display = dict(fresh.get("display") or {})
    for field, entry in (existing.get("display") or {}).items():
        if isinstance(entry, dict) and entry.get("user_override"):
            display[field] = entry
        elif field not in display:
            display[field] = entry
    merged["display"] = display

    wanted = dict(fresh.get("recommended") or {})
    wanted.update(user_values(existing))
    merged["recommended"] = wanted

    if existing.get("user"):
        merged["user"] = existing["user"]

    for key, value in existing.items():
        if key not in _KNOWN_TOP_LEVEL and key not in merged:
            merged[key] = value

    return merged


def build_payload(
    *,
    weight: str | Path,
    sha256: str,
    kind: str,
    family: str | None,
    civitai_version: dict[str, Any] | None,
    hf: dict[str, Any] | None,
    recommended: dict[str, dict[str, Any]],
    images: list[dict[str, Any]] | None = None,
    fetched_at: str | None = None,
) -> dict[str, Any]:
    path = Path(str(weight))
    version = civitai_version or {}
    model = version.get("model") or {}
    card = hf or {}

    sources: list[dict[str, Any]] = []
    if version:
        sources.append({
            "site": "civitai",
            "model_id": version.get("modelId"),
            "version_id": version.get("id"),
            "url": f"https://civitai.com/models/{version.get('modelId')}"
                   f"?modelVersionId={version.get('id')}",
            "fetched_at": fetched_at,
        })
    if card.get("repo"):
        sources.append({"site": "huggingface", "repo": card.get("repo"),
                        "path": card.get("path"), "fetched_at": fetched_at})

    try:
        size = path.stat().st_size
    except OSError:
        size = None

    name = model.get("name") or path.stem
    trained = [str(w) for w in version.get("trainedWords") or []]

    return {
        "schema": SCHEMA,
        "identity": {
            "file_name": path.name,
            "size": size,
            "hashes": {"sha256": sha256, "autov2": (sha256 or "")[:10]},
            "kind": kind,
            "family": family,
            "base_model": version.get("baseModel") or card.get("base_model"),
            "quantisation": next(
                (str((f.get("metadata") or {}).get("fp") or "")
                 for f in version.get("files") or []
                 if (f.get("metadata") or {}).get("fp")),
                None,
            ) or None,
            "sources": sources,
        },
        "display": {
            "name": {"value": name, "user_override": False},
            "description_html": {"value": version.get("description") or "", "user_override": False},
            "creator": (version.get("creator") or {}).get("username")
                       if isinstance(version.get("creator"), dict) else None,
            "license": {
                "name": card.get("license") or card.get("license_name"),
                "allowCommercialUse": model.get("allowCommercialUse"),
                "allowDerivatives": model.get("allowDerivatives"),
                "allowNoCredit": model.get("allowNoCredit"),
            },
            "nsfw_level": version.get("nsfwLevel"),
            "trigger_words": {"value": trained, "user_override": False},
            "images": images or [],
        },
        "recommended": recommended,
        "user": {"notes": "", "favorite": False},
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/test_model_intelligence_sidecar.py -q`
Expected: PASS

- [ ] **Step 5: Prove the user-preservation bites**

Change `merge` to `wanted = dict(fresh.get("recommended") or {})` with the `wanted.update(user_values(existing))` line deleted, and drop the `user_override` branch in the display loop. Re-run. Expected: `test_a_user_name_survives_a_refresh` and `test_a_user_setting_survives_a_refresh` FAIL. Revert; re-run: PASS.

- [ ] **Step 6: Commit**

```bash
git add python/model_intelligence/sidecar.py tests/test_model_intelligence_sidecar.py
git commit -m "feat(models): the per-model sidecar, where a refresh cannot overwrite the user

Beside the weight so it moves with the file. Two properties the merge
exists for: anything the user set survives a refresh, and an unknown key
written by a newer build survives a round-trip through an older one."
```

---

## Task 7: Previews

**Files:**
- Create: `python/model_intelligence/previews.py`
- Test: `tests/test_model_intelligence_previews.py`

**Interfaces:**
- Produces:
  - `previews.preview_dir(models_root: Path, sha256: str) -> Path`
  - `previews.download_previews(version: dict, *, models_root: Path, sha256: str, weight: Path, opener=None, limit: int = 6, max_nsfw_level: int = 2) -> list[dict]`
  - `previews.set_user_picture(weight: Path, image: Path) -> Path`
  - `previews.cover_path(weight: Path) -> Path | None`

- [ ] **Step 1: Write the failing test**

Create `tests/test_model_intelligence_previews.py`:

```python
"""Preview pictures.

The rule that matters: a hand-placed picture is never clobbered. Users (and other tools) already
drop `<stem>.png` beside a weight, and a metadata refresh that overwrote it would destroy work
the app did not create. So the downloaded cover only lands when nothing is there, and a picture
the user explicitly chooses is marked so no later refresh touches it.
"""
from __future__ import annotations

import io
from pathlib import Path

from model_intelligence import previews

PNG = bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 64


class FakeResponse(io.BytesIO):
    status = 200


class FakeOpener:
    def __init__(self, body=PNG):
        self.body = body
        self.urls = []

    def open(self, request, timeout=None):
        self.urls.append(getattr(request, "full_url", str(request)))
        return FakeResponse(self.body)


def _weight(tmp_path: Path) -> Path:
    path = tmp_path / "model.safetensors"
    path.write_bytes(b"w")
    return path


def _version(count=3, level=1):
    return {"images": [{"url": f"https://image.civitai.com/x/{i}.jpeg", "width": 8, "height": 8,
                        "nsfwLevel": level, "meta": {"steps": 8}} for i in range(count)]}


def test_downloads_into_a_hash_scoped_folder(tmp_path: Path):
    weight = _weight(tmp_path)
    opener = FakeOpener()
    images = previews.download_previews(_version(2), models_root=tmp_path, sha256="a" * 64,
                                        weight=weight, opener=opener)
    assert len(images) == 2
    for entry in images:
        assert Path(entry["local_path"]).exists()
        assert "a" * 64 in entry["local_path"].replace("\\", "/")


def test_the_cover_is_written_when_nothing_is_there(tmp_path: Path):
    weight = _weight(tmp_path)
    previews.download_previews(_version(1), models_root=tmp_path, sha256="a" * 64,
                               weight=weight, opener=FakeOpener())
    assert (tmp_path / "model.preview.jpg").exists()


def test_a_hand_placed_picture_is_never_clobbered(tmp_path: Path):
    weight = _weight(tmp_path)
    hand = tmp_path / "model.png"
    hand.write_bytes(b"the user's own picture")
    previews.download_previews(_version(1), models_root=tmp_path, sha256="a" * 64,
                               weight=weight, opener=FakeOpener())
    assert hand.read_bytes() == b"the user's own picture"
    assert not (tmp_path / "model.preview.jpg").exists()


def test_mature_previews_are_skipped_below_the_threshold(tmp_path: Path):
    weight = _weight(tmp_path)
    images = previews.download_previews(_version(3, level=8), models_root=tmp_path,
                                        sha256="a" * 64, weight=weight, opener=FakeOpener(),
                                        max_nsfw_level=2)
    assert images == []


def test_the_limit_is_respected(tmp_path: Path):
    weight = _weight(tmp_path)
    images = previews.download_previews(_version(20), models_root=tmp_path, sha256="a" * 64,
                                        weight=weight, opener=FakeOpener(), limit=6)
    assert len(images) == 6


def test_set_user_picture_marks_the_override(tmp_path: Path):
    weight = _weight(tmp_path)
    mine = tmp_path / "mine.png"
    mine.write_bytes(PNG)
    written = previews.set_user_picture(weight, mine)
    assert written.exists()
    assert previews.cover_path(weight) == written


def test_a_download_failure_is_skipped_not_fatal(tmp_path: Path):
    class Broken:
        def open(self, request, timeout=None):
            raise OSError("no route to host")

    weight = _weight(tmp_path)
    assert previews.download_previews(_version(2), models_root=tmp_path, sha256="a" * 64,
                                      weight=weight, opener=Broken()) == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/test_model_intelligence_previews.py -q`
Expected: FAIL — cannot import `previews`

- [ ] **Step 3: Write `python/model_intelligence/previews.py`**

```python
"""Preview pictures for a weight.

Downloaded images live under `<models root>/.spellvision/previews/<sha256>/`, keyed by hash so a
renamed or moved file keeps its pictures. The COVER is the one the Models page shows, and it is
written to `<stem>.preview.jpg` only when the weight has no picture already: users and other
tools (Lora-Manager, Stability Matrix) drop `<stem>.png` beside a weight, and overwriting that
would destroy work the app did not create.

`set_user_picture` is the explicit path -- the user chose this image, so it becomes the cover and
the sidecar marks it `user_override` so no later refresh disturbs it.
"""
from __future__ import annotations

import urllib.request
from pathlib import Path
from typing import Any

USER_AGENT = "SpellVision/1.0"
COVER_SUFFIX = ".preview.jpg"
_EXISTING_PICTURE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".preview.png", ".preview.jpeg")


def preview_dir(models_root: str | Path, sha256: str) -> Path:
    return Path(str(models_root)) / ".spellvision" / "previews" / str(sha256)


def cover_path(weight: str | Path) -> Path | None:
    path = Path(str(weight))
    for suffix in (COVER_SUFFIX,) + _EXISTING_PICTURE_SUFFIXES:
        candidate = path.with_name(path.stem + suffix)
        if candidate.exists():
            return candidate
    return None


def _has_hand_placed_picture(weight: Path) -> bool:
    for suffix in _EXISTING_PICTURE_SUFFIXES:
        if weight.with_name(weight.stem + suffix).exists():
            return True
    return False


def download_previews(
    version: dict[str, Any] | None,
    *,
    models_root: str | Path,
    sha256: str,
    weight: str | Path,
    opener: Any = None,
    limit: int = 6,
    max_nsfw_level: int = 2,
    timeout: float = 25.0,
) -> list[dict[str, Any]]:
    """Fetch up to `limit` previews. A failure skips that image; it never aborts the refresh."""
    client = opener or urllib.request
    weight_path = Path(str(weight))
    target_dir = preview_dir(models_root, sha256)
    out: list[dict[str, Any]] = []

    candidates = [
        image
        for image in (version or {}).get("images") or []
        if isinstance(image, dict)
        and image.get("url")
        and int(image.get("nsfwLevel") or 1) <= int(max_nsfw_level)
    ][:limit]

    for index, image in enumerate(candidates):
        destination = target_dir / f"{index}.jpg"
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            request = urllib.request.Request(str(image["url"]), headers={"User-Agent": USER_AGENT})
            with client.open(request, timeout=timeout) as response:
                destination.write_bytes(response.read())
        except OSError:
            continue
        out.append({
            "origin_url": str(image["url"]),
            "local_path": str(destination),
            "width": image.get("width"),
            "height": image.get("height"),
            "nsfw_level": image.get("nsfwLevel"),
            "is_cover": not out,
            "user_override": False,
            "meta": image.get("meta") or {},
        })

    if out and not _has_hand_placed_picture(weight_path):
        cover = weight_path.with_name(weight_path.stem + COVER_SUFFIX)
        try:
            cover.write_bytes(Path(out[0]["local_path"]).read_bytes())
        except OSError:
            pass

    return out


def set_user_picture(weight: str | Path, image: str | Path) -> Path:
    """The user chose this picture. It becomes the cover, whatever else is there."""
    weight_path = Path(str(weight))
    cover = weight_path.with_name(weight_path.stem + COVER_SUFFIX)
    cover.write_bytes(Path(str(image)).read_bytes())
    return cover
```

- [ ] **Step 4: Run to verify it passes**

Run: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/test_model_intelligence_previews.py -q`
Expected: PASS

- [ ] **Step 5: Prove the clobber guard bites**

Delete the `and not _has_hand_placed_picture(weight_path)` condition. Re-run. Expected: `test_a_hand_placed_picture_is_never_clobbered` FAILS. Revert; re-run: PASS.

- [ ] **Step 6: Commit**

```bash
git add python/model_intelligence/previews.py tests/test_model_intelligence_previews.py
git commit -m "feat(models): preview pictures, without clobbering the user's own

Downloads land under .spellvision/previews/<sha256>/ so they survive a
rename. The cover is only written when the weight has no picture already:
other tools drop <stem>.png beside a weight and overwriting that would
destroy work the app did not create."
```

---

## Task 8: Refresh orchestration

**Files:**
- Create: `python/model_intelligence/refresh.py`
- Test: `tests/test_model_intelligence_refresh.py`

**Interfaces:**
- Consumes: every module above.
- Produces:
  - `refresh.plan(roots: Sequence[Path], *, extensions=hashing.MODEL_EXTENSIONS) -> list[Path]` — **smallest file first**
  - `refresh.RefreshJob(roots, *, client=None, hf=None, models_root=None, cache_path=None, progress=None, cancel=None)` with `.run() -> dict`
  - The result: `{"ok", "examined", "identified", "no_match", "skipped_unreadable", "errors", "roots"}`

- [ ] **Step 1: Write the failing test**

Create `tests/test_model_intelligence_refresh.py`:

```python
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

from pathlib import Path

import pytest

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
    for index in range(5):
        _write(tmp_path, f"w{index}.safetensors", 10 + index)
    calls = {"n": 0}

    def cancel():
        calls["n"] += 1
        return calls["n"] > 2

    result = refresh.RefreshJob([tmp_path], client=FakeClient({}), models_root=tmp_path,
                                cache_path=tmp_path / "cache.json", cancel=cancel).run()
    assert result["examined"] < 5
    assert result["ok"] is True
    assert (tmp_path / "cache.json").exists()


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
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/test_model_intelligence_refresh.py -q`
Expected: FAIL — cannot import `refresh`

- [ ] **Step 3: Write `python/model_intelligence/refresh.py`**

```python
"""Walk the model roots, identify everything, write the sidecars.

Sizing decides the shape. Measured 2026-09-16: 759 files / 2.09 TB, hashing at ~440 MB/s, so a
full first pass is about 79 minutes. That is long enough that the job must be cancellable, must
persist its hash cache as it goes, and must order SMALLEST FILE FIRST -- the 475 LoRAs are 130 GB
and land within minutes, so the library fills in visibly while the 937 GB of checkpoints grind.
Ordering by directory instead would leave the user staring at nothing for half an hour.

A root that cannot be read is reported by name. It is never allowed to contribute zero files to a
total, because a zero is indistinguishable from a successful scan of an empty folder.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any, Callable, Sequence

from . import hashing, previews, readable_roots, recommended, sidecar
from .civitai_lookup import CivitaiClient, CivitaiThrottled

try:  # the classifier is optional in unit tests
    from model_classification import classify_model
except Exception:  # pragma: no cover - exercised only when the worker package is absent
    classify_model = None  # type: ignore[assignment]


def plan(
    roots: Sequence[str | Path],
    *,
    extensions: frozenset[str] = hashing.MODEL_EXTENSIONS,
) -> list[Path]:
    """Every weight under the readable roots, smallest first."""
    found: list[tuple[int, Path]] = []
    for root in readable_roots.readable_models_roots(roots):
        for path in root.rglob("*"):
            if path.suffix.lower() not in extensions:
                continue
            try:
                if not path.is_file():
                    continue
                found.append((path.stat().st_size, path))
            except OSError:
                continue
    found.sort(key=lambda pair: (pair[0], str(pair[1]).lower()))
    return [path for _size, path in found]


class RefreshJob:
    def __init__(
        self,
        roots: Sequence[str | Path],
        *,
        client: Any = None,
        hf: Any = None,
        models_root: str | Path | None = None,
        cache_path: str | Path | None = None,
        progress: Callable[[int, int, str], None] | None = None,
        cancel: Callable[[], bool] | None = None,
        force: bool = False,
    ) -> None:
        self.roots = list(roots)
        self.client = client if client is not None else CivitaiClient()
        self.hf = hf
        self.models_root = Path(str(models_root)) if models_root else (
            Path(str(self.roots[0])) if self.roots else Path(".")
        )
        self.cache_path = Path(str(cache_path)) if cache_path else (
            self.models_root / ".spellvision" / "hash_index.json"
        )
        self.progress = progress
        self.cancel = cancel
        self.force = force

    def _kind_and_family(self, path: Path) -> tuple[str, str | None]:
        if classify_model is None:
            return "other", None
        try:
            result = classify_model(str(path))
        except Exception:
            return "other", None
        return getattr(result, "model_type", "other") or "other", getattr(result, "family", None)

    def run(self) -> dict[str, Any]:
        statuses = [readable_roots.root_status(root) for root in self.roots]
        skipped = [status["path"] for status in statuses if not status["readable"]]

        files = plan(self.roots)
        cache = hashing.HashCache(self.cache_path)
        total = len(files)
        examined = identified = no_match = 0
        errors: list[dict[str, str]] = []
        now = _dt.datetime.now(_dt.timezone.utc).isoformat()

        for path in files:
            if self.cancel is not None and self.cancel():
                break

            digest = None if self.force else cache.get(path)
            if digest is None:
                try:
                    digest = hashing.file_sha256(path, cancel=self.cancel)
                except OSError as exc:
                    errors.append({"path": str(path), "error": str(exc)})
                    examined += 1
                    continue
                if digest is None:  # cancelled mid-file
                    break
                cache.put(path, digest)

            version = None
            try:
                version = self.client.by_hash(digest)
            except CivitaiThrottled as exc:
                errors.append({"path": str(path), "error": f"throttled: {exc}"})
            except OSError as exc:
                errors.append({"path": str(path), "error": str(exc)})

            kind, family = self._kind_and_family(path)
            existing = sidecar.read(path)
            images = []
            if version:
                try:
                    images = previews.download_previews(
                        version, models_root=self.models_root, sha256=digest, weight=path
                    )
                except OSError as exc:
                    errors.append({"path": str(path), "error": f"previews: {exc}"})

            block = recommended.build(
                civitai_version=version,
                card_settings=None,
                family=family,
                existing_user=sidecar.user_values(existing),
            )
            payload = sidecar.build_payload(
                weight=path, sha256=digest, kind=kind, family=family,
                civitai_version=version, hf=None, recommended=block,
                images=images, fetched_at=now,
            )
            try:
                sidecar.write(path, sidecar.merge(existing, payload))
            except OSError as exc:
                errors.append({"path": str(path), "error": f"sidecar: {exc}"})

            examined += 1
            if version:
                identified += 1
            else:
                no_match += 1
            if self.progress is not None:
                self.progress(examined, total, path.name)
            if examined % 25 == 0:
                cache.save()

        cache.save()
        return {
            "ok": True,
            "examined": examined,
            "identified": identified,
            "no_match": no_match,
            "skipped_unreadable": skipped,
            "errors": errors,
            "roots": statuses,
            "total": total,
        }
```

- [ ] **Step 4: Run to verify it passes**

Run: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/test_model_intelligence_refresh.py -q`
Expected: PASS

- [ ] **Step 5: Prove the ordering bites**

Change `found.sort(...)` to `found.sort(key=lambda pair: str(pair[1]).lower())`. Re-run. Expected: `test_plan_orders_smallest_first` FAILS. Revert; re-run: PASS.

- [ ] **Step 6: Commit**

```bash
git add python/model_intelligence/refresh.py tests/test_model_intelligence_refresh.py
git commit -m "feat(models): refresh a whole library, smallest file first

759 files / 2.09 TB is ~79 minutes of hashing on this box, so the job is
cancellable, persists its cache as it goes, and does the 475 LoRAs (130 GB)
before the 130 checkpoints (937 GB) -- the library fills in visibly instead
of nothing happening for half an hour. A locked root is reported by name and
never contributes a zero, which would read as a successful empty scan."
```

---

## Task 9: Worker commands

**Files:**
- Create: `python/model_intelligence_commands.py`
- Modify: `python/worker_tcp.py` (dispatch), `python/worker_command_audience.py` (classification), `docs/SPELLVISION_WORKER_PROTOCOL.md` (entries), `ARCHITECTURE.md` (module table)
- Test: `tests/test_model_intelligence_commands.py`

**Interfaces:**
- Produces four commands. Every reply carries `ok` and `type`:
  - `model_intel_get` → `{"ok", "type": "model_intel", "path", "sidecar": dict|None, "recommended": dict}`
  - `model_intel_refresh` → `{"ok", "type": "model_intel_refresh", "examined", "identified", "no_match", "skipped_unreadable", "errors", "total"}`
  - `model_intel_set_user` → `{"ok", "type": "model_intel_set_user", "path", "changed": [str]}`
  - `model_recommended_settings` → `{"ok", "type": "model_recommended_settings", "path", "family", "settings": dict, "warnings": [str]}`

- [ ] **Step 1: Write the failing test**

Create `tests/test_model_intelligence_commands.py`:

```python
"""The four model-intelligence commands over the real TCP protocol.

Nothing here touches the network: `model_intel_get` and `model_recommended_settings` read a
sidecar off disk, and `model_intel_refresh` is asked for a directory with no weights in it so it
returns an empty, honest result rather than doing 79 minutes of work in CI.
"""
from __future__ import annotations

import json
from pathlib import Path


def _first(messages, msg_type):
    for message in messages:
        if message.get("type") == msg_type:
            return message
    raise AssertionError(f"no {msg_type!r} in {[m.get('type') for m in messages]}")


def test_model_intel_get_on_an_unknown_path_is_honest(worker_client, tmp_path):
    reply = _first(
        worker_client({"command": "model_intel_get", "path": str(tmp_path / "nope.safetensors")}),
        "model_intel",
    )
    assert reply["ok"] is True
    assert reply["sidecar"] is None
    assert reply["recommended"] == {}


def test_model_intel_get_reads_a_sidecar(worker_client, tmp_path):
    weight = tmp_path / "w.safetensors"
    weight.write_bytes(b"w")
    (tmp_path / "w.spellvision.json").write_text(
        json.dumps({
            "schema": "spellvision.model-sidecar/1",
            "identity": {"kind": "checkpoint", "family": "krea2"},
            "display": {"name": {"value": "A Model", "user_override": False}},
            "recommended": {"steps": {"value": 10, "provenance": "site:image-meta-mode",
                                      "confidence": 1.0, "n": 10, "total": 10}},
        }),
        encoding="utf-8",
    )
    reply = _first(worker_client({"command": "model_intel_get", "path": str(weight)}), "model_intel")
    assert reply["sidecar"]["display"]["name"]["value"] == "A Model"
    assert reply["recommended"]["steps"]["value"] == 10


def test_model_recommended_settings_falls_back_to_the_family(worker_client, tmp_path):
    weight = tmp_path / "unknown.safetensors"
    weight.write_bytes(b"w")
    reply = _first(
        worker_client({"command": "model_recommended_settings", "path": str(weight),
                       "family": "krea2"}),
        "model_recommended_settings",
    )
    assert reply["ok"] is True
    assert reply["settings"]["steps"]["provenance"] == "table:family-default"


def test_model_recommended_settings_prefers_the_sidecar(worker_client, tmp_path):
    weight = tmp_path / "w.safetensors"
    weight.write_bytes(b"w")
    (tmp_path / "w.spellvision.json").write_text(
        json.dumps({
            "schema": "spellvision.model-sidecar/1",
            "identity": {"kind": "checkpoint", "family": "krea2"},
            "display": {},
            "recommended": {"steps": {"value": 10, "provenance": "site:image-meta-mode",
                                      "confidence": 1.0, "n": 10, "total": 10}},
        }),
        encoding="utf-8",
    )
    reply = _first(
        worker_client({"command": "model_recommended_settings", "path": str(weight),
                       "family": "krea2"}),
        "model_recommended_settings",
    )
    assert reply["settings"]["steps"]["value"] == 10
    assert reply["settings"]["steps"]["provenance"] == "site:image-meta-mode"


def test_model_intel_set_user_writes_a_name_that_a_refresh_would_keep(worker_client, tmp_path):
    weight = tmp_path / "w.safetensors"
    weight.write_bytes(b"w")
    reply = _first(
        worker_client({"command": "model_intel_set_user", "path": str(weight),
                       "name": "My Favourite"}),
        "model_intel_set_user",
    )
    assert reply["ok"] is True
    assert "name" in reply["changed"]
    stored = json.loads((tmp_path / "w.spellvision.json").read_text(encoding="utf-8"))
    assert stored["display"]["name"]["value"] == "My Favourite"
    assert stored["display"]["name"]["user_override"] is True


def test_model_intel_refresh_on_an_empty_directory_reports_zero_honestly(worker_client, tmp_path):
    reply = _first(
        worker_client({"command": "model_intel_refresh", "roots": [str(tmp_path)]}, timeout=60),
        "model_intel_refresh",
    )
    assert reply["ok"] is True
    assert reply["examined"] == 0
    assert reply["skipped_unreadable"] == []


def test_model_intel_refresh_names_an_unreadable_root(worker_client, tmp_path):
    missing = tmp_path / "not-here"
    reply = _first(
        worker_client({"command": "model_intel_refresh", "roots": [str(missing)]}, timeout=60),
        "model_intel_refresh",
    )
    assert reply["skipped_unreadable"] == [str(missing)]


def test_a_path_outside_the_model_roots_is_refused(worker_client, tmp_path):
    reply = _first(
        worker_client({"command": "model_intel_set_user", "path": "C:/Windows/System32/cmd.exe",
                       "name": "nope"}),
        "model_intel_set_user",
    )
    assert reply["ok"] is False
    assert "not a model file" in reply.get("error", "").lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/test_model_intelligence_commands.py -q`
Expected: FAIL — the worker replies with an unknown-command error

- [ ] **Step 3: Write `python/model_intelligence_commands.py`**

```python
"""Worker commands for model intelligence.

Four commands, each a thin adapter over `model_intelligence`: read what we know about one weight,
refresh a library, record a user override, and resolve the settings a model wants (which is what
W2's generation pages ask for on every checkpoint change).

`model_intel_refresh` can run for the better part of an hour on a full library, so it accepts a
`roots` subset and reports progress through the emitter rather than only at the end.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from model_intelligence import (
    family_seed_table,
    hashing,
    previews,
    readable_roots,
    recommended,
    sidecar,
)
from model_intelligence.civitai_lookup import DEFAULT_HOST, CivitaiClient
from model_intelligence.refresh import RefreshJob


def _weight_path(req: dict[str, Any]) -> Path | None:
    text = str(req.get("path") or "").strip()
    if not text:
        return None
    path = Path(text)
    if path.suffix.lower() not in hashing.MODEL_EXTENSIONS:
        return None
    return path


def handle_model_intel_get_command(req: dict[str, Any]) -> dict[str, Any]:
    path = _weight_path(req)
    if path is None:
        return {"ok": False, "type": "model_intel", "error": "path is not a model file"}
    payload = sidecar.read(path)
    return {
        "ok": True,
        "type": "model_intel",
        "path": str(path),
        "sidecar": payload,
        "recommended": (payload or {}).get("recommended") or {},
    }


def handle_model_recommended_settings_command(req: dict[str, Any]) -> dict[str, Any]:
    path = _weight_path(req)
    family = str(req.get("family") or "").strip() or None
    warnings: list[str] = []

    payload = sidecar.read(path) if path is not None else None
    if payload:
        settings = dict(payload.get("recommended") or {})
        family = family or ((payload.get("identity") or {}).get("family"))
    else:
        settings = {}
        if path is not None:
            warnings.append("no sidecar yet; run model_intel_refresh to identify this model")

    if family:
        variant = "turbo" if "turbo" in str(path or "").lower() else None
        for field, value in family_seed_table.seed_for(family, variant).items():
            settings.setdefault(field, {
                "value": value, "provenance": "table:family-default",
                "confidence": 1.0, "n": None, "total": None,
            })

    return {
        "ok": True,
        "type": "model_recommended_settings",
        "path": str(path) if path else "",
        "family": family,
        "settings": settings,
        "warnings": warnings,
    }


def handle_model_intel_set_user_command(req: dict[str, Any]) -> dict[str, Any]:
    path = _weight_path(req)
    if path is None:
        return {"ok": False, "type": "model_intel_set_user", "error": "path is not a model file"}

    payload = sidecar.read(path) or {
        "schema": sidecar.SCHEMA, "identity": {}, "display": {}, "recommended": {},
        "user": {"notes": "", "favorite": False},
    }
    display = dict(payload.get("display") or {})
    changed: list[str] = []

    name = str(req.get("name") or "").strip()
    if name:
        display["name"] = {"value": name, "user_override": True}
        changed.append("name")

    picture = str(req.get("picture") or "").strip()
    if picture:
        try:
            previews.set_user_picture(path, picture)
        except OSError as exc:
            return {"ok": False, "type": "model_intel_set_user", "error": str(exc)}
        images = list(display.get("images") or [])
        if images:
            images[0] = {**images[0], "user_override": True}
        display["images"] = images
        changed.append("picture")

    notes = req.get("notes")
    if isinstance(notes, str):
        payload["user"] = {**(payload.get("user") or {}), "notes": notes}
        changed.append("notes")

    settings = req.get("settings")
    if isinstance(settings, dict):
        wanted = dict(payload.get("recommended") or {})
        for field, value in settings.items():
            if field in recommended.FIELDS:
                wanted[field] = {"value": value, "provenance": "user", "confidence": 1.0,
                                 "n": None, "total": None}
                changed.append(f"settings.{field}")
        payload["recommended"] = wanted

    payload["display"] = display
    try:
        sidecar.write(path, payload)
    except OSError as exc:
        return {"ok": False, "type": "model_intel_set_user", "error": str(exc)}

    return {"ok": True, "type": "model_intel_set_user", "path": str(path), "changed": changed}


def handle_model_intel_refresh_command(req: dict[str, Any], emitter: Any = None) -> dict[str, Any]:
    roots = [str(r) for r in (req.get("roots") or []) if str(r).strip()]
    if not roots:
        return {"ok": False, "type": "model_intel_refresh", "error": "roots is required"}

    host = str(req.get("civitai_host") or DEFAULT_HOST)
    api_key = req.get("civitai_api_key")
    if not api_key:
        try:
            from credential_store import get_credential

            api_key = get_credential("civitai_api_key")
        except Exception:
            api_key = None

    def progress(done: int, total: int, name: str) -> None:
        if emitter is not None:
            emitter.emit({
                "ok": True, "type": "model_intel_progress",
                "current": done, "total": total, "message": name,
                "percent": int(100 * done / total) if total else 0,
            })

    job = RefreshJob(
        roots,
        client=CivitaiClient(host=host, api_key=api_key),
        models_root=req.get("models_root") or roots[0],
        progress=progress,
        force=bool(req.get("force")),
    )
    result = job.run()
    result["type"] = "model_intel_refresh"
    return result


def handle_model_roots_status_command(req: dict[str, Any]) -> dict[str, Any]:
    roots = [str(r) for r in (req.get("roots") or []) if str(r).strip()]
    return {
        "ok": True,
        "type": "model_roots_status",
        "roots": [readable_roots.root_status(root) for root in roots],
    }
```

- [ ] **Step 4: Register the commands in `python/worker_tcp.py`**

Find the `classify_models` branch (around line 699) and add immediately after it, matching the surrounding style exactly:

```python
        if command in {
            "model_intel_get",
            "model_intel_refresh",
            "model_intel_set_user",
            "model_recommended_settings",
            "model_roots_status",
        }:
            import model_intelligence_commands as mic

            if command == "model_intel_refresh":
                emitter.emit(mic.handle_model_intel_refresh_command(req, emitter))
            elif command == "model_intel_get":
                emitter.emit(mic.handle_model_intel_get_command(req))
            elif command == "model_intel_set_user":
                emitter.emit(mic.handle_model_intel_set_user_command(req))
            elif command == "model_recommended_settings":
                emitter.emit(mic.handle_model_recommended_settings_command(req))
            else:
                emitter.emit(mic.handle_model_roots_status_command(req))
            return
```

- [ ] **Step 5: Classify them in `python/worker_command_audience.py`**

`model_intel_get`, `model_intel_refresh`, `model_intel_set_user` and `model_recommended_settings` are **not** USER_FACING yet — the ratchet requires a command literal in `qt_ui/` for anything listed there, and no UI reaches them until W2 and W5. Add all five to `DIAGNOSTIC` with a comment, and move them to `USER_FACING` in the wave that wires them:

```python
    # Model intelligence (W1). DIAGNOSTIC until W2 wires model_recommended_settings into the
    # cockpit and W5 wires the rest into the Models page -- the audience ratchet requires a
    # qt_ui/ literal for anything called USER_FACING, and promoting these early would assert a
    # route that does not exist yet.
    "model_intel_get", "model_intel_refresh", "model_intel_set_user",
    "model_recommended_settings", "model_roots_status",
```

- [ ] **Step 6: Document them in `docs/SPELLVISION_WORKER_PROTOCOL.md`**

Add one entry per command in the existing format (copy the shape of the `classify_models` entry verbatim, including the request/response example blocks). Then run the protocol-doc test and fix the counts it reports:

Run: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/test_protocol_doc.py -q`

- [ ] **Step 7: Add the module row to `ARCHITECTURE.md`**

In the Python module table, add:

```markdown
| `model_intelligence/` | Who a weight is according to the site hosting it: hash, CivitAI/HF lookup, sidecar, previews, recommended settings. |
| `model_intelligence_commands.py` | The five worker commands over that package. |
```

Run: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/test_governing_docs.py -q`

- [ ] **Step 8: Run the command tests**

Run: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/test_model_intelligence_commands.py -q`
Expected: PASS

- [ ] **Step 9: Run every ratchet**

Run: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest -m ratchet -q`
Expected: PASS, with the sweep total unchanged at 229 across 31 rules (23 at zero). If `every-module-is-reachable` fires on a new module, the fix is to make it reachable — never to baseline it.

- [ ] **Step 10: Commit**

```bash
git add python/model_intelligence_commands.py python/worker_tcp.py python/worker_command_audience.py docs/SPELLVISION_WORKER_PROTOCOL.md ARCHITECTURE.md tests/test_model_intelligence_commands.py
git commit -m "feat(worker): five model-intelligence commands

get / refresh / set_user / recommended_settings / roots_status. Filed
DIAGNOSTIC rather than USER_FACING on purpose: the audience ratchet wants
a qt_ui literal for a user-facing command, and nothing reaches these until
W2 wires recommended_settings into the cockpit and W5 wires the rest into
the Models page. Promoting them now would assert a route that does not exist."
```

---

## Task 10: Placement and the post-download hook

**Files:**
- Create: `python/model_intelligence/placement.py`
- Modify: `python/download_manager.py` (success branch), `python/download_commands.py` (pass the models root through)
- Test: `tests/test_model_intelligence_placement.py`

**Interfaces:**
- Produces:
  - `placement.subdir_for(path: Path, *, kind: str | None = None) -> str`
  - `placement.place(source: Path, models_root: Path, *, kind: str | None = None, move: bool = True) -> Path`

**Why:** today a weight downloaded from the Models page lands in the asset cache (`python/.cache/assets/...`) and never appears in the library. A model the Models page cannot see is not, from the user's point of view, downloaded.

- [ ] **Step 1: Write the failing test**

Create `tests/test_model_intelligence_placement.py`:

```python
"""Where a downloaded weight belongs.

Today a download from the Models page lands in the asset cache and the library never shows it.
The mapping below mirrors ModelManagerPage::destSubdirForWeight so the C++ drop path and the
Python download path put the same file in the same place -- two resolvers for one question is the
defect Doc 50 rule 5 is about.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from model_intelligence import placement


@pytest.mark.parametrize(
    "name,kind,expected",
    [
        ("anything.safetensors", "checkpoint", "checkpoints"),
        ("anything.safetensors", "lora", "loras"),
        ("anything.safetensors", "vae", "vae"),
        ("anything.safetensors", "text_encoder", "text_encoders"),
        ("anything.safetensors", "clip_vision", "clip_vision"),
        ("anything.safetensors", "embedding", "embeddings"),
        ("anything.safetensors", "upscaler", "upscale_models"),
        ("anything.safetensors", "controlnet", "controlnet"),
        ("anything.safetensors", "diffusion_model", "diffusion_models"),
        ("mystery.safetensors", None, "checkpoints"),
        ("some_lora_v1.safetensors", None, "loras"),
        ("sdxl_vae.safetensors", None, "vae"),
        ("4x-UltraSharp.pth", None, "upscale_models"),
    ],
)
def test_subdir_for(name, kind, expected):
    assert placement.subdir_for(Path(name), kind=kind) == expected


def test_place_moves_the_file_into_the_library(tmp_path: Path):
    cache = tmp_path / "cache"
    cache.mkdir()
    source = cache / "w.safetensors"
    source.write_bytes(b"weights")
    root = tmp_path / "models"
    landed = placement.place(source, root, kind="lora")
    assert landed == root / "loras" / "w.safetensors"
    assert landed.read_bytes() == b"weights"
    assert not source.exists()


def test_place_can_copy_instead_of_moving(tmp_path: Path):
    source = tmp_path / "w.safetensors"
    source.write_bytes(b"weights")
    landed = placement.place(source, tmp_path / "models", kind="lora", move=False)
    assert landed.exists()
    assert source.exists()


def test_place_never_overwrites_an_existing_weight(tmp_path: Path):
    root = tmp_path / "models"
    (root / "loras").mkdir(parents=True)
    (root / "loras" / "w.safetensors").write_bytes(b"the one already there")
    source = tmp_path / "w.safetensors"
    source.write_bytes(b"the new one")
    landed = placement.place(source, root, kind="lora")
    assert (root / "loras" / "w.safetensors").read_bytes() == b"the one already there"
    assert landed.name != "w.safetensors"
    assert landed.read_bytes() == b"the new one"
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/test_model_intelligence_placement.py -q`
Expected: FAIL — cannot import `placement`

- [ ] **Step 3: Write `python/model_intelligence/placement.py`**

```python
"""Which models subdirectory a weight belongs in.

This mirrors `ModelManagerPage::destSubdirForWeight` deliberately: the C++ drag-and-drop path and
the Python download path answer the same question, and two resolvers that can disagree about where
a file goes is the defect Doc 50 rule 5 names. The classifier's kind wins when it has one; the
filename heuristic is the fallback for a file nothing has classified yet.

Nothing here overwrites. A name collision gets a suffix, because the file already on disk may be
the one the user is currently rendering with.
"""
from __future__ import annotations

import shutil
from pathlib import Path

KIND_SUBDIRS: dict[str, str] = {
    "checkpoint": "checkpoints",
    "diffusion_model": "diffusion_models",
    "lora": "loras",
    "vae": "vae",
    "text_encoder": "text_encoders",
    "clip_vision": "clip_vision",
    "embedding": "embeddings",
    "upscaler": "upscale_models",
    "controlnet": "controlnet",
    "style_model": "style_models",
}

_NAME_HINTS: tuple[tuple[str, str], ...] = (
    ("lora", "loras"),
    ("lycoris", "loras"),
    ("controlnet", "controlnet"),
    ("clip_vision", "clip_vision"),
    ("clipvision", "clip_vision"),
    ("text_encoder", "text_encoders"),
    ("t5xxl", "text_encoders"),
    ("umt5", "text_encoders"),
    ("clip_l", "text_encoders"),
    ("vae", "vae"),
    ("upscal", "upscale_models"),
    ("esrgan", "upscale_models"),
    ("embedding", "embeddings"),
    ("unet", "diffusion_models"),
)

_UPSCALE_EXTENSIONS = {".pth"}


def subdir_for(path: str | Path, *, kind: str | None = None) -> str:
    """The models subdirectory for this weight. Defaults to checkpoints, never to the root."""
    mapped = KIND_SUBDIRS.get(str(kind or "").strip().lower())
    if mapped:
        return mapped
    name = Path(str(path)).name.lower()
    for needle, subdir in _NAME_HINTS:
        if needle in name:
            return subdir
    if Path(str(path)).suffix.lower() in _UPSCALE_EXTENSIONS:
        return "upscale_models"
    return "checkpoints"


def place(
    source: str | Path,
    models_root: str | Path,
    *,
    kind: str | None = None,
    move: bool = True,
) -> Path:
    """Put a downloaded weight where the library can see it. Never overwrites."""
    src = Path(str(source))
    target_dir = Path(str(models_root)) / subdir_for(src, kind=kind)
    target_dir.mkdir(parents=True, exist_ok=True)

    target = target_dir / src.name
    if target.exists():
        stem, suffix = src.stem, src.suffix
        index = 1
        while target.exists():
            target = target_dir / f"{stem}_{index}{suffix}"
            index += 1

    if move:
        shutil.move(str(src), str(target))
    else:
        shutil.copy2(str(src), str(target))
    return target
```

- [ ] **Step 4: Run to verify it passes**

Run: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/test_model_intelligence_placement.py -q`
Expected: PASS

- [ ] **Step 5: Wire the hook into the download success branch**

In `python/download_manager.py`, in `_run`'s success branch (around line 350, where `local_path` and `cache_hit` are recorded), add placement + refresh **guarded so a failure never fails the download**:

```python
            placed_path = local_path
            if local_path and req.get("models_root"):
                try:
                    from model_intelligence import placement, refresh as mi_refresh
                    from model_intelligence.civitai_lookup import CivitaiClient

                    placed_path = str(
                        placement.place(local_path, req["models_root"], kind=req.get("model_kind"))
                    )
                    mi_refresh.RefreshJob(
                        [str(Path(placed_path).parent)],
                        client=CivitaiClient(api_key=req.get("civitai_api_key")),
                        models_root=req["models_root"],
                    ).run()
                except Exception as exc:  # placement is a convenience, never a download failure
                    log.warning("post-download placement failed for %s: %s", local_path, exc)
```

and record `placed_path` alongside `local_path` in the item state. **The `log.warning` level is deliberate** — `logging.info` is invisible under this repo's root logger.

- [ ] **Step 6: Run the download tests**

Run: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/test_download_manager.py tests/test_download_commands_live.py -q`
Expected: PASS (existing behaviour is unchanged when `models_root` is absent)

- [ ] **Step 7: Commit**

```bash
git add python/model_intelligence/placement.py python/download_manager.py python/download_commands.py tests/test_model_intelligence_placement.py
git commit -m "feat(models): a downloaded weight lands where the library can see it

Downloads stopped in the asset cache, so the Models page never showed them:
from the user's point of view the model was not downloaded. Placement mirrors
destSubdirForWeight so the C++ drop and the Python download agree, never
overwrites a weight already on disk, and a placement failure warns rather
than failing the download."
```

---

## Task 11: `kind` on the classifier, and the live proof

**Files:**
- Modify: `python/worker_service.py:997-1023` (`handle_classify_models_command` — add `kind` to each result)
- Create: `scripts/dev/refresh_model_intelligence.py`
- Test: `tests/test_model_intelligence_kind.py`
- Modify: `docs/design/55_t7_ship_walkthrough.html` (T3 section — the live proof)

**Interfaces:**
- `classify_models` results gain `"kind"`, one of the ten-value vocabulary (spec R1.2).

- [ ] **Step 1: Write the failing test**

Create `tests/test_model_intelligence_kind.py`:

```python
"""`classify_models` reports a kind the Models page can put in a tab.

The page currently guesses type from path substrings in C++ while the worker has a real
classifier, so the family shown can disagree with the family routed on. This closes half of that
(the kind); W5 makes the page consume it.
"""
from __future__ import annotations

KINDS = {
    "checkpoint", "diffusion_model", "lora", "vae", "text_encoder", "clip_vision",
    "embedding", "upscaler", "controlnet", "style_model", "other",
}


def _first(messages, msg_type):
    for message in messages:
        if message.get("type") == msg_type:
            return message
    raise AssertionError(f"no {msg_type!r} in {[m.get('type') for m in messages]}")


def test_classify_models_reports_a_kind_from_the_vocabulary(worker_client):
    reply = _first(
        worker_client({
            "command": "classify_models",
            "paths": [
                "D:/AI_ASSETS/models/checkpoints/sdxl/foo.safetensors",
                "D:/AI_ASSETS/models/loras/bar.safetensors",
                "D:/AI_ASSETS/models/vae/baz.safetensors",
                "D:/AI_ASSETS/models/clip_vision/qux.safetensors",
            ],
        }),
        "classify_models",
    )
    assert reply["ok"] is True
    kinds = [row["kind"] for row in reply["results"]]
    assert kinds == ["checkpoint", "lora", "vae", "clip_vision"]
    assert set(kinds) <= KINDS


def test_an_unclassifiable_path_is_other_not_a_guess(worker_client):
    reply = _first(
        worker_client({"command": "classify_models", "paths": ["C:/somewhere/mystery.bin"]}),
        "classify_models",
    )
    assert reply["results"][0]["kind"] in KINDS
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/test_model_intelligence_kind.py -q`
Expected: FAIL — `KeyError: 'kind'`

- [ ] **Step 3: Add `kind` to the classify handler**

In `python/worker_service.py`, in `handle_classify_models_command`, add to each result dict:

```python
                "kind": _KIND_VOCABULARY.get(
                    getattr(classification, "model_type", "") or "", "other"
                ),
```

and define the map near the top of that function's module section:

```python
# The ten kinds the Models page tabs are built from (spec R1.2). This is the classifier's own
# _L1_TYPE_CATEGORY vocabulary plus "other" -- a path that classifies as nothing gets "other"
# rather than being filed under checkpoints, because a wrong tab is worse than an honest one.
_KIND_VOCABULARY: dict[str, str] = {
    "checkpoint": "checkpoint",
    "diffusion_model": "diffusion_model",
    "lora": "lora",
    "vae": "vae",
    "text_encoder": "text_encoder",
    "clip_vision": "clip_vision",
    "embedding": "embedding",
    "upscaler": "upscaler",
    "controlnet": "controlnet",
    "style_model": "style_model",
    "video_stack": "other",
    "unknown": "other",
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/test_model_intelligence_kind.py -q`
Expected: PASS

- [ ] **Step 5: Write the live refresh script**

Create `scripts/dev/refresh_model_intelligence.py`:

```python
"""Run a real model-intelligence refresh over the live libraries and print a report.

This is the wave's live proof. It is a script rather than a test because the full pass is about
79 minutes on this box (759 files, 2.09 TB) -- far past any suite's budget -- and because the
result worth keeping is a table the walkthrough can quote, not a green tick.

    python scripts/dev/refresh_model_intelligence.py --roots D:/AI_ASSETS/models F:/AI_ASSETS/models
    python scripts/dev/refresh_model_intelligence.py --roots F:/AI_ASSETS/models --limit 40
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))

from credential_store import get_credential  # noqa: E402
from model_intelligence import readable_roots, refresh, sidecar  # noqa: E402
from model_intelligence.civitai_lookup import CivitaiClient  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--roots", nargs="+", required=True)
    parser.add_argument("--limit", type=int, default=0, help="stop after N files (0 = all)")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    for status in (readable_roots.root_status(root) for root in args.roots):
        print(f"root {status['path']}: "
              f"{'readable' if status['readable'] else 'SKIPPED (' + status['reason'] + ')'}")

    started = time.time()
    seen = {"n": 0}

    def progress(done: int, total: int, name: str) -> None:
        seen["n"] = done
        if done % 10 == 0 or done == total:
            rate = done / max(time.time() - started, 0.001)
            print(f"  {done}/{total}  {rate:.1f} files/s  {name}")

    job = refresh.RefreshJob(
        args.roots,
        client=CivitaiClient(api_key=get_credential("civitai_api_key")),
        models_root=args.roots[0],
        progress=progress,
        cancel=(lambda: args.limit and seen["n"] >= args.limit) if args.limit else None,
        force=args.force,
    )
    result = job.run()
    elapsed = time.time() - started

    print(json.dumps({k: v for k, v in result.items() if k != "roots"}, indent=1)[:2000])
    print(f"\nelapsed {elapsed / 60:.1f} min")

    identified = []
    for root in args.roots:
        for path in Path(root).rglob("*.spellvision.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            rec = payload.get("recommended") or {}
            steps = (rec.get("steps") or {})
            if steps.get("provenance") == "site:image-meta-mode":
                identified.append((path.stem.replace(".spellvision", ""),
                                   steps.get("value"), steps.get("n"),
                                   (rec.get("cfg") or {}).get("value"),
                                   (rec.get("sampler") or {}).get("value")))
    print(f"\n{len(identified)} models carry site-sourced settings:")
    for name, steps, n, cfg, sampler in sorted(identified)[:40]:
        print(f"  {name[:48]:48} steps={steps} (n={n}) cfg={cfg} sampler={sampler}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Run it for real on the F: root**

Run: `PYTHONPATH="" PYTHONUTF8=1 ./.venv/Scripts/python.exe scripts/dev/refresh_model_intelligence.py --roots F:/AI_ASSETS/models`
Expected: 35 files examined; the three Krea2 LoRAs and the house checkpoint identified; a table of site-sourced settings printed. Capture the output.

- [ ] **Step 7: Run the whole suite**

```bash
PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest -q
PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest -m ratchet -q
```
Expected: green, with the pre-existing counts unchanged except for the new tests.

- [ ] **Step 8: Write the live proof into the walkthrough**

In `docs/design/55_t7_ship_walkthrough.html`, under the **T3** section, add a row recording: the date, the roots and their readability, files examined, identified vs no-match, elapsed time, and — the headline — the table showing the house checkpoint's site-published settings next to what SpellVision renders today. State plainly that W1 only *stores* this; the cockpit does not use it until W2.

- [ ] **Step 9: Commit**

```bash
git add python/worker_service.py scripts/dev/refresh_model_intelligence.py tests/test_model_intelligence_kind.py docs/design/55_t7_ship_walkthrough.html
git commit -m "feat(models): classify_models reports a kind, and W1 proves itself on the live library

The ten-kind vocabulary the Models page tabs will use; an unclassifiable
path is 'other' rather than filed under checkpoints, because a wrong tab is
worse than an honest one. The refresh script is the wave's live proof: a
full pass is ~79 minutes, too long for any suite, and what is worth keeping
is the table, not a green tick."
```

---

## Self-Review

**Spec coverage (§1 of the design):**

| Spec item | Task |
|---|---|
| `hashing.py` | 1 |
| `readable_roots` / Python twin of `scannableModelsRoots` | 1 |
| `civitai_lookup.py` | 3 |
| `hf_lookup.py` | 4 |
| `recommended.py` | 5 |
| `family_seed_table.py` | 5 |
| `sidecar.py` | 6 |
| `previews.py` (incl. `set_user_picture`) | 7 |
| `refresh.py` (queue-visible progress) | 8 |
| Worker commands + three ratchets | 9 |
| Post-download hook (R1.1) + `placement.py` | 10 |
| Kind vocabulary (R1.2) on `classify_models` | 11 |
| Settings: Civitai host, mature previews | 3 (host allowlist), 7 (`max_nsfw_level`); the **Prefs UI** for both is W5, noted below |
| Live proof (R0.4) | 11 |

**Deliberately deferred, and where to:**
- The **Prefs toggles** for Civitai host and mature previews are W5 (Models page UI wave). W1 exposes both as command parameters with safe defaults, so nothing is blocked.
- `meta_parse` splits the sampler but `hf_lookup.settings_from_readme` is only wired into `recommended.build` through the `card_settings` argument; **`refresh.py` passes `card_settings=None`** because HF identification needs the sha256 index, which needs a repo list W1 does not build. This is stated in `refresh.py`'s call site and is a W5 follow-up, not an oversight.

**Type consistency check:** `recommended.build` is called with keyword arguments in Task 8 and Task 9 exactly as defined in Task 5. `sidecar.build_payload` keywords match between Tasks 6, 8. `previews.download_previews` keywords match between Tasks 7 and 8. `hashing.file_sha256(path, chunk=…, cancel=…)` matches between Tasks 1 and 8. `RefreshJob(...)` keywords match between Tasks 8, 9 and 11.

**Placeholder scan:** none. Every code step carries real code; every test step carries real assertions against real captured fixtures.
