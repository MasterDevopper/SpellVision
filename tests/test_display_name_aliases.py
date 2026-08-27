"""A graph may store a node's human-readable name in `type`; that is not a missing custom node.

Hand-written and LLM-generated workflows do this constantly. Measured on wangpt-optimized-json:
six of its nine "missing custom node" classes were core nodes under their display names --
"Load Diffusion Model" (UNETLoader), "VAE Decode" (VAEDecode), "KSampler (Advanced)"
(KSamplerAdvanced), "Load CLIP", "Load VAE", "Empty HunyuanVideo 1.0 Latent". Nothing was absent,
yet the workflow could never convert and Launch stayed disabled with no way to clear it.

Two rules make the fix safe rather than another silent substitution:
  * the mapping is derived from the LIVE /object_info, never a curated list that can go stale;
  * an ambiguous display name is dropped, not picked. The live set has 9 shared display names
    (`Int` is both `PrimitiveInt` and `Int-<emoji>`), and choosing one would rewire the graph to a
    node the author did not select.

The scanner and the converter must agree. If detection reported these missing while conversion
handled them, Launch would be disabled on a workflow that runs -- the same shape of bug as the
26-name builtin list.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))
from comfy_graph_converter import convert_ui_graph, display_name_aliases  # noqa: E402
from workflow_scanner import WorkflowNodeInfo, _detect_custom_nodes  # noqa: E402


OBJECT_INFO = {
    "UNETLoader": {"display_name": "Load Diffusion Model",
                   "input": {"required": {"unet_name": [["a.safetensors"]], "weight_dtype": [["default"]]}}},
    "VAEDecode": {"display_name": "VAE Decode",
                  "input": {"required": {"samples": ["LATENT"], "vae": ["VAE"]}}},
    "KSampler": {"display_name": "KSampler", "input": {"required": {}}},
    # Two classes share one display name -- must not be rewritten to either.
    "PrimitiveInt": {"display_name": "Int", "input": {"required": {"value": ["INT"]}}},
    "Int-Lab": {"display_name": "Int", "input": {"required": {"value": ["INT"]}}},
}


def test_aliases_are_built_from_the_live_schema():
    aliases = display_name_aliases(OBJECT_INFO)
    assert aliases["Load Diffusion Model"] == "UNETLoader"
    assert aliases["VAE Decode"] == "VAEDecode"


def test_an_ambiguous_display_name_is_dropped_not_picked():
    """Picking one of two classes would silently rewire the graph."""
    assert "Int" not in display_name_aliases(OBJECT_INFO)


def test_a_display_name_equal_to_its_class_name_is_not_an_alias():
    assert "KSampler" not in display_name_aliases(OBJECT_INFO)


def test_a_display_name_that_is_also_a_real_class_never_shadows_it():
    """If some pack's display name collides with another pack's class name, the class wins."""
    info = dict(OBJECT_INFO)
    info["SomePack_Thing"] = {"display_name": "KSampler", "input": {"required": {}}}
    assert display_name_aliases(info).get("KSampler") is None


# --- the converter ------------------------------------------------------------------------------

def _ui_graph(types: list[str]) -> dict:
    return {
        "nodes": [{"id": i + 1, "type": t, "widgets_values": []} for i, t in enumerate(types)],
        "links": [],
    }


def test_the_converter_rewrites_display_names_and_reports_it():
    result = convert_ui_graph(_ui_graph(["Load Diffusion Model", "VAE Decode"]), OBJECT_INFO)
    assert result.missing_classes == []
    assert {n["class_type"] for n in result.prompt.values()} == {"UNETLoader", "VAEDecode"}
    assert result.resolved_display_names == {"Load Diffusion Model": "UNETLoader", "VAE Decode": "VAEDecode"}


def test_widget_values_still_map_after_a_rewrite():
    """The rewrite must land on the real schema, or every widget value is dropped."""
    graph = {"nodes": [{"id": 1, "type": "Load Diffusion Model",
                        "widgets_values": ["flux.safetensors", "fp8_e4m3fn"]}], "links": []}
    result = convert_ui_graph(graph, OBJECT_INFO)
    assert result.prompt["1"]["inputs"] == {"unet_name": "flux.safetensors", "weight_dtype": "fp8_e4m3fn"}


def test_an_ambiguous_name_stays_missing_in_the_converter():
    result = convert_ui_graph(_ui_graph(["Int"]), OBJECT_INFO)
    assert result.missing_classes == ["Int"]
    assert result.resolved_display_names == {}


def test_a_genuinely_absent_class_is_still_missing():
    result = convert_ui_graph(_ui_graph(["SomeUninstalledNode"]), OBJECT_INFO)
    assert result.missing_classes == ["SomeUninstalledNode"]


# --- the scanner must agree ----------------------------------------------------------------------

def _nodes(types: list[str]) -> list[WorkflowNodeInfo]:
    return [WorkflowNodeInfo(node_id=str(i), class_type=t, raw={}) for i, t in enumerate(types)]


def test_detection_and_conversion_agree_on_display_names():
    """The failure this guards: detection says 'missing custom nodes', conversion succeeds anyway,
    and the Launch button stays disabled on a workflow that runs."""
    types = ["Load Diffusion Model", "VAE Decode"]
    aliases = set(display_name_aliases(OBJECT_INFO))
    assert _detect_custom_nodes(_nodes(types), live_classes=set(OBJECT_INFO),
                                live_display_names=aliases) == []
    assert convert_ui_graph(_ui_graph(types), OBJECT_INFO).missing_classes == []


def test_detection_without_the_alias_set_is_unchanged():
    """Callers that cannot build the alias set keep the previous, stricter behaviour."""
    assert _detect_custom_nodes(_nodes(["Load Diffusion Model"]), live_classes=set(OBJECT_INFO)) \
        == ["Load Diffusion Model"]
