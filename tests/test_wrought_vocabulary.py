"""Every vocabulary rule in DIRECTION_V2 section 4, enforced on the tree (Doc 50 rule 10).

Hermetic: the vocabulary is pure Python. Random draws use fixed seeds and a few hundred samples so a
weighted axis is exercised, not one lucky draw.
"""
from __future__ import annotations

import json
import random
import re
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
        # OWNER 2026-09-06: the face is human skin, the body below the jaw is one scaled hide
        # (the named-places pattern rendered as a sleeve and a throat plate). Face sentence first,
        # the hide second, the inherited colour third.
        assert pick["skin"].startswith("the face is") and pick["skin"].endswith("human skin"), pick["skin"]
        assert line.index(pick["skin"]) < line.index("one unbroken hide") < line.index("dragon ancestry")
        assert "no bare skin below the jaw" in line and "nowhere on the clothing" in line
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


# --- Task 6: hair as a generator -----------------------------------------------------------------

def test_hair_module_covers_every_race_with_bible_styles():
    import wrought_hair as h
    for race in v.RACE_PHYSIOLOGY:
        assert len(h.STYLES_BY_RACE[race]) >= 6, race
        assert h.ADORNMENT_BY_RACE[race], race
    assert "warrior braids" in " ".join(h.STYLES_BY_RACE["orc"])
    assert "scrap-metal clips" in " ".join(h.STYLES_BY_RACE["goblin"])
    assert "half-up crown" in " ".join(h.STYLES_BY_RACE["dark_elf"])


def test_hair_clause_shape_and_no_shaved_women():
    import wrought_hair as h
    rng = random.Random(2)
    for race in v.RACE_PHYSIOLOGY:
        for _ in range(60):
            clause = h.draw_hair(race, "woman", rng, "auburn", "thick and wavy")
            assert clause.startswith("a full head of auburn hair")
            assert "thick and wavy" in clause
            for shaved in h.SHAVED_FOR_WOMEN:
                assert shaved not in clause


def test_hair_variety_is_not_braids_every_time():
    import wrought_hair as h
    rng = random.Random(4)
    clauses = [h.draw_hair("human", "woman", rng, "black", "straight") for _ in range(200)]
    braided = sum("braid" in c for c in clauses) / len(clauses)
    assert braided <= 0.40, braided
    assert len(set(clauses)) >= 150


# --- Task 7: the wardrobe as dialect x register x slots x dye, plus asset plates -----------------

def test_wardrobe_dialects_and_ranks_follow_the_clothing_guide():
    import wrought_wardrobe as w
    for d in ("gothic", "tudor", "vernacular", "romanesque", "byzantine", "organic", "italianate"):
        assert d in w.DIALECTS, d
    assert [r for r, _ in w.RANKS] == ["labourer", "craftsman", "merchant", "noble", "ruler"]
    assert "undyed" in w.DYE_BY_RANK["labourer"] and "costly" in w.DYE_BY_RANK["noble"]


def test_outfit_has_every_slot_and_fits_the_word_budget():
    import wrought_wardrobe as w
    rng = random.Random(6)
    for race in v.RACE_PHYSIOLOGY:
        for _ in range(60):
            o = w.draw_outfit(race, rng, CULTURE["materials"])
            assert set(o.slots) >= {"under", "torso", "legs", "outer", "feet", "hands", "head", "belt", "accessory"}
            assert len(o.worn_clause().split()) <= 45, o.worn_clause()
            assert o.rank in dict(w.RANKS) and o.dialect in w.DIALECTS
            assert "mannequin" in o.plate_clause() and "front view" in o.plate_clause()


def test_dragonborn_wardrobe_and_armour_never_say_scale():
    import wrought_wardrobe as w
    rng = random.Random(7)
    for _ in range(200):
        assert "scale" not in w.draw_outfit("dragonborn", rng, "lacquered scale, heavy bronze").worn_clause().lower()
        assert "scale" not in w.draw_asset("armour", "dragonborn", rng, "lacquered scale").clause.lower()


def test_two_hundred_outfits_are_not_the_same_outfit():
    import wrought_wardrobe as w
    rng = random.Random(8)
    keys = {w.draw_outfit("human", rng, "wool, linen, iron").key() for _ in range(200)}
    assert len(keys) >= 180
    torsos = [w.draw_outfit("human", rng, "wool, linen, iron").slots["torso"] for _ in range(200)]
    assert max(torsos.count(t) for t in set(torsos)) <= 40, "no single torso garment on more than a fifth"


def test_every_asset_kind_draws_for_every_race():
    import wrought_wardrobe as w
    rng = random.Random(9)
    for kind in w.ASSET_KINDS:
        for race in v.RACE_PHYSIOLOGY:
            a = w.draw_asset(kind, race, rng, CULTURE["materials"])
            assert a.kind == kind and a.clause and "front view" in a.plate_clause
            assert "no figure" in a.plate_clause or "mannequin" in a.plate_clause


def test_draw_uses_the_wardrobe_generator():
    for pick in draws("human", 20):
        assert pick["tier"] in ("labourer", "craftsman", "merchant", "noble", "ruler")
        assert pick["clothing"] == pick["outfit"].worn_clause()


# --- Task 7 fix round 1: kit wear on worn frames, required slots, bronze-only dragonborn armour --

def test_kit_wear_lands_on_worn_frames_about_half_the_time():
    import wrought_wardrobe as w
    rng = random.Random(31)
    hits = sum(any(k and k in w.draw_outfit("human", rng, "wool, linen").worn_clause() for k in w.KIT_WEAR) for _ in range(400))
    assert 140 <= hits <= 260, hits


