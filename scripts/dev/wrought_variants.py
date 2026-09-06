"""The variation vocabulary a Wrought race batch draws from.

WHAT IS AUTHORED HERE AND WHAT IS READ. The engine already owns culture -- ethos, material logic,
ornament rule, surface bias, palette -- in `assets/content/cultures/<race>.ron`, and the generator
reads those rather than restating them. What the engine does NOT own is race PHYSICALITY: the
culture files describe how a people build and decorate, never how they look, and the race-pack
schema v2 carries `face` as an explicit parked null (R10). So everything below is AUTHORED, is a
first draft, and is meant to be corrected by the owner rather than trusted.

It lives here rather than in SpellBound because it is prompt vocabulary for generation, which is
SpellVision's half of the split. When R10 unparks, physiology and face belong in the race pack and
this module should read them instead of holding them.

THE APPEARANCE AXIS HAS A FLOOR, AND IT IS DELIBERATE. Owner rule: every race must include beautiful
women, and "ugly" means ORDINARY -- plain, unremarkable, weathered -- never hideous or deformed.
That is not squeamishness, it is the Look Matrix: "idealization WITHIN human measurement", and its
negative list already forbids "no racial feature that degrades". A generator that reaches for
grotesque when asked for unattractive produces a cast that reads as caricature, and for the
non-human races it reads as something worse. So the axis runs striking -> handsome -> ordinary ->
weathered, it stops there, and `deformed`/`grotesque`/`hideous` sit in the negative prompt.

WEIGHTS, NOT UNIFORM CHOICE. A hundred frames drawn uniformly across four appearance tiers gives
twenty-five plain faces per race whether or not that serves the dataset. The weights below put real
mass on the striking end because the owner asked for it explicitly, while keeping ordinary faces
common enough that the race does not read as a modelling agency.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import sys
from pathlib import Path

import wrought_hair
import wrought_wardrobe

# --- race physicality, sexed ------------------------------------------------------------------
#
# GROUNDED IN D&D 5e, then tweaked. 5e is the shared reference a reader already carries, so a race
# that matches it reads instantly; the tweaks are where this world differs. Each race is a `core`
# both sexes share plus a `male` and `female` expression, because sex is not a modifier applied
# after the fact -- it is part of how the race is built.
#
# CORRECTED: beastfolk previously read "an animal head with expressive eyes". The owner's rule, in
# BOTH PICK.md and README.md, is the opposite -- "kemonomimi (human face + ears/horns), NO ANIMAL
# HEADS". That one line would have spoiled every beastfolk frame.

# THE INVARIANT, applied to every female subject, in every race, at every build.
#
# The failure it exists to prevent: ask a diffusion model for a muscular, broad, stocky female of a
# strong race and it drifts to male morphology and adds breasts -- "a slimmer orc man with breasts".
# Sexual dimorphism collapses under mass, because the training mass for "broad and muscular" is male.
#
# So the feminine read is carried by STRUCTURE, which does not vary with build, rather than by size,
# which does. Build changes how much of her there is; it never changes whether she reads as a woman.
# And "soft" means a fat layer over the muscle, not fragility -- she is obviously capable of
# fighting. Soft, not delicate.
# RULING 2 2026-09-06 (coordinator): the FACE words restored in the prior ruling (rounded jaw,
# soft brow, full lips, large eyes) duplicated face_bundle_for's own JAW/BROW/LIPS/EYE_SHAPE draw --
# measured live ("a rounded jaw" landing twice in the same prompt). face_bundle_for owns the face
# now, one owner per feature; this sentence goes back to body structure only, plus the unelaborated
# marker "feminine facial structure" (the fact that the face reads as female, not what shape it is).
# FEMININE_BODY stays folded in (Ruling 1) -- it was always a strict subset of this sentence.
FEMININE_READ = (
    "unmistakably female, feminine facial structure, a defined waist above wide hips, hips "
    "broader than the ribcage, full bust, a soft layer over the muscle, smooth neck and "
    "shoulders without heavy trapezius bulk"
)
# The same rule stated where it binds. Every female frame carries these negatives.
FEMININE_NEGATIVE = (
    "masculine face, male jawline, square heavy jaw, heavy brow ridge, flat chest, "
    "a man with breasts, androgynous, male body with female features, thick masculine neck, "
    "straight waistless torso"
)

# The race's own signature feature, expressed differently by sex. Owner rule, generalised from
# "female orcs should have smaller tusks": whatever marks the race should also mark the sex, wherever
# the race has such a feature. It works in a portrait crop, where body proportion does not.
DIMORPHISM: dict[str, dict[str, str]] = {
    # LESSONS_ORC: "Small tusks collapse to a white lip cut. Prompt 3D ivory tusks past the lip."
    # "Smaller, finer" alone reproduced the collapse -- the suit pass rendered no tusk at all.
    "orc":        {"woman": "small but clearly three-dimensional ivory lower tusks rising past "
                            "the lip, finer than an orc man's",
                   "man": "large heavy tusks"},
    "goblin":     {"woman": "smaller, neater teeth and shorter ears than the men",
                   "man": "longer ears and more prominent teeth"},
    "dwarf":      {"woman": "no beard, hair braided at the temples with metal rings",
                   "man": "a full beard, worked and braided"},
    "dragonborn": {"woman": "finer scales and smaller, more swept-back horns than a male's",
                   "man": "coarser heavier scales and thick blunt horns"},
    "beastfolk":  {"woman": "smaller, more delicate ears than the men", "man": "larger ears"},
    "high_elf":   {"woman": "finer, more sharply swept ears", "man": "heavier jaw and brow"},
    "wood_elf":   {"woman": "finer ears", "man": "a squarer jaw"},
    "dark_elf":   {"woman": "finer ears and a softer chin", "man": "a harder angular jaw"},
    "human":      {"woman": "", "man": ""},
}

# For races whose FACE IS NOT HUMAN, the feminine read has to be spoken in their own anatomy.
# FEMININE_READ names a rounded jawline, soft brow and full lips -- human features. Applied to a
# dragonborn it laid a human face onto a draconic head, which is exactly the "human face on what
# would otherwise be a bipedal dragon" the owner rejected. Body dimorphism still applies; only the
# facial half is replaced.
FEMININE_FACE_OVERRIDE: dict[str, str] = {
    # Deliberately does NOT describe a head -- HEAD_VARIANTS does that, and a second description
    # would be the same three-places problem returning. This says only how the chosen head reads as
    # female: finer, softer-browed, larger-eyed, and under no circumstances human.
    "dragonborn": ("that head in its feminine form, finer and more delicate than a male's, larger "
                   "expressive eyes, a softer brow ridge, a slimmer neck, "
                   "no human facial features of any kind"),
}

MASCULINE_READ = (
    "unmistakably male, heavier brow and squarer jaw, broader through the shoulders than the hips, "
    "thicker neck"
)



# --- lineage: the colour a race inherits rather than draws at random ---------------------------
#
# The dragonborn core said "draconic scales in bronze slate green or dull red" -- one smeared
# average of several lineages, so every frame came out the same muddy green-bronze and a red or a
# blue dragonborn could not be asked for at all. 5e has ten draconic ancestries and they are the
# race's most legible variation axis: a black dragonborn and a white one read as the same people and
# obviously different bloodlines, which is exactly what a race pack wants.
#
# Held per RACE rather than as a bare dragonborn constant, because "an inherited colour that comes
# with matching eyes and horn" is not a dragonborn idea -- beastfolk pelts and tiefling infernal
# lines want the same shape, and a second table for each is how the head ended up described three
# times.
#
# COLOUR LAW APPLIES. Look Matrix section 4 caps skin saturation at 0.45, so these are stated dark
# and muted -- oxblood rather than fire-engine, slate rather than sky. The lineage is legible
# through hue and value, not through saturation, which is also what makes them read as animals
# instead of as toys.
LINEAGE: dict[str, dict[str, str]] = {
    "dragonborn": {
        # The five chromatics.
        "black": ("black dragon ancestry, matte charcoal-black scales with a faint oily green sheen "
                  "along the ridges, deep green eyes, black horns and claws"),
        "blue": ("blue dragon ancestry, deep slate-blue scales paling to blue-grey at the throat "
                 "and belly, pale gold eyes, dark blue-grey ridged horns"),
        "green": ("green dragon ancestry, dull olive and moss-green scales darkening along the "
                  "spine, amber-gold eyes, dark horn"),
        "red": ("red dragon ancestry, deep oxblood-red scales darkening to near-black at the ridges "
                "and brightening at the throat, burning amber eyes, black horns and claws"),
        # Both pale lineages failed the gate on gloss (0.0993 / 0.0875 against 0.045): a pale scale
        # under a hard key blows the specular. Stated matte in their own text rather than loosening
        # the rule for everyone.
        "white": ("white dragon ancestry, pale bone-white and cold grey matte scales with no shine, "
                  "ice-blue eyes, pale translucent horns"),
        # The five metallics.
        "brass": ("brass dragon ancestry, warm dull brass scales gone green at the edges with age, "
                  "dark amber eyes, weathered horn"),
        "bronze": ("bronze dragon ancestry, dark bronze scales with a verdigris cast at the joints, "
                   "gold eyes, dark ridged horns"),
        "copper": ("copper dragon ancestry, dull copper-red scales with green patina in the seams, "
                   "blue-green eyes, dark horn"),
        "gold": ("gold dragon ancestry, muted old-gold scales, deep gold eyes, pale gold horns"),
        "silver": ("silver dragon ancestry, pale pewter-silver matte scales, dull and unpolished, "
                   "pale grey eyes, white-grey horns"),
    },
}


def lineage_for(race: str, rng: random.Random, choice: str | None = None) -> str:
    """The subject's inherited colour, or nothing for a race that does not inherit one."""
    table = LINEAGE.get(race)
    if not table:
        return ""
    if choice:
        return table.get(choice, "")
    return table[rng.choice(sorted(table))]


