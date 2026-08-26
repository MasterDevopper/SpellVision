"""Node-drift detection (comfy_node_contract) and rename absorption (comfy_node_aliases).

The behaviour that matters most here is what these modules REFUSE to do: a rewrite that is not
validated against the live schema would turn a loud /prompt rejection into a silent wrong render,
which is the most expensive failure mode this codebase has.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))
from comfy_node_aliases import apply_node_aliases, load_aliases, unresolved_classes  # noqa: E402
from comfy_node_contract import (  # noqa: E402
    contract_for_classes,
    diff_contract,
    rename_candidates,
)


def _object_info(**classes):
    """Minimal /object_info shape: {ClassName: {"input": {"required"/"optional": {...}}, "output": [...]}}"""
    return dict(classes)


def _node(required=None, optional=None, output=None):
    spec = {}
    if required:
        spec["required"] = required
    if optional:
        spec["optional"] = optional
    return {"input": spec, "output": output or []}


# --------------------------------------------------------------------------------------
# contract + diff
# --------------------------------------------------------------------------------------

def test_contract_collapses_enum_contents_to_a_count():
    """A checkpoint list changes whenever a file lands on disk; that is not API drift."""
    info = _object_info(Loader=_node(required={"ckpt_name": [["a.safetensors", "b.safetensors"]]}))
    contract = contract_for_classes(info, ["Loader"])
    assert contract["Loader"]["inputs"]["ckpt_name"]["type"] == "ENUM[2]"

    info_more_files = _object_info(Loader=_node(required={"ckpt_name": [["a.safetensors"]]}))
    other = contract_for_classes(info_more_files, ["Loader"])
    # Different count is still a difference, but it is reported as shape, not as content churn.
    assert other["Loader"]["inputs"]["ckpt_name"]["type"] == "ENUM[1]"


def test_no_drift_between_identical_cores():
    info = _object_info(A=_node(required={"x": ["INT"]}, output=["LATENT"]))
    pinned = contract_for_classes(info, ["A"])
    diff = diff_contract(pinned, contract_for_classes(info, ["A"]))
    assert diff.findings == []
    assert "no node-API drift" in diff.summary()


def test_removed_node_is_breaking():
    pinned = contract_for_classes(_object_info(A=_node(required={"x": ["INT"]})), ["A"])
    live = contract_for_classes(_object_info(), ["A"])
    diff = diff_contract(pinned, live)
    assert [f.kind for f in diff.findings] == ["node_removed"]
    assert diff.breaking


def test_removed_and_retyped_inputs_are_distinguished():
    pinned = contract_for_classes(
        _object_info(A=_node(required={"gone": ["INT"], "changed": ["INT"]})), ["A"])
    live = contract_for_classes(
        _object_info(A=_node(required={"changed": ["FLOAT"]})), ["A"])
    diff = diff_contract(pinned, live)
    kinds = {(f.kind, f.input_name) for f in diff.findings}
    assert ("input_removed", "gone") in kinds
    assert ("input_retyped", "changed") in kinds
    # Only the removal breaks submission; a retype may still submit.
    assert [f.input_name for f in diff.breaking] == ["gone"]


def test_newly_required_input_is_flagged():
    pinned = contract_for_classes(_object_info(A=_node(required={"x": ["INT"]})), ["A"])
    live = contract_for_classes(
        _object_info(A=_node(required={"x": ["INT"], "brand_new": ["INT"]})), ["A"])
    diff = diff_contract(pinned, live)
    assert [(f.kind, f.input_name) for f in diff.findings] == [("input_now_required", "brand_new")]


def test_optional_becoming_required_is_flagged():
    pinned = contract_for_classes(_object_info(A=_node(optional={"x": ["INT"]})), ["A"])
    live = contract_for_classes(_object_info(A=_node(required={"x": ["INT"]})), ["A"])
    diff = diff_contract(pinned, live)
    assert [(f.kind, f.input_name) for f in diff.findings] == [("input_now_required", "x")]


def test_new_optional_input_is_not_drift():
    """Additions that cannot break an existing graph must not create noise."""
    pinned = contract_for_classes(_object_info(A=_node(required={"x": ["INT"]})), ["A"])
    live = contract_for_classes(
        _object_info(A=_node(required={"x": ["INT"]}, optional={"extra": ["INT"]})), ["A"])
    assert diff_contract(pinned, live).findings == []


def test_rename_candidates_rank_by_outputs_and_name_overlap():
    pinned = contract_for_classes(
        _object_info(LTXVImgToVideoConditionOnly=_node(required={"image": ["IMAGE"]},
                                                       output=["CONDITIONING"])),
        ["LTXVImgToVideoConditionOnly"])
    live = contract_for_classes(
        _object_info(
            LTXVImgToVideo=_node(required={"start_image": ["IMAGE"]}, output=["CONDITIONING"]),
            SaveImage=_node(required={"images": ["IMAGE"]}, output=[]),
        ),
        ["LTXVImgToVideo", "SaveImage"])
    diff = diff_contract(pinned, contract_for_classes(_object_info(), ["LTXVImgToVideoConditionOnly"]))
    candidates = rename_candidates(diff, live, pinned)
    assert candidates["LTXVImgToVideoConditionOnly"][0] == "LTXVImgToVideo"
    assert "SaveImage" not in candidates["LTXVImgToVideoConditionOnly"]


# --------------------------------------------------------------------------------------
# alias application
# --------------------------------------------------------------------------------------

ALIASES = {
    "nodes": {
        "OldNode": {"replaced_by": ["NewNode"], "inputs": {"image": "start_image"}},
    },
    "inputs": {
        "StableNode": {"legacy": "modern"},
    },
}


def test_class_rename_is_applied_and_inputs_follow():
    workflow = {"1": {"class_type": "OldNode", "inputs": {"image": ["9", 0], "steps": 8}}}
    info = _object_info(NewNode=_node(required={"start_image": ["IMAGE"], "steps": ["INT"]}))
    notes = apply_node_aliases(workflow, info, ALIASES)
    assert workflow["1"]["class_type"] == "NewNode"
    assert workflow["1"]["inputs"]["start_image"] == ["9", 0]
    assert "image" not in workflow["1"]["inputs"]
    assert workflow["1"]["inputs"]["steps"] == 8
    assert any("OldNode -> NewNode" in n for n in notes)


def test_rename_is_skipped_when_the_old_class_still_exists():
    """If the live core still defines what the builder named, rewriting would be a silent swap."""
    workflow = {"1": {"class_type": "OldNode", "inputs": {"image": ["9", 0]}}}
    info = _object_info(
        OldNode=_node(required={"image": ["IMAGE"]}),
        NewNode=_node(required={"start_image": ["IMAGE"]}),
    )
    assert apply_node_aliases(workflow, info, ALIASES) == []
    assert workflow["1"]["class_type"] == "OldNode"
    assert workflow["1"]["inputs"] == {"image": ["9", 0]}


def test_rename_is_skipped_when_the_replacement_does_not_exist():
    """A stale alias entry must be inert, not destructive."""
    workflow = {"1": {"class_type": "OldNode", "inputs": {"image": ["9", 0]}}}
    info = _object_info(SomethingElse=_node(required={"x": ["INT"]}))
    assert apply_node_aliases(workflow, info, ALIASES) == []
    assert workflow["1"]["class_type"] == "OldNode"


def test_input_rename_on_a_class_that_kept_its_name():
    workflow = {"1": {"class_type": "StableNode", "inputs": {"legacy": 4}}}
    info = _object_info(StableNode=_node(required={"modern": ["INT"]}))
    notes = apply_node_aliases(workflow, info, ALIASES)
    assert workflow["1"]["inputs"] == {"modern": 4}
    assert any("legacy -> modern" in n for n in notes)


def test_input_rename_skipped_when_target_absent_from_schema():
    workflow = {"1": {"class_type": "StableNode", "inputs": {"legacy": 4}}}
    info = _object_info(StableNode=_node(required={"legacy": ["INT"]}))
    assert apply_node_aliases(workflow, info, ALIASES) == []
    assert workflow["1"]["inputs"] == {"legacy": 4}


def test_existing_target_value_is_never_clobbered():
    workflow = {"1": {"class_type": "StableNode", "inputs": {"legacy": 4, "modern": 99}}}
    info = _object_info(StableNode=_node(required={"modern": ["INT"]}))
    apply_node_aliases(workflow, info, ALIASES)
    assert workflow["1"]["inputs"]["modern"] == 99


def test_no_object_info_means_no_rewrites():
    """With nothing to validate against, leaving the builder's graph untouched is the safe action."""
    workflow = {"1": {"class_type": "OldNode", "inputs": {"image": ["9", 0]}}}
    assert apply_node_aliases(workflow, None, ALIASES) == []
    assert workflow["1"]["class_type"] == "OldNode"


