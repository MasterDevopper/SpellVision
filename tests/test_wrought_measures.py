# tests/test_wrought_measures.py
"""The v2 measurements, on synthetic inputs. Hermetic: Jarvis is replaced by a fake `ask`."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "dev"))
sys.path.insert(0, str(ROOT / "python"))

import wrought_tells as t  # noqa: E402
import wrought_measures as m  # noqa: E402


def fake_ask_factory(reply: dict):
    def ask(prompt: str, image: str) -> str:
        return "here you go " + json.dumps(reply) + " done"
    return ask


def test_read_frame_parses_json_out_of_prose(tmp_path):
    img = tmp_path / "a.png"; Image.new("RGB", (64, 96), (40, 40, 40)).save(img)
    r = t.read_frame(img, ask=fake_ask_factory({"ai_tells": ["waxy_skin"], "ai_score": 6}))
    assert r["ai_tells"] == ["waxy_skin"] and r["ai_score"] == 6


def test_read_frame_reports_garbage_as_error(tmp_path):
    img = tmp_path / "a.png"; Image.new("RGB", (64, 96)).save(img)
    r = t.read_frame(img, ask=lambda p, i: "no json here")
    assert "error" in r


def test_read_frame_takes_the_last_json_object_when_the_model_echoes_the_schema(tmp_path):
    img = tmp_path / "a.png"; Image.new("RGB", (64, 96)).save(img)
    reply = 'schema: {"ai_tells": ["none"], "ai_score": 1} ... my answer: {"ai_tells": ["waxy_skin"], "ai_score": 6}'
    r = t.read_frame(img, ask=lambda p, i: reply)
    assert r["ai_tells"] == ["waxy_skin"] and r["ai_score"] == 6


def test_rates_are_per_readable_frame():
    readings = [{"ai_tells": ["waxy_skin", "perfect_symmetry"]}, {"ai_tells": ["waxy_skin"]}, {"error": "x"}]
    r = t.rates(readings)
    assert r["waxy_skin"] == 1.0 and r["perfect_symmetry"] == 0.5 and r["no_grain"] == 0.0


def test_gate_is_change_detection_against_the_keeper_rates():
    keeper = {"n": 18, "rates": {tell: 0.0 for tell in t.TELLS}}
    keeper["rates"].update({"perfect_symmetry": 0.8, "waxy_skin": 0.5, "generic_pretty_face": 0.6})
    at_teacher = [{"ai_tells": ["perfect_symmetry", "waxy_skin"]}] * 6 + [{"ai_tells": ["perfect_symmetry"]}] * 6
    assert t.gate(at_teacher, keeper).ok, "a batch AT the teacher's rates passes"
    worse = [{"ai_tells": ["perfect_symmetry", "waxy_skin", "plastic_skin"]}] * 12
    verdict = t.gate(worse, keeper)
    assert not verdict.ok
    assert {o["tell"] for o in verdict.offending} >= {"plastic_skin", "waxy_skin"}
    off = next(o for o in verdict.offending if o["tell"] == "plastic_skin")
    assert off["limit"] == pytest.approx(t.FLOOR) and off["batch_rate"] == 1.0


def test_gate_rejects_a_batch_it_could_not_read():
    keeper = {"n": 18, "rates": {tell: 0.0 for tell in t.TELLS}}
    v = t.gate([{"error": "x"}] * 12, keeper)
    assert not v.ok and v.offending[0]["tell"] == "_unreadable"
    half = [{"error": "x"}] * 7 + [{"ai_tells": []}] * 5
    assert not t.gate(half, keeper).ok


def test_calibrate_records_the_model(tmp_path):
    img = tmp_path / "a.png"; Image.new("RGB", (64, 96)).save(img)
    out = tmp_path / "keeper.json"
    t.calibrate([img], out, ask=fake_ask_factory({"ai_tells": [], "ai_score": 1}))
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["model"] == "injected"


def test_covary_names_the_axis_value_carrying_the_tell():
    recs = [{"variation": {"tier": "noble", "light": "a"}, "_tells": ["waxy_skin"]},
            {"variation": {"tier": "noble", "light": "b"}, "_tells": ["waxy_skin"]},
            {"variation": {"tier": "labourer", "light": "a"}, "_tells": []},
            {"variation": {"tier": "labourer", "light": "b"}, "_tells": []}]
    top = t.covary(recs, "waxy_skin")
    assert top[0] == ("tier=noble", 1.0)


def test_frames_falls_back_to_rglob_when_the_top_level_has_no_pngs(tmp_path):
    root = tmp_path / "_locks"
    (root / "lock_a").mkdir(parents=True)
    (root / "lock_b").mkdir(parents=True)
    img_a, img_b = root / "lock_a" / "plate.png", root / "lock_b" / "odd_name.png"
    Image.new("RGB", (64, 96)).save(img_a)
    Image.new("RGB", (64, 96)).save(img_b)
    found = t._frames([str(root)])
    assert sorted(found) == sorted([img_a, img_b])


def test_frames_prefers_top_level_pngs_when_present(tmp_path):
    top = tmp_path / "batch"
    top.mkdir()
    (top / "nested").mkdir()
    flat = top / "000.png"
    Image.new("RGB", (64, 96)).save(flat)
    Image.new("RGB", (64, 96)).save(top / "nested" / "001.png")
    found = t._frames([str(top)])
    assert found == [flat]


def test_thumb_is_repo_relative_and_keyed_by_root_and_dir(tmp_path):
    src = tmp_path / "wrought_v2" / "orc_woman" / "000_skin.png"
    src.parent.mkdir(parents=True); Image.new("RGB", (1216, 1728)).save(src)
    out = t.thumb(src)
    assert out.parent.name == "wrought_v2__orc_woman" and out.name == "000_skin.png"
    assert str(out).startswith(str(ROOT / "runtime" / "_jarvis_thumbs"))
    assert max(Image.open(out).size) == 640


def _figure(width=400, height=800, waist=60, hip=120, ground=(12, 12, 14), body=(120, 90, 70)):
    """A dark-ground plate with a synthetic hourglass: known waist and hip widths."""
    img = np.zeros((height, width, 3), dtype=np.uint8); img[:] = ground
    top, bottom = 80, 760
    for y in range(top, bottom):
        f = (y - top) / (bottom - top)
        w = hip if 0.50 <= f <= 0.70 else (waist if 0.35 <= f <= 0.55 else 90)
        img[y, width // 2 - w // 2: width // 2 + w // 2] = body
    return img


def test_widths_find_the_known_waist_and_hip(tmp_path):
    rgb = _figure()
    mask = m.dark_subject_mask(rgb)
    w = m.widths(mask)
    assert abs(w["waist_px"] - 60) <= 2 and abs(w["hip_px"] - 120) <= 2
    assert w["height_px"] == 680


def test_silhouette_delta_between_two_plates(tmp_path):
    a, b = tmp_path / "skin.png", tmp_path / "suit.png"
    Image.fromarray(_figure()).save(a)
    Image.fromarray(_figure(waist=66, hip=118)).save(b)
    d = m.silhouette_delta(a, b)
    assert d["waist_delta_px"] == pytest.approx(6, abs=2) and d["hip_delta_px"] == pytest.approx(2, abs=2)
    assert d["ok"]
    Image.fromarray(_figure(waist=80)).save(b)
    assert not m.silhouette_delta(a, b)["ok"]


def test_face_identity_is_zero_for_the_same_face(tmp_path):
    face = ROOT / "docs" / "pipeline" / "wrought_dataset" / "evidence" / "v2_defects_measured_2026-09-05.jpg"
    if not face.exists():
        pytest.skip("evidence image not present")
    r = m.face_identity(face, face)
    if r.get("face_px_a") is None:
        pytest.skip("no face detected in the evidence sheet")
    assert r["mae"] == 0.0 and r["ncc"] == pytest.approx(1.0, abs=1e-4)


def _a_pose(width=400, height=800, waist=60, hip=120):
    """Torso as before, plus arms attached at the shoulder and diverging outward -- the A-pose."""
    img = _figure(width, height, waist, hip)
    top, bottom = 80, 760
    for y in range(top + 60, top + 420):          # shoulder to mid-thigh
        f = (y - top - 60) / 360
        off = int(45 + 90 * f)                    # arm drifts outward with height
        for side in (-1, 1):
            x = width // 2 + side * off
            img[y, max(0, x - 10): x + 10] = (120, 90, 70)
    return img


def test_widths_measure_the_torso_not_the_arms_on_an_a_pose():
    w = m.widths(m.dark_subject_mask(_a_pose()))
    assert abs(w["waist_px"] - 60) <= 4 and abs(w["hip_px"] - 120) <= 4, w


def test_widths_on_an_empty_mask_returns_zeros():
    mask = np.zeros((100, 100), dtype=bool)
    assert m.widths(mask) == {"height_px": 0, "waist_px": 0, "hip_px": 0, "waist_row": 0, "hip_row": 0}


def test_silhouette_delta_rejects_unequal_plate_widths(tmp_path):
    a, b = tmp_path / "skin.png", tmp_path / "suit_half.png"
    Image.fromarray(_figure()).save(a)
    Image.fromarray(_figure(width=200)).save(b)
    with pytest.raises(ValueError):
        m.silhouette_delta(a, b)


def test_dark_subject_mask_refuses_a_contaminated_border():
    width, height = 400, 800
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:] = (12, 12, 14)
    img[:600, :] = (200, 180, 160)  # bright fill covering 600 of the 800 rows, touching every edge
    with pytest.raises(ValueError):
        m.dark_subject_mask(img)


def test_face_identity_reports_none_for_a_missing_face(tmp_path):
    face = ROOT / "docs" / "pipeline" / "wrought_dataset" / "evidence" / "v2_defects_measured_2026-09-05.jpg"
    if not face.exists():
        pytest.skip("evidence image not present")
    blank = tmp_path / "blank.png"
    Image.new("RGB", (256, 256), (10, 10, 10)).save(blank)
    r = m.face_identity(face, blank)
    if r.get("face_px_a") is None:
        pytest.skip("no face detected in the evidence sheet")
    assert r["mae"] is None and r["face_px_b"] is None


def test_dark_subject_mask_keeps_a_shadow_severed_figure():
    """A torso and legs split by a 12-row black band (a shadow the void swallows) are one figure."""
    img = _figure()
    img[430:442, :] = (12, 12, 14)              # sever the figure just below the waist band
    mask = m.dark_subject_mask(img)
    rows = np.where(mask.any(axis=1))[0]
    assert rows[0] <= 82 and rows[-1] >= 757, "both halves kept"


def test_widths_at_given_rows_reads_those_rows():
    mask = m.dark_subject_mask(_figure())
    w = m.widths(mask, rows=(400, 500))
    assert w["waist_row"] == 400 and w["hip_row"] == 500 and w["waist_px"] > 0


def test_paired_rows_map_fractions_onto_the_second_plate():
    a = m.dark_subject_mask(_figure(height=800))
    b = m.dark_subject_mask(_figure(height=800))
    (wa, ha), (wb, hb) = m.paired_rows(a, b)
    assert (wa, ha) == (wb, hb)
    c = m.dark_subject_mask(np.vstack([_figure(height=800), np.full((100, 400, 3), (12, 12, 14), np.uint8)]))
    (wa2, ha2), (wc_, hc) = m.paired_rows(a, c)
    assert (wa2, ha2) == (wa, ha) and abs(wc_ - wa) <= 1 and abs(hc - ha) <= 1


def test_silhouette_delta_is_paired_and_survives_a_severed_suit(tmp_path):
    a, b = tmp_path / "skin.png", tmp_path / "suit.png"
    Image.fromarray(_figure()).save(a)
    severed = _figure(waist=62, hip=118); severed[430:442, :] = (12, 12, 14)
    Image.fromarray(severed).save(b)
    d = m.silhouette_delta(a, b)
    assert d["paired"] and d["rows"]["skin"] == d["rows"]["suit"]
    assert d["height_delta_px"] <= 2 and d["ok"], d


def test_dark_subject_mask_raises_when_a_second_figure_sits_beside_the_first():
    """Two separate figures side by side -- not a severed one -- must not be silently kept as one."""
    canvas = np.zeros((800, 900, 3), dtype=np.uint8)
    canvas[:] = (12, 12, 14)
    canvas[:, :400] = _figure()
    canvas[:, 500:900] = _figure()
    with pytest.raises(ValueError):
        m.dark_subject_mask(canvas)


def test_widths_search_ignores_a_crotch_gap_outside_the_narrowed_waist_band():
    """A 12px gap cut through the centre column from 50%-62% height sits in the hip band, not the
    narrowed waist band -- neither the waist nor the hip measurement should be disturbed by it."""
    img = _a_pose()
    top, bottom = 80, 760
    height = bottom - top
    y0, y1 = top + int(0.50 * height), top + int(0.62 * height)
    cx = img.shape[1] // 2
    img[y0:y1, cx - 6:cx + 6] = (12, 12, 14)
    w = m.widths(m.dark_subject_mask(img))
    assert abs(w["waist_px"] - 60) <= 4 and abs(w["hip_px"] - 120) <= 4, w


def test_widths_at_given_rows_clamps_rather_than_raises():
    mask = m.dark_subject_mask(_figure())
    w = m.widths(mask, rows=(-99999, mask.shape[0] + 99999))
    assert w["waist_row"] == 0 and w["hip_row"] == mask.shape[0] - 1


def test_dark_subject_mask_keeps_a_leg_sized_fragment_with_low_column_overlap_below_the_body():
    """'Beside' needs BOTH <20% column overlap AND >=50% row overlap -- what a second figure looks
    like, not a severed limb. This fragment is 30% of the largest, sits entirely below it (0% row
    overlap) with ~40% column overlap -- above the 20% column floor -- so it is not 'beside' and
    must be kept, the way orc_woman/000's akimbo leg (48.9% column overlap) needs to be."""
    canvas = np.zeros((960, 450, 3), dtype=np.uint8)
    canvas[:] = (12, 12, 14)
    canvas[20:620, 100:300] = (120, 90, 70)     # the "body": rows 20-619, cols 100-299
    canvas[670:920, 242:386] = (120, 90, 70)    # a leg-sized fragment: 30% of the body's area,
                                                 # ~40% column overlap, 0% row overlap
    mask = m.dark_subject_mask(canvas)
    rows = np.where(mask.any(axis=1))[0]
    assert rows[0] <= 22 and rows[-1] >= 917, "both kept, not refused"


