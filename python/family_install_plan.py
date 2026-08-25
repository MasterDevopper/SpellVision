"""Family-slot install plan producer (Doc 19).

Workflow-scan install plans already exist. This producer reads COMPONENT_MANIFEST
slots + optional `source` rows and emits fetch/review/already_present without
walking a Comfy graph.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from model_dependency_manifest import COMPONENT_MANIFEST
from model_registry import family_license_info


def _basenames(present: Iterable[str] | None) -> set[str]:
    out: set[str] = set()
    for item in present or ():
        name = Path(str(item)).name.strip().lower()
        if name:
            out.add(name)
    return out


def _preferred_names(slot: dict[str, Any]) -> list[str]:
    preferred = slot.get("preferred") or []
    if preferred:
        return [str(name) for name in preferred]
    by_variant = slot.get("preferred_by_variant") or {}
    names: list[str] = []
    for group in by_variant.values():
        names.extend(str(name) for name in group)
    return names


def _slot_applies(slot: dict[str, Any], task: str) -> bool:
    tasks = slot.get("applies_to_tasks")
    if not tasks:
        return True
    return str(task or "").strip().lower() in {str(item).strip().lower() for item in tasks}


def _fetch_ref(slot: dict[str, Any]) -> str:
    source = slot.get("source") or {}
    repo = str(source.get("hf_repo") or "").strip()
    path = str(source.get("path") or "").strip()
    if repo and path:
        return f"hf://{repo}/{path}"
    return ""


def build_family_install_plan(
    family: str,
    *,
    task: str = "t2v",
    present_basenames: Iterable[str] | None = None,
) -> dict[str, Any]:
    family_id = str(family or "").strip().lower()
    task_id = str(task or "").strip().lower() or "t2v"
    present = _basenames(present_basenames)
    license_info = family_license_info(family_id)
    allow_auto = bool(license_info.get("commercial_use", True))
    row = COMPONENT_MANIFEST.get(family_id) or {}
    slots = row.get("slots") or {}
    items: list[dict[str, Any]] = []

    for slot_name, slot in slots.items():
        if not isinstance(slot, dict) or not _slot_applies(slot, task_id):
            continue
        if slot.get("is_primary"):
            continue
        preferred = _preferred_names(slot)
        matched = next((name for name in preferred if name.lower() in present), "")
        fetch_ref = _fetch_ref(slot)
        required = bool(slot.get("required"))
        if matched:
            action = "already_present"
        elif fetch_ref and allow_auto:
            action = "fetch"
        else:
            action = "review"
        items.append({
            "component": slot_name,
            "required": required,
            "preferred": preferred,
            "present_match": matched,
            "fetch_ref": fetch_ref,
            "install_action": action,
            "source_kind": "official_base" if fetch_ref else "",
            "browse_url": f"https://huggingface.co/{str((slot.get('source') or {}).get('hf_repo') or '').strip()}" if fetch_ref else "https://huggingface.co/models",
            "license_note": "" if allow_auto else str(license_info.get("license_note") or "non-commercial"),
        })

    missing = [item["component"] for item in items if item["install_action"] != "already_present" and item["required"]]
    return {
        "ok": True,
        "type": "family_install_plan",
        "family": family_id,
        "task": task_id,
        "commercial_use": allow_auto,
        "slots": items,
        "missing_required": missing,
        "fetchable": [item["fetch_ref"] for item in items if item["install_action"] == "fetch"],
    }


def apply_family_install_plan(
    plan: dict[str, Any] | None,
    *,
    dry_run: bool = True,
    cache_root: str | None = None,
    install_root: str | None = None,
    only_components: Iterable[str] | None = None,
    materialize=None,
) -> dict[str, Any]:
    """Materialize fetchable slots. dry_run is the default — never surprise-download."""
    plan = plan or {}
    slots = list(plan.get("slots") or [])
    results: list[dict[str, Any]] = []
    if materialize is None:
        from model_sources import materialize_asset
        materialize = materialize_asset

    dest_root = Path(install_root).expanduser() if install_root else None
    wanted = {str(name).strip().lower() for name in (only_components or ()) if str(name).strip()}
    subdirs = {
        "vae": "vae",
        "text_encoder": "text_encoders",
        "clip_vision": "clip_vision",
        "lora": "loras",
        "primary": "checkpoints",
        "unet_turbo": "diffusion_models",
        "unet_raw": "diffusion_models",
    }

    for slot in slots:
        action = str(slot.get("install_action") or "")
        ref = str(slot.get("fetch_ref") or "")
        component = str(slot.get("component") or "")
        if wanted and component.lower() not in wanted:
            results.append({
                "component": component,
                "ok": True,
                "skipped": True,
                "install_action": action or "skipped",
                "fetch_ref": ref,
            })
            continue
        if action != "fetch" or not ref:
            results.append({
                "component": component,
                "ok": action == "already_present",
                "skipped": True,
                "install_action": action,
                "fetch_ref": ref,
            })
            continue
        if dry_run:
            results.append({
                "component": component,
                "ok": True,
                "skipped": False,
                "dry_run": True,
                "install_action": action,
                "fetch_ref": ref,
            })
            continue
        asset = materialize(ref, asset_type=component or "model", cache_root=cache_root)
        local_path = getattr(asset, "local_path", None)
        installed = ""
        if dest_root and local_path and Path(local_path).is_file():
            dest_dir = dest_root / subdirs.get(component, "checkpoints")
            dest_dir.mkdir(parents=True, exist_ok=True)
            target = dest_dir / Path(local_path).name
            if Path(local_path).resolve() != target.resolve():
                import shutil
                shutil.copy2(local_path, target)
            installed = str(target)
        results.append({
            "component": component,
            "ok": bool(local_path or (getattr(asset, "resolved_kind", "") == "downloaded_file")),
            "skipped": False,
            "dry_run": False,
            "install_action": action,
            "fetch_ref": ref,
            "local_path": local_path,
            "installed_path": installed,
            "resolved_kind": getattr(asset, "resolved_kind", ""),
        })

    fetched = [row for row in results if not row.get("skipped") and not row.get("dry_run") and row.get("ok")]
    return {
        "ok": True,
        "type": "family_install_apply",
        "family": plan.get("family", ""),
        "dry_run": dry_run,
        "results": results,
        "fetched": [row["fetch_ref"] for row in fetched],
        "would_fetch": [row["fetch_ref"] for row in results if row.get("dry_run")],
        "installed": [row.get("installed_path") for row in fetched if row.get("installed_path")],
    }