# --- subspecies: beastfolk are six peoples, not one ------------------------------------------
#
# The night run's beastfolk core said "animal ears ... sometimes small horns" and named no animal, so
# the model filled fox and wolf and rolled horns on 5 of 12 (Jarvis vision, 2026-09-05). Owner's
# ruling the same evening: leopard, bear, lion, deer, panda, wolf to start; "small antlers on the
# female deer, no horns on the other 5". Kemonomimi throughout -- a human face and ONLY the animal
# ear pair, no human ear pair, which is the wording of the owner's own bear lock (W5, 21 Aug:
# "ONLY a pair of round tan bear ears on top of the head ... smooth warm brown skin, no body fur").
# So bear and panda carry no body marks at all; the others carry a skin PATTERN at the forearms and
# shoulders, never fur coverage. Hair is human hair (the fur-hair branch is gone).
SUBSPECIES: dict[str, dict[str, dict[str, str]]] = {
    "beastfolk": {
        "leopard": {"ears": "tall rounded leopard ears, black-tipped", "tail": "a long ringed leopard tail",
                    "marks": "leopard rosettes patterning the skin of the forearms and shoulders",
                    "hair_colours": "warm black, dark tawny, dark brown", "headgear": ""},
        "bear":    {"ears": "small round tan bear ears", "tail": "a short stub tail",
                    "marks": "", "hair_colours": "dark brown, black, chestnut", "headgear": ""},
        "lion":    {"ears": "broad rounded lion ears", "tail": "a tawny lion tail with a tufted tip",
                    "marks": "a warm tawny cast to the skin of the forearms and shoulders",
                    "hair_colours": "golden, tawny, dark gold", "headgear": ""},
        "deer":    {"ears": "tall narrow deer ears, fawn-lined", "tail": "a short white-tipped deer tail",
                    "marks": "dappled fawn spots across the shoulders",
                    "hair_colours": "light brown, fawn, chestnut", "headgear": "small antlers"},
        "panda":   {"ears": "round black panda ears", "tail": "a short black-tipped tail",
                    "marks": "", "hair_colours": "black, black with white streaks", "headgear": ""},
        "wolf":    {"ears": "tall pointed wolf ears, black-tipped", "tail": "a bushy grey-black wolf tail",
                    "marks": "grey-black mottled markings on the skin of the forearms",
                    "hair_colours": "grey, silver-grey, black", "headgear": ""},
    },
}


def subspecies_for(race: str, rng: random.Random, choice: str | None = None) -> tuple[str, str]:
    """(name, clause). The clause owns ears, tail, marks and headgear -- one owner per feature."""
    table = SUBSPECIES.get(race)
    if not table:
        return "", ""
    name = choice or rng.choice(sorted(table))
    row = table[name]
    parts = [f"a {name} beastfolk", "a human face",
             f"only the pair of {row['ears']} on top of the head, no human ear pair",
             row["tail"], row["marks"],
             row["headgear"] if row["headgear"] else "no horns, the crown of the head bare between the ears"]
    return name, ", ".join(p for p in parts if p)


# --- heads that are a genuine design fork ------------------------------------------------------
#
# Dragonborn had its head described in THREE places -- `core` ("a blunt draconic snout, heavy brow
# ridges and swept-back horns"), `female` ("a fully draconic head with a tapered feminine muzzle")
# and FEMININE_FACE_OVERRIDE -- so a variant would have had to out-argue two other descriptions
# rather than replace one. That is why the fork could not be shown as options: it was not a
# parameter, it was three constants agreeing with each other.
#
# Pulled into one table, the head becomes swappable and the question becomes answerable. The texts
# are SEX-NEUTRAL head architecture; femininity arrives through DIMORPHISM (finer scales, smaller
# horns) and FEMININE_READ, which is the same split every other race already uses.
HEAD_VARIANTS: dict[str, dict[str, str]] = {
    "dragonborn": {
        # E -- THE OWNER'S REFERENCE, and now the default. A HUMAN face carrying draconic features
        # rather than a dragon's head: scales arriving as a skin treatment at the temples and jaw and
        # running down the neck, horns above the ears, long ears, slit pupils in an otherwise human
        # eye, ordinary hair. The scale and the claw go to the LIMBS, which is where the reference
        # puts them.
        #
        # This is not a fifth taste; it is the world's stated rule, which dragonborn was wrongly
        # exempted from. PICK.md and README.md both say "kemonomimi (human face + ears/horns), NO
        # ANIMAL HEADS" -- for the world, not for beastfolk. The owner's "there's a human face on
        # what would otherwise be a bipedal dragon" was a complaint about a BADLY EXECUTED hybrid,
        # and it was read here as an instruction to abandon hybridisation. Four fully draconic heads
        # came out of that misreading; they stay in the table as alternates because they are
        # authored and the fork is now on the record, but they are no longer what the race is.
        # Scale placement moved to SKIN_SCALE_PLACEMENT (2026-09-05) -- this sentence duplicated it
        # and the two disagreed on where the scales thinned and thickened.
        # RULING 2 2026-09-06 (coordinator): said "human face" and "no muzzle" three ways each --
        # trimmed to one statement of each fact, <=32 words, same content.
        "kemonomimi": (
            "a human face with human nose and mouth, draconic features added rather than "
            "replacing, no muzzle, long ridged horns above the ears sweeping back, long pointed "
            "ears, slit-pupil eyes, ordinary human hair"),
        # A -- the current baseline. A true dragon's head, feminine only in fineness.
        "draconic": ("a fully draconic head, a tapered scaled muzzle with the nostrils at its tip, "
                     "a heavy scaled brow ridge over slit-pupil eyes, swept-back horns rising from "
                     "the skull, no external ears, no lips, a scaled throat running into the neck"),
        # B -- the muzzle shortened until the face has frontal presence. Still entirely reptilian;
        # what changes is that the eyes read before the snout does.
        "short_muzzle": ("a short blunt draconic muzzle barely longer than the jaw, a broad frontal "
                         "face, large forward-facing slit-pupil eyes set wide beneath a smooth "
                         "scaled brow, small swept-back horns, fine scales, no external ears, "
                         "expressive but wholly reptilian"),
        # C -- humanlike PROPORTION with wholly reptilian FEATURES. The boundary case: the thing the
        # owner rejected was a human face on a dragon, and this tests whether the objection was to
        # the proportions or to the features.
        "flat_faced": ("no muzzle at all, a flat scaled face on humanlike proportions, a low "
                       "draconic nose ridge where a snout would be, large slit-pupil eyes, a "
                       "scaled brow and cheek plates, a lipless mouth, swept-back horns, "
                       "no external ears, no human features, a scaled humanoid rather than a "
                       "dragon-headed one"),
        # D -- feminine through ornament and line rather than through softening the head. A long
        # neck and a display crest do the work a rounded jaw does on a human face.
        "crested": ("a fully draconic head carried on a long elegant neck, a slender tapered muzzle, "
                    "a fanned membranous crest sweeping back from the skull in place of hair, "
                    "fine iridescent scales across the cheek and throat, large luminous slit-pupil "
                    "eyes, slim curving horns following the crest, no external ears"),
    },
}
# The variant used when none is named -- so the default path renders exactly what it rendered
# before this table existed.
HEAD_DEFAULT: dict[str, str] = {"dragonborn": "kemonomimi"}


