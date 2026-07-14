"""Convert a ComfyUI **UI-graph** export (``{"nodes": [...], "links": [...]}`` -- what ComfyUI's
normal *Save* produces, and therefore what nearly every community workflow ships as) into the
**API-prompt** graph (``{node_id: {"class_type", "inputs"}}``) that the ``/prompt`` endpoint accepts.

Why this exists: ``/prompt`` rejects the UI-graph format outright (HTTP 500), so a UI-graph workflow
cannot launch at all without this conversion -- and once converted, the existing scanner extracts
model references + slot bindings from it for free (the ``inputs`` become the named dict it already reads).

The one thing that must not be guessed is the ``widgets_values`` -> named-input mapping: ComfyUI stores
a node's widget values as a POSITIONAL array with no names, and the positions map to input names only
via the node's schema. We take that schema from live ``/object_info`` (the caller supplies it) and never
assume positions. Two schema facts drive the mapping:
  * An input is a *widget* (consumes a ``widgets_values`` slot) iff its type spec is a COMBO (the type is
    a list of choices) or a primitive (INT/FLOAT/STRING/BOOLEAN). Everything else (MODEL/CLIP/VAE/
    CONDITIONING/LATENT/IMAGE/...) is a *connection*, filled from a link, not a widget.
  * A widget whose schema opts carry ``control_after_generate`` (seed / noise_seed) is followed by an
    EXTRA ``widgets_values`` entry (the "fixed"/"randomize"/... control) that must be skipped -- the #1
    source of silent positional misalignment.

Scope / known limits (reported, not silently wrong): pure-UI and non-executing nodes (Note, MarkdownNote,
muted ``mode==2``, bypassed ``mode==4``) are dropped; a link whose source was dropped leaves that input
unset. Reroute / GetNode-SetNode pass-through and bypass rewiring are NOT resolved here -- workflows that
lean on them may convert incompletely (they still bind, but may not render). Nodes ``object_info`` does
not know (missing custom nodes) raise a clear error rather than emitting a malformed node.
"""
from __future__ import annotations

from typing import Any

_PRIMITIVE_WIDGET_TYPES = {"INT", "FLOAT", "STRING", "BOOLEAN"}
# Nodes that never execute -> excluded from the API prompt entirely.
_UI_ONLY_TYPES = {"Note", "MarkdownNote", "Reroute", "Reroute (rgthree)", "PrimitiveNode"}


def _input_is_widget(type_spec: Any) -> bool:
    """True if this object_info input spec is a widget (consumes a widgets_values slot)."""
    if not isinstance(type_spec, list) or not type_spec:
        return False
    head = type_spec[0]
    if isinstance(head, list):
        return True  # COMBO (a list of choices)
    return head in _PRIMITIVE_WIDGET_TYPES


def _has_control_after_generate(type_spec: Any) -> bool:
    return (
        isinstance(type_spec, list)
        and len(type_spec) > 1
        and isinstance(type_spec[1], dict)
        and bool(type_spec[1].get("control_after_generate"))
    )


def is_ui_graph(workflow: Any) -> bool:
    """A UI-graph export carries a top-level ``nodes`` list (API-prompt graphs are node-id -> node dicts)."""
    return isinstance(workflow, dict) and isinstance(workflow.get("nodes"), list)


def convert_ui_graph_to_api_prompt(workflow: dict[str, Any], object_info: dict[str, Any]) -> dict[str, Any]:
    """Convert a UI-graph workflow into an API-prompt graph using ``object_info`` as the schema source.

    Raises ``ValueError`` naming the node class(es) ``object_info`` does not know (missing custom nodes)
    rather than emitting a malformed graph.
    """
    nodes = workflow.get("nodes") or []
    links = workflow.get("links") or []

    # link_id -> [src_node_id(str), src_output_slot]
    link_map: dict[Any, list[Any]] = {}
    for link in links:
        if isinstance(link, list) and len(link) >= 5:
            link_map[link[0]] = [str(link[1]), link[2]]

    # Nodes that do not execute (muted / bypassed / pure-UI) are dropped; links sourced from them go unset.
    excluded: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id"))
        if node.get("mode") in (2, 4) or str(node.get("type") or "") in _UI_ONLY_TYPES:
            excluded.add(node_id)

    unknown: set[str] = set()
    api: dict[str, Any] = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id"))
        if node_id in excluded:
            continue
        class_type = str(node.get("type") or "")
        node_schema = object_info.get(class_type)
        if not isinstance(node_schema, dict):
            unknown.add(class_type)
            continue

        schema_inputs = node_schema.get("input", {}) or {}
        ordered = list((schema_inputs.get("required") or {}).items()) + list((schema_inputs.get("optional") or {}).items())

        # Inputs wired to a link in the UI graph: name -> link_id.
        connected: dict[str, Any] = {}
        for inp in node.get("inputs") or []:
            if isinstance(inp, dict) and inp.get("link") is not None and inp.get("name"):
                connected[str(inp["name"])] = inp["link"]

        widgets = node.get("widgets_values")
        widgets = widgets if isinstance(widgets, list) else []

        api_inputs: dict[str, Any] = {}
        widget_cursor = 0
        for name, type_spec in ordered:
            if name in connected:
                src = link_map.get(connected[name])
                if src is not None and src[0] not in excluded:
                    api_inputs[name] = src
                # A widget that was "converted to input" (now a link) consumes no widgets_values slot.
                continue
            if _input_is_widget(type_spec):
                if widget_cursor < len(widgets):
                    api_inputs[name] = widgets[widget_cursor]
                    widget_cursor += 1
                    if _has_control_after_generate(type_spec):
                        widget_cursor += 1  # skip the control_after_generate follow-on value

        api[node_id] = {"class_type": class_type, "inputs": api_inputs}

    if unknown:
        raise ValueError(
            "Cannot convert UI-graph workflow: object_info has no schema for node class(es): "
            + ", ".join(sorted(unknown))
            + ". Install the missing custom nodes first."
        )
    return api
