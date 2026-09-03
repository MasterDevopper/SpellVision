"""Three launchers start the same ComfyUI, and they did not agree about how.

                            start_comfy.ps1   build_launch_command   MainWindow.cpp
    --use-sage-attention          yes                 no                  no
    PYTHONUTF8=1                  yes                 no                  yes
    PYTHONIOENCODING=utf-8        yes                 no                  yes

SageAttention was measured on this box at -25.1% per iteration on Wan 2.2 dual-noise and -22.8%
end to end, and only the DEVELOPER's launcher passed it. Starting SpellVision the way a user starts
it -- the app launching its own ComfyUI -- gave up roughly a quarter of the speed on the heaviest
path in the product, and every timing recorded in this repo was taken against a process the app
never starts.

PYTHONUTF8 is not tuning. CLAUDE.md 9.2: the Jul-10 RES4LYF pack ships a non-ASCII character that
crashes ComfyUI's stderr logging under Windows cp1252 and takes the whole process down. The
Python-managed launch set neither variable, so the same install lived or died on how it was started.

These are cross-language checks for the same reason ``test_comfy_root`` has one: the three sites are
in three languages, and a property that only one language can see is how they diverged in the first
place.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import comfy_launch_policy as policy  # noqa: E402

PS_LAUNCHER = (ROOT / "scripts" / "dev" / "start_comfy.ps1").read_text(encoding="utf-8", errors="replace")
QT_PROFILE = (ROOT / "qt_ui" / "shell" / "RuntimeProfile.cpp").read_text(encoding="utf-8", errors="replace")
QT_MAIN = (ROOT / "qt_ui" / "MainWindow.cpp").read_text(encoding="utf-8", errors="replace")


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv(policy.ATTENTION_ENV_VAR, raising=False)
    policy._PROBE_CACHE.clear()
    yield
    policy._PROBE_CACHE.clear()


def _fake_probe(monkeypatch, available: bool) -> None:
    monkeypatch.setattr(policy, "sageattention_available", lambda *_a, **_k: available)


# --- the three sides name the same things ---------------------------------------------------------

def test_every_launcher_names_the_same_flag() -> None:
    for name, text in (("start_comfy.ps1", PS_LAUNCHER), ("RuntimeProfile.cpp", QT_PROFILE)):
        assert policy.SAGE_FLAG in text, f"{name} does not name {policy.SAGE_FLAG}"


def test_every_launcher_reads_the_same_variable() -> None:
    """One name, so a user who sets it gets the same backend however they start the app."""
    for name, text in (("start_comfy.ps1", PS_LAUNCHER), ("RuntimeProfile.cpp", QT_PROFILE)):
        assert policy.ATTENTION_ENV_VAR in text, f"{name} does not read {policy.ATTENTION_ENV_VAR}"


@pytest.mark.parametrize("variable", sorted(policy.REQUIRED_ENV))
def test_every_launcher_sets_the_required_environment(variable: str) -> None:
    assert variable in PS_LAUNCHER, f"start_comfy.ps1 does not set {variable}"
    assert variable in QT_PROFILE, f"the Qt launch policy does not set {variable}"


def test_the_qt_launch_goes_through_the_policy_rather_than_spelling_it() -> None:
    """MainWindow spelled the two UTF-8 variables inline and passed no attention flag. Spelling them
    at the call site is how the third launcher came to have two of the three settings."""
    assert "applyComfyLaunchEnvironment" in QT_MAIN
    assert "comfyLaunchArguments" in QT_MAIN
    assert 'QStringLiteral("PYTHONUTF8")' not in QT_MAIN, (
        "MainWindow spells PYTHONUTF8 again instead of taking it from the policy"
    )


def test_the_python_launch_command_carries_the_policy() -> None:
    from comfy_bootstrap import build_launch_command

    command = build_launch_command(
        "C:/sv_comfynext_v034/ComfyUI", python_executable=sys.executable, probe_attention=False)
    if command:  # empty when this box has no ComfyUI entrypoint
        assert policy.SAGE_FLAG in command


# --- VRAM: one lever works, and the ones people reach for do not -----------------------------------
#
# Measured 2026-09-03 on a 32 GB card, LTX-2.3-22B full precision, seeds varied so no run was served
# ComfyUI's node cache. The same render peaked at 31.39 GB with no reservation and 11.47 GB with 22
# GB reserved -- and 97 frames at 2048x1280 output completed in 11.47 GB. Peak VRAM on this core is
# a measure of what was AVAILABLE, not of what was needed, and this repository's "premium,
# near-ceiling path" language came from reading it as the latter.


def test_every_launcher_reads_the_same_vram_variable() -> None:
    """The same shape as the attention variable, and for the same reason: a user who sets it must
    get the same behaviour however they start the app."""
    for name, text in (("start_comfy.ps1", PS_LAUNCHER), ("RuntimeProfile.cpp", QT_PROFILE)):
        assert policy.VRAM_HEADROOM_ENV_VAR in text, (
            f"{name} does not read {policy.VRAM_HEADROOM_ENV_VAR}"
        )


def test_every_launcher_names_the_same_vram_flag() -> None:
    for name, text in (("start_comfy.ps1", PS_LAUNCHER), ("RuntimeProfile.cpp", QT_PROFILE)):
        assert policy.RESERVE_VRAM_FLAG in text, f"{name} does not name {policy.RESERVE_VRAM_FLAG}"


def test_no_launcher_passes_a_flag_that_is_inert_under_dynamic_vram() -> None:
    """The conventional low-VRAM playbook is a no-op on this core, and worse than a no-op.

    ComfyUI 0.34.0 enables DynamicVRAM by default. `--lowvram`'s own help text says it "Doesn't do
    anything if dynamic vram is enabled"; `--novram`, `--highvram`, `--gpu-only` and `--cpu` all
    make `enables_dynamic_vram()` return False, i.e. they DISABLE the offload engine. A launcher
    reaching for one of them to make a large model fit would turn off the thing that was making it
    fit, and would produce a command line that looks like it addressed the problem.

    They may be NAMED -- all three launchers list them in order to refuse them -- so this asserts
    they are never appended to a command.
    """
    forbidden = sorted(policy.INERT_UNDER_DYNAMIC_VRAM)
    for name, text in (("start_comfy.ps1", PS_LAUNCHER), ("RuntimeProfile.cpp", QT_PROFILE)):
        for flag in forbidden:
            appended = [
                line for line in text.splitlines()
                if flag in line and ("+=" in line or "<<" in line or "append" in line.lower())
            ]
            assert not appended, f"{name} appends {flag} to the launch line: {appended}"


@pytest.mark.parametrize("flag", sorted(policy.INERT_UNDER_DYNAMIC_VRAM))
def test_asking_for_an_inert_flag_is_refused_with_the_reason(flag: str, monkeypatch) -> None:
    monkeypatch.delenv(policy.VRAM_HEADROOM_ENV_VAR, raising=False)
    with pytest.raises(RuntimeError) as excinfo:
        policy.resolve_vram_headroom(flag)
    assert flag in str(excinfo.value)
    assert policy.VRAM_HEADROOM_ENV_VAR in str(excinfo.value), (
        "the refusal has to say what to do instead, not only that this is wrong"
    )


def test_no_reservation_is_not_the_same_as_reserving_nothing(monkeypatch) -> None:
    """`None` means "pass no flag", and ComfyUI then applies its own OS-dependent reservation.

    Defaulting to an explicit 0 would OVERRIDE that with "reserve nothing", which is a change to
    behaviour dressed as a default.
    """
    monkeypatch.delenv(policy.VRAM_HEADROOM_ENV_VAR, raising=False)
    headroom, reason = policy.resolve_vram_headroom()
    assert headroom is None
    assert policy.vram_args(headroom) == []
    assert "no flag" in reason


def test_a_reservation_reaches_the_command_line(monkeypatch) -> None:
    monkeypatch.setenv(policy.VRAM_HEADROOM_ENV_VAR, "6")
    headroom, _reason = policy.resolve_vram_headroom()
    assert headroom == 6.0
    assert policy.vram_args(headroom) == [policy.RESERVE_VRAM_FLAG, "6"]


def test_a_value_that_is_not_a_number_is_refused(monkeypatch) -> None:
    monkeypatch.delenv(policy.VRAM_HEADROOM_ENV_VAR, raising=False)
    for bad in ("banana", "-1"):
        with pytest.raises(RuntimeError):
            policy.resolve_vram_headroom(bad)


# --- the backend is probed, never assumed ---------------------------------------------------------

def test_sage_is_the_default_when_it_is_installed(monkeypatch) -> None:
    _fake_probe(monkeypatch, True)
    backend, reason = policy.resolve_attention_backend("py")
    assert backend == policy.SAGE and "default" in reason
    assert policy.attention_args(backend) == [policy.SAGE_FLAG]


def test_a_missing_package_falls_back_loudly_rather_than_killing_comfyui(monkeypatch, caplog) -> None:
    """ComfyUI does `exit(-1)` when the flag is passed without the package, so an unprobed default
    would turn a working install into one that dies at startup with the reason in a log file."""
    import logging

    _fake_probe(monkeypatch, False)
    with caplog.at_level(logging.WARNING):
        backend, _ = policy.resolve_attention_backend("py")
    assert backend == policy.SDPA
    assert policy.attention_args(backend) == []
    assert any("pip install sageattention" in r.getMessage() for r in caplog.records), (
        "the fallback must name the command that fixes it"
    )


def test_asking_for_sage_by_name_without_the_package_is_refused(monkeypatch) -> None:
    """The distinction the whole module is built around. An unset preference may be downgraded; a
    stated one may not -- that is the same silent substitution Doc 19 forbids for models, and the
    user would never learn their measured 25% was not running."""
    _fake_probe(monkeypatch, False)
    with pytest.raises(RuntimeError) as excinfo:
        policy.resolve_attention_backend("py", explicit="sage")
    message = str(excinfo.value)
    assert policy.SAGE_FLAG in message and "pip install sageattention" in message


def test_asking_for_sdpa_never_probes(monkeypatch) -> None:
    """A user who wants SDPA should not pay for a subprocess to be told they can have it."""
    def _explode(*_a, **_k):
        raise AssertionError("probed despite an explicit SDPA request")

    monkeypatch.setattr(policy, "sageattention_available", _explode)
    assert policy.resolve_attention_backend("py", explicit="sdpa")[0] == policy.SDPA
    monkeypatch.setenv(policy.ATTENTION_ENV_VAR, "pytorch")
    assert policy.resolve_attention_backend("py")[0] == policy.SDPA


@pytest.mark.parametrize("spelling,expected", [
    ("sage", policy.SAGE), ("SAGE", policy.SAGE), (" sageattention ", policy.SAGE),
    ("sdpa", policy.SDPA), ("pytorch", policy.SDPA), ("off", policy.SDPA),
    ("", None), (None, None), ("nonsense", None),
])
def test_backend_spellings(spelling, expected) -> None:
    assert policy.normalize_backend(spelling) == expected


def test_an_unset_preference_is_distinguishable_from_a_stated_one() -> None:
    """Why normalize_backend returns None rather than a default: the two take different branches
    when the package is missing, and collapsing them would make the refusal above impossible."""
    assert policy.normalize_backend("") is None
    assert policy.normalize_backend("sage") == policy.SAGE


def test_an_explicit_argument_outranks_the_environment(monkeypatch) -> None:
    _fake_probe(monkeypatch, True)
    monkeypatch.setenv(policy.ATTENTION_ENV_VAR, "sage")
    assert policy.resolve_attention_backend("py", explicit="sdpa")[0] == policy.SDPA


# --- the probe asks the right interpreter ---------------------------------------------------------

def test_the_probe_asks_the_interpreter_that_will_run_comfyui(monkeypatch) -> None:
    """ComfyUI runs from its OWN venv (CLAUDE.md 9.2), decoupled from the worker's since the
    2026-07-17 cutover, and only one of them needs the package. Asking this process would answer
    about the wrong environment -- demonstrably: on this box the worker venv has no sageattention
    and ComfyUI's does."""
    seen: list[str] = []

    class _Result:
        returncode = 0

    monkeypatch.setattr(policy.subprocess, "run",
                        lambda cmd, **_k: (seen.append(cmd[0]), _Result())[1])
    policy._PROBE_CACHE.clear()
    policy.sageattention_available("C:/sv_comfynext_v034/.venv/Scripts/python.exe")
    assert seen == ["C:/sv_comfynext_v034/.venv/Scripts/python.exe"]


