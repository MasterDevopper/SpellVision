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
class WorkflowCapabilityEvidence:
    code: str
    label: str
    score: float = 0.0
    node_ids: list[str] = field(default_factory=list)


@dataclass
class WorkflowCapabilityReport:
    primary_task: str = "unknown"
    media_type: str = "unknown"
    supported_modes: list[str] = field(default_factory=list)
    required_inputs: list[str] = field(default_factory=list)
    optional_inputs: list[str] = field(default_factory=list)
    output_kinds: list[str] = field(default_factory=list)
    confidence: float = 0.0
    evidence: list[WorkflowCapabilityEvidence] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    classification_version: str = "workflow-capability-v1"


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
    capability_report: WorkflowCapabilityReport = field(default_factory=WorkflowCapabilityReport)
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
    report.capability_report = _classify_workflow_capabilities(nodes, report.model_references)
    report.inferred_task_command = report.capability_report.primary_task
    report.inferred_media_type = report.capability_report.media_type
    report.inferred_model_family_hints.extend(_infer_model_family_hints(report.model_references, nodes))
    report.slot_candidates.extend(_collect_slot_candidates(nodes))

    if report.node_count == 0:
        report.errors.append(ScanIssue("error", "empty_workflow", "No scanable nodes were found in the workflow payload"))

    if report.inferred_task_command == "unknown":
        report.warnings.append(ScanIssue("warning", "unknown_task", "Task type could not be confidently inferred"))

    if report.capability_report.confidence < 0.55:
        report.warnings.append(
            ScanIssue(
                "warning",
                "low_capability_confidence",
                f"Workflow capability classification confidence is low ({report.capability_report.confidence:.2f}). Review or override before production use.",
            )
        )

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


def _node_text(node: WorkflowNodeInfo) -> str:
    parts = [node.class_type, node.title or "", *node.input_names, *node.widget_names]
    inputs = node.raw.get("inputs") if isinstance(node.raw.get("inputs"), dict) else {}
    for key, value in inputs.items():
        parts.append(str(key))
        if isinstance(value, str):
            parts.append(value)
    return " ".join(part for part in parts if part).lower()


def _node_has_any(node: WorkflowNodeInfo, markers: tuple[str, ...] | set[str]) -> bool:
    text = _node_text(node)
    return any(marker.lower() in text for marker in markers)


def _node_ids(nodes: list[WorkflowNodeInfo], predicate: Any) -> list[str]:
    out: list[str] = []
    for node in nodes:
        try:
            if predicate(node):
                out.append(node.node_id)
        except Exception:
            continue
    return out


def _add_evidence(
    evidence: list[WorkflowCapabilityEvidence],
    *,
    code: str,
    label: str,
    score: float,
    node_ids: list[str] | None = None,
) -> None:
    if not node_ids:
        return
    evidence.append(
        WorkflowCapabilityEvidence(
            code=code,
            label=label,
            score=float(score),
            node_ids=sorted(set(node_ids)),
        )
    )


