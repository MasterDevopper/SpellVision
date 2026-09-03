"""Installing a node pack must need no git, pin the revision, and never move torch.

Three real defects motivate each half of this:

  * ``clone_custom_node_repo`` shells ``git clone``, and nothing in CMakeLists ships git -- on an MSI
    machine the install just fails. GitHub serves any ref as a zip, which also pins it.
  * a pack's requirements.txt routinely names a different torch; installing it breaks every
    generation family at once. A constraints file (the fix proven in bf3c1af) lets everything else
    resolve while the torch stack cannot move, and the versions are re-read afterwards so a move is
    a loud failure rather than a mystery three renders later.
  * ``ok = all(...)`` over an empty list is True, so the already-present branch reported success
    having done nothing.

The archive is remote input, so extraction is treated as hostile: zip-slip and symlink members are
refused outright.
"""
from __future__ import annotations

import io
import os
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))
import node_pack_installer as npi  # noqa: E402
from comfy_manager_bridge import clone_custom_node_repo  # noqa: E402


def _zip(members: dict[str, bytes], *, prefix: str = "ComfyUI-Thing-main/") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(prefix + name, data)
    return buf.getvalue()


def _write_zip(path, members, *, prefix="ComfyUI-Thing-main/"):
    path.write_bytes(_zip(members, prefix=prefix))
    return path


# --- URL handling ------------------------------------------------------------------------------

def test_only_github_over_https_is_accepted():
    assert npi.parse_github_repo("https://github.com/kijai/ComfyUI-KJNodes.git") == ("kijai", "ComfyUI-KJNodes")
    with pytest.raises(ValueError):
        npi.parse_github_repo("http://github.com/kijai/ComfyUI-KJNodes")
    with pytest.raises(ValueError):
        npi.parse_github_repo("https://evil.invalid/kijai/ComfyUI-KJNodes")


def test_a_semver_ref_also_tries_the_v_prefixed_tag():
    """The Registry publishes '1.5.0'; the git tag is usually 'v1.5.0'."""
    assert npi.candidate_refs("1.5.0") == ["1.5.0", "v1.5.0", None]


def test_a_commit_sha_is_used_verbatim():
    sha = "717092a3ceb51c474b5b3f77fc188979f0db9d67"
    assert npi.candidate_refs(sha) == [sha, None]


def test_no_ref_means_the_default_branch():
    assert npi.candidate_refs(None) == [None]


# --- extraction is hostile input ------------------------------------------------------------------

def test_the_repo_ref_prefix_directory_is_stripped(tmp_path):
    archive = _write_zip(tmp_path / "a.zip", {"__init__.py": b"x", "nodes/thing.py": b"y"})
    npi.extract_repo_archive(archive, tmp_path / "out")
    assert (tmp_path / "out" / "__init__.py").read_bytes() == b"x"
    assert (tmp_path / "out" / "nodes" / "thing.py").is_file()


