"""Family-aware upscale routing + Comfy pixel-graph graft.

Pixel path (this increment): UpscaleModelLoader -> ImageUpscaleWithModel, rewired
into every SaveImage. Latent LTX already lives in the two-stage template; SDXL
diffusers keep the PIL post-pass.
"""
from __future__ import annotations

from typing import Any

PIXEL_COMFY_FAMILIES = frozenset({
    "flux", "flux_image", "pixart", "pixart_image", "lumina", "lumina_image",
    "zimage", "zimage_image", "z-image", "z_image", "anima", "anima_image",
})
LATENT_FAMILIES = frozenset({"ltx", "ltx_video"})
_NONE = frozenset({"", "none", "off", "false", "0"})
_PIL = frozenset({"lanczos", "nearest", "bilinear"})
_PIXEL = frozenset({"model", "pixel", "esrgan", "comfy"})


def resolve_upscale_route(family: Any, method: Any, *, enabled: bool) -> str:
    if not enabled:
        return "none"
    method_id = str(method or "").strip().lower()
    if method_id in _NONE:
        return "none"
    if method_id in _PIL:
        return "pixel_pil"
    family_id = str(family or "").strip().lower()
    if method_id in _PIXEL:
        if family_id in PIXEL_COMFY_FAMILIES:
            return "pixel_comfy"
        if family_id in LATENT_FAMILIES:
            return "latent_ltx"
        return "pixel_pil"
    return "none"


def _combo_choices(object_info: dict[str, Any] | None, class_name: str, input_name: str) -> list[str]:
    if not object_info:
        return []
    node = object_info.get(class_name) or {}
    required = ((node.get("input") or {}).get("required") or {})
    raw = required.get(input_name)
    if not isinstance(raw, list) or not raw or not isinstance(raw[0], list):
        return []
    return [str(item).strip() for item in raw[0] if str(item).strip()]


def _next_numeric_id(graph: dict[str, Any]) -> int:
    nums = []
    for key in graph:
        try:
            nums.append(int(key))
        except (TypeError, ValueError):
            continue
    return (max(nums) if nums else 100) + 1


def resolve_upscale_model_name(object_info: dict[str, Any] | None, requested: Any) -> str:
    requested_name = str(requested or "").strip()
    choices = _combo_choices(object_info, "UpscaleModelLoader", "model_name")
    if requested_name:
        base = requested_name.replace("\\", "/").split("/")[-1]
        for choice in choices:
            if choice == requested_name or choice.endswith(base) or choice.split("/")[-1] == base:
                return choice
        return requested_name
    return choices[0] if choices else ""


def graft_pixel_upscale(
    graph: dict[str, Any],
    object_info: dict[str, Any] | None,
    *,
    model_name: Any = "",
) -> dict[str, Any]:
    """Rewire SaveImage inputs through ImageUpscaleWithModel. No-op if nodes missing."""
    if not isinstance(graph, dict) or not graph:
        return graph
    if object_info is not None and (
        "UpscaleModelLoader" not in object_info or "ImageUpscaleWithModel" not in object_info
    ):
        return graph

    resolved_model = resolve_upscale_model_name(object_info, model_name)
    if not resolved_model:
        return graph

    saves = [
        (nid, node)
        for nid, node in graph.items()
        if isinstance(node, dict) and node.get("class_type") == "SaveImage"
    ]
    if not saves:
        return graph

    next_id = _next_numeric_id(graph)
    loader_id = str(next_id)
    graph[loader_id] = {
        "class_type": "UpscaleModelLoader",
        "inputs": {"model_name": resolved_model},
    }
    next_id += 1
    for nid, node in saves:
        inputs = node.setdefault("inputs", {})
        image_ref = inputs.get("images")
        if not image_ref:
            continue
        up_id = str(next_id)
        next_id += 1
        graph[up_id] = {
            "class_type": "ImageUpscaleWithModel",
            "inputs": {
                "upscale_model": [loader_id, 0],
                "image": image_ref,
            },
        }
        inputs["images"] = [up_id, 0]
    return graph
