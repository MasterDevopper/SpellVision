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


def test_batch_jobs_do_not_share_one_dest() -> None:
    """N jobs used to copy the same output path, so dest N-1 overwrote dest 0."""
    jobs = expand_image_batch(
        {
            "command": "t2i",
            "batch_count": 3,
            "seed": 1,
            "output": "C:/out/spellvision_render.png",
            "metadata_output": "C:/out/spellvision_render.json",
            "original_output": "C:/out/spellvision_render.png",
        }
    )
    dests = [job["output"] for job in jobs]
    assert len(set(dests)) == 3
    assert dests[0].replace("\\", "/").endswith("spellvision_render.png")
    assert dests[1].replace("\\", "/").endswith("spellvision_render_b01.png")
    assert dests[2].replace("\\", "/").endswith("spellvision_render_b02.png")
    metas = [job["metadata_output"].replace("\\", "/") for job in jobs]
    assert len(set(metas)) == 3
    assert metas[1].endswith("spellvision_render_b01.json")


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


def test_worker_request_forwards_batch_count() -> None:
    """Cockpit batch_count never reached enqueue — WorkerRequestBuilder dropped it."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from cpp_source import definition_body

    body = definition_body("buildWorkerGenerationRequest")
    assert 'QStringLiteral("batch_count")' in body
    assert 'QStringLiteral("extra_models_roots")' in body
    assert 'QStringLiteral("models_root")' in body
    assert 'QStringLiteral("video_stack_mode")' in body
    assert 'QStringLiteral("i2v_source_image")' in body
    assert 'QStringLiteral("video_input_image")' in body
    assert 'QStringLiteral("lora_stack")' in body
    assert 'QStringLiteral("ltx_preferred_output")' in body
    assert 'QStringLiteral("operating_point")' in body


def test_worker_request_forwards_character_reference_keys() -> None:
    """Character sends ipadapter_weight + reference_mode. Allow-list dropped them."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from cpp_source import definition_body

    body = definition_body("buildWorkerGenerationRequest")
    assert 'QStringLiteral("ipadapter_weight")' in body
    assert 'QStringLiteral("reference_mode")' in body


def test_worker_request_forwards_ltx_companion_names() -> None:
    """LTX Advanced Gemma/VAE names never reached two-stage; builder dropped them."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from cpp_source import definition_body

    body = definition_body("buildWorkerGenerationRequest")
    assert 'QStringLiteral("ltx_text_encoder_name")' in body
    assert 'QStringLiteral("ltx_audio_vae_name")' in body
    assert 'QStringLiteral("ltx_text_projection_name")' in body
    assert 'QStringLiteral("ltx_video_vae_name")' in body


def test_worker_request_forwards_embedding_arrays() -> None:
    """+Pos/+Neg arrays never reached the worker. Allow-list dropped them."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from cpp_source import definition_body

    body = definition_body("buildWorkerGenerationRequest")
    assert 'QStringLiteral("positive_embeddings")' in body
    assert 'QStringLiteral("negative_embeddings")' in body


def test_worker_request_t2i_with_still_submits_as_i2i() -> None:
    """T2I with a reference still must become i2i inside the builder or input_image is dropped."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from cpp_source import definition_body

    body = definition_body("buildWorkerGenerationRequest")
    assert 'QStringLiteral("t2i")' in body
    assert 'QStringLiteral("i2i")' in body
    assert "input_image" in body
    # Remap, not just the i2i/i2v copy gate.
    assert 'taskCommand == QStringLiteral("t2i")' in body
