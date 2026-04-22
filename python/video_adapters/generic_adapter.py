from __future__ import annotations

from typing import Any

from .base import AdapterPrepareResult, VideoFamilyAdapter


class GenericVideoAdapter(VideoFamilyAdapter):
    family = "generic"
    display_name = "Generic Comfy Video"
    required_nodes: tuple[str, ...] = ()

    def score(self, req: dict[str, Any], object_info: dict[str, Any], *, command: str, family: str) -> int:
        return 1

    def prepare_request(self, req: dict[str, Any], object_info: dict[str, Any], *, command: str, family: str) -> AdapterPrepareResult:
        payload = dict(req)
        payload.setdefault("native_video_adapter_family", self.family)
        return AdapterPrepareResult(payload=payload, warnings=[])
