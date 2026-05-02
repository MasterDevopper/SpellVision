from __future__ import annotations

import json
import re
from collections import Counter
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ltx_smoke_test_route import ltx_t2v_smoke_test_snapshot


ROLE_ALIASES: dict[str, tuple[str, ...]] = {
    "prompt": ("prompt", "positive", "text", "caption"),
    "negative_prompt": ("negative", "negative_prompt", "uncond"),
    "seed": ("seed", "noise_seed"),
    "steps": ("steps", "num_steps"),
    "cfg": ("cfg", "guidance", "guidance_scale"),
    "sampler": ("sampler", "sampler_name"),
    "scheduler": ("scheduler", "scheduler_name"),
    "width": ("width", "w"),
    "height": ("height", "h"),
    "frames": ("frames", "frame", "length", "num_frames", "video_length"),
    "fps": ("fps", "frame_rate"),
    "model": ("model", "ckpt", "unet", "diffusion", "checkpoint"),
    "vae": ("vae", "video_vae"),
    "text_encoder": ("text_encoder", "clip", "gemma"),
    "text_projection": ("projection", "text_projection"),
}

SUBMISSION_ROLES = ("prompt", "seed", "steps", "cfg", "sampler", "scheduler", "width", "height", "frames", "fps")
ASSET_ROLES = ("model", "vae", "text_encoder", "text_projection")


@dataclass(frozen=True)
class LtxWorkflowGraphInspection:
    type: str = "ltx_workflow_graph_inspection"
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
    execution_mode: str = "graph_inspection"
    workflow_name: str = ""
    workflow_path: str = ""
    workflow_exists: bool = False
    workflow_load_ok: bool = False
    workflow_format: str = "unknown"
    node_count: int = 0
    link_count: int = 0
    prompt_api_candidate: bool = False
    prompt_api_validation_status: str = "unknown"
    normalization_status: str = "unknown"
    normalization_ready: bool = False
    role_coverage: dict[str, Any] = field(default_factory=dict)
    node_type_counts: dict[str, int] = field(default_factory=dict)
    graph_nodes: list[dict[str, Any]] = field(default_factory=list)
    role_candidates: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    prompt_api_preview: dict[str, Any] = field(default_factory=dict)
    conversion_plan: dict[str, Any] = field(default_factory=dict)
    smoke_request: dict[str, Any] = field(default_factory=dict)
    request_metadata: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    route: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: str) -> tuple[bool, Any, str]:
    try:
        text = Path(path).read_text(encoding="utf-8")
        return True, json.loads(text), "loaded"
    except UnicodeDecodeError:
        try:
            text = Path(path).read_text(encoding="utf-8-sig")
            return True, json.loads(text), "loaded_utf8_sig"
        except Exception as exc:
            return False, None, f"load_failed: {exc}"
    except Exception as exc:
        return False, None, f"load_failed: {exc}"


def _node_class(node: Any) -> str:
    if isinstance(node, dict):
        return str(node.get("class_type") or node.get("type") or node.get("name") or "unknown")
    return "unknown"


def _node_id(node: Any, fallback: str) -> str:
    if isinstance(node, dict):
        return str(node.get("id") or node.get("node_id") or fallback)
    return fallback


def _detect_workflow_format(workflow: Any) -> str:
    if isinstance(workflow, dict) and isinstance(workflow.get("nodes"), list):
        return "comfy_ui_graph"
    if isinstance(workflow, dict):
        values = list(workflow.values())
        if values and all(isinstance(value, dict) and "class_type" in value and "inputs" in value for value in values):
            return "prompt_api_graph"
    return "unknown"


def _workflow_nodes(workflow: Any, workflow_format: str) -> list[dict[str, Any]]:
    if workflow_format == "comfy_ui_graph" and isinstance(workflow, dict):
        result: list[dict[str, Any]] = []
        for index, node in enumerate(workflow.get("nodes") or []):
            if not isinstance(node, dict):
                continue
            result.append(node)
        return result
    if workflow_format == "prompt_api_graph" and isinstance(workflow, dict):
        result = []
        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                continue
            cloned = dict(node)
            cloned.setdefault("id", node_id)
            result.append(cloned)
        return result
    return []