def test_field_kit_outer_survives_into_the_worn_clause():
    import wrought_wardrobe as w
    rng = random.Random(32)
    seen = 0
    for _ in range(400):
        o = w.draw_outfit("orc", rng, "tanned hide, iron")
        if o.function != "civil":
            seen += 1
            assert o.slots["outer"] in o.worn_clause(), (o.function, o.worn_clause())
    assert seen >= 100


def test_dragonborn_armour_assets_are_bronze_plate_or_lamellar_only():
    import wrought_wardrobe as w
    rng = random.Random(33)
    for _ in range(100):
        a = w.draw_asset("armour", "dragonborn", rng, "lacquered scale, heavy bronze")
        assert a.name in w.DRAGONBORN_ARMOUR_OPTIONS, a.name


# --- Task 7 fix round 2: a rare over-budget draw is a redraw, not a crashed frame ----------------

def test_prompt_for_redraws_a_rare_over_budget_draw(monkeypatch):
    import generate_wrought_dataset as g
    calls = {"n": 0}
    real = v.budget_for
    def tight_once(race, head=None):
        calls["n"] += 1
        return 1 if calls["n"] == 1 else real(race, head)
    monkeypatch.setattr(v, "budget_for", tight_once)
    prompt, _ = g.prompt_for("dwarf", CULTURE, random.Random(41), "woman")
    assert calls["n"] >= 2 and v.word_count(prompt) <= real("dwarf")


def test_prompt_for_raises_when_the_budget_never_holds(monkeypatch):
    import generate_wrought_dataset as g
    monkeypatch.setattr(v, "budget_for", lambda race, head=None: 1)
    with pytest.raises(ValueError):
        g.prompt_for("dwarf", CULTURE, random.Random(42), "woman")


def test_fifty_seeds_of_dwarf_never_raise():
    import generate_wrought_dataset as g
    for seed in range(50):
        rng = random.Random(1000 + seed)
        for _ in range(40):
            g.prompt_for("dwarf", CULTURE, rng, "woman")


# --- Task 10: Lane A -- the skin plate, then the suit as a reference edit of it ------------------

def test_skin_plate_pick_is_two_piece_a_pose_and_square():
    rng = random.Random(11)
    pick = v.apply_skin_plate(v.draw("orc", rng, "woman"))
    assert "sports bra" in pick["clothing"] and "fitted" in pick["clothing"] and "barefoot" in pick["clothing"]
    assert "A-pose" in pick["framing"] and "square to camera" in pick["framing"]
    assert pick["tier"] == "skin_plate"
    line = v.subject_line("orc", pick, CULTURE)
    assert "arms bare to the shoulder" in line and "the shadow side" not in line


def test_lane_a_prompts_share_the_lead_and_the_suit_says_same_woman():
    import generate_wrought_dataset as g
    # seed 4, not 12: dwarf's own physiology+dimorphism+hair content runs close to the 400-word
    # ceiling under the skin-plate wardrobe (measured 389-397 across seeds 1-14), and seed 12
    # specifically breaches it (406) -- the exact scenario render_lane_a's redraw-on-breach exists
    # for. This direct call has no redraw, so it needs a seed that holds under budget on its own.
    rng = random.Random(4)
    pick = v.apply_skin_plate(v.draw("dwarf", rng, "woman"))
    skin, suit = g.lane_a_prompts("dwarf", CULTURE, pick)
    assert skin.startswith(g.WROUGHT_LEAD) and suit.startswith(g.WROUGHT_LEAD)
    assert "the same woman" in suit and "compression suit" in suit and "mid-grey" in suit
    assert "long-sleeved" in suit
    # Fix round 1 (Important #2): SKIN_PLATE_FRAMING already carries "square to camera" (it is
    # part of every skin-plate pose, suit or not), so asserting that substring alone in `suit`
    # could never fail. Assert on the constant that actually carries the fix, and on a substring
    # unique to it, so the test can distinguish "the fix landed" from "the framing always said this".
    assert "shoulders level, the same A-pose" in v.SUIT_EDIT_INSTRUCTION
    assert "shoulders level" in suit
    assert v.word_count(skin) <= v.budget_for("dwarf") and v.word_count(suit) <= v.budget_for("dwarf")
    for word in BANNED:
        assert word not in skin.lower() and word not in suit.lower()


def test_lane_a_canvas_is_the_a_pose_canvas():
    """896x1344, measured against 002: the same prompt at 1216x1728 scores material_floor 0.030
    against 0.176 here and loses the earth/iron palette. Both dimensions stay divisible by 32."""
    assert v.CANVAS_LANE_A == (896, 1344)
    assert all(d % 32 == 0 for d in v.CANVAS_LANE_A)


def test_lane_a_prompts_hold_for_dragonborn_and_beastfolk():
    # Fix round 1 (Important, plan-seeded): lane_a_prompts used the flat PROMPT_WORD_BUDGET (400),
    # not budget_for(race) -- dragonborn's four owned clauses put its budget at 460, so the flat
    # ceiling refused every dragonborn draw, not just a rare tail seed. Confirms both of the races
    # with a per-race allowance actually clear it now.
    import generate_wrought_dataset as g
    for race in ("dragonborn", "beastfolk"):
        rng = random.Random(51)
        ok = 0
        for _ in range(30):
            try:
                pick = v.apply_skin_plate(v.draw(race, rng, "woman", culture_materials=CULTURE["materials"]))
                skin, suit = g.lane_a_prompts(race, CULTURE, pick)
                ok += 1
            except ValueError:
                pass
        assert ok >= 24, (race, ok)