# Heads whose face is HUMAN. A kemonomimi head takes ordinary hair and the ordinary FEMININE_READ
# for the same reason every humanoid race does: there is no non-human face for either to fail on.
# The fully draconic alternates keep the horn crest and the draconic feminine read.
KEMONOMIMI_HEADS: dict[str, set[str]] = {"dragonborn": {"kemonomimi"}}


def is_kemonomimi(race: str, variant: str | None = None) -> bool:
    return (variant or HEAD_DEFAULT.get(race, "")) in KEMONOMIMI_HEADS.get(race, set())


def head_for(race: str, variant: str | None = None) -> str:
    """The race's head, if its head is a fork. Empty for races whose head is not in question."""
    table = HEAD_VARIANTS.get(race)
    if not table:
        return ""
    return table.get(variant or HEAD_DEFAULT.get(race, ""), "")


RACE_PHYSIOLOGY: dict[str, dict[str, str]] = {
    "orc": {
        # 5e: tall, powerfully built, greyish-green skin, jutting jaw with prominent lower tusks,
        # sloping forehead, pointed ears.
        "core": "lower tusks, a strong jaw, sloping brow, pointed ears, "
                "tall and powerfully built",
        "male": "heavy slab muscle, thick neck, broad flat chest",
        # The tweak: strength AND femininity together, never one bought with the other.
        # RULING 2026-09-06: stripped the waist/hips/bust restatement of FEMININE_READ -- kept the
        # one race-specific word: heavy muscle under a soft layer.
        "female": "heavy muscle under a soft layer",
    },
    "goblin": {
        # 5e: small, flat faces, broad noses, pointed ears, wide mouths, small sharp teeth.
        # GOBLIN_10 r3 lesson: "full body, adult head-to-body ratio, not a doll / giant head".
        "core": "small and wiry, a broad nose, long "
                "pointed ears, a wide mouth with small sharp teeth, "
                "adult head-to-body proportion, not a doll",
        "male": "sinewy and angular, sharp featured",
        # RULING 2026-09-06: stripped the waist restatement of FEMININE_READ -- kept the two
        # race-specific words: a small delicate face, a small nose.
        "female": "a small delicate face, a small nose",
    },
    "dwarf": {
        # 5e: 4-5 ft, as heavy as a human, ruddy or deep brown skin, thick hair.
        # Breadth-versus-height language did nothing: both suit frames rendered a normal human
        # head-count. Proportion is stated the way figure drawing states it -- in heads -- because
        # that is the only phrasing that has moved a diffusion prior on proportion.
        "core": "short and dense, about four and a half feet tall but as heavy as a tall human, "
                "stocky proportions of about five and a half heads tall, short limbs against a long "
                "deep torso, strong brows, a strong nose, thick hair",
        "male": "barrel-chested, heavily bearded, thick through the neck and forearms",
        # RULING 2026-09-06: stripped the waist/bust restatement of FEMININE_READ -- kept the three
        # race-specific words: breadth, heavy brow, strong nose.
        "female": "extremely broad for her height, a heavy brow, a strong nose",
    },
    "human": {
        "core": "the full human range of height, build and features",
        "male": "the full male human range",
        "female": "the full female human range, feminine proportion at every build",
    },
    "high_elf": {
        # 5e: slender, fine-boned, pointed ears, no facial or body hair, otherworldly poise.
        "core": "tall and slender, fine-boned, long swept-back pointed ears, high cheekbones, "
                "smooth hairless skin, an upright unhurried carriage",
        "male": "lean and flat-planed through the chest, a defined jaw",
        # RULING 2026-09-06: stripped the waist restatement of FEMININE_READ (and "large eyes",
        # now stated there too) -- kept the race-specific word: fine-boned, never boyish.
        "female": "fine-boned but never boyish",
    },
    "wood_elf": {
        # 5e: coppery skin, green/brown/hazel hair and eyes, wiry and quick.
        "core": "trim and athletic, pointed ears",
        "male": "sinewy, weathered, close-cut or bound hair",
        # RULING 2026-09-06: stripped the waist restatement of FEMININE_READ -- kept the two
        # race-specific words: full cheeks, never gaunt.
        "female": "full cheeks, never gaunt",
    },
    "dark_elf": {
        # 5e drow: obsidian to dusky grey skin, stark white or pale hair, pale eyes, slighter build.
        # Vision Bible row 1: "Pupil-less luminous eyes; long pointed ears; cool obsidian/violet/
        # gray skin."
        "core": "long pointed ears, slighter and finer than surface elves, eyes that carry against "
                "the dark skin",
        "male": "lean and close-muscled, sharp featured",
        # RULING 2026-09-06: stripped the waist restatement of FEMININE_READ (and "full lips, large
        # eyes", now stated there too) -- kept the race-specific words: young and smooth-skinned,
        # never severe.
        "female": "young and smooth-skinned, never severe",
    },
    "dragonborn": {
        # 5e: 6ft+, ~250 lb, scaled hide, blunt snout, brow ridges and horns, clawed hands, no ears.
        # Placement of the scale pattern moved to SKIN_SCALE_PLACEMENT -- one owner for where the
        # scales sit, not this core AND the skin clause disagreeing on it (2026-09-05).
        "core": "tall and strong, well over six feet, clawed hands, a heavy tail",
        "male": "massive through the chest and shoulders",
        # RULING 2026-09-06: stripped "powerfully built but visibly female" (FEMININE_READ already
        # says "unmistakably female") -- kept the two race-specific words: fine smooth scales, a
        # slimmer neck.
        "female": "fine smooth scales, a slimmer neck",
    },
    "beastfolk": {
        # Kemonomimi. Ears, tail, marks and headgear are owned by SUBSPECIES -- the core says only
        # what every subspecies shares, so the two never disagree.
        "core": "a human face, human skin, no animal head and no muzzle",
        "male": "broad and heavily built",
        # RULING 2026-09-06: stripped the waist/bust restatement of FEMININE_READ -- kept the one
        # race-specific phrase: a soft human face framed by the ears.
        "female": "a soft human face framed by the ears",
    },
}


def physiology_for(race: str, sex: str, head: str | None = None) -> str:
    """The race's shared core, this sex's expression, its dimorphism marker, and the invariant.

    `head` selects from HEAD_VARIANTS for the races whose head is a design fork; it is ignored for
    every race whose head is settled, so callers never have to know which is which.
    """
    entry = RACE_PHYSIOLOGY.get(race, {})
    parts = [entry.get("core", ""), head_for(race, head),
             entry.get("female" if sex == "woman" else "male", "")]
    parts.append(DIMORPHISM.get(race, {}).get(sex, ""))
    if sex == "woman":
        # Non-human faces take the feminine read in their own anatomy; everyone else takes the
        # human one. FEMININE_BODY is gone (ruling 2026-09-06, folded into FEMININE_READ, which was
        # always a superset of it) -- the draconic-alternate branch now appends FEMININE_READ too.
        # RESOLVED (Ruling 2 2026-09-06): FEMININE_READ carries body structure only now -- the face
        # is owned by face_bundle_for, one owner per feature -- so the draconic override no longer
        # argues with it; FEMININE_FACE_OVERRIDE's "no human facial features of any kind" stands
        # unopposed.
        if FEMININE_FACE_OVERRIDE.get(race) and not is_kemonomimi(race, head):
            parts.append(FEMININE_FACE_OVERRIDE[race])
            parts.append(FEMININE_READ)
        else:
            parts.append(FEMININE_READ)
    else:
        parts.append(MASCULINE_READ)
    return ", ".join(p for p in parts if p)



