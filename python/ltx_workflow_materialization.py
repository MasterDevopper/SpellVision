from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ltx_smoke_test_route import ltx_t2v_smoke_test_snapshot

PROMPT_INPUT_KEYS = ("prompt", "text", "positive", "positive_prompt", "caption")
NEGATIVE_INPUT_KEYS = ("negative", "negative_prompt")
WIDTH_INPUT_KEYS = ("width", "W")
HEIGHT_INPUT_KEYS = ("height", "H")
FRAME_INPUT_KEYS = ("frames", "frame_count", "num_frames", "length")
FPS_INPUT_KEYS = ("fps", "frame_rate")
SEED_INPUT_KEYS = ("seed", "noise_seed")
STEP_INPUT_KEYS = ("steps", "num_steps")
CFG_INPUT_KEYS = ("cfg", "cfg_scale", "guidance", "guidance_scale")
SAMPLER_INPUT_KEYS = ("sampler", "sampler_name")
SCHEDULER_INPUT_KEYS = ("scheduler", "scheduler_name")
MODEL_INPUT_KEYS = ("model", "model_name", "unet_name", "ckpt_name", "transformer", "transformer_name")
TEXT_ENCODER_INPUT_KEYS = ("clip", "clip_name", "text_encoder", "text_encoder_name", "text_encoder_name1", "t5_name")
TEXT_PROJECTION_INPUT_KEYS = ("text_projection", "projection", "projection_name", "text_projection_name")
VAE_INPUT_KEYS = ("vae", "vae_name", "video_vae", "video_vae_name")
AUDIO_VAE_INPUT_KEYS = ("audio_vae", "audio_vae_name")


@dataclass(frozen=True)
class MaterializedMutation:
    node_id: str
    class_type: str
    input_key: str
    role: str
    old_value: Any
    new_value: Any
    applied: bool = False

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LtxWorkflowMaterialization:
    type: str = "ltx_workflow_materialization_dry_run"
    ok: bool = True
    family: str = "ltx"
    display_name: str = "LTX-Video"
    validation_status: str = "experimental"
    readiness: str = "unknown"
    ready_to_test: bool = False
    gate_passed: bool = False
    generation_enabled: bool = False
    execution_mode: str = "dry_run"
    submitted: bool = False
    submission_status: str = "not_submitted"
    workflow_name: str = ""
    workflow_path: str = ""
    workflow_exists: bool = False
    workflow_load_ok: bool = False
    workflow_node_count: int = 0
    mutation_count: int = 0
    applied_mutation_count: int = 0
    required_roles_present: list[str] = field(default_factory=list)
    required_roles_missing: list[str] = field(default_factory=list)
    mutation_roles_found: list[str] = field(default_factory=list)
    mutation_roles_missing: list[str] = field(default_factory=list)
    prompt_api_candidate: bool = False
    prompt_api_validation_status: str = "not_validated"
    materialized_workflow_preview: dict[str, Any] = field(default_factory=dict)
    mutations: list[dict[str, Any]] = field(default_factory=list)
    smoke_request: dict[str, Any] = field(default_factory=dict)
    request_metadata: dict[str, Any] = field(default_factory=dict)
    output_contract: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    route: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _basename(value: Any) -> str:
    text = _safe_text(value).replace("\\", "/")
    return text.rsplit("/", 1)[-1] if text else ""


