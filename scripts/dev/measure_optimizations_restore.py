"""Give the owner's ComfyUI back exactly as found, on every exit from the arm loop.

This harness reconfigures a machine it does not own. Every arm restarts the owner's live ComfyUI
into a launch configuration chosen for the measurement, not for the owner -- and before Task 4, the
harness had no way back: it left the stack in whatever arm ran last, and an interrupted run (the
operator's own Ctrl+C is the likeliest interruption there is) stranded it in an arbitrary one. A
tool that borrows someone else's running process has to return it, not just stop touching it.

Three pieces:

**Capture, before the first restart.** ``capture_starting_state`` reads the running process's argv
back from ``optimization_provenance.probe()`` -- the same read-only ``GET /system_stats`` the rows
module already trusts more than any launch script's intent (the Qt sage probe fails open to SDPA on
a cold launch; only the live process is evidence).

**Restore, on every exit.** ``run_arms_with_restore`` wraps the arm loop in a bare ``try/finally``:
normal completion, an exception out of a step, and ``KeyboardInterrupt`` all reach the same
``finally``, because Python raises ``KeyboardInterrupt`` the same way it raises anything else and a
``finally`` does not care which. Nothing here needs its own signal handling.

**The one subtlety.** The starting state may not be expressible as an arm. This box's ComfyUI is
usually running with no attention flag at all, and ``{"attention": "sdpa"}`` is not that -- one
leaves the core to choose (today: sage, because sageattention is installed), the other pins SDPA
explicitly (``comfy_launch_policy.arm_args``). Where the closest arm cannot carry a field over,
``StartingState.unreproducible`` names it, and every printed report says so -- a restore that claims
fidelity it did not perform is worse than one that admits the gap, for the same reason a guard that
says "pass" because nothing measured it is worse than no guard.

A failed restore is reported, never swallowed: ``restore_starting_state`` catches its own transport
errors rather than letting them replace whatever exception sent the harness to ``finally`` in the
first place, and ``run_arms_with_restore`` always prints the outcome before propagating.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

import comfy_launch_policy
import optimization_provenance as provenance_probe

import measure_optimizations_link as link
from measure_optimizations_rows import ArmVerification, verify_arm

# Every field _closest_arm can try to carry over, in report order. Also the "everything is
# unreproducible" answer when the probe itself failed -- there is no partial credit for a state that
# was never read.
RESTORE_FIELDS: tuple[str, ...] = ("attention", "fast", "dynamic_vram", "vram_headroom")


@dataclass(frozen=True)
class StartingState:
    """What ComfyUI was running before the first restart, and the closest arm that gets back to it."""

    probe: dict[str, Any]
    restore_arm: dict[str, Any]
    unreproducible: tuple[str, ...]


@dataclass(frozen=True)
class RestoreResult:
    """What actually happened when the harness tried to hand the stack back -- never an exception."""

    attempted: bool
    ok: bool
    reason: str
    starting: StartingState
    verification: ArmVerification | None = None
    reply: dict[str, Any] = field(default_factory=dict)


def _attention_arm(argv: Sequence[str]) -> tuple[str | None, bool]:
    """``(value_for_the_arm, reproducible)``.

    ``None`` with ``reproducible=False`` means: no explicit flag was in the running argv, so the
    process was launched leaving ComfyUI's own policy to choose. Omitting the "attention" key routes
    a restore through that same policy -- the closest available action -- but it is a best effort,
    not a faithful restore: the policy's choice depends on what is installed and probed AT RESTORE
    TIME, not what was true when the original process launched.
    """
    argv = list(argv)
    if comfy_launch_policy.SAGE_FLAG in argv:
        return "sage", True
    if comfy_launch_policy.PYTORCH_ATTENTION_FLAG in argv:
        return "sdpa", True
    return None, False


def _closest_arm(block: dict[str, Any]) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Best-effort arm to restore this probe block to, and which fields it could not carry over."""
    if block.get("probe_error") or not block.get("comfy_argv"):
        return {}, RESTORE_FIELDS

    arm: dict[str, Any] = {}
    unreproducible: list[str] = []

    attention, reproducible = _attention_arm(block["comfy_argv"])
    if attention is not None:
        arm["attention"] = attention
    if not reproducible:
        unreproducible.append("attention")

    fast_flags = block.get("fast_flags") or []
    if fast_flags:
        arm["fast"] = list(fast_flags)
    # else: omit the key -- setting "fast": [] would emit a bare --fast, which enables every fast
    # feature (fast_from_argv's own bare-flag rule), not the none the running process had.

    dynamic_vram = block.get("dynamic_vram")
    if dynamic_vram is None:
        unreproducible.append("dynamic_vram")
    else:
        arm["dynamic_vram"] = bool(dynamic_vram)

    reserve = block.get("reserve_vram_gb")
    if reserve is not None:
        arm["vram_headroom"] = float(reserve)

    return arm, tuple(unreproducible)


