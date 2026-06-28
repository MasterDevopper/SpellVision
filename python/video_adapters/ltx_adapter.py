from __future__ import annotations

from typing import Any

from .base import (
    AdapterPrepareResult,
    VideoFamilyAdapter,
    haystack_for_detection,
    stack_dict_from_request,
)


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

        payload["video_model_stack"] = stack
        payload["model_stack"] = stack
        payload["native_video_adapter_warnings"] = warnings
        return AdapterPrepareResult(payload=payload, warnings=warnings)
