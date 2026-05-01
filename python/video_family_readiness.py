from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


LTX_REQUIRED_NODE_NAMES = (
    "LTXVGemmaCLIPModelLoader",
    "LTXVAudioVAELoader",
    "LTXVImgToVideo",
    "LtxvApiTextToVideo",
    "LTXVScheduler",
    "LTXVBaseSampler",
)

LTX_BLUEPRINT_NAMES = (
    "Text to Video (LTX-2.3).json",
    "Image to Video (LTX-2.3).json",
    "First-Last-Frame to Video (LTX-2.3).json",
)

LTX_WORKFLOW_NAME_PATTERNS = (
    r"LTX-2\.3_.*\.json$",
    r"LTX-2_.*\.json$",
)


@dataclass(frozen=True)
class FileCandidate:
    name: str
    path: str
    size_bytes: int
    relative_path: str = ""

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LtxReadinessSnapshot:
    type: str = "ltx_readiness_status"
    ok: bool = True
    family: str = "ltx"
    display_name: str = "LTX-Video"
    validation_status: str = "experimental"
    readiness: str = "missing_assets"
    ready_to_test: bool = False
    checked_at: str = ""
    asset_root: str = ""
    comfy_root: str = ""
    extra_model_paths_path: str = ""
    extra_model_paths_present: bool = False
    extra_model_paths_points_to_asset_root: bool = False
    extra_model_paths_required_keys_present: list[str] = field(default_factory=list)
    extra_model_paths_missing_keys: list[str] = field(default_factory=list)
    comfy_running: bool = False
    comfy_healthy: bool = False
    comfy_endpoint_alive: bool = False
    comfy_endpoint: str = ""
    ltx_nodes_available: bool = False
    ltx_nodes_found: list[str] = field(default_factory=list)
    ltx_nodes_missing: list[str] = field(default_factory=list)
    ltx_blueprints_found: list[str] = field(default_factory=list)
    ltx_blueprints_missing: list[str] = field(default_factory=list)
    ltx_example_workflows_found: list[str] = field(default_factory=list)
    ltx_checkpoint_candidates: list[dict[str, Any]] = field(default_factory=list)
    ltx_text_encoder_candidates: list[dict[str, Any]] = field(default_factory=list)
    ltx_projection_candidates: list[dict[str, Any]] = field(default_factory=list)
    ltx_video_vae_candidates: list[dict[str, Any]] = field(default_factory=list)
    ltx_audio_vae_candidates: list[dict[str, Any]] = field(default_factory=list)
    optional_audio_ready: bool = False
    missing_assets: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _first_existing_path(*paths: Path) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[0]


def _unresolved_path_token(value: object) -> bool:
    text = str(value or "").strip()
    return not text or "${" in text or "%SPELLVISION_" in text or "%AI_ASSETS" in text


def _default_asset_root(runtime_status: dict[str, Any] | None = None) -> Path:
    runtime_status = runtime_status or {}

    for key in ("SPELLVISION_ASSET_ROOT", "AI_ASSETS_ROOT"):
        raw = os.environ.get(key)
        if raw and not _unresolved_path_token(raw):
            return Path(raw).expanduser()

    runtime_root = runtime_status.get("runtime_root")
    if runtime_root and not _unresolved_path_token(runtime_root):
        runtime_path = Path(str(runtime_root)).expanduser()
        # D:/AI_ASSETS/comfy_runtime -> D:/AI_ASSETS
        if runtime_path.name.lower() == "comfy_runtime":
            return runtime_path.parent
        return runtime_path

    comfy_root = runtime_status.get("comfy_root")
    if comfy_root and not _unresolved_path_token(comfy_root):
        comfy_path = Path(str(comfy_root)).expanduser()
        # D:/AI_ASSETS/comfy_runtime/ComfyUI -> D:/AI_ASSETS
        if comfy_path.name.lower() == "comfyui" and comfy_path.parent.name.lower() == "comfy_runtime":
            return comfy_path.parent.parent

    return Path("D:/AI_ASSETS")


def _default_comfy_root(asset_root: Path) -> Path:
    for key in ("SPELLVISION_COMFY_ROOT", "COMFYUI_ROOT"):
        raw = os.environ.get(key)
        if raw and not _unresolved_path_token(raw):
            return Path(raw).expanduser()
    return asset_root / "comfy_runtime" / "ComfyUI"


def _default_model_root(asset_root: Path) -> Path:
    for key in ("SPELLVISION_MODELS_ROOT", "AI_MODELS_ROOT"):
        raw = os.environ.get(key)
        if raw and not _unresolved_path_token(raw):
            return Path(raw).expanduser()

    # If asset_root is already the model library, do not append models twice.
    if asset_root.name.lower() == "models":
        return asset_root

    return asset_root / "models"


