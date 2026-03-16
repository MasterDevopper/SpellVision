from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

try:
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None


BUILTIN_COMFY_CLASS_NAMES = {
    "CheckpointLoaderSimple",
    "CheckpointLoader",
    "VAELoader",
    "CLIPLoader",
    "LoraLoader",
    "LoadImage",
    "LoadImageMask",
    "LoadVideo",
    "EmptyLatentImage",
    "KSampler",
    "KSamplerAdvanced",
    "SamplerCustom",
    "CLIPTextEncode",
    "ConditioningCombine",
    "ConditioningSetArea",
    "VAEDecode",
    "VAEEncode",
    "SaveImage",
    "SaveAnimatedWEBP",
    "SaveWEBM",
    "ImageScale",
    "ImageUpscaleWithModel",
    "ControlNetLoader",
    "ControlNetApply",
    "ControlNetApplyAdvanced",
    "LoadAudio",
}

VIDEO_CLASS_HINTS = (
    "video",
    "wan",
    "ltx",
    "hunyuan",
    "cogvideo",
    "mochi",
    "animated",
    "webm",
    "frame",
)

IMAGE_TO_VIDEO_HINTS = (
    "image",
    "start_image",
    "init_image",
    "input_image",
)

VIDEO_TO_VIDEO_HINTS = (
    "video",
    "input_video",
    "source_video",
)

MODEL_FIELD_MAP = {
    "checkpoint": {"ckpt_name", "checkpoint", "model", "model_name"},
    "unet": {"unet_name"},
    "vae": {"vae_name", "vae"},
    "lora": {"lora_name", "lora"},
    "controlnet": {"control_net_name", "controlnet"},
    "clip": {"clip_name"},
    "repo_id": {"repo_id"},
}

CANONICAL_SLOT_ALIASES = {
    "prompt": {"text", "prompt", "positive", "positive_prompt"},
    "negative_prompt": {"negative", "negative_prompt", "negative_text"},
    "seed": {"seed", "noise_seed"},
    "steps": {"steps", "num_steps"},
    "cfg": {"cfg", "cfg_scale", "guidance", "guidance_scale"},
    "sampler": {"sampler", "sampler_name"},
    "scheduler": {"scheduler"},
    "width": {"width"},
    "height": {"height"},
    "fps": {"fps", "frame_rate"},
    "num_frames": {"frames", "num_frames", "length"},
    "input_image": {"image", "input_image", "image_path"},
    "input_video": {"video", "input_video", "video_path"},
    "checkpoint": {"ckpt_name", "checkpoint", "model_name"},
    "vae": {"vae_name"},
    "loras": {"lora", "lora_name", "lora_stack"},
    "output_prefix": {"filename_prefix", "output_path"},
}


@dataclass
class WorkflowSource:
    source_kind: str
    source_path: str | None = None
    display_name: str | None = None
    raw_text: str | None = None


@dataclass
class WorkflowNodeInfo:
    node_id: str
    class_type: str
    title: str | None = None
    input_names: list[str] = field(default_factory=list)
    widget_names: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelReference:
    kind: str
    value: str
    node_id: str
    input_name: str


@dataclass
class SlotCandidate:
    slot: str
    node_id: str
    input_name: str
    path: str
    confidence: float
    reason: str


@dataclass
class ScanIssue:
    level: str
    code: str
    message: str


