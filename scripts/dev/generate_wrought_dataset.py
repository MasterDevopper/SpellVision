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
import wrought_variants as variants  # noqa: E402

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

# THE STYLE BLOCK IS TWO HALVES AND THE ORDER IS MEASURED, NOT CHOSEN.
#
# The owner graded this in `runtime/style/datasets/wrought_house_v1/KREA2_PROMPT_ENGINEERING.md`:
# "002-lead beats subject-first for paint. Official 'first clause = subject' is true for identity
# steal, but house paint wants STUDIO + PBR MATERIALS IN THE FIRST SENTENCE, then the woman.
# Clothes-first also drifts painterly." And the C plates that led with the subject "went photoreal
# or anime". The block this replaced put the style LAST -- the exact ordering the owner had already
# measured as the photoreal drift. `002_REPEATABLE_FACTORS.md` section 8 gives the sentence.
#
# NEVER THE TOKEN "WROUGHT". Three owner documents say so independently (LESSONS_ORC: "it burned in
# as gold title text"; GOBLIN_10: "Do not title-token the word WROUGHT (burn-in)"; KREA2 notes:
# "Never title-token WROUGHT"), and this run reproduced it on an axe blade. The LoRA trigger
# `wrought style` belongs in the CAPTION files, where it is text for a trainer, not in a prompt for
# a sampler that renders text.
#
# NOT PAINTERLY. The replaced block asked for "painterly rendered surfaces". The owner's W5 lock
# (21 Aug, "all really good") is stated as "002-lead + not painterly / not oil / not brushstrokes",
# and every W4 nit is "a little too painterly". The word was pulling toward a graded failure.
#
# FULL COLOUR, NOT MUTED. The replaced block asked for "controlled saturation, restrained palette".
# `002_REPEATABLE_FACTORS.md` section 4: "Saturation is the game-character tell... punchy... NOT
# muted, not cinematic grade, not grey-olive" and bans `muted, desaturated, washed, grey-olive` when
# they leak. The Look Matrix ceiling (skin <= 0.45) still holds -- it is a ceiling, not a target.
WROUGHT_LEAD = (
    "A single strong directional key light in a dark studio, deep readable "
    "form shadows, almost no fill, no rim light, no set. Worked materials: tooled leather with "
    "flex creases and stitching, rivets seated in straps, beaten engraved metal that highlights "
    "only on its edges, matte chalky cloth with readable weave. Selective realism, not a "
    "photograph, not pore-level skin, not oil paint, not painterly, not cartoon. Full punchy earth "
    "and iron colour, not muted, not cinematic grade."
)
WROUGHT_TAIL = (
    "grounded stylized realism, physically based materials, material truth, every surface reads "
    "as its real substance, meso-scale surface detail, structural folds and creases that follow "
    "the underlying form, no micro pore detail, no smooth macro gradients, skin with living colour "
    "variation and no pore field, busy on the kit and simple on the void, "
    "same paint as the orc swordswoman plate"
)
WROUGHT_NEG = (
    # The house negative from 002_REPEATABLE_FACTORS section 8, merged rather than replaced.
    "photoreal, photograph, DSLR, micro pores, skin pores, pore detail, documentary, "
    "oil paint, painterly, brushstrokes, anime, cartoon, chibi, doll, anime-smooth, "
    "flat lighting, evenly lit, studio product photography, softbox, studio equipment in frame, "
    "beauty dish, rim light, neon, grayscale, muted, washed out, cinematic color grade, grey-olive, "
    "glossy, wet look, sheen, specular blowout, baked shading, painted highlights, "
    "grimdark, crushed blacks, desaturated grade, oversaturated, "
    "blurry, text, letters, watermark, signature, out of focus, bokeh, depth of field, "
    "two people, multiple figures, duplicate, mirrored pair, collage, "
    # THE WARDROBE IS ALWAYS WORN. Every frame draws a clothing tier, and the sampler dropped the
    # chest covering on 2 of 6 dragonborn anyway -- fantasy armour plus "full bust" has a strong
    # prior toward bare-chested. A style LoRA trained on that learns it. This is unconditional
    # rather than a suit-mode negative, because the failure is not about the suit: SUIT_NEGATIVE
    # carried these terms and so the one mode that could not produce the defect was the only mode
    # defended against it.
    "nude, topless, bare breasts, exposed nipples, bare chest, undressed, "
    # The owner's floor on the appearance axis, enforced where it actually binds. "Ugly" in this
    # cast means ordinary; the vocabulary never asks for worse and the negative refuses it.
    + variants.APPEARANCE_NEGATIVE
)

