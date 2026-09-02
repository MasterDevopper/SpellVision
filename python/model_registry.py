"""What a model file IS, inferred from its name, path and metadata.

The routing table underneath the "state your intent, not your node graph" promise: the UI shows a
checkpoint, the worker has to know which family it belongs to, which commands it can serve, and
which backend can run it, without the user ever saying.

``infer_model_family`` is the load-bearing call. Family tokens are matched on WORD BOUNDARIES and
longest-first, because plain substring matching made ``sdxl`` resolve to ``stable_diffusion`` --
the alias ``sd`` is a substring of it. A second, permissive pass then catches names that only ever
appear glued to other words. Two passes, in that order, or high-volume families mis-route.

Related: ``model_classification`` (the four-signal classifier the Qt scanner shares) and
``family_operating_points`` (what to DO with a family once it is known).
"""
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
    "krea2": ModelFamilySpec(
        key="krea2",
        display_name="Krea 2",
        task_family="image",
        media_type="image",
        supported_commands=("t2i", "i2i"),
        preferred_backends=("diffusers",),
        aliases=("krea-2", "krea_2", "krea2-raw", "krea2-turbo", "krea-2-raw", "krea-2-turbo"),
        accepted_extensions=(".safetensors",),
        repo_id_prefixes=("comfy-org/krea-2", "krea/krea-2", "krea/krea-2-raw", "krea/krea-2-turbo"),
        license_note=(
            "Krea 2 Community License + Acceptable Use Policy. "
            "Official bases: krea/Krea-2-Raw (default, ~52 steps CFG 3.5) and "
            "krea/Krea-2-Turbo (speed lane, 8 steps CFG 0). Comfy-Org/Krea-2 is the "
            "ungated ComfyUI pack (diffusion_models + qwen3vl_4b + qwen_image_vae). "
            "LoRAs are user variants — enabled, never required, not family-installed."
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
        commercial_use=False,
        auto_download=False,
        license_note=(
            "Tencent Hunyuan Community License (non-commercial). "
            "Badge and warn on commercial-use flows; do not auto-download or bundle."
        ),
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


# Token matching is BOUNDARY-AWARE and LONGEST-FIRST, because a plain ``alias in text``
# makes every family that is a string prefix of another one shadow it. Measured: the
# "sd" alias on stable_diffusion is a substring of "sdxl", and stable_diffusion is first
# in MODEL_FAMILIES, so ``infer_model_family("sdxl")`` returned "stable_diffusion" -- the
# literal family key resolving to the wrong family, and with it every sdxl/pony/illustrious
# path that carried no other signal.
#
# Leading edge: must not be preceded by a letter or digit, so "xl" never matches inside
# "juggernautxl" the way a bare substring would.
# Trailing edge: must not be followed by a LETTER, but a DIGIT is allowed, because version
# suffixes are written flush against the family name -- "flux1-dev", "wan2.2", "ltx2", "sd15".
# That asymmetry is the whole rule: "sd" matches "sd15" (correct, SD1.5 IS stable_diffusion)
# and does not match "sdxl" (a different architecture that merely starts with the same letters).
_TOKEN_RE_CACHE: dict[str, re.Pattern[str]] = {}


def _token_pattern(token: str) -> re.Pattern[str]:
    pattern = _TOKEN_RE_CACHE.get(token)
    if pattern is None:
        pattern = re.compile(r"(?<![a-z0-9])" + re.escape(token) + r"(?![a-z])")
        _TOKEN_RE_CACHE[token] = pattern
    return pattern


def _ranked_family_tokens() -> list[tuple[str, str]]:
    """All (token, family) pairs, longest token first so a specific alias beats the
    generic one it contains ("sd15" over "sd", "stable-diffusion-xl" over "stable-diffusion",
    "hunyuan_3d" over "hunyuan"). Ties keep registry declaration order, which is stable."""
    global _RANKED_TOKENS
    if _RANKED_TOKENS is None:
        pairs = list(_iter_family_tokens())
        _RANKED_TOKENS = sorted(
            ((tok, fam, idx) for idx, (tok, fam) in enumerate(pairs)),
            key=lambda item: (-len(item[0]), item[2]),
        )
        _RANKED_TOKENS = [(tok, fam) for tok, fam, _ in _RANKED_TOKENS]
    return _RANKED_TOKENS


_RANKED_TOKENS: list[tuple[str, str]] | None = None


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

    # PASS 1 -- boundary-aware. No false positives, but it also refuses the aliases that are
    # deliberately PREFIXES ("illustri" exists to match illustrious/illustriousXL/illustrij...),
    # because those legitimately continue with a letter.
    for candidate in candidates:
        normalized = candidate.replace("_", "-")
        for token, key in _ranked_family_tokens():
            pattern = _token_pattern(token)
            if pattern.search(candidate) or pattern.search(normalized):
                return key

    # PASS 2 -- the historical plain-substring match, still longest-token-first, reached only
    # when nothing matched cleanly. This is what keeps prefix aliases working. Running it
    # SECOND is the whole point: a clean match always wins, so "sdxl" can no longer be captured
    # by the "sd" alias, while "illustrijBTTR_v10" still resolves to illustrious.
    for candidate in candidates:
        normalized = candidate.replace("_", "-")
        for token, key in _ranked_family_tokens():
            if token in candidate or token in normalized:
                return key

    return "unknown"


def resolve_model_capabilities(model_family: str) -> ModelFamilySpec:
    key = str(model_family or "").strip().lower()
    if key in MODEL_FAMILIES:
        return MODEL_FAMILIES[key]
    for spec in MODEL_FAMILIES.values():
        if key in spec.aliases:
            return spec
    return MODEL_FAMILIES["unknown"]


def family_license_info(model_family: str) -> dict[str, object]:
    spec = resolve_model_capabilities(model_family)
    return {
        "key": spec.key,
        "commercial_use": bool(spec.commercial_use),
        "license_note": spec.license_note,
    }


def family_license_catalog() -> list[dict[str, object]]:
    """Every family's licence answer, once -- the export the UI badge path consumes.

    ``family_license_info`` answers for ONE family and needs the key already resolved. The Qt side
    has to answer the same question for a card grid it built from a disk scan, before any worker
    round trip, so it needs the whole table rather than a lookup service. This is that table, and
    it is the ONLY thing allowed to leave this module carrying a family name toward C++:
    ``scripts/dev/generate_family_license_table.py`` renders it into
    ``qt_ui/assets/FamilyLicenseTable.h`` and ``tests/test_family_license_surfaced.py`` re-renders
    it on every run and fails on any difference, so the generated copy cannot drift from this dict.

    Aliases travel with each row on purpose. The C++ copy that this replaces asked
    ``family.contains("anima")``, which is true of animagine, animatediff and animation -- the exact
    decoy collision the anima spec's own comment says its aliases exist to avoid. Shipping the
    aliases lets the Qt lookup resolve by EXACT key or EXACT alias, the way
    ``resolve_model_capabilities`` does, instead of by substring.
    """
    return [
        {
            "key": spec.key,
            "display_name": spec.display_name,
            "aliases": list(spec.aliases),
            "commercial_use": bool(spec.commercial_use),
            "auto_download": bool(spec.auto_download),
            "license_note": spec.license_note,
        }
        for spec in sorted(MODEL_FAMILIES.values(), key=lambda s: s.key)
    ]


def non_commercial_families() -> list[str]:
    """The family keys that must carry a badge and a soft warn (Doc 28 section 2).

    Derived, never listed. Doc 28 names Hunyuan and Anima; a list spelled anywhere else is a copy
    that goes stale the first time a fourth family arrives with a non-commercial licence.
    """
    return sorted(spec.key for spec in MODEL_FAMILIES.values() if not spec.commercial_use)


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
