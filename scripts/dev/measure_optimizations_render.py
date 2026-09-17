"""One render, and the number it is allowed to contribute.

The matrix above this module decides WHAT to run; this decides what a single render is, and it
refuses in three places rather than computing:

**The seconds come from the job's own record.** ``link.render`` also returns a stopwatch reading
around the whole request, and that number includes queue admission, request transport and the
keyframe upload -- none of which is the thing under test. The worker already writes
``generation_time_sec`` into every result envelope and its sidecar, so that is the number a row
carries; a completed job that did not report one is a FAILED run here, with that as its reason,
rather than a wall-clock figure quietly substituted for a render time. The wall reading is kept
alongside it, because the gap between the two is exactly what "cold" means.

**Every render gets its own seed.** Not its own filename -- the recorded trap on this project is a
re-submit that changed only the output filename, hit ComfyUI's node cache, and came back "12.1 s /
23.62 GB" for work that never happened. The cache is keyed on the graph, and the seed is in the
graph. The dest is made unique too, but only so renders do not overwrite each other.

**The provenance comes back with the render.** ``result.optimizations`` is the block
``worker_metadata._optimizations_block`` probed from the RUNNING ComfyUI's argv at the moment this
render ran -- which is a stronger statement than the arm this harness asked for. Where a result
carries none, the fallback is the argv read back from the restart reply, marked as such in
``provenance_source``, because a row that cannot say what produced its number is excluded by the
ledger and a row that pretends is worse.

One thing this module deliberately cannot supply: a peak VRAM figure for a native ComfyUI route.
``vram.py`` says why -- ComfyUI publishes no peak, and the worker's own allocator sees nothing on a
route that renders out-of-process. So ``peak_vram_gb`` is None on those rows and the ledger's memory
column says it is not comparable, instead of a current reading dressed up as a peak.
"""
from __future__ import annotations

import copy
import random
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import measure_optimizations_link as link

# The cockpit's own seed range (SamplingController.cpp: setRange(0, 2147483647)).
MAX_SEED = 2_147_483_647

_RANDOM = random.SystemRandom()

# Where an i2v template may carry its conditioning image. Checked in order; the first non-empty
# existing path wins, and none of them existing means the frame0 guard reports "not measured"
# rather than comparing against something that is not the keyframe.
_KEYFRAME_KEYS = (
    "input_image", "init_image", "source_image", "video_input_image", "image", "image_path",
)

# Suffix when a template names no output of its own. Only a fallback -- the template's own
# ``original_output`` decides, because it is the extension the builder for that family produces.
_SUFFIX_BY_MODE = {"t2i": ".png", "i2i": ".png", "t2v": ".mp4", "i2v": ".mp4"}

# The peak keys a result envelope may carry. Reserved-current is NOT in this list: it is not a peak,
# and recording it as one is the same lie as a stopwatch standing in for a render time.
_PEAK_KEYS = ("cuda_max_allocated_gb", "cuda_max_reserved_gb")


def fresh_seed() -> int:
    """A seed inside the range a user could type. A harness seed outside it would measure a
    configuration nobody can reproduce from the cockpit."""
    return _RANDOM.randrange(0, MAX_SEED + 1)


@dataclass(frozen=True)
class RenderOutcome:
    """What one render produced, or why it produced nothing."""

    ok: bool
    tag: str
    seed: int
    reason: str = ""
    seconds: float | None = None
    wall_seconds: float | None = None
    dest: str = ""
    job_id: str = ""
    peak_vram_gb: float | None = None
    provenance: dict[str, Any] = field(default_factory=dict)

    def record(self) -> dict[str, Any]:
        """The per-run entry a row carries, so a reader can see every attempt, not only the ones
        that produced a number."""
        return {
            "tag": self.tag, "seed": self.seed, "ok": self.ok, "seconds": self.seconds,
            "wall_seconds": self.wall_seconds, "job_id": self.job_id, "dest": self.dest,
            "reason": self.reason,
        }


