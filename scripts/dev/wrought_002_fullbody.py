"""Reproduce the 002 teacher exactly, then change ONE thing at a time toward a full-body plate.

The owner's rule: "002 is the truth that everything must match", and `002_REPEATABLE_FACTORS.md`
section 9 says "One miss per recut. Do not stack all six." So this renders a ladder, not a guess:

    A  exact reproduction of the teacher's own graph (768x1024, seed 1002)
    B  A + full-body framing words, same canvas
    C  B at a taller canvas that still divides by 32
    D  B at the Lane-A canvas the dataset actually uses

Every arm shares the teacher's UNET, CLIP, VAE, shift, seed, steps, cfg, sampler and scheduler,
which are read OUT OF THE TEACHER PNG rather than retyped, so a drift in this file cannot silently
change what "002" means. Run it with the local endpoint idle; it writes nothing outside `--out`.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wrought_comfy as wc  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
TEACHER = REPO / "runtime/style/datasets/wrought_house_v1/images/002.png"
# The teacher is ~thigh-up. These are the words that make it a full figure and nothing else: no
# style, no lighting, no material claim, so arm B differs from arm A by framing alone.
FULL_BODY = ("full body, head to feet, both feet inside the frame, standing at full height, "
             "the whole figure visible")


def teacher_graph(path: Path = TEACHER) -> dict:
    """The teacher's own generation graph, straight out of its PNG."""
    info = Image.open(path).info
    if "prompt" not in info:
        raise ValueError(f"{path} carries no embedded prompt graph")
    return json.loads(info["prompt"])


def _node(graph: dict, class_type: str) -> tuple[str, dict]:
    for nid, node in graph.items():
        if node.get("class_type") == class_type:
            return nid, node
    raise KeyError(class_type)


def arm(graph: dict, prefix: str, *, framing: str = "", width: int | None = None,
        height: int | None = None, unet: str | None = None) -> dict:
    """One rung: the teacher's graph with at most a framing phrase, a canvas and a checkpoint changed."""
    g = copy.deepcopy(graph)
    if unet:
        _, loader = _node(g, "UNETLoader")
        loader["inputs"]["unet_name"] = unet
    pos_id, pos = _node(g, "CLIPTextEncode")           # node 4 is the positive in the teacher graph
    if framing:
        pos["inputs"]["text"] = f"{pos['inputs']['text']}, {framing}"
    if width and height:
        _, latent = _node(g, "EmptySD3LatentImage")
        latent["inputs"]["width"], latent["inputs"]["height"] = width, height
    for nid, node in g.items():
        if node.get("class_type") == "SaveImage":
            node["inputs"]["filename_prefix"] = prefix
    return g


ARMS = [
    ("A_exact",              dict()),
    ("B_fullbody_768x1024",  dict(framing=FULL_BODY)),
    ("C_fullbody_896x1344",  dict(framing=FULL_BODY, width=896, height=1344)),
    ("D_fullbody_1216x1728", dict(framing=FULL_BODY, width=1216, height=1728)),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(REPO / "runtime/wrought_002_fullbody"))
    ap.add_argument("--api", default=wc.Endpoint().api)
    ap.add_argument("--arms", nargs="*", default=[name for name, _ in ARMS])
    ap.add_argument("--unet", default=None,
                    help="override the teacher's checkpoint to test one against it; the rest of the "
                         "graph (CLIP, VAE, shift, seed, steps, cfg, sampler, scheduler) is the "
                         "teacher's either way, so the checkpoint is the only variable")
    ap.add_argument("--tag", default="", help="suffix for the output names, e.g. the checkpoint")
    a = ap.parse_args()

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    endpoint = wc.Endpoint(a.api)
    base = teacher_graph()
    _, ks = _node(base, "KSampler")
    _, unet = _node(base, "UNETLoader")
    print(f"teacher graph: {unet['inputs']['unet_name']}  seed {ks['inputs']['seed']}  "
          f"{ks['inputs']['steps']} steps / cfg {ks['inputs']['cfg']} / "
          f"{ks['inputs']['sampler_name']} / {ks['inputs']['scheduler']}", flush=True)

    ok = 0
    for name, kwargs in ARMS:
        if name not in a.arms:
            continue
        target = out / f"{name}{a.tag}.png"
        graph = arm(base, f"w002_{name}", unet=a.unet, **kwargs)
        _, latent = _node(graph, "EmptySD3LatentImage")
        print(f"  {name}: {latent['inputs']['width']}x{latent['inputs']['height']}"
              f"{' + full-body framing' if kwargs.get('framing') else ' (teacher verbatim)'}",
              flush=True)
        if wc.render(endpoint, graph, target):
            ok += 1
            print(f"  {name} -> {target}", flush=True)
        else:
            print(f"  {name} FAILED", flush=True)
    print(f"{ok}/{len(a.arms)} arms rendered into {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
