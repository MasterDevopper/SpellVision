"""One resolver for "what settings should this page show for this model".

Four sources and two tables disagree, so the order lives in exactly one place. The two rules that
make the answer usable rather than merely correct:

  * a sampler the family's graph cannot accept is not offered -- a cockpit showing a default the
    generate path will refuse is worse than showing the family's own;
  * a hardware cap snaps with a warning, never silently (Doc 54 T5).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from model_intelligence import recommended, resolve, sidecar


def _sidecar_with(recommended: dict) -> dict:
    return {"schema": sidecar.SCHEMA, "identity": {"family": "krea2", "kind": "checkpoint"},
            "display": {}, "recommended": recommended}


def _entry(value, provenance, n=None, total=None):
    return {"value": value, "provenance": provenance, "confidence": 1.0, "n": n, "total": total}


def test_the_sidecar_beats_the_family_operating_point():
    """The headline: the house checkpoint says 10 steps, the runtime table says 52."""
    out = resolve.resolve_model_defaults(
        path="F:/models/loxsUtopicWorldKrea2_v20Quants.safetensors",
        family="krea2", mode="t2i",
        sidecar_payload=_sidecar_with({"steps": _entry(10, "site:image-meta-mode", 10, 10),
                                       "cfg": _entry(1.0, "site:image-meta-mode", 10, 10)}),
    )
    assert out["settings"]["steps"]["value"] == 10
    assert out["settings"]["steps"]["provenance"] == "site:image-meta-mode"
    assert out["settings"]["cfg"]["value"] == 1.0


def test_the_family_operating_point_fills_what_the_model_did_not_say():
    out = resolve.resolve_model_defaults(
        path="F:/models/x.safetensors", family="krea2", mode="t2i",
        sidecar_payload=_sidecar_with({"steps": _entry(10, "site:image-meta-mode", 10, 10)}),
    )
    assert out["settings"]["sampler"]["provenance"] == "table:family-operating-point"
    assert out["settings"]["sampler"]["value"] == "er_sde"


def test_with_no_sidecar_the_family_operating_point_is_the_answer():
    out = resolve.resolve_model_defaults(path="F:/models/x.safetensors", family="krea2",
                                         mode="t2i", sidecar_payload=None)
    assert out["settings"]["steps"]["value"] == 52
    assert out["settings"]["steps"]["provenance"] == "table:family-operating-point"


def test_a_user_value_beats_the_model_and_both_tables():
    out = resolve.resolve_model_defaults(
        path="F:/models/x.safetensors", family="krea2", mode="t2i",
        sidecar_payload=_sidecar_with({"steps": _entry(24, "user"),
                                       "cfg": _entry(1.0, "site:image-meta-mode", 10, 10)}),
    )
    assert out["settings"]["steps"]["value"] == 24
    assert out["settings"]["steps"]["provenance"] == "user"


def test_a_sampler_the_family_cannot_run_is_dropped_with_a_warning():
    """Krea2's allowlist does not contain dpm_2_ancestral. Offering it would produce a cockpit
    default the generate path refuses."""
    out = resolve.resolve_model_defaults(
        path="F:/models/x.safetensors", family="wan", mode="t2v",
        sidecar_payload={"schema": sidecar.SCHEMA, "identity": {"family": "wan"}, "display": {},
                         "recommended": {"sampler": _entry("dpm_2_ancestral", "site:image-meta-mode", 5, 5)}},
    )
    assert out["settings"]["sampler"]["value"] != "dpm_2_ancestral"
    assert out["settings"]["sampler"]["provenance"] == "table:family-operating-point"
    assert any("dpm_2_ancestral" in w for w in out["warnings"])


def test_a_sampler_the_family_can_run_survives():
    out = resolve.resolve_model_defaults(
        path="F:/models/x.safetensors", family="wan", mode="t2v",
        sidecar_payload={"schema": sidecar.SCHEMA, "identity": {"family": "wan"}, "display": {},
                         "recommended": {"sampler": _entry("uni_pc", "site:image-meta-mode", 5, 5)}},
    )
    assert out["settings"]["sampler"]["value"] == "uni_pc"
    assert out["warnings"] == [] or not any("uni_pc" in w for w in out["warnings"])


def test_a_live_sampler_list_narrows_the_allowlist_further():
    """Pinned to the EXACT answer, not to `!= "uni_pc"`.

    The old assertion passed on any value at all, including a wrong one -- and the value it gets is
    wrong: `_enforce_allowlist` substitutes the family floor without testing the floor itself
    against the live list, so `euler` is offered while the warning beside it prints a live list that
    does not contain `euler`. That gap (final-review I7) is UNREACHABLE in production -- nothing in
    `qt_ui/` sends `live_samplers`, and `SamplingController::applyFamilyChoices` rebuilds the combos
    from the family table before the model answer lands -- and it is carried to the wave that starts
    passing live lists. What this test now does is pin the behaviour so that fix cannot land
    unnoticed: the day the fallback is validated, this line fails and names itself.
    """
    out = resolve.resolve_model_defaults(
        path="F:/models/x.safetensors", family="wan", mode="t2v",
        sidecar_payload={"schema": sidecar.SCHEMA, "identity": {"family": "wan"}, "display": {},
                         "recommended": {"sampler": _entry("uni_pc", "site:image-meta-mode", 5, 5)}},
        live_samplers=["euler", "dpmpp_2m"],
    )
    assert out["settings"]["sampler"]["value"] == "euler"
    assert any("uni_pc" in w for w in out["warnings"])


# --- the quorum, applied where the cockpit READS -------------------------------------------------

def test_a_thin_site_mode_is_demoted_on_read_whatever_the_file_claims():
    """`recommended.build` applies the quorum on WRITE; 67 sidecars on this box predate it.

    The schema did not change, so nothing re-derives them: 16 fields were still claiming full
    `site:image-meta-mode` rank at n=1, which is one uploader's single render presented as this
    model's published settings. The gate is a property of the concept, so it is applied on the read
    as well, from the `n` the entry carries about itself.
    """
    out = resolve.resolve_model_defaults(
        path="F:/models/krea2DepthControlnet_v10.safetensors", family="krea2", mode="t2i",
        sidecar_payload=_sidecar_with({"sampler": _entry("euler", "site:image-meta-mode", 1, 1)}),
    )
    assert out["settings"]["sampler"]["provenance"] == "site:image-meta-weak"
    assert out["settings"]["sampler"]["n"] == 1


def test_a_site_mode_at_the_quorum_keeps_its_rank():
    out = resolve.resolve_model_defaults(
        path="F:/models/x.safetensors", family="krea2", mode="t2i",
        sidecar_payload=_sidecar_with({"steps": _entry(10, "site:image-meta-mode",
                                                      recommended.MODE_QUORUM, 10)}),
    )
    assert out["settings"]["steps"]["provenance"] == "site:image-meta-mode"


def test_an_entry_that_records_no_count_is_left_alone():
    """Absent evidence is not evidence of thinness. A card or user entry carries no `n` either, and
    demoting on a missing count would reclassify every one of them."""
    out = resolve.resolve_model_defaults(
        path="F:/models/x.safetensors", family="krea2", mode="t2i",
        sidecar_payload=_sidecar_with({"steps": _entry(10, "site:image-meta-mode")}),
    )
    assert out["settings"]["steps"]["provenance"] == "site:image-meta-mode"


def test_a_canvas_outside_the_spin_boxes_range_is_refused_not_shown():
    """`skinny_fat_v2_loraholic` resolved `width 1792 / height 8` from one example each.

    The C++ dropped the height (it requires >= 64) and wrote the width, so the canvas became 1792 x
    whatever was already there -- half from the model, half from nowhere, under a caption saying the
    model published both. A value the cockpit could not show is not a value.
    """
    out = resolve.resolve_model_defaults(
        path="F:/models/skinny_fat_v2_loraholic.safetensors", family="sdxl", mode="t2i",
        sidecar_payload=_sidecar_with({"width": _entry(1792, "site:image-meta-mode", 5, 5),
                                       "height": _entry(8, "site:image-meta-mode", 5, 5)}),
    )
    assert out["settings"]["width"]["value"] == 1792
    assert out["settings"]["height"]["value"] == 1024, "the family's height, not the site's 8"
    assert any("height" in w and "8" in w for w in out["warnings"])


# --- the operating point comes from data, and only if the family has one -------------------------

def test_an_operating_point_the_family_does_not_declare_falls_back_to_its_default():
    """A wan file with "turbo" in its name reported operating point "turbo", which wan does not
    have. `operating_point_params` then returned {} and the whole tuned point was lost: 20 / 3.5
    from the published floor where wan's own measured table says 28 / 4.0 -- and the reply named a
    Speed chip the cockpit does not build."""
    out = resolve.resolve_model_defaults(
        path="D:/models/wan2.2_t2v_turbo_fp8.safetensors", family="wan", mode="t2v",
        sidecar_payload=None,
    )
    assert out["operating_point"] == "quality"
    assert out["settings"]["steps"]["value"] == 28
    assert out["settings"]["cfg"]["value"] == 4.0


def test_a_word_containing_turbo_is_not_an_operating_point():
    out = resolve.resolve_model_defaults(
        path="D:/models/Turbocharged_Dreams_XL.safetensors", family="sdxl", mode="t2i",
        sidecar_payload=None,
    )
    assert out["settings"]["steps"]["value"] == 30, "sdxl's own published floor, not a turbo one"


def test_a_family_that_declares_turbo_still_gets_it_from_the_filename():
    """The substring fallback is not deleted -- it is the last resort for a weight with no sidecar,
    and krea2 really does declare a turbo row."""
    out = resolve.resolve_model_defaults(
        path="D:/models/krea2_turbo_lora_rank_64_bf16.safetensors", family="krea2", mode="t2i",
        sidecar_payload=None,
    )
    assert out["operating_point"] == "turbo"
    assert out["settings"]["steps"]["value"] == 8


def test_the_sidecar_variant_is_read_before_the_filename():
    """`identity.variant` is what the SITE said. It was dead until 2026-09-16 -- nothing wrote it --
    so the filename substring was the only mechanism the comment claimed was a fallback."""
    payload = _sidecar_with({})
    payload["identity"] = {"family": "krea2", "kind": "checkpoint", "variant": "turbo"}
    out = resolve.resolve_model_defaults(
        path="D:/models/loxsUtopicWorldKrea2_v20Quants.safetensors", family="krea2", mode="t2i",
        sidecar_payload=payload,
    )
    assert out["operating_point"] == "turbo"


# --- LTX's two routes want two different step counts ---------------------------------------------

def test_ltx_resolves_its_distilled_route_by_default():
    out = resolve.resolve_model_defaults(path="F:/models/ltx.safetensors", family="ltx",
                                         mode="t2v", sidecar_payload=None)
    assert out["settings"]["steps"]["value"] == 8
    assert out["settings"]["cfg"]["value"] == 1.0
    assert out["settings"]["steps"]["provenance"] == "table:family-operating-point"


def test_ltx_single_stage_full_gets_the_numbers_the_cpp_used_to_hold():
    """The deleted branch set 30 / 3.5 with the comment "Full ltx-2.3-22b wants 25-40 steps, CFG
    3-5". Task 1 carried only width/height/frames/fps, so the resolver fell to the DISTILLED seed
    for both routes -- a number CLAUDE.md S6 records as wrong for this one, pre-filled under a
    caption claiming a table provenance."""
    out = resolve.resolve_model_defaults(path="F:/models/ltx.safetensors", family="ltx",
                                         mode="t2v", sidecar_payload=None,
                                         route="single_stage_full")
    assert out["settings"]["steps"]["value"] == 30
    assert out["settings"]["cfg"]["value"] == 3.5


def test_a_canvas_beyond_the_vram_budget_snaps_with_a_warning_not_silently():
    out = resolve.resolve_model_defaults(
        path="F:/models/x.safetensors", family="wan", mode="t2v",
        sidecar_payload={"schema": sidecar.SCHEMA, "identity": {"family": "wan"}, "display": {},
                         "recommended": {"width": _entry(3840, "site:image-meta-mode", 5, 5),
                                         "height": _entry(2160, "site:image-meta-mode", 5, 5)}},
        vram_gb=8,
    )
    assert out["settings"]["width"]["value"] < 3840
    assert any("3840" in w for w in out["warnings"])
    assert out["settings"]["width"]["provenance"].endswith(":capped")


def test_no_cap_is_applied_when_the_hardware_is_not_known():
    out = resolve.resolve_model_defaults(
        path="F:/models/x.safetensors", family="wan", mode="t2v",
        sidecar_payload={"schema": sidecar.SCHEMA, "identity": {"family": "wan"}, "display": {},
                         "recommended": {"width": _entry(3840, "site:image-meta-mode", 5, 5)}},
        vram_gb=None,
    )
    assert out["settings"]["width"]["value"] == 3840
    assert out["warnings"] == []


def test_an_unknown_family_yields_whatever_the_sidecar_said_and_no_more():
    out = resolve.resolve_model_defaults(
        path="F:/models/x.safetensors", family=None, mode="t2i",
        sidecar_payload=_sidecar_with({"steps": _entry(10, "site:image-meta-mode", 10, 10)}),
    )
    assert out["settings"]["steps"]["value"] == 10
    assert "sampler" not in out["settings"]


def test_every_returned_field_declares_a_provenance():
    out = resolve.resolve_model_defaults(path="F:/models/x.safetensors", family="krea2",
                                         mode="t2i", sidecar_payload=None)
    assert out["settings"]
    for field, entry in out["settings"].items():
        assert entry.get("provenance"), field
