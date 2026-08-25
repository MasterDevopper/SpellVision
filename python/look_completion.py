"""Robust-addon-checker look-completion.

Inventory cropped Robust stills, plan a 768x1344 head-to-toe completion from
WHAT IS PRESENT (same hair / clothes / skin), and emit a Krea2 T2I or
pad-to-canvas regional-inpaint graph.

Worker command ``look_complete`` is registered by the Clothes+wire lane.
This module owns the contract, planner, inventory, and graph builders.
Do not I2I-photocopy a Grok still as identity. Do not swap a maxi dress
over fitted pants. Clothes-only stills belong to the other lane.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

log = logging.getLogger("spellvision.look_completion")

CONTRACT = "spellvision.look_complete.v1"
TARGET_NAME = "full_body_768x1344"
TARGET_WIDTH = 768
TARGET_HEIGHT = 1344
PRODUCER_UNET = ""
PRODUCER_PATH = ""
CLIP_NAME = "qwen3vl_4b_fp8_scaled.safetensors"
VAE_NAME = "qwen_image_vae.safetensors"
DEFAULT_STEPS = 52
DEFAULT_CFG = 3.5
COMFY_URL = "http://127.0.0.1:8188"
COMFY_OUTPUT = Path(r"C:\sv_comfynext\ComfyUI\output")

CROP_CLASSES = (
    "full_body",
    "three_quarter",
    "bust",
    "face",
    "clothes_only",
    "unknown",
)
PRESENT_REGIONS = ("face", "hair", "torso_clothes", "legs", "feet", "hands")
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".jfif", ".webp", ".bmp"}

KNOWN_PACKS = (
    "afro",
    "black hair",
    "cow girl",
    "dark hinata",
    "fox lady",
    "leapord",
    "nerd girl",
    "ninja",
    "nurse",
    "purple girl",
    "skirt elf",
    "sleepy",
    "sporty bear",
    "sword gal",
    "tattoo mommy",
    "white coat",
    "white hair black skin",
    "witch",
)

# Filename tokens that usually mean isolated garments / studies, not a character.
_CLOTHES_ONLY_TOKENS = (
    "clothes",
    "shirt",
    "shirts",
    "lips",
    "anatomy",
    "breast shapes",
    "poses",
)
_FACE_TOKENS = ("lips", "face")
_ANTHRO_PACKS = frozenset({"cow girl", "fox lady", "leapord", "sporty bear"})

# Recreate the REAL clothes present on the teacher. Never invent a maxi dress.
PACK_LOOK: dict[str, dict[str, str]] = {
    "witch": {
        "identity": (
            "green-skinned woman, long wavy black hair, red-orange eyes, "
            "pointed elf ears, slight smile"
        ),
        "clothes": (
            "olive felt witch hat with leather buckle band, plunging olive fitted top, "
            "brown leather shoulder armor, fingerless gloves, wide brown buckle corset belt, "
            "fitted olive pants hugging hips and thighs, brown knee-high leather boots, "
            "olive cape hanging behind the legs, brown side satchel"
        ),
    },
    "fox lady": {
        "identity": (
            "human face, warm pale skin, blue eyes, long black hair in two thick braids, "
            "fox ears, fluffy white fox tail"
        ),
        "clothes": (
            "brown fur-trimmed coat, gold brocade front panel, braided sash, "
            "baggy brown pants with white fur cuffs, brown heeled boots, forearm bracers"
        ),
    },
    "cow girl": {
        "identity": (
            "human face, warm brown skin, green eyes, huge curly black hair, "
            "small cow horns, cow ears, no muzzle, no fur body"
        ),
        "clothes": "white lace-up blouse, blue bow, long blue skirt, black heels, small clutch",
    },
    "leapord": {
        "identity": (
            "human face, light spots, cat ears, tail, no livestock head"
        ),
        "clothes": "recreate the real fitted outfit present on the source, hips visible",
    },
    "sporty bear": {
        "identity": "human face, bear ears, no muzzle, no feral bear head",
        "clothes": "recreate the real sporty outfit present on the source",
    },
    "white hair black skin": {
        "identity": "deep warm brown skin, short curly white hair, icy blue eyes",
        "clothes": "recreate the real clothes present on the source",
    },
    "white coat": {
        "identity": "human woman, long brown hair, blue eyes",
        "clothes": "white lab coat over the real inner outfit present on the source, hips visible",
    },
    "sleepy": {
        "identity": "human woman, long black hair, sleepy expression, headphones around neck",
        "clothes": "oversized white off-shoulder sweatshirt, baggy white sweatpants, red-black sneakers",
    },
    "skirt elf": {
        "identity": "elf woman, pointed ears, recreate the real face and hair present",
        "clothes": "recreate the real skirt outfit present on the source, hips visible",
    },
    "ninja": {
        "identity": "recreate the real face, hair, and skin present on the source",
        "clothes": "recreate the real ninja outfit present on the source, fitted pieces, hips visible",
    },
    "nurse": {
        "identity": "recreate the real face, hair, and skin present on the source",
        "clothes": "recreate the real nurse outfit present on the source",
    },
    "nerd girl": {
        "identity": "recreate the real face, hair, glasses, and skin present on the source",
        "clothes": "recreate the real clothes present on the source",
    },
    "sword gal": {
        "identity": "recreate the real face, hair, and skin present on the source",
        "clothes": "recreate the real fighter clothes present on the source, fitted pants not a dress",
    },
    "tattoo mommy": {
        "identity": "recreate the real face, hair, tattoos, and skin present on the source",
        "clothes": "recreate the real clothes present on the source",
    },
    "dark hinata": {
        "identity": "recreate the real face, hair, and skin present on the source",
        "clothes": "recreate the real clothes present on the source, hips visible",
    },
    "purple girl": {
        "identity": "recreate the real face, purple hair, and skin present on the source",
        "clothes": "recreate the real clothes present on the source",
    },
    "black hair": {
        "identity": "recreate the real face, black hair, and skin present on the source",
        "clothes": "recreate the real clothes present on the source",
    },
    "afro": {
        "identity": (
            "warm medium-brown skin, huge black afro curls, round glasses, "
            "full lips, soft neutral expression"
        ),
        "clothes": (
            "heather grey ribbed turtleneck mini sweater-dress, long sleeves, "
            "glossy black thigh-high heeled boots, hips and thighs visible below hem"
        ),
    },
}

FRAME_CLAUSE = (
    "full body, entire figure, head to toe, feet visible, standing, "
    "single figure only, no collage, no turnaround grid"
)
BODY_CLAUSE = (
    "hourglass figure, very full bust, very full hips, thick thighs, "
    "defined waist, narrower waist than hips"
)
HOUSE_CLAUSE = (
    "wrought style, cinematic game still, painted volume, materials and key light, "
    "grounded stylized realism"
)
ANTHRO_CLAUSE = (
    "kemonomimi, human face with animal ears or small horns and tail, "
    "not a livestock head, not a muzzle, not a feral animal head"
)
NEGATIVE_PROMPT = (
    "close-up, cropped, bust shot, missing feet, livestock head, muzzle, "
    "feral animal head, farm-cow, skinny, petite, fashion model, obese, SSBBW, "
    "no waist, second face, extra face, collage, turnaround grid, "
    "maxi dress, long robe hiding hips, extra limbs, text, watermark, "
    "3d render, blender, octane, product catalog, photoreal catalog, "
    "studio product photo, official style lora, darkbrush, retroanime"
)
# Per-still clothes win over pack defaults when a pack mixes outfits.
STEM_LOOK: dict[str, dict[str, str]] = {
    "fox_lady_concept_01_3q": {
        "clothes": (
            "dark brown string bikini top and matching bikini briefs, "
            "midriff visible, bare legs, bare feet, no coat, no armor, no boots"
        ),
        "negative": "gold armor, shrine robe, hakama, fur coat, boots, armored top",
    },
    "sporty_bear_concept_01_3q": {
        "identity": (
            "anthro bear woman as present on the source, brown bear muzzle and snout, "
            "round bear ears, long dark brown hair in two braids, amber eyes, "
            "not a human-only face, not a feral four-legged bear"
        ),
        "clothes": (
            "orange cropped puffer bomber jacket, white sports tank, "
            "shiny dark brown high-waist leggings with a gold B on the thigh, "
            "white sneakers with red laces"
        ),
        "kemonomimi": False,
    },
    "sporty_bear_concept_02_3q": {
        "identity": (
            "anthro bear woman as present on the source, brown bear muzzle and snout, "
            "round bear ears, long dark brown hair in two braids, amber eyes, "
            "not a human-only face, not a feral four-legged bear"
        ),
        "clothes": (
            "orange cropped puffer bomber jacket, white sports tank, "
            "shiny dark brown high-waist leggings with a gold B on the thigh, "
            "white sneakers with red laces, T-pose"
        ),
        "kemonomimi": False,
    },
    "tattoo_mommy_concept_01_3q": {
        "identity": (
            "the same woman as the source, light olive skin, brown hair in a high bun, "
            "green eyes, full left-arm sleeve tattoos, black choker, drop earring, "
            "athletic hourglass"
        ),
        "clothes": (
            "black sports bra, black thong, barefoot, no extra layers, "
            "no pants, no jacket, tattoos visible"
        ),
        "negative": "dress, jacket, pants, boots, extra outfit, maxi",
    },
    "leapord_concept_03_front": {
        "identity": (
            "kemonomimi leopard woman, human face, warm brown skin, "
            "voluminous curly blonde hair, green eyes, leopard ears, "
            "spotted leopard tail, gold hoop earrings"
        ),
        "clothes": (
            "leopard-print cropped jacket, black tank crop, "
            "dark grey sweatpants with white drawstring, chunky sneakers"
        ),
        "negative": "collage, face inset, livestock head, muzzle, maxi dress",
    },
}

# Optional vision pass on a SAMPLE of 6-8 stills (not the whole 160+ corpus).
VISION_SAMPLE: dict[str, dict[str, Any]] = {
    "witch/witch_concept_01_front.jpg": {
        "crop": "full_body",
        "present_regions": ["face", "hair", "torso_clothes", "legs", "feet", "hands"],
        "notes": "T-pose teacher, feet in frame, fitted olive pants + cape behind",
    },
    "fox lady/fox_lady_concept_01_front.jpg": {
        "crop": "full_body",
        "present_regions": ["face", "hair", "torso_clothes", "legs", "feet", "hands"],
        "notes": "T-pose kemonomimi, feet in frame, fur-trim coat + baggy pants",
    },
    "witch/witch_concept_01_3q.jpg": {
        "crop": "three_quarter",
        "present_regions": ["face", "hair", "torso_clothes", "legs", "hands"],
        "notes": "collage: bust inset + thigh crop + 3q with boots; not a single plate",
    },
    "clothes.jfif": {
        "crop": "clothes_only",
        "present_regions": ["torso_clothes"],
        "notes": "16 headless garment studies, other lane",
    },
    "fox lady/fox_lady_concept_04_back.jpg": {
        "crop": "full_body",
        "present_regions": ["face", "hair", "torso_clothes", "legs", "feet", "hands"],
        "notes": "two-view front/back, feet in frame",
    },
    "white coat/white_coat_concept_03_front.jpg": {
        "crop": "full_body",
        "present_regions": ["face", "hair", "torso_clothes", "legs", "feet", "hands"],
        "notes": "collage with full figure + two face insets",
    },
    "gyaru.jfif": {
        "crop": "three_quarter",
        "present_regions": ["face", "hair", "torso_clothes", "legs", "hands"],
        "notes": "single figure, boots cut mid-shaft, feet not in frame",
    },
    "sleepy/sleepy_concept_01_side.jpg": {
        "crop": "full_body",
        "present_regions": ["face", "hair", "torso_clothes", "legs", "feet", "hands"],
        "notes": "single figure, sneakers in frame",
    },
}

DEFAULT_ROBUST_ROOT = Path(
    r"C:\Users\xXste\Code_Projects\Master-Sculptor\Robust addon checker"
)
DEFAULT_INVENTORY_DIR = Path(
    r"C:\Users\xXste\Code_Projects\SpellVision\runtime\characters\robust_inventory"
)


class LookCompleteError(ValueError):
    """Planner or inventory could not honestly proceed."""


class LookCompleteRefused(LookCompleteError):
    """Fail-closed: this still belongs to another lane or has no character."""


@dataclass
class StillRecord:
    sha256: str
    paths: list[str]
    pack: str | None
    width: int
    height: int
    aspect: float
    crop: str
    present_regions: list[str]
    is_collage: bool
    bytes: int
    primary_path: str
    vision: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if payload.get("vision") is None:
            payload.pop("vision", None)
        return payload


@dataclass
class LookCompletePlan:
    contract: str = CONTRACT
    command: str = "look_complete"
    source_path: str = ""
    crop: str = "unknown"
    present_regions: list[str] = field(default_factory=list)
    missing_regions: list[str] = field(default_factory=list)
    target: str = TARGET_NAME
    target_width: int = TARGET_WIDTH
    target_height: int = TARGET_HEIGHT
    method: str = "t2i_identity"
    prompt: str = ""
    negative_prompt: str = NEGATIVE_PROMPT
    identity_clause: str = ""
    outfit_clause: str = ""
    already_complete: bool = False
    refused: bool = False
    refuse_reason: str = ""
    model: str = ""
    model_family: str = ""
    unet_name: str = ""
    steps: int = DEFAULT_STEPS
    cfg: float = DEFAULT_CFG
    seed: int = 0
    pack: str | None = None
    is_collage: bool = False
    notes: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        """Worker-facing look_complete payload (Clothes+wire registers the command)."""
        if self.refused:
            raise LookCompleteRefused(self.refuse_reason or "look_complete refused")
        return {
            "command": "look_complete",
            "input_image": self.source_path,
            "present_regions": list(self.present_regions),
            "missing_regions": list(self.missing_regions),
            "target": TARGET_NAME,
            "width": TARGET_WIDTH,
            "height": TARGET_HEIGHT,
            "method": self.method,
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
            "identity_prompt": self.identity_clause,
            "model": self.model,
            "model_family": self.model_family,
            "unet_name": self.unet_name,
            "steps": self.steps,
            "cfg": self.cfg,
            "seed": self.seed,
            "crop": self.crop,
            "already_complete": self.already_complete,
            "pack": self.pack,
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_robust_root() -> Path:
    env = os.environ.get("SPELLVISION_ROBUST_ROOT", "").strip()
    if env:
        return Path(env).expanduser()
    return DEFAULT_ROBUST_ROOT


def default_inventory_dir() -> Path:
    return DEFAULT_INVENTORY_DIR


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def iter_image_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            files.append(path)
    return files


def pack_from_relpath(rel: str) -> str | None:
    if not rel:
        return None
    head = rel.replace("\\", "/").split("/", 1)[0]
    if head in KNOWN_PACKS:
        return head
    return None


def _stem_tokens(name: str) -> str:
    return name.lower().replace("_", " ").replace("-", " ")


def filename_suggests_clothes_only(name: str) -> bool:
    token = _stem_tokens(Path(name).stem)
    if "concept" in token:
        return False
    return any(key in token for key in _CLOTHES_ONLY_TOKENS)


def filename_suggests_face_study(name: str) -> bool:
    token = _stem_tokens(Path(name).stem)
    return token in {"lips", "lips2", "lips3", "lips4"} or token.startswith("lips ")


def _open_rgb(path: Path):
    from PIL import Image

    with Image.open(path) as im:
        return im.convert("RGB")


def _content_mask(rgb) -> Any:
    """Non-background mask. Robust sheets are usually near-white; some are grey."""
    import numpy as np

    arr = np.asarray(rgb, dtype=np.int16)
    # Near-white studio sheet.
    white = (arr[:, :, 0] >= 242) & (arr[:, :, 1] >= 242) & (arr[:, :, 2] >= 242)
    # Flat grey / beige studio (sleepy, some fashion).
    mx = arr.max(axis=2)
    mn = arr.min(axis=2)
    flat = (mx - mn <= 12) & (mn >= 160)
    bg = white | flat
    return ~bg


def figure_metrics(rgb) -> dict[str, Any]:
    import numpy as np

    mask = _content_mask(rgb)
    h, w = mask.shape
    total = int(mask.size)
    count = int(mask.sum())
    fill = count / float(total) if total else 0.0
    if count < 32:
        return {
            "width": w,
            "height": h,
            "aspect": round(w / float(h), 4) if h else 0.0,
            "fill": fill,
            "bbox": None,
            "vertical_span": 0.0,
            "top_gap": 1.0,
            "bottom_gap": 1.0,
            "bottom_touch_ratio": 0.0,
            "component_count": 0,
            "is_collage": False,
            "top_fill": 0.0,
            "mid_fill": 0.0,
            "bot_fill": 0.0,
        }

    ys, xs = np.where(mask)
    y0, y1 = int(ys.min()), int(ys.max())
    x0, x1 = int(xs.min()), int(xs.max())
    bbox_h = max(1, y1 - y0 + 1)
    vertical_span = bbox_h / float(h)
    top_gap = y0 / float(h)
    bottom_gap = (h - 1 - y1) / float(h)
    edge_band = mask[max(0, h - max(2, h // 40)) :, :]
    bottom_touch = float(edge_band.mean()) if edge_band.size else 0.0

    # Connected components for collage / turnaround detection.
    visited = np.zeros_like(mask, dtype=bool)
    components = 0
    min_area = max(80, int(0.02 * count))
    yy, xx = np.where(mask)
    # Sample-strided flood to stay cheap on 1k+ stills.
    step = 4 if count > 80_000 else 2
    from collections import deque

    for i in range(0, len(yy), step * 8):
        y, x = int(yy[i]), int(xx[i])
        if visited[y, x] or not mask[y, x]:
            continue
        area = 0
        q = deque([(y, x)])
        visited[y, x] = True
        while q:
            cy, cx = q.popleft()
            area += 1
            for ny, nx in ((cy - 2, cx), (cy + 2, cx), (cy, cx - 2), (cy, cx + 2)):
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not visited[ny, nx]:
                    visited[ny, nx] = True
                    q.append((ny, nx))
        if area * (step * step) >= min_area:
            components += 1
        if components >= 6:
            break

    third = max(1, h // 3)
    top_fill = float(mask[:third, :].mean())
    mid_fill = float(mask[third : 2 * third, :].mean())
    bot_fill = float(mask[2 * third :, :].mean())
    is_collage = components >= 3 and fill > 0.12
    return {
        "width": w,
        "height": h,
        "aspect": round(w / float(h), 4) if h else 0.0,
        "fill": round(fill, 4),
        "bbox": [x0, y0, x1, y1],
        "vertical_span": round(vertical_span, 4),
        "top_gap": round(top_gap, 4),
        "bottom_gap": round(bottom_gap, 4),
        "bottom_touch_ratio": round(bottom_touch, 4),
        "component_count": components,
        "is_collage": is_collage,
        "top_fill": round(top_fill, 4),
        "mid_fill": round(mid_fill, 4),
        "bot_fill": round(bot_fill, 4),
    }


def classify_crop(
    *,
    name: str,
    width: int,
    height: int,
    metrics: Mapping[str, Any] | None = None,
) -> tuple[str, bool]:
    """Return (crop_class, is_collage). Filename + aspect + simple figure metrics."""
    if filename_suggests_clothes_only(name):
        return "clothes_only", False
    if filename_suggests_face_study(name):
        return "face", False

    aspect = (width / float(height)) if height else 1.0
    collage = bool(metrics and metrics.get("is_collage"))
    token = _stem_tokens(Path(name).stem)

    if metrics:
        span = float(metrics.get("vertical_span") or 0.0)
        bottom_gap = float(metrics.get("bottom_gap") or 1.0)
        top_gap = float(metrics.get("top_gap") or 1.0)
        bot_fill = float(metrics.get("bot_fill") or 0.0)
        mid_fill = float(metrics.get("mid_fill") or 0.0)
        top_fill = float(metrics.get("top_fill") or 0.0)
        touch = float(metrics.get("bottom_touch_ratio") or 0.0)
        # Empty canvas / nearly empty.
        if span < 0.08:
            return "unknown", collage
        # Face: content lives in the upper third.
        if span <= 0.45 and top_gap < 0.25 and bot_fill < 0.04 and mid_fill < 0.08:
            return "face", collage
        # Empty lower canvas is the bust/face tell — even if mid-band is busy.
        if bottom_gap >= 0.20 and span <= 0.82:
            if span <= 0.45 and mid_fill < 0.08:
                return "face", collage
            return "bust", collage
        # Bust: upper + mid, little/no legs.
        if span <= 0.72 and bot_fill < 0.08 and (top_fill + mid_fill) > bot_fill * 2.5:
            return "bust", collage
        # Three-quarter: figure reaches the bottom but is a wide truncation,
        # or named _3q, or squat portrait that is not tall enough for feet.
        named_3q = "_3q" in Path(name).stem.lower() or " 3q" in token
        truncated = touch >= 0.18 and aspect >= 0.70 and bottom_gap < 0.08
        squat = aspect >= 0.72 and span >= 0.70 and bottom_gap < 0.08
        if named_3q or truncated or squat:
            return "three_quarter", collage
        # Full body: tall figure, feet zone occupied, not a wide bottom chop.
        if span >= 0.78 and bot_fill >= 0.04 and aspect <= 0.78:
            return "full_body", collage
        if span >= 0.70 and bottom_gap < 0.10 and bot_fill >= 0.05 and aspect <= 0.70:
            return "full_body", collage
        if mid_fill >= 0.08 and bot_fill < 0.05:
            return "bust", collage
        if mid_fill >= 0.08:
            return "three_quarter", collage

    # Aspect-only fallback (no pixels, or degenerate metrics).
    if aspect <= 0.62:
        return "full_body", collage
    if aspect <= 0.78:
        return "three_quarter", collage
    if aspect <= 1.15:
        return "bust", collage
    return "unknown", collage


def regions_for_crop(crop: str, *, collage: bool = False) -> list[str]:
    if crop == "clothes_only":
        return ["torso_clothes"]
    if crop == "face":
        return ["face", "hair"]
    if crop == "bust":
        return ["face", "hair", "torso_clothes", "hands"]
    if crop == "three_quarter":
        return ["face", "hair", "torso_clothes", "legs", "hands"]
    if crop == "full_body":
        return ["face", "hair", "torso_clothes", "legs", "feet", "hands"]
    if collage:
        return ["face", "hair", "torso_clothes"]
    return ["face", "hair", "torso_clothes"]


def classify_still(path: Path, *, rel: str | None = None) -> dict[str, Any]:
    name = rel or path.name
    from PIL import Image

    with Image.open(path) as im:
        rgb = im.convert("RGB")
        width, height = rgb.size
    metrics = figure_metrics(rgb)
    crop, collage = classify_crop(
        name=name, width=width, height=height, metrics=metrics
    )
    regions = regions_for_crop(crop, collage=collage)
    return {
        "width": width,
        "height": height,
        "aspect": round(width / float(height), 4) if height else 0.0,
        "crop": crop,
        "is_collage": collage,
        "present_regions": regions,
        "metrics": metrics,
    }


def inventory_robust(
    root: Path | None = None,
    *,
    apply_vision_sample: bool = True,
) -> dict[str, Any]:
    root = Path(root or default_robust_root())
    if not root.is_dir():
        raise LookCompleteError(f"Robust root is not a directory: {root}")

    grouped: dict[str, dict[str, Any]] = {}
    files_seen = 0
    for path in iter_image_files(root):
        files_seen += 1
        rel = path.relative_to(root).as_posix()
        digest = sha256_file(path)
        bucket = grouped.get(digest)
        if bucket is None:
            info = classify_still(path, rel=rel)
            bucket = {
                "sha256": digest,
                "paths": [rel],
                "bytes": path.stat().st_size,
                "pack": pack_from_relpath(rel),
                **{k: info[k] for k in ("width", "height", "aspect", "crop", "is_collage", "present_regions")},
            }
            grouped[digest] = bucket
        else:
            bucket["paths"].append(rel)
            if bucket.get("pack") is None:
                bucket["pack"] = pack_from_relpath(rel)

    vision_hits: list[dict[str, Any]] = []
    if apply_vision_sample:
        by_rel = {}
        for bucket in grouped.values():
            for rel in bucket["paths"]:
                by_rel[rel] = bucket
        for rel, sample in VISION_SAMPLE.items():
            bucket = by_rel.get(rel)
            if bucket is None:
                continue
            bucket["vision"] = sample
            vision_hits.append({"path": rel, **sample, "heuristic_crop": bucket["crop"]})

    entries = []
    crop_hist: dict[str, int] = {key: 0 for key in CROP_CLASSES}
    for digest, bucket in grouped.items():
        paths = sorted(bucket["paths"])
        pack = bucket.get("pack")
        if pack is None:
            for rel in paths:
                pack = pack_from_relpath(rel)
                if pack:
                    break
        record = StillRecord(
            sha256=digest,
            paths=paths,
            pack=pack,
            width=int(bucket["width"]),
            height=int(bucket["height"]),
            aspect=float(bucket["aspect"]),
            crop=str(bucket["crop"]),
            present_regions=list(bucket["present_regions"]),
            is_collage=bool(bucket.get("is_collage")),
            bytes=int(bucket["bytes"]),
            primary_path=paths[0],
            vision=bucket.get("vision"),
        )
        crop_hist[record.crop] = crop_hist.get(record.crop, 0) + 1
        entries.append(record.to_dict())
    entries.sort(key=lambda row: (row.get("pack") or "zzz", row["primary_path"]))

    packs_found = sorted(
        {row["pack"] for row in entries if row.get("pack")}
    )
    dupes = sum(1 for row in entries if len(row["paths"]) > 1)
    return {
        "contract": CONTRACT,
        "source_root": str(root),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "packs": packs_found,
        "counts": {
            "files_seen": files_seen,
            "unique_hashes": len(entries),
            "duplicate_groups": dupes,
            "duplicate_extra_files": files_seen - len(entries),
            "packs": len(packs_found),
        },
        "crop_histogram": crop_hist,
        "vision_sample": vision_hits,
        "entries": entries,
    }


def write_inventory(
    index: Mapping[str, Any],
    dest_dir: Path | None = None,
) -> Path:
    dest_dir = Path(dest_dir or default_inventory_dir())
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / "index.json"
    out.write_text(json.dumps(index, indent=2), encoding="utf-8")
    log.warning("wrote inventory %s unique=%s", out, index.get("counts", {}).get("unique_hashes"))
    return out


def write_inventory_readme(dest_dir: Path, index: Mapping[str, Any]) -> Path:
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    counts = index.get("counts", {})
    hist = index.get("crop_histogram", {})
    lines = [
        "# Robust inventory (look-complete)",
        "",
        f"Contract: `{index.get('contract', CONTRACT)}`",
        f"Source: `{index.get('source_root', '')}`",
        f"Generated: `{index.get('generated_at', '')}`",
        "",
        "## Counts",
        "",
        f"- packs: **{counts.get('packs', 0)}** ({', '.join(index.get('packs') or [])})",
        f"- files seen: **{counts.get('files_seen', 0)}**",
        f"- unique hashes: **{counts.get('unique_hashes', 0)}**",
        f"- extra byte-dupes: **{counts.get('duplicate_extra_files', 0)}**",
        "",
        "## Crop histogram (unique hashes)",
        "",
    ]
    for key in CROP_CLASSES:
        lines.append(f"- `{key}`: {hist.get(key, 0)}")
    lines += [
        "",
        "## How this is used",
        "",
        "Character Studio + 14517 morphs need **768×1344 head-to-toe** (feet visible).",
        "Many Robust stills are bust / 3q / collage. `look_completion.plan_look_complete`",
        "emits a `look_complete` payload that recreates the **real clothes present**",
        "and extends downward. Clothes-only stills are refused (other lane).",
        "",
        "Producer stays **Utopic Quants** (`loxsUtopicWorldKrea2_v10Quants.safetensors`).",
        "Refs become prompts / outpaint condition — never I2I-photocopy a Grok still.",
        "",
        "Vision was run on a **sample of 8** stills, not the whole corpus. Heuristics",
        "label the rest. See `vision_sample` in `index.json`.",
        "",
        "Proofs from the live smoke live in `proofs/`.",
        "",
    ]
    path = dest_dir / "README.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _normalize_regions(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = [part.strip() for part in raw.replace(";", ",").split(",")]
    elif isinstance(raw, Sequence):
        parts = [str(item).strip() for item in raw]
    else:
        raise LookCompleteError("present_regions must be a list or comma string")
    out: list[str] = []
    for part in parts:
        if not part:
            continue
        if part not in PRESENT_REGIONS:
            raise LookCompleteError(f"unknown region {part!r}")
        if part not in out:
            out.append(part)
    return out


def missing_from(present: Sequence[str]) -> list[str]:
    have = set(present)
    return [name for name in PRESENT_REGIONS if name not in have]


def _look_for_source(path: Path | None, pack: str | None) -> tuple[str, str]:
    stem = path.stem.lower() if path else ""
    if stem in STEM_LOOK:
        row = STEM_LOOK[stem]
        clothes = row["clothes"]
        if row.get("identity"):
            return row["identity"], clothes
        ident = "recreate the same specific woman present in the source, same face, same hair, same skin"
        if pack and pack in PACK_LOOK:
            ident = PACK_LOOK[pack]["identity"]
        return ident, clothes
    if pack and pack in PACK_LOOK:
        row = PACK_LOOK[pack]
        return row["identity"], row["clothes"]
    name = _stem_tokens(path.stem) if path else ""
    identity = "recreate the same specific woman present in the source, same face, same hair, same skin"
    clothes = "recreate the real clothes present on the source, same pieces and colors, hips visible unless the garment is honestly long"
    if "witch" in name:
        return PACK_LOOK["witch"]["identity"], PACK_LOOK["witch"]["clothes"]
    if "fox" in name:
        return PACK_LOOK["fox lady"]["identity"], PACK_LOOK["fox lady"]["clothes"]
    return identity, clothes


def build_identity_prompt(
    *,
    present: Sequence[str],
    pack: str | None,
    source: Path | None,
    identity_hint: str = "",
    outfit_hint: str = "",
) -> tuple[str, str, str]:
    ident, clothes = _look_for_source(source, pack)
    if identity_hint.strip():
        ident = identity_hint.strip()
    if outfit_hint.strip():
        clothes = outfit_hint.strip()
    if pack in _ANTHRO_PACKS:
        stem = source.stem.lower() if source else ""
        if STEM_LOOK.get(stem, {}).get("kemonomimi", True) is not False:
            ident = f"{ANTHRO_CLAUSE}, {ident}"
    keep: list[str] = []
    if "face" in present or "hair" in present:
        keep.append("same face and hair as the source description")
    if "torso_clothes" in present:
        keep.append("same torso clothes continued downward, do not swap the outfit")
    if "legs" in present:
        keep.append("same legwear continued to the shoes")
    clauses = [
        FRAME_CLAUSE,
        ident,
        clothes,
        BODY_CLAUSE,
        HOUSE_CLAUSE,
        *keep,
        "extend the existing look downward until both feet are in frame",
    ]
    prompt = ", ".join(part for part in clauses if part)
    return ident, clothes, prompt


def plan_look_complete(
    source: str | Path | None = None,
    *,
    present_regions: Any = None,
    crop: str | None = None,
    method: str | None = None,
    identity_hint: str = "",
    outfit_hint: str = "",
    seed: int = 0,
    pack: str | None = None,
    classify_pixels: bool = True,
) -> LookCompletePlan:
    """Emit a LookCompletePlan for one still. Refuses clothes-only / no-character."""
    path = Path(source) if source else None
    detected: dict[str, Any] = {}
    if path is not None and path.is_file() and classify_pixels:
        try:
            detected = classify_still(path, rel=path.name)
        except Exception as exc:
            log.warning("classify failed for %s: %s", path, exc)
            detected = {}

    crop_name = (crop or detected.get("crop") or "unknown").strip().lower()
    if crop_name not in CROP_CLASSES:
        raise LookCompleteError(f"unknown crop {crop_name!r}")

    if present_regions is None:
        regions = list(detected.get("present_regions") or regions_for_crop(crop_name))
    else:
        regions = _normalize_regions(present_regions)

    pack_name = pack or (pack_from_relpath(path.as_posix()) if path else None)
    if pack_name is None and path is not None:
        # parent folder may be the pack even when we were handed an absolute path
        pack_name = pack_from_relpath(f"{path.parent.name}/{path.name}")

    collage = bool(detected.get("is_collage"))
    character_signal = any(name in regions for name in ("face", "hair"))
    clothes_only = crop_name == "clothes_only" or (
        "torso_clothes" in regions and not character_signal and "legs" not in regions
    )
    if clothes_only or (not character_signal and crop_name in {"clothes_only", "unknown"} and "torso_clothes" in regions):
        reason = (
            "source is clothes-only with no character; use the clothes_only lane"
        )
        return LookCompletePlan(
            source_path=str(path) if path else "",
            crop="clothes_only",
            present_regions=regions or ["torso_clothes"],
            missing_regions=[],
            method="refuse",
            refused=True,
            refuse_reason=reason,
            pack=pack_name,
            notes=[reason],
        )
    if not character_signal:
        reason = "no face/hair present — not a character still; refuse look_complete"
        return LookCompletePlan(
            source_path=str(path) if path else "",
            crop=crop_name,
            present_regions=regions,
            missing_regions=[],
            method="refuse",
            refused=True,
            refuse_reason=reason,
            pack=pack_name,
            notes=[reason],
        )

    missing = missing_from(regions)
    already = crop_name == "full_body" and "feet" in regions and not missing
    ident, clothes, prompt = build_identity_prompt(
        present=regions,
        pack=pack_name,
        source=path,
        identity_hint=identity_hint,
        outfit_hint=outfit_hint,
    )
    chosen = (method or "").strip().lower()
    if already:
        chosen = "noop"
    elif chosen not in {"t2i_identity", "pad_inpaint"}:
        # Default: T2I with a tight identity clause. Never I2I-photocopy.
        chosen = "t2i_identity"

    notes = []
    if collage:
        notes.append("source looks like a collage/sheet; T2I single-figure, do not photocopy the grid")
    if "feet" in missing:
        notes.append("synthesize feet-in-frame downward extension")
    if "legs" in missing:
        notes.append("synthesize legs continuing the real present outfit")

    return LookCompletePlan(
        source_path=str(path) if path else "",
        crop=crop_name,
        present_regions=regions,
        missing_regions=missing,
        method=chosen,
        prompt=prompt,
        identity_clause=ident,
        outfit_clause=clothes,
        already_complete=already,
        pack=pack_name,
        is_collage=collage,
        seed=int(seed),
        notes=notes,
        negative_prompt=(
            f"{NEGATIVE_PROMPT}, {STEM_LOOK[path.stem.lower()]['negative']}"
            if path is not None and path.stem.lower() in STEM_LOOK and STEM_LOOK[path.stem.lower()].get("negative")
            else NEGATIVE_PROMPT
        ),
    )


def payload_from_request(request: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a worker-shaped look_complete request and return the plan payload."""
    image = str(request.get("input_image") or request.get("source") or "").strip()
    if not image:
        raise LookCompleteError("input_image is required")
    model = str(request.get("model") or "").strip()
    if not model:
        raise LookCompleteError("model is required")
    target = str(request.get("target") or TARGET_NAME).strip()
    if target not in {TARGET_NAME, "full_body", "768x1344"}:
        raise LookCompleteError(f"unsupported target {target!r}")
    plan = plan_look_complete(
        image,
        present_regions=request.get("present_regions"),
        crop=request.get("crop"),
        method=request.get("method"),
        identity_hint=str(request.get("identity_prompt") or request.get("identity_hint") or ""),
        outfit_hint=str(request.get("outfit_hint") or ""),
        seed=int(request.get("seed") or 0),
        pack=request.get("pack"),
        classify_pixels=Path(image).is_file(),
    )
    if plan.refused:
        raise LookCompleteRefused(plan.refuse_reason)
    plan.model = model
    plan.unet_name = str(request.get("unet_name") or Path(model).name)
    family = str(request.get("model_family") or "").strip()
    if family:
        plan.model_family = family
    payload = plan.to_payload()
    payload["target"] = TARGET_NAME
    return payload


