"""Detect ComfyUI node-API drift by diffing a pinned contract against a live /object_info.

Pairs with comfy_node_aliases: this module says WHAT changed, that one absorbs the subset we have
curated a rewrite for. Keeping them separate is deliberate -- detection can be broad and noisy,
while conversion must be narrow and confirmed.

Only the classes SpellVision actually names are considered. The full dump is ~1360 classes; the
signal is in the ~72 our templates and builders reference, and folding in the rest buries it.

Enum inputs are compared by SHAPE (ENUM[n]), never by contents: a checkpoint list changes every
time a file lands on disk, and treating that as API drift would make the diff useless.
"""
from __future__ import annotations

from comfy_endpoint import comfy_endpoint

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

# Ordered worst-first: a caller that surfaces only the top N should see the graph-breaking ones.
SEVERITY = {
    "node_removed": 0,
    "input_removed": 1,
    "input_now_required": 2,
    "input_retyped": 3,
    "node_added": 4,
}


@dataclass
class Finding:
    kind: str
    node: str
    detail: str
    input_name: str = ""

    @property
    def severity(self) -> int:
        return SEVERITY.get(self.kind, 9)

    def __str__(self) -> str:
        where = f"{self.node}.{self.input_name}" if self.input_name else self.node
        return f"[{self.kind}] {where}: {self.detail}"


@dataclass
class ContractDiff:
    findings: list[Finding] = field(default_factory=list)

    @property
    def breaking(self) -> list[Finding]:
        """Findings that will make /prompt reject a graph, as opposed to merely being worth knowing."""
        return [f for f in self.findings if f.kind in {"node_removed", "input_removed", "input_now_required"}]

    def sorted(self) -> list[Finding]:
        return sorted(self.findings, key=lambda f: (f.severity, f.node, f.input_name))

    def summary(self) -> str:
        if not self.findings:
            return "no node-API drift in the classes SpellVision depends on"
        counts: dict[str, int] = {}
        for f in self.findings:
            counts[f.kind] = counts.get(f.kind, 0) + 1
        return ", ".join(f"{k}={v}" for k, v in sorted(counts.items(), key=lambda kv: SEVERITY.get(kv[0], 9)))


def _type_shape(decl: Any) -> str | None:
    """The comparable shape of an input's declared type. Enum contents are collapsed to a count."""
    if not isinstance(decl, list) or not decl:
        return None
    head = decl[0]
    if isinstance(head, list):
        return f"ENUM[{len(head)}]"
    return str(head)


def contract_for_classes(object_info: dict[str, Any], classes: Iterable[str]) -> dict[str, Any]:
    """The pinned-contract shape, from a live /object_info dump."""
    out: dict[str, Any] = {}
    for name in sorted(set(classes)):
        node = object_info.get(name)
        if not isinstance(node, dict):
            out[name] = {"__present__": False}
            continue
        entry: dict[str, Any] = {"__present__": True, "inputs": {}}
        spec = node.get("input") if isinstance(node.get("input"), dict) else {}
        for kind in ("required", "optional"):
            section = spec.get(kind)
            if not isinstance(section, dict):
                continue
            for input_name, decl in section.items():
                entry["inputs"][input_name] = {"kind": kind, "type": _type_shape(decl)}
        entry["outputs"] = node.get("output") or []
        out[name] = entry
    return out


def diff_contract(pinned: dict[str, Any], live: dict[str, Any]) -> ContractDiff:
    """Compare two contract dicts (as produced by contract_for_classes)."""
    diff = ContractDiff()

    for name, pinned_entry in sorted(pinned.items()):
        if not isinstance(pinned_entry, dict) or not pinned_entry.get("__present__"):
            continue
        live_entry = live.get(name)
        if not isinstance(live_entry, dict) or not live_entry.get("__present__"):
            diff.findings.append(Finding("node_removed", name, "no longer provided by this ComfyUI"))
            continue

        pinned_inputs = pinned_entry.get("inputs") or {}
        live_inputs = live_entry.get("inputs") or {}

        for input_name, pinned_decl in sorted(pinned_inputs.items()):
            live_decl = live_inputs.get(input_name)
            if live_decl is None:
                diff.findings.append(
                    Finding("input_removed", name, "input no longer exists", input_name))
                continue
            if pinned_decl.get("type") != live_decl.get("type"):
                diff.findings.append(Finding(
                    "input_retyped", name,
                    f"{pinned_decl.get('type')} -> {live_decl.get('type')}", input_name))

        # A newly-required input with no default breaks every graph that omits it.
        for input_name, live_decl in sorted(live_inputs.items()):
            if input_name in pinned_inputs:
                pinned_kind = pinned_inputs[input_name].get("kind")
                if pinned_kind == "optional" and live_decl.get("kind") == "required":
                    diff.findings.append(Finding(
                        "input_now_required", name, "was optional, now required", input_name))
                continue
            if live_decl.get("kind") == "required":
                diff.findings.append(Finding(
                    "input_now_required", name, "new required input", input_name))

    return diff


