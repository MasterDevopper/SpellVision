from __future__ import annotations

from typing import Any

from .base import (
    AdapterPrepareResult,
    VideoFamilyAdapter,
    haystack_for_detection,
    stack_dict_from_request,
)

_LTX_DIM_MULTIPLE = 32


def _snap_to_multiple(value: int, multiple: int) -> int:
    snapped = int(round(value / multiple)) * multiple
    return max(multiple, snapped)


def _snap_ltx_frame_length(value: int) -> int:
    # LTX's latent temporal stride makes valid frame counts (N*8)+1
    # (9, 17, 25, ... 49, 65, 97, 121, ...). Snap to the nearest valid count.
    n = max(1, int(round((value - 1) / 8)))
    return n * 8 + 1


class LtxVideoAdapter(VideoFamilyAdapter):
    """Native LTX (single-transformer, audio+video) adapter.

    Unlike Wan's dual-noise split stack, LTX runs through one embedded ComfyUI
    template (python/video_templates/ltx_av_native.json, a pruned single-pass AV
    graph). This adapter just tags the request for the LTX template route and
    surfaces the model-stack asset names; the heavy lifting (patching the proven
    template) happens in worker_service._build_native_ltx_video_prompt.
    """

    family = "ltx"
    display_name = "LTX Video"

    # The embedded template needs these LTX / audio-video / custom-sampler node
    # classes installed; is_available() gates the adapter on their presence.
    required_nodes = (
        "LTXVConditioning",
        "EmptyLTXVLatentVideo",
        "LTXVImgToVideoConditionOnly",
        "LTXVPreprocess",
        "LTXVEmptyLatentAudio",
        "LTXVAudioVAELoader",
        "LTXVConcatAVLatent",
        "LTXVSeparateAVLatent",
        "LTXVAudioVAEDecode",
        "LTXVTiledVAEDecode",
        "LTXVScheduler",
        "LTXAVTextEncoderLoader",
        "SamplerCustomAdvanced",
        "MultimodalGuider",
        "GuiderParameters",
        "ClownSampler_Beta",
        "CreateVideo",
        "SaveVideo",
    )

    def score(self, req: dict[str, Any], object_info: dict[str, Any], *, command: str, family: str) -> int:
        haystack = haystack_for_detection(req, family)
        if "ltx" not in haystack:
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
        payload["stack_kind"] = "ltx_av_single_pass"
        payload["native_video_route"] = "ltx_template"

        stack["family"] = self.family
        stack["model_family"] = self.family
        stack["video_family"] = self.family
        stack.setdefault("backend_kind", "native_video")
        stack["stack_kind"] = "ltx_av_single_pass"
        stack["native_video_route"] = "ltx_template"

        # Surface model-stack asset names the template builder may patch in
        # (it falls back to the template's proven defaults when these are absent).
        for src_keys, dst in (
            (("ltx_transformer", "transformer", "primary_path", "model_path"), "ltx_transformer"),
            (("ltx_video_vae", "video_vae", "vae_path", "vae_name"), "ltx_video_vae"),
            (("ltx_audio_vae", "audio_vae", "audio_vae_path"), "ltx_audio_vae"),
            (("ltx_text_encoder", "text_encoder", "text_encoder_path", "clip"), "ltx_text_encoder"),
            (("ltx_text_projection", "text_projection", "text_projection_path"), "ltx_text_projection"),
        ):
            value = next((payload.get(k) or stack.get(k) for k in src_keys if payload.get(k) or stack.get(k)), None)
            if value:
                payload[dst] = value

        # Hard LTX constraints (avoid a downstream ComfyUI 400 at submit): width &
        # height must be divisible by 32, and frame length must be (N*8)+1. Snap
        # invalid values in place with a clear warning rather than failing the run.
        for dim in ("width", "height"):
            try:
                value = int(payload.get(dim))
            except (TypeError, ValueError):
                continue
            snapped = _snap_to_multiple(value, _LTX_DIM_MULTIPLE)
            if snapped != value:
                warnings.append(f"LTX requires {dim} divisible by 32; snapped {value} -> {snapped}.")
            payload[dim] = snapped

        length_raw = next(
            (payload.get(k) for k in ("length", "frames", "num_frames", "frame_count")
             if payload.get(k) not in (None, "")),
            None,
        )
        try:
            length_value = int(length_raw)
        except (TypeError, ValueError):
            length_value = None
        if length_value is not None:
            snapped_length = _snap_ltx_frame_length(length_value)
            if snapped_length != length_value:
                warnings.append(f"LTX frame length must be (N*8)+1; snapped {length_value} -> {snapped_length}.")
            for key in ("length", "frames", "num_frames", "frame_count"):
                payload[key] = snapped_length

        payload["video_model_stack"] = stack
        payload["model_stack"] = stack
        payload["native_video_adapter_warnings"] = warnings
        return AdapterPrepareResult(payload=payload, warnings=warnings)
