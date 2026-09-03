"""What a per-frame ESRGAN upscale costs, before deciding whether to offer one for video.

The image route grafts UpscaleModelLoader -> ImageUpscaleWithModel after decode. For video the same
graft would run over every frame, and the cost is driven by OUTPUT pixels, not by the model's
weights. This measures where that lands on a 32 GB card, so the decision is a number rather than an
intuition.

Peak VRAM is sampled by polling /system_stats during execution -- ComfyUI reports current, not peak,
so the poll is deliberately tight. A short op can hide its peak between samples; that biases the
measurement OPTIMISTIC, which is the safe direction for a "does it fit" question only if we then
refuse near the boundary rather than at it.
"""
from __future__ import annotations

import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path("C:/Users/xXste/Code_Projects/SpellVision")
sys.path.insert(0, str(REPO / "python"))

from comfy_prompt_client import _http_get_json  # noqa: E402

API = "http://127.0.0.1:8188"
MODEL = "4x-UltraSharp.pth"   # native factor 4x, the Auto pick


def vram_used_gb() -> float:
    stats = _http_get_json(API, "/system_stats", timeout=15)
    for device in stats.get("devices", []):
        total = device.get("vram_total") or 0
        free = device.get("vram_free") or 0
        if total:
            return (total - free) / (1024 ** 3)
    return 0.0


class Peak(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.peak = 0.0
        self.stop = threading.Event()

    def run(self) -> None:
        while not self.stop.is_set():
            try:
                self.peak = max(self.peak, vram_used_gb())
            except Exception:
                pass
            time.sleep(0.15)


def probe(width: int, height: int, frames: int, scale: float | None) -> dict:
    """One batch of `frames` images at width x height through the upscale model."""
    graph = {
        "1": {"class_type": "EmptyImage",
              "inputs": {"width": width, "height": height, "batch_size": frames, "color": 4210752}},
        "2": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": MODEL}},
        "3": {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["2", 0], "image": ["1", 0]}},
        # Terminate small so the saved bytes are not what we are measuring.
        "4": {"class_type": "ImageScale",
              "inputs": {"image": ["3", 0], "upscale_method": "lanczos",
                         "width": 64, "height": 64, "crop": "disabled"}},
        "5": {"class_type": "SaveImage",
              "inputs": {"images": ["4", 0],
                         "filename_prefix": f"sv_vram_{width}x{height}x{frames}_{int(time.time())}"}},
    }

    baseline = vram_used_gb()
    watcher = Peak()
    watcher.start()
    started = time.perf_counter()
    result: dict = {"width": width, "height": height, "frames": frames,
                    "out_mp": (width * 4) * (height * 4) / 1e6, "baseline_gb": round(baseline, 2)}
    try:
        body = json.dumps({"prompt": graph, "client_id": "sv-vram-probe"}).encode()
        request = urllib.request.Request(f"{API}/prompt", data=body,
                                         headers={"Content-Type": "application/json"})
        prompt_id = json.loads(urllib.request.urlopen(request, timeout=90).read())["prompt_id"]
        for _ in range(1200):
            entry = (_http_get_json(API, f"/history/{prompt_id}", timeout=30) or {}).get(prompt_id)
            if not entry:
                time.sleep(0.5)
                continue
            status = entry.get("status", {})
            if status.get("completed"):
                result["outcome"] = "ok"
                break
            if status.get("status_str") == "error":
                messages = json.dumps(status.get("messages", []))[:300]
                result["outcome"] = "error"
                result["detail"] = messages
                break
            time.sleep(0.5)
        else:
            result["outcome"] = "timeout"
    except urllib.error.HTTPError as exc:
        result["outcome"] = "rejected"
        result["detail"] = exc.read()[:300].decode("replace")
    finally:
        watcher.stop.set()
        watcher.join(timeout=2)

    result["seconds"] = round(time.perf_counter() - started, 1)
    result["peak_gb"] = round(watcher.peak, 2)
    result["delta_gb"] = round(watcher.peak - baseline, 2)
    return result


def main() -> int:
    print(f"upscale model: {MODEL} (native 4x)")
    print(f"idle VRAM: {vram_used_gb():.2f} GB\n")

    # A single frame first, then the frame counts a real video actually produces. LTX's shipped
    # lengths are (N*8)+1: 49, 65, 97.
    cases = [
        (832, 480, 1),
        (832, 480, 8),
        (832, 480, 25),
        (832, 480, 49),
        (1024, 640, 49),
        (832, 480, 97),
    ]
    rows = []
    for width, height, frames in cases:
        row = probe(width, height, frames, None)
        rows.append(row)
        print(f"  {width}x{height} x{frames:3d}f -> out {row['out_mp']:7.1f} MP/frame  "
              f"peak {row['peak_gb']:6.2f} GB (+{row['delta_gb']:.2f})  "
              f"{row['seconds']:6.1f}s  {row['outcome']}"
              + (f"  {row.get('detail','')[:120]}" if row.get("detail") else ""))
        if row["outcome"] != "ok":
            print("    stopping: the first failure is the answer")
            break

    out = REPO / "build" / "video_upscale_cost.json"
    out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
