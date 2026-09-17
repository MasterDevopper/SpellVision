"""The harness that produces the rows, and the six disciplines it exists to enforce.

Not a live render -- this covers the row-building and the arm sequencing, which is where every one
of the published A/B's defects actually lived. Each test below names the measured failure it
prevents, because the harness's rules are not general research hygiene; they are this box's history.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "scripts" / "dev"))

import measure_optimizations as harness  # noqa: E402
import optimization_levers as levers  # noqa: E402


def _restart_reply(*argv: str, ok: bool = True) -> dict:
    return {"type": "comfy_runtime_ack", "ok": ok, "argv": ["python", "main.py", *argv]}


def _result(seconds: float, **kwargs) -> harness.RunResult:
    return harness.RunResult(
        seconds=seconds,
        dest=kwargs.get("dest", "C:/out/a.png"),
        job_id=kwargs.get("job_id", "job-1"),
        peak_vram_gb=kwargs.get("peak_vram_gb"),
        quality_values=kwargs.get("quality_values", {"black_fraction": 0.01}),
    )


def _provenance(backend: str = "sage", **overrides) -> dict:
    block = {"attention_backend": backend, "fast_flags": [], "dynamic_vram": True,
             "reserve_vram_gb": None, "comfy_argv": ["main.py"]}
    block.update(overrides)
    return block


CELL = harness.Cell(family="krea2", mode="t2i", lever="sage_attention")


# --- discipline 1: vary the seed every run ------------------------------------------------------


def test_every_run_of_a_cell_gets_a_different_seed() -> None:
    """ComfyUI's node cache returns a cached result for an identical prompt. The recorded trap on
    this project is a "12.1 s / 23.62 GB" that was a cache hit -- and it was a re-submit that
    changed only the output filename, so a fresh filename is not enough."""
    runs = harness.runs_for_cell()
    seeds = [run.seed for run in runs]
    assert len(set(seeds)) == len(seeds)


def test_two_cells_do_not_share_a_seed_sequence() -> None:
    assert [r.seed for r in harness.runs_for_cell()] != [r.seed for r in harness.runs_for_cell()]


def test_a_seed_is_inside_comfys_accepted_range() -> None:
    for run in harness.runs_for_cell():
        assert 0 <= run.seed <= harness.MAX_SEED


# --- discipline 2: discard the first run of every configuration ---------------------------------


def test_a_cell_is_three_runs_one_discarded_and_two_timed() -> None:
    """159.27 s cold against 120.72 s warm is the SAME configuration. The first run is recorded,
    marked cold, and never compared."""
    runs = harness.runs_for_cell()
    assert [run.warm for run in runs] == [False, True, True]


def test_the_cold_run_becomes_its_own_row_and_the_warm_runs_one_row() -> None:
    rows = harness.build_rows(
        CELL,
        harness.ArmStep(name="sage", arm={"attention": "sage"}, cells=(CELL,)),
        results=[_result(159.27), _result(120.72), _result(122.10)],
        provenance=_provenance(),
        baseline=harness.Baseline(mean=124.01, reserve_vram_gb=None),
        verification=harness.ArmVerification(ok=True, reason="", observed={}),
    )
    cold, warm = rows
    assert cold["warm"] is False and cold["seconds"] == [159.27]
    assert warm["warm"] is True and warm["seconds"] == [120.72, 122.10]


def test_the_cold_row_is_recorded_rather_than_thrown_away() -> None:
    """The archive's third arm was thrown away by being un-mentioned, not by being deleted. A
    discarded run that is not written down is how a 32% spread stays invisible."""
    rows = harness.build_rows(
        CELL,
        harness.ArmStep(name="sage", arm={"attention": "sage"}, cells=(CELL,)),
        results=[_result(159.27), _result(120.72), _result(122.10)],
        provenance=_provenance(),
        baseline=harness.Baseline(mean=124.01, reserve_vram_gb=None),
        verification=harness.ArmVerification(ok=True, reason="", observed={}),
    )
    assert rows[0]["excluded_from_delta"] is True
    assert rows[0]["delta_pct"] is None


# --- discipline 3: read the arm back from the restart reply -------------------------------------


def test_a_matching_argv_verifies_the_arm() -> None:
    check = harness.verify_arm({"attention": "sage"}, _restart_reply("--use-sage-attention"))
    assert check.ok is True
    assert check.observed["attention_backend"] == "sage"


def test_an_argv_that_does_not_match_the_requested_arm_is_refused() -> None:
    """THE plant. ComfyUI was running with sage this morning, died, was relaunched, and came back on
    SDPA. A request for an arm is not evidence the arm took."""
    check = harness.verify_arm(
        {"attention": "sage"}, _restart_reply("--use-pytorch-cross-attention")
    )
    assert check.ok is False
    assert "sage" in check.reason and "sdpa" in check.reason


def test_an_unverified_arm_marks_the_row_and_excludes_it() -> None:
    rows = harness.build_rows(
        CELL,
        harness.ArmStep(name="sage", arm={"attention": "sage"}, cells=(CELL,)),
        results=[_result(159.27), _result(120.72), _result(122.10)],
        provenance=_provenance(backend="sdpa"),
        baseline=harness.Baseline(mean=124.01, reserve_vram_gb=None),
        verification=harness.verify_arm(
            {"attention": "sage"}, _restart_reply("--use-pytorch-cross-attention")
        ),
    )
    warm = rows[-1]
    assert warm["excluded_from_delta"] is True
    assert warm["delta_pct"] is None
    assert any("arm" in reason for reason in warm["exclusions"])
    assert warm["arm_verified"] is False


def test_a_restart_reply_with_no_argv_cannot_verify_anything() -> None:
    check = harness.verify_arm({"attention": "sage"}, {"ok": True})
    assert check.ok is False
    assert "argv" in check.reason


def test_a_failed_restart_is_not_a_verified_arm() -> None:
    check = harness.verify_arm({"attention": "sage"}, _restart_reply("--use-sage-attention", ok=False))
    assert check.ok is False


@pytest.mark.parametrize(
    "arm,argv,ok",
    [
        ({"fast": ["fp16_accumulation"]}, ("--fast", "fp16_accumulation"), True),
        ({"fast": ["fp16_accumulation"]}, ("--fast", "fp8_matrix_mult"), False),
        ({"fast": ["fp16_accumulation"]}, (), False),
        ({"dynamic_vram": False}, ("--disable-dynamic-vram",), True),
        ({"dynamic_vram": False}, (), False),
        ({"vram_headroom": 22.0}, ("--reserve-vram", "22"), True),
        ({"vram_headroom": 22.0}, ("--reserve-vram", "16"), False),
        ({"vram_headroom": 22.0}, (), False),
    ],
)
def test_every_arm_axis_is_read_back_not_assumed(arm: dict, argv: tuple, ok: bool) -> None:
    assert harness.verify_arm(arm, _restart_reply(*argv)).ok is ok


# --- discipline 4: memory is only reported at a fixed reserve -----------------------------------


def test_an_open_budget_row_says_its_peak_is_not_comparable() -> None:
    rows = harness.build_rows(
        CELL,
        harness.ArmStep(name="sage", arm={"attention": "sage"}, cells=(CELL,)),
        results=[_result(159.27), _result(120.72, peak_vram_gb=30.9), _result(122.1, peak_vram_gb=31.0)],
        provenance=_provenance(reserve_vram_gb=None),
        baseline=harness.Baseline(mean=124.01, reserve_vram_gb=None),
        verification=harness.ArmVerification(ok=True, reason="", observed={}),
    )
    memory = rows[-1]["memory"]
    assert memory["comparable"] is False
    assert "reserve-vram" in memory["reason"]


def test_a_fixed_reserve_on_both_arms_makes_the_peak_comparable() -> None:
    rows = harness.build_rows(
        CELL,
        harness.ArmStep(name="sage", arm={"attention": "sage"}, cells=(CELL,)),
        results=[_result(159.27), _result(120.72, peak_vram_gb=11.47), _result(122.1, peak_vram_gb=11.5)],
        provenance=_provenance(reserve_vram_gb=22.0),
        baseline=harness.Baseline(mean=124.01, reserve_vram_gb=22.0),
        verification=harness.ArmVerification(ok=True, reason="", observed={}),
    )
    assert rows[-1]["memory"]["comparable"] is True
    assert rows[-1]["memory"]["peak_vram_gb"] == pytest.approx(11.5)


# --- discipline 5: every row carries a quality guard --------------------------------------------


def test_every_row_names_the_guards_its_lever_and_mode_require() -> None:
    rows = harness.build_rows(
        harness.Cell(family="wan22_fp8", mode="i2v", lever="sage_attention"),
        harness.ArmStep(name="sage", arm={"attention": "sage"}, cells=()),
        results=[_result(20.0), _result(21.0), _result(22.0)],
        provenance=_provenance(),
        baseline=harness.Baseline(mean=25.0, reserve_vram_gb=None),
        verification=harness.ArmVerification(ok=True, reason="", observed={}),
    )
    guards = rows[-1]["quality"]["guards"]
    assert "black_frame" in guards and "frame0_mae" in guards


def test_a_black_output_fails_the_guard_and_excludes_the_row() -> None:
    """SageAttention's documented failure mode is attention overflow producing black frames. A
    lever that is faster and wrong is not a win."""
    verdict = harness.quality_verdict(("black_frame",), {"black_fraction": 1.0})
    assert verdict["status"] == "fail"


def test_a_keyframe_that_drifted_fails_the_i2v_guard() -> None:
    assert harness.quality_verdict(("frame0_mae",), {"frame0_mae": 40.0})["status"] == "fail"
    assert harness.quality_verdict(("frame0_mae",), {"frame0_mae": 5.19})["status"] == "pass"


def test_a_guard_with_no_measurement_is_not_silently_a_pass() -> None:
    """A guard that reports "pass" because nothing measured it is worse than no guard: it makes the
    row look checked."""
    verdict = harness.quality_verdict(("black_frame",), {})
    assert verdict["status"] == "not_measured"


def test_an_unmeasured_guard_excludes_the_row_from_deltas() -> None:
    rows = harness.build_rows(
        CELL,
        harness.ArmStep(name="sage", arm={"attention": "sage"}, cells=(CELL,)),
        results=[_result(159.27, quality_values={}), _result(120.7, quality_values={}),
                 _result(122.1, quality_values={})],
        provenance=_provenance(),
        baseline=harness.Baseline(mean=124.01, reserve_vram_gb=None),
        verification=harness.ArmVerification(ok=True, reason="", observed={}),
    )
    assert rows[-1]["excluded_from_delta"] is True
    assert any("quality" in reason for reason in rows[-1]["exclusions"])


# --- the matrix and the arm order ---------------------------------------------------------------


def test_the_baseline_arm_runs_first() -> None:
    """Every other row needs baseline_mean for its own family and mode, and baseline_mean travels
    with the row rather than being looked up later."""
    steps = harness.arm_sequence(harness.build_matrix())
    assert steps[0].name == levers.BASELINE_LEVER.id


def test_one_restart_per_arm_not_one_per_cell() -> None:
    """A restart is minutes. Grouping the cells of one arm is the difference between a matrix that
    finishes overnight and one that does not."""
    steps = harness.arm_sequence(harness.build_matrix())
    assert len({step.name for step in steps}) == len(steps)
    sage = next(step for step in steps if step.name == "sage_attention")
    assert len(sage.cells) > 1


def test_a_graph_lever_rides_in_the_baseline_arm() -> None:
    """VAEDecodeTiled changes the graph, not the launch. Restarting for it would measure a restart."""
    steps = harness.arm_sequence(harness.build_matrix())
    baseline = steps[0]
    assert any(cell.lever == "vae_tiling" for cell in baseline.cells)


def test_a_blocked_lever_never_enters_the_matrix() -> None:
    """ck_int8_attention would resolve to automatic selection and produce a row labelled ck that did
    not run ck."""
    measured = {cell.lever for cell in harness.build_matrix()}
    assert "ck_int8_attention" not in measured
    assert "easycache" not in measured


def test_a_family_scoped_lever_only_appears_on_its_families() -> None:
    """--fast fp8_matrix_mult is inert on a bf16 checkpoint, so a cell for it would report the
    noise of an unchanged configuration as a delta."""
    families = {cell.family for cell in harness.build_matrix() if cell.lever == "fast_fp8_matrix_mult"}
    assert families == {"wan22_fp8"}


def test_every_family_gets_a_baseline_cell() -> None:
    baseline_cells = {(c.family, c.mode) for c in harness.build_matrix() if c.lever == levers.BASELINE_LEVER.id}
    expected = {(family, mode) for family, modes in levers.DEFAULT_FAMILIES.items() for mode in modes}
    assert baseline_cells == expected


def test_the_matrix_can_be_narrowed_to_named_families_and_levers() -> None:
    cells = harness.build_matrix(families=("krea2",), lever_ids=("sage_attention",))
    assert {c.family for c in cells} == {"krea2"}
    assert {c.lever for c in cells} == {"sdpa_baseline", "sage_attention"}, (
        "narrowing to one lever must still measure the baseline it is compared against"
    )


# --- the dry run ---------------------------------------------------------------------------------


def test_the_dry_run_prints_the_matrix_and_the_arm_order_without_rendering(capsys) -> None:
    assert harness.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "sdpa_baseline" in out and "sage_attention" in out
    assert "restart" in out.lower()
    assert "ck_int8_attention" in out, "a withheld lever has to be visible, with its reason"
    assert "nvfp4" in out, "the cuts are part of the answer, not an omission from it"


def test_the_dry_run_says_which_cells_have_no_request_template(capsys) -> None:
    """The harness will not invent a render request. A cell with no template is reported, not
    quietly skipped -- Task 5 needs to know what it is about to not measure."""
    harness.main(["--dry-run"])
    out = capsys.readouterr().out
    assert "request template" in out.lower()


def test_the_dry_run_never_touches_the_worker(monkeypatch) -> None:
    """The owner's stack is on this ComfyUI. A dry run that restarts it is not a dry run."""
    def explode(*_args, **_kwargs):
        raise AssertionError("--dry-run must not open a socket")

    monkeypatch.setattr(harness.link, "request", explode)
    assert harness.main(["--dry-run"]) == 0


