from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from comfy_graph_helpers import (
    text_encoder_device_input,
    vae_decode_node,
    text_encoder_device,
    _add_node,
    _build_clip_loader_node,
    _comfy_class_inputs,
    _comfy_input_choices,
    _comfy_unet_name,
    _comfy_unet_name_for_model,
    _comfy_vae_name,
    _emit_wan_lora_chain,
    _filename_prefix_from_output,
    _first_available_class,
    _first_stack_value,
    _input_default_choice,
    resolve_seed,
    task_of,
    sampling_for,
    stated_seed,
    _set_if_allowed,
    _stack_missing_parts,
    _sv_basename,
    _sv_choice_or_default,
    _sv_choose_comfy_choice,
    _sv_comfy_input_choices,
    _sv_is_fp8_scaled_name,
    _sv_set_default_required_inputs,
    _video_family_from_request_parts,
    _video_model_stack_from_request,
    _video_stack_first,
    _wan_lora_stack_entries,
)
from family_operating_points import (
    accel_loras_for,
    operating_point_params,
    resolve_family_defaults,
    resolve_operating_point,
)
from video_adapters.registry import select_native_video_adapter
from request_payload import bounded_option
from upscale_engine import (
    ROUTE_PIXEL_COMFY,
    ROUTE_RESIZE_COMFY,
    graft_image_resize,
    graft_pixel_upscale,
    resolve_upscale_route,
)
from video_family_contracts import (
    normalize_video_family_id,
    video_family_contract,
    video_family_pipeline_candidates,
)

log = logging.getLogger("spellvision.worker")

VIDEO_LOW_MODEL_KEYS = (
    "low_model",
    "low_model_path",
    "low_noise_model",
    "low_noise_model_path",
    "low_noise_path",
    "wan_low_noise_path",
    "low_unet_path",
    "low_noise_unet_path",
)
VIDEO_HIGH_MODEL_KEYS = (
    "high_model",
    "high_model_path",
    "high_noise_model",
    "high_noise_model_path",
    "high_noise_path",
    "wan_high_noise_path",
    "high_unet_path",
    "high_noise_unet_path",
)
VIDEO_PRIMARY_MODEL_KEYS = (
    "primary",
    "primary_path",
    "diffusers_path",
    "transformer",
    "transformer_path",
    "unet",
    "unet_path",
    "model",
    "model_path",
)


@dataclass
class NativeFamilyPlugin:
    family: str
    kind: str
    build: Any
    match_prefix: str = ""



def _native_video_model_reference(req: dict[str, Any]) -> str:
    stack = _video_model_stack_from_request(req)
    if stack:
        diffusers_path = _first_stack_value(stack, ("diffusers_path", "model_dir", "model_directory"))
        if diffusers_path:
            return diffusers_path

        primary = _first_stack_value(stack, ("primary_path", "transformer_path", "unet_path", "model_path"))
        if primary:
            return primary

    model = str(req.get("model") or req.get("model_id") or "").strip()
    if model.startswith("hf://"):
        model = model[5:]
    if not model:
        raise RuntimeError("Native video generation requires a model directory, Hugging Face repo id, or configured video model stack.")
    return model


def _infer_native_video_family(req: dict[str, Any]) -> str:
    stack = _video_model_stack_from_request(req)
    family = _video_family_from_request_parts(req, stack)
    return family if family != "unknown" else "unknown"


def _native_video_pipeline_candidates(command: str, family: str) -> list[str]:
    candidates = video_family_pipeline_candidates(command, family)
    if candidates:
        return candidates

    return [
        "WanImageToVideoPipeline",
        "WanPipeline",
        "LTXImageToVideoPipeline",
        "LTXVideoPipeline",
        "CogVideoXImageToVideoPipeline",
        "CogVideoXPipeline",
        "HunyuanVideoPipeline",
        "MochiPipeline",
    ] if str(command or "").strip().lower() == "i2v" else [
        "WanPipeline",
        "LTXVideoPipeline",
        "CogVideoXPipeline",
        "HunyuanVideoPipeline",
        "MochiPipeline",
    ]


def _is_split_video_stack_request(req: dict[str, Any]) -> bool:
    stack = _video_model_stack_from_request(req)
    stack_kind = str(stack.get("stack_kind") or req.get("native_video_stack_kind") or "").strip().lower()
    # wan_dual_noise routes to the split path the same way split_stack does -- BEFORE the primary-model
    # requirement below. The dual-noise builder reads high/low experts from the stack and ignores a
    # primary model, so requiring one was never meaningful for this stack kind; without this early
    # return a dual-noise request whose `model` is empty (the frontend sends the key but draft.model
    # can be blank when only high/low experts are selected) raises in _native_video_model_reference
    # before the builder ever runs.
    if stack_kind in ("split_stack", "wan_dual_noise"):
        return True
    model_ref = _native_video_model_reference(req)
    return Path(model_ref).suffix.lower() in {".safetensors", ".ckpt", ".bin", ".gguf"}

def _preferred_video_vae_name(object_info: dict[str, Any], family: str, vae_path: str, primary_path: str = "") -> str:
    requested = _comfy_vae_name(vae_path)
    available = _comfy_input_choices(object_info, "VAELoader", "vae_name")
    available_lower = {item.lower(): item for item in available}

    family_key = str(family or "").strip().lower()

    if family_key == "wan":
        # Version-aware order (interim VAE-variant fix), same as the core resolver.
        for preferred in _wan_vae_preference(primary_path, vae_path):
            found = available_lower.get(preferred.lower())
            if found:
                return found

        for item in available:
            lowered = item.lower()
            if "wan" in lowered and "vae" in lowered and "onthefly" not in lowered:
                return item

    if family_key in {"hunyuan_video", "hunyuan"}:
        for preferred in (
            "hunyuan_video_vae_bf16.safetensors",
            "hunyuan_video_vae_fp16.safetensors",
        ):
            found = available_lower.get(preferred.lower())
            if found:
                return found

    if requested in available:
        return requested

    return requested

def _sv_video_primary_name(object_info: dict[str, Any], primary_path: str, *, class_name: str = "WanVideoModelLoader") -> str:
    return _sv_choose_comfy_choice(object_info, class_name, "model", _comfy_unet_name(primary_path))

def _sv_video_text_encoder_name(object_info: dict[str, Any], stack: dict[str, Any]) -> str:
    explicit = str(stack.get("text_encoder_path") or stack.get("text_encoder") or "").strip()
    available = _sv_comfy_input_choices(object_info, "LoadWanVideoT5TextEncoder", "model_name")
    by_lower = {item.lower(): item for item in available}

    if explicit:
        found = by_lower.get(Path(explicit).name.lower())
        if found:
            return found

    for preferred in (
        "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
        "umt5_xxl_fp16.safetensors",
        "umt5_xxl_bf16.safetensors",
        "t5xxl_fp8_e4m3fn_scaled.safetensors",
        "t5xxl_fp16.safetensors",
        "t5xxl_bf16.safetensors",
    ):
        found = by_lower.get(preferred.lower())
        if found:
            return found

    for item in available:
        lowered = item.lower()
        if "umt5" in lowered or "t5xxl" in lowered or "t5" in lowered:
            return item

    return Path(explicit).name if explicit else ""

def _sv_video_vae_name(object_info: dict[str, Any], stack: dict[str, Any]) -> str:
    explicit = str(stack.get("vae_path") or stack.get("vae") or "").strip()
    available = _sv_comfy_input_choices(object_info, "WanVideoVAELoader", "model_name")
    by_lower = {item.lower(): item for item in available}

    if explicit:
        found = by_lower.get(Path(explicit).name.lower())
        if found:
            return found

    for preferred in (
        "wan2.2_vae.safetensors",
        "wan_2.1_vae.safetensors",
        "onTHEFLYWanAIWan21VideoModel_kijaiWan21VAE.safetensors",
    ):
        found = by_lower.get(preferred.lower())
        if found:
            return found

    for item in available:
        lowered = item.lower()
        if "wan" in lowered and "vae" in lowered:
            return item

    return Path(explicit).name if explicit else ""

def _sv_add_wan_empty_embeds_node(
    prompt: dict[str, Any],
    object_info: dict[str, Any],
    req: dict[str, Any],
    *,
    node_id: str,
) -> str:
    class_name = _first_available_class(
        object_info,
        (
            "WanVideoEmptyEmbeds",
            "WanVideoEmptyTextEmbeds",
            "WanVideoEmptyMMAudioLatents",
            "WanVideoImageToVideoEncode",
        ),
        label="WAN empty/text-to-video image embeds",
    )
    allowed = _comfy_class_inputs(object_info, class_name)
    inputs: dict[str, Any] = {}
    width = bounded_option(req, "width", 832)
    height = bounded_option(req, "height", 480)
    frames = bounded_option(req, "frames", 81)

    _set_if_allowed(inputs, allowed, ("width",), width)
    _set_if_allowed(inputs, allowed, ("height",), height)
    _set_if_allowed(inputs, allowed, ("num_frames", "frames", "length", "video_length", "frame_count"), frames)
    _set_if_allowed(inputs, allowed, ("batch_size",), 1)
    _sv_set_default_required_inputs(inputs, object_info, class_name)
    _add_node(prompt, node_id, class_name, inputs)
    return node_id

def _sv_core_wan_choice(object_info: dict[str, Any], class_name: str, input_name: str, requested: Any, defaults: tuple[str, ...]) -> str:
    choices = _comfy_input_choices(object_info, class_name, input_name)
    if not choices:
        return str(requested or (defaults[0] if defaults else "")).strip()

    by_lower = {str(choice).strip().lower(): str(choice).strip() for choice in choices}
    requested_text = str(requested or "").strip()
    if requested_text:
        found = by_lower.get(requested_text.lower())
        if found:
            return found

    for default in defaults:
        found = by_lower.get(str(default).lower())
        if found:
            return found

    return str(choices[0]).strip()

def _sv_core_wan_clip_name(object_info: dict[str, Any], stack: dict[str, Any], req: dict[str, Any]) -> str:
    explicit = str(req.get("video_text_encoder") or req.get("text_encoder") or stack.get("text_encoder") or stack.get("text_encoder_path") or stack.get("clip") or stack.get("clip_path") or "").strip()
    requested = _sv_basename(explicit)
    choices = _comfy_input_choices(object_info, "CLIPLoader", "clip_name")
    if not choices:
        return requested

    by_lower = {choice.lower(): choice for choice in choices}
    if requested:
        found = by_lower.get(requested.lower())
        if found:
            return found

    for preferred in ("umt5_xxl_fp8_e4m3fn_scaled.safetensors", "t5xxl_fp8_e4m3fn_scaled.safetensors", "t5xxl_fp16.safetensors"):
        found = by_lower.get(preferred.lower())
        if found:
            return found

    for choice in choices:
        lowered = choice.lower()
        if "umt5" in lowered or "t5" in lowered:
            return choice

    return choices[0]

def _sv_core_wan_vae_name(object_info: dict[str, Any], stack: dict[str, Any], primary_path: str = "", *, force_version: str = "") -> str:
    explicit = str(stack.get("vae_path") or stack.get("vae") or "").strip()
    requested = _sv_basename(explicit)
    choices = _comfy_input_choices(object_info, "VAELoader", "vae_name")
    if not choices:
        return requested

    by_lower = {choice.lower(): choice for choice in choices}
    if requested:  # explicit stack VAE always wins
        found = by_lower.get(requested.lower())
        if found:
            return found

    # Auto-resolve version-matched (interim VAE-variant fix): pick the VAE matching the
    # loaded Wan version instead of a blind 2.2-first guess. The probe reads the model
    # path (from the builder, which is req["model"] when the stack is bare -- the exact
    # crashing repro). Inconclusive -> the original 2.2-first order.
    # force_version overrides the filename probe: the Wan 2.2 A14B DUAL-NOISE stack uses the 16-ch
    # 2.1 VAE (wan_2.1_vae), which the "high_noise"/"low_noise" filename probe would otherwise mis-map
    # to the 48-ch 2.2 VAE. (The 5B TI2V path, which DOES use the 2.2 VAE, has no route yet -- future.)
    if force_version:
        preference = _wan_vae_preference_for_version(force_version)
    else:
        probe_path = primary_path or _first_stack_value(stack, ("primary_path", "transformer_path", "unet_path", "model_path"))
        preference = _wan_vae_preference(probe_path, str(stack.get("family") or ""))
    for preferred in preference:
        found = by_lower.get(preferred.lower())
        if found:
            return found

    for choice in choices:
        lowered = choice.lower()
        if "wan" in lowered and "vae" in lowered:
            return choice

    return choices[0]

def _path_looks_high_noise(path_value: str) -> bool:
    # Wan 2.2 dual-noise HIGH half by filename (lifted from the archived dual-core
    # fix). Noise-half is NOT a family concept and the classifier/registry don't carry
    # it, so it stays a filename predicate. Used only by the single-model i2v refuse-guard.
    haystack = str(path_value or "").replace("\\", "/").lower()
    return any(tok in haystack for tok in ("high_noise", "high-noise", "t2v_high", "_high_"))

def _path_looks_low_noise(path_value: str) -> bool:
    haystack = str(path_value or "").replace("\\", "/").lower()
    return any(tok in haystack for tok in ("low_noise", "low-noise", "t2v_low", "_low_"))

def _wan_vae_version_marker(*path_values: str) -> str:
    # "2.1" / "2.2" / "" from the model filename signal, to pick the VAE that matches
    # the loaded Wan version (2.1 latent = 16ch -> wan_2.1_vae; 2.2 = 48ch -> wan2.2_vae).
    # INTERIM for Doc 19's variant disambiguation -- reuses the existing filename signal,
    # invents no new classifier. The full producer-side resolution supersedes this later.
    h = " ".join(str(p or "") for p in path_values).replace("\\", "/").lower()
    if any(t in h for t in ("wan2.2", "wan_2.2", "wan-2.2", "wan22")) or "high_noise" in h or "low_noise" in h:
        return "2.2"
    if any(t in h for t in ("wan2.1", "wan_2.1", "wan-2.1", "wan21", "i2v_480p_14b", "i2v_720p_14b")):
        return "2.1"
    return ""

def _wan_vae_preference_for_version(marker: str) -> tuple[str, ...]:
    # Version-ranked VAE order for a KNOWN version. "2.1" -> 2.1-first (Wan 2.1 single-model AND
    # Wan 2.2 A14B dual-noise, which uses the 16-ch 2.1 VAE, NOT the 48-ch 2.2 VAE); anything else
    # -> the original 2.2-first order.
    if str(marker).strip() == "2.1":
        return ("wan_2.1_vae.safetensors", "wan2.1_vae.safetensors", "wan2.2_vae.safetensors", "wan_2.2_vae.safetensors")
    return ("wan2.2_vae.safetensors", "wan_2.2_vae.safetensors", "wan2.1_vae.safetensors", "wan_2.1_vae.safetensors")

def _wan_vae_preference(*path_values: str) -> tuple[str, ...]:
    # Version-aware VAE preference order from the FILENAME probe. On an inconclusive probe, falls
    # back to the original 2.2-first order (unchanged behavior for unmarked models).
    return _wan_vae_preference_for_version(_wan_vae_version_marker(*path_values))

def _sv_core_wan_clip_vision_name(object_info: dict[str, Any], stack: dict[str, Any], req: dict[str, Any]) -> str:
    # Resolve the Wan i2v CLIP-vision (CLIP-ViT-H) filename from the request/stack,
    # validated against the LIVE CLIPVisionLoader choices. Empty return -> omit
    # clip_vision (WanImageToVideo.clip_vision_output is optional -> the no-clip_vision
    # branch, valid for Wan 2.2 i2v which needs no CLIP-vision).
    requested = str(
        req.get("clip_vision") or req.get("clip_vision_path")
        or stack.get("clip_vision") or stack.get("clip_vision_path") or ""
    ).strip()
    requested_name = Path(requested).name if requested else ""
    choices = _comfy_input_choices(object_info, "CLIPVisionLoader", "clip_name")
    by_lower = {str(c).strip().lower(): str(c).strip() for c in choices}
    if requested_name and requested_name.lower() in by_lower:
        return by_lower[requested_name.lower()]
    for pref in ("clip_vision_h.safetensors", "clip_vision_vit_h.safetensors"):
        if pref in by_lower:
            return by_lower[pref]
    for low, orig in by_lower.items():
        if "clip_vision_h" in low or ("vit" in low and "_h" in low):
            return orig
    return ""

