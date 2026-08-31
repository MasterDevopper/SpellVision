"""Lock-plate demosaic for Krea2 / Qwen VAE i2i.

Low-denoise i2i through qwen_image_vae paints a crystalline mosaic onto skin.
The UNET is not the cause (BF16 and Quants both do it). Seed is not identity.

Fix: keep lock-plate high frequency (detail), take i2i low frequency (the edit),
and restore extra i2i color only where chroma actually moved (eyes, hair dye).

Shape edits (hair cut, brows, nose, mouth) are lock *edges*. They need a
protect mask so demosaic does not paint the lock silhouette back.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

# Normalized boxes on a 768x1344 standing full-body lock: (y0, y1, x0, x1).
# Head ~ top 22%. Clothes sit mid-frame so hips stay measurable for 14517.
REGION_BOXES: dict[str, tuple[float, float, float, float]] = {
    "hair_cap": (0.00, 0.22, 0.12, 0.88),
    "hair_fall_l": (0.12, 0.52, 0.02, 0.32),
    "hair_fall_r": (0.12, 0.52, 0.68, 0.98),
    "brow_band": (0.105, 0.155, 0.34, 0.66),
    "eyes": (0.125, 0.175, 0.34, 0.66),
    "nose": (0.155, 0.215, 0.42, 0.58),
    "mouth": (0.195, 0.255, 0.38, 0.62),
    "torso_clothes": (0.28, 0.58, 0.18, 0.82),
    "legs_clothes": (0.52, 0.88, 0.20, 0.80),
    "full_outfit": (0.26, 0.98, 0.12, 0.88),
}

# Named unions — hair cut must cover hanging strands, not just the skull.
REGION_GROUPS: dict[str, tuple[str, ...]] = {
    "hair_volume": ("hair_cap", "hair_fall_l", "hair_fall_r"),
    "face_features": ("brow_band", "eyes", "nose", "mouth"),
    "outfit": ("torso_clothes", "legs_clothes"),
}


def _as_rgb(arr: np.ndarray) -> np.ndarray:
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise ValueError(f"expected HxWx3 RGB, got {arr.shape}")
    return arr.astype(np.float32, copy=False)


def _gauss(img: np.ndarray, radius: float) -> np.ndarray:
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    return np.asarray(im.filter(ImageFilter.GaussianBlur(radius=float(radius))), dtype=np.float32)


def _chroma(img: np.ndarray) -> np.ndarray:
    rg = img[..., 0] - img[..., 1]
    yb = 0.5 * (img[..., 0] + img[..., 1]) - img[..., 2]
    return np.stack([rg, yb], axis=-1)


def freq_blend(lock: np.ndarray, edited: np.ndarray, radius: float) -> np.ndarray:
    """Lock high-freq + edited low-freq."""
    lock = _as_rgb(lock)
    edited = _as_rgb(edited)
    if lock.shape != edited.shape:
        raise ValueError(f"shape mismatch {lock.shape} vs {edited.shape}")
    return _gauss(edited, radius) + (lock - _gauss(lock, radius))


def chroma_delta(lock: np.ndarray, edited: np.ndarray) -> np.ndarray:
    return np.linalg.norm(_chroma(_as_rgb(edited)) - _chroma(_as_rgb(lock)), axis=-1)


def scale_box(
    box: tuple[float, float, float, float], height: int, width: int
) -> tuple[int, int, int, int]:
    y0, y1, x0, x1 = box
    return (
        max(0, int(round(y0 * height))),
        min(height, int(round(y1 * height))),
        max(0, int(round(x0 * width))),
        min(width, int(round(x1 * width))),
    )


def region_mask(
    shape: tuple[int, ...],
    name: str,
    *,
    feather: float = 8.0,
) -> np.ndarray:
    """HxW float mask in 0..1 for a named region on a standing lock plate."""
    if name in REGION_GROUPS:
        return combine_region_masks(shape, REGION_GROUPS[name], feather=feather)
    if name not in REGION_BOXES:
        known = ", ".join(sorted(set(REGION_BOXES) | set(REGION_GROUPS)))
        raise KeyError(f"unknown region {name!r}; known: {known}")
    height, width = int(shape[0]), int(shape[1])
    y0, y1, x0, x1 = scale_box(REGION_BOXES[name], height, width)
    m = np.zeros((height, width), dtype=np.float32)
    if y1 > y0 and x1 > x0:
        m[y0:y1, x0:x1] = 1.0
    if feather > 0:
        mimg = Image.fromarray((m * 255).astype(np.uint8)).filter(
            ImageFilter.GaussianBlur(radius=float(feather))
        )
        m = np.asarray(mimg, dtype=np.float32) / 255.0
    return m


def combine_region_masks(
    shape: tuple[int, ...], names: tuple[str, ...] | list[str], *, feather: float = 8.0
) -> np.ndarray:
    acc = np.zeros((int(shape[0]), int(shape[1])), dtype=np.float32)
    for name in names:
        acc = np.maximum(acc, region_mask(shape, name, feather=feather))
    return np.clip(acc, 0.0, 1.0)


def demosaic_lock_plate(
    lock: np.ndarray,
    edited: np.ndarray,
    *,
    radius: float = 3.0,
    edit_radius: float = 1.25,
    chroma_t: float = 16.0,
    feather: float = 2.0,
    protect_names: tuple[str, ...] | list[str] | None = None,
    protect_feather: float = 8.0,
) -> np.ndarray:
    """Kill Qwen-VAE mosaic while keeping intended color and shape edits.

    Body/skin uses a stronger lock-detail blend. Regions whose chroma moved
    (iris, hair dye) use a weaker blend so the edit survives.

    protect_names: named regions where lock edges must NOT win (hair cut,
    brow reshape, clothes swap). Those pixels come from the i2i edit.
    """
    lock = _as_rgb(lock)
    edited = _as_rgb(edited)
    base = freq_blend(lock, edited, radius)
    fine = freq_blend(lock, edited, edit_radius)
    delta = chroma_delta(lock, edited)
    mask = (delta > float(chroma_t)).astype(np.float32)
    mimg = Image.fromarray((mask * 255).astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(radius=float(feather))
    )
    m = (np.asarray(mimg, dtype=np.float32) / 255.0)[..., None]
    out = base * (1.0 - m) + fine * m
    if protect_names:
        prot = combine_region_masks(lock.shape, protect_names, feather=protect_feather)[..., None]
        out = out * (1.0 - prot) + edited * prot
    return np.clip(out, 0, 255).astype(np.uint8)


def demosaic_paths(
    lock_path: str | Path,
    edited_path: str | Path,
    dest_path: str | Path,
    **kwargs,
) -> Path:
    lock_p = Path(lock_path)
    edit_p = Path(edited_path)
    dest = Path(dest_path)
    lock = np.asarray(Image.open(lock_p).convert("RGB"))
    edited = np.asarray(Image.open(edit_p).convert("RGB"))
    if lock.shape != edited.shape:
        edited_im = Image.fromarray(edited).resize((lock.shape[1], lock.shape[0]), Image.Resampling.LANCZOS)
        edited = np.asarray(edited_im)
    out = demosaic_lock_plate(lock, edited, **kwargs)
    dest.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(out).save(dest)
    return dest