# --- identity: the face changes from frame to frame -----------------------------------------
#
# ORC NIGHT BATCH, 100 FRAMES, ONE WOMAN. Same face, same dark hair, same olive skin -- the model's
# single prior for "orc woman" filled every slot the prompt left open. LESSONS_ORC already lists
# "face identity still generic across a set" as open. For a STYLE LoRA this is worse than a
# cosmetic: a hundred plates of one face teach the trigger that the face is part of the style.
#
# So skin, hair colour and eye colour are DRAWN, per race, from the Vision Bible's own ranges where
# it gives them (orc "olive/forest/slate", drow "obsidian/violet/gray", goblin "amber/gold/green
# eyes") and 5e where it does not. Every range that a race core used to state in prose ("coppery or
# warm brown skin") moves here, and the core stops naming it -- the same one-owner-clause rule as
# crest/hair and lineage/eyes. Face shape and nose moved on (Task 5) to `face_bundle_for` -- the
# whole face, jaw and nose bridge included, has one owner now instead of identity_for and the old
# beauty-tier adjectives disagreeing about it.
#
# Races whose colour is owned elsewhere keep that owner: dragonborn eyes and scale colour belong to
# LINEAGE -- the skin tone is drawn here, as a sentence that LEADS the lineage clause (one owner for
# the skin, one for the scale colour, order rather than a second description doing the separating);
# dark-elf eyes are pupil-less and luminous by the Bible and vary only in their glow.
SKIN_BY_RACE: dict[str, list[str]] = {
    "orc": ["olive-green skin", "forest-green skin", "grey-green slate skin", "deep green skin"],
    "goblin": ["dull olive-yellow skin", "sallow grey-green skin", "mossy green skin",
               "pale yellow-green skin"],
    "dwarf": ["ruddy skin", "deep brown skin", "pale freckled skin", "warm tan skin"],
    "human": ["pale skin", "fair freckled skin", "olive skin", "warm brown skin", "deep brown skin",
              "golden tan skin"],
    "high_elf": ["pale porcelain skin", "pale golden skin", "light olive skin", "warm ivory skin"],
    "wood_elf": ["coppery skin", "warm brown skin", "tan olive skin", "deep copper skin"],
    "dark_elf": ["obsidian-black skin with a violet cast", "dusky grey skin", "cool violet-grey skin",
                 "deep slate skin"],
    # THE SKIN CLAUSE OWNS THE WHOLE SKIN. Records vs readings, 2026-09-05: prompts drew tan / olive /
    # deep brown on 70 of 100 dragonborn, Jarvis read the face as pale on 12 of 12 sampled -- the
    # trailing "human skin at the face" lost to the lineage scale sentence. Stated first, as a
    # sentence about THE SKIN, with the scales as a pattern ON it at named places. Gender-neutral --
    # fix round 1, 2026-09-05: "her skin is" rendered on a man draw too, because every axis clause in
    # this module is sex-agnostic text and sex arrives only through DIMORPHISM/FEMININE_READ/etc.
    "dragonborn": ["the skin is warm tan", "the skin is olive", "the skin is pale",
                   "the skin is deep brown", "the skin is golden brown", "the skin is dark umber"],
    "beastfolk": ["warm tan skin", "olive skin", "pale skin", "brown skin"],
}
# RULING 2 2026-09-06 (coordinator): trimmed from 31 to <=22 words, same six facts (temples,
# jaw, neck, forearms, backs of the hands, nowhere on the clothing).
SKIN_SCALE_PLACEMENT = ("the scales are a pattern on that skin: temples, jaw, neck, forearms, "
                        "backs of the hands, nowhere on the clothing")
# The owner's two Grok references (2026-09-05) exist to show exactly this: scales on the SKIN, the
# armour plain. Stated positively -- a negative prunes, only the positive builds.
# RULING 2 2026-09-06 (coordinator): trimmed from 29 to <=22 words, same facts (plain leather
# and cloth, visible stitching, matte, no scale pattern or texture, no lacquer on the clothing).
DRAGONBORN_GARMENT = ("the garment is plain worked leather and woven cloth, visible stitching, "
                      "matte, no scale pattern or texture, no lacquer on the clothing")
HAIR_COLOUR_BY_RACE: dict[str, list[str]] = {
    "orc": ["black", "dark brown", "auburn", "black with grey streaks"],
    "goblin": ["black", "dark rust-brown", "ash-brown", "green-black"],
    "dwarf": ["red", "auburn", "black", "dark brown", "blonde", "grey-streaked brown"],
    "human": ["black", "dark brown", "brown", "auburn", "blonde", "red", "dark blonde"],
    "high_elf": ["platinum blonde", "silver-white", "gold", "black", "chestnut"],
    "wood_elf": ["dark brown", "auburn", "black", "chestnut", "dark red"],
    "dark_elf": ["stark white", "silver", "pale ash", "white with a lavender cast"],
    "dragonborn": ["black", "dark brown", "auburn", "dark red"],
}
EYES_BY_RACE: dict[str, list[str]] = {
    "orc": ["amber eyes", "dark brown eyes", "hazel eyes", "gold eyes"],
    "goblin": ["large amber eyes", "large gold eyes", "large green eyes", "large yellow eyes"],
    "dwarf": ["dark brown eyes", "grey eyes", "hazel eyes", "blue eyes"],
    "human": ["brown eyes", "dark brown eyes", "hazel eyes", "green eyes", "grey eyes", "blue eyes"],
    "high_elf": ["pale grey eyes", "green eyes", "gold eyes", "violet eyes", "blue eyes"],
    "wood_elf": ["green eyes", "hazel eyes", "brown eyes", "amber eyes"],
    "dark_elf": ["pupil-less luminous lavender eyes", "pupil-less luminous white eyes",
                 "pupil-less luminous pale gold eyes", "pupil-less luminous ice-blue eyes"],
    "dragonborn": [],   # LINEAGE owns the eyes
    "beastfolk": ["amber eyes", "gold eyes", "green eyes", "grey eyes"],
}


def identity_for(race: str, rng: random.Random, hair_colours: str | None = None,
                  skins: list[str] | None = None) -> dict[str, str]:
    """Skin, eyes, and a hair colour for the hair axis to wear.

    `skins` overrides `SKIN_BY_RACE` when given -- the drawn nation's own skin family, so a
    character's skin comes from the people they are from rather than the race as a whole. Face
    shape and nose used to be drawn here; the face bundle (`face_bundle_for`) now owns the whole
    face, jaw and nose bridge included, so there is one owner instead of two disagreeing.
    """
    colours = ([c.strip() for c in hair_colours.split(",")] if hair_colours
               else HAIR_COLOUR_BY_RACE.get(race, HAIR_COLOUR_BY_RACE["human"]))
    return {
        "skin": rng.choice(skins if skins else SKIN_BY_RACE.get(race, SKIN_BY_RACE["human"])),
        "eyes": rng.choice(EYES_BY_RACE[race]) if EYES_BY_RACE.get(race) else "",
        "hair_colour": rng.choice(colours),
    }


