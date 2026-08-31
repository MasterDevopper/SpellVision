from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from credential_store import clear_credential, credential_status, get_credential, set_credential
from model_sources import _civitai_api_get_json, materialize_asset, parse_asset_reference


def test_hf_uri_parses_repo_and_filename() -> None:
    ref = parse_asset_reference("hf://Comfy-Org/Wan_2.2_ComfyUI_Repackaged/split_files/vae/wan_2.1_vae.safetensors")
    assert ref.kind == "hf_repo"
    assert ref.repo_id == "Comfy-Org/Wan_2.2_ComfyUI_Repackaged"
    assert ref.filename.endswith("wan_2.1_vae.safetensors")
    solo = parse_asset_reference("hf://gpt2/config.json")
    assert solo.repo_id == "gpt2"
    assert solo.filename == "config.json"
    red = parse_asset_reference("https://civitai.red/models/2862752/bowsette-fan-art")
    assert red.kind == "civitai_model_page"
    assert red.model_id == "2862752"
    assert red.source_name == "civitai"


def test_hf_repo_without_filename_stays_unfetched() -> None:
    asset = materialize_asset("Comfy-Org/Wan_2.2_ComfyUI_Repackaged")
    assert asset.resolved_kind == "hf_repo"
    assert asset.metadata.get("needs_filename") is True
    assert asset.metadata.get("fetched") is False



def test_store_set_get_clear_never_echoes_secret(tmp_path: Path, monkeypatch) -> None:
    store = tmp_path / "credentials.json"
    monkeypatch.delenv("SPELLVISION_HF_TOKEN", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGING_FACE_HUB_TOKEN", raising=False)
    set_credential("hf_token", "hf_secret_value", path=store)
    assert get_credential("hf_token", path=store) == "hf_secret_value"
    status = credential_status(path=store)
    assert status["hf_token_present"] is True
    assert status["hf_token_stored"] is True
    dumped = json_text(status)
    assert "hf_secret_value" not in dumped
    clear_credential("hf_token", path=store)
    assert get_credential("hf_token", path=store) == ""
    assert credential_status(path=store)["hf_token_present"] is False


def json_text(payload: dict) -> str:
    import json
    return json.dumps(payload)


def test_explicit_and_env_beat_store(tmp_path: Path, monkeypatch) -> None:
    store = tmp_path / "credentials.json"
    set_credential("hf_token", "stored", path=store)
    monkeypatch.setenv("HF_TOKEN", "from-env")
    assert get_credential("hf_token", path=store) == "from-env"
    assert get_credential("hf_token", explicit="from-arg", path=store) == "from-arg"


def test_store_file_is_encrypted_not_plaintext(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SPELLVISION_HF_TOKEN", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGING_FACE_HUB_TOKEN", raising=False)
    store = tmp_path / "credentials.json"
    secret = "hf_must_not_appear_on_disk"
    set_credential("hf_token", secret, path=store)
    raw = store.read_text(encoding="utf-8")
    assert secret not in raw
    payload = __import__("json").loads(raw)
    assert payload["version"] == 2
    assert payload["backend"] == "dpapi"
    assert get_credential("hf_token", path=store) == secret
    assert credential_status(path=store)["encrypted"] is True


def test_migrates_plaintext_v1(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SPELLVISION_HF_TOKEN", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGING_FACE_HUB_TOKEN", raising=False)
    store = tmp_path / "credentials.json"
    store.write_text('{"hf_token": "legacy_plain_token"}', encoding="utf-8")
    assert get_credential("hf_token", path=store) == "legacy_plain_token"
    raw = store.read_text(encoding="utf-8")
    assert "legacy_plain_token" not in raw
    assert get_credential("hf_token", path=store) == "legacy_plain_token"


def test_civitai_requests_send_user_agent(monkeypatch) -> None:
    seen: list[dict[str, str]] = []

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self) -> bytes:
            return b'{"id": 1}'

    def fake_urlopen(req, timeout=None):
        seen.append({k: v for k, v in req.header_items()})
        return FakeResp()

    monkeypatch.setattr("model_sources.urllib.request.urlopen", fake_urlopen)
    payload = _civitai_api_get_json(
        "https://civitai.com/api/v1/me",
        civitai_api_key="throwaway",
        timeout_sec=5,
    )
    assert payload["id"] == 1
    headers = {k.lower(): v for k, v in seen[0].items()}
    assert "spellvision" in headers.get("user-agent", "").lower()
    assert headers.get("authorization") == "Bearer throwaway"


