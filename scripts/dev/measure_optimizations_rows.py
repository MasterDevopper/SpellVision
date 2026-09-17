"""Turning three runs of one cell into rows the ledger will accept.

Two things happen here and both are refusals rather than computations.

**Did the arm take.** ``verify_arm`` compares what was ASKED for against the argv the restart
actually launched. Task 2 put ``argv`` on the restart reply for this one purpose: the Qt sage probe
fails open to SDPA on a cold launch, so a request for sage can legitimately produce a process
running SDPA -- which is what happened on this box the morning this wave was written. An arm that
cannot be verified marks every row under it and excludes it from deltas, rather than recording a
number under a label it did not earn.

**Was it still right.** ``quality_verdict`` returns ``pass`` / ``fail`` / ``not_measured`` over the
guards the lever and mode require. ``not_measured`` is a distinct answer on purpose: a guard that
reports "pass" because nothing measured it is worse than no guard, because it makes the row look
checked.

The cold run becomes its own row rather than being dropped. The archive's third arm was lost by
being un-mentioned, not by being deleted, and a discarded run nobody wrote down is how a 32% spread
between two runs of ONE arm stays invisible.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import measure_optimizations_quality as quality_probe
import optimization_levers as levers
import optimization_provenance as provenance_probe
import optimization_results as ledger

# A frame that is black to the eye over this much of its area is SageAttention's documented
# overflow failure (pv_accum_dtype), not a dark picture.
BLACK_FRAME_FAIL = 0.98
# Render-proven frame-0 MAE on this box: LTX ~3.5, Wan 2.2 5.19, Hunyuan 5.55. 12 sits comfortably
# above every proven value and far below a keyframe that was not honoured at all.
FRAME0_MAE_FAIL = 12.0
# Mean absolute channel difference against the baseline arm's output at the SAME seed, out of 255.
ARTEFACT_DELTA_FAIL = 8.0

_THRESHOLDS = {
    "black_frame": ("black_fraction", BLACK_FRAME_FAIL),
    "frame0_mae": ("frame0_mae", FRAME0_MAE_FAIL),
    "artefact": ("artefact_delta", ARTEFACT_DELTA_FAIL),
}


@dataclass
class RunResult:
    seconds: float
    dest: str = ""
    job_id: str = ""
    peak_vram_gb: float | None = None
    quality_values: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Baseline:
    """The baseline this row is compared against, carried TO the row rather than looked up later.

    Both halves matter: the mean, so a delta can never be computed against a baseline from another
    session or another build, and the reserve, because a peak VRAM figure is comparable only when
    both arms ran at the same fixed ``--reserve-vram``.
    """

    mean: float | None
    reserve_vram_gb: float | None


@dataclass(frozen=True)
class ArmVerification:
    ok: bool
    reason: str
    observed: dict[str, Any]


def verify_arm(arm: dict[str, Any] | None, restart_reply: dict[str, Any]) -> ArmVerification:
    """Read the arm back out of the restart reply's argv. A request is not evidence."""
    arm = arm or {}
    argv = restart_reply.get("argv")
    if not isinstance(argv, list) or not argv:
        return ArmVerification(False, "the restart reply carried no argv, so the arm cannot be read", {})

    observed = {
        "attention_backend": provenance_probe.attention_from_argv(argv),
        "fast_flags": provenance_probe.fast_from_argv(argv),
        "dynamic_vram": provenance_probe.dynamic_vram_from_argv(argv),
        "reserve_vram_gb": provenance_probe.reserve_vram_from_argv(argv),
        "argv": list(argv),
    }
    if restart_reply.get("ok") is False:
        reason = restart_reply.get("message") or restart_reply.get("error") or "no reason given"
        return ArmVerification(False, f"the restart failed: {reason}", observed)

    mismatches: list[str] = []
    if "attention" in arm and observed["attention_backend"] != str(arm["attention"]):
        mismatches.append(
            f"asked for attention {str(arm['attention'])!r}, argv says {observed['attention_backend']!r}"
        )
    if "fast" in arm and sorted(observed["fast_flags"]) != sorted(str(f) for f in arm["fast"]):
        mismatches.append(f"asked for --fast {list(arm['fast'])}, argv says {observed['fast_flags']}")
    if "dynamic_vram" in arm and observed["dynamic_vram"] is not bool(arm["dynamic_vram"]):
        mismatches.append(
            f"asked for dynamic_vram {arm['dynamic_vram']}, argv says {observed['dynamic_vram']}"
        )
    if "vram_headroom" in arm:
        wanted = float(arm["vram_headroom"])
        got = observed["reserve_vram_gb"]
        if got is None or float(got) != wanted:
            mismatches.append(f"asked for --reserve-vram {wanted:g}, argv says {got}")

    if mismatches:
        return ArmVerification(False, "; ".join(mismatches), observed)
    return ArmVerification(True, "", observed)


