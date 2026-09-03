"""Family-aware upscale routing + Comfy pixel-graph graft.

Pixel path: UpscaleModelLoader -> ImageUpscaleWithModel, rewired into every SaveImage.
SDXL diffusers keep the PIL post-pass, which ``image_runners.maybe_apply_request_upscale``
performs directly.

**This routes the IMAGE graph only, and it is called from exactly one place** --
``native_image_graphs`` asking whether to graft. It used to answer a fourth way, ``latent_ltx``,
for a latent upscale that lives in the LTX two-stage template and that nothing here has ever
performed: the branch was unreachable from any caller, and ``resolve_upscale_route`` is never
handed a video family. A route name that names no route reads as a capability on inspection, which
is worse than a gap.
"""
from __future__ import annotations

from typing import Any

PIXEL_COMFY_FAMILIES = frozenset({
    "flux", "flux_image", "pixart", "pixart_image", "lumina", "lumina_image",
    "zimage", "zimage_image", "z-image", "z_image", "anima", "anima_image",
})
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
        return "pixel_pil"
    return "none"


def _combo_choices(object_info: dict[str, Any] | None, class_name: str, input_name: str) -> list[str]:
    """Choices through the one reader.

    This function used to index ``raw[0]`` for a list, which reads the legacy combo shape only.
    ``UpscaleModelLoader.model_name`` is one of the 562 combos the live core has already migrated to
    ``["COMBO", {"options": [...]}]``, so it returned ``[]``, ``resolve_upscale_model_name`` returned
    ``""``, and ``graft_pixel_upscale`` returned the graph untouched -- the whole pixel upscale route
    was a no-op that reported success.
    """
    if not object_info:
        return []
    from comfy_graph_helpers import _sv_comfy_input_choices

    return [c for c in _sv_comfy_input_choices(object_info, class_name, input_name) if c.strip()]


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
