"""The execution loop: restart, verify, render, record -- one cell at a time.

Task 4 built every piece of this and deliberately stopped at ``--dry-run``. This is the part that
actually spends the hours, so its rules are about what happens when an hours-long run goes wrong
rather than about arithmetic.

**The arm is read back, never assumed.** Every step restarts the owner's ComfyUI and then reads the
argv out of the restart reply. A mismatch does not skip the step and does not quietly record the
rows either: the cells run, and every row from that step carries ``arm_verified: false`` with the
mismatch spelled out, which the ledger turns into an exclusion. The whole wave exists because an
earlier A/B asserted its arms instead of reading them, and the arms in that A/B were distinguishable
only because a human typed them into two filenames.

**A row lands the moment its cell finishes.** Not at the end of the run. This matrix is measured in
hours on a single-GPU box; a crash forty minutes in must not cost the thirty minutes before it. The
ledger is JSONL and appends under a lock for exactly this reason, and ``optimization_results.read``
already skips a half-written final line rather than failing the whole read.

**A re-run does not re-render what is already measured.** Before a cell runs, the ledger is asked
whether it already holds a WARM row for that family/mode/lever whose provenance fingerprint matches
the arm just read back from the argv. Matching provenance, not matching labels: "already measured"
must not be allowed to mean "measured once, on some other build". ``--force`` overrides, and every
skip prints what it skipped and why.

**One render failing is not the matrix failing.** A failed render is recorded as a failed run with
its reason and the cell keeps going; a cell where nothing survived is reported and the matrix moves
to the next lever. A failed RESTART is different and aborts: the arm is the independent variable, so
nothing measured under an arm that did not launch is interpretable. The abort still leaves through
``run_arms_with_restore``'s ``finally``, so the owner's stack is handed back either way.

**What is deliberately not measured here.** The artefact guard compares a lever's output against the
baseline arm's output AT THE SAME SEED, and every render in this harness gets a fresh seed because
that is what defeats ComfyUI's node cache. The two cannot both be true of one render, so by default
the artefact guard reports ``not_measured`` (which excludes the row) and says so on the line.
``--artefact-guard`` adds one extra, untimed render per cell at a seed shared with the baseline
cell, which is the only way to get an equal-seed comparison without letting a cached result reach a
timing. It costs one render per cell, which is why it is a choice rather than a default.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import measure_optimizations_link as link
import measure_optimizations_render as render
import optimization_levers as levers
import optimization_results as ledger
from measure_optimizations_rows import (
    ArmVerification,
    Baseline,
    RunResult,
    build_rows,
    measure_quality,
    verify_arm,
)
from measure_optimizations_restore import run_arms_with_restore

# One discarded run then two timed ones -- 159.27 s cold and 120.72 s warm are the SAME
# configuration in this project's own archive. Length must equal measure_optimizations.RUNS_PER_CELL
# (asserted in the tests; importing it here would be a cycle).
RUN_TAGS: tuple[str, ...] = ("cold", "warm_1", "warm_2")

GUARD_TAG = "guard"


class RestartFailed(RuntimeError):
    """The arm did not launch. Nothing below it could be interpreted, so the run stops."""


@dataclass(frozen=True)
class Options:
    requests: dict[str, Any]
    out_dir: Path
    force: bool = False
    artefact_guard: bool = False
    link_kwargs: dict[str, Any] = field(default_factory=dict)
    probe_kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass
class Tally:
    cells_measured: int = 0
    cells_skipped: int = 0
    rows_appended: int = 0
    renders_ok: int = 0
    renders_failed: int = 0
    failed_cells: list[str] = field(default_factory=list)
    unverified_arms: list[str] = field(default_factory=list)
    missing_templates: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not (self.failed_cells or self.unverified_arms or self.missing_templates)


def _label(cell: Any) -> str:
    return f"{cell.family}/{cell.mode} x {cell.lever}"


def _needs_artefact_guard(steps: Sequence[Any]) -> set[tuple[str, str]]:
    """The (family, mode) pairs some lever in this matrix compares at equal seed. The BASELINE cell
    of such a pair needs a guard render too, even though its own guards do not name artefact --
    there is nothing to compare against otherwise."""
    return {
        (cell.family, cell.mode)
        for step in steps for cell in step.cells
        if levers.GUARD_ARTEFACT in levers.required_guards(cell.lever, cell.mode)
    }


def run_matrix(steps: Sequence[Any], options: Options, printer: Any = print) -> Tally:
    """Run every arm for real, inside the restore wrapper. Returns what happened."""
    tally = Tally()
    recorded = ledger.read()
    baselines: dict[tuple[str, str], Baseline] = {}
    guard_seeds: dict[tuple[str, str], int] = {}
    guard_dests: dict[tuple[str, str, str], str] = {}
    guarded = _needs_artefact_guard(steps) if options.artefact_guard else set()
    options.out_dir.mkdir(parents=True, exist_ok=True)

    def run_step(step: Any) -> None:
        printer("")
        printer(f"=== arm {step.name!r}: restarting ComfyUI into {step.arm}")
        try:
            reply = link.restart_into_arm(step.arm, **options.link_kwargs)
        except Exception as exc:  # noqa: BLE001 -- turn it into the abort, with its cause named.
            raise RestartFailed(f"the restart request for arm {step.name!r} raised: {exc!r}") from exc
        if reply.get("ok") is False:
            reason = reply.get("message") or reply.get("error") or "the reply said ok: false"
            raise RestartFailed(f"arm {step.name!r} did not launch: {reason}")

        verification = verify_arm(step.arm, reply)
        if verification.ok:
            printer(f"    argv verified: {verification.observed.get('argv')}")
        else:
            tally.unverified_arms.append(f"{step.name}: {verification.reason}")
            printer(f"    ARM NOT VERIFIED: {verification.reason}")
            printer("    every row from this arm will be marked arm_verified:false and excluded")

        before = dict(rows=tally.rows_appended, ok=tally.renders_ok, bad=tally.renders_failed,
                      skipped=tally.cells_skipped)
        for cell in step.cells:
            _run_cell(cell, step, verification)
        printer(
            f"--- arm {step.name!r} finished: {len(step.cells)} cells, "
            f"{tally.rows_appended - before['rows']} rows, "
            f"{tally.renders_ok - before['ok']} renders ok, "
            f"{tally.renders_failed - before['bad']} failed, "
            f"{tally.cells_skipped - before['skipped']} skipped"
        )

    def _run_cell(cell: Any, step: Any, verification: ArmVerification) -> None:
        key = f"{cell.family}:{cell.mode}"
        template = options.requests.get(key)
        if not isinstance(template, dict) or not template:
            tally.missing_templates.append(key)
            printer(f"    SKIP {_label(cell)}: no request template for {key!r} -- this harness will "
                    "not invent one")
            return

        fingerprint = render.provenance_fingerprint(verification.observed)
        if not options.force:
            prior = render.already_measured(recorded, cell.family, cell.mode, cell.lever, fingerprint)
            if prior is not None:
                tally.cells_skipped += 1
                if cell.lever == levers.BASELINE_LEVER.id and prior.get("mean") is not None:
                    # A resumed run whose baseline cell is skipped must still carry that family's
                    # baseline_mean forward, or every lever measured after the resume records a
                    # number with nothing to compare it against -- which is the failure this whole
                    # ledger exists to prevent, arriving by way of the feature meant to save time.
                    baselines[(cell.family, cell.mode)] = Baseline(
                        mean=prior.get("mean"),
                        reserve_vram_gb=(prior.get("provenance") or {}).get("reserve_vram_gb"),
                    )
                printer(f"    SKIP {_label(cell)}: the ledger already holds a warm row recorded "
                        f"{prior.get('recorded_at')} on the same provenance {fingerprint} "
                        "(--force re-measures it)")
                return

        lever = levers.lever(cell.lever)
        pair = (cell.family, cell.mode)
        keyframe = render.keyframe_for(template)
        outcomes: list[render.RenderOutcome] = []
        for index, tag in enumerate(RUN_TAGS, start=1):
            outcome = render.render_once(
                template, family=cell.family, mode=cell.mode, lever=cell.lever,
                lever_request=lever.request, tag=tag, out_dir=options.out_dir,
                fallback_provenance=verification.observed, link_kwargs=options.link_kwargs,
            )
            outcomes.append(outcome)
            _print_render(step, cell, outcome, index, len(RUN_TAGS))

        guard_dest = ""
        if pair in guarded:
            guard_seed = guard_seeds.setdefault(pair, render.fresh_seed())
            guard = render.render_once(
                template, family=cell.family, mode=cell.mode, lever=cell.lever,
                lever_request=lever.request, tag=GUARD_TAG, out_dir=options.out_dir,
                fallback_provenance=verification.observed, link_kwargs=options.link_kwargs,
                seed=guard_seed,
            )
            _print_render(step, cell, guard, 0, len(RUN_TAGS))
            if guard.ok:
                guard_dest = guard.dest
                guard_dests[(cell.family, cell.mode, cell.lever)] = guard.dest

        succeeded = [o for o in outcomes if o.ok]
        if not succeeded:
            tally.failed_cells.append(f"{_label(cell)}: {outcomes[-1].reason}")
            printer(f"    CELL FAILED {_label(cell)}: every render failed -- "
                    f"{outcomes[-1].reason}. Continuing to the next lever.")
            return

        has_cold = outcomes[0].ok
        results = [
            RunResult(seconds=float(o.seconds or 0.0), dest=o.dest, job_id=o.job_id,
                      peak_vram_gb=o.peak_vram_gb)
            for o in succeeded
        ]
        values = measure_quality(cell.lever, cell.mode, succeeded[-1].dest, keyframe=keyframe)
        if guard_dest:
            reference = guard_dests.get((cell.family, cell.mode, levers.BASELINE_LEVER.id))
            if reference and reference != guard_dest:
                equal_seed = measure_quality(cell.lever, cell.mode, guard_dest,
                                             baseline_dest=reference)
                if "artefact_delta" in equal_seed:
                    values["artefact_delta"] = equal_seed["artefact_delta"]
            elif reference == guard_dest:
                # The baseline compared against itself is 0 by construction, not a measurement.
                values["artefact_delta"] = 0.0
        results[-1].quality_values = values

        provenance = succeeded[-1].provenance
        rows = build_rows(
            cell, step, results, provenance,
            baselines.get(pair, Baseline(mean=None, reserve_vram_gb=None)),
            verification, has_cold=has_cold, runs=[o.record() for o in outcomes],
        )
        for row in rows:
            ledger.append(row)
            recorded.append(row)
            tally.rows_appended += 1
        tally.cells_measured += 1

        warm = rows[-1] if rows and rows[-1].get("warm") else None
        if warm and cell.lever == levers.BASELINE_LEVER.id:
            baselines[pair] = Baseline(mean=warm.get("mean"),
                                       reserve_vram_gb=provenance.get("reserve_vram_gb"))
        if warm:
            quality = warm.get("quality") or {}
            printer(f"    recorded {_label(cell)}: mean {warm.get('mean'):.2f}s over "
                    f"{len(warm.get('seconds') or [])} timed runs, quality "
                    f"{quality.get('status')}, delta {warm.get('delta_pct')}")
            if levers.GUARD_ARTEFACT in (quality.get("unmeasured") or []):
                printer("      (the artefact guard needs an equal-seed comparison and every timed "
                        "render gets a fresh seed -- re-run with --artefact-guard to measure it)")

    def _print_render(step: Any, cell: Any, outcome: render.RenderOutcome, index: int,
                      total: int) -> None:
        position = "guard" if outcome.tag == GUARD_TAG else f"run {index}/{total}"
        cold = " COLD" if outcome.tag == RUN_TAGS[0] else ""
        head = f"  [{step.name}] {_label(cell)} {position}{cold} seed={outcome.seed}"
        if outcome.ok:
            tally.renders_ok += 1
            printer(f"{head} {outcome.seconds:.2f}s")
        else:
            tally.renders_failed += 1
            printer(f"{head} FAILED: {outcome.reason}")

    run_arms_with_restore(
        steps, run_step, probe_kwargs=options.probe_kwargs,
        link_kwargs=options.link_kwargs, printer=printer,
    )
    return tally


def describe_tally(tally: Tally, path: Any = None) -> str:
    lines = ["", "RUN SUMMARY", ""]
    lines.append(f"  cells measured: {tally.cells_measured}   skipped: {tally.cells_skipped}")
    lines.append(f"  renders: {tally.renders_ok} ok, {tally.renders_failed} failed")
    lines.append(f"  rows appended: {tally.rows_appended}" + (f" -> {path}" if path else ""))
    for name, entries in (("cells where every render failed", tally.failed_cells),
                          ("arms whose argv did not match the request", tally.unverified_arms),
                          ("cells with no request template", tally.missing_templates)):
        if entries:
            lines.append(f"  {name}:")
            lines += [f"    {entry}" for entry in entries]
    lines.append("")
    return "\n".join(lines)
