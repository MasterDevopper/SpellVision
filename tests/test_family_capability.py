"""Family parity: a family cannot be declared supported while missing a layer its routing needs.

Six families (anima, flux, hunyuan_video, krea2, mochi, wan) were brought to a high standard one at
a time and the pattern was never written down, so a family could be declared supported while
silently missing a layer -- `lumina` and `pixart` had a manifest, operating points, a sampler
allowlist and a native builder, and no display name, so both were labelled with the generic
"Image".

The measurement itself needed four corrections before it was trustworthy, and each one is a
cautionary note for anyone extending it:

1. Text-scanning module source reported `sdxl` as missing a native builder and a contract. It
   routes through diffusers, so neither layer applies -- hence `EXPECTED_LAYERS` is per routing.
2. The same scan reported image families as HAVING a video-only contract (`flux` matched `flux3`).
3. Scanning the whole scanner file for a family name said `lumina`/`pixart` were undetectable.
   Detection does not happen in C++ at all; it runs through `model_classification.classify_model`.
4. Scoping to `humanImageFamily` then reported the four VIDEO families as broken, because they are
   correctly listed in `humanVideoFamily` instead.

`KNOWN_GAPS` is a ratchet. It records the gaps that exist today so a NEW gap fails the suite
immediately, and closing one also fails -- forcing the baseline down rather than letting it rot.
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
REFERENCE_TIER = {"anima", "flux", "hunyuan_video", "krea2", "mochi", "wan",
                  # Joined by closing their gaps in the parity sweep.
                  "lumina", "pixart", "z_image", "ltx"}

# The ratchet. Measured 2026-08-28. Shrink this as gaps close; never grow it.
KNOWN_GAPS: dict[str, tuple[str, ...]] = {
    # sdxl / stable_diffusion / pony / illustrious USED to be listed here as missing an operating
    # point. Settling that question by measurement showed it was never a gap: nothing on the
    # diffusers path reads FAMILY_OPERATING_POINTS, so a row for them would be inert. The
    # expectation moved to EXPECTED_LAYERS instead of the values being invented. See
    # test_the_diffusers_path_does_not_read_operating_points below, which pins the reason.
    #
    # sd3's sampler gap is CLOSED. It stood open on purpose while there was no SD3 checkpoint here
    # to validate against -- copying sdxl's list was refused, because SD3 is flow-matching and
    # dpmpp_2m/karras are wrong for it. With a real SD3.5 Medium checkpoint on disk the family was
    # built out natively and every allow-listed sampler was submitted to the live KSampler against
    # it, so the entries are measured rather than assumed.
    #
    # cogvideox is not listed: it has no generation path at all, which the report states as
    # NO GENERATION PATH rather than as a set of missing layers.
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


def test_lumina_and_pixart_have_a_display_name():
    """Both fell through humanImageFamily to the generic "Image", so a Lumina checkpoint was
    labelled identically to an unclassified one. They were always DETECTED -- detection runs
    through model_classification.classify_model, not C++ -- so this was a labelling defect, not
    the reachability defect an earlier text-scan of the whole file claimed."""
    report = {c.family: c for c in family_capability_report()}
    for family in ("lumina", "pixart"):
        assert LAYER_COCKPIT in report[family].present
        assert report[family].at_parity


def test_z_image_resolves_its_own_operating_point_by_registry_key():
    """The registry key is `z_image`; the alias map carried `zimage` and `z-image` but not
    `z_image`, so the family could not reach its own tuned defaults. Only native_image_graphs
    worked, because it passes the literal "zimage_image"."""
    report = {c.family: c for c in family_capability_report()}
    capability = report["z_image"]
    assert LAYER_OPERATING_POINTS in capability.present
    assert LAYER_SAMPLERS in capability.present


def test_ltx_offers_the_cockpit_its_real_samplers():
    """LTX had no entry in either table, so family_sampling_choices("ltx") returned empty lists
    and empty defaults -- the most render-proven family offered the cockpit nothing.

    The values are read out of the shipped templates, not chosen: stage-1 and stage-2 sampler
    patch defaults, and an EMPTY scheduler list because neither LTX template exposes a scheduler
    input (both drive sigmas via ManualSigmas). "No scheduler" and "no entry" must not look the
    same, which is precisely the distinction that was missing."""
    from family_operating_points import family_sampling_choices, operating_point_params

    choices = family_sampling_choices("ltx")
    # Declared on the allowlist, because a template-driven family has no operating-point row to
    # take a default from -- without it this advertised "euler", which the template overrides.
    assert choices["default_sampler"] == "euler_ancestral_cfg_pp"
    assert "euler_cfg_pp" in choices["samplers"]
    assert choices["schedulers"] == [], "LTX drives sigmas explicitly; there is no scheduler"

    # And it must STILL have no operating-point row. LTX is template-driven: steps and cfg live in
    # the shipped graph, the builder ignores a passed cfg for the distilled route and warns. An
    # earlier pass of this sweep added a row "for parity" and broke two tests that assert this
    # emptiness on purpose -- the codebase was right and the parity expectation was wrong.
    from family_operating_points import FAMILY_OPERATING_POINTS

    assert "ltx" not in FAMILY_OPERATING_POINTS
    report = {c.family: c for c in family_capability_report()}
    assert LAYER_OPERATING_POINTS not in report["ltx"].expected, (
        "a template-driven family must not be expected to have a tuning row"
    )
    assert report["ltx"].at_parity


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


def test_the_diffusers_path_does_not_read_operating_points():
    """Why sdxl owes no operating-point row -- pinned so nobody "closes the gap" with an inert one.

    Measured 2026-08-28. ``image_runners`` passes req["steps"] and req["cfg"] straight into the
    pipeline; it never imports FAMILY_OPERATING_POINTS, and ``worker_service`` consults the table
    only for video family status payloads. A row added for sdxl would sit there looking
    authoritative and change nothing -- the exact "looks correct while being wrong" shape.

    If this test ever fails, the diffusers path has been wired to the table, and THAT is when
    per-family rows become worth writing -- each with its own render validation.
    """
    from pathlib import Path as _Path

    import image_runners

    source = _Path(image_runners.__file__).read_text(encoding="utf-8", errors="replace")
    assert "family_operating_points" not in source, (
        "image_runners now references the operating-point table -- if it consumes it, add rows for "
        "the diffusers families and restore LAYER_OPERATING_POINTS to their EXPECTED_LAYERS"
    )


def test_a_sampler_allowlist_is_owed_by_every_routed_family():
    """The counterpart to the operating-point exemption: samplers DO reach both pipelines, so a
    missing allowlist is a genuine gap rather than a bookkeeping one, whichever way a family routes.

    Verified by render on both sides, not by reading. Diffusers: the same SDXL prompt and seed
    through dpmpp_2m/karras and euler/normal produced images differing by a mean absolute 30.6 per
    channel. Native: SD3.5 Medium sampled with heun took 27.2s against euler's 15.1s on the same
    prompt and seed -- heun's two model evaluations per step, which is behaviour, not pixels.

    This test used to assert that sd3 HAD this gap. It was the last one open, and it is closed.
    """
    import image_runners

    assert hasattr(image_runners, "apply_sampler_and_scheduler")
    report = {c.family: c for c in family_capability_report()}
    for family, capability in report.items():
        if LAYER_SAMPLERS in capability.expected:
            assert LAYER_SAMPLERS not in capability.gaps, (
                f"{family} routes as {capability.routing} and owes a sampler allowlist"
            )
