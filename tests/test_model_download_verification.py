"""A downloaded model is checked against the provider's SHA256, not just its length.

Every check the transfer loop had before this was a PLAUSIBILITY check: Content-Length against the
declared size, bytes written against Content-Length, declared size within 1%. All of those pass for
any file of roughly the right length -- and the failure this module is shaped around is receiving a
*different artifact* of the right length. Civitai reuses one filename across precisions and across
uploaders, ``find_exact_download`` used to return the first same-named file from anyone, and a
download URL 302s to a delivery host. The digest is the only field in the payload that describes
the bytes rather than the listing.

Verified live against model 2823011 while writing this: all eight per-precision download URLs the
variant dialog produces resolve to the correct SHA256, including the three files that share one
filename inside "V2.0 Quants" -- exactly where a wrong match would have been invisible.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

import model_sources  # noqa: E402
from model_sources import AssetReference, _download_remote_asset  # noqa: E402

PAYLOAD = b"the bytes of a very small checkpoint" * 64
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()


class _Response:
    def __init__(self, body: bytes):
        self._body = body
        self._offset = 0
        self.headers = {"Content-Length": str(len(body))}

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = len(self._body) - self._offset
        chunk = self._body[self._offset:self._offset + size]
        self._offset += len(chunk)
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def transfer(monkeypatch, tmp_path):
    """Runs the real transfer loop over a stubbed response, with the metadata resolution stubbed
    so each test controls exactly what digest was declared."""

    def run(body: bytes, metadata: dict, *, url: str = "https://example.invalid/model.safetensors"):
        monkeypatch.setattr(model_sources.urllib.request, "urlopen",
                            lambda *a, **k: _Response(body))
        monkeypatch.setattr(model_sources, "_resolve_download_url_and_metadata",
                            lambda ref, **kwargs: (url, dict(metadata)))
        ref = AssetReference(raw=url, kind="direct_url", source_name="direct", asset_type="model",
                             url=url, filename="model.safetensors")
        return _download_remote_asset(ref, cache_root=str(tmp_path), civitai_api_key=None,
                                      force_download=True, timeout_sec=30)

    return run


def _downloaded_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file()]


def test_matching_bytes_are_accepted_and_recorded_as_verified(transfer, tmp_path):
    result = transfer(PAYLOAD, {"filename": "model.safetensors", "sha256": DIGEST})
    assert Path(result.local_path).read_bytes() == PAYLOAD
    assert result.metadata["sha256_verified"] is True


def test_bytes_that_do_not_match_the_declared_digest_are_refused(transfer, tmp_path):
    """The right length, the right name, the wrong file -- which every other check passes."""
    other = b"x" * len(PAYLOAD)
    assert len(other) == len(PAYLOAD), "the point is that only the digest can tell these apart"

    with pytest.raises(RuntimeError, match="SHA256"):
        transfer(other, {"filename": "model.safetensors", "sha256": DIGEST})


def test_a_refused_download_leaves_nothing_behind(transfer, tmp_path):
    """No partial file, and above all no file at the destination -- otherwise the next run finds it
    on disk, takes the cache-hit branch, and the wrong artifact is now permanent."""
    with pytest.raises(RuntimeError):
        transfer(b"y" * len(PAYLOAD), {"filename": "model.safetensors", "sha256": DIGEST})
    assert _downloaded_files(tmp_path) == []


def test_a_provider_that_declares_no_digest_still_downloads_but_says_it_is_unverified(transfer):
    """Refusing here would break every Hugging Face and direct-URL download. "Unverified" is a
    state the caller can see, which is the honest alternative to pretending it was checked."""
    result = transfer(PAYLOAD, {"filename": "model.safetensors"})
    assert Path(result.local_path).read_bytes() == PAYLOAD
    assert result.metadata["sha256_verified"] is False


def test_the_digest_comparison_is_case_insensitive_about_the_declaration(transfer):
    """Providers publish hex in either case; a case difference is not a mismatch."""
    result = transfer(PAYLOAD, {"filename": "model.safetensors", "sha256": DIGEST.upper()})
    assert result.metadata["sha256_verified"] is True


def test_the_file_is_hashed_as_it_arrives_rather_than_re_read(transfer, monkeypatch):
    """These files reach 24 GB. Verifying by re-reading the finished file would roughly double the
    wall-clock cost of every download, so the digest is fed from the transfer loop's own chunks."""
    import inspect

    source = inspect.getsource(model_sources._download_remote_asset)
    assert "digest.update(chunk)" in source
    assert "read_bytes()" not in source


