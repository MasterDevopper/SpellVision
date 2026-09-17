"""The worker can restart ComfyUI into a chosen A/B arm -- and the launch it performs keeps UTF-8.

Task 1 (optimization_provenance.py) made every render record which build produced it, by reading
the RUNNING process's argv back from `/system_stats`. That is only evidence if the build can be
changed on purpose: before this, `restart_comfy_runtime` accepted no attention/fast/VRAM keys, so
every restart launched the same environment-driven default, and the archive's only published A/B
(Doc 55, sage vs SDPA on krea2) is distinguishable solely because a human typed the arm name into an
output filename.

Two real defects sit on the path this exercises, neither speculative (t4-context.md "Launch
policy"):

1. `bootstrap_comfy_runtime` had no `vram_headroom` parameter, so the worker-managed launch could
   never reach `--reserve-vram` even though `build_launch_command` (which it calls) already
   supported it. Covered in `tests/test_comfy_launch_policy.py`
   (`test_bootstrap_comfy_runtime_can_pass_vram_headroom`).
2. `ComfyRuntimeManager.start` called `subprocess.Popen(command, cwd=...)` with no `env=`, so
   `comfy_launch_policy.launch_env()` -- which sets `PYTHONUTF8=1` / `PYTHONIOENCODING=utf-8` and
   whose own module docstring calls it load-bearing (a non-ASCII character in a bundled node pack
   crashes ComfyUI's stderr logging under Windows cp1252 without it) -- reached only the tests.
   `test_the_env_fix_actually_bites` below is the mandated plant for that one.

Nothing here starts, stops, or touches the live ComfyUI on :8188. `subprocess.Popen` is replaced
before any test that would otherwise launch a process, so these test the launch COMMAND's
construction, never its execution.
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
    monkeypatch.delenv(policy.ATTENTION_ENV_VAR, raising=False)
    monkeypatch.delenv(policy.VRAM_HEADROOM_ENV_VAR, raising=False)
    policy._PROBE_CACHE.clear()
    # The session arm is process-wide by design (comfy_session_arm), so an arm one test launches
    # with is still remembered by the next -- which is the whole point in the worker and a
    # cross-test leak here. `test_arm_none_never_emits_an_arm_only_flag` is about the FIRST launch
    # of a session, and it read a previous test's sdpa arm until this line existed.
    comfy_session_arm.forget_arm()
    yield
    policy._PROBE_CACHE.clear()
    comfy_session_arm.forget_arm()


class _FakeProc:
    """Stands in for the Popen handle. No process is actually spawned."""

    def __init__(self, pid: int) -> None:
        self.pid = pid


def _manager(tmp_path: Path, **overrides: Any) -> comfy_runtime_manager.ComfyRuntimeManager:
    (tmp_path / "main.py").write_text("", encoding="utf-8")
    kwargs = dict(
        python_executable=sys.executable,
        host="127.0.0.1",
        port=18188,  # not the live :8188 -- this manager never sends a real request that matters,
        # is_healthy is monkeypatched below, but the port is chosen off the live one on principle.
        startup_timeout_sec=0.05,
        poll_interval_sec=0.01,
    )
    kwargs.update(overrides)
    manager = comfy_runtime_manager.ComfyRuntimeManager(str(tmp_path), **kwargs)
    return manager


def _rig_for_a_fake_launch(monkeypatch, manager: comfy_runtime_manager.ComfyRuntimeManager):
    """Make manager.start() walk its real launch code (bootstrap -> Popen -> state write) without
    touching the network or the OS process table. Returns the list `Popen` was called with, and a
    dict of the kwargs it was called with, both mutated in place as they become known."""
    calls: dict[str, Any] = {}

    def _fake_popen(command, **kwargs):
        calls["command"] = list(command)
        calls["kwargs"] = kwargs
        return _FakeProc(pid=999999999)

    monkeypatch.setattr(comfy_runtime_manager.subprocess, "Popen", _fake_popen)
    # is_healthy would otherwise try a real HTTP request to the port above. False keeps status()
    # walking the same "not ready yet" branch on every poll, so start() reaches its timeout branch
    # quickly (poll_interval_sec/startup_timeout_sec above are both tiny) instead of spinning for
    # the real default of 60s.
    monkeypatch.setattr(manager, "is_healthy", lambda: False)
    # Avoid a real OS process lookup for a pid nothing spawned.
    monkeypatch.setattr(
        manager, "_get_process_info",
        lambda pid: {"pid": pid, "exists": False, "cmdline": [], "exe": None, "cwd": None, "create_time": None},
    )
    return calls


# --- ComfyRuntimeManager.start(): the arm reaches the command line, and so does the environment ---


def test_an_explicit_sdpa_arm_reaches_the_launched_command(tmp_path, monkeypatch) -> None:
    manager = _manager(tmp_path)
    calls = _rig_for_a_fake_launch(monkeypatch, manager)

    payload = manager.start(arm={"attention": "sdpa"})

    assert policy.PYTORCH_ATTENTION_FLAG in calls["command"]
    assert policy.SAGE_FLAG not in calls["command"]
    # The reply carries what was ACTUALLY launched -- a caller must be able to verify the arm took
    # rather than trust the request was honoured (the Qt sage probe fails open to SDPA on a cold
    # launch, so a request for sage can legitimately produce an SDPA process).
    assert payload["argv"] == calls["command"]


def test_a_vram_headroom_arm_reaches_the_launched_command(tmp_path, monkeypatch) -> None:
    manager = _manager(tmp_path)
    calls = _rig_for_a_fake_launch(monkeypatch, manager)

    manager.start(arm={"attention": "sdpa", "vram_headroom": 16})

    command = calls["command"]
    assert command[command.index(policy.RESERVE_VRAM_FLAG) + 1:] == ["16"]


def test_arm_none_never_emits_an_arm_only_flag(tmp_path, monkeypatch) -> None:
    """The default path (every non-A/B launch) must not pick up PYTORCH_ATTENTION_FLAG, which only
    an explicit arm ever emits."""
    manager = _manager(tmp_path)
    calls = _rig_for_a_fake_launch(monkeypatch, manager)
    monkeypatch.setattr(policy, "sageattention_available", lambda *_a, **_k: True)

    manager.start()  # arm defaults to None

    assert policy.PYTORCH_ATTENTION_FLAG not in calls["command"]


# --- Step 6's mandated plant: the env fix must actually bite --------------------------------------


def test_the_env_fix_actually_bites(tmp_path, monkeypatch) -> None:
    """Popen must receive an `env` carrying PYTHONUTF8=1. This is the defect-2 plant from the brief:
    run this against the current source (env= present) and it passes; delete the `env=` argument
    from ComfyRuntimeManager.start and it fails. See the task report for both transcripts."""
    manager = _manager(tmp_path)
    calls = _rig_for_a_fake_launch(monkeypatch, manager)

    manager.start(arm={"attention": "sdpa"})

    env = calls["kwargs"].get("env")
    assert env is not None, "Popen was called with no env= at all -- PYTHONUTF8 cannot reach it"
    assert env.get("PYTHONUTF8") == "1"
    assert env.get("PYTHONIOENCODING") == "utf-8"


# --- worker_service.handle_restart_comfy_runtime_command: construction, not execution --------------


class _FakeManager:
    """Records what handle_restart_comfy_runtime_command asked for; launches nothing."""

    def __init__(self) -> None:
        self.restart_calls: list[dict[str, Any]] = []

    def restart(self, timeout_sec=None, *, arm=None):
        self.restart_calls.append({"timeout_sec": timeout_sec, "arm": arm})
        return {
            "ok": True,
            "state": "ready_managed",
            "argv": [sys.executable, "main.py", "--use-pytorch-cross-attention"] if arm else
                    [sys.executable, "main.py"],
            "host": "127.0.0.1",
            "port": 18188,
        }


def _rig_worker_restart(monkeypatch) -> _FakeManager:
    fake = _FakeManager()
    monkeypatch.setattr(ws, "get_comfy_runtime_manager", lambda req=None: fake)
    monkeypatch.setattr(ws, "_sync_comfy_extra_model_paths", lambda req: False)
    return fake


def test_restart_command_threads_the_arm_keys_to_the_manager(monkeypatch) -> None:
    fake = _rig_worker_restart(monkeypatch)

    reply = ws.handle_restart_comfy_runtime_command({
        "command": "restart_comfy_runtime",
        "attention": "sdpa",
        "fast": ["fp16_accumulation"],
        "dynamic_vram": False,
        "vram_headroom": 16,
    })

    assert len(fake.restart_calls) == 1
    assert fake.restart_calls[0]["arm"] == {
        "attention": "sdpa", "fast": ["fp16_accumulation"],
        "dynamic_vram": False, "vram_headroom": 16,
    }
    # The reply carries the argv the manager reports it actually launched, unmodified -- a caller
    # reads this to verify the arm took rather than trusting the request was honoured.
    assert reply["argv"] == [sys.executable, "main.py", "--use-pytorch-cross-attention"]
    assert reply["type"] == "comfy_runtime_ack"
    assert reply["action"] == "restart_comfy_runtime"


def test_restart_command_with_no_arm_keys_passes_arm_none(monkeypatch) -> None:
    """Ruling W3-P1: a restart naming none of the arm keys must reach the manager as arm=None, the
    exact byte-for-byte default path -- not an empty dict, which arm_args() would treat as "an arm
    that explicitly asks for nothing" rather than "no arm at all"."""
    fake = _rig_worker_restart(monkeypatch)

    ws.handle_restart_comfy_runtime_command({"command": "restart_comfy_runtime"})

    assert fake.restart_calls[0]["arm"] is None