# --- Fix round 1 (Important): render_lane_a's redraw loop, exercised against a stubbed renderer ---

def _stub_lane_a_pipeline(monkeypatch, g):
    """Replace the render/measure/silhouette machinery with cheap stand-ins so what gets tested here
    is render_lane_a's OWN control flow (redraw on a repeated identity, redraw on a budget breach,
    give up after 8 attempts) -- not a live ComfyUI."""
    from PIL import Image

    def fake_render(endpoint, graph, target):
        Image.new("RGB", (64, 96)).save(target)
        return True

    monkeypatch.setattr(g.wc, "render", fake_render)
    monkeypatch.setattr(g, "measure", lambda png: {})
    monkeypatch.setattr(g, "verdict", lambda row, organic=True: [])
    monkeypatch.setattr(g.measures, "silhouette_delta", lambda a, b: {})
    monkeypatch.setattr(g.measures, "face_identity", lambda a, b: {})


class _FakeEndpoint:
    api = "fake"

    def upload(self, path):
        return "ref.png"

    def upload_reference(self, path, max_side=(768, 1088)):
        return "ref.png"

    def free_ram_gb(self):
        return 40.0


def test_render_lane_a_produces_a_record_with_both_files(monkeypatch, tmp_path):
    import generate_wrought_dataset as g
    import types
    _stub_lane_a_pipeline(monkeypatch, g)
    registry = v.IdentityRegistry(tmp_path / "_identities.json")
    args = types.SimpleNamespace(steps=52, cfg=3.5, model=None)
    record = g.render_lane_a(_FakeEndpoint(), "orc", CULTURE, random.Random(1), 0, 1000,
                             tmp_path, registry, args)
    assert record is not None
    assert record["files"]["skin"] == "000_skin.png"
    assert record["files"]["suit"] == "000_suit.png"
    assert registry.seen(record["identity_key"])


def test_render_lane_a_gives_up_after_eight_draws_of_a_seen_identity(monkeypatch, tmp_path):
    import generate_wrought_dataset as g
    import types
    _stub_lane_a_pipeline(monkeypatch, g)
    monkeypatch.setattr(g.variants, "identity_key", lambda pick: "same")
    registry = v.IdentityRegistry(tmp_path / "_identities.json")
    registry.add("same", "x")
    args = types.SimpleNamespace(steps=52, cfg=3.5, model=None)
    result = g.render_lane_a(_FakeEndpoint(), "orc", CULTURE, random.Random(2), 0, 1000,
                             tmp_path, registry, args)
    assert result is None


def test_render_lane_a_redraws_past_a_budget_breach(monkeypatch, tmp_path):
    import generate_wrought_dataset as g
    import types
    _stub_lane_a_pipeline(monkeypatch, g)
    real_budget_for = g.variants.budget_for
    calls = {"n": 0}

    def tight_then_real(race, head=None, fur=None):
        calls["n"] += 1
        return 1 if calls["n"] <= 2 else real_budget_for(race, head, fur=fur)

    monkeypatch.setattr(g.variants, "budget_for", tight_then_real)
    registry = v.IdentityRegistry(tmp_path / "_identities.json")
    args = types.SimpleNamespace(steps=52, cfg=3.5, model=None)
    record = g.render_lane_a(_FakeEndpoint(), "orc", CULTURE, random.Random(3), 0, 1000,
                             tmp_path, registry, args)
    assert record is not None
    assert calls["n"] >= 2


# --- Task 11: Lane B -- asset plates (garment/weapon alone) and fit plates ------------------------

def test_composition_axis_is_mostly_square_and_names_candid_features():
    rng = random.Random(13)
    picks = [v.composition_for(rng) for _ in range(500)]
    square = sum("square to camera" in p for p in picks) / len(picks)
    assert 0.50 <= square <= 0.70
    candid = [p for p in picks if "square to camera" not in p]
    assert all(("hip" in p or "off-centre" in p or "gaze" in p) for p in candid)


def test_lane_b_asset_prompt_has_no_figure_and_the_lead():
    import generate_wrought_dataset as g
    rng = random.Random(14)
    for kind in ("outfit", "weapon", "shoes", "armour", "equipment", "accessory"):
        prompt, meta = g.lane_b_prompt(kind, "dwarf", CULTURE, rng, fit=False)
        assert prompt.startswith(g.WROUGHT_LEAD) and prompt.endswith(g.WROUGHT_TAIL)
        assert "front view" in prompt and ("mannequin" in prompt or "no figure" in prompt)
        assert v.word_count(prompt) <= v.PROMPT_WORD_BUDGET
        assert meta["kind"] == kind


def test_lane_b_fit_prompt_dresses_a_drawn_character_in_the_same_outfit():
    import generate_wrought_dataset as g
    rng = random.Random(15)
    prompt, meta = g.lane_b_prompt("outfit", "human", CULTURE, rng, fit=True)
    assert meta["outfit"]["slots"]["torso"] in prompt
    assert "fully clothed" in prompt and meta["variation"]["nation"]


# --- Task 11 fix round 1: --fit + a stray --asset, the Lane B banned-word sweep, render_lane_b ---

