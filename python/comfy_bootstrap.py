from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

DEFAULT_COMFY_HOST = os.environ.get("SPELLVISION_COMFY_HOST", "127.0.0.1")
DEFAULT_COMFY_PORT = int(os.environ.get("SPELLVISION_COMFY_PORT", "8188"))
DEFAULT_MANAGER_REPO = os.environ.get("SPELLVISION_COMFY_MANAGER_REPO", "https://github.com/Comfy-Org/ComfyUI-Manager.git")


def spellvision_root(anchor: str | Path | None = None) -> Path:
    if anchor is None:
        return Path(__file__).resolve().parent.parent

    anchor_path = Path(anchor).resolve()
    probe = anchor_path if anchor_path.is_dir() else anchor_path.parent

    # If the caller passed a managed Comfy path like:
    #   <repo>/runtime/comfy/ComfyUI
    # or:
    #   <repo>/runtime/comfy
    # walk back up to the actual SpellVision project root.
    parts_lower = [part.lower() for part in probe.parts]
    for marker in ("runtime", "comfy"):
        if marker in parts_lower:
            pass
    if len(parts_lower) >= 3 and parts_lower[-3:] == ["runtime", "comfy", "comfyui"]:
        return probe.parent.parent.parent
    if len(parts_lower) >= 2 and parts_lower[-2:] == ["runtime", "comfy"]:
        return probe.parent.parent

    if (probe / "runtime" / "comfy").exists() or (probe / ".venv").exists():
        return probe

    for parent in [probe, *probe.parents]:
        if (parent / "runtime" / "comfy").exists() or (parent / ".venv").exists():
            return parent

    return Path(__file__).resolve().parent.parent


def runtime_root(root: str | Path | None = None) -> Path:
    return spellvision_root(root) / "runtime"


def comfy_runtime_root(root: str | Path | None = None) -> Path:
    return runtime_root(root) / "comfy"


def default_comfy_root(root: str | Path | None = None) -> Path:
    return comfy_runtime_root(root) / "ComfyUI"

def resolve_managed_comfy_python(
    root: str | Path | None = None,
    explicit_python: str | None = None,
) -> str:
    candidates: list[Path] = []

    if explicit_python:
        candidates.append(Path(str(explicit_python)).expanduser())
    override = os.environ.get("SPELLVISION_COMFY_PYTHON", "").strip()
    if override:
        candidates.append(Path(override).expanduser())

    venv_python = project_venv_python(root)
    if venv_python is not None:
        candidates.append(venv_python)

    if sys.executable:
        candidates.append(Path(sys.executable))

    for candidate in candidates:
        try:
            if candidate.exists():
                return str(candidate.resolve())
        except Exception:
            pass

    return sys.executable


def project_venv_python(root: str | Path | None = None) -> Path | None:
    base = spellvision_root(root)
    candidates = [
        base / ".venv" / "Scripts" / "python.exe",
        base / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def default_comfy_python(root: str | Path | None = None) -> str:
    override = os.environ.get("SPELLVISION_COMFY_PYTHON")
    if override:
        return override
    venv_python = project_venv_python(root)
    if venv_python is not None:
        return str(venv_python)
    return sys.executable


def state_file_path(comfy_root: str | Path | None = None) -> Path:
    root = Path(comfy_root) if comfy_root else default_comfy_root()
    return root.parent / "spellvision_comfy_state.json"


def logs_dir_path(comfy_root: str | Path | None = None) -> Path:
    root = Path(comfy_root) if comfy_root else default_comfy_root()
    return root.parent / "logs"


def ensure_runtime_layout(comfy_root: str | Path | None = None) -> dict[str, str]:
    root = Path(comfy_root) if comfy_root else default_comfy_root()
    root.parent.mkdir(parents=True, exist_ok=True)
    logs = logs_dir_path(root)
    logs.mkdir(parents=True, exist_ok=True)
    layout = {
        "runtime_root": str(root.parent),
        "comfy_root": str(root),
        "logs_dir": str(logs),
        "state_file": str(state_file_path(root)),
    }
    return layout


def detect_comfy_entrypoint(comfy_root: str | Path | None = None) -> Path | None:
    root = Path(comfy_root) if comfy_root else default_comfy_root()
    candidates = [
        root / "main.py",
        root / "server.py",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def detect_manager_dir(comfy_root: str | Path | None = None) -> Path | None:
    root = Path(comfy_root) if comfy_root else default_comfy_root()
    candidates = [
        root / "custom_nodes" / "ComfyUI-Manager",
        root / "custom_nodes" / "comfyui-manager",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def build_launch_command(
    comfy_root: str | Path | None = None,
    *,
    python_executable: str | None = None,
    host: str = DEFAULT_COMFY_HOST,
    port: int = DEFAULT_COMFY_PORT,
    extra_args: list[str] | None = None,
) -> list[str]:
    root = Path(comfy_root) if comfy_root else default_comfy_root()
    entry = detect_comfy_entrypoint(root)
    if entry is None:
        return []
    python_path = resolve_managed_comfy_python(root, python_executable)
    command = [python_path, str(entry), "--listen", host, "--port", str(port), "--dont-print-server"]
    if extra_args:
        command.extend(extra_args)
    return command


def bootstrap_comfy_runtime(
    comfy_root: str | Path | None = None,
    *,
    python_executable: str | None = None,
    host: str = DEFAULT_COMFY_HOST,
    port: int = DEFAULT_COMFY_PORT,
    create_dirs: bool = True,
) -> dict[str, Any]:
    root = Path(comfy_root) if comfy_root else default_comfy_root()
    layout = ensure_runtime_layout(root) if create_dirs else {
        "runtime_root": str(root.parent),
        "comfy_root": str(root),
        "logs_dir": str(logs_dir_path(root)),
        "state_file": str(state_file_path(root)),
    }
    entry = detect_comfy_entrypoint(root)
    manager_dir = detect_manager_dir(root)
    resolved_python = resolve_managed_comfy_python(root, python_executable)
    launch_cmd = build_launch_command(root, python_executable=resolved_python, host=host, port=port)
    models_root = root / "models"
    input_root = root / "input"
    output_root = root / "output"
    custom_nodes_root = root / "custom_nodes"

    payload: dict[str, Any] = {
        "ok": bool(entry),
        "installed": bool(entry),
        "ready_to_launch": bool(entry),
        "message": "ComfyUI runtime detected." if entry else "Managed ComfyUI runtime is not installed yet.",
        **layout,
        "entrypoint": str(entry) if entry else None,
        "manager_dir": str(manager_dir) if manager_dir else None,
        "manager_present": bool(manager_dir),
        "models_root": str(models_root),
        "input_root": str(input_root),
        "output_root": str(output_root),
        "custom_nodes_root": str(custom_nodes_root),
        "python_executable": resolved_python,
        "host": host,
        "port": int(port),
        "endpoint": f"http://{host}:{int(port)}",
        "recommended_command": launch_cmd,
        "manager_repo": DEFAULT_MANAGER_REPO,
    }
    return payload
