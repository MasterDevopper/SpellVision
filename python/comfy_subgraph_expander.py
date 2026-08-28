"""Flatten ComfyUI subgraphs into a plain UI graph.

Modern ComfyUI puts the real work inside ``definitions.subgraphs[]`` and references it from the
top level by UUID, so ``node["type"]`` is something like
``33e101ba-5dc4-4252-b3eb-2a67387cb931``. Nothing in this repo read ``definitions``, and the
consequence was not a visible failure but a confident wrong answer:

* The instance node carries ``properties.cnr_id == "comfy-core"`` -- the frontend stamps it with
  the core identity because the *subgraph node kind* is registered by core -- so the scanner's
  "skip core nodes" tier swallowed it whole. ``missing_custom_nodes`` came back empty, readiness
  computed ``ready = True``, and the library showed a green badge.
* The converter, which has no schema for a UUID, then refused to build the prompt at all, naming a
  hex string the user cannot act on.
* Every pack the subgraph's inner nodes needed was structurally unreachable, because no code path
  ever saw those nodes.

So one component said "ready" and another said "cannot run", about the same workflow, and the packs
that would have fixed it could not be discovered by any amount of Registry lookup.

## Why this is its own module, and not part of the converter

Flattening needs **no schema**. Conversion does. ``workflow_scanner`` runs with ComfyUI unreachable
by contract -- that is exactly when a green badge is most harmful -- so if expansion lived in
``comfy_graph_converter`` the scanner could only descend when the server happened to be up. A pure
topology pass can be imported by both, which is also what keeps their node ids identical: slot
bindings are persisted as ``"<node_id>.inputs.<name>"`` and resolved against the *converted* graph,
so the scanner and the converter must agree on ids or the bindings silently miss.

## Node id format

``"<instance_id>:<inner_id>"``, nesting as ``"115:12:3"``. This is ComfyUI's own convention -- its
frontend parses node locator ids by splitting on ``:`` -- so the ids we submit match the ones its
progress events and ``/prompt`` validation errors talk about.

## Facts that are easy to get wrong

* ``linkIds`` on ``inputs``/``outputs`` is **stale**. The bundled qwen template declares
  ``linkIds: [227, 247]`` for one input and link 227 does not exist. Boundary maps are built by
  scanning ``links`` for ``origin_id == -10`` / ``target_id == -20`` instead.
* One boundary input can feed **several** inner consumers (``image2`` reaches nodes 111 and 110).
* ``proxyWidgets`` entries are ``["-1", name]`` for a promoted boundary input, or
  ``["<inner_id>", name]`` for a widget on a specific inner node. Both occur.
* ``proxyWidgets`` and ``widgets_values`` are zipped **only** when their lengths match; they often
  do not, and a positional guess would assign values to the wrong widgets.
* Top-level links are ARRAYS ``[id, src, src_slot, dst, dst_slot, type]``; subgraph links are
  OBJECTS. Output is normalised to the array form so downstream sees one encoding.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MAX_DEPTH = 16
MAX_NODES = 5000

# A subgraph instance is identified by MEMBERSHIP in definitions.subgraphs -- exact, no guessing.
# This pattern is the fallback for the one case membership cannot cover: ComfyUI serves subgraph
# definitions from custom node packs too, so a file can reference one it does not carry. Such a
# node would otherwise pass through as an ordinary class and be reported as a missing custom node
# named `33e101ba-5dc4-...`, which is not something a user can install. No real node class is a
# bare UUID, so the shape is safe to use HERE, where nothing else can tell.
_UUID_TYPE = __import__("re").compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", __import__("re").IGNORECASE
)


def looks_like_subgraph_id(class_type: str) -> bool:
    return bool(_UUID_TYPE.match(str(class_type or "").strip()))

# Sentinel ids the frontend uses for a subgraph's own boundary.
BOUNDARY_INPUT_ID = -10
BOUNDARY_OUTPUT_ID = -20


class SubgraphRecursionError(RuntimeError):
    """A subgraph that (transitively) contains itself. Mirrors the frontend's own guard."""