def test_fit_refuses_a_stray_asset():
    # Important #1: --fit always renders the drawn OUTFIT worn by a character; before this fix a
    # `--fit --asset weapon` silently rendered the outfit anyway, with no warning that --asset was
    # ignored. validate_args is the extracted, hermetic surface -- no need to spawn main() with a
    # monkeypatched sys.argv to exercise the same argparse.error() path.
    import argparse
    import generate_wrought_dataset as g
    parser = argparse.ArgumentParser()
    with pytest.raises(SystemExit) as excinfo:
        g.validate_args(argparse.Namespace(lane="b", fit=True, asset="weapon"), parser)
    assert excinfo.value.code == 2
    # Every combination that should NOT raise:
    g.validate_args(argparse.Namespace(lane="b", fit=True, asset="outfit"), parser)
    g.validate_args(argparse.Namespace(lane="b", fit=False, asset="weapon"), parser)
    g.validate_args(argparse.Namespace(lane="a", fit=True, asset="weapon"), parser)
    g.validate_args(argparse.Namespace(lane="legacy", fit=True, asset="weapon"), parser)


def test_banned_words_never_reach_a_lane_b_prompt():
    import generate_wrought_dataset as g
    rng = random.Random(16)
    for race in v.RACE_PHYSIOLOGY:
        for kind in ("outfit", *g.wardrobe.ASSET_KINDS):
            for _ in range(10):
                prompt, _ = g.lane_b_prompt(kind, race, CULTURE, rng, fit=False)
                low = prompt.lower()
                for word in BANNED:
                    assert word not in low, (race, kind, word)
        for _ in range(10):
            prompt, _ = g.lane_b_prompt("outfit", race, CULTURE, rng, fit=True)
            low = prompt.lower()
            for word in BANNED:
                assert word not in low, (race, "fit", word)


def _stub_lane_b_render(monkeypatch, g):
    """Cheap stand-ins for render_lane_b's own control flow -- what gets tested here is the
    canvas/negative/record shape and the identity-registry redraw, not a live ComfyUI. Stashes the
    last graph submitted to wc.render so the negative actually built can be inspected (node "6" is
    the CLIPTextEncode carrying the negative -- see wrought_comfy._base)."""
    from PIL import Image
    captured: dict = {}

    def fake_render(endpoint, graph, target):
        captured["graph"] = graph
        Image.new("RGB", (64, 96)).save(target)
        return True

    monkeypatch.setattr(g.wc, "render", fake_render)
    monkeypatch.setattr(g, "measure", lambda png: {})
    monkeypatch.setattr(g, "verdict", lambda row, organic=False: [])
    return captured


def test_render_lane_b_asset_plate_writes_expected_files_and_negative(monkeypatch, tmp_path):
    import generate_wrought_dataset as g
    import types
    captured = _stub_lane_b_render(monkeypatch, g)
    args = types.SimpleNamespace(asset="weapon", fit=False, steps=52, cfg=3.5, model=None)
    record = g.render_lane_b(_FakeEndpoint(), "orc", CULTURE, random.Random(1), 0, 1000,
                             tmp_path, args)
    assert record is not None
    assert record["lane"] == "b" and record["kind"] == "weapon"
    assert record["canvas"] == [768, 1024]
    assert (tmp_path / "000_weapon.png").exists() and (tmp_path / "000.json").exists()
    assert "mannequin head" in captured["graph"]["6"]["inputs"]["text"]


def test_render_lane_b_fit_plate_writes_expected_files_and_negative(monkeypatch, tmp_path):
    import generate_wrought_dataset as g
    import types
    captured = _stub_lane_b_render(monkeypatch, g)
    registry = v.IdentityRegistry(tmp_path / "_identities.json")
    args = types.SimpleNamespace(asset="outfit", fit=True, steps=52, cfg=3.5, model=None)
    record = g.render_lane_b(_FakeEndpoint(), "orc", CULTURE, random.Random(1), 0, 1000,
                             tmp_path, args, registry)
    assert record is not None
    assert record["canvas"] == [768, 1344]
    assert "variation" in record and "identity_key" in record
    assert (tmp_path / "000_fit.png").exists()
    assert "mannequin head" not in captured["graph"]["6"]["inputs"]["text"]
    assert registry.seen(record["identity_key"])


def test_render_lane_b_fit_gives_up_when_every_identity_is_seen(monkeypatch, tmp_path):
    # Folded minor (Task 11 fix round 1): a fit plate is a character and goes through the identity
    # registry like Lane A -- a batch that has already seen every identity a race's vocabulary can
    # produce must give up rather than render a repeat, the same contract render_lane_a upholds.
    import generate_wrought_dataset as g
    import types
    _stub_lane_b_render(monkeypatch, g)
    monkeypatch.setattr(g.variants, "identity_key", lambda pick: "same")
    registry = v.IdentityRegistry(tmp_path / "_identities.json")
    registry.add("same", "x")
    args = types.SimpleNamespace(asset="outfit", fit=True, steps=52, cfg=3.5, model=None)
    result = g.render_lane_b(_FakeEndpoint(), "orc", CULTURE, random.Random(2), 0, 1000,
                             tmp_path, args, registry)
    assert result is None


# --- Task 12: captions and picks for v2 records ---------------------------------------------------

def _lane_a_record():
    rng = random.Random(16)
    pick = v.apply_skin_plate(v.draw("orc", rng, "woman"))
    return {"lane": "a", "race": "orc", "variation": {k: (x.__dict__ if hasattr(x, "__dict__") else x)
                                                       for k, x in pick.items()}}


