"""A job that fails before STARTING must still reach a terminal state.

`VALID_TRANSITIONS[QUEUED]` is `{STARTING, CANCELLED}` -- `QUEUED -> FAILED` is not a legal hop. And
fourteen generation handlers raise BEFORE reaching their own `transition_job(job, STARTING)`: a
missing input, an unsupported command, an unvalidated family. `fail_job` discarded
`transition_job`'s return, so those jobs kept `state == QUEUED` with an error attached.

On the queue lane that was not a cosmetic wrong state, it was permanent lost work. The item reverted
PREPARING -> QUEUED, was persisted that way, and was popped from `pending` so it never drained --
while `_load_manifest_unlocked` rebuilds `pending` from `state == QUEUED` on every start. **The item
re-ran and re-failed on every launch, forever.**

The sharpest detail: `image_runners.py` raises its native-family refusal EIGHT LINES ABOVE the
comment explaining why the guard has to come after the transition.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

# Tree-wide property, not a call-site check: no terminaliser may leave a job non-terminal.
# Runs in the pre-commit hook -- keep it fast.
pytestmark = pytest.mark.ratchet

from worker_service_state import (  # noqa: E402
    TERMINAL_STATES,
    JobRecord,
    JobState,
    cancel_job,
    fail_job,
    transition_job,
)


def _job(state: JobState) -> JobRecord:
    job = JobRecord(job_id="job_test", command="t2i")
    job.state = state
    return job


# --- the property ----------------------------------------------------------------------------------


@pytest.mark.parametrize("state", list(JobState))
def test_fail_job_terminalises_from_every_state(state):
    """The whole rule in one line. A terminaliser that can leave a job non-terminal is not one."""
    job = _job(state)
    fail_job(job, "something went wrong")
    assert job.state in TERMINAL_STATES, (
        f"fail_job left the job at {job.state.value} from {state.value} -- it would strand"
    )


@pytest.mark.parametrize("state", list(JobState))
def test_cancel_job_terminalises_from_every_state(state):
    job = _job(state)
    cancel_job(job)
    assert job.state in TERMINAL_STATES, (
        f"cancel_job left the job at {job.state.value} from {state.value}"
    )


def test_failing_straight_out_of_queued_reaches_failed():
    """The exact hop the fourteen early-refusal sites need, and the one that was illegal."""
    job = _job(JobState.QUEUED)
    assert transition_job(job, JobState.FAILED) is True
    assert job.state is JobState.FAILED


def test_the_walk_keeps_started_at_honest():
    """Walking through STARTING rather than making QUEUED -> FAILED legal: the job really did begin,
    it just failed in its first few lines. Adding the direct hop to VALID_TRANSITIONS would lose
    that, and would legalise the shortcut everywhere rather than only inside a terminaliser."""
    job = _job(JobState.QUEUED)
    assert job.timestamps.started_at is None
    fail_job(job, "refused before it could start")
    assert job.state is JobState.FAILED
    assert job.timestamps.started_at, "started_at should record that the job was entered"
    assert job.timestamps.finished_at


def test_a_terminal_job_is_not_re_terminalised():
    """An already-cancelled job must not be rewritten as failed by a late error."""
    job = _job(JobState.CANCELLED)
    fail_job(job, "late error")
    assert job.state is JobState.CANCELLED


def test_queued_to_completed_is_still_not_a_direct_hop():
    """The pre-existing rule this one is modelled on stays intact: a job may not report success
    without having run."""
    from worker_service_state import VALID_TRANSITIONS

    assert JobState.COMPLETED not in VALID_TRANSITIONS[JobState.QUEUED]
    assert JobState.FAILED not in VALID_TRANSITIONS[JobState.QUEUED]


# --- over the real protocol ------------------------------------------------------------------------


def test_an_early_refusal_reports_failed_not_queued(worker_client):
    """The user-visible half, driven through the socket the way the UI does.

    `i23d` without a workflow binding raises at worker_service.py:508, before any transition. The
    job update the UI receives must say failed -- it used to say queued, next to an error.
    """
    messages = worker_client({"command": "i23d", "prompt": "a small stone idol"})

    updates = [m for m in messages if m.get("type") == "job_update"]
    assert updates, f"no job_update at all: {messages}"

    final = updates[-1]
    assert final.get("state") == "failed", (
        f"an early refusal left the job at {final.get('state')!r}. A queue item in that state is "
        f"rebuilt into `pending` on every worker start and re-fails forever. {final}"
    )

    errors = [m for m in messages if m.get("type") == "error"]
    assert errors, "the refusal must also be reported as an error"
    assert errors[0].get("ok") is False