def _link_count(workflow: Any, workflow_format: str) -> int:
    if workflow_format == "comfy_ui_graph" and isinstance(workflow, dict):
        links = workflow.get("links") or []
        return len(links) if isinstance(links, list) else 0
    if workflow_format == "prompt_api_graph":
        count = 0
        for node in workflow.values() if isinstance(workflow, dict) else []:
            inputs = node.get("inputs") if isinstance(node, dict) else {}
            if not isinstance(inputs, dict):
                continue
            for value in inputs.values():
                if isinstance(value, list) and len(value) >= 2:
                    count += 1
        return count
    return 0


def _compact_value(value: Any, *, limit: int = 120) -> Any:
    if isinstance(value, str):
        return value if len(value) <= limit else value[: limit - 3] + "..."
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_compact_value(item, limit=limit) for item in value[:8]]
    if isinstance(value, dict):
        return {str(key): _compact_value(val, limit=limit) for key, val in list(value.items())[:8]}
    return str(value)[:limit]


def _text_matches_role(text: str, role: str) -> bool:
    lower = text.lower()
    return any(alias in lower for alias in ROLE_ALIASES.get(role, (role,)))


def _candidate_score(node_class: str, key: str, value: Any, role: str) -> int:
    haystack = f"{node_class} {key}".lower()
    score = 0
    if _text_matches_role(haystack, role):
        score += 3
    if isinstance(value, str) and role in {"prompt", "negative_prompt"} and len(value.strip()) >= 8:
        score += 2
    if role == "seed" and isinstance(value, int) and value > 1000:
        score += 2
    if role in {"steps", "width", "height", "frames", "fps"} and isinstance(value, int):
        score += 1
    if role == "cfg" and isinstance(value, (int, float)):
        score += 1
    return score


def _iter_node_values(node: dict[str, Any], workflow_format: str) -> list[tuple[str, Any, str]]:
    values: list[tuple[str, Any, str]] = []
    inputs = node.get("inputs")
    if isinstance(inputs, dict):
        for key, value in inputs.items():
            values.append((str(key), value, "inputs"))
    # Comfy UI graph exports often carry values in widgets_values without names.
    widgets = node.get("widgets_values")
    if isinstance(widgets, list):
        for index, value in enumerate(widgets):
            values.append((f"widgets_values[{index}]", value, "widgets_values"))
    properties = node.get("properties")
    if isinstance(properties, dict):
        for key, value in properties.items():
            values.append((str(key), value, "properties"))
    return values


def _find_role_candidates(nodes: list[dict[str, Any]], workflow_format: str) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {role: [] for role in (*SUBMISSION_ROLES, *ASSET_ROLES, "negative_prompt")}
    for index, node in enumerate(nodes):
        node_id = _node_id(node, str(index))
        node_class = _node_class(node)
        for key, value, source in _iter_node_values(node, workflow_format):
            for role in result.keys():
                score = _candidate_score(node_class, key, value, role)
                if score <= 0:
                    continue
                result[role].append({
                    "role": role,
                    "node_id": node_id,
                    "class_type": node_class,
                    "input_key": key,
                    "source": source,
                    "score": score,
                    "value_preview": _compact_value(value),
                    "safe_to_mutate": bool(workflow_format == "prompt_api_graph" and source == "inputs"),
                })
    for role, candidates in result.items():
        candidates.sort(key=lambda item: (-int(item.get("score", 0)), str(item.get("node_id", ""))))
        result[role] = candidates[:12]
    return result


def _node_summaries(nodes: list[dict[str, Any]], workflow_format: str, *, max_nodes: int = 80) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for index, node in enumerate(nodes[:max_nodes]):
        inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
        widgets = node.get("widgets_values") if isinstance(node.get("widgets_values"), list) else []
        summaries.append({
            "node_id": _node_id(node, str(index)),
            "class_type": _node_class(node),
            "title": node.get("title") if isinstance(node.get("title"), str) else "",
            "input_keys": sorted([str(key) for key in inputs.keys()])[:30],
            "widget_count": len(widgets),
            "widget_preview": [_compact_value(value, limit=80) for value in widgets[:8]],
        })
    return summaries


