"""Krea2 regional inpaint graph.

Global i2i cannot recut hair or swap clothes (latent keeps the lock).
VAEEncodeForInpaint is the live shape/clothes tool.

ConditioningSetMask is NOT used: Krea2/Qwen cond is not SD-shaped.
Live smoke 2026-08-19: KSampler raised ``too many values to unpack (expected 2)``.

Graph (render-proven class_types):
  Load lock + mask -> Grow/Feather -> VAEEncodeForInpaint
  -> KSampler denoise 1 -> decode -> ImageCompositeMasked onto lock
"""
from __future__ import annotations

from typing import Any
from comfy_graph_helpers import vae_decode_node


REQUIRED_CLASSES = (
    "UNETLoader",
    "CLIPLoader",
    "VAELoader",
    "CLIPTextEncode",
    "ModelSamplingAuraFlow",
    "LoadImage",
    "ImageToMask",
    "GrowMask",
    "FeatherMask",
    "VAEEncodeForInpaint",
    "KSampler",
    "VAEDecode",
    "ImageCompositeMasked",
    "SaveImage",
)


def build_krea2_regional_inpaint_graph(
    *,
    unet_name: str,
    clip_name: str = "qwen3vl_4b_fp8_scaled.safetensors",
    vae_name: str = "qwen_image_vae.safetensors",
    lock_image: str,
    mask_image: str,
    edit_prompt: str,
    identity_prompt: str = "",
    negative_prompt: str = (
        "second face, extra face, framed photo, inset portrait, floating rectangle, "
        "sheer, transparent, nude, mosaic, extra limbs, text, watermark"
    ),
    seed: int = 0,
    steps: int = 52,
    cfg: float = 3.5,
    grow_mask_by: int = 6,
    feather: int = 8,
    denoise: float = 0.7,
    latent_mode: str = "inpaint",
    filename_prefix: str = "krea2_inpaint",
    # The cockpit sends `enable_vae_tiling` on every request and these builders take exploded
    # scalars rather than the request, so the switch had nowhere to land. Optional and defaulted so
    # every existing call keeps working; the live callers thread it.
    request: dict[str, Any] | None = None,
    object_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not str(lock_image or "").strip():
        raise ValueError("lock_image is required")
    if not str(mask_image or "").strip():
        raise ValueError("mask_image is required")
    if not str(edit_prompt or "").strip():
        raise ValueError("edit_prompt is required")

    positive = edit_prompt
    ident = str(identity_prompt or "").strip()
    if ident:
        positive = f"{ident}, {edit_prompt}"
    mode = str(latent_mode or "inpaint").strip().lower()
    if mode not in {"inpaint", "noise_mask"}:
        raise ValueError("latent_mode must be 'inpaint' or 'noise_mask'")
    try:
        denoise_f = float(denoise)
    except Exception as exc:
        raise ValueError("denoise must be a number") from exc
    if not (0.0 <= denoise_f <= 1.0):
        # Inclusive at zero, matching every other builder and the bounds table. This refused a
        # stated 0.0 outright -- which at least SAID so, unlike the six that silently substituted
        # 0.6 -- but it still rejected a value the cockpit's spin box offers and KSampler accepts.
        # Denoise 0 on an inpaint returns the masked region unchanged: inert, and exactly what was
        # asked for.
        raise ValueError("denoise must be in [0, 1]")

    graph: dict[str, Any] = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": unet_name, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": clip_name, "type": "krea2"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae_name}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": ["2", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": negative_prompt, "clip": ["2", 0]}},
        "7": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 1.15}},
        "11": {"class_type": "LoadImage", "inputs": {"image": lock_image}},
        "12": {"class_type": "LoadImage", "inputs": {"image": mask_image}},
        "13": {"class_type": "ImageToMask", "inputs": {"image": ["12", 0], "channel": "red"}},
        "14": {
            "class_type": "GrowMask",
            "inputs": {"mask": ["13", 0], "expand": int(grow_mask_by), "tapered_corners": True},
        },
        "15": {
            "class_type": "FeatherMask",
            "inputs": {
                "mask": ["14", 0],
                "left": int(feather),
                "top": int(feather),
                "right": int(feather),
                "bottom": int(feather),
            },
        },
    }
    if mode == "noise_mask":
        graph["24"] = {
            "class_type": "VAEEncode",
            "inputs": {"pixels": ["11", 0], "vae": ["3", 0]},
        }
        graph["26"] = {
            "class_type": "SetLatentNoiseMask",
            "inputs": {"samples": ["24", 0], "mask": ["15", 0]},
        }
        latent_ref: list[Any] = ["26", 0]
    else:
        graph["24"] = {
            "class_type": "VAEEncodeForInpaint",
            "inputs": {
                "pixels": ["11", 0],
                "vae": ["3", 0],
                "mask": ["15", 0],
                "grow_mask_by": 0,
            },
        }
        latent_ref = ["24", 0]
    graph["8"] = {
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
            "latent_image": latent_ref,
            "denoise": denoise_f,
        },
    }
    graph["9"] = vae_decode_node(request or {}, object_info or {}, samples=["8", 0], vae=["3", 0])
    graph["25"] = {
        "class_type": "ImageCompositeMasked",
        "inputs": {
            "destination": ["11", 0],
            "source": ["9", 0],
            "x": 0,
            "y": 0,
            "resize_source": False,
            "mask": ["15", 0],
        },
    }
    graph["10"] = {
        "class_type": "SaveImage",
        "inputs": {"images": ["25", 0], "filename_prefix": filename_prefix},
    }
    return graph


def graph_uses_classes(graph: dict[str, Any], names: tuple[str, ...] = REQUIRED_CLASSES) -> list[str]:
    present = {str(n.get("class_type") or "") for n in graph.values()}
    return [name for name in names if name not in present]