# --- nations: skin diversity is a people, not a dice roll ------------------------------------
#
# Owner, 2026-09-05: "We need to make sure there is diversity in skin color which shows different
# nationalities. There are multiple orc clans, humans, etc. ... there should be no character that
# looks like another." Names are REGION PLACEHOLDERS until the owner names them ("region
# placeholders until I name them"). Skin families come from the Bible's own ranges (orc "olive green,
# forest green, dark brown, gray-green, slate"; goblin "green, olive, chartreuse, sickly yellow-green,
# grayish-green"; drow "obsidian black, smoky gray, deep violet, midnight blue"; human "all human
# tones", three kingdoms per human.ron), 5e where the Bible is silent (dwarf, elves). The marker is
# the clan's biography worn on the body -- Bible: orc "ritual tattoo-ink", goblin "clan-dyed" hair
# and ear shape "depending on clan", beastfolk "clan-marks ... worn in the hair and on the body".
# A None row is TBD(owner): it is listed so the slot is visible, drawn never, and warned about once.
NATIONS: dict[str, dict[str, dict | None]] = {
    "orc": {
        "highland": {"skin": ["olive-green skin", "grey-green slate skin"], "hair_texture": "coarse and thick",
                     "marker": "white warpaint streaks through the braids", "dialect": "vernacular"},
        "lowland": {"skin": ["forest-green skin", "deep green skin"], "hair_texture": "coarse, straight",
                    "marker": "red ritual tattoo-ink lines along the forearms", "dialect": "vernacular"},
        "coastal": {"skin": ["dark brown skin with a green cast", "slate-grey skin"], "hair_texture": "coarse, wavy",
                    "marker": "bony ridges along the brow and shoulders", "dialect": "romanesque"},
    },
    "goblin": {
        "warren": {"skin": ["mossy green skin", "grey-green skin"], "hair_texture": "wiry",
                   "marker": "ears ragged at the edges, clan-dyed teal streaks in the hair", "dialect": "vernacular"},
        "scrapyard": {"skin": ["dull olive-yellow skin", "chartreuse skin"], "hair_texture": "coarse and spiky",
                      "marker": "sharply spiked ears, bright pink clan dye in the hair", "dialect": "vernacular"},
        "marsh": {"skin": ["sallow yellow-green skin", "pale grey-green skin"], "hair_texture": "wiry, fine",
                  "marker": "floppy ears and faint bioluminescent freckles across the cheeks", "dialect": "organic"},
    },
    "dwarf": {
        "deephold": {"skin": ["ruddy skin", "pale freckled skin"], "hair_texture": "thick and straight",
                     "marker": "temple braids bound in iron rings", "dialect": "romanesque"},
        "foothill": {"skin": ["warm tan skin", "olive skin"], "hair_texture": "thick and wavy",
                     "marker": "a maker's mark tattooed on the back of each hand", "dialect": "tudor"},
        "ashvault": {"skin": ["deep brown skin", "dark umber skin"], "hair_texture": "thick and coiled",
                     "marker": "beads of cut stone threaded through the hair", "dialect": "romanesque"},
    },
    "human": {
        "monarchy": {"skin": ["pale skin", "fair freckled skin", "olive skin", "warm brown skin"],
                     "hair_texture": "straight or wavy", "marker": "a deep blue and gold ribbon at the collar",
                     "dialect": "gothic"},
        "parliament": {"skin": ["olive skin", "golden tan skin", "deep brown skin", "pale skin"],
                       "hair_texture": "wavy or curly", "marker": "a pewter guild pin on green cloth",
                       "dialect": "tudor"},
        "republic": {"skin": ["warm brown skin", "deep brown skin", "golden tan skin", "fair skin"],
                     "hair_texture": "coiled or curly", "marker": "a red and white sash at the waist",
                     "dialect": "vernacular"},
    },
    "high_elf": {
        "citadel": {"skin": ["pale porcelain skin", "warm ivory skin"], "hair_texture": "fine and straight",
                    "marker": "a thin silver circlet", "dialect": "gothic"},
        "coast": {"skin": ["pale golden skin", "light olive skin"], "hair_texture": "fine and wavy",
                  "marker": "a single rune inked at the wrist", "dialect": "italianate"},
        "TBD_owner_3": None,
    },
    "wood_elf": {
        "greenwood": {"skin": ["coppery skin", "tan olive skin"], "hair_texture": "thick and wavy",
                      "marker": "leaf-green dye at the tips of the hair", "dialect": "vernacular"},
        "highcanopy": {"skin": ["warm brown skin", "deep copper skin"], "hair_texture": "thick and coiled",
                       "marker": "a bark-brown tattoo band around the upper arm", "dialect": "organic"},
        "TBD_owner_3": None,
    },
    "dark_elf": {
        "undercity": {"skin": ["obsidian-black skin with a violet cast", "deep slate skin"],
                      "hair_texture": "silky and straight", "marker": "a crescent ornament in the hair",
                      "dialect": "gothic"},
        "deepmarch": {"skin": ["dusky grey skin", "cool violet-grey skin", "midnight-blue skin"],
                      "hair_texture": "silky and gently wavy", "marker": "faint glowing rune-lines at the collarbone",
                      "dialect": "gothic"},
        "TBD_owner_3": None,
    },
    "dragonborn": {
        # skin is owned by SKIN_BY_RACE["dragonborn"] (the sentence form); a nation only adds a marker.
        "oathhold": {"skin": ["the skin is warm tan", "the skin is deep brown", "the skin is golden brown"],
                     "hair_texture": "thick and straight", "marker": "an oath-mark inked along the forearm",
                     "dialect": "byzantine"},
        "slatecoast": {"skin": ["the skin is pale", "the skin is olive", "the skin is dark umber"],
                       "hair_texture": "thick and wavy", "marker": "a lineage seal on a bronze collar",
                       "dialect": "byzantine"},
        "TBD_owner_3": None,
    },
    "beastfolk": {
        "mixing_lands": {"skin": ["warm tan skin", "olive skin", "brown skin", "pale skin"],
                         "hair_texture": "thick", "marker": "clan beads braided into the hair",
                         "dialect": "vernacular"},
        "forest_pack": {"skin": ["warm brown skin", "deep brown skin", "olive skin"],
                        "hair_texture": "coarse", "marker": "a clan-dye red mark on the cheekbone",
                        "dialect": "organic"},
        "TBD_owner_3": None,
    },
}
_WARNED_TBD: set[str] = set()


def nation_for(race: str, rng: random.Random, choice: str | None = None) -> tuple[str, dict]:
    table = NATIONS.get(race, {})
    worked = {k: r for k, r in table.items() if r}
    if len(worked) < len(table) and race not in _WARNED_TBD:
        _WARNED_TBD.add(race)
        print(f"  [build] {race}: {len(table) - len(worked)} nation slot(s) TBD(owner); drawing from "
              f"{sorted(worked)}", file=sys.stderr)
    name = choice or rng.choice(sorted(worked))
    return name, worked[name]


def identity_key(pick: dict) -> str:
    """One string per character. Two picks with the same key are the same person; a batch refuses that."""
    fields = ("race", "nation", "subspecies", "skin", "hair_colour", "hair_texture", "eyes",
              "face_bundle", "mark")
    return hashlib.sha1("|".join(str(pick.get(f, "")) for f in fields).encode()).hexdigest()[:16]


class IdentityRegistry:
    """Persisted set of identity keys across every batch under one out root."""

    def __init__(self, path: Path):
        self.path = path
        self.keys: dict[str, str] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def seen(self, key: str) -> bool:
        return key in self.keys

    def add(self, key: str, where: str) -> None:
        self.keys[key] = where
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Write through a temp file and rename over the target -- a crash mid-write must not leave
        # a partial/corrupt JSON file for the next __init__ to choke on.
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.keys, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)


# --- the face is structured, not styled ----------------------------------------------------
#
# Jarvis vision, 2026-09-05, 12 frames x 6 races + the 002 plate: "generic_pretty_face" on 52 of
# 72 and "perfect_symmetry" on 61 of 72. The cause was in the prompt: STRIKING and HANDSOME were the
# same sentence on every frame ("smooth clear skin, full cheeks, large bright eyes, full lips,
# elegant even features"), which is a generic-face generator by construction, and the negative
# carried "asymmetric eyes". The tier survives as a WEIGHT over structural choices; the words that
# name a beauty-filter face are banned from every prompt (BANNED_PROMPT_WORDS, tested).
EYE_SHAPE = ["almond eyes", "hooded eyes", "round eyes", "deep-set eyes", "upturned eyes",
             "wide-set eyes", "close-set narrow eyes"]
BROW = ["straight brows", "arched brows", "heavy straight brows", "thin arched brows", "low flat brows"]
LIPS = ["full lips", "a wide mouth with thin lips", "a small full mouth", "a long upper lip",
        "lips with a deep cupid's bow"]
CHEEK = ["high cheekbones", "full round cheeks", "flat wide cheekbones", "hollow-under-the-bone cheeks",
         "soft low cheekbones"]
JAW = ["a rounded jaw", "a narrow tapering jaw", "a soft square jaw", "a long jaw", "a small pointed chin",
       "a strong chin with a cleft"]
NOSE_BRIDGE = ["a low nose bridge", "a high straight bridge", "a slight bump on the bridge",
               "a short upturned nose", "a broad flat bridge", "a long narrow nose"]
ASYMMETRY = ["one brow set a little higher than the other", "a smile that pulls to one side",
             "one eye a fraction narrower than the other", "a nose that leans slightly to one side"]
MARK_FACE = ["a healed nick on the left cheek", "a freckle cluster on the right temple",
             "a crooked front tooth", "a mole under the right eye", "a faint scar through one brow",
             "a chipped tooth", "a small birthmark below the ear", "freckles across the nose bridge"]

