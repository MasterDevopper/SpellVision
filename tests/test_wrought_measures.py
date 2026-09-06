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
    assert off["limit"] == pytest.approx(0.15) and off["batch_rate"] == 1.0


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


def test_thumb_is_repo_relative_and_keyed_by_root_and_dir(tmp_path):
    src = tmp_path / "wrought_v2" / "orc_woman" / "000_skin.png"
    src.parent.mkdir(parents=True); Image.new("RGB", (1216, 1728)).save(src)
    out = t.thumb(src)
    assert out.parent.name == "wrought_v2__orc_woman" and out.name == "000_skin.png"
    assert str(out).startswith(str(ROOT / "runtime" / "_jarvis_thumbs"))
    assert max(Image.open(out).size) == 640
