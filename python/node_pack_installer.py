"""Install a ComfyUI node pack from a pinned GitHub archive, without git and without moving torch.

Three problems with the install path this replaces:

1. **git is a hidden hard dependency.** ``comfy_manager_bridge.clone_custom_node_repo`` shells out to
   ``git clone``, and nothing in ``CMakeLists.txt`` ships git. On an MSI machine that has never seen
   a developer toolchain the install simply fails. GitHub serves every ref as a zip
   (``/archive/{ref}.zip``), so the archive path needs nothing but HTTPS -- and it pins the exact
   revision, which is what Doc 28 3 ("pinned commits, not floating main") asks for.

2. **pip can silently move torch.** A pack's ``requirements.txt`` routinely names a different torch,
   and installing it breaks every generation family at once. ``--no-deps`` is too blunt -- applied
   blanket it dropped wcwidth (WanVideoWrapper), pyparsing (RES4LYF) and matplotlib's transitive
   deps, and the packs then failed to import in a way that looked exactly like a core
   incompatibility. The fix proven in ``bf3c1af`` is a constraints file: everything resolves
   normally, the torch stack cannot move. Here the constraints are read from the target interpreter
   at install time rather than hardcoded, and the versions are re-read afterwards and compared, so a
   move is a loud failure instead of a discovery three renders later.

3. **Failures could read as success.** ``clone_custom_node_repo`` computes ``ok = all(...)`` over a
   list that is empty on the already-present branch, and returns "already present" without checking
   that what is present is what was asked for. Here ``ok`` is derived from steps that actually ran.

Security notes, since this downloads and unpacks a remote archive:
  * only https, and only github.com / codeload.github.com;
  * every extracted member is resolved and required to stay inside the destination (zip-slip), and
    symlink members are refused outright;
  * the archive is size-capped and written to a temp file first, so a partial download never becomes
    a half-installed pack.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ALLOWED_ARCHIVE_HOSTS = {"github.com", "www.github.com", "codeload.github.com"}
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
DOWNLOAD_CHUNK_BYTES = 1024 * 256
# Anything in this stack moving is a whole-application break, not a pack-level inconvenience.
TORCH_STACK = ("torch", "torchvision", "torchaudio")


@dataclass
class InstallStep:
    name: str
    ok: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PackInstallResult:
    ok: bool
    action: str
    package_name: str
    repo_url: str | None = None
    requested_ref: str | None = None
    resolved_ref: str | None = None
    pinned: bool = False
    destination: str | None = None
    steps: list[InstallStep] = field(default_factory=list)
    torch_before: dict[str, str] = field(default_factory=dict)
    torch_after: dict[str, str] = field(default_factory=dict)
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["steps"] = [s.to_dict() for s in self.steps]
        return payload


# ---------------------------------------------------------------------------
# GitHub archive
# ---------------------------------------------------------------------------

def parse_github_repo(repo_url: str) -> tuple[str, str]:
    """``https://github.com/owner/repo(.git)`` -> ``(owner, repo)``. Raises for anything else."""
    parsed = urllib.parse.urlparse(repo_url.strip())
    if parsed.scheme != "https":
        raise ValueError(f"Node pack archives must be fetched over https, got {parsed.scheme or 'no scheme'}.")
    if parsed.hostname not in ALLOWED_ARCHIVE_HOSTS:
        raise ValueError(f"Refusing to download a node pack from {parsed.hostname or repo_url!r}; only GitHub is allowed.")
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        raise ValueError(f"Could not read owner/repo from {repo_url!r}.")
    owner, repo = parts[0], parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    return owner, repo


def candidate_refs(ref: str | None) -> list[str | None]:
    """Refs to try, most precise first. ``None`` means the repository's default branch.

    A Registry version is a bare semver ("1.5.0") but the matching git tag is usually "v1.5.0", so
    both spellings are tried before falling back to the default branch. A commit sha needs neither.
    """
    if not ref:
        return [None]
    ref = ref.strip()
    if not ref:
        return [None]
    out: list[str | None] = [ref]
    if ref[0].isdigit() and not _looks_like_commit(ref):
        out.append(f"v{ref}")
    out.append(None)
    return out


def _looks_like_commit(ref: str) -> bool:
    return len(ref) >= 7 and all(c in "0123456789abcdefABCDEF" for c in ref)


def _archive_url(owner: str, repo: str, ref: str | None) -> str:
    quoted = urllib.parse.quote(ref, safe="") if ref else "HEAD"
    return f"https://codeload.github.com/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}/zip/{quoted}"


