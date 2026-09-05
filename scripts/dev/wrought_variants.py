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
MASCULINE_READ = (
    "unmistakably male, heavier brow and squarer jaw, broader through the shoulders than the hips, "
    "thicker neck"
)

RACE_PHYSIOLOGY: dict[str, dict[str, str]] = {
    "orc": {
        # 5e: tall, powerfully built, greyish-green skin, jutting jaw with prominent lower tusks,
        # sloping forehead, pointed ears.
        "core": "greyish-green skin, prominent lower tusks, a strong jaw, sloping brow, pointed ears, "
                "tall and powerfully built",
        "male": "heavy slab muscle, thick neck, broad flat chest",
        # The tweak: strength AND femininity together, never one bought with the other.
        "female": "strong and thickly built with heavy muscle under a soft layer, broad shoulders "
                  "that still sit narrower than her hips, a deep waist above wide heavy hips, "
                  "full heavy bust, smaller tusks, a softer brow than the men",
    },
    "goblin": {
        # 5e: small, flat faces, broad noses, pointed ears, wide mouths, small sharp teeth.
        "core": "small and wiry, dull olive-yellow to sallow grey-green skin, a broad nose, long "
                "pointed ears, a wide mouth with small sharp teeth, quick clever eyes",
        "male": "sinewy and angular, sharp featured",
        "female": "small and softly rounded rather than gaunt, a neat waist above rounded hips, "
                  "a softer face with larger eyes and fuller lips, clearly a woman at a glance",
    },
    "dwarf": {
        # 5e: 4-5 ft, as heavy as a human, ruddy or deep brown skin, thick hair.
        "core": "short and dense, about four and a half feet tall but as heavy as a tall human, "
                "ruddy or deep brown skin, strong brows, a strong nose, thick hair",
        "male": "barrel-chested, heavily bearded, thick through the neck and forearms",
        "female": "broad and powerfully built with a heavy soft-edged figure, a defined waist "
                  "between a full bust and wide strong hips, a smooth beardless face, braided hair; "
                  "stocky and unmistakably a woman",
    },
    "human": {
        "core": "the full human range of height, build, skin tone and features",
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
        "core": "lean and wiry, coppery or warm brown skin, pointed ears, "
                "green brown or hazel eyes, dark or auburn hair",
        "male": "sinewy, weathered, close-cut or bound hair",
        "female": "lithe and athletic with a soft-edged figure, a clear waist above rounded hips, "
                  "a warm open face; wiry strength that still reads feminine",
    },
    "dark_elf": {
        # 5e drow: obsidian to dusky grey skin, stark white or pale hair, pale eyes, slighter build.
        "core": "obsidian to dusky grey skin, stark white or pale hair, pale eyes that carry against "
                "the skin, pointed ears, slighter and finer than surface elves",
        "male": "lean and close-muscled, sharp featured",
        "female": "slender and distinctly curved, a narrow waist above full hips, fine soft features, "
                  "poised; never severe to the point of reading masculine",
    },
    "dragonborn": {
        # 5e: 6ft+, ~250 lb, scaled hide, blunt snout, brow ridges and horns, clawed hands, no ears.
        "core": "tall and heavy, well over six feet, a hide of overlapping scales in bronze slate "
                "green or dull red, a blunt draconic snout, heavy brow ridges and swept-back horns, "
                "no external ears, clawed hands",
        "male": "massive through the chest and shoulders, heavier horns",
        "female": "powerfully built but visibly female, a narrower snout and finer horns, a defined "
                  "waist above wide hips, a full chest, smoother scale over softer contours",
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


def physiology_for(race: str, sex: str) -> str:
    """The race's shared core, this sex's expression, and the invariant for women."""
    entry = RACE_PHYSIOLOGY.get(race, {})
    parts = [entry.get("core", "")]
    if sex == "woman":
        parts += [entry.get("female", ""), FEMININE_READ]
    else:
        parts += [entry.get("male", ""), MASCULINE_READ]
    return ", ".join(p for p in parts if p)


# --- appearance, with the floor the owner set ------------------------------------------------
#
# (text, weight). Weights, not uniform choice -- see the module docstring.
# Stated STRUCTURALLY and race-relative rather than as a bare adjective. "A handsome, attractive
# face" lost outright to goblin and dwarf physiology and rendered crones; naming the features that
# make a face attractive gives the sampler something the race description cannot simply overwrite.
STRIKING = ("a strikingly beautiful face by her own people's standards, smooth clear skin, "
            "full cheeks, bright clear eyes, full lips, even features")
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
APPEARANCE_BY_SEX: dict[str, list[tuple[str, int]]] = {
    "woman": [(STRIKING, 4), (HANDSOME, 3), (ORDINARY, 3), (WEATHERED, 2)],
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
    "wild and uncombed", "a shaved head", "a thick fringe over the brow",
    "greying at the temples, tied back", "hair worked with beads and small rings",
    "a rough side-part, grown out",
]
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

# --- everything else worth varying ------------------------------------------------------------
SEX = ["woman", "man"]
BUILD = ["lean and wiry", "heavy and thick-set", "broad and muscular", "slight and narrow",
         "stocky and powerful", "tall and rangy", "soft and full-figured", "athletic and balanced"]
# WEIGHTED, because PICK.md's acceptance criterion says "Age ~20-25" and a flat four-way draw put
# half the cast at middle-aged or older. The older tiers stay -- a world of nothing but
# twenty-somethings is its own failure -- but as a tail rather than half the batch.
AGE_WEIGHTED: list[tuple[str, int]] = [
    ("a young adult in their early twenties", 5),
    ("in their prime, around thirty", 3),
    ("middle-aged", 1),
    ("weathered and old", 1),
]
AGE = [text for text, _ in AGE_WEIGHTED]
FRAMING = ["full body standing, head to toe", "three-quarter length, from the thighs up",
           "waist-up portrait", "head and shoulders portrait"]
LIGHT = ["key light from the upper left", "key light from the upper right",
         "key light from one side, near profile", "key light from slightly above and in front",
         "low key light from below the eyeline", "key light behind and to one side, rim-lit"]
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


def hair_for(race: str, sex: str, rng: random.Random) -> str:
    """Hair, or the race-appropriate absence of it."""
    if race == "dragonborn":
        return rng.choice(["a swept-back crest of horn", "blunt horn ridges, no hair",
                           "a low crown of short horns"])
    if race == "beastfolk":
        return rng.choice(["a thick mane over the shoulders", "short dense fur, no styled hair",
                           "a ruff of longer fur at the throat", "a braided crest between the ears"])
    hair = rng.choice(HAIR)
    if sex == "man" and rng.random() < 0.6:
        hair += ", " + rng.choice(FACIAL_HAIR)
    return hair


def appearance_negative_for(appearance: str) -> str:
    """Keep an attractive or ordinary face from rendering as a crone. See NOT_HAGGARD."""
    return "" if appearance == WEATHERED else NOT_HAGGARD


def negative_for(sex: str) -> str:
    """The negatives a sex needs on top of the shared ones.

    Women carry FEMININE_NEGATIVE because the invariant has to bind on both sides: a positive
    describing feminine structure still loses to the model's prior for "broad and muscular", which
    is male. Stating what she must not become is what holds it.
    """
    return FEMININE_NEGATIVE if sex == "woman" else ""


def draw(race: str, rng: random.Random, sex: str | None = None) -> dict[str, str]:
    """One complete variation. Every axis is independent except hair, which follows the race.

    `sex` is fixed per batch rather than drawn, because the owner runs one sex at a time -- which
    also makes the batch reviewable: a sheet of sixteen women is judged against one expectation.
    """
    sex = sex or rng.choice(SEX)
    age = _weighted(rng, AGE_WEIGHTED)
    tier = rng.choice(list(CLOTHING))
    return {
        "sex": sex,
        "build": rng.choice(BUILD),
        "age": age,
        "appearance": appearance_for(sex, age, rng),
        "expression": rng.choice(EXPRESSION),
        "hair": hair_for(race, sex, rng),
        "tier": tier,
        "clothing": rng.choice(CLOTHING[tier]),
        "condition": rng.choice(CONDITION),
        "marks": rng.choice(MARKS),
        "framing": rng.choice(FRAMING),
        "light": rng.choice(LIGHT),
    }


def subject_line(race: str, pick: dict[str, str], culture: dict[str, str]) -> str:
    """Assemble the subject half of the prompt. The style block is added by the caller."""
    parts = [
        f"a single {race.replace('_', ' ')} {pick['sex']}",
        pick["age"],
        pick["build"],
        physiology_for(race, pick["sex"]),
        pick["appearance"],
        pick["expression"] + " expression",
        pick["hair"],
        f"wearing {pick['clothing']}, {pick['condition']}",
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