# Owner's beauty bell, kept as WEIGHTS over the structural options rather than as adjectives:
# striking narrows the choices toward the flattering end of human measurement (Look Matrix:
# "idealization WITHIN human measurement"), ordinary widens them. Weathered is a men's tier.
TIER_WEIGHTS: dict[str, list[tuple[str, int]]] = {
    "woman": [("striking", 3), ("handsome", 4), ("ordinary", 3)],
    "man": [("striking", 2), ("handsome", 3), ("ordinary", 3), ("weathered", 3)],
}
TIER_REGISTER = {
    "striking": "a face that draws the eye",
    "handsome": "an attractive, open face",
    "ordinary": "a plain, pleasant face",
    "weathered": "a plain face lined by work and weather, but healthy",
}
_STRIKING_EYES = ["almond eyes", "upturned eyes", "wide-set eyes", "round eyes"]
_STRIKING_LIPS = ["full lips", "lips with a deep cupid's bow", "a small full mouth"]
_STRIKING_CHEEK = ["high cheekbones", "full round cheeks"]


def face_bundle_for(rng: random.Random, tier: str) -> tuple[str, str]:
    """(bundle clause, mark). The tier reweights the draw; it never re-words it."""
    eyes = rng.choice(_STRIKING_EYES if tier == "striking" else EYE_SHAPE)
    lips = rng.choice(_STRIKING_LIPS if tier == "striking" else LIPS)
    cheek = rng.choice(_STRIKING_CHEEK if tier == "striking" else CHEEK)
    mark = rng.choice(MARK_FACE)
    bundle = ", ".join([TIER_REGISTER[tier], rng.choice(JAW), cheek, rng.choice(BROW),
                        rng.choice(NOSE_BRIDGE), eyes, lips, rng.choice(ASYMMETRY), mark])
    return bundle, mark


# Look Matrix section 3, the living-skin signal, verbatim in intent: this is what "not waxy" means
# in Wrought, and 002 does it. Stated once, on every frame.
#
# RULING 2026-09-06: trimmed from 45 to <=28 words. The original 170-word PROMPT_WORD_BUDGET was
# written down without measuring WROUGHT_LEAD (76 words, owner-locked) -- 76+35+45 already floors
# above 170 before a single word of subject. The ceiling is now 300 (hard), target 260, and this is
# one of six ordered cuts toward it; see PROMPT_WORD_BUDGET below.
LIVING_SKIN = ("the skin is living tissue: tone deepens into shadow and lightens on lit planes, a "
               "warm undertone at the ears, nose and knuckles, fine mottling, no gloss, no pores")

BANNED_PROMPT_WORDS = ("gorgeous", "flawless", "smooth clear skin", "elegant even features", "perfect",
                       "masterpiece", "8k", "ultra detailed", "hyperrealistic", "airbrushed",
                       "beauty filter", "dslr", "film grain", "kodak", "fujifilm", "f/1.8", "bokeh",
                       "iphone", "snapshot")
# RULING 2026-09-06 (coordinator, superseding the Task-5 guess of 170): 170 never accounted for the
# owner-locked 76-word WROUGHT_LEAD -- LEAD+TAIL+LIVING_SKIN alone floored above it before a single
# word of subject, and the pre-Task-5 tree was already measuring 350-520 words per race. 300 was
# tried next (where the Krea 2 guidance says the encoder's signal stops adding) but even after
# every trim it authorised, EVERY race stayed over it (26-182 words), because the remainder is
# race-defining content the owner asked for today (dragonborn's head/scale/garment/lineage stack,
# beastfolk's subspecies clause, dwarf's proportion-in-heads core) -- cutting it to hit an encoder
# soft ceiling was the wrong trade (RULING 2 2026-09-06). Budget is now 400, still a HARD guard
# (raise on breach), target <=350 on the worst race. Measured per race in the Task 5 commit; the
# tells gate in Tasks 14-15 measures whether length actually dilutes anything. See DIRECTION_V2
# Sec 3 item 7 (amended 2026-09-06).
PROMPT_WORD_BUDGET = 400

# RULING 3 2026-09-06 (coordinator): dragonborn is a structural outlier by design -- four owned
# clauses no other race has -- so the fix is a per-race allowance, not a looser global and not
# cutting the lineage axis.
#
# Dragonborn carries four owned clauses no other race has -- the kemonomimi head, the scale placement,
# the garment rule and the lineage -- and its ceiling measured ~445 over 5000 draws after every trim
# the other races took. An allowance, not a looser global: the other eight stay held at 400.
PROMPT_WORD_ALLOWANCE: dict[str, int] = {"dragonborn": 60}

# RULING 4 2026-09-06 (coordinator): the fully draconic ALTERNATE heads (opt-in via --head) carry
# the alternate head text and FEMININE_FACE_OVERRIDE on top of the four owned blocks -- measured up
# to 471 over 2000 draws. They are authored records, not the race (kemonomimi is what the race is,
# HEAD_DEFAULT), so they take their own allowance rather than loosening the default path.
PROMPT_WORD_ALLOWANCE_ALTERNATE_HEAD = 40


def budget_for(race: str, head: str | None = None) -> int:
    extra = PROMPT_WORD_ALLOWANCE_ALTERNATE_HEAD if (head and race in HEAD_VARIANTS and not is_kemonomimi(race, head)) else 0
    return PROMPT_WORD_BUDGET + PROMPT_WORD_ALLOWANCE.get(race, 0) + extra


def word_count(text: str) -> int:
    return len(text.split())


# Rides the negative on every frame whose appearance tier is not "weathered". The named failures
# are the ones the races actually produced, not hypotheticals.
NOT_HAGGARD = ("gaunt, haggard, emaciated, hollow cheeks, sunken eyes, deeply lined face, "
               "crone, witch-like, sickly, malnourished, elderly")

# What the appearance axis must never reach for. These ride the negative prompt on every frame.
# "asymmetric eyes" is gone -- ASYMMETRY above now states one on every face, on purpose, and this
# negative was fighting the positive it now stands beside.
APPEARANCE_NEGATIVE = ("hideous, grotesque, deformed face, disfigured, monstrous, "
                       "caricature, exaggerated features")

EXPRESSION = ["calm and level", "guarded, watchful", "a faint amused half-smile",
              "open and warm", "tired, thousand-yard", "hard, challenging stare",
              "mid-thought, distracted", "quietly proud"]

# --- hair -------------------------------------------------------------------------------------
#
# Moved to wrought_hair.py (Task 6): texture x length x race style x adornment, per race, instead
# of one generic fifteen-entry list. That list read as "braided" on ~60% of frames because six of
# its fifteen entries were braids; the Bible's per-race style lists and the cultures' adornment
# fix that. `hair_for` below stays the entry point every caller already uses.

# --- clothing ---------------------------------------------------------------------------------
#
# Moved to wrought_wardrobe.py (Task 7): the wardrobe is dialect x register x slots x dye x the
# race's own materials, drawn as an `Outfit` (`draw_outfit`), not a 26-line CLOTHING table with no
# dialect, rank, dye or slot axis -- the night run's table named "leather and fur warrior tunic" on
# most frames of every race. `draw()` below calls `wrought_wardrobe.draw_outfit`; `DIALECTS`,
# `RANKS`, `SLOT_OPTIONS`, `DYE_BY_RANK` and `CONDITION` now live there.


# --- the neutral reference garment ------------------------------------------------------------
#
# WHY A COMPRESSION SUIT IS THE STANDARD, and it is not a stylistic preference: anthropometric
# scanning dresses a subject this way because the garment adds a millimetre at the hip instead of a
# handspan, so the silhouette that comes out IS the body. The 002 finding was the same fact arriving
# as a bug -- THE WARDROBE WAS CARRYING THE SILHOUETTE, a corset cinching the waist and pauldrons
# squaring the shoulders -- which means a race judged in armour is a race judged in its armourer's
# taste. Strip to the suit and what is left is the physiology, which is the thing under review.
#
# NOT the flat-lit measurement pass in `generate_reference_sheet.py::CLEAN_BODY`. That one lights
# the subject evenly, and WROUGHT_NEG forbids exactly that by name ("flat lighting, evenly lit"), so
# a frame lit for measurement would fail the style gate it is being judged against. This keeps the
# Wrought light law untouched and changes ONE axis: the garment. Same reason the reference sheet had
# to drop the plate's "flat lighting" negative -- a prompt written for one purpose fights the next.
SUIT = ("a plain matte dark grey skin-tight full-body compression suit, seamless and unbroken, "
        "no folds, no flare, no loose fabric, no pockets, no belt, no straps, "
        "the garment follows the body exactly like a second skin, barefoot")
