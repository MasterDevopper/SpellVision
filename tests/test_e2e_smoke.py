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


def _find_wan_dual_experts() -> tuple[Path, Path] | None:
    """Discover a Wan 2.2 high-noise + low-noise expert PAIR on disk (for the dual-noise MoE smoke).
    Returns (high, low) or None. Any filesystem error degrades to None -- never raises."""
    high: Path | None = None
    low: Path | None = None
    for root in _CHECKPOINT_ROOTS:
        try:
            if not root.is_dir():
                continue
            for path in root.rglob("*.safetensors"):
                hay = str(path).lower()
                if "wan" not in hay:
                    continue
                if high is None and ("high_noise" in hay or "t2v_high" in hay or "_high_" in hay):
                    high = path
                elif low is None and ("low_noise" in hay or "t2v_low" in hay or "_low_" in hay):
                    low = path
        except OSError:
            continue
    return (high, low) if (high and low) else None


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


def test_smoke_t2v_wan_dual_noise_real_render(worker_client, tmp_path):
    """Wan 2.2 A14B dual-expert (MoE) T2V render -- the REAL acceptance gate for the dual-noise builder.
    The graph gate proves STRUCTURE; per the banked principle a coherent image-following render is the
    only acceptance for video. Skips cleanly when ComfyUI is down or both experts aren't on disk, so a
    bare machine never goes red. Run manually at the milestone with both experts present + ComfyUI up."""
    if not _comfy_reachable():
        pytest.skip("real model / ComfyUI not available: ComfyUI not reachable on 127.0.0.1:8188")
    experts = _find_wan_dual_experts()
    if experts is None:
        pytest.skip(
            "real model / ComfyUI not available: no Wan 2.2 high+low-noise expert pair found under "
            f"{[str(r) for r in _CHECKPOINT_ROOTS]}"
        )
    high, low = experts
    item = _render_to_completion(
        worker_client,
        {
            "command": "enqueue", "task_command": "t2v",
            "video_family": "wan",
            "native_video_stack_kind": "wan_dual_noise",
            "video_model_stack": {
                "stack_kind": "wan_dual_noise",
                "high_noise_path": str(high),
                "low_noise_path": str(low),
            },
            "prompt": "a calm ocean wave rolling toward the shore, cinematic",
            "width": 832, "height": 480, "num_frames": 81, "fps": 16,
            # Base-model budget (NOT the Lightx2v 4-step/cfg-1 config).
            "steps": 20, "cfg": 3.5, "seed": 42,
            "output": str(tmp_path / "smoke_t2v_wan_dual.mp4"),
        },
        timeout=1200.0,
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


def _find_wan_dual_i2v_experts() -> tuple[Path, Path] | None:
    """Official Wan 2.2 i2v high+low pair under diffusion_models. Skip, never raise."""
    high_name = "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors"
    low_name = "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors"
    roots = [
        Path(os.environ.get("SPELLVISION_ASSET_ROOT", "D:/AI_ASSETS")) / "models" / "diffusion_models",
    ]
    high = low = None
    for root in roots:
        try:
            if not root.is_dir():
                continue
            cand_h = root / high_name
            cand_l = root / low_name
            if cand_h.is_file():
                high = cand_h
            if cand_l.is_file():
                low = cand_l
        except OSError:
            continue
    return (high, low) if (high and low) else None


def _first_frame_png(video: Path, dest: Path) -> Path:
    import subprocess
    dest.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        ["ffmpeg", "-y", "-i", str(video), "-vframes", "1", str(dest)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0 or not dest.is_file():
        raise AssertionError(
            f"ffmpeg could not extract frame 0 from {video}: {completed.stderr[-400:]}"
        )
    return dest


def _rgb_mae(a_path: Path, b_path: Path) -> float:
    from PIL import Image
    import numpy as np
    with Image.open(a_path) as a, Image.open(b_path) as b:
        a_rgb = a.convert("RGB")
        b_rgb = b.convert("RGB").resize(a_rgb.size, Image.Resampling.BILINEAR)
        aa = np.asarray(a_rgb, dtype=np.float32)
        bb = np.asarray(b_rgb, dtype=np.float32)
    return float(np.mean(np.abs(aa - bb)))


def test_smoke_i2v_wan_dual_noise_real_render(worker_client, tmp_path):
    """Wan 2.2 dual-noise i2v render-proof (Doc 27 §1.2). Structure tests are not this gate."""
    if not _comfy_reachable():
        pytest.skip("real model / ComfyUI not available: ComfyUI not reachable on 127.0.0.1:8188")
    experts = _find_wan_dual_i2v_experts()
    if experts is None:
        pytest.skip(
            "real model / ComfyUI not available: official Wan 2.2 i2v high+low pair missing under "
            "D:/AI_ASSETS/models/diffusion_models"
        )
    high, low = experts
    key_src = Path(__file__).resolve().parent.parent / "runtime" / "style" / "hunt" / "locktest_human_002style_01.png"
    if not key_src.is_file():
        pytest.skip(f"i2v keyframe missing: {key_src}")
    from PIL import Image
    keyframe = tmp_path / "i2v_keyframe.png"
    with Image.open(key_src) as im:
        im.convert("RGB").resize((832, 480), Image.Resampling.LANCZOS).save(keyframe, "PNG")

    item = _render_to_completion(
        worker_client,
        {
            "command": "enqueue",
            "task_command": "i2v",
            "video_family": "wan",
            "native_video_stack_kind": "wan_dual_noise",
            "video_model_stack": {
                "stack_kind": "wan_dual_noise",
                "high_noise_path": str(high),
                "low_noise_path": str(low),
            },
            "input_image": str(keyframe),
            "prompt": "the figure turns slightly toward camera, hair moves, cinematic",
            "width": 832,
            "height": 480,
            "num_frames": 49,
            "fps": 16,
            # Short explicit budget. FAST Lightx2v LoRAs are t2v-named and not on disk here.
            "steps": 8,
            "cfg": 3.5,
            "seed": 42,
            "output": str(tmp_path / "smoke_i2v_wan_dual.mp4"),
        },
        timeout=1200.0,
    )
    _assert_output_file(item)
    result = item.get("result") if isinstance(item.get("result"), dict) else {}
    video = Path(str(result.get("output") or item.get("output") or ""))
    frame0 = _first_frame_png(video, tmp_path / "smoke_i2v_wan_dual_frame0.png")
    mae = _rgb_mae(frame0, keyframe)
    assert mae < 12.0, f"Wan 2.2 dual-noise i2v frame-0 MAE {mae:.2f} exceeds pin bar 12 (LTX 3.5 / Wan-2.1 3.54)"