def _path_text(path: Path) -> str:
    return str(path).replace("\\", "/")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception:
        return ""


def _normalize_path_for_compare(text: str) -> str:
    return str(text or "").strip().replace("\\", "/").rstrip("/").lower()


def _extra_model_paths_summary(extra_model_paths: Path, model_root: Path) -> tuple[bool, list[str], list[str]]:
    text = _read_text(extra_model_paths)
    if not text:
        return False, [], ["diffusion_models", "vae", "text_encoders", "clip"]

    normalized_text = _normalize_path_for_compare(text)
    model_root_norm = _normalize_path_for_compare(str(model_root))
    points_to_asset_root = model_root_norm in normalized_text

    required = ["diffusion_models", "vae", "text_encoders", "clip"]
    present = [key for key in required if re.search(rf"(?m)^\s*{re.escape(key)}\s*:", text)]
    missing = [key for key in required if key not in present]
    return points_to_asset_root, present, missing


def _file_candidate(root: Path, file_path: Path) -> FileCandidate:
    try:
        rel = str(file_path.relative_to(root)).replace("\\", "/")
    except Exception:
        rel = file_path.name
    try:
        size = int(file_path.stat().st_size)
    except Exception:
        size = 0
    return FileCandidate(name=file_path.name, path=str(file_path), size_bytes=size, relative_path=rel)


def _find_candidates(root: Path, patterns: tuple[str, ...], *, max_items: int = 30) -> list[FileCandidate]:
    if not root.exists():
        return []

    compiled = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
    matches: list[FileCandidate] = []
    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue
        name = file_path.name
        if not name.lower().endswith((".safetensors", ".pt", ".pth", ".bin", ".gguf")):
            continue
        if any(pattern.search(name) for pattern in compiled):
            matches.append(_file_candidate(root, file_path))
            if len(matches) >= max_items:
                break
    return sorted(matches, key=lambda item: item.path.lower())


