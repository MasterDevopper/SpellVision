"""The CivitAI client.

Verified live on 2026-09-16 with the owner's read-only key:
  * by-hash hit 4 of 4 local weights, and the ANONYMOUS response was identical to the keyed one.
    Reads do not need a key; downloads and mature previews do. So a missing key must never be
    treated as an error.
  * civitai.red returned byte-identical JSON for the same hash. The host is a setting.
  * an all-zero hash returns HTTP 404, which is a MISS and not a failure.

The unit tests drive a fake opener so they neither need the network nor a key. One live test at
the end carries `needs_network` and skips cleanly when offline.
"""
from __future__ import annotations

import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from model_intelligence import civitai_lookup

FIXTURES = Path(__file__).parent / "fixtures" / "model_intelligence"
HOUSE = json.loads((FIXTURES / "index.json").read_text(encoding="utf-8"))


class FakeResponse(io.BytesIO):
    status = 200

    def __init__(self, payload):
        super().__init__(json.dumps(payload).encode("utf-8"))


class FakeOpener:
    """Records every request and replays canned responses."""

    def __init__(self, responses):
        self.responses = responses
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        entry = self.responses.pop(0)
        if isinstance(entry, Exception):
            raise entry
        return FakeResponse(entry)


def _payload(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def test_the_default_opener_can_actually_open_a_request():
    """`urllib.request` (the module) has no `.open` -- only an `OpenerDirector` does. A client
    built with no `opener=` argument must default to something that survives the FIRST real
    request, not just construction: `civitai_lookup.CivitaiClient().by_hash(...)` used to raise
    `AttributeError` here before any bytes moved, because `opener or urllib.request` fell back to
    the bare module. This asserts the shape the default must have, with no network call."""
    client = civitai_lookup.CivitaiClient()
    assert client._opener is not civitai_lookup.urllib.request
    assert callable(getattr(client._opener, "open", None))


def test_by_hash_returns_the_version():
    opener = FakeOpener([_payload("civitai_checkpoint_combined_sampler")])
    client = civitai_lookup.CivitaiClient(opener=opener)
    version = client.by_hash("c25a00f94e1b117770291364f6431e21b4e1d7a83890ddb68b1396ec3a1db808")
    assert version["model"]["name"].startswith("Lox's Utopic World")
    assert version["baseModel"] == "Krea 2"


def test_a_404_is_a_miss_not_an_error():
    error = urllib.error.HTTPError("u", 404, "Not Found", {}, io.BytesIO(b"{}"))
    client = civitai_lookup.CivitaiClient(opener=FakeOpener([error]))
    assert client.by_hash("0" * 64) is None


def test_no_key_sends_no_authorization_header():
    opener = FakeOpener([_payload("civitai_controlnet_sparse_meta")])
    civitai_lookup.CivitaiClient(api_key=None, opener=opener).by_hash("a" * 64)
    assert opener.requests[0].get_header("Authorization") is None


def test_a_key_is_sent_as_a_bearer_token():
    opener = FakeOpener([_payload("civitai_controlnet_sparse_meta")])
    civitai_lookup.CivitaiClient(api_key="secret", opener=opener).by_hash("a" * 64)
    assert opener.requests[0].get_header("Authorization") == "Bearer secret"


def test_the_host_is_configurable_and_validated():
    opener = FakeOpener([_payload("civitai_controlnet_sparse_meta")])
    civitai_lookup.CivitaiClient(host="civitai.red", opener=opener).by_hash("a" * 64)
    assert opener.requests[0].full_url.startswith("https://civitai.red/api/v1/")
    with pytest.raises(ValueError):
        civitai_lookup.CivitaiClient(host="evil.example.com")


def test_a_429_is_retried_then_gives_up():
    throttled = urllib.error.HTTPError("u", 429, "Too Many", {}, io.BytesIO(b"{}"))
    opener = FakeOpener([throttled, throttled, throttled, throttled])
    client = civitai_lookup.CivitaiClient(opener=opener, sleep=lambda _s: None)
    with pytest.raises(civitai_lookup.CivitaiThrottled):
        client.by_hash("a" * 64)
    assert len(opener.requests) == 4


def test_a_429_that_clears_returns_the_version():
    throttled = urllib.error.HTTPError("u", 429, "Too Many", {}, io.BytesIO(b"{}"))
    opener = FakeOpener([throttled, _payload("civitai_controlnet_sparse_meta")])
    client = civitai_lookup.CivitaiClient(opener=opener, sleep=lambda _s: None)
    assert client.by_hash("a" * 64) is not None


def test_by_hashes_batches_and_keys_the_result_by_hash():
    one = _payload("civitai_lora_split_sampler")
    opener = FakeOpener([[one]])
    client = civitai_lookup.CivitaiClient(opener=opener)
    found = client.by_hashes([HOUSE["civitai_lora_split_sampler"]["sha256"]])
    assert list(found) == [HOUSE["civitai_lora_split_sampler"]["sha256"].lower()]


@pytest.mark.needs_network
def test_live_by_hash_hits_the_house_checkpoint():
    """The real API, anonymously. Skips when the network is not there."""
    import socket

    try:
        socket.create_connection(("civitai.com", 443), timeout=4).close()
    except OSError:
        pytest.skip("civitai.com unreachable")
    client = civitai_lookup.CivitaiClient()
    version = client.by_hash(HOUSE["civitai_checkpoint_combined_sampler"]["sha256"])
    assert version is not None
    assert version["model"]["name"].startswith("Lox's Utopic World")