# --- ACL hardening: a control that fails silently is not a control ---------------------------


def test_the_store_is_hardened_before_the_rename_not_after(monkeypatch, tmp_path):
    """The temp file is written at default (inherited) permissions.

    Restricting only the renamed store leaves the real file unrestricted for the window in
    between. The contents are DPAPI blobs bound to this user, so this is defence in depth rather
    than a plaintext leak -- but the ordering costs nothing and the window should not exist.
    """
    import credential_store

    order: list[str] = []
    real_restrict = credential_store._restrict_acl

    def tracking_restrict(path):
        order.append(f"restrict:{path.suffix}")
        return real_restrict(path)

    monkeypatch.setattr(credential_store, "_restrict_acl", tracking_restrict)

    store = tmp_path / "creds.json"
    credential_store._write_store({"civitai_api_key": "abc123"}, store)

    assert order, "the store was written without any ACL hardening at all"
    assert order[0] == "restrict:.tmp", (
        f"the temp file must be hardened before the rename; call order was {order}"
    )


def test_an_acl_failure_is_reported_rather_than_swallowed(monkeypatch, tmp_path, caplog):
    """Every failure here used to be `except Exception: pass`, including a non-zero icacls exit."""
    import credential_store

    def exploding_chmod(*args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(credential_store.os, "chmod", exploding_chmod)

    target = tmp_path / "creds.json"
    target.write_text("{}", encoding="utf-8")

    with caplog.at_level("WARNING"):
        ok = credential_store._restrict_acl(target)

    assert ok is False, "a failed hardening attempt must not report success"
    assert any("restrict permissions" in record.message.lower()
               or "restrict permissions" in record.getMessage().lower()
               for record in caplog.records), (
        f"the failure was not logged; records were {[r.getMessage() for r in caplog.records]}"
    )


def test_a_nonzero_icacls_exit_is_noticed(monkeypatch, tmp_path, caplog):
    """`check=False` raises nothing, so the return code has to be read to be seen."""
    import subprocess as sp

    import credential_store

    if credential_store.sys.platform != "win32":
        import pytest

        pytest.skip("icacls is Windows-only")

    monkeypatch.setattr(credential_store.os, "chmod", lambda *a, **k: None)
    monkeypatch.setenv("USERNAME", "someone")
    monkeypatch.setattr(
        credential_store.subprocess, "run",
        lambda *a, **k: sp.CompletedProcess(args=a, returncode=5, stdout="", stderr="Access is denied."),
    )

    with caplog.at_level("WARNING"):
        ok = credential_store._restrict_acl(tmp_path / "creds.json")

    assert ok is False
    assert any("icacls" in record.getMessage() for record in caplog.records)


def test_the_store_file_never_contains_the_plaintext_secret(tmp_path):
    """The property the whole module exists for, asserted on the bytes on disk."""
    import credential_store

    store = tmp_path / "creds.json"
    credential_store._write_store({"civitai_api_key": "sv-plaintext-canary-9182"}, store)

    raw = store.read_bytes()
    assert b"sv-plaintext-canary-9182" not in raw
    # And it round-trips, so the absence is encryption rather than a dropped write.
    assert credential_store._read_store(store).get("civitai_api_key") == "sv-plaintext-canary-9182"
