from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


CONTRACT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class VideoFamilyContract:
    family: str
    display_name: str
    tasks: tuple[str, ...]
    validation_status: str
    backend_route: str
    stack_kind: str
    required_components: tuple[str, ...]
    optional_components: tuple[str, ...]
    history_label_style: str
    runtime_affinity_fields: tuple[str, ...]
    readiness_notes: tuple[str, ...]
    markers: tuple[str, ...]
    pipeline_candidates_t2v: tuple[str, ...]
    pipeline_candidates_i2v: tuple[str, ...]

    @property
    def production_ready(self) -> bool:
        return self.validation_status == "production"

    @property
    def validated(self) -> bool:
        return self.validation_status in {"validated", "production"}

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["schema_version"] = CONTRACT_SCHEMA_VERSION
        payload["production_ready"] = self.production_ready
        payload["validated"] = self.validated
        # Convert tuples to lists for stable JSON payloads.
        for key, value in list(payload.items()):
            if isinstance(value, tuple):
                payload[key] = list(value)
        return payload


VIDEO_FAMILY_CONTRACTS: dict[str, VideoFamilyContract] = {
    "wan": VideoFamilyContract(
        family="wan",
        display_name="Wan",
        tasks=("t2v", "i2v"),
        validation_status="production",
        backend_route="native_comfy_template",
        stack_kind="wan_dual_noise",
        required_components=("low_noise_model", "high_noise_model", "vae", "text_encoder"),
        optional_components=("clip_vision", "lora", "teacache"),
        history_label_style="low_high_stack",
        runtime_affinity_fields=("family", "stack_kind", "low_noise_model", "high_noise_model", "vae", "text_encoder", "backend_route"),
        readiness_notes=("Wan is the current production T2V family.", "Use the low/high split stack contract for production renders."),
        markers=("wan", "wan2", "wan-2", "wan_2"),
        pipeline_candidates_t2v=("WanPipeline",),
        pipeline_candidates_i2v=("WanImageToVideoPipeline", "WanPipeline"),
    ),
    "ltx": VideoFamilyContract(
        family="ltx",
        display_name="LTX-Video",
        tasks=("t2v", "i2v"),
        validation_status="production",
        backend_route="native_comfy_template",
        stack_kind="ltx_av_single_pass",
        required_components=("model", "vae", "text_encoder"),
        # spatial_upscaler is the DISTILLED-TWO-STAGE route's ×2 latent upscaler (LatentUpscaleModelLoader).
        # OPTIONAL + route-dependent: only the default two-stage route uses it; the single-stage-full
        # (opt-in) route does not, so it must never be a hard requirement (mirrors Hunyuan's clip_vision).
        optional_components=("spatial_upscaler", "image_encoder", "lora", "scheduler_profile"),
        history_label_style="single_model_stack",
        runtime_affinity_fields=("family", "stack_kind", "model", "vae", "text_encoder", "workflow_or_template", "backend_route"),
        readiness_notes=("LTX-2.3 default route is distilled two-stage (Gemma text encode + ×2 spatial upscale, VRAM-safer); single-stage-full is opt-in (ltx_route='single_stage_full', quality/final).", "Full ltx-2.3-22b single-stage: use >=25 steps; 768x512x97f peaks ~31.4GB (premium, near-ceiling)."),
        markers=("ltx", "ltxv", "ltx-video", "ltx_video"),
        pipeline_candidates_t2v=("LTXVideoPipeline", "LTXPipeline"),
        pipeline_candidates_i2v=("LTXImageToVideoPipeline", "LTXVideoPipeline", "LTXPipeline"),
    ),
    "hunyuan_video": VideoFamilyContract(
        family="hunyuan_video",
        display_name="HunyuanVideo",
        tasks=("t2v", "i2v"),
        validation_status="production",
        backend_route="native_comfy_template",
        stack_kind="single_transformer_or_workflow",
        required_components=("model", "vae", "text_encoder"),
        # clip_vision is the i2v-only optional companion (v1-concat: CLIPVisionLoader(llava_llama3_vision)
        # -> CLIPVisionEncode -> TextEncodeHunyuanVideo_ImageToVideo). Manifest-gated applies_to_tasks:["i2v"]
        # OPTIONAL (not required_for) -- the mainstream HunyuanImageToVideo variant takes start_image+vae
        # with no clip_vision, so a blanket i2v requirement would false-block it.
        optional_components=("clip_vision", "lora", "scheduler_profile"),
        history_label_style="single_model_stack",
        runtime_affinity_fields=("family", "stack_kind", "model", "vae", "text_encoder", "workflow_or_template", "backend_route"),
        readiness_notes=(
            "T2V is production-native: DualCLIPLoader(hunyuan_video, clip_l+llava) + SamplerCustomAdvanced "
            "chain + ModelSamplingSD3(shift 7) + FluxGuidance, render-proven (build-order #4). I2V wiring is "
            "GROUNDED (v1 concat: CLIPVisionLoader(llava_llama3_vision)->CLIPVisionEncode->"
            "TextEncodeHunyuanVideo_ImageToVideo->HunyuanImageToVideo) but BLOCKED at render by a ComfyUI "
            "CLIPVisionEncode/llava3 768-vs-1024 projection issue. Discriminated: the on-disk vision file is "
            "byte-identical to the canonical Comfy-Org variant (sha256-verified), so it's the ComfyUI BUILD, "
            "not the file -> ships after a GATED ComfyUI update. i2v carve-out refuses it meanwhile.",
        ),
        markers=("hunyuan", "hyvideo", "hunyuanvideo"),
        pipeline_candidates_t2v=("HunyuanVideoPipeline",),
        pipeline_candidates_i2v=("HunyuanVideoImageToVideoPipeline", "HunyuanVideoPipeline"),
    ),
    "cogvideox": VideoFamilyContract(
        family="cogvideox",
        display_name="CogVideoX",
        tasks=("t2v", "i2v"),
        validation_status="detected",
        backend_route="future_comfy_profile",
        stack_kind="single_model_or_workflow",
        required_components=("model", "vae", "text_encoder"),
        optional_components=("lora", "scheduler_profile"),
        history_label_style="single_model_stack",
        runtime_affinity_fields=("family", "stack_kind", "model", "vae", "text_encoder", "workflow_or_template", "backend_route"),
        readiness_notes=("Detected only. Add a validated route before production use."),
        markers=("cogvideo", "cogvideox", "cog-video"),
        pipeline_candidates_t2v=("CogVideoXPipeline",),
        pipeline_candidates_i2v=("CogVideoXImageToVideoPipeline", "CogVideoXPipeline"),
    ),
    "mochi": VideoFamilyContract(
        family="mochi",
        display_name="Mochi",
        tasks=("t2v",),
        validation_status="production",
        backend_route="native_comfy_template",
        stack_kind="single_transformer_or_workflow",
        required_components=("model", "vae", "text_encoder"),
        optional_components=("scheduler_profile",),
        history_label_style="single_model_stack",
        runtime_affinity_fields=("family", "stack_kind", "model", "vae", "text_encoder", "workflow_or_template", "backend_route"),
        readiness_notes=(
            "T2V is production-native (build-order #5): UNETLoader(mochi transformer) + CLIPLoader(type=mochi, "
            "t5xxl) + VAELoader(mochi_vae) -> CLIPTextEncode x2 -> EmptyMochiLatentVideo -> KSampler(euler/simple, "
            "real cfg 4.5, 30 steps) -> VAEDecodeTiled -> CreateVideo/SaveVideo. Grounded from the official ComfyUI "
            "Mochi blueprint + live /object_info; render-proven. Mochi-1 is T2V-only (no i2v). Apache-2.0 (commercial-OK).",
        ),
        markers=("mochi",),
        pipeline_candidates_t2v=("MochiPipeline",),
        pipeline_candidates_i2v=("MochiPipeline",),
    ),
    "workflow": VideoFamilyContract(
        family="workflow",
        display_name="Comfy Workflow Video",
        tasks=("t2v", "i2v"),
        validation_status="configured",
        backend_route="comfy_workflow_profile",
        stack_kind="workflow_profile",
        required_components=("workflow_profile",),
        optional_components=("model", "vae", "text_encoder", "custom_nodes"),
        history_label_style="workflow_profile",
        runtime_affinity_fields=("family", "workflow_profile", "workflow_path", "backend_route"),
        readiness_notes=("Workflow-backed video support depends on the selected profile and node validation."),
        markers=("workflow", "comfy_workflow", "comfy-video"),
        pipeline_candidates_t2v=(),
        pipeline_candidates_i2v=(),
    ),
}


