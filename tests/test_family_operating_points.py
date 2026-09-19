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
    # Per TASK VARIANT since Phase 4b: this asserted a flat high/low, which is exactly how an i2v
    # job came to be handed the t2v accel pair. tests/test_operating_point_reachability.py owns the
    # pairing rules; this only checks the config is still the lightx2v one.
    for command in ("t2v", "i2v"):
        pair = fop.accel_loras_for(fop.operating_point_params("wan", "fast"), command)
        assert "lightx2v" in pair["high"] and "high_noise" in pair["high"]
        assert "lightx2v" in pair["low"] and "low_noise" in pair["low"]
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
        # W2: "sampler": "" recorded honestly (WanVideoSampler is scheduler-driven and has no
        # sampler_name literal to lift -- an empty string says "no choice to offer", same as the
        # ltx allowlist's empty schedulers tuple).
        "steps": 30, "cfg": 6.0, "sampler": "", "scheduler": "unipc", "shift": 5.0, "denoise": 1.0,
    }


def test_wan_diffusers_defaults_lifted_verbatim():
    # W2: sampler/scheduler recorded empty -- the diffusers WanPipeline path picks its scheduler
    # class in code, not by a ComfyUI-style name, so there is no literal to lift.
    assert _op("wan_diffusers") == {"steps": 30, "cfg": 5.0, "sampler": "", "scheduler": ""}


def test_hunyuan_defaults_lifted_verbatim():
    # shift 7.0 recorded for provenance; the builder keeps it hardcoded (not routed).
    # Distilled guidance lives on `guidance`, not on `cfg`. cfg 1.0 is the pinned KSampler
    # figure; 6.0 is what FluxGuidance actually steers with (family_seed_table, Doc 62 3e).
    assert _op("hunyuan_video") == {
        "steps": 20, "cfg": 1.0, "guidance": 6.0, "shift": 7.0, "sampler": "euler", "scheduler": "simple",
        "width": 832, "height": 480, "frames": 81, "fps": 16,
    }


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
    # W2: width/height added (published canvas, copied from family_seed_table).
    # `guidance` not `guidance_default`: C++ applyResolvedSettings reads `guidance`, and
    # guidance_from_request reads the same key off the table. The old name was recorded-only
    # and unreachable from either.
    assert _op("flux_image") == {
        "steps": 20, "cfg": 1.0, "guidance": 3.5, "sampler": "euler", "scheduler": "simple",
        "width": 1024, "height": 1024,
    }  # cfg/guidance/sampler grounded (pinned); only steps is routed


def test_pixart_image_defaults_lifted_verbatim():
    assert _op("pixart_image") == {
        "steps": 20, "cfg": 4.5, "sampler": "euler", "scheduler": "normal",
        "width": 1024, "height": 1024,
    }


def test_lumina_image_defaults_lifted_verbatim():
    assert _op("lumina_image") == {
        "steps": 30, "cfg": 4.0, "shift": 6.0, "sampler": "res_multistep", "scheduler": "normal",
        "width": 1024, "height": 1024,
    }


def test_zimage_image_defaults_lifted_verbatim():
    assert _op("zimage_image") == {
        "steps": 4, "cfg": 1.0, "shift": 3.0, "sampler": "res_multistep", "scheduler": "simple",
        "width": 1024, "height": 1024,
    }  # official Turbo config -- grounded


def test_anima_image_defaults_lifted_verbatim():
    assert _op("anima_image") == {
        "steps": 30, "cfg": 4.0, "sampler": "er_sde", "scheduler": "simple",
        "width": 1024, "height": 1024,
    }


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
    assert fast["lora"]["accel"] is True
    # The payload carries the per-variant pairs; the UI picks by its own mode (t2v page / i2v page).
    for command in ("t2v", "i2v"):
        assert "lightx2v" in fast["lora"][command]["high"]
        assert "lightx2v" in fast["lora"][command]["low"]
    assert fast["acceleration"]["type"] == "none"
    quality = next(op for op in p["operating_points"] if op["name"] == "quality")
    assert quality["lora"]["accel"] is False and quality["acceleration"]["type"] == "teacache"


