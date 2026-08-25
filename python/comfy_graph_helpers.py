from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import os
import re

from video_family_contracts import infer_video_family_from_text, normalize_video_family_id

def _comfy_input_info(object_info: dict[str, Any], class_name: str) -> dict[str, Any]:
    class_info = object_info.get(class_name)
    if not isinstance(class_info, dict):
        return {}

    input_info = class_info.get("input")
    if not isinstance(input_info, dict):
        return {}

    return input_info

def _comfy_input_bucket(object_info: dict[str, Any], class_name: str, bucket: str) -> dict[str, Any]:
    input_info = _comfy_input_info(object_info, class_name)
    bucket_value = input_info.get(bucket)
    if not isinstance(bucket_value, dict):
        return {}

    return bucket_value

def _comfy_class_inputs(object_info: dict[str, Any], class_name: str) -> set[str]:
    names: set[str] = set()
    for bucket in ("required", "optional"):
        values = _comfy_input_bucket(object_info, class_name, bucket)
        names.update(str(name) for name in values.keys())
    return names

def _comfy_required_inputs(object_info: dict[str, Any], class_name: str) -> set[str]:
    values = _comfy_input_bucket(object_info, class_name, "required")
    return {str(name) for name in values.keys()}

def _first_available_class(object_info: dict[str, Any], candidates: tuple[str, ...], *, label: str) -> str:
    for class_name in candidates:
        if class_name in object_info:
            return class_name
    raise RuntimeError(
        f"The SpellVision native video template needs a Comfy node for {label}, but none of these classes are available: "
        + ", ".join(candidates)
        + ". Install/enable the appropriate Comfy video nodes, then retry."
    )

def _path_after_named_dir(path_value: str, dir_names: tuple[str, ...]) -> str:
    normalized = Path(path_value).as_posix()
    parts = normalized.split("/")
    lowered = [part.lower() for part in parts]
    for dir_name in dir_names:
        token = dir_name.lower()
        if token in lowered:
            idx = lowered.index(token)
            tail = "/".join(parts[idx + 1:]).strip("/")
            if tail:
                return tail
    return Path(path_value).name

def _comfy_unet_name(path_value: str) -> str:
    return _path_after_named_dir(path_value, ("diffusion_models", "unet", "checkpoints"))

def _comfy_vae_name(path_value: str) -> str:
    return _path_after_named_dir(path_value, ("vae",))

def _comfy_clip_name(path_value: str) -> str:
    return _path_after_named_dir(path_value, ("text_encoders", "clip", "encoders"))

def _filename_prefix_from_output(output_path: str, job_id: str) -> str:
    # Always fold the unique job_id into the prefix so every submission yields a NOVEL
    # filename_prefix. Without this, re-submitting an identical graph (fixed seed + same output:
    # a re-gen, a re-queue, or a concurrent near-duplicate) is byte-identical, so ComfyUI fully
    # caches every node INCLUDING SaveVideo, re-executes nothing, and reports EMPTY /history
    # outputs -- the worker then has no asset to retrieve and the poll stalls at 95%. A unique
    # prefix invalidates the terminal save node's cache entry so it always re-runs (upstream
    # stays cached -- no wasted compute) and its output is always reported. The worker copies the
    # saved file to req["output"], so the ComfyUI-side name never surfaces to the user.
    safe_job = re.sub(r"[^a-zA-Z0-9_\-]+", "_", str(job_id or "")).strip("_")[:24] or "job"
    dest = Path(str(output_path or "").strip())
    raw_stem = dest.stem
    if raw_stem.lower().startswith("plate") and dest.parent.name:
        raw_stem = dest.parent.name
    stem = re.sub(r"[^a-zA-Z0-9_\-]+", "_", raw_stem).strip("_")[:72]
    if stem:
        return f"{stem}_{safe_job}"
    return f"spellvision_native_video_{safe_job}"

def _set_if_allowed(inputs: dict[str, Any], allowed: set[str], aliases: tuple[str, ...], value: Any) -> bool:
    if value is None:
        return False
    for name in aliases:
        if name in allowed:
            inputs[name] = value
            return True
    return False

def _clip_loader_type_for_family(family: str) -> str:
    family = str(family or "").strip().lower()
    if family == "wan":
        return "wan"
    if family == "hunyuan_video":
        return "hunyuan_video"
    if family == "ltx":
        return "ltxv"
    if family == "mochi":
        return "mochi"
    return "stable_diffusion"

