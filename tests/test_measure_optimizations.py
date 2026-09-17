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


# --- the execution loop (Task 5) -----------------------------------------------------------------
#
# Everything above covers the rules a row is held to. These cover the loop that produces the rows:
# restart, read the arm back, render cold-then-twice on fresh seeds, guard, record. Nothing here
# opens a socket -- harness.link.render and harness.link.restart_into_arm are the two fakes, and the
# probe uses the same _FakeProbeOpener the restore tests already use.

import measure_optimizations_run as runner  # noqa: E402
import optimization_results as results_ledger  # noqa: E402


def _argv_for(arm: dict | None) -> list[str]:
    """What ComfyUI would actually be launched with for this arm.

    Built here rather than imported from comfy_launch_policy so the fake cannot drift into agreeing
    with the code under test by construction -- the point of reading argv back is that it is a
    SECOND source.
    """
    argv = ["main.py"]
    arm = arm or {}
    if "attention" in arm:
        argv.append("--use-sage-attention" if arm["attention"] == "sage"
                    else "--use-pytorch-cross-attention")
    if arm.get("fast"):
        argv.append("--fast")
        argv.extend(str(name) for name in arm["fast"])
    if arm.get("dynamic_vram") is False:
        argv.append("--disable-dynamic-vram")
    if "vram_headroom" in arm:
        argv += ["--reserve-vram", str(arm["vram_headroom"])]
    return argv


_FAKE_PROVENANCE = {
    "attention_backend": "sdpa", "fast_flags": [], "dynamic_vram": True, "reserve_vram_gb": None,
    "comfy_version": "0.34.0",
}


def _completed(seconds: float = 10.0, *, dest: str = "", job_id: str = "job-1",
               provenance: dict | None = None) -> dict:
    """A terminal job_update. ``provenance=None`` means "whatever arm is actually running", which
    the rig fills in from the argv it last launched -- the same thing the worker's own
    _optimizations_block probes off the live process."""
    return {
        "type": "job_update", "job_id": job_id, "state": "completed",
        "result": {
            "output": dest,
            "generation_time_sec": seconds,
            "optimizations": dict(provenance) if provenance is not None else None,
        },
    }


def _provenance_of(argv: list[str]) -> dict:
    """What a render launched with this argv would report about itself."""
    import optimization_provenance as probe

    return {
        "attention_backend": probe.attention_from_argv(argv),
        "fast_flags": probe.fast_from_argv(argv),
        "dynamic_vram": probe.dynamic_vram_from_argv(argv),
        "reserve_vram_gb": probe.reserve_vram_from_argv(argv),
        "comfy_version": "0.34.0",
    }


def _failed(message: str = "CUDA out of memory") -> dict:
    return {"type": "job_update", "job_id": "job-x", "state": "failed",
            "error": {"code": "generation_error", "message": message}}


def _narrow_steps() -> list:
    """Two arms, one cell each: the smallest matrix that still has a baseline and a lever."""
    return harness.arm_sequence(
        harness.build_matrix(families=("krea2",), lever_ids=("sage_attention",))
    )


def _requests() -> dict:
    return {"krea2:t2i": {"command": "t2i", "steps": 10,
                          "original_output": "C:/out/plate.png",
                          "original_metadata_output": "C:/out/plate.json"}}


