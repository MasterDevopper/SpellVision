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
import wrought_measures as measures  # noqa: E402
import wrought_wardrobe as wardrobe  # noqa: E402

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


# A 27,000-draw sweep (Task 7 fix round 1) found dwarf over its budget on 5 of 50 seeds and
# dragonborn on 1 of 50 -- the vocabulary is right on average and wrong on a tail, not broken.
PROMPT_REDRAWS = 8


def _apply_forks(pick: dict, race: str, rng: random.Random, head: str | None, lineage: str | None) -> dict:
    """Apply the two opt-in forks (`--head`, `--lineage`) to a drawn pick, in place.

    ONE owner for both paths. Lane A drew its pick with `variants.draw` and never looked at
    `args.lineage`, so the ten "lineage batches" of 2026-09-06 (`--lineage black` ... `silver`)
    rendered twenty RANDOM lineages into dirs named for the flag -- `dragonborn_woman_red/000` is a
    brass dragon. The fork lived only inside `prompt_for`; now it lives here and both call it.
    """
    if lineage:
        pick["lineage"] = variants.lineage_for(race, rng, lineage)
    if head:
        pick["head"] = head
        # Hair follows the HEAD: a kemonomimi head has ordinary hair (colour + texture from the
        # identity), a fully draconic alternate has a crown of horn and no hair colour at all.
        pick["hair"] = variants.hair_for(race, pick["sex"], rng, head, pick["hair_colour"], pick["hair_texture"])
    return pick


def prompt_for(race: str, info: dict, rng: random.Random, sex: str | None = None,
               peak: bool = False, suit: bool = False,
               head: str | None = None, lineage: str | None = None) -> tuple[str, dict]:
    # A rare over-budget draw is a REDRAW, not a crashed frame: the guard stays hard on the
    # vocabulary (still raises if it never holds), but a batch must not die on seed luck.
    for _attempt in range(PROMPT_REDRAWS):
        pick = (variants.draw_peak(race, rng, sex or "woman", culture_materials=info["materials"]) if peak
                else variants.draw(race, rng, sex, culture_materials=info["materials"]))
        if suit:
            # Applied AFTER the draw rather than as another branch of it, so the two modes compose:
            # --peak --suit is the same best-case face as the peak sheet, with the wardrobe removed.
            # That comparability is the point -- one axis changed, not two.
            pick = variants.apply_suit(pick)
        _apply_forks(pick, race, rng, head, lineage)
        subject = variants.subject_line(race, pick, info)
        prompt = f"{WROUGHT_LEAD} {subject}, {WROUGHT_TAIL}"
        n = variants.word_count(prompt)
        # RULING 3 2026-09-06: per-race allowance (dragonborn +60) rather than one global raised to
        # cover its four owned clauses. RULING 4 2026-09-06: opt-in alternate heads take a further +40
        # (authored records, not the race) -- see variants.budget_for.
        budget = variants.budget_for(race, head)
        if n <= budget:
            return prompt, pick
    raise ValueError(f"prompt is {n} words, budget {budget} for {race}: {prompt[:120]}")


def lane_a_prompts(race: str, info: dict, pick: dict) -> tuple[str, str]:
    """The skin plate's full prompt and the suit edit's prompt, both 002-led.

    Budget is the race's own `budget_for(race)` (no head -- Lane A never selects one), not the flat
    `PROMPT_WORD_BUDGET`: dragonborn's four owned clauses put it at 460, and the flat 400 refused
    every dragonborn draw outright (30/30 in a sweep), not just a rare tail seed.
    """
    skin_subject = variants.subject_line(race, pick, info)
    suit_subject = ", ".join([variants.SUIT_EDIT_INSTRUCTION, pick["framing"], pick["light"]])
    skin = f"{WROUGHT_LEAD} {skin_subject}, {WROUGHT_TAIL}"
    suit = f"{WROUGHT_LEAD} {suit_subject}, {WROUGHT_TAIL}"
    budget = variants.budget_for(race, fur=pick.get("fur") or None)
    for p in (skin, suit):
        n = variants.word_count(p)
        if n > budget:
            raise ValueError(f"prompt is {n} words, budget {budget} for {race}: {p[:120]}")
    return skin, suit


