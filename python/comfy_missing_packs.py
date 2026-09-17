"""Turn "this ComfyUI has no schema for these node classes" into something the user can act on.

``KeyError: '3024'`` is what ComfyUI says when a prompt references a node that is not there.
``CR Text Concatenate is missing`` is better. ``This workflow needs ComfyUI_Comfyroll_CustomNodes
(https://github.com/Suzie1/ComfyUI_Comfyroll_CustomNodes), which is not installed`` is the sentence
that ends the problem, and the workflow file already contains it: ComfyUI writes
``properties.cnr_id`` / ``aux_id`` / ``ver`` onto every node it saves.

So this reads the pack identity out of the graph the user just dropped -- **offline, no Registry
call** -- via ``workflow_pack_resolver.declared_packs``, which is the repo's one place that knows
how those properties are shaped. Measured over the 14 imported UI graphs that currently convert to a
broken prompt: 10 name at least one pack this way. The rest declare nothing, and those classes are
reported bare rather than guessed at -- ranking packs by name similarity resolved 0 of 16 undeclared
classes when it was measured, so a guess here would be noise wearing the costume of an answer.

Licence is not consulted. It is disclosure elsewhere in this codebase and it is not a gate here
either: refusing to *name* a pack because its licence is UNKNOWN would hide exactly the packs that
matter (kjnodes, VHS, rgthree and easy-use all normalise to UNKNOWN).
"""
from __future__ import annotations

from typing import Any, Iterable

# Kept short deliberately: the message is read in a dialog and a log line, not a report.
_MAX_CLASSES_PER_PACK = 6


def _ui_graph_nodes(workflow: Any) -> list[dict[str, Any]]:
    if not isinstance(workflow, dict):
        return []
    nodes = workflow.get("nodes")
    if not isinstance(nodes, list):
        return []
    return [n for n in nodes if isinstance(n, dict)]


def _merge_by_cnr(packs: list[Any]) -> list[Any]:
    """One entry per pack when a graph declares the same pack both ways.

    A graph assembled from two exports can carry ``cnr_id`` alone on one node and
    ``aux_id`` + ``cnr_id`` on another, which ``declared_packs`` keys separately (``aux_id`` wins
    when present). trying-t2v does exactly that with Comfyroll and would otherwise be told twice to
    install the same repository.
    """
    merged: list[Any] = []
    by_cnr: dict[str, Any] = {}
    for pack in packs:
        cnr = (pack.cnr_id or "").strip().lower()
        if not cnr:
            merged.append(pack)
            continue
        existing = by_cnr.get(cnr)
        if existing is None:
            by_cnr[cnr] = pack
            merged.append(pack)
            continue
        existing.aux_id = existing.aux_id or pack.aux_id
        existing.declared_version = existing.declared_version or pack.declared_version
        existing.class_names = sorted(set(existing.class_names) | set(pack.class_names))
    return merged


def missing_pack_entries(workflow: Any, missing_classes: Iterable[str]) -> list[dict[str, Any]]:
    """``[{pack, repo_url, version, classes}]`` for the classes whose nodes declare a pack.

    Never raises and never reaches the network: a workflow that declares nothing, or a
    ``workflow_pack_resolver`` that cannot be imported, yields ``[]`` and the caller falls back to
    naming the bare classes.
    """
    wanted = sorted({str(c) for c in missing_classes if str(c).strip()})
    if not wanted:
        return []
    try:
        # Imported lazily: workflow_pack_resolver -> workflow_scanner -> comfy_graph_converter, and
        # the converter is this module's own caller.
        from workflow_pack_resolver import _github_repo_url, declared_packs
        from workflow_scanner import WorkflowNodeInfo
    except Exception:
        return []

    try:
        infos = [
            WorkflowNodeInfo(node_id=str(n.get("id")), class_type=str(n.get("type") or ""), raw=n)
            for n in _ui_graph_nodes(workflow)
        ]
        packs, _undeclared = declared_packs(infos, wanted)
    except Exception:
        return []

    entries: list[dict[str, Any]] = []
    for pack in _merge_by_cnr(packs):
        entries.append({
            "pack": pack.cnr_id or pack.aux_id or pack.key,
            "repo_url": _github_repo_url(pack.aux_id) if pack.aux_id else None,
            "version": pack.declared_version,
            "classes": sorted(pack.class_names),
        })
    entries.sort(key=lambda e: str(e["pack"]).lower())
    return entries


def _pack_line(entry: dict[str, Any]) -> str:
    classes = list(entry.get("classes") or [])
    shown = ", ".join(classes[:_MAX_CLASSES_PER_PACK])
    if len(classes) > _MAX_CLASSES_PER_PACK:
        shown += f" (+{len(classes) - _MAX_CLASSES_PER_PACK} more)"
    where = f" ({entry['repo_url']})" if entry.get("repo_url") else ""
    return f"  - {entry['pack']}{where} -- supplies {shown}"


def missing_class_message(workflow: Any, missing_classes: Iterable[str]) -> str:
    """The refusal a caller shows the user.

    The first sentence keeps the exact wording ``no schema for node class(es): <names>.`` that has
    been this failure's signature since the converter was written -- ``flows_health.py`` parses it,
    and changing it silently would break a reader rather than fix one.
    """
    names = sorted({str(c) for c in missing_classes if str(c).strip()})
    if not names:
        return ""
    entries = missing_pack_entries(workflow, names)
    covered = {c for entry in entries for c in entry.get("classes") or []}
    body = (
        "Cannot convert UI-graph workflow: object_info has no schema for node class(es): "
        + ", ".join(names)
        + ". Install the missing custom nodes first."
    )
    if entries:
        body += "\nThe workflow names the pack(s) it needs:\n" + "\n".join(
            _pack_line(entry) for entry in entries
        )
    undeclared = sorted(set(names) - covered)
    if undeclared:
        label = "The remaining class(es)" if entries else "The class(es)"
        body += (
            f"\n{label} name no pack in the workflow file, so they have to be found by hand: "
            + ", ".join(undeclared)
        )
    return body
