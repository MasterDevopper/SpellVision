"""Projected shrink-wrap scaffold onto a user-selected 14517-vertex body (Doc 44).

Honest status: this writes dest files + wrap_job.json. It does NOT cook a
wearable. stills_to_mesh and garment_cook remain blocked.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Iterable, Mapping

log = logging.getLogger("spellvision.garment_shrinkwrap")

CONTRACT = "spellvision.garment-shrinkwrap-scaffold.v1"
METHOD = "projected_shrinkwrap_scaffold"
BODY_VERTS_REQUIRED = 14517
BLOCKED_ON = ["stills_to_mesh", "garment_cook"]
REQUIRED_VIEWS = ("front", "side", "back")

BLENDER_CANDIDATES = (
    Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"),
    Path(r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe"),
    Path(r"C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"),
)

BLENDER_SCRIPT_REL = Path("scripts") / "garment_shrinkwrap_blender.py"


class GarmentShrinkwrapError(ValueError):
    """Plates cannot honestly feed a wrap scaffold."""


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        parts = [item.strip() for item in value.split(",")]
    elif isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        parts = [str(item).strip() for item in value]
    else:
        parts = []
    return [item for item in parts if item]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_body_path(request: Mapping[str, Any]) -> Path | None:
    explicit = str(request.get("body") or request.get("body_path") or request.get("mesh") or "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        return path if path.is_file() else path
    return None


def resolve_blender_path(request: Mapping[str, Any] | None = None) -> Path | None:
    explicit = ""
    if request is not None:
        explicit = str(request.get("blender") or request.get("blender_path") or "").strip()
    if not explicit:
        explicit = str(os.environ.get("SPELLVISION_BLENDER") or "").strip()
    if explicit:
        path = Path(explicit)
        return path if path.is_file() else None
    for candidate in BLENDER_CANDIDATES:
        if candidate.is_file():
            return candidate
    return None


def maybe_run_blender(job: dict[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
    """Optional. Never raises — scaffold JSON still stands if Blender is missing."""
    want = bool(request.get("run_blender"))
    if str(os.environ.get("SPELLVISION_SHRINKWRAP_BLENDER") or "").strip() in {"1", "true", "yes"}:
        want = True
    if not want:
        return {"ran": False, "reason": "run_blender not requested"}
    blender = resolve_blender_path(request)
    script = Path(__file__).resolve().parents[1] / BLENDER_SCRIPT_REL
    body = Path(str(job.get("body") or ""))
    dest = Path(str(job.get("wrap_mesh_dest") or ""))
    plates = Path(str(job.get("plates_dir") or ""))
    if blender is None or not script.is_file() or not body.is_file():
        return {
            "ran": False,
            "reason": "blender, script, or body missing",
            "blender": str(blender) if blender else "",
        }
    cmd = [
        str(blender),
        "--background",
        "--python",
        str(script),
        "--",
        "--body",
        str(body),
        "--plates",
        str(plates),
        "--dest",
        str(dest),
        "--verts",
        str(BODY_VERTS_REQUIRED),
    ]
    front_mask = plates / "silhouette_front.png"
    if front_mask.is_file():
        cmd.extend(["--front-mask", str(front_mask)])
    front_plate = plates / "front.png"
    if front_plate.is_file():
        cmd.extend(["--front-plate", str(front_plate)])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False)
    except Exception as exc:
        return {"ran": False, "reason": str(exc), "cmd": cmd}
    return {
        "ran": True,
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-1500:],
        "stderr_tail": (proc.stderr or "")[-800:],
        "dest_exists": dest.is_file(),
        "blender": str(blender),
    }


def collect_plates(plates_dir: Path, views: Iterable[str]) -> dict[str, Path]:
    found: dict[str, Path] = {}
    missing: list[str] = []
    for view in views:
        candidates = [
            plates_dir / f"{view}.png",
            plates_dir / f"clothes_01_{view}.png",
            plates_dir / f"{view}.jpg",
        ]
        match = next((path for path in candidates if path.is_file()), None)
        if match is None:
            missing.append(view)
        else:
            found[view] = match
    if missing:
        raise GarmentShrinkwrapError(
            f"missing required plates: {missing} under {plates_dir}"
        )
    return found


def refuse_identical_hashes(plates: Mapping[str, Path]) -> dict[str, str]:
    hashes = {view: _sha256(path) for view, path in plates.items()}
    inverted: dict[str, list[str]] = {}
    for view, digest in hashes.items():
        inverted.setdefault(digest, []).append(view)
    clashes = {digest: views for digest, views in inverted.items() if len(views) > 1}
    if clashes:
        detail = ", ".join(
            f"{digest[:12]}={'/'.join(views)}" for digest, views in clashes.items()
        )
        raise GarmentShrinkwrapError(
            f"required views have identical hashes (not distinct plates): {detail}"
        )
    return hashes


def extract_garment_silhouette(plate: Path, dest: Path) -> dict[str, Any]:
    """White-bg product sheet → L mask. Fail closed if almost empty or almost full."""
    from PIL import Image
    import numpy as np

    im = Image.open(plate).convert("RGB")
    arr = np.asarray(im, dtype=np.float32)
    luma = 0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2]
    # White product sheet vs dark Wrought studio.
    h, w = luma.shape
    ch, cw = max(1, h // 16), max(1, w // 16)
    corners = float(
        np.mean(
            [
                luma[:ch, :cw],
                luma[:ch, -cw:],
                luma[-ch:, :cw],
                luma[-ch:, -cw:],
            ]
        )
    )
    if corners < 50.0:
        garment = luma > 28.0
    else:
        garment = luma < 245
    frac = float(garment.mean())
    if frac < 0.02:
        raise GarmentShrinkwrapError(f"silhouette empty on {plate.name} (frac={frac:.4f})")
    if frac > 0.92:
        raise GarmentShrinkwrapError(f"silhouette is almost the whole frame on {plate.name} (frac={frac:.4f})")
    dest.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray((garment.astype(np.uint8) * 255), mode="L").save(dest)
    ys, xs = np.where(garment)
    return {
        "path": str(dest),
        "width": int(im.size[0]),
        "height": int(im.size[1]),
        "frac": frac,
        "bbox": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
    }


def extract_worn_garments_from_dummy(plate: Path, dest_dir: Path) -> dict[str, Any]:
    """Pull clothes off a dark-studio 051 dummy still. Not a white product sheet.

    Drops near-black backdrop, bright hair, and warm-brown skin. Remaining
    pigment is composited onto white as front.png for shrink-wrap.
    """
    from PIL import Image
    import numpy as np

    im = Image.open(plate).convert("RGB")
    arr = np.asarray(im, dtype=np.float32)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
    bg = luma < 22.0
    hair = luma > 175.0
    h, w = luma.shape
    yy = np.arange(h, dtype=np.int32)[:, None]
    head = yy < int(h * 0.22)
    skin = (
        (r > g + 6.0)
        & (g > b - 8.0)
        & ((r - b) > 22.0)
        & (luma > 38.0)
        & (luma < 200.0)
        & ~hair
    )
    olive = (g >= (r - 12.0)) & (g > b) & (luma > 30.0)
    leather = (luma < 100.0) & (r > 35.0) & (r > b + 8.0) & (r > g)
    garment = ~bg & ~hair & ~skin & ~head & (olive | leather)
    frac = float(garment.mean())
    if frac < 0.04:
        raise GarmentShrinkwrapError(f"worn extract empty on {plate.name} (frac={frac:.4f})")
    if frac > 0.85:
        raise GarmentShrinkwrapError(f"worn extract almost the whole frame on {plate.name} (frac={frac:.4f})")
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    mask = (garment.astype(np.uint8) * 255)
    rgb = arr.copy()
    rgb[~garment] = 255.0
    front = dest_dir / "front.png"
    mask_path = dest_dir / "silhouette_front.png"
    Image.fromarray(rgb.astype(np.uint8), mode="RGB").save(front)
    Image.fromarray(mask, mode="L").save(mask_path)
    ys, xs = np.where(garment)
    info = {
        "path": str(front),
        "mask": str(mask_path),
        "source": str(plate),
        "width": int(im.size[0]),
        "height": int(im.size[1]),
        "frac": frac,
        "bbox": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
        "method": "worn_dummy_extract",
    }
    (dest_dir / "extract_job.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    return info


def split_front_garment_pieces(mask_path: Path, dest_dir: Path, min_frac: float = 0.012) -> list[dict[str, Any]]:
    """Split a product-sheet mask into separable front pieces.

    Two-up sheets keep the left column only. Connected components become
    silhouette_front_piece_00.png (upper) / _01.png (lower).
    """
    from PIL import Image
    import numpy as np

    im = Image.open(mask_path).convert("L")
    mask = np.asarray(im, dtype=np.uint8) > 127
    h, w = mask.shape
    work = mask
    crop_note = "full"
    if w > int(h * 1.15):
        work = mask[:, : w // 2]
        crop_note = "left_half"
    # Downsample for flood-fill.
    small = Image.fromarray(work.astype(np.uint8) * 255).resize((80, 120), Image.NEAREST)
    s = np.asarray(small, dtype=np.uint8) > 127
    sh, sw = s.shape
    seen = np.zeros_like(s, dtype=bool)
    comps: list[list[tuple[int, int]]] = []
    for y in range(sh):
        for x in range(sw):
            if not s[y, x] or seen[y, x]:
                continue
            stack = [(y, x)]
            seen[y, x] = True
            cells: list[tuple[int, int]] = []
            while stack:
                cy, cx = stack.pop()
                cells.append((cy, cx))
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < sh and 0 <= nx < sw and s[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            if len(cells) / float(s.size) >= min_frac:
                comps.append(cells)
    comps.sort(key=lambda c: sum(p[0] for p in c) / len(c), reverse=True)
    dest_dir.mkdir(parents=True, exist_ok=True)
    pieces: list[dict[str, Any]] = []
    full = np.zeros((h, w), dtype=np.uint8)
    for i, cells in enumerate(comps[:4]):
        small_m = np.zeros((sh, sw), dtype=np.uint8)
        for cy, cx in cells:
            small_m[cy, cx] = 255
        piece_small = Image.fromarray(small_m, mode="L").resize((work.shape[1], work.shape[0]), Image.NEAREST)
        piece_arr = np.asarray(piece_small, dtype=np.uint8)
        canvas = np.zeros((h, w), dtype=np.uint8)
        canvas[:, : work.shape[1]] = piece_arr
        dest = dest_dir / f"silhouette_front_piece_{i:02d}.png"
        Image.fromarray(canvas, mode="L").save(dest)
        full = np.maximum(full, canvas)
        ys, xs = np.where(canvas > 127)
        pieces.append(
            {
                "path": str(dest),
                "index": i,
                "frac": float((canvas > 127).mean()),
                "bbox": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] if len(xs) else [],
                "crop": crop_note,
            }
        )
    if pieces:
        Image.fromarray(full, mode="L").save(dest_dir / "silhouette_front.png")
    return pieces


def write_plate_silhouettes(plates: Mapping[str, Path], plates_dir: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for view, path in plates.items():
        dest = plates_dir / f"silhouette_{view}.png"
        out[view] = extract_garment_silhouette(path, dest)
    front = plates.get("front")
    if front is not None:
        out["front_pieces"] = split_front_garment_pieces(plates_dir / "silhouette_front.png", plates_dir)
    return out


def run_garment_shrinkwrap(request: Mapping[str, Any]) -> dict[str, Any]:
    plates_dir_text = str(
        request.get("plates_dir") or request.get("dest") or request.get("clothes_dest") or ""
    ).strip()
    if not plates_dir_text:
        raise GarmentShrinkwrapError("plates_dir is required")
    plates_dir = Path(plates_dir_text).expanduser()
    if not plates_dir.is_dir():
        raise GarmentShrinkwrapError(f"plates_dir is not a directory: {plates_dir}")

    views = _as_list(request.get("views")) or list(REQUIRED_VIEWS)
    plates = collect_plates(plates_dir, views)
    hashes = refuse_identical_hashes(plates)
    silhouettes: dict[str, Any] = {}
    silhouette_error = ""
    try:
        silhouettes = write_plate_silhouettes(plates, plates_dir)
    except Exception as exc:
        silhouette_error = str(exc)

    body = resolve_body_path(request)
    body_present = bool(body and body.is_file())
    wrap_job_path = plates_dir / "wrap_job.json"
    blender_script = Path(__file__).resolve().parents[1] / BLENDER_SCRIPT_REL

    job = {
        "contract": CONTRACT,
        "method": METHOD,
        "body_verts_required": BODY_VERTS_REQUIRED,
        "blocked_on": list(BLOCKED_ON),
        "cook_complete": False,
        "plates_dir": str(plates_dir),
        "plates": {view: str(path) for view, path in plates.items()},
        "plate_sha256": hashes,
        "silhouettes": silhouettes,
        "silhouette_error": silhouette_error,
        "dest": str(plates_dir),
        "wrap_mesh_dest": str(plates_dir / "wrap_scaffold.glb"),
        "body": str(body) if body is not None else "",
        "body_present": body_present,
        "body_missing": not body_present,
        "blender_script": str(blender_script) if blender_script.is_file() else "",
        "character_id": str(request.get("character_id") or ""),
        "notes": (
            "Projected shrink-wrap SCAFFOLD only. stills_to_mesh and garment_cook "
            "are still Degraded. Do not treat wrap_scaffold.glb as a wearable."
        ),
    }
    wrap_job_path.write_text(json.dumps(job, indent=2) + "\n", encoding="utf-8")
    blender_run = maybe_run_blender(job, request)
    job["blender_run"] = blender_run
    wrap_job_path.write_text(json.dumps(job, indent=2) + "\n", encoding="utf-8")
    log.warning(
        "garment_shrinkwrap scaffold dest=%s body_present=%s blender=%s blocked_on=%s",
        plates_dir,
        body_present,
        blender_run.get("ran"),
        BLOCKED_ON,
    )
    return {
        "ok": True,
        "command": "garment_shrinkwrap",
        "method": METHOD,
        "body_verts_required": BODY_VERTS_REQUIRED,
        "blocked_on": list(BLOCKED_ON),
        "cook_complete": False,
        "wrap_job": str(wrap_job_path),
        "dest": str(plates_dir),
        "plates": job["plates"],
        "body": job["body"],
        "body_present": body_present,
        "blender_run": blender_run,
        "output": str(wrap_job_path),
        "output_path": str(wrap_job_path),
    }


def run_garment_shrinkwrap_job(req: dict[str, Any], emitter: Any, job: Any, active_job: Any) -> dict[str, Any]:
    from worker_service_state import JobState, complete_job, transition_job

    if emitter is not None and job is not None:
        transition_job(job, JobState.STARTING)
        emitter.status(job, "garment_shrinkwrap: writing scaffold")
        emitter.emit_job_update(job)
        transition_job(job, JobState.RUNNING)
    payload = run_garment_shrinkwrap(req)
    if emitter is not None:
        emitter.status(job, f"garment_shrinkwrap {payload['wrap_job']}")
    if job is not None:
        complete_job(job, payload)
        if emitter is not None:
            emitter.emit_job_update(job)
    return payload
