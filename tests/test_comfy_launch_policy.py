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
        "C:/sv_comfynext/ComfyUI", python_executable=sys.executable, probe_attention=False)
    if command:  # empty when this box has no ComfyUI entrypoint
        assert policy.SAGE_FLAG in command


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
    policy.sageattention_available("C:/sv_comfynext/.venv/Scripts/python.exe")
    assert seen == ["C:/sv_comfynext/.venv/Scripts/python.exe"]


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

    live = Path("C:/sv_comfynext/ComfyUI")
    if not live.exists():
        pytest.skip("no live ComfyUI install on this machine")
    found = comfy_venv_python(live)
    assert found is not None and found.exists()
    assert "sv_comfynext" in str(found), found


def test_running_on_a_foreign_interpreter_is_reported(tmp_path) -> None:
    """An override still WINS -- overriding is what an override is for. What it must not do is stay
    quiet: the interpreters are two different programs, and on this box SPELLVISION_COMFY_PYTHON is
    a stale USER variable left pointing at the project venv from before the cutover."""
    from comfy_bootstrap import comfy_python_report

    report = comfy_python_report(tmp_path, explicit_python=sys.executable)
    assert report["python_executable"] == str(Path(sys.executable).resolve())
    assert report["source"] == "explicit argument"
    assert report["is_comfy_own_venv"] is False
