"""Which models subdirectory a weight belongs in.

This mirrors `ModelManagerPage::destSubdirForWeight` deliberately: the C++ drag-and-drop path and
the Python download path answer the same question, and two resolvers that can disagree about where
a file goes is the defect Doc 50 rule 5 names. The classifier's kind wins when it has one; the
filename heuristic is the fallback for a file nothing has classified yet.

Nothing here overwrites. A name collision gets a suffix, because the file already on disk may be
the one the user is currently rendering with.
"""
from __future__ import annotations

import shutil
from pathlib import Path

KIND_SUBDIRS: dict[str, str] = {
    "checkpoint": "checkpoints",
    "diffusion_model": "diffusion_models",
    "lora": "loras",
    "vae": "vae",
    "text_encoder": "text_encoders",
    "clip_vision": "clip_vision",
    "embedding": "embeddings",
    "upscaler": "upscale_models",
    "controlnet": "controlnet",
    "style_model": "style_models",
}

_NAME_HINTS: tuple[tuple[str, str], ...] = (
    ("lora", "loras"),
    ("lycoris", "loras"),
    ("controlnet", "controlnet"),
    ("clip_vision", "clip_vision"),
    ("clipvision", "clip_vision"),
    ("text_encoder", "text_encoders"),
    ("t5xxl", "text_encoders"),
    ("umt5", "text_encoders"),
    ("clip_l", "text_encoders"),
    ("vae", "vae"),
    ("upscal", "upscale_models"),
    ("esrgan", "upscale_models"),
    ("embedding", "embeddings"),
    ("unet", "diffusion_models"),
)

_UPSCALE_EXTENSIONS = {".pth"}


def subdir_for(path: str | Path, *, kind: str | None = None) -> str:
    """The models subdirectory for this weight. Defaults to checkpoints, never to the root."""
    mapped = KIND_SUBDIRS.get(str(kind or "").strip().lower())
    if mapped:
        return mapped
    name = Path(str(path)).name.lower()
    for needle, subdir in _NAME_HINTS:
        if needle in name:
            return subdir
    if Path(str(path)).suffix.lower() in _UPSCALE_EXTENSIONS:
        return "upscale_models"
    return "checkpoints"


def place(
    source: str | Path,
    models_root: str | Path,
    *,
    kind: str | None = None,
    move: bool = True,
) -> Path:
    """Put a downloaded weight where the library can see it. Never overwrites."""
    src = Path(str(source))
    target_dir = Path(str(models_root)) / subdir_for(src, kind=kind)
    target_dir.mkdir(parents=True, exist_ok=True)

    target = target_dir / src.name
    if target.exists():
        stem, suffix = src.stem, src.suffix
        index = 1
        while target.exists():
            target = target_dir / f"{stem}_{index}{suffix}"
            index += 1

    if move:
        shutil.move(str(src), str(target))
    else:
        shutil.copy2(str(src), str(target))
    return target