# --- evidence sheets (Task 15B step 5, pulled forward so the fur ladder can be sheeted on arrival) --

def test_evidence_sheet_lays_out_a_grid_and_keeps_a_missing_plate_as_a_labelled_gap(tmp_path):
    from wrought_evidence_sheet import sheet, LABEL_H
    plates = []
    for i in range(3):
        p = tmp_path / f"{i}.png"
        Image.new("RGB", (40, 60), (200, 40 * i, 40)).save(p)
        plates.append(p)
    out = sheet(plates + [tmp_path / "missing.png"], ["a", "b", "c", "gap"], tmp_path / "s.jpg", cols=2, cell=(50, 70))
    im = Image.open(out)
    assert im.size == (2 * 50, 2 * (70 + LABEL_H))
    assert out.stat().st_size <= 2_000_000
    # The gap cell is the MISSING fill, not the ground and not a copy of a neighbour.
    assert im.getpixel((50 + 25, 70 + LABEL_H + 35)) != im.getpixel((25, 35))


def test_evidence_sheet_refuses_mismatched_labels(tmp_path):
    from wrought_evidence_sheet import sheet
    with pytest.raises(ValueError):
        sheet([tmp_path / "x.png"], ["one", "two"], tmp_path / "s.jpg")


# --- Task 15/15B probe questions: JSON parsing only, hermetic (fake `ask`/`ask_pair`) ------------

