"""Pin the node contract SpellVision actually depends on, from a live /object_info dump.

Doc 25 S0 wants "the diff surface for node-API drift". The whole 1360-class dump is mostly noise:
what can break us is a change to the classes our templates and builders name. This records exactly
those -- input names, their types, and whether they are required -- so a future core can be diffed
against it cheaply.
"""
from __future__ import annotations

import glob
import json
import re
import sys
from pathlib import Path

REPO = Path(r"C:\Users\xXste\Code_Projects\SpellVision")


def classes_we_depend_on() -> set[str]:
    used: set[str] = set()
    for f in glob.glob(str(REPO / "python" / "video_templates" / "*.json")):
        graph = json.loads(Path(f).read_text(encoding="utf-8"))
        for node in graph.values():
            if isinstance(node, dict) and node.get("class_type"):
                used.add(node["class_type"])
    # Builders also name classes directly (added/rewired nodes that no template carries).
    for f in glob.glob(str(REPO / "python" / "*.py")):
        text = Path(f).read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r'"class_type"\s*:\s*"([A-Za-z0-9_.]+)"', text):
            used.add(m.group(1))
    return used


def contract_for(info: dict, names: set[str]) -> dict:
    out: dict = {}
    for name in sorted(names):
        node = info.get(name)
        if node is None:
            out[name] = {"__present__": False}
            continue
        entry: dict = {"__present__": True, "inputs": {}}
        spec = node.get("input") or {}
        for kind in ("required", "optional"):
            for input_name, decl in (spec.get(kind) or {}).items():
                # decl[0] is either a type string or an enum list; record the SHAPE, not the
                # enum contents -- model filenames change constantly and are not API drift.
                type_repr = decl[0] if isinstance(decl, list) and decl else None
                if isinstance(type_repr, list):
                    type_repr = f"ENUM[{len(type_repr)}]"
                entry["inputs"][input_name] = {"kind": kind, "type": type_repr}
        entry["outputs"] = node.get("output") or []
        out[name] = entry
    return out


if __name__ == "__main__":
    info = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    names = classes_we_depend_on()
    contract = contract_for(info, names)
    missing = [n for n, v in contract.items() if not v.get("__present__")]
    payload = {
        "source": sys.argv[2] if len(sys.argv) > 2 else "live",
        "total_classes_in_core": len(info),
        "classes_depended_on": len(names),
        "missing": missing,
        "contract": contract,
    }
    out_path = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("node_contract.json")
    out_path.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")
    print(f"classes depended on: {len(names)}")
    print(f"missing from this core: {missing or 'none'}")
    print(f"wrote {out_path}")
