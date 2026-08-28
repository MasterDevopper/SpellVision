"""Family parity: a family cannot be declared supported while missing a layer its routing needs.

Six families (anima, flux, hunyuan_video, krea2, mochi, wan) were brought to a high standard one at
a time and the pattern was never written down. The consequence was invisible: `lumina` and `pixart`
have a component manifest, operating points, a sampler allowlist and a native graph builder — and
no user can select either, because the Qt asset scanner cannot detect their files.

`KNOWN_GAPS` is a ratchet. It records the gaps that exist today so a NEW gap fails the suite
immediately, and closing one also fails — forcing the baseline down rather than letting it rot.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from family_capability import (  # noqa: E402
    ALL_LAYERS,
    EXPECTED_LAYERS,
    LAYER_COCKPIT,
    LAYER_OPERATING_POINTS,
    LAYER_SAMPLERS,
    ROUTING_UNROUTED,
    families_with_gaps,
    family_capability_report,
    format_report,
)

# Families that were brought to full parity deliberately. These must never regress.
REFERENCE_TIER = {"anima", "flux", "hunyuan_video", "krea2", "mochi", "wan"}

# The ratchet. Measured 2026-08-28. Shrink this as gaps close; never grow it.
KNOWN_GAPS: dict[str, tuple[str, ...]] = {
    # LTX is the most render-proven family in the codebase and was special-cased instead of
    # generalised: no key in FAMILY_OPERATING_POINTS or FAMILY_SAMPLER_ALLOWLISTS, and no alias.
    "ltx": (LAYER_OPERATING_POINTS, LAYER_SAMPLERS),
    # Backend-complete, UI-invisible: manifest + operating points + samplers + builder all present,
    # but AssetCatalogScanner.cpp cannot detect the files, so the family is unreachable.
    "lumina": (LAYER_COCKPIT,),
    "pixart": (LAYER_COCKPIT,),
    # Diffusers families: a sampler allowlist exists for sdxl but no tuned operating point, so
    # Simple mode has no per-family defaults to offer. Open design question, not an oversight —
    # do not invent numbers without measuring renders.
    "sdxl": (LAYER_OPERATING_POINTS,),
    "stable_diffusion": (LAYER_OPERATING_POINTS,),
    "pony": (LAYER_OPERATING_POINTS,),
    "illustrious": (LAYER_OPERATING_POINTS,),
    # sd3 is registry-only: no manifest, no builder, no operating point, no sampler allowlist.
    "sd3": (LAYER_OPERATING_POINTS, LAYER_SAMPLERS),
}


def test_the_reference_tier_never_regresses():
    report = {c.family: c for c in family_capability_report()}
    for family in sorted(REFERENCE_TIER):
        assert family in report, f"{family} vanished from the registry"
        capability = report[family]
        assert capability.at_parity, (
            f"{family} lost a layer: {', '.join(capability.gaps)}\n\n{format_report()}"
        )


def test_known_gaps_match_exactly():
    """Fails on a NEW gap and on a CLOSED one. The second half is the point — a closed gap must
    be removed from the baseline, so this file always states the real remaining work."""
    actual = families_with_gaps()
    expected = {f: tuple(g) for f, g in KNOWN_GAPS.items()}
    normalised = {f: tuple(g) for f, g in actual.items()}

    new_gaps = {f: g for f, g in normalised.items() if f not in expected}
    closed = {f: g for f, g in expected.items() if f not in normalised}
    changed = {
        f: (expected[f], normalised[f])
        for f in set(expected) & set(normalised)
        if set(expected[f]) != set(normalised[f])
    }

    assert not new_gaps, f"new parity gap(s): {new_gaps}\n\n{format_report()}"
    assert not closed, f"gap(s) closed — remove them from KNOWN_GAPS: {closed}"
    assert not changed, f"gap(s) changed shape: {changed}\n\n{format_report()}"


def test_z_image_resolves_its_own_operating_point_by_registry_key():
    """The registry key is `z_image`; the alias map carried `zimage` and `z-image` but not
    `z_image`, so the family could not reach its own tuned defaults. Only native_image_graphs
    worked, because it passes the literal "zimage_image"."""
    report = {c.family: c for c in family_capability_report()}
    capability = report["z_image"]
    assert LAYER_OPERATING_POINTS in capability.present
    assert LAYER_SAMPLERS in capability.present


def test_every_expected_layer_is_a_real_layer():
    for routing, layers in EXPECTED_LAYERS.items():
        for layer in layers:
            assert layer in ALL_LAYERS, f"{routing} expects unknown layer {layer!r}"


def test_an_unrouted_family_is_never_reported_at_parity():
    """It expects no layers, so a bare `not gaps` would call it supported — the most misleading
    possible answer for a family the app cannot generate with."""
    for capability in family_capability_report():
        if capability.routing == ROUTING_UNROUTED:
            assert not capability.at_parity
            assert "NO GENERATION PATH" in format_report([capability])


def test_the_report_degrades_honestly_when_the_cockpit_source_is_unreadable(monkeypatch):
    """An unreadable C++ file must not be reported as 'this family is undetectable'."""
    import family_capability as fc

    monkeypatch.setattr(fc, "_cockpit_source", lambda: "")
    for capability in fc.family_capability_report():
        assert LAYER_COCKPIT not in capability.present
