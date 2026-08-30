"""Qwen-Image-Edit-2511 graph. Image goes through VL (+ optional VAE ref), empty latent, denoise 1.

This is NOT Krea2/Utopic. Use it for identity-preserving edits (clothes, hair cut)
when Krea2 i2i/inpaint cannot. House look is a later restyle pass.
"""
from __future__ import annotations

from typing import Any
from comfy_graph_helpers import vae_decode_node

REQUIRED_CLASSES = (
    "UNETLoader",
    "CLIPLoader",
    "VAELoader",
    "LoadImage",
    "TextEncodeQwenImageEditPlus",
    "CLIPTextEncode",
    "ModelSamplingAuraFlow",
    "EmptySD3LatentImage",
    "KSampler",
    "VAEDecode",
    "SaveImage",
)

UNET_NAME = "qwen_image_edit_2511_fp8mixed.safetensors"
CLIP_NAME = "qwen_2.5_vl_7b_fp8_scaled.safetensors"
VAE_NAME = "qwen_image_vae.safetensors"


def build_qwen_image_edit_graph(
    *,
    input_image: str,
    prompt: str,
    negative_prompt: str = "second face, extra face, inset, mosaic, blurry, extra limbs, text, watermark",
    width: int = 768,
    height: int = 1344,
    seed: int = 0,
    steps: int = 20,
    cfg: float = 4.0,
    shift: float = 1.15,
    filename_prefix: str = "qwen_edit",
    pass_vae: bool = True,
    reference_images: tuple[str, ...] = (),
    unet_name: str = UNET_NAME,
    clip_name: str = CLIP_NAME,
    vae_name: str = VAE_NAME,
    # The cockpit sends `enable_vae_tiling` on every request and these builders take exploded
    # scalars rather than the request, so the switch had nowhere to land. Optional and defaulted so
    # every existing call keeps working; the live callers thread it.
    request: dict[str, Any] | None = None,
    object_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not str(input_image or "").strip():
        raise ValueError("input_image is required")
    if not str(prompt or "").strip():
        raise ValueError("prompt is required")

    encode_pos: dict[str, Any] = {
        "clip": ["2", 0],
        "prompt": prompt,
        "image1": ["11", 0],
    }
    refs = [str(x).strip() for x in reference_images if str(x or "").strip()]
    if len(refs) > 2:
        raise ValueError("Qwen-Edit Plus takes at most 2 extra reference images")
    extra_loads: dict[str, Any] = {}
    for i, name in enumerate(refs, start=2):
        nid = str(12 + i)  # image2 -> 14, image3 -> 15
        extra_loads[nid] = {"class_type": "LoadImage", "inputs": {"image": name}}
        encode_pos[f"image{i}"] = [nid, 0]
    if pass_vae:
        encode_pos["vae"] = ["3", 0]

    graph: dict[str, Any] = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": unet_name, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": clip_name, "type": "qwen_image"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae_name}},
        "11": {"class_type": "LoadImage", "inputs": {"image": input_image}},
    }
    graph.update(extra_loads)
    graph.update(
        {
            "4": {"class_type": "TextEncodeQwenImageEditPlus", "inputs": encode_pos},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": negative_prompt, "clip": ["2", 0]}},
            "7": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": float(shift)}},
            "12": {
                "class_type": "EmptySD3LatentImage",
                "inputs": {"width": int(width), "height": int(height), "batch_size": 1},
            },
            "8": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["7", 0],
                    "seed": int(seed),
                    "steps": int(steps),
                    "cfg": float(cfg),
                    "sampler_name": "euler",
                    "scheduler": "simple",
                    "positive": ["4", 0],
                    "negative": ["6", 0],
                    "latent_image": ["12", 0],
                    "denoise": 1.0,
                },
            },
            "9": vae_decode_node(request or {}, object_info or {}, samples=["8", 0], vae=["3", 0]),
            "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": filename_prefix}},
        }
    )
    return graph


def graph_uses_classes(graph: dict[str, Any], names: tuple[str, ...] = REQUIRED_CLASSES) -> list[str]:
    present = {str(n.get("class_type") or "") for n in graph.values()}
    return [name for name in names if name not in present]