def _prompt_api_validation(workflow: Any, workflow_format: str, role_candidates: dict[str, list[dict[str, Any]]]) -> tuple[bool, str]:
    if workflow_format != "prompt_api_graph":
        return False, "not_prompt_api_graph_or_unknown"
    missing = [role for role in ("prompt", "seed", "steps") if not role_candidates.get(role)]
    if missing:
        return False, "prompt_api_missing_mutation_roles:" + ",".join(missing)
    return True, "prompt_api_candidate"


def _build_prompt_api_preview(workflow: Any, workflow_format: str, role_candidates: dict[str, list[dict[str, Any]]], smoke_request: dict[str, Any]) -> tuple[dict[str, Any], int]:
    if workflow_format != "prompt_api_graph" or not isinstance(workflow, dict):
        return {}, 0
    materialized = deepcopy(workflow)
    applied = 0
    role_to_value = {
        "prompt": smoke_request.get("prompt"),
        "negative_prompt": smoke_request.get("negative_prompt"),
        "seed": smoke_request.get("seed"),
        "steps": smoke_request.get("steps"),
        "cfg": smoke_request.get("cfg"),
        "sampler": smoke_request.get("sampler"),
        "scheduler": smoke_request.get("scheduler"),
        "width": smoke_request.get("width"),
        "height": smoke_request.get("height"),
        "frames": smoke_request.get("frames"),
        "fps": smoke_request.get("fps"),
    }
    for role, value in role_to_value.items():
        candidates = [item for item in role_candidates.get(role, []) if item.get("safe_to_mutate")]
        if not candidates:
            continue
        item = candidates[0]
        node_id = str(item.get("node_id"))
        input_key = str(item.get("input_key"))
        if node_id in materialized and isinstance(materialized[node_id].get("inputs"), dict):
            materialized[node_id]["inputs"][input_key] = value
            applied += 1
    preview = {str(key): materialized[key] for key in list(materialized.keys())[:12]}
    return preview, applied


