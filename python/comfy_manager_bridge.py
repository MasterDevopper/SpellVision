from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable
import json
import os
import shutil
import subprocess


DEFAULT_MANAGER_REPO_URL = "https://github.com/Comfy-Org/ComfyUI-Manager.git"


@dataclass
class CommandResult:
    ok: bool
    cmd: list[str]
    cwd: str | None = None
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ComfyManagerPaths:
    comfy_root: str
    custom_nodes_root: str
    manager_root: str
    cm_cli_path: str
    requirements_path: str | None = None
    exists: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NodeInstallOutcome:
    ok: bool
    action: str
    package_name: str | None = None
    repo_url: str | None = None
    destination: str | None = None
    command_results: list[dict[str, Any]] = field(default_factory=list)
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def detect_manager_paths(comfy_root: str | Path) -> ComfyManagerPaths:
    comfy_root = str(Path(comfy_root).resolve())
    custom_nodes_root = str(Path(comfy_root) / "custom_nodes")

    candidates = [
        Path(custom_nodes_root) / "ComfyUI-Manager",
        Path(custom_nodes_root) / "comfyui-manager",
    ]

    for candidate in candidates:
        cm_cli = candidate / "cm-cli.py"
        if cm_cli.exists():
            req_path = candidate / "requirements.txt"
            return ComfyManagerPaths(
                comfy_root=comfy_root,
                custom_nodes_root=custom_nodes_root,
                manager_root=str(candidate),
                cm_cli_path=str(cm_cli),
                requirements_path=str(req_path) if req_path.exists() else None,
                exists=True,
            )

    preferred = candidates[0]
    req_path = preferred / "requirements.txt"
    return ComfyManagerPaths(
        comfy_root=comfy_root,
        custom_nodes_root=custom_nodes_root,
        manager_root=str(preferred),
        cm_cli_path=str(preferred / "cm-cli.py"),
        requirements_path=str(req_path),
        exists=False,
    )


def ensure_manager_installed(
    comfy_root: str | Path,
    *,
    python_executable: str = "python",
    manager_repo_url: str = DEFAULT_MANAGER_REPO_URL,
    install_requirements: bool = True,
    timeout_sec: int = 900,
) -> tuple[ComfyManagerPaths, list[CommandResult]]:
    paths = detect_manager_paths(comfy_root)
    logs: list[CommandResult] = []
    Path(paths.custom_nodes_root).mkdir(parents=True, exist_ok=True)

    if not paths.exists:
        clone_cmd = ["git", "clone", manager_repo_url, paths.manager_root]
        clone_result = _run_command(clone_cmd, cwd=paths.custom_nodes_root, timeout_sec=timeout_sec)
        logs.append(clone_result)
        paths = detect_manager_paths(comfy_root)

    if install_requirements and paths.requirements_path and Path(paths.requirements_path).exists():
        pip_cmd = [python_executable, "-m", "pip", "install", "-r", paths.requirements_path]
        logs.append(_run_command(pip_cmd, cwd=paths.manager_root, timeout_sec=timeout_sec))

    return paths, logs


def run_cm_cli(
    comfy_root: str | Path,
    args: Iterable[str],
    *,
    python_executable: str = "python",
    timeout_sec: int = 900,
    ensure_manager: bool = False,
) -> tuple[ComfyManagerPaths, CommandResult]:
    if ensure_manager:
        paths, _ = ensure_manager_installed(comfy_root, python_executable=python_executable, timeout_sec=timeout_sec)
    else:
        paths = detect_manager_paths(comfy_root)

    if not paths.exists:
        return paths, CommandResult(
            ok=False,
            cmd=[],
            cwd=paths.manager_root,
            returncode=None,
            stderr="ComfyUI-Manager is not installed",
        )

    env = os.environ.copy()
    env["COMFYUI_PATH"] = paths.comfy_root
    cmd = [python_executable, paths.cm_cli_path, *list(args)]
    result = _run_command(cmd, cwd=paths.manager_root, timeout_sec=timeout_sec, env=env)
    return paths, result


