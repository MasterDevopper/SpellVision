"""An image on disk must be able to say what sampler produced it.

The sidecar carried steps, cfg and seed but no sampler or scheduler at all, so two renders that
differed only by sampler were indistinguishable after the fact. Found while settling the SDXL
operating-point question: both comparison runs wrote JSON with neither key.

The request and the EFFECT are recorded separately because they can disagree.
``apply_sampler_and_scheduler`` returns applied=False when it cannot map the requested name to a
diffusers scheduler class, and the pipeline then keeps its own default -- writing only the request
would assert a sampler that never ran.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from worker_metadata import build_metadata_payload  # noqa: E402

BASE = dict(
    image_path="out.png", metadata_output="out.json", backend_name="StableDiffusionXLPipeline",
    device="cuda", dtype="float16", detected_pipeline="sdxl", lora_used=False,
    elapsed=3.0, steps_per_sec=9.0,
)


def payload(req, stats):
    return build_metadata_payload(req=req, scheduler_stats=stats, **BASE)


def test_an_applied_sampler_is_recorded_with_the_class_that_ran():
    data = payload({"sampler": "dpmpp_2m", "scheduler": "karras"},
                   {"applied": True, "scheduler_class": "DPMSolverMultistepScheduler"})
    assert data["sampler"] == "dpmpp_2m"
    assert data["scheduler"] == "karras"
    assert data["sampler_applied"] is True
    assert data["scheduler_class"] == "DPMSolverMultistepScheduler"


def test_a_sampler_that_did_not_apply_is_recorded_as_not_applied():
    """The whole point. Live check on a real render: requesting 'not_a_real_sampler' completed
    successfully on the pipeline default and wrote sampler_applied=false, scheduler_class=null."""
    data = payload({"sampler": "not_a_real_sampler", "scheduler": "karras"},
                   {"applied": False, "scheduler_class": None})
    assert data["sampler"] == "not_a_real_sampler"
    assert data["sampler_applied"] is False, "a sampler that never ran must not be asserted as fact"
    assert data["scheduler_class"] is None


def test_no_sampler_requested_records_none_rather_than_an_empty_string():
    data = payload({}, None)
    assert data["sampler"] is None
    assert data["scheduler"] is None
    assert data["sampler_applied"] is False


def test_missing_scheduler_stats_does_not_raise():
    """Callers that predate the parameter must keep working."""
    data = build_metadata_payload(req={"sampler": "euler"}, **BASE)
    assert data["sampler"] == "euler"
    assert data["sampler_applied"] is False


def test_an_unmappable_sampler_is_warned_about_at_runtime(caplog):
    """The sidecar records it durably; this makes it visible while it happens.

    WARNING specifically -- the root logger sits at WARNING in this app, so logging.info would be
    invisible (CLAUDE.md section 4).
    """
    from image_runners import apply_sampler_and_scheduler

    class FakePipe:
        scheduler = type("S", (), {"config": {}})()

    with caplog.at_level("WARNING"):
        stats = apply_sampler_and_scheduler(FakePipe(), {"sampler": "not_a_real_sampler"})

    assert stats["applied"] is False
    assert any("no diffusers scheduler mapping" in r.getMessage() for r in caplog.records)


def test_no_sampler_requested_is_not_warned_about(caplog):
    """Leaving it blank is normal, not a problem to report."""
    from image_runners import apply_sampler_and_scheduler

    class FakePipe:
        scheduler = type("S", (), {"config": {}})()

    with caplog.at_level("WARNING"):
        apply_sampler_and_scheduler(FakePipe(), {})
    assert not [r for r in caplog.records if "scheduler mapping" in r.getMessage()]