# The variation vocabulary lives in wrought_variants: race physicality, faces with the owner's
# floor on the appearance axis, hair, clothing tiers, condition, marks, framing and light. It is
# separate because it is the part the owner edits, and because race physicality belongs in the race
# pack once R10 unparks `face`.

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


def prompt_for(race: str, info: dict, rng: random.Random, sex: str | None = None,
               peak: bool = False, suit: bool = False,
               head: str | None = None, lineage: str | None = None) -> tuple[str, dict]:
    pick = (variants.draw_peak(race, rng, sex or "woman") if peak
            else variants.draw(race, rng, sex))
    if suit:
        # Applied AFTER the draw rather than as another branch of it, so the two modes compose:
        # --peak --suit is the same best-case face as the peak sheet, with the wardrobe removed.
        # That comparability is the point -- one axis changed, not two.
        pick = variants.apply_suit(pick)
    if lineage:
        pick["lineage"] = variants.lineage_for(race, rng, lineage)
    if head:
        pick["head"] = head
        # Re-drawn rather than kept, because hair follows the HEAD: a kemonomimi dragonborn has
        # ordinary hair and a fully draconic one has a crown of horn, and the draw that produced
        # `pick` did not know which head was coming.
        if race in variants.HEAD_VARIANTS:
            pick["hair"] = variants.hair_for(race, pick["sex"], rng, head)
    subject = variants.subject_line(race, pick, info)
    return f"{WROUGHT_LEAD} {subject}, {WROUGHT_TAIL}", pick


