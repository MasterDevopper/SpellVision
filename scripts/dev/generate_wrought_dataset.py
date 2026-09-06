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
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "python"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_wrought import measure, verdict  # noqa: E402
import wrought_variants as variants  # noqa: E402
import wrought_comfy as wc  # noqa: E402

CULTURES = Path("C:/Users/xXste/Code_Projects/SpellBound-Engine/assets/content/cultures")

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
#
# TRIMMED (Task 5, prompt word budget): the removed clauses (meso-scale detail, no micro pore, no
# smooth gradients, skin colour variation) are now said once by LIVING_SKIN in wrought_variants --
# stating them twice was the tail spending words the face bundle needed.
#
# TRIMMED FURTHER, RULING 2026-09-06: dropped "structural folds that follow the form" -- the
# outfit clause already carries "structural folds" via CLOTHING/condition, and this was the tail's
# own restatement of it. Part of the 300-word hard budget (170 was measured wrong: it never
# accounted for the owner-locked 76-word WROUGHT_LEAD).
WROUGHT_TAIL = (
    "grounded stylized realism, physically based materials, every surface reads as its "
    "real substance, busy on the kit and simple on the void, same paint as the orc "
    "swordswoman plate"
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
        # Hair follows the HEAD: a kemonomimi head has ordinary hair (colour + texture from the
        # identity), a fully draconic alternate has a crown of horn and no hair colour at all.
        if race in variants.HEAD_VARIANTS:
            hair = variants.hair_for(race, pick["sex"], rng, head)
            if variants.is_kemonomimi(race, head):
                hair += f", a full head of {pick['hair_colour']} hair, {pick['hair_texture']}"
            pick["hair"] = hair
    subject = variants.subject_line(race, pick, info)
    prompt = f"{WROUGHT_LEAD} {subject}, {WROUGHT_TAIL}"
    n = variants.word_count(prompt)
    # RULING 3 2026-09-06: per-race allowance (dragonborn +60) rather than one global raised to
    # cover its four owned clauses. RULING 4 2026-09-06: opt-in alternate heads take a further +40
    # (authored records, not the race) -- see variants.budget_for.
    budget = variants.budget_for(race, head)
    if n > budget:
        raise ValueError(f"prompt is {n} words, budget {budget} for {race}: {prompt[:120]}")
    return prompt, pick


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("race")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--seed", type=int, default=9000)
    parser.add_argument("--out", default=str(REPO / "runtime" / "wrought_dataset"))
    parser.add_argument("--api", default=wc.Endpoint().api,
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
    parser.add_argument("--model", default=None, help="UNET checkpoint; defaults to wrought_comfy.UNET")
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
    endpoint = wc.Endpoint(args.api)
    rng = random.Random(args.seed)

    print(f"endpoint {endpoint.api} | model {args.model or wc.UNET} | {args.steps} steps cfg {args.cfg}"
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
        ram = endpoint.free_ram_gb()
        if 0 <= ram < 10:
            # The 20x cliff. Say it before the run slows rather than after it has.
            print(f"  [warn] host RAM free {ram:.1f} GB -- throughput collapses below ~8 GB; "
                  "restart ComfyUI to reclaim it")
        width, height = variants.canvas_for(pick["framing"])
        width, height = args.width or width, args.height or height
        extra = ", ".join(x for x in (
            variants.negative_for(pick["sex"]),
            variants.appearance_negative_for(pick["appearance"]),
            variants.SUIT_NEGATIVE if args.suit else "",
            variants.race_negative_for(args.race),
        ) if x)
        graph = wc.t2i_graph(positive, WROUGHT_NEG + (", " + extra if extra else ""),
                             seed, prefix, width, height, args.steps, args.cfg, args.model)
        target = out_dir / f"{index:03d}.png"
        if not wc.render(endpoint, graph, target):
            print(f"  {index:03d} FAILED")
            continue

        row = measure(target)
        # ORGANIC: every frame in a race batch is a character, so the no-gloss SKIN rule is enforced
        # rather than merely reported. This is not a formality. v20Quants at 30 steps produced a
        # blown-out white region across a torso on the 002 plate prompt, and the default gate PASSED
        # it -- the artifact's own noise raised detail_mid to 0.1117, the highest reading in the
        # whole model matrix, so the defect looked like quality. Under --organic it fails on gloss
        # 0.0518 against 0.045, which is the only criterion that saw it.
        checks = verdict(row, organic=True)
        record = {"index": index, "file": target.name, "seed": seed, "variation": pick,
                  "canvas": [width, height], "model": args.model or wc.UNET, "steps": args.steps,
                  "cfg": args.cfg, "endpoint": endpoint.api,
                  "prompt": positive, "gate": "WROUGHT" if all(ok for _, ok, _ in checks) else "OFF-STYLE",
                  "failed": [k for k, ok, _ in checks if not ok],
                  "metrics": {k: row.get(k) for k in
                              ("detail_mid", "saturation_p50", "material_floor", "gloss_fraction",
                               "face_px", "face_fine_over_meso", "face_texture")}}
        records.append(record)
        (out_dir / f"{index:03d}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(f"  {index:03d} {record['gate']:9s} ram {ram:5.1f}GB  "
              f"{pick['sex']:5s} {pick['age'][:12]:12s} {pick['tier']:13s} "
              f"{(args.head or '-'):13s} {pick.get('lineage', '-').split(' ')[0]:8s} "
              f"face {str(row.get('face_fine_over_meso', '-')):6s} "
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
