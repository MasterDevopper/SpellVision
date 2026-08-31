"""How much of the Flows library can actually launch, on each core?

Convert-only (no rendering), so it is cheap enough to run across all 81 imported workflows. The
UI-graph -> API-prompt conversion needs a live schema for every node class in the graph, so this
measures exactly one thing: can the workflow be turned into something submittable at all.

Run against BOTH cores. A workflow that fails on both is a library-health problem (missing custom
node pack), not a bump regression -- and that distinction is the whole point of running it twice.
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

MISSING_RE = re.compile(r"no schema for node class\(es\): (.+?)(?:\.\s|$)")


def object_info(api: str) -> dict:
    """Through the shared reader in ``comfy_prompt_client``.

    This function used to pass ``Connection: close`` explicitly, recorded at the time as the FIX for
    the resets. It was the cause. Measured against core v0.34.0 (6.76MB body), requests otherwise
    identical: bare and ``Accept-Encoding`` variants succeeded 3 of 3; ``Connection: close``
    reset 3 of 3. urllib sends that header unconditionally, so the retry loop below could never have
    escaped it -- five attempts at a request guaranteed to fail.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "python"))
    from comfy_prompt_client import _http_get_json

    last = None
    for attempt in range(5):
        try:
            return _http_get_json(api, "/object_info", timeout=180)
        except (OSError, json.JSONDecodeError, RuntimeError) as exc:
            last = exc
            time.sleep(min(8.0, 0.5 * (2 ** attempt)))
    raise RuntimeError(f"object_info failed: {last}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8189")
    ap.add_argument("--label", default="target")
    args = ap.parse_args()

    from comfy_graph_converter import convert_ui_graph_to_api_prompt, is_ui_graph

    info = object_info(args.api)
    print(f"{args.label}: {len(info)} node classes\n")

    ok, failed = [], []
    missing_counter: Counter[str] = Counter()

    for folder in sorted(p for p in IMPORTED.iterdir() if p.is_dir()):
        wf = folder / "workflow.json"
        if not wf.is_file():
            continue
        try:
            graph = json.loads(wf.read_text(encoding="utf-8"))
        except Exception:
            failed.append((folder.name, "unreadable"))
            continue
        try:
            out = convert_ui_graph_to_api_prompt(graph, info) if is_ui_graph(graph) else graph
            if isinstance(out, dict) and out:
                ok.append(folder.name)
            else:
                failed.append((folder.name, "empty graph"))
        except Exception as exc:
            msg = str(exc)
            m = MISSING_RE.search(msg)
            if m:
                for cls in m.group(1).split(","):
                    cls = cls.strip()
                    if cls:
                        missing_counter[cls] += 1
                failed.append((folder.name, "missing nodes"))
            else:
                failed.append((folder.name, f"{type(exc).__name__}"))

    total = len(ok) + len(failed)
    print(f"convertible: {len(ok)}/{total}   blocked: {len(failed)}/{total}\n")

    reasons = Counter(r for _, r in failed)
    for reason, n in reasons.most_common():
        print(f"  {n:>3}  {reason}")

    print("\ntop missing node classes (workflows blocked by each):")
    for cls, n in missing_counter.most_common(18):
        print(f"  {n:>3}  {cls}")

    Path(f"flows_health_{args.label}.json").write_text(
        json.dumps({"ok": ok, "failed": failed,
                    "missing": missing_counter.most_common()}, indent=1), encoding="utf-8")