def build_krea2_t2i_graph(
    *,
    prompt: str,
    negative_prompt: str = NEGATIVE_PROMPT,
    unet_name: str = PRODUCER_UNET,
    clip_name: str = CLIP_NAME,
    vae_name: str = VAE_NAME,
    width: int = TARGET_WIDTH,
    height: int = TARGET_HEIGHT,
    seed: int = 0,
    steps: int = DEFAULT_STEPS,
    cfg: float = DEFAULT_CFG,
    filename_prefix: str = "look_complete",
) -> dict[str, Any]:
    """Empty-latent Krea2 T2I at 768x1344. Proven class_types from native_image_graphs."""
    if not str(prompt or "").strip():
        raise LookCompleteError("prompt is required")
    if width % 16 or height % 16:
        raise LookCompleteError("width/height must be divisible by 16")
    cfg_f = float(cfg)
    if cfg_f <= 0.0:
        cfg_f = 1.0
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": unet_name, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": clip_name, "type": "krea2"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae_name}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": negative_prompt, "clip": ["2", 0]}},
        "7": {
            "class_type": "EmptySD3LatentImage",
            "inputs": {"width": int(width), "height": int(height), "batch_size": 1},
        },
        "5": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 1.15}},
        "8": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["5", 0],
                "seed": int(seed),
                "steps": int(steps),
                "cfg": cfg_f,
                "sampler_name": "euler",
                "scheduler": "simple",
                "positive": ["4", 0],
                "negative": ["6", 0],
                "latent_image": ["7", 0],
                "denoise": 1.0,
            },
        },
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": filename_prefix}},
    }


