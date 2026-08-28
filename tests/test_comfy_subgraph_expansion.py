"""Subgraphs: the graph shape that reported ready and then refused to run.

Modern ComfyUI puts the real work in ``definitions.subgraphs[]`` and references it by UUID. Nothing
read ``definitions``, and the failure was not visible:

* the instance node carries ``cnr_id == "comfy-core"``, so the scanner's skip-core tier swallowed
  it and reported ZERO missing dependencies -- a green badge;
* the converter, with no schema for a UUID, then refused the whole graph naming a hex string;
* every pack the inner nodes needed was structurally unreachable.

Fixtures come from the installed ``comfyui_workflow_templates`` packages rather than being vendored,
because a copied template goes stale silently. Tests skip when the packages are absent.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from comfy_subgraph_expander import (  # noqa: E402
    SubgraphRecursionError,
    flatten_ui_graph,
    has_subgraphs,
)

TEMPLATE_GLOB = os.path.join(
    str(Path(__file__).resolve().parents[1]), ".venv", "Lib", "site-packages",
    "comfyui_workflow_templates*", "templates", "*.json",
)


def templates():
    return glob.glob(TEMPLATE_GLOB)


def load(name):
    matches = [p for p in templates() if os.path.basename(p) == name]
    if not matches:
        pytest.skip(f"bundled template {name} not installed")
    return json.loads(Path(matches[0]).read_text(encoding="utf-8"))


# --- identity: every existing import must be provably untouched ---------------------------


def test_a_graph_without_subgraphs_is_returned_unchanged():
    graph = {"nodes": [{"id": 1, "type": "KSampler"}, {"id": 2, "type": "SaveImage"}],
             "links": [[7, 1, 0, 2, 0, "IMAGE"]]}
    flat = flatten_ui_graph(graph)
    assert [n["id"] for n in flat.nodes] == [1, 2]
    assert flat.links == [[7, 1, 0, 2, 0, "IMAGE"]]
    assert not flat.subgraphs and not flat.warnings


def test_identity_holds_across_every_non_subgraph_template():
    """The regression property for this whole module. Measured: 268 of the bundled templates have
    no subgraphs, and all 268 must come back with the same node ids in the same order."""
    paths = templates()
    if not paths:
        pytest.skip("bundled workflow templates not installed")
    checked = 0
    for path in paths:
        try:
            graph = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(graph, dict) or "nodes" not in graph or has_subgraphs(graph):
            continue
        checked += 1
        before = [n.get("id") for n in graph["nodes"]]
        assert [n.get("id") for n in flatten_ui_graph(graph).nodes] == before, path
    assert checked > 100, f"expected a large identity corpus, checked {checked}"


# --- the real fixture ----------------------------------------------------------------------


def test_the_qwen_template_expands_with_its_promoted_widgets():
    graph = load("02_qwen_Image_edit_subgraphed.json")
    flat = flatten_ui_graph(graph)

    assert len(graph["nodes"]) == 6, "fixture drifted"
    assert len(flat.nodes) == 22, "17 inner nodes replace the single instance"
    assert not any(str(n["id"]) == "115" for n in flat.nodes), "the instance itself is gone"

    by_id = {str(n["id"]): n for n in flat.nodes}
    sampler = by_id["115:3"]
    assert sampler["type"] == "KSampler"
    # Promoted onto the instance's surface and set by the user there.
    assert sampler["_sv_literals"] == {"seed": 1118877715456453, "steps": 4, "cfg": 1}
    assert by_id["115:37"]["_sv_literals"]["unet_name"] == \
        "qwen_image_edit_2509_fp8_e4m3fn.safetensors"


def test_the_boundary_output_is_rewired_to_the_inner_producer():
    flat = flatten_ui_graph(load("02_qwen_Image_edit_subgraphed.json"))
    into_save = [l for l in flat.links if str(l[3]) == "60"]
    assert into_save, "SaveImage lost its input"
    assert str(into_save[0][1]) == "115:8", "must read from the inner producer, not the instance"


def test_no_link_survives_pointing_at_a_node_that_does_not_exist():
    """Dangling links are invisible until submission, and then ComfyUI rejects the prompt naming a
    node the user cannot find. Superseded boundary links caused this in 89 of 119 templates."""
    for name in ("02_qwen_Image_edit_subgraphed.json",
                 "03_video_wan2_2_14B_i2v_subgraphed.json"):
        flat = flatten_ui_graph(load(name))
        ids = {str(n["id"]) for n in flat.nodes}
        assert not [l for l in flat.links if str(l[1]) not in ids or str(l[3]) not in ids], name


def test_every_bundled_subgraph_template_flattens_cleanly():
    paths = templates()
    if not paths:
        pytest.skip("bundled workflow templates not installed")
    checked = 0
    for path in paths:
        try:
            graph = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(graph, dict) or not has_subgraphs(graph):
            continue
        checked += 1
        flat = flatten_ui_graph(graph)
        ids = {str(n["id"]) for n in flat.nodes}
        assert len(ids) == len(flat.nodes), f"duplicate node ids in {path}"
        assert not [l for l in flat.links if str(l[1]) not in ids or str(l[3]) not in ids], path
    assert checked > 50, f"expected a large subgraph corpus, checked {checked}"


# --- the traps ------------------------------------------------------------------------------


def test_a_bypassed_instance_is_not_expanded():
    """3 of the 6 instances in one real workflow are mode 4. Inlining a graph ComfyUI would never
    run is worse than leaving it alone."""
    graph = {
        "nodes": [{"id": 1, "type": "sg-1", "mode": 4, "inputs": [], "widgets_values": []}],
        "links": [],
        "definitions": {"subgraphs": [{"id": "sg-1", "name": "s", "nodes": [
            {"id": 9, "type": "KSampler", "inputs": []}], "links": [], "inputs": [], "outputs": []}]},
    }
    flat = flatten_ui_graph(graph)
    assert [str(n["id"]) for n in flat.nodes] == ["1"]
    assert any("mode 4" in w for w in flat.warnings)


def test_a_length_mismatch_applies_no_promoted_values():
    """proxyWidgets and widgets_values disagree on 112 of 161 real instances. A positional guess
    would hand values to the wrong widgets; the inner defaults are the safe answer."""
    graph = {
        "nodes": [{"id": 1, "type": "sg-1", "mode": 0, "inputs": [],
                   "widgets_values": ["only-one"],
                   "properties": {"proxyWidgets": [["-1", "a"], ["-1", "b"]]}}],
        "links": [],
        "definitions": {"subgraphs": [{
            "id": "sg-1", "name": "s",
            "nodes": [{"id": 9, "type": "KSampler",
                       "inputs": [{"name": "a", "type": "INT", "link": None}]}],
            "links": [{"id": 1, "origin_id": -10, "origin_slot": 0, "target_id": 9, "target_slot": 0}],
            "inputs": [{"name": "a", "type": "INT"}, {"name": "b", "type": "INT"}],
            "outputs": [],
        }]},
    }
    flat = flatten_ui_graph(graph)
    inner = next(n for n in flat.nodes if str(n["id"]) == "1:9")
    assert "_sv_literals" not in inner or not inner["_sv_literals"]
    assert any("disagree" in w for w in flat.warnings)


def test_a_self_referencing_subgraph_raises_rather_than_hanging():
    graph = {
        "nodes": [{"id": 1, "type": "sg-1", "mode": 0, "inputs": [], "widgets_values": []}],
        "links": [],
        "definitions": {"subgraphs": [{
            "id": "sg-1", "name": "s",
            "nodes": [{"id": 9, "type": "sg-1", "mode": 0, "inputs": [], "widgets_values": []}],
            "links": [], "inputs": [], "outputs": [],
        }]},
    }
    with pytest.raises(SubgraphRecursionError):
        flatten_ui_graph(graph)


def test_an_instance_whose_definition_is_missing_is_reported_not_dropped():
    """Definitions can be served from a custom node pack, so a file may reference one it does not
    carry. Reporting it as an unresolved SUBGRAPH is actionable; reporting a UUID as a missing node
    class is not."""
    absent = "33e101ba-5dc4-4252-b3eb-2a67387cb931"
    graph = {"nodes": [{"id": 1, "type": absent, "mode": 0, "inputs": []}],
             "links": [],
             "definitions": {"subgraphs": [{"id": "sg-other", "nodes": [], "links": [],
                                            "inputs": [], "outputs": []}]}}
    flat = flatten_ui_graph(graph)
    assert flat.unresolved_subgraphs == [absent]
    assert [str(n["id"]) for n in flat.nodes] == ["1"]


def test_a_uuid_type_is_the_only_fallback_and_a_normal_class_never_trips_it():
    """Identification is by MEMBERSHIP in definitions.subgraphs. The UUID shape is used solely for
    an instance whose definition is absent, where nothing else can tell -- and no real node class
    is a bare UUID."""
    from comfy_subgraph_expander import looks_like_subgraph_id

    assert looks_like_subgraph_id("33e101ba-5dc4-4252-b3eb-2a67387cb931")
    for name in ("KSampler", "Image Comparer (rgthree)", "", "33e101ba", "not-a-uuid-at-all"):
        assert not looks_like_subgraph_id(name)


def test_scanner_and_converter_agree_on_node_ids():
    """Slot bindings are persisted as "<node_id>.inputs.<name>" and resolved against the CONVERTED
    graph, so the two sides must produce the same ids or bindings silently miss."""
    from workflow_scanner import scan_workflow

    graph = load("02_qwen_Image_edit_subgraphed.json")
    scanned = {n.node_id for n in scan_workflow(graph).nodes}
    flattened = {str(n["id"]) for n in flatten_ui_graph(graph).nodes}
    assert scanned == flattened
