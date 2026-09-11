"""Keep ComfyUI extra_model_paths.yaml in sync with SpellVision model libraries.

Add folder… and the primary models root only help Generate if Comfy can see those
directories. This module writes the managed block; it does not invent a drive.
"""

from __future__ import annotations

import re
from pathlib import Path

BEGIN_MARK = "# >>> SpellVision managed model paths >>>"
END_MARK = "# <<< SpellVision managed model paths <<<"

_SUBDIRS = (
    ("checkpoints", "checkpoints"),
    ("configs", "configs"),
    ("vae", "vae"),
    ("clip", "text_encoders"),
    ("text_encoders", "text_encoders"),
    ("clip_vision", "clip_vision"),
    ("loras", "loras"),
    ("controlnet", "controlnet"),
    ("embeddings", "embeddings"),
    ("upscale_models", "upscale_models"),
    ("latent_upscale_models", "latent_upscale_models"),
    ("unet", "diffusion_models"),
    ("diffusion_models", "diffusion_models"),
)


def stanza_name(index: int) -> str:
    if index <= 0:
        return "spellvision"
    return f"spellvision_extra_{index - 1}"


def library_root_from_model_path(model_path: str) -> str:
    """Walk up from a checkpoint until a directory named ``models``.

    Character Studio sends the F: UNET path without extra_models_roots. Companions
    (raw UNET, qwen3vl, VAE) live in sibling folders of that same library.
    """
    text = str(model_path or "").strip()
    if not text:
        return ""
    path = Path(text)
    for parent in [path.parent, *path.parents]:
        if parent.name.lower() == "models":
            return _posix(str(parent))
    return ""


def extra_roots_from_request(req: dict | None) -> list[str]:
    """extra_models_roots as a list, tuple, or a single path string."""
    extra = (req or {}).get("extra_models_roots")
    if isinstance(extra, str):
        text = extra.strip()
        return [text] if text else []
    if isinstance(extra, (list, tuple)):
        return [str(item).strip() for item in extra if str(item).strip()]
    return []


def libraries_from_request(req: dict | None) -> list[str]:
    """Primary root + extra roots + the selected checkpoint's own models library."""
    req = req or {}
    libraries: list[str] = []
    primary = str(req.get("models_root") or "").strip()
    if primary:
        libraries.append(primary)
    libraries.extend(extra_roots_from_request(req))
    for key in ("model", "model_path", "primary_path"):
        inferred = library_root_from_model_path(str(req.get(key) or ""))
        if inferred:
            libraries.append(inferred)
            break
    return libraries


def _posix(path: str) -> str:
    return str(path).replace("\\", "/").rstrip("/")


def compose_managed_block(libraries: list[str]) -> str:
    roots: list[str] = []
    seen: set[str] = set()
    for raw in libraries:
        text = _posix(str(raw or "").strip())
        if not text or text in seen:
            continue
        seen.add(text)
        roots.append(text)
    if not roots:
        return ""
    lines = [BEGIN_MARK]
    for i, root in enumerate(roots):
        lines.append(f"{stanza_name(i)}:")
        lines.append(f"    base_path: {root}")
        for key, rel in _SUBDIRS:
            lines.append(f"    {key}: {rel}")
    lines.append(END_MARK)
    return "\n".join(lines) + "\n"


def merge_managed_block(existing: str, block: str) -> str:
    text = existing or ""
    replacement = block.strip()
    if BEGIN_MARK in text and END_MARK in text:
        pattern = re.escape(BEGIN_MARK) + r".*?" + re.escape(END_MARK)
        updated = re.sub(pattern, replacement, text, flags=re.DOTALL)
        if not replacement:
            return updated.strip() + ("\n" if updated.strip() else "")
        return updated
    if not replacement:
        return text
    if text.strip():
        return text.rstrip() + "\n\n" + block
    return block


def write_managed_extra_model_paths(yaml_path: str | Path, libraries: list[str]) -> bool:
    """Rewrite the managed block. Returns True if the file changed."""
    path = Path(yaml_path)
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    block = compose_managed_block(libraries)
    merged = merge_managed_block(existing, block)
    if merged == existing:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(merged, encoding="utf-8")
    return True
