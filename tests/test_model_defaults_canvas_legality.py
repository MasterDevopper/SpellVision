"""The canvas rules `resolve.py` TRANSCRIBED, held against the code they were transcribed from.

`_CANVAS_SNAP`, `_snap_wh`, `_snap_frames` and `_snap_canvas_legality` are about forty lines of
per-family divisibility copied by hand out of `video_adapters/ltx_adapter.py` and the two `_snap`
closures in `native_video_graphs.py`, under ruling W2-P3 (the cockpit must show a legal pair rather
than one the builder will silently correct). They shipped with no test at all -- and hand-copied
constraints are exactly the code that rots against its source, because the source moves and the
copy has no way to notice.

So this file does two different jobs, and the second is the one that matters in a year:

  * the SNAP tests pin the behaviour a user sees (a 3840x2161 LTX canvas becomes a pair LTX's own
    adapter accepts, and says so);
  * the DRIFT tests read the numbers back out of the modules the copy came from, so a stride that
    changes there fails here rather than becoming a cockpit that confidently displays an illegal
    size.

LTX's originals are importable, so that half is a real differential test against the live
functions. Mochi's and hunyuan_video's live inside builder bodies as closures, so those are held
to the literal formulas in their source text -- weaker, and named as weaker, but it still fails the
day someone edits the stride.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from model_intelligence import resolve  # noqa: E402


def _entry(value, provenance="site:image-meta-mode", n=5, total=5):
    return {"value": value, "provenance": provenance, "confidence": 1.0, "n": n, "total": total}


def _resolve(family, *, width=None, height=None, frames=None, mode="t2v", **kw):
    recommended = {}
    if width is not None:
        recommended["width"] = _entry(width)
    if height is not None:
        recommended["height"] = _entry(height)
    if frames is not None:
        recommended["frames"] = _entry(frames)
    return resolve.resolve_model_defaults(
        path="F:/models/x.safetensors", family=family, mode=mode,
        sidecar_payload={"schema": "spellvision.model-sidecar/1", "identity": {}, "display": {},
                         "recommended": recommended},
        **kw,
    )


# --- what the user sees ---------------------------------------------------------------------------

def test_ltx_snaps_both_dimensions_to_32_and_says_so():
    out = _resolve("ltx", width=1000, height=700)
    assert out["settings"]["width"]["value"] % 32 == 0
    assert out["settings"]["height"]["value"] % 32 == 0
    assert out["settings"]["width"]["value"] == 992
    assert out["settings"]["height"]["value"] == 704
    assert any("divisible by 32" in w for w in out["warnings"])


def test_ltx_frame_length_is_snapped_to_the_n_times_8_plus_1_ladder():
    out = _resolve("ltx", frames=50)
    assert out["settings"]["frames"]["value"] == 49
    assert (out["settings"]["frames"]["value"] - 1) % 8 == 0
    assert any("(N*8)+1" in w for w in out["warnings"])


def test_a_legal_ltx_canvas_is_left_alone_and_warns_about_nothing():
    out = _resolve("ltx", width=832, height=480, frames=49)
    assert out["settings"]["width"]["value"] == 832
    assert out["settings"]["height"]["value"] == 480
    assert out["settings"]["frames"]["value"] == 49
    assert out["warnings"] == []


def test_mochi_floors_rather_than_rounding():
    """The two families snap in opposite directions, and the difference is not cosmetic: LTX's
    adapter rounds to the NEAREST multiple, mochi's builder floors. A single shared helper would
    show one of them a size its builder then changes underneath it."""
    out = _resolve("mochi", width=860, height=490)
    assert out["settings"]["width"]["value"] == 848
    assert out["settings"]["height"]["value"] == 480


def test_hunyuan_video_frame_length_floors_to_the_n_times_4_plus_1_ladder():
    out = _resolve("hunyuan_video", frames=75)
    assert out["settings"]["frames"]["value"] == 73
    assert any("(N*4)+1" in w for w in out["warnings"])


def test_a_family_with_no_declared_constraint_is_not_snapped():
    """wan has no `_CANVAS_SNAP` row. Inventing one here -- "16 is probably fine" -- is how a
    transcription becomes a guess."""
    out = _resolve("wan", width=833, height=481)
    assert out["settings"]["width"]["value"] == 833
    assert out["settings"]["height"]["value"] == 481
    assert out["warnings"] == []


def test_a_non_numeric_canvas_never_reaches_the_snap():
    """`_snap_canvas_legality` has a try/except for a non-numeric width. It is now unreachable from
    a sidecar -- `_sidecar_entries`' sanity floor refuses the entry outright and the family's own
    value is used -- and the guard stays, because the snap does not get to assume who calls it."""
    out = _resolve("ltx", width="wide", height=480)
    assert out["settings"]["width"]["value"] == 832
    assert out["settings"]["height"]["value"] == 480
    assert any("wide" in w for w in out["warnings"])


def test_the_cap_runs_before_the_snap_so_the_displayed_pair_is_legal():
    """Ordered the other way round -- which is how this shipped -- an LTX canvas capped for VRAM
    came out at 1123x636. 1123 % 32 == 3: a pair LTX's own adapter refuses, shown in the cockpit as
    a size. Whatever the cap picks, the snap is what makes it legal, so the snap has to be last."""
    out = _resolve("ltx", width=7680, height=4320, vram_gb=8)
    assert out["settings"]["width"]["value"] % 32 == 0
    assert out["settings"]["height"]["value"] % 32 == 0
    assert out["settings"]["width"]["value"] < 7680
    assert any("heuristic" in w for w in out["warnings"])


# --- the heuristic cap is generous, or it is a bug wearing a safety label --------------------------

@pytest.mark.parametrize("vram_gb", [6, 8, 10, 12, 16, 24, 32])
def test_a_plain_1024_square_is_never_capped_on_any_card_we_ship_to(vram_gb):
    """0.5 x VRAM / 6000 B/px capped a stock 1024x1024 SDXL default to 846x846 on 8 GB and 732x732
    on 6 GB -- sizes that render fine. A cap that refuses the most common family's default size on
    the most common card is not catching the obvious case; it IS the obvious case. Latent only
    because nothing sends `vram_gb` yet, which is the worst way for a number to be safe."""
    out = resolve.resolve_model_defaults(path="F:/models/x.safetensors", family="sdxl", mode="t2i",
                                         sidecar_payload=None, vram_gb=vram_gb)
    assert out["settings"]["width"]["value"] == 1024
    assert out["settings"]["height"]["value"] == 1024
    assert out["warnings"] == []


def test_4k_on_8gb_is_still_refused_which_is_what_the_cap_is_for():
    out = _resolve("wan", width=3840, height=2160, vram_gb=8)
    assert out["settings"]["width"]["value"] < 3840
    assert out["settings"]["width"]["provenance"].endswith(":capped")


# --- held against the source the copy came from ---------------------------------------------------

def test_ltx_is_snapped_exactly_as_its_own_adapter_would():
    """A real differential test: `resolve._snap_wh` / `_snap_frames` against the functions in
    `video_adapters/ltx_adapter.py` the constants were transcribed from. Values chosen to hit both
    rounding directions, the max() floor and the ladder's bottom rung."""
    from video_adapters import ltx_adapter

    spec = resolve._CANVAS_SNAP["ltx"]
    for value in (1, 15, 16, 17, 31, 64, 700, 833, 1000, 1023, 1025, 3840, 4321):
        assert resolve._snap_wh(value, spec["wh_multiple"], spec["wh_mode"]) == \
            ltx_adapter._snap_to_multiple(value, ltx_adapter._LTX_DIM_MULTIPLE), value
    for value in (1, 2, 8, 9, 33, 48, 49, 50, 96, 97, 121, 500):
        assert resolve._snap_frames(value, spec["frame_stride"], spec["frame_min"],
                                    spec["frame_mode"]) == \
            ltx_adapter._snap_ltx_frame_length(value), value


