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
5. the live install, ``C:/sv_comfynext_v034/ComfyUI``, if it is there;
6. the most recent superseded install, ``C:/sv_comfynext/ComfyUI``, if it is there -- **with a
   warning**, because per CLAUDE.md 9.2 a superseded tree is kept for rollback and is not live;
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

# The 2026-08-31 cutover (Doc 25 S7). LIVE is the v0.34.0 core in its own isolated venv.
LIVE_COMFY = Path("C:/sv_comfynext_v034/ComfyUI")

# Every tree that USED to be live, newest first. Kept as a list rather than a single constant
# because the first cutover taught the lesson the hard way: `prefer_live` matched exactly one
# suffix, `comfy_runtime/ComfyUI`, so it redirected the May build and would have sailed a stale
# `C:/sv_comfynext/ComfyUI` straight through to the superseded core after this cutover -- the very
# failure the function exists to prevent, one generation behind. A list makes the next cutover an
# append rather than an edit to a condition, and it makes rollback two-deep instead of one.
SUPERSEDED_COMFY = (
    Path("C:/sv_comfynext/ComfyUI"),            # v0.27.0, Jul-10 core -- the 2026-07-17 cutover
    Path("D:/AI_ASSETS/comfy_runtime/ComfyUI"),  # cf9cbec5, May build
)

# The tree to fall back to when LIVE is gone. The most recent superseded build, not the oldest.
ROLLBACK_COMFY = SUPERSEDED_COMFY[0]

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


def _superseded_keys() -> tuple[str, ...]:
    return tuple(str(p).replace("\\", "/").lower().rstrip("/") for p in SUPERSEDED_COMFY)


def prefer_live(path: str | Path) -> Path:
    """Redirect a path into ANY superseded tree to the live install, when the live install exists.

    Configuration, saved settings, history metadata and old contracts keep carrying whatever root
    was live when they were written, and following one would run generation against a superseded
    core while everything else talks to the current one. There is no error in that case -- the old
    tree and its venv are still on disk, so every existence check succeeds and the only symptom is
    the wrong core.

    Checked against the whole list rather than one hardcoded suffix. The previous version matched
    only ``comfy_runtime/ComfyUI``, which meant that at the 2026-08-31 cutover a stale
    ``C:/sv_comfynext/ComfyUI`` -- the root that had been live for six weeks and is therefore the
    one most likely to be stored anywhere -- would have passed through untouched.
    """
    candidate = Path(path).expanduser()
    if not LIVE_COMFY.exists():
        return candidate
    key = str(candidate).replace("\\", "/").lower().rstrip("/")
    for superseded in _superseded_keys():
        if key == superseded or key.startswith(superseded + "/"):
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

    # Walk the superseded trees newest-first. Rollback became two-deep at the 2026-08-31 cutover,
    # and a single constant would have skipped the v0.27.0 tree entirely to land on the May build --
    # two generations back, silently, because both still exist on disk.
    for superseded in SUPERSEDED_COMFY:
        if not superseded.exists():
            continue
        # Reachable, but never quietly. CLAUDE.md 9.2 keeps these trees for rollback only, and a
        # readiness check or a node install that lands here while the live install is the one
        # actually serving :8188 produces answers about the wrong ComfyUI.
        log.warning(
            "Falling back to a ROLLBACK ComfyUI at %s -- the live install at %s is not present. "
            "Set SPELLVISION_COMFY if this is not what you want.",
            superseded, LIVE_COMFY,
        )
        return superseded.resolve()

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