def test_caption_v2_lane_a_names_the_plate_kind_and_the_identity():
    import audit_wrought_night as a
    rec = _lane_a_record()
    skin, suit = a.caption_for("orc", rec, "skin"), a.caption_for("orc", rec, "suit")
    assert skin.startswith("wrought style, a single orc woman") and "sports bra" in skin
    assert "compression suit" in suit and rec["variation"]["skin"] in suit
    assert "WROUGHT" not in skin and "WROUGHT" not in suit
    for word in BANNED:
        assert word not in skin.lower()


def test_caption_v2_lane_b_asset_and_fit():
    import audit_wrought_night as a
    rec = {"lane": "b", "kind": "weapon", "caption": "weapon, a hand axe with a wrapped haft, craftsman register"}
    assert a.caption_for("dwarf", rec) == "wrought style, weapon, a hand axe with a wrapped haft, craftsman register, alone on a dark ground"
    rng = random.Random(17)
    pick = v.draw("human", rng, "woman")
    fit = {"lane": "b", "kind": "fit", "outfit": pick["outfit"].__dict__,
           "variation": {k: (x.__dict__ if hasattr(x, "__dict__") else x) for k, x in pick.items()}}
    c = a.caption_for("human", fit)
    assert c.startswith("wrought style, a single human woman") and pick["outfit"].slots["torso"] in c


# --- Task 12 fix round 1: records_for's v1/v2 branches and the collector's resolution, hermetic ---

def _tiny_png(path: Path, colour: tuple[int, int, int]) -> None:
    from PIL import Image
    Image.new("RGB", (8, 8), colour).save(path)


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def _legacy_variation() -> dict:
    """Every key `caption_for`'s legacy (no-`lane`) branch dereferences without `.get`."""
    return {"sex": "woman", "lineage": "", "skin": "", "face": "", "eyes": "", "build": "average",
            "age": "young adult", "hair": "brown hair", "expression": "neutral",
            "clothing": "plain robes", "condition": "clean", "marks": "",
            "framing": "waist-up portrait", "light": "key light from the left"}


def test_records_for_v1_root_is_one_entry_per_frame(tmp_path):
    import audit_wrought_night as a
    d = tmp_path / "orc_woman"
    d.mkdir()
    _tiny_png(d / "017.png", (10, 20, 30))
    _write_json(d / "017.json", {"file": "017.png", "variation": _legacy_variation()})
    recs = a.records_for(tmp_path)
    assert list(recs) == ["orc"]
    assert len(recs["orc"]) == 1
    assert recs["orc"][0]["_png"] == d / "017.png"
    assert "_which" not in recs["orc"][0]


def test_records_for_v2_lane_a_is_two_entries_for_skin_and_suit(tmp_path):
    import audit_wrought_night as a
    d = tmp_path / "human_woman"
    d.mkdir()
    _tiny_png(d / "000_skin.png", (10, 10, 10))
    _tiny_png(d / "000_suit.png", (200, 200, 200))
    _write_json(d / "000.json", {"lane": "a", "race": "human",
                                 "files": {"skin": "000_skin.png", "suit": "000_suit.png"},
                                 "variation": {"sex": "woman"}})
    recs = a.records_for(tmp_path)
    assert len(recs["human"]) == 2
    by_which = {r.get("_which", "skin"): r for r in recs["human"]}
    assert by_which["skin"]["_png"] == d / "000_skin.png" and "_which" not in by_which["skin"]
    assert by_which["suit"]["_png"] == d / "000_suit.png"


def test_records_for_v2_lane_a_with_no_suit_is_one_entry(tmp_path):
    import audit_wrought_night as a
    d = tmp_path / "human_woman"
    d.mkdir()
    _tiny_png(d / "000_skin.png", (10, 10, 10))
    _write_json(d / "000.json", {"lane": "a", "race": "human",
                                 "files": {"skin": "000_skin.png", "suit": None},
                                 "variation": {"sex": "woman"}})
    recs = a.records_for(tmp_path)
    assert len(recs["human"]) == 1
    assert recs["human"][0]["_png"] == d / "000_skin.png"


def test_records_for_v2_lane_b_is_one_entry_with_race_from_the_record(tmp_path):
    import audit_wrought_night as a
    d = tmp_path / "dwarf_weapon"
    d.mkdir()
    _tiny_png(d / "000_weapon.png", (50, 60, 70))
    _write_json(d / "000.json", {"lane": "b", "race": "dwarf", "kind": "weapon",
                                 "file": "000_weapon.png", "caption": "weapon, a hand axe"})
    recs = a.records_for(tmp_path)
    # The directory is "dwarf_weapon", not "dwarf_woman"/"dwarf_man" -- race must come from the
    # record, not a `.rsplit("_", 1)` on the dir name (that would give "dwarf_weapon").
    assert list(recs) == ["dwarf"]
    assert len(recs["dwarf"]) == 1
    assert recs["dwarf"][0]["_png"] == d / "000_weapon.png"


