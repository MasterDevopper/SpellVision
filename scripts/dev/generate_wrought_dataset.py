"""Generate a judged Wrought dataset, one race at a time, from the engine's own culture files.

The owner judges pass/fail; this produces the candidates and the review sheets. What comes out is
two things at once: the training set for a Wrought style LoRA, and a labelled sample wide enough to
re-derive the gate's thresholds -- which currently rest on seventeen character plates and have been
wrong four times for exactly that reason.

PROMPTS COME FROM `assets/content/cultures/<race>.ron`, not from invention. Each culture already
carries `material_logic`, an `ornament` rule, a `surface_bias` and a named palette with hex values,
so a dwarf renders in forged steel and cut stone with Maker ornament and a goblin in brass and
salvage, because the world says so. A dataset generated off generic fantasy vocabulary would train a
LoRA on a world that does not exist.

VARIATION IS DELIBERATE AND STRUCTURED. A hundred near-identical frames teach a LoRA one pose. Each
render draws a different combination of sex, build, age, wardrobe tier, framing and light angle,
while the STYLE block stays fixed -- because the style is the thing being taught and everything else
is what it must survive.

TWO OPERATIONAL FACTS, both measured this session:

* **Host RAM is the throughput cliff, not VRAM.** Renders ran at 20-26 s/iteration against ~1.1 s/it
  once host RAM fell to 6.3 GB free -- a 20x collapse, because DynamicVRAM pages weights there.
  `POST /free` reclaimed almost nothing since the in-flight model holds it. This checks free RAM
  between renders and warns before the cliff rather than after.
* **The style token can render as text.** "WROUGHT" appeared on an axe blade despite `text` in the
  negative. Frames are gated, but a text filter is still needed before training; noted per-frame so
  the owner can reject on sight.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "python"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from comfy_prompt_client import _http_get_json  # noqa: E402
from check_wrought import measure, verdict  # noqa: E402

API = "http://127.0.0.1:8188"
CULTURES = Path("C:/Users/xXste/Code_Projects/SpellBound-Engine/assets/content/cultures")
# The QUANT of the same v10 the 002 plate used -- same lineage, and it is what makes a long run
# survive. Measured back to back on identical prompt and seed: bf16 148.7 s leaving 6.6 GB of host
# RAM free, quant 146.6 s leaving 10.4 GB, both passing the Wrought gate. Sustained over six frames
# the quant held 2.21 s/iteration with RAM stable at 10.8 GB, where bf16 had collapsed to 20-26 s/it
# at 6.4 GB free -- because ComfyUI's resident copy plus the OS file cache of a 23.88 GB checkpoint
# leaves DynamicVRAM nowhere to page. A 900-frame run cannot afford that.
UNET = "loxsUtopicWorldKrea2_v10Quants.safetensors"
CLIP = "qwen3vl_4b_fp8_scaled.safetensors"
VAE = "qwen_image_vae.safetensors"

# Fixed. This is the thing being taught; everything else varies around it.
WROUGHT_STYLE = (
    "WROUGHT style, grounded stylized realism, PBR-native, physically based materials, "
    "material truth, every surface reads as its real substance, "
    "meso-scale surface detail, structural folds and creases that follow the underlying form, "
    "no micro pore detail, no smooth macro gradients, "
    "dark studio background, single dominant key light, deep shadow falloff, "
    "light and falloff come from the scene and not from painted highlights, "
    "controlled saturation, restrained palette, painterly rendered surfaces"
)
WROUGHT_NEG = (
    "photoreal, photograph, micro pores, skin pores, anime, cartoon, anime-smooth, "
    "flat lighting, evenly lit, studio product photography, "
    "glossy, wet look, sheen, specular blowout, baked shading, painted highlights, "
    "grimdark, crushed blacks, desaturated grade, oversaturated, "
    "blurry, text, letters, watermark, signature, out of focus, bokeh, depth of field, "
    "two people, multiple figures, duplicate, mirrored pair, collage"
)

# The axes a hundred frames vary along. Style holds; these do not.
SEX = ["woman", "man"]
BUILD = ["lean and wiry", "heavy and thick-set", "broad and muscular", "slight and narrow",
         "stocky and powerful", "tall and rangy"]
AGE = ["young adult", "in their prime", "middle-aged", "weathered and old"]
TIER = ["plain working clothes, patched and worn",
        "a travelling outfit with a heavy cloak",
        "practical armour over layered cloth",
        "full heavy armour of the culture's making",
        "fine clothes marking status"]
FRAMING = ["full body standing, head to toe",
           "three-quarter length, from the thighs up",
           "waist-up portrait",
           "head and shoulders portrait"]
LIGHT = ["key light from the upper left", "key light from the upper right",
         "key light from one side, near profile", "key light from slightly above and in front"]


def culture(race: str) -> dict:
    """Materials, ornament, surface bias and palette, read out of the engine's own content."""
    text = (CULTURES / f"{race}.ron").read_text(encoding="utf-8")
    materials = re.search(r"material_logic:\s*\[(.*?)\]", text, re.S)
    return {
        "materials": ", ".join(re.findall(r'"([^"]+)"', materials.group(1))) if materials else "",
        "ornament": (re.search(r"ornament:\s*(\w+)", text) or [None, ""])[1],
        "surface": (re.search(r"surface_bias:\s*(\w+)", text) or [None, ""])[1],
        "palette": ", ".join(n for n, _ in re.findall(r'Swatch\("([^"]+)",\s*"(#[0-9A-Fa-f]{6})"', text)[:4]),
    }


