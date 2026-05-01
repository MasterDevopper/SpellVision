from pathlib import Path
import re

path = Path("python/video_family_readiness.py")
text = path.read_text(encoding="utf-8")

old = '''def _default_asset_root() -> Path:
    raw = os.environ.get("SPELLVISION_ASSET_ROOT") or os.environ.get("AI_ASSETS_ROOT") or "D:/AI_ASSETS"
    return Path(raw).expanduser()
'''

new = '''def _unresolved_path_token(value: object) -> bool:
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
'''

if old not in text:
    raise SystemExit("Expected _default_asset_root block not found; inspect python/video_family_readiness.py before patching.")

text = text.replace(old, new)
text = text.replace("asset_root = _default_asset_root()", "asset_root = _default_asset_root(runtime_status)")

path.write_text(text, encoding="utf-8")
print("Patched video_family_readiness.py asset root resolution.")
