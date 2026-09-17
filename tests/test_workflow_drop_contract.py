"""The contract a dropped workflow is answered with, asserted against the OWNER's real workflows.

Two facts had no home before this.

**The import reply had no launch-readiness field.** `WorkflowImportResult` answered "what is in this
graph" and stopped, so every caller that wanted "can this run here" either made a second round trip
(only Flows did) or guessed. The drop path guessed: `safe_to_submit` was the literal `false`, under a
comment saying the IMPORTER reports no readiness -- true of the importer, false of the system,
because the readiness command was two files away. It is on the reply now, computed by the same
function `check_workflow_launch_readiness` returns, so the two cannot drift into disagreeing about
the same workflow.

**Readiness had two answers where it needed three.** A UI-graph export hides its model names in
positional `widgets_values`, so `scan_workflow` returns `model_references=[]` -- and zero references
read as "no models missing" and carried the whole verdict to `ready`. It shipped:
`krea2-compact-t2i-v10` had `"ok": true` stored beside `models 0/0 present`, a green badge on a
workflow whose checkpoints nobody had looked at. Three of its four models are in fact absent. The
verdict is now UNDETERMINED (`ready: None`) when the model half could not be measured, and the
readiness pass compiles a UI graph in memory -- the same `convert_ui_graph` the compile command and
the launch path use -- so that it usually can be.

The fixtures are the owner's own workflows under `runtime/imported_workflows`, in both shapes: UI
graphs (the majority, and the ones that produced the bug) and the single API-prompt graph that is
the positive control. Nothing here is a synthetic graph -- classifying graphs nobody on this project
wrote is the whole job.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "python"))

import node_dependency_resolver as ndr  # noqa: E402
import workflow_library_commands as wlc  # noqa: E402
from workflow_scanner import load_workflow_source, scan_workflow  # noqa: E402

OWNER_WORKFLOWS = REPO / "runtime" / "imported_workflows"
NODE_CATALOG = str(REPO / "python" / "starter_node_catalog.json")


# --------------------------------------------------------------------------- helpers

def owner_dir(slug: str) -> Path:
    path = OWNER_WORKFLOWS / slug
    assert path.is_dir(), f"owner workflow {slug} is not in this checkout"
    return path


class _OfflineWS:
    """ComfyUI unreachable. The honest worst case, and the one that must not report `ready`."""

    @staticmethod
    def _comfy_object_info(api_url):
        raise OSError("ComfyUI unreachable")


def _import(tmp_path, monkeypatch, slug: str, *, files=("workflow.json",)) -> dict:
    monkeypatch.setattr(wlc, "_ws", lambda: _OfflineWS)
    source = owner_dir(slug) / files[0]
    # comfy_root is an empty directory: no ComfyUI-Manager, so nothing shells out, and every model
    # reads as absent. That makes the readiness verdict deterministic without a live backend.
    comfy_root = tmp_path / "comfy"
    comfy_root.mkdir()
    return wlc.handle_import_workflow_command({
        "source": str(source),
        "destination_root": str(tmp_path / "imported"),
        "profile_name": slug,
        "comfy_root": str(comfy_root),
        "node_catalog": NODE_CATALOG,
        "model_cache_root": str(tmp_path / "cache"),
    })


def _readiness_over(tmp_path, monkeypatch, slug: str, *, names: tuple[str, ...]) -> dict:
    """Run the readiness command over a COPY of the owner's own files, taking only `names`."""
    monkeypatch.setattr(wlc, "_ws", lambda: _OfflineWS)
    root = tmp_path / slug
    root.mkdir(parents=True)
    for name in names:
        shutil.copy2(owner_dir(slug) / name, root / name)
    comfy_root = tmp_path / "comfy"
    comfy_root.mkdir(exist_ok=True)
    return wlc.handle_check_workflow_launch_readiness_command({
        "import_root": str(root),
        "comfy_root": str(comfy_root),
        "node_catalog": NODE_CATALOG,
        "model_cache_root": str(tmp_path / "cache"),
    })


# --------------------------------------------------------------------------- classification
#
# What each of the owner's graphs IS. The drop path routes on this, so a graph that starts
# classifying differently has to change this table deliberately rather than quietly land somewhere
# else. mmaudio is here because the answer has to be allowed to be "nowhere": v2v has no page, and
# the drop refuses it by name instead of dropping it on t2i because the filename looked plausible.