def pad_source_to_canvas(
    source: Path,
    dest_canvas: Path,
    dest_mask: Path,
    *,
    width: int = TARGET_WIDTH,
    height: int = TARGET_HEIGHT,
    overlap: int = 28,
) -> dict[str, Any]:
    """Place the source at the top of 768x1344 and mask the empty downward band."""
    from PIL import Image, ImageDraw

    src = _open_rgb(source)
    sw, sh = src.size
    scale = min(width / float(sw), height / float(sh), 1.0)
    # Prefer filling width so a bust/3q sits in the upper canvas.
    scale = min(width / float(sw), 1.0)
    nw = max(1, int(sw * scale))
    nh = max(1, int(sh * scale))
    if nh > height:
        scale = height / float(sh)
        nw = max(1, int(sw * scale))
        nh = max(1, int(sh * scale))
    resized = src.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (width, height), (248, 248, 248))
    x = (width - nw) // 2
    y = 0
    canvas.paste(resized, (x, y))
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    band_top = max(0, y + nh - overlap)
    draw.rectangle((0, band_top, width, height), fill=255)
    dest_canvas.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dest_canvas)
    mask.save(dest_mask)
    return {
        "canvas": str(dest_canvas),
        "mask": str(dest_mask),
        "placed": [x, y, nw, nh],
        "band_top": band_top,
    }


