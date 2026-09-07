"""Does the Krea 2 pose ControlNet LoRA work on OUR checkpoint, given the encoder it was built for?

Two things blocked it on 2026-09-06 and they were never separated: the Ostris nodes were missing,
AND the LoRA is trained for Krea2 Turbo. The second Comfy tree (`C:\\sv_comfy_edit`, port 8189) now
carries `comfyui-krea2-ostris-edit` at the exact commit the author's workflow declared, so this
isolates the second cause: the author's own wiring, on our checkpoint at our sampler.

    LoadImage(skeleton) -> FluxKontextImageScale -> TextEncodeKrea2OstrisEdit(clip, prompt, vae, image1)
    -> FluxKontextMultiReferenceLatentMethod -> KSampler.positive
    UNETLoader -> LoraLoaderModelOnly(pose LoRA) -> Krea2OstrisEditModelPatch -> ModelSamplingAuraFlow

Node signatures were read from the running tree's `/object_info`, not from memory. Arms vary only
the LoRA strength and, in the last arm, the sampler -- so a clean render at our settings and a
corrupt one at Turbo's settings would say the sampler is what matters, and the reverse would say the
checkpoint is.
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_wrought_dataset as g  # noqa: E402
import wrought_comfy as wc  # noqa: E402
import wrought_variants as variants  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "runtime" / "wrought_pose_ostris"
SKELETON = REPO / "runtime" / "wrought_pose" / "skel_wolf_OpenposePreprocessor.png"
POSE_LORA = "krea2_turbo_openpose_controlnet.safetensors"
TURBO = "krea2_turbo_fp8_scaled.safetensors"
W, H, SEED = 896, 1344, 77002
CULTURE = {"materials": "tanned hide, woven fiber, carved wood, bone, natural dye",
           "palette": "umber, deep forest green, clan-dye red, dappled green-gold"}
# The author's trigger, verbatim from the model page; the pose map is what it names.
TRIGGER = ("AstroDWPoseSimpleV01, a simplified DWPose structure map on a black background, ")


def ostris_graph(positive: str, negative: str, prefix: str, skeleton_name: str, *,
                 strength: float, unet: str | None = None, steps: int = 52, cfg: float = 3.5) -> dict:
    """The author's wiring with our checkpoint and sampler, built on wrought_comfy's base graph."""
    graph = wc.t2i_graph(positive, negative, SEED, prefix, W, H, steps, cfg, unet)
    graph["11"] = {"class_type": "LoadImage", "inputs": {"image": skeleton_name}}
    graph["14"] = {"class_type": "FluxKontextImageScale", "inputs": {"image": ["11", 0]}}
    graph["4"] = {"class_type": "TextEncodeKrea2OstrisEdit",
                  "inputs": {"clip": ["2", 0], "prompt": positive, "vae": ["3", 0],
                             "image1": ["14", 0]}}
    graph["12"] = {"class_type": "FluxKontextMultiReferenceLatentMethod",
                   "inputs": {"conditioning": ["4", 0],
                              "reference_latents_method": "index_timestep_zero"}}
    graph["8"]["inputs"]["positive"] = ["12", 0]
    graph["13"] = {"class_type": "LoraLoaderModelOnly",
                   "inputs": {"model": ["1", 0], "lora_name": POSE_LORA,
                              "strength_model": float(strength)}}
    graph["15"] = {"class_type": "Krea2OstrisEditModelPatch",
                   "inputs": {"model": ["13", 0], "kv_cache": False}}
    graph["5"]["inputs"]["model"] = ["15", 0]
    return graph


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--api", default="http://127.0.0.1:8189")
    a = ap.parse_args()
    if not SKELETON.exists():
        print(f"missing skeleton {SKELETON}"); return 1
    OUT.mkdir(parents=True, exist_ok=True)
    endpoint = wc.Endpoint(a.api)
    pick = variants.apply_skin_plate(
        variants.draw("beastfolk", random.Random(11), "woman", culture_materials=CULTURE["materials"],
                      subspecies="wolf", fur="whole", face="muzzle"))
    positive, _ = g.lane_a_prompts("beastfolk", CULTURE, pick)
    negative = ", ".join(x for x in (g.WROUGHT_NEG, variants.negative_for("woman"),
                                     variants.SKIN_PLATE_NEGATIVE, variants.FUR_NEGATIVE) if x)
    skel = endpoint.upload(SKELETON)
    print(f"skeleton uploaded as {skel}; endpoint {a.api}", flush=True)

    arms = [
        ("A_ours_lora1.0", dict(strength=1.0)),
        ("B_ours_lora0.6", dict(strength=0.6)),
        ("C_ours_trigger", dict(strength=1.0)),                      # same, with the author's trigger
        ("D_turbo_settings", dict(strength=1.0, unet=TURBO, steps=10, cfg=1.0)),
    ]
    for name, kwargs in arms:
        prompt = (TRIGGER + positive) if name.endswith("trigger") else positive
        graph = ostris_graph(prompt, negative, f"wop_{name}", skel, **kwargs)
        ok = wc.render(endpoint, graph, OUT / f"{name}.png")
        print(("  ok   " if ok else "  FAIL ") + name, flush=True)
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
