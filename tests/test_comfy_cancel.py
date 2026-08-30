"""Cancel has to cross the process boundary, and it has to stop at the right prompt.

Before this, cancelling stopped SpellVision polling and nothing else: ComfyUI rendered the prompt to
completion holding 20+ GB, while the UI showed a clean cancel. The dangerous half of the fix is the
new one -- ``/interrupt`` takes no prompt id, so an over-eager cancel kills whatever happens to be
running, which may belong to somebody else's ComfyUI tab. These tests pin both directions: the
cancel reaches ComfyUI, and it does not reach past it.

Hermetic by construction: ``urlopen`` is replaced, so nothing here opens a socket.
"""
from __future__ import annotations

import io
import json
import sys
import threading
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

import comfy_cancel  # noqa: E402
from worker_service_state import (  # noqa: E402
    ActiveJobHandle,
    JobRecord,
    JobState,
    register_active_job,
    request_job_cancel,
    unregister_active_job,
)

API = "http://127.0.0.1:8188"


class _Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class FakeComfy:
    """A ComfyUI that records what was asked of it."""

    def __init__(self, *, running=(), pending=(), queue_error=None):
        self.queue_payload = {
            # The real shape: [number, prompt_id, prompt, extra_data, outputs].
            "queue_running": [[0, pid, {}, {}, []] for pid in running],
            "queue_pending": [[1, pid, {}, {}, []] for pid in pending],
        }
        self.queue_error = queue_error
        self.posts: list[tuple[str, dict]] = []

    def urlopen(self, request, timeout=None):
        url = request if isinstance(request, str) else request.full_url
        data = None if isinstance(request, str) else request.data
        if url.endswith("/queue") and data is None:
            if self.queue_error:
                raise self.queue_error
            return _Response(json.dumps(self.queue_payload).encode())
        body = json.loads(data.decode()) if data else {}
        self.posts.append((url.rsplit("/", 1)[-1], body))
        return _Response(b"{}")

    @property
    def actions(self) -> list[str]:
        return [path for path, _ in self.posts]


@pytest.fixture
def comfy(monkeypatch):
    def _install(**kwargs):
        fake = FakeComfy(**kwargs)
        monkeypatch.setattr(comfy_cancel.urllib.request, "urlopen", fake.urlopen)
        return fake
    return _install


# --- where the prompt is decides what we do -------------------------------------------------------

def test_a_running_prompt_is_interrupted(comfy):
    fake = comfy(running=["p1"])
    outcome = comfy_cancel.cancel_prompt(API, "p1")
    assert outcome["state"] == "running"
    assert fake.actions == ["interrupt"]
    assert outcome["ok"]


def test_a_pending_prompt_is_deleted_and_never_interrupted(comfy):
    """The load-bearing case.

    /interrupt has no prompt id, so interrupting while OUR prompt merely sits in the queue would
    kill whatever is executing -- plausibly a render started from ComfyUI's own web UI against the
    same instance. Deleting from the queue is precise; interrupting is not.
    """
    fake = comfy(running=["someone-elses"], pending=["p1"])
    outcome = comfy_cancel.cancel_prompt(API, "p1")
    assert outcome["state"] == "pending"
    assert fake.actions == ["queue"]
    assert "interrupt" not in fake.actions
    assert fake.posts[0][1] == {"delete": ["p1"]}


def test_an_absent_prompt_does_nothing_and_says_so(comfy):
    fake = comfy(running=["other"], pending=[])
    outcome = comfy_cancel.cancel_prompt(API, "p1")
    assert outcome["state"] == "absent"
    assert fake.actions == []
    # Not an error. A cancel that arrived after the render finished did its job.
    assert outcome["ok"]


def test_an_unreadable_queue_falls_back_to_both(comfy):
    """Only here is the blunt instrument justified: we cannot see what is running.

    Losing an unrelated render is the lesser harm against leaving 20+ GB pinned by a job the user
    cancelled, and a ComfyUI that will not answer /queue is usually one SpellVision started.
    """
    fake = comfy(queue_error=urllib.error.URLError("connection refused"))
    outcome = comfy_cancel.cancel_prompt(API, "p1")
    assert outcome["state"] == "unknown"
    assert set(fake.actions) == {"queue", "interrupt"}
    assert not outcome["ok"]
    assert any("unreadable" in e for e in outcome["errors"])


def test_an_empty_prompt_id_is_refused_rather_than_broadcast(comfy):
    fake = comfy(running=["p1"])
    outcome = comfy_cancel.cancel_prompt(API, "")
    assert not outcome["ok"]
    assert fake.actions == []


def test_a_failed_interrupt_is_reported_not_raised(monkeypatch, comfy):
    fake = comfy(running=["p1"])

    def explode(request, timeout=None):
        if not isinstance(request, str) and request.data is not None:
            raise TimeoutError("read timed out")
        return fake.urlopen(request, timeout)

    monkeypatch.setattr(comfy_cancel.urllib.request, "urlopen", explode)
    outcome = comfy_cancel.cancel_prompt(API, "p1")
    # TimeoutError is an OSError and NOT a URLError. A URLError-only handler here would let a
    # transport hiccup during a cancel surface as a crash instead of a cancel.
    assert not outcome["ok"]
    assert "TimeoutError" in outcome["errors"][0]


