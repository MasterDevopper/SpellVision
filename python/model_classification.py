"""Layered model classifier -- the ONE source of truth for "what architecture
is this model", replacing the three disconnected filename-substring guessers
(worker ``detect_pipeline_type``, registry ``infer_model_family``, Qt
``inferImageFamilyFromText``).

Precedence (STEP-0 survey decided: directory-as-strong-signal, strictness (b)):

  1. METADATA             -- safetensors ``__metadata__`` arch string; the actual
                             file, so it is definitive when present (~23% of
                             community checkpoints) and OVERRIDES a wrong directory
                             or a wrong caller tag. Header read only (cheap, ~KB);
                             never loads tensors. This is what makes the worker
                             authoritative over an upstream guess.
  2. ``requested_family`` -- an explicit caller/UI assertion, honored ABOVE the
                             directory/filename guesses but BELOW the actual-file
                             metadata (a filename-derived UI tag must not override
                             what the file itself declares). Pony #1 threads this;
                             its authority is preserved for the no-metadata case.
  3. LEVEL-2 DIRECTORY     -- the architecture subfolder (checkpoints/sdxl, /flux,
                             /ltx ...). Strong vote: covers the ~72% of the sdxl
                             folder that no filename token identifies.
  4. FILENAME              -- the old substring heuristic (via the registry's
                             ``infer_model_family``), DEMOTED to last-resort family
                             AND used to separate SUB-FAMILIES the folder lumps
                             together (pony / illustrious / noobai inside sdxl/).

LEVEL-1 DIRECTORY (checkpoints / loras / vae / diffusion_models / ...) is
authoritative for the model *type* (yaml-enforced, already clean) and feeds
``model_type`` + ``task_family``; it does not compete for the arch family.

Documented ceiling (per the build decision -- NOT solved here): a misfiled,
bare-``__metadata__`` checkpoint (e.g. an SD1.5 model dropped in sdxl/ with no
metadata and no name token) resolves to its wrong-but-honest directory vote with
low confidence. Only tensor-shape loading would catch it; we intentionally do not.
The STEP-0 cleanup swept such misfiles out of sdxl/ so the directory is honest.
"""
from __future__ import annotations

import json
import os
import re
import struct
from dataclasses import dataclass
from typing import Optional

from model_registry import MODEL_FAMILIES, infer_model_family

# --- arch family -> diffusers image-pipeline selector (the worker's contract) ---
# Video families do not route through the diffusers image pipeline; they carry
# "video" here purely as an informational arch class.
_PIPELINE_TYPE_BY_FAMILY: dict[str, str] = {
    "pony": "sdxl", "illustrious": "sdxl", "sdxl": "sdxl",
    "stable_diffusion": "sd", "sd15": "sd", "sd2": "sd",
    "sd3": "sd3", "flux": "flux",
    "ltx": "video", "wan": "video", "hunyuan_video": "video",
    "mochi": "video", "cogvideox": "video",
    "hunyuan_3d": "other", "qwen_image": "other",
    "unknown": "sd",  # legacy fallback for an unrecognized IMAGE checkpoint
}

# --- level-2 architecture subfolder -> family ---
_L2_DIR_FAMILY: dict[str, str] = {
    "sdxl": "sdxl", "sd-xl": "sdxl",
    "sd15": "stable_diffusion", "sd1.5": "stable_diffusion", "sd": "stable_diffusion",
    "sd3": "sd3", "flux": "flux",
    "pony": "pony", "illustrious": "illustrious",
    "ltx": "ltx", "ltxv": "ltx", "wan": "wan",
    "hunyuan": "hunyuan_video", "hunyuan_video": "hunyuan_video",
    "mochi": "mochi", "cogvideox": "cogvideox", "cogvideo": "cogvideox",
    "hunyuan_3d": "hunyuan_3d", "qwen": "qwen_image", "qwen_image": "qwen_image",
}

