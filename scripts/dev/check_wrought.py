"""Measure whether an image obeys the Wrought Naturalism look law.

The law is not invented here. It is `docs/knowledge/characters/female-look-matrix.md` in
SpellBound-Engine -- the canonical governing ruleset -- and it is unusually measurable for an art
direction, which is what makes a checker possible at all:

  register     "Grounded stylized realism, PBR-native. Explicitly NOT photoreal, NOT anime-smooth.
                Grounded geometry, stylized surface."
  Class C      meso-detail. BOTH neighbours are named failures: (a) macro-only gradients, the
                anime-smooth failure; (b) micro pore detail, THE PHOTOREAL FAILURE; (c) gloss/sheen.
  colour law   skin saturation <= 0.45; dyed cloth <= 0.55 common, <= 0.70 costly.
  negatives    no baked shading, no grimdark grade, no glossy/wet sheen.
  scope        "One ruleset for characters and world -- a woman's forearm and a leather strap obey
                the same detail-frequency law." So this applies to props and buildings, not only to
                skin, and that is the point of measuring it rather than eyeballing a face.

FOUR MEASUREMENTS, each aimed at one named failure mode.

* **Detail band.** Class C sits between two failures that are both frequency claims, so it is
  measured as one: energy in the MID band of the spatial spectrum against the high band. Micro-pore
  photoreal pushes energy high; anime-smooth macro gradients starve the mid. This reuses the band
  technique from the upscale render gate, where it separated a real upscale from a resample.
* **Chroma.** The colour law is a saturation ceiling, stated as a number.
* **Gloss.** A wet-look highlight is a cluster of near-white, near-desaturated pixels -- specular
  blowout. Counted as a fraction of the subject.
* **Crush.** "No grimdark grade" -- if the subject's own shadows are clipped to black, the grade ate
  the material response the register asks for.

THRESHOLDS ARE CALIBRATED, NOT CHOSEN. Run `--calibrate` over a set of images the owner has already
accepted as Wrought (the locked plates) and it prints the observed range. A limit invented before
that measurement would be a taste claim wearing a number.
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


# Every subject crop is resampled to this height before its spectrum is taken, so the frequency
# bands compare surfaces rather than render sizes.
SPECTRUM_HEIGHT = 1024

# CALIBRATED 2026-09-04 over the 17 images in the owner's `_locks/` set -- work already accepted as
# Wrought (002_orc_teacher, bearfolk_r3, human_002style, bear_armor_w5 x6, goblin_keep x8). These
# are observed ranges widened slightly at the edges, not thresholds anyone chose, and the sample is
# small enough that they should be re-derived as the accepted set grows.
#
# `detail_mid_over_high` is deliberately NOT a criterion. It ranged 2.11 to 122.21 across the same
# seventeen images, because detail_high goes near zero on a soft-lit plate and the ratio explodes.
# A metric that spans 60x across work the owner accepts is measuring noise.
WROUGHT = {
    # Colour law, Look Matrix section 4 -- which states a CEILING and no floor: "skin saturation
    # <= 0.45", "dyed cloth <= 0.55 common, <= 0.70 costly".
    #
    # A floor of 0.22 was fitted here from the observed 0.256..0.506, and the first non-character
    # subject broke it: a wrought-iron axe with leather binding and a wood haft measured 0.109 and
    # was called OFF-STYLE while passing detail, crush and gloss, and while being visibly correct.
    # It was correct -- steel, leather and wood ARE desaturated, and a law that requires colour of a
    # grey object is not a law about style.
    #
    # The calibration set was seventeen CHARACTER plates, so it encoded a property of green and tan
    # skin as a property of Wrought. That is the same shape as measuring a costume and calling it a
    # body: the sample carried something the rule then claimed. Ceiling only, as written.
    "saturation_p50": (None, 0.55),
    # Class C meso-detail, sections 1 and 3. Observed 0.0336..0.1170. The FLOOR is what matters:
    # below it the surface is macro-gradient, which is the anime-smooth failure -- and, measured, it
    # is also where flat studio lighting lands, which is how the sheet renders drifted.
    "detail_mid": (0.030, None),
    # "No grimdark grade", section 10 -- measured as WHERE THE SHADOW SITS, not as the presence of
    # black pixels. Observed luma_p05 0.134..0.222 across the seventeen.
    #
    # The first version counted pixels below luma 0.02 and required ~zero, because all seventeen
    # locked plates scored exactly 0.0000. A dark-furred boar then failed at 0.0359 while being
    # visibly correct, and so did a render whose only sin was black sportswear. Both were right and
    # the rule was wrong: none of the seventeen had a black-furred subject, so "no black pixels" had
    # been fitted from a sample of light-skinned figures on dark grounds.
    #
    # Grimdark is a GRADE -- a compressed tonal range -- not the presence of dark materials. The
    # boar keeps 3.6% pure black AND a shadow floor at 0.161; the flat sheet has 3.3% AND a floor at
    # 0.044. The floor separates them; the count never could.
    #
    # Third time this session that a criterion fitted to the character set was wrong on a
    # non-character. The lesson is about the SAMPLE, not the metric: seventeen images of one kind of
    # subject encode that subject's properties as laws.
    "material_floor": (0.10, None),
}

# GLOSS IS A SKIN RULE, and the Look Matrix says so in those words: "No glossy/wet SKIN sheen."
# A polished steel pauldron measured 0.1861 and was called off-style for being metal -- but material
# truth is the register's first demand, and steel that does not throw a highlight is not truthful.
# Applying a skin rule to a helmet is a category error in the checker, not a fault in the render.
#
# So it is advisory by default and a hard gate only when the caller states the subject is organic
# (`--organic`). Observed 0.0000..0.0332 across the seventeen character plates, which is the band it
# is enforced against when it IS enforced.
GLOSS_LIMIT = 0.045


def verdict(row: dict, organic: bool = False) -> list[tuple[str, bool, str]]:
    """Each calibrated criterion, with why it exists."""
    reasons = {
        "saturation_p50": "colour law (Look Matrix 4)",
        "detail_mid": "Class C meso-detail -- below the floor is the anime-smooth/flat failure",
        "material_floor": "no grimdark grade -- lit material keeps its shadow off pure black "
                          "(void is excluded; a dark hall is absence of material, not a grade)",
        "gloss_fraction": "no glossy/wet sheen",
    }
    out = []
    if organic:
        value = row.get("gloss_fraction")
        out.append(("gloss_fraction", value is not None and value <= GLOSS_LIMIT,
                    f"{value} (want <= {GLOSS_LIMIT}) -- no glossy/wet skin sheen"))
    for key, (low, high) in WROUGHT.items():
        value = row.get(key)
        ok = value is not None and (low is None or value >= low) and (high is None or value <= high)
        bound = (f">= {low}" if high is None else f"<= {high}" if low is None else f"{low}..{high}")
        out.append((key, ok, f"{value} (want {bound}) -- {reasons[key]}"))
    return out


def _bands(gray: np.ndarray) -> tuple[float, float, float]:
    """Energy in the low, mid and high thirds of the spatial spectrum, normalised."""
    windowed = gray - gray.mean()
    spectrum = np.abs(np.fft.fftshift(np.fft.fft2(windowed))) ** 2
    h, w = spectrum.shape
    cy, cx = h // 2, w // 2
    yy, xx = np.ogrid[:h, :w]
    radius = np.sqrt(((yy - cy) / cy) ** 2 + ((xx - cx) / cx) ** 2)
    total = spectrum.sum() or 1.0
    low = spectrum[radius <= 0.15].sum() / total
    mid = spectrum[(radius > 0.15) & (radius <= 0.45)].sum() / total
    high = spectrum[radius > 0.45].sum() / total
    return float(low), float(mid), float(high)


def measure(path: Path) -> dict:
    image = Image.open(path).convert("RGB")
    rgb = np.asarray(image).astype(np.float32) / 255.0

    mask = subject_mask(np.asarray(image))
    if mask.sum() < 500:
        # No usable subject -- measure the whole frame rather than refusing, because a prop or a
        # building may fill it, and this checker is meant to apply to those too.
        mask = np.ones(rgb.shape[:2], dtype=bool)

    subject = rgb[mask]
    maximum = subject.max(axis=1)
    minimum = subject.min(axis=1)
    saturation = np.where(maximum > 0, (maximum - minimum) / np.maximum(maximum, 1e-6), 0.0)
    luma = subject @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)

    # THE SPECTRUM IS TAKEN OVER THE SUBJECT, NOT THE FRAME. Measured the other way first, and the
    # numbers were nonsense: the owner-locked plates scored detail_mid 0.084-0.131 while these
    # renders scored 0.009-0.040, an order of magnitude apart, which would say the renders are
    # radically SMOOTHER than the plates. They are not. The plates are tight 768x1024 crops; these
    # are padded reference sheets with a large empty grey ground, and empty background contributes
    # zero energy at every frequency, dragging both bands down. The measurement was reading the
    # framing, not the surface -- the same class of mistake as measuring a costume and calling it a
    # body.
    # ...AND AT A COMMON RESOLUTION, which is the second half of the same correction. Spatial
    # frequency is relative to image size: a 3 px pore in a 768-wide plate and a 5 px pore in a
    # 1216-wide sheet are the same physical detail at different NORMALISED frequencies. Comparing
    # band energies across resolutions therefore compares the render sizes, not the surfaces. The
    # subject crop is resampled to a fixed height before the spectrum so the bands mean one thing.
    rows = np.where(mask.any(axis=1))[0]
    cols = np.where(mask.any(axis=0))[0]
    crop = image.convert("L").crop((int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1))
    scale = SPECTRUM_HEIGHT / crop.height
    crop = crop.resize((max(8, int(crop.width * scale)), SPECTRUM_HEIGHT), Image.LANCZOS)
    gray = np.asarray(crop).astype(np.float32) / 255.0
    low, mid, high = _bands(gray)

    gloss = float(((luma > 0.92) & (saturation < 0.15)).mean())
    crush = float((luma < 0.02).mean())

    # THE SHADOW FLOOR IS A PROPERTY OF MATERIAL, NOT OF VOID. A hearth-lit interior has genuine
    # unlit volume -- the dark end of a hall where there is simply nothing to light -- and including
    # it drags luma_p05 to 0.0 and calls a beautifully material scene grimdark. A subject on a
    # ground has no such void, which is why the character-calibrated version never saw this.
    #
    # "No grimdark grade" is a claim about how MATERIAL is rendered, so the percentile is taken over
    # pixels that show a surface at all. Void is the absence of the thing the rule governs.
    material = luma[luma >= 0.02]
    floor = float(np.percentile(material, 5)) if material.size else 0.0

    return {
        "path": str(path),
        "saturation_p50": round(float(np.percentile(saturation, 50)), 3),
        "saturation_p95": round(float(np.percentile(saturation, 95)), 3),
        "detail_mid": round(mid, 4),
        "detail_high": round(high, 4),
        "detail_mid_over_high": round(mid / high, 2) if high else None,
        "gloss_fraction": round(gloss, 4),
        "crush_fraction": round(crush, 4),
        "luma_p05": round(float(np.percentile(luma, 5)), 3),
        "material_floor": round(floor, 3),
        "void_fraction": round(float((luma < 0.02).mean()), 4),
        "luma_p95": round(float(np.percentile(luma, 95)), 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--calibrate", action="store_true",
                        help="print the observed range over these images, to derive thresholds "
                             "from accepted work instead of inventing them")
    parser.add_argument("--organic", action="store_true",
                        help="the subject is skin/flesh, so the no-gloss skin rule is enforced "
                             "rather than merely reported")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    files: list[Path] = []
    for raw in args.paths:
        p = Path(raw)
        if p.is_dir():
            files.extend(sorted(q for q in p.iterdir()
                                if q.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}))
        elif p.is_file():
            files.append(p)

    rows = [measure(f) for f in files]
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0

    header = f"{'image':34s} {'sat50':>6s} {'sat95':>6s} {'mid':>7s} {'high':>7s} {'m/h':>6s} {'gloss':>7s} {'crush':>7s}"
    print(header)
    print("-" * len(header))
    for r in rows:
        print(f"{Path(r['path']).stem[:34]:34s} {r['saturation_p50']:6.3f} {r['saturation_p95']:6.3f} "
              f"{r['detail_mid']:7.4f} {r['detail_high']:7.4f} "
              f"{(r['detail_mid_over_high'] or 0):6.2f} {r['gloss_fraction']:7.4f} {r['crush_fraction']:7.4f}")

    if not args.calibrate:
        for r in rows:
            checks = verdict(r, args.organic)
            state = "WROUGHT" if all(ok for _, ok, _ in checks) else "OFF-STYLE"
            print(f"\n{state}  {Path(r['path']).stem}")
            for key, ok, detail in checks:
                print(f"   {'ok  ' if ok else 'FAIL'}  {key}: {detail}")

    if args.calibrate and rows:
        print("\nobserved range across these images (use to set thresholds):")
        for key in ("saturation_p50", "saturation_p95", "detail_mid", "detail_high",
                    "detail_mid_over_high", "gloss_fraction", "crush_fraction"):
            values = [r[key] for r in rows if r[key] is not None]
            if values:
                print(f"  {key:22s} {min(values):8.4f} .. {max(values):8.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