def download_repo_archive(
    repo_url: str,
    ref: str | None,
    destination: Path,
    *,
    timeout_sec: int = 300,
) -> tuple[str | None, bool]:
    """Fetch a repo archive to ``destination``. Returns ``(resolved_ref, pinned)``.

    ``pinned`` is False when the requested ref was not found and the default branch was used
    instead -- the caller must surface that, because an unpinned install is a different promise.
    """
    owner, repo = parse_github_repo(repo_url)
    last_error: Exception | None = None
    for candidate in candidate_refs(ref):
        url = _archive_url(owner, repo, candidate)
        try:
            _download_to(url, destination, timeout_sec=timeout_sec)
        except urllib.error.HTTPError as exc:
            last_error = exc
            if int(getattr(exc, "code", 0) or 0) == 404:
                continue
            raise
        return candidate, candidate is not None
    raise RuntimeError(f"No downloadable archive for {repo_url} at ref {ref!r}: {last_error}")


def _download_to(url: str, destination: Path, *, timeout_sec: int) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "SpellVision/1.0 (node pack install)"})
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(prefix="svpack_", suffix=".part", dir=str(destination.parent))
    os.close(tmp_fd)
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as resp, open(tmp_name, "wb") as fh:
            declared = resp.headers.get("Content-Length")
            if declared and declared.isdigit() and int(declared) > MAX_ARCHIVE_BYTES:
                raise RuntimeError(f"Node pack archive is larger than the {MAX_ARCHIVE_BYTES} byte limit.")
            written = 0
            while True:
                chunk = resp.read(DOWNLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_ARCHIVE_BYTES:
                    raise RuntimeError(f"Node pack archive exceeded the {MAX_ARCHIVE_BYTES} byte limit.")
                fh.write(chunk)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, destination)
    except Exception:
        try:
            os.unlink(tmp_name)
        except Exception:
            pass
        raise


def extract_repo_archive(archive: Path, destination: Path) -> Path:
    """Unpack a GitHub zip into ``destination``, stripping its single top-level ``repo-ref/`` folder.

    Every member is checked to land inside ``destination``, and symlinks are refused: a crafted
    archive must not be able to write outside the custom_nodes directory or plant a link into it.
    """
    destination.mkdir(parents=True, exist_ok=True)
    resolved_root = destination.resolve()
    with zipfile.ZipFile(archive) as zf:
        members = [m for m in zf.infolist() if not m.is_dir()]
        if not members:
            raise RuntimeError("Node pack archive is empty.")
        prefixes = {m.filename.split("/", 1)[0] for m in zf.infolist() if "/" in m.filename}
        strip = prefixes.pop() + "/" if len(prefixes) == 1 else ""
        total = 0
        for member in members:
            # 0xA000 is S_IFLNK in the high 16 bits of external_attr for zips written on POSIX.
            if (member.external_attr >> 16) & 0xF000 == 0xA000:
                raise RuntimeError(f"Refusing to extract symlink member {member.filename!r} from a node pack archive.")
            name = member.filename[len(strip):] if strip and member.filename.startswith(strip) else member.filename
            if not name:
                continue
            target = (resolved_root / name).resolve()
            if target != resolved_root and resolved_root not in target.parents:
                raise RuntimeError(f"Refusing to extract {member.filename!r} outside the destination directory.")
            total += member.file_size
            if total > MAX_ARCHIVE_BYTES:
                raise RuntimeError("Node pack archive expands beyond the allowed size.")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
    return destination


# ---------------------------------------------------------------------------
# Torch protection
# ---------------------------------------------------------------------------

def torch_stack_versions(python_executable: str, *, timeout_sec: int = 120) -> dict[str, str]:
    """Read the installed torch stack from the interpreter that will run the pip install.

    Read from the target interpreter rather than hardcoded, because the worker venv and the ComfyUI
    venv are decoupled and a hardcoded pin would silently protect the wrong one.
    """
    code = (
        "import json,importlib.metadata as m\n"
        "out={}\n"
        "for name in ('torch','torchvision','torchaudio'):\n"
        "    try: out[name]=m.version(name)\n"
        "    except Exception: pass\n"
        "print(json.dumps(out))"
    )
    try:
        proc = subprocess.run([python_executable, "-c", code], capture_output=True, text=True,
                              timeout=timeout_sec, check=False)
        if proc.returncode != 0:
            return {}
        return {k: str(v) for k, v in json.loads(proc.stdout.strip() or "{}").items()}
    except Exception:
        return {}


def write_torch_constraints(path: Path, versions: dict[str, str]) -> Path | None:
    """Write a pip constraints file pinning whatever torch stack is currently installed."""
    lines = [f"{name}=={version}" for name, version in versions.items() if name in TORCH_STACK and version]
    if not lines:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    return path


# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------