SUIT_CONDITION = "clean and unmarked"
# Full body, because a suit pass exists to show proportion and a portrait crop throws proportion
# away. Head to toe is stated three ways because the model cropped feet under a single phrasing.
SUIT_FRAMING = ("full body standing, head to toe, the entire figure visible from head to feet, "
                "both feet fully visible inside the frame, standing straight and square to camera")
# The suit is the axis under test, so everything that could re-clothe her is refused. "nude" and
# "topless" are here because a prompt that removes armour without naming a replacement is read by
# the sampler as an invitation.
SUIT_NEGATIVE = ("armour, armor plates, pauldrons, cloak, cape, coat, robe, dress, skirt, tunic, "
                 "loose clothing, baggy fabric, belt, pouches, straps, harness, jewellery, "
                 "weapons, props, boots, shoes, gloves, nude, topless, bare chest, "
                 "cropped, cut off feet, cut off head, out of frame, close up, portrait crop")


def apply_suit(pick: dict[str, str]) -> dict[str, str]:
    """Swap the wardrobe for the neutral garment and open the framing to full body."""
    pick = dict(pick)
    pick["tier"] = "suit"
    pick["clothing"] = SUIT
    pick["condition"] = SUIT_CONDITION
    pick["framing"] = SUIT_FRAMING
    return pick


# --- everything else worth varying ------------------------------------------------------------
SEX = ["woman", "man"]
# THE BODY BAND IS PER RACE, and one band for everyone is a recorded drift cause.
# RACE_FEMALE_LOOK_LOCK.md, "Why later plates drifted", item 1: "One body for all races. Hunt +
# look-complete used 'hourglass, very full bust, very full hips' on everyone. Bible: Drow is
# slim/lithe; Goblin is 4'2-5'0 compact; Orc is tall/solid; Human varies." The uniform BUILD list
# this replaces made the opposite error in both directions -- "heavy and thick-set" and "soft and
# full-figured" on one end, "slight and narrow" on the other -- and the suit sheet showed exactly
# that: orc and dwarf drew heavy, the elves drew thin. PICK.md's keep rule names both ends as
# failures: "Fit hourglass / Bible body band -- not plus-size dump, not skinny stick."
#
# Bands are the Vision Bible's own words where it has them (Drow, Goblin, Orc, Human). Races the
# Bible does not band take a fit default in the same register.
BUILD_BY_RACE: dict[str, list[str]] = {
    "dark_elf": ["slim and lithe", "elegant and curvy", "athletic, a rogue's build"],
    "goblin": ["compact and slim", "compact and curvy, a short-stack figure", "scrappy and athletic"],
    "orc": ["tall and solid", "warrior athletic", "amazon curvy", "a lean raider's build"],
    "human": ["slim", "average and fit", "curvy", "athletic", "an amazon's build"],
}
BUILD_DEFAULT = ["athletic and balanced", "curvy athletic", "fit hourglass", "strong and full-figured"]
BUILD = sorted({b for v in BUILD_BY_RACE.values() for b in v} | set(BUILD_DEFAULT))


def build_for(race: str, rng: random.Random) -> str:
    return rng.choice(BUILD_BY_RACE.get(race, BUILD_DEFAULT))


# WEIGHTED, because PICK.md's acceptance criterion says "Age ~20-25" and a flat four-way draw put
# half the cast at middle-aged or older. The older tiers stay -- a world of nothing but
# twenty-somethings is its own failure -- but as a tail rather than half the batch.
# PICK.md says "Age ~20-25"; LESSONS_ORC says "18-20 reads too young. Target 25-30"; the house block
# says "twenty-seven". The overlap is the mid-twenties, and "early twenties" was sitting at the
# edge the orc lessons already rejected.
# The old tier is gone for the dataset. Two of six verification frames drew it, and there is no
# place for it in the owner's acceptance criteria: PICK.md keeps "Age ~20-25", the beauty bell runs
# 6-7 / 7-8 / 8-9 / 9-10 with "no ugly", and LESSONS_ORC records "old/wrinkled faces = fail when
# asking for prettiest". A LoRA trained on a fifth of old faces learns them. Middle-aged stays as a
# thin tail so the style is seen surviving a lined face at all.
AGE_WEIGHTED: list[tuple[str, int]] = [
    ("a young adult in their mid-twenties, about twenty-five", 6),
    ("in their prime, around thirty", 3),
    ("middle-aged", 1),
]
AGE = [text for text, _ in AGE_WEIGHTED]
FRAMING = ["full body standing, head to toe", "three-quarter length, from the thighs up",
           "waist-up portrait", "head and shoulders portrait"]
# Owner-locked canvases: 768x1024 for the paint (002 itself), 768x1344 for a figure with feet in.
CANVAS_FULL, CANVAS_PORTRAIT = (768, 1344), (768, 1024)


def canvas_for(framing: str) -> tuple[int, int]:
    """The locked canvas for a framing: a figure gets the outfit size, a portrait the paint size."""
    return CANVAS_PORTRAIT if "portrait" in framing else CANVAS_FULL
# 002_REPEATABLE_FACTORS section 1: key upper-left ~45 degrees, fill "almost none", rim "none /
# negligible -- if you miss: neon outline, hero CGI". The list this replaces offered "rim-lit" and
# "from below the eyeline" as equal draws, which is two of six frames lit in a way the owner had
# already graded as a miss. Upper-left is weighted because it is the teacher's light; the others
# stay so the style is learned as surviving a key angle, not as one angle.
LIGHT_WEIGHTED: list[tuple[str, int]] = [
    ("key light from the upper left", 4),
    ("key light from the upper right", 2),
    ("key light from one side, near profile", 1),
    ("key light from slightly above and in front", 1),
]
LIGHT = [text for text, _ in LIGHT_WEIGHTED]
# Marks are biography, per the Look Matrix: "scars as biography deltas". They are not damage.
MARKS = ["", "", "old scars across the forearms", "a single old scar across the face",
         "work-callused hands and forearms", "tattooed marks of the culture",
         "sun-darkened hands and face", "a healed break in the nose"]


def _weighted(rng: random.Random, options: list[tuple[str, int]]) -> str:
    return rng.choices([text for text, _ in options], weights=[w for _, w in options], k=1)[0]


def appearance_for(sex: str, age: str, rng: random.Random) -> str:
    """The tier NAME. The face bundle is drawn from it in draw()."""
    return _weighted(rng, TIER_WEIGHTS[sex])


def hair_for(race: str, sex: str, rng: random.Random, head: str | None = None,
             colour: str = "", texture: str = "") -> str:
    """Hair follows the HEAD: a fully draconic alternate has a crown of horn, everyone else has hair."""
    if race in HEAD_VARIANTS and not is_kemonomimi(race, head):
        return rng.choice(["a swept-back crest of horn", "blunt horn ridges, no hair",
                           "a low crown of short horns"])
    return wrought_hair.draw_hair(race, sex, rng, colour, texture)


def appearance_negative_for(appearance: str) -> str:
    """Keep an attractive or ordinary face from rendering as a crone. See NOT_HAGGARD."""
    return "" if appearance == "weathered" else NOT_HAGGARD


# LESSONS_ORC: "Tudor noble gray grew a tail. Negative: tail." A tail is a race feature, so the
# negative is race-keyed: the races that HAVE one must not be told they do not.
RACE_NEGATIVE: dict[str, str] = {
    race: "tail" for race in ("orc", "goblin", "dwarf", "human", "high_elf", "wood_elf", "dark_elf")
}


def race_negative_for(race: str) -> str:
    return RACE_NEGATIVE.get(race, "")


def negative_for(sex: str) -> str:
    """The negatives a sex needs on top of the shared ones.

    Women carry FEMININE_NEGATIVE because the invariant has to bind on both sides: a positive
    describing feminine structure still loses to the model's prior for "broad and muscular", which
    is male. Stating what she must not become is what holds it.
    """
    return FEMININE_NEGATIVE if sex == "woman" else ""


