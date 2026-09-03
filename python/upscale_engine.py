"""Family-aware upscale routing + Comfy pixel-graph graft.

Pixel path: ``UpscaleModelLoader -> ImageUpscaleWithModel -> ImageScale``, rewired into every
``SaveImage``. SDXL and the other diffusers families keep the PIL post-pass, which
``image_runners.maybe_apply_request_upscale`` performs directly.

**This routes the IMAGE graph only.** It used to answer a fourth way, ``latent_ltx``, for a latent
upscale that lives in the LTX two-stage template and that nothing here has ever performed: the
branch was unreachable and a route name that names no route reads as a capability on inspection.

Three things this module got wrong for as long as it existed, all of the same kind -- **the answer
was wrong and looked ordinary**:

1. ``_combo_choices`` read the legacy ``/object_info`` combo shape only.
   ``UpscaleModelLoader.model_name`` is one of the 562 combos the live core has migrated to
   ``["COMBO", {"options": …}]``, so it returned ``[]``, the model name resolved to ``""`` and the
   graft returned the graph untouched. **The route did nothing, on every family, and said nothing.**
2. A model name that matched no live choice was passed through unvalidated, so a stale name became
   a ComfyUI 400 after the graph was accepted rather than a message where the mistake was made.
3. ``PIXEL_COMFY_FAMILIES`` was a second, smaller list of the families whose graphs this builder
   builds. ``krea2`` and ``sd3`` were in ``NATIVE_IMAGE_FAMILIES`` and not in it, so they resolved
   to the PIL route -- which only the diffusers runner performs. Nobody performed it. Asking for an
   upscale on krea2 produced no upscale and no complaint.

So the route vocabulary now includes ``"unavailable"``: a request this build cannot honour is
reported, never quietly downgraded and never quietly dropped.
"""
from __future__ import annotations

import logging
from typing import Any

# WARNING and above: the root logger sits at WARNING, so log.info is invisible (CLAUDE.md 4).
log = logging.getLogger("spellvision.upscale")

_NONE = frozenset({"", "none", "off", "false", "0"})
_PIL = frozenset({"lanczos", "nearest", "bilinear", "bicubic"})
_PIXEL = frozenset({"model", "pixel", "esrgan", "comfy"})

ROUTE_NONE = "none"
ROUTE_PIXEL_COMFY = "pixel_comfy"      # an upscale MODEL, in the graph
ROUTE_RESIZE_COMFY = "resize_comfy"    # algorithmic resampling, in the graph
ROUTE_PIXEL_PIL = "pixel_pil"          # the diffusers runner's PIL post-pass
ROUTE_UNAVAILABLE = "unavailable"      # nothing here can do what was asked

# The cockpit's algorithmic methods, mapped to what ComfyUI's ImageScale calls them. Same
# operation, different spelling -- "nearest" is "nearest-exact" there. A method with no mapping is
# not silently swapped for a neighbour; it does not take this route.
_COMFY_RESAMPLE = {
    "lanczos": "lanczos",
    "nearest": "nearest-exact",
    "bilinear": "bilinear",
    "bicubic": "bicubic",
}

# An upscale model whose NAME declares a content specialisation. "Auto" used to mean
# ``choices[0]``, which on this box is ``4x-AnimeSharp.safetensors`` -- so the default upscaler for
# a photoreal render was an anime model, picked by nothing more than catalog order. This is not a
# quality ranking and makes no claim about which model is better: it is only a statement that a
# model advertising a subject should be chosen deliberately rather than inherited.
_SPECIALISED_MARKERS = ("anime", "yandere", "manga", "cartoon", "realistic", "face", "text")


class UpscaleUnavailable(RuntimeError):
    """The user asked for an upscale this build cannot perform.

    Raised where the graph is built, which is before any sampling happens, so the cost of refusing
    is a message rather than a wasted render.
    """