def prompt_for(race: str, info: dict, rng: random.Random) -> tuple[str, dict]:
    pick = {"sex": rng.choice(SEX), "build": rng.choice(BUILD), "age": rng.choice(AGE),
            "tier": rng.choice(TIER), "framing": rng.choice(FRAMING), "light": rng.choice(LIGHT)}
    subject = (
        f"a single {race.replace('_', ' ')} {pick['sex']}, {pick['build']}, {pick['age']}, "
        f"wearing {pick['tier']}, {pick['framing']}, {pick['light']}, "
        f"materials of this culture: {info['materials']}, "
        f"{info['surface'].lower()} surfaces, {info['ornament'].lower()} ornament, "
        f"palette of {info['palette']}"
    )
    return f"{subject}, {WROUGHT_STYLE}", pick


def build_graph(positive: str, seed: int, prefix: str, width: int, height: int) -> dict:
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP, "type": "krea2"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": ["2", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": WROUGHT_NEG, "clip": ["2", 0]}},
        "5": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 1.15}},
        "7": {"class_type": "EmptySD3LatentImage",
              "inputs": {"width": width, "height": height, "batch_size": 1}},
        "8": {"class_type": "KSampler",
              "inputs": {"model": ["5", 0], "seed": seed, "steps": 52, "cfg": 3.5,
                         "sampler_name": "euler", "scheduler": "simple", "positive": ["4", 0],
                         "negative": ["6", 0], "latent_image": ["7", 0], "denoise": 1.0}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": prefix}},
    }


def fetch(filename: str) -> bytes:
    """Pull a rendered frame over HTTP, never off a disk path.

    THE BANKED HAZARD, and it fails silently. A disk path resolves on the machine running THIS
    script, so pointing the harness at a remote endpoint would copy whatever sits in the LOCAL
    ComfyUI output directory -- and that directory is full of this session's earlier renders, so the
    dataset fills with plausible, wrong, unrelated images and nothing errors. The recorded form of
    this is exact: "HTTP paths work remotely, disk paths do not; the hazard is a FULL stale output
    dir, not an empty one." An empty one would at least crash.

    /view is served by whichever endpoint rendered the frame, so this is correct on localhost and on
    spellnode without a branch.
    """
    url = f"{API}/view?filename={urllib.parse.quote(filename)}&type=output"
    with urllib.request.urlopen(url, timeout=180) as response:
        return response.read()


