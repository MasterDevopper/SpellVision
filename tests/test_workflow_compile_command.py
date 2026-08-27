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

def test_non_strict_reports_missing_and_still_returns_a_partial_prompt():
    result = convert_ui_graph(_ui_graph("SomeUninstalledNode"), SCHEMA)
    assert isinstance(result, ConversionResult)
    assert result.missing_classes == ["SomeUninstalledNode"]
    assert result.node_count == 2, "the resolvable nodes are still compiled, for inspection"
    assert "1" in result.prompt


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
