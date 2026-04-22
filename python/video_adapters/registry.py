from __future__ import annotations

from typing import Any

from .base import VideoFamilyAdapter
from .generic_adapter import GenericVideoAdapter
from .wan_adapter import WanVideoAdapter


def available_video_adapters() -> list[VideoFamilyAdapter]:
    return [WanVideoAdapter(), GenericVideoAdapter()]


def select_native_video_adapter(
    req: dict[str, Any],
    object_info: dict[str, Any],
    *,
    command: str,
    family: str,
) -> VideoFamilyAdapter:
    adapters = available_video_adapters()
    best = adapters[-1]
    best_score = -1

    for adapter in adapters:
        score = adapter.score(req, object_info, command=command, family=family)
        if score > best_score:
            best = adapter
            best_score = score

    return best
