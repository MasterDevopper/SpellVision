"""A widget "converted to input" still occupies its ``widgets_values`` slot.

The converter used to skip such an input WITHOUT advancing the widget cursor, on the stated
assumption that a promoted widget consumes no slot. That is false in modern ComfyUI exports, and
the consequence is silent: every widget after the promoted one reads one slot early, so the graph
converts cleanly and renders the wrong thing.

Measured over the 401 bundled workflow templates: **108** nodes have a linked widget-input AND a
full ``widgets_values`` array; **8** have a genuinely short one. The 8 are why the fix keys on the
``widget`` marker the frontend writes rather than always advancing.

The end-to-end case that proved it, from ``api_bfl_flux2_max_sofa_swap.json``:

    schema order  : prompt, width, height, seed, prompt_upsampling, images
    linked        : width, height
    widgets_values: [prompt, 1024, 1024, 605236935620651, "randomize", True]

    before -> seed = 1024                (width's value)
              prompt_upsampling = 605236935620651   (an int where a bool belongs)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from comfy_graph_converter import convert_ui_graph_to_api_prompt  # noqa: E402


def object_info():
    """A node whose widget order is prompt, width, height, seed, prompt_upsampling."""
    return {
        "Target": {
            "input": {
                "required": {
                    "prompt": ["STRING", {}],
                    "width": ["INT", {}],
                    "height": ["INT", {}],
                    "seed": ["INT", {}],
                    "prompt_upsampling": ["BOOLEAN", {}],
                },
                "optional": {"images": ["IMAGE", {}]},
            }
        },
        "Source": {"input": {"required": {}}},
    }


def graph(*, widget_marker: bool, values):
    """`Target` with width+height promoted to links from `Source`."""
    return {
        "nodes": [
            {"id": 1, "type": "Source", "mode": 0, "inputs": [],
             "outputs": [{"name": "W", "type": "INT", "links": [10]},
                         {"name": "H", "type": "INT", "links": [11]}]},
            {
                "id": 2, "type": "Target", "mode": 0,
                "inputs": [
                    {"name": "width", "type": "INT", "link": 10,
                     **({"widget": {"name": "width"}} if widget_marker else {})},
                    {"name": "height", "type": "INT", "link": 11,
                     **({"widget": {"name": "height"}} if widget_marker else {})},
                ],
                "outputs": [],
                "widgets_values": values,
            },
        ],
        "links": [[10, 1, 0, 2, 0, "INT"], [11, 1, 1, 2, 1, "INT"]],
    }


FULL = ["a prompt", 1024, 1024, 605236935620651, True]


def convert(g):
    result = convert_ui_graph_to_api_prompt(g, object_info(), strict=False)
    return getattr(result, "prompt", result)


def test_a_promoted_widget_consumes_its_slot():
    api = convert(graph(widget_marker=True, values=FULL))
    inputs = api["2"]["inputs"]

    assert inputs["seed"] == 605236935620651, "seed must not pick up width's value"
    assert inputs["prompt_upsampling"] is True, "a bool input must not receive the seed"
    assert inputs["prompt"] == "a prompt"
    # The promoted widgets are links, not literals.
    assert inputs["width"] == ["1", 0]
    assert inputs["height"] == ["1", 1]


def test_a_legacy_export_without_the_widget_marker_keeps_the_old_behaviour():
    """8 of the 401 templates genuinely ship a SHORT array. Without the marker the input is a
    plain link and occupies no slot, so the old no-advance path is the correct one."""
    short = ["a prompt", 605236935620651, True]
    api = convert(graph(widget_marker=False, values=short))
    inputs = api["2"]["inputs"]

    assert inputs["seed"] == 605236935620651
    assert inputs["prompt_upsampling"] is True


def test_a_pure_link_input_never_consumes_a_slot():
    """IMAGE/MODEL inputs are not widget-backed even when the marker logic runs."""
    g = graph(widget_marker=True, values=FULL)
    g["nodes"][0]["outputs"] = [{"name": "IMAGE", "type": "IMAGE", "links": [12]}]
    g["nodes"][1]["inputs"] = [{"name": "images", "type": "IMAGE", "link": 12}]
    g["links"] = [[12, 1, 0, 2, 0, "IMAGE"]]

    inputs = convert(g)["2"]["inputs"]
    assert inputs["prompt"] == "a prompt"
    assert inputs["width"] == 1024, "a non-widget link must not shift the widget cursor"
    assert inputs["seed"] == 605236935620651


def test_the_real_template_that_exposed_this_if_it_is_installed():
    """Corpus check against the bundled template, skipped when the package is absent."""
    import json
    import pytest

    root = Path(__file__).resolve().parents[1] / ".venv" / "Lib" / "site-packages"
    matches = list(root.glob("comfyui_workflow_templates*/templates/api_bfl_flux2_max_sofa_swap.json"))
    if not matches:
        pytest.skip("bundled workflow templates not installed")

    payload = json.loads(matches[0].read_text(encoding="utf-8"))
    node = next(n for n in payload["nodes"] if n.get("type") == "Flux2MaxImageNode")
    linked = [i["widget"]["name"] for i in node["inputs"]
              if isinstance(i.get("widget"), dict) and i.get("link") is not None]

    assert linked == ["width", "height"], "fixture drifted; re-derive the expectation"
    assert node["widgets_values"][3] == 605236935620651
    assert len(node["widgets_values"]) == 6, "the array is FULL despite two promoted widgets"
