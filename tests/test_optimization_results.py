"""The ledger that holds an optimization measurement, and the four rules it exists to enforce.

This project published an A/B -- SageAttention 120.72 s against SDPA 124.01 s, about 3%. Since
then, three things came out of this box:

* ``runtime/state/job_archive.json`` holds a THIRD arm nobody mentioned,
  ``t4_sage_queue_3d2236390c95`` at **159.27 s**, same seed, same steps, same size, fifteen minutes
  before the quoted sage run. The real numbers are 159.27 / 120.72 / 124.01, and the published gap
  is smaller than the variance between two runs of the same arm.
* The arms were distinguishable only because a human typed ``t4_sage`` and ``t4_sdpa`` into two
  output filenames. Nothing in the data said which build produced which number.
* ComfyUI was running with sage, died, was relaunched, and came back on SDPA silently.

So a single timing is not a measurement, an asserted arm is not a read arm, and the first run of a
configuration is not comparable to the second. Each of those is a rule below, and each rule is here
because a published number on this project already violated it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

import optimization_commands  # noqa: E402
import optimization_levers as levers  # noqa: E402
import optimization_provenance  # noqa: E402
import optimization_results as ledger  # noqa: E402


def _provenance(backend: str = "sage", **overrides) -> dict:
    block = {
        "comfy_version": "0.34.0",
        "comfy_argv": ["main.py", "--use-sage-attention"],
        "attention_backend": backend,
        "fast_flags": [],
        "dynamic_vram": True,
        "reserve_vram_gb": None,
        "torch": "2.10.0+cu128",
        "packages": {"sageattention": True},
    }
    block.update(overrides)
    return block


def _row(**overrides) -> dict:
    row = {
        "family": "krea2",
        "mode": "t2i",
        "lever": "sage_attention",
        "arm": "sage",
        "seconds": [120.72, 122.10],
        "baseline_mean": 124.01,
        "warm": True,
        "quality": {"guards": ["black_frame"], "status": "pass", "values": {}},
        "provenance": _provenance(),
        "dest": "C:/out/a.png",
        "job_id": "job-1",
    }
    row.update(overrides)
    return row


@pytest.fixture()
def ledger_path(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "optimization_results.jsonl"
    monkeypatch.setattr(ledger, "_LEDGER_PATH_OVERRIDE", path)
    # The command probes the RUNNING ComfyUI for the panel's active column. That is a read-only
    # GET /system_stats, but a unit test whose answer depends on whether a render box happens to be
    # up is not a unit test -- and on a box that IS up it would also make the suite wait on a
    # socket. Stub it; the probe has its own tests in test_optimization_provenance.py.
    monkeypatch.setattr(optimization_provenance, "probe", lambda *a, **k: _provenance())
    return path


# --- rule 1: seconds is a list, never a scalar ------------------------------------------------


def test_a_scalar_seconds_is_refused() -> None:
    """A single timing is not a measurement. The published A/B was three scalars, and two of them
    were the same configuration."""
    with pytest.raises(ValueError, match="seconds"):
        ledger.normalize_row(_row(seconds=120.72))


def test_one_timing_is_recorded_but_never_compared() -> None:
    """Refusing to record it would lose the run; comparing it would repeat the published mistake."""
    row = ledger.normalize_row(_row(seconds=[120.72]))
    assert row["mean"] == pytest.approx(120.72)
    assert row["excluded_from_delta"] is True
    assert row["delta_pct"] is None
    assert any("one timed run" in reason for reason in row["exclusions"])


def test_the_mean_is_derived_not_accepted() -> None:
    """A caller-supplied mean is a second source of truth for the same fact."""
    row = ledger.normalize_row(_row(seconds=[100.0, 110.0], mean=1.0))
    assert row["mean"] == pytest.approx(105.0)


# --- rule 2: warm is explicit -------------------------------------------------------------------


def test_warm_must_be_stated() -> None:
    """159.27 against 120.72 is the SAME configuration, cold and warm. A row that does not say
    which one it is cannot be read."""
    missing = _row()
    missing.pop("warm")
    with pytest.raises(ValueError, match="warm"):
        ledger.normalize_row(missing)


def test_a_cold_row_is_recorded_and_excluded() -> None:
    row = ledger.normalize_row(_row(warm=False))
    assert row["excluded_from_delta"] is True
    assert row["delta_pct"] is None
    assert any("cold" in reason for reason in row["exclusions"])


# --- rule 3: baseline_mean travels with the row -------------------------------------------------


def test_the_delta_is_computed_from_the_rows_own_baseline() -> None:
    row = ledger.normalize_row(_row(seconds=[120.0, 122.0], baseline_mean=124.0))
    assert row["delta_pct"] == pytest.approx((121.0 - 124.0) / 124.0 * 100.0)


def test_a_row_without_a_baseline_has_no_delta() -> None:
    """A baseline row is the reference, not a comparison. It is recorded and carries no delta,
    rather than borrowing a number from another session or another build."""
    row = ledger.normalize_row(_row(lever="sdpa_baseline", arm="baseline", baseline_mean=None))
    assert row["delta_pct"] is None
    assert row["excluded_from_delta"] is False


def test_the_ledger_never_looks_up_a_baseline_from_another_row(ledger_path) -> None:
    """The whole point of carrying it on the row: reading the ledger cannot resurrect a baseline
    from a different build."""
    ledger.append(_row(lever="sdpa_baseline", arm="baseline", baseline_mean=None, seconds=[124.0, 124.5]))
    ledger.append(_row(baseline_mean=None))
    rows = ledger.read()
    assert [r["delta_pct"] for r in rows] == [None, None]


# --- rule 4: a row whose arm could not be read is recorded and excluded --------------------------


def test_unknown_provenance_is_recorded_and_excluded_from_deltas() -> None:
    """ComfyUI came back on SDPA silently this morning. The harness must be able to say "this ran,
    and I cannot tell you on what" -- and that row must not produce a percentage."""
    row = ledger.normalize_row(_row(provenance=_provenance(backend="unknown")))
    assert row["excluded_from_delta"] is True
    assert row["delta_pct"] is None
    assert any("unknown" in reason for reason in row["exclusions"])