def test_collect_resolves_both_pick_forms_and_a_suit_pick_copies_the_suit_file(tmp_path):
    import collect_wrought_picks as c
    root_a = tmp_path / "root_a"
    (root_a / "orc_woman").mkdir(parents=True)
    _tiny_png(root_a / "orc_woman" / "017.png", (1, 2, 3))
    _write_json(root_a / "orc_woman" / "017.json", {"file": "017.png", "variation": _legacy_variation()})

    root_b = tmp_path / "root_b"
    (root_b / "human_woman").mkdir(parents=True)
    _tiny_png(root_b / "human_woman" / "000_skin.png", (0, 0, 0))
    _tiny_png(root_b / "human_woman" / "000_suit.png", (255, 255, 255))
    _write_json(root_b / "human_woman" / "000.json",
                {"lane": "a", "race": "human",
                 "files": {"skin": "000_skin.png", "suit": "000_suit.png"},
                 "variation": {"sex": "woman", "build": "average", "age": "young adult",
                               "hair": "brown hair", "light": "key light from the left"}})

    out = tmp_path / "out"
    copied, missing = c.collect(["orc/017", "root_b/human_woman/000_suit"], [root_a, root_b], out)
    assert copied == 2 and missing == []

    v1_png = out / "root_a_orc_017.png"
    v2_png = out / "root_b_human_woman_000_suit.png"
    assert v1_png.exists() and v1_png.with_suffix(".txt").exists()
    assert v2_png.exists() and v2_png.with_suffix(".txt").exists()
    # Stem addressing: the "000_suit" pick must resolve to the SUIT png, not the skin one.
    assert v2_png.read_bytes() == (root_b / "human_woman" / "000_suit.png").read_bytes()
    assert v2_png.read_bytes() != (root_b / "human_woman" / "000_skin.png").read_bytes()
    assert "compression suit" in v2_png.with_suffix(".txt").read_text(encoding="utf-8")


def test_collect_out_default_is_a_dated_directory_under_repo(tmp_path, monkeypatch):
    import collect_wrought_picks as c
    monkeypatch.setattr(c, "REPO", tmp_path)
    picks_file = tmp_path / "picks.txt"
    picks_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["collect_wrought_picks.py", str(picks_file)])

    assert c.main() == 0

    base = tmp_path / "runtime" / "style" / "datasets" / "wrought_v2"
    dirs = list(base.iterdir())
    assert len(dirs) == 1
    assert re.fullmatch(r"train_\d{4}-\d{2}-\d{2}", dirs[0].name), dirs[0].name


def test_collect_out_given_is_used_verbatim(tmp_path, monkeypatch):
    import collect_wrought_picks as c
    monkeypatch.setattr(c, "REPO", tmp_path)
    picks_file = tmp_path / "picks.txt"
    picks_file.write_text("", encoding="utf-8")
    custom_out = tmp_path / "wherever" / "custom_train"
    monkeypatch.setattr(sys, "argv",
                        ["collect_wrought_picks.py", str(picks_file), "--out", str(custom_out)])

    assert c.main() == 0

    assert custom_out.exists()
    assert not (tmp_path / "runtime" / "style").exists()


# --- Task 17A: one out_dir_for(args), Lane A carries head/lineage; the picker reads v2 records ---

def test_out_dir_for_lane_a_carries_head_and_lineage():
    import generate_wrought_dataset as g
    from types import SimpleNamespace
    base = SimpleNamespace(out="R", race="dragonborn", lane="a", head=None, lineage=None, asset="outfit",
                           fit=False, peak=False, suit=False, sex=None)
    assert g.out_dir_for(base).name == "dragonborn_woman"
    assert g.out_dir_for(SimpleNamespace(**{**base.__dict__, "lineage": "red"})).name == "dragonborn_woman_red"
    assert g.out_dir_for(SimpleNamespace(**{**base.__dict__, "head": "draconic", "lineage": "red"})).name == "dragonborn_woman_draconic_red"


def test_out_dir_for_lane_b_and_legacy_are_unchanged():
    import generate_wrought_dataset as g
    from types import SimpleNamespace
    b = SimpleNamespace(out="R", race="dwarf", lane="b", head=None, lineage=None, asset="weapon", fit=False,
                        peak=False, suit=False, sex=None)
    assert g.out_dir_for(b).name == "dwarf_weapon"
    assert g.out_dir_for(SimpleNamespace(**{**b.__dict__, "asset": "outfit", "fit": True})).name == "dwarf_fit"
    legacy = SimpleNamespace(out="R", race="orc", lane="legacy", head=None, lineage="red", asset="outfit",
                             fit=False, peak=True, suit=True, sex="woman")
    assert g.out_dir_for(legacy).name == "orc_peak_suit_red_woman"


def test_picker_rows_for_v2_lane_a_and_b(tmp_path):
    import json
    from PIL import Image
    import build_wrought_picker as bp
    a = tmp_path / "human_woman"; a.mkdir()
    for stem in ("000_skin", "000_suit"):
        Image.new("RGB", (8, 8)).save(a / f"{stem}.png")
    (a / "000.json").write_text(json.dumps({"lane": "a", "race": "human", "index": 0, "files": {"skin": "000_skin.png", "suit": "000_suit.png"},
        "gate": {"skin": {"gate": "WROUGHT"}, "suit": {"gate": "OFF-STYLE"}},
        "measures": {"silhouette": {"waist_delta_px": 3, "hip_delta_px": 5, "ok": True}, "identity": {"ncc": 0.6}},
        "variation": {"sex": "woman", "nation": "monarchy"}}), encoding="utf-8")
    b = tmp_path / "dwarf_weapon"; b.mkdir()
    Image.new("RGB", (8, 8)).save(b / "000_weapon.png")
    (b / "000.json").write_text(json.dumps({"lane": "b", "race": "dwarf", "index": 0, "kind": "weapon", "file": "000_weapon.png",
        "caption": "weapon, a hand axe", "gate": "WROUGHT", "metrics": {}}), encoding="utf-8")
    rows = bp.rows_for(tmp_path)
    kinds = {r["kind"] for r in rows}
    assert kinds == {"a", "weapon"}
    ra = next(r for r in rows if r["kind"] == "a")
    assert len(ra["thumbs"]) == 2 and ra["export"] == [f"{tmp_path.name}/human_woman/000_skin", f"{tmp_path.name}/human_woman/000_suit"]
    assert ra["silhouette"]["ok"] and ra["identity"]["ncc"] == 0.6


