"""The wardrobe as the Clothing Production Guide defines it, in code.

Guide v1.2, section 0: "Architecture defines the dialect. Class is only one axis of register."
Register = wealth/rank x profession x institution x occasion x condition x function. Section 5: dye
is money -- labourers wear the colour of the sheep and the plant, merchants show they paid for blue
or red. Section 8: "If two NPCs from the same town look like they own the same outfit in different
sizes, the clothing system has failed." The night run's 26-line CLOTHING table had none of these
axes and Jarvis named "leather and fur warrior tunic" on most frames of every race.

Each outfit is nine SLOTS drawn under one dialect's cut language and one rank's material/dye/
ornament/condition signal, with the race's own materials (from its culture file) named once. The same
Outfit renders two ways: WORN on a character (Lane B fit plates, and the dressed exploration frames)
and ALONE on a mannequin (Lane B asset plates, Guide section 7.5), so the garment the 3D stage
receives is the garment the character wore.

Dragonborn never receive a scale garment (DIRECTION_V2 section 4): on a scaled race a scale garment
reads as body scale, and the model put scales on the clothing unasked on 5 of 12 frames.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

DIALECTS: dict[str, str] = {
    "vernacular": "simple geometry, local cloth, repair as normal speech",
    "tudor": "structured upper body, fuller lower volume, belts and straps",
    "gothic": "vertical emphasis, long lines, hoods and clean high forms",
    "romanesque": "heavy rounded protective volumes, thick cloth",
    "byzantine": "layered hierarchy, panels, formal stacking of garments",
    "italianate": "classical ease, clean proportion, climate-open cuts",
    "organic": "irregular, body-following, grown or felt logic",
    "elizabethan": "strong shape definition, ornament pushed to edges and status zones",
}
RACE_DIALECTS: dict[str, list[str]] = {
    "human": ["gothic", "tudor", "vernacular"], "orc": ["vernacular", "romanesque"],
    "goblin": ["vernacular"], "dwarf": ["romanesque", "tudor"], "high_elf": ["gothic", "italianate"],
    "wood_elf": ["vernacular", "organic"], "dark_elf": ["gothic"], "dragonborn": ["byzantine", "romanesque"],
    "beastfolk": ["vernacular", "organic"],
}
# (rank, weight). The five-step ladder is a readability check; profession/occasion/condition vary it.
RANKS: list[tuple[str, int]] = [("labourer", 3), ("craftsman", 3), ("merchant", 2), ("noble", 1), ("ruler", 1)]
DYE_BY_RANK = {
    "labourer": "undyed, the colour of the sheep and the plant",
    "craftsman": "a little local plant dye, drab and limited",
    "merchant": "visible paid colour, woad or madder on meaningful areas",
    "noble": "costly dye in larger fields, disciplined",
    "ruler": "the richest legal accents in disciplined fields",
}
ORNAMENT_BY_RANK = {"labourer": "no ornament", "craftsman": "trade tools and marks",
                    "merchant": "controlled trim", "noble": "focal ornament at the edges, marks of house",
                    "ruler": "full status ornament"}
CONDITION_BY_RANK = {"labourer": ["heavy wear and patches", "patched many times", "stained and mended"],
                     "craftsman": ["used but maintained", "worn and repaired"],
                     "merchant": ["clean presentation", "well kept but used"],
                     "noble": ["clean, high craft"], "ruler": ["immaculate", "historic and cared for"]}
CONDITION = sorted({c for v in CONDITION_BY_RANK.values() for c in v})
PROFESSION_BY_RANK = {
    "labourer": ["field hand", "carter", "porter", "washerwoman", "quarry worker"],
    "craftsman": ["smith", "tailor", "miller", "leatherworker", "carpenter", "guard"],
    "merchant": ["cloth merchant", "spice trader", "innkeeper", "scribe", "moneylender"],
    "noble": ["household lady", "landholder", "court officer", "temple patron"],
    "ruler": ["a ruling house", "the high seat", "a chief of chiefs"],
}
OCCASION = ["at work", "at market", "on the road", "formal", "off duty"]
FUNCTION = [("civil", 3), ("light field kit", 2), ("heavy field kit", 1)]

# Slot options by dialect. Each string is a garment; the rank supplies material, dye and condition.
SLOT_OPTIONS: dict[str, dict[str, list[str]]] = {
    "under": {"*": ["a linen shift", "a fitted linen shirt", "a wool undertunic", "a long-sleeved chemise"]},
    "torso": {
        "vernacular": ["a belted tunic", "a laced bodice over the shift", "a sleeveless jerkin", "a wrap-front tunic"],
        "tudor": ["a structured bodice", "a fitted doublet", "a laced kirtle bodice", "a boned jacket"],
        "gothic": ["a long fitted cotehardie", "a high-collared gown bodice", "a long buttoned surcoat", "a fitted hooded tunic"],
        "romanesque": ["a heavy rounded tunic", "a thick belted overtunic", "a padded gambeson", "a broad-shouldered wool coat"],
        "byzantine": ["a layered panelled tunic", "a stacked formal tunic", "a panelled dalmatic", "a long tabard over a tunic"],
        "italianate": ["a loose open-necked tunic", "a light fitted bodice", "a draped overtunic", "a short cape over a shirt"],
        "organic": ["a hide wrap bound with cord", "a felted body-following tunic", "a fibre-woven wrap", "an irregular pieced jerkin"],
        "elizabethan": ["a boned pointed bodice", "a fitted jacket with edge ornament", "a stiffened doublet", "a high-necked bodice"],
    },
    "legs": {
        "vernacular": ["loose trousers", "a plain skirt to the ankle", "cross-gartered leggings", "a split working skirt"],
        "tudor": ["a full skirt", "fitted hose under a kirtle", "full trousers gathered at the knee", "a full gathered skirt"],
        "gothic": ["a long straight skirt", "fitted hose", "a long slim gown skirt", "narrow trousers"],
        "romanesque": ["thick wool trousers", "a heavy full skirt", "padded leggings", "a wide wool skirt"],
        "byzantine": ["a long panelled skirt", "straight trousers under a long tunic", "a layered long skirt", "narrow trousers"],
        "italianate": ["light loose trousers", "a light skirt to the calf", "a wrapped skirt", "loose linen trousers"],
        "organic": ["hide leggings", "a wrapped fibre skirt", "cord-bound leggings", "a short pieced skirt over leggings"],
        "elizabethan": ["a full skirt with a stiffened hem", "fitted hose", "a gathered skirt", "narrow trousers"],
    },
    "outer": {"*": ["", "", "a hooded cloak", "a short mantle", "a long coat", "an apron", "a fur-lined mantle",
                    "a hooded shawl pinned across the chest", "a sleeveless overcoat"]},
    "feet": {"*": ["low leather shoes", "tall boots", "ankle boots", "wrapped leather shoes", "hobnailed boots",
                   "soft turned shoes", "sandals bound to the calf"]},
    "hands": {"*": ["", "", "leather gloves", "forearm wraps", "fingerless gloves", "long gloves"]},
    "head": {"*": ["", "", "a linen coif", "a hood", "a wrapped headscarf", "a felt cap", "a simple circlet"]},
    "belt": {"*": ["a plain belt", "a wide belt with a pouch", "a knotted sash", "a tooled belt", "a belt of linked plates"]},
    "accessory": {"*": ["", "a pouch", "a knife at the belt", "a scarf", "a satchel", "a ring of keys",
                        "a wooden bead necklace", "a brooch"]},
}
FIELD_KIT = {
    "light field kit": ["a studded leather jerkin over the tunic", "a boiled leather cuirass with strapped bracers",
                        "a mail shirt worn open over cloth", "a brigandine of plates riveted between cloth layers",
                        "a lamellar of small leather plates laced in rows"],
    "heavy field kit": ["a plate cuirass over mail with pauldrons strapped high", "banded armour with a heavy gorget",
                        "layered lamellar over a long padded coat", "a mail hauberk to the knee under a plated harness"],
}
# Dragonborn: the culture's "lacquered scale" reads as BODY scale on this race. Bronze and plate only.
DRAGONBORN_KIT = {
    "light field kit": ["a boiled leather cuirass with bronze bracers", "a brigandine of bronze plates riveted between cloth",
                        "a lamellar of small bronze plates laced in rows"],
    "heavy field kit": ["a bronze plate cuirass over mail with bronze pauldrons", "banded bronze armour with a heavy gorget",
                        "layered bronze lamellar over a long padded coat"],
}

# DIRECTION_V2 section 3.5: named imperfections at meso scale, on the KIT (Class A/B), where Wrought
# wants its detail, and Spec section 3.5 puts on WORN frames specifically -- fix round 1 had this
# living only in plate_clause, which drops it from every fit plate and dressed exploration frame.
# Drawn exactly 1-in-2 via `rng.random() < 0.5` in `draw_outfit` (not `rng.choice(KIT_WEAR)`, whose
# 1-in-7 empty entry gave 6-in-7 odds, not 1-in-2). KIT_WEAR keeps its leading "" for callers that
# iterate the whole list (a lookup table read); KIT_WEAR_ENTRIES is the non-empty options the coin
# flip actually draws from.
KIT_WEAR = ["", "the sleeve creased at the elbow", "a scuffed boot toe", "one rivet dented",
            "a strap twisted", "the hem frayed", "a seam re-stitched in a different thread"]
KIT_WEAR_ENTRIES = [w for w in KIT_WEAR if w]

ASSET_KINDS = ("weapon", "shoes", "armour", "equipment", "accessory")
ASSET_OPTIONS: dict[str, list[str]] = {
    "weapon": ["a hand axe with a wrapped haft", "a long knife in a tooled sheath", "a short sword with a plain crossguard",
               "a spear with a leaf blade", "a recurve bow and a quiver", "a war hammer with a bronze head",
               "a heavy falchion", "a quarterstaff shod in iron", "a sling and a pouch of stones", "a hooked bill"],
    "shoes": ["low leather shoes with a toggle", "tall riding boots", "hobnailed working boots", "soft turned shoes",
              "sandals bound to the calf", "ankle boots with a side lace", "fur-lined winter boots", "wrapped leather shoes"],
    "armour": ["a boiled leather cuirass", "a mail shirt", "a brigandine of riveted plates", "a plate cuirass with pauldrons",
               "a padded gambeson", "a lamellar coat", "a banded cuirass with a gorget", "a leather jerkin with studs"],
    "equipment": ["a pack harness with rolled blanket", "a water skin and a tin cup", "a coil of rope and a grapnel",
                  "a lantern and a tinderbox", "a tool roll of chisels", "a leather satchel of scrolls",
                  "a smith's apron and tongs", "a folding camp stool"],
    "accessory": ["a tooled belt with a pouch", "a brooch of worked metal", "a bead necklace", "a ring of iron keys",
                  "a wrapped headscarf", "a pair of long gloves", "a scarf of undyed wool", "a bone hairpin"],
}
# Fix round 1 (plan-seeded issue): ASSET_OPTIONS["armour"] never contained the word "scale" in the
# first place, so `draw_asset`'s scale-word filter matched nothing and a dragonborn armour plate
# could draw any of the eight generic options -- the same "reads as body scale" problem DRAGONBORN_
# KIT exists to prevent on the worn wardrobe, unaddressed on the standalone asset plate. Dragonborn
# armour plates draw from this bronze/plate/lamellar list instead.
DRAGONBORN_ARMOUR_OPTIONS = ["a bronze plate cuirass with pauldrons", "a banded bronze cuirass with a gorget",
                             "a lamellar coat of small bronze plates", "a boiled leather cuirass with bronze bracers",
                             "a brigandine of bronze plates riveted between cloth"]


# The canonical nine-slot order, used everywhere the slot order is spelled out (fix round 1, minor
# 5): `_garments()`'s join and `worn_clause()`'s garment join both read from here instead of each
# keeping (and risking disagreeing on) their own copy.
SLOTS = ("under", "torso", "legs", "outer", "feet", "hands", "head", "belt", "accessory")

# worn_clause's WORKING budget -- well under the 45-word HARD cap the class contract promises.
# Fix round 1 (controller ruling): torso, legs, feet and -- whenever the outfit calls for one --
# the field-kit `outer` are REQUIRED and always stated regardless of budget pressure (a worn frame
# must never be missing body coverage, and a field-kit armour slot must never lose to the budget
# on half its draws, which the old flat 22-word greedy fill did). under/hands/head/belt/accessory
# are OPTIONAL and are added, in that order, only while the running total still fits inside
# WORN_CLAUSE_TARGET; the race's materials fill whatever is left after that. Dialect NAME, rank and
# dye stay in the prefix (dye came back in this round too -- register is more than a garment list).
WORN_CLAUSE_TARGET = 32
_REQUIRED_SLOTS = ("torso", "legs", "feet")
_OPTIONAL_SLOT_ORDER = ("under", "hands", "head", "belt", "accessory")


@dataclass
class Outfit:
    race: str
    dialect: str
    rank: str
    profession: str
    occasion: str
    function: str
    condition: str
    dye: str
    materials: str
    slots: dict[str, str] = field(default_factory=dict)
    kit_wear: str = ""

    def key(self) -> str:
        return "|".join([self.dialect, self.rank, self.function] + [self.slots[s] for s in sorted(self.slots)])

    def _garments(self) -> str:
        return ", ".join(self.slots[s] for s in SLOTS if self.slots.get(s))

    def worn_clause(self) -> str:
        """What she wears, said once, under 45 words: dialect NAME, rank, dye, the slots, one wear.

        torso/legs/feet, and `outer` whenever the outfit is in a field kit, are REQUIRED -- always
        stated, budget or no budget, so a worn frame never drops body coverage or a field-kit armour
        slot. under/hands/head/belt/accessory are OPTIONAL, added in that order only while the
        running total still fits `WORN_CLAUSE_TARGET`; the race's materials fill whatever is left.
        The ornament sentence stays in `plate_clause` (no word cap there) -- dye is short enough to
        keep here, ornament is not. A meso-scale kit_wear (DIRECTION_V2 3.5, drawn 1-in-2 in
        `draw_outfit`) is appended whenever one was drawn. `set(outfit.slots)` still names all nine
        regardless of what the sentence had room to say, and the 45-word hard cap is enforced as a
        final safety clamp even though the required content alone never measured above it."""
        prefix_words = [self.dialect + ",", self.rank + ",", self.dye + ":"]
        required = list(_REQUIRED_SLOTS)
        if self.function != "civil":
            required.append("outer")
        included = {s for s in required if self.slots.get(s)}
        wear = f", {self.kit_wear}" if self.kit_wear else ""
        used = (len(" ".join(prefix_words).split())
                + sum(len(self.slots[s].split()) for s in included)
                + len(self.kit_wear.split()))
        remaining = WORN_CLAUSE_TARGET - used
        for slot in _OPTIONAL_SLOT_ORDER:
            text = self.slots.get(slot, "")
            n = len(text.split())
            if text and n <= remaining:
                included.add(slot)
                remaining -= n
        garments = ", ".join(self.slots[s] for s in SLOTS if s in included)
        kept, used_m = [], 0
        materials_budget = max(0, remaining)
        for item in (i.strip() for i in self.materials.split(",")):
            n = len(item.split())
            if item and used_m + n <= materials_budget:
                kept.append(item)
                used_m += n
        tail = f"; {', '.join(kept)}" if kept else ""
        clause = f"{' '.join(prefix_words)} {garments}{wear}{tail}"
        words = clause.split()
        return " ".join(words[:45]) if len(words) > 45 else clause

    def plate_clause(self) -> str:
        """The same garments alone: Guide section 7.5, the clothes-only product plate.

        No word cap here (only the WORN clause has one), so the full dye/ornament/condition
        sentences and the same meso-scale kit_wear worn_clause states all get to run in full."""
        wear = f", {self.kit_wear}" if self.kit_wear else ""
        # Dry-run fix round 1 (Task 11, measured on the Lane B smoke render): "an empty mannequin"
        # alone still rendered as a dark human silhouette with a head and neck above the collar.
        # Stated positively -- "mannequin with no head" -- rather than trusting the negative alone.
        return (f"{self.rank} {self.dialect} clothes on an empty mannequin with no head, front view, "
                f"the garments alone with no figure: {self._garments()}{wear}; {self.dye}, "
                f"{ORNAMENT_BY_RANK[self.rank]}, {self.condition}; materials: {self.materials}")

    def caption(self) -> str:
        return f"{self.rank} {self.dialect} outfit, {self._garments()}, {self.condition}"


def _weighted(rng: random.Random, options: list[tuple[str, int]]) -> str:
    return rng.choices([t for t, _ in options], weights=[w for _, w in options], k=1)[0]


def _slot(rng: random.Random, slot: str, dialect: str) -> str:
    table = SLOT_OPTIONS[slot]
    return rng.choice(table.get(dialect) or table["*"])


def draw_outfit(race: str, rng: random.Random, materials: str, dialect: str | None = None,
                rank: str | None = None) -> Outfit:
    dialect = dialect or rng.choice(RACE_DIALECTS.get(race, ["vernacular"]))
    rank = rank or _weighted(rng, RANKS)
    function = _weighted(rng, FUNCTION)
    slots = {s: _slot(rng, s, dialect) for s in SLOT_OPTIONS}
    if function != "civil":
        kit = DRAGONBORN_KIT if race == "dragonborn" else FIELD_KIT
        slots["outer"] = rng.choice(kit[function])
    if race == "dragonborn":
        for k, val in slots.items():
            assert "scale" not in val.lower(), (k, val)
    materials = ", ".join(m for m in materials.split(", ") if "scale" not in m.lower()) if race == "dragonborn" else materials
    # Exactly 1-in-2, not KIT_WEAR's own 1-in-7 empty-entry ratio (fix round 1).
    kit_wear = rng.choice(KIT_WEAR_ENTRIES) if rng.random() < 0.5 else ""
    return Outfit(race=race, dialect=dialect, rank=rank, profession=rng.choice(PROFESSION_BY_RANK[rank]),
                  occasion=rng.choice(OCCASION), function=function,
                  condition=rng.choice(CONDITION_BY_RANK[rank]), dye=DYE_BY_RANK[rank],
                  materials=materials, slots=slots, kit_wear=kit_wear)


@dataclass
class Asset:
    kind: str
    race: str
    name: str
    clause: str
    plate_clause: str
    caption: str


def draw_asset(kind: str, race: str, rng: random.Random, materials: str) -> Asset:
    """One standalone asset for a Lane-B plate: weapon, shoes, armour, equipment, accessory."""
    if kind not in ASSET_KINDS:
        raise ValueError(f"unknown asset kind {kind!r}; one of {ASSET_KINDS}")
    if race == "dragonborn":
        materials = ", ".join(m for m in materials.split(", ") if "scale" not in m.lower())
        options = (DRAGONBORN_ARMOUR_OPTIONS if kind == "armour"
                   else [o for o in ASSET_OPTIONS[kind] if "scale" not in o.lower()])
    else:
        options = ASSET_OPTIONS[kind]
    name = rng.choice(options)
    rank = _weighted(rng, RANKS)
    clause = f"{name}, {rank} register, {DYE_BY_RANK[rank]}, {rng.choice(CONDITION_BY_RANK[rank])}, materials: {materials}"
    plate = (f"{clause}, alone on a plain dark ground, front view, no figure, the object fills the frame, "
             f"every material reads as its real substance")
    return Asset(kind=kind, race=race, name=name, clause=clause, plate_clause=plate,
                 caption=f"{kind}, {name}, {rank} register")
