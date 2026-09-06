"""Every vocabulary rule in DIRECTION_V2 section 4, enforced on the tree (Doc 50 rule 10).

Hermetic: the vocabulary is pure Python. Random draws use fixed seeds and a few hundred samples so a
weighted axis is exercised, not one lucky draw.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

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


def test_dragonborn_skin_clause_owns_the_skin_and_precedes_lineage():
    for pick in draws("dragonborn", 60):
        line = v.subject_line("dragonborn", pick, CULTURE)
        assert pick["skin"].startswith("the skin is"), pick["skin"]
        assert line.index(pick["skin"]) < line.index("dragon ancestry")
        assert "scales are a pattern on that skin" in line
        assert "no scale pattern" in line and "no lacquered surface on the clothing" in line


def test_lineage_never_states_skin_or_hair_colour():
    for text in v.LINEAGE["dragonborn"].values():
        assert " skin" not in text and "hair" not in text, text


def test_dragonborn_wardrobe_never_asks_for_scale_garments():
    for pick in draws("dragonborn", 200):
        assert "scale" not in pick["clothing"].lower(), pick["clothing"]


def test_dragonborn_clauses_are_gender_neutral():
    rng = random.Random(21)
    for _ in range(30):
        pick = v.draw("dragonborn", rng, "man")
        line = v.subject_line("dragonborn", pick, CULTURE).lower()
        assert " her " not in line and " she " not in line, line


def test_every_race_has_at_least_one_worked_nation_with_skin_and_marker():
    for race in v.RACE_PHYSIOLOGY:
        rows = [r for r in v.NATIONS[race].values() if r]
        assert rows, race
        for r in rows:
            assert r["skin"] and r["marker"] and r["hair_texture"] and r["dialect"], (race, r)


def test_human_nations_are_the_three_kingdoms():
    assert set(v.NATIONS["human"]) >= {"monarchy", "parliament", "republic"}


def test_draw_carries_nation_and_its_skin_family():
    for race in v.RACE_PHYSIOLOGY:
        for pick in draws(race, 60):
            row = v.NATIONS[race][pick["nation"]]
            assert row is not None
            assert pick["skin"] in row["skin"] or race == "dragonborn"


def test_identity_key_is_stable_and_sensitive():
    rng = random.Random(1)
    a = v.draw("orc", rng, "woman")
    assert v.identity_key(a) == v.identity_key(dict(a))
    b = dict(a); b["skin"] = "something else"
    assert v.identity_key(a) != v.identity_key(b)


def test_registry_refuses_a_repeat(tmp_path):
    reg = v.IdentityRegistry(tmp_path / "ids.json")
    assert not reg.seen("k1")
    reg.add("k1", "orc/000")
    assert reg.seen("k1")
    reg2 = v.IdentityRegistry(tmp_path / "ids.json")
    assert reg2.seen("k1"), "persisted across processes"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "DIRECTION_V2 lines 168/236 say the uniqueness hash 'degrades' until face_bundle/mark "
        "exist (Task 5) -- and it measurably does. Task 4 alone bounds human's identity space at "
        "nation(3) x skin|nation(<=4) x hair_colour(7) x eyes(6) = 504 combinations; a 300-draw "
        "sample from a 504-slot space collides by the birthday bound (measured 223/300 unique, "
        "matching the ~226 predicted). Reaching >=295 needs a space in the thousands, which is "
        "exactly what Task 5's face_bundle_for (JAW x CHEEK x BROW x NOSE_BRIDGE x EYE_SHAPE x "
        "LIPS x ASYMMETRY x MARK_FACE, six figures) supplies. Drop this xfail once Task 5 lands --"
        "it should clear 295 by a wide margin, not by a hair."
    ),
)
def test_three_hundred_draws_of_one_race_are_three_hundred_identities():
    keys = {v.identity_key(p) for p in draws("human", 300)}
    assert len(keys) >= 295


def test_head_override_keeps_hair_colour_and_texture():
    import generate_wrought_dataset as g
    rng = random.Random(23)
    _, kemo = g.prompt_for("dragonborn", CULTURE, rng, "woman", head="kemonomimi")
    assert kemo["hair_colour"] in kemo["hair"] and kemo["hair_texture"] in kemo["hair"]
    assert "a full head of" in kemo["hair"]
    _, crest = g.prompt_for("dragonborn", CULTURE, rng, "woman", head="draconic")
    assert "horn" in crest["hair"] and "a full head of" not in crest["hair"]