def _add_node(prompt: dict[str, Any], node_id: str, class_type: str, inputs: dict[str, Any]) -> None:
    prompt[node_id] = {"class_type": class_type, "inputs": inputs}

def _int_or_default(value: Any, default: int) -> int:
    if value in (None, ""):
        return default

    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def _build_clip_loader_node(
    prompt: dict[str, Any],
    object_info: dict[str, Any],
    stack: dict[str, Any],
    family: str,
) -> str:
    clip1_path = str(stack.get("text_encoder_path") or "").strip()
    clip2_path = str(stack.get("text_encoder_2_path") or "").strip()
    if not clip1_path:
        raise RuntimeError("The selected native split video stack does not include a text encoder path.")

    if clip2_path and "DualCLIPLoader" in object_info:
        class_name = "DualCLIPLoader"
        allowed = _comfy_class_inputs(object_info, class_name)
        inputs: dict[str, Any] = {}
        _set_if_allowed(inputs, allowed, ("clip_name1", "clip1_name"), _comfy_clip_name(clip1_path))
        _set_if_allowed(inputs, allowed, ("clip_name2", "clip2_name"), _comfy_clip_name(clip2_path))
        _set_if_allowed(inputs, allowed, ("type", "clip_type"), _clip_loader_type_for_family(family))
        _add_node(prompt, "2", class_name, inputs)
        return "2"

    class_name = _first_available_class(object_info, ("CLIPLoader", "DualCLIPLoader"), label="text encoder loading")
    allowed = _comfy_class_inputs(object_info, class_name)
    inputs = {}
    if class_name == "DualCLIPLoader":
        _set_if_allowed(inputs, allowed, ("clip_name1", "clip1_name"), _comfy_clip_name(clip1_path))
        _set_if_allowed(inputs, allowed, ("clip_name2", "clip2_name"), _comfy_clip_name(clip1_path))
    else:
        _set_if_allowed(inputs, allowed, ("clip_name", "clip", "text_encoder_name"), _comfy_clip_name(clip1_path))
    _set_if_allowed(inputs, allowed, ("type", "clip_type"), _clip_loader_type_for_family(family))
    _add_node(prompt, "2", class_name, inputs)
    return "2"

def _comfy_input_choices(object_info: dict[str, Any], class_name: str, input_name: str) -> list[str]:
    if not isinstance(object_info, dict):
        return []

    info = object_info.get(class_name)
    if not isinstance(info, dict):
        return []

    raw_input_info = info.get("input")
    if not isinstance(raw_input_info, dict):
        return []

    for bucket in ("required", "optional"):
        values = raw_input_info.get(bucket)
        if not isinstance(values, dict):
            continue

        spec = values.get(input_name)
        if not isinstance(spec, (list, tuple)) or not spec:
            continue

        first = spec[0]
        if isinstance(first, (list, tuple)):
            return [str(item) for item in first if str(item).strip()]

    return []

def _sv_comfy_input_choices(object_info: dict[str, Any], class_name: str, input_name: str) -> list[str]:
    for bucket in ("required", "optional"):
        values = _comfy_input_bucket(object_info, class_name, bucket)
        spec = values.get(input_name)
        if isinstance(spec, (list, tuple)) and spec:
            first = spec[0]
            if isinstance(first, (list, tuple)):
                return [str(item) for item in first if str(item).strip()]
            if len(spec) > 1 and isinstance(spec[1], dict):
                options = spec[1].get("options")
                if isinstance(options, list):
                    return [str(item) for item in options if str(item).strip()]
    return []

def _sv_choose_comfy_choice(object_info: dict[str, Any], class_name: str, input_name: str, requested: str) -> str:
    requested = str(requested or "").strip()
    requested_name = Path(requested).name
    available = _sv_comfy_input_choices(object_info, class_name, input_name)
    if not available:
        return requested_name or requested

    by_lower = {item.lower(): item for item in available}
    for candidate in (requested, requested_name):
        found = by_lower.get(str(candidate).lower())
        if found:
            return found

    # Prefer a basename match when a stale subfolder-prefixed value leaks through.
    for item in available:
        if Path(item).name.lower() == requested_name.lower():
            return item

    return requested_name or requested

def _sv_set_default_required_inputs(
    inputs: dict[str, Any],
    object_info: dict[str, Any],
    class_name: str,
    *,
    skip: set[str] | None = None,
) -> None:
    skip = skip or set()
    for input_name in sorted(_comfy_required_inputs(object_info, class_name)):
        if input_name in inputs or input_name in skip:
            continue
        default_value = _input_default_choice(object_info, class_name, input_name, None)
        if default_value is not None:
            inputs[input_name] = default_value

