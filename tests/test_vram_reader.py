"""A VRAM number that does not say where it came from is not a measurement.

Ten places read GPU memory and they do not measure the same thing -- torch in the worker process,
an ``nvidia-smi`` subprocess, NVML in Qt, and four result payloads that wrote the literal ``0.0``.

The zeros are the defect. On a native route the weights are in ComfyUI's process, so asking torch in
the worker returns approximately nothing; on the FLUX.3 route the render happens on Black Forest
Labs' hardware and there is no local GPU at all. All three wrote the same zero into
``cuda_allocated_gb``, a field every other route fills with a real measurement, and history rows and
the bottom bar read it. A zero meaning "not measured here" is indistinguishable from one meaning
"used no memory", and it is presented as the latter.

Provenance is not bookkeeping. A number without it cannot be compared against another number without
it -- which is how a cached ComfyUI run reporting "12.1 s / 23.62 GB" ended up in the same table as a
real 30.94 GB peak during the FP8 measurement.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import vram  # noqa: E402
from vram import (  # noqa: E402
    SOURCE_COMFY_STATS,
    SOURCE_REMOTE,
    SOURCE_UNAVAILABLE,
    SOURCE_WORKER_TORCH,
    VramReading,
    comfy_vram,
    headroom_note,
    reading_for,
    remote_vram,
    worker_vram,
)

STATS = {"devices": [{"name": "cuda:0", "vram_total": 34_359_738_368, "vram_free": 31_000_000_000}]}


# --- not measured is None, never zero -------------------------------------------------------------

def test_an_unavailable_reading_reports_none_not_zero() -> None:
    """The whole point. `0.0` was the old answer and it reads as a measurement."""
    payload = VramReading().payload()
    assert payload["cuda_allocated_gb"] is None
    assert payload["cuda_reserved_gb"] is None
    assert payload["vram_source"] == SOURCE_UNAVAILABLE
    assert VramReading().measured is False


def test_a_hosted_render_is_its_own_answer() -> None:
    """FLUX.3 renders on the BFL API. Its old 0.0 was very nearly TRUE -- no local VRAM was used --
    and still useless, because it is the same zero the ComfyUI routes wrote when they had not
    looked. Naming the source separates them."""
    reading = remote_vram()
    assert reading.source == SOURCE_REMOTE
    assert reading.measured is True, "a hosted render IS a known state, not a failed reading"
    assert reading.payload()["cuda_allocated_gb"] is None
    assert "no local GPU" in reading.measures


def test_every_source_describes_itself_in_words() -> None:
    """The payload travels into history and metadata, where the reader is no longer near the code
    that took it."""
    for source in (SOURCE_WORKER_TORCH, SOURCE_COMFY_STATS, SOURCE_REMOTE, SOURCE_UNAVAILABLE):
        described = VramReading(source=source).measures
        assert described and described != source, source


# --- each reader measures its own process ---------------------------------------------------------

def test_the_comfy_reader_uses_comfyuis_own_numbers(monkeypatch) -> None:
    monkeypatch.setattr("comfy_prompt_client._http_get_json", lambda *_a, **_k: STATS)
    reading = comfy_vram("http://127.0.0.1:8188")
    assert reading.source == SOURCE_COMFY_STATS
    assert reading.total_gb == 32.0
    assert reading.free_gb == pytest.approx(28.87, abs=0.01)


def test_the_comfy_reader_invents_no_allocator_figure(monkeypatch) -> None:
    """`total - free` would attribute every other process's memory to this render. ComfyUI does not
    publish a torch allocator figure for our benefit, so those stay None."""
    monkeypatch.setattr("comfy_prompt_client._http_get_json", lambda *_a, **_k: STATS)
    reading = comfy_vram("http://127.0.0.1:8188")
    assert reading.allocated_gb is None and reading.reserved_gb is None
    assert reading.max_allocated_gb is None, (
        "ComfyUI publishes no peak; substituting a current reading would report a much smaller one"
    )


def test_an_unreachable_comfy_is_unavailable_not_zero(monkeypatch, caplog) -> None:
    import logging

    def _boom(*_a, **_k):
        raise OSError("connection refused")

    monkeypatch.setattr("comfy_prompt_client._http_get_json", _boom)
    with caplog.at_level(logging.WARNING):
        reading = comfy_vram("http://127.0.0.1:9999")
    assert reading.source == SOURCE_UNAVAILABLE
    assert any("VRAM reading failed" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("stats", [None, {}, {"devices": []}, {"devices": "nope"}, {"devices": [None]}])
def test_a_malformed_stats_body_is_unavailable(monkeypatch, stats) -> None:
    monkeypatch.setattr("comfy_prompt_client._http_get_json", lambda *_a, **_k: stats)
    assert comfy_vram("http://x").source == SOURCE_UNAVAILABLE


def test_the_route_chooses_its_reader(monkeypatch) -> None:
    monkeypatch.setattr("comfy_prompt_client._http_get_json", lambda *_a, **_k: STATS)
    assert reading_for("http://127.0.0.1:8188").source == SOURCE_COMFY_STATS
    monkeypatch.setattr(vram, "worker_vram", lambda: VramReading(source=SOURCE_WORKER_TORCH))
    assert reading_for(None).source == SOURCE_WORKER_TORCH
    assert reading_for("").source == SOURCE_WORKER_TORCH


def test_a_fallback_still_says_which_process_it_measured(monkeypatch) -> None:
    """Falling back to the worker's view when ComfyUI is unreachable is better than nothing, but
    only because the source field stops anyone comparing the two by accident."""
    monkeypatch.setattr(vram, "comfy_vram", lambda *_a, **_k: VramReading())
    monkeypatch.setattr(vram, "worker_vram", lambda: VramReading(source=SOURCE_WORKER_TORCH,
                                                                free_gb=12.0))
    reading = reading_for("http://127.0.0.1:8188")
    assert reading.source == SOURCE_WORKER_TORCH


def test_the_worker_reader_reports_a_peak() -> None:
    """Every VRAM claim in this repo is about PEAK -- the FP8 comparison was 29.49 against 30.94 GB
    peak, not current -- and the field did not exist in the first version of this reader."""
    reading = worker_vram()
    if not reading.measured:
        pytest.skip("no CUDA on this machine")
    assert reading.max_allocated_gb is not None
    assert reading.total_gb and reading.total_gb > 0


# --- the submit-time note ---------------------------------------------------------------------------

def test_the_submit_note_records_what_was_free() -> None:
    """No route has ever recorded this, so an OOM arrives with no precondition and the first
    question after one has never been answerable."""
    before = VramReading(source=SOURCE_COMFY_STATS, free_gb=30.0, total_gb=32.0)
    note = headroom_note(before)
    assert note["vram_free_at_submit_gb"] == 30.0
    assert note["vram_source_at_submit"] == SOURCE_COMFY_STATS


def test_a_delta_is_only_taken_between_like_sources() -> None:
    """Subtracting the worker's view from ComfyUI's would manufacture a number out of two
    measurements of different processes."""
    before = VramReading(source=SOURCE_COMFY_STATS, free_gb=30.0)
    same = VramReading(source=SOURCE_COMFY_STATS, free_gb=12.0)
    other = VramReading(source=SOURCE_WORKER_TORCH, free_gb=12.0)
    assert headroom_note(before, same)["vram_free_delta_gb"] == 18.0
    assert headroom_note(before, other)["vram_free_delta_gb"] is None


def test_the_note_is_not_a_budget_check() -> None:
    """Deliberately records rather than refuses: a threshold without a measurement behind it is a
    heuristic, and rule 1 does not allow one. This is the measurement that makes a check possible."""
    note = headroom_note(VramReading(source=SOURCE_COMFY_STATS, free_gb=0.1, total_gb=32.0))
    assert "refuse" not in str(note) and "error" not in note


def test_a_job_handle_carries_the_submit_reading() -> None:
    from worker_service_state import ActiveJobHandle, JobRecord

    handle = ActiveJobHandle(job=JobRecord(job_id="j", command="t2v"))
    assert handle.submit_vram == {}
    handle.submit_vram = headroom_note(VramReading(source=SOURCE_REMOTE))
    assert handle.submit_vram["vram_source_at_submit"] == SOURCE_REMOTE


def test_recording_the_reading_never_breaks_a_running_render(monkeypatch, caplog) -> None:
    """It is taken after the submit, on purpose: the render is already running, and a diagnostic
    that could fail it would be worse than no diagnostic."""
    import logging

    import comfy_prompt_client
    from worker_service_state import ActiveJobHandle, JobRecord

    monkeypatch.setattr(vram, "reading_for", lambda *_a, **_k: (_ for _ in ()).throw(OSError("x")))
    handle = ActiveJobHandle(job=JobRecord(job_id="j", command="t2v"))
    with caplog.at_level(logging.WARNING):
        comfy_prompt_client._record_submit_vram(handle, "http://x")
    assert handle.submit_vram == {}


# --- no number escapes without a source ------------------------------------------------------------

def test_no_vram_number_is_written_by_hand() -> None:
    """The sweep owns this tree-wide; asserted here so the rule's subject stays visible in the file
    that explains it. The exemptions are the reader's own torch calls and two monkeypatch stubs."""
    sys.path.insert(0, str(ROOT / "tests"))
    from sweeps import exemptions, rules

    rule = [r for r in rules.ALL_RULES if r.name == "vram-numbers-name-their-source"][0]
    exempt = exemptions.EXEMPT[rule.name]
    unexplained = [str(v) for v in rule.run() if v.site not in exempt]
    assert not unexplained, unexplained