def _should_use_native_wan_core_route(req: dict[str, Any], object_info: dict[str, Any]) -> bool:
    route = str(req.get("native_video_route") or req.get("wan_text_route") or req.get("video_route") or "auto").strip().lower().replace("-", "_")
    if route in {"wrapper", "wan_wrapper", "wanvideowrapper", "wan_video_wrapper"}:
        return False
    if route in {"core", "wan_core", "core_wan", "comfy_core"}:
        return True

    stack = _video_model_stack_from_request(req)
    text_encoder = str(req.get("video_text_encoder") or req.get("text_encoder") or stack.get("text_encoder") or stack.get("text_encoder_path") or stack.get("clip") or stack.get("clip_path") or "").strip()
    if _sv_is_fp8_scaled_name(text_encoder):
        return True

    return True

def _sv_core_choice_or_default(
    object_info: dict[str, Any],
    class_name: str,
    input_name: str,
    requested: Any,
    default: str,
) -> str:
    choices = _comfy_input_choices(object_info, class_name, input_name)
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

def _wan_dual_expert_path(req: dict[str, Any], stack: dict[str, Any], keys: tuple[str, ...]) -> str:
    # A dual-noise expert path lives in the video_model_stack (AssetCatalogScanner populates
    # high_noise_path/high_noise_model_path/wan_high_noise_path + low equivalents), but may also
    # arrive at the request top level -- check the stack first, then the request, across all aliases.
    value = _video_stack_first(stack, *keys)
    if value:
        return value
    for key in keys:
        value = str(req.get(key) or "").strip()
        if value:
            return value
    return ""

def _is_wan_dual_noise_request(req: dict[str, Any]) -> bool:
    # True iff the request is a Wan 2.2 A14B dual-noise stack (stack_kind marker) carrying BOTH
    # experts. The C++ frontend sets native_video_stack_kind (GenerationRequestBuilder) and stacks
    # stack_kind/stack_mode (AssetCatalogScanner); accept any of them.
    stack = _video_model_stack_from_request(req)
    kind = str(
        req.get("native_video_stack_kind")
        or req.get("video_stack_kind")
        or stack.get("stack_kind")
        or stack.get("stack_mode")
        or ""
    ).strip().lower()
    if kind != "wan_dual_noise":
        return False
    high = _wan_dual_expert_path(req, stack, VIDEO_HIGH_MODEL_KEYS)
    low = _wan_dual_expert_path(req, stack, VIDEO_LOW_MODEL_KEYS)
    return bool(high and low)

def _wan_expert_task_variant(path_value: str) -> str:
    # t2v / i2v task variant from an expert filename (for the dual-noise pairing guard). "" if neither.
    haystack = str(path_value or "").replace("\\", "/").lower()
    if "t2v" in haystack:
        return "t2v"
    if "i2v" in haystack:
        return "i2v"
    return ""

def _wan_split_step(req: dict[str, Any], steps: int) -> int:
    """Where the high-noise expert hands over to the low-noise one.

    The cockpit's Split combo offers four choices -- Auto midpoint, Manual split step, Favor
    high-noise, Favor low-noise -- and NONE of them did anything. `wan_split` carries the mode and
    `split_step` the manual value; the builder read neither and always used ``steps // 2``, so all
    four entries rendered the same video. `wan_split_mode` is the same value under a second name,
    sent by the same line of the request builder.

    The bias ratios are the obvious reading of the labels rather than a measured optimum: two
    thirds of the budget to the expert the user favoured. They are a starting point for a
    measurement, and saying so here is better than a number that looks authoritative.
    """
    mode = str(req.get("wan_split") or req.get("wan_split_mode") or "auto").strip().lower()
    if mode == "manual":
        return bounded_option(
            req, "split_step", steps // 2,
            aliases=("split_step", "noise_split_step", "wan_noise_split_step"),
            minimum=1, maximum=steps - 1,
        )
    if mode == "high_bias":
        return max(1, min(steps - 1, round(steps * 2 / 3)))
    if mode == "low_bias":
        return max(1, min(steps - 1, round(steps / 3)))
    if mode not in {"auto", ""}:
        logging.warning("Unknown wan_split mode %r; using the auto midpoint.", mode)
    return steps // 2


def _build_native_wan_dual_noise_video_prompt(req: dict[str, Any], object_info: dict[str, Any], *, command: str, family: str, job_id: str) -> dict[str, Any]:
    """Wan 2.2 A14B dual-expert (MoE) T2V. TWO diffusion checkpoints (high-noise + low-noise), one per
    KSamplerAdvanced stage: the high-noise expert denoises steps [0, split) and passes its leftover
    noise to the low-noise expert, which finishes [split, steps]. Grounded on the official ComfyUI
    video_wan2_2_14B_t2v template (two UNETLoader weight_dtype="default", two ModelSamplingSD3 shift 5.0,
    EmptyHunyuanLatentVideo, umt5 CLIP type "wan", wan_2.1 VAE, both text-encodes feed BOTH samplers).
    The template's LoRA/switch/primitive/math/markdown scaffolding is flattened away (literals baked) --
    same pruning discipline as the LTX migration; optional LoRA is a later pass via the contract's
    optional_components slot, not the switch machinery.

    Defaults are BASE-MODEL (full fp8 14B, no acceleration LoRA): steps=20 / cfg=3.5 is a sane Wan-T2V
    budget. The official template's steps=4 / cfg=1 / split=2 is the Lightx2v-LoRA config -- a no-LoRA
    render at 4 steps looks terrible, so it is NOT the default, but every knob is req-overridable, so the
    LoRA path is reachable later by passing steps=4, cfg=1. split = steps // 2 (grounded).

    I2V (2026-08-17 ship lock): same two-expert sampler chain, but WanImageToVideo replaces the empty
    latent. Conditioning enters ONCE and is shared by both stages."""
    if command not in ("t2v", "i2v"):
        raise RuntimeError(
            "The Wan 2.2 dual-noise MoE builder supports T2V and I2V only."
        )

    stack = _video_model_stack_from_request(req)
    high_path = _wan_dual_expert_path(req, stack, VIDEO_HIGH_MODEL_KEYS)
    low_path = _wan_dual_expert_path(req, stack, VIDEO_LOW_MODEL_KEYS)
    # Dual-noise contract required_components: BOTH experts. A dual-noise request missing one is an
    # error naming the absent expert -- NOT a silent fall-back to a single-model primary_path render.
    if not high_path:
        raise RuntimeError(
            "Wan 2.2 dual-noise T2V requires the HIGH-noise expert checkpoint "
            "(high_noise_path / high_noise_model_path / wan_high_noise_path); none was provided."
        )
    if not low_path:
        raise RuntimeError(
            "Wan 2.2 dual-noise T2V requires the LOW-noise expert checkpoint "
            "(low_noise_path / low_noise_model_path / wan_low_noise_path); none was provided."
        )

    # Expert-pairing guard (HARD ERROR by choice): the two experts must be the SAME task variant.
    # A t2v-high + i2v-low pairing renders off-model (the i2v refiner runs without its image
    # conditioning -> a degraded/noisy clip after ~8 min of compute, diagnosed live). A clear upfront
    # error beats silently burning the render and shipping bad output; the frontend should offer only
    # matched pairs. (Empty variant on either side -> no signal -> allowed.)
    high_variant = _wan_expert_task_variant(high_path)
    low_variant = _wan_expert_task_variant(low_path)
    if high_variant and low_variant and high_variant != low_variant:
        raise RuntimeError(
            f"Wan 2.2 dual-noise expert mismatch: the HIGH-noise expert is a {high_variant.upper()} "
            f"checkpoint but the LOW-noise expert is a {low_variant.upper()} checkpoint. Both experts "
            "must be the same task variant (both t2v, or both i2v) -- a mixed pair renders off-model. "
            f"high={os.path.basename(high_path)} low={os.path.basename(low_path)}"
        )

    # Per-family operating point (Phase 1 + 3a): validate the request's operating_point NAME first
    # (unknown -> warn + fall back to the family default; never raise), then resolve sampling params
    # with the valid name. The table fills blank/auto params; an explicit request value always wins;
    # anything the table lacks falls to the inline literal safety net kept below. Absent operating_point
    # -> the family default ("quality" for Wan), so a NORMAL request (frontend sends concrete
    # steps/cfg/sampler) is byte-identical to before this change.
    _op_name = resolve_operating_point("wan", req.get("operating_point"))
    _op = resolve_family_defaults("wan", _op_name, req)
    frames = bounded_option(req, "frames", 81)
    fps = bounded_option(req, "fps", 16)
    # High/low step counts and the split point come from the request when it states them.
    #
    # They were read from NOWHERE. The cockpit shows High Noise Steps, Low Noise Steps and Split
    # Step only in WAN dual-noise mode, and GenerationRequestBuilder sends six keys for them --
    # wan_split, wan_split_mode, high_steps, low_steps, split_step, noise_split_step,
    # wan_noise_split_step -- while this builder computed `steps // 2` from the operating point and
    # ignored every one. Three Advanced controls, visible exactly where they did nothing. That is
    # the VAE Tiling defect with the sign flipped, and it is why the fix for both is a sweep rather
    # than two edits.
    high_steps = bounded_option(req, "high_steps", 0, aliases=("high_steps", "high_noise_steps"))
    low_steps = bounded_option(req, "low_steps", 0, aliases=("low_steps", "low_noise_steps"))
    if high_steps > 0 and low_steps > 0:
        # Stated as a pair: they define both the total and the boundary, which is exactly what the
        # two spin boxes mean on screen.
        steps = high_steps + low_steps
        split = high_steps
    else:
        steps = bounded_option(_op, "steps", 20)
        if steps < 2:
            steps = 2
        split = _wan_split_step(req, steps)
    width = bounded_option(req, "width", 832)
    height = bounded_option(req, "height", 480)
    cfg = bounded_option(_op, "cfg", 3.5)
    seed = resolve_seed(req)
    # Per-expert shift: high_noise_shift/low_noise_shift still OVERRIDE the resolved base shift (they
    # are per-expert, not an operating-point axis). The base falls to the resolved shift, then 5.0.
    _base_shift = bounded_option(_op, "shift", 5.0)
    high_shift = float(req.get("high_noise_shift") or _base_shift)
    low_shift = float(req.get("low_noise_shift") or _base_shift)

    # LoRA stack (enabled entries only), routed per expert by filename: high_noise -> high only,
    # low_noise -> low only, neither -> both (content LoRA applies to the whole model). Reuses the
    # existing _path_looks_high/low_noise predicates -- no new detection.
    lora_entries = _wan_lora_stack_entries(req)
    # LoRA FOOTGUN CLOSE (phase 3a): an operating point may DECLARE accel LoRAs (the "fast" point is
    # 4 steps / cfg 1 -- garbage on the non-distilled base model WITHOUT its Lightx2v accel LoRAs). If
    # the resolved operating point declares lora.accel AND the request supplied NO LoRA stack, auto-
    # inject the declared high/low accel LoRAs with a LOUD warning: an API/script caller sending
    # operating_point="fast" alone must never silently get a 4-step garbage render. The UI path (3b)
    # always populates the visible LoRA stack, so lora_entries is non-empty there and this never fires;
    # a caller who supplied ANY LoRA stack is left untouched (their explicit intent wins). The injected
    # names route through the SAME per-expert filename logic below (high_noise->high, low_noise->low).
    if not lora_entries:
        _op_params = operating_point_params("wan", _op_name)
        _pair = accel_loras_for(_op_params, command)
        if _pair:
            _accel = [{"name": _pair[k], "strength": 1.0} for k in ("high", "low") if _pair.get(k)]
            logging.warning(
                "operating_point %r declares accel LoRAs but the request supplied no lora_stack; "
                "AUTO-INJECTING %s for %s (this operating point runs %d steps / cfg %s, which renders "
                "garbage on the base model without them). Supply an explicit lora_stack to override.",
                _op_name, [e["name"] for e in _accel], command, steps, cfg,
            )
            lora_entries = _accel
        elif (_op_params.get("lora") or {}).get("accel"):
            # The point wants accel LoRAs and declares none for THIS command. Running anyway at 4
            # steps / cfg 1 renders garbage, and borrowing the other variant's pair renders
            # off-model -- the very thing the expert-pair guard above refuses. Say so and stop.
            raise RuntimeError(
                f"operating_point {_op_name!r} runs {steps} steps at cfg {cfg}, which requires its "
                f"accel LoRAs, and it declares none for command {command!r}. Add the {command} pair "
                f"to the operating point, supply an explicit lora_stack, or select a different "
                f"operating point -- the other task variant's pair would render off-model."
            )
    high_loras: list[dict[str, Any]] = []
    low_loras: list[dict[str, Any]] = []
    for _lora in lora_entries:
        _is_high = _path_looks_high_noise(_lora["name"])
        _is_low = _path_looks_low_noise(_lora["name"])
        if _is_high and not _is_low:
            high_loras.append(_lora)
        elif _is_low and not _is_high:
            low_loras.append(_lora)
        else:
            high_loras.append(_lora)
            low_loras.append(_lora)

    prompt: dict[str, Any] = {}

    # --- shared CLIP + text encodes (feed BOTH samplers) ---
    clip_class = _first_available_class(object_info, ("CLIPLoader",), label="WAN dual-noise CLIP loading")
    allowed = _comfy_class_inputs(object_info, clip_class)
    inputs: dict[str, Any] = {}
    _set_if_allowed(inputs, allowed, ("clip_name",), _sv_core_wan_clip_name(object_info, stack, req))
    _set_if_allowed(inputs, allowed, ("type", "clip_type"), "wan")
    _set_if_allowed(inputs, allowed, ("device",), text_encoder_device(req, object_info, clip_class, stack=stack))
    _add_node(prompt, "1", clip_class, inputs)

    text_class = _first_available_class(object_info, ("CLIPTextEncode",), label="WAN dual-noise text encoding")
    allowed = _comfy_class_inputs(object_info, text_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("clip",), ["1", 0])
    _set_if_allowed(inputs, allowed, ("text", "prompt"), str(req.get("prompt") or ""))
    _add_node(prompt, "2", text_class, inputs)

    inputs = {}
    _set_if_allowed(inputs, allowed, ("clip",), ["1", 0])
    _set_if_allowed(inputs, allowed, ("text", "prompt"), str(req.get("negative_prompt") or ""))
    _add_node(prompt, "3", text_class, inputs)

    # --- TWO UNETLoader experts (weight_dtype "default"; fp8 is baked into the checkpoint) ---
    unet_class = _first_available_class(object_info, ("UNETLoader",), label="WAN dual-noise diffusion model loading")
    unet_allowed = _comfy_class_inputs(object_info, unet_class)
    weight_dtype = _sv_core_choice_or_default(object_info, unet_class, "weight_dtype", req.get("weight_dtype"), "default")

    inputs = {}
    _set_if_allowed(inputs, unet_allowed, ("unet_name", "model_name", "ckpt_name", "checkpoint"), _sv_video_primary_name(object_info, high_path, class_name=unet_class))
    _set_if_allowed(inputs, unet_allowed, ("weight_dtype",), weight_dtype)
    _add_node(prompt, "4", unet_class, inputs)   # HIGH-noise expert

    inputs = {}
    _set_if_allowed(inputs, unet_allowed, ("unet_name", "model_name", "ckpt_name", "checkpoint"), _sv_video_primary_name(object_info, low_path, class_name=unet_class))
    _set_if_allowed(inputs, unet_allowed, ("weight_dtype",), weight_dtype)
    _add_node(prompt, "12", unet_class, inputs)  # LOW-noise expert

    # --- VAE: dual-noise A14B is ARCHITECTURALLY LOCKED to the 16-ch 2.1 VAE. An explicit VAE in the
    # stack (the frontend defaults to wan2.2_vae for a "2.2" model) is INVALID here, not a preference --
    # the 48-ch 2.2 VAE crashes VAEDecode 48-vs-16 on the 16-ch latent the 14B experts produce. Strip
    # the explicit VAE keys so _sv_core_wan_vae_name's "explicit wins" branch can't return it and the
    # resolver falls through to force_version="2.1". Only THIS builder strips it -- the "explicit wins"
    # rule stays intact for every other Wan path (the single-model core call passes the stack unmodified).
    vae_stack = {k: v for k, v in stack.items() if k not in ("vae", "vae_path")}
    vae_class = _first_available_class(object_info, ("VAELoader",), label="WAN dual-noise VAE loading")
    allowed = _comfy_class_inputs(object_info, vae_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("vae_name", "vae", "model_name"), _sv_core_wan_vae_name(object_info, vae_stack, high_path, force_version="2.1"))
    _add_node(prompt, "5", vae_class, inputs)

    # --- per-expert LoRA chains inserted between each UNETLoader and its ModelSamplingSD3:
    # UNETLoader -> [LoraLoaderModelOnly ...] -> ModelSamplingSD3 (the template's node-83/85 slot).
    # Empty list -> the ref stays the UNETLoader, no nodes emitted (no-LoRA path byte-identical). ---
    high_model_ref = _emit_wan_lora_chain(prompt, object_info, ["4", 0], high_loras, node_prefix="h_lora_")
    low_model_ref = _emit_wan_lora_chain(prompt, object_info, ["12", 0], low_loras, node_prefix="l_lora_")

    # --- TWO ModelSamplingSD3 (per-expert shift), one per expert ---
    sampling_class = _first_available_class(object_info, ("ModelSamplingSD3",), label="WAN dual-noise model sampling config")
    sampling_allowed = _comfy_class_inputs(object_info, sampling_class)
    inputs = {}
    _set_if_allowed(inputs, sampling_allowed, ("model",), high_model_ref)
    _set_if_allowed(inputs, sampling_allowed, ("shift",), high_shift)
    _add_node(prompt, "6", sampling_class, inputs)   # HIGH

    inputs = {}
    _set_if_allowed(inputs, sampling_allowed, ("model",), low_model_ref)
    _set_if_allowed(inputs, sampling_allowed, ("shift",), low_shift)
    _add_node(prompt, "13", sampling_class, inputs)  # LOW

    # --- latent / image conditioning. T2V = empty latent. I2V = WanImageToVideo once, shared. ---
    sampler_positive: list[Any] = ["2", 0]
    sampler_negative: list[Any] = ["3", 0]
    sampler_latent: list[Any] = ["7", 0]
    if command == "i2v":
        image_class = _first_available_class(object_info, ("LoadImage",), label="WAN dual-noise i2v keyframe load")
        allowed = _comfy_class_inputs(object_info, image_class)
        inputs = {}
        _set_if_allowed(inputs, allowed, ("image",), str(req.get("input_image_comfy_name") or ""))
        _add_node(prompt, "20", image_class, inputs)

        clip_vision_link: list[Any] | None = None
        clip_vision_model = _sv_core_wan_clip_vision_name(object_info, stack, req)
        if "CLIPVisionLoader" in object_info and "CLIPVisionEncode" in object_info and clip_vision_model:
            cv_loader_class = _first_available_class(object_info, ("CLIPVisionLoader",), label="WAN dual-noise i2v clip-vision loading")
            allowed = _comfy_class_inputs(object_info, cv_loader_class)
            inputs = {}
            _set_if_allowed(inputs, allowed, ("clip_name",), clip_vision_model)
            _add_node(prompt, "21", cv_loader_class, inputs)

            cv_encode_class = _first_available_class(object_info, ("CLIPVisionEncode",), label="WAN dual-noise i2v clip-vision encode")
            allowed = _comfy_class_inputs(object_info, cv_encode_class)
            inputs = {}
            _set_if_allowed(inputs, allowed, ("clip_vision",), ["21", 0])
            _set_if_allowed(inputs, allowed, ("image",), ["20", 0])
            _set_if_allowed(inputs, allowed, ("crop",), str(req.get("clip_vision_crop") or "center"))
            _add_node(prompt, "22", cv_encode_class, inputs)
            clip_vision_link = ["22", 0]

        i2v_class = _first_available_class(object_info, ("WanImageToVideo",), label="WAN dual-noise i2v image conditioning")
        allowed = _comfy_class_inputs(object_info, i2v_class)
        inputs = {}
        _set_if_allowed(inputs, allowed, ("positive",), ["2", 0])
        _set_if_allowed(inputs, allowed, ("negative",), ["3", 0])
        _set_if_allowed(inputs, allowed, ("vae",), ["5", 0])
        _set_if_allowed(inputs, allowed, ("start_image",), ["20", 0])
        if clip_vision_link is not None:
            _set_if_allowed(inputs, allowed, ("clip_vision_output",), clip_vision_link)
        _set_if_allowed(inputs, allowed, ("width",), width)
        _set_if_allowed(inputs, allowed, ("height",), height)
        _set_if_allowed(inputs, allowed, ("length", "frames", "num_frames", "frame_count"), frames)
        _set_if_allowed(inputs, allowed, ("batch_size",), bounded_option(req, "batch_size", 1))
        _add_node(prompt, "7", i2v_class, inputs)
        sampler_positive = ["7", 0]
        sampler_negative = ["7", 1]
        sampler_latent = ["7", 2]
    else:
        latent_class = _first_available_class(object_info, ("EmptyHunyuanLatentVideo", "EmptyWanLatentVideo", "WanEmptyLatentVideo", "EmptyLatentVideo"), label="WAN dual-noise latent video creation")
        allowed = _comfy_class_inputs(object_info, latent_class)
        inputs = {}
        _set_if_allowed(inputs, allowed, ("width",), width)
        _set_if_allowed(inputs, allowed, ("height",), height)
        _set_if_allowed(inputs, allowed, ("length", "frames", "num_frames", "frame_count"), frames)
        _set_if_allowed(inputs, allowed, ("batch_size",), bounded_option(req, "batch_size", 1))
        _add_node(prompt, "7", latent_class, inputs)

    # --- TWO chained KSamplerAdvanced: HIGH [0, split) leaves leftover noise -> LOW [split, steps] ---
    sampler_class = _first_available_class(object_info, ("KSamplerAdvanced",), label="WAN dual-noise sampling")
    sampler_allowed = _comfy_class_inputs(object_info, sampler_class)
    sampler_name = _sv_core_wan_choice(object_info, sampler_class, "sampler_name", _op.get("sampler"), ("euler", "dpmpp_2m", "dpm++_2m", "uni_pc", "unipc"))
    scheduler_name = _sv_core_wan_choice(object_info, sampler_class, "scheduler", _op.get("scheduler"), ("simple", "normal", "sgm_uniform", "karras"))

    inputs = {}
    _set_if_allowed(inputs, sampler_allowed, ("model",), ["6", 0])
    _set_if_allowed(inputs, sampler_allowed, ("add_noise",), "enable")
    _set_if_allowed(inputs, sampler_allowed, ("noise_seed", "seed"), seed)
    _set_if_allowed(inputs, sampler_allowed, ("steps",), steps)
    _set_if_allowed(inputs, sampler_allowed, ("cfg",), cfg)
    _set_if_allowed(inputs, sampler_allowed, ("sampler_name", "sampler"), sampler_name)
    _set_if_allowed(inputs, sampler_allowed, ("scheduler", "scheduler_name"), scheduler_name)
    _set_if_allowed(inputs, sampler_allowed, ("positive",), sampler_positive)
    _set_if_allowed(inputs, sampler_allowed, ("negative",), sampler_negative)
    _set_if_allowed(inputs, sampler_allowed, ("latent_image", "samples"), sampler_latent)
    _set_if_allowed(inputs, sampler_allowed, ("start_at_step",), 0)
    _set_if_allowed(inputs, sampler_allowed, ("end_at_step",), split)
    _set_if_allowed(inputs, sampler_allowed, ("return_with_leftover_noise",), "enable")
    _add_node(prompt, "8", sampler_class, inputs)   # HIGH-noise stage

    inputs = {}
    _set_if_allowed(inputs, sampler_allowed, ("model",), ["13", 0])
    _set_if_allowed(inputs, sampler_allowed, ("add_noise",), "disable")
    _set_if_allowed(inputs, sampler_allowed, ("noise_seed", "seed"), seed)
    _set_if_allowed(inputs, sampler_allowed, ("steps",), steps)
    _set_if_allowed(inputs, sampler_allowed, ("cfg",), cfg)
    _set_if_allowed(inputs, sampler_allowed, ("sampler_name", "sampler"), sampler_name)
    _set_if_allowed(inputs, sampler_allowed, ("scheduler", "scheduler_name"), scheduler_name)
    _set_if_allowed(inputs, sampler_allowed, ("positive",), sampler_positive)
    _set_if_allowed(inputs, sampler_allowed, ("negative",), sampler_negative)
    # THE MoE HANDOFF: the low stage consumes the HIGH sampler's leftover-noise latent (node 8), NOT
    # the empty latent. Getting this link right is the entire dual-expert mechanism.
    _set_if_allowed(inputs, sampler_allowed, ("latent_image", "samples"), ["8", 0])
    _set_if_allowed(inputs, sampler_allowed, ("start_at_step",), split)
    _set_if_allowed(inputs, sampler_allowed, ("end_at_step",), steps)
    _set_if_allowed(inputs, sampler_allowed, ("return_with_leftover_noise",), "disable")
    _add_node(prompt, "14", sampler_class, inputs)  # LOW-noise stage

    # --- decode (from the LOW sampler) -> create video -> save ---
    decode_class = _first_available_class(object_info, ("VAEDecode",), label="WAN dual-noise VAE decode")
    allowed = _comfy_class_inputs(object_info, decode_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("samples",), ["14", 0])
    _set_if_allowed(inputs, allowed, ("vae",), ["5", 0])
    _add_node(prompt, "9", decode_class, inputs)

    create_video_class = _first_available_class(object_info, ("CreateVideo",), label="WAN dual-noise video assembly")
    allowed = _comfy_class_inputs(object_info, create_video_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("images",), ["9", 0])
    _set_if_allowed(inputs, allowed, ("fps",), fps)
    _add_node(prompt, "10", create_video_class, inputs)

    save_class = _first_available_class(object_info, ("SaveVideo", "SaveWEBM"), label="WAN dual-noise video saving")
    allowed = _comfy_class_inputs(object_info, save_class)
    output_value = str(req.get("output") or req.get("output_path") or f"spellvision_render_t2v_{job_id}")
    filename_prefix = _filename_prefix_from_output(output_value, job_id)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("video",), ["10", 0])
    _set_if_allowed(inputs, allowed, ("filename_prefix", "filename", "path"), filename_prefix)
    _set_if_allowed(inputs, allowed, ("format",), "mp4")
    _set_if_allowed(inputs, allowed, ("codec",), "h264")
    _add_node(prompt, "11", save_class, inputs)

    return _spellvision_apply_teacache_to_native_video_prompt(prompt, req, object_info)

