"""G-e2e Tier 2 -- milestone render smoke (Doc 21 §3).

One GENUINE generation per path (t2i / i2i / t2v / comfy_workflow) driven through the
real spawned worker with a REAL checkpoint on disk and a LIVE ComfyUI, asserting that
an actual output FILE appears and is non-trivial (non-zero size, right extension).

THE TIER BOUNDARY (see also test_e2e_lifecycle.py):
  * Tier 1 (test_e2e_lifecycle.py) = PLUMBING: lifecycle + contract, runs every pass,
    no models/ComfyUI. Green means the job routes + completes + the result is well-formed.
  * Tier 2 (this file, @pytest.mark.smoke) = RENDERS: real output files. Runs at
    milestones via `pytest -m smoke`. Only Tier 2 green means "a video/image actually
    rendered."
Neither tier substitutes for the other.

ENVIRONMENT-DEPENDENT BY NATURE -- so it SKIPS, never FAILS, on a bare machine:
  * every test is @pytest.mark.smoke and is NOT collected by the default `pytest` run
    (pytest.ini sets addopts = -m "not smoke"); it runs only under `pytest -m smoke`;
  * a guard checks ComfyUI is reachable on :8188 AND a matching checkpoint exists on
    disk, and pytest.skip(...)s cleanly when either is absent. A RED Tier 2 therefore
    means "a real render regressed", never "this machine lacked the models today".

The worker itself is guaranteed up by the session-scoped worker_client fixture; the
extra availability the render needs (ComfyUI + a checkpoint) is what the guard covers.
"""

from __future__ import annotations

import os
import time
import urllib.request
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke


# --------------------------------------------------------------------------- availability guard
# (the load-bearing safety property: absence -> SKIP, never ERROR / FAIL)

_COMFY_STATS_URL = "http://127.0.0.1:8188/system_stats"

# Checkpoint roots, env-overridable. The default is the resolved asset root (CLAUDE.md
# §9: D:/AI_ASSETS). Missing / unreadable roots degrade to "not found", never raise.
_CHECKPOINT_ROOTS = [
    Path(os.environ.get("SPELLVISION_ASSET_ROOT", "D:/AI_ASSETS")) / "models" / "checkpoints",
]
_IMPORTED_WORKFLOWS_ROOT = Path(__file__).resolve().parent.parent / "runtime" / "imported_workflows"


def _comfy_reachable(timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(_COMFY_STATS_URL, timeout=timeout) as resp:
            return 200 <= getattr(resp, "status", resp.getcode()) < 300
    except Exception:
        return False


def _find_checkpoint(keywords: tuple[str, ...]) -> Path | None:
    """First *.safetensors whose path (dir or filename, lowercased) matches any keyword.
    Any filesystem error (missing root, permissions) degrades to None -- never raises."""
    for root in _CHECKPOINT_ROOTS:
        try:
            if not root.is_dir():
                continue
            for path in root.rglob("*.safetensors"):
                hay = str(path).lower()
                if any(k in hay for k in keywords):
                    return path
        except OSError:
            continue
    return None


def _find_imported_workflow() -> Path | None:
    try:
        if not _IMPORTED_WORKFLOWS_ROOT.is_dir():
            return None
        for name in ("workflow.json", "prompt_api.json"):
            for path in _IMPORTED_WORKFLOWS_ROOT.glob(f"*/{name}"):
                if path.is_file():
                    return path
    except OSError:
        return None
    return None


def _require_render_env(*, model_keywords: tuple[str, ...] | None = None,
                        need_workflow: bool = False) -> dict:
    """Return the discovered assets, or pytest.skip cleanly if the env can't render.
    This is the ONLY place a bare environment is turned into a SKIP (not a FAIL)."""
    if not _comfy_reachable():
        pytest.skip("real model / ComfyUI not available: ComfyUI not reachable on 127.0.0.1:8188")

    assets: dict = {}
    if model_keywords is not None:
        model = _find_checkpoint(model_keywords)
        if model is None:
            pytest.skip(
                f"real model / ComfyUI not available: no checkpoint matching {model_keywords} "
                f"under {[str(r) for r in _CHECKPOINT_ROOTS]}"
            )
        assets["model"] = str(model)
    if need_workflow:
        workflow = _find_imported_workflow()
        if workflow is None:
            pytest.skip(f"real model / ComfyUI not available: no imported workflow under {_IMPORTED_WORKFLOWS_ROOT}")
        assets["workflow_path"] = str(workflow)
    return assets


# --------------------------------------------------------------------------- render helpers

_MEDIA_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".webm", ".gif"}


def _snapshot(worker_client) -> dict:
    messages = worker_client({"command": "queue_status"}, timeout=10.0)
    snaps = [m for m in messages if m.get("type") == "queue_snapshot"]
    assert snaps, f"queue_status returned no queue_snapshot; got: {messages!r}"
    return snaps[-1]