def rename_candidates(diff: ContractDiff, live: dict[str, Any], pinned: dict[str, Any]) -> dict[str, list[str]]:
    """Propose replacements for removed nodes. REPORT ONLY -- never auto-applied.

    A rename cannot be detected with certainty, so this ranks by structural agreement (identical
    output types) plus name-token overlap. Applying a wrong guess would turn a loud failure into a
    silent wrong render, so a human promotes a candidate into comfy_node_aliases.json, ideally after
    a confirming render.
    """
    removed = [f.node for f in diff.findings if f.kind == "node_removed"]
    if not removed:
        return {}

    def tokens(name: str) -> set[str]:
        return {t.lower() for t in re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z]*|\d+|[a-z]+", name) if t}

    out: dict[str, list[str]] = {}
    for gone in removed:
        gone_outputs = list((pinned.get(gone) or {}).get("outputs") or [])
        gone_tokens = tokens(gone)
        scored: list[tuple[float, str]] = []
        for name, entry in live.items():
            if name in pinned or not isinstance(entry, dict) or not entry.get("__present__"):
                continue
            score = 0.0
            if list(entry.get("outputs") or []) == gone_outputs and gone_outputs:
                score += 2.0
            overlap = gone_tokens & tokens(name)
            if gone_tokens:
                score += 2.0 * len(overlap) / len(gone_tokens)
            if score > 0.75:
                scored.append((score, name))
        scored.sort(key=lambda s: (-s[0], s[1]))
        out[gone] = [name for _, name in scored[:5]]
    return out


def load_pinned(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return payload.get("contract") if isinstance(payload, dict) and "contract" in payload else payload


def _main(argv: list[str]) -> int:
    """Diff a pinned contract against a running ComfyUI.

    Run this after any ComfyUI update, before trusting a render:
        python python/comfy_node_contract.py docs/pipeline/comfy_baselines/node_contract_<sha>.json
    """
    import argparse
    import urllib.request

    parser = argparse.ArgumentParser(description=_main.__doc__)
    parser.add_argument("pinned", help="pinned contract JSON from a previous core")
    parser.add_argument("--api", default=comfy_endpoint(), help="live ComfyUI base URL")
    parser.add_argument("--candidates", action="store_true",
                        help="also propose replacements for removed nodes (REPORT ONLY)")
    args = parser.parse_args(argv)

    pinned = load_pinned(args.pinned)
    # Through the shared reader, not urllib. urllib ALWAYS sends `Connection: close`, and on a core
    # whose /object_info body is 6.76MB that resets mid-read every time -- this tool died on exactly
    # the bump it exists to screen.
    from comfy_prompt_client import _http_get_json

    object_info = _http_get_json(args.api, "/object_info", timeout=90)

    live = contract_for_classes(object_info, pinned.keys())
    diff = diff_contract(pinned, live)

    print(f"pinned classes: {len(pinned)}   live core classes: {len(object_info)}")
    print(f"drift: {diff.summary()}\n")
    for finding in diff.sorted():
        print(f"  {finding}")

    if args.candidates:
        # Compare against the WHOLE live core, not just the pinned subset -- a replacement is by
        # definition a class we did not previously depend on.
        whole = contract_for_classes(object_info, object_info.keys())
        for gone, options in rename_candidates(diff, whole, pinned).items():
            print(f"\n  rename candidates for {gone} (REPORT ONLY -- confirm with a render):")
            for option in options:
                print(f"     - {option}")

    # Non-zero only on drift that will actually reject a graph, so this is CI-usable as a gate.
    return 1 if diff.breaking else 0


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
