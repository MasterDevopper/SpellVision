"""Does an image set satisfy the character reference-sheet contract, mechanically?

The contract is SpellBound-Engine's `docs/pipeline/CHARACTER_IMAGE_INPUT_SPEC_2026-08-07.md`, whose
constraints are each stated as "miss it and it fails" -- they were derived from the image->3D tool's
actual failure modes, not from taste. `CONCEPT_TO_ASSET_PIPELINE_2026-09-04.md` stage 2a says the
resulting set "should be checked by a script, not by eye", and this is that script.

WHAT IT CHECKS (mechanical, no model needed)
  * subject is separable from the background at all
  * subject is not touching a frame edge   -> the "full body, uncropped, 5-10% margin" rule
  * subject fills enough of the frame      -> ">= 1024 px on the subject, 2048 ideal"
  * background is plain enough to remove   -> "solid/simple, clearly separable"
  * lighting is flat enough                -> "soft, frontal, low-contrast"
  * the view set is complete               -> "FRONT + BACK minimum, F/B/L/R preferred"

SCOPE: this verifies SHEET-LIT renders -- flat, even, plain ground -- because that is what the
contract demands. Handed a look-set render (key light, dark studio, the Wrought law) the mask
shatters, since shadowed skin matches a dark background in both chroma and magnitude. It detects
that and stops rather than reporting six confident false failures off a fragment.

WHAT IT DOES NOT CHECK, and says so rather than passing silently: A-pose, camera orthographicity,
and cross-view identity. Those need the vision judge. A checker that quietly ignores three of the
eleven constraints would report a pass the set has not earned.

SEGMENTATION -- the part with two scars on it; see `subject_mask`. Never threshold luminance (tan
skin on a pale ground reads as background, and a run was lost to a judge that saw only hair), and
one border median is not a background model (a graded ground then classifies as subject and every
image reports "runs off all four edges"). Both were hit here, not anticipated.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

# From the input spec. Each is a stated hard constraint, not a preference.
MIN_SUBJECT_PX = 1024          # "subject should fill the frame at >= 1024 px on the subject"
IDEAL_SUBJECT_PX = 2048
MIN_MARGIN_FRAC = 0.05         # "~5-10% margin"
MAX_BACKGROUND_STD = 42.0      # "plain, high-contrast, removable"
MAX_SUBJECT_CONTRAST = 0.62    # "even / flat lighting"; harsh shadows distort depth
REQUIRED_VIEWS = ("front", "back")
PREFERRED_VIEWS = ("front", "back", "left", "right")

UNCHECKABLE = (
    "A-pose (arms 30-45 deg out, legs separable)",
    "near-orthographic camera -- the tool calls a wrong camera its single biggest failure",
    "cross-view IDENTITY -- whether it is the same character in every view",
)

# Cross-view consistency tolerances. Input spec 4: "same scale and baseline -- feet on the same
# bottom line, head at the same top, subject centered and the SAME SIZE in every view. Inconsistent
# scale/pose between views = a broken fuse."
#
# This was nearly deferred to the vision judge along with identity. It should not have been: scale
# and baseline are the mask's bounding box, which is arithmetic. Only "is it the same character"
# needs eyes. Deferring a checkable constraint to a judge that is not wired yet is how a set ships
# unchecked.
MAX_SCALE_SPREAD = 0.04        # subject height, as a fraction of frame height
MAX_BASELINE_SPREAD = 0.02     # where the feet sit
MAX_CENTRE_SPREAD = 0.06       # horizontal placement


@dataclass
class Finding:
    ok: bool
    rule: str
    detail: str


@dataclass
class SheetReport:
    path: str
    findings: list[Finding] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return all(f.ok for f in self.findings)

    def add(self, ok: bool, rule: str, detail: str) -> None:
        self.findings.append(Finding(ok, rule, detail))


def subject_candidates(rgb: np.ndarray, tolerance: float = 34.0) -> np.ndarray:
    """Every non-background pixel, before the largest-blob reduction.

    Subject = the largest blob that is not background-coloured and does not touch the frame.

    Two failures are designed around here, and BOTH were hit rather than anticipated:

    1. **Never threshold luminance.** On a pale ground, tan skin reads as *background*; a run was
       lost to a judge that saw only hair and told the model to become it. Distance from the
       BACKGROUND COLOUR is the method, same as `stage_judge._subject_mask` in the engine.

    2. **One median is not a background model.** The first version of this function took a single
       median over all four borders. On a studio plate with a graded or vignetted ground -- which is
       most of them -- the darker edge sits further from that median than `tolerance`, so the
       BACKGROUND ITSELF classifies as subject, the bounding box spans the whole frame, and every
       image reports "runs off all four edges". It was caught by an internal contradiction rather
       than by eye: the same image scored a background colour spread of sigma 5.7, and a background
       that uniform cannot also be touching every edge.

    3. **A cast shadow is not the subject.** It touches the feet, so it joins the subject's
       connected component and drags the bounding box to wherever it falls -- reported here as
       "runs off the LEFT edge" while the body was comfortably inside. Caught by looking at the
       dumped mask, which is the engine's standing law for exactly this.

    So: the background reference is estimated PER EDGE and the nearest one is used per pixel, which
    absorbs a gradient; pixels matching a reference's colour DIRECTION but darker are treated as
    shadow; then the mask is reduced to its largest connected component, which discards the speckle
    a gradient still leaves at the corners.
    """
    h, w, _ = rgb.shape
    pixels = rgb.astype(np.float32)
    band = max(2, min(h, w) // 100)
    references = np.stack([
        np.median(pixels[:band, :, :].reshape(-1, 3), axis=0),
        np.median(pixels[-band:, :, :].reshape(-1, 3), axis=0),
        np.median(pixels[:, :band, :].reshape(-1, 3), axis=0),
        np.median(pixels[:, -band:, :].reshape(-1, 3), axis=0),
    ])
    # Distance to the CLOSEST edge reference: a pixel matching any edge's background is background.
    distance = np.min(
        np.linalg.norm(pixels[None, :, :, :] - references[:, None, None, :], axis=3), axis=0
    )
    raw = distance > tolerance

    # 3. A CAST SHADOW IS NOT THE SUBJECT. Studio plates put the figure on a floor, and the contact
    #    shadow touches the feet -- so it joins the subject's connected component and drags the
    #    bounding box wherever it falls. Measured on the regenerated orc sheet: the body sat with
    #    healthy margins while the shadow streaked off the lower-left corner, and the report read
    #    "left margin 0.0%, subject runs off the LEFT edge". The tell was that the offending pixels
    #    were at rows 1486-1549 of 1728 -- 86-90% down the frame, which is floor, not a hand.
    #
    #    A shadow is the GROUND COLOUR AT LOWER LUMINANCE: same chromaticity, smaller magnitude. So
    #    a pixel is also background when its colour direction matches an edge reference and it is
    #    not brighter than it. Hue is what separates a shadow from a dark object.
    #    A SHADOW IS ONLY MODERATELY DARKER, and that bound is load-bearing rather than cosmetic.
    #    Without it this rule ate the subject's clothing: on a neutral-grey ground a BLACK sports bra
    #    and shorts share the ground's colour DIRECTION exactly, so "same chroma, darker" classified
    #    them as shadow, split the body into disconnected pieces, and the largest-component step then
    #    kept a fragment -- reported as a 460x966 subject with 20-31% margins on an image where she
    #    fills the frame. A cast shadow on a light ground sits around 55-100% of its brightness;
    #    black cloth is far below that, so the floor separates them.
    magnitude = np.linalg.norm(pixels, axis=2, keepdims=True)
    unit = pixels / np.maximum(magnitude, 1e-6)
    reference_magnitude = np.linalg.norm(references, axis=1)
    reference_unit = references / np.maximum(reference_magnitude[:, None], 1e-6)
    alignment = np.max(np.einsum("hwc,rc->rhw", unit, reference_unit), axis=0)
    ratio = magnitude[:, :, 0] / max(float(reference_magnitude.max()), 1e-6)
    shadow = (alignment > 0.999) & (ratio >= 0.55) & (ratio <= 1.02)
    raw &= ~shadow
    return raw


def subject_mask(rgb: np.ndarray, tolerance: float = 34.0) -> np.ndarray:
    """The subject: the largest non-background blob. See `subject_candidates` for the segmentation."""
    raw = subject_candidates(rgb, tolerance)
    if not raw.any():
        return raw

    labels, count = ndimage.label(raw)
    if count <= 1:
        return raw
    sizes = ndimage.sum(raw, labels, index=np.arange(1, count + 1))
    return labels == (int(np.argmax(sizes)) + 1)


def check_image(path: Path) -> SheetReport:
    report = SheetReport(path=str(path))
    image = Image.open(path).convert("RGB")
    rgb = np.asarray(image)
    height, width, _ = rgb.shape

    mask = subject_mask(rgb)
    coverage = float(mask.mean())
    if coverage < 0.01:
        report.add(False, "separable subject",
                   "almost nothing differs from the border colour -- the subject cannot be masked "
                   "out, so every measurement below would be meaningless")
        return report
    if coverage > 0.96:
        report.add(False, "separable subject",
                   f"{coverage:.0%} of the frame reads as subject -- the background is not "
                   "distinguishable from it")
        return report
    report.add(True, "separable subject", f"subject occupies {coverage:.0%} of the frame")

    # EXACTLY ONE FIGURE. A "side profile view" prompt produced a mirrored PAIR facing each other,
    # and nothing here said so directly: the largest-component step silently kept one of them, so the
    # subject measured 450 px wide instead of ~1000 and the second body inflated the background
    # spread to sigma 58. The set failed for a reason that named the background. A duplicate figure
    # is a common enough diffusion failure -- and fatal to a fuse, which would have two characters to
    # reconcile -- that it is worth stating rather than inferring.
    labels, count = ndimage.label(subject_candidates(rgb))
    if count:
        sizes = np.sort(ndimage.sum(np.ones_like(labels, dtype=bool), labels,
                                    index=np.arange(1, count + 1)))[::-1]
        biggest = sizes[0]
        rivals = [s for s in sizes[1:] if s > biggest * 0.25]

        # SEGMENTATION SANITY, before any bbox number is believed. A DARK-ground render breaks this
        # mask: shadowed skin matches the background in both chroma and magnitude, so the body
        # shatters. Measured on a deliberately Wrought-lit frame -- key light, dark studio -- the
        # figure came apart into seven comparable blobs and the report claimed a "258x476 subject
        # occupying 2% of the frame" on an image where she fills it. Every margin, size and lighting
        # number after that was derived from a fragment.
        #
        # So this checker is scoped: it verifies SHEET-LIT renders, which is what it is for. Handed
        # a look-set render it says so and stops, rather than emitting six confident false failures.
        if len(rivals) >= 3 and coverage < 0.10:
            report.add(False, "segmentation is reliable here",
                       f"the subject fragmented into {len(rivals) + 1} comparable pieces covering "
                       f"only {coverage:.0%} of the frame. That is what a DARK-ground render does to "
                       "a background-distance mask -- shadowed skin reads as background. This "
                       "checker verifies sheet-lit images; it cannot measure a look-set render, and "
                       "the remaining rules are skipped rather than answered wrongly.")
            return report

        report.add(
            not rivals, "exactly one figure",
            f"largest blob {int(biggest)} px"
            + (f"; {len(rivals)} more of comparable size ({', '.join(str(int(r)) for r in rivals)})"
               " -- more than one figure in the frame" if rivals else " and nothing else comparable"),
        )

    rows = np.where(mask.any(axis=1))[0]
    cols = np.where(mask.any(axis=0))[0]
    top, bottom = int(rows[0]), int(rows[-1])
    left, right = int(cols[0]), int(cols[-1])
    subject_h, subject_w = bottom - top + 1, right - left + 1
    report.metrics = {
        "subject_h_frac": subject_h / height,          # scale, normalised so frame size cancels
        "baseline_frac": (bottom + 1) / height,        # where the feet sit
        "centre_frac": ((left + right) / 2) / width,   # horizontal placement
    }

    # Uncropped, with margin. A subject running into the frame edge is a cut-off limb.
    margins = {
        "top": top / height, "bottom": (height - 1 - bottom) / height,
        "left": left / width, "right": (width - 1 - right) / width,
    }
    touching = [side for side, m in margins.items() if m < MIN_MARGIN_FRAC]
    report.add(
        not touching, "uncropped, >=5% margin",
        f"margins t/b/l/r = {margins['top']:.1%}/{margins['bottom']:.1%}/"
        f"{margins['left']:.1%}/{margins['right']:.1%}"
        + (f" -- SUBJECT RUNS OFF THE {', '.join(s.upper() for s in touching)} EDGE, so the body is "
           "cropped and this is a portrait rather than a full-body reference" if touching else ""),
    )

    # Enough pixels ON THE SUBJECT, which is not the same as a big image.
    subject_px = max(subject_h, subject_w)
    report.add(
        subject_px >= MIN_SUBJECT_PX, ">=1024 px on the subject",
        f"subject is {subject_w}x{subject_h} px in a {width}x{height} frame"
        + ("" if subject_px >= IDEAL_SUBJECT_PX else f" (ideal is {IDEAL_SUBJECT_PX})"),
    )

    # Plain, removable background.
    background = rgb[~mask]
    background_std = float(background.std()) if background.size else 0.0
    report.add(
        background_std <= MAX_BACKGROUND_STD, "plain removable background",
        f"background colour spread sigma={background_std:.1f} "
        f"(limit {MAX_BACKGROUND_STD:.0f})"
        + ("" if background_std <= MAX_BACKGROUND_STD
           else " -- a graded, vignetted or scenic background does not mask cleanly"),
    )

    # Flat, even lighting on the subject.
    subject = rgb[mask].astype(np.float32)
    luma = subject @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    p5, p95 = np.percentile(luma, 5), np.percentile(luma, 95)
    contrast = float((p95 - p5) / 255.0)
    report.add(
        contrast <= MAX_SUBJECT_CONTRAST, "flat, even lighting",
        f"subject luminance p5-p95 spread {contrast:.2f} (limit {MAX_SUBJECT_CONTRAST:.2f})"
        + ("" if contrast <= MAX_SUBJECT_CONTRAST
           else " -- dramatic/directional light gives MoGe a wrong camera and distorts depth"),
    )
    return report


def cross_view_findings(reports: list[SheetReport]) -> list[Finding]:
    """Do the views agree about scale, baseline and placement? Input spec 4.

    A set can pass every per-image rule and still be useless: four correctly-framed views of four
    slightly different-sized characters do not fuse. This is the check that catches a generation
    profile that re-frames each render.
    """
    usable = [r for r in reports if r.metrics]
    if len(usable) < 2:
        return []
    findings: list[Finding] = []
    for key, limit, label in (
        ("subject_h_frac", MAX_SCALE_SPREAD, "same size in every view"),
        ("baseline_frac", MAX_BASELINE_SPREAD, "feet on the same bottom line"),
        ("centre_frac", MAX_CENTRE_SPREAD, "subject centred consistently"),
    ):
        values = [r.metrics[key] for r in usable]
        spread = max(values) - min(values)
        detail = (
            f"spread {spread:.3f} across {len(values)} views (limit {limit:.3f}); "
            + ", ".join(f"{Path(r.path).stem}={r.metrics[key]:.3f}" for r in usable)
        )
        findings.append(Finding(spread <= limit, label, detail))
    return findings


def check_set(paths: list[Path]) -> dict:
    reports = [check_image(p) for p in paths]
    named = {p.stem.lower(): p for p in paths}
    present = {view for view in PREFERRED_VIEWS if any(view in stem for stem in named)}
    missing_required = [v for v in REQUIRED_VIEWS if v not in present]
    cross = cross_view_findings(reports)
    return {
        "images": [
            {"path": r.path, "ok": r.ok,
             "findings": [{"ok": f.ok, "rule": f.rule, "detail": f.detail} for f in r.findings]}
            for r in reports
        ],
        "cross_view": [{"ok": f.ok, "rule": f.rule, "detail": f.detail} for f in cross],
        "views_present": sorted(present),
        "views_missing_required": missing_required,
        "set_ok": (all(r.ok for r in reports) and not missing_required
                   and all(f.ok for f in cross)),
        "not_checked": list(UNCHECKABLE),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="image files, or a directory of them")
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    args = parser.parse_args()

    files: list[Path] = []
    for raw in args.paths:
        p = Path(raw)
        if p.is_dir():
            files.extend(sorted(q for q in p.iterdir()
                                if q.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}))
        elif p.is_file():
            files.append(p)
    if not files:
        print("no images found", file=sys.stderr)
        return 2

    result = check_set(files)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0 if result["set_ok"] else 1

    for entry in result["images"]:
        print(f"\n{'PASS' if entry['ok'] else 'FAIL'}  {entry['path']}")
        for f in entry["findings"]:
            print(f"   {'ok  ' if f['ok'] else 'FAIL'}  {f['rule']}: {f['detail']}")
    if result["cross_view"]:
        print("\ncross-view consistency (input spec 4):")
        for f in result["cross_view"]:
            print(f"   {'ok  ' if f['ok'] else 'FAIL'}  {f['rule']}: {f['detail']}")
    print(f"\nviews present: {result['views_present'] or 'none named by filename'}")
    if result["views_missing_required"]:
        print(f"MISSING REQUIRED VIEWS: {result['views_missing_required']}")
    print("\nNOT checked here (needs the vision judge):")
    for item in result["not_checked"]:
        print(f"   - {item}")
    print(f"\nSET: {'PASS' if result['set_ok'] else 'FAIL'}")
    return 0 if result["set_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
