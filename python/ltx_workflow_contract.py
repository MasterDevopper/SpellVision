from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from video_family_contracts import video_family_contract
from video_family_readiness import ltx_readiness_snapshot


PREFERRED_LTX_23_WORKFLOW_NAMES = (
    "LTX-2.3_T2V_I2V_Single_Stage_Distilled_Full.json",
    "LTX-2.3_T2V_I2V_Two_Stage_Distilled.json",
)

PREFERRED_LTX_BLUEPRINT_NAMES = (
    "Text to Video (LTX-2.3).json",
    "Image to Video (LTX-2.3).json",
    "First-Last-Frame to Video (LTX-2.3).json",
)


@dataclass(frozen=True)
class LtxWorkflowAsset:
    role: str
    name: str = ""
    path: str = ""
    size_bytes: int = 0
    required: bool = True

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LtxTestWorkflowContract:
    type: str = "ltx_test_workflow_contract"
    ok: bool = True
    family: str = "ltx"
    display_name: str = "LTX-Video"
    validation_status: str = "experimental"
    production_ready: bool = False
    ready_to_test: bool = False
    readiness: str = ""
    generation_enabled: bool = False
    generation_gate: str = "experimental_ready_to_test_required"
    backend_route: str = "comfy_profile_or_template"
    backend_type: str = "comfy_ltx_workflow"
    workflow_kind: str = "ltx_2_3_single_stage"
    workflow_source: str = ""
    workflow_name: str = ""
    workflow_path: str = ""
    workflow_profile_id: str = "ltx_2_3_t2v_i2v_single_stage_test"
    workflow_profile_name: str = "LTX 2.3 T2V/I2V Single Stage Test"
    request_kind: str = "t2v"
    stack_kind: str = "ltx_2_3_single_stage"
    stack_mode: str = "single_stage"
    stack_summary: str = ""
    assets: list[dict[str, Any]] = field(default_factory=list)
    recommended_settings: dict[str, Any] = field(default_factory=dict)
    request_metadata: dict[str, Any] = field(default_factory=dict)
    missing_assets: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    readiness_snapshot: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


def _first_candidate(readiness: dict[str, Any], key: str) -> dict[str, Any]:
    values = readiness.get(key)
    if isinstance(values, list) and values:
        first = values[0]
        return first if isinstance(first, dict) else {}
    return {}


def _candidate_asset(readiness: dict[str, Any], key: str, role: str, *, required: bool = True) -> LtxWorkflowAsset:
    item = _first_candidate(readiness, key)
    return LtxWorkflowAsset(
        role=role,
        name=str(item.get("name") or ""),
        path=str(item.get("path") or ""),
        size_bytes=int(item.get("size_bytes") or 0),
        required=required,
    )


def _choose_video_vae(readiness: dict[str, Any]) -> dict[str, Any]:
    candidates = readiness.get("ltx_video_vae_candidates")
    if not isinstance(candidates, list):
        return {}
    for item in candidates:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").lower()
        if "video" in name and "audio" not in name:
            return item
    for item in candidates:
        if isinstance(item, dict):
            return item
    return {}


def _choose_workflow(readiness: dict[str, Any]) -> tuple[str, str, str]:
    example_paths = [str(path) for path in readiness.get("ltx_example_workflows_found") or []]
    for preferred in PREFERRED_LTX_23_WORKFLOW_NAMES:
        for path in example_paths:
            normalized = path.replace("\\", "/")
            if normalized.endswith("/" + preferred) or normalized.endswith(preferred):
                return "example_workflow", preferred, path

    blueprint_paths = [str(path) for path in readiness.get("ltx_blueprints_found") or []]
    for preferred in PREFERRED_LTX_BLUEPRINT_NAMES:
        for path in blueprint_paths:
            normalized = path.replace("\\", "/")
            if normalized.endswith("/" + preferred) or normalized.endswith(preferred):
                return "blueprint", preferred, path

    if example_paths:
        path = example_paths[0]
        return "example_workflow", Path(path).name, path
    if blueprint_paths:
        path = blueprint_paths[0]
        return "blueprint", Path(path).name, path
    return "", "", ""


