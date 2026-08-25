"""Active worker job ids are unique and cannot overwrite an in-flight owner."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))

from worker_service_state import (  # noqa: E402
    ActiveJobHandle,
    JobRecord,
    get_active_job,
    register_active_job,
    unregister_active_job,
)


def test_register_active_job_rejects_duplicate_without_replacing_owner() -> None:
    job_id = "job-duplicate-regression"
    unregister_active_job(job_id)
    first = ActiveJobHandle(job=JobRecord(job_id=job_id, command="noop_slow"))
    second = ActiveJobHandle(job=JobRecord(job_id=job_id, command="noop_slow"))
    try:
        assert register_active_job(first) is True
        assert register_active_job(second) is False
        assert get_active_job(job_id) is first
    finally:
        unregister_active_job(job_id)