def test_payload_single_point_family():
    p = fop.family_operating_points_payload("hunyuan_video")
    assert p["default_operating_point"] == "default"
    assert [op["name"] for op in p["operating_points"]] == ["default"]
    # W2: params grew sampler/scheduler/width/height/frames/fps alongside steps/cfg/shift.
    assert p["operating_points"][0]["params"] == {
        "steps": 20, "cfg": 1.0, "guidance": 6.0, "shift": 7.0, "sampler": "euler", "scheduler": "simple",
        "width": 832, "height": 480, "frames": 81, "fps": 16,
    }
    assert p["operating_points"][0]["lora"] == {} and p["operating_points"][0]["acceleration"] == {}


def test_payload_empty_for_template_or_unknown_family():
    # LTX is template-driven (no op-point selector row). Unknown families ship nothing.
    # Mochi used to be empty too; it now has a grounded default point (steps/cfg) so the
    # UI can surface a single-point payload (no selector, same as hunyuan).
    for fam in ("ltx", "cogvideox", "totally_unknown"):
        p = fop.family_operating_points_payload(fam)
        assert p["operating_points"] == [] and p["default_operating_point"] == "", f"{fam} must ship no points"
    mochi = fop.family_operating_points_payload("mochi")
    assert mochi["default_operating_point"] == "default"
    assert [op["name"] for op in mochi["operating_points"]] == ["default"]
    assert mochi["operating_points"][0]["params"]["steps"] == 30
    assert mochi["operating_points"][0]["params"]["cfg"] == 4.5


def test_payload_is_generically_renderable():
    # The UI contract: >1 point -> render a selector; <=1 -> none. No family names hardcoded.
    assert len(fop.family_operating_points_payload("wan")["operating_points"]) == 2            # selector
    assert len(fop.family_operating_points_payload("hunyuan_video")["operating_points"]) == 1  # single
    assert len(fop.family_operating_points_payload("ltx")["operating_points"]) == 0            # none


def test_wan_sampling_choices_include_operating_point_pins_only_from_allowlist():
    choices = fop.family_sampling_choices("wan")
    assert "euler" in choices["samplers"]
    assert "simple" in choices["schedulers"]
    assert choices["default_sampler"] == "euler"
    assert choices["default_scheduler"] == "simple"
    assert "heunpp2" in choices["samplers"]
    payload = fop.family_operating_points_payload("wan")
    assert payload["samplers"] == choices["samplers"]
    assert payload["default_sampler"] == "euler"


def test_every_family_offers_the_live_ksampler_catalog():
    """Auto still picks the family default. The dropdown is the full Comfy list, not the allow-list."""
    flux = fop.family_sampling_choices("flux")
    assert flux["default_sampler"] == "euler"
    assert flux["default_scheduler"] == "simple"
    assert "heunpp2" in flux["samplers"]
    assert "er_sde" in flux["samplers"]
    assert "uni_pc" in flux["samplers"]
    assert "karras" in flux["schedulers"]
    krea = fop.family_sampling_choices("krea2")
    assert krea["default_sampler"] == "er_sde"
    assert "dpmpp_2m" in krea["samplers"]
    assert "euler_ancestral" in krea["samplers"]


def test_sampling_choices_intersect_object_info():
    object_info = {
        "KSampler": {
            "input": {
                "required": {
                    "sampler_name": [["euler", "dpmpp_2m"], {}],
                    "scheduler": [["simple"], {}],
                }
            }
        }
    }
    choices = fop.family_sampling_choices("wan", object_info=object_info)
    assert choices["samplers"] == ["euler", "dpmpp_2m"] or set(choices["samplers"]) <= {"euler", "dpmpp_2m"}
    assert "simple" in choices["schedulers"]
    assert "normal" not in choices["schedulers"]


def test_a_pinned_default_this_build_does_not_offer_is_not_smuggled_into_the_list():
    """The intersection above held for everything EXCEPT the family's own pin, which was added back
    after it -- so the one name most likely to be forwarded was the one name never checked.

    krea2 pins ``er_sde``. Against a build offering only ``euler`` the resolver answered
    ``['er_sde', 'euler']``, sampling_for read that as "allowed", forwarded it, and ComfyUI answered
    400. The test is written against the RESOLVER rather than through sampling_for because this is
    where the claim is made, and because the same list populates the cockpit's dropdown: offering a
    name the build cannot run is the same defect one layer up.
    """
    thin = {"KSampler": {"input": {"required": {
        "sampler_name": [["euler"], {}], "scheduler": [["simple"], {}]}}}}
    choices = fop.family_sampling_choices("krea2", object_info=thin)
    assert choices["samplers"] == ["euler"]
    assert choices["schedulers"] == ["simple"]
    # With no live list there is nothing to intersect against, so the pin is still trusted.
    assert "er_sde" in fop.family_sampling_choices("krea2")["samplers"]


