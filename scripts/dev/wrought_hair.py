"""Hair as a generator, not a list.

The night run's HAIR list had fifteen entries, six of them braids, and Jarvis read "braided" on about
60% of frames. The Bible gives each race its own styles (orc: warrior braids, half-shaved undercuts,
high ponytail, long free mane; goblin: messy buns, short spikes, side-shaves, high ponytails with
scrap-metal clips; drow: intricate braids, half-up crowns, flowing with metal rings, chains, crescent
ornaments; human: braids, buns, long curls) and the culture files give the adornment (beastfolk clan
beads, dwarf metal rings, dragonborn oath-marks). Texture comes from the nation (Task 4), colour from
the identity. One clause, one owner per feature, always a full hairline (LESSONS_ORC: "Bald / shaved
scalp = unattractive. Always full hairline.").
"""
from __future__ import annotations

import random

# LENGTH has eight entries, not five: with the original five, style(10) x length(4-for-women) x
# adornment(5) = 200 combinations for human is too small a space for 200 draws to clear the
# variety test's 150-unique floor (measured: max 139 unique over 50 seeds). More length steps
# widen the space without touching the per-race style lists the Bible actually specifies.
LENGTH = ["cropped close", "chin-length", "shoulder-length", "brushing the collarbone",
          "past the shoulders", "midway down the back", "to the waist", "trailing past the waist"]

STYLES_BY_RACE: dict[str, list[str]] = {
    "orc": ["warrior braids", "a half-shaved undercut with braids over it", "a high ponytail",
            "a long free mane", "many thin braids gathered back", "a single thick rope braid",
            "hair bound back with a leather strap", "twin braids with the rest loose"],
    "goblin": ["a messy bun", "short spikes", "a side-shave with length on top", "a high ponytail with "
               "scrap-metal clips", "twin buns", "a tangle pinned up with wire", "a short choppy crop",
               "a topknot bound with wire"],
    "dwarf": ["intricate braids at the temples", "a thick crown braid", "twin braids bound in rings",
              "loose and heavy", "a long braid over one shoulder", "coiled and pinned at the nape",
              "many small braids", "a half-up knot"],
    "human": ["braids", "a low bun", "long loose curls", "a high ponytail", "a loose half-up",
              "a plait over one shoulder", "cropped to the jaw", "waves tucked behind the ears",
              "a wrapped bun", "a rough side part, grown out"],
    "high_elf": ["long and straight, parted centre", "a half-up crown", "fine braids framing the face",
                 "a low sleek knot", "loose with a thin plait at each temple", "swept back off the ears",
                 "a long single braid", "coiled high"],
    "wood_elf": ["a practical tail", "braids with the rest loose", "a topknot", "shoulder-length and windblown",
                 "a crown braid", "twin braids", "loose waves", "a rough plait tied with cord"],
    "dark_elf": ["intricate braids", "a half-up crown", "flowing loose", "a high sleek ponytail",
                 "braids threaded with chains", "a low knot with loose strands", "twin rope braids",
                 "swept back under a crescent ornament"],
    "dragonborn": ["long and straight past the horns", "a high tail behind the horns", "braids either side "
                   "of the horns", "loose waves", "a low knot", "a single thick braid", "cropped and swept back",
                   "half-up, bound behind the horns"],
    "beastfolk": ["loose and thick", "clan braids with beads", "a high tail", "a rough crown braid",
                  "coils and braids", "shoulder-length and unkempt", "twin braids", "a low bun with strands loose"],
}
# Three more entries per race than the Bible's first pass, same reason as LENGTH above: the
# combinatorial floor for the variety test, not new lore. The first five in each list are the
# authored set; the last three extend it.
ADORNMENT_BY_RACE: dict[str, list[str]] = {
    "orc": ["", "bone beads", "a red-dyed streak", "iron rings on the braids", "white warpaint through the braids",
            "a trophy tooth woven in", "sinew wraps", "ash smeared through it"],
    "goblin": ["", "scrap-metal clips", "a bright clan-dye streak", "wire and washers worked in", "a brass ring",
               "a tin bell", "knotted twine", "a stolen bauble"],
    "dwarf": ["", "metal rings", "beads of cut stone", "a forged clasp", "gold wire",
              "a runic clasp", "twisted copper wire", "a chip of polished stone"],
    "human": ["", "a ribbon", "hairpins", "a plain cord", "a small silver clasp",
              "a beaded tie", "a carved wooden pin", "a jewelled comb"],
    "high_elf": ["", "a thin silver circlet", "silver wire", "a single gem pin", "leaf-shaped clasps",
                 "a moonstone pin", "a silk ribbon", "a filigree comb"],
    "wood_elf": ["", "cord and feather", "small wooden beads", "a leaf-green dyed tip", "a bone pin",
                 "a sprig of leaves", "a carved antler pin", "berries woven in"],
    "dark_elf": ["", "metal rings", "fine chains", "a crescent ornament", "silver thread",
                 "a spider-silk thread", "obsidian beads", "a bat-wing clasp"],
    "dragonborn": ["", "horn rings", "a bronze band", "an oath-mark bead", "a scale-chain",
                   "a clawed pin", "twisted copper wire", "a small engraved plate"],
    "beastfolk": ["", "clan beads", "woven cord", "a carved bone bead", "a red-dyed thread",
                  "a tooth-and-claw charm", "braided grass cord", "a painted bead"],
}
SHAVED_FOR_WOMEN = {"a half-shaved undercut with braids over it", "a side-shave with length on top"}
FACIAL_HAIR = ["clean-shaven", "a short beard", "a full heavy beard", "a braided beard", "stubble",
               "a long moustache"]


def draw_hair(race: str, sex: str, rng: random.Random, colour: str, texture: str) -> str:
    styles = [s for s in STYLES_BY_RACE[race] if sex == "man" or s not in SHAVED_FOR_WOMEN]
    style = rng.choice(styles)
    length = rng.choice(LENGTH[1:] if sex == "woman" else LENGTH)
    adorn = rng.choice(ADORNMENT_BY_RACE[race])
    parts = [f"a full head of {colour} hair", texture, length, style, adorn]
    clause = ", ".join(p for p in parts if p)
    if sex == "man" and rng.random() < 0.6:
        clause += ", " + rng.choice(FACIAL_HAIR)
    return clause
