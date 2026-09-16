"""One resolver for "what settings should this page show for this model".

Four sources and two tables disagree, so the order lives in exactly one place. The two rules that
make the answer usable rather than merely correct:

  * a sampler the family's graph cannot accept is not offered -- a cockpit showing a default the
    generate path will refuse is worse than showing the family's own;
  * a hardware cap snaps with a warning, never silently (Doc 54 T5).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from model_intelligence import resolve, sidecar

FIXTURES = Path(__file__).parent / "fixtures" / "model_intelligence"


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
    out = resolve.resolve_model_defaults(
        path="F:/models/x.safetensors", family="wan", mode="t2v",
        sidecar_payload={"schema": sidecar.SCHEMA, "identity": {"family": "wan"}, "display": {},
                         "recommended": {"sampler": _entry("uni_pc", "site:image-meta-mode", 5, 5)}},
        live_samplers=["euler", "dpmpp_2m"],
    )
    assert out["settings"]["sampler"]["value"] != "uni_pc"
    assert any("uni_pc" in w for w in out["warnings"])


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
