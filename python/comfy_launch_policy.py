"""One answer to "how is ComfyUI launched", for the three places that launch it.

Three sites started the same process with three different command lines, and each was missing
something a sibling had:

                            start_comfy.ps1   build_launch_command   MainWindow.cpp
    --use-sage-attention          yes                 no                  no
    PYTHONUTF8=1                  yes                 no                  yes
    PYTHONIOENCODING=utf-8        yes                 no                  yes

Both gaps are load-bearing.

**SageAttention** was measured on this box at -25.1% per iteration on Wan 2.2 dual-noise and -22.8%
end to end (Doc 25 S5, re-measured with fixed seeds and ComfyUI restarted between configs). Only the
developer's PowerShell launcher passed it. Starting SpellVision the way a user starts it -- the app
launching its own ComfyUI -- gave up that 22-25% on the heaviest path in the product.

**PYTHONUTF8** is not an optimisation. CLAUDE.md 9.2: the Jul-10 RES4LYF pack ships a non-ASCII
character in a matplotlib label that crashes ComfyUI's stderr logging under Windows cp1252, taking
the whole process down. The Python-managed launch set neither variable.

The flag cannot simply be added everywhere, which is why this is a policy and not a constant.
ComfyUI's attention module does ``exit(-1)`` when ``--use-sage-attention`` is passed and the package
is absent (``comfy/ldm/modules/attention.py``) -- so hardcoding it turns a working install without
sageattention into a ComfyUI that dies at startup with the reason in a log file nobody is reading.
The PowerShell launcher defaults to sage unconditionally and gets away with it only because this box
has the package.

So the backend is PROBED, once per interpreter, and the three failure modes are kept distinct:

  * asked for sage, available          -> sage
  * asked for nothing, unavailable     -> SDPA, with a warning naming the pip command
  * asked for sage EXPLICITLY, missing -> refuse here, before launching

The last one matters most. Downgrading a user who explicitly asked for sage would be a silent
substitution of the thing they asked for; letting it through would be ComfyUI exiting with -1 into a
log. Raising names the problem at the point of the decision.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

log = logging.getLogger(__name__)

# The variable every launcher reads to choose a backend. One name, so a user who sets it gets the
# same answer whichever way they start the app.
ATTENTION_ENV_VAR = "SPELLVISION_COMFY_ATTENTION"

SAGE = "sage"
SDPA = "sdpa"

# Spellings accepted for each backend. `pytorch` is what ComfyUI's own banner calls SDPA, and it is
# what a user copying from the log would type.
_SAGE_NAMES = frozenset({"sage", "sageattention", "sage_attention"})
_SDPA_NAMES = frozenset({"sdpa", "pytorch", "torch", "none", "off", "default"})

SAGE_FLAG = "--use-sage-attention"

# Required for every ComfyUI launch, not optional and not a tuning choice. See the module docstring.
REQUIRED_ENV: dict[str, str] = {
    "PYTHONUTF8": "1",
    "PYTHONIOENCODING": "utf-8",
}

_PROBE_CACHE: dict[str, bool] = {}


def normalize_backend(value: Any) -> str | None:
    """The backend a spelling names, or None if it names none.

    Returns None for an empty value so "unset" stays distinguishable from "explicitly asked for
    something"; the two take different branches when the package is missing.
    """
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text in _SAGE_NAMES:
        return SAGE
    if text in _SDPA_NAMES:
        return SDPA
    log.warning(
        "Unknown %s value %r; expected one of %s. Falling back to automatic selection.",
        ATTENTION_ENV_VAR, value, sorted(_SAGE_NAMES | _SDPA_NAMES),
    )
    return None


def sageattention_available(python_executable: str | Path | None = None) -> bool:
    """Whether ``import sageattention`` succeeds in the interpreter that will run ComfyUI.

    ComfyUI runs from its OWN venv (CLAUDE.md 9.2 -- isolated since the 2026-07-17 cutover), so
    asking this process is the wrong question: the worker's venv and Comfy's venv are decoupled and
    only one of them needs the package.

    Cached per interpreter path. Answering costs a subprocess; a ComfyUI launch happens once per
    session, but readiness checks ask far more often than that.
    """
    exe = str(python_executable or sys.executable)
    if exe in _PROBE_CACHE:
        return _PROBE_CACHE[exe]
    available = False
    try:
        completed = subprocess.run(
            [exe, "-c", "import sageattention"],
            capture_output=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        available = completed.returncode == 0
    except (OSError, subprocess.SubprocessError) as exc:
        # Could not ask. Report unavailable rather than assume either way: the optimistic answer
        # costs a ComfyUI that exits -1, and the answer is re-derived on the next launch anyway.
        log.warning("Could not probe sageattention with %s: %s", exe, exc)
    _PROBE_CACHE[exe] = available
    return available


def resolve_attention_backend(
    python_executable: str | Path | None = None,
    *,
    explicit: Any = None,
    probe: bool = True,
) -> tuple[str, str]:
    """``(backend, reason)`` -- the backend to launch with, and why, for logging.

    Raises ``RuntimeError`` when sage is asked for by name and the package is missing. See the
    module docstring for why that case refuses instead of downgrading.
    """
    requested = normalize_backend(explicit)
    source = "argument"
    if requested is None:
        requested = normalize_backend(os.environ.get(ATTENTION_ENV_VAR))
        source = ATTENTION_ENV_VAR

    if requested == SDPA:
        return SDPA, f"{source} selected pytorch SDPA"

    if not probe:
        return SAGE, f"{source} selected sageattention (unprobed)" if requested == SAGE else (
            "default (unprobed)")

    available = sageattention_available(python_executable)
    exe = python_executable or sys.executable

    if requested == SAGE:
        if not available:
            raise RuntimeError(
                f"{source} asked for sageattention, and `import sageattention` fails in {exe}. "
                f"ComfyUI exits with -1 when {SAGE_FLAG} is passed without the package, so this "
                f"refuses before launching. Install it with `{exe} -m pip install sageattention`, "
                f"or set {ATTENTION_ENV_VAR}=sdpa."
            )
        return SAGE, f"{source} selected sageattention"

    if available:
        return SAGE, "default (sageattention is installed; ~25% on Wan)"
    log.warning(
        "sageattention is not installed in %s; ComfyUI will run on pytorch SDPA. Measured on this "
        "box, sageattention is ~25%% faster per iteration on Wan 2.2 dual-noise. Install it with "
        "`%s -m pip install sageattention`, or set %s=sdpa to silence this.",
        exe, exe, ATTENTION_ENV_VAR,
    )
    return SDPA, "default (sageattention is not installed)"


def attention_args(backend: str) -> list[str]:
    """The ComfyUI CLI arguments a backend needs. SDPA is ComfyUI's default and names no flag."""
    return [SAGE_FLAG] if backend == SAGE else []


def launch_args(
    python_executable: str | Path | None = None,
    *,
    explicit: Any = None,
    probe: bool = True,
) -> list[str]:
    """The policy's contribution to a ComfyUI command line."""
    backend, reason = resolve_attention_backend(python_executable, explicit=explicit, probe=probe)
    log.warning("ComfyUI attention backend: %s -- %s", backend, reason)
    return attention_args(backend)


def launch_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """``base`` (default the current environment) with the required variables applied.

    They are applied, not defaulted: a stale ``PYTHONIOENCODING`` inherited from a parent shell is
    exactly the case that crashes stderr logging.
    """
    env = dict(os.environ if base is None else base)
    env.update(REQUIRED_ENV)
    return env
