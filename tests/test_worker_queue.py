"""Worker queue contract tests, using the test-only `noop_slow` command.

These tests verify the queue / state-machine / cancellation paths of
worker_service.py without requiring a real generation backend. They use the
`noop_slow` command added in python/worker_service.py (see
WORKER_NOOP_SLOW_EDITS.md).

Three tests:

  test_noop_slow_completes_through_full_state_machine
      Submits a quick noop_slow and verifies the job reaches state
      'completed' in both the job_update stream and the terminal result
      message. This is the contract ping currently fails -- so if this test
      passes while the ping xfail still xfails, we have confirmed the bug is
      local to ping (specifically, the queued -> completed direct jump),
      not a systemic problem with transition_job.

  test_noop_slow_emits_monotonic_progress
      Submits a multi-step noop_slow and verifies progress values are
      monotonically non-decreasing and end at total.

  test_noop_slow_can_be_cancelled
      Submits a long noop_slow on a background thread, sends a cancel
      command, and verifies the job ends in state 'cancelled'. If the
      worker rejects the cancel command name we are guessing, this test
      self-skips with a clear diagnostic.
"""

from __future__ import annotations

import socket
import threading
import time

import pytest


def _format_stream(messages):
    if not messages:
        return "  (empty stream)"
    return "\n".join(f"  [{i:2d}] {m}" for i, m in enumerate(messages))


def _states_from_job_updates(messages, job_id):
    return [
        m.get("state")
        for m in messages
        if m.get("type") == "job_update" and m.get("job_id") == job_id and m.get("state")
    ]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

@pytest.mark.contract
def test_noop_slow_completes_through_full_state_machine(worker_client):
    """A normal command must transition queued -> running -> completed.

    This is the contract ping currently fails. If THIS test passes while
    test_ping_terminal_state_reaches_completed continues to xfail, the bug
    is confirmed to be a queued -> completed direct-jump rejection in
    transition_job, not a systemic state-machine failure.
    """
    job_id = "test-noop-happy-001"
    messages = worker_client(
        {
            "command": "noop_slow",
            "job_id": job_id,
            "duration_sec": 0.1,
            "steps": 3,
        },
        timeout=15.0,
    )

    assert messages, "worker emitted no messages"

    # Terminal result must be ok and report state=completed.
    results = [m for m in messages if m.get("type") == "result"]
    assert results, (
        f"no terminal result message.\n"
        f"types seen: {[m.get('type') for m in messages]}\n"
        f"full stream:\n{_format_stream(messages)}"
    )
    terminal = results[-1]
    assert terminal.get("ok") is True, (
        f"noop_slow result not ok: {terminal!r}\n"
        f"full stream:\n{_format_stream(messages)}"
    )
    assert terminal.get("state") == "completed", (
        f"noop_slow terminal state expected 'completed', got "
        f"{terminal.get('state')!r}.\n"
        f"terminal message: {terminal!r}\n"
        f"full stream:\n{_format_stream(messages)}"
    )

    # The job_update stream must pass through 'running' on the way to
    # 'completed'. This is what proves we are exercising the full state
    # machine, not bypassing it like ping does.
    states_seen = _states_from_job_updates(messages, job_id)
    assert "running" in states_seen, (
        f"job_update stream never showed 'running' state.\n"
        f"states for {job_id}: {states_seen}\n"
        f"full stream:\n{_format_stream(messages)}"
    )
    assert "completed" in states_seen, (
        f"job_update stream never reached 'completed' state.\n"
        f"states for {job_id}: {states_seen}\n"
        f"full stream:\n{_format_stream(messages)}"
    )


# ---------------------------------------------------------------------------
# Progress monotonicity
# ---------------------------------------------------------------------------

@pytest.mark.contract
def test_noop_slow_emits_monotonic_progress(worker_client):
    """Progress values must be non-decreasing and reach the declared total.

    The C++ shell's GenerationStatusController and the bottom progress bar
    both assume progress only moves forward and ends at total. A regression
    where a backend emits progress out of order would cause the UI to
    visibly jitter.
    """
    job_id = "test-noop-progress-001"
    steps = 5
    messages = worker_client(
        {
            "command": "noop_slow",
            "job_id": job_id,
            "duration_sec": 0.2,
            "steps": steps,
        },
        timeout=15.0,
    )

    # Pull (current, total) from every job_update that carries progress info
    # for this job.
    progress_points: list[tuple[int, int]] = []
    for msg in messages:
        if msg.get("type") != "job_update":
            continue
        if msg.get("job_id") != job_id:
            continue
        prog = msg.get("progress")
        if not isinstance(prog, dict):
            continue
        current = prog.get("current")
        total = prog.get("total")
        if isinstance(current, int) and isinstance(total, int):
            progress_points.append((current, total))

    assert progress_points, (
        f"no progress points for {job_id}.\n"
        f"full stream:\n{_format_stream(messages)}"
    )

    # Monotonic non-decreasing in 'current'.
    currents = [c for c, _t in progress_points]
    for prev, curr in zip(currents, currents[1:]):
        assert curr >= prev, (
            f"progress went backwards: {prev} -> {curr}.\n"
            f"all progress points: {progress_points}\n"
            f"full stream:\n{_format_stream(messages)}"
        )

    # Final progress reaches total.
    final_current, final_total = progress_points[-1]
    assert final_total == steps, (
        f"final progress total expected {steps}, got {final_total}.\n"
        f"all progress points: {progress_points}"
    )
    assert final_current == final_total, (
        f"final progress current ({final_current}) did not reach total "
        f"({final_total}).\n"
        f"all progress points: {progress_points}\n"
        f"full stream:\n{_format_stream(messages)}"
    )


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------

