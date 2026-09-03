"""The render gate for the upscale route: it has to produce detail a resample cannot.

Marked `needs_comfy` + `needs_gpu`, so it is excluded from the hermetic lane and from CI. It is the
milestone gate, and it is here rather than in a scratch script because it is the only check that can
tell a working upscale from the lanczos that silently stood in for one.

**Pixel distance is the wrong measurement.** It answers "did the bytes change", and the silent
fallback changed the bytes too -- it resampled and saved. What separates a real upscale from a
resample is high-frequency ENERGY at IDENTICAL dimensions: the detail a resampling filter cannot
invent, because it is not in the source.

Measured 2026-09-02 on the live core (v0.34.0), anima at 512x768 -> 1024x1536, seed fixed, the two
graphs differing ONLY in how they scale:

| | Laplacian variance | high-band energy (>0.25 Nyquist) |
|---|---|---|
| model (4x-UltraSharp -> ImageScale) | 0.111086 | 21.20% |
| lanczos (ImageScale alone) | 0.013130 | 9.06% |
| **ratio** | **x8.46** | **x2.34** |

Two supporting numbers, both worth keeping:

* Downsampled back to 512x768, the lanczos output is MAE **2.57** from the base render and the
  model output is **9.14** -- the model is reconstructing, not merely resizing.
* The two outputs are MAE **16.14** apart in pixels. So a pixel-distance check would *register*
  this difference; what it could not do is say which of the two is the upscale. A recon note said
  pixel distance would pass the silent lanczos outright, and that overstated it -- the honest claim
  is that distance detects a change without telling you its direction.

The sampler half of both graphs is byte-identical, so ComfyUI's node cache serves the same latent
to both. Here that is the control rather than a trap: it makes the base image a constant. The trap
version of the same behaviour -- an identical resubmit returning a cached result that reads as a
fast render -- is recorded in Doc 53.
"""
from __future__ import annotations

import io
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

pytestmark = [pytest.mark.needs_comfy, pytest.mark.needs_gpu, pytest.mark.slow]

API = "http://127.0.0.1:8188"
MODEL = "D:/AI_ASSETS/models/diffusion_models/anima/anima-base-v1.0.safetensors"
PROMPT = (
    "extreme close-up photograph of a woven linen sleeve over chainmail, individual threads, "
    "frayed fibres, fine metal rings, dust motes, harsh side light, macro lens"
)
WIDTH, HEIGHT, SEED = 512, 768, 20260902

# Thresholds sit well under the measured 8.46x / 2.34x. They are here to catch the route silently
# becoming a resample again, not to pin one upscale model's character.
MIN_LAPLACIAN_RATIO = 3.0
MIN_HIGH_BAND_RATIO = 1.5


def _request(job: str, **extra) -> dict:
    req = {
        "command": "t2i",
        "model": MODEL,
        "model_family": "anima",
        "prompt": PROMPT,
        "negative_prompt": "blurry, smooth, soft focus",
        "width": WIDTH,
        "height": HEIGHT,
        "steps": 24,
        "cfg": 4.0,
        "seed": SEED,
        "output": str(ROOT / "build" / f"upscale_gate_{job}.png"),
        "metadata_output": str(ROOT / "build" / f"upscale_gate_{job}.json"),
    }
    req.update(extra)
    return req


