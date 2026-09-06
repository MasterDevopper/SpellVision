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


def test_dragonborn_skin_clause_owns_the_skin_and_precedes_lineage():
    for pick in draws("dragonborn", 60):
        line = v.subject_line("dragonborn", pick, CULTURE)
        assert pick["skin"].startswith("the skin is"), pick["skin"]
        assert line.index(pick["skin"]) < line.index("dragon ancestry")
        assert "scales are a pattern on that skin" in line
        # RULING 2 2026-09-06: DRAGONBORN_GARMENT trimmed to <=22 words; "no lacquered
        # surface on the clothing" is now "no lacquer on the clothing" -- same fact, said
        # shorter. Updated to match rather than pin stale wording.
        assert "no scale pattern" in line and "no lacquer on the clothing" in line


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


# --- Task 5: the face bundle, the living-skin clause, and the prompt ratchets ------------------

BANNED = ("gorgeous", "flawless", "smooth clear skin", "elegant even features", "perfect",
          "masterpiece", "8k", "ultra detailed", "hyperrealistic", "airbrushed", "beauty filter",
          "dslr", "film grain", "kodak", "fujifilm", "f/1.8", "bokeh", "iphone", "snapshot")


def test_banned_words_never_reach_a_prompt():
    import generate_wrought_dataset as g
    rng = random.Random(9)
    info = CULTURE
    for race in v.RACE_PHYSIOLOGY:
        for _ in range(40):
            positive, _pick = g.prompt_for(race, info, rng, "woman")
            low = positive.lower()
            for word in BANNED:
                assert word not in low, (race, word)


def test_asymmetric_eyes_is_not_a_negative_anywhere():
    import generate_wrought_dataset as g
    assert "asymmetric eyes" not in v.APPEARANCE_NEGATIVE
    assert "asymmetric eyes" not in g.WROUGHT_NEG


def test_every_face_has_one_mark_and_a_stated_asymmetry():
    for race in v.RACE_PHYSIOLOGY:
        for pick in draws(race, 40):
            assert pick["mark"] in v.MARK_FACE
            assert "one brow set a little higher" in pick["face_bundle"] or \
                   any(a in pick["face_bundle"] for a in v.ASYMMETRY)


def test_living_skin_clause_is_in_every_subject_line():
    for race in v.RACE_PHYSIOLOGY:
        for pick in draws(race, 10):
            assert v.LIVING_SKIN in v.subject_line(race, pick, CULTURE)


def test_prompt_word_budget_holds_for_every_race():
    # RULING 3 2026-09-06: per-race allowance (dragonborn +60), not one global -- see
    # variants.budget_for. Track the max per race, not just the overall worst.
    import generate_wrought_dataset as g
    rng = random.Random(5)
    worst_by_race: dict[str, int] = {}
    for race in v.RACE_PHYSIOLOGY:
        for _ in range(60):
            positive, _ = g.prompt_for(race, CULTURE, rng, "woman")
            n = v.word_count(positive)
            worst_by_race[race] = max(worst_by_race.get(race, 0), n)
            assert n <= v.budget_for(race), (race, n)


def test_appearance_tiers_keep_the_owner_weights():
    tiers = [p["appearance"] for p in draws("human", 600)]
    share = {t: tiers.count(t) / len(tiers) for t in set(tiers)}
    assert 0.20 <= share["striking"] <= 0.40 and share["handsome"] >= 0.30
    assert "weathered" not in share