# PEAK. The owner asked to see "the objective, no matter what race is looking at them, most
# beautiful women of each race" -- so this is not a tier of the distribution, it is the distribution
# collapsed to its best case. Everything that competes with the face is pinned: young, the striking
# tier, a framing where the face actually reads, and a light that flatters rather than dramatises.
# Build and clothing still vary, because a beauty that only survives one body is not the race's.
def draw_peak(race: str, rng: random.Random, sex: str = "woman", culture_materials: str = "") -> dict[str, str]:
    pick = draw(race, rng, sex, culture_materials=culture_materials)
    pick["age"] = "a young adult in their mid-twenties, about twenty-five"
    pick["appearance"] = "striking"
    pick["face_bundle"], pick["mark"] = face_bundle_for(rng, "striking")
    pick["expression"] = rng.choice(["calm and level", "a faint amused half-smile",
                                     "open and warm", "quietly proud"])
    pick["framing"] = rng.choice(["waist-up portrait", "head and shoulders portrait"])
    pick["light"] = rng.choice(["key light from the upper left",
                                "key light from slightly above and in front"])
    pick["marks"] = ""
    return pick


def draw(race: str, rng: random.Random, sex: str | None = None, culture_materials: str = "") -> dict[str, str]:
    """One complete variation. Every axis is independent except hair, which follows the race.

    `sex` is fixed per batch rather than drawn, because the owner runs one sex at a time -- which
    also makes the batch reviewable: a sheet of sixteen women is judged against one expectation.
    `culture_materials` is the race's own materials (from its culture file), named once by the
    wardrobe rather than a second time in the subject line's own tail.
    """
    sex = sex or rng.choice(SEX)
    age = _weighted(rng, AGE_WEIGHTED)
    # Nation first: it is the identity's own people, and its skin list is what identity_for draws
    # from -- SKIN_BY_RACE is the fallback for a race with no nation entry, never the primary source
    # once a nation has been drawn.
    nation, nation_row = nation_for(race, rng)
    subspecies, subspecies_clause = subspecies_for(race, rng)
    identity = identity_for(race, rng, SUBSPECIES.get(race, {}).get(subspecies, {}).get("hair_colours"),
                             skins=nation_row["skin"])
    # Hair is a generator now (wrought_hair, Task 6): texture x length x race style x adornment,
    # always opening "a full head of {colour} hair" -- the positive form of "always full hairline"
    # (LESSONS_ORC). Colour comes from the drawn identity, texture from the drawn nation (Task 4);
    # beastfolk colour still comes from the drawn subspecies via `identity_for`'s hair_colours arg.
    hair = hair_for(race, sex, rng, colour=identity["hair_colour"], texture=nation_row["hair_texture"])
    # The tier is a WEIGHT, not a sentence -- see face_bundle_for's module note. It is drawn once
    # here and used twice: to name "appearance" and to shape the structural draw beneath it.
    appearance_tier = appearance_for(sex, age, rng)
    face_bundle, mark = face_bundle_for(rng, appearance_tier)
    outfit = wrought_wardrobe.draw_outfit(race, rng, materials=culture_materials or "")
    return {
        "sex": sex,
        "race": race,
        "nation": nation,
        "nation_marker": nation_row["marker"],
        "hair_texture": nation_row["hair_texture"],
        "skin": identity["skin"],
        "hair_colour": identity["hair_colour"],
        "eyes": identity["eyes"],
        "lineage": lineage_for(race, rng),
        "subspecies": subspecies,
        "subspecies_clause": subspecies_clause,
        "build": build_for(race, rng),
        "age": age,
        "appearance": appearance_tier,
        "face_bundle": face_bundle,
        "mark": mark,
        "expression": rng.choice(EXPRESSION),
        "hair": hair,
        "outfit": outfit,
        "tier": outfit.rank,
        "clothing": outfit.worn_clause(),
        "condition": outfit.condition,
        "marks": rng.choice(MARKS),
        "framing": rng.choice(FRAMING),
        "light": _weighted(rng, LIGHT_WEIGHTED),
    }


def subject_line(race: str, pick: dict[str, str], culture: dict[str, str]) -> str:
    """Assemble the subject half of the prompt. The style block is added by the caller."""
    head = pick.get("head") or None
    # Regenerated when a test (or caller) overrides `pick["subspecies"]` after the draw, rather than
    # trusting a stale `subspecies_clause` that no longer names the same subspecies. The seed does
    # not matter here -- `choice` is set, so `subspecies_for` never calls `rng`.
    sub_name = pick.get("subspecies", "")
    sub_clause = (subspecies_for(race, random.Random(0), sub_name)[1] if sub_name
                  else pick.get("subspecies_clause", ""))
    # THE SKIN CLAUSE MUST PRECEDE THE LINEAGE CLAUSE. Records vs readings, 2026-09-05: with skin
    # trailing lineage, the lineage's scale-colour sentence won and the face rendered pale on 12 of
    # 12 sampled regardless of the drawn skin tone. Stated as the skin sentence first, scales as a
    # pattern on it second, and only then the inherited colour -- so a reader (and the model) meets
    # the skin before the scale.
    dragon = race == "dragonborn"
    skin_block = [pick.get("skin", "")] + ([SKIN_SCALE_PLACEMENT] if dragon else [])
    parts = [
        f"a single {race.replace('_', ' ')} {pick['sex']}",
        pick["age"],
        pick["build"],
        physiology_for(race, pick["sex"], head),
        sub_clause,
        *skin_block,
        pick.get("lineage", ""),
        pick["face_bundle"],
        pick.get("eyes", ""),
        LIVING_SKIN,
        pick["expression"] + " expression",
        pick["hair"],
        # STATED, not merely negated. "nude, topless, bare breasts" went into the negative and 2 of
        # 6 frames were still topless: an open riding coat over a bare torso satisfies "wearing a
        # coat" perfectly, and the negative loses to "full bust" plus a coat that the model knows
        # how to wear open. Third time this lesson has arrived -- the orthographic profile had to be
        # described by its consequences, and the appearance tiers by their features, for the same
        # reason. A negative prunes; only the positive builds.
        f"wearing {pick['clothing']}, {pick['condition']}, fully clothed, "
        "the garment closed and covering the chest, torso and legs completely",
        # Scale garments were asked for in 6 prompts and rendered in 5 of 12 (2026-09-05) -- the
        # wardrobe clause above never forbade scale on the clothing, only stated what covered it.
        # Stated positively, right after the wardrobe clause it qualifies.
        DRAGONBORN_GARMENT if dragon else "",
        pick["marks"],
        pick.get("nation_marker", ""),
        pick["framing"],
        pick["light"],
        # DELETED (Task 7): the trailing "materials: ..." clause. The outfit clause above (Outfit.
        # worn_clause) already names the race's materials once; this was a second statement of the
        # same fact and Task 5 had already trimmed it once for exactly that kind of duplication.
        f"palette of {culture.get('palette', '')}",
    ]
    return ", ".join(p for p in parts if p)


def combinations() -> int:
    """Rough size of the space, to show a hundred frames are not near-duplicates."""
    face_bundle_space = (len(JAW) * len(CHEEK) * len(BROW) * len(NOSE_BRIDGE)
                         * len(EYE_SHAPE) * len(LIPS) * len(ASYMMETRY) * len(MARK_FACE))
    total = (len(SEX) * len(BUILD) * len(AGE) * 4 * len(EXPRESSION)
             * max(len(v) for v in LINEAGE.values())
             * face_bundle_space * 4 * 4
             * len(wrought_hair.LENGTH) * max(len(s) for s in wrought_hair.STYLES_BY_RACE.values())
             * max(len(a) for a in wrought_hair.ADORNMENT_BY_RACE.values())
             * len(wrought_wardrobe.DIALECTS) * len(wrought_wardrobe.RANKS) * 4**9
             * len(MARKS) * len(FRAMING) * len(LIGHT))
    return total


if __name__ == "__main__":
    rng = random.Random(1)
    print(f"variation space: {combinations():,} combinations\n")
    for race in ("orc", "high_elf", "dragonborn", "beastfolk"):
        pick = draw(race, rng)
        print(f"--- {race} ---")
        print(subject_line(race, pick, {"materials": "…", "surface": "Worn",
                                        "ornament": "Trophy", "palette": "…"})[:300])
        print()