# --- discipline 7: give the stack back -----------------------------------------------------------
#
# This harness restarts a ComfyUI it does not own. Before this discipline, nothing restored it: the
# harness left the owner's stack in whatever arm ran last, and an interrupted run -- their own
# Ctrl+C, the likeliest interruption there is -- stranded it in an arbitrary one. Every test here
# uses a fake urllib opener for the probe and a monkeypatched harness.link.restart_into_arm for the
# restart -- no socket, real or fake-over-TCP, is ever opened.


class _FakeProbeResponse(io.BytesIO):
    status = 200


class _FakeProbeOpener:
    """Stands in for urllib against ComfyUI's own /system_stats -- never a real socket."""

    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def open(self, request, timeout=None):  # noqa: ARG002 -- signature matches urllib's opener
        return _FakeProbeResponse(json.dumps(self.payload).encode("utf-8"))


def _system_stats(argv: list[str]) -> dict:
    return {
        "system": {
            "comfyui_version": "0.34.0",
            "pytorch_version": "2.10.0+cu128",
            "python_version": "3.12.7",
            "argv": list(argv),
            "comfy_package_versions": [],
        }
    }


def _ack(*argv: str, ok: bool = True, **extra) -> dict:
    reply = {"type": "comfy_runtime_ack", "ok": ok, "argv": ["main.py", *argv]}
    reply.update(extra)
    return reply


