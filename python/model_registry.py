from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
import os
import re
from urllib.parse import urlparse

SUPPORTED_GENERATION_COMMANDS = {"t2i", "i2i", "t2v", "i2v", "v2v", "ti2v"}

DEFAULT_VIDEO_RUNTIME_HINTS: dict[str, list[str]] = {
    "wan": ["diffusers", "native_python", "comfy_workflow"],
    "ltx": ["native_python", "diffusers", "comfy_workflow"],
    "hunyuan_video": ["comfy_workflow", "diffusers", "native_python"],
    "cogvideox": ["diffusers", "comfy_workflow"],
    "mochi": ["diffusers", "comfy_workflow"],
    "flux": ["diffusers"],
    "pony": ["diffusers"],
    "illustrious": ["diffusers"],
    "z_image": ["diffusers", "comfy_workflow"],
    "qwen_image": ["diffusers", "comfy_workflow"],
    "animatediff": ["comfy_workflow", "diffusers"],
    "stable_video_diffusion": ["diffusers", "comfy_workflow"],
    "pyramid_flow": ["diffusers", "comfy_workflow"],
    "sdxl": ["diffusers"],
    "sd3": ["diffusers"],
    "stable_diffusion": ["diffusers"],
    "unknown": ["diffusers", "native_python", "comfy_workflow"],
}


@dataclass(frozen=True)
class ModelFamilySpec:
    key: str
    display_name: str
    task_family: str
    media_type: str
    supported_commands: tuple[str, ...]
    preferred_backends: tuple[str, ...]
    aliases: tuple[str, ...] = field(default_factory=tuple)
    accepted_extensions: tuple[str, ...] = field(default_factory=tuple)
    experimental_extensions: tuple[str, ...] = field(default_factory=tuple)
    repo_id_prefixes: tuple[str, ...] = field(default_factory=tuple)

    def supports(self, command: str) -> bool:
        return command.strip().lower() in self.supported_commands


