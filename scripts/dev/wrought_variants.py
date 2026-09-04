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

# --- race physicality -----------------------------------------------------------------------
#
# AUTHORED, NOT CANONICAL. Each entry pairs a build tendency with the features that make the race
# readable in silhouette and at portrait distance. Kept short on purpose: a long physical description
# crowds out the style block, and the style is what the dataset exists to teach.
RACE_PHYSIOLOGY: dict[str, dict[str, str]] = {
    "orc": {
        "body": "heavy-boned and powerfully built, broad through the shoulders and hips",
        "features": "green to olive skin, lower tusks, pointed ears, heavy brow, dense dark hair",
        "note": "strength reads as mass and muscle together, never as leanness",
    },
    "goblin": {
        "body": "small, wiry and quick, long-limbed for their height",
        "features": "sallow green or grey-green skin, long mobile ears, sharp features, small eyes "
                    "set close, pointed teeth",
        "note": "clever rather than feral; the face should read as thinking",
    },
    "dwarf": {
        "body": "short, dense and thick-limbed, deep-chested",
        # No sex-conditional clause here. It read "the men bearded and the women often braided",
        # which lands in a woman's prompt as a statement about men -- noise the sampler has to
        # resolve. Beards are drawn by `hair_for`, which already knows the sex.
        "features": "ruddy weathered skin, heavy brows, strong noses, thick hair",
        "note": "breadth and density, never simply short humans",
    },
    "human": {
        "body": "the full human range, from slight to heavy",
        "features": "the full human range of skin tones, hair colours and features",
        "note": "the baseline the other races are read against",
    },
    "high_elf": {
        "body": "tall and slender, long-limbed, upright carriage",
        "features": "pale luminous skin, long swept-back pointed ears, fine bones, high cheekbones, "
                    "pale or silver hair",
        "note": "composed and unhurried; pristine surfaces per the culture",
    },
    "wood_elf": {
        "body": "lean and light, wiry rather than delicate",
        "features": "warm brown or olive skin, pointed ears, sun-marked faces, dark or auburn hair "
                    "often braided with cord",
        "note": "weathered where the high elf is pristine",
    },
    "dark_elf": {
        "body": "tall and lean, close-muscled",
        "features": "ashen grey to deep charcoal skin, pointed ears, pale hair, light eyes that "
                    "carry against the skin",
        "note": "contrast between dark skin and pale hair is the read; never a villain cue",
    },
    "dragonborn": {
        "body": "tall and heavy, broad-backed, digitigrade stance",
        "features": "overlapping scales in bronze, slate, green or dull red, a blunt draconic muzzle, "
                    "horn ridges sweeping back, no external ears",
        "note": "scale is a material -- it must read as keratin under the key light, not as armour",
    },
    "beastfolk": {
        "body": "powerfully built, varying by stock, digitigrade or plantigrade",
        "features": "a coat of fur over the whole body, an animal head with expressive eyes, upright "
                    "ears, clawed hands that still work tools",
        "note": "human proportion and posture under an animal coat; the face must carry expression",
    },
}

# --- appearance, with the floor the owner set ------------------------------------------------
#
# (text, weight). Weights, not uniform choice -- see the module docstring.
STRIKING = "a strikingly beautiful face, fine features, clear symmetry"
HANDSOME = "a handsome, attractive face"
ORDINARY = "an ordinary, unremarkable face, plain but pleasant"
WEATHERED = "a plain weathered face, lined by work and weather"

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
AGE = ["a young adult", "in their prime", "middle-aged", "weathered and old"]
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


def draw(race: str, rng: random.Random) -> dict[str, str]:
    """One complete variation. Every axis is independent except hair, which follows the race."""
    sex = rng.choice(SEX)
    age = rng.choice(AGE)
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
    physiology = RACE_PHYSIOLOGY.get(race, {})
    parts = [
        f"a single {race.replace('_', ' ')} {pick['sex']}",
        pick["age"],
        pick["build"],
        physiology.get("body", ""),
        physiology.get("features", ""),
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