class _Rig:
    """A whole fake run: every render answered from a script, every request captured."""

    def __init__(self, tmp_path, monkeypatch, *, responder=None, restarter=None):
        self.sent: list[dict] = []
        self.rows_seen_at_render: list[int] = []
        self.printed: list[str] = []
        self.arms: list[dict | None] = []
        self._responder = responder or (lambda request, index: _completed(10.0 + index))
        self._restarter = restarter
        self.running: dict = dict(_FAKE_PROVENANCE)

        monkeypatch.setattr(results_ledger, "_LEDGER_PATH_OVERRIDE",
                            tmp_path / "optimization_results.jsonl")
        monkeypatch.setattr(harness.link, "render", self._render)
        monkeypatch.setattr(harness.link, "restart_into_arm", self._restart)
        monkeypatch.setattr(runner, "measure_quality",
                            lambda *_a, **_kw: {"black_fraction": 0.01, "artefact_delta": 0.5})
        self.out_dir = tmp_path / "renders"

    def _render(self, request, **_kwargs):
        self.sent.append(request)
        self.rows_seen_at_render.append(len(results_ledger.read()))
        message = self._responder(request, len(self.sent) - 1)
        result = message.get("result")
        if isinstance(result, dict) and result.get("optimizations") is None:
            result["optimizations"] = dict(self.running)
        return 99.0, message

    def _restart(self, arm, **_kwargs):
        self.arms.append(arm)
        reply = (self._restarter(arm) if self._restarter is not None
                 else {"type": "comfy_runtime_ack", "ok": True, "argv": _argv_for(arm)})
        if reply.get("ok") is not False:
            self.running = _provenance_of(list(reply.get("argv") or []))
        return reply

    def run(self, *, steps=None, requests=None, force=False, artefact_guard=False):
        options = runner.Options(
            requests=_requests() if requests is None else requests,
            out_dir=self.out_dir,
            force=force,
            artefact_guard=artefact_guard,
            probe_kwargs={
                "opener": _FakeProbeOpener(_system_stats(["main.py", "--use-sage-attention"]))
            },
        )
        return runner.run_matrix(steps or _narrow_steps(), options, printer=self.printed.append)

    @property
    def rows(self) -> list[dict]:
        return results_ledger.read()


def test_the_run_tags_cover_exactly_the_runs_a_cell_performs() -> None:
    assert len(runner.RUN_TAGS) == harness.RUNS_PER_CELL


def test_a_full_fake_run_records_every_cell_it_measured(tmp_path, monkeypatch) -> None:
    """One warm row per cell -- the measurement -- and its cold row beside it, because a discarded
    run nobody wrote down is how a 32% spread between two runs of ONE arm stays invisible."""
    rig = _Rig(tmp_path, monkeypatch)
    steps = _narrow_steps()
    tally = rig.run(steps=steps)

    cells = [cell for step in steps for cell in step.cells]
    warm = [row for row in rig.rows if row["warm"] is True]
    cold = [row for row in rig.rows if row["warm"] is False]
    assert len(warm) == len(cells)
    assert len(cold) == len(cells)
    assert {(row["family"], row["mode"], row["lever"]) for row in warm} == {
        (cell.family, cell.mode, cell.lever) for cell in cells
    }
    assert tally.cells_measured == len(cells)
    assert tally.renders_ok == len(cells) * harness.RUNS_PER_CELL


def test_every_render_in_the_whole_run_gets_its_own_seed(tmp_path, monkeypatch) -> None:
    """ComfyUI's node cache is keyed on the graph, and the seed is in the graph. The recorded trap
    on this project is a re-submit that changed only the output filename and came back in 12.1 s."""
    rig = _Rig(tmp_path, monkeypatch)
    rig.run()
    seeds = [request["seed"] for request in rig.sent]
    assert len(set(seeds)) == len(seeds)
    assert all(0 <= seed <= harness.MAX_SEED for seed in seeds)
    assert len({request["output"] for request in rig.sent}) == len(rig.sent)


def test_the_seconds_come_from_the_job_not_from_the_stopwatch(tmp_path, monkeypatch) -> None:
    """link.render also returns a wall reading, and it includes queue admission and upload. The
    worker's own generation_time_sec is the render; the round trip is not."""
    rig = _Rig(tmp_path, monkeypatch, responder=lambda _req, index: _completed(12.5))
    rig.run()
    warm = [row for row in rig.rows if row["warm"]][0]
    assert warm["seconds"] == [12.5, 12.5]
    assert 99.0 not in warm["seconds"], "the wall time must never reach a row as the render time"


def test_a_completed_job_that_reported_no_time_is_a_failed_run(tmp_path, monkeypatch) -> None:
    def no_time(_request, _index):
        message = _completed(10.0)
        message["result"].pop("generation_time_sec")
        return message

    rig = _Rig(tmp_path, monkeypatch, responder=no_time)
    tally = rig.run()
    assert rig.rows == []
    assert tally.renders_failed == len(_narrow_steps()) * harness.RUNS_PER_CELL
    assert any("generation_time_sec" in entry for entry in tally.failed_cells)


