from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ltx_workflow_graph_inspection import ltx_workflow_graph_inspection_snapshot


@dataclass(frozen=True)
class LtxPromptApiAdapterSnapshot:
    type: str = "ltx_prompt_api_conversion_adapter"
    ok: bool = True
    family: str = "ltx"
    display_name: str = "LTX-Video"
    validation_status: str = "experimental"
    readiness: str = "unknown"
    ready_to_test: bool = False
    gate_passed: bool = False
    generation_enabled: bool = False
    submitted: bool = False
    submission_status: str = "not_submitted"
    execution_mode: str = "adapter_preview"
    workflow_name: str = ""
    workflow_path: str = ""
    workflow_exists: bool = False
    workflow_load_ok: bool = False
    workflow_format: str = "unknown"
    node_count: int = 0
    link_count: int = 0
    prompt_api_candidate: bool = False
    prompt_api_validation_status: str = "unknown"
    normalization_ready: bool = False
    adapter_ready: bool = False
    adapter_status: str = "unknown"
    safe_to_submit: bool = False
    prompt_api_export_path: str = ""
    prompt_api_export_exists: bool = False
    prompt_api_export_load_ok: bool = False
    prompt_api_export_validation_status: str = "not_provided"
    conversion_required: bool = True
    adapter_role_map: dict[str, Any] = field(default_factory=dict)
    adapter_mutation_preview: list[dict[str, Any]] = field(default_factory=list)
    unresolved_roles: list[str] = field(default_factory=list)
    blocked_submit_reasons: list[str] = field(default_factory=list)
    prompt_api_preview: dict[str, Any] = field(default_factory=dict)
    conversion_plan: dict[str, Any] = field(default_factory=dict)
    graph_inspection: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json_file(path_value: Any) -> tuple[dict[str, Any], str]:
    if not path_value:
        return {}, "not_provided"
    path = Path(str(path_value)).expanduser()
    if not path.exists():
        return {}, "missing"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": str(exc)}, "load_failed"
    if not isinstance(data, dict):
        return {"error": "JSON root is not an object"}, "invalid_root"
    return data, "loaded"


def _is_prompt_api_graph(workflow: dict[str, Any]) -> bool:
    if not workflow or "nodes" in workflow or "links" in workflow:
        return False
    node_like = 0
    for key, node in workflow.items():
        if isinstance(key, str) and key.isdigit() and isinstance(node, dict):
            if isinstance(node.get("inputs"), dict) and isinstance(node.get("class_type"), str):
                node_like += 1
    return node_like > 0


def _prompt_api_validation_status(workflow: dict[str, Any], load_status: str) -> str:
    if load_status != "loaded":
        return load_status
    return "prompt_api_graph_detected" if _is_prompt_api_graph(workflow) else "not_prompt_api_graph"