def _build_native_wan_core_video_prompt(req: dict[str, Any], object_info: dict[str, Any], *, command: str, family: str, job_id: str) -> dict[str, Any]:
    if command not in ("t2v", "i2v"):
        raise RuntimeError("The native WAN core adapter supports T2V and single-model I2V only.")

    stack = _video_model_stack_from_request(req)
    primary_path = _first_stack_value(stack, ("primary_path", "transformer_path", "unet_path", "model_path")) or str(req.get("model") or "")
    if not primary_path:
        raise RuntimeError("The selected WAN video stack has no primary diffusion model path.")

    # Single-model i2v refuse-guard: a Wan 2.2 dual-noise HALF cannot drive the single-UNET
    # core i2v graph -- warn and refuse rather than silently build a degraded render. (Dual-
    # noise i2v is a separate, unwired topology.)
    if command == "i2v" and (_path_looks_high_noise(primary_path) or _path_looks_low_noise(primary_path)):
        raise RuntimeError(
            "This is a Wan 2.2 dual-noise model half; single-model i2v needs a single-file "
            "i2v checkpoint (Wan 2.1 i2v, or a single-file 2.2). Dual-noise i2v is a separate topology."
        )

    # Phase 2a: default values lifted to the operating-point table; each read keeps its verbatim
    # request aliases and inserts the table default before the (kept) literal safety net.
    _defaults = operating_point_params("wan_core", "default")
    frames = bounded_option(req, "frames", 81)
    fps = bounded_option(req, "fps", 16)
    steps = bounded_option(req, "steps", 30, table=_defaults)
    width = bounded_option(req, "width", 832)
    height = bounded_option(req, "height", 480)
    cfg = bounded_option(req, "cfg", 5.0, table=_defaults)
    seed = resolve_seed(req)

    prompt: dict[str, Any] = {}

    clip_class = _first_available_class(object_info, ("CLIPLoader",), label="WAN core CLIP loading")
    allowed = _comfy_class_inputs(object_info, clip_class)
    inputs: dict[str, Any] = {}
    _set_if_allowed(inputs, allowed, ("clip_name",), _sv_core_wan_clip_name(object_info, stack, req))
    _set_if_allowed(inputs, allowed, ("type", "clip_type"), "wan")
    _set_if_allowed(inputs, allowed, ("device",), text_encoder_device(req, object_info, clip_class, stack=stack))
    _add_node(prompt, "1", clip_class, inputs)

    text_class = _first_available_class(object_info, ("CLIPTextEncode",), label="WAN core text encoding")
    allowed = _comfy_class_inputs(object_info, text_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("clip",), ["1", 0])
    _set_if_allowed(inputs, allowed, ("text", "prompt"), str(req.get("prompt") or ""))
    _add_node(prompt, "2", text_class, inputs)

    inputs = {}
    _set_if_allowed(inputs, allowed, ("clip",), ["1", 0])
    _set_if_allowed(inputs, allowed, ("text", "prompt"), str(req.get("negative_prompt") or ""))
    _add_node(prompt, "3", text_class, inputs)

    unet_class = _first_available_class(object_info, ("UNETLoader",), label="WAN core diffusion model loading")
    allowed = _comfy_class_inputs(object_info, unet_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("unet_name", "model_name", "ckpt_name", "checkpoint"), _sv_video_primary_name(object_info, primary_path, class_name=unet_class))
    _set_if_allowed(inputs, allowed, ("weight_dtype",), _sv_core_choice_or_default(object_info, unet_class, "weight_dtype", req.get("weight_dtype"), "default"))
    _add_node(prompt, "4", unet_class, inputs)

    vae_class = _first_available_class(object_info, ("VAELoader",), label="WAN core VAE loading")
    allowed = _comfy_class_inputs(object_info, vae_class)
    inputs = {}
    # VAE version-match guard (Doc 26 §2, Option A). A Wan 2.1 model uses the 16-ch wan_2.1_vae; the
    # 48-ch wan2.2_vae crashes VAEDecode (48-vs-16) on the 16-ch latent the 2.1 UNet produces. The
    # frontend may send an explicit wan2.2_vae in the stack (its default for a "2.x" model) -- for a 2.1
    # primary that is INVALID, not a preference, so strip a MISMATCHED explicit 2.2 VAE and force 2.1 so
    # the resolver's version-match picks wan_2.1_vae. A 2.2 single-file model keeps its 2.2 VAE (no
    # strip/force). Mirrors the dual-noise builder's strip; here it is version-GATED to 2.1 primaries so
    # single-model 2.2 t2v is untouched.
    vae_stack = stack
    vae_force = ""
    if _wan_vae_version_marker(primary_path) == "2.1":
        vae_force = "2.1"
        if _wan_vae_version_marker(str(stack.get("vae_path") or stack.get("vae") or "")) == "2.2":
            vae_stack = {k: v for k, v in stack.items() if k not in ("vae", "vae_path")}
    _set_if_allowed(inputs, allowed, ("vae_name", "vae", "model_name"), _sv_core_wan_vae_name(object_info, vae_stack, primary_path, force_version=vae_force))
    _add_node(prompt, "5", vae_class, inputs)

    sampling_class = _first_available_class(object_info, ("ModelSamplingSD3",), label="WAN core model sampling config")
    allowed = _comfy_class_inputs(object_info, sampling_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("model",), ["4", 0])
    _set_if_allowed(inputs, allowed, ("shift",), bounded_option(req, "shift", 5.0, table=_defaults))
    _add_node(prompt, "6", sampling_class, inputs)

    # --- node 7: the sampler's latent source. FORK A: t2v = empty latent; i2v = the
    # WanImageToVideo image-conditioning subgraph (nodes 1-6 and 9-11 stay identical). ---
    sampler_positive: list[Any] = ["2", 0]
    sampler_negative: list[Any] = ["3", 0]
    sampler_latent: list[Any] = ["7", 0]
    if command == "i2v":
        # Image ingress: the keyframe was already uploaded to ComfyUI's input dir by
        # run_native_split_stack_video (req["input_image_comfy_name"]); LoadImage refs it
        # (a raw local path 400s against LoadImage's input-dir COMBO). Same bridge as LTX.
        image_class = _first_available_class(object_info, ("LoadImage",), label="WAN i2v keyframe load")
        allowed = _comfy_class_inputs(object_info, image_class)
        inputs = {}
        _set_if_allowed(inputs, allowed, ("image",), str(req.get("input_image_comfy_name") or ""))
        _add_node(prompt, "20", image_class, inputs)

        # Conditional clip_vision: WanImageToVideo.clip_vision_output is OPTIONAL, so wire
        # the CLIPVisionLoader->CLIPVisionEncode chain only when the encoder nodes exist AND
        # a CLIP-ViT-H model resolves (Wan 2.1 i2v needs it; Wan 2.2 i2v omits it -- the one
        # optional input covers both branches).
        clip_vision_link: list[Any] | None = None
        clip_vision_model = _sv_core_wan_clip_vision_name(object_info, stack, req)
        if "CLIPVisionLoader" in object_info and "CLIPVisionEncode" in object_info and clip_vision_model:
            cv_loader_class = _first_available_class(object_info, ("CLIPVisionLoader",), label="WAN i2v clip-vision loading")
            allowed = _comfy_class_inputs(object_info, cv_loader_class)
            inputs = {}
            _set_if_allowed(inputs, allowed, ("clip_name",), clip_vision_model)
            _add_node(prompt, "21", cv_loader_class, inputs)

            cv_encode_class = _first_available_class(object_info, ("CLIPVisionEncode",), label="WAN i2v clip-vision encode")
            allowed = _comfy_class_inputs(object_info, cv_encode_class)
            inputs = {}
            _set_if_allowed(inputs, allowed, ("clip_vision",), ["21", 0])
            _set_if_allowed(inputs, allowed, ("image",), ["20", 0])
            _set_if_allowed(inputs, allowed, ("crop",), str(req.get("clip_vision_crop") or "center"))
            _add_node(prompt, "22", cv_encode_class, inputs)
            clip_vision_link = ["22", 0]

        i2v_class = _first_available_class(object_info, ("WanImageToVideo",), label="WAN i2v image conditioning")
        allowed = _comfy_class_inputs(object_info, i2v_class)
        inputs = {}
        _set_if_allowed(inputs, allowed, ("positive",), ["2", 0])
        _set_if_allowed(inputs, allowed, ("negative",), ["3", 0])
        _set_if_allowed(inputs, allowed, ("vae",), ["5", 0])
        _set_if_allowed(inputs, allowed, ("start_image",), ["20", 0])
        if clip_vision_link is not None:
            _set_if_allowed(inputs, allowed, ("clip_vision_output",), clip_vision_link)
        _set_if_allowed(inputs, allowed, ("width",), width)
        _set_if_allowed(inputs, allowed, ("height",), height)
        _set_if_allowed(inputs, allowed, ("length", "frames", "num_frames", "frame_count"), frames)
        _set_if_allowed(inputs, allowed, ("batch_size",), bounded_option(req, "batch_size", 1))
        _add_node(prompt, "7", i2v_class, inputs)
        # WanImageToVideo emits (positive', negative', latent) -> the sampler reads these
        # instead of nodes 2/3 and the empty latent.
        sampler_positive = ["7", 0]
        sampler_negative = ["7", 1]
        sampler_latent = ["7", 2]
    else:
        latent_class = _first_available_class(object_info, ("EmptyHunyuanLatentVideo", "EmptyWanLatentVideo", "WanEmptyLatentVideo", "EmptyLatentVideo"), label="WAN core latent video creation")
        allowed = _comfy_class_inputs(object_info, latent_class)
        inputs = {}
        _set_if_allowed(inputs, allowed, ("width",), width)
        _set_if_allowed(inputs, allowed, ("height",), height)
        _set_if_allowed(inputs, allowed, ("length", "frames", "num_frames", "frame_count"), frames)
        _set_if_allowed(inputs, allowed, ("batch_size",), bounded_option(req, "batch_size", 1))
        _add_node(prompt, "7", latent_class, inputs)

    sampler_class = _first_available_class(object_info, ("KSamplerAdvanced",), label="WAN core sampling")
    allowed = _comfy_class_inputs(object_info, sampler_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("model",), ["6", 0])
    _set_if_allowed(inputs, allowed, ("add_noise",), str(req.get("add_noise") or "enable"))
    _set_if_allowed(inputs, allowed, ("noise_seed", "seed"), seed)
    _set_if_allowed(inputs, allowed, ("steps",), steps)
    _set_if_allowed(inputs, allowed, ("cfg",), cfg)
    _set_if_allowed(inputs, allowed, ("sampler_name", "sampler"), _sv_core_wan_choice(object_info, sampler_class, "sampler_name", req.get("video_sampler") or req.get("sampler") or _defaults.get("sampler"), ("dpmpp_2m", "dpm++_2m", "euler", "uni_pc", "unipc")))
    _set_if_allowed(inputs, allowed, ("scheduler", "scheduler_name"), _sv_core_wan_choice(object_info, sampler_class, "scheduler", req.get("video_scheduler") or req.get("scheduler") or _defaults.get("scheduler"), ("sgm_uniform", "normal", "simple", "karras")))
    _set_if_allowed(inputs, allowed, ("positive",), sampler_positive)
    _set_if_allowed(inputs, allowed, ("negative",), sampler_negative)
    _set_if_allowed(inputs, allowed, ("latent_image", "samples"), sampler_latent)
    _set_if_allowed(inputs, allowed, ("start_at_step",), int(req.get("start_at_step") or 0))
    _set_if_allowed(inputs, allowed, ("end_at_step",), int(req.get("end_at_step") or steps))
    _set_if_allowed(inputs, allowed, ("return_with_leftover_noise",), str(req.get("return_with_leftover_noise") or "disable"))
    _add_node(prompt, "8", sampler_class, inputs)

    decode_class = _first_available_class(object_info, ("VAEDecode",), label="WAN core VAE decode")
    allowed = _comfy_class_inputs(object_info, decode_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("samples",), ["8", 0])
    _set_if_allowed(inputs, allowed, ("vae",), ["5", 0])
    _add_node(prompt, "9", decode_class, inputs)

    create_video_class = _first_available_class(object_info, ("CreateVideo",), label="WAN core video assembly")
    allowed = _comfy_class_inputs(object_info, create_video_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("images",), ["9", 0])
    _set_if_allowed(inputs, allowed, ("fps",), fps)
    _add_node(prompt, "10", create_video_class, inputs)

    save_class = _first_available_class(object_info, ("SaveVideo", "SaveWEBM"), label="WAN core video saving")
    allowed = _comfy_class_inputs(object_info, save_class)
    output_value = str(req.get("output") or req.get("output_path") or f"spellvision_render_t2v_{job_id}")
    # SaveVideo saves UNDER ComfyUI's output dir -- an absolute path outside it is rejected
    # ("Saving image outside the output folder is not allowed"). Use the same safe stem
    # helper the LTX + wrapper builders use; the worker maps the saved file back to output.
    filename_prefix = _filename_prefix_from_output(output_value, job_id)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("video",), ["10", 0])
    _set_if_allowed(inputs, allowed, ("filename_prefix", "filename", "path"), filename_prefix)
    _set_if_allowed(inputs, allowed, ("format",), "mp4")
    _set_if_allowed(inputs, allowed, ("codec",), "h264")
    _add_node(prompt, "11", save_class, inputs)

    return _spellvision_apply_teacache_to_native_video_prompt(prompt, req, object_info)