def test_a_probe_that_cannot_run_reports_unavailable(monkeypatch, caplog) -> None:
    """Optimism costs a ComfyUI that exits -1. The answer is re-derived next launch anyway."""
    import logging

    monkeypatch.setattr(policy.subprocess, "run",
                        lambda *_a, **_k: (_ for _ in ()).throw(OSError("no such file")))
    policy._PROBE_CACHE.clear()
    with caplog.at_level(logging.WARNING):
        assert policy.sageattention_available("nope") is False
    assert any("probe" in r.getMessage().lower() for r in caplog.records)


def test_the_probe_is_cached_per_interpreter(monkeypatch) -> None:
    calls: list[str] = []

    class _Result:
        returncode = 0

    monkeypatch.setattr(policy.subprocess, "run",
                        lambda cmd, **_k: (calls.append(cmd[0]), _Result())[1])
    policy._PROBE_CACHE.clear()
    for _ in range(3):
        policy.sageattention_available("a")
    policy.sageattention_available("b")
    assert calls == ["a", "b"]


# --- the required environment is applied, not defaulted -------------------------------------------

def test_the_required_variables_overwrite_an_inherited_value() -> None:
    """A stale PYTHONIOENCODING inherited from a parent shell is exactly the case that crashes
    stderr logging, so these are applied over the base rather than filled in behind it."""
    env = policy.launch_env({"PYTHONIOENCODING": "cp1252", "KEEP": "me"})
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["PYTHONUTF8"] == "1"
    assert env["KEEP"] == "me"