def _render(label: str, **extra):
    """Through the shipped builder, so the gate measures the product's own graph."""
    from comfy_prompt_client import _http_get_json
    from PIL import Image

    import worker_service  # noqa: F401  -- binds the names the builders reach through
    from native_image_graphs import (
        _build_native_image_prompt,
        _native_image_family,
        _resolve_native_image_stack,
    )

    info = _http_get_json(API, "/object_info", timeout=180)
    req = _request(label, **extra)
    family = _native_image_family(req) or "anima"
    resolved = _resolve_native_image_stack(req, info, family)
    missing = [slot.component for slot in resolved.missing_required()]
    if missing:
        pytest.skip(f"{family} stack incomplete on this machine: {missing}")
    graph = _build_native_image_prompt(family, req, info, f"gate-{label}", resolved)

    body = json.dumps({"prompt": graph, "client_id": f"sv-gate-{label}"}).encode()
    request = urllib.request.Request(
        f"{API}/prompt", data=body, headers={"Content-Type": "application/json"})
    try:
        prompt_id = json.loads(urllib.request.urlopen(request, timeout=90).read())["prompt_id"]
    except urllib.error.HTTPError as exc:  # pragma: no cover - a rejected graph is a real failure
        pytest.fail(f"{label}: ComfyUI rejected the graph: {exc.read()[:1200].decode('replace')}")

    for _ in range(900):
        entry = (_http_get_json(API, f"/history/{prompt_id}", timeout=30) or {}).get(prompt_id)
        if entry and entry.get("status", {}).get("completed"):
            images = [img for node in entry.get("outputs", {}).values()
                      for img in node.get("images", [])]
            assert images, f"{label}: completed with no image"
            img = images[-1]
            url = (f"{API}/view?filename={img['filename']}"
                   f"&subfolder={img.get('subfolder', '')}&type={img.get('type', 'output')}")
            return Image.open(io.BytesIO(urllib.request.urlopen(url, timeout=120).read())).convert("RGB")
        time.sleep(1)
    pytest.fail(f"{label}: no history after 900s")


def _grey(image):
    import numpy as np

    return np.asarray(image.convert("L"), dtype=np.float64) / 255.0


def _laplacian_variance(g) -> float:
    lap = (-4.0 * g[1:-1, 1:-1]
           + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:])
    return float(lap.var())


def _high_band_fraction(g, cutoff: float = 0.25) -> float:
    import numpy as np

    spec = np.abs(np.fft.fftshift(np.fft.fft2(g - g.mean()))) ** 2
    h, w = spec.shape
    yy, xx = np.mgrid[0:h, 0:w]
    radius = np.sqrt(((yy - h / 2) / (h / 2)) ** 2 + ((xx - w / 2) / (w / 2)) ** 2)
    total = spec.sum()
    return float(spec[radius > cutoff].sum() / total) if total else 0.0


def test_the_model_route_recovers_detail_a_resample_cannot() -> None:
    model = _render("model_x2", upscale_enabled=True, upscale_method="model", upscale_scale=2.0)
    lanczos = _render("lanczos_x2", upscale_enabled=True, upscale_method="lanczos", upscale_scale=2.0)

    assert model.size == lanczos.size == (WIDTH * 2, HEIGHT * 2), (
        "both routes must land on the asked-for size before the comparison means anything -- the "
        "Scale box reached neither of them until ImageScale followed the upscale model"
    )

    model_lap = _laplacian_variance(_grey(model))
    lanczos_lap = _laplacian_variance(_grey(lanczos))
    model_hf = _high_band_fraction(_grey(model))
    lanczos_hf = _high_band_fraction(_grey(lanczos))

    lap_ratio = model_lap / max(lanczos_lap, 1e-12)
    hf_ratio = model_hf / max(lanczos_hf, 1e-12)
    report = (f"laplacian {model_lap:.6f} vs {lanczos_lap:.6f} (x{lap_ratio:.2f}); "
              f"high-band {model_hf:.4f} vs {lanczos_hf:.4f} (x{hf_ratio:.2f})")

    assert lap_ratio >= MIN_LAPLACIAN_RATIO, f"the model route is resampling, not upscaling: {report}"
    assert hf_ratio >= MIN_HIGH_BAND_RATIO, f"no high-frequency content was added: {report}"


def test_the_upscaled_image_is_the_same_picture() -> None:
    """A detail metric alone would be satisfied by an upscaler that invented a different image.

    Downsampled back to the render's own size, the result has to still be the render. Measured:
    lanczos MAE 2.57 (near-identity), model MAE 9.14 -- reconstruction, not a different picture.
    """
    import numpy as np

    base = _render("base")
    model = _render("model_x2", upscale_enabled=True, upscale_method="model", upscale_scale=2.0)
    down = np.asarray(model.resize(base.size, __import__("PIL.Image", fromlist=["Image"]).LANCZOS),
                      dtype=np.float64)
    mae = float(np.abs(down - np.asarray(base, dtype=np.float64)).mean())
    assert mae < 25.0, f"the upscale returned a different picture, not a larger one (MAE {mae:.2f})"
