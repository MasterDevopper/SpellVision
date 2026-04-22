from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import (
    AdapterPrepareResult,
    VideoFamilyAdapter,
    choose_from_object_info_aliases,
    haystack_for_detection,
    input_choices,
    normalize_choice,
    stack_dict_from_request,
)

CORE_SCHEDULERS = ("sgm_uniform", "normal", "simple", "karras")
CORE_SAMPLERS = ("dpmpp_2m", "dpm++_2m", "euler", "uni_pc", "unipc")
WRAPPER_SCHEDULERS = ("normal", "simple", "sgm_uniform", "flowmatch_causvid")
WRAPPER_SAMPLERS = ("uni_pc", "unipc", "euler", "euler_ancestral", "dpmpp_2m")


def _basename(value: Any) -> str:
    text = str(value or "").strip().replace("\\", "/")
    return Path(text).name if text else ""


def _is_fp8_scaled(value: Any) -> bool:
    name = _basename(value).lower()
    return bool(name and "fp8" in name and "scaled" in name)


def _choose_core_clip(object_info: dict[str, Any], requested: Any) -> tuple[str, bool, list[str]]:
    choices = input_choices(object_info, "CLIPLoader", "clip_name")
    requested_name = _basename(requested)
    if not choices:
        return requested_name, False, []

    by_lower = {choice.lower(): choice for choice in choices}
    if requested_name:
        found = by_lower.get(requested_name.lower())
        if found:
            return found, False, choices

    for preferred in (
        "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
        "t5xxl_fp8_e4m3fn_scaled.safetensors",
        "t5xxl_fp16.safetensors",
    ):
        found = by_lower.get(preferred.lower())
        if found:
            return found, bool(requested_name and requested_name.lower() != found.lower()), choices

    for choice in choices:
        lowered = choice.lower()
        if "umt5" in lowered or "t5" in lowered:
            return choice, bool(requested_name and requested_name.lower() != choice.lower()), choices

    return choices[0], bool(requested_name and requested_name.lower() != choices[0].lower()), choices


def _choose_wrapper_t5(object_info: dict[str, Any], requested: Any) -> tuple[str, bool, list[str]]:
    choices = input_choices(object_info, "LoadWanVideoT5TextEncoder", "model_name")
    requested_name = _basename(requested)
    if not choices:
        return requested_name, False, []

    by_lower = {choice.lower(): choice for choice in choices}
    if requested_name and not _is_fp8_scaled(requested_name):
        found = by_lower.get(requested_name.lower())
        if found:
            return found, False, choices

    for choice in choices:
        lowered = choice.lower()
        if "t5" in lowered and not _is_fp8_scaled(choice) and any(m in lowered for m in ("fp16", "bf16")):
            return choice, bool(requested_name and requested_name.lower() != choice.lower()), choices

    for choice in choices:
        if not _is_fp8_scaled(choice):
            return choice, bool(requested_name and requested_name.lower() != choice.lower()), choices

    return choices[0], bool(requested_name and requested_name.lower() != choices[0].lower()), choices


def _route(req: dict[str, Any], requested_text: Any) -> str:
    raw = str(req.get("wan_text_route") or req.get("native_video_route") or req.get("video_route") or "auto").strip().lower().replace("-", "_")
    if raw in {"wrapper", "wan_wrapper", "wanvideowrapper", "wan_video_wrapper"}:
        return "wrapper"
    if raw in {"core", "wan_core", "core_wan", "comfy_core"}:
        return "core"
    if _is_fp8_scaled(requested_text):
        return "core"
    return "core"


