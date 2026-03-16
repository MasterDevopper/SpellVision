from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

SUPPORTED_GENERATION_COMMANDS = {"t2i", "i2i", "t2v", "i2v", "v2v", "ti2v"}

DEFAULT_VIDEO_RUNTIME_HINTS: dict[str, list[str]] = {
    "wan": ["diffusers", "native_python", "comfy_workflow"],
    "ltx": ["native_python", "diffusers", "comfy_workflow"],
    "hunyuan_video": ["comfy_workflow", "diffusers", "native_python"],
    "cogvideox": ["diffusers", "comfy_workflow"],
    "mochi": ["diffusers", "comfy_workflow"],
    "flux": ["diffusers"],
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


def _iter_family_tokens() -> Iterable[tuple[str, str]]:
    for key, spec in MODEL_FAMILIES.items():
        yield key, key
        for alias in spec.aliases:
            yield alias, key


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
