"""Close must unload both diffusers cache and Comfy-resident models."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "qt_ui" / "MainWindow.cpp"
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


def test_ui_exit_never_unloads_and_gates_kill_on_verified_idle_queue():
    """Exit contract: adopted Comfy is untouched; app-owned Comfy stops only
    when /queue is verifiably idle. Busy or unknown state detaches the process
    instead of killing it. There is no unload_all_runtimes at exit."""
    text = MAIN.read_text(encoding="utf-8")
    teardown_at = text.find("void MainWindow::tearDownComfyOnExit")
    assert teardown_at > 0, "tearDownComfyOnExit missing"
    teardown_end = text.find("\n}\n", teardown_at)
    body = text[teardown_at:teardown_end]
    assert "unload_all_runtimes" not in body, "exit must not unload runtimes (adopted Comfy is untouched)"
    assert "probeComfyQueueState" in body, "exit must verify /queue before stopping app-owned Comfy"
    assert "ComfyQueueState::Idle" in body, "only verified idle permits termination"
    assert "setParent(nullptr)" in body, "busy/unknown state must detach, not kill"


def test_unload_all_runtimes_requests_comfy_free(monkeypatch):
    import worker_runtime as runtime
    import worker_service as ws

    calls: list[dict] = []

    def fake_free(**kwargs):
        calls.append(kwargs)
        return {"ok": True, "status": 200}

    monkeypatch.setattr(runtime, "request_comfy_free_memory", fake_free)
    monkeypatch.setattr(runtime, "unload_cached_pipelines", lambda: {"old_key": "x"})
    monkeypatch.setattr(runtime, "reset_video_runtime_cache", lambda *_a, **_k: {"reset": True})
    monkeypatch.setattr(runtime, "clear_cuda_memory", lambda: {"allocated_gb": 0})
    monkeypatch.setattr(
        runtime,
        "runtime_memory_ack",
        lambda action, ok=True, **fields: {"ok": ok, "action": action, **fields},
    )

    payload = ws.handle_runtime_memory_control_command({"command": "unload_all_runtimes"})
    assert payload.get("ok") is True
    assert calls, "unload_all_runtimes must POST Comfy /free so native weights leave VRAM"


def test_unload_all_runtimes_fails_closed_when_comfy_free_fails(monkeypatch):
    import worker_runtime as runtime
    import worker_service as ws

    monkeypatch.setattr(
        runtime,
        "request_comfy_free_memory",
        lambda **_k: {"ok": False, "error": "connection refused", "url": "http://127.0.0.1:8188/free"},
    )
    monkeypatch.setattr(runtime, "unload_cached_pipelines", lambda: {"old_key": "x"})
    monkeypatch.setattr(runtime, "reset_video_runtime_cache", lambda *_a, **_k: {"reset": True})
    monkeypatch.setattr(runtime, "clear_cuda_memory", lambda: {"allocated_gb": 0})

    payload = ws.handle_runtime_memory_control_command({"command": "unload_all_runtimes"})
    assert payload.get("ok") is False
    assert payload.get("comfy_free", {}).get("ok") is False


def test_request_comfy_free_memory_posts_unload_models(monkeypatch):
    import comfy_prompt_client as cpc

    seen: dict[str, object] = {}

    class FakeResp:
        status = 200

        def read(self):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=0):
        seen["url"] = req.full_url if hasattr(req, "full_url") else req.get_full_url()
        seen["data"] = req.data
        seen["timeout"] = timeout
        return FakeResp()

    monkeypatch.setattr(cpc.urllib.request, "urlopen", fake_urlopen)
    result = cpc.request_comfy_free_memory(api_url="http://127.0.0.1:8188", timeout_sec=2.0)
    assert result["ok"] is True
    assert str(seen["url"]).rstrip("/").endswith("/free")
    assert b"unload_models" in seen["data"]
    assert b"free_memory" in seen["data"]
