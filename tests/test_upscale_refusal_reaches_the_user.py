"""A refusal has to survive to the end of the run, or it is not a report.

`emitter.status` writes `job.progress.message`, which the cockpit shows while the job is busy --
and which the *next* status overwrites. A run that says "upscale skipped" mid-flight and then ends
with "Generation complete" beside a normal-looking image has told the user nothing they can act on:
the sentence they needed was on screen for a moment, and the outcome contradicted it.

So the note is kept on the request and applied to the job's TERMINAL message, which the response
parser reads out of `progress.message` and `GenerationStatusController` passes to `routeOutput` as
the caption beside the image.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import image_runners  # noqa: E402
from worker_service_state import JobRecord  # noqa: E402


def _job() -> JobRecord:
    return JobRecord(job_id="job-1", command="t2i")


def test_a_note_reaches_the_terminal_message_and_the_payload() -> None:
    req: dict = {}
    image_runners._note(req, "Upscale skipped: the image is unchanged.")
    job = _job()
    payload: dict = {"ok": True}

    image_runners._apply_generation_notes(req, job, payload)

    assert payload["generation_notes"] == ["Upscale skipped: the image is unchanged."]
    assert "Upscale skipped" in job.progress.message, (
        "the caption beside the finished image is the only place a partial success is still visible"
    )


def test_a_clean_run_says_nothing_extra() -> None:
    """A note channel that fires on every run is noise, and noise is how a real one gets ignored."""
    job = _job()
    before = job.progress.message
    payload: dict = {"ok": True}
    image_runners._apply_generation_notes({}, job, payload)
    assert "generation_notes" not in payload
    assert job.progress.message == before


def test_the_same_note_is_not_repeated() -> None:
    req: dict = {}
    for _ in range(3):
        image_runners._note(req, "Upscale skipped: the image is unchanged.")
    assert req["generation_notes"] == ["Upscale skipped: the image is unchanged."]


def test_a_refused_model_upscale_records_a_note() -> None:
    """The whole path: a model request on a diffusers family with no ESRGAN packages present."""
    import upscale_engine

    req = {
        "upscale_enabled": True,
        "upscale_method": "model",
        "upscale_scale": 2.0,
        "model_family": "sdxl",
    }
    real = upscale_engine._pil_model_path_available
    upscale_engine._pil_model_path_available = lambda: False
    try:
        returned = image_runners.maybe_apply_request_upscale(req, "no/such/file.png")
    finally:
        upscale_engine._pil_model_path_available = real

    assert returned == "no/such/file.png", "the rendered image is kept; only the upscale is refused"
    assert req.get("generation_notes"), "the refusal left no trace the user could ever see"
    assert "Upscale skipped" in req["generation_notes"][0]