MODEL_FAMILIES: dict[str, ModelFamilySpec] = {
    "stable_diffusion": ModelFamilySpec(
        key="stable_diffusion",
        display_name="Stable Diffusion",
        task_family="image",
        media_type="image",
        supported_commands=("t2i", "i2i"),
        preferred_backends=("diffusers",),
        aliases=("sd", "sd15", "sd1.5", "stable-diffusion"),
        accepted_extensions=(".ckpt", ".safetensors"),
        repo_id_prefixes=("stable-diffusion",),
    ),
    "sdxl": ModelFamilySpec(
        key="sdxl",
        display_name="Stable Diffusion XL",
        task_family="image",
        media_type="image",
        supported_commands=("t2i", "i2i"),
        preferred_backends=("diffusers",),
        aliases=("sd-xl", "stable-diffusion-xl"),
        accepted_extensions=(".ckpt", ".safetensors"),
        repo_id_prefixes=("sdxl",),
    ),
    "sd3": ModelFamilySpec(
        key="sd3",
        display_name="Stable Diffusion 3",
        task_family="image",
        media_type="image",
        supported_commands=("t2i",),
        preferred_backends=("diffusers",),
        aliases=("stable-diffusion-3",),
        accepted_extensions=(".safetensors",),
        repo_id_prefixes=("stable-diffusion-3", "sd3"),
    ),
    "flux": ModelFamilySpec(
        key="flux",
        display_name="FLUX",
        task_family="image",
        media_type="image",
        supported_commands=("t2i", "i2i"),
        preferred_backends=("diffusers",),
        aliases=("black-forest-labs-flux",),
        accepted_extensions=(".safetensors",),
        repo_id_prefixes=("flux",),
    ),
    "pony": ModelFamilySpec(
        key="pony",
        display_name="Pony Diffusion",
        task_family="image",
        media_type="image",
        supported_commands=("t2i", "i2i"),
        preferred_backends=("diffusers", "comfy_workflow"),
        aliases=("pony-diffusion", "ponyxl", "pony-xl"),
        accepted_extensions=(".ckpt", ".safetensors"),
        repo_id_prefixes=("pony", "pony-diffusion"),
    ),
    "illustrious": ModelFamilySpec(
        key="illustrious",
        display_name="Illustrious",
        task_family="image",
        media_type="image",
        supported_commands=("t2i", "i2i"),
        preferred_backends=("diffusers", "comfy_workflow"),
        aliases=("illustrious-xl", "illustriousxl"),
        accepted_extensions=(".ckpt", ".safetensors"),
        repo_id_prefixes=("illustrious",),
    ),
    "z_image": ModelFamilySpec(
        key="z_image",
        display_name="Z-Image",
        task_family="image",
        media_type="image",
        supported_commands=("t2i", "i2i"),
        preferred_backends=("diffusers", "comfy_workflow"),
        aliases=("zimage", "z-image"),
        accepted_extensions=(".safetensors", ".gguf"),
        repo_id_prefixes=("z-image", "zimage"),
    ),
    "qwen_image": ModelFamilySpec(
        key="qwen_image",
        display_name="Qwen Image",
        task_family="image",
        media_type="image",
        supported_commands=("t2i", "i2i"),
        preferred_backends=("diffusers", "comfy_workflow"),
        aliases=("qwen-image", "qwen_image"),
        accepted_extensions=(".safetensors", ".gguf"),
        repo_id_prefixes=("qwen-image", "qwen/qwen-image"),
    ),
    "wan": ModelFamilySpec(
        key="wan",
        display_name="Wan Video",
        task_family="video",
        media_type="video",
        supported_commands=("t2v", "i2v", "ti2v", "v2v"),
        preferred_backends=("diffusers", "native_python", "comfy_workflow"),
        aliases=("wan2", "wan2.1", "wan2.2", "wan-video"),
        accepted_extensions=(".safetensors",),
        repo_id_prefixes=("wan-ai/wan", "wan-ai/wan2", "wan-ai/wan2.1", "wan-ai/wan2.2"),
    ),
    "ltx": ModelFamilySpec(
        key="ltx",
        display_name="LTX Video",
        task_family="video",
        media_type="video",
        supported_commands=("t2v", "i2v", "v2v"),
        preferred_backends=("native_python", "diffusers", "comfy_workflow"),
        aliases=("ltx-video", "ltxv", "ltx-2", "ltx-2.3"),
        accepted_extensions=(".safetensors",),
        experimental_extensions=(".gguf",),
        repo_id_prefixes=("lightricks/ltx", "lightricks/ltx-video", "lightricks/ltx-2", "lightricks/ltx-2.3"),
    ),
    "hunyuan_video": ModelFamilySpec(
        key="hunyuan_video",
        display_name="Hunyuan Video",
        task_family="video",
        media_type="video",
        supported_commands=("t2v", "i2v"),
        preferred_backends=("comfy_workflow", "diffusers", "native_python"),
        aliases=("hunyuan", "hunyuanvideo", "hyvideo"),
        accepted_extensions=(".safetensors",),
        repo_id_prefixes=("tencent/hunyuanvideo", "hunyuanvideo", "hunyuan-video"),
    ),
    "cogvideox": ModelFamilySpec(
        key="cogvideox",
        display_name="CogVideoX",
        task_family="video",
        media_type="video",
        supported_commands=("t2v", "i2v"),
        preferred_backends=("diffusers", "comfy_workflow"),
        aliases=("cogvideo", "cog-video-x"),
        accepted_extensions=(".safetensors",),
        repo_id_prefixes=("thudm/cogvideox", "cogvideox"),
    ),
    "mochi": ModelFamilySpec(
        key="mochi",
        display_name="Mochi",
        task_family="video",
        media_type="video",
        supported_commands=("t2v",),
        preferred_backends=("diffusers", "comfy_workflow"),
        aliases=("mochi-1",),
        accepted_extensions=(".safetensors",),
        repo_id_prefixes=("genmo/mochi", "mochi-1"),
    ),
    "animatediff": ModelFamilySpec(
        key="animatediff",
        display_name="AnimateDiff",
        task_family="video",
        media_type="video",
        supported_commands=("t2v", "i2v", "v2v"),
        preferred_backends=("comfy_workflow", "diffusers"),
        aliases=("animate-diff", "animatediff-motion"),
        accepted_extensions=(".safetensors", ".ckpt"),
        repo_id_prefixes=("animatediff", "guoyww/animatediff"),
    ),
    "stable_video_diffusion": ModelFamilySpec(
        key="stable_video_diffusion",
        display_name="Stable Video Diffusion",
        task_family="video",
        media_type="video",
        supported_commands=("i2v", "v2v"),
        preferred_backends=("diffusers", "comfy_workflow"),
        aliases=("stable-video-diffusion", "svd", "svd-xt"),
        accepted_extensions=(".safetensors",),
        repo_id_prefixes=("stabilityai/stable-video-diffusion", "stable-video-diffusion"),
    ),
    "pyramid_flow": ModelFamilySpec(
        key="pyramid_flow",
        display_name="Pyramid Flow",
        task_family="video",
        media_type="video",
        supported_commands=("t2v", "i2v"),
        preferred_backends=("diffusers", "comfy_workflow"),
        aliases=("pyramid-flow", "pyramidflow"),
        accepted_extensions=(".safetensors",),
        repo_id_prefixes=("pyramid-flow",),
    ),
    "unknown": ModelFamilySpec(
        key="unknown",
        display_name="Unknown Model Family",
        task_family="image",
        media_type="image",
        supported_commands=tuple(sorted(SUPPORTED_GENERATION_COMMANDS)),
        preferred_backends=("diffusers", "native_python", "comfy_workflow"),
    ),
}