def test_launch_env_does_not_mutate_its_input() -> None:
    base = {"PYTHONIOENCODING": "cp1252"}
    policy.launch_env(base)
    assert base == {"PYTHONIOENCODING": "cp1252"}


# --- ComfyUI runs on ComfyUI's interpreter --------------------------------------------------------

def test_the_python_side_knows_about_comfys_own_venv() -> None:
    """Qt's RuntimeProfile had always looked for the venv beside the ComfyUI root; the Python side
    had not, and fell through to the project venv. The two halves disagreed about which interpreter
    runs ComfyUI -- the same divergence the comfy-root resolver closed for the install path."""
    from comfy_bootstrap import comfy_venv_python

    # The root comes from the resolver, never from a literal here. Spelled out, this test survived
    # the 2026-08-31 cutover while testing the SUPERSEDED tree, and the assertion below made that
    # invisible: "sv_comfynext" is a substring of "sv_comfynext_v034", so a check for it passes
    # against either install. It would have gone on reporting success about the wrong ComfyUI.
    from comfy_root import LIVE_COMFY

    live = LIVE_COMFY
    if not live.exists():
        pytest.skip("no live ComfyUI install on this machine")
    found = comfy_venv_python(live)
    assert found is not None and found.exists()
    # The venv sits beside the install (<root>/../.venv), so this is the precise statement the
    # substring check was gesturing at: the interpreter found must live inside the live tree.
    assert found.is_relative_to(live.parent), f"{found} is not inside the live install {live}"


def test_running_on_a_foreign_interpreter_is_reported(tmp_path) -> None:
    """An override still WINS -- overriding is what an override is for. What it must not do is stay
    quiet: the interpreters are two different programs, and on this box SPELLVISION_COMFY_PYTHON is
    a stale USER variable left pointing at the project venv from before the cutover."""
    from comfy_bootstrap import comfy_python_report

    report = comfy_python_report(tmp_path, explicit_python=sys.executable)
    assert report["python_executable"] == str(Path(sys.executable).resolve())
    assert report["source"] == "explicit argument"
    assert report["is_comfy_own_venv"] is False
