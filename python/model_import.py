"""Paste-a-link model import.

Official base buttons stay the first-run fast path. This module inspects a
Hugging Face or Civitai URL into a catalog of versions/files so the user can
pick Anima vs Illustrious, v1 vs v17, or a high/low dual-noise pair. Import
copies into the user-chosen models root by asset type.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from credential_store import get_credential
from model_sources import materialize_asset, parse_asset_reference

TYPE_TO_SUBDIR = {
    "checkpoint": "checkpoints",
    "lora": "loras",
    "locon": "loras",
    "lycoris": "loras",
    "dora": "loras",
    "textualinversion": "embeddings",
    "hypernetwork": "hypernetworks",
    "controlnet": "controlnet",
    "vae": "vae",
    "upscaler": "upscale_models",
    "aestheticgradient": "aesthetic_gradients",
    "poses": "poses",
    "motionmodule": "animatediff_models",
    "wildcards": "wildcards",
}

FAMILY_ALIASES = {
    "anima": "anima",
    "illustrious": "illustrious",
    "illustrious xl": "illustrious",
    "pony": "pony",
    "noobai": "noobai",
    "sdxl": "sdxl",
    "sdxl 1.0": "sdxl",
    "sd 1.5": "sd1.5",
    "sd1.5": "sd1.5",
    "flux.1 d": "flux",
    "flux.1 s": "flux",
    "flux": "flux",
    "wan video": "wan",
    "wan": "wan",
    "hunyuan video": "hunyuan",
    "hunyuan": "hunyuan",
    "ltxv": "ltx",
    "ltx": "ltx",
    "krea 2": "krea2",
    "krea2": "krea2",
}


def dest_subdir(model_type: str, filename: str = "") -> str:
    name = str(filename or "").lower()
    if any(token in name for token in ("lora", "locon", "lycoris")):
        return "loras"
    if "vae" in name:
        return "vae"
    if any(token in name for token in ("_txt", "text_encoder", "umt5", "t5xxl", "clip_l", "clip_g", "qwen3vl")):
        return "text_encoders"
    if "clip_vision" in name or "clip-vision" in name:
        return "clip_vision"
    if "krea2" in name or name.startswith("krea-2") or name.startswith("krea_2"):
        return "diffusion_models"
    if "upscale" in name or "esrgan" in name or "swinir" in name or "ultrasharp" in name or name.startswith("4x-") or name.startswith("4x_"):
        return "upscale_models"
    if "controlnet" in name:
        return "controlnet"
    kind = str(model_type or "").strip().lower().replace(" ", "")
    return TYPE_TO_SUBDIR.get(kind, "checkpoints")


def noise_role(filename: str) -> str:
    name = str(filename or "").lower().replace("-", "_")
    if "high_noise" in name or "highnoise" in name:
        return "high"
    if "low_noise" in name or "lownoise" in name:
        return "low"
    return "single"


def family_hints(*parts: str, base_model: str = "") -> list[str]:
    canonical = FAMILY_ALIASES.get(str(base_model or "").strip().lower())
    if canonical:
        return [canonical]
    blob = " ".join(str(part or "") for part in parts).lower()
    found: list[str] = []
    for token, alias in FAMILY_ALIASES.items():
        if token in blob and alias not in found:
            found.append(alias)
    return found


def _file_entry(
    version_id: str,
    version_name: str,
    file_row: dict[str, Any],
    model_type: str,
    model_name: str,
    base_model: str = "",
) -> dict[str, Any]:
    filename = str(file_row.get("name") or "").strip()
    dest = dest_subdir(model_type, filename)
    entry = {
        "choice_id": f"{version_id}:{filename}",
        "version_id": str(version_id),
        "version_name": version_name,
        "filename": filename,
        "size_kb": file_row.get("sizeKB") or file_row.get("sizeKb") or 0,
        "download_url": str(file_row.get("downloadUrl") or (
            f"https://civitai.com/api/download/models/{version_id}?fileId={file_row.get('id')}"
            if file_row.get("id") else f"https://civitai.com/api/download/models/{version_id}"
        )),
        "model_type": model_type,
        "base_model": str(base_model or "").strip(),
        "dest_subdir": dest,
        "noise_role": noise_role(filename),
        "family_hints": family_hints(model_name, version_name, filename, base_model=base_model),
        "pair_with": [],
        "role": dest,
    }
    entry["dest_filename"] = dest_filename(entry, filename)
    return entry


def dest_filename(row: dict[str, Any], local_path: str) -> str:
    source = Path(local_path).name or str(row.get("filename") or "model.safetensors")
    stem = Path(source).stem
    suffix = Path(source).suffix or ".safetensors"
    family = ""
    hints = row.get("family_hints") or []
    if hints:
        family = str(hints[0]).strip().lower().replace(" ", "")
    if not family:
        family = str(row.get("base_model") or "").strip().lower().replace(" ", "")
    if family and family not in stem.lower():
        return f"{stem}_{family}{suffix}"
    return source


def _attach_pairs(choices: list[dict[str, Any]]) -> None:
    by_version: dict[str, list[dict[str, Any]]] = {}
    for choice in choices:
        by_version.setdefault(str(choice.get("version_id") or ""), []).append(choice)
    for group in by_version.values():
        highs = [row for row in group if row["noise_role"] == "high"]
        lows = [row for row in group if row["noise_role"] == "low"]
        if len(highs) == 1 and len(lows) == 1:
            highs[0]["pair_with"] = [lows[0]["choice_id"]]
            lows[0]["pair_with"] = [highs[0]["choice_id"]]
            highs[0]["pair_required"] = True
            lows[0]["pair_required"] = True


def inspect_model_url(
    url: str,
    *,
    civitai_get: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ref = parse_asset_reference(url, asset_type="model")
    if ref.kind in {"civitai_model_page", "civitai_model_version", "civitai_download_url"}:
        return _inspect_civitai(ref, civitai_get=civitai_get)
    if ref.kind == "hf_repo":
        filename = str(ref.filename or "")
        if not filename:
            return {
                "ok": True,
                "type": "model_import_catalog",
                "source": "huggingface",
                "needs_filename": True,
                "repo_id": ref.repo_id,
                "choices": [],
                "note": "Paste hf://org/repo/path/file or browse Hugging Face for the exact file.",
            }
        return {
            "ok": True,
            "type": "model_import_catalog",
            "source": "huggingface",
            "choices": [{
                "choice_id": f"hf:{ref.repo_id}:{filename}",
                "version_id": "main",
                "version_name": "main",
                "filename": Path(filename).name,
                "size_kb": 0,
                "download_url": f"hf://{ref.repo_id}/{filename}",
                "model_type": dest_subdir("", filename) if dest_subdir("", filename) != "checkpoints" else "checkpoint",
                "dest_subdir": dest_subdir("", filename),
                "noise_role": noise_role(filename),
                "family_hints": family_hints(ref.repo_id, filename),
                "pair_with": [],
            }],
        }
    return {"ok": False, "type": "model_import_catalog", "error": f"Unsupported URL kind {ref.kind!r}", "choices": []}


def _inspect_civitai(ref, *, civitai_get) -> dict[str, Any]:
    if civitai_get is None:
        from model_sources import _civitai_api_get_json
        civitai_get = lambda url: _civitai_api_get_json(
            url,
            civitai_api_key=get_credential("civitai_api_key"),
            timeout_sec=45,
        )
    model_id = ref.model_id
    if ref.kind == "civitai_download_url" and ref.model_version_id:
        version = civitai_get(f"https://civitai.com/api/v1/model-versions/{ref.model_version_id}")
        model_type = str((version.get("model") or {}).get("type") or "Checkpoint")
        model_name = str((version.get("model") or {}).get("name") or "")
        choices = [
            _file_entry(
                str(version.get("id") or ref.model_version_id),
                str(version.get("name") or ""),
                file_row,
                model_type,
                model_name,
                str(version.get("baseModel") or ""),
            )
            for file_row in (version.get("files") or [])
            if isinstance(file_row, dict)
        ]
        _attach_pairs(choices)
        return {"ok": True, "type": "model_import_catalog", "source": "civitai", "model_type": model_type, "choices": choices}

    if not model_id:
        return {"ok": False, "type": "model_import_catalog", "error": "Civitai URL has no model id", "choices": []}
    payload = civitai_get(f"https://civitai.com/api/v1/models/{model_id}")
    model_type = str(payload.get("type") or "Checkpoint")
    model_name = str(payload.get("name") or "")
    choices: list[dict[str, Any]] = []
    for version in payload.get("modelVersions") or []:
        if not isinstance(version, dict):
            continue
        version_id = str(version.get("id") or "")
        version_name = str(version.get("name") or version_id)
        if ref.model_version_id and version_id != str(ref.model_version_id):
            continue
        for file_row in version.get("files") or []:
            if isinstance(file_row, dict):
                choices.append(_file_entry(
                    version_id,
                    version_name,
                    file_row,
                    model_type,
                    model_name,
                    str(version.get("baseModel") or ""),
                ))
    _attach_pairs(choices)
    return {
        "ok": True,
        "type": "model_import_catalog",
        "source": "civitai",
        "model_id": model_id,
        "model_name": model_name,
        "model_type": model_type,
        "choices": choices,
    }


def import_model_choices(
    catalog: dict[str, Any],
    choice_ids: list[str],
    *,
    install_root: str,
    include_pairs: bool = True,
    materialize=None,
) -> dict[str, Any]:
    wanted = {str(item) for item in choice_ids}
    by_id = {str(row.get("choice_id")): row for row in (catalog.get("choices") or [])}
    if include_pairs:
        extra = set()
        for choice_id in list(wanted):
            row = by_id.get(choice_id) or {}
            extra.update(str(item) for item in (row.get("pair_with") or []))
        wanted.update(extra)
    if materialize is None:
        materialize = materialize_asset
    dest_root = Path(install_root)
    installed: list[str] = []
    results: list[dict[str, Any]] = []
    for choice_id in wanted:
        row = by_id.get(choice_id)
        if not row:
            results.append({"choice_id": choice_id, "ok": False, "error": "unknown choice"})
            continue
        ref = row.get("download_url") or ""
        asset = materialize(ref, asset_type=str(row.get("model_type") or "model").lower())
        local_path = getattr(asset, "local_path", None)
        if not local_path or not Path(local_path).is_file():
            results.append({"choice_id": choice_id, "ok": False, "error": "download failed"})
            continue
        dest_dir = dest_root / str(row.get("dest_subdir") or "checkpoints")
        dest_dir.mkdir(parents=True, exist_ok=True)
        target = dest_dir / dest_filename(row, local_path)
        if Path(local_path).resolve() != target.resolve():
            import shutil
            shutil.copy2(local_path, target)
        installed.append(str(target))
        results.append({"choice_id": choice_id, "ok": True, "installed_path": str(target), "dest_subdir": row.get("dest_subdir")})
    return {
        "ok": all(row.get("ok") for row in results) if results else False,
        "type": "model_import_result",
        "installed": installed,
        "results": results,
    }