@dataclass
class WorkflowScanReport:
    report_id: str
    source: WorkflowSource
    graph_format: str
    node_count: int
    nodes: list[WorkflowNodeInfo]
    model_references: list[ModelReference] = field(default_factory=list)
    missing_custom_nodes: list[str] = field(default_factory=list)
    inferred_task_command: str = "unknown"
    inferred_media_type: str = "unknown"
    inferred_model_family_hints: list[str] = field(default_factory=list)
    slot_candidates: list[SlotCandidate] = field(default_factory=list)
    warnings: list[ScanIssue] = field(default_factory=list)
    errors: list[ScanIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_workflow_source(source: str | Path | dict[str, Any], source_kind: str | None = None) -> tuple[WorkflowSource, dict[str, Any]]:
    if isinstance(source, dict):
        ws = WorkflowSource(source_kind=source_kind or "dict", display_name="in-memory workflow")
        return ws, source

    if isinstance(source, Path):
        source = str(source)

    if isinstance(source, str):
        stripped = source.strip()
        if stripped.startswith("{"):
            payload = json.loads(stripped)
            ws = WorkflowSource(source_kind=source_kind or "json_text", display_name="inline json", raw_text=stripped)
            return ws, payload

        path = Path(source)
        if path.exists():
            suffix = path.suffix.lower()
            if suffix == ".json":
                payload = json.loads(path.read_text(encoding="utf-8"))
                ws = WorkflowSource(source_kind=source_kind or "json_file", source_path=str(path), display_name=path.name)
                return ws, payload
            if suffix in {".png", ".webp"}:
                payload = _extract_embedded_workflow(path)
                ws = WorkflowSource(source_kind=source_kind or "image_metadata", source_path=str(path), display_name=path.name)
                return ws, payload

    raise ValueError("Unsupported workflow source. Expected dict, JSON text, .json, .png, or .webp")


def scan_workflow(source: str | Path | dict[str, Any], source_kind: str | None = None) -> WorkflowScanReport:
    workflow_source, payload = load_workflow_source(source, source_kind=source_kind)
    graph_format, nodes = _extract_nodes(payload)

    report = WorkflowScanReport(
        report_id=str(uuid4()),
        source=workflow_source,
        graph_format=graph_format,
        node_count=len(nodes),
        nodes=nodes,
    )

    report.model_references.extend(_extract_model_references(nodes))
    report.missing_custom_nodes.extend(_detect_custom_nodes(nodes))
    report.inferred_task_command, report.inferred_media_type = _infer_task_type(nodes)
    report.inferred_model_family_hints.extend(_infer_model_family_hints(report.model_references, nodes))
    report.slot_candidates.extend(_collect_slot_candidates(nodes))

    if report.node_count == 0:
        report.errors.append(ScanIssue("error", "empty_workflow", "No scanable nodes were found in the workflow payload"))

    if report.inferred_task_command == "unknown":
        report.warnings.append(ScanIssue("warning", "unknown_task", "Task type could not be confidently inferred"))

    if report.missing_custom_nodes:
        report.warnings.append(
            ScanIssue(
                "warning",
                "custom_nodes_detected",
                f"Detected likely custom node classes: {', '.join(sorted(report.missing_custom_nodes))}",
            )
        )

    return report


def save_scan_report(report: WorkflowScanReport, path: str | Path) -> str:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return str(out_path)


def _extract_embedded_workflow(path: Path) -> dict[str, Any]:
    if Image is None:
        raise ValueError("Pillow is required to extract workflows from PNG/WebP metadata")

    with Image.open(path) as img:
        info = dict(getattr(img, "info", {}) or {})
        candidate_values: list[str] = []

        for key in ("workflow", "prompt", "comfy_workflow", "parameters", "comment", "Description"):
            value = info.get(key)
            if isinstance(value, bytes):
                try:
                    value = value.decode("utf-8", errors="ignore")
                except Exception:
                    value = None
            if isinstance(value, str) and "{" in value:
                candidate_values.append(value)

        exif = info.get("exif")
        if isinstance(exif, bytes):
            decoded = exif.decode("utf-8", errors="ignore")
            if "{" in decoded:
                candidate_values.append(decoded)

        for value in candidate_values:
            payload = _try_extract_json_object(value)
            if isinstance(payload, dict):
                return payload

    raise ValueError(f"No readable embedded Comfy-style workflow JSON was found in {path}")


def _try_extract_json_object(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if not text:
        return None

    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass

    first = text.find("{")
    last = text.rfind("}")
    if first == -1 or last == -1 or last <= first:
        return None

    try:
        payload = json.loads(text[first:last + 1])
        if isinstance(payload, dict):
            return payload
    except Exception:
        return None
    return None


def _extract_nodes(payload: dict[str, Any]) -> tuple[str, list[WorkflowNodeInfo]]:
    if _looks_like_api_prompt(payload):
        return "comfy_api_prompt", _extract_api_prompt_nodes(payload)
    if _looks_like_ui_graph(payload):
        return "comfy_ui_graph", _extract_ui_graph_nodes(payload)
    return "unknown", []


def _looks_like_api_prompt(payload: dict[str, Any]) -> bool:
    if not isinstance(payload, dict) or not payload:
        return False
    for key, value in payload.items():
        if not isinstance(value, dict):
            return False
        if "class_type" not in value and "inputs" not in value:
            return False
    return True


def _looks_like_ui_graph(payload: dict[str, Any]) -> bool:
    return isinstance(payload, dict) and isinstance(payload.get("nodes"), list)


def _extract_api_prompt_nodes(payload: dict[str, Any]) -> list[WorkflowNodeInfo]:
    nodes: list[WorkflowNodeInfo] = []
    for node_id, node in payload.items():
        class_type = str(node.get("class_type") or node.get("type") or "Unknown")
        inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
        nodes.append(
            WorkflowNodeInfo(
                node_id=str(node_id),
                class_type=class_type,
                title=str(node.get("_meta", {}).get("title")) if isinstance(node.get("_meta"), dict) else None,
                input_names=list(inputs.keys()),
                widget_names=[],
                raw=node,
            )
        )
    return nodes


def _extract_ui_graph_nodes(payload: dict[str, Any]) -> list[WorkflowNodeInfo]:
    nodes: list[WorkflowNodeInfo] = []
    for node in payload.get("nodes", []):
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or node.get("index") or len(nodes))
        class_type = str(node.get("type") or node.get("class_type") or "Unknown")
        widget_names = []
        widgets = node.get("widgets_values")
        if isinstance(widgets, list):
            widget_names = [f"widget_{idx}" for idx, _ in enumerate(widgets)]
        nodes.append(
            WorkflowNodeInfo(
                node_id=node_id,
                class_type=class_type,
                title=str(node.get("title")) if node.get("title") is not None else None,
                input_names=[str(inp.get("name")) for inp in node.get("inputs", []) if isinstance(inp, dict) and inp.get("name")],
                widget_names=widget_names,
                raw=node,
            )
        )
    return nodes


def _extract_model_references(nodes: list[WorkflowNodeInfo]) -> list[ModelReference]:
    refs: list[ModelReference] = []
    for node in nodes:
        inputs = node.raw.get("inputs") if isinstance(node.raw.get("inputs"), dict) else {}
        for kind, keys in MODEL_FIELD_MAP.items():
            for key in keys:
                value = inputs.get(key)
                if isinstance(value, str) and value.strip():
                    refs.append(ModelReference(kind=kind, value=value.strip(), node_id=node.node_id, input_name=key))
    return refs


def _detect_custom_nodes(nodes: list[WorkflowNodeInfo]) -> list[str]:
    detected: list[str] = []
    for node in nodes:
        class_type = node.class_type.strip()
        if not class_type:
            continue
        if class_type in BUILTIN_COMFY_CLASS_NAMES:
            continue
        if class_type.startswith("SV_"):
            continue
        detected.append(class_type)
    return sorted(set(detected))


def _infer_task_type(nodes: list[WorkflowNodeInfo]) -> tuple[str, str]:
    class_text = " ".join(node.class_type.lower() for node in nodes)
    input_names = {name.lower() for node in nodes for name in node.input_names}

    has_video = any(hint in class_text for hint in VIDEO_CLASS_HINTS) or "fps" in input_names or "num_frames" in input_names or "frames" in input_names
    has_input_image = any(name in input_names for name in IMAGE_TO_VIDEO_HINTS)
    has_input_video = any(name in input_names for name in VIDEO_TO_VIDEO_HINTS)
    has_save_image = "saveimage" in class_text
    has_save_video = "saveanimatedwebp" in class_text or "savewebm" in class_text or "video" in class_text

    if has_video and has_input_video:
        return "v2v", "video"
    if has_video and has_input_image:
        return "i2v", "video"
    if has_video:
        return "t2v", "video"
    if has_input_image and has_save_image:
        return "i2i", "image"
    if has_save_image or "ksampler" in class_text:
        return "t2i", "image"
    return "unknown", "unknown"


def _infer_model_family_hints(model_refs: list[ModelReference], nodes: list[WorkflowNodeInfo]) -> list[str]:
    hints_text = " ".join(
        [ref.value for ref in model_refs] +
        [node.class_type for node in nodes] +
        [name for node in nodes for name in node.input_names]
    ).lower()

    families = []
    for family, markers in {
        "wan": ("wan",),
        "ltx": ("ltx",),
        "hunyuan_video": ("hunyuan", "hunyuanvideo"),
        "cogvideox": ("cogvideo", "cogvideox"),
        "mochi": ("mochi",),
        "sdxl": ("sdxl",),
        "flux": ("flux",),
    }.items():
        if any(marker in hints_text for marker in markers):
            families.append(family)
    return families


def _collect_slot_candidates(nodes: list[WorkflowNodeInfo]) -> list[SlotCandidate]:
    candidates: list[SlotCandidate] = []

    for node in nodes:
        inputs = node.raw.get("inputs") if isinstance(node.raw.get("inputs"), dict) else {}
        for slot, aliases in CANONICAL_SLOT_ALIASES.items():
            for input_name in inputs.keys():
                norm = str(input_name).strip().lower()
                if norm in aliases:
                    confidence = 0.92
                    reason = "exact input alias match"
                    if slot in {"prompt", "negative_prompt"} and "text" in node.class_type.lower():
                        confidence = 0.98
                        reason = "text encoder input alias match"
                    elif slot in {"checkpoint", "vae", "loras"} and "loader" in node.class_type.lower():
                        confidence = 0.97
                        reason = "loader node input alias match"

                    candidates.append(
                        SlotCandidate(
                            slot=slot,
                            node_id=node.node_id,
                            input_name=input_name,
                            path=f"{node.node_id}.inputs.{input_name}",
                            confidence=confidence,
                            reason=reason,
                        )
                    )
    candidates.sort(key=lambda item: (item.slot, -item.confidence, item.node_id))
    return candidates
