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


class RuntimePaths:
    ROOT = Path(__file__).resolve().parent.parent

    ASSET_ROOT = _env_path("SPELLVISION_ASSETS", Path("D:/AI_ASSETS"))
    MODELS = _optional_env_path("SPELLVISION_MODELS")
    # LIVE Comfy (2026-07-17 cutover). Env SPELLVISION_COMFY wins; D: comfy_runtime is rollback only.
    _live_comfy = Path("C:/sv_comfynext/ComfyUI")
    _rollback_comfy = Path("D:/AI_ASSETS/comfy_runtime/ComfyUI")
    COMFY = _env_path(
        "SPELLVISION_COMFY",
        _live_comfy if _live_comfy.exists() else (_rollback_comfy if _rollback_comfy.exists() else ASSET_ROOT / "comfy_runtime" / "ComfyUI"),
    )
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