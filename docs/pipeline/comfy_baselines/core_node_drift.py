"""Doc 25 S2, done statically: which nodes we depend on does a target core still define?

Standing up v0.33.1 to dump /object_info needs an isolated venv with torch -- hours and ~10GB. But
the failure that actually kills a graph is a node being renamed or removed, and that is visible in
NODE_CLASS_MAPPINGS without running anything. This answers "does the bump break a graph outright",
not "did an input type change" -- the latter still needs the live dump at S3.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path


def mapping_keys(tree_root: Path) -> set[str]:
    """Every string key assigned into a NODE_CLASS_MAPPINGS-ish dict anywhere in the tree."""
    found: set[str] = set()
    for py in tree_root.rglob("*.py"):
        # Skip vendored/test noise, and custom_nodes -- those ship with the node packs, not the
        # core, so counting them as core inverts the whole classification (it made kijai's
        # HyVideo* look like core nodes the bump had deleted).
        parts = set(py.parts)
        if {".git", "tests", "tests-unit", "script_examples", "custom_nodes"} & parts:
            continue
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Modern core registers through the V3 schema -- `class Foo(io.ComfyNode)` declaring
        # `node_id="Foo"` in define_schema(), collected by an extension class list. Nothing named
        # NODE_CLASS_MAPPINGS appears, so keying only on that name misses most of the core (it
        # found 344 of ~600+ and wrongly classed core nodes like BasicGuider as custom-pack).
        found.update(re.findall(r'node_id\s*=\s*"([A-Za-z0-9_.]+)"', text))
        if "NODE_CLASS_MAPPINGS" not in text and "NODE_DISPLAY_NAME_MAPPINGS" not in text:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            # Fall back to a regex sweep so a parse failure never silently hides nodes.
            found.update(re.findall(r'"([A-Za-z0-9_.]+)"\s*:\s*[A-Za-z_]', text))
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
                if not any("NODE_CLASS_MAPPINGS" in t for t in targets):
                    continue
                if isinstance(node.value, ast.Dict):
                    for k in node.value.keys:
                        if isinstance(k, ast.Constant) and isinstance(k.value, str):
                            found.add(k.value)
            # `MAPPINGS["Name"] = Cls` style
            if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
                if isinstance(node.slice.value, str):
                    found.add(node.slice.value)
        # Some extras build mappings from a class list; catch the common `class Foo` + string form.
        found.update(re.findall(r'^\s*"([A-Za-z0-9_.]+)"\s*:\s*[A-Za-z_][A-Za-z0-9_]*\s*,?\s*$',
                                text, re.MULTILINE))
    return found


if __name__ == "__main__":
    baseline = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    target_root = Path(sys.argv[2])

    depended = sorted(baseline["contract"].keys())
    target_nodes = mapping_keys(target_root)
    print(f"target core defines ~{len(target_nodes)} node names")

    # A class we depend on that the TARGET core does not define is only alarming if the LIVE core
    # defined it -- otherwise it comes from a custom node pack, which a core bump does not touch.
    live_core_nodes = mapping_keys(Path(sys.argv[3])) if len(sys.argv) > 3 else set()

    core_provided = [n for n in depended if n in live_core_nodes]
    custom_provided = [n for n in depended if n not in live_core_nodes]

    gone = [n for n in core_provided if n not in target_nodes]

    print(f"\ndepended-on classes: {len(depended)}")
    print(f"  provided by live CORE:        {len(core_provided)}")
    print(f"  provided by CUSTOM node packs: {len(custom_provided)} (unaffected by a core bump)")
    print(f"\nREMOVED/RENAMED in target core: {gone or 'none'}")
    if custom_provided:
        print("\ncustom-pack classes (re-verify these against the packs, not the core):")
        for n in custom_provided:
            print("   ", n)