def test_the_starting_state_is_captured_before_any_restart() -> None:
    """The probe reads the RUNNING process -- the same evidence verify_arm trusts -- not what a
    launch script intended."""
    state = harness.capture_starting_state(
        opener=_FakeProbeOpener(_system_stats(["main.py", "--use-sage-attention"]))
    )
    assert state.probe["attention_backend"] == "sage"
    assert state.restore_arm["attention"] == "sage"
    assert "attention" not in state.unreproducible


def test_no_attention_flag_at_all_is_not_the_same_as_pinning_sdpa() -> None:
    """The one named subtlety: a bare launch that lands on SDPA because nothing was installed to
    pick sage is not evidence SDPA was asked for. {"attention": "sdpa"} PINS it explicitly
    (comfy_launch_policy.arm_args); a restore that cannot tell the difference must say so."""
    state = harness.capture_starting_state(
        opener=_FakeProbeOpener(_system_stats(["main.py", "--listen", "127.0.0.1"]))
    )
    assert state.probe["attention_backend"] == "sdpa"
    assert "attention" not in state.restore_arm
    assert "attention" in state.unreproducible


def test_restore_runs_on_normal_completion(monkeypatch) -> None:
    calls = []

    def fake_restart(arm, **_kwargs):
        calls.append(arm)
        return _ack("--use-sage-attention")

    monkeypatch.setattr(harness.link, "restart_into_arm", fake_restart)
    ran = []
    result = harness.run_arms_with_restore(
        ["arm-a", "arm-b"],
        ran.append,
        probe_kwargs={"opener": _FakeProbeOpener(_system_stats(["main.py", "--use-sage-attention"]))},
        printer=lambda _line: None,
    )
    assert ran == ["arm-a", "arm-b"]
    assert calls == [{"attention": "sage", "dynamic_vram": True}]
    assert result.attempted is True and result.ok is True


