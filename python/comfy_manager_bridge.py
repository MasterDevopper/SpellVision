from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable
import json
import os
import subprocess

from streamed_process import run_streamed


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
    # This is the FALLBACK for a URL the archive installer refused -- which is precisely when the
    # URL is unusual. git parses a leading `-` as an option (`-c core.sshCommand=...`,
    # `--upload-pack=...`), and a non-https scheme is a different trust story from the archive
    # endpoint's https-only allowlist. Refuse both here, in the one function both callers share,
    # rather than at each call site.
    cleaned_url = str(repo_url or "").strip()
    if cleaned_url.startswith("-"):
        raise ValueError(f"Refusing to clone {cleaned_url!r}: a repository URL cannot begin with '-'.")
    if not cleaned_url.lower().startswith("https://"):
        raise ValueError(
            f"Refusing to clone {cleaned_url!r}: node packs are fetched over https only. "
            f"(ssh://, git://, file:// and bare paths are not accepted.)"
        )
    repo_url = cleaned_url

    paths = detect_manager_paths(comfy_root)
    custom_nodes_root = Path(paths.custom_nodes_root)
    custom_nodes_root.mkdir(parents=True, exist_ok=True)

    target_name = package_name or _repo_name_from_url(repo_url)
    destination = custom_nodes_root / target_name
    command_results: list[dict[str, Any]] = []

    if destination.exists():
        return NodeInstallOutcome(
            ok=True,
            action="already_present",
            package_name=target_name,
            repo_url=repo_url,
            destination=str(destination),
            command_results=[],
            message="already present (revision not verified; nothing was installed)",
        )

    # `--` ends option parsing, so nothing that survived the check above can still be read as one.
    clone_result = _run_command(["git", "clone", "--", repo_url, str(destination)], cwd=custom_nodes_root, timeout_sec=timeout_sec)
    command_results.append(clone_result.to_dict())

    if clone_result.ok and install_requirements:
        req = destination / "requirements.txt"
        if req.exists():
            # Without a constraints file a pack's requirements can install a different torch and
            # break every generation family. node_pack_installer is the path that guards this; this
            # git route stays only as a fallback for a repo host the archive path cannot serve.
            pip_result = _run_command([python_executable, "-m", "pip", "install", "-r", str(req)], cwd=destination, timeout_sec=timeout_sec)
            command_results.append(pip_result.to_dict())

    # `all()` over an empty list is True, which is how a no-op used to report success. Every branch
    # that reaches here has run at least the clone, so require that explicitly rather than relying
    # on the list being non-empty.
    ok = bool(command_results) and all(item.get("ok", False) for item in command_results)
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
    on_line=None,
) -> CommandResult:
    """Run a manager command, reporting each line as it arrives.

    These are git and pip operations with a 900-second budget. Captured whole they produced no
    output at all until they finished, so a fifteen-minute clone and a hung process looked the same
    from outside. See python/streamed_process.py.
    """
    try:
        streamed = run_streamed(cmd, cwd=cwd, env=env, timeout=timeout_sec, on_line=on_line)
        if streamed.error and streamed.returncode is None:
            raise RuntimeError(streamed.error)
        return CommandResult(
            ok=streamed.ok,
            cmd=list(cmd),
            cwd=str(cwd) if cwd else None,
            returncode=streamed.returncode if streamed.returncode is not None else -1,
            stdout=streamed.stdout,
            stderr=streamed.stderr or (streamed.error if streamed.timed_out else ""),
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