def test_zip_slip_is_refused(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("ComfyUI-Thing-main/ok.py", b"x")
        zf.writestr("ComfyUI-Thing-main/../../../escaped.py", b"pwned")
    archive = tmp_path / "evil.zip"
    archive.write_bytes(buf.getvalue())
    with pytest.raises(RuntimeError, match="outside the destination"):
        npi.extract_repo_archive(archive, tmp_path / "out")
    assert not (tmp_path / "escaped.py").exists()


def test_symlink_members_are_refused(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo("ComfyUI-Thing-main/link")
        info.external_attr = (0xA1FF << 16)  # S_IFLNK | 0777
        zf.writestr(info, "/etc/passwd")
    archive = tmp_path / "link.zip"
    archive.write_bytes(buf.getvalue())
    with pytest.raises(RuntimeError, match="symlink"):
        npi.extract_repo_archive(archive, tmp_path / "out")


def test_an_empty_archive_is_an_error_not_an_empty_pack(tmp_path):
    archive = tmp_path / "empty.zip"
    with zipfile.ZipFile(archive, "w"):
        pass
    with pytest.raises(RuntimeError, match="empty"):
        npi.extract_repo_archive(archive, tmp_path / "out")


# --- install ---------------------------------------------------------------------------------

@pytest.fixture
def fake_github(monkeypatch):
    """Serves the archive for a known set of refs; 404s the rest, like GitHub does."""
    state = {"requested": [], "available": {"abc1234"}, "members": {"__init__.py": b"NODE_CLASS_MAPPINGS={}"}}

    def download(url, destination, *, timeout_sec):
        ref = url.rsplit("/", 1)[-1]
        state["requested"].append(ref)
        if ref not in state["available"]:
            import urllib.error
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(_zip(state["members"]))

    monkeypatch.setattr(npi, "_download_to", download)
    return state


def _install(tmp_path, **kwargs):
    kwargs.setdefault("repo_url", "https://github.com/x/ComfyUI-Thing")
    repo_url = kwargs.pop("repo_url")
    return npi.install_node_pack(tmp_path / "comfy", repo_url, install_requirements=False, **kwargs)


def test_install_lands_the_pack_and_records_the_pin(tmp_path, fake_github):
    result = _install(tmp_path, package_name="ComfyUI-Thing", ref="abc1234")
    assert result.ok is True
    assert result.pinned is True
    assert result.resolved_ref == "abc1234"
    assert (tmp_path / "comfy" / "custom_nodes" / "ComfyUI-Thing" / "__init__.py").is_file()


def test_a_missing_ref_falls_back_to_the_default_branch_and_says_so(tmp_path, fake_github):
    """Installing HEAD instead of the requested revision is a different promise; it must be visible."""
    fake_github["available"] = {"HEAD"}
    result = _install(tmp_path, package_name="ComfyUI-Thing", ref="1.5.0")
    assert result.ok is True
    assert result.pinned is False
    assert "unpinned" in (result.message or "").lower()
    assert fake_github["requested"] == ["1.5.0", "v1.5.0", "HEAD"]


def test_an_existing_pack_is_not_reported_as_installed(tmp_path, fake_github):
    """The already-present branch must not read as 'the requested revision is now present'."""
    existing = tmp_path / "comfy" / "custom_nodes" / "ComfyUI-Thing"
    existing.mkdir(parents=True)
    (existing / "marker").write_text("old", encoding="utf-8")

    result = _install(tmp_path, package_name="ComfyUI-Thing", ref="abc1234")
    assert result.action == "already_present"
    assert "revision was not checked" in (result.message or "")
    assert (existing / "marker").is_file(), "the existing checkout is left alone"
    assert fake_github["requested"] == [], "nothing was downloaded"


def test_allow_replace_reinstalls_over_an_existing_pack(tmp_path, fake_github):
    existing = tmp_path / "comfy" / "custom_nodes" / "ComfyUI-Thing"
    existing.mkdir(parents=True)
    (existing / "marker").write_text("old", encoding="utf-8")

    result = _install(tmp_path, package_name="ComfyUI-Thing", ref="abc1234", allow_replace=True)
    assert result.ok is True
    assert not (existing / "marker").exists()
    assert (existing / "__init__.py").is_file()


def test_a_download_failure_leaves_nothing_behind(tmp_path, fake_github):
    fake_github["available"] = set()
    result = _install(tmp_path, package_name="ComfyUI-Thing", ref="abc1234")
    assert result.ok is False
    assert not (tmp_path / "comfy" / "custom_nodes" / "ComfyUI-Thing").exists()


def test_the_destination_cannot_escape_custom_nodes(tmp_path, fake_github):
    with pytest.raises(ValueError):
        _install(tmp_path, package_name="../evil", ref="abc1234")


# --- torch protection --------------------------------------------------------------------------

def test_requirements_install_under_a_constraints_file(tmp_path, fake_github, monkeypatch):
    fake_github["members"] = {"__init__.py": b"x", "requirements.txt": b"numpy\n"}
    monkeypatch.setattr(npi, "torch_stack_versions", lambda *a, **k: {"torch": "2.10.0", "torchvision": "0.25.0"})

    seen: dict[str, object] = {}

    def fake_streamed(cmd, **kwargs):
        seen["cmd"] = list(cmd)
        idx = cmd.index("-c")
        seen["constraints"] = open(cmd[idx + 1], encoding="ascii").read()
        # The runner forwards each line as it arrives; a fake that never calls back would let the
        # reporting half rot while this test stayed green.
        on_line = kwargs.get("on_line")
        if on_line is not None:
            on_line("stdout", "Collecting numpy")
        return npi.StreamedResult(cmd=list(cmd), returncode=0)

    monkeypatch.setattr(npi, "run_streamed", fake_streamed)
    progress: list[str] = []
    result = npi.install_node_pack(tmp_path / "comfy", "https://github.com/x/ComfyUI-Thing",
                                   package_name="ComfyUI-Thing", ref="abc1234",
                                   on_progress=progress.append)
    assert result.ok is True
    assert "torch==2.10.0" in str(seen["constraints"])
    assert "torchvision==0.25.0" in str(seen["constraints"])

    # The install used to produce nothing at all until it finished, with a 1800-second budget: a
    # half-hour of still screen is indistinguishable from a crash. Each step says so as it happens,
    # and pip's own narration is forwarded through.
    assert any("downloading" in line for line in progress), progress
    assert any("installing Python requirements" in line for line in progress), progress
    assert any("Collecting numpy" in line for line in progress), progress


def test_a_torch_move_fails_the_install_loudly(tmp_path, fake_github, monkeypatch):
    """Files on disk is not success when the torch stack shifted: every family depends on it."""
    fake_github["members"] = {"__init__.py": b"x", "requirements.txt": b"torch==2.4.0\n"}
    versions = iter([{"torch": "2.10.0"}, {"torch": "2.4.0"}])
    monkeypatch.setattr(npi, "torch_stack_versions", lambda *a, **k: next(versions))

    class Proc:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(npi.subprocess, "run", lambda cmd, **kw: Proc())
    result = npi.install_node_pack(tmp_path / "comfy", "https://github.com/x/ComfyUI-Thing",
                                   package_name="ComfyUI-Thing", ref="abc1234")
    assert result.ok is False
    assert "2.10.0 -> 2.4.0" in (result.message or "")
    assert any(step.name == "torch_unchanged" and not step.ok for step in result.steps)


def test_no_torch_installed_is_not_treated_as_a_move(tmp_path, fake_github, monkeypatch):
    fake_github["members"] = {"__init__.py": b"x", "requirements.txt": b"numpy\n"}
    monkeypatch.setattr(npi, "torch_stack_versions", lambda *a, **k: {})

    class Proc:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(npi.subprocess, "run", lambda cmd, **kw: Proc())
    result = npi.install_node_pack(tmp_path / "comfy", "https://github.com/x/ComfyUI-Thing",
                                   package_name="ComfyUI-Thing", ref="abc1234")
    assert result.ok is True


# --- the empty-list success bug -----------------------------------------------------------------

def test_clone_bridge_no_longer_reports_a_no_op_as_a_git_clone(tmp_path):
    """`all([])` is True. The already-present branch used to return action='git_clone', ok=True."""
    existing = tmp_path / "custom_nodes" / "Thing"
    existing.mkdir(parents=True)
    outcome = clone_custom_node_repo(tmp_path, "https://github.com/x/Thing", package_name="Thing")
    assert outcome.action == "already_present"
    assert "nothing was installed" in (outcome.message or "")
