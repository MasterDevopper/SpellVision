"""Unit tests for the UI-graph -> API-prompt converter.

Hermetic: object_info is a hand-built schema fixture, so these run without a live ComfyUI.
The delicate invariant under test is the widgets_values -> named-input mapping -- specifically
the control_after_generate follow-on skip (the #1 source of silent positional misalignment) and
the rule that a schema widget wired as a link consumes no widgets_values slot.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

from comfy_graph_converter import convert_ui_graph_to_api_prompt, is_ui_graph  # noqa: E402


# A minimal schema covering the nodes used below. Mirrors /object_info shape:
# input spec is [type_or_choices, opts?]; a list-of-choices head is a COMBO widget,
# INT/FLOAT/STRING/BOOLEAN are primitive widgets, and a bare type name is a connection.
OBJECT_INFO = {
    "CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [["a.safetensors", "b.safetensors"]]}}},
    "CLIPTextEncode": {"input": {"required": {"text": ["STRING", {"multiline": True}], "clip": ["CLIP"]}}},
    "EmptyLatentImage": {"input": {"required": {"width": ["INT"], "height": ["INT"], "batch_size": ["INT"]}}},
    "KSampler": {"input": {"required": {
        "model": ["MODEL"],
        "seed": ["INT", {"control_after_generate": True}],
        "steps": ["INT"],
        "cfg": ["FLOAT"],
        "sampler_name": [["euler", "dpmpp_2m"]],
        "scheduler": [["normal", "karras"]],
        "positive": ["CONDITIONING"],
        "negative": ["CONDITIONING"],
        "latent_image": ["LATENT"],
        "denoise": ["FLOAT"],
    }}},
    "Note": {"input": {}},
}


def _sample_ui_graph():
    return {
        "nodes": [
            {"id": 1, "type": "CheckpointLoaderSimple", "inputs": [], "widgets_values": ["a.safetensors"]},
            {"id": 2, "type": "CLIPTextEncode", "inputs": [{"name": "clip", "link": 1}], "widgets_values": ["a cat"]},
            {"id": 3, "type": "CLIPTextEncode", "inputs": [{"name": "clip", "link": 2}], "widgets_values": ["blurry"]},
            {"id": 4, "type": "EmptyLatentImage", "inputs": [], "widgets_values": [512, 768, 1]},
            {"id": 5, "type": "KSampler",
             "inputs": [{"name": "model", "link": 3}, {"name": "positive", "link": 4},
                        {"name": "negative", "link": 5}, {"name": "latent_image", "link": 6}],
             # seed, THEN the control_after_generate follow-on 'randomize', then the rest.
             "widgets_values": [42, "randomize", 25, 7.5, "dpmpp_2m", "karras", 1.0]},
            {"id": 9, "type": "Note", "widgets_values": ["ignore me"]},
        ],
        "links": [
            [1, 1, 1, 2, 0, "CLIP"], [2, 1, 1, 3, 0, "CLIP"], [3, 1, 0, 5, 0, "MODEL"],
            [4, 2, 0, 5, 1, "CONDITIONING"], [5, 3, 0, 5, 2, "CONDITIONING"], [6, 4, 0, 5, 3, "LATENT"],
        ],
    }


def test_is_ui_graph_discriminates_formats():
    assert is_ui_graph({"nodes": [], "links": []}) is True
    assert is_ui_graph({"3": {"class_type": "KSampler", "inputs": {}}}) is False


def test_control_after_generate_skip_keeps_widgets_aligned():
    """The 'randomize' control after `seed` must be skipped so steps/cfg/sampler land correctly."""
    api = convert_ui_graph_to_api_prompt(_sample_ui_graph(), OBJECT_INFO)
    ks = api["5"]["inputs"]
    assert ks["seed"] == 42
    assert ks["steps"] == 25          # would be 'randomize' if the control value were not skipped
    assert ks["cfg"] == 7.5
    assert ks["sampler_name"] == "dpmpp_2m"
    assert ks["scheduler"] == "karras"
    assert ks["denoise"] == 1.0


def test_links_resolve_to_node_id_and_output_slot():
    api = convert_ui_graph_to_api_prompt(_sample_ui_graph(), OBJECT_INFO)
    ks = api["5"]["inputs"]
    assert ks["model"] == ["1", 0]        # CheckpointLoaderSimple MODEL output
    assert ks["positive"] == ["2", 0]
    assert ks["latent_image"] == ["4", 0]
    # CLIPTextEncode's clip is a link (not a widget); its text is the sole widget.
    assert api["2"]["inputs"]["clip"] == ["1", 1]
    assert api["2"]["inputs"]["text"] == "a cat"


def test_widget_values_map_by_schema_order():
    api = convert_ui_graph_to_api_prompt(_sample_ui_graph(), OBJECT_INFO)
    assert api["1"]["inputs"]["ckpt_name"] == "a.safetensors"
    assert api["4"]["inputs"] == {"width": 512, "height": 768, "batch_size": 1}


def test_ui_only_nodes_are_dropped():
    api = convert_ui_graph_to_api_prompt(_sample_ui_graph(), OBJECT_INFO)
    assert "9" not in api  # the Note node never executes


def test_missing_node_class_raises_clearly():
    graph = {"nodes": [{"id": 1, "type": "SomeUninstalledCustomNode", "widgets_values": [1]}], "links": []}
    with pytest.raises(ValueError, match="SomeUninstalledCustomNode"):
        convert_ui_graph_to_api_prompt(graph, OBJECT_INFO)


def test_muted_and_bypassed_nodes_excluded():
    graph = {
        "nodes": [
            {"id": 1, "type": "CheckpointLoaderSimple", "inputs": [], "widgets_values": ["a.safetensors"]},
            {"id": 2, "type": "EmptyLatentImage", "inputs": [], "widgets_values": [512, 512, 1], "mode": 4},  # bypassed
            {"id": 3, "type": "EmptyLatentImage", "inputs": [], "widgets_values": [64, 64, 1], "mode": 2},   # muted
        ],
        "links": [],
    }
    api = convert_ui_graph_to_api_prompt(graph, OBJECT_INFO)
    assert set(api.keys()) == {"1"}