class WanVideoAdapter(VideoFamilyAdapter):
    family = "wan"
    display_name = "WAN Video"
    required_nodes = (
        "CLIPLoader",
        "CLIPTextEncode",
        "UNETLoader",
        "VAELoader",
        "ModelSamplingSD3",
        "EmptyHunyuanLatentVideo",
        "KSamplerAdvanced",
        "VAEDecode",
        "CreateVideo",
        "SaveVideo",
    )

    def score(self, req: dict[str, Any], object_info: dict[str, Any], *, command: str, family: str) -> int:
        haystack = haystack_for_detection(req, family)
        if "wan" not in haystack and "wan2" not in haystack and "wan22" not in haystack:
            return 0
        return 100 if self.is_available(object_info) else 0

    def prepare_request(self, req: dict[str, Any], object_info: dict[str, Any], *, command: str, family: str) -> AdapterPrepareResult:
        payload = dict(req)
        warnings: list[str] = []
        stack = stack_dict_from_request(payload)

        payload["native_video_adapter_family"] = self.family
        payload["resolved_native_video_family"] = self.family
        payload["model_family"] = self.family
        payload["video_family"] = self.family
        payload.setdefault("backend_kind", "native_video")
        payload.setdefault("stack_kind", "split_stack")

        stack["family"] = self.family
        stack["model_family"] = self.family
        stack["video_family"] = self.family
        stack.setdefault("backend_kind", "native_video")
        stack.setdefault("stack_kind", "split_stack")

        requested_text = payload.get("video_text_encoder") or payload.get("text_encoder") or stack.get("text_encoder") or stack.get("text_encoder_path") or stack.get("clip") or stack.get("clip_path")
        route = _route(payload, requested_text)
        payload["wan_text_route"] = route
        payload["native_video_route"] = "wan_core" if route == "core" else "wan_wrapper"
        stack["wan_text_route"] = route
        stack["native_video_route"] = payload["native_video_route"]

        if route == "core":
            encoder, changed, text_choices = _choose_core_clip(object_info, requested_text)
            sampler_node = "KSamplerAdvanced"
            sampler_defaults = CORE_SAMPLERS
            scheduler_defaults = CORE_SCHEDULERS
            if changed:
                warnings.append(f"WAN core route uses CLIPLoader(type='wan'); text encoder '{_basename(requested_text) or '<empty>'}' was replaced with '{encoder}'.")
        else:
            encoder, changed, text_choices = _choose_wrapper_t5(object_info, requested_text)
            sampler_node = "WanVideoSampler"
            sampler_defaults = WRAPPER_SAMPLERS
            scheduler_defaults = WRAPPER_SCHEDULERS
            if _is_fp8_scaled(requested_text):
                warnings.append(f"WAN wrapper route rejects fp8-scaled text encoder '{_basename(requested_text)}'; using '{encoder}'.")
            elif changed:
                warnings.append(f"WAN wrapper text encoder '{_basename(requested_text) or '<empty>'}' was replaced with '{encoder}'.")

        if encoder:
            payload["text_encoder"] = encoder
            payload["text_encoder_path"] = encoder
            payload["video_text_encoder"] = encoder
            stack["text_encoder"] = encoder
            stack["text_encoder_path"] = encoder
            stack["clip"] = encoder
            stack["clip_path"] = encoder

        scheduler, scheduler_changed, scheduler_choices, scheduler_input = choose_from_object_info_aliases(
            object_info,
            sampler_node,
            ("scheduler", "scheduler_name"),
            payload.get("video_scheduler") or payload.get("scheduler"),
            preferred_defaults=scheduler_defaults,
        )
        if scheduler:
            if scheduler_changed:
                warnings.append(f"WAN scheduler '{normalize_choice(payload.get('video_scheduler') or payload.get('scheduler')) or '<auto>'}' is not valid for {sampler_node}; using '{scheduler}'.")
            payload["scheduler"] = scheduler
            payload["video_scheduler"] = scheduler
            stack["scheduler"] = scheduler
            stack["video_scheduler"] = scheduler

        sampler, sampler_changed, sampler_choices, sampler_input = choose_from_object_info_aliases(
            object_info,
            sampler_node,
            ("sampler_name", "sampler", "sampler_type"),
            payload.get("video_sampler") or payload.get("sampler"),
            preferred_defaults=sampler_defaults,
        )
        if sampler:
            if sampler_changed:
                warnings.append(f"WAN sampler '{normalize_choice(payload.get('video_sampler') or payload.get('sampler')) or '<auto>'}' is not valid for {sampler_node}; using '{sampler}'.")
            payload["sampler"] = sampler
            payload["video_sampler"] = sampler
            stack["sampler"] = sampler
            stack["video_sampler"] = sampler

        payload["video_model_stack"] = stack
        payload["model_stack"] = stack
        payload["native_video_adapter_warnings"] = warnings
        payload["native_video_text_encoder_choices"] = text_choices
        payload["native_video_sampler_node"] = sampler_node
        payload["native_video_scheduler_choices"] = scheduler_choices
        payload["native_video_scheduler_input"] = scheduler_input
        payload["native_video_sampler_choices"] = sampler_choices
        payload["native_video_sampler_input"] = sampler_input

        return AdapterPrepareResult(payload=payload, warnings=warnings)
