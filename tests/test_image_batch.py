"""Cockpit Batch is A1111 batch count: N stills, not one job that ignores the knob."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from request_payload import expand_image_batch, image_batch_count


def test_batch_count_four_expands_t2i_into_four_jobs() -> None:
    jobs = expand_image_batch(
        {"command": "t2i", "batch_count": 4, "seed": 10, "prompt": "goblin"}
    )
    assert len(jobs) == 4
    assert [job["seed"] for job in jobs] == [10, 11, 12, 13]
    assert all(job.get("batch_count") == 1 for job in jobs)
    assert [job["batch_index"] for job in jobs] == [0, 1, 2, 3]


def test_batch_count_four_expands_t2v_into_four_jobs() -> None:
    """T2V Advanced still shows Batch. Four clips must queue as four jobs."""
    jobs = expand_image_batch({"command": "t2v", "batch_count": 4, "seed": 1})
    assert len(jobs) == 4
    assert [job["seed"] for job in jobs] == [1, 2, 3, 4]
    assert all(job.get("batch_count") == 1 for job in jobs)


def test_missing_or_one_is_a_single_job() -> None:
    assert len(expand_image_batch({"command": "t2i"})) == 1
    assert len(expand_image_batch({"command": "i2i", "batch_count": 1})) == 1
    assert image_batch_count({"batch_count": 0}) == 1
    assert image_batch_count({"batch_count": 99}) == 32


def test_enqueue_expands_image_batch() -> None:
    """Worker enqueue used to ignore batch_count. Four stills must become four jobs."""
    text = Path(__file__).resolve().parents[1].joinpath("python", "worker_queue.py").read_text(
        encoding="utf-8"
    )
    enqueue = text.split("def enqueue(self, req", 1)[1].split("def update_from_job", 1)[0]
    assert "expand_image_batch" in enqueue


def test_simple_mode_does_not_send_hidden_batch() -> None:
    """Batch is Advanced-only. A hidden spin holding 4 must not enqueue 4 in Simple."""
    cpp = Path(__file__).resolve().parents[1].joinpath(
        "qt_ui", "ImageGenerationPage.cpp"
    ).read_text(encoding="utf-8")
    start = cpp.index("draft.batchCount")
    line = cpp[start : cpp.index(";", start) + 1]
    assert "advanced_" in line
