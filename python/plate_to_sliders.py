"""Fail-closed plate → slider solve for Path B packs.

Clothes stills are not figure plates. Face stills cannot drive missing face
families. Performance B1–B5 are never identity. Completeness stays false.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

CONTRACT = "spellbound.plate-to-sliders.v1"

# Shipped identity sliders only (must match MorphCoverage shipped_layer ids).
SHIPPED_IDENTITY = frozenset(
    {
        "shoulders_wide",
        "shoulders_narrow",
        "hips_wide",
        "hips_narrow",
        "waist_wide",
        "waist_slim",
        "belly_full",
        "belly_tone",
        "weight_heavy",
        "weight_thin",
        "muscle_toned",
        "muscle_soft",
        "pectoral",
        "breast_size",
        "breast_fullness",
        "breast_saggy",
        "bust_large",
        "bust_small",
        "glute_volume",
        "thigh_thick",
        "thigh_slim",
        "calf_thick",
        "upperarm_thick",
        "jaw_wide",
        "jaw_narrow",
        "chin_forward",
        "chin_back",
    }
)

_PERF_PREFIXES = ("breath_", "blink_", "speech_", "flex_", "soft_")
_FACE_BLOCKED = (
    "cheek",
    "nose",
    "eye_spacing",
    "brow",
    "lips",
    "ear",
)


class PlateToSlidersError(ValueError):
    """The pack cannot honestly produce identity sliders."""


def _kind(name: str) -> str:
    n = name.lower()
    if "face" in n:
        return "face"
    if "cloth" in n or "garment" in n:
        return "clothes"
    if "figure" in n or n.startswith("body_") or "_body_" in n:
        return "figure"
    return "other"


def plate_to_sliders_complete() -> bool:
    return False


def solve_plate_to_sliders(request: Mapping[str, Any]) -> dict[str, Any]:
    """Inspect a Jarvis pack and refuse clothes-as-WHR / missing families."""

    if request.get("clothes_as_figure") or request.get("measure_clothes_whr"):
        raise PlateToSlidersError("clothes stills cannot drive WHR / identity sliders")

    proposed = request.get("sliders") or {}
    if not isinstance(proposed, Mapping):
        raise PlateToSlidersError("sliders must be an object")
    for key, raw in proposed.items():
        name = str(key)
        if any(name.startswith(p) for p in _PERF_PREFIXES):
            raise PlateToSlidersError(f"{name} is a performance channel, not identity")
        if name not in SHIPPED_IDENTITY:
            raise PlateToSlidersError(f"{name} is not a shipped identity slider")
        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise PlateToSlidersError(f"{name} must be a finite 0..1 float") from exc
        if value != value or value < 0.0 or value > 1.0:
            raise PlateToSlidersError(f"{name} must be in [0,1]")

    pack_dir_text = str(request.get("pack_dir") or "").strip()
    images: dict[str, Any] = {}
    if pack_dir_text:
        manifest_path = Path(pack_dir_text).expanduser().resolve() / "pack_manifest.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            raw_images = manifest.get("images", {})
            if isinstance(raw_images, Mapping):
                images = dict(raw_images)
    extra = request.get("images")
    if isinstance(extra, Mapping):
        images.update(extra)

    kinds = [_kind(str(k)) for k in images]
    has_figure = "figure" in kinds
    has_clothes = "clothes" in kinds
    has_face = "face" in kinds

    blocked: list[str] = ["morph_coverage", "plate_to_sliders"]
    if has_face:
        blocked.extend(_FACE_BLOCKED)
    if has_clothes and not has_figure:
        blocked.append("no_figure_plates")
    if not has_figure:
        if proposed:
            raise PlateToSlidersError(
                "no figure plates — refuse slider invent from clothes/face"
            )
        sliders: dict[str, float] = {}
    else:
        sliders = {str(k): float(v) for k, v in proposed.items()}

    output_text = str(request.get("output") or "").strip()
    result = {
        "ok": True,
        "contract": CONTRACT,
        "complete": False,
        "sliders": sliders,
        "blocked_on": blocked,
        "has_figure": has_figure,
        "has_clothes": has_clothes,
        "has_face": has_face,
        "honest": [
            "Clothes ≠ WHR. Face plates do not invent jaw/nose sliders.",
            "Only shipped identity ids may be proposed, and only with figure plates.",
            "plate_to_sliders_complete=false until coverage + owner eyes.",
        ],
    }
    if output_text:
        output = Path(output_text).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        result["output"] = str(output)
    return result


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed plate→slider solve")
    parser.add_argument("--request", required=True)
    args = parser.parse_args(argv)
    try:
        request = json.loads(Path(args.request).read_text(encoding="utf-8"))
        print(json.dumps(solve_plate_to_sliders(request)))
        return 0
    except (OSError, json.JSONDecodeError, PlateToSlidersError) as exc:
        print(json.dumps({"ok": False, "error": str(exc), "complete": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(_main())
