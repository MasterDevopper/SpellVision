"""Actually LAUNCH the convertible imported workflows, not just convert them.

Converting proves the graph can be expressed; only submitting proves ComfyUI accepts it. This
submits every convertible workflow and classifies what comes back, because the failure MODE is the
useful part:

  accepted   - /prompt took it (the launch path works end to end)
  missing-model  - value_not_in_list on a loader: the workflow names a file not on this box
  bad-input      - a validation error on a widget value: the converter's problem, or the workflow's
  other          - anything else, worth reading individually

Only "bad-input" would indicate something wrong with our conversion. Missing models are library
content, not code.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, r"C:\Users\xXste\Code_Projects\SpellVision\python")

IMPORTED = Path(r"C:\Users\xXste\Code_Projects\SpellVision\runtime\imported_workflows")


def http_get(api: str, path: str, timeout: int = 180, attempts: int = 6) -> dict:
    last = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(f"{api}{path}", headers={"Connection": "close"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last = exc
            time.sleep(min(10.0, 1.0 * (2 ** attempt)))
    raise RuntimeError(str(last))


def classify(body: str) -> str:
    if "value_not_in_list" in body:
        return "missing-model"
    if "Invalid image file" in body:
        return "missing-input-image"
    if "required_input_missing" in body:
        return "unlinked-required-input"
    if "Failed to convert an input value" in body:
        return "bad-input"      # the one that would implicate the converter
    if "custom_validation_failed" in body:
        return "custom-validation"
    return "other"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8189")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    from comfy_graph_converter import convert_ui_graph_to_api_prompt, is_ui_graph

    oi = http_get(args.api, "/object_info")
    print(f"{len(oi)} classes\n", flush=True)

    outcomes: Counter[str] = Counter()
    detail: list[tuple[str, str]] = []
    n = 0

    for folder in sorted(p for p in IMPORTED.iterdir() if p.is_dir()):
        wf_path = folder / "workflow.json"
        if not wf_path.is_file():
            continue
        try:
            wf = json.loads(wf_path.read_text(encoding="utf-8"))
            graph = convert_ui_graph_to_api_prompt(wf, oi) if is_ui_graph(wf) else wf
        except Exception:
            outcomes["not-convertible"] += 1
            continue
        if not isinstance(graph, dict) or not graph:
            outcomes["not-convertible"] += 1
            continue

        for node in graph.values():
            if isinstance(node, dict) and isinstance(node.get("inputs"), dict):
                if "filename_prefix" in node["inputs"]:
                    node["inputs"]["filename_prefix"] = f"lw_{folder.name[:20]}"

        try:
            req = urllib.request.Request(f"{args.api}/prompt",
                                         data=json.dumps({"prompt": graph}).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                json.loads(r.read().decode())
            outcomes["accepted"] += 1
            detail.append((folder.name, "accepted"))
            # Do not let an accepted graph actually render -- this sweep is about the launch path,
            # and 60+ real renders would take hours. Clear it immediately.
            try:
                urllib.request.urlopen(urllib.request.Request(
                    f"{args.api}/queue", data=json.dumps({"clear": True}).encode(),
                    headers={"Content-Type": "application/json"}), timeout=30)
            except Exception:
                pass
            try:
                urllib.request.urlopen(urllib.request.Request(
                    f"{args.api}/interrupt", data=b"", method="POST"), timeout=30)
            except Exception:
                pass
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            kind = classify(body)
            outcomes[kind] += 1
            detail.append((folder.name, kind))
        except Exception as exc:
            outcomes["transport"] += 1
            detail.append((folder.name, f"transport:{type(exc).__name__}"))

        n += 1
        if args.limit and n >= args.limit:
            break

    print("=== LAUNCH OUTCOMES ===")
    for kind, count in outcomes.most_common():
        print(f"  {count:>3}  {kind}")
    print("\nbad-input cases (would implicate the converter):")
    bad = [name for name, k in detail if k == "bad-input"]
    print("  " + (", ".join(bad) if bad else "none"))