def _find_item(snapshot: dict, queue_item_id: str) -> dict | None:
    for item in snapshot.get("items", []):
        if item.get("queue_item_id") == queue_item_id:
            return item
    return None


def _render_to_completion(worker_client, request: dict, *, timeout: float) -> dict:
    """Enqueue a real generation and poll until it COMPLETES (or fails/errors -> the
    test asserts on the terminal state, so a genuine failure surfaces as red)."""
    ack_messages = worker_client(request, timeout=30.0)
    acks = [m for m in ack_messages if m.get("queue_item_id")]
    assert acks, f"enqueue produced no ack with a queue_item_id; got: {ack_messages!r}"
    queue_item_id = acks[-1]["queue_item_id"]

    deadline = time.monotonic() + timeout
    last_item: dict | None = None
    terminal = {"completed", "failed", "cancelled", "skipped"}
    while time.monotonic() < deadline:
        item = _find_item(_snapshot(worker_client), queue_item_id)
        if item is not None:
            last_item = item
            if item.get("state") in terminal:
                return item
        time.sleep(0.5)
    raise AssertionError(
        f"render {queue_item_id} did not reach a terminal state within {timeout:.0f}s; "
        f"last observed: {last_item!r}"
    )


def _assert_output_file(item: dict) -> None:
    """A real render must COMPLETE and leave a non-trivial output file on disk."""
    assert item["state"] == "completed", (
        f"real render did not complete: state={item['state']!r} error={item.get('error')!r}"
    )
    result = item.get("result") if isinstance(item.get("result"), dict) else {}
    output = str(result.get("output") or item.get("output") or "").strip()
    assert output, f"completed render reported no output path: {item!r}"

    path = Path(output)
    assert path.is_file(), f"render output file does not exist on disk: {output!r}"
    assert path.stat().st_size > 0, f"render output file is empty (0 bytes): {output!r}"
    assert path.suffix.lower() in _MEDIA_SUFFIXES, f"render output has unexpected extension: {output!r}"


# --------------------------------------------------------------------------- the smoke tests

def test_smoke_t2i_real_render(worker_client, tmp_path):
    env = _require_render_env(model_keywords=("sdxl",))
    item = _render_to_completion(
        worker_client,
        {
            "command": "enqueue", "task_command": "t2i",
            "model": env["model"],
            "prompt": "a red cube on a white table, studio lighting",
            "negative_prompt": "",
            "width": 768, "height": 768, "steps": 8, "cfg": 6.0, "seed": 12345,
            "sampler": "euler_a", "scheduler": "normal",
            "output": str(tmp_path / "smoke_t2i.png"),
        },
        timeout=300.0,
    )
    _assert_output_file(item)


def test_smoke_i2i_real_render(worker_client, tmp_path):
    env = _require_render_env(model_keywords=("sdxl",))
    # A real input image on disk (created locally so the test is self-contained).
    from PIL import Image
    input_image = tmp_path / "smoke_i2i_input.png"
    Image.new("RGB", (768, 768), (32, 64, 128)).save(input_image, "PNG")

    item = _render_to_completion(
        worker_client,
        {
            "command": "enqueue", "task_command": "i2i",
            "model": env["model"],
            "input_image": str(input_image),
            "prompt": "a blue gradient turned into a painted sky",
            "negative_prompt": "",
            "width": 768, "height": 768, "steps": 8, "cfg": 6.0, "seed": 777,
            "strength": 0.6, "sampler": "euler_a", "scheduler": "normal",
            "output": str(tmp_path / "smoke_i2i.png"),
        },
        timeout=300.0,
    )
    _assert_output_file(item)


def test_smoke_t2v_real_render(worker_client, tmp_path):
    env = _require_render_env(model_keywords=("ltx",))
    item = _render_to_completion(
        worker_client,
        {
            "command": "enqueue", "task_command": "t2v",
            "model": env["model"], "video_family": "ltx",
            "prompt": "a calm ocean wave rolling toward the shore",
            "width": 768, "height": 512, "num_frames": 49, "fps": 16,
            "steps": 12, "cfg": 3.0, "seed": 42,
            "output": str(tmp_path / "smoke_t2v.mp4"),
        },
        timeout=900.0,
    )
    _assert_output_file(item)


def test_smoke_comfy_workflow_real_render(worker_client, tmp_path):
    env = _require_render_env(need_workflow=True)
    item = _render_to_completion(
        worker_client,
        {
            "command": "enqueue", "task_command": "comfy_workflow",
            "workflow_path": env["workflow_path"],
            "output": str(tmp_path / "smoke_cw.png"),
        },
        timeout=600.0,
    )
    _assert_output_file(item)