def _sv_choice_or_default(
    object_info: dict[str, Any],
    class_name: str,
    input_name: str,
    requested: Any,
    default: str,
) -> str:
    choices = _sv_comfy_input_choices(object_info, class_name, input_name)
    by_lower = {str(item).strip().lower(): str(item).strip() for item in choices}

    requested_text = str(requested or "").strip()
    if requested_text:
        found = by_lower.get(requested_text.lower())
        if found:
            return found

    found_default = by_lower.get(str(default).strip().lower())
    if found_default:
        return found_default

    if choices:
        return str(choices[0]).strip()

    return default

def _sv_basename(value: Any) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        return ""
    return Path(text).name

def _sv_is_fp8_scaled_name(value: Any) -> bool:
    name = _sv_basename(value).lower()
    return bool(name and "fp8" in name and "scaled" in name)

def _sv_video_lora_name(object_info: dict[str, Any], lora_path: str, *, class_name: str) -> str:
    # Resolve a LoRA path to the LoraLoaderModelOnly.lora_name COMBO entry -- the same subdir-qualified
    # basename resolution _sv_video_primary_name does for UNET names (loras/ is the named model dir).
    return _sv_choose_comfy_choice(object_info, class_name, "lora_name", _path_after_named_dir(lora_path, ("loras",)))

def _wan_lora_stack_entries(req: dict[str, Any]) -> list[dict[str, Any]]:
    # The frontend sends lora_stack (== loras) = [{"name": <path>, "strength": <double>, "enabled": <bool>}].
    # Read name/strength (NOT path/scale -- those are model_sources.py's keys, a different layer). Keep
    # only enabled==True entries, preserving stack order.
    raw = req.get("lora_stack")
    if not isinstance(raw, list):
        raw = req.get("loras")
    entries: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict) or item.get("enabled") is False:
                continue
            name = str(item.get("name") or item.get("value") or "").strip()
            if not name:
                continue
            try:
                strength = float(item.get("strength", item.get("weight", 1.0)))
            except (TypeError, ValueError):
                strength = 1.0
            entries.append({"name": name, "strength": strength})
    return entries

def _emit_wan_lora_chain(prompt: dict[str, Any], object_info: dict[str, Any], model_ref: list[Any], lora_entries: list[dict[str, Any]], *, node_prefix: str) -> list[Any]:
    """Thread a chain of LoraLoaderModelOnly (model-only) nodes onto model_ref: UNET -> LoRA_1 -> LoRA_2
    -> ... -> returned ref. Each node's `model` input = the PREVIOUS node's output (the chain), lora_name
    resolved against the live LoraLoaderModelOnly choices, strength_model = the entry's single strength.
    An empty list returns model_ref unchanged and emits NO nodes -- the no-LoRA path stays byte-identical."""
    if not lora_entries:
        return model_ref
    lora_class = _first_available_class(object_info, ("LoraLoaderModelOnly",), label="WAN dual-noise LoRA loading")
    allowed = _comfy_class_inputs(object_info, lora_class)
    current = model_ref
    for index, entry in enumerate(lora_entries):
        node_id = f"{node_prefix}{index}"
        inputs: dict[str, Any] = {}
        _set_if_allowed(inputs, allowed, ("model",), current)
        _set_if_allowed(inputs, allowed, ("lora_name",), _sv_video_lora_name(object_info, str(entry["name"]), class_name=lora_class))
        _set_if_allowed(inputs, allowed, ("strength_model",), float(entry["strength"]))
        _add_node(prompt, node_id, lora_class, inputs)
        current = [node_id, 0]
    return current

# ============================================================================
# Native IMAGE path (route B, Flux-B / B-img1). The `native_comfy_template` path
# existed only for VIDEO (run_native_video). Flux single-file transformers can't be
# loaded by diffusers from_single_file without the gated FLUX.1-dev config/tokenizers
# (fresh-machine STOP, proven live), but ComfyUI's UNETLoader/DualCLIPLoader/VAELoader
# eat the on-disk single-file format natively with zero downloads. So Flux renders
# through a ComfyUI graph, mirroring run_native_split_stack_video but producing a PNG.
# B-img1 = the scaffold with a HAND-CODED Flux graph + FIXED companions; the grounded
# template + resolve_stack (Flux-A) precision-matched companions + readiness are B-img2.
# ============================================================================

