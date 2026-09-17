"""A restart nobody armed must not silently re-arm ComfyUI from the environment.

Sibling of `test_optimization_arm_restart.py`, which covers the arm ARRIVING at the launch command.
This file covers the arm SURVIVING a restart that was performed for some other reason.

The defect, seen in a live run in `build/worker_service.stderr.log`::

    ComfyUI attention backend (arm): sdpa -- argument selected pytorch SDPA
    ComfyUI VRAM headroom (arm): ComfyUI's own OS-dependent reservation (no flag)
    ComfyUI attention backend: sage -- default (sageattention is installed; ~25% on Wan)
    Invalidated cached ComfyUI /object_info: extra_model_paths.yaml changed

A later request rewrote `extra_model_paths.yaml`; `handle_ensure_comfy_runtime_command` restarts
ComfyUI when that file changes (ComfyUI reads it only at startup). That restart passed no arm, the
launch policy re-resolved attention from the environment, and this box has sageattention installed
-- so the explicitly requested SDPA became sage. Every timing after that point was recorded under an
arm that no longer applied, and in normal product use a user who adds a model library mid-session
gets the same backend swap with nothing in the UI saying so.

Nothing here starts, stops or touches the live ComfyUI on :8188. `subprocess.Popen` is replaced
before any test that would otherwise launch a process, and `is_healthy` before any test that would
otherwise make an HTTP request, so these test the launch COMMAND, never its execution.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import comfy_launch_policy as policy  # noqa: E402
import comfy_runtime_manager  # noqa: E402
import comfy_session_arm  # noqa: E402
import worker_service as ws  # noqa: E402


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    """No env-driven arm, no probe cache, and no arm remembered from another test.

    The session arm is deliberately process-wide (that is the whole point -- see
    `comfy_session_arm`), so it is exactly the sort of state that leaks between tests if nobody
    clears it.
    """
    monkeypatch.delenv(policy.ATTENTION_ENV_VAR, raising=False)
    monkeypatch.delenv(policy.VRAM_HEADROOM_ENV_VAR, raising=False)
    policy._PROBE_CACHE.clear()
    comfy_session_arm.forget_arm()
    yield
    policy._PROBE_CACHE.clear()
    comfy_session_arm.forget_arm()


class _FakeProc:
    def __init__(self, pid: int) -> None:
        self.pid = pid


def _manager(tmp_path: Path) -> comfy_runtime_manager.ComfyRuntimeManager:
    (tmp_path / "main.py").write_text("", encoding="utf-8")
    return comfy_runtime_manager.ComfyRuntimeManager(
        str(tmp_path),
        python_executable=sys.executable,
        host="127.0.0.1",
        port=18188,  # not the live :8188; is_healthy is patched, but the port is chosen off it.
        startup_timeout_sec=0.05,
        poll_interval_sec=0.01,
    )


def _rig(monkeypatch, manager) -> list[list[str]]:
    """Let the manager walk its real launch path without spawning anything.

    `sageattention_available` is forced True because that is what makes this box's environment
    default `sage`: without it the regression below cannot fire, and the test would pass for the
    wrong reason on a machine that simply lacks the package.
    """
    launched: list[list[str]] = []

    def _fake_popen(command, **kwargs):
        launched.append(list(command))
        return _FakeProc(pid=999999999)

    monkeypatch.setattr(comfy_runtime_manager.subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(policy, "sageattention_available", lambda *_a, **_k: True)
    monkeypatch.setattr(manager, "is_healthy", lambda: False)
    monkeypatch.setattr(
        manager, "_get_process_info",
        lambda pid: {"pid": pid, "exists": False, "cmdline": [], "exe": None,
                     "cwd": None, "create_time": None},
    )
    return launched


def _backend_of(command: list[str]) -> str:
    """Which attention backend a launch command actually asks for."""
    if policy.SAGE_FLAG in command:
        return policy.SAGE
    if policy.PYTORCH_ATTENTION_FLAG in command:
        return policy.SDPA
    return "unpinned"


# --- the memory itself ----------------------------------------------------------------------------


def test_an_explicit_arm_is_used_on_restart(tmp_path, monkeypatch) -> None:
    manager = _manager(tmp_path)
    launched = _rig(monkeypatch, manager)

    manager.restart(arm={"attention": "sdpa"})

    assert _backend_of(launched[-1]) == policy.SDPA


def test_a_restart_with_no_arm_reuses_the_remembered_one(tmp_path, monkeypatch) -> None:
    """The fix. Environment default here is sage; the session was started as sdpa."""
    manager = _manager(tmp_path)
    launched = _rig(monkeypatch, manager)

    manager.start(arm={"attention": "sdpa"})
    manager.restart()  # no arm -- a restart for somebody else's reason

    assert _backend_of(launched[0]) == policy.SDPA
    assert _backend_of(launched[-1]) == policy.SDPA, (
        "an unarmed restart re-resolved the backend from the environment and replaced the arm"
    )


def test_an_explicit_empty_arm_goes_back_to_the_environment(tmp_path, monkeypatch) -> None:
    """`{}` and "no arm given" are different requests and must stay distinguishable."""
    manager = _manager(tmp_path)
    launched = _rig(monkeypatch, manager)

    manager.start(arm={"attention": "sdpa"})
    manager.restart(arm={})

    assert _backend_of(launched[-1]) == policy.SAGE
    assert comfy_session_arm.remembered_arm() is None
    # And it is the byte-for-byte default branch, not an arm that computes the same flags: only an
    # explicit arm ever spells PYTORCH_ATTENTION_FLAG, and the default branch never does.
    assert policy.PYTORCH_ATTENTION_FLAG not in launched[-1]


def test_the_first_launch_of_a_session_still_takes_the_environment(tmp_path, monkeypatch) -> None:
    """With nothing remembered there is nothing to reuse, so the old behaviour is unchanged."""
    manager = _manager(tmp_path)
    launched = _rig(monkeypatch, manager)

    manager.start()

    assert _backend_of(launched[-1]) == policy.SAGE
    assert policy.PYTORCH_ATTENTION_FLAG not in launched[-1]


def test_a_remembered_arm_carries_every_axis(tmp_path, monkeypatch) -> None:
    manager = _manager(tmp_path)
    launched = _rig(monkeypatch, manager)

    manager.start(arm={"attention": "sdpa", "vram_headroom": 22.0, "dynamic_vram": False})
    manager.restart()

    command = launched[-1]
    assert _backend_of(command) == policy.SDPA
    assert policy.DISABLE_DYNAMIC_VRAM_FLAG in command
    assert command[command.index(policy.RESERVE_VRAM_FLAG) + 1] == "22"


# --- the memory survives the rebuild that would otherwise discard it -------------------------------


def test_a_manager_rebuild_keeps_the_remembered_arm(tmp_path, monkeypatch) -> None:
    """`get_comfy_runtime_manager` rebuilds the manager whenever comfy_root/host/port/python differ
    -- including on a re-resolution that lands on the same interpreter by a different spelling. A
    memory held on the instance would be dropped by exactly that incidental rebuild, which is the
    one separating an armed start from the yaml-triggered restart that follows it."""
    first = _manager(tmp_path)
    launched = _rig(monkeypatch, first)
    first.start(arm={"attention": "sdpa"})

    rebuilt = _manager(tmp_path)  # a second manager over the same runtime: the rebuild
    _rig(monkeypatch, rebuilt)
    assert rebuilt is not first
    rebuilt.restart()

    assert _backend_of(launched[-1]) == policy.SDPA


def test_get_comfy_runtime_manager_rebuilds_without_forgetting(monkeypatch, tmp_path) -> None:
    """The rebuild through the real worker entry point, rather than by constructing two managers."""
    (tmp_path / "main.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(ws, "default_comfy_root", lambda: str(tmp_path))
    ws.COMFY_RUNTIME_MANAGER = None
    try:
        first = ws.get_comfy_runtime_manager({"comfy_root": str(tmp_path)})
        comfy_session_arm.remember_arm({"attention": "sdpa"})
        ws.COMFY_RUNTIME_MANAGER = None  # what a differing host/port/python does
        second = ws.get_comfy_runtime_manager({"comfy_root": str(tmp_path)})
        assert second is not first
        assert comfy_session_arm.remembered_arm() == {"attention": "sdpa"}
    finally:
        ws.COMFY_RUNTIME_MANAGER = None


# --- the regression, through the handler that caused it --------------------------------------------


def test_a_yaml_triggered_restart_does_not_change_the_backend(tmp_path, monkeypatch) -> None:
    """THE regression. `handle_ensure_comfy_runtime_command` restarts when extra_model_paths.yaml
    changes; that restart must not re-arm the session from the environment.

    The manager handed to the handler is a real `ComfyRuntimeManager` with Popen and is_healthy
    replaced -- the whole path except the process spawn. A fake that resolved the arm itself would
    only prove the fake resolves arms."""
    manager = _manager(tmp_path)
    launched = _rig(monkeypatch, manager)
    monkeypatch.setattr(ws, "get_comfy_runtime_manager", lambda req=None: manager)
    monkeypatch.setattr(ws, "_sync_comfy_extra_model_paths", lambda req: True)  # yaml changed

    manager.start(arm={"attention": "sdpa"})
    assert _backend_of(launched[-1]) == policy.SDPA

    ws.handle_ensure_comfy_runtime_command({"command": "ensure_comfy_runtime",
                                            "startup_timeout_sec": 0.05})

    assert len(launched) == 2, "the yaml change should have relaunched ComfyUI exactly once"
    assert _backend_of(launched[-1]) == policy.SDPA, (
        f"a yaml-triggered restart replaced the requested {policy.SDPA} with "
        f"{_backend_of(launched[-1])} -- the live-run defect"
    )


# --- the request layer can say both things ---------------------------------------------------------


def test_a_nested_empty_arm_is_a_request_for_the_environment() -> None:
    """The flat keys cannot express "clear": an empty selection from them is indistinguishable from
    naming none. The nested form can, so both meanings survive the wire."""
    assert ws._arm_from_request({"command": "restart_comfy_runtime"}) is None
    assert ws._arm_from_request({"command": "restart_comfy_runtime", "arm": {}}) == {}
    assert ws._arm_from_request({"arm": {"attention": "sage"}}) == {"attention": "sage"}
    assert ws._arm_from_request({"attention": "sdpa"}) == {"attention": "sdpa"}