def test_image_family_alias_resolves_allowlist():
    flux = fop.family_sampling_choices("flux")
    assert flux["default_sampler"] == "euler"
    assert "euler" in flux["samplers"]
    sdxl = fop.family_sampling_choices("sdxl")
    assert "dpmpp_2m" in sdxl["samplers"]
    assert sdxl["default_sampler"]
    snap = fop.family_sampling_snapshot()
    assert "wan" in snap and "sdxl" in snap and "flux" in snap
    assert snap["flux"]["default_sampler"] == "euler"


# --------------------------------------------------------------------------- W2: schema growth (canvas + duration)

def test_every_operating_point_carries_a_complete_sampling_set():
    """A point the cockpit applies must say what to apply.

    Before W2 the video canvas/frames/fps values lived as literals in
    ImageGenerationPage_video.cpp while steps/cfg/sampler lived here, so the two could disagree
    and did. This asserts the table alone is sufficient.
    """
    from family_operating_points import FAMILY_OPERATING_POINTS, OPERATING_POINT_FIELDS

    required = {"steps", "cfg", "sampler", "scheduler"}
    for family, block in FAMILY_OPERATING_POINTS.items():
        for name, point in block["operating_points"].items():
            missing = required - set(point)
            assert not missing, f"{family}/{name} is missing {sorted(missing)}"
            unknown = set(point) - set(OPERATING_POINT_FIELDS)
            assert not unknown, f"{family}/{name} has unknown fields {sorted(unknown)}"


def test_video_families_carry_their_canvas_and_duration():
    """wan / hunyuan_video / mochi must name frames and fps, because the C++ that used to hold
    those numbers is being deleted in this wave.

    LTX is checked separately, against FAMILY_SAMPLER_ALLOWLISTS rather than
    FAMILY_OPERATING_POINTS: this table has NO "ltx" row, on purpose. LTX is template-driven (steps
    and cfg live in the shipped graph and the builder ignores a cockpit value for the distilled
    route) and two tests already assert the row's absence deliberately --
    test_the_operating_point_table_has_no_ltx_row below, and
    test_family_capability.py::test_ltx_offers_the_cockpit_its_real_samplers, whose own comment
    says an earlier pass added a row "for parity" and broke both. Re-adding it here to carry
    width/height/frames/fps would be the same regression a third time, so those fields were
    declared on the allowlist instead, beside the sampler facts LTX already publishes there.
    """
    from family_operating_points import FAMILY_OPERATING_POINTS, FAMILY_SAMPLER_ALLOWLISTS

    for family in ("wan", "hunyuan_video", "mochi"):
        block = FAMILY_OPERATING_POINTS[family]
        point = block["operating_points"][block["default_operating_point"]]
        assert point.get("frames"), f"{family} default point names no frames"
        assert point.get("fps"), f"{family} default point names no fps"
        assert point.get("width") and point.get("height"), f"{family} default point names no canvas"

    ltx = FAMILY_SAMPLER_ALLOWLISTS["ltx"]
    assert ltx.get("frames"), "ltx allowlist names no frames"
    assert ltx.get("fps"), "ltx allowlist names no fps"
    assert ltx.get("width") and ltx.get("height"), "ltx allowlist names no canvas"


def test_the_operating_point_table_has_no_ltx_row():
    """LTX is template-driven and stays absent from FAMILY_OPERATING_POINTS on purpose -- see the
    comment above FAMILY_SAMPLER_ALLOWLISTS["ltx"] and family_capability.TEMPLATE_DRIVEN_FAMILIES.
    An earlier pass added a row "for parity" and broke this exact assertion plus
    test_family_capability.py's; both are pinned so a future pass does not repeat it a third time."""
    from family_operating_points import FAMILY_OPERATING_POINTS

    assert "ltx" not in FAMILY_OPERATING_POINTS


def test_the_wan_numbers_that_were_in_cpp_are_now_in_the_table():
    """The exact values ImageGenerationPage_video.cpp:219-278 applied, so the move is lossless."""
    from family_operating_points import FAMILY_OPERATING_POINTS

    point = FAMILY_OPERATING_POINTS["wan"]["operating_points"][
        FAMILY_OPERATING_POINTS["wan"]["default_operating_point"]
    ]
    assert point["shift"] == 5.0
    assert point["width"] == 832 and point["height"] == 480
    assert point["frames"] == 81 and point["fps"] == 16
