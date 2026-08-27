"""Follow-up research: can the GRAPH tell us the architecture the missing model must satisfy?

The naive "same family as the requested filename" test rescued only 10 of 56 workflows. Two
reasons, and both point at the same fix:

  * 33 references classify as "unknown" -- the classifier reads the FILENAME, and the filename of a
    model you do not have is weak evidence.
  * 11 classify as "illustrious" with no illustrious stand-in, even though the box is full of SDXL
    checkpoints. Illustrious IS an SDXL derivative; the taxonomy conflates ARCHITECTURE (what the
    graph can actually load) with LINEAGE (a stylistic finetune).

So this measures a different signal: infer the required architecture from the NODES AROUND the
loader, which are present and unambiguous, and see how much that recovers.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, r"C:\Users\xXste\Code_Projects\SpellVision\python")

API = "http://127.0.0.1:8189"
IMPORTED = Path(r"C:\Users\xXste\Code_Projects\SpellVision\runtime\imported_workflows")

# Node classes that pin an architecture unambiguously when present in the same graph.
ARCH_MARKERS = {
    "EmptyLatentImage": "sd15_or_sdxl",
    "EmptySD3LatentImage": "sd3_or_flux_or_krea2",
    "EmptyHunyuanLatentVideo": "hunyuan_video",
    "EmptyLTXVLatentVideo": "ltx",
    "EmptyMochiLatentVideo": "mochi",
    "WanImageToVideo": "wan",
    "WanVideoModelLoader": "wan",
    "FluxGuidance": "flux",
    "CLIPTextEncodeSDXL": "sdxl",
    "ModelSamplingSD3": "sd3_or_flux",
    "ModelSamplingAuraFlow": "lumina_or_krea2",
    "SDXLPromptStyler": "sdxl",
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


if __name__ == "__main__":
    from comfy_graph_converter import convert_ui_graph_to_api_prompt, is_ui_graph

    oi = http_get("/object_info")

    have_marker = 0
    no_marker = 0
    marker_hits: Counter[str] = Counter()
    clip_type_hits: Counter[str] = Counter()
    latent_dims = Counter()

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

        # Only look at graphs that have a MISSING ckpt/unet.
        missing = False
        for node in graph.values():
            if not isinstance(node, dict):
                continue
            for inp in ("ckpt_name", "unet_name"):
                val = (node.get("inputs") or {}).get(inp)
                if isinstance(val, str) and val:
                    avail = choices_for(oi, str(node.get("class_type")), inp)
                    if avail and val not in avail:
                        missing = True
        if not missing:
            continue

        classes = {str(n.get("class_type")) for n in graph.values() if isinstance(n, dict)}
        found = sorted(ARCH_MARKERS[c] for c in classes if c in ARCH_MARKERS)
        if found:
            have_marker += 1
            for f in found:
                marker_hits[f] += 1
        else:
            no_marker += 1

        # A CLIPLoader's `type` widget names the architecture outright -- the strongest signal there is.
        for n in graph.values():
            if isinstance(n, dict) and str(n.get("class_type")).startswith("CLIPLoader"):
                t = (n.get("inputs") or {}).get("type")
                if isinstance(t, str):
                    clip_type_hits[t] += 1
        # Latent dimensions narrow SD15 (512) vs SDXL (1024) when nothing else does.
        for n in graph.values():
            if isinstance(n, dict) and str(n.get("class_type")) == "EmptyLatentImage":
                w = (n.get("inputs") or {}).get("width")
                if isinstance(w, (int, float)):
                    latent_dims[int(w)] += 1

    print(f"workflows with a MISSING ckpt/unet: {have_marker + no_marker}")
    print(f"  architecture inferable from graph markers: {have_marker}")
    print(f"  no marker at all:                          {no_marker}\n")
    print("marker signals seen:")
    for k, v in marker_hits.most_common():
        print(f"  {v:>3}  {k}")
    print("\nCLIPLoader.type values (names the architecture outright):")
    for k, v in clip_type_hits.most_common(10):
        print(f"  {v:>3}  {k}")
    print("\nEmptyLatentImage widths (512 => sd15, 1024 => sdxl):")
    for k, v in latent_dims.most_common(6):
        print(f"  {v:>3}  {k}px")