def _find_existing_files(root: Path, names: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    for name in names:
        path = root / name
        if path.exists():
            found.append(str(path))
    return found


def _find_example_workflows(comfy_root: Path) -> list[str]:
    workflows_root = comfy_root / "custom_nodes" / "ComfyUI-LTXVideo" / "example_workflows"
    if not workflows_root.exists():
        return []

    compiled = [re.compile(pattern, re.IGNORECASE) for pattern in LTX_WORKFLOW_NAME_PATTERNS]
    found: list[str] = []
    for path in workflows_root.rglob("*.json"):
        text = str(path).replace("\\", "/")
        if any(pattern.search(path.name) for pattern in compiled):
            found.append(text)
    return sorted(found)


def _fetch_comfy_object_info(endpoint: str) -> dict[str, Any]:
    endpoint = str(endpoint or "").strip().rstrip("/")
    if not endpoint:
        return {}
    try:
        with urllib.request.urlopen(f"{endpoint}/object_info", timeout=5) as response:
            payload = response.read().decode("utf-8", errors="replace")
        data = json.loads(payload)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _object_info_node_names(object_info: dict[str, Any]) -> set[str]:
    if not isinstance(object_info, dict):
        return set()
    return {str(key) for key in object_info.keys()}


def ltx_readiness_snapshot(runtime_status: dict[str, Any] | None = None, object_info: dict[str, Any] | None = None) -> dict[str, Any]:
    runtime_status = runtime_status or {}
    asset_root = _default_asset_root(runtime_status)
    comfy_root = _default_comfy_root(asset_root)
    model_root = _default_model_root(asset_root)
    extra_model_paths = comfy_root / "extra_model_paths.yaml"
    blueprints_root = comfy_root / "blueprints"

    endpoint = str(runtime_status.get("endpoint") or os.environ.get("COMFY_API_URL") or "http://127.0.0.1:8188")
    object_info = object_info if isinstance(object_info, dict) else _fetch_comfy_object_info(endpoint)
    node_names = _object_info_node_names(object_info)
    ltx_nodes_found = sorted([name for name in LTX_REQUIRED_NODE_NAMES if name in node_names])
    ltx_nodes_missing = sorted([name for name in LTX_REQUIRED_NODE_NAMES if name not in node_names])

    blueprints_found = _find_existing_files(blueprints_root, LTX_BLUEPRINT_NAMES)
    blueprints_missing = [name for name in LTX_BLUEPRINT_NAMES if not (blueprints_root / name).exists()]
    example_workflows = _find_example_workflows(comfy_root)

    diffusion_root = model_root / "diffusion_models"
    text_encoder_root = model_root / "text_encoders"
    vae_root = model_root / "vae"

    checkpoint_candidates = _find_candidates(
        diffusion_root,
        (r"ltx", r"ltxv", r"dasiwa.*ltx", r"lightspeed"),
        max_items=50,
    )
    text_encoder_candidates = _find_candidates(
        text_encoder_root,
        (r"gemma", r"ltx.*text", r"text.*ltx"),
        max_items=30,
    )
    projection_candidates = _find_candidates(
        text_encoder_root,
        (r"projection", r"proj", r"ltx.*text.*projection"),
        max_items=30,
    )
    video_vae_candidates = _find_candidates(
        vae_root,
        (r"ltx.*video.*vae", r"video.*vae.*ltx", r"ltx.*vae"),
        max_items=30,
    )
    audio_vae_candidates = _find_candidates(
        vae_root,
        (r"ltx.*audio.*vae", r"audio.*vae.*ltx", r"ltx23_audio"),
        max_items=30,
    )

    extra_present = extra_model_paths.exists()
    points_to_asset_root, extra_keys_present, extra_missing_keys = _extra_model_paths_summary(extra_model_paths, model_root)

    missing_assets: list[str] = []
    if not checkpoint_candidates:
        missing_assets.append("ltx_checkpoint")
    if not text_encoder_candidates:
        missing_assets.append("gemma_text_encoder")
    if not projection_candidates:
        missing_assets.append("ltx_text_projection")
    if not video_vae_candidates:
        missing_assets.append("ltx_video_vae")

    ltx_nodes_available = not ltx_nodes_missing
    blueprints_available = bool(blueprints_found)
    model_paths_ready = bool(extra_present and points_to_asset_root and not extra_missing_keys)
    ready_to_test = bool(
        ltx_nodes_available
        and blueprints_available
        and model_paths_ready
        and checkpoint_candidates
        and text_encoder_candidates
        and video_vae_candidates
    )

    if not ltx_nodes_available:
        readiness = "missing_nodes"
    elif not model_paths_ready:
        readiness = "model_paths_not_ready"
    elif missing_assets:
        readiness = "missing_assets"
    elif not blueprints_available:
        readiness = "missing_blueprints"
    else:
        readiness = "ready_to_test"

    notes: list[str] = []
    if checkpoint_candidates:
        notes.append("LTX checkpoint candidates were found in D:/AI_ASSETS/models/diffusion_models.")
    if missing_assets:
        notes.append("LTX support assets are still incomplete; do not enable production generation yet.")
    if audio_vae_candidates:
        notes.append("Optional LTX audio VAE candidate detected for audio/video workflows.")
    else:
        notes.append("Optional LTX audio VAE was not found; this is acceptable for silent T2V tests.")

    snapshot = LtxReadinessSnapshot(
        checked_at=_utc_now_iso(),
        asset_root=str(model_root),
        comfy_root=str(comfy_root),
        extra_model_paths_path=str(extra_model_paths),
        extra_model_paths_present=extra_present,
        extra_model_paths_points_to_asset_root=points_to_asset_root,
        extra_model_paths_required_keys_present=extra_keys_present,
        extra_model_paths_missing_keys=extra_missing_keys,
        comfy_running=bool(runtime_status.get("running", False)),
        comfy_healthy=bool(runtime_status.get("healthy", False)),
        comfy_endpoint_alive=bool(runtime_status.get("endpoint_alive", False)),
        comfy_endpoint=endpoint,
        ltx_nodes_available=ltx_nodes_available,
        ltx_nodes_found=ltx_nodes_found,
        ltx_nodes_missing=ltx_nodes_missing,
        ltx_blueprints_found=blueprints_found,
        ltx_blueprints_missing=blueprints_missing,
        ltx_example_workflows_found=example_workflows,
        ltx_checkpoint_candidates=[item.to_payload() for item in checkpoint_candidates],
        ltx_text_encoder_candidates=[item.to_payload() for item in text_encoder_candidates],
        ltx_projection_candidates=[item.to_payload() for item in projection_candidates],
        ltx_video_vae_candidates=[item.to_payload() for item in video_vae_candidates],
        ltx_audio_vae_candidates=[item.to_payload() for item in audio_vae_candidates],
        optional_audio_ready=bool(audio_vae_candidates),
        missing_assets=missing_assets,
        readiness=readiness,
        ready_to_test=ready_to_test,
        notes=notes,
    )
    return snapshot.to_payload()