def dest_for(out_dir: Path, family: str, mode: str, lever: str, tag: str, seed: int,
             template: dict[str, Any]) -> tuple[str, str]:
    """``(output, metadata_output)`` for one render, unique by construction.

    Unique so renders never overwrite each other -- NOT as a cache defence. Changing only the
    filename is exactly the re-submit that returned a cached "12.1 s".
    """
    original = str(template.get("original_output") or template.get("output") or "").strip()
    suffix = Path(original).suffix if original else _SUFFIX_BY_MODE.get(mode, ".png")
    stem = f"{family}_{mode}_{lever}_{tag}_{seed}"
    return str(out_dir / f"{stem}{suffix or '.png'}"), str(out_dir / f"{stem}.json")


def keyframe_for(template: dict[str, Any]) -> str | None:
    """The i2v conditioning image this request renders from, if it names one on disk."""
    for key in _KEYFRAME_KEYS:
        candidate = str(template.get(key) or "").strip()
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def build_request(
    template: dict[str, Any],
    *,
    lever_request: dict[str, Any] | None,
    seed: int,
    output: str,
    metadata_output: str,
    job_id: str,
) -> dict[str, Any]:
    """One worker request: the archived template, this lever's switches, this render's seed.

    The lever's ``request`` keys are applied LAST and over the template, because that is the one
    thing the cell is changing. Everything else is the template's, unedited -- a harness that
    rewrote a checkpoint or a step count would be measuring a render the operator never asked for.
    """
    request = copy.deepcopy(template)
    request.pop("queue_item_id", None)
    request.pop("retry_of", None)
    request["batch_count"] = 1
    request["seed"] = int(seed)
    request["job_id"] = job_id
    request["output"] = output
    request["metadata_output"] = metadata_output
    request["original_output"] = output
    request["original_metadata_output"] = metadata_output
    request["submit_origin"] = "optimization_harness"
    request.update(dict(lever_request or {}))
    return request


def _terminal_reason(terminal: dict[str, Any]) -> str:
    error = terminal.get("error")
    if isinstance(error, dict):
        message = str(error.get("message") or error.get("code") or "").strip()
        if message:
            return message
    for key in ("message", "error", "reason"):
        value = terminal.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    state = str(terminal.get("state") or "").strip()
    return f"the worker returned state {state!r} with no reason" if state else (
        "the worker closed the connection without a terminal message"
    )


def _peak_from(result: dict[str, Any]) -> float | None:
    for key in _PEAK_KEYS:
        value = result.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def outcome_from(
    terminal: dict[str, Any],
    *,
    tag: str,
    seed: int,
    wall_seconds: float,
    requested_dest: str,
    fallback_provenance: dict[str, Any] | None = None,
) -> RenderOutcome:
    """Read one render's result, refusing anything that is not a completed job with its own time."""
    terminal = terminal if isinstance(terminal, dict) else {}
    result = terminal.get("result") if isinstance(terminal.get("result"), dict) else {}
    job_id = str(terminal.get("job_id") or result.get("job_id") or "")

    if str(terminal.get("state") or "") != "completed":
        return RenderOutcome(ok=False, tag=tag, seed=seed, wall_seconds=wall_seconds,
                             job_id=job_id, reason=_terminal_reason(terminal))

    seconds = result.get("generation_time_sec")
    if not isinstance(seconds, (int, float)) or isinstance(seconds, bool):
        return RenderOutcome(
            ok=False, tag=tag, seed=seed, wall_seconds=wall_seconds, job_id=job_id,
            reason=("the job completed but reported no generation_time_sec; the round-trip wall "
                    f"time ({wall_seconds:.2f} s) includes queue and upload and is not the thing "
                    "under test, so this run contributes no timing"),
        )

    provenance = result.get("optimizations")
    if isinstance(provenance, dict) and provenance:
        provenance = {**provenance, "provenance_source": "render_result"}
    else:
        provenance = {
            **dict(fallback_provenance or {}),
            "provenance_source": "restart_argv",
            "probe_error": ("the render's result carried no optimizations block; this provenance "
                            "was read from the restart reply's argv instead"),
        }

    dest = str(
        result.get("output") or result.get("video_output") or result.get("video_path")
        or requested_dest
    )
    return RenderOutcome(
        ok=True, tag=tag, seed=seed, seconds=float(seconds), wall_seconds=wall_seconds,
        dest=dest, job_id=job_id, peak_vram_gb=_peak_from(result), provenance=provenance,
    )


