"""Unit gates for the per-family operating-point table + resolver (Phase 1, Wan-first)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))
import family_operating_points as fop  # noqa: E402


R = fop.resolve_family_defaults


def test_request_value_wins_over_table():
    assert R("wan", "quality", {"steps": 12})["steps"] == 12          # req 12 beats table 28
    assert R("wan", "quality", {"cfg": 2.5})["cfg"] == 2.5            # req 2.5 beats table 4.0
    assert R("wan", "quality", {"sampler": "dpmpp_2m"})["sampler"] == "dpmpp_2m"  # req beats table euler


def test_table_fills_when_request_absent():
    got = R("wan", "quality", {})
    assert got["steps"] == 28 and got["cfg"] == 4.0
    assert got["sampler"] == "euler" and got["scheduler"] == "simple" and got["shift"] == 5.0


def test_blank_and_auto_sampler_resolve_from_table():
    # THE key case: the UI's "auto" sends "" (normalizeAutoValue). It must resolve from the table.
    assert R("wan", "quality", {"sampler": ""})["sampler"] == "euler"
    assert R("wan", "quality", {"sampler": "auto"})["sampler"] == "euler"
    assert R("wan", "quality", {"scheduler": "  AUTO "})["scheduler"] == "simple"


def test_absent_operating_point_uses_family_default():
    # No operating_point named -> wan default_operating_point ("quality") -> steps 28.
    assert R("wan", None, {})["steps"] == 28
    assert R("wan", "", {})["steps"] == 28
    assert fop.default_operating_point("wan") == "quality"


def test_fast_operating_point_is_the_lightx2v_config():
    fast = R("wan", "fast", {})
    assert fast["steps"] == 4 and fast["cfg"] == 1.0
    assert fast["sampler"] == "euler" and fast["scheduler"] == "simple"
    lora = fop.operating_point_params("wan", "fast")["lora"]
    assert lora["accel"] is True
    assert "lightx2v" in lora["high"] and "high_noise" in lora["high"]
    assert "lightx2v" in lora["low"] and "low_noise" in lora["low"]
    # fast deliberately runs no TeaCache (redundant at 4 steps)
    assert fop.operating_point_params("wan", "fast")["acceleration"]["type"] == "none"


def test_quality_declares_teacache_acceleration():
    accel = fop.operating_point_params("wan", "quality")["acceleration"]
    assert accel["type"] == "teacache" and accel.get("profile") == "balanced"
    assert fop.operating_point_params("wan", "quality")["lora"]["accel"] is False


def test_cfg_and_shift_aliases():
    assert R("wan", "quality", {"guidance_scale": 6.5})["cfg"] == 6.5           # guidance_scale -> cfg
    assert R("wan", "quality", {"model_sampling_shift": 9.0})["shift"] == 9.0   # alias -> shift


def test_falsy_numeric_treated_as_not_provided():
    # steps=0 / cfg=0 are falsy -> resolve from the table (matches the old `req.get(..) or <lit>`).
    assert R("wan", "quality", {"steps": 0})["steps"] == 28
    assert R("wan", "quality", {"cfg": 0})["cfg"] == 4.0


def test_unknown_family_returns_only_request_supplied():
    # Unknown family -> no table; only what the request itself supplied survives (builder literals cover the rest).
    assert R("nope_family", "quality", {}) == {}
    assert R("nope_family", "quality", {"steps": 7}) == {"steps": 7}


def test_unknown_operating_point_is_passthrough_not_crash():
    assert R("wan", "does_not_exist", {}) == {}
    assert R("wan", "does_not_exist", {"cfg": 3.0}) == {"cfg": 3.0}
