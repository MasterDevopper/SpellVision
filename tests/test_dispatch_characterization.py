"""G-dispatch characterization test (Doc 21 Pass 1 / Step 1).

Pins the CURRENT generation-dispatch behavior of BOTH dispatchers against unmodified
worker_service.py: for each path, which run_* target the dispatch resolves to, and the
native-image-fork decision. Drives the REAL dispatch (not a replica) by monkeypatching the
seven run_* module globals to recorders and invoking the actual code:

  * QUEUE dispatcher  -> QueueManager._run_queue_item  (reads item.command)
  * TCP-direct dispatcher -> WorkerTCPHandler.handle    (reads req["command"] or req["action"])

Includes ADVERSARIAL fixtures where the command keys deliberately disagree -- the only place
the plain-read precedence is observable. This test encodes today's behavior AS-IS (bugs
included, e.g. the TCP path having no native-image fork); it must pass against current code
BEFORE any C3 refactor touches the dispatch.
"""
from __future__ import annotations

import io
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))
import worker_service as ws  # noqa: E402

RUN_FUNCS = [
    "run_t2i", "run_i2i", "run_native_image", "run_comfy_workflow",
    "run_native_video", "run_ltx_prompt_api_queued_job", "run_noop_slow",
]

# A native-image family checkpoint path (classifier's filename layer -> flux -> native route).
FLUX_MODEL = "D:/AI_ASSETS/models/checkpoints/flux/fluxmania_kreamania.safetensors"
# A plain SDXL checkpoint (not a native-image family -> diffusers route).
SDXL_MODEL = "D:/AI_ASSETS/models/checkpoints/sdxl/some_sdxl.safetensors"


@pytest.fixture
def recorders(monkeypatch):
    """Patch every run_* to a recorder that logs which fired and returns a benign payload
    (so the surrounding job machinery completes without doing real work)."""
    calls: list[str] = []

    def make(name):
        def rec(req, emitter, job, active_job):
            calls.append(name)
            try:
                ws.transition_job(job, ws.JobState.COMPLETED)
            except Exception:
                pass
            return {"ok": True, "task_type": name}
        return rec

    for fn in RUN_FUNCS:
        monkeypatch.setattr(ws, fn, make(fn))
    return calls


def _observe_queue(recorders, *, item_command: str, req: dict) -> str:
    """Drive the REAL queue dispatcher for one item; return the run_* that fired (or 'RAISED:<msg>')."""
    qm = ws.QueueManager()
    qid = "qtest"
    item = ws.QueueItem(queue_item_id=qid, command=item_command, request_snapshot=dict(req))
    with qm.lock:
        qm.items[qid] = item
        qm.order.append(qid)
        qm.active_queue_item_id = qid
    del recorders[:]
    try:
        qm._run_queue_item(qid)
    except Exception as exc:  # dispatch's own try/except catches most; guard anyway
        if not recorders:
            return f"RAISED:{type(exc).__name__}:{exc}"
    return recorders[-1] if recorders else "NONE"


def _observe_tcp(recorders, *, req: dict) -> str:
    """Drive the REAL TCP-direct dispatcher via a fake-socket handler; return the run_* that fired."""
    handler = ws.WorkerTCPHandler.__new__(ws.WorkerTCPHandler)
    handler.rfile = io.BytesIO(json.dumps(req).encode("utf-8") + b"\n")
    handler.wfile = io.BytesIO()
    del recorders[:]
    try:
        handler.handle()
    except Exception as exc:
        if not recorders:
            return f"RAISED:{type(exc).__name__}:{exc}"
    return recorders[-1] if recorders else "NONE"


# --------------------------------------------------------------------------- QUEUE dispatcher

@pytest.mark.parametrize("item_command,req,expected", [
    # plain t2i/i2i: native-image fork present on the QUEUE path
    ("t2i", {"command": "t2i", "model": FLUX_MODEL}, "run_native_image"),
    ("t2i", {"command": "t2i", "model": SDXL_MODEL}, "run_t2i"),
    ("i2i", {"command": "i2i", "model": FLUX_MODEL}, "run_native_image"),
    ("i2i", {"command": "i2i", "model": SDXL_MODEL}, "run_i2i"),
    ("comfy_workflow", {"command": "comfy_workflow"}, "run_comfy_workflow"),
    # t2v/i2v: workflow-binding fork
    ("t2v", {"command": "t2v", "model": "wan.safetensors"}, "run_native_video"),
    ("t2v", {"command": "t2v", "workflow_path": "x.json"}, "run_comfy_workflow"),
    ("i2v", {"command": "i2v", "model": "wan.safetensors"}, "run_native_video"),
])
def test_queue_dispatch(recorders, item_command, req, expected):
    assert _observe_queue(recorders, item_command=item_command, req=req) == expected


def test_queue_reads_item_command_not_req_command(recorders):
    """ADVERSARIAL: the QUEUE plain switch reads item.command, NOT req['command'].
    item.command='t2i' but req['command']='i2i' -> resolves via item.command (t2i)."""
    got = _observe_queue(recorders, item_command="t2i", req={"command": "i2i", "model": SDXL_MODEL})
    assert got == "run_t2i", f"queue must read item.command (t2i), got {got}"


# --------------------------------------------------------------------------- TCP-direct dispatcher

@pytest.mark.parametrize("req,expected", [
    # NOTE: the TCP-direct path has NO native-image fork -> flux t2i still -> run_t2i (the C1 divergence).
    ({"command": "t2i", "model": FLUX_MODEL}, "run_t2i"),
    ({"command": "i2i", "model": FLUX_MODEL}, "run_i2i"),
    ({"command": "noop_slow"}, "run_noop_slow"),
    ({"command": "comfy_workflow"}, "run_comfy_workflow"),
    ({"command": "t2v", "model": "wan.safetensors"}, "run_native_video"),
    ({"command": "t2v", "workflow_path": "x.json"}, "run_comfy_workflow"),
])
def test_tcp_dispatch(recorders, req, expected):
    assert _observe_tcp(recorders, req=req) == expected


@pytest.mark.parametrize("req,expected", [
    # ADVERSARIAL: command vs task_command disagree -> the plain read uses 'command', task_command ignored.
    ({"command": "t2i", "task_command": "i2i", "model": SDXL_MODEL}, "run_t2i"),
    ({"command": "i2i", "task_command": "t2i", "model": SDXL_MODEL}, "run_i2i"),
    # ADVERSARIAL: 'command' absent, 'action' present -> the read falls back to 'action'.
    ({"action": "t2i", "model": SDXL_MODEL}, "run_t2i"),
])
def test_tcp_dispatch_adversarial_key_conflict(recorders, req, expected):
    assert _observe_tcp(recorders, req=req) == expected