def render_once(
    template: dict[str, Any],
    *,
    family: str,
    mode: str,
    lever: str,
    lever_request: dict[str, Any] | None,
    tag: str,
    out_dir: Path,
    fallback_provenance: dict[str, Any] | None = None,
    link_kwargs: dict[str, Any] | None = None,
    seed: int | None = None,
) -> RenderOutcome:
    """Send one render over the worker socket and read its own number back.

    Never raises for a render-side failure: a transport error is an outcome with a reason, because
    one dead render must not take the other thirty-five with it.

    ``seed`` is supplied only by the equal-seed artefact guard, whose whole point is to repeat one
    seed across arms; it is never timed, so a node-cache hit on it cannot reach a measurement. Every
    TIMED render leaves it None and gets a fresh one.
    """
    seed = fresh_seed() if seed is None else int(seed)
    job_id = f"opt_{uuid.uuid4().hex[:12]}"
    output, metadata_output = dest_for(out_dir, family, mode, lever, tag, seed, template)
    request = build_request(
        template, lever_request=lever_request, seed=seed, output=output,
        metadata_output=metadata_output, job_id=job_id,
    )
    try:
        wall_seconds, terminal = link.render(request, **(link_kwargs or {}))
    except Exception as exc:  # noqa: BLE001 -- a dead render is a row, not a crashed matrix.
        return RenderOutcome(ok=False, tag=tag, seed=seed, job_id=job_id,
                             reason=f"the render request raised: {exc!r}")
    return outcome_from(terminal, tag=tag, seed=seed, wall_seconds=wall_seconds,
                        requested_dest=output, fallback_provenance=fallback_provenance)


# --- resume ---------------------------------------------------------------------------------------
#
# This matrix is measured in hours. A crash forty minutes in must not cost the thirty minutes
# before it, and a re-run must not re-render what the ledger already holds -- but only where the
# recorded row was produced by the SAME build and the same arm, or "already measured" would mean
# "measured once, on something else".

_FINGERPRINT_KEYS = ("attention_backend", "fast_flags", "dynamic_vram", "reserve_vram_gb")


def provenance_fingerprint(block: dict[str, Any] | None) -> tuple[Any, ...]:
    """The four axes that make two renders the same configuration. Comparable between a ledger
    row's recorded provenance and the argv read back from a restart, which is what makes the resume
    check answerable BEFORE a cell runs."""
    block = block or {}
    fast = block.get("fast_flags") or []
    reserve = block.get("reserve_vram_gb")
    return (
        str(block.get("attention_backend") or "unknown"),
        tuple(sorted(str(flag) for flag in fast)) if isinstance(fast, (list, tuple)) else (),
        None if block.get("dynamic_vram") is None else bool(block.get("dynamic_vram")),
        None if reserve is None else float(reserve),
    )


def already_measured(
    rows: list[dict[str, Any]], family: str, mode: str, lever: str, fingerprint: tuple[Any, ...],
) -> dict[str, Any] | None:
    """The ledger row that makes re-running this cell pointless, or None.

    A WARM row only: a cold row is recorded but never compared, so a cell whose only row is the
    discarded first run has not been measured. An unverified arm does not count either -- that row
    exists precisely because nobody could say what produced it.
    """
    for row in reversed(rows):
        if (str(row.get("family")) != family or str(row.get("mode")) != mode
                or str(row.get("lever")) != lever):
            continue
        if row.get("warm") is not True or row.get("arm_verified") is False:
            continue
        if provenance_fingerprint(row.get("provenance")) == fingerprint:
            return row
    return None