@pytest.mark.parametrize("slug,task,media", [
    ("krea2-compact-t2i-v10", "t2i", "image"),
    ("krea2-pro-grade-v17", "i2i", "image"),
    ("krea2-character-forge-sheet", "i2i", "image"),
    ("asteral-json", "t2i", "image"),
    ("pose-control-v5-2-json", "i2i", "image"),
    ("wan-simple-t2v-json", "t2v", "video"),
    ("wan-simple-i2v-json", "i2v", "video"),
    ("mmaudio-json", "v2v", "video"),
    ("ltx-api-json", "v2v", "video"),
])
def test_each_owner_workflow_classifies_to_what_it_actually_is(slug, task, media):
    source, payload = load_workflow_source(str(owner_dir(slug) / "workflow.json"))
    report = scan_workflow(payload, source_kind=source.source_kind)
    assert report.inferred_task_command == task
    assert report.inferred_media_type == media


def test_the_three_krea2_workflows_are_ui_graphs_with_no_compiled_prompt():
    # The shape that produced the bug, and the reason the drop path compiles. Asserted rather than
    # assumed: if one of them gains a prompt_api.json the tests below stop measuring what they think.
    for slug in ("krea2-compact-t2i-v10", "krea2-pro-grade-v17", "krea2-character-forge-sheet"):
        payload = json.loads((owner_dir(slug) / "workflow.json").read_text(encoding="utf-8"))
        assert isinstance(payload.get("nodes"), list), f"{slug} is no longer a UI graph"
        assert not (owner_dir(slug) / "prompt_api.json").is_file(), f"{slug} now has a compiled prompt"


# --------------------------------------------------------------------------- readiness on the reply

def test_the_import_reply_carries_a_launch_readiness_verdict(tmp_path, monkeypatch):
    reply = _import(tmp_path, monkeypatch, "asteral-json")
    assert reply["ok"] is True
    assert "launch_readiness" in reply, "the import reply must answer 'can this run here'"
    block = reply["launch_readiness"]
    for key in ("ready", "readiness_determined", "summary", "missing_node_classes",
                "missing_runtime_assets"):
        assert key in block, f"the readiness block is missing {key}"


def test_a_failed_import_reports_readiness_as_undetermined_not_as_not_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(wlc, "_ws", lambda: _OfflineWS)
    comfy_root = tmp_path / "comfy"
    comfy_root.mkdir()
    reply = wlc.handle_import_workflow_command({
        "source": str(tmp_path / "does-not-exist.json"),
        "destination_root": str(tmp_path / "imported"),
        "comfy_root": str(comfy_root),
        "node_catalog": NODE_CATALOG,
    })
    assert reply["ok"] is False
    assert reply["launch_readiness"]["ready"] is None
    assert reply["launch_readiness"]["readiness_determined"] is False


# --------------------------------------------------------------------------- the third state

def test_a_ui_graph_whose_models_could_not_be_read_is_undetermined_not_ready(tmp_path, monkeypatch):
    # THE regression. krea2-compact-t2i-v10 stored `"ok": true` beside `models 0/0 present`: the
    # scan saw no model references because they live in widgets_values, and no references read as
    # nothing missing. With no live schema to compile against, the only honest answer is that the
    # models were not checked.
    reply = _readiness_over(tmp_path, monkeypatch, "krea2-compact-t2i-v10", names=("workflow.json",))
    assert reply["ok"] is True, "the command itself succeeded"
    assert reply["ready"] is None, "an unmeasured model set must not read as ready"
    assert reply["readiness_determined"] is False
    assert "could not be read" in reply["undetermined_reason"]
    assert "NOT CHECKED" in reply["summary"], "the summary has to say so where the user reads it"


def test_a_compiled_prompt_beside_the_graph_makes_the_verdict_determinate(tmp_path, monkeypatch):
    # The same shape with the models visible: a real verdict, not a shrug. asteral-json carries the
    # owner's own compiled prompt, and its five checkpoints/LoRAs are read out of it.
    reply = _readiness_over(tmp_path, monkeypatch, "asteral-json",
                            names=("workflow.json", "prompt_api.json"))
    assert reply["readiness_determined"] is True
    assert isinstance(reply["ready"], bool)
    assert reply["model_counts"]["checked"] > 0, "the models were actually looked at"