@dataclass
class FlatGraph:
    nodes: list[dict[str, Any]] = field(default_factory=list)
    links: list[list[Any]] = field(default_factory=list)
    subgraphs: list[dict[str, Any]] = field(default_factory=list)
    unresolved_subgraphs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _definitions(workflow: dict[str, Any]) -> dict[str, dict[str, Any]]:
    defs = (workflow.get("definitions") or {}).get("subgraphs") or []
    out: dict[str, dict[str, Any]] = {}
    for entry in defs:
        if isinstance(entry, dict) and entry.get("id"):
            out[str(entry["id"])] = entry
    return out


def _as_link_array(link: Any) -> list[Any] | None:
    """Normalise either link encoding to the top-level array form."""
    if isinstance(link, (list, tuple)) and len(link) >= 5:
        return list(link)[:6] if len(link) >= 6 else [*list(link)[:5], None]
    if isinstance(link, dict):
        return [
            link.get("id"),
            link.get("origin_id"),
            link.get("origin_slot"),
            link.get("target_id"),
            link.get("target_slot"),
            link.get("type"),
        ]
    return None


def has_subgraphs(workflow: Any) -> bool:
    return bool(isinstance(workflow, dict) and _definitions(workflow))


def flatten_ui_graph(workflow: Any) -> FlatGraph:
    """Inline every subgraph instance. Identity on a workflow that has none.

    That identity property is the regression test for this module: a graph without
    ``definitions.subgraphs`` must come back with the same node ids, in the same order, so every
    existing import is provably untouched.
    """
    result = FlatGraph()
    if not isinstance(workflow, dict):
        return result

    definitions = _definitions(workflow)
    top_nodes = [n for n in (workflow.get("nodes") or []) if isinstance(n, dict)]
    top_links = [a for a in (_as_link_array(l) for l in (workflow.get("links") or [])) if a]

    if not definitions:
        result.nodes = top_nodes
        result.links = top_links
        return result

    # Link ids must stay unique across every inlined copy.
    used = [int(l[0]) for l in top_links if isinstance(l[0], int)]
    counter = {"next": (max(used) + 1) if used else 1}

    def new_link_id() -> int:
        value = counter["next"]
        counter["next"] += 1
        return value

    result.links = list(top_links)
    for node in top_nodes:
        class_type = str(node.get("type") or "")
        if class_type not in definitions:
            if looks_like_subgraph_id(class_type):
                # Referenced but not carried -- report it as an unresolved SUBGRAPH so readiness
                # can say "this workflow uses a subgraph whose definition is missing" instead of
                # listing a UUID among the custom nodes to install.
                result.unresolved_subgraphs.append(class_type)
            result.nodes.append(node)
            continue
        if node.get("mode") in (2, 4):
            # A muted or bypassed instance does not execute. Expanding it would inline a whole
            # graph that ComfyUI would never run, and 3 of the 6 instances in one real workflow
            # are mode 4 -- so this is the common case, not an edge case.
            result.nodes.append(node)
            result.warnings.append(
                f"subgraph instance {node.get('id')} is mode {node.get('mode')}; not expanded"
            )
            continue
        _expand(node, definitions, result, new_link_id, ancestry=(), depth=0)

    # Final prune. A subgraph definition can cite a node id in its own `links` that is absent from
    # its own `nodes` -- observed in one shipped template, where four links referenced an inner node
    # the definition never declared. A link to a node that does not exist is not harmless: nothing
    # dereferences it until submission, and then ComfyUI rejects the prompt naming a node the user
    # cannot find in their graph. Dropping it leaves the consuming input unset, which the schema
    # default covers, and the warning says how many were lost.
    emitted_ids = {str(node.get("id")) for node in result.nodes}
    kept = [l for l in result.links if str(l[1]) in emitted_ids and str(l[3]) in emitted_ids]
    if len(kept) != len(result.links):
        result.warnings.append(
            f"dropped {len(result.links) - len(kept)} link(s) referencing a node no subgraph "
            "definition declared"
        )
        result.links = kept

    return result


