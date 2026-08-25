from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


PYTHON_DIR = Path(__file__).resolve().parent.parent / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

import worker_service as ws
import native_runners


class RecordingEmitter:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.updates = 0

    def emit(self, _payload: dict) -> None:
        pass

    def emit_job_update(self, _job: ws.JobRecord) -> None:
        self.updates += 1

    def status(self, job: ws.JobRecord, message: str) -> None:
        ws.set_job_message(job, message)
        self.messages.append(message)

    def progress(self, _job: ws.JobRecord, _step: int, _total: int, _message: str | None = None) -> None:
        pass


@pytest.mark.skipif(
    not os.environ.get("BFL_API_KEY"),
    reason="FLUX.3 is a paid BFL API preview; set BFL_API_KEY to run integration",
)
def test_worker_flux3_route_completes_history_ready_payload(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "clip.mp4"
    metadata = tmp_path / "clip.json"
    request = {
        "command": "t2v",
        "task_type": "t2v",
        "prompt": "A fox runs through mist.",
        "width": 1280,
        "height": 720,
        "frames": 120,
        "fps": 24,
        "output": str(output),
        "metadata_output": str(metadata),
        "original_output": str(output),
        "resolved_native_video_family": "flux3",
    }

    def fake_submit(req, output_path, *, should_cancel, on_status):
        assert req["backend_route"] == "bfl_api"
        assert should_cancel() is False
        on_status("Generating")
        Path(output_path).write_bytes(b"fake-mp4")
        return {"request_id": "job-remote", "output_path": str(output_path)}

    monkeypatch.setattr(native_runners, "submit_flux3_video", fake_submit)
    job = ws.create_job(request)
    active_job = ws.ActiveJobHandle(job)
    emitter = RecordingEmitter()

    result = ws.run_flux3_video(request, emitter, job, active_job)

    assert job.state == ws.JobState.COMPLETED
    assert output.read_bytes() == b"fake-mp4"
    assert metadata.is_file()
    assert result["backend_route"] == "bfl_api"
    assert result["video_backend_type"] == "bfl_api"
    assert result["video_path"] == str(output)
    assert result["flux3_request_id"] == "job-remote"
    assert "FLUX.3: Generating" in emitter.messages