def _json_safe(pick: dict) -> dict:
    """The record's `variation` must round-trip through json.dumps. `pick["outfit"]` is an Outfit
    dataclass, not a dict, since Task 7 -- write its fields instead of the object itself."""
    return {k: (v.__dict__ if hasattr(v, "__dict__") else v) for k, v in pick.items()}


def render_lane_a(endpoint: "wc.Endpoint", race: str, info: dict, rng: random.Random, index: int,
                  seed: int, out_dir: Path, registry: variants.IdentityRegistry, args) -> dict | None:
    # Redraw until the identity is new -- a batch refuses a repeat (DIRECTION_V2 section 4). A
    # budget breach on this draw's prompts is treated the same way: a rare over-budget draw is a
    # redraw, not a crash, the same rule `prompt_for` already follows.
    # Task 15C: the fur ladder (--fur, --subspecies). --subspecies pins a beastfolk row; 'cycle'
    # takes the frame index so a batch renders one of each subspecies in order. Resolved here, once,
    # rather than in the redraw loop below, since it does not change across the 8 attempts.
    fur = getattr(args, "fur", None)
    subspecies_arg = getattr(args, "subspecies", None)
    sub_table = variants.SUBSPECIES.get(race, {})
    resolved_subspecies = (sorted(sub_table)[index % len(sub_table)] if subspecies_arg == "cycle" and sub_table
                           else subspecies_arg if subspecies_arg else None)
    pick = key = skin_prompt = suit_prompt = None
    for _attempt in range(8):
        candidate = variants.apply_skin_plate(
            variants.draw(race, rng, "woman", culture_materials=info["materials"],
                         subspecies=resolved_subspecies, fur=fur))
        _apply_forks(candidate, race, rng, getattr(args, "head", None), getattr(args, "lineage", None))
        candidate_key = variants.identity_key(candidate)
        # A --fur batch renders the SAME character at every rung on purpose (same --seed -> same
        # draws -> same face/hair/nation, only the fur clause differs), so the registry would refuse
        # every rung after the first. Bypassed entirely when --fur is set: not checked here, not
        # added below.
        if not fur and registry.seen(candidate_key):
            continue
        try:
            skin_prompt, suit_prompt = lane_a_prompts(race, info, candidate)
        except ValueError:
            continue
        pick, key = candidate, candidate_key
        break
    else:
        print(f"  {index:03d} no new identity in 8 draws -- vocabulary too narrow for {race}")
        return None
    width, height = variants.CANVAS_LANE_A
    # A fur rung prunes the garment reading of "fur" -- the first ladder's velvet rung rendered a velvet
    # jacket on 4 of 6 plates. The positive (FUR_GROWN) builds; this only prunes.
    fur_negative = variants.FUR_NEGATIVE if pick.get("fur") not in ("", None, "none") else ""
    negative = ", ".join(x for x in (WROUGHT_NEG, variants.negative_for("woman"),
                                     variants.appearance_negative_for(pick["appearance"]),
                                     variants.SKIN_PLATE_NEGATIVE, variants.race_negative_for(race),
                                     fur_negative) if x)
    skin_png, suit_png = out_dir / f"{index:03d}_skin.png", out_dir / f"{index:03d}_suit.png"
    ram = endpoint.free_ram_gb()
    if 0 <= ram < 10:
        # The 20x cliff (see module docstring). Once per pair, before the skin render -- the same
        # warning the legacy loop prints, so a Lane A batch gets the same heads-up.
        print(f"  [warn] host RAM free {ram:.1f} GB -- throughput collapses below ~8 GB; "
              "restart ComfyUI to reclaim it")
    if not wc.render(endpoint, wc.t2i_graph(skin_prompt, negative, seed, f"wv2_{race}_{index:03d}_skin",
                                            width, height, args.steps, args.cfg, args.model), skin_png):
        print(f"  {index:03d} skin FAILED"); return None
    if not getattr(args, "skin_only", False):
        # --skin-only (Task 15C): the fur ladder judges the skin plate alone -- no reference upload,
        # no suit edit. suit_png is never created, so every downstream `png.exists()` /
        # `suit_png.exists()` check below already yields the right shape (files.suit/gate.suit/
        # measures None) without a second branch.
        ref_name = endpoint.upload_reference(skin_png)
        suit_negative = ", ".join([WROUGHT_NEG, variants.negative_for("woman"), variants.SUIT_NEGATIVE])
        if not wc.render(endpoint, wc.reference_edit_graph(suit_prompt, suit_negative, seed + 500_000,
                                                           f"wv2_{race}_{index:03d}_suit", width, height,
                                                           ref_name, args.steps, args.cfg, args.model), suit_png):
            print(f"  {index:03d} suit FAILED (skin kept)")
    if not fur:
        registry.add(key, f"{out_dir.name}/{index:03d}")
    # The shape is the same whether or not the suit rendered -- "suit"/"silhouette"/"identity" are
    # always present, None when there is nothing to report, so a reader never has to branch on a
    # missing key to tell a failure from a pass.
    gates = {"skin": None, "suit": None}
    for name, png in (("skin", skin_png), ("suit", suit_png)):
        if png.exists():
            row = measure(png)
            checks = verdict(row, organic=True)
            gates[name] = {"gate": "WROUGHT" if all(ok for _, ok, _ in checks) else "OFF-STYLE",
                           "failed": [k for k, ok, _ in checks if not ok],
                           "metrics": {k: row.get(k) for k in ("detail_mid", "material_floor", "gloss_fraction",
                                                                "face_px", "face_fine_over_meso")}}
    measures_out = {"silhouette": None, "identity": None}
    if suit_png.exists():
        measures_out = {"silhouette": measures.silhouette_delta(skin_png, suit_png),
                        "identity": measures.face_identity(skin_png, suit_png)}
    record = {"lane": "a", "race": race, "index": index, "seed": seed, "identity_key": key,
              "variation": _json_safe(pick), "canvas": [width, height], "model": args.model or wc.UNET,
              "steps": args.steps, "cfg": args.cfg, "endpoint": endpoint.api,
              "prompts": {"skin": skin_prompt, "suit": suit_prompt},
              "files": {"skin": skin_png.name, "suit": suit_png.name if suit_png.exists() else None},
              "gate": gates, "measures": measures_out}
    (out_dir / f"{index:03d}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    sil = measures_out.get("silhouette") or {}
    skin_gate = gates.get("skin") or {}
    suit_gate = gates.get("suit") or {}
    print(f"  {index:03d} skin {skin_gate.get('gate', '-'):9s} suit {suit_gate.get('gate', '-'):9s} "
          f"waist d {sil.get('waist_delta_px', '-')} hip d {sil.get('hip_delta_px', '-')} "
          f"{pick['nation']:12s} {pick.get('subspecies', ''):8s} {pick.get('fur', ''):6s} {pick['appearance']}")
    return record


# --- Lane B: asset plates (garment/weapon/etc alone) and fit plates (the outfit worn) -----------
#
# ASSET_NEGATIVE rides on every asset plate ONLY (never a fit plate, which needs the figure). Guide
# section 7.5 wants the garment or object alone, and the model's own prior for "clothes" or "armour"
# includes a body wearing them unless told otherwise.
ASSET_NEGATIVE = "person, figure, face, hands, body, mannequin head, portrait, character"


def lane_b_prompt(kind: str, race: str, info: dict, rng: random.Random, fit: bool) -> tuple[str, dict]:
    """The Lane B prompt: an asset alone (`kind`), or with `fit=True` the same wardrobe WORN by a
    freshly drawn character, with the composition axis (square 6 / candid 4) on the framing.

    Budget is the race's own `budget_for(race)` (Lane B never selects a head), not the flat
    `PROMPT_WORD_BUDGET` -- the same reason `lane_a_prompts` does this. A fit prompt draws a whole
    character, so a rare over-budget draw is a REDRAW (up to `PROMPT_REDRAWS` attempts), same rule
    `prompt_for` already follows; an asset-alone prompt is short enough that a breach is a real bug,
    not sampling tail, so it raises on the first draw.
    """
    budget = variants.budget_for(race)
    if fit:
        for _attempt in range(PROMPT_REDRAWS):
            pick = variants.draw(race, rng, "woman", culture_materials=info["materials"])
            pick["framing"] = "full body standing, head to toe, " + variants.composition_for(rng)
            subject = variants.subject_line(race, pick, info)
            prompt = f"{WROUGHT_LEAD} {subject}, {WROUGHT_TAIL}"
            n = variants.word_count(prompt)
            if n <= budget:
                meta = {"kind": "fit", "outfit": pick["outfit"].__dict__, "variation": _json_safe(pick)}
                return prompt, meta
        raise ValueError(f"prompt is {n} words, budget {budget} for {race}: {prompt[:120]}")
    if kind == "outfit":
        outfit = wardrobe.draw_outfit(race, rng, info["materials"])
        prompt = f"{WROUGHT_LEAD} {outfit.plate_clause()}, {WROUGHT_TAIL}"
        meta = {"kind": kind, "outfit": outfit.__dict__, "caption": outfit.caption()}
    else:
        asset = wardrobe.draw_asset(kind, race, rng, info["materials"])
        prompt = f"{WROUGHT_LEAD} {asset.plate_clause}, {WROUGHT_TAIL}"
        meta = {"kind": kind, "asset": asset.__dict__, "caption": asset.caption}
    n = variants.word_count(prompt)
    if n > budget:
        raise ValueError(f"prompt is {n} words, budget {budget} for {race}: {prompt[:120]}")
    return prompt, meta


def render_lane_b(endpoint: "wc.Endpoint", race: str, info: dict, rng: random.Random, index: int,
                  seed: int, out_dir: Path, args,
                  registry: "variants.IdentityRegistry | None" = None) -> dict | None:
    """Fix round 1 (folded minor): a fit plate is a character, so it goes through the identity
    registry the same way Lane A does -- "no two characters alike" applies to Lane B fit plates
    too. An asset plate is a garment or object, not a person, and skips the registry entirely."""
    key = None
    if args.fit:
        for _attempt in range(8):
            prompt, meta = lane_b_prompt(args.asset, race, info, rng, True)
            key = variants.identity_key(meta["variation"])
            if not registry.seen(key):
                break
        else:
            print(f"  {index:03d} no new identity in 8 draws -- vocabulary too narrow for {race}")
            return None
    else:
        prompt, meta = lane_b_prompt(args.asset, race, info, rng, False)
    width, height = variants.CANVAS_FIT if args.fit else variants.CANVAS_ASSET
    negative = WROUGHT_NEG if args.fit else f"{WROUGHT_NEG}, {ASSET_NEGATIVE}"
    if args.fit:
        negative = ", ".join([negative, variants.negative_for("woman"),
                              variants.appearance_negative_for(meta["variation"]["appearance"]),
                              variants.race_negative_for(race)])
    stem = f"{index:03d}_{'fit' if args.fit else args.asset}"
    png = out_dir / f"{stem}.png"
    if not wc.render(endpoint, wc.t2i_graph(prompt, negative, seed, f"wv2_{race}_{stem}", width, height,
                                            args.steps, args.cfg, args.model), png):
        print(f"  {index:03d} FAILED"); return None
    if args.fit:
        registry.add(key, f"{out_dir.name}/{index:03d}")
    row = measure(png)
    checks = verdict(row, organic=bool(args.fit))
    record = {"lane": "b", "race": race, "index": index, "seed": seed, "canvas": [width, height],
              "model": args.model or wc.UNET, "steps": args.steps, "cfg": args.cfg, "endpoint": endpoint.api,
              "prompt": prompt, "file": png.name, **meta,
              **({"identity_key": key} if args.fit else {}),
              "gate": "WROUGHT" if all(ok for _, ok, _ in checks) else "OFF-STYLE",
              "failed": [k for k, ok, _ in checks if not ok],
              "metrics": {k: row.get(k) for k in ("detail_mid", "material_floor", "gloss_fraction")}}
    (out_dir / f"{index:03d}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(f"  {index:03d} {record['gate']:9s} {meta['kind']:9s} {meta.get('caption', '')[:70]}")
    return record


def validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """Fix round 1 (Important #1): `--fit` used to silently ignore a stray `--asset` -- it always
    renders the drawn OUTFIT worn by a character, never a weapon/shoes/armour/equipment/accessory
    worn, so a `--fit --asset weapon` that looked like it asked for a worn weapon plate quietly
    rendered the outfit instead with no warning. Now an argparse-style usage error."""
    if args.lane == "b" and args.fit and args.asset != "outfit":
        parser.error("--fit renders the drawn OUTFIT worn by a character; --asset applies to "
                     "alone plates only")
    # Task 15C: --subspecies/--fur only mean anything for a race with a subspecies table
    # (beastfolk today) -- named early as usage errors rather than silently drawing/ignored.
    # `args.race` is read only once either flag is actually set, so a caller (e.g. a test) that
    # builds a bare Namespace for an unrelated check (--fit/--asset) is untouched.
    subspecies_arg = getattr(args, "subspecies", None)
    fur_arg = getattr(args, "fur", None)
    if subspecies_arg or fur_arg:
        race = getattr(args, "race", None)
        table = variants.SUBSPECIES.get(race)
        if subspecies_arg:
            if not table:
                parser.error(f"--subspecies is only valid for a race with a subspecies table (not {race})")
            elif subspecies_arg != "cycle" and subspecies_arg not in table:
                parser.error(f"--subspecies {subspecies_arg!r} is not in {race}'s table: "
                             f"{sorted(table)} (or 'cycle')")
        if fur_arg and not table:
            parser.error(f"--fur is only valid for a race with a subspecies table (not {race})")


def out_dir_for(args) -> Path:
    """The one out_dir expression for every lane -- `main()` had three copies (Lane A, Lane B,
    legacy) that had drifted: Task 15A found Lane A always named its dir `<race>_woman`, ignoring
    `--head`/`--lineage`, so ten dragonborn lineage batches (`--lineage red`, `--lineage blue`, ...)
    would all land in the same `dragonborn_woman/` and overwrite each other's frames.

    Lane A now carries the same suffixes the legacy path already used for exactly this reason
    (`_<head>` then `_<lineage>`, in that order -- head is the coarser fork so it sorts first).
    Lane B and legacy are unchanged from the branches this replaces.
    """
    if args.lane == "a":
        # Task 15C: --subspecies/--fur append after head/lineage. getattr with a default keeps the
        # pre-existing SimpleNamespace-based tests (which never set these two attrs) passing
        # unchanged. subspecies only names the dir when it is an actual NAME -- 'cycle' renders one
        # of each subspecies in the SAME dir, so it must not be named in the dir once per name.
        subspecies_arg = getattr(args, "subspecies", None)
        fur_arg = getattr(args, "fur", None)
        suffix = ((f"_{args.head}" if args.head else "") + (f"_{args.lineage}" if args.lineage else "")
                  + (f"_{subspecies_arg}" if subspecies_arg and subspecies_arg != "cycle" else "")
                  + (f"_fur-{fur_arg}" if fur_arg else ""))
        return Path(args.out) / f"{args.race}_woman{suffix}"
    if args.lane == "b":
        return Path(args.out) / f"{args.race}_{'fit' if args.fit else args.asset}"
    suffix = ("_peak" if args.peak else "") + ("_suit" if args.suit else "") \
        + (f"_{args.head}" if args.head else "") + (f"_{args.lineage}" if args.lineage else "") \
        + (f"_{args.sex}" if args.sex else "")
    return Path(args.out) / f"{args.race}{suffix}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("race")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--seed", type=int, default=9000)
    parser.add_argument("--out", default=str(REPO / "runtime" / "wrought_v2"))
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
    parser.add_argument("--lane", choices=["a", "b", "legacy"], default="legacy",
                        help="a: the skin plate then the suit as a reference edit of it "
                             "(DIRECTION_V2 section 9), one identity per pair. b: asset plates -- "
                             "the drawn outfit or one Asset (--asset) alone on a mannequin/dark "
                             "ground, or (--fit) the same outfit worn by a drawn character with the "
                             "composition axis. legacy: the original one-plate-per-index loop this "
                             "script had before Lane A/B.")
    parser.add_argument("--asset", choices=["outfit", *wardrobe.ASSET_KINDS], default="outfit",
                        help="Lane B only: which asset the plate shows alone. 'outfit' is the drawn "
                             "wardrobe on a mannequin; the rest are one standalone Asset.")
    parser.add_argument("--fit", action="store_true",
                        help="Lane B fit plate: the drawn outfit WORN by a drawn character, with "
                             "the composition axis")
    parser.add_argument("--subspecies", default=None,
                        help="pin a subspecies (beastfolk: leopard | bear | lion | deer | panda | "
                             "wolf) instead of drawing it, or 'cycle' so frame index i takes "
                             "sorted(table)[i %% len(table)] -- one of each across a batch. Only "
                             "valid for a race with a subspecies table.")
    parser.add_argument("--fur", choices=variants.FUR_LEVELS, default=None,
                        help="OWNER 2026-09-06 fur-coverage ladder, on the first v2 beastfolk "
                             "plates: 'Test different amounts of full body fur from none to long "
                             "full fur coverage, what I want exists somewhere in between.' none | "
                             "down | velvet | short | plush | long, opt-in (default draw unchanged). "
                             "A --fur batch bypasses the identity registry -- see render_lane_a.")
    parser.add_argument("--skin-only", action="store_true",
                        help="Lane A: render the skin plate only -- no reference upload, no suit "
                             "edit, no silhouette/identity measures. For the fur ladder, where only "
                             "the skin plate shows the coat.")
    args = parser.parse_args()
    validate_args(args, parser)

    info = culture(args.race)
    out_dir = out_dir_for(args)
    out_dir.mkdir(parents=True, exist_ok=True)
    endpoint = wc.Endpoint(args.api)
    rng = random.Random(args.seed)
    registry = variants.IdentityRegistry(Path(args.out) / "_identities.json")

    print(f"endpoint {endpoint.api} | model {args.model or wc.UNET} | {args.steps} steps cfg {args.cfg}"
          f" | sex {args.sex or 'mixed'}")
    print(f"{args.race}: {info['materials']}")
    print(f"  ornament={info['ornament']} surface={info['surface']} palette={info['palette']}")
    print(f"  {args.count} frames -> {out_dir}\n")

    records = []
    if args.lane == "a":
        for index in range(args.count):
            record = render_lane_a(endpoint, args.race, info, rng, index, args.seed + index,
                                   out_dir, registry, args)
            if record is not None:
                records.append(record)
    elif args.lane == "b":
        for index in range(args.count):
            record = render_lane_b(endpoint, args.race, info, rng, index, args.seed + index,
                                   out_dir, args, registry)
            if record is not None:
                records.append(record)
    else:
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
            record = {"index": index, "file": target.name, "seed": seed, "variation": _json_safe(pick),
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
    if args.lane == "a":
        passed = sum(1 for r in records if r["gate"]["skin"]["gate"] == "WROUGHT")
    else:
        passed = sum(1 for r in records if r["gate"] == "WROUGHT")
    summary.write_text(json.dumps({"race": args.race, "count": len(records),
                                   "gate_pass": passed, "records": records}, indent=2),
                       encoding="utf-8")
    print(f"\n{args.race}: {passed}/{len(records)} pass the gate (owner judgement is what counts)")
    print(f"wrote {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
