"""Character Studio Path B create contract.

Facilitates character creation as plates + pack + an explicitly selected
body. Does not sew clothes, cook hair, rebind the rig, or rewrite the body.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from character_export_validate import (
    FEMALE_LOCK_JOINTS,
    FEMALE_LOCK_VERTS,
    HUMAN_RIG_JOINT_NAMES,
    HUMAN_RIG_NAME,
    CharacterExportValidateError,
    validate_export_package,
)
from plate_to_sliders import solve_plate_to_sliders

CONTRACT = "spellbound.character-studio-create.v1"

_BLOCKED_ON = (
    "concept_to_style",
    "stills_to_mesh",
    "hair_create",
    "rig_author",
    "vl_unwired",
    "morph_coverage",
    "plate_to_sliders",
)


class CharacterCreateError(ValueError):
    """The studio cannot honestly claim a Path B create."""


def build_create_contract(request: Mapping[str, Any]) -> dict[str, Any]:
    """Write character_create.json for a Path B studio create."""

    if request.get("identity_path") not in (None, "", "B"):
        raise CharacterCreateError("identity_path must be B; Path A is adjunct only")
    if request.get("pixal_as_identity") or request.get("trellis_as_identity"):
        raise CharacterCreateError("Pixal/TRELLIS cannot be character identity")

    project = str(request.get("project") or request.get("pack_id") or "").strip()
    if not project:
        raise CharacterCreateError("project is required")

    output_text = str(request.get("output") or request.get("output_dir") or "").strip()
    if not output_text:
        raise CharacterCreateError("output is required")
    output = Path(output_text).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    pack_dir_text = str(request.get("pack_dir") or "").strip()
    pack_dir = Path(pack_dir_text).expanduser().resolve() if pack_dir_text else None
    pack_ready = bool(pack_dir and (pack_dir / "pack_manifest.json").is_file())

    body_text = str(
        request.get("body") or request.get("body_path") or request.get("glb") or request.get("glb_path") or ""
    ).strip()
    if not body_text:
        raise CharacterCreateError("body is required; choose a body mesh in Character Studio")
    body_source = Path(body_text).expanduser().resolve()
    if not body_source.is_file():
        raise CharacterCreateError(f"body mesh does not exist: {body_source}")

    contract = {
        "contract": CONTRACT,
        "project": project,
        "identity_path": "B",
        "studio_create_facilitated": True,
        "create_complete": False,
        "body": {
            "source": str(body_source),
            "vertex_count": FEMALE_LOCK_VERTS,
            "joints": FEMALE_LOCK_JOINTS,
            "rig": HUMAN_RIG_NAME,
            "joint_names": list(HUMAN_RIG_JOINT_NAMES),
            "sliders": "owner-reviewed MorphLayers",
        },
        "lanes": {
            "plates": "concept + clothes turnaround",
            "morph": {
                "coverage_complete": False,
                "contract": "spellbound.whole-body-morph.v1",
                "plate_to_sliders_complete": False,
                "note": "starter 25 identity RONs; face/proportion/breast axes/glute axes still missing",
            },
            "garment": {"cook_complete": False, "live": "T4 tunic bind"},
            "hair": {"cook_complete": False, "slot": "hair.wear.scalp", "occupancy": "empty"},
            "rig": {"cook_complete": False, "author_complete": False, "lock_joints": FEMALE_LOCK_JOINTS},
        },
        "pack_dir": str(pack_dir) if pack_dir else None,
        "pack_ready": pack_ready,
        "concept_to_style_complete": False,
        "pixal_identity": False,
        "validated": False,
        "blocked_on": list(_BLOCKED_ON),
        "honest": [
            "Studio can author plates + pack against the selected body mesh.",
            "NOT stills-to-mesh / NOT hair groom / NOT I5 rebind / NOT body rewrite.",
            "Gen3D / TRELLIS / UltraShape are adjunct props only.",
        ],
    }
    solve = solve_plate_to_sliders(
        {
            "pack_dir": str(pack_dir) if pack_dir else "",
            "output": str(output.with_name("sliders.json")),
        }
    )
    contract["lanes"]["morph"]["sliders"] = solve.get("sliders", {})
    contract["lanes"]["morph"]["solver_blocked_on"] = solve.get("blocked_on", [])
    blocked = list(dict.fromkeys(list(_BLOCKED_ON) + list(solve.get("blocked_on") or [])))
    contract["blocked_on"] = blocked
    validation_request: dict[str, Any] = {
        "identity_path": contract["identity_path"],
        "pixal_identity": contract["pixal_identity"],
        "pixal_as_identity": request.get("pixal_as_identity"),
        "trellis_as_identity": request.get("trellis_as_identity"),
        "body": contract["body"],
    }
    glb = request.get("glb") or request.get("glb_path")
    if glb:
        validation_request["glb"] = glb
    try:
        validation = validate_export_package(validation_request)
    except CharacterExportValidateError as exc:
        raise CharacterCreateError(str(exc)) from exc
    contract["validated"] = bool(validation.get("validated"))
    output.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "contract": str(output),
        "studio_create_facilitated": True,
        "create_complete": False,
        "pack_ready": pack_ready,
        "validated": bool(contract["validated"]),
        "blocked_on": blocked,
        "sliders": solve.get("sliders", {}),
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write a Character Studio Path B create contract")
    parser.add_argument("--request", required=True, help="JSON request file")
    args = parser.parse_args(argv)
    try:
        request = json.loads(Path(args.request).read_text(encoding="utf-8"))
        print(json.dumps(build_create_contract(request)))
        return 0
    except (OSError, json.JSONDecodeError, CharacterCreateError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(_main())
