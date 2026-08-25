"""Durable retry archive survives worker restart."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PYTHON_ROOT = ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

import worker_service as ws
from worker_service_state import JobError, JobRecord, JobState


def test_archived_failure_remains_retryable_after_reload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive_path = tmp_path / "job_archive.json"
    monkeypatch.setattr(ws, "JOB_ARCHIVE_PATH", archive_path)
    monkeypatch.setattr(ws, "persist_video_history_entry", lambda _entry: None)
    monkeypatch.setattr(ws, "build_history_entry", lambda _job, _request: None)
    ws.JOB_ARCHIVE.clear()
    ws.JOB_ARCHIVE_ORDER.clear()

    job = JobRecord(job_id="job_source", command="t2i", state=JobState.FAILED)
    job.error = JobError(code="render_failed", message="boom")
    job.retry_count = 1
    request = {
        "command": "t2i",
        "prompt": "persistent retry",
        "output": str(tmp_path / "plate.png"),
        "metadata_output": str(tmp_path / "plate.json"),
        "retry_count": 1,
    }
    ws.archive_job(job, request)
    assert archive_path.is_file()

    ws.JOB_ARCHIVE.clear()
    ws.JOB_ARCHIVE_ORDER.clear()
    ws.load_job_archive()
    retry = ws.build_retry_request("job_source", {})

    assert retry is not None
    assert retry["prompt"] == "persistent retry"
    assert retry["retry_of"] == "job_source"
    assert retry["retry_count"] == 2


def test_corrupt_archive_fails_closed_without_destroying_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive_path = tmp_path / "job_archive.json"
    archive_path.write_text("{truncated", encoding="utf-8")
    monkeypatch.setattr(ws, "JOB_ARCHIVE_PATH", archive_path)
    ws.JOB_ARCHIVE.clear()
    ws.JOB_ARCHIVE_ORDER.clear()

    ws.load_job_archive()

    assert ws.JOB_ARCHIVE == {}
    assert archive_path.read_text(encoding="utf-8") == "{truncated"
