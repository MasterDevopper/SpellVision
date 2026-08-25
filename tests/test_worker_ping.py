"""Ping contract tests.

The ping command is the smallest end-to-end exercise of the worker service.
These tests pin the basic invariants of the C++ <-> Python contract that
everything else relies on.

QUEUED → COMPLETED stays illegal as a direct hop. Instant jobs (ping) reach
COMPLETED by walking STARTING → RUNNING → COMPLETED inside transition_job.
"""

from __future__ import annotations

import pytest


def _format_stream(messages):
    """Pretty-print the full message stream for use in assertion messages."""
    if not messages:
        return "  (empty stream)"
    return "\n".join(f"  [{i:2d}] {m}" for i, m in enumerate(messages))


@pytest.mark.contract
def test_ping_returns_pong(worker_client):
    """Core ping contract: terminal result message has ok, pong, job_id.

    This is the contract the C++ shell actually relies on. We do *not*
    assert anything about `state` here -- see the module docstring and
    test_ping_terminal_state_reaches_completed below.
    """
    messages = worker_client({"command": "ping"}, timeout=15.0)

    assert messages, "worker emitted no messages at all"

    # Every message must be a dict with a 'type' field; this is the basic
    # shape the C++ WorkerResponseParser assumes.
    for i, msg in enumerate(messages):
        assert isinstance(msg, dict), (
            f"message {i} is not a dict: {msg!r}\nfull stream:\n{_format_stream(messages)}"
        )
        assert "type" in msg, (
            f"message {i} missing 'type': {msg!r}\nfull stream:\n{_format_stream(messages)}"
        )

    # The worker must close the stream with at least one terminal 'result'
    # message. (There may be earlier job_update messages, but 'result' is the
    # one the C++ side blocks on.)
    results = [m for m in messages if m.get("type") == "result"]
    assert results, (
        f"no terminal result message in worker output.\n"
        f"types seen: {[m.get('type') for m in messages]}\n"
        f"full stream:\n{_format_stream(messages)}"
    )

    terminal = results[-1]
    assert terminal.get("ok") is True, (
        f"ping result not ok: {terminal!r}\nfull stream:\n{_format_stream(messages)}"
    )
    assert terminal.get("pong") is True, (
        f"ping result missing pong: {terminal!r}\nfull stream:\n{_format_stream(messages)}"
    )
    assert terminal.get("job_id"), (
        f"ping result missing job_id: {terminal!r}\nfull stream:\n{_format_stream(messages)}"
    )


@pytest.mark.contract
def test_ping_assigns_job_id_when_client_omits_it(worker_client):
    """The worker must mint a job_id when the client does not provide one.

    The C++ shell relies on this so it can track progress even for ad-hoc
    ping/diagnostic requests.
    """
    messages = worker_client({"command": "ping"}, timeout=15.0)

    job_ids = {m.get("job_id") for m in messages if m.get("job_id")}
    assert len(job_ids) == 1, (
        f"expected exactly one job_id across the ping stream, got: {job_ids}\n"
        f"full stream:\n{_format_stream(messages)}"
    )
    (job_id,) = job_ids
    assert isinstance(job_id, str) and job_id.strip(), (
        f"job_id is not a non-empty string: {job_id!r}"
    )


@pytest.mark.contract
def test_ping_respects_client_supplied_job_id(worker_client):
    """If the client supplies a job_id, the worker must echo it back."""
    supplied = "test-ping-job-0001"
    messages = worker_client({"command": "ping", "job_id": supplied}, timeout=15.0)

    results = [m for m in messages if m.get("type") == "result"]
    assert results, f"no result in stream:\n{_format_stream(messages)}"
    assert results[-1].get("job_id") == supplied, (
        f"worker did not echo supplied job_id; result: {results[-1]!r}\n"
        f"full stream:\n{_format_stream(messages)}"
    )


@pytest.mark.contract
def test_ping_terminal_state_reaches_completed(worker_client):
    """Ping terminal result must report state=completed."""
    messages = worker_client({"command": "ping"}, timeout=15.0)

    results = [m for m in messages if m.get("type") == "result"]
    assert results, f"no result in stream:\n{_format_stream(messages)}"

    terminal = results[-1]
    terminal_state = terminal.get("state")
    assert terminal_state == "completed", (
        f"ping terminal state expected 'completed', got {terminal_state!r}.\n"
        f"terminal message: {terminal!r}\n"
        f"full stream:\n{_format_stream(messages)}"
    )
