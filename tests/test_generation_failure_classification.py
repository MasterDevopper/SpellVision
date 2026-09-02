"""A defect and a bad request must not read the same on the pill beside Generate.

The first live T2I after the 2026-09-01 security pass failed with
`module 'worker_service' has no attribute 'resolve_comfy_output_path'`, shown to the user as if it
were their doing. The queue runner now classifies before it emits: programming-error types get code
`internal_error` and a message that says so; everything else keeps its message and the
`generation_error` code the rest of the system already keys on.

Two lanes: the classifier alone, and the REAL queue runner (`QueueManager._run_queue_item`) with
dispatch monkeypatched to raise, read back from the manifest it persisted.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import generation_failure as gf  # noqa: E402
import worker_service as ws  # noqa: E402


@pytest.mark.parametrize("exc", [
    AttributeError("module 'worker_service' has no attribute 'resolve_comfy_output_path'"),
    KeyError("model"),
    TypeError("build_graph() missing 1 required positional argument: 'req'"),
    NameError("name '_snap16' is not defined"),
])
def test_programming_errors_are_labelled_internal(exc):
    code, message = gf.classify_failure(exc)
    assert code == gf.INTERNAL_ERROR_CODE
    assert message.startswith(gf.INTERNAL_ERROR_PREFIX)
    assert type(exc).__name__ in message
    # The original text survives: a report needs it.
    assert str(exc).strip("'") in message


@pytest.mark.parametrize("exc", [
    ValueError("width must be a multiple of 16"),
    FileNotFoundError("checkpoint not found: x.safetensors"),
    RuntimeError("ComfyUI returned 400: value_not_in_list"),
    OSError("[WinError 10054] connection reset"),
])
def test_user_and_environment_errors_keep_their_message(exc):
    code, message = gf.classify_failure(exc)
    assert code == gf.GENERATION_ERROR_CODE
    assert message == str(exc)


def test_an_empty_message_falls_back_to_the_type_name():
    code, message = gf.classify_failure(RuntimeError())
    assert code == gf.GENERATION_ERROR_CODE
    assert message == "RuntimeError"


def _run_one_item_that_raises(tmp_path: Path, monkeypatch, exc: BaseException) -> dict:
    def boom(*_args, **_kwargs):
        raise exc

    monkeypatch.setattr(ws, "dispatch_generation", boom)
    manifest = tmp_path / "queue_manifest.json"
    qm = ws.QueueManager(manifest_path=manifest)
    qid = "qfail"
    req = {
        "command": "t2i", "task_type": "t2i", "prompt": "x",
        "model": str(tmp_path / "some_sdxl.safetensors"),
        "width": 64, "height": 64, "steps": 1, "cfg": 1.0, "seed": 1,
        "output": str(tmp_path / "o.png"), "metadata_output": str(tmp_path / "o.json"),
    }
    item = ws.QueueItem(queue_item_id=qid, command="t2i", request_snapshot=dict(req))
    with qm.lock:
        qm.items[qid] = item
        qm.order.append(qid)
        qm.active_queue_item_id = qid
    qm._run_queue_item(qid)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    items = data["items"]
    if isinstance(items, dict):
        return items[qid]
    return next(e for e in items if qid in (e.get("id"), e.get("queue_item_id")))


def test_the_real_queue_runner_records_an_internal_error_code(tmp_path, monkeypatch):
    entry = _run_one_item_that_raises(
        tmp_path, monkeypatch,
        AttributeError("module 'worker_service' has no attribute 'resolve_comfy_output_path'"),
    )
    assert entry["state"] == "failed"
    assert entry["error"]["code"] == gf.INTERNAL_ERROR_CODE
    assert entry["error"]["message"].startswith(gf.INTERNAL_ERROR_PREFIX)
    assert "resolve_comfy_output_path" in entry["error"]["message"]
    assert "Traceback" in (entry["error"].get("traceback") or "")


def test_the_real_queue_runner_keeps_generation_error_for_a_bad_request(tmp_path, monkeypatch):
    entry = _run_one_item_that_raises(tmp_path, monkeypatch, ValueError("width must be a multiple of 16"))
    assert entry["state"] == "failed"
    assert entry["error"]["code"] == gf.GENERATION_ERROR_CODE
    assert entry["error"]["message"] == "width must be a multiple of 16"