def test_beast_question_round_trips_through_ask_json(tmp_path):
    img = tmp_path / "a.png"; Image.new("RGB", (64, 96)).save(img)
    reply = {"species": "leopard", "horns": False, "human_ears": False, "fur_body": False}
    r = t.ask_json(img, t.BEAST_QUESTION, ask=fake_ask_factory(reply))
    assert r == reply


def test_dragon_question_round_trips_through_ask_json(tmp_path):
    img = tmp_path / "a.png"; Image.new("RGB", (64, 96)).save(img)
    reply = {"face_skin": "deep brown", "scales_on_skin": True, "scales_on_garment": False,
             "scale_colour": "red", "scale_coverage": "whole"}
    r = t.ask_json(img, t.DRAGON_QUESTION, ask=fake_ask_factory(reply))
    assert r == reply


def test_outfit_question_round_trips_through_ask_json(tmp_path):
    img = tmp_path / "a.png"; Image.new("RGB", (64, 96)).save(img)
    reply = {"outfit": "a long blue gown dress", "hair": "loose wavy dark brown", "candid": True}
    r = t.ask_json(img, t.OUTFIT_QUESTION, ask=fake_ask_factory(reply))
    assert r == reply


def test_figure_question_round_trips_through_ask_json(tmp_path):
    img = tmp_path / "a.png"; Image.new("RGB", (64, 96)).save(img)
    reply = {"figure_present": False, "object": "a leather boot"}
    r = t.ask_json(img, t.FIGURE_QUESTION, ask=fake_ask_factory(reply))
    assert r == reply