def test_picker_rows_for_v1_record_is_one_thumb_and_a_bare_stem_export(tmp_path):
    """Fix round 1 (folded minor): `rows_for`'s v1 (no `lane` key) branch had no test -- a real
    night-run record has no `lane` key at all, one JSON beside one same-stem PNG."""
    import json
    from PIL import Image
    import build_wrought_picker as bp
    d = tmp_path / "orc_woman"; d.mkdir()
    Image.new("RGB", (8, 8)).save(d / "017.png")
    (d / "017.json").write_text(json.dumps({"index": 17, "gate": "WROUGHT", "metrics": {},
        "variation": {"sex": "woman", "build": "average"}}), encoding="utf-8")
    rows = bp.rows_for(tmp_path)
    assert len(rows) == 1
    r = rows[0]
    assert r["kind"] == "v1"
    assert r["thumbs"] == [d / "017.png"]
    assert r["export"] == [f"{tmp_path.name}/orc_woman/017"]


# --- 2026-09-06: Lane A honours --lineage / --head (the ten lineage batches rendered random lineages) --

def test_apply_forks_sets_the_named_lineage_and_head():
    import generate_wrought_dataset as g
    rng = random.Random(7)
    pick = v.apply_skin_plate(v.draw("dragonborn", rng, "woman", culture_materials=CULTURE["materials"]))
    g._apply_forks(pick, "dragonborn", rng, None, "red")
    assert pick["lineage"].startswith("red dragon ancestry"), pick["lineage"]
    g._apply_forks(pick, "dragonborn", rng, "draconic", "silver")
    assert pick["lineage"].startswith("silver dragon ancestry") and pick["head"] == "draconic"
    # A race without a lineage table is untouched.
    human = v.draw("human", rng, "woman", culture_materials=CULTURE["materials"])
    assert g._apply_forks(dict(human), "human", rng, None, "red")["lineage"] == human["lineage"]


def test_lane_a_and_legacy_paths_both_apply_the_forks():
    """The fork must have ONE owner that both paths call -- the Lane A runner drew its pick and never
    read args.lineage, and twenty pairs rendered under the wrong dir names before anyone noticed."""
    import inspect
    import generate_wrought_dataset as g
    assert "_apply_forks(" in inspect.getsource(g.render_lane_a)
    assert "_apply_forks(" in inspect.getsource(g.prompt_for)


# --- Task 15C: the beastfolk fur ladder (owner 2026-09-06: "from none to long full fur coverage") --






def test_out_dir_for_lane_a_carries_subspecies_and_fur():
    import generate_wrought_dataset as g
    from types import SimpleNamespace
    base = dict(out="R", race="beastfolk", lane="a", head=None, lineage=None, asset="outfit", fit=False,
                peak=False, suit=False, sex=None, subspecies=None, fur=None)
    assert g.out_dir_for(SimpleNamespace(**base)).name == "beastfolk_woman"
    assert g.out_dir_for(SimpleNamespace(**{**base, "fur": "plush"})).name == "beastfolk_woman_fur-plush"
    assert g.out_dir_for(SimpleNamespace(**{**base, "subspecies": "leopard", "fur": "long"})).name == "beastfolk_woman_leopard_fur-long"
    assert g.out_dir_for(SimpleNamespace(**{**base, "subspecies": "cycle", "fur": "down"})).name == "beastfolk_woman_fur-down"


# --- v3 beastfolk: the legs are animal, and face kind x fur reach are the two axes ----------------
#
# Rewritten from the owner's four references (deer, wolf, bear, panda), which land in four different
# cells of the grid. The depth ladder these replace asked the wrong question -- see SUBSPECIES.

def test_every_subspecies_has_animal_legs_and_human_head_hair_in_every_cell():
    """The one rule all four owner references share. It holds in every cell, not per species."""
    for name, row in v.SUBSPECIES["beastfolk"].items():
        for face in v.FACE_KINDS:
            for reach in v.FUR_REACHES:
                _, clause = v.subspecies_for("beastfolk", random.Random(0), name, fur=reach, face=face)
                assert v.ANIMAL_LEGS.format(foot=row["foot"]) in clause, (name, face, reach)
                assert v.HEAD_HAIR in clause and "digitigrade" in clause
                assert "no human ear pair" in clause


def test_deer_alone_ends_in_hooves_and_carries_no_claws_on_her_hands():
    deer, _ = v.subspecies_for("beastfolk", random.Random(0), "deer", fur="legs", face="part")
    clause = v.subspecies_for("beastfolk", random.Random(0), "deer", fur="legs", face="part")[1]
    assert "cloven hooves" in clause and "short blunt nails" in clause and "claws" not in clause
    for other in ("wolf", "bear", "lion", "panda", "leopard"):
        c = v.subspecies_for("beastfolk", random.Random(0), other, fur="legs", face="part")[1]
        assert "clawed paws" in c and "cloven" not in c, other


def test_fur_reach_says_what_is_bare_and_marks_only_appear_where_skin_is():
    for name, row in v.SUBSPECIES["beastfolk"].items():
        legs = v.subspecies_for("beastfolk", random.Random(0), name, fur="legs", face="muzzle")[1]
        whole = v.subspecies_for("beastfolk", random.Random(0), name, fur="whole", face="muzzle")[1]
        assert "the torso, the arms and the hands are bare skin" in legs
        assert "human hands with" in legs and "furred hands with" in whole
        # A marking is a fact about BARE skin, so it must not survive into the fully furred cell.
        if row["marks"]:
            assert row["marks"] in legs and row["marks"] not in whole, name