def test_a_missing_provenance_block_is_the_same_as_an_unknown_one() -> None:
    row = ledger.normalize_row(_row(provenance={}))
    assert row["excluded_from_delta"] is True
    assert row["delta_pct"] is None


def test_a_caller_supplied_exclusion_survives_normalization() -> None:
    """The harness excludes a row whose restart argv did not match the arm it asked for. The ledger
    must not overwrite that with its own verdict."""
    row = ledger.normalize_row(_row(exclusions=["arm not verified: asked sage, argv says sdpa"]))
    assert row["excluded_from_delta"] is True
    assert row["delta_pct"] is None
    assert row["exclusions"] == ["arm not verified: asked sage, argv says sdpa"]


def test_a_failed_quality_guard_excludes_the_row() -> None:
    """A lever that is faster and wrong is not a win."""
    row = ledger.normalize_row(
        _row(quality={"guards": ["black_frame"], "status": "fail", "values": {"black_fraction": 1.0}})
    )
    assert row["excluded_from_delta"] is True
    assert any("quality" in reason for reason in row["exclusions"])


# --- the required fields ------------------------------------------------------------------------


@pytest.mark.parametrize("field", ["family", "mode", "lever", "arm"])
def test_a_row_must_say_what_it_measured(field: str) -> None:
    row = _row()
    row.pop(field)
    with pytest.raises(ValueError, match=field):
        ledger.normalize_row(row)


def test_a_row_must_carry_a_quality_guard() -> None:
    """Seconds alone cannot distinguish a win from a faster wrong answer."""
    row = _row()
    row.pop("quality")
    with pytest.raises(ValueError, match="quality"):
        ledger.normalize_row(row)


def test_memory_is_only_comparable_at_a_fixed_reserve() -> None:
    """DynamicVRAM expands to fill what is available, so a peak measures availability, not need."""
    open_budget = ledger.normalize_row(_row(memory={"peak_vram_gb": 30.9}))
    assert open_budget["memory"]["comparable"] is False
    assert "reserve" in open_budget["memory"]["reason"]

    fixed = ledger.normalize_row(
        _row(
            provenance=_provenance(reserve_vram_gb=22.0),
            memory={"peak_vram_gb": 11.47, "baseline_reserve_vram_gb": 22.0},
        )
    )
    assert fixed["memory"]["comparable"] is True