def test_same_person_question_round_trips_through_ask_json_pair(tmp_path):
    a = tmp_path / "a.png"; b = tmp_path / "b.png"
    Image.new("RGB", (64, 96)).save(a); Image.new("RGB", (64, 96)).save(b)
    reply = {"same_person": True, "reason": "same face, hair and pose"}
    seen = {}

    def fake_ask_pair(prompt, image_a, image_b):
        seen["images"] = (image_a, image_b)
        return json.dumps(reply)

    r = t.ask_json_pair(a, b, t.SAME_PERSON_QUESTION, ask=fake_ask_pair)
    assert r == reply
    assert seen["images"][0] != seen["images"][1], "both thumbs must be passed, not one twice"


# --- gate --records: the NNN.json beside each frame, and covary's top three per offending tell ---

def test_record_for_finds_the_json_beside_a_suffixed_frame(tmp_path):
    (tmp_path / "000.json").write_text(json.dumps({"variation": {"tier": "noble"}}), encoding="utf-8")
    frame = tmp_path / "000_skin.png"
    Image.new("RGB", (64, 96)).save(frame)
    rec = t._record_for(frame)
    assert rec == {"variation": {"tier": "noble"}}


def test_record_for_returns_none_when_no_json_sits_beside_the_frame(tmp_path):
    frame = tmp_path / "000_skin.png"
    Image.new("RGB", (64, 96)).save(frame)
    assert t._record_for(frame) is None