def test_unresolved_classes_names_the_missing_node():
    workflow = {
        "1": {"class_type": "Known", "inputs": {}},
        "2": {"class_type": "Vanished", "inputs": {}},
    }
    info = _object_info(Known=_node())
    assert unresolved_classes(workflow, info) == ["Vanished"]
    assert unresolved_classes(workflow, None) == []


# --------------------------------------------------------------------------------------
# the shipped alias file
# --------------------------------------------------------------------------------------

def test_shipped_alias_file_parses_and_has_the_expected_shape():
    table = load_aliases(force_reload=True)
    assert isinstance(table.get("nodes"), dict)
    assert isinstance(table.get("inputs"), dict)


def test_missing_alias_file_degrades_to_no_aliases(tmp_path):
    """A broken or absent alias file must never take generation down."""
    assert load_aliases(tmp_path / "does_not_exist.json") == {"nodes": {}, "inputs": {}}


def test_malformed_alias_file_degrades_to_no_aliases(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert load_aliases(bad) == {"nodes": {}, "inputs": {}}


def test_native_video_shim_resolves_at_runtime():
    """native_video_graphs reaches the alias pass through a late-bound shim. Those shims compile AND
    import while still being dead -- that exact pattern took both LTX routes down once already, so
    the shim is exercised, not just referenced."""
    import native_video_graphs as nvg

    workflow = {"1": {"class_type": "OldNode", "inputs": {"image": ["9", 0]}}}
    info = _object_info(NewNode=_node(required={"start_image": ["IMAGE"]}))
    notes = nvg._apply_node_aliases(workflow, info, ALIASES)
    assert workflow["1"]["class_type"] == "NewNode"
    assert workflow["1"]["inputs"] == {"start_image": ["9", 0]}
    assert notes


def test_alias_entries_are_well_formed():
    """Guards the curated file itself: every entry must name a replacement or input map."""
    table = json.loads((Path(__file__).parents[1]
                        / "python" / "comfy_node_aliases.json").read_text(encoding="utf-8"))
    for name, entry in (table.get("nodes") or {}).items():
        assert isinstance(entry, dict), name
        assert entry.get("replaced_by") or entry.get("inputs"), f"{name} does nothing"