def _workflow_nodes(ui_workflow: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = ui_workflow.get("nodes")
    return [node for node in nodes if isinstance(node, dict)] if isinstance(nodes, list) else []


def _node_by_id(nodes: list[dict[str, Any]], node_id: str) -> dict[str, Any] | None:
    for node in nodes:
        if str(node.get("id")) == str(node_id):
            return node
    return None


def _node_class(node: dict[str, Any] | None) -> str:
    return str((node or {}).get("type") or (node or {}).get("class_type") or "").strip()


def _widget_values(node: dict[str, Any] | None) -> list[Any]:
    values = (node or {}).get("widgets_values")
    return values if isinstance(values, list) else []


def _slot_exists(nodes: list[dict[str, Any]], node_id: str, expected_class: str, widget_index: int) -> bool:
    node = _node_by_id(nodes, node_id)
    return bool(_node_class(node) == expected_class and len(_widget_values(node)) > widget_index)


def _slot(role: str, node_id: str, class_type: str, widget_index: int, value: Any, confidence: str, note: str = "") -> dict[str, Any]:
    return {
        "role": role,
        "node_id": str(node_id),
        "class_type": class_type,
        "source": "widgets_values",
        "input_key": f"widgets_values[{widget_index}]",
        "widget_index": widget_index,
        "target_value": value,
        "confidence": confidence,
        "safe_to_mutate": False,
        "note": note,
    }


def _build_current_ui_adapter_map(nodes: list[dict[str, Any]], smoke_request: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[dict[str, Any]]]:
    planned = {
        "prompt": ("2483", "CLIPTextEncode", 0, smoke_request.get("prompt"), "high", "Positive prompt text node."),
        "negative_prompt": ("2612", "CLIPTextEncode", 0, smoke_request.get("negative_prompt", ""), "high", "Negative prompt text node."),
        "width": ("3059", "EmptyLTXVLatentVideo", 0, smoke_request.get("width"), "high", "Latent width widget."),
        "height": ("3059", "EmptyLTXVLatentVideo", 1, smoke_request.get("height"), "high", "Latent height widget."),
        "frames": ("3059", "EmptyLTXVLatentVideo", 2, smoke_request.get("frames"), "high", "Latent frame count widget."),
        "batch": ("3059", "EmptyLTXVLatentVideo", 3, 1, "medium", "Batch size; kept at 1 for smoke test."),
        "seed_primary": ("4814", "RandomNoise", 0, smoke_request.get("seed"), "medium", "Primary RandomNoise seed preview."),
        "seed_secondary": ("4832", "RandomNoise", 0, smoke_request.get("seed"), "medium", "Secondary RandomNoise seed preview."),
        "cfg": ("4828", "CFGGuider", 0, smoke_request.get("cfg"), "high", "CFG guider widget."),
        "sampler": ("4831", "KSamplerSelect", 0, smoke_request.get("sampler"), "medium", "Sampler may need LTX-specific translation."),
        "fps": ("4978", "PrimitiveFloat", 0, smoke_request.get("fps"), "high", "FPS primitive."),
        "frames_primitive": ("4979", "PrimitiveInt", 0, smoke_request.get("frames"), "high", "Frame count primitive."),
        "checkpoint": ("3940", "CheckpointLoaderSimple", 0, smoke_request.get("video_primary_model_name"), "high", "LTX checkpoint loader."),
        "text_encoder": ("4960", "LTXAVTextEncoderLoader", 0, smoke_request.get("video_text_encoder_name"), "high", "Gemma text encoder loader."),
        "text_projection": ("4960", "LTXAVTextEncoderLoader", 1, smoke_request.get("video_text_projection_name"), "medium", "Likely projection/model slot; requires object_info confirmation before submit."),
        "audio_vae": ("4010", "LTXVAudioVAELoader", 0, smoke_request.get("video_audio_vae_name"), "medium", "Optional audio VAE loader."),
        "output_prefix_primary": ("4823", "SaveVideo", 0, "spellvision_ltx_smoke", "medium", "Primary SaveVideo prefix."),
        "output_prefix_secondary": ("4852", "SaveVideo", 0, "spellvision_ltx_smoke", "medium", "Secondary SaveVideo prefix."),
    }

    adapter_map: dict[str, Any] = {}
    unresolved: list[str] = []
    mutation_preview: list[dict[str, Any]] = []
    for role, (node_id, class_type, widget_index, value, confidence, note) in planned.items():
        if _slot_exists(nodes, node_id, class_type, widget_index):
            item = _slot(role, node_id, class_type, widget_index, value, confidence, note)
            adapter_map[role] = item
            mutation_preview.append(item)
        else:
            unresolved.append(role)
    return adapter_map, unresolved, mutation_preview


def _minimal_prompt_api_preview(prompt_api_export: dict[str, Any], smoke_request: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[dict[str, Any]]]:
    if not _is_prompt_api_graph(prompt_api_export):
        return {}, ["prompt_api_graph"], []

    preview = copy.deepcopy(prompt_api_export)
    mutation_preview: list[dict[str, Any]] = []
    unresolved: list[str] = []

    def apply_first(role: str, class_tokens: tuple[str, ...], input_names: tuple[str, ...], value: Any) -> bool:
        for node_id, node in preview.items():
            if not isinstance(node, dict):
                continue
            class_type = str(node.get("class_type") or "")
            if not any(token.lower() in class_type.lower() for token in class_tokens):
                continue
            inputs = node.get("inputs")
            if not isinstance(inputs, dict):
                continue
            for name in input_names:
                if name in inputs:
                    old = inputs.get(name)
                    inputs[name] = value
                    mutation_preview.append({
                        "role": role,
                        "node_id": str(node_id),
                        "class_type": class_type,
                        "source": "inputs",
                        "input_key": name,
                        "old_value_preview": str(old)[:120],
                        "target_value": value,
                        "confidence": "medium",
                        "safe_to_mutate": True,
                    })
                    return True
        return False

    role_specs = [
        ("prompt", ("TextEncode", "CLIPTextEncode", "Gemma"), ("text", "prompt", "positive"), smoke_request.get("prompt")),
        ("negative_prompt", ("TextEncode", "CLIPTextEncode", "Gemma"), ("negative", "negative_prompt", "text"), smoke_request.get("negative_prompt", "")),
        ("seed", ("RandomNoise", "KSampler"), ("noise_seed", "seed"), smoke_request.get("seed")),
        ("steps", ("KSampler", "Sampler", "Scheduler"), ("steps",), smoke_request.get("steps")),
        ("cfg", ("CFGGuider", "Guider", "KSampler"), ("cfg", "guidance", "guidance_scale"), smoke_request.get("cfg")),
        ("width", ("EmptyLTXVLatentVideo", "EmptyLatent"), ("width",), smoke_request.get("width")),
        ("height", ("EmptyLTXVLatentVideo", "EmptyLatent"), ("height",), smoke_request.get("height")),
        ("frames", ("EmptyLTXVLatentVideo", "PrimitiveInt"), ("length", "frames", "num_frames", "frame_count"), smoke_request.get("frames")),
    ]

    for role, class_tokens, input_names, value in role_specs:
        if not apply_first(role, class_tokens, input_names, value):
            unresolved.append(role)

    return preview, unresolved, mutation_preview


def ltx_prompt_api_conversion_adapter_snapshot(req: dict[str, Any] | None = None, runtime_status: dict[str, Any] | None = None) -> dict[str, Any]:
    req = req or {}
    runtime_status = runtime_status or {}
    graph = ltx_workflow_graph_inspection_snapshot(req, runtime_status=runtime_status)

    smoke_request = graph.get("smoke_request") if isinstance(graph.get("smoke_request"), dict) else {}
    workflow_path = str(graph.get("workflow_path") or "")
    workflow, workflow_status = _load_json_file(workflow_path)
    nodes = _workflow_nodes(workflow)

    export_path = str(req.get("prompt_api_export_path") or req.get("api_workflow_path") or "").strip()
    prompt_api_export, export_status = _load_json_file(export_path)
    export_is_prompt_api = _is_prompt_api_graph(prompt_api_export)
    export_validation = _prompt_api_validation_status(prompt_api_export, export_status)

    adapter_map, ui_unresolved, ui_preview = _build_current_ui_adapter_map(nodes, smoke_request)
    prompt_preview: dict[str, Any] = {}
    export_unresolved: list[str] = []
    export_mutations: list[dict[str, Any]] = []

    if export_is_prompt_api:
        prompt_preview, export_unresolved, export_mutations = _minimal_prompt_api_preview(prompt_api_export, smoke_request)

    using_prompt_export = bool(export_is_prompt_api and not export_unresolved)
    adapter_ready = bool(adapter_map and not ui_unresolved)
    normalization_ready = using_prompt_export

    blocked_submit_reasons: list[str] = []
    if not bool(graph.get("gate_passed", False)):
        blocked_submit_reasons.append("ltx_gate_not_passed")
    if not normalization_ready:
        blocked_submit_reasons.append("prompt_api_export_required_or_unresolved")
    if not export_path:
        blocked_submit_reasons.append("prompt_api_export_path_not_provided")
    if export_path and not export_is_prompt_api:
        blocked_submit_reasons.append("provided_export_is_not_prompt_api_graph")
    if export_unresolved:
        blocked_submit_reasons.append("prompt_api_export_missing_mutation_roles")
    if req.get("submit") or req.get("execute") or req.get("submit_to_comfy"):
        blocked_submit_reasons.append("submission_intentionally_blocked_in_pass7")

    submission_status = "prompt_api_export_validated" if using_prompt_export else "adapter_preview_requires_prompt_api_export"
    adapter_status = "prompt_api_export_ready" if using_prompt_export else "ui_graph_adapter_plan_ready"

    conversion_plan = {
        "source_format": graph.get("workflow_format"),
        "target_format": "prompt_api_graph",
        "adapter_ready": adapter_ready,
        "normalization_ready": normalization_ready,
        "safe_to_submit": False,
        "requires_prompt_api_export": not using_prompt_export,
        "prompt_api_export_path": export_path,
        "prompt_api_export_validation_status": export_validation,
        "ui_adapter_unresolved_roles": ui_unresolved,
        "prompt_api_export_unresolved_roles": export_unresolved,
        "next_step": (
            "Use the validated Prompt API export in the safe submission route."
            if using_prompt_export
            else "Export the LTX workflow from ComfyUI using Save (API Format), then rerun this adapter with prompt_api_export_path."
        ),
    }

    diagnostics = {
        "checked_at": _utc_now_iso(),
        "workflow_load_status": workflow_status,
        "workflow_path_exists": bool(workflow_path and Path(workflow_path).exists()),
        "workflow_format": graph.get("workflow_format"),
        "node_count": graph.get("node_count"),
        "link_count": graph.get("link_count"),
        "prompt_api_candidate": graph.get("prompt_api_candidate"),
        "graph_normalization_ready": graph.get("normalization_ready"),
        "adapter_role_count": len(adapter_map),
        "adapter_unresolved_count": len(ui_unresolved),
        "prompt_api_export_path": export_path,
        "prompt_api_export_exists": bool(export_path and Path(export_path).exists()),
        "prompt_api_export_load_status": export_status,
        "prompt_api_export_is_prompt_api": export_is_prompt_api,
        "prompt_api_export_unresolved_roles": export_unresolved,
        "requested_submit": bool(req.get("submit") or req.get("execute") or req.get("submit_to_comfy")),
        "comfy_running": bool((graph.get("diagnostics") or {}).get("comfy_running", False)),
        "comfy_healthy": bool((graph.get("diagnostics") or {}).get("comfy_healthy", False)),
        "comfy_endpoint_alive": bool((graph.get("diagnostics") or {}).get("comfy_endpoint_alive", False)),
    }

    notes = [
        "This pass creates the LTX Prompt API conversion adapter only; it does not submit to ComfyUI.",
        "The selected LTX workflow is a Comfy UI graph, so a real Prompt API export is still required for safe submission.",
        "When a Prompt API export path is provided, this adapter previews safe input mutations without queueing a render.",
    ]
    if using_prompt_export:
        notes.append("A Prompt API export was detected and preview mutations were built.")
    else:
        notes.append("Run ComfyUI Save (API Format) for this workflow and pass prompt_api_export_path to continue.")

    return LtxPromptApiAdapterSnapshot(
        readiness=str(graph.get("readiness") or "unknown"),
        ready_to_test=bool(graph.get("ready_to_test", False)),
        gate_passed=bool(graph.get("gate_passed", False)),
        generation_enabled=bool(graph.get("generation_enabled", False)),
        submitted=False,
        submission_status=submission_status,
        execution_mode="adapter_preview",
        workflow_name=str(graph.get("workflow_name") or ""),
        workflow_path=workflow_path,
        workflow_exists=bool(graph.get("workflow_exists", False)),
        workflow_load_ok=bool(graph.get("workflow_load_ok", False)),
        workflow_format=str(graph.get("workflow_format") or "unknown"),
        node_count=int(graph.get("node_count") or 0),
        link_count=int(graph.get("link_count") or 0),
        prompt_api_candidate=bool(graph.get("prompt_api_candidate", False)),
        prompt_api_validation_status=str(graph.get("prompt_api_validation_status") or "unknown"),
        normalization_ready=normalization_ready,
        adapter_ready=adapter_ready,
        adapter_status=adapter_status,
        safe_to_submit=False,
        prompt_api_export_path=export_path,
        prompt_api_export_exists=bool(export_path and Path(export_path).exists()),
        prompt_api_export_load_ok=export_status == "loaded",
        prompt_api_export_validation_status=export_validation,
        conversion_required=not using_prompt_export,
        adapter_role_map=adapter_map,
        adapter_mutation_preview=export_mutations if using_prompt_export else ui_preview,
        unresolved_roles=export_unresolved if using_prompt_export else ui_unresolved,
        blocked_submit_reasons=blocked_submit_reasons,
        prompt_api_preview=prompt_preview if using_prompt_export else {},
        conversion_plan=conversion_plan,
        graph_inspection=graph,
        diagnostics=diagnostics,
        notes=notes,
    ).to_payload()