# --- level-1 type category folder -> (model_type, default task hint) ---
_L1_TYPE_CATEGORY: dict[str, tuple[str, str]] = {
    "checkpoints": ("checkpoint", "image"),
    "diffusion_models": ("diffusion_model", "unknown"),
    "unet": ("diffusion_model", "unknown"),
    "loras": ("lora", "unknown"),
    "vae": ("vae", "unknown"),
    "controlnet": ("controlnet", "image"),
    "clip_vision": ("clip_vision", "unknown"),
    "text_encoders": ("text_encoder", "unknown"),
    "clip": ("text_encoder", "unknown"),
    "upscale_models": ("upscaler", "image"),
    "embeddings": ("embedding", "image"),
    "style_models": ("style_model", "image"),
    "video": ("video_stack", "video"),
}


@dataclass(frozen=True)
class ModelClassification:
    family: str                     # finest registry family key we could determine
    task_family: str                # image | video | 3d | unknown
    pipeline_type: str              # sd | sdxl | sd3 | flux | video | other
    sub_family: Optional[str]       # lineage within an arch class (pony/illustrious/noobai/animagine/base)
    confidence: float               # 0.0 - 1.0
    source_layer: str               # requested_family | metadata | directory_l2 | filename | directory_l1 | unknown
    model_type: str = "unknown"     # checkpoint | lora | vae | diffusion_model | ...


def _norm(text: str) -> str:
    return str(text or "").strip().lower().replace("\\", "/")


def _path_parts(path: str) -> list[str]:
    return [p for p in _norm(path).split("/") if p]


_WEIGHT_EXT = ("safetensors", "ckpt", "gguf", "pt", "pth", "bin")


