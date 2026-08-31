"""/object_info must not be fetched with `Connection: close`, because that header causes the reset.

The reset it was added to fix ("the ~2MB body resets mid-read, so send Connection: close and retry")
was really caused by it. Measured against ComfyUI core v0.34.0 on :8189, 6.76MB body, identical
requests otherwise:

    bare / Accept-Encoding: identity / Accept-Encoding: gzip -> 3 of 3 succeeded
    Connection: close, with or without gzip                  -> 3 of 3 ConnectionResetError

urllib always sends that header -- ``AbstractHTTPHandler.do_open`` puts it unconditionally -- so no
urlopen-based fetch can avoid it, and dropping the explicit header changed nothing. The fix is a
different client. Effect on the suite: the readiness test went from 20.9s (retry budget burning
against a server that reset every attempt) to 0.12s.

These tests run against a local stdlib server, so they assert the wire behaviour without needing
ComfyUI.
"""
from __future__ import annotations

import gzip
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))
import comfy_prompt_client as cpc  # noqa: E402


PAYLOAD = {"KSampler": {"display_name": "KSampler"}, "VAEDecode": {"display_name": "VAE Decode"}}


class _Handler(BaseHTTPRequestHandler):
    seen_headers: dict[str, str] = {}
    serve_gzip = False

    def do_GET(self):  # noqa: N802 - stdlib naming
        type(self).seen_headers = {k.lower(): v for k, v in self.headers.items()}
        body = json.dumps(PAYLOAD).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        if type(self).serve_gzip and "gzip" in (self.headers.get("Accept-Encoding") or ""):
            body = gzip.compress(body)
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # keep pytest output clean
        pass


@pytest.fixture
def server():
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_the_fetch_never_sends_connection_close(server):
    """The regression guard. This header, not the body size, is what resets the socket."""
    _Handler.serve_gzip = False
    cpc._http_get_json(server, "/object_info")
    assert "connection" not in _Handler.seen_headers, _Handler.seen_headers


def test_a_gzipped_response_is_decompressed(server):
    _Handler.serve_gzip = True
    assert cpc._http_get_json(server, "/object_info") == PAYLOAD


def test_an_uncompressed_response_still_parses(server):
    _Handler.serve_gzip = False
    assert cpc._http_get_json(server, "/object_info") == PAYLOAD


def test_object_info_goes_through_this_transport(server, monkeypatch):
    """The cache sits in front of it, so clear it or the assertion tests a stale entry."""
    _Handler.serve_gzip = True
    monkeypatch.setattr(cpc, "_OBJECT_INFO_CACHE", {})
    assert cpc._fetch_comfy_object_info(server) == PAYLOAD
    assert "connection" not in _Handler.seen_headers


def test_an_http_error_is_raised_not_returned_as_a_partial_dict(server, monkeypatch):
    """A truncated or error body must never reach node resolution as if it were a schema."""
    def failing(*args, **kwargs):
        raise RuntimeError("HTTP 503 from ComfyUI")

    monkeypatch.setattr(cpc, "_http_get_json", failing)
    monkeypatch.setattr(cpc, "_OBJECT_INFO_RETRY_BUDGET_SEC", 0.1)
    with pytest.raises(RuntimeError, match="Failed to read ComfyUI object_info"):
        cpc._fetch_comfy_object_info(server)