def test_annotate_covary_names_the_top_axis_value_per_offending_tell(tmp_path):
    for i, tier in enumerate(["noble", "noble", "labourer", "labourer"]):
        (tmp_path / f"{i:03d}.json").write_text(
            json.dumps({"variation": {"tier": tier}}), encoding="utf-8")
    frames = [tmp_path / f"{i:03d}_skin.png" for i in range(4)]
    for f in frames:
        Image.new("RGB", (64, 96)).save(f)
    readings = [{"ai_tells": ["waxy_skin"]}, {"ai_tells": ["waxy_skin"]},
                {"ai_tells": []}, {"ai_tells": []}]
    offending = [{"tell": "waxy_skin", "batch_rate": 0.5, "keeper_rate": 0.0, "limit": 0.25}]
    t.annotate_covary(offending, frames, readings)
    assert offending[0]["covary_top3"][0] == ("tier=noble", 1.0)


def test_annotate_covary_skips_frames_with_no_record_beside_them(tmp_path):
    frame = tmp_path / "000_skin.png"
    Image.new("RGB", (64, 96)).save(frame)
    offending = [{"tell": "waxy_skin", "batch_rate": 1.0, "keeper_rate": 0.0, "limit": 0.25}]
    t.annotate_covary(offending, [frame], [{"ai_tells": ["waxy_skin"]}])
    assert offending[0]["covary_top3"] == []