@pytest.mark.parametrize("family,builder", [
    ("mochi", "_build_native_mochi_video_prompt"),
    ("hunyuan_video", "_build_native_hunyuan_video_prompt"),
])
def test_the_video_builders_still_snap_the_way_this_module_says_they_do(family, builder):
    """Mochi's and hunyuan_video's snaps are closures inside builder bodies, so they cannot be
    imported and compared the way LTX's can. They are held instead to the literal formulas in
    `native_video_graphs.py` -- a weaker check, named as weaker, that still fails the day a stride
    moves there and leaves this module quietly describing the old one."""
    source = (ROOT / "python" / "native_video_graphs.py").read_text(encoding="utf-8")
    spec = resolve._CANVAS_SNAP[family]

    # `_snap(req.get("width"), <default>, <multiple>)` -- the multiple is the third argument.
    multiples = {int(m) for m in re.findall(r'_snap\(req\.get\("(?:width|height)"\), \d+, (\d+)\)', source)}
    assert spec["wh_multiple"] in multiples, (family, multiples)

    # `((max(<min>, raw_len) - 1) // <stride>) * <stride> + 1`
    ladders = {(int(a), int(b)) for a, b in
               re.findall(r"\(\(max\((\d+), raw_len\) - 1\) // (\d+)\) \* \2 \+ 1", source)}
    assert (spec["frame_min"], spec["frame_stride"]) in ladders, (family, ladders)

    # And the builder this row describes still exists under the name this test names.
    assert f"def {builder}" in source, builder


def test_every_snap_row_names_a_family_the_allowlists_know():
    """A row keyed on a name no family resolves to is a rule that can never fire -- the quietest way
    for a transcription to stop being applied."""
    import family_operating_points as fop

    for family in resolve._CANVAS_SNAP:
        assert family in fop.FAMILY_SAMPLER_ALLOWLISTS, family