def build_graph(positive: str, seed: int, prefix: str, width: int, height: int,
                steps: int = 52, cfg: float = 3.5, unet: str | None = None,
                negative_extra: str = "") -> dict:
    return {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": unet or UNET, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP, "type": "krea2"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": ["2", 0]}},
        "6": {"class_type": "CLIPTextEncode",
              "inputs": {"text": WROUGHT_NEG + (", " + negative_extra if negative_extra else ""),
                         "clip": ["2", 0]}},
        "5": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 1.15}},
        "7": {"class_type": "EmptySD3LatentImage",
              "inputs": {"width": width, "height": height, "batch_size": 1}},
        "8": {"class_type": "KSampler",
              "inputs": {"model": ["5", 0], "seed": seed, "steps": steps, "cfg": cfg,
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
    parser.add_argument("--sex", choices=["woman", "man"], default=None,
                        help="run ONE SEX per batch. Fixed rather than drawn, so the female "
                             "invariant is enforced throughout and a review sheet is judged "
                             "against a single expectation.")
    parser.add_argument("--peak", action="store_true",
                        help="collapse the distribution to its best case: young, the striking "
                             "appearance tier, a portrait framing and a flattering key light. For "
                             "seeing the most beautiful women a race can produce, not for a batch.")
    parser.add_argument("--suit", action="store_true",
                        help="render in the neutral compression suit at full body instead of the "
                             "drawn wardrobe. The wardrobe carries the silhouette (the 002 "
                             "finding), so a race judged in armour is judged in its armourer's "
                             "taste; the suit shows the physiology itself. Composes with --peak.")
    parser.add_argument("--head", default=None,
                        help="select a head from wrought_variants.HEAD_VARIANTS for races whose "
                             "head is a design fork (dragonborn: draconic | short_muzzle | "
                             "flat_faced | crested). Ignored for races whose head is settled.")
    parser.add_argument("--lineage", default=None,
                        help="pin the draconic ancestry instead of drawing it (dragonborn: black | "
                             "blue | green | red | white | brass | bronze | copper | gold | "
                             "silver). Drawn uniformly when unset, so a batch covers all ten.")
    parser.add_argument("--model", default=None, help="UNET checkpoint; defaults to UNET above")
    parser.add_argument("--steps", type=int, default=52)
    parser.add_argument("--cfg", type=float, default=3.5)
    # OWNER-LOCKED SIZES. 002_REPEATABLE_FACTORS: "Do not retune the sampler to chase 002. Keep
    # 52 / 3.5 / euler / simple / 768x1024"; KREA2 notes: "768x1344 (outfit) or 768x1024 (002 paint
    # A/B)"; RACE_FEMALE_LOOK_LOCK: full body 768x1344, feet in. The canvas follows the FRAMING --
    # a portrait draw renders at the paint size, a full-figure draw at the outfit size -- and
    # neither is the 832x1216 this script had been using, which matched no locked plate.
    parser.add_argument("--width", type=int, default=None, help="override; default follows framing")
    parser.add_argument("--height", type=int, default=None, help="override; default follows framing")
    args = parser.parse_args()

    info = culture(args.race)
    suffix = ("_peak" if args.peak else "") + ("_suit" if args.suit else "") \
        + (f"_{args.head}" if args.head else "") + (f"_{args.lineage}" if args.lineage else "") \
        + (f"_{args.sex}" if args.sex else "")
    out_dir = Path(args.out) / f"{args.race}{suffix}"
    out_dir.mkdir(parents=True, exist_ok=True)
    API = args.api
    rng = random.Random(args.seed)

    print(f"endpoint {API} | model {args.model or UNET} | {args.steps} steps cfg {args.cfg}"
          f" | sex {args.sex or 'mixed'}")
    print(f"{args.race}: {info['materials']}")
    print(f"  ornament={info['ornament']} surface={info['surface']} palette={info['palette']}")
    print(f"  {args.count} frames -> {out_dir}\n")

    records = []
    for index in range(args.count):
        positive, pick = prompt_for(args.race, info, rng, args.sex, args.peak,
                                    args.suit, args.head, args.lineage)
        seed = args.seed + index
        prefix = f"wdata_{args.race}_{index:03d}"
        ram = free_ram_gb()
        if 0 <= ram < 10:
            # The 20x cliff. Say it before the run slows rather than after it has.
            print(f"  [warn] host RAM free {ram:.1f} GB -- throughput collapses below ~8 GB; "
                  "restart ComfyUI to reclaim it")
        width, height = variants.canvas_for(pick["framing"])
        width, height = args.width or width, args.height or height
        files = wait_for(submit(build_graph(positive, seed, prefix, width, height,
                                            args.steps, args.cfg, args.model,
                                            ", ".join(x for x in (
                                                variants.negative_for(pick["sex"]),
                                                variants.appearance_negative_for(pick["appearance"]),
                                                variants.SUIT_NEGATIVE if args.suit else "",
                                                variants.race_negative_for(args.race),
                                            ) if x))))
        if not files:
            print(f"  {index:03d} FAILED")
            continue

        target = out_dir / f"{index:03d}.png"
        target.write_bytes(fetch(files[0]))

        row = measure(target)
        # ORGANIC: every frame in a race batch is a character, so the no-gloss SKIN rule is enforced
        # rather than merely reported. This is not a formality. v20Quants at 30 steps produced a
        # blown-out white region across a torso on the 002 plate prompt, and the default gate PASSED
        # it -- the artifact's own noise raised detail_mid to 0.1117, the highest reading in the
        # whole model matrix, so the defect looked like quality. Under --organic it fails on gloss
        # 0.0518 against 0.045, which is the only criterion that saw it.
        checks = verdict(row, organic=True)
        record = {"index": index, "file": target.name, "seed": seed, "variation": pick,
                  "canvas": [width, height], "model": args.model or UNET, "steps": args.steps,
                  "cfg": args.cfg, "endpoint": API,
                  "prompt": positive, "gate": "WROUGHT" if all(ok for _, ok, _ in checks) else "OFF-STYLE",
                  "failed": [k for k, ok, _ in checks if not ok],
                  "metrics": {k: row[k] for k in
                              ("detail_mid", "saturation_p50", "material_floor", "gloss_fraction")}}
        records.append(record)
        (out_dir / f"{index:03d}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(f"  {index:03d} {record['gate']:9s} ram {ram:5.1f}GB  "
              f"{pick['sex']:5s} {pick['age'][:12]:12s} {pick['tier']:13s} "
              f"{(args.head or '-'):13s} {pick.get('lineage', '-').split(' ')[0]:8s} "
              f"{pick['appearance'].split(',')[0][:26]}")
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