def test_memory_at_a_different_reserve_than_the_baseline_is_not_comparable() -> None:
    row = ledger.normalize_row(
        _row(
            provenance=_provenance(reserve_vram_gb=22.0),
            memory={"peak_vram_gb": 11.47, "baseline_reserve_vram_gb": 16.0},
        )
    )
    assert row["memory"]["comparable"] is False


# --- append and read ----------------------------------------------------------------------------


def test_append_writes_one_json_line_per_row(ledger_path) -> None:
    ledger.append(_row())
    ledger.append(_row(lever="fast_fp16_accumulation", arm="fast_fp16_accumulation"))
    lines = ledger_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["lever"] == "sage_attention"


def test_append_normalizes_before_writing(ledger_path) -> None:
    """The file is the evidence. A delta the rules forbid must not be able to reach it even if a
    caller computed one."""
    ledger.append(_row(provenance=_provenance(backend="unknown"), delta_pct=-99.0))
    assert json.loads(ledger_path.read_text(encoding="utf-8").strip())["delta_pct"] is None


def test_read_returns_nothing_when_the_ledger_does_not_exist(ledger_path) -> None:
    assert ledger.read() == []


def test_read_limit_returns_the_newest_rows(ledger_path) -> None:
    for index in range(5):
        ledger.append(_row(job_id=f"job-{index}"))
    assert [r["job_id"] for r in ledger.read(limit=2)] == ["job-3", "job-4"]


def test_a_corrupt_line_does_not_lose_the_rest(ledger_path) -> None:
    ledger.append(_row(job_id="good-1"))
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")
    ledger.append(_row(job_id="good-2"))
    assert [r["job_id"] for r in ledger.read()] == ["good-1", "good-2"]


def test_a_recorded_at_stamp_is_added_when_absent(ledger_path) -> None:
    ledger.append(_row())
    assert ledger.read()[0]["recorded_at"]


# --- the lever catalogue ------------------------------------------------------------------------


def test_every_cut_lever_states_why_it_was_cut() -> None:
    """Task 5 publishes these. A cut with no reason is re-litigated every wave."""
    assert levers.CUT_LEVERS
    for name, reason in levers.CUT_LEVERS.items():
        assert reason.strip(), f"{name} is cut for no stated reason"


@pytest.mark.parametrize(
    "name", ["sage_attention_3", "nvfp4", "flash_attention", "teacache", "magcache", "gguf",
             "radial_sparse_attention"],
)
def test_the_research_cuts_are_all_recorded(name: str) -> None:
    assert name in levers.CUT_LEVERS


def test_a_blocked_lever_is_not_offered_as_runnable() -> None:
    """A lever this stack cannot actually launch must not appear in a matrix that will be run --
    a cell that silently falls back to another arm is the defect this wave exists to remove."""
    runnable = {lever.id for lever in levers.runnable_levers()}
    blocked = {lever.id for lever in levers.ALL_LEVERS if lever.status == "blocked"}
    assert blocked
    assert not (runnable & blocked)
    for lever in levers.ALL_LEVERS:
        if lever.status == "blocked":
            assert lever.blocked_reason.strip(), f"{lever.id} is blocked for no stated reason"


def test_sage_rows_record_which_sageattention_is_installed() -> None:
    """1.0.6 is SA1 Triton kernels; the research says SA2.2 is the first real measurement and its
    wheel is not installed (and installing it in the owner's live venv is not this wave's call).
    A sage number without that version is not interpretable."""
    sage = levers.lever("sage_attention")
    assert levers.SAGEATTENTION_INSTALLED in sage.note


def test_the_baseline_lever_pins_sdpa_explicitly() -> None:
    """A bare launch that happens to land on SDPA is not evidence that SDPA was asked for."""
    assert levers.BASELINE_LEVER.arm == {"attention": "sdpa"}


def test_required_guards_cover_the_documented_failure_modes() -> None:
    assert "black_frame" in levers.required_guards("sage_attention", "t2i")
    assert "frame0_mae" in levers.required_guards("sage_attention", "i2v")
    assert "artefact" in levers.required_guards("fast_fp8_matrix_mult", "t2i")