def _expand(instance, definitions, result, new_link_id, *, ancestry, depth) -> None:
    """Inline one instance node in place of itself."""
    subgraph_id = str(instance.get("type") or "")
    instance_path = str(instance.get("id"))
    if depth >= MAX_DEPTH or len(result.nodes) > MAX_NODES:
        result.warnings.append(f"subgraph {subgraph_id} exceeded expansion limits; left unexpanded")
        result.nodes.append(instance)
        return
    if subgraph_id in ancestry:
        raise SubgraphRecursionError(
            "subgraph contains itself: " + " -> ".join([*ancestry, subgraph_id])
        )

    definition = definitions.get(subgraph_id)
    if definition is None:
        result.unresolved_subgraphs.append(subgraph_id)
        result.nodes.append(instance)
        return

    inner_nodes = [n for n in (definition.get("nodes") or []) if isinstance(n, dict)]
    inner_links = [a for a in (_as_link_array(l) for l in (definition.get("links") or [])) if a]
    boundary_inputs = definition.get("inputs") or []
    boundary_outputs = definition.get("outputs") or []

    result.subgraphs.append({
        "id": subgraph_id,
        "name": str(definition.get("name") or ""),
        "instance_path": instance_path,
        "inner_count": len(inner_nodes),
    })

    def path(inner_id: Any) -> str:
        return f"{instance_path}:{inner_id}"

    literals = _promoted_literals(instance, boundary_inputs, result)

    # What the instance's own inputs are wired to, by boundary-input NAME.
    upstream: dict[str, Any] = {}
    for entry in (instance.get("inputs") or []):
        if isinstance(entry, dict) and entry.get("name") and entry.get("link") is not None:
            upstream[str(entry["name"])] = entry["link"]

    # slot index -> [(inner_node_id, inner_slot)] -- read from links, never from stale linkIds.
    consumers: dict[int, list[tuple[Any, Any]]] = {}
    producers: dict[int, tuple[Any, Any]] = {}
    body_links: list[list[Any]] = []
    for link in inner_links:
        _lid, origin, origin_slot, target, target_slot, ltype = (list(link) + [None] * 6)[:6]
        if origin == BOUNDARY_INPUT_ID:
            consumers.setdefault(int(origin_slot or 0), []).append((target, target_slot))
        elif target == BOUNDARY_OUTPUT_ID:
            producers[int(target_slot or 0)] = (origin, origin_slot)
        else:
            body_links.append([new_link_id(), path(origin), origin_slot,
                               path(target), target_slot, ltype])

    # Re-point each inner node's inputs at the rewritten link ids.
    inner_by_id = {str(n.get("id")): n for n in inner_nodes}
    link_for: dict[tuple[str, Any], Any] = {}
    for link in body_links:
        link_for[(str(link[3]), link[4])] = link[0]

    emitted: list[dict[str, Any]] = []
    for node in inner_nodes:
        clone = dict(node)
        clone["id"] = path(node.get("id"))
        clone["_sv_path_id"] = clone["id"]
        clone["_sv_parent"] = instance_path
        clone_inputs = []
        for index, entry in enumerate(node.get("inputs") or []):
            if not isinstance(entry, dict):
                continue
            new_entry = dict(entry)
            new_entry["link"] = link_for.get((clone["id"], index), link_for.get((clone["id"], entry.get("name"))))
            clone_inputs.append(new_entry)
        clone["inputs"] = clone_inputs
        emitted.append(clone)

    # Boundary INPUTS: either rewire to the instance's upstream, or plant a literal.
    for slot, targets in consumers.items():
        name = _boundary_name(boundary_inputs, slot)
        for target_id, target_slot in targets:
            clone = next((n for n in emitted if n["id"] == path(target_id)), None)
            if clone is None:
                continue
            entry = _input_at(clone, target_slot)
            if entry is None:
                continue
            if name in upstream:
                link_id = new_link_id()
                source = _source_of(result.links, upstream[name])
                if source is None:
                    entry["link"] = None
                    continue
                result.links.append([link_id, source[0], source[1], clone["id"], target_slot, entry.get("type")])
                entry["link"] = link_id
            elif name in literals:
                entry["link"] = None
                clone.setdefault("_sv_literals", {})[str(entry.get("name") or name)] = literals[name]
            else:
                # Nothing drives it: leave unset so ComfyUI applies the schema default. This is
                # what happens when the instance input is fed by a BYPASSED node, which is exactly
                # the real case for the qwen template's optional image2/image3.
                entry["link"] = None

    result.nodes.extend(emitted)
    result.links.extend(body_links)

    # Boundary OUTPUTS: consumers of the instance now read from the inner producer.
    for slot, (origin_id, origin_slot) in producers.items():
        for link in result.links:
            if str(link[1]) == instance_path and link[2] == slot:
                link[1] = path(origin_id)
                link[2] = origin_slot

    # The instance node no longer exists, so any link still touching it is dangling. Links INTO it
    # were superseded above by fresh links from the same upstream straight to the inner consumers;
    # links OUT of it were rewritten in place unless the subgraph declares no producer for that
    # slot. Leaving either behind produced dangling references in 89 of the 119 subgraph templates
    # -- harmless-looking, because nothing dereferences a link by id until submission, and then it
    # is a validation error pointing at a node that is not in the graph.
    result.links[:] = [
        link for link in result.links
        if str(link[1]) != instance_path and str(link[3]) != instance_path
    ]

    # Recurse into nested instances.
    for clone in list(emitted):
        if str(clone.get("type") or "") in definitions and clone.get("mode") not in (2, 4):
            result.nodes.remove(clone)
            _expand(clone, definitions, result, new_link_id,
                    ancestry=(*ancestry, subgraph_id), depth=depth + 1)


