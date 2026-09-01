"""Civitai wants its key in the query on downloads, and in a header on the API. Not the same call.

Every authenticated Civitai download failed, and the error pointed at nothing useful:

    400 InvalidRequest -- Missing x-amz-content-sha256

The download endpoint 302s to an S3-backed CDN and urllib carries ``Authorization`` across the
redirect. S3 reads ``Bearer <key>`` as a half-finished SigV4 attempt and rejects it with an error
about AWS request signing -- on a request that never meant to talk to AWS. Nothing in that message
suggests the credential is simply in the wrong place, which is why the download lane could be broken
without anyone reading it as an auth bug.

Measured against the live endpoint before the fix, same URL and key:

    Authorization: Bearer <key>   -> 400, the S3 signing error
    ?token=<key>                  -> 200, binary/octet-stream, 13,148,974,712 bytes

The API-JSON endpoint is the opposite: no redirect, and it takes the header. So this is a case where
"be consistent" is the wrong instinct -- the two calls genuinely differ, and a fix that unified them
would break the half that works. Both directions are asserted here for that reason.

The third property is the one that would be a security bug rather than a broken feature: the token
goes into the URL used for the REQUEST, and must not reach the URL recorded in asset metadata, which
is persisted into an on-disk manifest.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import model_sources  # noqa: E402

KEY = "civitai-test-key-do-not-log"


def _download_block() -> str:
    """The auth block from the download path, by name rather than by line number."""
    source = (ROOT / "python" / "model_sources.py").read_text(encoding="utf-8")
    start = source.index("def _download_remote_asset")
    end = source.index("def ", start + 10)
    return source[start:end]


# --- the download path: query, not header --------------------------------------------------------

def test_the_download_path_puts_the_key_in_the_query() -> None:
    block = _download_block()
    assert 'request_url = _append_query_params(download_url, {"token": civitai_api_key})' in block


def test_the_download_path_does_not_set_an_authorization_header_for_civitai() -> None:
    """The regression, stated exactly. This header is what S3 rejects."""
    block = _download_block()
    assert 'headers.setdefault("Authorization", f"Bearer {civitai_api_key}")' not in block, (
        "the Bearer header is carried across Civitai's redirect to S3 and answered with "
        "400 InvalidRequest / Missing x-amz-content-sha256"
    )


def test_the_request_uses_the_token_bearing_url() -> None:
    block = _download_block()
    assert "urllib.request.Request(request_url" in block
    assert "urllib.request.Request(download_url" not in block


# --- the API path is deliberately the other way ---------------------------------------------------

def test_the_api_json_path_still_uses_a_header() -> None:
    """Not an inconsistency to tidy away. The API endpoint does not redirect and takes the header;
    unifying the two would break the half that works."""
    source = (ROOT / "python" / "model_sources.py").read_text(encoding="utf-8")
    start = source.index("def _civitai_api_get_json")
    block = source[start:source.index("def ", start + 10)]
    assert 'headers["Authorization"] = f"Bearer {civitai_api_key}"' in block


# --- the token must not be persisted --------------------------------------------------------------

def test_the_recorded_url_is_the_clean_one() -> None:
    """`download_url` is written into asset metadata and from there into an on-disk manifest.
    Appending the token to that variable rather than to a separate request URL would write the
    credential to disk -- a broken feature becoming a leaked secret."""
    block = _download_block()
    assert 'metadata["download_url"] = download_url' in block
    assert 'metadata["download_url"] = request_url' not in block


def test_appending_the_token_leaves_the_original_url_untouched() -> None:
    original = "https://civitai.com/api/download/models/3262504?fileId=3146121"
    with_token = model_sources._append_query_params(original, {"token": KEY})
    assert KEY in with_token
    assert KEY not in original
    assert "fileId=3146121" in with_token, "the existing query must survive"


def test_a_url_with_no_query_still_gets_one() -> None:
    out = model_sources._append_query_params(
        "https://civitai.com/api/download/models/3238520", {"token": KEY})
    assert out.endswith(f"?token={KEY}") or f"token={KEY}" in out


@pytest.mark.parametrize("params", [{}, None])
def test_no_params_is_a_no_op(params) -> None:
    url = "https://civitai.com/api/download/models/1"
    assert model_sources._append_query_params(url, params or {}) == url