def _build_native_wan_split_video_prompt(
    req: dict[str, Any],
    object_info: dict[str, Any],
    *,
    command: str,
    family: str,
    job_id: str,
) -> dict[str, Any]:
    if command != "t2v":
        raise RuntimeError("The native WAN template adapter currently supports T2V only. Use a compiled I2V workflow for I2V until the I2V adapter is wired.")

    stack = _video_model_stack_from_request(req)
    primary_path = _first_stack_value(stack, ("primary_path", "transformer_path", "unet_path", "model_path"))
    if not primary_path:
        raise RuntimeError("The selected WAN video stack has no primary diffusion model path.")

    frames = bounded_option(req, "frames", 81)
    _defaults = operating_point_params("wan_wrapper", "default")  # Phase 2a: default values lifted to the table
    fps = bounded_option(req, "fps", 16)
    steps = bounded_option(req, "steps", 30, table=_defaults)
    cfg = bounded_option(req, "cfg", 6.0, table=_defaults)
    shift = bounded_option(req, "shift", 5.0, table=_defaults)
    seed = resolve_seed(req)

    prompt: dict[str, Any] = {}

    model_class = _first_available_class(object_info, ("WanVideoModelLoader",), label="WAN video model loading")
    allowed = _comfy_class_inputs(object_info, model_class)
    inputs: dict[str, Any] = {}
    _set_if_allowed(inputs, allowed, ("model",), _sv_video_primary_name(object_info, primary_path, class_name=model_class))
    _set_if_allowed(inputs, allowed, ("base_precision",), str(req.get("base_precision") or "bf16"))
    _set_if_allowed(inputs, allowed, ("quantization",), str(req.get("model_quantization") or req.get("quantization") or "disabled"))
    _set_if_allowed(inputs, allowed, ("load_device",), str(req.get("model_load_device") or "offload_device"))
    _set_if_allowed(inputs, allowed, ("attention_mode",), _wrapper_attention_mode(req))
    _sv_set_default_required_inputs(inputs, object_info, model_class)
    _add_node(prompt, "1", model_class, inputs)

    t5_class = _first_available_class(object_info, ("LoadWanVideoT5TextEncoder",), label="WAN T5 text encoder loading")
    allowed = _comfy_class_inputs(object_info, t5_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("model_name",), _sv_video_text_encoder_name(object_info, stack))
    _set_if_allowed(inputs, allowed, ("precision",), str(req.get("text_encoder_precision") or "bf16"))
    _set_if_allowed(inputs, allowed, ("load_device",), str(req.get("text_encoder_load_device") or "offload_device"))
    _set_if_allowed(inputs, allowed, ("quantization",), str(req.get("text_encoder_quantization") or "disabled"))
    _sv_set_default_required_inputs(inputs, object_info, t5_class)
    _add_node(prompt, "2", t5_class, inputs)

    text_class = _first_available_class(object_info, ("WanVideoTextEncode",), label="WAN text encoding")
    allowed = _comfy_class_inputs(object_info, text_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("positive_prompt",), str(req.get("prompt") or ""))
    _set_if_allowed(inputs, allowed, ("negative_prompt",), str(req.get("negative_prompt") or ""))
    _set_if_allowed(inputs, allowed, ("t5",), ["2", 0])
    _set_if_allowed(inputs, allowed, ("force_offload",), False)
    _set_if_allowed(inputs, allowed, ("device",), text_encoder_device(req, object_info, text_class))
    _sv_set_default_required_inputs(inputs, object_info, text_class)
    _add_node(prompt, "3", text_class, inputs)

    image_embeds_node_id = _sv_add_wan_empty_embeds_node(prompt, object_info, req, node_id="4")

    sampler_class = _first_available_class(object_info, ("WanVideoSampler",), label="WAN video sampling")
    allowed = _comfy_class_inputs(object_info, sampler_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("model",), ["1", 0])
    _set_if_allowed(inputs, allowed, ("image_embeds",), [image_embeds_node_id, 0])
    _set_if_allowed(inputs, allowed, ("text_embeds",), ["3", 0])
    _set_if_allowed(inputs, allowed, ("steps",), steps)
    _set_if_allowed(inputs, allowed, ("cfg",), cfg)
    _set_if_allowed(inputs, allowed, ("shift",), shift)
    _set_if_allowed(inputs, allowed, ("seed",), seed)
    _set_if_allowed(inputs, allowed, ("force_offload",), True)
    _set_if_allowed(inputs, allowed, ("scheduler",), _sv_choice_or_default(object_info, sampler_class, "scheduler", req.get("video_scheduler") or req.get("scheduler") or _defaults.get("scheduler"), "unipc"))
    _set_if_allowed(inputs, allowed, ("riflex_freq_index",), int(req.get("riflex_freq_index") or 0))
    _set_if_allowed(inputs, allowed, ("denoise_strength",), bounded_option(req, "denoise", 1.0, table=_defaults))
    _sv_set_default_required_inputs(inputs, object_info, sampler_class)
    _add_node(prompt, "5", sampler_class, inputs)

    vae_class = _first_available_class(object_info, ("WanVideoVAELoader",), label="WAN VAE loading")
    allowed = _comfy_class_inputs(object_info, vae_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("model_name",), _sv_video_vae_name(object_info, stack))
    _set_if_allowed(inputs, allowed, ("precision",), str(req.get("vae_precision") or "bf16"))
    _set_if_allowed(inputs, allowed, ("use_cpu_cache",), bool(req.get("vae_use_cpu_cache", False)))
    _set_if_allowed(inputs, allowed, ("verbose",), bool(req.get("vae_verbose", False)))
    _sv_set_default_required_inputs(inputs, object_info, vae_class)
    _add_node(prompt, "6", vae_class, inputs)

    decode_class = _first_available_class(object_info, ("WanVideoDecode",), label="WAN video decode")
    allowed = _comfy_class_inputs(object_info, decode_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("vae",), ["6", 0])
    _set_if_allowed(inputs, allowed, ("samples",), ["5", 0])
    _set_if_allowed(inputs, allowed, ("enable_vae_tiling",), bool(req.get("enable_vae_tiling", False)))
    _set_if_allowed(inputs, allowed, ("tile_x",), int(req.get("tile_x") or 272))
    _set_if_allowed(inputs, allowed, ("tile_y",), int(req.get("tile_y") or 272))
    _set_if_allowed(inputs, allowed, ("tile_stride_x",), int(req.get("tile_stride_x") or 144))
    _set_if_allowed(inputs, allowed, ("tile_stride_y",), int(req.get("tile_stride_y") or 128))
    _sv_set_default_required_inputs(inputs, object_info, decode_class)
    _add_node(prompt, "7", decode_class, inputs)

    create_class = _first_available_class(object_info, ("CreateVideo",), label="video creation")
    allowed = _comfy_class_inputs(object_info, create_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("images",), ["7", 0])
    _set_if_allowed(inputs, allowed, ("fps",), float(fps))
    _sv_set_default_required_inputs(inputs, object_info, create_class)
    _add_node(prompt, "8", create_class, inputs)

    save_class = _first_available_class(object_info, ("SaveVideo",), label="video output saving")
    allowed = _comfy_class_inputs(object_info, save_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("video",), ["8", 0])
    _set_if_allowed(inputs, allowed, ("filename_prefix",), _filename_prefix_from_output(str(req.get("output") or ""), job_id))
    _set_if_allowed(inputs, allowed, ("format",), str(req.get("video_format") or "mp4"))
    _set_if_allowed(inputs, allowed, ("codec",), str(req.get("video_codec") or "h264"))
    _sv_set_default_required_inputs(inputs, object_info, save_class)
    _add_node(prompt, "9", save_class, inputs)

    return _spellvision_apply_teacache_to_native_video_prompt(prompt, req, object_info)

def _infer_native_video_family_key(req: dict[str, Any], family: str) -> str:
    explicit = str(
        family
        or req.get("model_family")
        or req.get("family")
        or req.get("video_family")
        or ""
    ).strip()
    if explicit and normalize_video_family_id(explicit) not in {"unknown", "video", "native_video", "split_stack"}:
        return normalize_video_family_id(explicit)

    stack = _video_model_stack_from_request(req)
    inferred = _video_family_from_request_parts(req, stack)
    return inferred if inferred != "unknown" else (normalize_video_family_id(explicit) if explicit else "unknown")

def _ltx_route_for(req: dict[str, Any]) -> str:
    """LTX-2.3 route selection. DEFAULT = distilled two-stage (newer/better for most uses AND
    VRAM-safer on the 32GB-floor 5090). OPT IN to the single-stage-full (quality/final-render) route
    with req['ltx_route']='single_stage_full' (aliases 'single_stage'/'full') or req['ltx_single_stage_full']=True.
    """
    route = str(req.get("ltx_route") or "").strip().lower()
    if route in {"single_stage_full", "single_stage", "full"}:
        return "single_stage_full"
    if req.get("ltx_single_stage_full") is True:
        return "single_stage_full"
    return "two_stage_distilled"