def _type_and_arch_dir(path: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (model_type, task_hint, level2_arch_dir) from the folder layout.

    The level-2 arch dir is the folder immediately inside the type category, and
    only when it is a real folder (strictly before the filename) -- a checkpoint
    loose at the category root has no arch dir.
    """
    parts = _path_parts(path)
    if not parts:
        return None, None, None
    tail = parts[-1]
    has_file = "." in tail and tail.rsplit(".", 1)[-1] in _WEIGHT_EXT
    file_idx = len(parts) - 1 if has_file else len(parts)
    for i, part in enumerate(parts):
        if part in _L1_TYPE_CATEGORY:
            model_type, task_hint = _L1_TYPE_CATEGORY[part]
            if i + 1 < file_idx:  # a folder sits between the category and the file
                return model_type, task_hint, parts[i + 1]
            return model_type, task_hint, None
    return None, None, None


def _normalize_family(requested_family: Optional[str]) -> Optional[str]:
    if not requested_family:
        return None
    fam = infer_model_family("", str(requested_family))
    return fam if fam and fam != "unknown" else None


def _family_from_arch_string(s: str) -> Optional[str]:
    s = s.lower()
    if not s:
        return None
    if "sdxl" in s or ("xl" in s and "stable-diffusion" in s):
        return "sdxl"
    if "flux" in s:
        return "flux"
    if "pixart" in s:
        return "pixart"
    if "lumina" in s:
        return "lumina"
    if "z_image" in s or "z-image" in s:
        return "z_image"
    if "stable-diffusion-3" in s or "sd3" in s or "sd-3" in s:
        return "sd3"
    if "ltx" in s or "lightricks" in s:
        return "ltx"
    if "hunyuan" in s and "video" in s:
        return "hunyuan_video"
    if "wan" in s:
        return "wan"
    if "mochi" in s:
        return "mochi"
    if "cogvideo" in s:
        return "cogvideox"
    if "playground" in s:
        return "sdxl"
    if "stable-diffusion-2" in s or "sd-2" in s:
        return "sd2"
    if "stable-diffusion" in s or "sd-v1" in s or "sd-1" in s:
        return "stable_diffusion"
    return None


def _metadata_family(path: str) -> Optional[str]:
    """Read the safetensors ``__metadata__`` arch string. Header only -- never
    loads tensors. Returns a family or None (absent/unreadable/no arch key)."""
    p = str(path or "")
    if not p.lower().endswith(".safetensors") or not os.path.isfile(p):
        return None
    try:
        with open(p, "rb") as f:
            n = struct.unpack("<Q", f.read(8))[0]
            if n <= 0 or n > 80_000_000:
                return None
            md = json.loads(f.read(n).decode("utf-8", "replace")).get("__metadata__")
    except Exception:
        return None
    if not md or not isinstance(md, dict):
        return None
    for key in ("modelspec.architecture", "general.architecture", "architecture", "arch"):
        val = md.get(key)
        if isinstance(val, str):
            fam = _family_from_arch_string(val)
            if fam:
                return fam
    return None


def _filename_sub_family(path: str) -> Optional[str]:
    n = os.path.basename(_norm(path))
    if "pony" in n or "pdxl" in n:
        return "pony"
    if "noob" in n:
        return "noobai"
    if "illustri" in n or "ilxl" in n or re.search(r"(^|[_\-. ])il([_\-. v]|$)", n):
        return "illustrious"
    if "animagine" in n:
        return "animagine"
    return None


def _arch_class(family: str) -> str:
    return _PIPELINE_TYPE_BY_FAMILY.get(family, "sd")


def _task_family(family: str, task_hint: Optional[str]) -> str:
    spec = MODEL_FAMILIES.get(family)
    if spec is not None:
        return spec.task_family
    if family == "hunyuan_3d":
        return "3d"
    if family == "qwen_image":
        return "image"
    return task_hint or "unknown"


def classify_model(path: str, *, requested_family: Optional[str] = None) -> ModelClassification:
    """Classify a model by the layered precedence. See module docstring."""
    path_s = str(path or "")
    model_type, task_hint, l2_dir = _type_and_arch_dir(path_s)

    # Signals in PRECEDENCE ORDER (first non-empty wins the family slot):
    # metadata (actual file) > requested_family (explicit tag) > directory > filename.
    signals: list[tuple[str, str, float]] = []
    meta_fam = _metadata_family(path_s)
    if meta_fam:
        signals.append((meta_fam, "metadata", 0.97))
    rf = _normalize_family(requested_family)
    if rf:
        signals.append((rf, "requested_family", 0.90))
    l2_fam = _L2_DIR_FAMILY.get(l2_dir or "")
    if l2_fam:
        signals.append((l2_fam, "directory_l2", 0.80))
    fn_fam = infer_model_family(path_s)
    if fn_fam and fn_fam != "unknown":
        signals.append((fn_fam, "filename", 0.60))

    if signals:
        family, source_layer, confidence = signals[0]
    elif model_type:
        family, source_layer, confidence = "unknown", "directory_l1", 0.25
    else:
        family, source_layer, confidence = "unknown", "unknown", 0.15

    # SUB-FAMILY: the filename is the only signal that separates lineages the
    # sdxl/ folder lumps together. It also PROMOTES a generic "sdxl" to its
    # specific registry family (pony/illustrious) when the name says so.
    sub_family: Optional[str] = None
    fn_sub = _filename_sub_family(path_s)
    if _arch_class(family) == "sdxl":
        if family == "sdxl" and fn_sub in ("pony", "illustrious"):
            family = fn_sub
            source_layer = f"{source_layer}+filename"
        sub_family = fn_sub or (family if family in ("pony", "illustrious") else "base")

    return ModelClassification(
        family=family,
        task_family=_task_family(family, task_hint),
        pipeline_type=_PIPELINE_TYPE_BY_FAMILY.get(family, "sd"),
        sub_family=sub_family,
        confidence=round(confidence, 2),
        source_layer=source_layer,
        model_type=model_type or "unknown",
    )


def detect_image_pipeline_type(path: str, requested_family: Optional[str] = None) -> str:
    """Worker-facing shim: the diffusers image-pipeline selector (sd/sdxl/sd3/flux).
    Delegates to the classifier and clamps to a valid image pipeline type -- a
    non-image classification falls back to the legacy filename substring so this
    never returns "video"/"other" to the image loader."""
    result = classify_model(path, requested_family=requested_family)
    if result.pipeline_type in ("sd", "sdxl", "sd3", "flux"):
        return result.pipeline_type
    lower = _norm(path)
    if "flux" in lower:
        return "flux"
    if "stable-diffusion-3" in lower or "sd3" in lower:
        return "sd3"
    if "xl" in lower or "sdxl" in lower:
        return "sdxl"
    return "sd"
