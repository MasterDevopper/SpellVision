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
the pixels live in ``measure_optimizations_quality``; the matrix and the arm order live in
``measure_optimizations_matrix``; one render and the resume check live in
``measure_optimizations_render``; the loop that spends the hours lives in
``measure_optimizations_run``. This module owns the CLI.

**A seventh discipline, added once the six above were in place: give the stack back.** Every arm
restarts a ComfyUI this harness does not own. Before this, nothing restored it, so the harness left
the owner's stack in whatever arm ran last -- and an interrupted run (their own Ctrl+C) stranded it
in an arbitrary one. ``measure_optimizations_restore`` captures the running argv before the first
restart and hands it back in a ``finally`` around the arm loop, on every exit: normal completion, an
exception, or ``KeyboardInterrupt``. Where the starting state cannot be expressed as an arm --
no attention flag at all is not the same as pinning ``{"attention": "sdpa"}`` -- it says so rather
than claiming a fidelity it did not perform, and a restore that itself fails is reported, not
swallowed.

**The live matrix runs from here.** It restarts the owner's ComfyUI once per arm and renders for
hours, so it needs an explicit ``--requests`` file: a run with nothing to render still refuses, and
the harness never invents a request. Rows are appended as each cell finishes, a re-run skips what
the ledger already holds on matching provenance, and the arm loop runs inside
``run_arms_with_restore`` so the stack is handed back on every exit.

    python scripts/dev/measure_optimizations.py --dry-run
    python scripts/dev/measure_optimizations.py --dry-run --family krea2 --lever sage_attention
    python scripts/dev/measure_optimizations.py --family krea2 --family ltx \\
        --requests runtime/optimization_requests.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import measure_optimizations_link as link  # noqa: E402,F401  (the live path's transport)
from measure_optimizations_rows import (  # noqa: E402
    ArmVerification,
    Baseline,
    RunResult,
    build_rows,
    measure_quality,
    quality_verdict,
    verify_arm,
)
from measure_optimizations_restore import (  # noqa: E402
    RestoreResult,
    StartingState,
    capture_starting_state,
    describe_restore,
    describe_starting_state,
    restore_starting_state,
    run_arms_with_restore,
)
import measure_optimizations_render as render  # noqa: E402,F401  (re-exported)
import measure_optimizations_run as runner  # noqa: E402
import optimization_results as ledger  # noqa: E402
from measure_optimizations_matrix import (  # noqa: E402
    MAX_SEED,
    RUNS_PER_CELL,
    ArmStep,
    Cell,
    RunPlan,
    arm_sequence,
    build_matrix,
    describe,
    load_requests,
    runs_for_cell,
)

# Re-exported so one import reaches the whole harness: the tests, and any later reader, address
# `measure_optimizations.X` rather than having to know which of the seven modules X lives in.
__all__ = [
    "ArmStep", "ArmVerification", "Baseline", "Cell", "DEFAULT_OUT_DIR", "MAX_SEED",
    "RUNS_PER_CELL", "RestoreResult", "RunPlan", "RunResult", "StartingState", "arm_sequence",
    "build_matrix", "build_rows", "capture_starting_state", "describe", "describe_restore",
    "describe_starting_state", "ledger", "link", "main", "measure_quality", "quality_verdict",
    "render", "restore_starting_state", "run_arms_with_restore", "runner", "runs_for_cell",
    "session_secret", "verify_arm",
]

# Where the harness's own renders land. Deliberately NOT the owner's gallery: an hours-long matrix
# writes a hundred plates whose only purpose is to be measured, and a run that fills the folder the
# owner actually looks at has made itself expensive to run twice.
DEFAULT_OUT_DIR = ROOT / "runtime" / "optimization_renders"


def session_secret(port: int, override: str | None = None) -> str:
    """The per-launch secret every non-probe worker command must carry (security pass v1).

    Resolved the way any client resolves it -- environment, then the file the running worker
    published for that port -- because this harness does not spawn the worker, it borrows the one
    the owner is already running.
    """
    if override:
        return link.session_secret(override)
    try:
        from worker_auth import read_session_secret

        return read_session_secret(port)
    except Exception:  # noqa: BLE001 -- an unreadable secret is a refusal from the worker, not a crash here.
        import os

        return link.session_secret(os.environ.get(link.SESSION_FILE_ENV))


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
    parser.add_argument("--force", action="store_true",
                        help="re-measure cells the ledger already holds a matching warm row for")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR),
                        help=f"where this run's renders land (default: {DEFAULT_OUT_DIR})")
    parser.add_argument("--artefact-guard", action="store_true",
                        help="add one untimed render per cell at a seed shared with the baseline "
                             "cell, so the artefact guard has an equal-seed comparison; without it "
                             "that guard reports not_measured and excludes its rows")
    parser.add_argument("--host", default=link.HOST, help="worker host")
    parser.add_argument("--port", type=int, default=link.PORT, help="worker port")
    parser.add_argument("--session-file", default=None,
                        help="the worker's session-secret file, when it is not where a client "
                             "would look for it")
    parser.add_argument("--timeout", type=float, default=1800.0,
                        help="seconds to wait on one worker request; a render is the unit here, so "
                             "this is deliberately long")
    args = parser.parse_args(list(argv) if argv is not None else None)

    steps = arm_sequence(build_matrix(families=args.family or None, lever_ids=args.lever or None))
    requests = load_requests(args.requests)

    if args.dry_run:
        print(describe(steps, requests))
        return 0

    if not requests:
        # The live matrix restarts the owner's ComfyUI once per arm and renders for hours. Starting
        # that with nothing to render is never what anyone meant, so a bare invocation still
        # refuses -- and says what it wanted rather than exiting silently.
        print(
            "Nothing to render: this run has no request templates, and this harness will not "
            "invent one -- a made-up checkpoint or step count would measure a render nobody asked "
            "for.\nPass --requests with a JSON file mapping \"family:mode\" to a real worker "
            "request.\n"
        )
        print(describe(steps, requests))
        return 2

    options = runner.Options(
        requests=requests,
        out_dir=Path(args.out_dir),
        force=args.force,
        artefact_guard=args.artefact_guard,
        link_kwargs={
            "host": args.host,
            "port": args.port,
            "timeout": args.timeout,
            "secret": session_secret(args.port, args.session_file),
        },
    )

    print(describe(steps, requests))
    print(f"LIVE RUN -- {len(steps)} arms, renders to {options.out_dir}, rows appended to "
          f"{ledger.ledger_path()} as each cell finishes.\n")

    try:
        tally = runner.run_matrix(steps, options)
    except runner.RestartFailed as exc:
        # The arm is the independent variable. Nothing measured under an arm that did not launch
        # could be read, so this stops rather than producing rows nobody can interpret -- and the
        # stack was still handed back on the way out of run_arms_with_restore.
        print(f"\nABORTED: {exc}")
        print("  the arm is the independent variable; rows recorded under an arm that did not "
              "launch cannot be interpreted.\n")
        return 1

    print(runner.describe_tally(tally, ledger.ledger_path()))
    return 0 if tally.clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
