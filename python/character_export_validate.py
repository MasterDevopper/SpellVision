"""Fail-closed Character Studio export validator.

Export is a package, never a rewritten SpellBound female.glb.
Identity is Path B: frozen 14517 + Human.rig 53. TRELLIS/Pixal/UltraShape
are not identity. UltraShape is Hunyuan Community, not Apache.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any, Mapping

FEMALE_LOCK_VERTS = 14517
FEMALE_LOCK_JOINTS = 53
HUMAN_RIG_NAME = "Human.rig"
# Skin-joint names from SpellBound assets/models/human/female.glb (read-only).
HUMAN_RIG_JOINT_NAMES: tuple[str, ...] = (
    "Root",
    "pelvis",
    "spine_01",
    "spine_02",
    "spine_03",
    "clavicle_l",
    "upperarm_l",
    "lowerarm_l",
    "hand_l",
    "index_01_l",
    "index_02_l",
    "index_03_l",
    "middle_01_l",
    "middle_02_l",
    "middle_03_l",
    "pinky_01_l",
    "pinky_02_l",
    "pinky_03_l",
    "ring_01_l",
    "ring_02_l",
    "ring_03_l",
    "thumb_01_l",
    "thumb_02_l",
    "thumb_03_l",
    "clavicle_r",
    "upperarm_r",
    "lowerarm_r",
    "hand_r",
    "index_01_r",
    "index_02_r",
    "index_03_r",
    "middle_01_r",
    "middle_02_r",
    "middle_03_r",
    "pinky_01_r",
    "pinky_02_r",
    "pinky_03_r",
    "ring_01_r",
    "ring_02_r",
    "ring_03_r",
    "thumb_01_r",
    "thumb_02_r",
    "thumb_03_r",
    "neck_01",
    "head",
    "thigh_l",
    "calf_l",
    "foot_l",
    "ball_l",
    "thigh_r",
    "calf_r",
    "foot_r",
    "ball_r",
)

assert len(HUMAN_RIG_JOINT_NAMES) == FEMALE_LOCK_JOINTS


class CharacterExportValidateError(ValueError):
    """Export package is not the frozen 14517 / Human.rig 53 lock."""


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def _glb_position_count(path: Path) -> int:
    data = path.read_bytes()
    if len(data) < 20 or data[:4] != b"glTF":
        raise CharacterExportValidateError(f"glb is not glTF binary: {path}")
    _magic, _version, length = struct.unpack_from("<4sII", data, 0)
    offset = 12
    json_chunk: dict[str, Any] | None = None
    while offset + 8 <= min(length, len(data)):
        chunk_len, chunk_type = struct.unpack_from("<I4s", data, offset)
        payload = data[offset + 8 : offset + 8 + chunk_len]
        if chunk_type == b"JSON":
            json_chunk = json.loads(payload.decode("utf-8"))
            break
        offset += 8 + chunk_len
    if not isinstance(json_chunk, dict):
        raise CharacterExportValidateError(f"glb has no JSON chunk: {path}")
    accessors = json_chunk.get("accessors") or []
    meshes = json_chunk.get("meshes") or []
    if not meshes:
        raise CharacterExportValidateError(f"glb has no meshes: {path}")
    primitives = (meshes[0] or {}).get("primitives") or []
    if not primitives:
        raise CharacterExportValidateError(f"glb mesh has no primitives: {path}")
    position = (primitives[0] or {}).get("attributes", {}).get("POSITION")
    if position is None:
        raise CharacterExportValidateError(f"glb primitive has no POSITION: {path}")
    try:
        count = accessors[int(position)]["count"]
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise CharacterExportValidateError(f"glb POSITION accessor unreadable: {path}") from exc
    parsed = _as_int(count)
    if parsed is None:
        raise CharacterExportValidateError(f"glb POSITION count missing: {path}")
    return parsed


def validate_export_package(request: Mapping[str, Any]) -> dict[str, Any]:
    """Fail closed unless the package is Path B 14517 / Human.rig 53."""

    if request.get("identity_path") != "B":
        raise CharacterExportValidateError(
            "identity_path must be B (frozen female.glb); Path A is adjunct only"
        )
    if (
        request.get("pixal_identity")
        or request.get("pixal_as_identity")
        or request.get("trellis_as_identity")
        or request.get("trellis_identity")
    ):
        raise CharacterExportValidateError("Pixal/TRELLIS cannot be character identity")

    body = request.get("body")
    if not isinstance(body, Mapping):
        raise CharacterExportValidateError("body is required")

    verts = _as_int(body.get("vertex_count"))
    if verts != FEMALE_LOCK_VERTS:
        raise CharacterExportValidateError(
            f"body.vertex_count {verts} != lock {FEMALE_LOCK_VERTS}"
        )

    joints = _as_int(body.get("joints"))
    if joints != FEMALE_LOCK_JOINTS:
        raise CharacterExportValidateError(
            f"body.joints {joints} != Human.rig lock {FEMALE_LOCK_JOINTS}"
        )

    rig = body.get("rig")
    if rig not in (None, "", HUMAN_RIG_NAME):
        raise CharacterExportValidateError(f"body.rig {rig!r} != {HUMAN_RIG_NAME}")

    names = body.get("joint_names")
    if names is None:
        names = request.get("joint_names")
    if names is not None:
        got = [str(name) for name in names]
        if got != list(HUMAN_RIG_JOINT_NAMES):
            raise CharacterExportValidateError(
                f"joint_names {len(got)} do not match Human.rig {FEMALE_LOCK_JOINTS}"
            )

    result: dict[str, Any] = {
        "ok": True,
        "validated": True,
        "vertex_count": FEMALE_LOCK_VERTS,
        "joints": FEMALE_LOCK_JOINTS,
        "rig": HUMAN_RIG_NAME,
        "joint_names": list(HUMAN_RIG_JOINT_NAMES),
        "identity_path": "B",
        "pixal_identity": False,
    }

    glb_text = str(request.get("glb") or request.get("glb_path") or "").strip()
    if glb_text:
        glb_path = Path(glb_text).expanduser()
        if not glb_path.is_file():
            raise CharacterExportValidateError(f"glb is not a readable file: {glb_path}")
        count = _glb_position_count(glb_path)
        if count != FEMALE_LOCK_VERTS:
            raise CharacterExportValidateError(
                f"glb POSITION count {count} != lock {FEMALE_LOCK_VERTS}"
            )
        result["glb_position_count"] = count

    return result