def install_node_pack(
    comfy_root: str | Path,
    repo_url: str,
    *,
    package_name: str | None = None,
    ref: str | None = None,
    python_executable: str = "python",
    install_requirements: bool = True,
    allow_replace: bool = False,
    timeout_sec: int = 1800,
) -> PackInstallResult:
    """Install one node pack into ``comfy_root/custom_nodes`` from a pinned GitHub archive."""
    owner, repo = parse_github_repo(repo_url)
    target_name = (package_name or repo).strip() or repo
    if target_name in {".", ".."} or "/" in target_name or "\\" in target_name:
        raise ValueError(f"Unsafe node pack directory name: {target_name!r}")

    custom_nodes = Path(comfy_root).expanduser().resolve() / "custom_nodes"
    destination = (custom_nodes / target_name).resolve()
    if custom_nodes not in destination.parents:
        raise ValueError(f"Node pack destination escapes custom_nodes: {destination}")

    result = PackInstallResult(ok=False, action="install_node_pack", package_name=target_name,
                               repo_url=repo_url, requested_ref=ref, destination=str(destination))

    if destination.exists() and not allow_replace:
        # Distinct from success. Nothing was installed, and the caller must not read this as "the
        # requested revision is now present" -- the existing checkout may be any revision at all.
        result.ok = True
        result.action = "already_present"
        result.message = (f"{target_name} is already installed. Its revision was not checked; "
                          f"pass allow_replace to reinstall at {ref or 'the default branch'}.")
        result.steps.append(InstallStep("check_destination", True, "already present, left untouched"))
        return result

    result.torch_before = torch_stack_versions(python_executable)

    with tempfile.TemporaryDirectory(prefix="svpack_") as tmp:
        tmp_path = Path(tmp)
        archive = tmp_path / f"{repo}.zip"
        try:
            resolved_ref, pinned = download_repo_archive(repo_url, ref, archive, timeout_sec=min(timeout_sec, 600))
        except Exception as exc:
            result.steps.append(InstallStep("download", False, f"{type(exc).__name__}: {exc}"))
            result.message = f"Could not download {repo_url}: {exc}"
            return result
        result.resolved_ref = resolved_ref
        result.pinned = pinned
        result.steps.append(InstallStep(
            "download", True,
            f"{owner}/{repo} at {resolved_ref or 'default branch'}"
            + ("" if pinned else " (requested ref not found; NOT pinned)")))

        staging = tmp_path / "unpacked"
        try:
            extract_repo_archive(archive, staging)
        except Exception as exc:
            result.steps.append(InstallStep("extract", False, f"{type(exc).__name__}: {exc}"))
            result.message = f"Could not unpack the archive for {target_name}: {exc}"
            return result
        result.steps.append(InstallStep("extract", True, f"unpacked into {staging.name}"))

        backup: Path | None = None
        if destination.exists():
            backup = destination.with_name(destination.name + ".replaced")
            shutil.rmtree(backup, ignore_errors=True)
            destination.rename(backup)
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(staging), str(destination))
        except Exception as exc:
            if backup is not None and not destination.exists():
                backup.rename(destination)  # put the working checkout back
            result.steps.append(InstallStep("place", False, f"{type(exc).__name__}: {exc}"))
            result.message = f"Could not place {target_name} into custom_nodes: {exc}"
            return result
        result.steps.append(InstallStep("place", True, str(destination)))
        if backup is not None:
            shutil.rmtree(backup, ignore_errors=True)

        requirements = destination / "requirements.txt"
        if install_requirements and requirements.is_file():
            constraints = write_torch_constraints(tmp_path / "torch-constraints.txt", result.torch_before)
            cmd = [python_executable, "-m", "pip", "install", "-r", str(requirements)]
            if constraints is not None:
                cmd[4:4] = ["-c", str(constraints)]
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec, check=False)
                ok = proc.returncode == 0
                detail = (proc.stderr or proc.stdout or "").strip()[-2000:]
            except Exception as exc:
                ok, detail = False, f"{type(exc).__name__}: {exc}"
            result.steps.append(InstallStep(
                "requirements", ok,
                ("installed under torch constraints" if constraints is not None
                 else "installed (no torch stack found to constrain)") if ok else detail))
            if not ok:
                result.message = f"{target_name} was installed but its Python requirements failed."

    result.torch_after = torch_stack_versions(python_executable)
    moved = {name: (result.torch_before.get(name), result.torch_after.get(name))
             for name in TORCH_STACK
             if result.torch_before.get(name) and result.torch_before.get(name) != result.torch_after.get(name)}
    if moved:
        # Loud, and ok=False even though the files are on disk: every generation family depends on
        # this stack, so a silent move would surface as unrelated breakage much later.
        detail = "; ".join(f"{n}: {before} -> {after}" for n, (before, after) in moved.items())
        result.steps.append(InstallStep("torch_unchanged", False, detail))
        result.ok = False
        result.message = (f"Installing {target_name} moved the torch stack ({detail}). "
                          "This breaks every generation family; reinstall the pinned torch build before generating.")
        return result
    if result.torch_before:
        result.steps.append(InstallStep("torch_unchanged", True,
                                        ", ".join(f"{n}=={v}" for n, v in sorted(result.torch_before.items()))))

    result.ok = all(step.ok for step in result.steps)
    if result.ok and not result.message:
        result.message = (f"Installed {target_name} at {result.resolved_ref or 'the default branch'}"
                          + ("." if result.pinned else " (unpinned: the requested revision was not available)."))
    return result
