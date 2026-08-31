from __future__ import annotations

import json
import struct
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from character_create import CharacterCreateError, build_create_contract
from character_export_validate import (
    FEMALE_LOCK_JOINTS,
    FEMALE_LOCK_VERTS,
    HUMAN_RIG_JOINT_NAMES,
    CharacterExportValidateError,
    validate_export_package,
)
from character_pack import build_character_pack


def _ok_request(**overrides: object) -> dict:
    request: dict = {
        "identity_path": "B",
        "pixal_identity": False,
        "body": {
            "vertex_count": FEMALE_LOCK_VERTS,
            "joints": FEMALE_LOCK_JOINTS,
            "rig": "Human.rig",
            "joint_names": list(HUMAN_RIG_JOINT_NAMES),
        },
    }
    request.update(overrides)
    return request


def _minimal_glb(path: Path, position_count: int) -> Path:
    gltf = {
        "asset": {"version": "2.0"},
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "accessors": [{"count": position_count, "componentType": 5126, "type": "VEC3"}],
        "buffers": [{"byteLength": 0}],
    }
    payload = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    pad = (4 - (len(payload) % 4)) % 4
    payload += b" " * pad
    header = struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(payload))
    chunk = struct.pack("<I4s", len(payload), b"JSON") + payload
    path.write_bytes(header + chunk)
    return path


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
            "pieces": ["hat"],
            "palette": ["bone"],
        }
    )
    return pack


def test_validate_export_package_accepts_14517_53_path_b() -> None:
    result = validate_export_package(_ok_request())
    assert result["ok"] is True
    assert result["validated"] is True
    assert result["vertex_count"] == 14517
    assert result["joints"] == 53
    assert result["identity_path"] == "B"
    assert result["pixal_identity"] is False
    assert result["rig"] == "Human.rig"
    assert result["joint_names"] == list(HUMAN_RIG_JOINT_NAMES)
    assert len(result["joint_names"]) == 53


def test_validate_export_package_refuses_42342_verts() -> None:
    with pytest.raises(CharacterExportValidateError, match="42342"):
        validate_export_package(
            _ok_request(body={"vertex_count": 42342, "joints": 53, "rig": "Human.rig"})
        )


def test_validate_export_package_refuses_54_bones() -> None:
    with pytest.raises(CharacterExportValidateError, match="54"):
        validate_export_package(
            _ok_request(body={"vertex_count": 14517, "joints": 54, "rig": "Human.rig"})
        )


def test_validate_export_package_refuses_path_a() -> None:
    with pytest.raises(CharacterExportValidateError, match="Path A|identity_path"):
        validate_export_package(_ok_request(identity_path="A"))


def test_validate_export_package_refuses_pixal_as_identity() -> None:
    with pytest.raises(CharacterExportValidateError, match="Pixal|identity"):
        validate_export_package(_ok_request(pixal_as_identity=True))


def test_validate_export_package_refuses_wrong_glb_position_count(tmp_path: Path) -> None:
    glb = _minimal_glb(tmp_path / "prop.glb", 42342)
    with pytest.raises(CharacterExportValidateError, match="42342"):
        validate_export_package(_ok_request(glb=str(glb)))


def test_validate_export_package_accepts_14517_glb_without_rewriting(tmp_path: Path) -> None:
    glb = _minimal_glb(tmp_path / "lock.glb", 14517)
    before = glb.read_bytes()
    result = validate_export_package(_ok_request(glb=str(glb)))
    assert result["validated"] is True
    assert result["glb_position_count"] == 14517
    assert glb.read_bytes() == before


def test_create_contract_stamps_validated_true_only_on_pass(tmp_path: Path) -> None:
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
    assert result["validated"] is True
    body = json.loads(out.read_text(encoding="utf-8"))
    assert body["validated"] is True
    assert body["identity_path"] == "B"
    assert body["pixal_identity"] is False
    assert body["body"]["vertex_count"] == 14517
    assert body["body"]["joints"] == 53
    assert body["body"]["rig"] == "Human.rig"
    assert body["body"]["joint_names"] == list(HUMAN_RIG_JOINT_NAMES)
    assert not any(p.name == "female.glb" for p in tmp_path.rglob("female.glb"))


def test_create_contract_does_not_stamp_validated_when_path_a(tmp_path: Path) -> None:
    out = tmp_path / "character_create.json"
    with pytest.raises(CharacterCreateError, match="Path A|identity_path"):
        build_create_contract(
            {
                "project": "witch",
                "output": str(out),
                "identity_path": "A",
            }
        )
    assert not out.exists()