def test_a_restart_whose_argv_does_not_match_marks_and_excludes_its_rows(tmp_path, monkeypatch) -> None:
    """THE plant, now on the live path. ComfyUI was running with sage this morning, died, was
    relaunched and came back on SDPA. A request for an arm is not evidence the arm took."""
    def always_sdpa(_arm):
        return {"type": "comfy_runtime_ack", "ok": True,
                "argv": ["main.py", "--use-pytorch-cross-attention"]}

    rig = _Rig(tmp_path, monkeypatch, restarter=always_sdpa)
    tally = rig.run()

    sage = [row for row in rig.rows if row["lever"] == "sage_attention"]
    assert sage, "the cells still run -- an unverified arm is recorded, not skipped"
    for row in sage:
        assert row["arm_verified"] is False
        assert row["excluded_from_delta"] is True
        assert row["delta_pct"] is None
        assert any("arm" in reason for reason in row["exclusions"])
    assert any("sage_attention" in entry for entry in tally.unverified_arms)
    assert any("ARM NOT VERIFIED" in line for line in rig.printed)


def test_a_failed_render_does_not_abort_the_matrix(tmp_path, monkeypatch) -> None:
    """One dead render must not take the other thirty-five with it."""
    def one_bad(_request, index):
        return _failed() if index == 1 else _completed(10.0 + index)

    rig = _Rig(tmp_path, monkeypatch, responder=one_bad)
    tally = rig.run()

    assert tally.renders_failed == 1
    assert tally.cells_measured == 2, "the matrix kept going"
    warm = [row for row in rig.rows if row["warm"]]
    assert len(warm) == 2
    first = next(row for row in rig.rows if row["lever"] == "sdpa_baseline" and row["warm"])
    assert len(first["seconds"]) == 1
    assert any("one timed run" in reason for reason in first["exclusions"])
    assert any(entry["ok"] is False and entry["reason"] for entry in first["runs"])


def test_a_failed_cold_run_does_not_relabel_a_warm_run_as_cold(tmp_path, monkeypatch) -> None:
    """159.27 s and 120.72 s are one configuration cold and warm. A row that says the wrong one
    cannot be read, and the first SURVIVING run is not automatically the cold one."""
    def cold_dies(_request, index):
        return _failed("cold OOM") if index == 0 else _completed(10.0 + index)

    rig = _Rig(tmp_path, monkeypatch, responder=cold_dies)
    rig.run(steps=_narrow_steps()[:1])

    assert [row["warm"] for row in rig.rows] == [True]
    assert rig.rows[0]["seconds"] == [11.0, 12.0]


def test_a_failed_restart_aborts_the_run_and_still_hands_the_stack_back(tmp_path, monkeypatch) -> None:
    """The arm is the independent variable: nothing measured under an arm that did not launch is
    interpretable. But the owner's ComfyUI is still theirs."""
    def dead(arm):
        if arm == {"attention": "sdpa"}:
            return {"type": "comfy_runtime_ack", "ok": True, "argv": _argv_for(arm)}
        return {"type": "comfy_runtime_ack", "ok": False, "error": "comfy would not come back up"}

    rig = _Rig(tmp_path, monkeypatch, restarter=dead)
    with pytest.raises(runner.RestartFailed, match="would not come back up"):
        rig.run()
    assert any("RESTORE" in line for line in rig.printed)


def test_the_resume_check_skips_a_cell_the_ledger_already_holds(tmp_path, monkeypatch) -> None:
    """This run is measured in hours. A re-run must not re-render what is already recorded -- but
    only where the recorded row carries the same provenance, or "already measured" would mean
    "measured once, on some other build"."""
    rig = _Rig(tmp_path, monkeypatch)
    rig.run()
    assert len(rig.sent) == 6

    again = _Rig(tmp_path, monkeypatch)
    tally = again.run()
    assert again.sent == []
    assert tally.cells_skipped == 2
    assert any("already holds a warm row" in line for line in again.printed)


def test_force_re_measures_a_cell_the_ledger_already_holds(tmp_path, monkeypatch) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    rig.run()
    again = _Rig(tmp_path, monkeypatch)
    tally = again.run(force=True)
    assert len(again.sent) == 6
    assert tally.cells_skipped == 0


def test_a_row_recorded_under_other_provenance_does_not_count_as_measured(tmp_path, monkeypatch) -> None:
    other = dict(_FAKE_PROVENANCE, attention_backend="sage", fast_flags=["fp16_accumulation"])
    rig = _Rig(tmp_path, monkeypatch,
               responder=lambda _req, index: _completed(10.0 + index, provenance=other))
    rig.run()
    again = _Rig(tmp_path, monkeypatch)
    again.run()
    assert len(again.sent) == 6, "a matching label is not a matching build"