def ltx_workflow_graph_inspection_snapshot(req: dict[str, Any] | None = None, runtime_status: dict[str, Any] | None = None) -> dict[str, Any]:
    req = req or {}
    runtime_status = runtime_status or {}
    route = ltx_t2v_smoke_test_snapshot(req, runtime_status=runtime_status)
    workflow_path = str(route.get("workflow_path") or "")
    workflow_exists = bool(workflow_path and Path(workflow_path).exists())
    workflow_load_ok, workflow, workflow_load_status = _load_json(workflow_path) if workflow_exists else (False, None, "missing_workflow")
    workflow_format = _detect_workflow_format(workflow) if workflow_load_ok else "unknown"
    nodes = _workflow_nodes(workflow, workflow_format)
    node_type_counts = dict(sorted(Counter(_node_class(node) for node in nodes).items()))
    role_candidates = _find_role_candidates(nodes, workflow_format)
    prompt_api_candidate, prompt_api_validation_status = _prompt_api_validation(workflow, workflow_format, role_candidates)
    smoke_request = dict(route.get("smoke_request") or {})
    prompt_api_preview, applied_mutation_count = _build_prompt_api_preview(workflow, workflow_format, role_candidates, smoke_request)

    role_coverage = {
        "submission_roles_present": [role for role in SUBMISSION_ROLES if role_candidates.get(role)],
        "submission_roles_missing": [role for role in SUBMISSION_ROLES if not role_candidates.get(role)],
        "asset_roles_present": [role for role in ASSET_ROLES if role_candidates.get(role)],
        "asset_roles_missing": [role for role in ASSET_ROLES if not role_candidates.get(role)],
    }

    if not bool(route.get("gate_passed", False)):
        normalization_status = "blocked_by_ltx_gate"
        submission_status = "blocked_by_gate"
    elif not workflow_load_ok:
        normalization_status = "blocked_workflow_load_failed"
        submission_status = "blocked_workflow_load_failed"
    elif workflow_format == "comfy_ui_graph":
        normalization_status = "ui_graph_inspected_prompt_api_conversion_required"
        submission_status = "dry_run_requires_prompt_api_conversion"
    elif prompt_api_candidate:
        normalization_status = "prompt_api_preview_ready"
        submission_status = "dry_run_prompt_api_preview_ready"
    else:
        normalization_status = "blocked_prompt_api_validation_failed"
        submission_status = "blocked_prompt_api_validation_failed"

    conversion_plan = {
        "source_format": workflow_format,
        "target_format": "prompt_api_graph",
        "safe_to_submit": False,
        "conversion_required": workflow_format == "comfy_ui_graph",
        "next_step": "Export or normalize the UI graph into Prompt API JSON, then rerun dry-run validation." if workflow_format == "comfy_ui_graph" else "Validate prompt API node mappings before enabling submit.",
        "required_submission_roles": list(SUBMISSION_ROLES),
        "missing_submission_roles": role_coverage["submission_roles_missing"],
        "applied_preview_mutations": applied_mutation_count,
    }

    diagnostics = {
        "checked_at": _utc_now_iso(),
        "workflow_load_status": workflow_load_status,
        "workflow_path_exists": workflow_exists,
        "workflow_format": workflow_format,
        "node_count": len(nodes),
        "link_count": _link_count(workflow, workflow_format),
        "prompt_api_candidate": prompt_api_candidate,
        "prompt_api_validation_status": prompt_api_validation_status,
        "normalization_status": normalization_status,
        "requested_submit": bool(req.get("submit") or req.get("execute") or req.get("submit_to_comfy")),
        "comfy_running": bool(route.get("diagnostics", {}).get("comfy_running", False)),
        "comfy_healthy": bool(route.get("diagnostics", {}).get("comfy_healthy", False)),
        "comfy_endpoint_alive": bool(route.get("diagnostics", {}).get("comfy_endpoint_alive", False)),
    }

    notes = [
        "This pass inspects LTX workflow graph structure and builds a Prompt API normalization preview only.",
        "No ComfyUI prompt submission is performed in this pass.",
        "Wan production routing remains untouched.",
    ]
    if workflow_format == "comfy_ui_graph":
        notes.append("The selected workflow is a Comfy UI graph export; it must be converted to Prompt API JSON before safe /prompt submission.")
    if role_coverage["submission_roles_missing"]:
        notes.append("Some submission roles were not found as directly mutable inputs; use graph_nodes and role_candidates to inspect mappings.")

    return LtxWorkflowGraphInspection(
        readiness=str(route.get("readiness") or "unknown"),
        ready_to_test=bool(route.get("ready_to_test", False)),
        gate_passed=bool(route.get("gate_passed", False)),
        generation_enabled=bool(route.get("generation_enabled", False)),
        submitted=False,
        submission_status=submission_status,
        workflow_name=str(route.get("workflow_name") or ""),
        workflow_path=workflow_path,
        workflow_exists=workflow_exists,
        workflow_load_ok=workflow_load_ok,
        workflow_format=workflow_format,
        node_count=len(nodes),
        link_count=_link_count(workflow, workflow_format),
        prompt_api_candidate=prompt_api_candidate,
        prompt_api_validation_status=prompt_api_validation_status,
        normalization_status=normalization_status,
        normalization_ready=prompt_api_candidate,
        role_coverage=role_coverage,
        node_type_counts=node_type_counts,
        graph_nodes=_node_summaries(nodes, workflow_format),
        role_candidates=role_candidates,
        prompt_api_preview=prompt_api_preview,
        conversion_plan=conversion_plan,
        smoke_request=smoke_request,
        request_metadata=dict(route.get("request_metadata") or {}),
        diagnostics=diagnostics,
        route=route,
        notes=notes,
    ).to_payload()
