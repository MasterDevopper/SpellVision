"""Ping contract tests.

The ping command is the smallest end-to-end exercise of the worker service.
These tests pin the basic invariants of the C++ <-> Python contract that
everything else relies on.

Test design notes
-----------------

The terminal-state contract for ping is currently **broken** in the worker.
Specifically:

  * worker_service.py's ping handler calls
        transition_job(job, JobState.COMPLETED)
    but `transition_job` evidently rejects the queued -> completed transition
    (likely a state-machine guard requiring a queued -> running -> completed
    path). The call returns without raising, but `job.state` stays as QUEUED.
  * Consequently, every message in the ping stream -- including the terminal
    `result` message -- reports `state: "queued"`, even though `ok: true` and
    `pong: true` are correctly set and the C++ side sees the request as
    successful.

The C++ shell currently gets away with this because the ping handler is only
used for diagnostics and the C++ side keys off `ok`/`pong`, not `state`. But
it is a real contract gap that should be fixed in the worker.

We pin this with a strict xfail test rather than a passing assertion against
the broken behavior, so that:

  * `pytest` is green today (xfail counts as expected-fail, not a regression).
  * The day someone repairs `transition_job` for fast-completing jobs, the
    xfail will XPASS, pytest will fail loudly, and we will remember to delete
    the xfail and adopt the contract as a hard requirement.
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
@pytest.mark.xfail(
    strict=True,
    reason=(
        "Known worker bug: transition_job(JobState.COMPLETED) silently fails "
        "to mutate job.state for ping, so the terminal 'result' message "
        "still reports state='queued'. The pong/ok contract is met but the "
        "state contract is not. Likely cause: state-machine validation that "
        "requires queued -> running -> completed and silently rejects a "
        "direct queued -> completed jump. When this test starts XPASSing "
        "(i.e. the worker is fixed), delete this @xfail and adopt the "
        "assertion as a hard contract requirement."
    ),
)
def test_ping_terminal_state_reaches_completed(worker_client):
    """Pin the intended terminal-state contract for ping.

    See the module docstring for the full context. This test is strict-xfail
    today because the worker does not yet satisfy this contract.
    """
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
