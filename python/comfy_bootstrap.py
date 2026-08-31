"""ComfyUI runtime path + launch resolution (SpellVision worker).

Owns: pure resolution of the SpellVision repo root and the managed-ComfyUI runtime layout
-- repo / runtime / comfy roots (``spellvision_root``, ``default_comfy_root``), the managed
venv Python (``resolve_managed_comfy_python`` / ``project_venv_python``, following
``SPELLVISION_COMFY_PYTHON`` -> ``.venv`` -> ``sys.executable``), state/log file paths,
directory-layout creation (``ensure_runtime_layout``), entrypoint / ComfyUI-Manager
detection, and the launch command (``build_launch_command`` / ``bootstrap_comfy_runtime``).
Module constants (``DEFAULT_COMFY_HOST`` / ``DEFAULT_COMFY_PORT`` / ``DEFAULT_MANAGER_REPO``)
are env-derived and read-only.

Owns no mutable runtime state -- no caches, registries, or locks; every function is a pure
path/command computation. Depends only on the stdlib. Imported by ``comfy_runtime_manager``
(which drives the actual ComfyUI subprocess) and ``worker_service``.
"""
from __future__ import annotations

from comfy_endpoint import comfy_host, comfy_port

import logging
import os
import sys
from pathlib import Path
from typing import Any
import comfy_launch_policy

log = logging.getLogger(__name__)

DEFAULT_COMFY_HOST = comfy_host()
DEFAULT_COMFY_PORT = comfy_port()
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

def comfy_venv_python(comfy_root: str | Path | None = None) -> Path | None:
    """ComfyUI's OWN interpreter -- the venv beside its install, or one inside it.

    Since the 2026-07-17 cutover (CLAUDE.md 9.2) ComfyUI runs from an ISOLATED venv with kornia
    pinned to 0.8.2 and sageattention installed, decoupled from the worker's `.venv`. Qt's
    RuntimeProfile has always known this and looked here; the Python side did not, and fell through
    to the project venv -- so the two halves disagreed about which interpreter runs ComfyUI, the
    same divergence the comfy-root resolver fixed for the install path.

    Candidate order mirrors RuntimeProfile's exactly, so both halves answer alike.
    """
    if not comfy_root:
        return None
    base = Path(comfy_root)
    for candidate in (
        base.parent / ".venv" / "Scripts" / "python.exe",
        base.parent / ".venv" / "bin" / "python",
        base / "venv" / "Scripts" / "python.exe",
        base / "venv" / "bin" / "python",
    ):
        try:
            if candidate.is_file():
                return candidate.resolve()
        except OSError:
            continue
    return None


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

    # ComfyUI's own venv before the worker's. Launching Comfy with the worker's interpreter runs it
    # against unpinned kornia and without sageattention -- a different program than the one every
    # measurement in this repo was taken against.
    comfy_python = comfy_venv_python(root if root else default_comfy_root())
    if comfy_python is not None:
        candidates.append(comfy_python)

    venv_python = project_venv_python(root)
    if venv_python is not None:
        candidates.append(venv_python)

    if sys.executable:
        candidates.append(Path(sys.executable))

    for candidate in candidates:
        try:
            if candidate.is_file():
                resolved = str(candidate.resolve())
                _warn_if_not_comfys_own_interpreter(resolved, root)
                return resolved
        except Exception:
            pass

    return sys.executable


_REPORTED_FOREIGN_INTERPRETERS: set[tuple[str, str]] = set()