def list_installed_nodes(
    comfy_root: str | Path,
    *,
    python_executable: str = "python",
    timeout_sec: int = 300,
) -> dict[str, Any]:
    paths, result = run_cm_cli(
        comfy_root,
        ["simple-show", "installed", "--mode", "cache"],
        python_executable=python_executable,
        timeout_sec=timeout_sec,
        ensure_manager=False,
    )

    names = set(_parse_simple_show_names(result.stdout))
    custom_nodes_root = Path(paths.custom_nodes_root)
    if custom_nodes_root.exists():
        for item in custom_nodes_root.iterdir():
            if item.is_dir() and not item.name.startswith(".") and item.name not in {"__pycache__"}:
                names.add(item.name)

    return {
        "manager_present": paths.exists,
        "paths": paths.to_dict(),
        "names": sorted(names),
        "command_result": result.to_dict(),
    }


def install_registered_nodes(
    comfy_root: str | Path,
    package_names: list[str],
    *,
    python_executable: str = "python",
    timeout_sec: int = 1800,
    channel: str = "default",
    mode: str = "remote",
) -> list[NodeInstallOutcome]:
    if not package_names:
        return []

    ensure_manager_installed(comfy_root, python_executable=python_executable, timeout_sec=timeout_sec)
    outcomes: list[NodeInstallOutcome] = []
    for package_name in package_names:
        _, result = run_cm_cli(
            comfy_root,
            ["install", package_name, "--channel", channel, "--mode", mode],
            python_executable=python_executable,
            timeout_sec=timeout_sec,
            ensure_manager=False,
        )
        outcomes.append(
            NodeInstallOutcome(
                ok=result.ok,
                action="manager_install",
                package_name=package_name,
                command_results=[result.to_dict()],
                message=None if result.ok else (result.stderr or result.stdout or "manager install failed"),
            )
        )
    return outcomes


def clone_custom_node_repo(
    comfy_root: str | Path,
    repo_url: str,
    *,
    package_name: str | None = None,
    python_executable: str = "python",
    timeout_sec: int = 1800,
    install_requirements: bool = True,
) -> NodeInstallOutcome:
    paths = detect_manager_paths(comfy_root)
    custom_nodes_root = Path(paths.custom_nodes_root)
    custom_nodes_root.mkdir(parents=True, exist_ok=True)

    target_name = package_name or _repo_name_from_url(repo_url)
    destination = custom_nodes_root / target_name
    command_results: list[dict[str, Any]] = []

    if destination.exists():
        return NodeInstallOutcome(
            ok=True,
            action="git_clone",
            package_name=target_name,
            repo_url=repo_url,
            destination=str(destination),
            command_results=[],
            message="already present",
        )

    clone_result = _run_command(["git", "clone", repo_url, str(destination)], cwd=custom_nodes_root, timeout_sec=timeout_sec)
    command_results.append(clone_result.to_dict())

    if clone_result.ok and install_requirements:
        req = destination / "requirements.txt"
        if req.exists():
            pip_result = _run_command([python_executable, "-m", "pip", "install", "-r", str(req)], cwd=destination, timeout_sec=timeout_sec)
            command_results.append(pip_result.to_dict())

    ok = all(item.get("ok", False) for item in command_results) if command_results else True
    return NodeInstallOutcome(
        ok=ok,
        action="git_clone",
        package_name=target_name,
        repo_url=repo_url,
        destination=str(destination),
        command_results=command_results,
        message=None if ok else "git clone node install failed",
    )


def set_cli_only_mode(
    comfy_root: str | Path,
    enabled: bool,
    *,
    python_executable: str = "python",
    timeout_sec: int = 300,
) -> CommandResult:
    _, result = run_cm_cli(
        comfy_root,
        ["cli-only-mode", "enable" if enabled else "disable"],
        python_executable=python_executable,
        timeout_sec=timeout_sec,
        ensure_manager=True,
    )
    return result


def _run_command(
    cmd: list[str],
    *,
    cwd: str | Path | None = None,
    timeout_sec: int = 900,
    env: dict[str, str] | None = None,
) -> CommandResult:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        return CommandResult(
            ok=proc.returncode == 0,
            cmd=list(cmd),
            cwd=str(cwd) if cwd else None,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )
    except Exception as exc:
        return CommandResult(
            ok=False,
            cmd=list(cmd),
            cwd=str(cwd) if cwd else None,
            returncode=None,
            stderr=str(exc),
        )


def _parse_simple_show_names(text: str) -> list[str]:
    names: list[str] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("-=") or line.startswith("FETCH DATA") or line.startswith("WARN:"):
            continue
        if line.startswith("["):
            continue
        names.append(line)
    return names


def _repo_name_from_url(repo_url: str) -> str:
    name = repo_url.rstrip("/").rsplit("/", 1)[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name or "custom-node"