def resolve_upscale_route(family: Any, method: Any, *, enabled: bool) -> str:
    """Which mechanism performs this request -- or that nothing does.

    ``family`` is the classified native-image family. The comfy graft is available for exactly the
    families whose graph this builder produces, so that list is imported rather than re-stated;
    keeping a second copy is what left krea2 and sd3 silently un-upscalable.
    """
    if not enabled:
        return ROUTE_NONE
    method_id = str(method or "").strip().lower()
    if method_id in _NONE:
        return ROUTE_NONE

    family_id = str(family or "").strip().lower()
    native = _native_image_families()
    is_native = family_id in native

    if method_id in _PIXEL:
        if is_native:
            return ROUTE_PIXEL_COMFY
        # A diffusers family reaches the PIL post-pass, which cannot run an ESRGAN model: basicsr
        # and realesrgan are in neither venv. It used to answer pixel_pil here, and the runner then
        # resampled with lanczos and logged a warning nobody sees -- a user who chose
        # "Pixel (Comfy ESRGAN)" got a lanczos resize labelled as a success.
        return ROUTE_PIXEL_PIL if _pil_model_path_available() else ROUTE_UNAVAILABLE

    if method_id in _PIL:
        if not is_native:
            return ROUTE_PIXEL_PIL
        # A native family's image is produced inside ComfyUI, so the PIL post-pass never sees it.
        # ComfyUI's own ImageScale offers the same four resampling filters, so the request is
        # performed rather than upgraded to a model upscale -- substituting a *better* method is
        # still substituting, and the user asked for this one.
        return ROUTE_RESIZE_COMFY if method_id in _COMFY_RESAMPLE else ROUTE_UNAVAILABLE

    return ROUTE_NONE


def route_note(route: str, family: Any, method: Any) -> str:
    """The sentence a user should see when a route cannot be honoured. Empty when it can."""
    if route != ROUTE_UNAVAILABLE:
        return ""
    return (
        f"Upscale was requested as '{str(method or '').strip() or 'model'}' for "
        f"{str(family or 'this model').strip() or 'this model'}, and this build cannot perform it: "
        "the model-based upscaler needs the ComfyUI graph path, and this family renders through "
        "diffusers. Choose Lanczos to resample, or turn the upscale off."
    )


def _native_image_families() -> frozenset[str]:
    """The one list of families whose graph the native image builder produces.

    Imported lazily: ``native_image_graphs`` imports this module, so a top-level import would be a
    cycle. The alternative -- restating the list here -- is the defect this function exists to end.
    """
    try:
        from native_image_graphs import NATIVE_IMAGE_FAMILIES

        return frozenset(str(f).strip().lower() for f in NATIVE_IMAGE_FAMILIES)
    except Exception:  # pragma: no cover - only if the builder module is unavailable
        return frozenset({"flux", "pixart", "lumina", "z_image", "anima", "krea2", "sd3"})


def _pil_model_path_available() -> bool:
    """Whether the diffusers runner's model upscale can actually run.

    Both packages are absent from both venvs, so this is False on this machine and has always been.
    It is a probe rather than a constant because installing them is a supported thing to do, and a
    constant would then be wrong in the other direction.
    """
    try:
        import importlib.util

        return bool(
            importlib.util.find_spec("basicsr") and importlib.util.find_spec("realesrgan")
        )
    except Exception:  # pragma: no cover
        return False


def _combo_choices(object_info: dict[str, Any] | None, class_name: str, input_name: str) -> list[str]:
    """Choices through the one reader, which absorbs both live ``/object_info`` shapes."""
    if not object_info:
        return []
    from comfy_graph_helpers import _comfy_input_choices

    return [c for c in _comfy_input_choices(object_info, class_name, input_name) if c.strip()]


def _next_numeric_id(graph: dict[str, Any]) -> int:
    nums = []
    for key in graph:
        try:
            nums.append(int(key))
        except (TypeError, ValueError):
            continue
    return (max(nums) if nums else 100) + 1


def _is_specialised(name: str) -> bool:
    lowered = name.lower()
    return any(marker in lowered for marker in _SPECIALISED_MARKERS)


def auto_upscale_model(choices: list[str]) -> str:
    """The model "Auto" means: a generalist, in catalog order, and only then anything at all."""
    for choice in choices:
        if not _is_specialised(choice):
            return choice
    return choices[0] if choices else ""


def resolve_upscale_model_name(object_info: dict[str, Any] | None, requested: Any) -> str:
    """Snap a requested upscaler onto a name the live loader genuinely offers.

    Returns "" when a name was asked for and no live choice matches -- the caller refuses rather
    than submitting a name ComfyUI will reject 400 lines into a graph. Doc 27 spells four of these
    models as stems, so a stem is matched against the choice's stem as well as its full name.
    """
    requested_name = str(requested or "").strip()
    choices = _combo_choices(object_info, "UpscaleModelLoader", "model_name")
    if not requested_name:
        return auto_upscale_model(choices)
    if not choices:
        # No live catalog to check against (an object_info-less caller, or a core that publishes no
        # loader). Passing the name through is the old behaviour and is right here: there is nothing
        # to contradict it.
        return requested_name

    base = requested_name.replace("\\", "/").split("/")[-1]
    stem = base.rsplit(".", 1)[0].lower()
    for choice in choices:
        if choice == requested_name:
            return choice
    for choice in choices:
        choice_base = choice.replace("\\", "/").split("/")[-1]
        if choice_base == base or choice_base.rsplit(".", 1)[0].lower() == stem:
            return choice
    return ""


