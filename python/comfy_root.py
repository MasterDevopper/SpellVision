"""The one place that decides which ComfyUI **install directory** to use.

Sibling of ``comfy_endpoint``, and deliberately the same shape, because it is the same defect one
layer down. Not to be confused with it: the endpoint is an HTTP URL and the root is a directory on
disk. A remote endpoint has no local root at all.

Before this, eight sites resolved the root their own way across four environment-variable names, and
they did not agree in a way that mattered:

* Qt's ``RuntimeProfile`` exports exactly one name, ``SPELLVISION_COMFY``, into every child process.
* ``video_family_readiness`` read exactly two, ``SPELLVISION_COMFY_ROOT`` and ``COMFYUI_ROOT``.

The intersection is empty. So **readiness could never see the configured root**, whatever the user
set, and fell through to its own default -- which on a box with the D: tree present is the ROLLBACK
build that CLAUDE.md 9.2 forbids probing as live. A user pointing SpellVision at one ComfyUI got
readiness answers about a different one, with nothing anywhere saying so.

``ltx_requeue_draft_submission`` went further and hardcoded that rollback path as a literal default.

## Precedence

Highest to lowest, first non-empty wins:

1. an explicit argument -- ``req["comfy_root"]`` or a caller-supplied path;
2. ``SPELLVISION_COMFY`` -- what the Qt shell exports, so this is the configured value in practice;
3. ``SPELLVISION_COMFY_ROOT``;
4. ``COMFYUI_ROOT``;
5. the live install, ``C:/sv_comfynext/ComfyUI``, if it is there;
6. the rollback install, ``D:/AI_ASSETS/comfy_runtime/ComfyUI``, if it is there -- **with a
   warning**, because per CLAUDE.md 9.2 that tree is kept for rollback and is not the live one;
7. ``<projectRoot>/runtime/comfy/ComfyUI``.

Every historical name is honoured, so nothing that worked stops working -- they feed one chain now
instead of four. New configuration should use ``SPELLVISION_COMFY``, which is the name the shell
already exports.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger("spellvision.comfy")

# The 2026-07-17 cutover (Doc 25). LIVE is the Jul-10 core in its own isolated venv; ROLLBACK is the
# May build kept only so the cutover can be undone.
LIVE_COMFY = Path("C:/sv_comfynext/ComfyUI")
ROLLBACK_COMFY = Path("D:/AI_ASSETS/comfy_runtime/ComfyUI")

# In precedence order, kept as data so the ordering is inspectable and testable rather than buried in
# an `or` chain that has to be read carefully to be trusted.
ROOT_ENV_VARS = ("SPELLVISION_COMFY", "SPELLVISION_COMFY_ROOT", "COMFYUI_ROOT")

# Values that mean "nobody filled this in". An unexpanded template leaking through as a literal path
# is how a resolver silently starts pointing at a directory named ``${SPELLVISION_ROOT}``.
_UNRESOLVED_TOKENS = ("${", "%", "<", "todo", "unset", "none")


def _is_unresolved(value: str) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return True
    return any(token in text for token in _UNRESOLVED_TOKENS)


def _clean(value: Any) -> str:
    text = str(value or "").strip().strip('"')
    return "" if _is_unresolved(text) else text


def prefer_live(path: str | Path) -> Path:
    """Redirect a rollback-tree path to the live install when the live install exists.

    A path ending in ``comfy_runtime/ComfyUI`` is the pre-cutover tree. Configuration, saved
    metadata and old contracts still carry it, and following it would run generation against the May
    core while everything else talks to the July one.
    """
    candidate = Path(path).expanduser()
    if not LIVE_COMFY.exists():
        return candidate
    key = str(candidate).replace("\\", "/").lower()
    if key.endswith("/comfy_runtime/comfyui") or "/comfy_runtime/comfyui/" in key:
        return LIVE_COMFY
    return candidate


def comfy_root(
    req: Any = None,
    *,
    explicit: str | Path | None = None,
    project_root: str | Path | None = None,
) -> Path:
    """The ComfyUI install directory for this request. Never empty.

    ``req`` may be a request dict (``comfy_root`` is read from it) or omitted entirely.
    """
    if explicit:
        return prefer_live(explicit).resolve()

    if isinstance(req, dict):
        stated = _clean(req.get("comfy_root") or req.get("comfyui_root"))
        if stated:
            return prefer_live(stated).resolve()

    for name in ROOT_ENV_VARS:
        value = _clean(os.environ.get(name))
        if value:
            return prefer_live(value).resolve()

    if LIVE_COMFY.exists():
        return LIVE_COMFY.resolve()

    if ROLLBACK_COMFY.exists():
        # Reachable, but never quietly. CLAUDE.md 9.2 keeps this tree for rollback only, and a
        # readiness check or a node install that lands here while the live install is the one
        # actually serving :8188 produces answers about the wrong ComfyUI.
        log.warning(
            "Falling back to the ROLLBACK ComfyUI at %s -- the live install at %s is not present. "
            "Set SPELLVISION_COMFY if this is not what you want.",
            ROLLBACK_COMFY, LIVE_COMFY,
        )
        return ROLLBACK_COMFY.resolve()

    base = Path(project_root) if project_root else Path(__file__).resolve().parent.parent
    return (base / "runtime" / "comfy" / "ComfyUI").resolve()


def comfy_user_workflow(name: str, req: Any = None, **kwargs: Any) -> Path:
    """A workflow JSON under ComfyUI's own ``user/default/workflows``.

    Three modules each carried the same literal for the exported LTX graph, all three pointing into
    the ROLLBACK tree. A user on the live install had every one of them looking in a directory that
    is not the one ComfyUI writes to.
    """
    return comfy_root(req, **kwargs) / "user" / "default" / "workflows" / name


def comfy_output_root(req: Any = None, **kwargs: Any) -> Path:
    """Where ComfyUI writes its outputs. Derived, never configured separately.

    Three modules each hardcoded an output directory, two of them under the rollback tree and one
    under the live one -- so which of them found a render depended on which literal it happened to
    carry.
    """
    return comfy_root(req, **kwargs) / "output"