UNKNOWN_VIDEO_FAMILY_CONTRACT = VideoFamilyContract(
    family="unknown",
    display_name="Unknown Video Family",
    tasks=("t2v", "i2v"),
    validation_status="unsupported",
    backend_route="unknown",
    stack_kind="unknown",
    required_components=(),
    optional_components=(),
    history_label_style="generic",
    runtime_affinity_fields=("family", "stack_kind", "model", "backend_route"),
    readiness_notes=("Unknown video family. Select a supported family contract before enabling production generation."),
    markers=(),
    pipeline_candidates_t2v=(),
    pipeline_candidates_i2v=(),
)


_ALIASES = {
    "wan2": "wan",
    "wan_2": "wan",
    "wan-2": "wan",
    "ltxv": "ltx",
    "ltx_video": "ltx",
    "ltx-video": "ltx",
    "hunyuan": "hunyuan_video",
    "hyvideo": "hunyuan_video",
    "hunyuanvideo": "hunyuan_video",
    "cogvideo": "cogvideox",
    "cog-video": "cogvideox",
    "comfy_workflow": "workflow",
    "comfy-video": "workflow",
}


def normalize_video_family_id(value: Any) -> str:
    family = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    family = _ALIASES.get(family, family)
    return family or "unknown"


def video_family_contract(family: Any) -> VideoFamilyContract:
    family_id = normalize_video_family_id(family)
    return VIDEO_FAMILY_CONTRACTS.get(family_id, UNKNOWN_VIDEO_FAMILY_CONTRACT)


