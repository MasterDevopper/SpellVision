from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from upscale_engine import graft_pixel_upscale, resolve_upscale_route


OBJECT_INFO = {
    "UpscaleModelLoader": {"input": {"required": {"model_name": [["4x-UltraSharp.pth", "4x-AnimeSharp.pth"], {}]}}},
    "ImageUpscaleWithModel": {"input": {"required": {"upscale_model": ["UPSCALE_MODEL"], "image": ["IMAGE"]}}},
    "SaveImage": {"input": {"required": {"images": ["IMAGE"], "filename_prefix": ["STRING", {}]}}},
}


def test_route_native_image_model_is_comfy_pixel() -> None:
    assert resolve_upscale_route("flux", "model", enabled=True) == "pixel_comfy"
    assert resolve_upscale_route("z_image", "pixel", enabled=True) == "pixel_comfy"
    assert resolve_upscale_route("anima", "pixel", enabled=True) == "pixel_comfy"
    assert resolve_upscale_route("sdxl", "model", enabled=True) == "pixel_pil"
    # `latent_ltx` was a fourth return value no caller ever compared against, for a latent upscale
    # the LTX two-stage template performs and this module does not. The only caller asks one
    # question -- graft or not -- and a video family never reaches it.
    assert resolve_upscale_route("ltx", "model", enabled=True) == "pixel_pil"
    assert resolve_upscale_route("flux", "lanczos", enabled=True) == "pixel_pil"
    assert resolve_upscale_route("flux", "model", enabled=False) == "none"


def test_graft_rewires_saveimage_through_esrgan() -> None:
    graph = {
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": "sv"}},
    }
    grafted = graft_pixel_upscale(graph, OBJECT_INFO, model_name="4x-UltraSharp.pth")
    saves = [n for n in grafted.values() if n.get("class_type") == "SaveImage"]
    assert len(saves) == 1
    assert saves[0]["inputs"]["images"][0] != "9"
    up_id = saves[0]["inputs"]["images"][0]
    assert grafted[up_id]["class_type"] == "ImageUpscaleWithModel"
    assert grafted[up_id]["inputs"]["image"] == ["9", 0]
    loader_id = grafted[up_id]["inputs"]["upscale_model"][0]
    assert grafted[loader_id]["class_type"] == "UpscaleModelLoader"
    assert grafted[loader_id]["inputs"]["model_name"] == "4x-UltraSharp.pth"


def test_graft_skips_when_upscale_nodes_missing() -> None:
    graph = {"10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": "sv"}}}
    out = graft_pixel_upscale(dict(graph), {"SaveImage": {}}, model_name="4x-UltraSharp.pth")
    assert out["10"]["inputs"]["images"] == ["9", 0]
