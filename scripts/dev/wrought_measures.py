# scripts/dev/wrought_measures.py
"""Two plates of one character: does the suit keep the silhouette, and is it the same face?

DIRECTION_V2 section 9: the SKIN plate (two-piece, markings visible) is the material truth and the
SUIT plate (a reference edit of it) is the proportion truth. Both are Wrought-lit -- dark studio,
one key -- so `check_reference_sheet.subject_mask` (built for a light, flat ground) shatters on them
(documented there). This mask is the dark-ground counterpart: the ground is sampled from the border
and anything that differs from it in luma OR chroma by more than the tolerance is subject; the
largest component wins. The suit is mid-grey for this reason (a dark-grey suit on a near-black void
would not separate).

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

SILHOUETTE_LIMIT_PX_AT_1216 = 8.0
_CASCADE = None


def _rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"))


def dark_subject_mask(rgb: np.ndarray, tolerance: float = 28.0) -> np.ndarray:
    h, w, _ = rgb.shape
    border = np.concatenate([rgb[:8].reshape(-1, 3), rgb[-8:].reshape(-1, 3),
                             rgb[:, :8].reshape(-1, 3), rgb[:, -8:].reshape(-1, 3)]).astype(np.float32)
    ground = np.median(border, axis=0)
    diff = np.abs(rgb.astype(np.float32) - ground).max(axis=2)
    candidates = diff > tolerance
    candidates = ndimage.binary_opening(candidates, iterations=2)
    labels, count = ndimage.label(candidates)
    if count == 0:
        return candidates
    sizes = ndimage.sum(candidates, labels, index=np.arange(1, count + 1))
    keep = labels == (int(np.argmax(sizes)) + 1)
    return ndimage.binary_fill_holes(keep)


def widths(mask: np.ndarray) -> dict:
    rows = np.where(mask.any(axis=1))[0]
    if rows.size == 0:
        return {"height_px": 0, "waist_px": 0, "hip_px": 0, "waist_row": 0, "hip_row": 0}
    top, bottom = int(rows[0]), int(rows[-1])
    height = bottom - top + 1
    row_width = mask.sum(axis=1)

    def band(lo: float, hi: float) -> tuple[int, int]:
        a, b = top + int(height * lo), top + int(height * hi)
        return a, max(b, a + 1)

    wa, wb = band(0.35, 0.55)
    ha, hb = band(0.50, 0.70)
    waist_row = wa + int(np.argmin(row_width[wa:wb]))
    hip_row = ha + int(np.argmax(row_width[ha:hb]))
    return {"height_px": height, "waist_px": int(row_width[waist_row]), "hip_px": int(row_width[hip_row]),
            "waist_row": waist_row, "hip_row": hip_row}


def silhouette_delta(skin: Path, suit: Path) -> dict:
    a, b = _rgb(skin), _rgb(suit)
    wa, wb = widths(dark_subject_mask(a)), widths(dark_subject_mask(b))
    # Scales UP for a canvas wider than the 1216 reference (proportionally more pixels for the
    # same physical distance); never shrinks below the nominal 8px for a narrower one (a small
    # preview/test render isn't held to a tighter absolute-pixel budget than production).
    limit = SILHOUETTE_LIMIT_PX_AT_1216 * max(1.0, a.shape[1] / 1216.0)
    out = {"waist_delta_px": abs(wa["waist_px"] - wb["waist_px"]),
           "hip_delta_px": abs(wa["hip_px"] - wb["hip_px"]),
           "height_delta_px": abs(wa["height_px"] - wb["height_px"]),
           "limit_px": limit, "skin": wa, "suit": wb}
    out["ok"] = out["waist_delta_px"] < limit and out["hip_delta_px"] < limit
    return out


def _face_crop(rgb: np.ndarray) -> tuple[np.ndarray | None, int | None]:
    global _CASCADE
    if _CASCADE is None:
        _CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    grey = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    faces = _CASCADE.detectMultiScale(grey, scaleFactor=1.1, minNeighbors=5, minSize=(48, 48))
    if len(faces) == 0:
        return None, None
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    crop = cv2.resize(grey[y:y + h, x:x + w], (128, 128), interpolation=cv2.INTER_AREA)
    return crop, int(w)


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
