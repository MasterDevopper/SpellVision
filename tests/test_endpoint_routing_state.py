"""Four pieces of worker state assumed there was only ever one ComfyUI.

The endpoint has been resolved per request since `comfy_endpoint` landed, and `comfy_prompt_client`
parameterises every call on `api_url`. So a job *can* already be pointed at a second box. What
would happen if one were is the subject of this file, and each of these was measured as a
file:line before it was written:

* `QueueManager` kept ONE `active_queue_item_id`, so two endpoints could not both be busy -- the
  second box would sit idle behind a render on the first;
* `get_comfy_runtime_manager` was one global rebuilt whenever host/port differed, so alternating
  endpoints would thrash it, and `run_comfy_workflow` calls `ensure_comfy_runtime`
  unconditionally -- a REMOTE job would have tried to start a LOCAL ComfyUI process;
* `request_comfy_free_memory` and `wait_until_comfy_queue_idle` accept an `api_url` and every
  caller omitted it, so a job on the second box would have unloaded models on the first -- the
  cross-firing /free trap, which is worse than doing nothing because it succeeds;
* the video runtime cache is one module global compared against the AMBIENT endpoint, so a local
  job alternating with a remote one would invalidate the remote's warm runtime every time, and
  every remote render would pay a cold start.

Everything here runs against stdlib HTTP servers stood up in-process. The real ComfyUI on :8188
and the real worker on :8765 are never touched.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))

import comfy_prompt_client as cpc  # noqa: E402
import worker_queue  # noqa: E402
import worker_runtime  # noqa: E402
import worker_service as ws  # noqa: E402


# --- two fake ComfyUIs ---------------------------------------------------------------------------

class FakeComfy:
    def __init__(self, name: str) -> None:
        self.name = name
        self.freed = 0
        self.hits: list[str] = []
        self._httpd: HTTPServer | None = None
        self._url = ""

    def start(self) -> "FakeComfy":
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self):  # noqa: N802
                outer.hits.append(f"GET {self.path}")
                if self.path == "/queue":
                    return self._json({"queue_running": [], "queue_pending": []})
                if self.path == "/system_stats":
                    return self._json({"system": {"comfyui_version": "0.34.0"}, "devices": []})
                return self._json({})

            def do_POST(self):  # noqa: N802
                outer.hits.append(f"POST {self.path}")
                length = int(self.headers.get("Content-Length") or 0)
                if length:
                    self.rfile.read(length)
                if self.path == "/free":
                    outer.freed += 1
                return self._json({"ok": True})

            def _json(self, payload):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self._httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self._url = f"http://127.0.0.1:{self._httpd.server_port}"
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

    @property
    def url(self) -> str:
        assert self._url
        return self._url


@pytest.fixture
def two_endpoints():
    a, b = FakeComfy("A").start(), FakeComfy("B").start()
    try:
        yield a, b
    finally:
        a.stop()
        b.stop()


# --- 1: the queue has a lane per endpoint ---------------------------------------------------------

class _LaneQueue(worker_queue.QueueManager):
    """A QueueManager whose items block instead of rendering, so lanes are observable."""

    def __init__(self, manifest_path) -> None:
        super().__init__(manifest_path=manifest_path)
        self.started: list[str] = []
        self.release = threading.Event()
        self._seen = threading.Event()

    def _run_queue_item(self, queue_item_id: str) -> None:
        self.started.append(queue_item_id)
        self._seen.set()
        self.release.wait(timeout=10.0)
        self._finalize_queue_item(queue_item_id)

    def wait_for_start(self, count: int, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and len(self.started) < count:
            time.sleep(0.01)


def _lane_queue(tmp_path) -> _LaneQueue:
    return _LaneQueue(manifest_path=tmp_path / "queue.json")


def _add(qm: worker_queue.QueueManager, qid: str, endpoint: str | None) -> None:
    req = {"command": "t2i", "prompt": "x"}
    if endpoint:
        req["comfy_api_url"] = endpoint
    item = worker_queue.QueueItem(queue_item_id=qid, command="t2i", request_snapshot=req)
    with qm.lock:
        qm.items[qid] = item
        qm.order.append(qid)
        qm.pending.append(qid)


def test_an_item_carries_the_endpoint_its_request_resolves_to(two_endpoints):
    a, _b = two_endpoints
    item = worker_queue.QueueItem(
        queue_item_id="q", command="t2i", request_snapshot={"comfy_api_url": a.url},
    )
    assert item.endpoint == a.url


def test_two_endpoints_run_concurrently(tmp_path, two_endpoints):
    a, b = two_endpoints
    qm = _lane_queue(tmp_path)
    _add(qm, "on_a", a.url)
    _add(qm, "on_b", b.url)
    with qm.lock:
        qm._start_next_locked()
    qm.wait_for_start(2)
    qm.release.set()
    assert sorted(qm.started) == ["on_a", "on_b"], qm.started


def test_a_second_job_on_the_same_endpoint_still_waits(tmp_path, two_endpoints):
    """One lane per endpoint, and inside a lane the queue stays strictly serial as it always was."""
    a, _b = two_endpoints
    qm = _lane_queue(tmp_path)
    _add(qm, "first", a.url)
    _add(qm, "second", a.url)
    with qm.lock:
        qm._start_next_locked()
    qm.wait_for_start(1)
    time.sleep(0.2)
    assert qm.started == ["first"]
    qm.release.set()
    qm.wait_for_start(2)
    assert qm.started == ["first", "second"]


def test_finishing_one_lane_does_not_release_the_other(tmp_path, two_endpoints):
    a, b = two_endpoints
    qm = _lane_queue(tmp_path)
    _add(qm, "a1", a.url)
    _add(qm, "b1", b.url)
    with qm.lock:
        qm._start_next_locked()
    qm.wait_for_start(2)
    with qm.lock:
        active = dict(qm.active_by_endpoint)
    assert active == {a.url: "a1", b.url: "b1"}, active
    qm._finalize_queue_item("a1")
    with qm.lock:
        assert qm.active_by_endpoint == {b.url: "b1"}
    qm.release.set()


def test_the_single_active_id_still_answers_for_one_endpoint(tmp_path, two_endpoints):
    """The snapshot the UI polls keeps its field; it is derived from the map, not a second copy."""
    a, _b = two_endpoints
    qm = _lane_queue(tmp_path)
    _add(qm, "only", a.url)
    with qm.lock:
        qm._start_next_locked()
    qm.wait_for_start(1)
    assert qm.active_queue_item_id == "only"
    assert qm.snapshot_payload()["active_queue_item_ids"] == {a.url: "only"}
    qm.release.set()


# --- 2: the runtime manager is per endpoint, and a remote one is never a process --------------------

def test_the_runtime_manager_is_keyed_by_endpoint_not_rebuilt(two_endpoints):
    a, b = two_endpoints
    first = ws.get_comfy_runtime_manager({"comfy_api_url": a.url})
    other = ws.get_comfy_runtime_manager({"comfy_api_url": b.url})
    again = ws.get_comfy_runtime_manager({"comfy_api_url": a.url})
    assert first is not other
    assert first is again, "asking for endpoint A again rebuilt its manager -- that is the thrash"


def test_a_remote_ensure_never_touches_the_local_process_manager(monkeypatch, two_endpoints):
    """run_comfy_workflow calls ensure_comfy_runtime unconditionally. For a remote endpoint that
    used to mean: start a ComfyUI process on THIS machine and then submit to the other one."""
    a, _b = two_endpoints
    remote = a.url.replace("127.0.0.1", "192.0.2.10")  # TEST-NET-1, never loopback

    def explode(*_a, **_k):
        raise AssertionError("the local ComfyUI process manager was consulted for a remote endpoint")

    monkeypatch.setattr(ws, "get_comfy_runtime_manager", explode)
    monkeypatch.setattr(ws, "_sync_comfy_extra_model_paths", explode)
    reply = ws.handle_ensure_comfy_runtime_command({"comfy_api_url": remote, "health_timeout_sec": 1.0})
    assert reply["endpoint"] == remote
    assert reply["healthy"] is False  # TEST-NET-1 does not answer; fail closed


def test_a_remote_ensure_is_a_health_probe_and_reports_healthy(monkeypatch, two_endpoints):
    a, _b = two_endpoints
    # is_local_endpoint is the one rule and it uses ipaddress.is_loopback, so a loopback fake would
    # take the local branch. Point the resolver at a non-loopback name that maps to the fake.
    monkeypatch.setattr(ws.comfy_endpoint_module, "is_local_endpoint", lambda req=None: False)
    reply = ws.handle_ensure_comfy_runtime_command({"comfy_api_url": a.url})
    assert reply["healthy"] is True
    assert reply["running"] is True
    assert reply["ownership"] == "external"
    assert "GET /system_stats" in a.hits


def test_a_remote_status_is_a_health_probe_too(monkeypatch, two_endpoints):
    """comfy_runtime_identity_snapshot asks for status; against a remote endpoint a LOCAL manager's
    process state is not an answer about that machine."""
    a, _b = two_endpoints
    monkeypatch.setattr(ws.comfy_endpoint_module, "is_local_endpoint", lambda req=None: False)
    reply = ws.handle_comfy_runtime_status_command({"comfy_api_url": a.url})
    assert reply["endpoint"] == a.url
    assert reply["healthy"] is True


# --- 3: /free goes to the endpoint the job is on -----------------------------------------------------

def _warm_video_cache(endpoint: str, signature: str = "sig-v") -> None:
    cache = worker_runtime.video_runtime_cache_for(endpoint)
    with worker_runtime.VIDEO_RUNTIME_LOCK:
        cache.update({
            "active_command": "t2v",
            "active_signature": signature,
            "comfy_runtime_endpoint": endpoint,
            "comfy_runtime_pid": 4242,
            "comfy_runtime_running": True,
            "comfy_runtime_healthy": True,
            "comfy_runtime_endpoint_alive": True,
        })


def test_free_goes_to_the_endpoint_the_job_is_on(monkeypatch, two_endpoints):
    """The cross-firing /free trap: a job on B unloading models on A succeeds and is wrong."""
    a, b = two_endpoints
    worker_runtime.forget_video_runtime_caches()
    _warm_video_cache(b.url)
    monkeypatch.setattr(worker_runtime, "image_runtime_cache_active", lambda: False)
    monkeypatch.setattr(worker_runtime, "clear_cuda_memory", lambda: {})
    monkeypatch.setattr(worker_runtime, "cuda_memory_snapshot", lambda: {})

    worker_runtime.prepare_runtime_for_request({"command": "t2i", "comfy_api_url": b.url})

    assert b.freed == 1, f"B was not asked to free: {b.hits}"
    assert a.freed == 0, f"A was freed for a job on B: {a.hits}"


def test_unload_all_runtimes_frees_the_endpoint_it_was_asked_about(monkeypatch, two_endpoints):
    a, b = two_endpoints
    monkeypatch.setattr(worker_runtime, "unload_cached_pipelines", lambda: {})
    monkeypatch.setattr(worker_runtime, "clear_cuda_memory", lambda: {})
    monkeypatch.setattr(worker_runtime, "runtime_memory_status_snapshot", lambda action: {"action": action})

    worker_runtime.handle_runtime_memory_control_command(
        {"command": "unload_all_runtimes", "comfy_api_url": b.url}
    )
    assert b.freed == 1
    assert a.freed == 0


def test_the_idle_wait_polls_the_endpoint_it_was_given(two_endpoints):
    a, b = two_endpoints
    assert cpc.wait_until_comfy_queue_idle(api_url=b.url, timeout_sec=3.0) is True
    assert any(h == "GET /queue" for h in b.hits)
    assert not any(h == "GET /queue" for h in a.hits)


# --- 4: a warm remote runtime survives an alternating local job ---------------------------------------

def test_a_warm_remote_runtime_survives_an_alternating_local_job(monkeypatch, two_endpoints):
    """One global cache compared against the ambient endpoint meant every alternation was a reset,
    so the second box would have paid a cold 22B load on every other render."""
    _a, b = two_endpoints
    worker_runtime.forget_video_runtime_caches()
    _warm_video_cache(b.url, "remote-sig")
    monkeypatch.setattr(worker_runtime, "image_runtime_cache_active", lambda: False)
    monkeypatch.setattr(worker_runtime, "clear_cuda_memory", lambda: {})
    monkeypatch.setattr(worker_runtime, "cuda_memory_snapshot", lambda: {})

    # A local video job on a different endpoint, whose own cache is cold.
    worker_runtime.prepare_runtime_for_request({"command": "t2v", "comfy_api_url": "http://127.0.0.1:8188"})

    remote = worker_runtime.video_runtime_cache_for(b.url)
    assert remote["active_signature"] == "remote-sig", (
        "the local job invalidated the remote endpoint's warm runtime"
    )


def test_each_endpoint_keeps_its_own_signature(two_endpoints):
    a, b = two_endpoints
    worker_runtime.forget_video_runtime_caches()
    _warm_video_cache(a.url, "sig-a")
    _warm_video_cache(b.url, "sig-b")
    assert worker_runtime.video_runtime_cache_for(a.url)["active_signature"] == "sig-a"
    assert worker_runtime.video_runtime_cache_for(b.url)["active_signature"] == "sig-b"


def test_resetting_one_endpoints_cache_leaves_the_other(two_endpoints):
    a, b = two_endpoints
    worker_runtime.forget_video_runtime_caches()
    _warm_video_cache(a.url, "sig-a")
    _warm_video_cache(b.url, "sig-b")
    worker_runtime.reset_video_runtime_cache("test", endpoint=a.url)
    assert worker_runtime.video_runtime_cache_for(a.url)["active_signature"] is None
    assert worker_runtime.video_runtime_cache_for(b.url)["active_signature"] == "sig-b"