def test_restore_runs_when_the_arm_loop_raises(monkeypatch) -> None:
    """An exception mid-matrix must not strand the stack in whatever arm was running when it blew
    up."""
    calls = []
    monkeypatch.setattr(
        harness.link, "restart_into_arm",
        lambda arm, **_kw: calls.append(arm) or _ack("--use-sage-attention"),
    )

    def boom(_step):
        raise RuntimeError("render blew up")

    with pytest.raises(RuntimeError, match="render blew up"):
        harness.run_arms_with_restore(
            ["arm-a"], boom,
            probe_kwargs={"opener": _FakeProbeOpener(_system_stats(["main.py", "--use-sage-attention"]))},
            printer=lambda _line: None,
        )
    assert calls == [{"attention": "sage", "dynamic_vram": True}]


def test_restore_runs_on_keyboard_interrupt(monkeypatch) -> None:
    """The operator's own Ctrl+C is the likeliest interruption there is, and exactly when stranding
    the stack would be worst."""
    calls = []
    monkeypatch.setattr(
        harness.link, "restart_into_arm",
        lambda arm, **_kw: calls.append(arm) or _ack("--use-sage-attention"),
    )

    def interrupt(_step):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        harness.run_arms_with_restore(
            ["arm-a"], interrupt,
            probe_kwargs={"opener": _FakeProbeOpener(_system_stats(["main.py", "--use-sage-attention"]))},
            printer=lambda _line: None,
        )
    assert calls == [{"attention": "sage", "dynamic_vram": True}]