def _classify_workflow_capabilities(
    nodes: list[WorkflowNodeInfo],
    model_refs: list[ModelReference] | None = None,
) -> WorkflowCapabilityReport:
    """Infer workflow capability from graph evidence, not filenames."""

    model_refs = model_refs or []
    if not nodes:
        return WorkflowCapabilityReport(
            primary_task="unknown",
            media_type="unknown",
            confidence=0.0,
            warnings=["No nodes were available for capability classification."],
        )

    evidence: list[WorkflowCapabilityEvidence] = []
    warnings_out: list[str] = []

    text_node_ids = _node_ids(
        nodes,
        lambda node: (
            "cliptextencode" in node.class_type.lower()
            or "textencode" in node.class_type.lower()
            or any(name.lower() in {"text", "prompt", "positive", "positive_prompt", "negative", "negative_prompt"} for name in node.input_names)
        ),
    )
    image_source_ids = _node_ids(
        nodes,
        lambda node: (
            "loadimage" in node.class_type.lower()
            or "image loader" in _node_text(node)
            or ("clipvision" in node.class_type.lower() and any("image" in name.lower() for name in node.input_names))
        ),
    )
    video_source_ids = _node_ids(
        nodes,
        lambda node: (
            "loadvideo" in node.class_type.lower()
            or "videoload" in node.class_type.lower()
            or "vhs_loadvideo" in node.class_type.lower()
            or ("loader" in node.class_type.lower() and "video" in _node_text(node))
        ),
    )
    audio_source_ids = _node_ids(
        nodes,
        lambda node: "loadaudio" in node.class_type.lower() or ("loader" in node.class_type.lower() and "audio" in _node_text(node)),
    )

    video_core_ids = _node_ids(
        nodes,
        lambda node: _node_has_any(
            node,
            {
                "wan", "ltx", "hunyuan", "hunyuanvideo", "cogvideo", "cogvideox", "mochi",
                "animatediff", "svd", "stablevideodiffusion", "video latent", "latentvideo",
                "emptylatentvideo", "emptyhunyuanlatentvideo", "modelsampling3d", "createvideo",
                "videoksampler", "frames", "num_frames", "frame_rate", "fps",
            },
        ),
    )
    video_output_ids = _node_ids(
        nodes,
        lambda node: _node_has_any(
            node,
            {
                "savewebm", "saveanimatedwebp", "savevideo", "videocombine", "createvideo",
                "vhs_videocombine", "animatedwebp", "webm", "mp4", "gif",
            },
        ),
    )
    image_output_ids = _node_ids(
        nodes,
        lambda node: "saveimage" in node.class_type.lower() or "previewimage" in node.class_type.lower(),
    )
    audio_output_ids = _node_ids(
        nodes,
        lambda node: "saveaudio" in node.class_type.lower() or ("audio" in node.class_type.lower() and "save" in node.class_type.lower()),
    )

    _add_evidence(evidence, code="text_conditioning", label="Text conditioning/prompt inputs detected", score=0.18, node_ids=text_node_ids)
    _add_evidence(evidence, code="image_source", label="Source image loader/input detected", score=0.30, node_ids=image_source_ids)
    _add_evidence(evidence, code="video_source", label="Source video loader/input detected", score=0.34, node_ids=video_source_ids)
    _add_evidence(evidence, code="audio_source", label="Source audio loader/input detected", score=0.20, node_ids=audio_source_ids)
    _add_evidence(evidence, code="video_generation_core", label="Video generation / video latent nodes detected", score=0.32, node_ids=video_core_ids)
    _add_evidence(evidence, code="video_output", label="Video or animated output node detected", score=0.34, node_ids=video_output_ids)
    _add_evidence(evidence, code="image_output", label="Image output node detected", score=0.26, node_ids=image_output_ids)
    _add_evidence(evidence, code="audio_output", label="Audio output node detected", score=0.24, node_ids=audio_output_ids)

    has_text = bool(text_node_ids)
    has_image_source = bool(image_source_ids)
    has_video_source = bool(video_source_ids)
    has_video_core = bool(video_core_ids)
    has_video_output = bool(video_output_ids)
    has_image_output = bool(image_output_ids)
    has_audio_output = bool(audio_output_ids)

    output_kinds: list[str] = []
    if has_video_output or has_video_core:
        output_kinds.append("video")
    if any("webp" in _node_text(node) or "gif" in _node_text(node) for node in nodes if node.node_id in video_output_ids):
        output_kinds.append("gif")
    if has_image_output:
        output_kinds.append("image")
    if has_audio_output:
        output_kinds.append("audio")
    output_kinds = sorted(set(output_kinds))

    required_inputs: list[str] = []
    optional_inputs: list[str] = []
    if has_text:
        required_inputs.append("positive_prompt")
        optional_inputs.append("negative_prompt")
    if has_image_source:
        required_inputs.append("source_image")
    if has_video_source:
        required_inputs.append("source_video")
    if audio_source_ids:
        required_inputs.append("source_audio")

    all_input_names = {name.lower() for node in nodes for name in node.input_names}
    for slot, markers in {
        "seed": {"seed", "noise_seed"},
        "steps": {"steps", "num_steps", "num_inference_steps"},
        "cfg": {"cfg", "cfg_scale", "guidance", "guidance_scale", "embedded_guidance_scale"},
        "width": {"width"},
        "height": {"height"},
        "frames": {"frames", "num_frames", "frame_count", "length", "video_frames", "total_frames"},
        "fps": {"fps", "frame_rate"},
        "motion_strength": {"motion", "motion_strength", "movement_strength", "motion_bucket_id", "noise_aug_strength"},
        "checkpoint": {"ckpt_name", "checkpoint", "model", "model_name", "unet_name", "repo_id"},
        "lora": {"lora", "lora_name", "lora_stack"},
    }.items():
        if all_input_names.intersection(markers) and slot not in required_inputs:
            optional_inputs.append(slot)

    primary_task = "unknown"
    media_type = "unknown"
    supported_modes: list[str] = []

    if has_video_output or has_video_core:
        media_type = "video"
        if has_video_source:
            primary_task = "v2v"
            supported_modes = ["v2v"]
        elif has_image_source:
            primary_task = "i2v"
            supported_modes = ["i2v"]
            if has_text:
                supported_modes.append("t2v")
                warnings_out.append("Image input was detected, but the graph also contains text conditioning; review whether the image source is required or optional.")
        else:
            primary_task = "t2v"
            supported_modes = ["t2v"]
    elif has_image_output:
        media_type = "image"
        if has_image_source:
            primary_task = "i2i"
            supported_modes = ["i2i"]
        else:
            primary_task = "t2i"
            supported_modes = ["t2i"]
    elif has_audio_output or audio_source_ids:
        media_type = "audio"
        primary_task = "audio"
        supported_modes = ["audio"]

    if has_video_source and has_image_source:
        warnings_out.append("Both image and video source inputs were detected; workflow may support multiple video modes or require manual classification.")
    if media_type == "video" and not has_text:
        warnings_out.append("Video workflow has no obvious text conditioning node; it may be control/video driven or use embedded prompts.")

    raw_confidence = sum(item.score for item in evidence)
    if primary_task != "unknown":
        raw_confidence += 0.18
    if media_type != "unknown":
        raw_confidence += 0.12
    if primary_task in {"t2v", "i2v", "v2v"} and (has_video_output or has_video_core):
        raw_confidence += 0.18
    if primary_task in {"t2i", "i2i"} and has_image_output:
        raw_confidence += 0.16
    if primary_task == "t2v" and has_image_source:
        raw_confidence -= 0.25
    if primary_task == "i2v" and not has_image_source:
        raw_confidence -= 0.25
    if primary_task == "v2v" and not has_video_source:
        raw_confidence -= 0.25

    confidence = max(0.0, min(0.99, round(raw_confidence, 2)))
    if primary_task == "unknown":
        confidence = min(confidence, 0.35)

    return WorkflowCapabilityReport(
        primary_task=primary_task,
        media_type=media_type,
        supported_modes=sorted(set(supported_modes)),
        required_inputs=sorted(set(required_inputs)),
        optional_inputs=sorted(set(optional_inputs)),
        output_kinds=sorted(set(output_kinds)),
        confidence=confidence,
        evidence=evidence,
        warnings=warnings_out,
    )


def _infer_task_type(nodes: list[WorkflowNodeInfo]) -> tuple[str, str]:
    capability = _classify_workflow_capabilities(nodes, [])
    return capability.primary_task, capability.media_type


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