def _build_native_ltx_two_stage_prompt(
    req: dict[str, Any],
    object_info: dict[str, Any],
    *,
    command: str,
    family: str,
    job_id: str,
) -> dict[str, Any]:
    """LTX-2.3 DISTILLED TWO-STAGE route (default). Repo-owned template grounded (construction-identity
    verified) from the official ComfyUI-LTXVideo example LTX-2.3_T2V_I2V_Two_Stage_Distilled.json:
    EmptyLTXVLatentVideo -> stage-1 SamplerCustomAdvanced (ManualSigmas, distilled) -> LTXVLatentUpsampler
    + LatentUpscaleModelLoader (spatial x2) -> stage-2 SamplerCustomAdvanced -> LTXVTiledVAEDecode ->
    CreateVideo/SaveVideo, with the AV branch (LTXVAudioVAELoader/Decode + Concat/Separate AV) kept, and
    the per-stage LTXVImgToVideoConditionOnly gated by the bypass boolean (4987). Never read the live D:
    workflow at runtime. Patches user inputs only -- topology is preserved (== the blueprint)."""
    template_path = Path(__file__).resolve().parent / "video_templates" / "ltx23_two_stage.json"
    graph = json.loads(template_path.read_text(encoding="utf-8"))
    warnings: list[str] = []

    if isinstance(object_info, dict):
        missing_classes = sorted({
            str(node.get("class_type"))
            for node in graph.values()
            if isinstance(node, dict) and node.get("class_type") and node["class_type"] not in object_info
        })
        if missing_classes:
            warnings.append("LTX two-stage template references node classes missing from ComfyUI /object_info: " + ", ".join(missing_classes))

    def patch(node_id: str, key: str, value: Any) -> None:
        node = graph.get(node_id)
        if isinstance(node, dict) and isinstance(node.get("inputs"), dict) and value is not None:
            node["inputs"][key] = value

    def first(*keys: str) -> Any:
        for key in keys:
            value = req.get(key)
            if value not in (None, ""):
                return value
        return None

    # Prompts (2483 positive / 2612 negative -- same ids as the single-stage lineage).
    patch("2483", "text", first("prompt"))
    negative = first("negative_prompt", "negative")
    if negative is not None:
        patch("2612", "text", negative)

    # Dimensions / length / fps. length is a PrimitiveInt (4988) feeding EmptyLTXVLatentVideo + audio;
    # fps is a PrimitiveFloat (4989).
    width = first("width")
    height = first("height")
    if width is not None:
        patch("3059", "width", int(width))
    if height is not None:
        patch("3059", "height", int(height))
    length = first("length", "frames", "num_frames")
    if length is not None:
        patch("4988", "value", int(length))
    # batch_size is the actual BATCH (1 = single clip), NOT the frame count. The UI->API conversion
    # misaligned it: length (video) / frames_number (audio) were widget-converted-to-inputs, but ComfyUI
    # keeps their GHOST value in widgets_values, so batch_size picked up that ghost (video=121, audio=97).
    # Those mismatch at LTXVConcatAVLatent ("size 49 vs 97"). Force both latents' batch to 1.
    patch("3059", "batch_size", 1)
    patch("3980", "batch_size", 1)
    fps = first("fps", "frame_rate")
    if fps is not None:
        patch("4989", "value", float(fps))

    # Sampling. Distilled path uses fixed ManualSigmas (NOT a step count), so steps are intentionally
    # not routed.
    #
    # STAGE IDENTITY IS BY DATAFLOW -- the node ids do NOT read in stage order:
    #   BASE   = 4829 SamplerCustomAdvanced <- guider 4828, noise 4832 (blueprint seed 43),
    #            sampler 4831, sigmas 4984 (8-step 1.0 -> 0.0), latent 4528
    #   REFINE = 4971 SamplerCustomAdvanced <- guider 4964, noise 4967 (blueprint seed 42),
    #            sampler 4976, sigmas 4985 (3-step 0.85 -> 0.0), latent 4969 (post-upsample)
    # The blueprint uses two DIFFERENT seeds deliberately; reusing one correlates the refine noise
    # with the base noise, so derive the second instead of duplicating.
    # stated_seed, not first(): same zero-survives rule as every other builder, while keeping
    # "the request said nothing" distinct from "the request said zero". Silence has to leave the
    # blueprint's own two seeds (43 base / 42 refine) alone -- they are deliberately different, so
    # the refine noise is not correlated with the base noise.
    seed = stated_seed(req)
    if seed is not None:
        patch("4832", "noise_seed", int(seed))      # base
        patch("4967", "noise_seed", int(seed) + 1)  # refine

    # CFG is NOT the generic cockpit cfg on this route. Both CFGGuiders ship at 1 because the graph is
    # DISTILLED (8+3 ManualSigmas steps through a distilled LoRA). Feeding it the image-style cfg the
    # cockpit always sends -- 7.0 by default, 3.5 once the LTX family preset fires, and that preset is
    # tuned for the SINGLE-STAGE full model -- burns the render. Only an explicit ltx_distilled_cfg
    # overrides; a stray high generic cfg is reported rather than applied.
    distilled_cfg = first("ltx_distilled_cfg")
    if distilled_cfg is not None:
        patch("4964", "cfg", float(distilled_cfg))
        patch("4828", "cfg", float(distilled_cfg))
    else:
        generic_cfg = first("cfg", "cfg_scale")
        try:
            if generic_cfg is not None and float(generic_cfg) > 1.5:
                warnings.append(
                    f"LTX distilled two-stage ignored cfg={float(generic_cfg):g}; distilled guiders stay at 1. "
                    "Pass ltx_distilled_cfg to override."
                )
        except (TypeError, ValueError):
            pass

    # Asset names. The UI->API conversion dropped the source-loader combo widgets for 4982/4974/4010,
    # so set them explicitly (blueprint defaults) unless the request overrides -- keeps the graph
    # renderable and self-consistent with the blueprint.
    # ALWAYS-SEPARATE VAE topology (INTENTIONAL divergence from the official two-stage blueprint, which
    # pulls VAEs from the checkpoint's embedded slot). This mirrors the single-stage ltx_av_native pattern
    # exactly: checkpoint 3940 = MODEL only; video VAE from a dedicated VAELoader (5001), audio VAE from
    # LTXVAudioVAELoader (4010), text projection on the text-encoder loader (4982) -- all SEPARATE files.
    # Rationale: decouples two-stage from checkpoint-embedded VAE, so ANY LTX checkpoint works (incl. the
    # VRAM-friendly 21GB diffusion-only variant), and both LTX routes share one VAE pattern. Do NOT "fix"
    # this back to the blueprint's [3940,2] wiring -- that reintroduces the VAE-less-checkpoint crash.
    patch("3940", "ckpt_name", first("ltx_transformer") or "ltx-2.3-22b-dev.safetensors")
    patch("5001", "vae_name", first("ltx_video_vae") or "LTX23_video_vae_bf16.safetensors")
    patch("4010", "ckpt_name", first("ltx_audio_vae") or "LTX23_audio_vae_bf16.safetensors")
    patch("4982", "text_encoder", first("ltx_text_encoder") or "comfy_gemma_3_12B_it.safetensors")
    patch("4982", "ckpt_name", first("ltx_text_projection") or "ltx-2.3_text_projection_bf16.safetensors")
    # `ltx_text_encoder_device` is a key nothing else in the tree reads, so the cockpit's
    # `text_encoder_device` was silently dropped on this route -- a control that works everywhere
    # else and does nothing here. Both keys are accepted, the LTX-specific one first so an existing
    # caller keeps its override, and the value is resolved against the node's own vocabulary
    # (LTXAVTextEncoderLoader takes ["default", "cpu"], the core spelling) rather than passed
    # through. Absent a stated value the memory profile decides, as it now does on every route.
    patch("4982", "device", text_encoder_device(
        req, object_info, "LTXAVTextEncoderLoader",
        keys=("ltx_text_encoder_device", "text_encoder_device"),
    ) or None)
    patch("4974", "model_name", first("ltx_spatial_upscaler") or "ltx-2.3-spatial-upscaler-x2-1.1.safetensors")

    # Distilled LoRA is the DEFAULT of this route (its defining feature) -- kept, never bypassed. Only
    # its name/strength are overridable.
    # Default to the bare filename (the official pack README installs the distilled LoRA to models/loras/,
    # not the blueprint author's ltxv/ltx2/ subpath) so a README-following download resolves.
    # 4922 IS the distilled adapter, so it stays PINNED. It used to read the generic lora keys, which
    # broke the route two ways: (a) selecting any lora in the cockpit REPLACED the distilled one,
    # leaving 8-step distilled sigmas driving a non-distilled model (noise), and (b) lora_scale is sent
    # unconditionally and defaults to 1.0 even with no lora selected, so every render silently ran the
    # distilled adapter at 2x the blueprint 0.5. Only the ltx_distilled_* keys touch this node now.
    patch("4922", "lora_name", first("ltx_distilled_lora") or "ltx-2.3-22b-distilled-lora-384-1.1.safetensors")
    distilled_strength = first("ltx_distilled_lora_strength")
    if distilled_strength is not None:
        patch("4922", "strength_model", float(distilled_strength))

    # A user-selected lora CHAINS after the distilled one (4922 -> 8801 -> both guiders) rather than
    # replacing it. Same opt-out token set as the single-stage route, so "none"/"off"/"" skip the insert
    # instead of patching a bogus filename.
    explicit_lora = next((req.get(k) for k in ("lora", "lora_name", "ltx_lora") if k in req), KeyError)
    explicit_opt_out = (
        req.get("use_lora") is False
        or (explicit_lora is not KeyError and str(explicit_lora or "").strip().lower() in {"", "none", "off", "disabled", "no"})
    )
    user_lora = None if explicit_opt_out else first("lora", "lora_name", "ltx_lora")
    if user_lora:
        user_strength = first("lora_scale", "lora_strength")
        graph["8801"] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": ["4922", 0],
                "lora_name": user_lora,
                "strength_model": float(user_strength) if user_strength is not None else 1.0,
            },
        }
        for node_id, node in graph.items():
            if node_id == "8801" or not isinstance(node, dict):
                continue
            inputs = node.get("inputs")
            if not isinstance(inputs, dict):
                continue
            for key, value in inputs.items():
                if isinstance(value, list) and len(value) == 2 and str(value[0]) == "4922":
                    inputs[key] = ["8801", 0]

    # Sampler choice (quality knob). The UI->API conversion dropped these ["COMBO",{options}]-format
    # widgets (the converter's _input_is_widget only knew the legacy [[list],{}] form), so restore the
    # blueprint samplers and expose them as overrides. The per-node defaults below are the blueprint's
    # and stay attached to their node ids; the STAGE KEYS map by dataflow (see the stage-identity note
    # above) -- 4831 feeds the base sampler 4829, 4976 feeds the refine sampler 4971. These were
    # previously labelled the other way round, so ltx_sampler_stage1/stage2 hit the wrong stage.
    # LTX genuinely needs TWO stage samplers, so the ltx_sampler_stage1/stage2 namespace stays --
    # collapsing it would be applying a rule at the wrong level. What was wrong is that a plain
    # `sampler`, which is what the cockpit's dropdown sends and what every other family reads, was
    # ignored: the LTX allowlist offered three samplers and none of them could be selected. Stage 1
    # now honours it (validated against that same allowlist), and stage 2 keeps the refine default
    # unless named explicitly.
    _ltx_stage1, _ = sampling_for("ltx", req, object_info, "euler_ancestral_cfg_pp", "")
    patch("4831", "sampler_name", first("ltx_sampler_stage1", "ltx_sampler") or _ltx_stage1)
    patch("4976", "sampler_name", first("ltx_sampler_stage2", "ltx_sampler") or "euler_cfg_pp")

    # SaveVideo format/codec (dropped combo widgets; blueprint auto/auto -- overridable).
    patch("4852", "format", first("video_format") or "auto")
    patch("4852", "codec", first("video_codec") or "auto")

    # VAE-decode tiling is a VRAM/hardware knob (the blueprint Note: tune tiles/overlap to hardware).
    # Defaults 2x2 tiles / overlap 6 (fine for 32GB); expose overrides without moving the default.
    tiles_h = first("ltx_tiles_horizontal")
    tiles_v = first("ltx_tiles_vertical")
    tile_overlap = first("ltx_tile_overlap")
    if tiles_h is not None:
        patch("4995", "horizontal_tiles", int(tiles_h))
    if tiles_v is not None:
        patch("4995", "vertical_tiles", int(tiles_v))
    if tile_overlap is not None:
        patch("4995", "overlap", int(tile_overlap))

    # ResizeImageMaskNode (4990) is in the graph even for t2v (its output feeds the conditioners, which
    # bypass via 4987 but still validate), so its required inputs (dropped by the UI->API conversion) must
    # ALWAYS be set or ComfyUI 400s on a missing required input. resize_type is a COMFY_DYNAMICCOMBO_V3:
    # "scale longer dimension" carries a nested required `longer_size` (the blueprint's 1536 middle widget).
    # V3 DynamicCombo nested inputs are keyed "<combo>.<nested>" (comfy_api _io.py: f"{inp.id}.{nested_inp.id}"),
    # so the "scale longer dimension" size is "resize_type.longer_size", NOT a flat "longer_size".
    patch("4990", "resize_type", first("ltx_resize_type") or "scale longer dimension")
    patch("4990", "resize_type.longer_size", int(first("ltx_resize_longer_size") or 1536))
    patch("4990", "scale_method", first("ltx_resize_interpolation") or "lanczos")

    # t2v vs i2v: bypass boolean (4987) gates both per-stage LTXVImgToVideoConditionOnly (3159/4970).
    # bypass=True => t2v. The keyframe (already uploaded by run_native_split_stack_video) is the
    # Comfy-side LoadImage name in req["input_image_comfy_name"]; it flows 2004 LoadImage ->
    # ResizeImageMaskNode -> the conditioners. No image uploaded for an i2v request -> fall back to t2v.
    comfy_image = first("input_image_comfy_name")
    want_i2v = command == "i2v"
    is_i2v = want_i2v and bool(comfy_image)
    if want_i2v and not comfy_image:
        warnings.append("LTX two-stage i2v requested but no input image was uploaded; falling back to t2v (bypass).")
    patch("4987", "value", (not is_i2v))  # bypass=True => t2v (image ignored)
    if is_i2v:
        patch("2004", "image", str(comfy_image))
        # Image-conditioning strength. Blueprint stage-1=0.7, stage-2=1.0 (full adherence at high-res)
        # -- keep that shape by default; an explicit knob overrides stage-1, and a separate override
        # exposes stage-2 (was frozen).
        strength = first("ltx_image_strength", "i2v_strength", "image_conditioning_strength")
        if strength is not None:
            try:
                patch("3159", "strength", float(strength))
            except (TypeError, ValueError):
                pass
        strength2 = first("ltx_image_strength_stage2")
        if strength2 is not None:
            try:
                patch("4970", "strength", float(strength2))
            except (TypeError, ValueError):
                pass

    # Output prefix.
    output = first("output")
    if output:
        patch("4852", "filename_prefix", _filename_prefix_from_output(str(output), job_id))

    # The blueprint baked BARE model filenames; ComfyUI's combo lists are subfolder-relative
    # (e.g. checkpoints live at ltx\ltx-2.3-22b-dev.safetensors). The native-video submit path does NOT
    # run name resolution, so normalize every model-file input to ComfyUI's exact catalogued string here
    # (basename match), the same way the comfy_workflow launch path does -- else /prompt 400s on ckpt_name.
    _resolve_graph_model_names(graph, object_info)

    # Absorb node/input renames from a ComfyUI update, same as the comfy_workflow launch path. This
    # route needs it MORE, not less: these graphs are built from repo-owned templates grounded
    # against one particular core, so an upstream rename would break every LTX render at once with
    # no per-workflow escape hatch. Every rewrite is validated against the live schema, so this is a
    # no-op on a core that still defines what the template names.
    for _alias_note in _apply_node_aliases(graph, object_info):
        log.warning("native video: node alias applied -- %s", _alias_note)

    # GUARD (always-separate topology): the video/audio VAE + text-projection are SEPARATE files, required
    # regardless of the checkpoint. If any is absent from ComfyUI's live loader lists (unresolved after the
    # name normalization above), fail fast with a clear message NAMING the file, instead of a deep
    # VAELoader / VAE-decode crash. This is NOT an embedded-VAE check: a diffusion-only LTX checkpoint is
    # fully supported (and VRAM-preferred) here -- the guard fires only when a genuinely-required SEPARATE
    # file is missing, never on the checkpoint's lack of an embedded VAE.
    if isinstance(object_info, dict) and object_info:
        _sep_required = [
            ("5001", "VAELoader", "vae_name", "models/vae/ltx or checkpoints/ltx"),
            ("4010", "LTXVAudioVAELoader", "ckpt_name", "models/checkpoints/ltx"),
            ("4982", "LTXAVTextEncoderLoader", "ckpt_name", "models/checkpoints/ltx (text projection)"),
        ]
        _missing_sep = []
        for _nid, _cls, _key, _where in _sep_required:
            _name = str((graph.get(_nid) or {}).get("inputs", {}).get(_key) or "").strip()
            if _name and _name not in _sv_comfy_input_choices(object_info, _cls, _key):
                _missing_sep.append(f"{_name} ({_cls}.{_key}; stage under {_where})")
        if _missing_sep:
            raise RuntimeError(
                "LTX-2.3 two-stage needs these SEPARATE VAE/text-projection files (always-separate VAE "
                "topology, independent of the checkpoint's embedded VAE): " + "; ".join(_missing_sep)
                + ". Stage them and retry. NOTE: a diffusion-only LTX checkpoint is fully supported here "
                "(VRAM-preferred) -- this is NOT an embedded-VAE requirement."
            )

    req["resolved_native_video_family"] = "ltx"
    req["native_video_route"] = "ltx_two_stage"
    req["native_video_adapter_warnings"] = list(req.get("native_video_adapter_warnings") or []) + warnings
    return graph

