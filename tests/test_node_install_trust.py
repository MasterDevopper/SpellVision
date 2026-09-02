"""The git fallback cannot be steered by its URL, and 'pinned' means a commit.

Security audit finding 5, 2026-09-01. Two defects on one install path:

``clone_custom_node_repo`` ran ``git clone <repo_url> <dest>`` with no scheme check and no ``--``.
It is the FALLBACK for a URL the archive installer refused -- which is precisely when the URL is
unusual. git parses a leading ``-`` as an option, so a repo_url of ``-c core.sshCommand=...`` or
``--upload-pack=...`` becomes a command-line flag; and ssh:// / git:// / file:// are a different
trust story from the archive endpoint's https-only allowlist.

``download_repo_archive`` reported ``pinned=True`` whenever the REQUESTED ref existed -- including a
branch. Doc 28 section 3 asks for "pinned commits, not floating main"; a branch that exists today is
floating main by another name, and the UI was showing it as pinned.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import comfy_manager_bridge as bridge  # noqa: E402
import node_pack_installer as installer  # noqa: E402


# --- the git fallback --------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "-c core.sshCommand=calc",
    "--upload-pack=calc",
    "-oProxyCommand=calc",
    "-",
])
def test_a_url_beginning_with_a_dash_is_refused_before_git_sees_it(tmp_path, url) -> None:
    with pytest.raises(ValueError, match="cannot begin with '-'"):
        bridge.clone_custom_node_repo(tmp_path, url)


@pytest.mark.parametrize("url", [
    "ssh://git@github.com/owner/repo.git",
    "git://github.com/owner/repo.git",
    "file:///C:/anywhere",
    "http://github.com/owner/repo",          # plaintext is not https
    "github.com/owner/repo",                 # bare host path
    "C:\\Users\\victim\\repo",
])
def test_only_https_is_cloned(tmp_path, url) -> None:
    with pytest.raises(ValueError, match="https only"):
        bridge.clone_custom_node_repo(tmp_path, url)


def test_the_clone_command_ends_option_parsing_before_the_url(monkeypatch, tmp_path) -> None:
    """Defence in depth behind the prefix check: even a URL that passed it is never in a position
    where git could read it as an option."""
    seen: list[list[str]] = []

    class _R:
        ok = True
        def to_dict(self):
            return {"ok": True}

    def fake_run(argv, **_kw):
        seen.append(list(argv))
        # Simulate the clone by creating the destination so the requirements step has a path.
        Path(argv[-1]).mkdir(parents=True, exist_ok=True)
        return _R()

    monkeypatch.setattr(bridge, "_run_command", fake_run)
    (tmp_path / "custom_nodes").mkdir(parents=True, exist_ok=True)
    bridge.clone_custom_node_repo(tmp_path, "https://github.com/owner/repo", install_requirements=False)
    clone = [a for a in seen if a[:2] == ["git", "clone"]]
    assert clone, seen
    assert clone[0][2] == "--", f"no `--` before the URL: {clone[0]}"
    assert clone[0][3] == "https://github.com/owner/repo"


def test_the_refusal_names_the_url_and_the_rule(tmp_path) -> None:
    with pytest.raises(ValueError) as excinfo:
        bridge.clone_custom_node_repo(tmp_path, "git://x/y")
    assert "git://x/y" in str(excinfo.value)
    assert "https only" in str(excinfo.value)


# --- pinned means a commit ---------------------------------------------------------------------

def _stub_download(monkeypatch, found: set[str | None]):
    """Pretend codeload serves exactly the refs in ``found`` (None = default branch)."""
    import urllib.error

    def fake_download(url, destination, *, timeout_sec):
        import urllib.parse

        # _archive_url percent-encodes the ref (release/2026 -> release%2F2026); undo that so the
        # stub compares what the installer MEANT, not what the wire carried.
        ref = urllib.parse.unquote(url.rsplit("/zip/", 1)[1])
        ref = None if ref == "HEAD" else ref
        if ref in found:
            Path(destination).write_bytes(b"PK")
            return
        raise urllib.error.HTTPError(url, 404, "nf", hdrs=None, fp=None)

    monkeypatch.setattr(installer, "_download_to", fake_download)


def test_a_commit_hash_is_pinned(monkeypatch, tmp_path) -> None:
    _stub_download(monkeypatch, {"15d09ab"})
    ref, pinned = installer.download_repo_archive("https://github.com/o/r", "15d09ab", tmp_path / "a.zip")
    assert ref == "15d09ab" and pinned is True


def test_a_full_sha_is_pinned(monkeypatch, tmp_path) -> None:
    sha = "0123456789abcdef0123456789abcdef01234567"
    _stub_download(monkeypatch, {sha})
    assert installer.download_repo_archive("https://github.com/o/r", sha, tmp_path / "a.zip") == (sha, True)


@pytest.mark.parametrize("ref", ["main", "master", "develop", "v1.2.3", "release/2026"])
def test_a_branch_or_tag_that_exists_is_not_pinned(monkeypatch, tmp_path, ref) -> None:
    """The regression: the requested ref was found, and that used to be reported as pinned."""
    _stub_download(monkeypatch, {ref})
    resolved, pinned = installer.download_repo_archive("https://github.com/o/r", ref, tmp_path / "a.zip")
    assert resolved == ref
    assert pinned is False, f"{ref!r} is a branch or tag and was reported as pinned"


def test_falling_back_to_the_default_branch_is_not_pinned(monkeypatch, tmp_path) -> None:
    _stub_download(monkeypatch, {None})
    resolved, pinned = installer.download_repo_archive("https://github.com/o/r", "nonexistent", tmp_path / "a.zip")
    assert resolved is None and pinned is False


def test_no_ref_at_all_is_not_pinned(monkeypatch, tmp_path) -> None:
    _stub_download(monkeypatch, {None})
    assert installer.download_repo_archive("https://github.com/o/r", None, tmp_path / "a.zip") == (None, False)


# --- the plan reaches the UI before anything is applied -----------------------------------------

def test_the_retry_response_carries_the_planned_actions_captured_before_apply() -> None:
    """The response carried only counts ("installable: 3"), so the consent dialog could not show
    what those three were. The plan must be captured BEFORE apply -- afterwards the plans are
    re-checked and describe what is now installed, not what was about to be."""
    source = (ROOT / "python" / "workflow_library_commands.py").read_text(encoding="utf-8")
    start = source.index('"retry_workflow_dependencies requires a valid import_root')
    body = source[start:source.index('"type": "workflow_dependency_retry_result"', start)]
    capture = body.index("planned_node_actions = [dict(action) for action in node_plan.install_actions]")
    apply = body.index("apply_node_install_plan(node_plan")
    assert capture < apply, "the plan is captured after apply, so it would describe the post-install state"
    tail = source[source.index('"type": "workflow_dependency_retry_result"', start):]
    assert '"planned_node_actions": planned_node_actions' in tail[:1200]
    assert '"planned_model_actions": planned_model_actions' in tail[:1200]


def test_the_consent_dialog_asks_after_the_plan_and_names_pinned_only_for_commits() -> None:
    """The UI half. Phase 1 runs with apply OFF; the dialog is built from planned_node_actions;
    'pinned' is reserved for ref_kind == commit; Cancel is the default."""
    sys.path.insert(0, str(ROOT / "tests"))
    from cpp_source import find_definition

    _path, body = find_definition("onRetryDependenciesClicked", qualifier="WorkflowLibraryPage")
    plan_off = body.index('planRequest.insert(QStringLiteral("auto_apply_node_deps"), false)')
    dialog = body.index('planned_node_actions')
    apply_on = body.index('request.insert(QStringLiteral("auto_apply_node_deps"), true)')
    assert plan_off < dialog < apply_on, "consent must sit between the plan fetch and the apply"
    assert 'refKind == QStringLiteral("commit")' in body
    assert "pinned commit" in body
    assert "NOT pinned" in body
    assert "setDefaultButton(QMessageBox::Cancel)" in body
    # User-facing text only: the comment explaining why the phrase was removed may quote it.
    code_only = "\n".join(line for line in body.splitlines() if not line.strip().startswith("//"))
    assert "where it has a catalog match" not in code_only, "the stale Doc-46-era wording is back"
