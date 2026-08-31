"""Author the small, explicit character-reference pack consumed by Jarvis.

This module prepares evidence only.  It does not generate a body, sew garments, run
VL, or claim that SpellBound's concept-to-style cook is complete.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any, Mapping


CONTRACT = "spellbound.jarvis-character-pack.v1"
_IMAGE_NAMES = {
    "face_front": "face_01_front",
    "face_3q": "face_01_3q",
    "clothes_front": "clothes_01_front",
    "clothes_side": "clothes_01_side",
    "clothes_back": "clothes_01_back",
    "clothes_3q": "clothes_01_3q",
}
_ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
_REQUIRED_ALWAYS = ("face_front", "clothes_front")
_OPTIMAL_KEYS = tuple(_IMAGE_NAMES)


class CharacterPackError(ValueError):
    """The selected files cannot honestly satisfy the pack contract."""


def _clean_values(value: Any) -> list[str]:
    if isinstance(value, str):
        candidates = re.split(r"[,\n]", value)
    elif isinstance(value, list):
        candidates = [str(item) for item in value]
    else:
        candidates = []
    return [item.strip() for item in candidates if item.strip()]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_request(request: Mapping[str, Any]) -> tuple[str, Path, dict[str, Path], list[str], list[str], str]:
    pack_id = str(request.get("pack_id", "")).strip()
    if not pack_id:
        raise CharacterPackError("pack_id is required")

    output_text = str(request.get("output_dir", "")).strip()
    if not output_text:
        raise CharacterPackError("output_dir is required")
    output_dir = Path(output_text).expanduser().resolve()

    raw_images = request.get("images", {})
    if not isinstance(raw_images, Mapping):
        raise CharacterPackError("images must be an object keyed by pack slot")

    images: dict[str, Path] = {}
    failures: list[str] = []
    for key, raw_path in raw_images.items():
        if key not in _IMAGE_NAMES or not str(raw_path).strip():
            continue
        path = Path(str(raw_path)).expanduser().resolve()
        if not path.is_file():
            failures.append(f"{key} is not a readable file")
            continue
        if path.suffix.lower() not in _ALLOWED_SUFFIXES:
            failures.append(f"{key} must be PNG, JPEG, WebP, or BMP")
            continue
        images[key] = path

    for key in _REQUIRED_ALWAYS:
        if key not in images:
            failures.append(f"{key} is required")
    if "clothes_side" not in images and "clothes_back" not in images:
        failures.append("clothes_side or clothes_back is required")

    pieces = _clean_values(request.get("pieces"))
    palette = _clean_values(request.get("palette"))
    if not pieces:
        failures.append("a piece list is required")
    if not palette:
        failures.append("a named palette is required")

    if failures:
        raise CharacterPackError("; ".join(failures))

    seen_hashes: dict[str, str] = {}
    for key, path in images.items():
        digest = _sha256(path)
        previous = seen_hashes.get(digest)
        if previous is not None:
            raise CharacterPackError(
                f"{previous} and {key} contain identical bytes; required angles must be different bytes"
            )
        seen_hashes[digest] = key

    pose = str(request.get("pose", "T- or A-pose, white ground")).strip()
    return pack_id, output_dir, images, pieces, palette, pose


def build_character_pack(request: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and atomically write one Jarvis character reference pack."""

    pack_id, output_dir, images, pieces, palette, pose = _validate_request(request)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = output_dir.with_name(f".{output_dir.name}.building-{uuid.uuid4().hex}")
    backup = output_dir.with_name(f".{output_dir.name}.backup-{uuid.uuid4().hex}")
    staging.mkdir()

    image_manifest: dict[str, dict[str, str]] = {}
    try:
        for key, source in images.items():
            destination_name = _IMAGE_NAMES[key] + source.suffix.lower()
            destination = staging / destination_name
            shutil.copy2(source, destination)
            image_manifest[key] = {
                "file": destination_name,
                "sha256": _sha256(destination),
                "source": str(source),
            }

        notes = "\n".join(
            [
                f"pack: {pack_id}",
                f"pieces: {', '.join(pieces)}",
                f"palette: {', '.join(palette)}",
                f"pose: {pose}",
                "body: frozen female.glb + owner-reviewed sliders",
                "do-not: nudes, MH/UE paste, fused clothing",
                "",
            ]
        )
        (staging / "notes.txt").write_text(notes, encoding="utf-8")

        missing_optional = [key for key in _OPTIMAL_KEYS if key not in images]
        optimal = not missing_optional
        manifest = {
            "contract": CONTRACT,
            "pack_id": pack_id,
            "status": "ready",
            "optimal": optimal,
            "missing_optional": missing_optional,
            "body_source": "frozen female.glb + owner-reviewed sliders",
            "clothing_mesh_policy": "separate wearable meshes; never fuse into the body",
            "concept_to_style_complete": False,
            "cook_status": "reference pack authored; VL, stills-to-mesh, Wrought transfer, bind/cook, and Stage proof remain downstream",
            "images": image_manifest,
            "pieces": pieces,
            "palette": palette,
            "pose": pose,
        }
        (staging / "pack_manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )

        replaced_existing = output_dir.exists()
        if replaced_existing:
            output_dir.replace(backup)
        try:
            staging.replace(output_dir)
        except Exception:
            if backup.exists() and not output_dir.exists():
                backup.replace(output_dir)
            raise
        if backup.exists():
            shutil.rmtree(backup)

        return {
            "ok": True,
            "status": "ready",
            "optimal": optimal,
            "missing_optional": missing_optional,
            "output_dir": str(output_dir),
            "manifest": str(output_dir / "pack_manifest.json"),
            "replaced_existing": replaced_existing,
        }
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a SpellBound Jarvis character pack")
    parser.add_argument("--request", required=True, help="JSON request file")
    args = parser.parse_args(argv)

    try:
        request = json.loads(Path(args.request).read_text(encoding="utf-8"))
        result = build_character_pack(request)
    except (OSError, json.JSONDecodeError, CharacterPackError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 2

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
