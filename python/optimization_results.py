"""The ledger an optimization measurement is recorded in, and the rules a row is held to.

This project published one A/B: SageAttention 120.72 s against SDPA 124.01 s, about 3%. Three
things have since come out of this box, and each is a rule below.

1. ``runtime/state/job_archive.json`` holds a THIRD arm nobody mentioned --
   ``t4_sage_queue_3d2236390c95`` at **159.27 s**, same seed, same steps, same size, fifteen
   minutes before the quoted sage run. So the real numbers are 159.27 / 120.72 / 124.01 and the
   published gap is smaller than the variance between two runs of the SAME arm. Hence ``seconds``
   is a list and a row with one timing is recorded but never compared.
2. The arms were distinguishable only because a human typed ``t4_sage`` and ``t4_sdpa`` into two
   output filenames -- nothing in the data said which build produced which number. Task 1 fixed
   that; ``provenance`` is that block, read from the running process's argv.
3. ComfyUI was running with sage, died, was relaunched, and came back on SDPA silently. So a row
   whose ``provenance.attention_backend`` is ``unknown`` is RECORDED and excluded from every delta:
   the harness has to be able to say "this ran, and I cannot tell you on what".

And one rule that is structural rather than historical: ``baseline_mean`` travels WITH the row.
Nothing here looks a baseline up from another row, because a baseline from another session or
another build is how a 3% delta gets published over a 30% spread.

``normalize_row`` is where all of it is enforced, and ``append`` always calls it. A caller cannot
write a delta the rules forbid, even by computing one itself -- the file is the evidence, so the
evidence has to be the authority.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import optimization_levers

log = logging.getLogger(__name__)

LEDGER_FILENAME = "optimization_results.jsonl"

# Tests point this at a tmp_path. Production leaves it None and the path is derived, so the ledger
# follows SPELLVISION_STATE_ROOT the way every other piece of worker state does.
_LEDGER_PATH_OVERRIDE: Path | None = None

_WRITE_LOCK = threading.Lock()

_REQUIRED_FIELDS = ("family", "mode", "lever", "arm")

# A row larger than this is a bug in the caller, not a measurement; the read path skips it rather
# than letting one runaway line define how much memory reading the ledger costs.
_MAX_LINE_BYTES = 256 * 1024


def ledger_path() -> Path:
    if _LEDGER_PATH_OVERRIDE is not None:
        return Path(_LEDGER_PATH_OVERRIDE)
    from worker_durable_state import worker_state_root

    return worker_state_root() / LEDGER_FILENAME


def _numbers(value: Any) -> list[float]:
    """``seconds`` as a list of floats, refusing a scalar in the caller's words.

    A scalar is not a type error to be coerced -- it is the claim this module exists to reject, so
    it is reported as the claim rather than as a cast failure.
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        raise ValueError(
            "seconds must be a LIST of timed runs, never a scalar: a single timing is not a "
            "measurement. The published A/B on this project was three scalars and two of them were "
            "the same configuration, cold and warm (159.27 s and 120.72 s)."
        )
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("seconds must be a non-empty list of timed runs")
    out: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError(f"seconds contains a non-numeric entry: {item!r}")
        out.append(float(item))
    return out


def _memory_block(raw: Any, provenance: dict[str, Any]) -> dict[str, Any]:
    """The memory column, and whether it may be read.

    DynamicVRAM (``comfy-aimdo``, on by default on this core) hooks CUDA allocation and expands to
    fill what it is given, so a peak measures what was AVAILABLE, not what was needed: measured on
    this box, LTX 97f at 2048x1280 peaked 30.98 GB unconstrained and 11.47 GB at a 22 GB reserve --
    the same render. A peak is therefore comparable only when both arms ran at the same fixed
    ``--reserve-vram``, and a row that did not must SAY so rather than omit the field and look like
    it simply had nothing to report.
    """
    raw = dict(raw) if isinstance(raw, dict) else {}
    reserve = provenance.get("reserve_vram_gb")
    baseline_reserve = raw.get("baseline_reserve_vram_gb")
    block = {
        "peak_vram_gb": raw.get("peak_vram_gb"),
        "reserve_vram_gb": reserve,
        "baseline_reserve_vram_gb": baseline_reserve,
        "comparable": False,
        "reason": "",
    }
    if reserve is None:
        block["reason"] = (
            "no --reserve-vram was passed; under DynamicVRAM a peak measures what was AVAILABLE, "
            "not what was needed, so this number is not comparable to any other row's"
        )
        return block
    if baseline_reserve is None:
        block["reason"] = (
            f"run at a fixed --reserve-vram {reserve:g}, but the baseline row's reserve is not "
            "recorded, so there is nothing to compare it against."
        )
        return block
    if float(baseline_reserve) != float(reserve):
        block["reason"] = (
            f"run at --reserve-vram {reserve:g} against a baseline at {float(baseline_reserve):g}; "
            "different budgets produce different peaks for the same render."
        )
        return block
    block["comparable"] = True
    block["reason"] = f"both arms ran at a fixed --reserve-vram {reserve:g}"
    return block


