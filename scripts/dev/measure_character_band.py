"""Measure a character's proportion band from a finished reference sheet.

This is the step that turns a picture into something arguable -- stage 1 of
`CONCEPT_TO_ASSET_PIPELINE_2026-09-04.md`. The output is the `band` half of a JCAS spec
(`tools/blender/jcas/refs.py` + `grounding.json`), so a measured character can be placed among the
eight grounded presets instead of described in adjectives.

WHAT THE BAND IS, read off the existing grounding rather than invented: `{height, waist, hip, whr,
bust}`, where waist and hip are silhouette WIDTHS and bust is a side-view projection DEPTH. The
child preset reads waist 0.238 / hip 0.273 / bust 0.053 at height 1.177 -- those are metres of
width and depth, not circumferences.

TWO THINGS THIS REFUSES TO GUESS

**Arms.** The A-pose that makes a sheet fusable also puts the arms level with the waist, and a naive
per-row width then measures arm-to-arm. That exact defect is on record in JCAS: a measure that
clipped the arms produced a phantom WHR which the reasoner then optimised toward. So each row is
reduced to the horizontal run CONTAINING THE BODY'S CENTRE -- at waist height the silhouette reads
arm | gap | torso | gap | arm, and the middle run is the torso.

**Scale.** Pixels become metres only with a real height, which the input spec lists as a hard
requirement for exactly this reason. It is a required argument here, never a default, and every
ratio that does not need it -- WHR above all -- is reported unscaled so the most discriminating
number carries no assumption at all.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_reference_sheet import subject_mask  # noqa: E402

# Vertical search windows, as a fraction DOWN from the top of the subject. Anthropometric rather
# than tuned: the natural waist sits above the iliac crest, the hip's widest point at the greater
# trochanter, and the bust between them and the shoulder.
BUST_BAND = (0.20, 0.34)
WAIST_BAND = (0.34, 0.46)
HIP_BAND = (0.46, 0.58)
UNDERBUST_BAND = (0.30, 0.38)


def _run_count(row: np.ndarray) -> int:
    """How many separate silhouette runs this row has. 3 at the waist means arm | torso | arm."""
    count = 0
    previous = False
    for value in row:
        if value and not previous:
            count += 1
        previous = bool(value)
    return count


def _central_run(row: np.ndarray, centre: int, max_gap: int = 12) -> int:
    """Width of the horizontal run of `row` containing `centre`, bridging gaps up to `max_gap`.

    Two different jobs, and the gap size is what separates them.

    **Arm rejection.** Without taking the central run, a row through the waist of an A-posed figure
    measures fingertip to fingertip. The gap between an arm and the torso is large -- hundreds of
    pixels -- so it is never bridged.

    **Noise bridging**, added after the cross-view test failed. Measured front against back on the
    same character in the same pose: the hips agreed to 3.5% and the waist did not, 206 px against
    109 px. At that row the back view's torso -- a single 206 px run one percent higher up -- had
    split into 75 + 112 across a THREE PIXEL gap, a braid or a crease shadow, and the body centre
    landed in the smaller half. So the "waist" was half a torso, and the WHR that followed was
    0.258 rather than 0.468.

    A three-pixel gap in a two-hundred-pixel torso is not an anatomical separation. Bridging up to
    `max_gap` keeps the arm rejection intact while refusing to be split by a hair.
    """
    if not row.any():
        return 0
    n = len(row)
    if not row[centre]:
        # Body centre fell in a gap -- between the legs, or in a split like the one above. Start
        # from the nearest filled pixel rather than abandoning the row for its widest run.
        filled = np.where(row)[0]
        centre = int(filled[np.argmin(np.abs(filled - centre))])

    left = centre
    while left > 0:
        if row[left - 1]:
            left -= 1
            continue
        probe = left - 1
        while probe >= 0 and left - probe <= max_gap and not row[probe]:
            probe -= 1
        if probe >= 0 and row[probe] and left - probe <= max_gap:
            left = probe
            continue
        break

    right = centre
    while right < n - 1:
        if row[right + 1]:
            right += 1
            continue
        probe = right + 1
        while probe < n and probe - right <= max_gap and not row[probe]:
            probe += 1
        if probe < n and row[probe] and probe - right <= max_gap:
            right = probe
            continue
        break
    return right - left + 1


def _profile(mask: np.ndarray) -> tuple[np.ndarray, int, int, int]:
    rows = np.where(mask.any(axis=1))[0]
    cols = np.where(mask.any(axis=0))[0]
    top, bottom = int(rows[0]), int(rows[-1])
    centre = int((cols[0] + cols[-1]) // 2)
    widths = np.array([_central_run(mask[y], centre) for y in range(top, bottom + 1)])
    return widths, top, bottom, centre


def _window(widths: np.ndarray, band: tuple[float, float]) -> tuple[int, int]:
    n = len(widths)
    return int(n * band[0]), max(int(n * band[1]), int(n * band[0]) + 1)


def measure(front: Path, side: Path | None, real_height_m: float) -> dict:
    front_mask = subject_mask(np.asarray(Image.open(front).convert("RGB")))
    widths, top, bottom, _ = _profile(front_mask)
    subject_px = bottom - top + 1
    metres_per_px = real_height_m / subject_px

    # A number with no landmark is not auditable. Every measurement reports WHERE it was taken and
    # how many silhouette runs that row had, because that is what says whether the arms were
    # separated there -- and the arm-clip defect is on record as one that produced a plausible
    # wrong answer rather than an obvious one.
    lo, hi = _window(widths, WAIST_BAND)
    waist_i = lo + int(np.argmin(widths[lo:hi]))
    waist_px = int(widths[waist_i])              # the waist is the NARROWEST point in its window
    lo, hi = _window(widths, HIP_BAND)
    hip_i = lo + int(np.argmax(widths[lo:hi]))
    hip_px = int(widths[hip_i])                  # the hip is the WIDEST point in its window
    lo, hi = _window(widths, BUST_BAND)
    bust_i = lo + int(np.argmax(widths[lo:hi]))
    bust_width_px = int(widths[bust_i])
    shoulder_px = int(widths[: _window(widths, BUST_BAND)[0]].max()) if _window(widths, BUST_BAND)[0] else 0

    landmarks = {
        name: {"at_fraction": round(index / len(widths), 3),
               "width_px": int(widths[index]),
               "silhouette_runs": _run_count(front_mask[top + index]),
               "arms_separated": _run_count(front_mask[top + index]) >= 3}
        for name, index in (("waist", waist_i), ("hip", hip_i), ("bust", bust_i))
    }

    result = {
        "front": str(front),
        "landmarks": landmarks,
        "subject_px": subject_px,
        "real_height_m": real_height_m,
        # Scale-free first: these need no height assumption and are what place a character in the
        # axis space.
        "whr": round(waist_px / hip_px, 3) if hip_px else None,
        "waist_over_height": round(waist_px / subject_px, 4),
        "hip_over_height": round(hip_px / subject_px, 4),
        "bust_width_over_height": round(bust_width_px / subject_px, 4),
        "shoulder_over_hip": round(shoulder_px / hip_px, 3) if hip_px else None,
        # Then metres, which do carry the stated assumption.
        "band": {
            "height": round(real_height_m, 3),
            "waist": round(waist_px * metres_per_px, 3),
            "hip": round(hip_px * metres_per_px, 3),
            "whr": round(waist_px / hip_px, 3) if hip_px else None,
        },
    }

    if side is not None and side.exists():
        side_mask = subject_mask(np.asarray(Image.open(side).convert("RGB")))
        depths, s_top, s_bottom, _ = _profile(side_mask)
        s_px = s_bottom - s_top + 1
        lo, hi = _window(depths, BUST_BAND)
        peak = int(depths[lo:hi].max())
        lo, hi = _window(depths, UNDERBUST_BAND)
        trough = int(depths[lo:hi].min())
        # Bust as PROJECTION, matching how the grounded presets record it: the depth at the bust
        # minus the depth just under it, so torso thickness cancels out.
        result["side"] = str(side)
        result["bust_projection_over_height"] = round((peak - trough) / s_px, 4)
        result["band"]["bust"] = round((peak - trough) * (real_height_m / s_px), 3)
    return result


def compare_to_presets(result: dict, grounding: Path) -> list[str]:
    """Where this character sits among the presets that are already grounded in real data."""
    if not grounding.is_file():
        return [f"(no grounding.json at {grounding}; skipped)"]
    presets = json.loads(grounding.read_text(encoding="utf-8"))
    whr = result.get("whr")
    lines = []
    for name, entry in sorted(presets.items(),
                              key=lambda kv: abs((kv[1].get("band") or {}).get("whr", 9) - (whr or 0))):
        band = entry.get("band") or {}
        if band.get("whr") is None:
            continue
        lines.append(f"  {name:12s} whr {band['whr']:.3f}   (this character: {whr:.3f}, "
                     f"delta {abs(band['whr'] - whr):.3f})")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--front", required=True)
    parser.add_argument("--side")
    parser.add_argument("--height", type=float, required=True,
                        help="the character's real height in metres; required, never assumed")
    parser.add_argument("--grounding",
                        default="C:/Users/xXste/Code_Projects/SpellBound-Engine/tools/blender/jcas/grounding.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = measure(Path(args.front), Path(args.side) if args.side else None, args.height)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    print("measured from the sheet")
    print(f"  subject height        {result['subject_px']} px  -> {result['real_height_m']} m (stated)")
    print(f"  WHR                   {result['whr']}          <- needs no height assumption")
    print(f"  waist / height        {result['waist_over_height']}")
    print(f"  hip / height          {result['hip_over_height']}")
    print(f"  bust width / height   {result['bust_width_over_height']}")
    print(f"  shoulder / hip        {result['shoulder_over_hip']}")
    print("\n  landmarks (where each number came from):")
    for name, info in result["landmarks"].items():
        flag = "" if info["arms_separated"] else "   <-- ARMS NOT SEPARATED HERE; width may include them"
        print(f"    {name:6s} at {info['at_fraction']:.3f} down, {info['width_px']:4d} px, "
              f"{info['silhouette_runs']} runs{flag}")
    if "bust_projection_over_height" in result:
        print(f"  bust projection/height {result['bust_projection_over_height']}")
    print(f"\n  band (metres): {json.dumps(result['band'])}")
    print("\nnearest grounded presets by WHR:")
    for line in compare_to_presets(result, Path(args.grounding)):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