def _asset_payloads(readiness: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    checkpoint = _candidate_asset(readiness, "ltx_checkpoint_candidates", "ltx_checkpoint")
    text_encoder = _candidate_asset(readiness, "ltx_text_encoder_candidates", "gemma_text_encoder")
    projection = _candidate_asset(readiness, "ltx_projection_candidates", "ltx_text_projection")
    video_vae_item = _choose_video_vae(readiness)
    video_vae = LtxWorkflowAsset(
        role="ltx_video_vae",
        name=str(video_vae_item.get("name") or ""),
        path=str(video_vae_item.get("path") or ""),
        size_bytes=int(video_vae_item.get("size_bytes") or 0),
        required=True,
    )
    audio_vae = _candidate_asset(readiness, "ltx_audio_vae_candidates", "ltx_audio_vae_optional", required=False)

    assets = [checkpoint, text_encoder, projection, video_vae, audio_vae]
    by_role = {asset.role: asset.to_payload() for asset in assets}
    return [asset.to_payload() for asset in assets], by_role


def ltx_test_workflow_contract_snapshot(
    *,
    runtime_status: dict[str, Any] | None = None,
    object_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    readiness = ltx_readiness_snapshot(runtime_status=runtime_status, object_info=object_info)
    contract = video_family_contract("ltx")
    workflow_source, workflow_name, workflow_path = _choose_workflow(readiness)
    assets, assets_by_role = _asset_payloads(readiness)

    checkpoint = assets_by_role.get("ltx_checkpoint", {})
    text_encoder = assets_by_role.get("gemma_text_encoder", {})
    projection = assets_by_role.get("ltx_text_projection", {})
    video_vae = assets_by_role.get("ltx_video_vae", {})
    audio_vae = assets_by_role.get("ltx_audio_vae_optional", {})

    ready_to_test = bool(readiness.get("ready_to_test") and workflow_path)
    missing_assets = list(readiness.get("missing_assets") or [])
    if not workflow_path:
        missing_assets.append("ltx_test_workflow")

    generation_enabled = bool(ready_to_test and not missing_assets)
    stack_summary_parts = [
        str(checkpoint.get("name") or "checkpoint missing"),
        str(text_encoder.get("name") or "gemma missing"),
        str(video_vae.get("name") or "video vae missing"),
    ]
    stack_summary = " • ".join(stack_summary_parts)

    recommended_settings = {
        "cfg": 1.0,
        "steps": 8,
        "sampler": "euler",
        "scheduler": "linear_quadratic",
        "negative_prompt_effective": False,
        "recommended_start_mode": "t2v_then_i2v",
        "notes": [
            "DaSiWa LTX 2.3 Lightspeed is designed for low-step testing.",
            "Avoid extra speed LoRAs for the first smoke test.",
        ],
    }

    request_metadata = {
        "video_family": "ltx",
        "video_request_kind": "t2v",
        "video_stack_kind": "ltx_2_3_single_stage",
        "video_stack_mode": "single_stage",
        "video_stack_ready": generation_enabled,
        "video_model_stack_summary": stack_summary,
        "video_primary_model": checkpoint.get("path") or "",
        "video_primary_model_name": checkpoint.get("name") or "",
        "video_text_encoder": text_encoder.get("path") or "",
        "video_text_encoder_name": text_encoder.get("name") or "",
        "video_text_projection": projection.get("path") or "",
        "video_text_projection_name": projection.get("name") or "",
        "video_vae": video_vae.get("path") or "",
        "video_vae_name": video_vae.get("name") or "",
        "video_audio_vae": audio_vae.get("path") or "",
        "video_audio_vae_name": audio_vae.get("name") or "",
        "video_backend_type": "comfy_ltx_workflow",
        "video_backend_name": "ComfyUI-LTXVideo",
        "video_family_backend_route": contract.backend_route,
        "video_family_validation_status": contract.validation_status,
        "video_family_production_ready": contract.production_ready,
        "workflow_profile_id": "ltx_2_3_t2v_i2v_single_stage_test",
        "workflow_profile_name": "LTX 2.3 T2V/I2V Single Stage Test",
        "workflow_profile_path": workflow_path,
        "workflow_source": workflow_source,
        "workflow_name": workflow_name,
        "recommended_cfg": recommended_settings["cfg"],
        "recommended_steps": recommended_settings["steps"],
        "recommended_sampler": recommended_settings["sampler"],
        "recommended_scheduler": recommended_settings["scheduler"],
    }

    notes: list[str] = [
        "LTX remains experimental and is not replacing the Wan production route.",
        "This contract is for test workflow selection and metadata surfacing only.",
    ]
    if generation_enabled:
        notes.append("LTX readiness is ready_to_test; a gated smoke-test route can be wired next.")
    else:
        notes.append("LTX generation must remain disabled until readiness and workflow selection are complete.")

    payload = LtxTestWorkflowContract(
        display_name=contract.display_name,
        validation_status=contract.validation_status,
        production_ready=contract.production_ready,
        ready_to_test=ready_to_test,
        readiness=str(readiness.get("readiness") or ""),
        generation_enabled=generation_enabled,
        backend_route=contract.backend_route,
        workflow_source=workflow_source,
        workflow_name=workflow_name,
        workflow_path=workflow_path,
        stack_summary=stack_summary,
        assets=assets,
        recommended_settings=recommended_settings,
        request_metadata=request_metadata,
        missing_assets=missing_assets,
        notes=notes,
        readiness_snapshot=readiness,
    )
    return payload.to_payload()
