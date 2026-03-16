from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def ensure_profile_root(root: str | Path) -> Path:
    path = Path(root)
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_profiles(root: str | Path) -> list[dict[str, Any]]:
    root_path = ensure_profile_root(root)
    profiles = []
    for path in sorted(root_path.rglob("profile.json")):
        try:
            profiles.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    return profiles


def load_profile(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
