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


# --------------------------------------------------------------------------- Phase 2a: lifted defaults
# Each entry must reproduce the touched builder's old inline literals VERBATIM (pure lift-and-shift).

def _op(key):
    return fop.operating_point_params(key, "default")


def test_wan_core_defaults_lifted_verbatim():
    assert _op("wan_core") == {
        "steps": 30, "cfg": 5.0, "sampler": "dpmpp_2m", "scheduler": "sgm_uniform", "shift": 5.0,
    }


def test_wan_wrapper_defaults_lifted_verbatim():
    assert _op("wan_wrapper") == {
        "steps": 30, "cfg": 6.0, "scheduler": "unipc", "shift": 5.0, "denoise": 1.0,
    }  # no sampler (WanVideoSampler is scheduler-driven)


def test_wan_diffusers_defaults_lifted_verbatim():
    assert _op("wan_diffusers") == {"steps": 30, "cfg": 5.0}


def test_hunyuan_defaults_lifted_verbatim():
    # shift 7.0 recorded for provenance; the builder keeps it hardcoded (not routed).
    assert _op("hunyuan_video") == {"steps": 20, "cfg": 6.0, "shift": 7.0}


def test_generic_fallback_defaults_retuned():
    # RETUNED (not lifted verbatim): reasoned defaults aligned to the validated video shape --
    # low cfg, history-free sampler, simple scheduler, Wan-aligned shift. Not render-validated.
    got = _op("native_split_generic")
    assert got == {
        "steps": 30, "cfg": 4.5, "sampler": "euler", "scheduler": "simple", "shift": 5.0, "denoise": 1.0,
    }
    assert got["cfg"] == 4.5 and got["sampler"] == "euler" and got["scheduler"] == "simple" and got["shift"] == 5.0, \
        "the retuned generic values (cfg 4.5 / euler / simple / shift 5.0) replaced the noisy 7.0 / dpmpp_2m / karras / 8.0"


# --------------------------------------------------------------------------- Phase 2b: image defaults

def test_flux_image_defaults_lifted_verbatim():
    assert _op("flux_image") == {
        "steps": 20, "cfg": 1.0, "guidance_default": 3.5, "sampler": "euler", "scheduler": "simple",
    }  # cfg/guidance/sampler grounded (pinned); only steps is routed


def test_pixart_image_defaults_lifted_verbatim():
    assert _op("pixart_image") == {"steps": 20, "cfg": 4.5, "sampler": "euler", "scheduler": "normal"}


def test_lumina_image_defaults_lifted_verbatim():
    assert _op("lumina_image") == {
        "steps": 30, "cfg": 4.0, "shift": 6.0, "sampler": "res_multistep", "scheduler": "normal",
    }


def test_zimage_image_defaults_lifted_verbatim():
    assert _op("zimage_image") == {
        "steps": 4, "cfg": 1.0, "shift": 3.0, "sampler": "res_multistep", "scheduler": "simple",
    }  # official Turbo config -- grounded


def test_anima_image_defaults_lifted_verbatim():
    assert _op("anima_image") == {"steps": 30, "cfg": 4.0, "sampler": "er_sde", "scheduler": "simple"}


# --------------------------------------------------------------------------- Phase 3a: operating_point validation

def test_resolve_operating_point_blank_and_valid():
    assert fop.resolve_operating_point("wan", None) == "quality"   # blank -> family default
    assert fop.resolve_operating_point("wan", "") == "quality"
    assert fop.resolve_operating_point("wan", "  ") == "quality"
    assert fop.resolve_operating_point("wan", "fast") == "fast"    # valid -> itself
    assert fop.resolve_operating_point("wan", "quality") == "quality"


def test_resolve_operating_point_unknown_warns_and_falls_back(caplog):
    import logging
    with caplog.at_level(logging.WARNING):
        got = fop.resolve_operating_point("wan", "does_not_exist")
    assert got == "quality", "unknown op for a KNOWN family -> fall back to the default"
    assert any("Unknown operating_point" in r.getMessage() and "does_not_exist" in r.getMessage() for r in caplog.records), \
        "unknown op must emit a fallback WARNING"


def test_resolve_operating_point_unknown_family_is_silent_passthrough(caplog):
    import logging
    with caplog.at_level(logging.WARNING):
        got = fop.resolve_operating_point("nope_family", "whatever")
    assert got == "whatever", "unknown family -> passthrough (nothing to validate against)"
    assert not any("Unknown operating_point" in r.getMessage() for r in caplog.records), "no warning for an unknown family"


def test_resolve_operating_point_leaves_family_defaults_passthrough_intact():
    # The validation layer is SEPARATE: resolve_family_defaults still passes an unknown op through as {}
    # (unchanged contract). Callers resolve the NAME first, then the params.
    assert R("wan", "does_not_exist", {}) == {}


# --------------------------------------------------------------------------- Phase 3a: UI operating-point payload

def test_payload_wan_ships_quality_and_fast():
    p = fop.family_operating_points_payload("wan")
    assert p["default_operating_point"] == "quality"
    assert [op["name"] for op in p["operating_points"]] == ["quality", "fast"]
    fast = next(op for op in p["operating_points"] if op["name"] == "fast")
    assert fast["params"]["steps"] == 4 and fast["params"]["cfg"] == 1.0
    assert fast["params"]["sampler"] == "euler" and fast["params"]["scheduler"] == "simple"
    assert "lora" not in fast["params"] and "acceleration" not in fast["params"], "params must exclude the declarative sub-blocks"
    assert fast["lora"]["accel"] is True and "lightx2v" in fast["lora"]["high"] and "lightx2v" in fast["lora"]["low"]
    assert fast["acceleration"]["type"] == "none"
    quality = next(op for op in p["operating_points"] if op["name"] == "quality")
    assert quality["lora"]["accel"] is False and quality["acceleration"]["type"] == "teacache"


def test_payload_single_point_family():
    p = fop.family_operating_points_payload("hunyuan_video")
    assert p["default_operating_point"] == "default"
    assert [op["name"] for op in p["operating_points"]] == ["default"]
    assert p["operating_points"][0]["params"] == {"steps": 20, "cfg": 6.0, "shift": 7.0}
    assert p["operating_points"][0]["lora"] == {} and p["operating_points"][0]["acceleration"] == {}


def test_payload_empty_for_template_or_unknown_family():
    # LTX is template-driven (no row); an unknown family has none. The UI shows no selector for either.
    for fam in ("ltx", "mochi", "cogvideox", "totally_unknown"):
        p = fop.family_operating_points_payload(fam)
        assert p["operating_points"] == [] and p["default_operating_point"] == "", f"{fam} must ship no points"


def test_payload_is_generically_renderable():
    # The UI contract: >1 point -> render a selector; <=1 -> none. No family names hardcoded.
    assert len(fop.family_operating_points_payload("wan")["operating_points"]) == 2            # selector
    assert len(fop.family_operating_points_payload("hunyuan_video")["operating_points"]) == 1  # single
    assert len(fop.family_operating_points_payload("ltx")["operating_points"]) == 0            # none
