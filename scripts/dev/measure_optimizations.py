"""Time every optimization against its unoptimized twin, under rules a single run cannot satisfy.

This project published one A/B -- SageAttention 120.72 s against SDPA 124.01 s, about 3%. The
archive holds a third arm nobody mentioned at 159.27 s, same seed, same steps, same size, fifteen
minutes before the quoted sage run; the arms were distinguishable only because a human typed
``t4_sage`` and ``t4_sdpa`` into two output filenames; and the morning this was written ComfyUI was
running with sage, died, was relaunched, and came back on SDPA silently. So the six disciplines
below are not research hygiene -- they are this box's history:

1. **Vary the seed every run.** ComfyUI's node cache returns a cached result for an identical
   prompt, and the recorded trap here is a "12.1 s / 23.62 GB" that was a cache hit on a re-submit
   which changed only the output filename.
2. **Discard the first run of every configuration** -- recorded, marked ``warm: false`` -- then take
   two timed runs. 159.27 and 120.72 are the same configuration cold and warm.
3. **Restart between arms and READ THE ARGV BACK** from the restart reply (Task 2 added that field
   for exactly this). An argv that does not match marks the row and excludes it, rather than
   quietly recording a number under a label it did not earn.
4. **Memory only at a fixed ``--reserve-vram``.** DynamicVRAM expands to fill what is available, so
   an unconstrained peak measures availability, not need.
5. **Every row carries a quality guard.** A lever that is faster and wrong is not a win.
6. **Run through the worker, not around it** (W3-P2), so each row is also a real job with a sidecar.
   ``scripts/dev/wrought_comfy.py`` and ``runtime/night_run.py`` talk to ComfyUI directly, and that
   is precisely why their numbers never reached a sidecar.

Rules 3-5 live in ``measure_optimizations_rows``; the wire lives in ``measure_optimizations_link``;
the pixels live in ``measure_optimizations_quality``. This module owns the matrix, the arm order and
the CLI.

**Task 4 ends at ``--dry-run``.** Running the live matrix is Task 5: it restarts the owner's ComfyUI
once per arm and renders for hours, so a bare invocation deliberately refuses.

    python scripts/dev/measure_optimizations.py --dry-run
    python scripts/dev/measure_optimizations.py --dry-run --family krea2 --lever sage_attention
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import measure_optimizations_link as link  # noqa: E402,F401  (the live path's transport)
import optimization_levers as levers  # noqa: E402
from measure_optimizations_rows import (  # noqa: E402
    ArmVerification,
    Baseline,
    RunResult,
    build_rows,
    measure_quality,
    quality_verdict,
    verify_arm,
)

__all__ = [
    "ArmStep", "ArmVerification", "Baseline", "Cell", "RunPlan", "RunResult",
    "arm_sequence", "build_matrix", "build_rows", "describe", "link", "main", "measure_quality",
    "quality_verdict", "runs_for_cell", "verify_arm",
]

# The cockpit's own seed range (SamplingController.cpp: setRange(0, 2147483647)). A harness seed
# outside the range a user can type would measure a configuration nobody can reproduce.
MAX_SEED = 2_147_483_647

RUNS_PER_CELL = 3  # one discarded, then two timed.

_RANDOM = random.SystemRandom()


@dataclass(frozen=True)
class Cell:
    """One measurement: this lever, on this family, in this mode."""

    family: str
    mode: str
    lever: str


@dataclass(frozen=True)
class ArmStep:
    """The cells that share one ComfyUI launch, so the restart is paid once rather than per cell."""

    name: str
    arm: dict[str, Any] | None
    cells: tuple[Cell, ...]


@dataclass(frozen=True)
class RunPlan:
    index: int
    seed: int
    warm: bool


def build_matrix(
    families: Sequence[str] | None = None,
    lever_ids: Sequence[str] | None = None,
) -> list[Cell]:
    """Every cell to measure.

    The baseline lever is always included, even when the caller narrows to one lever: a row carries
    its own ``baseline_mean``, so measuring a lever without measuring the thing it is compared
    against produces a row with no delta at all.

    A lever with a ``families`` restriction only appears on those families. ``--fast
    fp8_matrix_mult`` is inert on a bf16 checkpoint, so a cell for it elsewhere would report the
    measurement noise of an unchanged configuration as a delta.
    """
    family_modes = {
        family: modes for family, modes in levers.DEFAULT_FAMILIES.items()
        if not families or family in families
    }
    wanted = set(lever_ids or ())
    if wanted:
        wanted.add(levers.BASELINE_LEVER.id)

    cells: list[Cell] = []
    for lever in levers.runnable_levers():
        if wanted and lever.id not in wanted:
            continue
        for family, modes in family_modes.items():
            if lever.families and family not in lever.families:
                continue
            for mode in modes:
                cells.append(Cell(family=family, mode=mode, lever=lever.id))
    return cells


def arm_sequence(cells: Sequence[Cell]) -> list[ArmStep]:
    """The cells grouped into launches, baseline first.

    Baseline first because every other row needs its family's ``baseline_mean``, and that number
    travels WITH the row -- there is no later lookup to fall back on.

    Graph levers (``vae_tiling``) ride inside the baseline launch. They change the graph, not the
    process, so restarting for one would measure a restart.
    """
    grouped: dict[str, list[Cell]] = {}
    arms: dict[str, dict[str, Any] | None] = {}
    for cell in cells:
        lever = levers.lever(cell.lever)
        name = lever.id if lever.arm else levers.BASELINE_LEVER.id
        arms[name] = lever.arm if lever.arm else levers.BASELINE_LEVER.arm
        grouped.setdefault(name, []).append(cell)

    ordered = [levers.BASELINE_LEVER.id] + sorted(n for n in grouped if n != levers.BASELINE_LEVER.id)
    return [
        ArmStep(name=name, arm=arms[name], cells=tuple(grouped[name]))
        for name in ordered if name in grouped
    ]


def runs_for_cell() -> list[RunPlan]:
    """Three runs: one discarded and two timed, each on its own fresh seed.

    The seed is what defeats ComfyUI's node cache. Changing the output filename is NOT enough -- the
    cache is keyed on the graph, and the recorded trap on this project is a re-submit that changed
    only the filename and came back in 12.1 s with a 23.62 GB "peak" that was never measured.
    """
    return [
        RunPlan(index=index, seed=_RANDOM.randrange(0, MAX_SEED + 1), warm=index > 0)
        for index in range(RUNS_PER_CELL)
    ]


def load_requests(path: str | None) -> dict[str, Any]:
    """``"family:mode"`` -> a worker request.

    The harness will not invent a render request: a cell with no template is REPORTED and skipped,
    never filled in with a guess about which checkpoints the operator meant.
    """
    if not path:
        return {}
    try:
        loaded = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"could not read the request templates at {path}: {exc}")
        return {}
    return loaded if isinstance(loaded, dict) else {}


def describe(steps: Sequence[ArmStep], requests: dict[str, Any]) -> str:
    """The plan, in the order it would run, including what it will NOT measure and why."""
    lines: list[str] = ["", "ARM SEQUENCE -- one ComfyUI restart per arm, baseline first", ""]
    total = 0
    for position, step in enumerate(steps, start=1):
        lines.append(f"  {position}. restart into arm {step.name!r}: {step.arm}")
        lines.append("     then read the argv back from the restart reply; a mismatch marks every "
                     "row below it and excludes it from deltas")
        for cell in step.cells:
            guards = ", ".join(levers.required_guards(cell.lever, cell.mode))
            missing = "" if f"{cell.family}:{cell.mode}" in requests else "   [NO REQUEST TEMPLATE -- skipped]"
            lines.append(
                f"       {cell.family}/{cell.mode} x {cell.lever}: {RUNS_PER_CELL} runs "
                f"(1 cold + 2 timed), fresh seed each, guards [{guards}]{missing}"
            )
            total += RUNS_PER_CELL
        lines.append("")
    lines.append(f"  {total} renders across {len(steps)} arms. No render was performed.")

    lines += ["", "DECLARED AND WITHHELD -- on this core, not askable from this repository:", ""]
    lines += [f"  {lever.id}: {lever.blocked_reason}" for lever in levers.blocked_levers()]
    lines += ["", "CUT -- not reachable on core 0.34.0 + torch 2.10/cu128:", ""]
    lines += [f"  {name}: {reason}" for name, reason in levers.CUT_LEVERS.items()]
    lines += [
        "",
        f"Every row records sageattention {levers.SAGEATTENTION_INSTALLED} -- SA1, Triton kernels. "
        "The research puts the first real measurement at SA2.2, whose wheel is not installed, and "
        "installing it in the owner's live ComfyUI venv is not this wave's call (W3-P3). Read every "
        "sage number as SA1.",
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure the optimization matrix through the worker.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="print the matrix and the arm order; render nothing, restart nothing")
    parser.add_argument("--family", action="append", default=[],
                        help="restrict to this family (repeatable)")
    parser.add_argument("--lever", action="append", default=[],
                        help="restrict to this lever (repeatable); the baseline is always included")
    parser.add_argument("--requests", default=None,
                        help='JSON file mapping "family:mode" to a worker request')
    args = parser.parse_args(list(argv) if argv is not None else None)

    steps = arm_sequence(build_matrix(families=args.family or None, lever_ids=args.lever or None))
    requests = load_requests(args.requests)

    if args.dry_run:
        print(describe(steps, requests))
        return 0

    print(
        "Running the live matrix is Task 5. It restarts ComfyUI once per arm and renders for hours,\n"
        "on the stack the owner is using, so this harness refuses to start it from a bare\n"
        "invocation. The plan follows; run it from Task 5 with an explicit request-template file.\n"
    )
    print(describe(steps, requests))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