def free_ram_gb() -> float:
    try:
        return _http_get_json(API, "/system_stats", timeout=15)["system"]["ram_free"] / 2**30
    except Exception:
        return -1.0


def submit(graph: dict) -> str:
    body = json.dumps({"prompt": graph, "client_id": "sv-wrought-dataset"}).encode()
    request = urllib.request.Request(f"{API}/prompt", data=body,
                                     headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(request, timeout=120).read())["prompt_id"]


def wait_for(prompt_id: str, timeout_s: int = 900) -> list[str]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        entry = (_http_get_json(API, f"/history/{prompt_id}", timeout=30) or {}).get(prompt_id)
        if entry:
            status = entry.get("status", {})
            if status.get("completed"):
                return [i["filename"] for o in entry.get("outputs", {}).values()
                        for i in o.get("images", [])]
            if status.get("status_str") == "error":
                return []
        time.sleep(2.0)
    return []


def main() -> int:
    global API  # set from --api before anything reads it
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("race")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--seed", type=int, default=9000)
    parser.add_argument("--out", default=str(REPO / "runtime" / "wrought_dataset"))
    parser.add_argument("--api", default=API,
                        help="ComfyUI endpoint. http://192.168.1.127:8188 is spellnode; frames are "
                             "fetched over HTTP so a remote endpoint needs no share and no branch.")
    parser.add_argument("--width", type=int, default=832)
    parser.add_argument("--height", type=int, default=1216)
    args = parser.parse_args()

    info = culture(args.race)
    out_dir = Path(args.out) / args.race
    out_dir.mkdir(parents=True, exist_ok=True)
    API = args.api
    rng = random.Random(args.seed)

    print(f"endpoint {API}")
    print(f"{args.race}: {info['materials']}")
    print(f"  ornament={info['ornament']} surface={info['surface']} palette={info['palette']}")
    print(f"  {args.count} frames -> {out_dir}\n")

    records = []
    for index in range(args.count):
        positive, pick = prompt_for(args.race, info, rng)
        seed = args.seed + index
        prefix = f"wdata_{args.race}_{index:03d}"
        ram = free_ram_gb()
        if 0 <= ram < 10:
            # The 20x cliff. Say it before the run slows rather than after it has.
            print(f"  [warn] host RAM free {ram:.1f} GB -- throughput collapses below ~8 GB; "
                  "restart ComfyUI to reclaim it")
        files = wait_for(submit(build_graph(positive, seed, prefix, args.width, args.height)))
        if not files:
            print(f"  {index:03d} FAILED")
            continue

        target = out_dir / f"{index:03d}.png"
        target.write_bytes(fetch(files[0]))

        row = measure(target)
        checks = verdict(row)
        record = {"index": index, "file": target.name, "seed": seed, "variation": pick,
                  "prompt": positive, "gate": "WROUGHT" if all(ok for _, ok, _ in checks) else "OFF-STYLE",
                  "failed": [k for k, ok, _ in checks if not ok],
                  "metrics": {k: row[k] for k in
                              ("detail_mid", "saturation_p50", "material_floor", "gloss_fraction")}}
        records.append(record)
        (out_dir / f"{index:03d}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(f"  {index:03d} {record['gate']:9s} ram {ram:5.1f}GB  "
              f"{pick['sex']}/{pick['build'][:12]}/{pick['framing'][:14]}")
        sys.stdout.flush()

    summary = out_dir / "_summary.json"
    passed = sum(1 for r in records if r["gate"] == "WROUGHT")
    summary.write_text(json.dumps({"race": args.race, "count": len(records),
                                   "gate_pass": passed, "records": records}, indent=2),
                       encoding="utf-8")
    print(f"\n{args.race}: {passed}/{len(records)} pass the gate (owner judgement is what counts)")
    print(f"wrote {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
