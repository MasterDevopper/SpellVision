"""Missing-node detection must be tiered, and must not invent blockers.

The old implementation compared class names against a hardcoded 26-name builtin set, which is a
tiny fraction of a ~1100-class ComfyUI core. Core classes (UNETLoader, Canny, EmptySD3LatentImage,
ModelSamplingAuraFlow, RescaleCFG, Primitive*) and nodes that never execute (Note, Reroute,
MarkdownNote, rgthree's group controls) were all reported as missing custom nodes -- permanent
false blockers that disabled the Launch button and that "Retry Dependencies" could never clear.

Measured across the 81-workflow library after this change: workflows reporting missing nodes went
39 -> 16, distinct flagged classes 165 -> 40, and the residual is genuinely-absent packs.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))
from comfy_graph_converter import _UI_ONLY_TYPES  # noqa: E402
from workflow_scanner import WorkflowNodeInfo, _detect_custom_nodes, node_pack_identity  # noqa: E402


def _node(class_type: str, *, cnr_id: str | None = None, aux_id: str | None = None) -> WorkflowNodeInfo:
    props: dict[str, str] = {}
    if cnr_id:
        props["cnr_id"] = cnr_id
    if aux_id:
        props["aux_id"] = aux_id
    return WorkflowNodeInfo(
        node_id="1",
        class_type=class_type,
        raw={"properties": props} if props else {},
    )


def test_live_class_set_is_the_authority():
    """A class ComfyUI actually has is never missing, whatever the builtin list says."""
    nodes = [_node("UNETLoader"), _node("Canny"), _node("EmptySD3LatentImage")]
    assert _detect_custom_nodes(nodes, live_classes={"UNETLoader", "Canny", "EmptySD3LatentImage"}) == []


def test_comfy_core_identity_clears_a_node_without_a_live_set():
    """Offline, a node that declares itself core is still not a blocker."""
    nodes = [_node("ModelSamplingAuraFlow", cnr_id="comfy-core")]
    assert _detect_custom_nodes(nodes, live_classes=None) == []


def test_non_executing_nodes_are_never_blockers():
    nodes = [_node("Note"), _node("Reroute"), _node("MarkdownNote"),
             _node("Fast Groups Bypasser (rgthree)"), _node("Label (rgthree)")]
    assert _detect_custom_nodes(nodes, live_classes=set()) == []


def test_ui_only_list_is_shared_with_the_converter():
    """If these drift, a workflow converts fine while the UI insists it has missing dependencies."""
    for name in ("Note", "Reroute", "Label (rgthree)"):
        assert name in _UI_ONLY_TYPES


def test_genuinely_absent_class_is_still_reported():
    nodes = [_node("SomeUninstalledPackNode", cnr_id="some-pack")]
    assert _detect_custom_nodes(nodes, live_classes={"KSampler"}) == ["SomeUninstalledPackNode"]


def test_a_custom_pack_node_is_not_excused_by_declaring_a_pack():
    """Declaring aux_id says WHERE it comes from, not that it is installed."""
    nodes = [_node("ImageResizeKJv2", aux_id="kijai/ComfyUI-KJNodes")]
    assert _detect_custom_nodes(nodes, live_classes=set()) == ["ImageResizeKJv2"]


def test_pack_identity_is_extracted():
    ident = node_pack_identity(_node("X", cnr_id="comfyui-easy-use"))
    assert ident["cnr_id"] == "comfyui-easy-use"
    assert node_pack_identity(_node("X")) == {}


def test_sv_prefixed_nodes_are_ours_and_skipped():
    assert _detect_custom_nodes([_node("SV_SomethingInternal")], live_classes=set()) == []