# --- the worker command -------------------------------------------------------------------------


def test_the_command_returns_rows_families_and_levers(ledger_path) -> None:
    ledger.append(_row())
    ledger.append(_row(family="ltx", mode="t2v", lever="vae_tiling", arm="baseline"))
    reply = optimization_commands.handle_optimization_results_command({})
    assert reply["ok"] is True
    assert reply["type"] == "optimization_results"
    assert len(reply["rows"]) == 2
    assert reply["families"] == ["krea2", "ltx"]
    assert reply["levers"] == ["sage_attention", "vae_tiling"]


def test_the_command_filters_by_family_and_lever(ledger_path) -> None:
    ledger.append(_row())
    ledger.append(_row(family="ltx", mode="t2v", lever="vae_tiling", arm="baseline"))
    assert len(optimization_commands.handle_optimization_results_command({"family": "ltx"})["rows"]) == 1
    assert len(
        optimization_commands.handle_optimization_results_command({"lever": "sage_attention"})["rows"]
    ) == 1


def test_the_command_carries_the_cut_reasons(ledger_path) -> None:
    """So the document Task 5 generates does not have to re-derive them from the research file."""
    reply = optimization_commands.handle_optimization_results_command({})
    assert reply["cut_levers"]["nvfp4"]


def test_the_command_answers_on_an_empty_ledger(ledger_path) -> None:
    reply = optimization_commands.handle_optimization_results_command({})
    assert reply["ok"] is True
    assert reply["rows"] == []


def test_the_reply_carries_every_lever_not_only_the_measured_ones(ledger_path) -> None:
    """The Runtime panel renders one row per catalogue entry.

    Driving it from ``rows`` alone would mean a lever nobody has measured is absent from the table
    entirely -- which reads as "there is no such option" rather than "nobody has timed it", and
    that invisibility is the whole subject of this wave.
    """
    reply = optimization_commands.handle_optimization_results_command({})
    ids = [entry["id"] for entry in reply["catalogue"]]
    assert ids == [lever.id for lever in levers.ALL_LEVERS]
    assert all(entry["label"] for entry in reply["catalogue"])
    blocked = next(e for e in reply["catalogue"] if e["status"] == levers.BLOCKED)
    assert blocked["blocked_reason"], "a blocked lever must carry the reason it cannot be asked for"


def test_the_reply_carries_the_live_arm(ledger_path) -> None:
    """Installed and active are different facts, and only the probe answers the second one."""
    reply = optimization_commands.handle_optimization_results_command({})
    assert reply["provenance"]["attention_backend"] == "sage"
    assert "packages" in reply["provenance"]


def test_a_probe_that_raises_does_not_take_the_ledger_with_it(ledger_path, monkeypatch) -> None:
    """A dead ComfyUI must not make the measurements unreadable, and must not be reported as SDPA.

    ``probe()`` already swallows a failed HTTP read into an honest ``unknown`` block; this covers
    the rarer case where resolving the endpoint itself raises.
    """
    def boom(*args, **kwargs):
        raise RuntimeError("no endpoint")

    monkeypatch.setattr(optimization_provenance, "probe", boom)
    reply = optimization_commands.handle_optimization_results_command({})
    assert reply["ok"] is True
    assert reply["provenance"]["attention_backend"] == "unknown"
    assert "no endpoint" in reply["provenance"]["probe_error"]


def test_the_command_is_classified_and_wired() -> None:
    """USER_FACING since W3 T6: ManagerPage's optimization panel is the route.

    The audience ratchet (tests/test_worker_command_audience.py) is what holds the other half --
    a USER_FACING command with no ``qt_ui/`` call site fails there.
    """
    import worker_command_audience as audience
    import worker_client

    assert "optimization_results" in audience.USER_FACING
    assert "optimization_results" not in audience.DIAGNOSTIC
    payload, _ = worker_client.normalize_worker_message({"type": "optimization_results", "ok": True}, None)
    assert payload["type"] == "optimization_results", (
        "an unregistered wire type arrives as client_warning with ok=False"
    )
