"""The four model-intelligence commands over the real TCP protocol.

Nothing here touches the network: `model_intel_get` and `model_recommended_settings` read a
sidecar off disk, and `model_intel_refresh` is asked for a directory with no weights in it so it
returns an empty, honest result rather than doing 79 minutes of work in CI.
"""
from __future__ import annotations

import json
from pathlib import Path


def _first(messages, msg_type):
    for message in messages:
        if message.get("type") == msg_type:
            return message
    raise AssertionError(f"no {msg_type!r} in {[m.get('type') for m in messages]}")


def test_model_intel_get_on_an_unknown_path_is_honest(worker_client, tmp_path):
    reply = _first(
        worker_client({"command": "model_intel_get", "path": str(tmp_path / "nope.safetensors")}),
        "model_intel",
    )
    assert reply["ok"] is True
    assert reply["sidecar"] is None
    assert reply["recommended"] == {}


def test_model_intel_get_reads_a_sidecar(worker_client, tmp_path):
    weight = tmp_path / "w.safetensors"
    weight.write_bytes(b"w")
    (tmp_path / "w.spellvision.json").write_text(
        json.dumps({
            "schema": "spellvision.model-sidecar/1",
            "identity": {"kind": "checkpoint", "family": "krea2"},
            "display": {"name": {"value": "A Model", "user_override": False}},
            "recommended": {"steps": {"value": 10, "provenance": "site:image-meta-mode",
                                      "confidence": 1.0, "n": 10, "total": 10}},
        }),
        encoding="utf-8",
    )
    reply = _first(worker_client({"command": "model_intel_get", "path": str(weight)}), "model_intel")
    assert reply["sidecar"]["display"]["name"]["value"] == "A Model"
    assert reply["recommended"]["steps"]["value"] == 10


def test_model_recommended_settings_falls_back_to_the_family(worker_client, tmp_path):
    weight = tmp_path / "unknown.safetensors"
    weight.write_bytes(b"w")
    reply = _first(
        worker_client({"command": "model_recommended_settings", "path": str(weight),
                       "family": "krea2"}),
        "model_recommended_settings",
    )
    assert reply["ok"] is True
    assert reply["settings"]["steps"]["provenance"] == "table:family-default"


def test_model_recommended_settings_prefers_the_sidecar(worker_client, tmp_path):
    weight = tmp_path / "w.safetensors"
    weight.write_bytes(b"w")
    (tmp_path / "w.spellvision.json").write_text(
        json.dumps({
            "schema": "spellvision.model-sidecar/1",
            "identity": {"kind": "checkpoint", "family": "krea2"},
            "display": {},
            "recommended": {"steps": {"value": 10, "provenance": "site:image-meta-mode",
                                      "confidence": 1.0, "n": 10, "total": 10}},
        }),
        encoding="utf-8",
    )
    reply = _first(
        worker_client({"command": "model_recommended_settings", "path": str(weight),
                       "family": "krea2"}),
        "model_recommended_settings",
    )
    assert reply["settings"]["steps"]["value"] == 10
    assert reply["settings"]["steps"]["provenance"] == "site:image-meta-mode"


def test_model_intel_set_user_writes_a_name_that_a_refresh_would_keep(worker_client, tmp_path):
    weight = tmp_path / "w.safetensors"
    weight.write_bytes(b"w")
    reply = _first(
        worker_client({"command": "model_intel_set_user", "path": str(weight),
                       "name": "My Favourite"}),
        "model_intel_set_user",
    )
    assert reply["ok"] is True
    assert "name" in reply["changed"]
    stored = json.loads((tmp_path / "w.spellvision.json").read_text(encoding="utf-8"))
    assert stored["display"]["name"]["value"] == "My Favourite"
    assert stored["display"]["name"]["user_override"] is True


def test_model_intel_refresh_on_an_empty_directory_reports_zero_honestly(worker_client, tmp_path):
    reply = _first(
        worker_client({"command": "model_intel_refresh", "roots": [str(tmp_path)]}, timeout=60),
        "model_intel_refresh",
    )
    assert reply["ok"] is True
    assert reply["examined"] == 0
    assert reply["skipped_unreadable"] == []


def test_model_intel_refresh_names_an_unreadable_root(worker_client, tmp_path):
    missing = tmp_path / "not-here"
    reply = _first(
        worker_client({"command": "model_intel_refresh", "roots": [str(missing)]}, timeout=60),
        "model_intel_refresh",
    )
    assert reply["skipped_unreadable"] == [str(missing)]


def test_a_path_outside_the_model_roots_is_refused(worker_client, tmp_path):
    reply = _first(
        worker_client({"command": "model_intel_set_user", "path": "C:/Windows/System32/cmd.exe",
                       "name": "nope"}),
        "model_intel_set_user",
    )
    assert reply["ok"] is False
    assert "not a model file" in reply.get("error", "").lower()
