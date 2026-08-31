"""A model root that cannot be READ is not a model root with nothing in it.

The two were indistinguishable, and the difference is expensive. Every checkpoint on this machine
lives under ``D:/AI_ASSETS/models``, mapped in through ``extra_model_paths.yaml``. With that drive
locked by BitLocker the index fell from thousands of files to 57, every model on it resolved as
MISSING, and the install plan would have offered to download models the user already owns -- tens of
gigabytes each -- with nothing anywhere saying the drive was locked.

Three separate places swallowed it, which is why it produced silence rather than an error:

* ``Path.resolve()`` RAISES on a locked drive rather than returning the path unchanged, and the
  ``except Exception: pass`` around it dropped the root before the walk ever saw it;
* ``Path.is_dir()`` answers False for any OSError, so the guard skipped what it could not stat;
* ``os.walk`` discards errors unless given an ``onerror`` handler.

Each one on its own turns "unreadable" into "empty". Under-reporting presence is the dangerous
direction: over-reporting fails loudly at load time, while this fails by quietly proposing an
expensive wrong answer.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

import model_dependency_resolver as mdr  # noqa: E402

# The real Windows error. Not a plain PermissionError, which is why a handler written for the
# obvious cases would still have missed it.
BITLOCKER = OSError(
    -2144272384,
    "This drive is locked by BitLocker Drive Encryption. You must unlock this drive from Control Panel",
)


@pytest.fixture
def comfy_root(tmp_path, monkeypatch):
    """A ComfyUI tree with its own models dir plus one extra root that we can make hostile."""
    root = tmp_path / "ComfyUI"
    (root / "models" / "checkpoints").mkdir(parents=True)
    (root / "models" / "checkpoints" / "local.safetensors").write_bytes(b"x")

    locked = tmp_path / "locked_drive" / "checkpoints"
    locked.mkdir(parents=True)
    (locked / "on_the_locked_drive.safetensors").write_bytes(b"y")

    monkeypatch.setattr(mdr, "_load_extra_model_path_roots",
                        lambda _root: {"checkpoints": [locked]})
    return root, locked


def _lock(monkeypatch, target: Path, error: OSError = BITLOCKER):
    """Make every filesystem call against ``target`` fail the way a locked drive does.

    ``stat`` is included deliberately. A locked drive does not answer "no" to ``is_file()`` -- it
    raises, and pathlib re-raises anything outside its small set of ignorable errnos. A stub that
    only blocked directory listing would leave ``is_file()`` truthfully reporting files the code
    cannot actually open, and the test would then be measuring a drive that is not really locked.
    """
    real_scandir, real_resolve, real_walk, real_stat = os.scandir, Path.resolve, os.walk, Path.stat

    def stat(self, *args, **kwargs):
        if str(self).startswith(str(target)):
            raise error
        return real_stat(self, *args, **kwargs)

    def scandir(path=".", *args, **kwargs):
        if str(path).startswith(str(target)):
            raise error
        return real_scandir(path, *args, **kwargs)

    def resolve(self, *args, **kwargs):
        if str(self).startswith(str(target)):
            raise error
        return real_resolve(self, *args, **kwargs)

    def walk(top, *args, **kwargs):
        if str(top).startswith(str(target)):
            raise error
        return real_walk(top, *args, **kwargs)

    monkeypatch.setattr(mdr.os, "scandir", scandir)
    monkeypatch.setattr(Path, "resolve", resolve)
    monkeypatch.setattr(mdr.os, "walk", walk)
    monkeypatch.setattr(Path, "stat", stat)


def test_a_readable_pair_of_roots_indexes_both_and_reports_nothing(comfy_root):
    root, _locked = comfy_root
    _subdirs, _models, basenames, unreadable = mdr._build_model_search_context(root)
    assert "local.safetensors" in basenames
    assert "on_the_locked_drive.safetensors" in basenames
    assert unreadable == []


def test_an_unreadable_root_is_reported_instead_of_indexing_as_empty(comfy_root, monkeypatch):
    root, locked = comfy_root
    _lock(monkeypatch, locked)

    _subdirs, _models, basenames, unreadable = mdr._build_model_search_context(root)

    # The readable root still works -- one bad root must not take the whole index down.
    assert "local.safetensors" in basenames
    assert "on_the_locked_drive.safetensors" not in basenames

    assert len(unreadable) == 1, f"the locked root must be named: {unreadable}"
    assert str(locked) in unreadable[0]["path"]
    assert "BitLocker" in unreadable[0]["reason"]


def test_the_root_survives_a_resolve_that_raises(comfy_root, monkeypatch):
    """The specific line that produced the silence. ``Path.resolve()`` raising dropped the root
    before the walk, so there was no error to catch and no root to report on -- it simply was not
    in the set any more."""
    root, locked = comfy_root
    _lock(monkeypatch, locked)

    _subdirs, _models, _basenames, unreadable = mdr._build_model_search_context(root)
    assert [entry["path"] for entry in unreadable] == [str(locked)]


def test_a_root_that_is_merely_absent_is_not_an_error(tmp_path, monkeypatch):
    """extra_model_paths.yaml lists roots optimistically -- this machine's own config names an F:
    drive alongside D: -- so "not there" is the normal case and must stay quiet, or the real signal
    drowns."""
    root = tmp_path / "ComfyUI"
    (root / "models").mkdir(parents=True)
    monkeypatch.setattr(mdr, "_load_extra_model_path_roots",
                        lambda _r: {"checkpoints": [tmp_path / "no_such_drive" / "checkpoints"]})

    _subdirs, _models, _basenames, unreadable = mdr._build_model_search_context(root)
    assert unreadable == []


def test_an_empty_but_readable_root_is_not_an_error(tmp_path, monkeypatch):
    root = tmp_path / "ComfyUI"
    (root / "models").mkdir(parents=True)
    empty = tmp_path / "empty" / "checkpoints"
    empty.mkdir(parents=True)
    monkeypatch.setattr(mdr, "_load_extra_model_path_roots", lambda _r: {"checkpoints": [empty]})

    _subdirs, _models, _basenames, unreadable = mdr._build_model_search_context(root)
    assert unreadable == []


def test_the_install_plan_says_so_rather_than_offering_the_download(comfy_root, monkeypatch):
    """The consequence the user actually meets. A model on the unreadable root is reported missing
    -- there is no way to know otherwise -- but the plan has to carry the reason alongside, or the
    only thing shown is an invitation to re-download something already owned."""
    root, locked = comfy_root
    _lock(monkeypatch, locked)

    from workflow_scanner import ModelReference, WorkflowScanReport, WorkflowSource

    report = WorkflowScanReport(
        report_id="test",
        source=WorkflowSource(source_kind="file", source_path=str(root / "wf.json")),
        graph_format="api_prompt",
        node_count=1,
        nodes=[],
        model_references=[ModelReference(kind="checkpoint",
                                         value="on_the_locked_drive.safetensors",
                                         node_id="1", input_name="ckpt_name")],
    )
    plan = mdr.build_model_install_plan(report, comfy_root=root)

    missing = [dep for dep in plan.dependencies if dep.install_action != "already_present"]
    assert missing, "a model on an unreadable root cannot be seen, so it reports missing"

    assert [entry["path"] for entry in plan.unreadable_roots] == [str(locked)]
    assert any("could not be read" in message for message in plan.errors), plan.errors
    assert any("reported missing" in message for message in plan.errors), plan.errors