def test_rows_are_appended_as_each_cell_finishes_not_at_the_end(tmp_path, monkeypatch) -> None:
    """A crash forty minutes into an hours-long run must not cost the thirty minutes before it.

    Proved by watching the ledger DURING the run: the renders of the second cell must already see
    the first cell's rows on disk. Batching the appends to the end makes every reading zero.
    """
    rig = _Rig(tmp_path, monkeypatch)
    rig.run()
    assert rig.rows_seen_at_render[:3] == [0, 0, 0], "nothing is recorded before a cell finishes"
    assert rig.rows_seen_at_render[3] == 2, (
        "the first cell's cold and warm rows must be on disk before the second cell renders"
    )


def test_a_cell_with_no_request_template_is_reported_rather_than_invented(tmp_path, monkeypatch) -> None:
    """The harness will not guess a checkpoint or a step count -- that would measure a render
    nobody asked for."""
    rig = _Rig(tmp_path, monkeypatch)
    tally = rig.run(requests={})
    assert rig.sent == []
    assert rig.rows == []
    assert tally.missing_templates == ["krea2:t2i", "krea2:t2i"]
    assert any("will not invent" in line for line in rig.printed)


def test_the_baseline_mean_travels_to_the_lever_row(tmp_path, monkeypatch) -> None:
    """A delta is never computed against a baseline looked up from another session or build."""
    rig = _Rig(tmp_path, monkeypatch,
               responder=lambda _req, index: _completed(100.0 if index < 3 else 50.0))
    rig.run()
    sage = next(row for row in rig.rows if row["lever"] == "sage_attention" and row["warm"])
    assert sage["baseline_mean"] == pytest.approx(100.0)
    assert sage["delta_pct"] == pytest.approx(-50.0)


def test_the_progress_output_names_the_arm_the_cell_and_the_run(tmp_path, monkeypatch) -> None:
    """This goes to a terminal for an hour; it is the operator's only window."""
    rig = _Rig(tmp_path, monkeypatch)
    rig.run()
    lines = [line for line in rig.printed if "run 1/3" in line]
    assert lines and "COLD" in lines[0]
    assert "sdpa_baseline" in lines[0] and "krea2/t2i" in lines[0] and "seed=" in lines[0]
    assert any("finished:" in line for line in rig.printed)


def test_the_artefact_guard_adds_one_untimed_equal_seed_render_when_asked(tmp_path, monkeypatch) -> None:
    """Every timed render gets a fresh seed, so an equal-seed comparison needs its own render. It
    is never timed, so a node-cache hit on it cannot reach a measurement."""
    steps = harness.arm_sequence(
        harness.build_matrix(families=("krea2",), lever_ids=("vae_tiling",))
    )
    rig = _Rig(tmp_path, monkeypatch)
    rig.run(steps=steps, artefact_guard=True)

    def _is_guard(request):
        return Path(request["output"]).stem.endswith("_" + runner.GUARD_TAG + "_"
                                                     + str(request["seed"]))

    guard = [request for request in rig.sent if _is_guard(request)]
    assert len(guard) == 2, "one guard render per cell, baseline included"
    assert len({request["seed"] for request in guard}) == 1, "the guard seed is shared across arms"
    timed = [request for request in rig.sent if not _is_guard(request)]
    assert all(request["seed"] != guard[0]["seed"] for request in timed)
    for row in rig.rows:
        assert all(entry["seed"] != guard[0]["seed"] for entry in row["runs"])


def test_the_lever_request_keys_are_the_only_thing_the_harness_changes(tmp_path, monkeypatch) -> None:
    """vae_tiling is a request key, not a launch flag. Everything else in the template is the
    operator's and is sent unedited."""
    steps = harness.arm_sequence(
        harness.build_matrix(families=("krea2",), lever_ids=("vae_tiling",))
    )
    rig = _Rig(tmp_path, monkeypatch)
    rig.run(steps=steps)
    tiled = [request for request in rig.sent if request.get("enable_vae_tiling") is True]
    assert len(tiled) == harness.RUNS_PER_CELL
    assert all(request["steps"] == 10 for request in rig.sent), "the template is not rewritten"


def test_the_live_path_refuses_when_there_are_no_request_templates(capsys) -> None:
    """A bare invocation still refuses: restarting the owner's ComfyUI five times to render nothing
    is never what anyone meant."""
    assert harness.main([]) == 2
    assert "will not" in capsys.readouterr().out.lower()