def _build_native_ltx_video_prompt(
    req: dict[str, Any],
    object_info: dict[str, Any],
    *,
    command: str,
    family: str,
    job_id: str,
) -> dict[str, Any]:
    # LTX-2.3 route: distilled two-stage is the DEFAULT; single-stage-full is opt-in (quality/final).
    if _ltx_route_for(req) == "two_stage_distilled":
        return _build_native_ltx_two_stage_prompt(req, object_info, command=command, family=family, job_id=job_id)
    # ---- single-stage-full route (opt-in), UNCHANGED ----
    # Repo-owned EMBEDDED template (pruned single-pass audio+video graph seeded
    # from ltx_api.json). Never read the live D: workflow at runtime.
    template_path = Path(__file__).resolve().parent / "video_templates" / "ltx_av_native.json"
    graph = json.loads(template_path.read_text(encoding="utf-8"))
    warnings: list[str] = []

    if isinstance(object_info, dict):
        missing_classes = sorted({
            str(node.get("class_type"))
            for node in graph.values()
            if isinstance(node, dict) and node.get("class_type") and node["class_type"] not in object_info
        })
        if missing_classes:
            warnings.append("LTX template references node classes missing from ComfyUI /object_info: " + ", ".join(missing_classes))

    def patch(node_id: str, key: str, value: Any) -> None:
        node = graph.get(node_id)
        if isinstance(node, dict) and isinstance(node.get("inputs"), dict) and value is not None:
            node["inputs"][key] = value

    def first(*keys: str) -> Any:
        for key in keys:
            value = req.get(key)
            if value not in (None, ""):
                return value
        return None

    # Prompts.
    patch("2483", "text", first("prompt"))
    negative = first("negative_prompt", "negative")
    if negative is not None:
        patch("2612", "text", negative)

    # Dimensions / length / fps. length (4979) + fps (4978) drive BOTH video and audio.
    width = first("width")
    height = first("height")
    if width is not None:
        patch("3059", "width", int(width))
    if height is not None:
        patch("3059", "height", int(height))
    length = first("length", "frames", "num_frames")
    if length is not None:
        patch("4979", "value", int(length))
    fps = first("fps", "frame_rate")
    if fps is not None:
        patch("4978", "value", float(fps))

    # Sampling.
    # stated_seed, not first(): same zero-survives rule as every other builder, while keeping
    # "the request said nothing" distinct from "the request said zero". Silence has to leave the
    # blueprint's own two seeds (43 base / 42 refine) alone -- they are deliberately different, so
    # the refine noise is not correlated with the base noise.
    seed = stated_seed(req)
    if seed is not None:
        patch("4814", "noise_seed", int(seed))
    steps = first("steps")
    if steps is not None:
        patch("4966", "steps", int(steps))
    cfg = first("cfg", "cfg_scale")
    if cfg is not None:
        patch("4964", "cfg", float(cfg))  # VIDEO guider; AUDIO guider (4963) stays fixed.

    # Asset names (keep the template's proven defaults when not provided).
    patch("3940", "ckpt_name", first("ltx_transformer"))
    patch("4986", "vae_name", first("ltx_video_vae"))
    patch("4010", "ckpt_name", first("ltx_audio_vae"))
    patch("4960", "text_encoder", first("ltx_text_encoder"))
    patch("4960", "ckpt_name", first("ltx_text_projection"))

    # LoRA: OFF by default. chel was only ever a lora-application test, never an intended
    # default (it also skewed composition regardless of prompt). So ABSENCE of a lora now
    # bypasses node 4968 cleanly (rewire every referrer to the checkpoint MODEL output --
    # the verified no-dangling path). A provided name (+ optional strength) still wires
    # 4968 with that lora; chel remains in the template JSON only as a fallback reachable
    # by explicitly re-selecting it.
    explicit_lora = next((req.get(k) for k in ("lora", "lora_name", "ltx_lora") if k in req), KeyError)
    explicit_opt_out = (
        req.get("use_lora") is False
        or (explicit_lora is not KeyError and str(explicit_lora or "").strip().lower() in {"", "none", "off", "disabled", "no"})
    )
    # An opt-out token ("none"/"off"/...) is truthy as a string, so clear lora_name
    # to fall through to the bypass branch instead of patching a bogus lora file.
    lora_name = None if explicit_opt_out else first("lora", "lora_name", "ltx_lora")
    if lora_name:
        patch("4968", "lora_name", lora_name)
        lora_strength = first("lora_scale", "lora_strength")
        if lora_strength is not None:
            patch("4968", "strength_model", float(lora_strength))
    elif "4968" in graph:
        for node in graph.values():
            inputs = node.get("inputs") if isinstance(node, dict) else None
            if not isinstance(inputs, dict):
                continue
            for key, value in inputs.items():
                if isinstance(value, list) and len(value) == 2 and str(value[0]) == "4968":
                    inputs[key] = ["3940", 0]  # LoraLoaderModelOnly MODEL -> CheckpointLoaderSimple MODEL
        graph.pop("4968", None)

    # t2v vs i2v: the bypass boolean (4977) gates LTXVImgToVideoConditionOnly (3159).
    # The keyframe is already uploaded to ComfyUI by run_native_split_stack_video, which
    # stashes the Comfy-side LoadImage name in req["input_image_comfy_name"] (LoadImage
    # is a COMBO of input-dir files -- a raw local path would 400). If i2v is requested
    # but no image was uploaded, fall back to t2v (bypass=True) with a warning.
    comfy_image = first("input_image_comfy_name")
    want_i2v = command == "i2v"
    is_i2v = want_i2v and bool(comfy_image)
    if want_i2v and not comfy_image:
        warnings.append("LTX i2v requested but no input image was uploaded; falling back to t2v (bypass).")
    patch("4977", "value", (not is_i2v))  # bypass=True => t2v (image ignored)
    if is_i2v:
        patch("2004", "image", str(comfy_image))
        # Image-conditioning strength (how strongly the render adheres to the keyframe).
        # Only an explicit knob overrides the template default (3159.strength=0.7);
        # denoise is intentionally NOT auto-mapped (inverse semantics).
        strength = first("ltx_image_strength", "i2v_strength", "image_conditioning_strength")
        if strength is not None:
            try:
                patch("3159", "strength", float(strength))
            except (TypeError, ValueError):
                pass

    # Output prefix.
    output = first("output")
    if output:
        patch("4823", "filename_prefix", _filename_prefix_from_output(str(output), job_id))

    req["resolved_native_video_family"] = "ltx"
    req["native_video_route"] = "ltx_template"
    req["native_video_adapter_warnings"] = list(req.get("native_video_adapter_warnings") or []) + warnings
    return graph

def _wrapper_attention_mode(req: dict[str, Any]) -> str:
    """Attention backend for the kijai wrapper nodes (HyVideoModelLoader / WanVideoModelLoader).

    These wrappers call sageattn THEMSELVES rather than routing through ComfyUI's global
    --use-sage-attention path, so the launcher flag does not reach them and they need their own
    setting. Both were pinned to "sdpa" and no caller ever overrode it, so the wrapper paths
    were leaving the same speedup on the table that the global flag was.

    Default is sageattn on the evidence: Doc 25 S5 measured +25% on Hunyuan 129f (317s -> 237s)
    with quality holding, through this exact wrapper; the 2026-08-25 A/B independently measured
    -25.1% s/it on Wan and pixel-gated both families. Pass attention_mode="sdpa" to fall back.
    """
    return str(req.get("attention_mode") or "").strip() or "sageattn"


def _resolve_native_video_stack(req: dict[str, Any], object_info: dict[str, Any], family: str):
    """Producer-side component resolution for a native-VIDEO family via the generic engine -- the
    video analog of _resolve_native_image_stack. FIRST used by HunyuanVideo: it proves
    component_resolver.resolve_stack (the image path's core) works for a video family too. The video
    family's contract required_components are passed as the floor so the readiness gate matches the
    contract. Wan/LTX keep their inline resolvers for now; unifying the whole video run path onto this
    is what the deferred family-plugin decomposition inherits (Hunyuan is the reference implementation).
    """
    from component_resolver import resolve_stack
    fam = str(family or "").strip().lower()
    try:
        from video_family_contracts import VIDEO_FAMILY_CONTRACTS
        contract = VIDEO_FAMILY_CONTRACTS.get(fam)
        contract_required = contract.required_components if contract else None
    except Exception:
        contract_required = None
    primary = str(req.get("model") or "")
    stack = req.get("stack") if isinstance(req.get("stack"), dict) else {}
    return resolve_stack(
        primary,
        family=fam,
        requested_family=fam,
        stack=stack,
        req=req,
        task=task_of(req, "t2v"),
        choices_for=lambda cls, inp: _comfy_input_choices(object_info, cls, inp),
        contract_required=contract_required,
    )

def _is_kijai_hunyuan_format(model_path: str) -> bool:
    """Header-peek a HunyuanVideo checkpoint: True if it is the kijai/HunyuanVideoWrapper transformer
    layout (double_blocks/single_blocks keys) that HyVideoModelLoader loads, False for the native-Comfy
    layout (which only loads via the core UNETLoader path -- the one blocked by the i2v CLIPVisionEncode
    llava-768 bug). Reads only the safetensors header, never the weights."""
    try:
        import struct
        with open(model_path, "rb") as f:
            (hlen,) = struct.unpack("<Q", f.read(8))
            head = f.read(hlen).decode("utf-8", "ignore")
        return ('"double_blocks.' in head) or ('"single_blocks.' in head)
    except Exception:
        return False

