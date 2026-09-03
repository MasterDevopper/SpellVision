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


# `mode_block` and `detail_label` lived here until 2026-09-03 with NO production caller -- only their
# own tests. `detail_label` was a statement of the rule for what a history row's Detail column says,
# and the page that actually renders that column had hand-rolled the same rule inline. Two
# implementations, one tested and unused, one used and untested, agreeing by coincidence. The rule
# now lives once, in qt_ui/history/HistoryRowLabels.{h,cpp}, where it is rendered and where the
# ctest `history_row_labels` holds it. This module keeps what the WORKER needs: the mode vocabulary
# and the payload attach.