def _warn_if_not_comfys_own_interpreter(resolved: str, root: str | Path | None) -> None:
    """Say so when ComfyUI is about to run on an interpreter that is not its own.

    An explicit override still WINS -- overriding is what an override is for, and a resolver that
    repairs its input cannot be trusted when it disagrees with the user. What it must not do is stay
    quiet, because the two interpreters are two different programs: ComfyUI's venv has kornia pinned
    to 0.8.2 and sageattention installed, and every timing in this repo was measured against it.

    This is not hypothetical. `SPELLVISION_COMFY_PYTHON` is set as a USER variable on the
    development box, still pointing at the project venv from before the 2026-07-17 cutover -- the
    exact sibling of the `SPELLVISION_COMFY` drift that was found and cleared in 2026-08. The
    PowerShell launcher never reads the variable and hardcodes the right venv, so the developer's
    renders were correct while the app's were quietly running somewhere else.
    """
    own = comfy_venv_python(root if root else default_comfy_root())
    if own is None or str(own).lower() == str(resolved).lower():
        return
    # Once per pair, not once per call. This runs on the runtime-STATUS path, which is polled, and
    # a standing condition reported on every poll is not a louder warning -- it is a quieter one,
    # because it trains the reader to skip it. It also deadlocked the worker: the pytest harness
    # gives the worker a stderr PIPE and drains it only at teardown, so a per-poll warning fills the
    # buffer and the process blocks on write, mid-request, with no reply and no error.
    if (resolved.lower(), str(own).lower()) in _REPORTED_FOREIGN_INTERPRETERS:
        return
    _REPORTED_FOREIGN_INTERPRETERS.add((resolved.lower(), str(own).lower()))
    log.warning(
        "ComfyUI will run on %s, which is NOT its own venv (%s). Those are different programs: "
        "ComfyUI's venv carries the pinned kornia and sageattention this repo's timings were "
        "measured against. If this came from SPELLVISION_COMFY_PYTHON, that variable is stale.",
        resolved, own,
    )


def comfy_python_report(root: str | Path | None = None, explicit_python: str | None = None) -> dict[str, Any]:
    """What interpreter ComfyUI will run on, where the answer came from, and whether it is its own.

    Readiness answers "is ComfyUI installed"; this answers "is it the ComfyUI we measured", which is
    a different question and the one that was going unasked.
    """
    resolved = resolve_managed_comfy_python(root, explicit_python)
    own = comfy_venv_python(root if root else default_comfy_root())
    override = os.environ.get("SPELLVISION_COMFY_PYTHON", "").strip()
    if explicit_python:
        source = "explicit argument"
    elif override:
        source = "SPELLVISION_COMFY_PYTHON"
    elif own is not None and str(own).lower() == str(resolved).lower():
        source = "ComfyUI's own venv"
    else:
        source = "project venv or interpreter fallback"
    return {
        "python_executable": resolved,
        "source": source,
        "comfy_own_venv": str(own) if own else "",
        "is_comfy_own_venv": bool(own) and str(own).lower() == str(resolved).lower(),
    }


def project_venv_python(root: str | Path | None = None) -> Path | None:
    base = spellvision_root(root)
    candidates = [
        base / ".venv" / "Scripts" / "python.exe",
        base / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.is_file():
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
    apply_launch_policy: bool = True,
    probe_attention: bool = True,
) -> list[str]:
    root = Path(comfy_root) if comfy_root else default_comfy_root()
    entry = detect_comfy_entrypoint(root)
    if entry is None:
        return []
    python_path = resolve_managed_comfy_python(root, python_executable)
    command = [python_path, str(entry), "--listen", host, "--port", str(port), "--dont-print-server"]
    # The attention backend is policy, not a caller's choice: this command line and the PowerShell
    # launcher's start the same process, and they disagreed. `extra_args` had been the seam for it
    # and no caller ever passed one -- a parameter is not a policy, it is a place a policy could
    # have gone.
    if apply_launch_policy:
        command.extend(comfy_launch_policy.launch_args(python_path, probe=probe_attention))
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
    apply_launch_policy: bool = False,
    probe_attention: bool = True,
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
    # `apply_launch_policy` is off by default because this function REPORTS -- runtime status calls
    # it on a poll loop, and resolving the attention backend means probing an interpreter with a
    # subprocess. ComfyRuntimeManager.start() asks for the policy; nothing that merely describes the
    # runtime should pay for it.
    launch_cmd = build_launch_command(
        root, python_executable=resolved_python, host=host, port=port,
        apply_launch_policy=apply_launch_policy, probe_attention=probe_attention,
    )
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
