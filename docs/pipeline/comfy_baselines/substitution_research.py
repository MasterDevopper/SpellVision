"""Research: how often is a missing model actually substitutable?

54 of 81 imported workflows fail to launch purely because they name a model file that is not on
this box. The question is whether that SHOULD be fatal. SpellVision's premise is that it resolves
dependencies for the user, and a workflow whose only problem is "wants juggernautXL, we have
realvisXL" is a workflow we could run.

This measures, per blocked loader input:
  * what family the REQUESTED model belongs to (from its filename, via model_classification)
  * whether the live catalog for that exact loader input holds any model of the same family
  * so: would a family-aware fallback have made this workflow launchable?

Deliberately does not substitute anything. It only sizes the opportunity, because the cost of a
WRONG substitution (a silently wrong render) is high enough that the number has to justify it.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, r"C:\Users\xXste\Code_Projects\SpellVision\python")

API = "http://127.0.0.1:8189"
IMPORTED = Path(r"C:\Users\xXste\Code_Projects\SpellVision\runtime\imported_workflows")

MODEL_INPUTS = {
    "ckpt_name", "unet_name", "lora_name", "vae_name", "clip_name", "clip_name1", "clip_name2",
    "control_net_name", "style_model_name", "upscale_model_name", "model_name", "clip_vision_name",
    "gguf_name", "ipadapter_file", "instantid_file",
}


def http_get(path: str, attempts: int = 6) -> dict:
    last = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(f"{API}{path}", headers={"Connection": "close"})
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last = exc
            time.sleep(min(10.0, 1.0 * (2 ** attempt)))
    raise RuntimeError(str(last))


def choices_for(oi: dict, cls: str, inp: str) -> list[str]:
    spec = ((oi.get(cls) or {}).get("input") or {})
    for kind in ("required", "optional"):
        decl = (spec.get(kind) or {}).get(inp)
        if isinstance(decl, list) and decl and isinstance(decl[0], list):
            return [str(x) for x in decl[0]]
    return []


def family_of(name: str) -> str:
    import model_classification as mc
    try:
        return (mc.classify_model(name).family or "unknown").lower()
    except Exception:
        return "unknown"


if __name__ == "__main__":
    from comfy_graph_converter import convert_ui_graph_to_api_prompt, is_ui_graph

    oi = http_get("/object_info")
    print(f"{len(oi)} classes\n")

    blocked_wf = 0
    rescuable_wf = 0
    per_family: Counter[str] = Counter()
    rescuable_family: Counter[str] = Counter()
    examples: dict[str, list[tuple[str, str]]] = defaultdict(list)
    unresolvable: Counter[str] = Counter()

    for folder in sorted(p for p in IMPORTED.iterdir() if p.is_dir()):
        wf_path = folder / "workflow.json"
        if not wf_path.is_file():
            continue
        try:
            wf = json.loads(wf_path.read_text(encoding="utf-8"))
            graph = convert_ui_graph_to_api_prompt(wf, oi) if is_ui_graph(wf) else wf
        except Exception:
            continue
        if not isinstance(graph, dict):
            continue

        misses: list[tuple[str, str, str]] = []   # (class, input, requested)
        for node in graph.values():
            if not isinstance(node, dict):
                continue
            cls = str(node.get("class_type") or "")
            for inp, val in (node.get("inputs") or {}).items():
                if inp not in MODEL_INPUTS or not isinstance(val, str) or not val.strip():
                    continue
                avail = choices_for(oi, cls, inp)
                if avail and val not in avail:
                    misses.append((cls, inp, val))

        if not misses:
            continue
        blocked_wf += 1

        all_rescuable = True
        for cls, inp, requested in misses:
            fam = family_of(requested)
            per_family[fam] += 1
            avail = choices_for(oi, cls, inp)
            same_family = [a for a in avail if family_of(a) == fam and fam != "unknown"]
            if same_family:
                rescuable_family[fam] += 1
                if len(examples[fam]) < 3:
                    examples[fam].append((Path(requested).name, Path(same_family[0]).name))
            else:
                all_rescuable = False
                unresolvable[f"{fam} @ {inp}"] += 1
        if all_rescuable:
            rescuable_wf += 1

    print(f"workflows blocked ONLY by missing models: {blocked_wf}")
    print(f"  ...every missing model has a same-family alternative: {rescuable_wf}")
    print(f"  ...at least one has no alternative:                   {blocked_wf - rescuable_wf}\n")

    print("per missing-model-reference, by family:")
    for fam, n in per_family.most_common():
        print(f"  {fam:<16} {n:>3} missing   {rescuable_family.get(fam,0):>3} have a same-family stand-in")

    print("\nexample substitutions that would be available:")
    for fam, pairs in list(examples.items())[:8]:
        for want, got in pairs[:2]:
            print(f"  [{fam}] {want[:44]:<44} -> {got[:44]}")

    print("\nno same-family stand-in (would still block):")
    for k, n in unresolvable.most_common(10):
        print(f"  {n:>3}  {k}")
