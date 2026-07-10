from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
import os
import re
from urllib.parse import urlparse

SUPPORTED_GENERATION_COMMANDS = {"t2i", "i2i", "t2v", "i2v", "v2v", "ti2v"}


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
    # License dimension (Doc 19 T3 registry -- first introduced for Anima). Defaults preserve
    # today's behavior for every existing family; a non-commercial / no-auto-download model sets
    # commercial_use=False + auto_download=False so the future assisted-download hook points the
    # user at the official source and surfaces the license instead of fetching/bundling on a guess.
    commercial_use: bool = True
    auto_download: bool = True
    license_note: str = ""

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
    "pony": ModelFamilySpec(
        key="pony",
        display_name="Pony Diffusion (SDXL)",
        task_family="image",
        media_type="image",
        supported_commands=("t2i", "i2i"),
        preferred_backends=("diffusers",),
        # Pony is an SDXL finetune -- it loads the SDXL pipeline. The family
        # exists so routing does not depend on an "xl" token in the filename.
        aliases=("pony", "ponydiffusion", "pony-diffusion", "ponyxl"),
        accepted_extensions=(".ckpt", ".safetensors"),
        repo_id_prefixes=("pony",),
    ),
    "illustrious": ModelFamilySpec(
        key="illustrious",
        display_name="Illustrious (SDXL)",
        task_family="image",
        media_type="image",
        supported_commands=("t2i", "i2i"),
        preferred_backends=("diffusers",),
        # Also an SDXL finetune; same no-"xl"-in-name mis-load risk as Pony.
        aliases=("illustrious", "illustri", "illustriousxl"),
        accepted_extensions=(".ckpt", ".safetensors"),
        repo_id_prefixes=("illustrious",),
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
    "pixart": ModelFamilySpec(
        key="pixart",
        display_name="PixArt-Sigma",
        task_family="image",
        media_type="image",
        supported_commands=("t2i", "i2i"),
        preferred_backends=("diffusers",),   # vestigial like Flux's -- native routing is via _should_route_native_image
        aliases=("pixart-sigma", "pixart-alpha", "pixart_sigma", "pixartsigma"),
        accepted_extensions=(".safetensors",),
        repo_id_prefixes=("pixart-alpha/pixart", "pixart"),
    ),
    "lumina": ModelFamilySpec(
        key="lumina",
        display_name="Lumina Image 2.0",
        task_family="image",
        media_type="image",
        supported_commands=("t2i", "i2i"),
        preferred_backends=("diffusers",),   # vestigial like Flux/PixArt -- native routing via _should_route_native_image
        aliases=("lumina-2", "lumina2", "lumina-image-2", "lumina_image_2"),
        accepted_extensions=(".safetensors",),
        repo_id_prefixes=("alpha-vllm/lumina", "lumina"),
    ),
    "z_image": ModelFamilySpec(
        key="z_image",
        display_name="Z-Image Turbo",
        task_family="image",
        media_type="image",
        supported_commands=("t2i", "i2i"),
        preferred_backends=("diffusers",),   # vestigial -- native routing via _should_route_native_image
        aliases=("z-image", "zimage", "z-image-turbo", "z_image_turbo", "z-image-omni"),
        accepted_extensions=(".safetensors",),
        repo_id_prefixes=("comfy-org/z_image", "z_image", "z-image"),
    ),
    "anima": ModelFamilySpec(
        key="anima",
        display_name="Anima",
        task_family="image",
        media_type="image",
        supported_commands=("t2i", "i2i"),
        preferred_backends=("diffusers",),   # vestigial -- native routing via _should_route_native_image
        # Cosmos-Predict2-derived 2B DiT, anime/illustration-only. Split-stack like Z-Image
        # (UNETLoader, diffusion_models/anima/). Aliases are SPECIFIC on purpose: a bare "anima"
        # substring-collides with animagine/animatediff/animation decoys -- the directory (anima/)
        # + metadata layers are the authoritative signals, these are decoy-safe last-resorts.
        aliases=("anima-base", "anima-preview", "cosmos-anima"),
        accepted_extensions=(".safetensors",),
        repo_id_prefixes=("circlestonelabs/anima", "anima-base"),
        # FIRST non-commercial model in the arc: CircleStone Labs Non-Commercial + NVIDIA Open
        # Model License (Cosmos-Predict2 derivative). SpellVision building the graph / letting a
        # user with the file generate is fine (user's model use); the assisted-download hook must
        # NOT auto-fetch/bundle -- point the user at the official source and surface the license.
        commercial_use=False,
        auto_download=False,
        license_note=(
            "CircleStone Labs Non-Commercial License + NVIDIA Open Model License "
            "(Cosmos-Predict2 derivative). Non-commercial; point user to official source, "
            "do not auto-download or bundle."
        ),
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
    # NOTE: this is the FILENAME LAYER of the one layered classifier
    # (model_classification.classify_model), not a standalone router. It matches
    # registry aliases / repo prefixes against the path + an optional explicit
    # family tag. Pipeline routing does NOT call this directly -- it goes through
    # classify_model, which composes this under directory + metadata signals.
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