def _exclusions(row: dict[str, Any], seconds: list[float], provenance: dict[str, Any]) -> list[str]:
    """Every reason this row may not produce a delta. Caller-supplied reasons come FIRST and are
    never overwritten -- the harness's "the restart argv did not match the arm I asked for" is a
    fact this module cannot re-derive."""
    reasons: list[str] = [str(reason) for reason in (row.get("exclusions") or []) if str(reason).strip()]

    if len(seconds) < 2:
        reasons.append(
            "only one timed run: a single timing is not a measurement (two runs of the same arm "
            "differed by 32% in the published A/B)"
        )
    if row.get("warm") is not True:
        reasons.append(
            "cold run: the first run of a configuration is not comparable to the second "
            "(159.27 s cold against 120.72 s warm, same configuration)"
        )

    backend = provenance.get("attention_backend")
    if not backend or backend == "unknown":
        reasons.append(
            "the attention backend of the running process could not be read (provenance."
            "attention_backend is unknown): this ran, and the ledger cannot say on what"
        )

    quality = row.get("quality") or {}
    if isinstance(quality, dict) and quality.get("status") == "fail":
        reasons.append(
            f"the quality guard failed ({', '.join(str(g) for g in quality.get('guards') or []) or 'unnamed'}): "
            "a lever that is faster and wrong is not a win"
        )
    return reasons


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    """A validated, self-consistent row -- or ``ValueError`` naming what is missing.

    Derived rather than accepted: ``mean`` (a caller-supplied mean is a second source of truth for
    the same fact), ``exclusions``, ``excluded_from_delta`` and ``delta_pct``.
    """
    if not isinstance(row, dict):
        raise ValueError("a ledger row must be a dict")

    for field in _REQUIRED_FIELDS:
        if not str(row.get(field) or "").strip():
            raise ValueError(f"a ledger row must state its {field}")

    if "warm" not in row or not isinstance(row.get("warm"), bool):
        raise ValueError(
            "a ledger row must state 'warm' explicitly as a bool: the archive's 159.27 s and "
            "120.72 s are the same configuration cold and warm, and a row that does not say which "
            "cannot be read"
        )

    quality = row.get("quality")
    if not isinstance(quality, dict) or not quality.get("guards"):
        raise ValueError(
            "a ledger row must carry a quality guard (quality.guards): seconds alone cannot "
            "distinguish a win from a faster wrong answer"
        )

    seconds = _numbers(row.get("seconds"))
    provenance = row.get("provenance") if isinstance(row.get("provenance"), dict) else {}

    normalized = dict(row)
    normalized["seconds"] = seconds
    normalized["mean"] = sum(seconds) / len(seconds)
    normalized["provenance"] = provenance
    normalized["quality"] = dict(quality)
    normalized["memory"] = _memory_block(row.get("memory"), provenance)

    reasons = _exclusions(row, seconds, provenance)
    normalized["exclusions"] = reasons
    normalized["excluded_from_delta"] = bool(reasons)

    baseline = row.get("baseline_mean")
    if reasons or baseline in (None, "") or float(baseline) == 0.0:
        normalized["delta_pct"] = None
        normalized["baseline_mean"] = float(baseline) if isinstance(baseline, (int, float)) else None
    else:
        baseline = float(baseline)
        normalized["baseline_mean"] = baseline
        normalized["delta_pct"] = (normalized["mean"] - baseline) / baseline * 100.0

    normalized.setdefault("dest", "")
    normalized.setdefault("job_id", "")
    normalized["recorded_at"] = str(row.get("recorded_at") or datetime.now().isoformat())
    return normalized


def append(row: dict[str, Any]) -> Path:
    """Normalize, then append one JSON line. Returns the ledger path."""
    normalized = normalize_row(row)
    path = ledger_path()
    line = json.dumps(normalized, ensure_ascii=False, default=str)
    with _WRITE_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    return path


def read(limit: int | None = None) -> list[dict[str, Any]]:
    """Rows oldest-first; ``limit`` returns the newest ``limit`` of them.

    A corrupt line is skipped with a warning rather than failing the read: a half-written line from
    an interrupted run must not take the rest of a night's measurements with it.
    """
    path = ledger_path()
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open("rb") as handle:
            for raw in handle:
                if len(raw) > _MAX_LINE_BYTES:
                    log.warning("optimization ledger: skipped an oversized line (%d bytes)", len(raw))
                    continue
                text = raw.strip()
                if not text:
                    continue
                try:
                    item = json.loads(text.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    log.warning("optimization ledger: skipped an unparseable line")
                    continue
                if isinstance(item, dict):
                    rows.append(item)
    except OSError as exc:
        log.warning("optimization ledger could not be read (%s): %s", path, exc)
        return []
    if limit is not None and limit >= 0:
        return rows[-limit:] if limit else []
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    """The families and levers the ledger actually holds rows for.

    Observed, not catalogued: a lever in ``optimization_levers`` with no row is a lever nobody has
    measured, and the difference between "measured" and "listed" is the whole subject here.
    """
    families = sorted({str(row.get("family") or "") for row in rows} - {""})
    levers = sorted({str(row.get("lever") or "") for row in rows} - {""})
    return {"families": families, "levers": levers}


def unmeasured_levers(rows: list[dict[str, Any]]) -> list[str]:
    """Runnable levers with no row yet. The honest gap in the matrix."""
    measured = {str(row.get("lever") or "") for row in rows}
    return [lever.id for lever in optimization_levers.runnable_levers() if lever.id not in measured]
