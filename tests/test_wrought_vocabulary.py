"""Every vocabulary rule in DIRECTION_V2 section 4, enforced on the tree (Doc 50 rule 10).

Hermetic: the vocabulary is pure Python. Random draws use fixed seeds and a few hundred samples so a
weighted axis is exercised, not one lucky draw.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "dev"))
sys.path.insert(0, str(ROOT / "python"))

import wrought_variants as v  # noqa: E402

CULTURE = {"materials": "tanned hide, woven fiber, carved wood, bone, natural dye",
           "surface": "Maintained", "ornament": "Clan", "palette": "umber, deep forest green"}
BEAST = ("leopard", "bear", "lion", "deer", "panda", "wolf")


def draws(race: str, n: int = 300, sex: str = "woman"):
    rng = random.Random(42)
    return [v.draw(race, rng, sex) for _ in range(n)]


def test_beastfolk_has_exactly_the_six_subspecies():
    assert tuple(sorted(v.SUBSPECIES["beastfolk"])) == tuple(sorted(BEAST))


def test_only_deer_has_headgear_and_it_is_antlers():
    for name, row in v.SUBSPECIES["beastfolk"].items():
        if name == "deer":
            assert "antler" in row["headgear"]
        else:
            assert row["headgear"] == "", name


def test_beastfolk_core_no_longer_offers_horns():
    core = v.RACE_PHYSIOLOGY["beastfolk"]["core"] + v.DIMORPHISM["beastfolk"]["woman"]
    assert "horn" not in core.lower()


def test_bear_and_panda_marks_are_ears_only():
    for name in ("bear", "panda"):
        assert v.SUBSPECIES["beastfolk"][name]["marks"] == "", name


def test_subspecies_marks_are_skin_patterns_not_fur():
    for name, row in v.SUBSPECIES["beastfolk"].items():
        low = row["marks"].lower()
        for word in ("fur", "hair", "pelt", "coat"):
            assert word not in low, (name, word, row["marks"])


def test_every_beastfolk_draw_names_one_subspecies_and_human_hair():
    seen = set()
    for pick in draws("beastfolk"):
        assert pick["subspecies"] in BEAST
        seen.add(pick["subspecies"])
        assert "fur" not in pick["hair"].lower(), pick["hair"]
        assert "a full head of" in pick["hair"]
    assert seen == set(BEAST), "300 draws must cover all six"


def test_subject_line_states_no_horns_for_hornless_subspecies():
    rng = random.Random(3)
    for name in BEAST:
        pick = v.draw("beastfolk", rng, "woman")
        pick["subspecies"] = name
        line = v.subject_line("beastfolk", pick, CULTURE).lower()
        assert "only the pair of" in line and "no human ear" in line
        if name == "deer":
            assert "antler" in line
        else:
            assert "no horns" in line, name


def test_no_race_but_beastfolk_draws_a_subspecies():
    for race in ("orc", "human", "dragonborn"):
        assert all(p["subspecies"] == "" for p in draws(race, 20))