def _build_native_hunyuan_wrapper_i2v_prompt(req: dict[str, Any], object_info: dict[str, Any], *,
                                             job_id: str) -> dict[str, Any]:
    """HunyuanVideo I2V via the kijai HunyuanVideoWrapper -- the path that SIDESTEPS the upstream core
    CLIPVisionEncode 768-vs-1024 llava bug that blocks the native i2v graph. GROUNDED verbatim from the
    wrapper's own example_workflows/hyvideo_i2v_example_fixed_model_02.json: HyVideoModelLoader(kijai i2v
    transformer, fp8) + HyVideoBlockSwap -> HyVideoI2VEncode(image + prompt, NO clip_vision) for the
    conditioning embeds; HyVideoEncode VAE-encodes the (bucket-scaled) keyframe -> image_cond_latents;
    HyVideoSampler(FlowMatchDiscrete, flow_shift 7, i2v_mode 'stability') -> HyVideoDecode -> CreateVideo
    -> SaveVideo. Requires a KIJAI-FORMAT i2v checkpoint (double_blocks/single_blocks); a native-Comfy
    i2v file is refused with a clear message (it only loads via the bug-blocked core path)."""
    model_path = str(req.get("model") or "")
    model_name = _comfy_unet_name_for_model(object_info, model_path)
    if not model_name:
        raise RuntimeError(
            f"HunyuanVideo i2v transformer is not visible to ComfyUI: {model_path!r} (must be under diffusion_models/)."
        )
    if not _is_kijai_hunyuan_format(model_path):
        raise RuntimeError(
            f"HunyuanVideo i2v checkpoint {model_name!r} is native-Comfy format, which only loads via the core "
            "CLIPVisionEncode i2v path -- blocked by an upstream llava clip_vision (768-vs-1024) bug. Download a "
            "kijai-format i2v model (e.g. hunyuan_video_I2V_720_fixed_fp8_e4m3fn.safetensors from "
            "Kijai/HunyuanVideo_comfy) into diffusion_models/ and select it."
        )
    hy_models = _comfy_input_choices(object_info, "HyVideoModelLoader", "model")
    if hy_models and model_name not in hy_models:
        raise RuntimeError(
            f"HunyuanVideo i2v model {model_name!r} is not in HyVideoModelLoader's list; ensure the "
            "ComfyUI-HunyuanVideoWrapper custom node is installed and the file is under diffusion_models/."
        )
    # HyVideoVAELoader + HyVideoEncode/Decode require the KIJAI diffusers-format VAE
    # (AutoencoderKLCausal3D, keyed decoder.conv_norm_out.weight) -- the native-Comfy hunyuan_video_vae
    # at models/vae root is rejected (wrong keys), and HyVideoEncode uses the diffusers .latent_dist API
    # + skips the scaling factor, so a native comfy VAE is incompatible (API + scaling). The kijai VAE
    # ships as hyvid/hunyuan_video_vae_bf16.safetensors (a subdir to dodge the same-name native file).
    hy_vaes = _comfy_input_choices(object_info, "HyVideoVAELoader", "model_name")
    vae = next((v for v in hy_vaes if "hyvid" in v.lower() and "hunyuan" in v.lower() and "vae" in v.lower()), "")
    if not vae:
        vae = next((v for v in hy_vaes if "hunyuan" in v.lower() and "vae" in v.lower()
                    and v.strip().lower() != "hunyuan_video_vae_bf16.safetensors"), "")
    if not vae:
        raise RuntimeError(
            "The kijai-format HunyuanVideo VAE required by the wrapper i2v path is not installed. Download "
            "hunyuan_video_vae_bf16.safetensors from Kijai/HunyuanVideo_comfy into models/vae/hyvid/ "
            "(the native-Comfy hunyuan VAE at models/vae root has incompatible keys)."
        )

    image_ref = str(req.get("input_image_comfy_name") or req.get("input_image") or "").strip()
    if not image_ref:
        raise RuntimeError("HunyuanVideo i2v requires an input keyframe image (none resolved/uploaded).")

    prompt = str(req.get("prompt") or "")
    _defaults = operating_point_params("hunyuan_video", "default")
    try:
        steps = bounded_option(req, "steps", 30, table=_defaults)
    except Exception:
        steps = 30
    if steps < 1:
        steps = 30
    try:
        guidance = bounded_option(req, "cfg", 6.0)
    except Exception:
        guidance = 6.0
    if guidance <= 0:
        guidance = 6.0
    # Hunyuan temporal /4 -> frame length must be (N*4)+1 (blueprint used 65).
    try:
        raw_len = int(req.get("length") or req.get("num_frames") or 65)
    except Exception:
        raw_len = 65
    length = ((max(5, raw_len) - 1) // 4) * 4 + 1
    try:
        fps = bounded_option(req, "fps", 24.0)
    except Exception:
        fps = 24.0
    seed = resolve_seed(req, "seed")
    flow_shift = bounded_option(req, "shift", 7.0)
    base_size = str(req.get("hunyuan_bucket_base_size") or "720")
    if base_size not in {"360", "540", "720"}:
        base_size = "720"
    prefix = _filename_prefix_from_output(str(req.get("output") or ""), job_id)

    # attention_mode now defaults to sageattn (see _wrapper_attention_mode). The old note here
    # held it at 'sdpa' until i2v was render-proven -- that happened in eeb4d03, and the
    # 2026-08-25 A/B pixel-gated sage on both video families, so the condition is met.
    return {
        "1": {"class_type": "HyVideoBlockSwap", "inputs": {"double_blocks_to_swap": 20, "single_blocks_to_swap": 0, "offload_txt_in": False, "offload_img_in": False}},
        "2": {"class_type": "HyVideoModelLoader", "inputs": {"model": model_name, "base_precision": "bf16", "quantization": "fp8_e4m3fn", "load_device": "offload_device", "attention_mode": _wrapper_attention_mode(req), "block_swap_args": ["1", 0]}},
        "3": {"class_type": "HyVideoVAELoader", "inputs": {"model_name": vae, "precision": "bf16"}},
        "4": {"class_type": "DownloadAndLoadHyVideoTextEncoder", "inputs": {"llm_model": "Kijai/llava-llama-3-8b-text-encoder-tokenizer", "clip_model": "disabled", "precision": "fp16", "apply_final_norm": False, "hidden_state_skip_layer": 2, "quantization": "disabled", "load_device": "offload_device"}},
        "5": {"class_type": "LoadImage", "inputs": {"image": image_ref}},
        "6": {"class_type": "HyVideoGetClosestBucketSize", "inputs": {"image": ["5", 0], "base_size": base_size}},
        "7": {"class_type": "ImageScale", "inputs": {"image": ["5", 0], "upscale_method": "lanczos", "width": ["6", 0], "height": ["6", 1], "crop": "disabled"}},
        "8": {"class_type": "HyVideoEncode", "inputs": {"vae": ["3", 0], "image": ["7", 0], "enable_vae_tiling": False, "temporal_tiling_sample_size": 64, "spatial_tile_sample_min_size": 256, "auto_tile_size": True, "noise_aug_strength": 0.02, "latent_strength": 1.0, "latent_dist": "mode"}},
        "9": {"class_type": "HyVideoI2VEncode", "inputs": {"text_encoders": ["4", 0], "prompt": prompt, "force_offload": True, "prompt_template": "I2V_video", "image": ["7", 0], "image_embed_interleave": 4}},
        "10": {"class_type": "HyVideoSampler", "inputs": {"model": ["2", 0], "hyvid_embeds": ["9", 0], "image_cond_latents": ["8", 0], "width": ["6", 0], "height": ["6", 1], "num_frames": length, "steps": steps, "embedded_guidance_scale": guidance, "flow_shift": flow_shift, "seed": seed, "force_offload": True, "denoise_strength": 1.0, "scheduler": "FlowMatchDiscreteScheduler", "riflex_freq_index": 0, "i2v_mode": "stability"}},
        "11": {"class_type": "HyVideoDecode", "inputs": {"vae": ["3", 0], "samples": ["10", 0], "enable_vae_tiling": True, "temporal_tiling_sample_size": 64, "spatial_tile_sample_min_size": 192, "auto_tile_size": False}},
        "12": {"class_type": "CreateVideo", "inputs": {"images": ["11", 0], "fps": fps}},
        "13": {"class_type": "SaveVideo", "inputs": {"video": ["12", 0], "filename_prefix": prefix, "format": "auto", "codec": "auto"}},
    }

def _build_native_hunyuan_video_prompt(req: dict[str, Any], object_info: dict[str, Any], *,
                                       command: str, family: str, job_id: str) -> dict[str, Any]:
    """HunyuanVideo T2V native graph (build-order #4). The FIRST video builder to thread the GENERIC
    component resolver (_resolve_native_video_stack -> component_resolver.resolve_stack) rather than
    family-private resolvers -- the video path's proof that the image core works for video. GROUNDED
    from the official hunyuan_video_text_to_video.json blueprint: the dual encoder loads via ONE
    DualCLIPLoader(type="hunyuan_video", clip_l + llava) -- like Flux, not two CLIPLoaders -- then
    ModelSamplingSD3(shift 7) + FluxGuidance (cfg MAPPED, NON-distilled, not pinned) feed the
    SamplerCustomAdvanced chain (RandomNoise / BasicGuider / KSamplerSelect(euler) / BasicScheduler
    (simple)); EmptyHunyuanLatentVideo -> VAEDecodeTiled -> CreateVideo -> SaveVideo. Companions are
    resolver-driven (llava precision-matched to the transformer dtype + clip_l + hunyuan vae).
    Render-proven clean (STEP 0). I2V is wrapper-only (not production): kijai HunyuanVideoWrapper.
    """
    if command == "i2v":
        # Wrapper-only i2v (not production). Native v1-concat / CLIPVisionEncode is blocked
        # by the upstream llava 768-vs-1024 bug; do not rebuild that dead graph here.
        return _build_native_hunyuan_wrapper_i2v_prompt(req, object_info, job_id=job_id)
    model_path = str(req.get("model") or "")
    unet_name = _comfy_unet_name_for_model(object_info, model_path)
    if not unet_name:
        raise RuntimeError(
            f"HunyuanVideo transformer is not visible to ComfyUI UNETLoader: {model_path!r} (must be under diffusion_models/)."
        )
    resolved = _resolve_native_video_stack(req, object_info, "hunyuan_video")
    missing = [s.component for s in resolved.missing_required()]
    if missing:
        raise RuntimeError(
            "HunyuanVideo stack incomplete -- missing required component(s): " + ", ".join(missing)
            + ". The resolver found no valid on-disk file for them; resolve or download before generating."
        )
    clip_l = resolved.value("text_encoder_clip_l") or "clip_l.safetensors"
    llava = resolved.value("text_encoder") or "llava_llama3_fp16.safetensors"   # precision-matched
    vae = resolved.value("vae") or "hunyuan_video_vae_bf16.safetensors"

    def _snap(value: Any, default: int, mult: int) -> int:
        try:
            v = int(value)
        except Exception:
            v = default
        return max(mult, v - (v % mult))

    prompt = str(req.get("prompt") or "")
    width = _snap(req.get("width"), 848, 16)
    height = _snap(req.get("height"), 480, 16)
    # Hunyuan temporal compression is /4 -> frame length must be (N*4)+1 (73/61/49...).
    try:
        raw_len = int(req.get("length") or req.get("num_frames") or 73)
    except Exception:
        raw_len = 73
    length = ((max(5, raw_len) - 1) // 4) * 4 + 1
    # Phase 2a: steps/cfg defaults lifted to the table (shift=7 below stays a hardcoded constant --
    # not a req-fallback -- so it is only recorded in the table, not routed).
    _defaults = operating_point_params("hunyuan_video", "default")
    try:
        steps = bounded_option(req, "steps", 20, table=_defaults)
    except Exception:
        steps = 20
    if steps < 1:
        steps = 20  # standard (non-distilled); blueprint default 20, honor the cockpit otherwise
    try:
        guidance = bounded_option(req, "cfg", 6.0, table=_defaults)
    except Exception:
        guidance = 6.0
    if guidance <= 0:
        guidance = 6.0  # cfg MAPPED -> FluxGuidance (blueprint 6); NOT pinned (Hunyuan is non-distilled)
    try:
        fps = bounded_option(req, "fps", 24.0)
    except Exception:
        fps = 24.0
    seed = resolve_seed(req, "seed")
    shift = 7.0  # ModelSamplingSD3 shift (grounded from the blueprint)
    prefix = _filename_prefix_from_output(str(req.get("output") or ""), job_id)
    # The blueprint's euler/simple stay the fallback, but they are no longer LITERALS: the cockpit
    # offers this family a sampler dropdown and the graph ignored it outright, so choosing dpmpp_2m
    # for Hunyuan rendered euler. The allowlist advertised dpmpp_2m/normal as the DEFAULT -- picked
    # alphabetically, because the family declared none -- so the advertised default was one the
    # graph could not produce.
    sampler_name, scheduler_name = sampling_for("hunyuan_video", req, object_info, "euler", "simple")

    graph: dict[str, Any] = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": unet_name, "weight_dtype": "default"}},
        "2": {"class_type": "DualCLIPLoader",
              "inputs": {"clip_name1": clip_l, "clip_name2": llava, "type": "hunyuan_video",
                         **text_encoder_device_input(req, object_info, "DualCLIPLoader")}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "5": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["4", 0], "guidance": guidance}},
        "6": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": shift}},
        "7": {"class_type": "BasicGuider", "inputs": {"model": ["6", 0], "conditioning": ["5", 0]}},
        "8": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": sampler_name}},
        "9": {"class_type": "BasicScheduler", "inputs": {"model": ["6", 0], "scheduler": scheduler_name, "steps": steps, "denoise": 1.0}},
        "10": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "11": {"class_type": "EmptyHunyuanLatentVideo", "inputs": {"width": width, "height": height, "length": length, "batch_size": 1}},
        "12": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["10", 0], "guider": ["7", 0], "sampler": ["8", 0], "sigmas": ["9", 0], "latent_image": ["11", 0]}},
        # Tiled by DECLARATION, not by hardcode: hunyuan needs the headroom at video frame counts,
        # and a request that turns tiling off must be able to.
        "13": vae_decode_node(req, object_info, samples=["12", 0], vae=["3", 0], default_tiled=True),
        "14": {"class_type": "CreateVideo", "inputs": {"images": ["13", 0], "fps": fps}},
        "15": {"class_type": "SaveVideo", "inputs": {"video": ["14", 0], "filename_prefix": prefix, "format": "auto", "codec": "auto"}},
    }
    return graph

def _build_native_mochi_video_prompt(req: dict[str, Any], object_info: dict[str, Any], *,
                                     command: str, family: str, job_id: str) -> dict[str, Any]:
    """Genmo Mochi-1 T2V native graph (build-order #5). GROUNDED from the official ComfyUI Mochi blueprint
    + a live /object_info dump on this box: the transformer loads via UNETLoader (mochi_preview_bf16, under
    diffusion_models/), the T5-XXL encoder via CLIPLoader(type="mochi"), the dedicated Mochi VAE via
    VAELoader. Two CLIPTextEncode nodes (pos/neg) -> EmptyMochiLatentVideo (w/h divisible by 16, length
    (N*6)+1) -> KSampler (euler/simple, REAL cfg -- Mochi is NOT distilled) -> VAEDecodeTiled (VRAM-safe on
    the 32GB card: the 18.7GB bf16 transformer + Mochi VAE decode is near-ceiling) -> CreateVideo -> SaveVideo.
    Companions (t5 + mochi_vae) are resolver-driven via the generic component resolver, mirroring Hunyuan.
    Mochi-1 is T2V-only; i2v is not a model capability and never reaches here (contract tasks=("t2v",); the
    run_native_split_stack_video i2v carve-out refuses non-ltx/wan families upstream)."""
    model_path = str(req.get("model") or "")
    unet_name = _comfy_unet_name_for_model(object_info, model_path)
    if not unet_name:
        raise RuntimeError(
            f"Mochi transformer is not visible to ComfyUI UNETLoader: {model_path!r} (must be under diffusion_models/)."
        )
    resolved = _resolve_native_video_stack(req, object_info, "mochi")
    missing = [s.component for s in resolved.missing_required()]
    if missing:
        raise RuntimeError(
            "Mochi stack incomplete -- missing required component(s): " + ", ".join(missing)
            + ". The resolver found no valid on-disk file for them; resolve or download before generating."
        )
    text_encoder = resolved.value("text_encoder") or "t5xxl_fp16.safetensors"
    vae = resolved.value("vae") or "mochi_vae.safetensors"

    def _snap(value: Any, default: int, mult: int) -> int:
        try:
            v = int(value)
        except Exception:
            v = default
        return max(mult, v - (v % mult))

    prompt = str(req.get("prompt") or "")
    negative = str(req.get("negative_prompt") or "")
    width = _snap(req.get("width"), 848, 16)     # EmptyMochiLatentVideo requires w/h divisible by 16
    height = _snap(req.get("height"), 480, 16)
    # Mochi temporal compression is /6 -> length must satisfy (length-1) divisible by 6 (7,13,...,163). Snap down.
    try:
        raw_len = int(req.get("length") or req.get("num_frames") or 25)
    except Exception:
        raw_len = 25
    length = ((max(7, raw_len) - 1) // 6) * 6 + 1
    _defaults = operating_point_params("mochi", "default")
    try:
        steps = bounded_option(req, "steps", 30, table=_defaults)
    except Exception:
        steps = 30
    if steps < 1:
        steps = 30
    try:
        cfg = bounded_option(req, "cfg", 4.5, table=_defaults)
    except Exception:
        cfg = 4.5
    if cfg <= 0:
        cfg = 4.5   # Mochi uses REAL cfg (non-distilled); request-overridable, NOT pinned
    try:
        fps = bounded_option(req, "fps", 24.0)
    except Exception:
        fps = 24.0
    seed = resolve_seed(req, "seed")
    prefix = _filename_prefix_from_output(str(req.get("output") or ""), job_id)

    # Mochi's operating point declares euler/simple and the graph hardcoded the same pair, so the
    # values do not change -- but they were unreachable, and an allowlist of one entry is a fact
    # about the family rather than a reason to skip the resolver.
    mochi_sampler, mochi_scheduler = sampling_for("mochi", req, object_info, "euler", "simple")
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": unet_name, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": text_encoder, "type": "mochi",
                         **text_encoder_device_input(req, object_info, "CLIPLoader")}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["2", 0]}},
        "7": {"class_type": "EmptyMochiLatentVideo", "inputs": {"width": width, "height": height, "length": length, "batch_size": 1}},
        "8": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "seed": seed, "steps": steps, "cfg": cfg, "sampler_name": mochi_sampler, "scheduler": mochi_scheduler, "positive": ["4", 0], "negative": ["6", 0], "latent_image": ["7", 0], "denoise": 1.0}},
        # Tiled by DECLARATION, as for hunyuan above.
        "9": vae_decode_node(req, object_info, samples=["8", 0], vae=["3", 0], default_tiled=True),
        "10": {"class_type": "CreateVideo", "inputs": {"images": ["9", 0], "fps": fps}},
        "11": {"class_type": "SaveVideo", "inputs": {"video": ["10", 0], "filename_prefix": prefix, "format": "auto", "codec": "auto"}},
    }

def _hunyuan_video_build(req: dict[str, Any], object_info: dict[str, Any], *, command: str, family: str, job_id: str):
    req["resolved_native_video_family"] = "hunyuan_video"
    req["native_video_route"] = "hunyuan_template"
    return _build_native_hunyuan_video_prompt(req, object_info, command=command, family=family, job_id=job_id)

def _wan_video_build(req: dict[str, Any], object_info: dict[str, Any], *, command: str, family: str, job_id: str):
    req["resolved_native_video_family"] = "wan"
    # Wan 2.2 A14B dual-noise: two experts + two-stage sampler. Routed BEFORE the
    # single-model core/wrapper checks when both experts are present. T2V and I2V.
    if (
        command in ("t2v", "i2v")
        and _is_wan_dual_noise_request(req)
        and "UNETLoader" in object_info
        and "KSamplerAdvanced" in object_info
    ):
        req["native_video_route"] = "wan_dual_noise"
        return _build_native_wan_dual_noise_video_prompt(req, object_info, command=command, family=family, job_id=job_id)
    if _should_use_native_wan_core_route(req, object_info) and "CLIPLoader" in object_info and "KSamplerAdvanced" in object_info:
        req["native_video_route"] = "wan_core"
        return _build_native_wan_core_video_prompt(req, object_info, command=command, family=family, job_id=job_id)
    if "WanVideoModelLoader" in object_info:
        req["native_video_route"] = "wan_wrapper"
        return _build_native_wan_split_video_prompt(req, object_info, command=command, family=family, job_id=job_id)
    return None  # no wan sub-route matched -> fall through to the generic fallback

def _ltx_video_build(req: dict[str, Any], object_info: dict[str, Any], *, command: str, family: str, job_id: str):
    req["resolved_native_video_family"] = "ltx"
    req["native_video_route"] = "ltx_template"
    return _build_native_ltx_video_prompt(req, object_info, command=command, family=family, job_id=job_id)