def test_the_api_prompt_graph_is_determinate_with_no_compile_at_all(tmp_path, monkeypatch):
    # ltx-api-json is the only owner workflow stored as an API prompt. scan_workflow reads its model
    # literals out of named inputs directly, so nothing has to be compiled for the verdict to mean
    # something -- the positive control the UI-graph path is measured against.
    source, payload = load_workflow_source(str(owner_dir("ltx-api-json") / "workflow.json"))
    assert not isinstance(payload.get("nodes"), list), "ltx-api-json is no longer an API prompt"
    report = scan_workflow(payload, source_kind=source.source_kind)
    assert report.model_references, "an API prompt exposes its models to the scan"


# --------------------------------------------------------------------------- one author

def test_the_import_reply_and_the_readiness_command_give_the_same_verdict(tmp_path, monkeypatch):
    # Two replies, one function. If these ever disagree, a dropped workflow and the same workflow in
    # Flows would be telling the user different things about the same file on the same machine.
    reply = _import(tmp_path, monkeypatch, "krea2-character-forge-sheet")
    import_root = reply["artifacts"]["import_root"]
    fresh = wlc.handle_check_workflow_launch_readiness_command({
        "import_root": import_root,
        "comfy_root": str(tmp_path / "comfy"),
        "node_catalog": NODE_CATALOG,
        "model_cache_root": str(tmp_path / "cache"),
    })
    block = reply["launch_readiness"]
    assert fresh["ok"] is True
    for key in ("ready", "readiness_determined", "missing_node_classes", "missing_runtime_assets",
                "node_counts", "model_counts"):
        assert block[key] == fresh[key], f"the two readiness answers disagree on {key}"


def test_the_verdict_is_written_into_the_profile_the_library_reads(tmp_path, monkeypatch):
    # Flows, Home and the launch path all read `metadata.last_launch_readiness` off profile.json. A
    # freshly imported workflow used to have none at all, so it showed as never checked until
    # somebody pressed a button.
    reply = _import(tmp_path, monkeypatch, "asteral-json")
    profile = json.loads(Path(reply["artifacts"]["profile_path"]).read_text(encoding="utf-8"))
    stored = profile["metadata"]["last_launch_readiness"]
    assert stored["summary"] == reply["launch_readiness"]["summary"]
    assert stored["ok"] is bool(reply["launch_readiness"]["ready"])
    assert "determined" in stored, "the profile has to carry the third state too"


# --------------------------------------------------------------------------- the cost of asking

def test_no_missing_classes_means_no_subprocess(monkeypatch, tmp_path):
    """The installed-node snapshot is only consulted to place a MISSING class's pack.

    It shells out to cm-cli, and it was being run whether or not there was anything to place:
    measured at 132.6 s of a 134.4 s readiness pass on a workflow with zero missing classes -- and
    both the import path and the readiness path build this plan, so a dropped workflow paid it twice
    on its way to a page. This asserts the skip behaviourally, by making the call fatal.
    """
    calls: list[str] = []

    def _explode(*args, **kwargs):
        calls.append("called")
        raise AssertionError("the installed-node snapshot must not run with nothing to resolve")

    monkeypatch.setattr(ndr, "list_installed_nodes", _explode)

    source, payload = load_workflow_source(str(owner_dir("asteral-json") / "workflow.json"))
    clean = scan_workflow(payload, source_kind=source.source_kind)
    assert not clean.missing_custom_nodes, "asteral-json resolves every class in this checkout"
    plan = ndr.build_node_install_plan(clean, comfy_root=str(tmp_path), node_catalog=NODE_CATALOG,
                                       search_undeclared=False)
    assert plan.install_actions == []
    assert calls == []

    # ... and the control: with something to resolve, it IS consulted. Otherwise this test would
    # pass just as well against a function that had deleted the snapshot outright.
    source, payload = load_workflow_source(str(owner_dir("wan-simple-i2v-json") / "workflow.json"))
    dirty = scan_workflow(payload, source_kind=source.source_kind)
    assert dirty.missing_custom_nodes, "wan-simple-i2v-json has unresolved classes in this checkout"
    with pytest.raises(AssertionError, match="must not run"):
        ndr.build_node_install_plan(dirty, comfy_root=str(tmp_path), node_catalog=NODE_CATALOG,
                                    search_undeclared=False)
    assert calls == ["called"]
