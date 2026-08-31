"""A malformed image request must say what is missing, before anything expensive happens.

These runners read the request with bare subscripts in 33 places. A caller that omitted one field
surfaced as ``KeyError: 'output'`` -- raised deep in the run, after a multi-gigabyte pipeline load
and a full sampling pass, naming neither the caller nor the field in any useful way.

Found exactly that way: two consecutive SDXL measurement runs died on ``'output'`` and then
``'metadata_output'``, one field per attempt, each costing a model load.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from image_runners import REQUIRED_IMAGE_REQUEST_KEYS, require_request_keys  # noqa: E402

COMPLETE = {
    "model": "m.safetensors", "prompt": "a cat", "output": "out.png",
    "metadata_output": "out.json", "width": 1024, "height": 1024,
    "steps": 28, "cfg": 7.0, "seed": 4242,
}


def test_a_complete_request_passes():
    require_request_keys(dict(COMPLETE), "t2i")


@pytest.mark.parametrize("missing", REQUIRED_IMAGE_REQUEST_KEYS)
def test_each_required_field_is_named_when_absent(missing):
    req = {k: v for k, v in COMPLETE.items() if k != missing}
    with pytest.raises(ValueError) as excinfo:
        require_request_keys(req, "t2i")
    assert missing in str(excinfo.value)


def test_every_missing_field_is_reported_at_once():
    """One field per attempt is how this cost two model loads to diagnose."""
    with pytest.raises(ValueError) as excinfo:
        require_request_keys({"model": "m"}, "t2i")
    message = str(excinfo.value)
    for key in ("prompt", "output", "metadata_output", "width", "height", "steps", "cfg", "seed"):
        assert key in message


def test_i2i_additionally_requires_its_input_image():
    with pytest.raises(ValueError, match="input_image"):
        require_request_keys(dict(COMPLETE), "i2i", "input_image")


def test_the_message_names_the_command_and_what_was_present():
    with pytest.raises(ValueError) as excinfo:
        require_request_keys({"model": "m"}, "i2i", "input_image")
    message = str(excinfo.value)
    assert "i2i" in message
    assert "Present: model" in message


def test_a_present_but_falsy_value_is_not_missing():
    """seed 0 and cfg 0.0 are legitimate. Presence is the check, not truthiness -- the or-default
    trap that produced three separate bugs in this codebase already."""
    req = dict(COMPLETE, seed=0, cfg=0.0, steps=0)
    require_request_keys(req, "t2i")


def test_the_guard_runs_after_the_queued_to_starting_transition():
    """Ordering that looks cosmetic and is not.

    The job state machine permits QUEUED -> {STARTING, CANCELLED} only. A raise while the item is
    still QUEUED cannot be recorded as FAILED: the error lands on the queue item but its state
    stays "queued" and it never drains -- a permanently stuck row, which is the documented
    QUEUED-to-terminal bug arriving by a new door.

    Validating one line too early did exactly that to both e2e lifecycle tests. Pinned by source
    order so the guard cannot drift back above the transition.
    """
    from pathlib import Path as _Path

    import image_runners

    source = _Path(image_runners.__file__).read_text(encoding="utf-8", errors="replace")
    for runner in ("def run_t2i(", "def run_i2i("):
        body = source[source.index(runner):]
        transition = body.index("transition_job(job, JobState.STARTING)")
        guard = body.index("require_request_keys(req,")
        assert transition < guard, (
            f"{runner} validates before the STARTING transition; a failure there strands the "
            f"queue item at 'queued' forever"
        )