def _mochi_video_build(req: dict[str, Any], object_info: dict[str, Any], *, command: str, family: str, job_id: str):
    req["resolved_native_video_family"] = "mochi"
    req["native_video_route"] = "mochi_template"
    return _build_native_mochi_video_prompt(req, object_info, command=command, family=family, job_id=job_id)

def _native_video_plugin_for(family_key: str) -> "NativeFamilyPlugin | None":
    for plugin in NATIVE_VIDEO_FAMILY_PLUGINS:
        if plugin.match_prefix and family_key.startswith(plugin.match_prefix):
            return plugin
    return None

# A spatial latent upsampler multiplies the FRAME size without touching the requested width. On the
# default LTX route (two-stage distilled) `LTXVLatentUpsampler` runs between the two samplers, so a
# request for 768x512 renders a 1536x1024 picture: `req["width"]` is the size of the LATENT there,
# not the size of what comes out. Measured 2026-09-03 -- a 768x512x49f render produced a 1536x1024
# file, and the first version of the upscale graft targeted `req["width"] * scale` = 1536, which the
# frame already was, so it upscaled and then resized straight back to the size it started at. That
# is the same shape as this feature's original defect: a request honoured into a no-op.
_SPATIAL_LATENT_UPSAMPLERS: dict[str, int] = {
    "LTXVLatentUpsampler": 2,
}


def _video_frame_dimensions(graph: dict[str, Any], width: int, height: int) -> tuple[int, int]:
    """The size of the picture this graph produces, which is not always the size that was asked for.

    Derived from the graph rather than declared per family: a route that adds a spatial upsampler
    gets the right answer without anyone remembering to update a table, and a route that does not is
    unaffected. The factor table names node CLASSES, so it is checkable against `/object_info`.
    """
    factor = 1
    for node in graph.values():
        if isinstance(node, dict):
            factor *= _SPATIAL_LATENT_UPSAMPLERS.get(node.get("class_type"), 1)
    return int(width) * factor, int(height) * factor


def _apply_video_upscale(
    graph: dict[str, Any],
    req: dict[str, Any],
    object_info: dict[str, Any],
    *,
    family: str,
) -> dict[str, Any]:
    """Graft the requested upscale onto the video graph's image sink.

    Video was excluded from this route on the grounds that an ESRGAN pass "will not fit alongside
    LTX's ~31 GB". Measured on the live core 2026-09-03, LTX two-stage 768x512x49f, seeds varied so
    both runs really sampled: **baseline peak 31.55 GB, with the upscale 31.70 GB** -- +0.15 GB, not
    the +3.0 the same node costs when measured alone on an idle card. The two numbers do not stack
    because the peak is set by the SAMPLER, and ComfyUI has already freed the transformer by the
    time a node one hop after VAE decode runs. What the upscale costs on a real render is time:
    79.3s -> 285.4s for 49 frames at 3072x2048 out.
    """
    route = resolve_upscale_route(
        family, req.get("upscale_method"), enabled=bool(req.get("upscale_enabled"))
    )
    if route not in (ROUTE_PIXEL_COMFY, ROUTE_RESIZE_COMFY):
        return graph
    frame_width, frame_height = _video_frame_dimensions(
        graph, bounded_option(req, "width", 832), bounded_option(req, "height", 480)
    )
    common = dict(
        scale=bounded_option(req, "upscale_scale", 2.0),
        target_width=frame_width,
        target_height=frame_height,
    )
    if route == ROUTE_PIXEL_COMFY:
        return graft_pixel_upscale(
            graph,
            object_info,
            model_name=req.get("upscale_model_name") or req.get("upscale_model"),
            **common,
        )
    return graft_image_resize(graph, object_info, method=req.get("upscale_method"), **common)


def _build_native_split_video_prompt(
    req: dict[str, Any],
    object_info: dict[str, Any],
    *,
    command: str,
    family: str,
    job_id: str,
) -> dict[str, Any]:
    """Build the family's video graph, then apply whatever post-processing the request asked for.

    The upscale is applied HERE rather than inside each builder for the reason Doc 50 rule 10 gives:
    a post-pass added at one builder is a post-pass six other builders do not have. There is one
    place every video graph passes through, and this is it.
    """
    graph = _build_native_split_video_graph(
        req, object_info, command=command, family=family, job_id=job_id
    )
    return _apply_video_upscale(graph, req, object_info, family=family)


def _build_native_split_video_graph(
    req: dict[str, Any],
    object_info: dict[str, Any],
    *,
    command: str,
    family: str,
    job_id: str,
) -> dict[str, Any]:
    family_key = _infer_native_video_family_key(req, family)
    _raise_if_unvalidated_native_video_family(family_key, command=command)
    # STAGE 2b: the inline hunyuan/wan/ltx branching is fully replaced by the registry-plugin seam.
    # _native_video_plugin_for matches family_key.startswith(match_prefix) in the original if-chain
    # order; build returns None only for wan's no-sub-route case -> fall through to the generic fallback.
    video_plugin = _native_video_plugin_for(family_key)
    if video_plugin is not None:
        graph = video_plugin.build(req, object_info, command=command, family=family, job_id=job_id)
        if graph is not None:
            return graph

    # GENERIC unknown-family fallback: no hunyuan/wan/ltx builder matched. Make it OBSERVABLE -- these
    # defaults are REASONED (aligned to the validated video shape) but NOT render-validated for this
    # specific model. logging.info is filtered at the worker's root WARNING level, so this is a warning.
    _defaults = operating_point_params("native_split_generic", "default")
    req["native_video_route"] = "generic_fallback"
    logging.warning(
        "No specific native-video builder matched video family %r; using the GENERIC fallback "
        "(cfg=%s sampler=%s scheduler=%s shift=%s) -- these defaults are reasoned, not validated for this model.",
        family_key, _defaults.get("cfg"), _defaults.get("sampler"), _defaults.get("scheduler"), _defaults.get("shift"),
    )

    stack = _video_model_stack_from_request(req)
    missing = _stack_missing_parts(stack)
    if missing:
        raise RuntimeError("The selected native video stack is incomplete: missing " + ", ".join(missing))

    primary_path = _first_stack_value(stack, ("primary_path", "transformer_path", "unet_path", "model_path"))
    vae_path = str(stack.get("vae_path") or "").strip()
    if not primary_path:
        raise RuntimeError("The selected native split video stack has no primary diffusion model path.")
    if not vae_path:
        raise RuntimeError("The selected native split video stack has no VAE path.")

    unet_class = _first_available_class(
        object_info,
        ("UNETLoader", "DiffusionModelLoader", "LoadDiffusionModel"),
        label="diffusion model loading",
    )
    vae_class = _first_available_class(object_info, ("VAELoader",), label="VAE loading")
    text_class = _first_available_class(object_info, ("CLIPTextEncode",), label="prompt text encoding")
    sampler_class = _first_available_class(object_info, ("KSampler", "KSamplerAdvanced"), label="sampling")
    decode_class = _first_available_class(object_info, ("VAEDecode",), label="VAE decode")
    latent_class = _first_available_class(
        object_info,
        (
            "EmptyHunyuanLatentVideo",
            "EmptyWanLatentVideo",
            "WanEmptyLatentVideo",
            "EmptyLTXVLatentVideo",
            "EmptyLatentVideo",
        ),
        label="video latent creation",
    )
    save_class = _first_available_class(
        object_info,
        ("SaveWEBM", "SaveAnimatedWEBP", "VHS_VideoCombine", "SaveVideo"),
        label="video output saving",
    )

    frames = bounded_option(req, "frames", 81)
    fps = bounded_option(req, "fps", 16)
    width = bounded_option(req, "width", 832)
    height = bounded_option(req, "height", 480)
    # Defaults come from the native_split_generic table row (resolved above, with the generic-fallback
    # warning). The inline literals here are the last-resort safety net if that row is ever removed;
    # retuned to match the row (was cfg 7.0 / dpmpp_2m / karras / shift 8.0).
    steps = bounded_option(req, "steps", 30, table=_defaults)
    cfg = bounded_option(req, "cfg", 4.5, table=_defaults)
    seed = resolve_seed(req)

    prompt: dict[str, Any] = {}

    allowed = _comfy_class_inputs(object_info, unet_class)
    inputs: dict[str, Any] = {}
    _set_if_allowed(inputs, allowed, ("unet_name", "model_name", "ckpt_name", "checkpoint"), _comfy_unet_name(primary_path))
    _set_if_allowed(inputs, allowed, ("weight_dtype", "dtype"), _input_default_choice(object_info, unet_class, "weight_dtype", "default"))
    _add_node(prompt, "1", unet_class, inputs)

    clip_node_id = _build_clip_loader_node(prompt, object_info, stack, family)

    allowed = _comfy_class_inputs(object_info, vae_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("vae_name", "vae"), _preferred_video_vae_name(object_info, family, vae_path, primary_path))
    _add_node(prompt, "3", vae_class, inputs)

    model_link: list[Any] = ["1", 0]
    if "ModelSamplingSD3" in object_info:
        allowed = _comfy_class_inputs(object_info, "ModelSamplingSD3")
        inputs = {}
        _set_if_allowed(inputs, allowed, ("model",), model_link)
        _set_if_allowed(inputs, allowed, ("shift",), bounded_option(req, "shift", 5.0, table=_defaults))
        _add_node(prompt, "4", "ModelSamplingSD3", inputs)
        model_link = ["4", 0]

    allowed = _comfy_class_inputs(object_info, text_class)
    pos_inputs = {}
    _set_if_allowed(pos_inputs, allowed, ("clip",), [clip_node_id, 0])
    _set_if_allowed(pos_inputs, allowed, ("text", "prompt"), str(req.get("prompt") or ""))
    _add_node(prompt, "5", text_class, pos_inputs)

    neg_inputs = {}
    _set_if_allowed(neg_inputs, allowed, ("clip",), [clip_node_id, 0])
    _set_if_allowed(neg_inputs, allowed, ("text", "prompt"), str(req.get("negative_prompt") or ""))
    _add_node(prompt, "6", text_class, neg_inputs)

    allowed = _comfy_class_inputs(object_info, latent_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("width",), width)
    _set_if_allowed(inputs, allowed, ("height",), height)
    _set_if_allowed(inputs, allowed, ("length", "frames", "num_frames", "video_length", "frame_count"), frames)
    _set_if_allowed(inputs, allowed, ("batch_size",), 1)
    _add_node(prompt, "7", latent_class, inputs)

    allowed = _comfy_class_inputs(object_info, sampler_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("model",), model_link)
    _set_if_allowed(inputs, allowed, ("positive",), ["5", 0])
    _set_if_allowed(inputs, allowed, ("negative",), ["6", 0])
    _set_if_allowed(inputs, allowed, ("latent_image", "latent"), ["7", 0])
    _set_if_allowed(inputs, allowed, ("seed", "noise_seed"), seed)
    _set_if_allowed(inputs, allowed, ("steps",), steps)
    _set_if_allowed(inputs, allowed, ("cfg", "cfg_scale"), cfg)
    # Was `req.get("sampler") or default or "euler"` -- it honoured the request but validated
    # nothing, so a stale dropdown entry went straight to ComfyUI and came back a 400. Same resolver
    # as the UI populates from, so the two cannot disagree about what is selectable.
    _generic_sampler, _generic_scheduler = sampling_for(
        family_key or family, req, object_info,
        str(_defaults.get("sampler") or "euler"), str(_defaults.get("scheduler") or "simple"))
    _set_if_allowed(inputs, allowed, ("sampler_name", "sampler"), _generic_sampler)
    _set_if_allowed(inputs, allowed, ("scheduler",), _generic_scheduler)
    _set_if_allowed(inputs, allowed, ("denoise",), bounded_option(req, "denoise", 1.0, table=_defaults))
    _add_node(prompt, "8", sampler_class, inputs)

    allowed = _comfy_class_inputs(object_info, decode_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("samples", "latent", "latents"), ["8", 0])
    _set_if_allowed(inputs, allowed, ("vae",), ["3", 0])
    _add_node(prompt, "9", decode_class, inputs)

    allowed = _comfy_class_inputs(object_info, save_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("images", "image", "frames"), ["9", 0])
    _set_if_allowed(inputs, allowed, ("fps", "frame_rate"), fps)
    _set_if_allowed(inputs, allowed, ("filename_prefix", "filename", "output_path"), _filename_prefix_from_output(str(req.get("output") or ""), job_id))
    _set_if_allowed(inputs, allowed, ("codec",), _input_default_choice(object_info, save_class, "codec", "vp9"))
    _set_if_allowed(inputs, allowed, ("format",), _input_default_choice(object_info, save_class, "format", "webm"))
    _set_if_allowed(inputs, allowed, ("crf",), _input_default_choice(object_info, save_class, "crf", 23))
    _set_if_allowed(inputs, allowed, ("quality",), _input_default_choice(object_info, save_class, "quality", 80))
    _set_if_allowed(inputs, allowed, ("save_output",), _input_default_choice(object_info, save_class, "save_output", True))
    _add_node(prompt, "10", save_class, inputs)

    return prompt

def _prepare_native_video_adapter_request(
    req: dict[str, Any],
    object_info: dict[str, Any],
    *,
    command: str,
    family: str,
) -> dict[str, Any]:
    """Apply the family adapter before native video prompt construction.

    This keeps generic image/sampler defaults from leaking into family-specific
    Comfy nodes, such as WAN's sampler scheduler vocabulary.
    """
    try:
        from video_adapters.registry import select_native_video_adapter
    except Exception as exc:
        adapted = dict(req)
        warnings = list(adapted.get("native_video_adapter_warnings") or [])
        warnings.append(f"Native video adapter registry unavailable: {exc}")
        adapted["native_video_adapter_warnings"] = warnings
        return adapted

    adapter = select_native_video_adapter(req, object_info, command=command, family=family)
    result = adapter.prepare_request(req, object_info, command=command, family=family)
    adapted = result.payload
    adapted["native_video_adapter_family"] = adapter.family
    if result.warnings:
        adapted["native_video_adapter_warnings"] = result.warnings
    return adapted


def _canonical_native_video_family(family: str) -> str:
    return normalize_video_family_id(family)

def _raise_if_unvalidated_native_video_family(family: str, *, command: str) -> None:
    canonical = _canonical_native_video_family(family)
    contract = video_family_contract(canonical)
    status = contract.status_for_task(command)
    # production = native production path. wrapper = honest non-production sidestep (Hunyuan i2v).
    if status in {"production", "wrapper"}:
        return
    raise RuntimeError(
        f"{command.upper()} native video is production-enabled only for families marked production in the video family registry. "
        f"Resolved family '{canonical}' {command} is {status}; {contract.display_name} is not validated end-to-end yet. "
        "Use the production Wan video stack or run this family through an imported Comfy workflow/profile until it has its own validation pass."
    )


def _resolve_graph_model_names(*args, **kwargs):
    # Lives in comfy_prompt_client, NOT worker_service -- the godfile split moved it and the
    # worker no longer re-exports it, so the old `ws.` indirection raised AttributeError and
    # took both LTX routes down with it. comfy_prompt_client does not import this module, so
    # there is no cycle to lazily break here; the local import just keeps the shim shape.
    from comfy_prompt_client import _resolve_graph_model_names as impl

    return impl(*args, **kwargs)


def _apply_node_aliases(*args, **kwargs):
    # Same shim shape as above. comfy_node_aliases has no imports from this package, so the local
    # import is for consistency with the surrounding style rather than to break a cycle.
    from comfy_node_aliases import apply_node_aliases as impl

    return impl(*args, **kwargs)


def _spellvision_apply_teacache_to_native_video_prompt(*args, **kwargs):
    import worker_service as ws

    return ws._spellvision_apply_teacache_to_native_video_prompt(*args, **kwargs)


NATIVE_VIDEO_FAMILY_PLUGINS: tuple[NativeFamilyPlugin, ...] = (
    NativeFamilyPlugin(family="hunyuan_video", kind="video", build=_hunyuan_video_build, match_prefix="hunyuan"),
    NativeFamilyPlugin(family="wan", kind="video", build=_wan_video_build, match_prefix="wan"),
    NativeFamilyPlugin(family="ltx", kind="video", build=_ltx_video_build, match_prefix="ltx"),
    NativeFamilyPlugin(family="mochi", kind="video", build=_mochi_video_build, match_prefix="mochi"),
)