def graft_pixel_upscale(
    graph: dict[str, Any],
    object_info: dict[str, Any] | None,
    *,
    model_name: Any = "",
    scale: float | None = None,
    target_width: int | None = None,
    target_height: int | None = None,
) -> dict[str, Any]:
    """Rewire every ``SaveImage`` through ``ImageUpscaleWithModel``, then to the asked-for size.

    ``ImageUpscaleWithModel`` has **no scale input** in the live schema -- it applies whatever
    factor the model was trained at, which for all six models on this box is 4x. The cockpit's
    Scale box therefore changed nothing on this route. It is honoured by following the model with
    an ``ImageScale`` to an explicit target computed from the requested dimensions, which is exact
    and needs no guess about the model's native factor from its filename.
    """
    if not isinstance(graph, dict) or not graph:
        return graph
    if object_info is not None and (
        "UpscaleModelLoader" not in object_info or "ImageUpscaleWithModel" not in object_info
    ):
        raise UpscaleUnavailable(
            "This ComfyUI does not provide UpscaleModelLoader / ImageUpscaleWithModel, so the "
            "model upscale cannot be performed. Choose an algorithmic method or turn upscale off."
        )

    requested = str(model_name or "").strip()
    resolved_model = resolve_upscale_model_name(object_info, model_name)
    if not resolved_model:
        available = _combo_choices(object_info, "UpscaleModelLoader", "model_name")
        if requested:
            raise UpscaleUnavailable(
                f"Upscale model {requested!r} is not one ComfyUI offers. Available: "
                + (", ".join(available) if available else "none")
            )
        raise UpscaleUnavailable(
            "Upscale was requested but this ComfyUI has no upscale models installed "
            "(models/upscale_models is empty)."
        )
    if requested and resolved_model != requested:
        log.warning("[upscale] %r resolved to the live catalog entry %r", requested, resolved_model)

    saves = [
        (nid, node)
        for nid, node in graph.items()
        if isinstance(node, dict) and node.get("class_type") == "SaveImage"
    ]
    if not saves:
        raise UpscaleUnavailable(
            "The graph for this family has no SaveImage to upscale into, so the request could not "
            "be applied."
        )

    want_resize = (
        scale is not None
        and target_width
        and target_height
        and object_info is not None
        and "ImageScale" in object_info
    )
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
        tail: list[Any] = [up_id, 0]
        if want_resize:
            scale_id = str(next_id)
            next_id += 1
            graph[scale_id] = {
                "class_type": "ImageScale",
                "inputs": {
                    "image": [up_id, 0],
                    "upscale_method": "lanczos",
                    "width": int(round(float(target_width) * float(scale))),
                    "height": int(round(float(target_height) * float(scale))),
                    "crop": "disabled",
                },
            }
            tail = [scale_id, 0]
        inputs["images"] = tail
    return graph


def graft_image_resize(
    graph: dict[str, Any],
    object_info: dict[str, Any] | None,
    *,
    method: Any,
    scale: float,
    target_width: int,
    target_height: int,
) -> dict[str, Any]:
    """Algorithmic resampling inside the graph, for a family whose image never reaches PIL."""
    if not isinstance(graph, dict) or not graph:
        return graph
    resample = _COMFY_RESAMPLE.get(str(method or "").strip().lower())
    if not resample:
        raise UpscaleUnavailable(f"No ComfyUI resampling filter matches {method!r}.")
    if object_info is not None and "ImageScale" not in object_info:
        raise UpscaleUnavailable("This ComfyUI does not provide ImageScale, so the resize cannot run.")
    if not (target_width and target_height and scale and scale > 1.0):
        return graph

    saves = [
        (nid, node)
        for nid, node in graph.items()
        if isinstance(node, dict) and node.get("class_type") == "SaveImage"
    ]
    if not saves:
        raise UpscaleUnavailable("The graph for this family has no SaveImage to resize into.")

    next_id = _next_numeric_id(graph)
    for _nid, node in saves:
        inputs = node.setdefault("inputs", {})
        image_ref = inputs.get("images")
        if not image_ref:
            continue
        scale_id = str(next_id)
        next_id += 1
        graph[scale_id] = {
            "class_type": "ImageScale",
            "inputs": {
                "image": image_ref,
                "upscale_method": resample,
                "width": int(round(float(target_width) * float(scale))),
                "height": int(round(float(target_height) * float(scale))),
                "crop": "disabled",
            },
        }
        inputs["images"] = [scale_id, 0]
    return graph