def _load_workflow(path: str) -> tuple[dict[str, Any], str]:
    workflow_path = Path(path)
    if not workflow_path.exists():
        return {}, "workflow_path_missing"
    try:
        data = json.loads(workflow_path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        try:
            data = json.loads(workflow_path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            return {}, f"workflow_json_load_failed:{exc}"
    except Exception as exc:
        return {}, f"workflow_json_load_failed:{exc}"
    return (data if isinstance(data, dict) else {}), "loaded" if isinstance(data, dict) else "workflow_not_object"


def _workflow_nodes(workflow: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    if all(isinstance(v, dict) for v in workflow.values()) and any("class_type" in v for v in workflow.values() if isinstance(v, dict)):
        return [(str(k), v) for k, v in workflow.items() if isinstance(v, dict)]

    nodes = workflow.get("nodes")
    if isinstance(nodes, list):
        normalized: list[tuple[str, dict[str, Any]]] = []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id") or node.get("index") or len(normalized))
            normalized.append((node_id, node))
        return normalized
    return []


def _class_type(node: dict[str, Any]) -> str:
    return _safe_text(node.get("class_type") or node.get("type") or node.get("title"))


def _inputs(node: dict[str, Any]) -> dict[str, Any]:
    inputs = node.get("inputs")
    return inputs if isinstance(inputs, dict) else {}


def _find_input_mutations(workflow: dict[str, Any], *, smoke_request: dict[str, Any], request_metadata: dict[str, Any]) -> list[MaterializedMutation]:
    role_values: dict[str, Any] = {
        "prompt": smoke_request.get("prompt"),
        "negative_prompt": smoke_request.get("negative_prompt"),
        "width": smoke_request.get("width"),
        "height": smoke_request.get("height"),
        "frames": smoke_request.get("frames"),
        "fps": smoke_request.get("fps"),
        "seed": smoke_request.get("seed"),
        "steps": smoke_request.get("steps"),
        "cfg": smoke_request.get("cfg"),
        "sampler": smoke_request.get("sampler"),
        "scheduler": smoke_request.get("scheduler"),
        "model": _basename(request_metadata.get("video_primary_model")),
        "text_encoder": _basename(request_metadata.get("video_text_encoder")),
        "text_projection": _basename(request_metadata.get("video_text_projection")),
        "vae": _basename(request_metadata.get("video_vae")),
        "audio_vae": _basename(request_metadata.get("video_audio_vae")),
    }
    key_roles: list[tuple[str, tuple[str, ...]]] = [
        ("prompt", PROMPT_INPUT_KEYS),
        ("negative_prompt", NEGATIVE_INPUT_KEYS),
        ("width", WIDTH_INPUT_KEYS),
        ("height", HEIGHT_INPUT_KEYS),
        ("frames", FRAME_INPUT_KEYS),
        ("fps", FPS_INPUT_KEYS),
        ("seed", SEED_INPUT_KEYS),
        ("steps", STEP_INPUT_KEYS),
        ("cfg", CFG_INPUT_KEYS),
        ("sampler", SAMPLER_INPUT_KEYS),
        ("scheduler", SCHEDULER_INPUT_KEYS),
        ("model", MODEL_INPUT_KEYS),
        ("text_encoder", TEXT_ENCODER_INPUT_KEYS),
        ("text_projection", TEXT_PROJECTION_INPUT_KEYS),
        ("vae", VAE_INPUT_KEYS),
        ("audio_vae", AUDIO_VAE_INPUT_KEYS),
    ]
    mutations: list[MaterializedMutation] = []
    for node_id, node in _workflow_nodes(workflow):
        inputs = _inputs(node)
        if not inputs:
            continue
        class_type = _class_type(node)
        for role, keys in key_roles:
            new_value = role_values.get(role)
            if new_value is None:
                continue
            for key in keys:
                if key in inputs:
                    mutations.append(MaterializedMutation(node_id, class_type, key, role, inputs.get(key), new_value, False))
    return mutations


def _apply_mutations(workflow: dict[str, Any], mutations: list[MaterializedMutation]) -> dict[str, Any]:
    materialized = copy.deepcopy(workflow)
    nodes_by_id = {node_id: node for node_id, node in _workflow_nodes(materialized)}
    for mutation in mutations:
        node = nodes_by_id.get(mutation.node_id)
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict) or mutation.input_key not in inputs:
            continue
        inputs[mutation.input_key] = mutation.new_value
    return materialized


def _preview_workflow(workflow: dict[str, Any], limit: int = 8) -> dict[str, Any]:
    preview: dict[str, Any] = {}
    for index, (node_id, node) in enumerate(_workflow_nodes(workflow)):
        if index >= limit:
            break
        preview[node_id] = {"class_type": _class_type(node), "inputs": _inputs(node)}
    return preview


def _required_roles_from_request(request_metadata: dict[str, Any]) -> dict[str, bool]:
    return {
        "model": bool(request_metadata.get("video_primary_model")),
        "text_encoder": bool(request_metadata.get("video_text_encoder")),
        "text_projection": bool(request_metadata.get("video_text_projection")),
        "vae": bool(request_metadata.get("video_vae")),
    }


def ltx_workflow_materialization_dry_run_snapshot(req: dict[str, Any] | None = None, runtime_status: dict[str, Any] | None = None) -> dict[str, Any]:
    req = req or {}
    runtime_status = runtime_status or {}
    route = ltx_t2v_smoke_test_snapshot(req, runtime_status=runtime_status)
    smoke_request = dict(route.get("smoke_request") or {})
    request_metadata = dict(route.get("request_metadata") or {})
    workflow_path = _safe_text(route.get("workflow_path") or smoke_request.get("workflow_profile_path"))

    workflow, load_status = _load_workflow(workflow_path)
    workflow_exists = Path(workflow_path).exists() if workflow_path else False
    workflow_load_ok = bool(workflow and load_status == "loaded")
    nodes = _workflow_nodes(workflow) if workflow_load_ok else []
    prompt_api_candidate = bool(nodes and all("class_type" in node for _, node in nodes[: min(len(nodes), 5)]))

    mutations = _find_input_mutations(workflow, smoke_request=smoke_request, request_metadata=request_metadata) if workflow_load_ok else []
    materialized = _apply_mutations(workflow, mutations) if workflow_load_ok else {}
    role_set = sorted({mutation.role for mutation in mutations})
    required_roles = _required_roles_from_request(request_metadata)
    required_roles_present = sorted([role for role, present in required_roles.items() if present])
    required_roles_missing = sorted([role for role, present in required_roles.items() if not present])
    expected_mutation_roles = ["prompt", "width", "height", "frames", "fps", "seed", "steps", "cfg", "sampler", "scheduler"]
    mutation_roles_missing = sorted([role for role in expected_mutation_roles if role not in role_set])

    gate_passed = bool(route.get("gate_passed", False))
    submit_requested = bool(req.get("submit") or req.get("execute") or req.get("submit_to_comfy"))
    if not gate_passed:
        submission_status = "blocked_by_gate"
    elif not workflow_load_ok:
        submission_status = load_status
    elif submit_requested:
        submission_status = "dry_run_validated_submit_not_performed"
    else:
        submission_status = "dry_run_validated"

    notes = [
        "This pass loads the selected LTX workflow and performs a dry-run materialization only.",
        "No ComfyUI prompt submission is performed in this pass.",
        "Wan production routing remains untouched.",
    ]
    if not prompt_api_candidate:
        notes.append("Selected workflow may be a UI graph export rather than prompt API JSON; the next pass should normalize graph-to-prompt submission carefully.")
    if mutation_roles_missing:
        notes.append("Some smoke fields were not mapped to direct input keys; inspect workflow nodes before enabling submit.")

    diagnostics = {
        "checked_at": _utc_now_iso(),
        "workflow_load_status": load_status,
        "workflow_path_exists": workflow_exists,
        "workflow_node_count": len(nodes),
        "prompt_api_candidate": prompt_api_candidate,
        "mutation_roles_found": role_set,
        "mutation_roles_missing": mutation_roles_missing,
        "requested_submit": submit_requested,
        "comfy_running": bool((route.get("diagnostics") or {}).get("comfy_running", False)),
        "comfy_healthy": bool((route.get("diagnostics") or {}).get("comfy_healthy", False)),
        "comfy_endpoint_alive": bool((route.get("diagnostics") or {}).get("comfy_endpoint_alive", False)),
    }

    return LtxWorkflowMaterialization(
        readiness=str(route.get("readiness") or "unknown"),
        ready_to_test=bool(route.get("ready_to_test", False)),
        gate_passed=gate_passed,
        generation_enabled=bool(route.get("generation_enabled", False)),
        submitted=False,
        submission_status=submission_status,
        workflow_name=str(route.get("workflow_name") or ""),
        workflow_path=workflow_path,
        workflow_exists=workflow_exists,
        workflow_load_ok=workflow_load_ok,
        workflow_node_count=len(nodes),
        mutation_count=len(mutations),
        applied_mutation_count=len(mutations) if workflow_load_ok else 0,
        required_roles_present=required_roles_present,
        required_roles_missing=required_roles_missing,
        mutation_roles_found=role_set,
        mutation_roles_missing=mutation_roles_missing,
        prompt_api_candidate=prompt_api_candidate,
        prompt_api_validation_status="candidate" if prompt_api_candidate else "not_prompt_api_graph_or_unknown",
        materialized_workflow_preview=_preview_workflow(materialized),
        mutations=[m.to_payload() | {"applied": workflow_load_ok} for m in mutations],
        smoke_request=smoke_request,
        request_metadata=request_metadata,
        output_contract=dict(route.get("output_contract") or {}),
        diagnostics=diagnostics,
        route=route,
        notes=notes,
    ).to_payload()
