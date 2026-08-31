from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from character_pack import CharacterPackError, build_character_pack


def _image(path: Path, content: bytes) -> str:
    path.write_bytes(content)
    return str(path)


def _request(tmp_path: Path) -> dict:
    source = tmp_path / "source"
    source.mkdir()
    return {
        "pack_id": "witch",
        "output_dir": str(tmp_path / "witch" / "jarvis_pack"),
        "images": {
            "face_front": _image(source / "face.png", b"face-front"),
            "clothes_front": _image(source / "front.jpg", b"clothes-front"),
            "clothes_side": _image(source / "side.jpg", b"clothes-side"),
        },
        "pieces": ["hat", "pauldron", "boots", "cloak"],
        "palette": ["bone", "charcoal", "tarnished-brass"],
        "pose": "T-pose, white ground",
    }


def test_build_character_pack_writes_canonical_files_notes_and_manifest(tmp_path: Path) -> None:
    request = _request(tmp_path)

    result = build_character_pack(request)

    pack = Path(request["output_dir"])
    assert result["status"] == "ready"
    assert result["optimal"] is False
    assert (pack / "face_01_front.png").read_bytes() == b"face-front"
    assert (pack / "clothes_01_front.jpg").read_bytes() == b"clothes-front"
    assert (pack / "clothes_01_side.jpg").read_bytes() == b"clothes-side"
    notes = (pack / "notes.txt").read_text(encoding="utf-8")
    assert "pieces: hat, pauldron, boots, cloak" in notes
    assert "palette: bone, charcoal, tarnished-brass" in notes
    assert "do-not: nudes, MH/UE paste, fused clothing" in notes

    manifest = json.loads((pack / "pack_manifest.json").read_text(encoding="utf-8"))
    assert manifest["contract"] == "spellbound.jarvis-character-pack.v1"
    assert manifest["body_source"] == "frozen female.glb + owner-reviewed sliders"
    assert manifest["concept_to_style_complete"] is False
    assert manifest["images"]["clothes_front"]["sha256"] == hashlib.sha256(b"clothes-front").hexdigest()


def test_build_character_pack_rejects_identical_required_views(tmp_path: Path) -> None:
    request = _request(tmp_path)
    duplicate = tmp_path / "source" / "back-copy.jpg"
    duplicate.write_bytes(b"clothes-front")
    request["images"]["clothes_back"] = str(duplicate)
    request["images"].pop("clothes_side")

    with pytest.raises(CharacterPackError, match="different bytes"):
        build_character_pack(request)

    assert not Path(request["output_dir"]).exists()


def test_build_character_pack_requires_face_clothes_turn_and_piece_metadata(tmp_path: Path) -> None:
    request = _request(tmp_path)
    request["images"].pop("face_front")
    request["pieces"] = []

    with pytest.raises(CharacterPackError) as error:
        build_character_pack(request)

    message = str(error.value)
    assert "face_front" in message
    assert "piece list" in message


def test_build_character_pack_reports_optimal_when_front_side_back_and_optional_views_exist(tmp_path: Path) -> None:
    request = _request(tmp_path)
    source = tmp_path / "source"
    request["images"].update(
        {
            "face_3q": _image(source / "face-3q.webp", b"face-three-quarter"),
            "clothes_back": _image(source / "back.png", b"clothes-back"),
            "clothes_3q": _image(source / "clothes-3q.png", b"clothes-three-quarter"),
        }
    )

    result = build_character_pack(request)

    assert result["status"] == "ready"
    assert result["optimal"] is True
    assert result["missing_optional"] == []
