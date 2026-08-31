"""Absorb ComfyUI node/input renames so a core or custom-pack update does not break our graphs.

SpellVision owns all graph construction, so every builder names node classes and input keys that
were grounded against one particular ComfyUI. When upstream renames a node or an input, every graph
naming the old identity starts failing /prompt validation -- and the builders were correct when
written, so "fix the builder" means re-grounding all of them against each new core.

This module is the alternative: a data-driven rewrite applied to the finished graph immediately
before submission. Builders keep naming what they were grounded on; the alias map translates to
whatever the live core actually calls it.

This is deliberately the same shape as `_resolve_graph_model_names` in comfy_prompt_client, which
already rewrites model FILE names against the live catalog for exactly the same reason (a baked-in
"nova.safetensors" vs ComfyUI's catalogued "sdxl\\nova.safetensors"). Node and input identity is
that problem one level up, at the same seam.

**Every rewrite is validated against the live /object_info before it is applied.** A rename is only
taken when the replacement class genuinely exists, and an input rename only when the target input
is genuinely in that class's schema. A blind rewrite would turn a loud 400 into a silent wrong
render, which is strictly worse -- graphs that submit successfully but render garbage are this
codebase's most expensive failure mode.

Curated entries only. Auto-detected rename *candidates* belong in a report for a human to promote
into this file; they must never be applied on a guess.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

ALIAS_FILE = Path(__file__).with_name("comfy_node_aliases.json")

_CACHE: dict[str, Any] | None = None


def load_aliases(path: Path | None = None, *, force_reload: bool = False) -> dict[str, Any]:
    """The curated alias map. Missing or malformed file degrades to "no aliases", never raises --
    a broken alias file must not take generation down with it."""
    global _CACHE
    if _CACHE is not None and not force_reload and path is None:
        return _CACHE

    target = path or ALIAS_FILE
    data: dict[str, Any] = {"nodes": {}, "inputs": {}}
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            data = {
                "nodes": raw.get("nodes") if isinstance(raw.get("nodes"), dict) else {},
                "inputs": raw.get("inputs") if isinstance(raw.get("inputs"), dict) else {},
            }
    except FileNotFoundError:
        pass
    except Exception as exc:
        log.warning("comfy node aliases: could not read %s (%s); continuing with no aliases", target, exc)

    if path is None:
        _CACHE = data
    return data


def _class_input_names(object_info: dict[str, Any], class_type: str) -> set[str]:
    node = object_info.get(class_type)
    if not isinstance(node, dict):
        return set()
    spec = node.get("input")
    if not isinstance(spec, dict):
        return set()
    names: set[str] = set()
    for kind in ("required", "optional"):
        section = spec.get(kind)
        if isinstance(section, dict):
            names.update(section.keys())
    return names


def _resolve_replacement(entry: dict[str, Any], object_info: dict[str, Any]) -> str | None:
    """First candidate the LIVE core actually defines. Ordered by preference in the alias file."""
    replaced_by = entry.get("replaced_by")
    if isinstance(replaced_by, str):
        replaced_by = [replaced_by]
    if not isinstance(replaced_by, list):
        return None
    for candidate in replaced_by:
        if isinstance(candidate, str) and candidate in object_info:
            return candidate
    return None


def apply_node_aliases(
    workflow: dict[str, Any],
    object_info: dict[str, Any] | None,
    aliases: dict[str, Any] | None = None,
) -> list[str]:
    """Rewrite renamed node classes and input keys in-place. Returns human-readable rewrite notes.

    No-ops without /object_info: every rewrite is gated on the live schema, so with nothing to
    validate against the correct action is to leave the graph exactly as the builder produced it.
    """
    if not object_info or not isinstance(workflow, dict):
        return []

    table = aliases if aliases is not None else load_aliases()
    node_aliases = table.get("nodes") or {}
    input_aliases = table.get("inputs") or {}
    if not node_aliases and not input_aliases:
        return []

    notes: list[str] = []

    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "")
        if not class_type:
            continue

        renamed_inputs: dict[str, str] = {}

        # 1. Class rename -- only when the live core does NOT define the current name. If it still
        #    exists, the builder's choice is valid and rewriting it would be a silent behaviour swap.
        if class_type not in object_info:
            entry = node_aliases.get(class_type)
            if isinstance(entry, dict):
                replacement = _resolve_replacement(entry, object_info)
                if replacement:
                    node["class_type"] = replacement
                    notes.append(f"node {node_id}: {class_type} -> {replacement}")
                    mapped = entry.get("inputs")
                    if isinstance(mapped, dict):
                        renamed_inputs.update({str(k): str(v) for k, v in mapped.items()})
                    class_type = replacement

        # 2. Input renames, from the class entry and from the standalone per-class input table.
        standalone = input_aliases.get(class_type)
        if isinstance(standalone, dict):
            renamed_inputs.update({str(k): str(v) for k, v in standalone.items()})

        if not renamed_inputs:
            continue

        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue

        live_inputs = _class_input_names(object_info, class_type)
        for old_name, new_name in renamed_inputs.items():
            if old_name not in inputs:
                continue
            # Only move a key the live schema no longer accepts onto one it does. Guards against an
            # alias entry that has itself gone stale.
            if old_name in live_inputs or new_name not in live_inputs:
                continue
            if new_name in inputs:
                continue  # already set explicitly; never clobber a real value
            inputs[new_name] = inputs.pop(old_name)
            notes.append(f"node {node_id} ({class_type}): input {old_name} -> {new_name}")

    return notes


def unresolved_classes(workflow: dict[str, Any], object_info: dict[str, Any] | None) -> list[str]:
    """Classes the graph names that the live core does not define and no alias could repair.

    Callers use this to fail loudly and specifically ("ComfyUI no longer provides X") instead of
    letting /prompt answer with a generic validation error.
    """
    if not object_info or not isinstance(workflow, dict):
        return []
    missing: set[str] = set()
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "")
        if class_type and class_type not in object_info:
            missing.add(class_type)
    return sorted(missing)
