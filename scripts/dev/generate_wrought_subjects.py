"""Is Wrought reproducible on a subject that is not a character?

The Look Matrix says it must be: "One ruleset for characters and world -- a woman's forearm and a
leather strap obey the same detail-frequency law." That sentence is the whole reason a style LoRA is
worth training rather than a character LoRA, and it is testable.

The STYLE block below is subject-agnostic by construction: it names lighting, surface treatment and
colour law, and says nothing about what is being lit. Everything subject-specific lives in SUBJECTS.
"""
from __future__ import annotations

import json, sys, time, urllib.request
from pathlib import Path

REPO = Path("C:/Users/xXste/Code_Projects/SpellVision")
sys.path.insert(0, str(REPO / "python"))
from comfy_prompt_client import _http_get_json  # noqa: E402

API = "http://127.0.0.1:8188"
UNET, CLIP, VAE = ("loxsUtopicWorldKrea2_v10BF16.safetensors",
                   "qwen3vl_4b_fp8_scaled.safetensors", "qwen_image_vae.safetensors")

# The Wrought law, transcribed from docs/knowledge/characters/female-look-matrix.md. Nothing here
# names a species, a body or a garment -- that is the test.
WROUGHT_STYLE = (
    "WROUGHT style, grounded stylized realism, PBR-native, physically based materials, "
    "material truth, every surface reads as its real substance, "
    "meso-scale surface detail, anatomical and structural folds and creases that follow the "
    "underlying form, no micro pore detail, no smooth macro gradients, "
    "dark studio background, single dominant key light, deep shadow falloff, "
    "light and falloff come from the scene and not from painted highlights, "
    "controlled saturation, restrained palette, "
    "painterly rendered surfaces, detailed material surfaces"
)
WROUGHT_NEG = (
    "photoreal, photograph, micro pores, skin pores, anime, cartoon, anime-smooth, "
    "flat lighting, evenly lit, studio product photography, "
    "glossy, wet look, sheen, specular blowout, baked shading, painted highlights, "
    "grimdark, crushed blacks, desaturated grade, oversaturated, "
    "blurry, text, watermark, out of focus, bokeh, depth of field"
)

SUBJECTS = {
    "weapon": "a single orcish war axe resting upright, wrought iron head with a notched edge, "
              "bound leather grip, bone and fur trophy wrapping",
    "building": "a single orc longhouse of unfinished timber and wrought iron banding, "
                "turf roof, heavy plank door, standing alone",
    "creature": "a single shaggy tundra boar, coarse matted fur, chipped tusks, standing in profile",
}


def build(name: str, seed: int) -> dict:
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP, "type": "krea2"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "4": {"class_type": "CLIPTextEncode",
              "inputs": {"text": f"{SUBJECTS[name]}, {WROUGHT_STYLE}", "clip": ["2", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": WROUGHT_NEG, "clip": ["2", 0]}},
        "5": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 1.15}},
        "7": {"class_type": "EmptySD3LatentImage", "inputs": {"width": 768, "height": 1024, "batch_size": 1}},
        "8": {"class_type": "KSampler",
              "inputs": {"model": ["5", 0], "seed": seed, "steps": 52, "cfg": 3.5,
                         "sampler_name": "euler", "scheduler": "simple", "positive": ["4", 0],
                         "negative": ["6", 0], "latent_image": ["7", 0], "denoise": 1.0}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0],
                                                     "filename_prefix": f"wrought_{name}"}},
    }


def run(name: str, seed: int) -> dict:
    body = json.dumps({"prompt": build(name, seed), "client_id": "sv-wrought"}).encode()
    rq = urllib.request.Request(f"{API}/prompt", data=body, headers={"Content-Type": "application/json"})
    pid = json.loads(urllib.request.urlopen(rq, timeout=120).read())["prompt_id"]
    for _ in range(2400):
        e = (_http_get_json(API, f"/history/{pid}", timeout=30) or {}).get(pid)
        if e and e.get("status", {}).get("completed"):
            return {"subject": name, "files": [i["filename"] for o in e.get("outputs", {}).values()
                                               for i in o.get("images", [])]}
        if e and e.get("status", {}).get("status_str") == "error":
            return {"subject": name, "error": json.dumps(e["status"].get("messages", []))[:300]}
        time.sleep(1.0)
    return {"subject": name, "error": "timeout"}


if __name__ == "__main__":
    for i, s in enumerate(sys.argv[1:] or list(SUBJECTS)):
        print(json.dumps(run(s, 4400 + i))); sys.stdout.flush()
