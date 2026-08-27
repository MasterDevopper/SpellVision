"""A COMBO declared as a bare type string must still consume a widgets_values slot.

widgets_values is positional with no names, so an input the converter fails to recognise as a
widget does not merely lose its own value -- every LATER widget value shifts one slot left. That
turns into a /prompt rejection at best, and a silently wrong render at worst.

Regression: SaveWEBM declares `codec` as a bare "COMBO". The converter only accepted an inline list
of choices, so ['WanI2V', 'vp9', 16.0, 13.33] mapped to filename_prefix='WanI2V', fps='vp9',
crf=16.0 and ComfyUI answered "could not convert 'vp9' to FLOAT". The live core declares 631 such
inputs across 359 node classes, and newer cores keep converting more inputs to this form.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))
from comfy_graph_converter import convert_ui_graph_to_api_prompt  # noqa: E402


def _ui_graph(node_type: str, widgets: list) -> dict:
    return {
        "nodes": [
            {"id": 1, "type": "PreviewImage", "widgets_values": [], "inputs": [], "outputs": [
                {"name": "IMAGE", "type": "IMAGE", "links": [10]}]},
            {"id": 2, "type": node_type, "widgets_values": widgets,
             "inputs": [{"name": "images", "type": "IMAGE", "link": 10}], "outputs": []},
        ],
        "links": [[10, 1, 0, 2, 0, "IMAGE"]],
    }


SAVEWEBM_SCHEMA = {
    "PreviewImage": {"input": {"required": {"images": ["IMAGE", {}]}}, "output": ["IMAGE"]},
    "SaveWEBM": {"input": {"required": {
        "images": ["IMAGE", {}],
        "filename_prefix": ["STRING", {}],
        "codec": ["COMBO", {}],          # bare type string, options resolved at runtime
        "fps": ["FLOAT", {}],
        "crf": ["FLOAT", {}],
    }}, "output": []},
}


def test_bare_combo_consumes_a_widget_slot():
    graph = convert_ui_graph_to_api_prompt(
        _ui_graph("SaveWEBM", ["WanI2V", "vp9", 16.0, 13.3333]), SAVEWEBM_SCHEMA)
    inputs = graph["2"]["inputs"]
    assert inputs["filename_prefix"] == "WanI2V"
    assert inputs["codec"] == "vp9", "bare COMBO must receive its value, not be skipped"
    assert inputs["fps"] == 16.0, "fps must not inherit the codec value"
    assert inputs["crf"] == 13.3333


def test_dynamic_combo_v3_also_consumes_a_slot():
    """v0.34.0 re-types several inputs to COMFY_DYNAMICCOMBO_V3 (SaveVideo.codec/format)."""
    schema = {
        "PreviewImage": SAVEWEBM_SCHEMA["PreviewImage"],
        "SaveVideo": {"input": {"required": {
            "images": ["IMAGE", {}],
            "filename_prefix": ["STRING", {}],
            "format": ["COMFY_DYNAMICCOMBO_V3", {}],
            "codec": ["COMFY_DYNAMICCOMBO_V3", {}],
            "fps": ["FLOAT", {}],
        }}, "output": []},
    }
    graph = convert_ui_graph_to_api_prompt(
        _ui_graph("SaveVideo", ["clip", "mp4", "h264", 24.0]), schema)
    inputs = graph["2"]["inputs"]
    assert inputs["format"] == "mp4"
    assert inputs["codec"] == "h264"
    assert inputs["fps"] == 24.0


def test_inline_combo_still_works():
    """The classic list-of-choices form must be unaffected by the fix."""
    schema = {
        "PreviewImage": SAVEWEBM_SCHEMA["PreviewImage"],
        "Sampler": {"input": {"required": {
            "images": ["IMAGE", {}],
            "sampler_name": [["euler", "dpmpp_2m"], {}],
            "steps": ["INT", {}],
        }}, "output": []},
    }
    graph = convert_ui_graph_to_api_prompt(_ui_graph("Sampler", ["dpmpp_2m", 20]), schema)
    inputs = graph["2"]["inputs"]
    assert inputs["sampler_name"] == "dpmpp_2m"
    assert inputs["steps"] == 20


def test_connection_inputs_are_not_treated_as_widgets():
    """Guard the other direction: widening widget detection must not swallow link inputs."""
    schema = {
        "PreviewImage": SAVEWEBM_SCHEMA["PreviewImage"],
        "Thing": {"input": {"required": {
            "images": ["IMAGE", {}],
            "model": ["MODEL", {}],
            "label": ["STRING", {}],
        }}, "output": []},
    }
    graph = convert_ui_graph_to_api_prompt(_ui_graph("Thing", ["hello"]), schema)
    inputs = graph["2"]["inputs"]
    assert inputs["label"] == "hello", "MODEL must not have consumed the widget slot"
    assert "model" not in inputs or not isinstance(inputs.get("model"), str)


@pytest.mark.parametrize("declared", ["combo", "Combo", "COMBO"])
def test_combo_detection_is_case_insensitive(declared):
    schema = {
        "PreviewImage": SAVEWEBM_SCHEMA["PreviewImage"],
        "N": {"input": {"required": {
            "images": ["IMAGE", {}],
            "mode": [declared, {}],
            "value": ["INT", {}],
        }}, "output": []},
    }
    graph = convert_ui_graph_to_api_prompt(_ui_graph("N", ["fast", 7]), schema)
    assert graph["2"]["inputs"]["mode"] == "fast"
    assert graph["2"]["inputs"]["value"] == 7


def test_null_widget_value_is_omitted_but_still_consumes_its_slot():
    """A null widget value is dropped so ComfyUI can apply its default -- forwarding None turns
    into "float() argument must be ... not 'NoneType'". The cursor must still advance, or every
    later value shifts.

    Real workflows ship this way: wan-simple-t2v saves ModelSamplingSD3 with widgets_values [None].
    """
    schema = {
        "PreviewImage": SAVEWEBM_SCHEMA["PreviewImage"],
        "N": {"input": {"required": {
            "images": ["IMAGE", {}],
            "shift": ["FLOAT", {}],
            "steps": ["INT", {}],
        }}, "output": []},
    }
    graph = convert_ui_graph_to_api_prompt(_ui_graph("N", [None, 20]), schema)
    inputs = graph["2"]["inputs"]
    assert "shift" not in inputs, "None must be omitted, not forwarded"
    assert inputs["steps"] == 20, "the null slot must still be consumed"


def test_zero_and_empty_string_widgets_are_preserved():
    """Guard against over-eager dropping: 0, 0.0 and '' are real values, not absence."""
    schema = {
        "PreviewImage": SAVEWEBM_SCHEMA["PreviewImage"],
        "N": {"input": {"required": {
            "images": ["IMAGE", {}],
            "cfg": ["FLOAT", {}],
            "text": ["STRING", {}],
            "steps": ["INT", {}],
        }}, "output": []},
    }
    graph = convert_ui_graph_to_api_prompt(_ui_graph("N", [0.0, "", 0]), schema)
    inputs = graph["2"]["inputs"]
    assert inputs["cfg"] == 0.0
    assert inputs["text"] == ""
    assert inputs["steps"] == 0
