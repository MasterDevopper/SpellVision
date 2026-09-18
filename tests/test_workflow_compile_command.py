"""compile_workflow_prompt: one compiler, and a three-state answer.

The command replaces the C++ compiler in WorkflowLibraryPage, which used a hardcoded 21-class
widget table and silently emitted `"inputs": {}` for anything outside it (530 nodes across 19 of 80
workflows lost every widget value).

The contract that matters most is the THIRD state. "ComfyUI is not running" is not
"no missing nodes" and not "missing nodes" -- collapsing it into either lies to the user.
`_validate_models_against_object_info` already has that bug on the model side (returns None on an
unreachable ComfyUI, caller falls back to the disk plan and can report ready), which is exactly
what these tests exist to stop happening again.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))
import workflow_library_commands as wlc  # noqa: E402
from comfy_graph_converter import ConversionResult, convert_ui_graph  # noqa: E402


SCHEMA = {
    "CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": ["COMBO", {}]}}, "output": ["MODEL"]},
    "PreviewImage": {"input": {"required": {"images": ["IMAGE", {}]}}, "output": []},
}


def _ui_graph(extra_type: str | None = None) -> dict:
    nodes = [
        {"id": 1, "type": "CheckpointLoaderSimple", "widgets_values": ["foo.safetensors"],
         "inputs": [], "outputs": [{"name": "MODEL", "type": "MODEL", "links": []}]},
        {"id": 2, "type": "PreviewImage", "widgets_values": [], "inputs": [], "outputs": []},
    ]
    if extra_type:
        nodes.append({"id": 3, "type": extra_type, "widgets_values": [], "inputs": [], "outputs": []})
    return {"nodes": nodes, "links": []}


# ---------------------------------------------------------------- converter result

def test_non_strict_refuses_rather_than_returning_a_partial_prompt():
    """The partial prompt this used to assert WAS the defect.

    "the resolvable nodes are still compiled, for inspection" reads reasonably until you notice
    that every link INTO an unresolvable node survives the omission. ComfyUI rejects the result
    with `KeyError: '<id>'` from inside validate_inputs, naming an id no user has ever seen, and
    the compile reply said `ok: false` beside a prompt_api.json that said otherwise. Nothing
    inspected the partial graph; two callers submitted it.
    """
    result = convert_ui_graph(_ui_graph("SomeUninstalledNode"), SCHEMA)
    assert isinstance(result, ConversionResult)
    assert result.missing_classes == ["SomeUninstalledNode"]
    assert result.errors, "a conversion that could not resolve a class must say so"
    assert "SomeUninstalledNode" in result.errors[0]
    assert result.prompt == {}, "no partial graph escapes"
    assert result.node_count == 0


def test_non_strict_clean_graph_reports_nothing_missing():
    result = convert_ui_graph(_ui_graph(), SCHEMA)
    assert result.missing_classes == []
    assert result.node_count == 2
    assert result.prompt["1"]["inputs"]["ckpt_name"] == "foo.safetensors"


def test_ui_only_nodes_are_dropped_not_reported_missing():
    """A Note never executes; it must not read as a missing dependency."""
    result = convert_ui_graph(_ui_graph("Note"), SCHEMA)
    assert result.missing_classes == []
    assert "3" in result.dropped_ui_only


def test_strict_mode_still_raises_for_the_submit_path():
    """Launching a graph with classes ComfyUI lacks must fail loudly, not partially submit."""
    from comfy_graph_converter import convert_ui_graph_to_api_prompt
    with pytest.raises(ValueError, match="SomeUninstalledNode"):
        convert_ui_graph_to_api_prompt(_ui_graph("SomeUninstalledNode"), SCHEMA)


# ---------------------------------------------------------------- the three states

def _run(tmp_path, monkeypatch, graph, object_info):
    (tmp_path / "workflow.json").write_text(json.dumps(graph), encoding="utf-8")

    class _FakeWS:
        @staticmethod
        def _comfy_object_info(api_url):
            if object_info is None:
                raise OSError("ComfyUI unreachable")
            return object_info

    monkeypatch.setattr(wlc, "_ws", lambda: _FakeWS)
    return wlc.handle_compile_workflow_prompt_command({"import_root": str(tmp_path)})


def test_state_convertible(tmp_path, monkeypatch):
    out = _run(tmp_path, monkeypatch, _ui_graph(), SCHEMA)
    assert out["ok"] is True
    assert out["object_info_available"] is True
    assert out["missing_classes"] == []
    assert (tmp_path / "prompt_api.json").is_file()


def test_state_missing_classes(tmp_path, monkeypatch):
    out = _run(tmp_path, monkeypatch, _ui_graph("SomeUninstalledNode"), SCHEMA)
    assert out["ok"] is False
    assert out["object_info_available"] is True
    assert out["missing_classes"] == ["SomeUninstalledNode"]


def test_a_refused_compile_writes_no_prompt_file(tmp_path, monkeypatch):
    """`ok: false` in a reply is not a fact about the disk.

    The refused prompt used to be written anyway, so a graph with unresolvable classes left a
    prompt_api.json behind that the draft builder and the readiness pass then read as a compile
    that had worked. The reply is gone by the next command; the file is not.
    """
    out = _run(tmp_path, monkeypatch, _ui_graph("SomeUninstalledNode"), SCHEMA)
    assert out["ok"] is False
    assert not (tmp_path / "prompt_api.json").exists()
    assert out["compiled_prompt_path"] is None
    assert "SomeUninstalledNode" in out["reason"]


def test_a_refused_compile_leaves_an_earlier_good_prompt_alone(tmp_path, monkeypatch):
    """Refusing must not destroy a prompt that worked -- the pack may simply be uninstalled today."""
    earlier = tmp_path / "prompt_api.json"
    earlier.write_text(json.dumps({"1": {"class_type": "PreviewImage", "inputs": {}}}), encoding="utf-8")
    _run(tmp_path, monkeypatch, _ui_graph("SomeUninstalledNode"), SCHEMA)
    assert json.loads(earlier.read_text(encoding="utf-8")) == {
        "1": {"class_type": "PreviewImage", "inputs": {}}
    }


def test_state_unknown_when_comfy_is_down(tmp_path, monkeypatch):
    """The load-bearing one: unreachable must be distinguishable from both other answers."""
    out = _run(tmp_path, monkeypatch, _ui_graph("SomeUninstalledNode"), None)
    assert out["ok"] is False
    assert out["object_info_available"] is False
    assert out["missing_classes"] == [], "must not claim to know what is missing"
    assert "not reachable" in out["reason"].lower()


def test_unknown_state_is_not_mistakable_for_success(tmp_path, monkeypatch):
    """A caller checking only `ok` and `missing_classes` must not read offline as 'all good'."""
    offline = _run(tmp_path, monkeypatch, _ui_graph(), None)
    online = _run(tmp_path, monkeypatch, _ui_graph(), SCHEMA)
    assert offline["missing_classes"] == online["missing_classes"] == []
    assert offline["ok"] is False and online["ok"] is True
    assert offline["object_info_available"] != online["object_info_available"]


def test_offline_still_says_what_kind_of_graph_it_is(tmp_path, monkeypatch):
    """Offline inspection needs one fact the schema is not required for.

    Folding `object_info_available: false` into the refusal set took offline inspection away, and
    the owner's correction is that the page should OPEN with submission closed. Opening it honestly
    means reading the values from the SOURCE graph rather than from a `prompt_api.json` of unknown
    age -- and that needs to know whether the source graph is already an API prompt (readable now)
    or a UI graph (readable only once there is a schema to convert it against). `is_ui_graph` is a
    fact about the file, so it is still answered while ComfyUI is down.
    """
    out = _run(tmp_path, monkeypatch, _ui_graph(), None)
    assert out["object_info_available"] is False
    assert out["graph_format"] == "comfy_ui_graph"
    # And it still refuses to pretend it knows anything about node availability.
    assert out["missing_classes"] == []
    assert out.get("compiled_prompt_path") is None


def test_offline_reports_an_api_prompt_as_one(tmp_path, monkeypatch):
    """An API prompt is readable with no schema at all, and saying so is what fills the cockpit."""
    out = _run(tmp_path, monkeypatch, {"1": {"class_type": "PreviewImage", "inputs": {}}}, None)
    assert out["object_info_available"] is False
    assert out["graph_format"] == "comfy_api_prompt"


def test_offline_writes_no_prompt_file(tmp_path, monkeypatch):
    """Unreachable is not a licence to leave an artefact behind that a later reader would trust."""
    _run(tmp_path, monkeypatch, _ui_graph(), None)
    assert not (tmp_path / "prompt_api.json").exists()
