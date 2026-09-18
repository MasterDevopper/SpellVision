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

import re
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


# --------------------------------------------------------------------------------------------
# A class the live schema does not publish is not always a missing pack.
# --------------------------------------------------------------------------------------------
#
# `wangpt-optimized-json` refuses over `Latent Upscale` and `CLIP Text Encode (Positive Prompt)`.
# Those are node TITLES of core nodes, stored in `node.type` by a hand-written or LLM-authored
# graph. Nothing is missing, nothing can be installed, and "Install the missing custom nodes first"
# sends the reader to a page that cannot help them.
#
# The suggestion below is an EXACT match after normalisation -- drop every non-alphanumeric
# character, lowercase, and optionally drop one trailing parenthetical -- not a similarity ranking.
# That distinction is load-bearing: ranking packs by name similarity resolved 0 of 16 undeclared
# classes when it was measured here, which is why this repo carries a curated alias table for
# renames instead. A normalised exact hit is a different claim ("these are the same characters")
# and it is offered as a SUGGESTION only. Nothing in this module rewrites a class name; a name the
# code guesses at is how a graph silently becomes a different graph.

_TRAILING_PARENTHETICAL = re.compile(r"\s*\([^()]*\)\s*$")


def _normalise_class_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def _schema_name_index(object_info: Any) -> dict[str, str]:
    """normalised name -> the one class it can mean. Ambiguous keys are dropped.

    Built from the live schema's class names AND display names, so "Upscale Latent" reaches
    ``LatentUpscale`` from either direction. A key two classes share is dropped rather than picked
    between, the same rule ``display_name_aliases`` uses -- the live set has 9 display names owned
    by two classes apiece.
    """
    if not isinstance(object_info, dict) or not object_info:
        return {}
    seen: dict[str, str | None] = {}

    def offer(key: str, class_name: str) -> None:
        if not key:
            return
        if key in seen and seen[key] != class_name:
            seen[key] = None
            return
        seen.setdefault(key, class_name)

    for class_name, spec in object_info.items():
        if not isinstance(class_name, str):
            continue
        offer(_normalise_class_name(class_name), class_name)
        if isinstance(spec, dict) and isinstance(spec.get("display_name"), str):
            offer(_normalise_class_name(spec["display_name"]), class_name)
    return {key: cls for key, cls in seen.items() if cls}


def near_miss_suggestions(object_info: Any, class_names: Iterable[str]) -> dict[str, str]:
    """``{unresolvable name: the live class it normalises onto}`` -- a suggestion, never a rewrite.

    Two spellings are tried and both must land on exactly one live class: the name itself, and the
    name with one trailing parenthetical removed ("CLIP Text Encode (Positive Prompt)" is a title
    whose suffix distinguishes two copies of the same core node).
    """
    index = _schema_name_index(object_info)
    if not index:
        return {}
    out: dict[str, str] = {}
    for name in class_names:
        text = str(name).strip()
        if not text:
            continue
        for candidate in (text, _TRAILING_PARENTHETICAL.sub("", text)):
            hit = index.get(_normalise_class_name(candidate))
            if hit and hit != text:
                out[text] = hit
                break
    return out


def _pack_line(entry: dict[str, Any]) -> str:
    classes = list(entry.get("classes") or [])
    shown = ", ".join(classes[:_MAX_CLASSES_PER_PACK])
    if len(classes) > _MAX_CLASSES_PER_PACK:
        shown += f" (+{len(classes) - _MAX_CLASSES_PER_PACK} more)"
    where = f" ({entry['repo_url']})" if entry.get("repo_url") else ""
    return f"  - {entry['pack']}{where} -- supplies {shown}"


def missing_class_message(
    workflow: Any,
    missing_classes: Iterable[str],
    object_info: Any = None,
) -> str:
    """The refusal a caller shows the user.

    The first sentence keeps the exact wording ``no schema for node class(es): <names>.`` that has
    been this failure's signature since the converter was written -- ``flows_health.py`` parses it,
    and changing it silently would break a reader rather than fix one.

    ``object_info``, when the caller has it, turns a class the live schema simply does not publish
    into the right sentence. "Install the missing custom nodes first" is only true of a class that
    IS a custom node; said over ``Latent Upscale`` -- a core node's title -- it sends the user to
    install something that does not exist.
    """
    names = sorted({str(c) for c in missing_classes if str(c).strip()})
    if not names:
        return ""
    entries = missing_pack_entries(workflow, names)
    covered = {c for entry in entries for c in entry.get("classes") or []}
    undeclared = sorted(set(names) - covered)
    # Only ever consulted for classes no pack claims: a class a pack DOES supply is a missing pack,
    # whatever its name happens to look like.
    suggestions = near_miss_suggestions(object_info, undeclared)
    unexplained = [name for name in undeclared if name not in suggestions]

    # "Install" is earned by a class something could actually install: one whose pack the workflow
    # names, or one nothing can account for. A refusal made up entirely of retitled core nodes
    # never says it.
    installable = bool(entries) or bool(unexplained)
    guidance = (
        " Install the missing custom nodes first."
        if installable
        else " These are names the live schema does not publish, not packs to install."
    )
    body = (
        "Cannot convert UI-graph workflow: object_info has no schema for node class(es): "
        + ", ".join(names)
        + "."
        + guidance
    )
    if entries:
        body += "\nThe workflow names the pack(s) it needs:\n" + "\n".join(
            _pack_line(entry) for entry in entries
        )
    if suggestions:
        body += (
            "\nThese name(s) are not published by the live schema and read as a renamed or "
            "retitled core node:\n"
            + "\n".join(
                f'  - "{name}" -- did you mean `{suggestions[name]}`?'
                for name in sorted(suggestions)
            )
            + "\nNothing is substituted automatically. Fix the node's class in the workflow "
            "yourself -- a rename this code guessed at would silently make it a different graph."
        )
    if unexplained:
        label = "The remaining class(es)" if (entries or suggestions) else "The class(es)"
        body += (
            f"\n{label} name no pack in the workflow file, so they have to be found by hand: "
            + ", ".join(unexplained)
        )
    return body