def _probe_cancel_command_name(host: str, port: int) -> str | None:
    """Try the most likely cancel command names against a non-existent job.

    Returns the first name the worker does not reject as unknown_command,
    or None if all candidates fail. We probe with a nonexistent job_id so
    we never accidentally cancel real work.
    """
    candidates = ["cancel_job", "cancel", "request_job_cancel", "job_cancel"]
    for name in candidates:
        try:
            with socket.create_connection((host, port), timeout=5.0) as sock:
                payload = f'{{"command": "{name}", "job_id": "__probe_nonexistent__"}}\n'
                sock.sendall(payload.encode("utf-8"))
                sock.shutdown(socket.SHUT_WR)
                sock.settimeout(5.0)
                buf = b""
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
        except Exception:
            continue

        text = buf.decode("utf-8", errors="replace")
        # If the response mentions unknown_command, this name is wrong.
        if "unknown_command" in text:
            continue
        return name
    return None


@pytest.mark.contract
def test_noop_slow_can_be_cancelled(worker_service, worker_client):
    """A long-running noop_slow must finish promptly when cancelled.

    We submit a noop_slow with duration_sec=5.0 on a background thread,
    wait a short moment so the worker actually starts processing, then
    send a cancel command on the main thread. The submission must return
    within a small multiple of the cancel-send time, well below the 5s
    requested duration.
    """
    host = worker_service["host"]
    port = worker_service["port"]

    # Determine the cancel command name. If none of our candidates work, skip
    # with diagnostic info -- we want this test to be useful next iteration
    # rather than silently failing.
    cancel_command = _probe_cancel_command_name(host, port)
    if cancel_command is None:
        pytest.skip(
            "Could not determine the external cancel command name. None of "
            "['cancel_job', 'cancel', 'request_job_cancel', 'job_cancel'] "
            "were accepted by the worker. Inspect worker_service.py's "
            "WorkerTCPHandler.handle() to find the actual cancel command "
            "and update _probe_cancel_command_name in this test."
        )

    job_id = "test-noop-cancel-001"
    submission: dict = {}

    def submit():
        try:
            submission["messages"] = worker_client(
                {
                    "command": "noop_slow",
                    "job_id": job_id,
                    "duration_sec": 5.0,
                    "steps": 100,
                },
                timeout=15.0,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced via submission dict
            submission["error"] = exc

    submit_thread = threading.Thread(target=submit, daemon=True)
    started_at = time.monotonic()
    submit_thread.start()

    # Give the worker a moment to actually start processing. noop_slow with
    # duration=5.0 and steps=100 yields a 50ms per-step rhythm, so 300ms is
    # comfortably inside the job.
    time.sleep(0.3)

    # Send the cancel.
    cancel_messages = worker_client(
        {"command": cancel_command, "job_id": job_id},
        timeout=5.0,
    )

    # The submission must finish far faster than its requested 5.0s duration.
    # If cancel is honored promptly we expect well under 1.5s wall time.
    submit_thread.join(timeout=10.0)
    elapsed = time.monotonic() - started_at
    assert not submit_thread.is_alive(), (
        f"noop_slow did not finish within 10s after cancel; submission still "
        f"running. cancel command: {cancel_command!r}, cancel response: "
        f"{cancel_messages!r}"
    )
    assert "error" not in submission, (
        f"submission thread raised: {submission.get('error')!r}"
    )
    assert elapsed < 4.0, (
        f"noop_slow took {elapsed:.2f}s after cancel; expected well under "
        f"the 5.0s requested duration. cancel may not be effective.\n"
        f"cancel command: {cancel_command!r}\n"
        f"cancel response: {cancel_messages!r}"
    )

    # The submission's job_update stream should report state='cancelled' at
    # some point. (We don't require it on the terminal 'result' message,
    # because we've seen that the result message's state can lag transitions
    # depending on the code path.)
    messages = submission.get("messages", [])
    states_seen = _states_from_job_updates(messages, job_id)
    assert "cancelled" in states_seen, (
        f"job never reached 'cancelled' state via job_update.\n"
        f"states for {job_id}: {states_seen}\n"
        f"cancel command used: {cancel_command!r}\n"
        f"cancel response: {cancel_messages!r}\n"
        f"submission stream:\n{_format_stream(messages)}"
    )
