"""Worker commands for model intelligence.

Four commands, each a thin adapter over `model_intelligence`: read what we know about one weight,
refresh a library, record a user override, and resolve the settings a model wants (which is what
W2's generation pages ask for on every checkpoint change).

`model_intel_refresh` can run for the better part of an hour on a full library, so it accepts a
`roots` subset and reports progress through the emitter rather than only at the end.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from model_intelligence import (
    family_seed_table,
    hashing,
    previews,
    readable_roots,
    recommended,
    sidecar,
)
from model_intelligence.civitai_lookup import DEFAULT_HOST, CivitaiClient
from model_intelligence.refresh import RefreshJob


def _weight_path(req: dict[str, Any]) -> Path | None:
    text = str(req.get("path") or "").strip()
    if not text:
        return None
    path = Path(text)
    if path.suffix.lower() not in hashing.MODEL_EXTENSIONS:
        return None
    return path


def handle_model_intel_get_command(req: dict[str, Any]) -> dict[str, Any]:
    path = _weight_path(req)
    if path is None:
        return {"ok": False, "type": "model_intel", "error": "path is not a model file"}
    payload = sidecar.read(path)
    return {
        "ok": True,
        "type": "model_intel",
        "path": str(path),
        "sidecar": payload,
        "recommended": (payload or {}).get("recommended") or {},
    }


def handle_model_recommended_settings_command(req: dict[str, Any]) -> dict[str, Any]:
    path = _weight_path(req)
    family = str(req.get("family") or "").strip() or None
    warnings: list[str] = []

    payload = sidecar.read(path) if path is not None else None
    if payload:
        settings = dict(payload.get("recommended") or {})
        family = family or ((payload.get("identity") or {}).get("family"))
    else:
        settings = {}
        if path is not None:
            warnings.append("no sidecar yet; run model_intel_refresh to identify this model")

    if family:
        variant = "turbo" if "turbo" in str(path or "").lower() else None
        for field, value in family_seed_table.seed_for(family, variant).items():
            settings.setdefault(field, {
                "value": value, "provenance": "table:family-default",
                "confidence": 1.0, "n": None, "total": None,
            })

    return {
        "ok": True,
        "type": "model_recommended_settings",
        "path": str(path) if path else "",
        "family": family,
        "settings": settings,
        "warnings": warnings,
    }


def handle_model_intel_set_user_command(req: dict[str, Any]) -> dict[str, Any]:
    path = _weight_path(req)
    if path is None:
        return {"ok": False, "type": "model_intel_set_user", "error": "path is not a model file"}

    payload = sidecar.read(path) or {
        "schema": sidecar.SCHEMA, "identity": {}, "display": {}, "recommended": {},
        "user": {"notes": "", "favorite": False},
    }
    display = dict(payload.get("display") or {})
    changed: list[str] = []

    name = str(req.get("name") or "").strip()
    if name:
        display["name"] = {"value": name, "user_override": True}
        changed.append("name")

    picture = str(req.get("picture") or "").strip()
    if picture:
        try:
            previews.set_user_picture(path, picture)
        except OSError as exc:
            return {"ok": False, "type": "model_intel_set_user", "error": str(exc)}
        images = list(display.get("images") or [])
        if images:
            images[0] = {**images[0], "user_override": True}
        display["images"] = images
        changed.append("picture")

    notes = req.get("notes")
    if isinstance(notes, str):
        payload["user"] = {**(payload.get("user") or {}), "notes": notes}
        changed.append("notes")

    settings = req.get("settings")
    if isinstance(settings, dict):
        wanted = dict(payload.get("recommended") or {})
        for field, value in settings.items():
            if field in recommended.FIELDS:
                wanted[field] = {"value": value, "provenance": "user", "confidence": 1.0,
                                 "n": None, "total": None}
                changed.append(f"settings.{field}")
        payload["recommended"] = wanted

    payload["display"] = display
    try:
        sidecar.write(path, payload)
    except OSError as exc:
        return {"ok": False, "type": "model_intel_set_user", "error": str(exc)}

    return {"ok": True, "type": "model_intel_set_user", "path": str(path), "changed": changed}


def handle_model_intel_refresh_command(req: dict[str, Any], emitter: Any = None) -> dict[str, Any]:
    roots = [str(r) for r in (req.get("roots") or []) if str(r).strip()]
    if not roots:
        return {"ok": False, "type": "model_intel_refresh", "error": "roots is required"}

    host = str(req.get("civitai_host") or DEFAULT_HOST)
    api_key = req.get("civitai_api_key")
    if not api_key:
        try:
            from credential_store import get_credential

            api_key = get_credential("civitai_api_key")
        except Exception:
            api_key = None

    def progress(done: int, total: int, name: str) -> None:
        if emitter is not None:
            emitter.emit({
                "ok": True, "type": "model_intel_progress",
                "current": done, "total": total, "message": name,
                "percent": int(100 * done / total) if total else 0,
            })

    try:
        client = CivitaiClient(host=host, api_key=api_key)
    except ValueError as exc:
        # A bad host is a refusal, not a crash -- it can arrive here from a settings field the
        # user typed into, not just from code that already validated it.
        return {"ok": False, "type": "model_intel_refresh", "error": str(exc)}

    job = RefreshJob(
        roots,
        client=client,
        models_root=req.get("models_root") or roots[0],
        progress=progress,
        force=bool(req.get("force")),
    )
    result = job.run()
    result["type"] = "model_intel_refresh"
    return result


def handle_model_roots_status_command(req: dict[str, Any]) -> dict[str, Any]:
    roots = [str(r) for r in (req.get("roots") or []) if str(r).strip()]
    return {
        "ok": True,
        "type": "model_roots_status",
        "roots": [readable_roots.root_status(root) for root in roots],
    }
