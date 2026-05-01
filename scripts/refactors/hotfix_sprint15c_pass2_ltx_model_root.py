from pathlib import Path

path = Path("python/video_family_readiness.py")
text = path.read_text(encoding="utf-8")

old = '''def _default_comfy_root(asset_root: Path) -> Path:
    raw = os.environ.get("SPELLVISION_COMFY_ROOT") or os.environ.get("COMFYUI_ROOT")
    if raw:
        return Path(raw).expanduser()
    return asset_root / "comfy_runtime" / "ComfyUI"


def _default_model_root(asset_root: Path) -> Path:
    raw = os.environ.get("SPELLVISION_MODELS_ROOT") or os.environ.get("AI_MODELS_ROOT")
    if raw:
        return Path(raw).expanduser()
    return asset_root / "models"
'''

new = '''def _default_comfy_root(asset_root: Path) -> Path:
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
'''

if old not in text:
    raise SystemExit("Expected root helper block not found; inspect python/video_family_readiness.py before patching.")

text = text.replace(old, new)
path.write_text(text, encoding="utf-8")
print("Patched readiness root helpers to ignore unresolved model/comfy env placeholders.")