def capture_starting_state(
    *,
    api_url: str | None = None,
    opener: Any = None,
    comfy_python: str | None = None,
    timeout: float = provenance_probe.DEFAULT_TIMEOUT_SEC,
) -> StartingState:
    """Probe the live ComfyUI before the first restart. Read-only (``GET /system_stats``), so this
    is safe against the owner's running stack -- it is the same call the rows module already makes
    per render."""
    block = provenance_probe.probe(
        api_url, opener=opener, timeout=timeout, force_refresh=True, comfy_python=comfy_python,
    )
    arm, unreproducible = _closest_arm(block)
    return StartingState(probe=block, restore_arm=arm, unreproducible=unreproducible)


def describe_starting_state(state: StartingState) -> str:
    """Printed BEFORE anything restarts, so the operator sees what this run will return to."""
    block = state.probe
    lines = ["", "STARTING STATE -- what this run will restore on exit", ""]
    if block.get("probe_error") or not block.get("comfy_argv"):
        lines.append(
            f"  could not be probed ({block.get('probe_error') or 'no argv in the response'}); "
            "this run cannot promise to restore anything"
        )
        lines.append("")
        return "\n".join(lines)

    lines.append(
        f"  attention={block.get('attention_backend')!r} fast={block.get('fast_flags')} "
        f"dynamic_vram={block.get('dynamic_vram')} reserve_vram_gb={block.get('reserve_vram_gb')}"
    )
    lines.append(f"  argv: {block.get('comfy_argv')}")
    lines.append(f"  will restore to arm: {state.restore_arm}")
    if state.unreproducible:
        lines.append(
            "  CANNOT faithfully reproduce: " + ", ".join(state.unreproducible) +
            " -- restoring the closest arm this harness can ask for, not a byte-identical relaunch"
        )
    lines.append("")
    return "\n".join(lines)


def restore_starting_state(state: StartingState, **link_kwargs: Any) -> RestoreResult:
    """Restart ComfyUI back into the closest arm to where it started.

    Never raises. A restore that failed must be REPORTED -- via the returned ``RestoreResult`` and
    whatever the caller prints from it -- not turned into a second, different exception on top of
    whatever sent the harness to its ``finally`` block in the first place.
    """
    if state.probe.get("probe_error") or not state.probe.get("comfy_argv"):
        reason = (
            "the starting state could not be probed "
            f"({state.probe.get('probe_error') or 'no argv in the response'}), so there is nothing "
            "to restore to -- the stack was left as the last arm left it"
        )
        return RestoreResult(attempted=False, ok=False, reason=reason, starting=state)

    try:
        reply = link.restart_into_arm(state.restore_arm, **link_kwargs)
    except Exception as exc:  # noqa: BLE001 -- report, never let a transport error mask the original.
        return RestoreResult(
            attempted=True, ok=False, reason=f"the restore request itself raised: {exc!r}",
            starting=state,
        )

    verification = verify_arm(state.restore_arm, reply)
    if reply.get("ok") is False:
        reason = reply.get("message") or reply.get("error") or "the restart reply said ok: false"
        return RestoreResult(attempted=True, ok=False, reason=reason, starting=state,
                              verification=verification, reply=reply)
    if not verification.ok:
        return RestoreResult(attempted=True, ok=False, reason=verification.reason, starting=state,
                              verification=verification, reply=reply)
    return RestoreResult(attempted=True, ok=True, reason="", starting=state,
                          verification=verification, reply=reply)


def describe_restore(result: RestoreResult) -> str:
    lines = ["", "RESTORE -- handing the stack back", ""]
    if not result.attempted:
        lines.append(f"  NOT ATTEMPTED: {result.reason}")
    elif result.ok:
        lines.append(f"  restored to arm {result.starting.restore_arm}")
        if result.starting.unreproducible:
            lines.append(
                "  NOTE: " + ", ".join(result.starting.unreproducible) +
                " could not be reproduced -- this is the closest arm, not the original launch"
            )
    else:
        lines.append(f"  FAILED: {result.reason}")
        lines.append("  the stack was NOT confirmed restored -- check ComfyUI (:8188) by hand")
    lines.append("")
    return "\n".join(lines)


def run_arms_with_restore(
    steps: Sequence[Any],
    run_step: Callable[[Any], None],
    *,
    probe_kwargs: dict[str, Any] | None = None,
    link_kwargs: dict[str, Any] | None = None,
    printer: Callable[[str], None] = print,
) -> RestoreResult:
    """Run ``run_step`` once per arm in ``steps``, and hand the stack back on every exit.

    Normal completion, an exception out of ``run_step``, and ``KeyboardInterrupt`` (the operator's
    Ctrl+C -- the likeliest interruption, and exactly when stranding the stack would be worst) all
    reach the same ``finally``; a bare ``try/finally`` needs no special-casing for any of the three,
    because ``KeyboardInterrupt`` propagates through ``finally`` the same as any other exception.

    ``run_step`` is Task 5's render-and-record body, supplied by the caller -- this function owns
    only getting the stack back, not the matrix execution itself.
    """
    starting = capture_starting_state(**(probe_kwargs or {}))
    printer(describe_starting_state(starting))
    try:
        for step in steps:
            run_step(step)
    finally:
        result = restore_starting_state(starting, **(link_kwargs or {}))
        printer(describe_restore(result))
    return result
