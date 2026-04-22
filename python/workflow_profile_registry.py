from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def ensure_profile_root(root: str | Path) -> Path:
    path = Path(root)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_profile_with_paths(path: Path, root_path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None

    payload.setdefault("name", payload.get("profile_name") or path.parent.name)
    payload.setdefault("profile_path", str(path))
    payload.setdefault("import_root", str(path.parent))
    payload.setdefault("import_slug", path.parent.name)
    payload.setdefault("workflow_path", payload.get("workflow_source") or str(path.parent / "workflow.json"))

    capability = payload.get("capability_report")
    if not isinstance(capability, dict):
        capability = (payload.get("metadata") or {}).get("capability_report") if isinstance(payload.get("metadata"), dict) else None
    if isinstance(capability, dict):
        payload.setdefault("task_command", capability.get("primary_task") or payload.get("task_command"))
        payload.setdefault("media_type", capability.get("media_type") or payload.get("media_type"))
        payload.setdefault("supported_modes", capability.get("supported_modes") or [])
        payload.setdefault("classification_confidence", capability.get("confidence") or 0.0)

    return payload


def list_profiles(root: str | Path) -> list[dict[str, Any]]:
    root_path = ensure_profile_root(root)
    profiles: list[dict[str, Any]] = []
    for path in sorted(root_path.rglob("profile.json")):
        profile = _load_profile_with_paths(path, root_path)
        if profile is not None:
            profiles.append(profile)
    return profiles


def load_profile(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Profile is not a JSON object: {path}")
    return payload