# --- picking the right file to compare against ---------------------------------------------------


def test_the_file_id_in_the_url_selects_the_entry_whose_digest_is_used():
    """One version publishes the same filename at several precisions, so the version's PRIMARY file
    is frequently not the file being fetched. Attaching the primary's digest to a different file's
    bytes would fail a perfectly good download -- a verification that fires on correct input is
    worse than none."""
    payload = {"files": [
        {"id": 1, "name": "ckpt.safetensors", "primary": True, "sizeKB": 25_000_000,
         "hashes": {"SHA256": "aaaa"}},
        {"id": 2, "name": "ckpt.safetensors", "sizeKB": 12_000_000, "hashes": {"SHA256": "bbbb"}},
    ]}
    assert model_sources._pick_primary_civitai_file(payload)["id"] == 1
    assert model_sources._pick_primary_civitai_file(payload, "2")["id"] == 2
    # An id that is not there resolves to nothing rather than to the primary: better no digest than
    # the wrong one.
    assert model_sources._pick_primary_civitai_file(payload, "9") == {}


def _version_payload():
    return {"files": [
        {"id": 11, "name": "ckpt.safetensors", "primary": True, "type": "Model",
         "metadata": {"format": "SafeTensor", "size": "full", "fp": "bf16"},
         "hashes": {"SHA256": "AAAA"}},
        {"id": 12, "name": "ckpt.safetensors", "type": "Model",
         "metadata": {"format": "SafeTensor", "size": "full", "fp": "fp8"},
         "hashes": {"SHA256": "BBBB"}},
    ]}


def _ref(url: str, params: dict) -> AssetReference:
    return AssetReference(raw=url, kind="civitai_download_url", source_name="civitai",
                          asset_type="model", url=url, model_version_id="3262504",
                          query_params=params)


def test_a_download_url_is_matched_to_its_file_by_the_selectors_civitai_puts_in_it(monkeypatch):
    """This is the path the variant dialog produces -- it returns the chosen file's own
    downloadUrl. Without this lookup it would be the one download path with no digest, so the
    common case went unchecked while the rarer ones were covered."""
    monkeypatch.setattr(model_sources, "_civitai_api_get_json",
                        lambda url, **kwargs: _version_payload())

    by_fp = model_sources._civitai_file_behind_download_url(
        _ref("https://civitai.com/api/download/models/3262504?fp=fp8", {"fp": "fp8"}),
        civitai_api_key=None, timeout_sec=10)
    assert by_fp["id"] == 12

    by_id = model_sources._civitai_file_behind_download_url(
        _ref("https://civitai.com/api/download/models/3262504?fileId=11", {"fileId": "11"}),
        civitai_api_key=None, timeout_sec=10)
    assert by_id["id"] == 11


def test_an_ambiguous_or_unreachable_lookup_yields_no_digest_rather_than_a_guess(monkeypatch):
    """Both failures cost verification and nothing else. Guessing which file was meant would attach
    the wrong digest and refuse a good download."""
    monkeypatch.setattr(model_sources, "_civitai_api_get_json",
                        lambda url, **kwargs: _version_payload())
    # No selectors and two candidate files: nothing distinguishes them.
    assert model_sources._civitai_file_behind_download_url(
        _ref("https://civitai.com/api/download/models/3262504", {}),
        civitai_api_key=None, timeout_sec=10) == {}

    def explode(url, **kwargs):
        raise RuntimeError("Civitai API request failed")

    monkeypatch.setattr(model_sources, "_civitai_api_get_json", explode)
    assert model_sources._civitai_file_behind_download_url(
        _ref("https://civitai.com/api/download/models/3262504?fileId=11", {"fileId": "11"}),
        civitai_api_key=None, timeout_sec=10) == {}