def _comfy_ckpt_name_for_model(object_info: dict[str, Any], model_path: str) -> str:
    """Map a local checkpoint path to the exact CheckpointLoaderSimple.ckpt_name combo entry.

    ComfyUI lists checkpoints as subdir-qualified names (e.g. "flux\\fluxmania_kreamania.safetensors").
    We match by basename against the live /object_info choices so the graph references the name the
    loader actually expects (separator + subdir included), not the absolute path.
    """
    base = Path(str(model_path or "").replace("\\", "/")).name.strip().lower()
    if not base:
        return ""
    node = object_info.get("CheckpointLoaderSimple") or {}
    spec = ((node.get("input") or {}).get("required") or {}).get("ckpt_name")
    choices = spec[0] if isinstance(spec, list) and spec and isinstance(spec[0], list) else []
    for c in choices:
        if Path(str(c).replace("\\", "/")).name.strip().lower() == base:
            return str(c)
    return ""

def _comfy_unet_name_for_model(object_info: dict[str, Any], model_path: str) -> str:
    """UNETLoader sibling of _comfy_ckpt_name_for_model, for split-stack families (Z-Image, ...) whose
    transformer lives in diffusion_models/ and loads via UNETLoader.unet_name -- NOT CheckpointLoaderSimple.
    Match by basename against the live /object_info UNETLoader choices (subdir + separator included).
    """
    base = Path(str(model_path or "").replace("\\", "/")).name.strip().lower()
    if not base:
        return ""
    node = object_info.get("UNETLoader") or {}
    spec = ((node.get("input") or {}).get("required") or {}).get("unet_name")
    choices = spec[0] if isinstance(spec, list) and spec and isinstance(spec[0], list) else []
    for c in choices:
        if Path(str(c).replace("\\", "/")).name.strip().lower() == base:
            return str(c)
    return ""


def _first_nonempty_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _video_stack_basename(value: Any) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        return ""
    return os.path.basename(text)


def _video_stack_first(stack: dict[str, Any], *keys: str) -> str:
    for key in keys:
        text = str(stack.get(key) or "").strip()
        if text:
            return text
    return ""


def _video_model_stack_from_request(req: dict[str, Any]) -> dict[str, Any]:
    raw = req.get("video_model_stack") or req.get("model_stack") or {}
    return dict(raw) if isinstance(raw, dict) else {}


def _first_stack_value(stack: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = str(stack.get(key) or "").strip()
        if value:
            return value
    return ""


def _stack_missing_parts(stack: dict[str, Any]) -> list[str]:
    raw = stack.get("missing_parts")
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def _video_family_from_request_parts(req: dict[str, Any], stack: dict[str, Any]) -> str:
    explicit = _first_nonempty_text(
        req.get("resolved_native_video_family"),
        req.get("video_family"),
        req.get("model_family"),
        req.get("family"),
        stack.get("video_family"),
        stack.get("model_family"),
        stack.get("family"),
    )
    if explicit:
        return normalize_video_family_id(explicit)
    return infer_video_family_from_text(
        req.get("model"),
        req.get("model_display"),
        req.get("workflow_profile_name"),
        req.get("profile_path"),
        req.get("workflow_profile_path"),
        json.dumps(stack, sort_keys=True) if stack else "",
    )


def _input_default_choice(object_info: dict[str, Any], class_name: str, input_name: str, fallback: Any = None) -> Any:
    for bucket in ("required", "optional"):
        values = _comfy_input_bucket(object_info, class_name, bucket)
        if input_name not in values:
            continue
        spec = values.get(input_name)
        if isinstance(spec, dict):
            default_value = spec.get("default")
            if default_value is not None:
                return default_value
        if isinstance(spec, (list, tuple)) and spec:
            first = spec[0]
            if isinstance(first, list) and first:
                return first[0]
            if isinstance(first, tuple) and first:
                return first[0]
            if len(spec) > 1 and isinstance(spec[1], dict):
                default_value = spec[1].get("default")
                if default_value is not None:
                    return default_value
                options = spec[1].get("options")
                if isinstance(options, list) and options:
                    return options[0]
        if isinstance(spec, (list, tuple)) and len(spec) > 1 and isinstance(spec[1], dict):
            default_value = spec[1].get("default")
            if default_value is not None:
                return default_value
    return fallback