def infer_video_family_from_text(*values: Any) -> str:
    text = " ".join(str(value or "") for value in values).strip().lower().replace("-", "_")
    if not text:
        return "unknown"
    for family, contract in VIDEO_FAMILY_CONTRACTS.items():
        for marker in contract.markers:
            normalized_marker = marker.lower().replace("-", "_")
            if normalized_marker and normalized_marker in text:
                return family
    return "unknown"


def video_family_pipeline_candidates(command: Any, family: Any) -> list[str]:
    command_id = str(command or "").strip().lower()
    contract = video_family_contract(family)
    candidates = contract.pipeline_candidates_i2v if command_id == "i2v" else contract.pipeline_candidates_t2v
    return list(candidates)


def video_family_contracts_snapshot() -> dict[str, Any]:
    # Phase 3b: fold each family's operating points INTO the snapshot so the cockpit can fetch the whole
    # fast/quality table in one shot and cache it (they're a static table -- no per-change round-trip),
    # then render a selector GENERICALLY (>1 point -> show; the UI never learns a family name).
    from family_operating_points import family_operating_points_payload

    families: dict[str, Any] = {}
    for family, contract in VIDEO_FAMILY_CONTRACTS.items():
        payload = contract.to_payload()
        ops = family_operating_points_payload(family)
        payload["operating_points"] = ops["operating_points"]
        payload["default_operating_point"] = ops["default_operating_point"]
        families[family] = payload
    families["unknown"] = UNKNOWN_VIDEO_FAMILY_CONTRACT.to_payload()
    production_families = [f for f, c in VIDEO_FAMILY_CONTRACTS.items() if c.production_ready]
    experimental_families = [f for f, c in VIDEO_FAMILY_CONTRACTS.items() if c.validation_status == "experimental"]
    return {
        "type": "video_family_contracts",
        "ok": True,
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "active_production_family": "wan",
        "production_families": production_families,
        "active_experimental_family": experimental_families[0] if experimental_families else "",
        "families": families,
    }