@dataclass(frozen=True)
class ModelReferenceInfo:
    raw: str
    kind: str
    path: str | None = None
    extension: str | None = None
    repo_id: str | None = None


REPO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)


def _iter_family_tokens() -> Iterable[tuple[str, str]]:
    for key, spec in MODEL_FAMILIES.items():
        yield key, key
        for alias in spec.aliases:
            yield alias, key
        for repo_prefix in spec.repo_id_prefixes:
            yield repo_prefix, key


def detect_model_reference(model: str | None) -> ModelReferenceInfo:
    raw = str(model or "").strip()
    if not raw:
        return ModelReferenceInfo(raw="", kind="empty")

    if raw.startswith("hf://"):
        repo_id = raw[5:]
        return ModelReferenceInfo(raw=raw, kind="hf_repo", repo_id=repo_id)

    if URL_PATTERN.match(raw):
        parsed = urlparse(raw)
        ext = Path(parsed.path).suffix.lower() or None
        if 'civitai.com' in (parsed.netloc or '').lower():
            return ModelReferenceInfo(raw=raw, kind="remote_civitai_url", path=raw, extension=ext)
        return ModelReferenceInfo(raw=raw, kind="remote_url", path=raw, extension=ext)

    normalized = raw.replace('\\', '/')
    if REPO_ID_PATTERN.match(raw) and not os.path.isabs(raw) and not raw.startswith('./') and not raw.startswith('../'):
        return ModelReferenceInfo(raw=raw, kind="hf_repo", repo_id=raw)

    path = Path(raw)
    suffix = path.suffix.lower()
    if suffix:
        if suffix == '.json':
            return ModelReferenceInfo(raw=raw, kind="workflow_json", path=str(path), extension=suffix)
        return ModelReferenceInfo(raw=raw, kind="weights_file", path=str(path), extension=suffix)

    if normalized.endswith('/'):
        return ModelReferenceInfo(raw=raw, kind="directory", path=raw)

    return ModelReferenceInfo(raw=raw, kind="directory_or_id", path=raw)


def infer_model_family(model: str | None, requested_family: str | None = None) -> str:
    if requested_family:
        normalized = requested_family.strip().lower().replace(" ", "_").replace("-", "_")
        if normalized in MODEL_FAMILIES:
            return normalized
        for alias, key in _iter_family_tokens():
            if normalized == alias.replace(" ", "_").replace("-", "_"):
                return key

    model_text = str(model or "").strip().lower()
    if not model_text:
        return "unknown"

    model_name = Path(model_text).name
    candidates = [model_text, model_name]
    for candidate in candidates:
        normalized = candidate.replace("_", "-")
        for alias, key in _iter_family_tokens():
            if alias in candidate or alias in normalized:
                return key

    return "unknown"


def resolve_model_capabilities(model_family: str) -> ModelFamilySpec:
    return MODEL_FAMILIES.get(model_family, MODEL_FAMILIES["unknown"])


def infer_runtime_backend(runtime: str | None, backend_kind: str | None, model_family: str | None) -> str:
    explicit = str(runtime or backend_kind or "").strip().lower()
    if explicit:
        return explicit
    spec = resolve_model_capabilities(model_family or "unknown")
    return spec.preferred_backends[0] if spec.preferred_backends else "diffusers"


def infer_runtime_backend_from_request(req: dict[str, object] | None) -> str:
    req = req or {}
    explicit = str(req.get('runtime') or req.get('backend_kind') or '').strip().lower()
    if explicit:
        return explicit
    if req.get('workflow_path') or req.get('workflow_json') or req.get('comfy_workflow'):
        return 'comfy_workflow'
    if req.get('native_entrypoint') or req.get('native_repo_dir') or req.get('native_args_template'):
        return 'native_python'
    model_family = infer_model_family(str(req.get('model') or ''), str(req.get('model_family') or '') or None)
    reference = detect_model_reference(str(req.get('model') or ''))
    if reference.kind in {'hf_repo', 'directory', 'directory_or_id'}:
        spec = resolve_model_capabilities(model_family)
        if 'diffusers' in spec.preferred_backends:
            return 'diffusers'
    return infer_runtime_backend(None, None, model_family)
