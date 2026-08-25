"""Pure request-shape helpers. No torch — safe for unit tests."""

from __future__ import annotations

from typing import Any


def resolve_request_lora(req: dict[str, Any]) -> tuple[str | None, float]:
    """Return (path, scale) from `lora`/`lora_scale` or the first enabled `loras[]` item."""
    raw = req.get("lora")
    if isinstance(raw, str) and raw.strip() and raw.strip().lower() != "none":
        try:
            scale = float(req.get("lora_scale", 1.0))
        except (TypeError, ValueError):
            scale = 1.0
        return raw.strip(), scale

    items = req.get("loras")
    if not isinstance(items, list):
        return None, 1.0
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("enabled") is False:
            continue
        path = item.get("path") or item.get("name") or item.get("value")
        if not isinstance(path, str) or not path.strip():
            continue
        weight = item.get("weight", item.get("strength", 1.0))
        try:
            scale = float(weight)
        except (TypeError, ValueError):
            scale = 1.0
        return path.strip(), scale
    return None, 1.0


def studio_effective_mode(requested: str, payload: dict[str, Any]) -> str:
    mode = (requested or "t2i").strip().lower() or "t2i"
    image = payload.get("input_image")
    if mode == "t2i" and isinstance(image, str) and image.strip():
        return "i2i"
    return mode
