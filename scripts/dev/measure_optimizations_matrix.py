"""The matrix: which cells exist, in what order their arms run, and what the plan looks like.

Separated from the entry point so neither file grows past the size where a reader stops reading it.
Two decisions live here and both are about what a row can mean:

**The baseline is never optional.** Narrowing to one lever still measures the baseline it is
compared against, because ``baseline_mean`` travels WITH the row -- there is no later lookup, and a
delta computed against a baseline from another session or another build is how a 3% gap gets
published over a 30% spread.

**A lever only appears where it does something.** ``--fast fp8_matrix_mult`` is inert on a bf16
checkpoint, so a cell for it elsewhere would report the measurement noise of an unchanged
configuration as a delta.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import measure_optimizations_render as render
import optimization_levers as levers

MAX_SEED = render.MAX_SEED

RUNS_PER_CELL = 3  # one discarded, then two timed.



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
        RunPlan(index=index, seed=render.fresh_seed(), warm=index > 0)
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
