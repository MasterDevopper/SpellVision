"""Delete one model file, and only one that is ours to delete.

The Models page had no delete at all. Adding one means the worker will unlink whatever path the UI
names, so the path is checked against the one place models are allowed to live: the configured
models root (SPELLVISION_MODELS, the same value RuntimeProfile exports to this process). Outside
it, refused. No root configured, refused -- fail closed, because "delete anywhere" is not a feature
a missing setting should switch on.

Symlinks are refused rather than followed: unlinking a link is harmless, but a UI that shows the
link's target as the model would have just deleted something it did not display. Directories are
refused -- a model is a file. The sidecars ModelSidecar.cpp reads go with the file, so the library
cannot show a ghost with a preview and no weights.

Local-only by construction: the command is not in worker_auth.INTEGRATION_COMMANDS.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

MODEL_SUFFIXES: frozenset[str] = frozenset({
    ".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf", ".onnx",
})
# What ModelSidecar.cpp looks for beside <stem>: metadata, previews, video preview.
SIDECAR_SUFFIXES: tuple[str, ...] = (
    ".metadata.json", ".json", ".civitai.info", ".png", ".jpg", ".jpeg", ".webp", ".mp4",
)


def models_root() -> Path | None:
    """The configured models root, or None. Read through runtime_paths so this is the same value
    the rest of the worker uses, not a second env read."""
    try:
        from runtime_paths import RuntimePaths

        root = RuntimePaths.MODELS
    except Exception:
        root = None
    if not root:
        return None
    try:
        return Path(root).expanduser().resolve()
    except (OSError, RuntimeError):
        return None


def _is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def plan_delete(path_value: str, root: Path | None = None) -> dict[str, Any]:
    """Decide, without touching anything, whether ``path_value`` may be deleted and what goes with it.

    Returns ``{"ok": bool, "error": str, "target": str, "sidecars": [str]}``. Kept separate from
    the deletion so the refusal reasons are testable on their own and the UI can show what WILL be
    removed before it is.
    """
    root = root if root is not None else models_root()
    raw = str(path_value or "").strip()
    if not raw:
        return {"ok": False, "error": "No model path was given.", "target": "", "sidecars": []}
    if root is None:
        return {"ok": False, "target": raw, "sidecars": [],
                "error": "No models root is configured (SPELLVISION_MODELS), so the worker cannot "
                         "tell which files are models. Refusing to delete."}
    try:
        target = Path(raw).expanduser()
        resolved = target.resolve()
    except (OSError, RuntimeError) as exc:
        return {"ok": False, "error": f"Cannot resolve that path: {exc}", "target": raw, "sidecars": []}
    if target.is_symlink():
        return {"ok": False, "target": raw, "sidecars": [],
                "error": "That entry is a link, not a file. Refusing: the library showed the link's "
                         "target, and deleting the link would remove something it did not show."}
    if not _is_within(resolved, root):
        return {"ok": False, "target": str(resolved), "sidecars": [],
                "error": f"That file is outside the models root ({root}). Only files under the "
                         f"models root can be deleted from here."}
    if not resolved.is_file():
        return {"ok": False, "target": str(resolved), "sidecars": [],
                "error": "That path is not a regular file. A model is a file; directories are not "
                         "deleted from here."}
    if resolved.suffix.lower() not in MODEL_SUFFIXES:
        return {"ok": False, "target": str(resolved), "sidecars": [],
                "error": f"{resolved.name} does not have a model extension "
                         f"({', '.join(sorted(MODEL_SUFFIXES))}). Refusing."}
    stem = resolved.with_suffix("")
    sidecars = [str(p) for p in (Path(str(stem) + suffix) for suffix in SIDECAR_SUFFIXES)
                if p.is_file() and not p.is_symlink() and _is_within(p.resolve(), root)]
    return {"ok": True, "error": "", "target": str(resolved), "sidecars": sidecars}


def delete_model(path_value: str, root: Path | None = None) -> dict[str, Any]:
    plan = plan_delete(path_value, root)
    if not plan["ok"]:
        return {"type": "model_delete_result", "ok": False, "action": "delete_model",
                "path": plan["target"], "deleted": [], "error": plan["error"]}
    deleted: list[str] = []
    errors: list[str] = []
    for item in [plan["target"], *plan["sidecars"]]:
        try:
            os.remove(item)
            deleted.append(item)
        except OSError as exc:
            errors.append(f"{item}: {exc}")
    return {"type": "model_delete_result", "ok": not errors, "action": "delete_model",
            "path": plan["target"], "deleted": deleted,
            "error": "; ".join(errors) if errors else ""}
