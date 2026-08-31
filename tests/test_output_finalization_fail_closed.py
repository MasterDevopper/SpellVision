from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from worker_metadata import output_finalization_contract
from worker_service_state import JobRecord, JobState, complete_job, transition_job


def _running_job(job_id: str) -> JobRecord:
    job = JobRecord(job_id=job_id, command="t2i")
    transition_job(job, JobState.STARTING)
    transition_job(job, JobState.RUNNING)
    return job


def test_zero_byte_or_non_file_output_fails_contract(tmp_path: Path) -> None:
    metadata = tmp_path / "plate.json"
    metadata.write_text("{}", encoding="utf-8")
    empty = tmp_path / "plate.png"
    empty.write_bytes(b"")

    contract = output_finalization_contract(
        str(empty), str(metadata), media_type="image", metadata_write_status="written"
    )
    assert contract["output_contract_ok"] is False
    assert "output_file_empty" in contract["output_contract_warnings"]

    directory = tmp_path / "not-an-artifact.png"
    directory.mkdir()
    contract = output_finalization_contract(
        str(directory), str(metadata), media_type="image", metadata_write_status="written"
    )
    assert contract["output_contract_ok"] is False
    assert "output_not_regular_file" in contract["output_contract_warnings"]


def test_known_image_signature_is_accepted(tmp_path: Path) -> None:
    output = tmp_path / "plate.png"
    output.write_bytes(b"\x89PNG\r\n\x1a\n" + b"payload")
    metadata = tmp_path / "plate.json"
    metadata.write_text("{}", encoding="utf-8")

    contract = output_finalization_contract(
        str(output), str(metadata), media_type="image", metadata_write_status="written"
    )
    assert contract["output_contract_ok"] is True
    assert contract["output_media_valid"] is True


def test_invalid_declared_contract_cannot_complete_job() -> None:
    job = _running_job("invalid-artifact")
    complete_job(
        job,
        {
            "output_contract_version": 1,
            "output_contract_ok": False,
            "output_contract_warnings": ["output_file_empty"],
            "output": "plate.png",
        },
    )
    assert job.state is JobState.FAILED
    assert job.result is None
    assert job.error is not None
    assert job.error.code == "output_contract_failed"

    legacy = _running_job("non-artifact-command")
    complete_job(legacy, {"task_type": "noop", "output": None})
    assert legacy.state is JobState.COMPLETED