def quality_verdict(guards: Sequence[str], values: dict[str, Any]) -> dict[str, Any]:
    """``pass`` / ``fail`` / ``not_measured`` over the guards this row requires."""
    failed: list[str] = []
    missing: list[str] = []
    for guard in guards:
        key, limit = _THRESHOLDS.get(guard, (guard, None))
        if key not in values or values[key] is None:
            missing.append(guard)
            continue
        if limit is not None and float(values[key]) >= limit:
            failed.append(f"{guard}={values[key]}")
    return {
        "guards": list(guards),
        "status": "fail" if failed else ("not_measured" if missing else "pass"),
        "values": dict(values),
        "failed": failed,
        "unmeasured": missing,
    }


def measure_quality(cell_lever: str, mode: str, dest: str, *, keyframe: str | None = None,
                    baseline_dest: str | None = None) -> dict[str, Any]:
    """The measured guard values for one output. Called on the live path; absent keys mean the
    measurement could not be taken, which reaches the row as ``not_measured`` rather than as
    silence."""
    guards = levers.required_guards(cell_lever, mode)
    return quality_probe.measure(dest, guards=guards, keyframe=keyframe, baseline_dest=baseline_dest)


def build_rows(
    cell: Any,
    step: Any,
    results: Sequence[RunResult],
    provenance: dict[str, Any],
    baseline: Baseline,
    verification: ArmVerification,
    has_cold: bool = True,
    runs: Sequence[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """One cold row and one warm row, both normalized by the ledger before they are returned.

    ``has_cold=False`` says the first entry of ``results`` is NOT the discarded run -- the cold
    render failed and only timed ones came back. Without it the first surviving warm run would be
    relabelled cold, which is the same species of quiet mislabelling as recording a number under an
    arm it did not run on: the archive's 159.27 s and 120.72 s are one configuration cold and warm,
    and a row that says the wrong one cannot be read.

    ``runs`` is every attempt including the failed ones, carried onto the row so a reader can see
    what was tried rather than only what survived.
    """
    if not results:
        return []
    guards = levers.required_guards(cell.lever, cell.mode)
    is_baseline = cell.lever == levers.BASELINE_LEVER.id

    def _row(timed: Sequence[RunResult], warm: bool) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for run in timed:
            merged.update(run.quality_values or {})
        verdict = quality_verdict(guards, merged)

        exclusions: list[str] = []
        if not verification.ok:
            exclusions.append(
                f"the arm could not be verified from the restart argv: {verification.reason}"
            )
        if verdict["status"] == "not_measured":
            exclusions.append(
                "the quality guard for this row was not measured "
                f"({', '.join(verdict['unmeasured'])}); a lever that is faster and wrong is not a win"
            )

        peaks = [run.peak_vram_gb for run in timed if run.peak_vram_gb is not None]
        return ledger.normalize_row({
            "family": cell.family,
            "mode": cell.mode,
            "lever": cell.lever,
            "arm": step.name,
            "arm_requested": dict(step.arm or {}),
            "arm_verified": verification.ok,
            "arm_verification": verification.reason,
            "seconds": [run.seconds for run in timed],
            "baseline_mean": None if is_baseline else baseline.mean,
            "warm": warm,
            "quality": verdict,
            "provenance": provenance,
            "memory": {
                "peak_vram_gb": max(peaks) if peaks else None,
                "baseline_reserve_vram_gb": baseline.reserve_vram_gb,
            },
            "exclusions": exclusions,
            "runs": [dict(entry) for entry in (runs or [])],
            "dest": timed[-1].dest,
            "job_id": timed[-1].job_id,
            # Every sage number is an SA1 number. Recorded on every row rather than only the sage
            # ones, so a reader comparing two rows never has to go looking for which is which.
            "sageattention_installed": levers.SAGEATTENTION_INSTALLED,
        })

    if not has_cold:
        return [_row(results, warm=True)]
    rows = [_row(results[:1], warm=False)]
    if len(results) > 1:
        rows.append(_row(results[1:], warm=True))
    return rows
