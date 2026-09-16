"""The per-model sidecar.

Two properties matter more than the schema itself:

  1. A refresh must never silently discard what the USER set. If someone renamed a model or fixed
     its step count, a later metadata refresh that overwrote it would be a data-loss bug that
     looks like a feature working.
  2. An unknown field written by a NEWER version of SpellVision must survive a round-trip through
     an older one, or a rollback quietly strips data.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from model_intelligence import sidecar


def _weight(tmp_path: Path) -> Path:
    path = tmp_path / "model.safetensors"
    path.write_bytes(b"weights")
    return path


def test_the_sidecar_sits_beside_the_weight(tmp_path: Path):
    assert sidecar.sidecar_path(_weight(tmp_path)).name == "model.spellvision.json"


def test_round_trip(tmp_path: Path):
    weight = _weight(tmp_path)
    payload = sidecar.build_payload(weight=weight, sha256="a" * 64, kind="checkpoint",
                                    family="krea2", civitai_version=None, hf=None,
                                    recommended={"steps": {"value": 10, "provenance": "user",
                                                           "confidence": 1.0, "n": None,
                                                           "total": None}})
    sidecar.write(weight, payload)
    loaded = sidecar.read(weight)
    assert loaded["schema"] == sidecar.SCHEMA
    assert loaded["identity"]["hashes"]["sha256"] == "a" * 64
    assert loaded["recommended"]["steps"]["value"] == 10


def test_reading_a_missing_sidecar_is_none(tmp_path: Path):
    assert sidecar.read(_weight(tmp_path)) is None


def test_reading_a_corrupt_sidecar_is_none_not_an_exception(tmp_path: Path):
    weight = _weight(tmp_path)
    sidecar.sidecar_path(weight).write_text("{ not json", encoding="utf-8")
    assert sidecar.read(weight) is None


def test_a_user_name_survives_a_refresh(tmp_path: Path):
    existing = {
        "schema": sidecar.SCHEMA,
        "display": {"name": {"value": "My Favourite Model", "user_override": True}},
        "recommended": {},
        "identity": {},
    }
    fresh = {
        "schema": sidecar.SCHEMA,
        "display": {"name": {"value": "Site Name", "user_override": False}},
        "recommended": {},
        "identity": {},
    }
    merged = sidecar.merge(existing, fresh)
    assert merged["display"]["name"]["value"] == "My Favourite Model"


def test_a_site_name_replaces_a_non_overridden_one(tmp_path: Path):
    existing = {"schema": sidecar.SCHEMA, "display": {"name": {"value": "old", "user_override": False}},
                "recommended": {}, "identity": {}}
    fresh = {"schema": sidecar.SCHEMA, "display": {"name": {"value": "new", "user_override": False}},
             "recommended": {}, "identity": {}}
    assert sidecar.merge(existing, fresh)["display"]["name"]["value"] == "new"


def test_a_user_setting_survives_a_refresh():
    existing = {"schema": sidecar.SCHEMA, "identity": {}, "display": {},
                "recommended": {"steps": {"value": 24, "provenance": "user", "confidence": 1.0}}}
    fresh = {"schema": sidecar.SCHEMA, "identity": {}, "display": {},
             "recommended": {"steps": {"value": 10, "provenance": "site:image-meta-mode",
                                       "confidence": 1.0}}}
    assert sidecar.merge(existing, fresh)["recommended"]["steps"]["value"] == 24


def test_user_values_extracts_only_user_entries():
    payload = {"recommended": {"steps": {"value": 24, "provenance": "user"},
                               "cfg": {"value": 1.0, "provenance": "site:image-meta-mode"}}}
    assert list(sidecar.user_values(payload)) == ["steps"]


def test_unknown_fields_survive_a_round_trip(tmp_path: Path):
    weight = _weight(tmp_path)
    sidecar.sidecar_path(weight).write_text(
        json.dumps({"schema": sidecar.SCHEMA, "identity": {}, "display": {}, "recommended": {},
                    "something_from_the_future": {"a": 1}}),
        encoding="utf-8",
    )
    existing = sidecar.read(weight)
    merged = sidecar.merge(existing, {"schema": sidecar.SCHEMA, "identity": {}, "display": {},
                                      "recommended": {}})
    sidecar.write(weight, merged)
    assert sidecar.read(weight)["something_from_the_future"] == {"a": 1}


def test_the_write_is_atomic_and_leaves_no_temp_file(tmp_path: Path):
    weight = _weight(tmp_path)
    sidecar.write(weight, sidecar.build_payload(weight=weight, sha256="b" * 64, kind="lora",
                                                family=None, civitai_version=None, hf=None,
                                                recommended={}))
    assert not list(tmp_path.glob("*.tmp"))
