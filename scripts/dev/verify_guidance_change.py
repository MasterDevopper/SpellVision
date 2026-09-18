"""Render the same request at several FluxGuidance values and report what came back.

Doc 62 3e changed which number reaches `FluxGuidance` / `embedded_guidance_scale`: it was the
cockpit's `cfg`, it is now the model's stated `guidance`. Three families steer through it (flux
image, hunyuan t2v, hunyuan i2v), and the change shipped without a render.

The two numbers that matter on this library: `cfg` resolves to **1.0** for both families (correct
for a distilled model) and `guidance` to **3.5** flux / **6.0** hunyuan. So the old path fed
FluxGuidance 1.0 -- nearly unguided -- and the new one feeds the family's real figure.

Only `guidance` varies between arms, so the graph differs and ComfyUI's node cache cannot answer a
later arm with an earlier arm's image. The seed is held FIXED for the same reason the cache trap
exists: with the seed varying, a difference would be sampling noise rather than the lever.

Not a timing harness. The numbers it prints are pixel statistics, and it makes no speed claim.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import measure_optimizations_link as link  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "runtime" / "optimization_requests.json"
OUT = ROOT / "runtime" / "guidance_check"


def load_template(key: str) -> dict:
    payload = json.loads(TEMPLATES.read_text(encoding="utf-8"))
    template = payload.get(key)
    if not isinstance(template, dict):
        raise SystemExit(f"no archived template {key!r}; have {sorted(payload)}")
    return template


def describe(path: Path) -> str:
    """Mean/stdev per channel and a rough saturation, from the file the worker actually wrote.

    Reported so a reader can see the arms differ in the direction guidance moves things, without
    the script pretending to judge which image is better -- that is the owner's eye, not a number.
    """
    try:
        from PIL import Image
    except ImportError:
        return "(Pillow not available)"
    if not path.is_file():
        return "MISSING"
    if path.suffix.lower() == ".mp4":
        # A video's statistics come from one extracted frame; without ffmpeg, say so rather than
        # reporting nothing, because "no numbers" and "no file" must not look the same.
        frame = path.with_name(path.stem + "_frame.png")
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(path),
             "-vf", "select=eq(n\\,12)", "-vframes", "1", str(frame)],
            check=False, capture_output=True,
        )
        size = path.stat().st_size
        if not frame.is_file():
            return f"{size/1e6:.2f} MB  (no ffmpeg frame)"
        return f"{size/1e6:.2f} MB  frame12 " + describe(frame)
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        pixels = list(rgb.getdata())
    if not pixels:
        return "EMPTY"
    channels = list(zip(*pixels))
    means = [statistics.fmean(c) for c in channels]
    stdevs = [statistics.pstdev(c) for c in channels]
    saturation = statistics.fmean(
        [(max(p) - min(p)) / 255.0 for p in pixels[:: max(1, len(pixels) // 20000)]]
    )
    return (
        f"mean {means[0]:6.1f}/{means[1]:6.1f}/{means[2]:6.1f}  "
        f"sd {stdevs[0]:5.1f}/{stdevs[1]:5.1f}/{stdevs[2]:5.1f}  sat {saturation:.3f}"
    )


def run(key: str, guidances: list[float], seed: int, overrides: dict) -> int:
    template = load_template(key)
    secret = link.session_secret(os.environ.get(link.SESSION_FILE_ENV))
    OUT.mkdir(parents=True, exist_ok=True)
    family = key.replace(":", "_")
    suffix = ".mp4" if template.get("command", "").endswith("2v") else ".png"

    failures = 0
    for guidance in guidances:
        stem = f"{family}_g{guidance}_s{seed}"
        output = OUT / f"{stem}{suffix}"
        request = dict(template)
        request.update(overrides)
        request["seed"] = seed
        request["guidance"] = guidance
        request["batch_count"] = 1
        request["job_id"] = f"guidance_{stem}_{int(time.time())}"
        request["output"] = str(output)
        request["original_output"] = str(output)
        request["metadata_output"] = str(OUT / f"{stem}.json")
        request["original_metadata_output"] = str(OUT / f"{stem}.json")
        request["submit_origin"] = "guidance_verification"

        started = time.monotonic()
        messages = link.request(request, secret=secret, timeout=3600.0)
        elapsed = time.monotonic() - started
        terminal = messages[-1] if messages else {}
        state = str(terminal.get("state") or terminal.get("type") or "?")
        ok = state in {"completed", "done", "ok"} or bool(terminal.get("ok"))
        print(f"guidance {guidance:<5} {state:<12} {elapsed:6.1f}s  {describe(output)}")
        if not ok:
            failures += 1
            reason = terminal.get("error") or terminal.get("message") or terminal
            print(f"    NOT OK: {str(reason)[:300]}")
    print(f"\nwrote to {OUT}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", default="flux:t2i")
    parser.add_argument("--guidance", type=float, nargs="+", default=[1.0, 3.5, 7.0])
    parser.add_argument("--seed", type=int, default=770118)
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    args = parser.parse_args()

    overrides: dict = {}
    for item in args.set:
        key, _, raw = item.partition("=")
        try:
            overrides[key] = int(raw)
        except ValueError:
            try:
                overrides[key] = float(raw)
            except ValueError:
                overrides[key] = raw
    return run(args.template, args.guidance, args.seed, overrides)


if __name__ == "__main__":
    raise SystemExit(main())
