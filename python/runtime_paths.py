from __future__ import annotations

import os
from pathlib import Path


def _env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name, "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return default.resolve()


class RuntimePaths:
    ROOT = Path(__file__).resolve().parent.parent

    ASSET_ROOT = _env_path("SPELLVISION_ASSETS", ROOT / "external_assets")
    MODELS = _env_path("SPELLVISION_MODELS", ASSET_ROOT / "models")
    COMFY = _env_path("SPELLVISION_COMFY", ASSET_ROOT / "comfy_runtime" / "ComfyUI")
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
            path.mkdir(parents=True, exist_ok=True)