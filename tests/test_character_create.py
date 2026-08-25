from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from character_create import CharacterCreateError, build_create_contract
from character_pack import build_character_pack


def _pack(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    (source / "face.png").write_bytes(b"face-front")
    (source / "front.jpg").write_bytes(b"clothes-front")
    (source / "side.jpg").write_bytes(b"clothes-side")
    pack = tmp_path / "witch" / "jarvis_pack"
    build_character_pack(
        {
            "pack_id": "witch",
            "output_dir": str(pack),
            "images": {
                "face_front": str(source / "face.png"),
                "clothes_front": str(source / "front.jpg"),
                "clothes_side": str(source / "side.jpg"),
            },
            "pieces": ["hat", "cloak"],
            "palette": ["bone", "charcoal"],
        }
    )
    return pack


def test_create_contract_path_b_is_facilitated_not_cook_complete(tmp_path: Path) -> None:
    pack = _pack(tmp_path)
    out = tmp_path / "witch" / "character_create.json"
    selected_body = tmp_path / "selected_body.glb"
    selected_body.write_bytes(b"selected-body")
    result = build_create_contract(
        {
            "project": "witch",
            "output": str(out),
            "pack_dir": str(pack),
            "identity_path": "B",
            "body": str(selected_body),
        }
    )
    assert result["ok"] is True
    assert result["studio_create_facilitated"] is True
    assert result["create_complete"] is False
    assert result["pack_ready"] is True
    assert "stills_to_mesh" in result["blocked_on"]
    assert "hair_create" in result["blocked_on"]
    body = json.loads(out.read_text(encoding="utf-8"))
    assert body["contract"] == "spellbound.character-studio-create.v1"
    assert body["body"]["vertex_count"] == 14517
    assert body["body"]["joints"] == 53
    assert Path(body["body"]["source"]) == selected_body.resolve()
    assert body["lanes"]["hair"]["occupancy"] == "empty"
    assert body["lanes"]["morph"]["coverage_complete"] is False
    assert body["lanes"]["morph"]["plate_to_sliders_complete"] is False
    assert body["lanes"]["morph"]["sliders"] == {}
    assert "morph_coverage" in result["blocked_on"]
    assert "plate_to_sliders" in result["blocked_on"]
    assert "no_figure_plates" in result["blocked_on"]
    assert result["sliders"] == {}
    assert (tmp_path / "witch" / "sliders.json").is_file()
    assert body["pixal_identity"] is False
    assert body["validated"] is True
    assert result["validated"] is True
    assert body["concept_to_style_complete"] is False


def test_create_contract_refuses_pixal_identity(tmp_path: Path) -> None:
    out = tmp_path / "character_create.json"
    with pytest.raises(CharacterCreateError, match="Pixal"):
        build_create_contract(
            {
                "project": "witch",
                "output": str(out),
                "pixal_as_identity": True,
            }
        )
    assert not out.exists()


def test_create_contract_requires_selected_body(tmp_path: Path) -> None:
    with pytest.raises(CharacterCreateError, match="body is required"):
        build_create_contract({"project": "witch", "output": str(tmp_path / "character_create.json")})
