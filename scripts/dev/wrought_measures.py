# scripts/dev/wrought_measures.py
"""Two plates of one character: does the suit keep the silhouette, and is it the same face?

DIRECTION_V2 section 9: the SKIN plate (two-piece, markings visible) is the material truth and the
SUIT plate (a reference edit of it) is the proportion truth. Both are Wrought-lit -- dark studio,
one key -- so `check_reference_sheet.subject_mask` (built for a light, flat ground) shatters on them
(documented there). This mask is the dark-ground counterpart: the ground is sampled from the border
and anything that differs from it in luma OR chroma by more than the tolerance is subject; every
component big enough to be a body part is kept UNLESS it sits BESIDE the largest one (little
column overlap, matching rows -- what a second figure looks like, not a severed limb) and is big
enough to be a rival, in which case it is refused as a second figure. The suit is mid-grey for this
reason (a dark-grey suit on a near-black void would not separate).

Thresholds: silhouette accept < 8 px at 1216 wide (Jarvis, section 9.6) -- restated after the first
twenty pairs, as Doc 50 rule 1 requires; face identity is RECORDED (MAE + normalised cross-
correlation on the largest Haar face) and not thresholded until twenty pairs exist.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent))
from measure_character_band import _central_run  # noqa: E402

# Jarvis section 9.6. PROVISIONAL -- restated once the first twenty real skin/suit pairs exist
# (Doc 50 rule 1: a number this early carries the sample size it was set from, not none).
SILHOUETTE_LIMIT_PX_AT_1216 = 8.0

# A Wrought void sits near black: the locks' own subject-shadow floor reads luma 0.13-0.22 of 255
# (~33-56), and the void behind the subject is darker than that floor. 90 sits above every lock's
# void and below any lit skin, so a border that medians above it is not void -- the subject itself
# is touching the frame edge and contaminating the sample, and returning a mask built on that
# would be a plausible wrong number rather than a caught one.
GROUND_LUMA_MAX = 90.0

# Anthropometric fractions of subject height from the top -- the natural waist of a standing adult
# sits ~0.38-0.42, the crotch ~0.50-0.53. Task 14b fix round 1: the old waist band (0.35, 0.55)
# reached into the crotch's shadow gap, and on orc_woman/002 the real central-run width tapered
# 16, 12, 11, 8, 6, 2 px on the way into that gap -- the naive argmin called the 2px row a "waist".
# Narrowed so the band stops short of where the gap starts; HIP_BAND is unchanged (its argmax
# search already prefers a WIDE row over a gap, never a narrow one).
WAIST_BAND = (0.30, 0.47)
HIP_BAND = (0.50, 0.70)

# PROVISIONAL (Task 14b fix round 1): a gap is not a waist. Reject any row in the waist band
# narrower than this fraction of the band's median width before taking the argmin.
WAIST_GAP_REJECT_FRACTION = 0.40

_CASCADE = None


def _rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"))


def dark_subject_mask(rgb: np.ndarray, tolerance: float = 28.0, keep_fraction: float = 0.05) -> np.ndarray:
    # PROVISIONAL: lower than the light-ground checker's subject_mask tolerance (34) because a dark
    # void has less pixel-value spread than a lit sheet ground; re-derived at Task 14 once twenty
    # real pairs exist to set it from.
    border = np.concatenate([rgb[:8].reshape(-1, 3), rgb[-8:].reshape(-1, 3),
                             rgb[:, :8].reshape(-1, 3), rgb[:, -8:].reshape(-1, 3)]).astype(np.float32)
    ground = np.median(border, axis=0)
    luma = 0.2126 * ground[0] + 0.7152 * ground[1] + 0.0722 * ground[2]
    if luma > GROUND_LUMA_MAX:
        raise ValueError(f"estimated ground luma {luma:.1f} is not a dark-studio void; the subject "
                          "may touch the frame border")
    diff = np.abs(rgb.astype(np.float32) - ground).max(axis=2)
    candidates = diff > tolerance
    # iterations=2: removes single-pixel border speckle without eating a real ~20px-wide arm/limb.
    candidates = ndimage.binary_opening(candidates, iterations=2)
    labels, count = ndimage.label(candidates)
    if count == 0:
        return candidates
    sizes = ndimage.sum(candidates, labels, index=np.arange(1, count + 1))
    largest_id = int(np.argmax(sizes)) + 1
    largest_size = float(sizes[largest_id - 1])

    def col_span(label_id: int) -> tuple[int, int]:
        cols = np.where((labels == label_id).any(axis=0))[0]
        return int(cols[0]), int(cols[-1])

    def row_span(label_id: int) -> tuple[int, int]:
        rows = np.where((labels == label_id).any(axis=1))[0]
        return int(rows[0]), int(rows[-1])

    largest_col_lo, largest_col_hi = col_span(largest_id)
    largest_col_span = largest_col_hi - largest_col_lo + 1
    largest_row_lo, largest_row_hi = row_span(largest_id)
    largest_row_span = largest_row_hi - largest_row_lo + 1

    # Task 14b: a mid-grey suit's shadow side can merge with the near-black void at this tolerance,
    # shattering one figure into several fragments (208px "figure" measured on a full standing
    # woman, Task 14 report). Keeping only the single largest fragment silently measures a torso
    # piece instead of the person. A hand is ~1-2% of a 1216x1728 figure; a shadow-severed leg or
    # torso is >=10% -- so keep_fraction=0.05 keeps every real body-part fragment.
    #
    # But size alone cannot tell a severed limb from a second figure standing beside the first.
    # Fix round 1 gated on column overlap alone (>=50% of the smaller span to keep) and that refused
    # a real severed leg: an akimbo pose on orc_woman/000 pulls the largest fragment's own column
    # span toward one side (it already contains a whole connected arm+leg there), so the OTHER leg
    # only overlapped it by 48.9% of the smaller span -- just under the 50% floor -- and got refused
    # as if it were a second figure. It is not: a person standing BESIDE you shares your ROWS (near
    # 100% row overlap) while sharing almost none of your COLUMNS (near 0%); a limb under or over you
    # is the opposite -- it can land almost anywhere in column space (as orc_woman/000 shows) but
    # never shares your rows the way a second body does. So "beside" is now column overlap < 20% of
    # the smaller column span AND row overlap >= 50% of the smaller row span (two figures side by
    # side: ~0% columns, ~100% rows). Only a component that is BOTH beside AND big enough to be a
    # rival (>=25% of the largest -- the sheet checker's own threshold, `check_reference_sheet.py`'s
    # `rivals`) is refused; every other component >= keep_fraction is kept outright, no further
    # overlap requirement.
    keep_labels = [largest_id]
    for label_id in range(1, count + 1):
        if label_id == largest_id:
            continue
        size = float(sizes[label_id - 1])
        if size < keep_fraction * largest_size:
            continue
        lo, hi = col_span(label_id)
        col_overlap = max(0, min(hi, largest_col_hi) - max(lo, largest_col_lo) + 1)
        col_smaller = min(hi - lo + 1, largest_col_span)
        col_overlap_frac = col_overlap / col_smaller if col_smaller > 0 else 0.0

        rlo, rhi = row_span(label_id)
        row_overlap = max(0, min(rhi, largest_row_hi) - max(rlo, largest_row_lo) + 1)
        row_smaller = min(rhi - rlo + 1, largest_row_span)
        row_overlap_frac = row_overlap / row_smaller if row_smaller > 0 else 0.0

        beside = col_overlap_frac < 0.20 and row_overlap_frac >= 0.50
        if beside and size >= 0.25 * largest_size:
            raise ValueError(f"more than one figure: a component of {size / largest_size:.0%} of "
                              "the largest sits beside it")
        keep_labels.append(label_id)
    keep = np.isin(labels, keep_labels)
    return ndimage.binary_fill_holes(keep)


def widths(mask: np.ndarray, rows: tuple[int, int] | None = None) -> dict:
    subject_rows = np.where(mask.any(axis=1))[0]
    if subject_rows.size == 0:
        return {"height_px": 0, "waist_px": 0, "hip_px": 0, "waist_row": 0, "hip_row": 0}
    top, bottom = int(subject_rows[0]), int(subject_rows[-1])
    height = bottom - top + 1
    # A per-row `.sum()` measures an A-pose fingertip to fingertip -- the arm-clip defect already
    # fixed once in measure_character_band._central_run (read its docstring). Reuse that fix at the
    # mask's own column centroid rather than re-deriving arm rejection here.
    centre = int(np.round(np.mean(np.where(mask)[1])))
    row_width = np.array([_central_run(mask[y], centre) for y in range(mask.shape[0])])

    if rows is not None:
        # Clamp rather than raise -- a row mapped from a differently-proportioned second plate
        # (`paired_rows`) can round to just outside this mask's own extent; that is still the
        # nearest sane row to read, not a reason to blow up the whole measurement.
        waist_row = min(max(int(rows[0]), 0), mask.shape[0] - 1)
        hip_row = min(max(int(rows[1]), 0), mask.shape[0] - 1)
    else:
        def band(lo: float, hi: float) -> tuple[int, int]:
            a, b = top + int(height * lo), top + int(height * hi)
            return a, max(b, a + 1)

        wa, wb = band(*WAIST_BAND)
        ha, hb = band(*HIP_BAND)
        waist_candidates = row_width[wa:wb]
        # A crotch-shadow gap reads as a near-zero-width row -- not a waist. Reject any row
        # narrower than WAIST_GAP_REJECT_FRACTION of the band's median before taking the argmin;
        # fall back to the full band if every row in it is somehow rejected.
        median = float(np.median(waist_candidates)) if waist_candidates.size else 0.0
        survivors = np.where(waist_candidates >= WAIST_GAP_REJECT_FRACTION * median)[0]
        if survivors.size == 0:
            survivors = np.arange(waist_candidates.size)
        waist_row = wa + int(survivors[np.argmin(waist_candidates[survivors])])
        hip_row = ha + int(np.argmax(row_width[ha:hb]))
    return {"height_px": height, "waist_px": int(row_width[waist_row]), "hip_px": int(row_width[hip_row]),
            "waist_row": int(waist_row), "hip_row": int(hip_row)}


def paired_rows(mask_a: np.ndarray, mask_b: np.ndarray) -> tuple[tuple[int, int], tuple[int, int]]:
    """Search waist/hip on A as `widths` does; map those rows onto B by height fraction.

    A small repose between the skin and suit plate moves the independently-searched hip row by
    hundreds of pixels even when the two figures agree in height (orc_woman/002, Task 14 report:
    heights 1689 vs 1686, hip delta 284px). Searching once on the skin plate and reading the suit
    plate at the SAME fractional position removes that independent-search degree of freedom.
    """
    rows_a = np.where(mask_a.any(axis=1))[0]
    rows_b = np.where(mask_b.any(axis=1))[0]
    wa = widths(mask_a)
    waist_a, hip_a = wa["waist_row"], wa["hip_row"]
    if rows_a.size == 0 or rows_b.size == 0:
        return (waist_a, hip_a), (waist_a, hip_a)
    top_a, height_a = int(rows_a[0]), wa["height_px"]
    top_b, height_b = int(rows_b[0]), int(rows_b[-1]) - int(rows_b[0]) + 1
    waist_frac = (waist_a - top_a) / height_a
    hip_frac = (hip_a - top_a) / height_a
    waist_b = top_b + int(round(waist_frac * height_b))
    hip_b = top_b + int(round(hip_frac * height_b))
    waist_b = min(max(waist_b, 0), mask_b.shape[0] - 1)
    hip_b = min(max(hip_b, 0), mask_b.shape[0] - 1)
    return (waist_a, hip_a), (waist_b, hip_b)


def silhouette_delta(skin: Path, suit: Path) -> dict:
    a, b = _rgb(skin), _rgb(suit)
    if a.shape[1] != b.shape[1]:
        # The two plates are one canvas by contract (DIRECTION_V2 section 9) -- a width mismatch
        # means the wrong file paired up, not a real proportion to measure.
        raise ValueError(f"plates differ in width: {a.shape[1]} vs {b.shape[1]}")
    mask_a, mask_b = dark_subject_mask(a), dark_subject_mask(b)
    (rows_a, rows_b) = paired_rows(mask_a, mask_b)
    wa, wb = widths(mask_a, rows=rows_a), widths(mask_b, rows=rows_b)
    # Scales UP for a canvas wider than the 1216 reference (proportionally more pixels for the
    # same physical distance); never shrinks below the nominal 8px for a narrower one (a small
    # preview/test render isn't held to a tighter absolute-pixel budget than production).
    limit = SILHOUETTE_LIMIT_PX_AT_1216 * max(1.0, a.shape[1] / 1216.0)
    out = {"waist_delta_px": abs(wa["waist_px"] - wb["waist_px"]),
           "hip_delta_px": abs(wa["hip_px"] - wb["hip_px"]),
           "height_delta_px": abs(wa["height_px"] - wb["height_px"]),
           "limit_px": limit, "skin": wa, "suit": wb,
           "rows": {"skin": list(rows_a), "suit": list(rows_b)}, "paired": True}
    out["ok"] = out["waist_delta_px"] < limit and out["hip_delta_px"] < limit
    return out


def _face_crop(rgb: np.ndarray) -> tuple[np.ndarray | None, int | None]:
    global _CASCADE
    if _CASCADE is None:
        _CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    grey = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    # OpenCV's documented defaults for frontal faces at >= 48px; the same three values
    # check_wrought.face_texture uses (scripts/dev/check_wrought.py:169), so a face detected here
    # detects the same way it does there.
    faces = _CASCADE.detectMultiScale(grey, scaleFactor=1.1, minNeighbors=5, minSize=(48, 48))
    if len(faces) == 0:
        return None, None
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    crop = cv2.resize(grey[y:y + h, x:x + w], (128, 128), interpolation=cv2.INTER_AREA)
    return crop, int(w)


# --- whole-mask overlap: the silhouette measure of record ---------------------------------------
#
# The two-row measure (waist + hip) is NOISE on an A-pose: the hip band (50-70 % of height) sits at
# the thigh gap, so `_central_run` reads one thigh or nothing, and the shadow side of the torso under
# the single key light drops out of the dark-ground mask at the waist row. Measured 2026-09-06 on
# an img2img output whose body is the skin plate's own latent (visually identical): waist d 25,
# hip d 150 px. The whole-mask overlap on the same pair: IoU 0.906, median row-extent difference
# 2 px -- while the four reference-edit pairs (a different body by eye) score IoU 0.39-0.54 and
# 52-147 px. So the gate is the overlap; the two-row deltas stay in the record as context only.
SILHOUETTE_IOU_SAME_BODY = 0.85   # provisional: 1 identical pair at 0.906, 4 different at <= 0.54


def _row_extent(mask: np.ndarray) -> np.ndarray:
    """Rightmost minus leftmost subject pixel per row (arms included); 0 where the row is empty."""
    w = np.zeros(mask.shape[0], dtype=np.int32)
    for y in np.where(mask.any(axis=1))[0]:
        xs = np.where(mask[y])[0]
        w[y] = xs[-1] - xs[0]
    return w


def silhouette_overlap(skin: Path, suit: Path) -> dict:
    """IoU of the two subject masks on the shared canvas, plus the median absolute row-extent
    difference over rows where both have subject. Same framing is assumed (both plates are rendered
    at CANVAS_LANE_A from the same seed); a plate of a different size is resized to the skin's."""
    a = dark_subject_mask(np.asarray(Image.open(skin).convert("RGB")))
    im_b = Image.open(suit).convert("RGB")
    if im_b.size != Image.open(skin).size:
        im_b = im_b.resize(Image.open(skin).size)
    b = dark_subject_mask(np.asarray(im_b))
    union = int((a | b).sum())
    iou = float((a & b).sum() / union) if union else 0.0
    wa, wb = _row_extent(a), _row_extent(b)
    both = (wa > 0) & (wb > 0)
    extent = float(np.median(np.abs(wa[both] - wb[both]))) if both.any() else None
    return {"iou": round(iou, 4), "median_extent_delta_px": extent, "area_skin": int(a.sum()),
            "area_suit": int(b.sum()), "same_body": iou >= SILHOUETTE_IOU_SAME_BODY}


def face_identity(a: Path, b: Path) -> dict:
    ca, pa = _face_crop(_rgb(a))
    cb, pb = _face_crop(_rgb(b))
    if ca is None or cb is None:
        return {"mae": None, "ncc": None, "face_px_a": pa, "face_px_b": pb}
    mae = float(np.abs(ca.astype(np.float32) - cb.astype(np.float32)).mean())
    ncc = float(cv2.matchTemplate(ca, cb, cv2.TM_CCOEFF_NORMED)[0, 0])
    return {"mae": mae, "ncc": ncc, "face_px_a": pa, "face_px_b": pb}


if __name__ == "__main__":
    skin, suit = Path(sys.argv[1]), Path(sys.argv[2])
    print(json.dumps({"silhouette": silhouette_delta(skin, suit), "identity": face_identity(skin, suit)}, indent=1))
