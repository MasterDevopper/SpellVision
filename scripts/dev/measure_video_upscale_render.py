"""Does a model upscale survive a REAL video render, at the moment it would actually run?

`measure_video_upscale_cost.py` answered what the upscale node costs ON ITS OWN: +3.0-3.4 GB,
bounded, frame-count independent. What it could not answer is residency -- whether the video
transformer is still holding VRAM when the upscale runs, one node after VAE decode, in the same
graph. A cost measured alone is not a cost in situ.

So this builds the graph the SHIPPING builder builds and submits it. Baseline and grafted use
DIFFERENT SEEDS: an identical sampler half would be served from ComfyUI's node cache, and a cached
latent means no transformer was ever resident -- the run would report a peak that answers a
different question.

Measured 2026-09-03, live core v0.34.0, LTX two-stage 768x512x49f:

    baseline        peak 31.55 GB   79.3s   -> 1536x1024x49f
    with upscale    peak 31.70 GB  285.4s   -> 3072x2048x49f

+0.15 GB. The peak is the SAMPLER's, and the transformer is already freed by the time the upscale
runs, so the isolated +3.0 GB never stacks. What a video upscale costs is time.

Run:  .venv/Scripts/python.exe scripts/dev/measure_video_upscale_render.py
      .venv/Scripts/python.exe scripts/dev/measure_video_upscale_render.py '[["up",768,512,49,1,2.0]]'
"""
from __future__ import annotations

import json
import sys
import threading
import time
import urllib.request
from pathlib import Path

REPO = Path("C:/Users/xXste/Code_Projects/SpellVision")
sys.path.insert(0, str(REPO / "python"))

from comfy_prompt_client import _http_get_json  # noqa: E402
import native_video_graphs as nvg  # noqa: E402

API = "http://127.0.0.1:8188"
LTX = "D:/AI_ASSETS/models/checkpoints/ltx/ltx-2.3-22b-dev.safetensors"
UPSCALE_MODEL = "4x-UltraSharp.pth"


def usage_gb() -> tuple[float, float]:
    """(VRAM used, host RAM used), both in GB.

    Host RAM is tracked because DynamicVRAM's whole mechanism is paging weights OUT of VRAM and into
    it: a VRAM figure alone describes half of where the model went, and on a machine with less RAM
    than this one the second half is the one that fails.
    """
    stats = _http_get_json(API, "/system_stats", timeout=20)
    vram = 0.0
    for device in stats.get("devices", []):
        total, free = device.get("vram_total") or 0, device.get("vram_free") or 0
        if total:
            vram = (total - free) / (1024 ** 3)
            break
    system = stats.get("system", {})
    ram_total, ram_free = system.get("ram_total") or 0, system.get("ram_free") or 0
    return vram, ((ram_total - ram_free) / (1024 ** 3) if ram_total else 0.0)


def vram_used_gb() -> float:
    return usage_gb()[0]