def test_a_failed_restore_is_reported_not_swallowed(monkeypatch) -> None:
    """A silent failed restore is worse than no restore -- the operator would believe the stack is
    back when it is not."""
    monkeypatch.setattr(
        harness.link, "restart_into_arm",
        lambda arm, **_kw: _ack(
            "--use-pytorch-cross-attention", ok=False, error="comfy would not come back up",
        ),
    )
    printed = []
    result = harness.run_arms_with_restore(
        ["arm-a"], lambda _step: None,
        probe_kwargs={"opener": _FakeProbeOpener(_system_stats(["main.py", "--use-sage-attention"]))},
        printer=printed.append,
    )
    assert result.attempted is True and result.ok is False
    assert "comfy would not come back up" in result.reason
    assert any("FAILED" in line for line in printed)


def test_a_restore_transport_error_does_not_mask_the_original_exception(monkeypatch) -> None:
    """restore_starting_state must catch its own failure rather than let it replace whatever
    exception sent the harness to `finally` in the first place -- two different problems must not
    collapse into one confusing traceback."""
    def blow_up(*_args, **_kwargs):
        raise OSError("socket gone")

    monkeypatch.setattr(harness.link, "restart_into_arm", blow_up)
    printed = []

    def boom(_step):
        raise RuntimeError("render blew up")

    with pytest.raises(RuntimeError, match="render blew up"):
        harness.run_arms_with_restore(
            ["arm-a"], boom,
            probe_kwargs={"opener": _FakeProbeOpener(_system_stats(["main.py", "--use-sage-attention"]))},
            printer=printed.append,
        )
    assert any("FAILED" in line and "socket gone" in line for line in printed)


def test_the_starting_state_is_printed_before_the_restore(monkeypatch) -> None:
    """So the operator can see, before anything restarts, what this run will be returned to."""
    monkeypatch.setattr(
        harness.link, "restart_into_arm",
        lambda arm, **_kw: _ack("--use-sage-attention"),
    )
    printed = []
    harness.run_arms_with_restore(
        ["arm-a"], lambda _step: None,
        probe_kwargs={"opener": _FakeProbeOpener(_system_stats(["main.py", "--use-sage-attention"]))},
        printer=printed.append,
    )
    joined = "\n".join(printed)
    assert joined.index("STARTING STATE") < joined.index("RESTORE")


def test_a_successful_restore_still_names_what_it_could_not_reproduce() -> None:
    """A restore that claims fidelity it did not perform is worse than one that admits the gap."""
    state = harness.capture_starting_state(opener=_FakeProbeOpener(_system_stats(["main.py"])))
    assert "attention" in state.unreproducible
    text = harness.describe_restore(
        harness.RestoreResult(attempted=True, ok=True, reason="", starting=state)
    )
    assert "attention" in text and "could not be reproduced" in text


def test_when_nothing_could_be_probed_the_restore_is_not_attempted(monkeypatch) -> None:
    """No starting state means no honest claim about what "restored" would even mean -- refuse
    rather than restart into a guess."""
    def must_not_restart(*_args, **_kwargs):
        raise AssertionError("must not restart when nothing was captured to restore to")

    monkeypatch.setattr(harness.link, "restart_into_arm", must_not_restart)
    printed = []
    result = harness.run_arms_with_restore(
        ["arm-a"], lambda _step: None,
        probe_kwargs={"opener": _FakeProbeOpener({"system": {}})},
        printer=printed.append,
    )
    assert result.attempted is False and result.ok is False
    assert any("NOT ATTEMPTED" in line for line in printed)
