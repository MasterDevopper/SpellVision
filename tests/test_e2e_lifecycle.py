"""G-e2e Tier 1 -- the standing lifecycle & contract gate (Doc 21 §3).

Drives ONE job per generation path (t2i / i2i / t2v / comfy_workflow) through the
REAL spawned worker: the real client-normalized enqueue -> the real QueueManager ->
the real dispatch_generation -> a real terminal state. It asserts the JOB LIFECYCLE
and the RESULT/ERROR CONTRACT -- NOT a real render. That is what keeps it fast,
deterministic, and free of any dependency on model files or a live ComfyUI.

How it stays cheap without stubbing (the worker runs in a separate process, so we
cannot monkeypatch its run_* the way G-dispatch does): each request is shaped to
fail FAST inside its real dispatch target, BEFORE any model load or ComfyUI spawn --

  * t2i / i2i        : no ``model`` key            -> run_t2i/run_i2i raise KeyError
                       at get_or_load_pipelines(req["model"]) immediately.
  * t2v              : no model, no workflow binding -> family resolves to "unknown"
                       (validation_status=unsupported) -> the native-video validation
                       gate raises before _load_native_video_pipeline.
  * comfy_workflow   : no workflow_path / profile_path -> run_comfy_workflow raises
                       "requires workflow_path" before the managed-runtime ensure call.

So every path reaches a terminal FAILED with a well-formed error contract. Per the
known QUEUED->COMPLETED xfail the terminal state is asserted as "reaches terminal +
well-formed payload", not specifically COMPLETED. Tier 2 (a real-render smoke test,
marker-gated with skip-when-unavailable) is a separate follow-on, not this file.
"""

from __future__ import annotations

import os
import tempfile
import time

import pytest


# Queue-item states the run can legitimately end in. We expect FAILED here (no
# model / no ComfyUI), but per the QUEUED->COMPLETED xfail the contract we pin is
# "reaches a terminal state with a well-formed payload", not COMPLETED specifically.
TERMINAL_STATES = {"completed", "failed", "cancelled", "skipped"}

# Keys the queue snapshot's per-item payload contract must always carry -- even on
# failure. These are what the C++ shell's history/queue UI reads back.
CONTRACT_ITEM_KEYS = {
    "queue_item_id", "command", "state", "progress",
    "result", "error", "output", "metadata_output", "original_output", "timestamps",
}

# A short output stem keeps the queue's unique-path construction (which appends the
# queue_item_id to the stem) well under the 120-char truncation cap, so the full
# queue_item_id survives in item["output"] and we can assert construction happened.
_OUT_DIR = os.path.join(tempfile.gettempdir(), "spellvision_e2e")


def _out(name: str) -> str:
    # The path is never written (every job fails before os.makedirs), so the
    # directory need not exist -- it only has to be a plausible base output.
    return os.path.join(_OUT_DIR, name)


# task_command, request-shaped-to-fail-fast, output suffix
PATHS = [
    ("t2i", {"command": "enqueue", "task_command": "t2i", "output": _out("e2e_t2i.png")}),
    ("i2i", {"command": "enqueue", "task_command": "i2i", "output": _out("e2e_i2i.png")}),
    ("t2v", {"command": "enqueue", "task_command": "t2v", "output": _out("e2e_t2v.mp4")}),
    ("comfy_workflow", {"command": "enqueue", "task_command": "comfy_workflow", "output": _out("e2e_cw.png")}),
]


def _snapshot(worker_client) -> dict:
    """Poll the real queue for its current snapshot."""
    messages = worker_client({"command": "queue_status"}, timeout=10.0)
    snaps = [m for m in messages if m.get("type") == "queue_snapshot"]
    assert snaps, f"queue_status returned no queue_snapshot; got: {messages!r}"
    return snaps[-1]


def _find_item(snapshot: dict, queue_item_id: str) -> dict | None:
    for item in snapshot.get("items", []):
        if item.get("queue_item_id") == queue_item_id:
            return item
    return None


def _drive_to_terminal(worker_client, request: dict, *, timeout: float = 20.0) -> tuple[dict, dict]:
    """Enqueue one request and poll until its queue item reaches a terminal state.

    Returns (enqueue_ack, terminal_item). Fails the test if the job never reaches a
    terminal state within the (generous, but never actually hit) timeout budget.
    """
    ack_messages = worker_client(request, timeout=15.0)
    acks = [m for m in ack_messages if m.get("queue_item_id")]
    assert acks, f"enqueue produced no ack carrying a queue_item_id; got: {ack_messages!r}"
    ack = acks[-1]
    queue_item_id = ack["queue_item_id"]

    deadline = time.monotonic() + timeout
    last_item: dict | None = None
    while time.monotonic() < deadline:
        item = _find_item(_snapshot(worker_client), queue_item_id)
        if item is not None:
            last_item = item
            if item.get("state") in TERMINAL_STATES:
                return ack, item
        time.sleep(0.1)

    raise AssertionError(
        f"queue item {queue_item_id} never reached a terminal state within {timeout:.0f}s; "
        f"last observed: {last_item!r}"
    )


@pytest.mark.parametrize("task_command,request_payload", PATHS, ids=[p[0] for p in PATHS])
def test_generation_path_reaches_terminal_with_wellformed_contract(worker_client, task_command, request_payload):
    """Each generation path: accepted -> queued -> dispatched -> terminal, with a
    well-formed result/error contract. Real queue + real dispatch_generation, no render."""
    ack, item = _drive_to_terminal(worker_client, dict(request_payload))

    # --- accepted: the enqueue ack is well-formed and carries the identifiers ---
    assert ack.get("ok") is True, f"enqueue not ok: {ack!r}"
    assert ack.get("action") == "enqueue", f"enqueue action wrong: {ack.get('action')!r}"
    assert isinstance(ack.get("job_id"), str) and ack["job_id"], f"enqueue lacks a job_id: {ack!r}"

    # --- appears in the queue with the command/task_type echoed back correctly ---
    assert item["command"] == task_command, (
        f"queue echoed command {item['command']!r}, expected {task_command!r}"
    )

    # --- transitioned through real states to a terminal state ---
    assert item["state"] in TERMINAL_STATES, (
        f"{task_command} did not reach a terminal state; state={item['state']!r}"
    )

    # --- the per-item contract keys are all present (even on failure) ---
    missing = CONTRACT_ITEM_KEYS - set(item.keys())
    assert not missing, f"queue item missing contract keys {missing}; item keys: {sorted(item.keys())}"

    # --- output path was CONSTRUCTED through the queue (unique stem = base + queue_item_id) ---
    output = item.get("output")
    assert isinstance(output, str) and output, f"item output not constructed: {output!r}"
    assert item["queue_item_id"] in output, (
        f"constructed output {output!r} does not carry the queue_item_id "
        f"{item['queue_item_id']!r} (queue path construction did not run)"
    )

    # --- the terminal payload has the right SHAPE for whichever terminal it is ---
    if item["state"] == "failed":
        err = item.get("error")
        assert isinstance(err, dict), f"failed item has no error dict: {err!r}"
        assert isinstance(err.get("code"), str) and err["code"], f"error missing code: {err!r}"
        assert isinstance(err.get("message"), str) and err["message"], f"error missing message: {err!r}"
    elif item["state"] == "completed":
        res = item.get("result")
        assert isinstance(res, dict), f"completed item has no result dict: {res!r}"
        assert res.get("output"), f"completed result missing output: {res!r}"
