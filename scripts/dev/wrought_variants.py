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

import random

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
FEMININE_READ = (
    "unmistakably female, feminine facial structure with a rounded jawline, soft brow, full lips "
    "and large eyes, a clearly defined waist above wide hips, hips broader than the ribcage, "
    "full bust, a soft layer over the muscle rather than a lean cut, smooth neck and shoulders "
    "without heavy trapezius bulk"
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
    "beastfolk":  {"woman": "smaller, more delicate ears and finer horns if any",
                   "man": "larger ears and heavier horns"},
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

FEMININE_BODY = ("a clearly defined waist above wide hips, hips broader than the ribcage, "
                 "full bust, a soft layer over the muscle rather than a lean cut")

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
# horns) and FEMININE_BODY, which is the same split every other race already uses.
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
        "kemonomimi": (
            "a human face -- human facial structure, a human nose and mouth, smooth human skin "
            "across the centre of the face -- with draconic features added to it rather than "
            "replacing it, no muzzle and no snout, "
            "fine scales patterning the temples and hairline and cheekbones and jawline, thinning "
            "toward the centre of the face and thickening down the neck onto the shoulders, "
            "long ridged horns rising above the ears and sweeping back, "
            "long pointed ears, slit-pupil reptilian eyes, ordinary human hair on the head"),
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
        "female": "strong and thickly built with heavy muscle under a soft layer, broad shoulders "
                  "that still sit narrower than her hips, a deep waist above wide heavy hips, "
                  "full heavy bust, a softer brow than the men",
    },
    "goblin": {
        # 5e: small, flat faces, broad noses, pointed ears, wide mouths, small sharp teeth.
        # GOBLIN_10 r3 lesson: "full body, adult head-to-body ratio, not a doll / giant head".
        "core": "small and wiry, a broad nose, long "
                "pointed ears, a wide mouth with small sharp teeth, "
                "adult head-to-body proportion, not a doll",
        "male": "sinewy and angular, sharp featured",
        "female": "small and softly rounded, well-fed rather than wiry, a neat waist above rounded hips, "
                  "a small delicate face with bright eyes, a small nose, full lips and "
                  "smooth unlined skin; mischievous rather than harsh, clearly a woman at a glance",
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
        "female": "extremely broad for her height, shoulders nearly as wide as she is tall, "
                  "a deep barrel ribcage, thick forearms and large strong hands, a short thick neck, "
                  "deep-set eyes beneath a heavy brow, a strong straight nose, high hard cheekbones, "
                  "a defined waist between a full bust and wide strong hips; "
                  "clearly a dwarf and not a short human",
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
        "female": "slender but curved, a narrow waist above clearly rounded hips, a soft full mouth, "
                  "large eyes; fine-boned but never boyish",
    },
    "wood_elf": {
        # 5e: coppery skin, green/brown/hazel hair and eyes, wiry and quick.
        "core": "trim and athletic, pointed ears",
        "male": "sinewy, weathered, close-cut or bound hair",
        "female": "athletic and healthy with visible tone and a soft layer over it, full cheeks, "
                  "a clear waist above rounded hips, a warm open face, well-fed and strong; "
                  "never gaunt, never thin",
    },
    "dark_elf": {
        # 5e drow: obsidian to dusky grey skin, stark white or pale hair, pale eyes, slighter build.
        # Vision Bible row 1: "Pupil-less luminous eyes; long pointed ears; cool obsidian/violet/
        # gray skin."
        "core": "long pointed ears, slighter and finer than surface elves, eyes that carry against "
                "the dark skin",
        "male": "lean and close-muscled, sharp featured",
        "female": "young and smooth-skinned, slender and distinctly curved, a narrow waist above full "
                  "hips, fine soft features, full lips, large eyes, unlined flawless skin; "
                  "poised and youthful, never severe and never aged",
    },
    "dragonborn": {
        # 5e: 6ft+, ~250 lb, scaled hide, blunt snout, brow ridges and horns, clawed hands, no ears.
        "core": "tall and strong, well over six feet, draconic scales heaviest across the "
                "forearms shoulders and lower legs and lightest at the face, clawed hands, "
                "a heavy tail",
        "male": "massive through the chest and shoulders",
        "female": "powerfully built but visibly female, fine smooth scales, a slimmer neck, "
                  "smoother scale over softer contours",
    },
    "beastfolk": {
        # NOT a 5e race and NOT anthropomorphic. Owner rule, PICK.md and README.md: kemonomimi --
        # a HUMAN FACE with animal ears and horns. No animal heads, no muzzles.
        "core": "a human face with animal ears set high on the head, sometimes small horns, a tail, "
                "fur markings across the skin at the forearms and shoulders, "
                "no animal head and no muzzle, the face is human",
        "male": "broad and heavily built, coarse hair",
        "female": "athletic and full-figured, a defined waist above wide hips, a full bust, "
                  "a soft human face framed by the ears; clearly a woman with animal features",
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
        # human one. Body dimorphism is in FEMININE_BODY either way. A kemonomimi head IS a human
        # face, so it takes the human read -- the override is for the draconic alternates only.
        if FEMININE_FACE_OVERRIDE.get(race) and not is_kemonomimi(race, head):
            parts.append(FEMININE_FACE_OVERRIDE[race])
            parts.append(FEMININE_BODY)
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
# So skin, hair colour, eye colour and face shape are DRAWN, per race, from the Vision Bible's own
# ranges where it gives them (orc "olive/forest/slate", drow "obsidian/violet/gray", goblin
# "amber/gold/green eyes") and 5e where it does not. Every range that a race core used to state in
# prose ("coppery or warm brown skin") moves here, and the core stops naming it -- the same
# one-owner-clause rule as crest/hair and lineage/eyes.
#
# Races whose colour is owned elsewhere keep that owner: dragonborn eyes and scale belong to
# LINEAGE (only the human face-skin is drawn here); dark-elf eyes are pupil-less and luminous by
# the Bible and vary only in their glow.
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
    "dragonborn": ["warm tan human skin at the face", "olive human skin at the face",
                   "pale human skin at the face", "deep brown human skin at the face"],
    "beastfolk": ["warm tan skin", "olive skin", "pale skin", "brown skin"],
}
HAIR_COLOUR_BY_RACE: dict[str, list[str]] = {
    "orc": ["black", "dark brown", "auburn", "black with grey streaks"],
    "goblin": ["black", "dark rust-brown", "ash-brown", "green-black"],
    "dwarf": ["red", "auburn", "black", "dark brown", "blonde", "grey-streaked brown"],
    "human": ["black", "dark brown", "brown", "auburn", "blonde", "red", "dark blonde"],
    "high_elf": ["platinum blonde", "silver-white", "gold", "black", "chestnut"],
    "wood_elf": ["dark brown", "auburn", "black", "chestnut", "dark red"],
    "dark_elf": ["stark white", "silver", "pale ash", "white with a lavender cast"],
    "dragonborn": ["black", "dark brown", "auburn", "dark red"],
    "beastfolk": ["tawny", "black", "grey", "russet", "spotted gold"],
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
FACE_SHAPE = ["a round face", "an oval face", "a heart-shaped face", "a long face with a narrow chin",
              "a soft square face", "high cheekbones and a tapered chin"]
NOSE = ["a small nose", "a straight nose", "a slightly upturned nose", "a broad nose",
        "an aquiline nose"]
# Races whose core already names the nose (dwarf "a strong nose", goblin "a broad nose").
NOSE_OWNED_BY_CORE = {"dwarf", "goblin"}


def identity_for(race: str, rng: random.Random) -> dict[str, str]:
    """Skin, eyes, face shape, nose, and a hair colour for the hair axis to wear."""
    return {
        "skin": rng.choice(SKIN_BY_RACE.get(race, SKIN_BY_RACE["human"])),
        "eyes": rng.choice(EYES_BY_RACE[race]) if EYES_BY_RACE.get(race) else "",
        "face": rng.choice(FACE_SHAPE),
        "nose": "" if race in NOSE_OWNED_BY_CORE else rng.choice(NOSE),
        "hair_colour": rng.choice(HAIR_COLOUR_BY_RACE.get(race, HAIR_COLOUR_BY_RACE["human"])),
    }


# --- appearance, with the floor the owner set ------------------------------------------------
#
# (text, weight). Weights, not uniform choice -- see the module docstring.
# Stated STRUCTURALLY and race-relative rather than as a bare adjective. "A handsome, attractive
# face" lost outright to goblin and dwarf physiology and rendered crones; naming the features that
# make a face attractive gives the sampler something the race description cannot simply overwrite.
STRIKING = ("a strikingly beautiful face by any standard, genuinely gorgeous, smooth clear skin, "
            "full cheeks, large bright eyes, full lips, elegant even features, "
            "beautiful regardless of who is looking")
HANDSOME = ("a handsome, attractive face, smooth skin, healthy full cheeks, clear eyes, "
            "even features")
ORDINARY = ("an ordinary, unremarkable face, plain but pleasant and healthy, smooth skin")
WEATHERED = "a plain face lined by work and weather, but healthy"

# Rides the negative on every frame whose appearance tier is not WEATHERED. The named failures are
# the ones the races actually produced, not hypotheticals.
NOT_HAGGARD = ("gaunt, haggard, emaciated, hollow cheeks, sunken eyes, deeply lined face, "
               "crone, witch-like, sickly, malnourished, elderly")

# Sex-dependent, because the owner's rule is specific: EVERY RACE MUST INCLUDE BEAUTIFUL WOMEN. Left
# to one shared table that emerges at roughly 13 frames per hundred, which is enough to be present
# and not enough to be reliable. Weighted this way it is about a third of the women in each race,
# with ordinary and weathered faces still common enough that the cast does not read as a modelling
# agency -- the other half of the same instruction.
# Women: the owner's beauty bell (6-7 ~25%, 7-8 ~40%, 8-9 ~25%, 9-10 ~10%) has no tier below
# "ordinary attractive", so WEATHERED is a men's tier only.
APPEARANCE_BY_SEX: dict[str, list[tuple[str, int]]] = {
    "woman": [(STRIKING, 3), (HANDSOME, 4), (ORDINARY, 3)],
    "man": [(STRIKING, 2), (HANDSOME, 3), (ORDINARY, 3), (WEATHERED, 3)],
}

# Age vetoes symmetry, not beauty. "Weathered and old" drawing "clear symmetry" reads as a prompt
# arguing with itself, and the sampler resolves that by picking one -- usually by making the face
# young, which quietly erases the age axis from the dataset. An old face that carries is HANDSOME.
AGE_FORBIDS_STRIKING = "weathered and old"

# What the appearance axis must never reach for. These ride the negative prompt on every frame.
APPEARANCE_NEGATIVE = ("hideous, grotesque, deformed face, disfigured, monstrous, "
                       "caricature, exaggerated features, asymmetric eyes")

EXPRESSION = ["calm and level", "guarded, watchful", "a faint amused half-smile",
              "open and warm", "tired, thousand-yard", "hard, challenging stare",
              "mid-thought, distracted", "quietly proud"]

# --- hair -------------------------------------------------------------------------------------
#
# Kept generic so it composes with any race; the race's own `features` line supplies colour and
# texture tendencies. Dragonborn take none of these -- see `hair_for`.
HAIR = [
    "long loose hair", "long hair in a single thick braid", "many tight braids gathered back",
    "a shaved undercut with length on top", "close-cropped practical hair",
    "a topknot bound with cord", "shoulder-length and unkempt", "twin braids framing the face",
    "hair bound in a wrapped bun", "a long ponytail high on the head",
    "wild, thick and uncombed", "a thick fringe over the brow",
    "greying at the temples, tied back", "hair worked with beads and small rings",
    "a rough side-part, grown out",
]
SHAVED_FOR_WOMEN = {"close-cropped practical hair", "a shaved undercut with length on top"}
FACIAL_HAIR = ["clean-shaven", "a short beard", "a full heavy beard", "a braided beard",
               "stubble", "a long moustache"]

# --- clothing ---------------------------------------------------------------------------------
#
# Outerwear, by tier. The existing `garment-types-vocabulary.md` in SpellBound covers the FOUNDATION
# layer (the fitted innermost garment) and deliberately does not overlap this. Materials come from
# the culture file at render time, so a dwarf's "heavy coat" is forged-steel-and-cut-stone country
# and a goblin's is salvage, without either being written twice.
CLOTHING: dict[str, list[str]] = {
    "working": [
        "plain working clothes, patched and much repaired",
        "a rough tunic belted at the waist over loose trousers",
        "a sleeveless work jerkin, bare arms, forearm wraps",
        "an apron over shirtsleeves, tools still on the belt",
        "layered rags and wraps against the cold",
        "a short smock and cross-gartered leggings",
    ],
    "travelling": [
        "a travelling outfit under a heavy hooded cloak",
        "an oiled riding coat over layered wool",
        "a fur-lined mantle clasped at the shoulder",
        "a long coat, road-stained, with a pack harness",
        "a hooded shawl wrapped across the chest and pinned",
    ],
    "light armour": [
        "a studded leather jerkin over a padded shirt",
        "a boiled leather cuirass with strapped bracers",
        "a mail shirt worn open over cloth, sleeves pushed back",
        "scale sewn onto a leather backing, shoulders bare",
        "a brigandine of plates riveted between cloth layers",
    ],
    "heavy armour": [
        "full heavy armour of the culture's own making",
        "a plate cuirass over mail, pauldrons strapped high",
        "banded armour with a heavy gorget and vambraces",
        "layered lamellar over a long padded coat",
        "a mail hauberk to the knee under a plated harness",
    ],
    "fine": [
        "fine clothes marking status, well cut and unpatched",
        "an embroidered overcoat with worked fastenings",
        "a long formal robe with a heavy ornamented belt",
        "a fitted doublet under a fur-collared cloak",
        "ceremonial dress of the culture, worn with authority",
    ],
}
CONDITION = ["newly made and clean", "well kept but used", "worn and repaired",
             "hard-used, stained and mended", "old, faded, and patched many times"]


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
    options = APPEARANCE_BY_SEX[sex]
    if AGE_FORBIDS_STRIKING in age:
        options = [(t, w) for t, w in options if t != STRIKING]
    return _weighted(rng, options)


def hair_for(race: str, sex: str, rng: random.Random, head: str | None = None) -> str:
    """Hair, or the race-appropriate absence of it.

    Follows the HEAD rather than the race, because for dragonborn the two disagree: the kemonomimi
    head has ordinary hair and the fully draconic alternates have a crown of horn instead.
    """
    if race in HEAD_VARIANTS and not is_kemonomimi(race, head):
        return rng.choice(["a swept-back crest of horn", "blunt horn ridges, no hair",
                           "a low crown of short horns"])
    if race == "beastfolk":
        return rng.choice(["a thick mane over the shoulders", "short dense fur, no styled hair",
                           "a ruff of longer fur at the throat", "a braided crest between the ears"])
    # LESSONS_ORC: "Bald / shaved scalp = unattractive. Always full hairline." Night frame orc/003
    # drew "close-cropped practical hair" and rendered as shaved; the undercut does the same on a
    # woman. Both stay in the list for men.
    hair = rng.choice([h for h in HAIR if sex == "man" or h not in SHAVED_FOR_WOMEN])
    if sex == "man" and rng.random() < 0.6:
        hair += ", " + rng.choice(FACIAL_HAIR)
    return hair


def appearance_negative_for(appearance: str) -> str:
    """Keep an attractive or ordinary face from rendering as a crone. See NOT_HAGGARD."""
    return "" if appearance == WEATHERED else NOT_HAGGARD


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
def draw_peak(race: str, rng: random.Random, sex: str = "woman") -> dict[str, str]:
    pick = draw(race, rng, sex)
    pick["age"] = "a young adult in their mid-twenties, about twenty-five"
    pick["appearance"] = STRIKING
    pick["expression"] = rng.choice(["calm and level", "a faint amused half-smile",
                                     "open and warm", "quietly proud"])
    pick["framing"] = rng.choice(["waist-up portrait", "head and shoulders portrait"])
    pick["light"] = rng.choice(["key light from the upper left",
                                "key light from slightly above and in front"])
    pick["marks"] = ""
    return pick


def draw(race: str, rng: random.Random, sex: str | None = None) -> dict[str, str]:
    """One complete variation. Every axis is independent except hair, which follows the race.

    `sex` is fixed per batch rather than drawn, because the owner runs one sex at a time -- which
    also makes the batch reviewable: a sheet of sixteen women is judged against one expectation.
    """
    sex = sex or rng.choice(SEX)
    age = _weighted(rng, AGE_WEIGHTED)
    tier = rng.choice(list(CLOTHING))
    identity = identity_for(race, rng)
    hair = hair_for(race, sex, rng)
    # The colour rides the hair axis rather than standing alone, so "a topknot bound with cord,
    # auburn hair" is one clause about one thing. Fur races colour the fur.
    # "A full head of" is the positive form of "always full hairline". Goblin night frames 023 and
    # 038 drew "wild and uncombed" and rendered bald -- the shaved options were already excluded,
    # so the absence of a full-hairline claim was the gap. Same lesson as coverage: a negative
    # prunes, only the positive builds.
    hair = (f"{hair}, {identity['hair_colour']} fur" if race == "beastfolk"
            else f"{hair}, a full head of {identity['hair_colour']} hair")
    return {
        "sex": sex,
        "skin": identity["skin"],
        "eyes": identity["eyes"],
        "face": identity["face"],
        "nose": identity["nose"],
        "lineage": lineage_for(race, rng),
        "build": build_for(race, rng),
        "age": age,
        "appearance": appearance_for(sex, age, rng),
        "expression": rng.choice(EXPRESSION),
        "hair": hair,
        "tier": tier,
        "clothing": rng.choice(CLOTHING[tier]),
        "condition": rng.choice(CONDITION),
        "marks": rng.choice(MARKS),
        "framing": rng.choice(FRAMING),
        "light": _weighted(rng, LIGHT_WEIGHTED),
    }


def subject_line(race: str, pick: dict[str, str], culture: dict[str, str]) -> str:
    """Assemble the subject half of the prompt. The style block is added by the caller."""
    head = pick.get("head") or None
    parts = [
        f"a single {race.replace('_', ' ')} {pick['sex']}",
        pick["age"],
        pick["build"],
        physiology_for(race, pick["sex"], head),
        pick.get("lineage", ""),
        pick.get("skin", ""),
        pick.get("face", ""),
        pick.get("nose", ""),
        pick.get("eyes", ""),
        pick["appearance"],
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
        pick["marks"],
        pick["framing"],
        pick["light"],
        f"materials of this culture: {culture.get('materials', '')}",
        f"{culture.get('surface', '').lower()} surfaces",
        f"{culture.get('ornament', '').lower()} ornament",
        f"palette of {culture.get('palette', '')}",
    ]
    return ", ".join(p for p in parts if p)


def combinations() -> int:
    """Rough size of the space, to show a hundred frames are not near-duplicates."""
    total = (len(SEX) * len(BUILD) * len(AGE) * 4 * len(EXPRESSION)
             * max(len(v) for v in LINEAGE.values())
             * len(FACE_SHAPE) * len(NOSE) * 4 * 4 * 4
             * len(HAIR) * sum(len(v) for v in CLOTHING.values()) * len(CONDITION)
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