def build_look_complete_inpaint_graph(
    *,
    lock_image: str,
    mask_image: str,
    plan: LookCompletePlan,
    filename_prefix: str = "look_complete_inpaint",
) -> dict[str, Any]:
    """Pad-to-canvas empty-band inpaint. Reuses krea2_regional_inpaint (do not edit that file)."""
    from krea2_regional_inpaint import build_krea2_regional_inpaint_graph

    edit = (
        f"{FRAME_CLAUSE}, continue the same outfit downward, "
        f"{plan.outfit_clause or 'same real clothes'}, both feet visible, "
        "do not change the face or hair already present"
    )
    return build_krea2_regional_inpaint_graph(
        unet_name=plan.unet_name,
        lock_image=lock_image,
        mask_image=mask_image,
        edit_prompt=edit,
        identity_prompt=plan.identity_clause,
        negative_prompt=plan.negative_prompt,
        seed=plan.seed,
        steps=plan.steps,
        cfg=plan.cfg,
        filename_prefix=filename_prefix,
        denoise=0.85,
    )


def build_graph_for_plan(
    plan: LookCompletePlan,
    *,
    lock_image: str | None = None,
    mask_image: str | None = None,
    filename_prefix: str = "look_complete",
) -> dict[str, Any]:
    if plan.refused:
        raise LookCompleteRefused(plan.refuse_reason)
    if plan.method == "noop":
        raise LookCompleteError("source is already full_body with feet; nothing to generate")
    if plan.method == "pad_inpaint":
        if not lock_image or not mask_image:
            raise LookCompleteError("pad_inpaint requires lock_image and mask_image")
        return build_look_complete_inpaint_graph(
            lock_image=lock_image,
            mask_image=mask_image,
            plan=plan,
            filename_prefix=filename_prefix,
        )
    return build_krea2_t2i_graph(
        prompt=plan.prompt,
        negative_prompt=plan.negative_prompt,
        unet_name=plan.unet_name,
        seed=plan.seed,
        steps=plan.steps,
        cfg=plan.cfg,
        filename_prefix=filename_prefix,
    )


