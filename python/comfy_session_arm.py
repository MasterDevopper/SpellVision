"""The launch arm this worker session last started ComfyUI with.

A launch "arm" is a named configuration -- ``{"attention": "sdpa"}``, ``{"dynamic_vram": False}``,
``{"vram_headroom": 22.0}`` -- that ``comfy_launch_policy.arm_args`` turns into ComfyUI CLI flags.
``restart_comfy_runtime`` can ask for one, so an optimization can be timed against the same job with
and without it.

**The defect this module exists to close.** Observed in a live run, in
``build/worker_service.stderr.log``::

    ComfyUI attention backend (arm): sdpa -- argument selected pytorch SDPA
    ComfyUI VRAM headroom (arm): ComfyUI's own OS-dependent reservation (no flag)
    ComfyUI attention backend: sage -- default (sageattention is installed; ~25% on Wan)
    Invalidated cached ComfyUI /object_info: extra_model_paths.yaml changed

A later request rewrote ``extra_model_paths.yaml``; ``handle_ensure_comfy_runtime_command`` restarts
ComfyUI when that file changes, because ComfyUI reads it only at startup. That restart passed no
arm, so the launch policy resolved attention from the environment -- and this box has sageattention
installed, so the default is sage. The SDPA the caller explicitly asked for was replaced with sage,
with nothing in the reply or the UI saying so.

That is not only a measurement problem. A user who adds a model library mid-session gets the same
silent restart: renders before and after it ran on different attention backends, and nothing records
why. The measurement case is merely where it was visible, because the arm was written down.

**Why the memory is a module and not an attribute.** ``worker_service.get_comfy_runtime_manager``
REBUILDS the ``ComfyRuntimeManager`` whenever comfy_root / host / port / python differ from the
cached one -- including when a re-resolution merely spells the same interpreter differently. An
attribute would be dropped by exactly the incidental rebuild that separates an armed start from the
yaml-triggered restart that follows it, i.e. the memory would be worthless precisely when it
matters. There is one ComfyUI per worker session; the manager object is a rebuildable *view* of it,
not its owner, so the launch configuration belongs to the session.

**Three states, kept distinct.** "No arm given" (reuse what the session was launched with), "this
arm" (use and remember it), and "explicitly the default arm" (forget, and go back to the
environment). An empty mapping is the third, which is why emptiness is not treated as absence here:
``None`` and ``{}`` mean different things and are resolved on different branches.
"""
from __future__ import annotations

import threading
from typing import Any, Mapping

_LOCK = threading.RLock()
_ARM: dict[str, Any] | None = None

# Why a launch is configured the way it is, in the words the stderr log uses. The attention/VRAM
# lines are the only reason the defect above was findable, so a remembered arm has to be visible
# in them as a remembered arm -- not as an ordinary one, and certainly not as a default.
EXPLICIT = "arm"
REMEMBERED = "remembered arm"
DEFAULT = "no arm -- environment defaults"
EXPLICIT_DEFAULT = "explicit default arm -- environment defaults"


def remembered_arm() -> dict[str, Any] | None:
    """A copy of the arm the session was last launched with, or ``None`` if there is none."""
    with _LOCK:
        return dict(_ARM) if _ARM is not None else None


def remember_arm(arm: Mapping[str, Any] | None) -> None:
    """Record ``arm`` as the session's arm. An empty or ``None`` arm forgets instead."""
    global _ARM
    with _LOCK:
        _ARM = dict(arm) if arm else None


def forget_arm() -> None:
    """Go back to the environment on the next armless launch."""
    remember_arm(None)


def resolve_launch_arm(requested: Mapping[str, Any] | None) -> tuple[dict[str, Any] | None, str]:
    """``(arm_to_launch, why)`` for one launch, updating the session's memory.

    ``requested is None`` -- nobody named an arm -- reuses the remembered one, and falls through to
    the environment only when there is nothing to remember (the first launch of a session).

    ``requested == {}`` is an explicit request for the default arm: it forgets, and returns ``None``
    so the caller walks the byte-for-byte default branch of ``build_launch_command`` rather than an
    ``arm_args({})`` that computes the same flags by a different route.
    """
    if requested is None:
        remembered = remembered_arm()
        if remembered is not None:
            return remembered, REMEMBERED
        return None, DEFAULT
    if not requested:
        forget_arm()
        return None, EXPLICIT_DEFAULT
    arm = dict(requested)
    remember_arm(arm)
    return arm, EXPLICIT