def test_restart_command_reply_carries_the_launched_argv(monkeypatch) -> None:
    fake = _rig_worker_restart(monkeypatch)

    reply = ws.handle_restart_comfy_runtime_command({"command": "restart_comfy_runtime", "attention": "sdpa"})

    assert reply["argv"] == [sys.executable, "main.py", "--use-pytorch-cross-attention"]


def test_restart_command_invalidates_optimization_provenance(monkeypatch) -> None:
    """Task 1 added invalidate_optimization_provenance() and nothing called it. Without this, every
    A/B row after the first restart would carry the PREVIOUS arm's cached provenance while looking
    complete -- worse than recording no provenance at all. Verified here by planting a value in the
    real cache (the same module-level dict optimization_provenance.probe() populates) and asserting
    the restart handler clears it, rather than by mocking the function -- a mock would only prove the
    call happened, not that it does what invalidation means."""
    _rig_worker_restart(monkeypatch)

    from optimization_provenance import _CACHE, _CACHE_LOCK

    with _CACHE_LOCK:
        _CACHE["http://127.0.0.1:18188"] = (0.0, {"attention_backend": "stale"})
        assert _CACHE  # planted

    ws.handle_restart_comfy_runtime_command({"command": "restart_comfy_runtime"})

    with _CACHE_LOCK:
        assert not _CACHE, "restart_comfy_runtime did not invalidate optimization provenance"
