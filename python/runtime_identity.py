"""One runtime-identity tuple for SpellVision.

Worker Python and Comfy Python are different interpreters. A path that
*exists* is not enough — it must be a regular file. This module is the
Python-side SSOT; the Qt RuntimeProfile mirrors the same precedence.
"""

from __future__ import annotations

import os
from pathlib import Path


LIVE_COMFY = Path("C:/sv_comfynext/ComfyUI")
ROLLBACK_COMFY = Path("D:/AI_ASSETS/comfy_runtime/ComfyUI")


def is_regular_executable(path: str | Path | None) -> bool:
    if not path:
        return False
    try:
        candidate = Path(path).expanduser()
        return candidate.is_file() and not candidate.is_dir()
    except OSError:
        return False


def _first_regular_file(candidates: list[str | Path | None]) -> Path | None:
    seen: set[str] = set()
    for raw in candidates:
        if not raw:
            continue
        try:
            candidate = Path(raw).expanduser()
        except (TypeError, ValueError):
            continue
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if is_regular_executable(candidate):
            return candidate.resolve()
    return None


def resolve_worker_python(
    project_root: str | Path,
    *,
    explicit: str | Path | None = None,
) -> Path | None:
    root = Path(project_root)
    virtual_env = os.environ.get("VIRTUAL_ENV", "").strip()
    return _first_regular_file(
        [
            explicit,
            os.environ.get("SPELLVISION_WORKER_PYTHON", "").strip() or None,
            Path(virtual_env) / "Scripts" / "python.exe" if virtual_env else None,
            Path(virtual_env) / "bin" / "python" if virtual_env else None,
            root / ".venv" / "Scripts" / "python.exe",
            root / ".venv" / "bin" / "python",
        ]
    )


def _prefer_live_comfy(path: Path) -> Path:
    candidate = Path(path).expanduser()
    if LIVE_COMFY.exists():
        key = str(candidate).replace("\\", "/").lower()
        if key.endswith("/comfy_runtime/comfyui") or "/comfy_runtime/comfyui" in key:
            return LIVE_COMFY.resolve()
    return candidate


def resolve_comfy_root(
    project_root: str | Path | None = None,
    *,
    explicit: str | Path | None = None,
) -> Path:
    if explicit:
        return _prefer_live_comfy(Path(explicit)).resolve()
    override = os.environ.get("SPELLVISION_COMFY", "").strip()
    if override:
        return _prefer_live_comfy(Path(override)).resolve()
    if LIVE_COMFY.exists():
        return LIVE_COMFY.resolve()
    if ROLLBACK_COMFY.exists():
        return ROLLBACK_COMFY.resolve()
    base = Path(project_root) if project_root else Path(__file__).resolve().parent.parent
    return (base / "runtime" / "comfy" / "ComfyUI").resolve()


def resolve_comfy_python(
    comfy_root: str | Path,
    *,
    explicit: str | Path | None = None,
) -> Path | None:
    """Never fall back to the worker / controller interpreter."""
    root = Path(comfy_root)
    return _first_regular_file(
        [
            explicit,
            os.environ.get("SPELLVISION_COMFY_PYTHON", "").strip() or None,
            root.parent / ".venv" / "Scripts" / "python.exe",
            root.parent / ".venv" / "bin" / "python",
            root / "venv" / "Scripts" / "python.exe",
            root / "venv" / "bin" / "python",
        ]
    )


def resolve_models_root(*, explicit: str | Path | None = None) -> Path | None:
    if explicit:
        return Path(explicit).expanduser().resolve()
    override = os.environ.get("SPELLVISION_MODELS", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return None


def identity_dict(
    project_root: str | Path,
    *,
    worker_python: str | Path | None = None,
    comfy_root: str | Path | None = None,
    comfy_python: str | Path | None = None,
    models_root: str | Path | None = None,
) -> dict[str, str]:
    root = Path(project_root)
    comfy = resolve_comfy_root(root, explicit=comfy_root)
    worker = resolve_worker_python(root, explicit=worker_python)
    comfy_py = resolve_comfy_python(comfy, explicit=comfy_python)
    models = resolve_models_root(explicit=models_root)
    return {
        "project_root": str(root.resolve()),
        "worker_python": str(worker) if worker else "",
        "worker_script": str((root / "python" / "worker_service.py").resolve()),
        "comfy_root": str(comfy),
        "comfy_python": str(comfy_py) if comfy_py else "",
        "models_root": str(models) if models else "",
    }


def resolve_comfy_python_from_request(req: dict | None = None) -> str:
    """Comfy interpreter only. Never honor worker ``python_executable``."""
    req = req or {}
    comfy_root = req.get("comfy_root") or resolve_comfy_root()
    explicit = req.get("comfy_python_executable")
    resolved = resolve_comfy_python(comfy_root, explicit=explicit)
    return str(resolved) if resolved else ""