def comfy_url() -> str:
    return (
        os.environ.get("COMFY_API_URL")
        or os.environ.get("SPELLVISION_COMFY_URL")
        or COMFY_URL
    ).rstrip("/")


def upload_comfy_image(path: Path, *, api: str | None = None) -> str:
    api = (api or comfy_url()).rstrip("/")
    data = path.read_bytes()
    boundary = "----svlc" + str(int(time.time() * 1000))
    body = bytearray()
    body += (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{path.name}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode()
    body += data + b"\r\n"
    for field_name, value in (("type", "input"), ("overwrite", "true")):
        body += (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{field_name}"\r\n\r\n{value}\r\n'
        ).encode()
    body += f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{api}/upload/image",
        data=bytes(body),
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "Connection": "close"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode())
    return str(payload["name"])


def submit_comfy_prompt(graph: Mapping[str, Any], *, api: str | None = None, client_id: str = "sv-look-complete") -> str:
    api = (api or comfy_url()).rstrip("/")
    req = urllib.request.Request(
        f"{api}/prompt",
        data=json.dumps({"prompt": dict(graph), "client_id": client_id}).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "Connection": "close"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        enq = json.loads(resp.read().decode())
    prompt_id = str(enq.get("prompt_id") or "").strip()
    if not prompt_id:
        raise LookCompleteError(f"Comfy /prompt did not return prompt_id: {enq}")
    return prompt_id


def wait_comfy_output(
    stem: str,
    started: float,
    *,
    timeout: float = 600.0,
    out_dir: Path | None = None,
) -> Path:
    out_dir = Path(out_dir or COMFY_OUTPUT)
    deadline = time.time() + timeout
    while time.time() < deadline:
        hits = [
            path
            for path in out_dir.glob(f"{stem}*.png")
            if path.is_file() and path.stat().st_size > 4000 and path.stat().st_mtime >= started - 2
        ]
        if hits:
            return max(hits, key=lambda path: path.stat().st_mtime)
        time.sleep(6)
    raise LookCompleteError(f"Comfy output timeout for stem {stem!r}")


def run_look_complete(
    source: str | Path,
    dest_dir: Path,
    *,
    method: str | None = None,
    seed: int = 4419,
    timeout: float = 600.0,
    model: str = "",
    unet_name: str = "",
) -> dict[str, Any]:
    """Live smoke: plan + generate one completed still. Never POST /free."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    model = str(model or "").strip()
    if not model:
        raise LookCompleteError("model is required")
    plan = plan_look_complete(source, method=method, seed=seed)
    plan.model = model
    plan.unet_name = str(unet_name or "").strip() or Path(model).name
    if plan.refused:
        raise LookCompleteRefused(plan.refuse_reason)
    if plan.already_complete and plan.method == "noop":
        report = {
            "ok": True,
            "verdict": "already_complete",
            "plan": plan.to_dict(),
            "output": None,
        }
        (dest_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report

    stem = f"look_complete_{Path(plan.source_path).stem}_{plan.method}_{seed}"
    lock_name = mask_name = None
    extra: dict[str, Any] = {}
    if plan.method == "pad_inpaint":
        canvas = dest_dir / f"{stem}_canvas.png"
        mask = dest_dir / f"{stem}_mask.png"
        extra = pad_source_to_canvas(Path(plan.source_path), canvas, mask)
        lock_name = upload_comfy_image(canvas)
        mask_name = upload_comfy_image(mask)
    graph = build_graph_for_plan(
        plan,
        lock_image=lock_name,
        mask_image=mask_name,
        filename_prefix=stem,
    )
    started = time.time()
    prompt_id = submit_comfy_prompt(graph)
    log.warning("look_complete enqueued prompt_id=%s stem=%s", prompt_id, stem)
    produced = wait_comfy_output(stem, started, timeout=timeout)
    dest = dest_dir / f"{stem}.png"
    dest.write_bytes(produced.read_bytes())
    report = {
        "ok": True,
        "verdict": "generated",
        "prompt_id": prompt_id,
        "output": str(dest),
        "comfy_output": str(produced),
        "elapsed_sec": round(time.time() - started, 1),
        "plan": plan.to_dict(),
        "pad": extra,
        "house": "utopic_quants",
        "note": "vision-check identity / outfit / feet before calling this a keeper",
    }
    (dest_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (dest_dir / f"{stem}_prompt.txt").write_text(plan.prompt, encoding="utf-8")
    return report


def _cmd_inventory(args: argparse.Namespace) -> int:
    index = inventory_robust(Path(args.root) if args.root else default_robust_root())
    dest = Path(args.out) if args.out else default_inventory_dir()
    write_inventory(index, dest)
    write_inventory_readme(dest, index)
    print(json.dumps({"ok": True, "out": str(dest / "index.json"), "counts": index["counts"], "crop_histogram": index["crop_histogram"]}, indent=2))
    return 0


def _cmd_plan(args: argparse.Namespace) -> int:
    plan = plan_look_complete(
        args.image,
        present_regions=args.regions,
        method=args.method,
        seed=args.seed,
    )
    payload = None
    if not plan.refused:
        payload = plan.to_payload()
    print(json.dumps({"plan": plan.to_dict(), "payload": payload}, indent=2))
    return 1 if plan.refused else 0


def _cmd_complete(args: argparse.Namespace) -> int:
    report = run_look_complete(
        args.image,
        Path(args.out),
        method=args.method,
        seed=args.seed,
        timeout=args.timeout,
    )
    print(json.dumps({k: report[k] for k in report if k != "plan"}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="look_completion")
    sub = parser.add_subparsers(dest="cmd", required=True)
    inv = sub.add_parser("inventory", help="hash + classify Robust stills")
    inv.add_argument("--root", default=str(default_robust_root()))
    inv.add_argument("--out", default=str(default_inventory_dir()))
    inv.set_defaults(func=_cmd_inventory)
    pl = sub.add_parser("plan", help="emit a LookCompletePlan / payload")
    pl.add_argument("--image", required=True)
    pl.add_argument("--regions", default=None)
    pl.add_argument("--method", default=None)
    pl.add_argument("--seed", type=int, default=0)
    pl.set_defaults(func=_cmd_plan)
    sm = sub.add_parser("complete", help="live Comfy smoke (never /free)")
    sm.add_argument("--image", required=True)
    sm.add_argument("--out", default=str(default_inventory_dir() / "proofs"))
    sm.add_argument("--method", default="t2i_identity")
    sm.add_argument("--seed", type=int, default=4419)
    sm.add_argument("--timeout", type=float, default=600.0)
    sm.set_defaults(func=_cmd_complete)
    return parser


def run_look_complete_job(req: dict[str, Any], emitter: Any, job: Any, active_job: Any) -> dict[str, Any]:
    """Worker dispatch entry. Fail closed. Never POST /free."""
    from worker_service_state import JobState, complete_job, transition_job

    source = str(req.get("input_image") or req.get("source") or "").strip()
    if not source:
        raise LookCompleteError("look_complete requires input_image")
    model = str(req.get("model") or "").strip()
    if not model:
        raise LookCompleteError("look_complete requires model")
    dest_dir = Path(
        str(req.get("dest") or req.get("output_dir") or default_inventory_dir() / "proofs")
    )
    method = str(req.get("method") or "").strip() or None
    try:
        seed = int(req.get("seed") or 4419)
    except Exception:
        seed = 4419
    if emitter is not None and job is not None:
        transition_job(job, JobState.STARTING)
        emitter.status(job, f"look_complete: {Path(source).name}")
        emitter.emit_job_update(job)
        transition_job(job, JobState.RUNNING)
    payload = run_look_complete(
        source,
        dest_dir,
        method=method,
        seed=seed,
        model=model,
        unet_name=str(req.get("unet_name") or ""),
    )
    if emitter is not None:
        emitter.status(job, f"look_complete {payload.get('verdict')} {payload.get('output')}")
    if job is not None:
        complete_job(job, payload)
        if emitter is not None:
            emitter.emit_job_update(job)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING)
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