def test_queue_entries_of_an_unexpected_shape_do_not_produce_a_confident_wrong_answer():
    assert comfy_cancel._prompt_ids("not a list") == set()
    assert comfy_cancel._prompt_ids([["only-one-element"]]) == set()
    assert comfy_cancel._prompt_ids([{"prompt_id": "p1"}]) == {"p1"}
    assert comfy_cancel._prompt_ids([[0, "p1", {}, {}, []]]) == {"p1"}


# --- the handle carries the hooks -----------------------------------------------------------------

def _handle() -> ActiveJobHandle:
    return ActiveJobHandle(job=JobRecord(job_id="job-1", command="t2i", state=JobState.RUNNING))


def test_a_hook_registered_after_the_cancel_still_runs():
    """The race this closes: a submission that lands between the cancel and the poll check.

    Without it the prompt id is registered on a job already cancelled, nobody fires the hook, and
    the render runs to completion -- the exact bug, reintroduced by timing.
    """
    handle = _handle()
    handle.cancel_event.set()
    fired = []
    handle.add_cancel_hook(lambda: fired.append("late"))
    assert fired == ["late"]


def test_hooks_are_drained_so_a_second_cancel_is_not_a_second_interrupt():
    handle = _handle()
    fired = []
    handle.add_cancel_hook(lambda: fired.append(1))
    handle.run_cancel_hooks()
    handle.run_cancel_hooks()
    assert fired == [1]


def test_one_failing_hook_does_not_strand_the_others():
    handle = _handle()
    fired = []

    def boom():
        raise RuntimeError("comfy is gone")

    handle.add_cancel_hook(boom)
    handle.add_cancel_hook(lambda: fired.append("second"))
    outcomes = handle.run_cancel_hooks()
    assert fired == ["second"]
    assert outcomes[0]["ok"] is False


def test_requesting_a_cancel_fires_the_hooks():
    handle = _handle()
    fired = []
    handle.add_cancel_hook(lambda: fired.append("comfy"))
    assert register_active_job(handle)
    try:
        accepted, job = request_job_cancel("job-1")
    finally:
        unregister_active_job("job-1", handle)
    assert accepted
    assert job is handle.job
    assert fired == ["comfy"], "a cancel that does not reach ComfyUI leaves the GPU held"


def test_hooks_registered_from_another_thread_are_not_lost():
    handle = _handle()
    fired = []
    barrier = threading.Barrier(2)

    def register():
        barrier.wait()
        handle.add_cancel_hook(lambda: fired.append("t"))

    worker = threading.Thread(target=register)
    worker.start()
    barrier.wait()
    worker.join()
    handle.run_cancel_hooks()
    assert fired == ["t"]


# --- the submitter wires the two together ----------------------------------------------------------

def test_the_shared_submitter_registers_a_hook_for_the_prompt_it_started(monkeypatch, comfy):
    import comfy_prompt_client

    def fake_urlopen(request, timeout=None):
        return _Response(json.dumps({"prompt_id": "abc123"}).encode())

    monkeypatch.setattr(comfy_prompt_client.urllib.request, "urlopen", fake_urlopen)
    handle = _handle()
    prompt_id = comfy_prompt_client._submit_comfy_prompt(API, {"1": {}}, handle)

    assert prompt_id == "abc123"
    assert len(handle.cancel_hooks) == 1
    assert handle.cancel_hooks[0][0] == "comfy:abc123"

    fake = comfy(running=["abc123"])
    handle.run_cancel_hooks()
    assert fake.actions == ["interrupt"]


def test_a_submitter_given_no_handle_still_returns_the_prompt_id(monkeypatch):
    """The synchronous helpers that submit outside the job lanes must keep working."""
    import comfy_prompt_client

    monkeypatch.setattr(
        comfy_prompt_client.urllib.request, "urlopen",
        lambda request, timeout=None: _Response(json.dumps({"prompt_id": "solo"}).encode()),
    )
    assert comfy_prompt_client._submit_comfy_prompt(API, {"1": {}}) == "solo"


# --- the cancel COMMAND has to be honest about what it reached ------------------------------------

def test_a_failed_backend_cancel_is_recorded_on_the_handle(comfy):
    """The queue lane reads this to decide whether the cancel it just did was a real one."""
    import worker_queue

    fake = comfy(queue_error=urllib.error.URLError("refused"))
    handle = _handle()
    handle.add_cancel_hook(lambda: comfy_cancel.cancel_prompt(API, "p1"))
    handle.run_cancel_hooks()

    assert set(fake.actions) == {"queue", "interrupt"}
    failures = worker_queue._failed_backend_cancels(handle)
    assert len(failures) == 1, "a cancel that could not read the queue must not look clean"


def test_a_successful_backend_cancel_leaves_nothing_to_report(comfy):
    import worker_queue

    comfy(running=["p1"])
    handle = _handle()
    handle.add_cancel_hook(lambda: comfy_cancel.cancel_prompt(API, "p1"))
    handle.run_cancel_hooks()
    assert worker_queue._failed_backend_cancels(handle) == []


def test_no_handle_means_nothing_to_report_not_a_failure():
    """A job with no out-of-process work is a clean cancel, not an unknown one."""
    import worker_queue

    assert worker_queue._failed_backend_cancels(None) == []
