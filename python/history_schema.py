"""History record schema v2: core + per-mode payload.

v1 flattened image fields onto a video-shaped row (UI then stuffed steps into the
Duration column). v2 keeps a stable core and a `mode_payload` keyed by media
type. Readers must prefer `mode_payload` and fall back to the v1 top-level keys.
"""
from __future__ import annotations

from typing import Any

HISTORY_SCHEMA_VERSION = 2

IMAGE_MODES = frozenset({"t2i", "i2i"})
VIDEO_MODES = frozenset({"t2v", "i2v", "v2v", "ti2v"})
KNOWN_MODES = IMAGE_MODES | VIDEO_MODES


def normalize_mode(command: Any, media_type: Any = "") -> str:
    cmd = str(command or "").strip().lower()
    if cmd in KNOWN_MODES:
        return cmd
    media = str(media_type or "").strip().lower()
    return "t2v" if media == "video" else "t2i"


def attach_mode_payload(
    entry: dict[str, Any],
    *,
    media_type: str,
    command: Any,
    image_details: dict[str, Any] | None = None,
    video_details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mode = normalize_mode(command, media_type)
    payload: dict[str, Any] = {}
    if str(media_type).strip().lower() == "image":
        payload["image"] = dict(image_details or {})
    else:
        payload["video"] = dict(video_details or {})
    entry["schema_version"] = HISTORY_SCHEMA_VERSION
    entry["mode"] = mode
    entry["mode_payload"] = payload
    return entry


def mode_block(entry: dict[str, Any], kind: str) -> dict[str, Any]:
    payload = entry.get("mode_payload")
    if isinstance(payload, dict):
        block = payload.get(kind)
        if isinstance(block, dict):
            return block
    return {}


def detail_label(entry: dict[str, Any]) -> str:
    """Human column for the mode-aware Detail field (never borrow Duration)."""
    media = str(entry.get("media_type") or "").strip().lower()
    mode = str(entry.get("mode") or normalize_mode(entry.get("command"), media)).upper()
    if media == "image":
        image = mode_block(entry, "image")
        steps = image.get("image_steps", entry.get("image_steps"))
        if steps not in (None, ""):
            return f"{mode} • {steps} steps"
        return mode or "IMAGE"
    video = mode_block(entry, "video")
    duration = video.get("duration_label") or entry.get("video_duration_label") or entry.get("duration_label")
    if duration:
        return str(duration)
    return mode or "VIDEO"