def test_a_resumed_run_still_carries_the_skipped_baselines_mean(tmp_path, monkeypatch) -> None:
    """The feature that saves an hour must not cost the comparison. A resumed run whose baseline
    cell is skipped still has to hand that family's baseline_mean to every lever below it, or the
    levers measured after the resume record numbers with nothing to compare them against."""
    first = _Rig(tmp_path, monkeypatch, responder=lambda _req, _index: _completed(100.0))
    first.run(steps=_narrow_steps()[:1])

    second = _Rig(tmp_path, monkeypatch, responder=lambda _req, _index: _completed(50.0))
    tally = second.run()

    assert tally.cells_skipped == 1, "the baseline cell was already measured"
    sage = next(row for row in second.rows if row["lever"] == "sage_attention" and row["warm"])
    assert sage["baseline_mean"] == pytest.approx(100.0)
    assert sage["delta_pct"] == pytest.approx(-50.0)


# --- the sidecar fix: real artefacts from the failed 36-render run ------------------------------
#
# The matrix that ran live on 2026-09-16 produced 36 real renders and recorded zero rows, because
# the reader looked for `generation_time_sec` on `terminal["result"]`, and the worker's actual last
# message on this socket (`EventEmitter.result`, worker_tcp.py) has no nested "result" key at all --
# it flattens the job's fields onto the top level. The sidecars those 36 renders wrote are still on
# disk. This section points the reader at one of them directly, rather than a synthetic fixture that
# could encode a shape the real worker never produces (this wave has already been bitten twice by
# exactly that).

_REAL_SIDECAR = ROOT / "runtime" / "optimization_renders" / "ltx_t2v_sage_attention_warm_2_5935368.json"


def _flat_result_terminal(job_id: str, *, state: str = "completed") -> dict:
    """The shape `EventEmitter.result` actually sends: no nested "result" key, just the job's
    fields (would-be `asdict(job.result)`) flattened alongside type/ok/job_id/state. This is what
    every real completed render's terminal message looks like -- unlike `_completed()` above, which
    models the earlier `job_update` push that never survives to be the terminal message."""
    return {"type": "result", "ok": state == "completed", "job_id": job_id, "state": state}


def test_a_real_sidecar_from_the_failed_run_supplies_the_timing_and_provenance() -> None:
    """The number was always there. Point the reader at the actual sidecar one of the 36 failed
    renders wrote and it must recover both the seconds and the build that produced them, even though
    the terminal message (correctly, per `_flat_result_terminal`) carries neither."""
    assert _REAL_SIDECAR.is_file(), f"the archived sidecar is missing: {_REAL_SIDECAR}"

    outcome = harness.render.outcome_from(
        _flat_result_terminal("opt_695910b4f3c8"),
        tag="warm_2", seed=5935368, wall_seconds=36.58,
        requested_dest=str(_REAL_SIDECAR.with_suffix(".mp4")),
        requested_metadata=str(_REAL_SIDECAR),
    )

    assert outcome.ok, outcome.reason
    assert outcome.seconds == pytest.approx(36.44)
    assert outcome.provenance["provenance_source"] == "render_sidecar"
    assert outcome.provenance["attention_backend"] == "sage"
    assert outcome.provenance["comfy_version"] == "0.34.0"


def test_an_unreadable_sidecar_is_refused_not_wall_clocked(tmp_path) -> None:
    """THE plant: point the reader at a metadata path that does not exist, with a terminal message
    (the real flat shape) that carries no number either. It must refuse with the existing reasoning
    -- the round-trip wall time is not the thing under test -- rather than silently recording
    `wall_seconds` as if it were a render time."""
    missing = tmp_path / "does_not_exist_5935368.json"
    assert not missing.exists()

    outcome = harness.render.outcome_from(
        _flat_result_terminal("opt_missing"),
        tag="warm_2", seed=5935368, wall_seconds=36.58,
        requested_dest=str(tmp_path / "does_not_exist_5935368.mp4"),
        requested_metadata=str(missing),
    )

    assert outcome.ok is False
    assert outcome.seconds is None
    assert "generation_time_sec" in outcome.reason
    assert "round-trip wall time (36.58 s)" in outcome.reason
    assert "sidecar" in outcome.reason.lower()
