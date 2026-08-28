"""The download commands over the real TCP protocol, against a live worker.

The unit tests drive DownloadManager in-process. These prove the other half: that the commands
are actually reachable on the wire, return the documented payload shape, and -- the point of the
whole lane -- that issuing one does not stop the worker answering anything else.

Nothing here touches the network. A bad reference fails fast in the resolver, which is enough to
exercise start -> status -> terminal state without downloading a gigabyte in CI.
"""
from __future__ import annotations

import time


def _first(messages, msg_type):
    for message in messages:
        if message.get("type") == msg_type:
            return message
    raise AssertionError(f"no {msg_type!r} in {[m.get('type') for m in messages]}")


def test_download_status_is_reachable_and_empty_on_a_fresh_worker(worker_client):
    status = _first(worker_client({"command": "download_status"}), "download_status")
    assert status["ok"] is True
    assert isinstance(status["items"], list)
    assert set(status["aggregate"]) == {"current", "total", "percent", "message"}
    assert status["max_concurrent"] >= 1


def test_start_download_requires_a_reference(worker_client):
    ack = _first(worker_client({"command": "start_download"}), "download_ack")
    assert ack["ok"] is False
    assert "reference" in ack["error"]


def test_start_download_returns_immediately_and_the_worker_stays_responsive(worker_client):
    """The requirement in one test: a download must not interrupt the rest of the app."""
    began = time.monotonic()
    ack = _first(
        worker_client({
            "command": "start_download",
            "reference": "https://invalid.invalid/definitely-not-there.safetensors",
            "label": "probe.safetensors",
        }),
        "download_ack",
    )
    elapsed = time.monotonic() - began
    assert ack["ok"] is True, ack
    assert elapsed < 10.0, "start_download must not block on the transfer"

    download_id = ack["download_id"]
    assert ack["item"]["label"] == "probe.safetensors"
    assert set(ack["item"]["progress"]) == {"current", "total", "percent", "message"}

    # The worker answers an unrelated command while that download is in flight or finishing.
    pong = _first(worker_client({"command": "ping"}), "result")
    assert pong["ok"] is True

    # And the record is visible by id from a brand-new connection -- no socket is held open.
    status = _first(
        worker_client({"command": "download_status", "download_id": download_id}),
        "download_status",
    )
    assert status["ok"] is True
    assert status["items"][0]["download_id"] == download_id

    # It reaches a terminal state on its own (this reference cannot resolve, so: failed).
    deadline = time.monotonic() + 30
    state = status["items"][0]["state"]
    while time.monotonic() < deadline and state not in {"completed", "failed", "cancelled"}:
        time.sleep(0.2)
        state = _first(
            worker_client({"command": "download_status", "download_id": download_id}),
            "download_status",
        )["items"][0]["state"]
    assert state == "failed", f"expected an unresolvable reference to fail, got {state!r}"


def test_cancel_requires_an_id_and_reports_an_unknown_one_honestly(worker_client):
    ack = _first(worker_client({"command": "cancel_download"}), "download_ack")
    assert ack["ok"] is False
    assert "download_id" in ack["error"]

    ack = _first(
        worker_client({"command": "cancel_download", "download_id": "dl_nope"}), "download_ack"
    )
    assert ack["ok"] is False
    assert ack["cancel_requested"] is False


# --- Civitai variant listing --------------------------------------------------------------


def test_civitai_variants_requires_a_reference(worker_client):
    result = _first(worker_client({"command": "civitai_variants"}), "civitai_variants")
    assert result["ok"] is False
    assert "reference" in result["error"]


def test_a_non_civitai_reference_needs_no_choice(worker_client):
    """A plain URL or a bare filename has no versions to choose between, and must not be
    reported as ambiguous just because we could not look it up."""
    for reference in ["https://example.test/model.safetensors", "foo.safetensors"]:
        result = _first(
            worker_client({"command": "civitai_variants", "reference": reference}),
            "civitai_variants",
        )
        assert result["ok"] is True, result
        assert result["needs_choice"] is False
        assert result["variants"] == []


def test_a_reference_that_already_names_its_version_needs_no_choice(worker_client):
    result = _first(
        worker_client({
            "command": "civitai_variants",
            "reference": "https://civitai.com/models/2842735/vintage-mix-by-ak?modelVersionId=3234746",
        }),
        "civitai_variants",
    )
    assert result["ok"] is True
    assert result["needs_choice"] is False, "the link already picked one"
    assert result["model_version_id"] == "3234746"
