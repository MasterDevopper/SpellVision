"""Where everything lives on this machine, and which env var can move it.

One resolver for the ComfyUI root, the models root, outputs, and the imported-workflow library, so
a path is never re-derived (and re-derived differently) at a call site.

Roots are forked in practice and CLAUDE.md section 9 is the record: assets live under
``D:/AI_ASSETS``, the live ComfyUI install is ``C:/sv_comfynext_v034/ComfyUI`` after the 2026-08-31
cutover, and ``default_comfy_root()`` here is drift that nothing should rely on. Prefer the
environment override, and treat a disagreement between this module and section 9 as a bug in one of
them rather than a choice.
"""
from __future__ import annotations

import os
from pathlib import Path


def _env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name, "").strip()
    path = Path(raw).expanduser() if raw else default
    try:
        return path.resolve()
    except OSError:
        return path


def _optional_env_path(name: str) -> Path | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    try:
        return path.resolve()
    except OSError:
        return path


from comfy_root import comfy_root
class RuntimePaths:
    ROOT = Path(__file__).resolve().parent.parent

    ASSET_ROOT = _env_path("SPELLVISION_ASSETS", Path("D:/AI_ASSETS"))
    MODELS = _optional_env_path("SPELLVISION_MODELS")
    # The install root, from the one resolver. This class used to make the live/rollback decision
    # itself, with its own copy of both literals -- a second implementation of the same precedence
    # that had already drifted from the others by the time anyone looked.
    COMFY = comfy_root()
    TRELLIS = _env_path("SPELLVISION_TRELLIS", ASSET_ROOT / "trellis" / "Trellis")
    CACHE = _env_path("SPELLVISION_CACHE", ASSET_ROOT / "cache")
    LOGS = _env_path("SPELLVISION_LOGS", ASSET_ROOT / "logs")
    DATASETS = _env_path("SPELLVISION_DATASETS", ASSET_ROOT / "datasets")
    ASSET_CACHE = _env_path("SPELLVISION_ASSET_CACHE", CACHE / "assets")

    @classmethod
    def ensure_runtime_dirs(cls) -> None:
        for path in (
            cls.ASSET_ROOT,
            cls.MODELS,
            cls.CACHE,
            cls.LOGS,
            cls.DATASETS,
            cls.ASSET_CACHE,
        ):
            if path:
                path.mkdir(parents=True, exist_ok=True)