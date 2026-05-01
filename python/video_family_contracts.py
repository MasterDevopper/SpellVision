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
        validation_status="experimental",
        backend_route="comfy_profile_or_template",
        stack_kind="single_transformer_or_workflow",
        required_components=("model", "vae", "text_encoder"),
        optional_components=("image_encoder", "lora", "scheduler_profile"),
        history_label_style="single_model_stack",
        runtime_affinity_fields=("family", "stack_kind", "model", "vae", "text_encoder", "workflow_or_template", "backend_route"),
        readiness_notes=("LTX is detection-ready but not production validated yet.", "Add a Comfy template/profile route before marking it validated."),
        markers=("ltx", "ltxv", "ltx-video", "ltx_video"),
        pipeline_candidates_t2v=("LTXVideoPipeline", "LTXPipeline"),
        pipeline_candidates_i2v=("LTXImageToVideoPipeline", "LTXVideoPipeline", "LTXPipeline"),
    ),
    "hunyuan_video": VideoFamilyContract(
        family="hunyuan_video",
        display_name="HunyuanVideo",
        tasks=("t2v", "i2v"),
        validation_status="detected",
        backend_route="future_comfy_profile",
        stack_kind="single_transformer_or_workflow",
        required_components=("model", "vae", "text_encoder"),
        optional_components=("lora", "scheduler_profile"),
        history_label_style="single_model_stack",
        runtime_affinity_fields=("family", "stack_kind", "model", "vae", "text_encoder", "workflow_or_template", "backend_route"),
        readiness_notes=("Detected only. Add a validated Comfy route before enabling production use."),
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
        validation_status="detected",
        backend_route="future_comfy_profile",
        stack_kind="single_model_or_workflow",
        required_components=("model",),
        optional_components=("vae", "text_encoder", "scheduler_profile"),
        history_label_style="single_model_stack",
        runtime_affinity_fields=("family", "stack_kind", "model", "workflow_or_template", "backend_route"),
        readiness_notes=("Detected only. Add a validated route before production use."),
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
    families = {family: contract.to_payload() for family, contract in VIDEO_FAMILY_CONTRACTS.items()}
    families["unknown"] = UNKNOWN_VIDEO_FAMILY_CONTRACT.to_payload()
    return {
        "type": "video_family_contracts",
        "ok": True,
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "active_production_family": "wan",
        "active_experimental_family": "ltx",
        "families": families,
    }
