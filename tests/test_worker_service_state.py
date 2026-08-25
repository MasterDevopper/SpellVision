"""Unit tests for the worker job state machine.

C5: QUEUED → COMPLETED is not a direct legal hop. Instant jobs (ping) must
still reach COMPLETED by walking STARTING → RUNNING → COMPLETED.
"""

from __future__ import annotations

import sys
from pathlib import Path

PYTHON_DIR = Path(__file__).resolve().parent.parent / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from worker_service_state import (  # noqa: E402
    JobState,
    VALID_TRANSITIONS,
    create_job,
    transition_job,
)


def test_queued_to_completed_is_not_a_direct_legal_transition() -> None:
    assert JobState.COMPLETED not in VALID_TRANSITIONS[JobState.QUEUED]


def test_instant_job_walks_to_completed() -> None:
    job = create_job({"command": "ping"})
    assert job.state == JobState.QUEUED

    assert transition_job(job, JobState.COMPLETED) is True
    assert job.state == JobState.COMPLETED
    assert job.timestamps.started_at
    assert job.timestamps.finished_at


def test_direct_illegal_hops_still_rejected() -> None:
    job = create_job({"command": "ping"})
    assert transition_job(job, JobState.RUNNING) is False
    assert job.state == JobState.QUEUED

    completed = create_job({"command": "ping"})
    assert transition_job(completed, JobState.STARTING) is True
    assert transition_job(completed, JobState.RUNNING) is True
    assert transition_job(completed, JobState.COMPLETED) is True
    assert transition_job(completed, JobState.RUNNING) is False
    assert completed.state == JobState.COMPLETED