def _promoted_literals(instance, boundary_inputs, result) -> dict[str, Any]:
    """Values the instance supplies for widgets promoted to its own surface.

    ``proxyWidgets`` and ``widgets_values`` are zipped only on an exact length match. They
    frequently disagree -- a ``control_after_generate`` follow-on gets its own proxy entry, and
    many instances ship an empty ``widgets_values`` -- and a positional guess would hand values to
    the wrong widgets. On a mismatch, no override is applied and the inner nodes' own
    ``widgets_values`` still produce a valid graph.
    """
    properties = instance.get("properties") or {}
    proxies = properties.get("proxyWidgets")
    values = instance.get("widgets_values")
    if not isinstance(proxies, list) or not isinstance(values, list):
        return {}
    if len(proxies) != len(values):
        result.warnings.append(
            f"subgraph instance {instance.get('id')}: proxyWidgets({len(proxies)}) and "
            f"widgets_values({len(values)}) disagree; promoted values not applied"
        )
        return {}

    names = {str(entry.get("name")) for entry in boundary_inputs if isinstance(entry, dict)}
    literals: dict[str, Any] = {}
    for proxy, value in zip(proxies, values):
        if not (isinstance(proxy, (list, tuple)) and len(proxy) >= 2):
            continue
        inner_id, widget_name = str(proxy[0]), str(proxy[1])
        if value is None:
            continue
        if inner_id == "-1":
            if widget_name in names:
                literals[widget_name] = value
            else:
                result.warnings.append(
                    f"subgraph instance {instance.get('id')}: promoted widget {widget_name!r} "
                    "does not match any subgraph input"
                )
        else:
            literals[f"{inner_id}.{widget_name}"] = value
    return literals


def _boundary_name(boundary_inputs, slot: int) -> str:
    if 0 <= slot < len(boundary_inputs):
        entry = boundary_inputs[slot]
        if isinstance(entry, dict):
            return str(entry.get("name") or "")
    return ""


def _input_at(node: dict[str, Any], slot: Any):
    inputs = node.get("inputs") or []
    if isinstance(slot, int) and 0 <= slot < len(inputs):
        return inputs[slot]
    for entry in inputs:
        if isinstance(entry, dict) and entry.get("name") == slot:
            return entry
    return None


def _source_of(links: list[list[Any]], link_id: Any):
    for link in links:
        if link and link[0] == link_id:
            return link[1], link[2]
    return None