def test_face_kind_muzzle_and_part_are_actually_different_faces():
    muzzle = v.subspecies_for("beastfolk", random.Random(0), "wolf", fur="whole", face="muzzle")[1]
    part = v.subspecies_for("beastfolk", random.Random(0), "wolf", fur="whole", face="part")[1]
    assert "an animal muzzle" in muzzle and "no muzzle" not in muzzle
    assert "no muzzle" in part and "a human face" in part


def test_unknown_reach_or_face_raises_rather_than_falling_back():
    for kwargs in ({"fur": "plush"}, {"face": "human"}, {"fur": "none"}):
        with pytest.raises(ValueError):
            v.subspecies_for("beastfolk", random.Random(0), "wolf", **kwargs)


def test_both_axes_are_drawn_when_unpinned_and_reach_the_subject_line():
    """An unpinned draw is still a valid v3 character: the axes are drawn, not left empty."""
    seen_reach, seen_face = set(), set()
    for seed in range(40):
        pick = v.draw("beastfolk", random.Random(seed), "woman", culture_materials=CULTURE["materials"])
        assert pick["fur"] in v.FUR_REACHES and pick["face_kind"] in v.FACE_KINDS
        seen_reach.add(pick["fur"]); seen_face.add(pick["face_kind"])
        line = v.subject_line("beastfolk", pick, CULTURE)
        assert v.FUR_REACH[pick["fur"]] in line and v.FACE_KIND[pick["face_kind"]] in line
    assert seen_reach == set(v.FUR_REACHES) and seen_face == set(v.FACE_KINDS)


def test_a_pinned_cell_survives_the_round_trip_through_draw_and_subject_line():
    """Task 15C's bug in a new shape: the clause is rebuilt in subject_line, so an axis pinned at
    draw time has to reach it, or the frame renders a different cell than its record claims."""
    for reach in v.FUR_REACHES:
        for face in v.FACE_KINDS:
            pick = v.draw("beastfolk", random.Random(7), "woman", culture_materials=CULTURE["materials"],
                          subspecies="bear", fur=reach, face=face)
            line = v.subject_line("beastfolk", pick, CULTURE)
            assert v.FUR_REACH[reach] in line and v.FACE_KIND[face] in line, (reach, face)


def test_no_cell_says_coat_pelt_or_hide():
    """The model reads "coat" as a garment: the first ladder's velvet rung rendered a velvet jacket
    on 4 of 6 plates. Fur is body fur, never something worn."""
    texts = [*v.FUR_REACH.values(), *v.FACE_KIND.values(), v.HEAD_HAIR, v.FUR_GROWN, v.ANIMAL_LEGS,
             *(row["coat"] for row in v.SUBSPECIES["beastfolk"].values())]
    for text in texts:
        assert not re.search(r"\b(coat|pelt|hide|jacket)\b", text), text


def test_every_v3_cell_fits_the_beastfolk_budget():
    import generate_wrought_dataset as g
    budget = v.budget_for("beastfolk")
    worst = 0
    for name in v.SUBSPECIES["beastfolk"]:
        for face in v.FACE_KINDS:
            for reach in v.FUR_REACHES:
                for seed in range(3):
                    pick = v.apply_skin_plate(v.draw("beastfolk", random.Random(400 + seed), "woman",
                                                     culture_materials=CULTURE["materials"],
                                                     subspecies=name, fur=reach, face=face))
                    skin, suit = g.lane_a_prompts("beastfolk", CULTURE, pick)
                    worst = max(worst, v.word_count(skin))
    assert worst <= budget, worst


def test_out_dir_for_lane_a_carries_the_cell():
    import generate_wrought_dataset as g
    from types import SimpleNamespace
    base = dict(out="R", race="beastfolk", lane="a", head=None, lineage=None, asset="outfit", fit=False,
                peak=False, suit=False, sex=None, subspecies=None, fur=None, face=None)
    assert g.out_dir_for(SimpleNamespace(**base)).name == "beastfolk_woman"
    assert g.out_dir_for(SimpleNamespace(**{**base, "fur": "limbs"})).name == "beastfolk_woman_fur-limbs"
    assert g.out_dir_for(SimpleNamespace(**{**base, "subspecies": "wolf", "fur": "whole", "face": "muzzle"})
                         ).name == "beastfolk_woman_wolf_fur-whole_face-muzzle"
    assert g.out_dir_for(SimpleNamespace(**{**base, "subspecies": "cycle", "fur": "legs"})
                         ).name == "beastfolk_woman_fur-legs"


def test_each_beastfolk_flag_is_refused_on_its_own_for_a_race_without_a_table():
    """Each flag alone, because the --face guard was nested under "subspecies or fur" and so only
    fired when a second flag was also set: `--face muzzle` on an orc reached the renderer."""
    import argparse
    import generate_wrought_dataset as g
    from types import SimpleNamespace
    parser = argparse.ArgumentParser()
    for flag, value in (("subspecies", "wolf"), ("fur", "whole"), ("face", "muzzle")):
        args = SimpleNamespace(lane="a", fit=False, asset="outfit", race="orc",
                               subspecies=None, fur=None, face=None, suit_denoise=None)
        setattr(args, flag, value)
        with pytest.raises(SystemExit):
            g.validate_args(args, parser)
