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
    """With no sidecar at all, the answer is the runtime operating-point table (tuned by this
    project's own render comparisons), not the published family floor underneath it -- that
    ordering is resolve.py's whole point (Task 3 / W2). Before the delegation this asserted
    "table:family-default", which was the OLD, wrong precedence: the exact defect the resolver
    exists to fix (krea2's own house checkpoint publishes 10/1 while the family table said 52/3.5,
    and this command was answering 52/3.5 from the WEAKER of the two tables)."""
    weight = tmp_path / "unknown.safetensors"
    weight.write_bytes(b"w")
    reply = _first(
        worker_client({"command": "model_recommended_settings", "path": str(weight),
                       "family": "krea2"}),
        "model_recommended_settings",
    )
    assert reply["ok"] is True
    assert reply["settings"]["steps"]["value"] == 52
    assert reply["settings"]["steps"]["provenance"] == "table:family-operating-point"
    assert reply["operating_point"] == "raw"


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
    """Refused for its LOCATION, which is what the name says.

    The old version sent `C:/Windows/System32/cmd.exe` and was refused for its EXTENSION. Change
    that to `evil.safetensors` and it returned ok:True and wrote a sidecar there -- while the
    protocol document and this test's own name both asserted containment. The path here is a
    genuine model file, in a genuine directory, that is simply not under the roots the request
    names.
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    weight = outside / "evil.safetensors"
    weight.write_bytes(b"w")
    root = tmp_path / "models"
    root.mkdir()

    reply = _first(
        worker_client({"command": "model_intel_set_user", "path": str(weight),
                       "roots": [str(root)], "name": "nope"}),
        "model_intel_set_user",
    )
    assert reply["ok"] is False
    assert "outside the model roots" in reply.get("error", "").lower()
    assert not (outside / "evil.spellvision.json").exists()


def test_a_path_inside_the_named_roots_is_accepted(worker_client, tmp_path):
    """The containment check must not refuse the ordinary case."""
    root = tmp_path / "models"
    (root / "checkpoints").mkdir(parents=True)
    weight = root / "checkpoints" / "w.safetensors"
    weight.write_bytes(b"w")
    reply = _first(
        worker_client({"command": "model_intel_set_user", "path": str(weight),
                       "roots": [str(root)], "name": "Mine"}),
        "model_intel_set_user",
    )
    assert reply["ok"] is True
    assert (root / "checkpoints" / "w.spellvision.json").exists()


def test_a_picture_outside_the_model_roots_is_refused(worker_client, tmp_path):
    """`picture` was an arbitrary-file-read primitive with an attacker-chosen destination: any
    readable file copied beside any path as `<stem>.preview.jpg`. Bounded to LOCAL_TRUSTED by
    worker_auth, never bounded by this module."""
    root = tmp_path / "models"
    root.mkdir()
    weight = root / "w.safetensors"
    weight.write_bytes(b"w")
    secret = tmp_path / "credentials.json"
    secret.write_bytes(b"not-a-picture")

    reply = _first(
        worker_client({"command": "model_intel_set_user", "path": str(weight),
                       "roots": [str(root)], "picture": str(secret)}),
        "model_intel_set_user",
    )
    assert reply["ok"] is False
    assert "picture is outside the model roots" in reply.get("error", "").lower()
    assert not (root / "w.preview.jpg").exists()


def test_a_request_that_names_no_roots_is_documented_as_unchecked(worker_client, tmp_path):
    """The honest half of I1. With no roots in the request there is no location check, and the
    protocol document now says so in those words rather than claiming the opposite."""
    weight = tmp_path / "anywhere.safetensors"
    weight.write_bytes(b"w")
    reply = _first(
        worker_client({"command": "model_intel_set_user", "path": str(weight), "name": "x"}),
        "model_intel_set_user",
    )
    assert reply["ok"] is True

    from pathlib import Path as _Path

    doc = (_Path(__file__).resolve().parents[1] / "docs" / "SPELLVISION_WORKER_PROTOCOL.md")
    text = doc.read_text(encoding="utf-8")
    assert "location check at all" in text, (
        "the protocol document must state what is and is not checked"
    )


def test_a_host_outside_the_allowlist_is_refused_not_a_crash(worker_client, tmp_path):
    """CivitaiClient(host=...) raises ValueError for a host outside the allowlist. That can reach
    handle_model_intel_refresh_command from a settings field, not just from already-validated code,
    so a bad host must come back as ok:False rather than taking down the handler."""
    reply = _first(
        worker_client({
            "command": "model_intel_refresh",
            "roots": [str(tmp_path)],
            "civitai_host": "evil.example.com",
        }, timeout=60),
        "model_intel_refresh",
    )
    assert reply["ok"] is False
    assert "evil.example.com" in reply.get("error", "")
