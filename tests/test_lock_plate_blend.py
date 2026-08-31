from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from lock_plate_blend import (
    chroma_delta,
    demosaic_lock_plate,
    freq_blend,
    region_mask,
    scale_box,
)


def _lock_plate() -> np.ndarray:
    y, x = np.mgrid[0:64, 0:64]
    img = np.zeros((64, 64, 3), dtype=np.float32)
    img[..., 0] = 80
    img[..., 1] = 50
    img[..., 2] = 40
    img[20:28, 20:28] = (40, 80, 200)  # blue iris
    img += ((x + y) % 3)[..., None]  # fine skin grain
    return img


def _mosaic_edit(lock: np.ndarray) -> np.ndarray:
    edited = lock.copy()
    # crystalline mosaic
    tiles = ((np.mgrid[0:64, 0:64][0] // 4) + (np.mgrid[0:64, 0:64][1] // 4)) % 2
    edited = edited + tiles[..., None] * 35
    edited[20:28, 20:28] = (200, 160, 40)  # amber iris
    return np.clip(edited, 0, 255)


def test_freq_blend_kills_tile_energy() -> None:
    lock = _lock_plate()
    edited = _mosaic_edit(lock)
    blended = freq_blend(lock, edited, 3.0)
    # mosaic is high-freq; blended should sit closer to lock than raw i2i
    assert float(np.mean(np.abs(blended - lock))) < float(np.mean(np.abs(edited - lock)))


def test_demosaic_keeps_iris_chroma() -> None:
    lock = _lock_plate()
    edited = _mosaic_edit(lock)
    out = demosaic_lock_plate(lock, edited, radius=3.0, edit_radius=1.25, chroma_t=16.0)
    iris_lock = chroma_delta(lock, lock[20:28, 20:28].mean(axis=(0, 1), keepdims=True))
    # iris of output vs lock should still be a real color change
    iris_out = out[20:28, 20:28].astype(np.float32)
    iris_lock_px = lock[20:28, 20:28]
    assert float(chroma_delta(iris_lock_px, iris_out).mean()) > 20.0
    # and not collapse back to lock blue
    assert float(np.mean(iris_out[..., 0])) > float(np.mean(iris_lock_px[..., 0]))
    del iris_lock


def test_demosaic_same_prompt_stays_near_lock() -> None:
    lock = _lock_plate()
    # mosaic only, no color edit
    tiles = ((np.mgrid[0:64, 0:64][0] // 4) + (np.mgrid[0:64, 0:64][1] // 4)) % 2
    edited = np.clip(lock + tiles[..., None] * 35, 0, 255)
    out = demosaic_lock_plate(lock, edited)
    err_out = float(np.mean(np.abs(out.astype(np.float32) - lock)))
    err_raw = float(np.mean(np.abs(edited - lock)))
    assert err_out < err_raw
    assert err_out < 22.0


def test_scale_box_maps_768x1344_to_other_sizes() -> None:
    y0, y1, x0, x1 = scale_box((0.00, 0.22, 0.12, 0.88), 1344, 768)
    assert y0 == 0 and y1 > 200
    assert 80 < x0 < 150 and 650 < x1 < 720


def test_region_mask_hair_cap_is_top_not_feet() -> None:
    m = region_mask((1344, 768), "hair_cap", feather=0)
    assert m.shape == (1344, 768)
    assert float(m[:80, 384].mean()) > 0.8
    assert float(m[1200:, 384].mean()) < 0.05


def test_hair_volume_covers_sides_not_feet() -> None:
    m = region_mask((1344, 768), "hair_volume", feather=0)
    assert float(m[40, 384].mean()) > 0.8  # crown
    assert float(m[400, 80].mean()) > 0.8  # left fall
    assert float(m[400, 700].mean()) > 0.8  # right fall
    assert float(m[400, 384].mean()) < 0.2  # face/chest center
    assert float(m[1200, 384].mean()) < 0.05


def test_shape_protect_keeps_hair_edit() -> None:
    lock = _lock_plate()
    # high-freq hair silhouette on the lock (vertical stripes)
    lock[:16, :] = 40
    lock[:16, 0:64:4] = 220
    edited = lock.copy()
    edited[:16, :] = (230, 230, 240)  # short/solid hair
    out_plain = demosaic_lock_plate(lock, edited)
    out_prot = demosaic_lock_plate(lock, edited, protect_names=("hair_cap",))
    # unprotected must pull lock stripe energy back
    assert float(out_plain[:8].std()) > float(out_prot[:8].std())
    assert float(out_prot[:8, 32, 0].mean()) > 180.0