class Peak(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.peak = 0.0
        self.peak_ram = 0.0
        self.stop = threading.Event()

    def run(self) -> None:
        while not self.stop.is_set():
            try:
                vram, ram = usage_gb()
                self.peak = max(self.peak, vram)
                self.peak_ram = max(self.peak_ram, ram)
            except Exception:
                pass
            time.sleep(0.25)


# A spatial latent upsampler multiplies the FRAME size without touching the requested width, so
# req["width"] is the LATENT size on that route, not the size of the picture that comes out.
_SPATIAL_LATENT_UPSAMPLERS = {"LTXVLatentUpsampler": 2}


def frame_dimensions(graph: dict, width: int, height: int) -> tuple[int, int]:
    factor = 1
    for node in graph.values():
        if isinstance(node, dict):
            factor *= _SPATIAL_LATENT_UPSAMPLERS.get(node.get("class_type"), 1)
    return width * factor, height * factor


def graft(graph: dict, scale: float, target_w: int, target_h: int) -> dict:
    """The graft this probe measures.

    Kept as its own copy DELIBERATELY: the point of the probe is to measure a cost independently of
    whether the shipped route is wired correctly, and calling upscale_engine here would make a
    broken route read as a cheap one. The shipped implementation is
    `upscale_engine.graft_pixel_upscale` + `native_video_graphs._apply_video_upscale`, and
    `tests/test_upscale_reaches_every_family.py` is what holds THAT to the tree.
    """
    sinks = [(nid, n) for nid, n in graph.items()
             if isinstance(n, dict) and n.get("class_type") in ("CreateVideo", "SaveWEBM", "VHS_VideoCombine")]
    assert sinks, "no video sink in the graph"
    next_id = max((int(k) for k in graph if str(k).isdigit()), default=0) + 1
    loader = str(next_id); next_id += 1
    graph[loader] = {"class_type": "UpscaleModelLoader", "inputs": {"model_name": UPSCALE_MODEL}}
    for _nid, node in sinks:
        ref = node["inputs"].get("images")
        if not ref:
            continue
        up = str(next_id); next_id += 1
        graph[up] = {"class_type": "ImageUpscaleWithModel",
                     "inputs": {"upscale_model": [loader, 0], "image": ref}}
        sc = str(next_id); next_id += 1
        graph[sc] = {"class_type": "ImageScale",
                     "inputs": {"image": [up, 0], "upscale_method": "lanczos",
                                "width": int(target_w * scale), "height": int(target_h * scale),
                                "crop": "disabled"}}
        node["inputs"]["images"] = [sc, 0]
    return graph


def run(label: str, width: int, height: int, frames: int, seed: int, scale: float | None) -> dict:
    object_info = _http_get_json(API, "/object_info", timeout=180)
    req = {
        "command": "t2v", "model": LTX, "video_family": "ltx",
        "prompt": "a calm ocean wave rolling toward the shore, cinematic, slow dolly",
        "negative_prompt": "blurry",
        "width": width, "height": height, "frames": frames, "num_frames": frames,
        "fps": 16, "steps": 12, "cfg": 3.0, "seed": seed,
        "output": str(REPO / "build" / f"video_upscale_gate_{label}.mp4"),
    }
    graph = nvg._build_native_split_video_prompt(
        req, object_info, command="t2v", family="ltx", job_id=f"gate-{label}-{seed}")
    frame_w, frame_h = frame_dimensions(graph, width, height)
    result_dims = (frame_w, frame_h)
    if scale:
        graph = graft(graph, scale, frame_w, frame_h)

    baseline = vram_used_gb()
    watcher = Peak(); watcher.start()
    started = time.perf_counter()
    result = {"label": label, "dims": f"{width}x{height}x{frames}f", "seed": seed,
              "scale": scale, "baseline_gb": round(baseline, 2), "nodes": len(graph),
              "frame": f"{result_dims[0]}x{result_dims[1]}",
              "expect": f"{int(result_dims[0]*(scale or 1))}x{int(result_dims[1]*(scale or 1))}"}
    try:
        body = json.dumps({"prompt": graph, "client_id": "sv-video-upscale-gate"}).encode()
        rq = urllib.request.Request(f"{API}/prompt", data=body,
                                    headers={"Content-Type": "application/json"})
        prompt_id = json.loads(urllib.request.urlopen(rq, timeout=120).read())["prompt_id"]
        for _ in range(3600):
            entry = (_http_get_json(API, f"/history/{prompt_id}", timeout=30) or {}).get(prompt_id)
            if entry:
                status = entry.get("status", {})
                if status.get("completed"):
                    result["outcome"] = "ok"
                    result["outputs"] = json.dumps(entry.get("outputs", {}))[:400]
                    break
                if status.get("status_str") == "error":
                    result["outcome"] = "error"
                    result["detail"] = json.dumps(status.get("messages", []))[:600]
                    break
            time.sleep(1.0)
        else:
            result["outcome"] = "timeout"
    except Exception as exc:  # the failure IS the measurement here
        result["outcome"] = type(exc).__name__
        detail = getattr(exc, "read", None)
        result["detail"] = (detail()[:600].decode("replace") if detail else str(exc))[:600]
    finally:
        watcher.stop.set(); watcher.join(timeout=3)

    result["seconds"] = round(time.perf_counter() - started, 1)
    result["peak_gb"] = round(watcher.peak, 2)
    result["peak_ram_gb"] = round(watcher.peak_ram, 2)
    return result


def main() -> int:
    cases = json.loads(sys.argv[1]) if len(sys.argv) > 1 else [
        ["base49", 768, 512, 49, 70101, None],
        ["up49", 768, 512, 49, 70102, 2.0],
    ]
    rows = []
    for label, w, h, f, seed, scale in cases:
        row = run(label, w, h, f, seed, scale)
        rows.append(row)
        print(f"  {label:8s} {row['dims']:14s} seed {seed}  peak {row['peak_gb']:6.2f} GB  "
              f"ram {row['peak_ram_gb']:6.2f} GB  {row['seconds']:7.1f}s  {row['outcome']}"
              + (f"\n      {row.get('detail','')[:400]}" if row.get("detail") else ""))
        sys.stdout.flush()
    out = REPO / "build" / "video_upscale_gate.json"
    out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
