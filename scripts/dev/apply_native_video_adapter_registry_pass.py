from __future__ import annotations

from pathlib import Path
import re
import textwrap

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPO_ROOT / "python"
ADAPTER_ROOT = PYTHON_ROOT / "video_adapters"

FILES: dict[str, str] = {
    "__init__.py": '''from .registry import available_video_adapters, select_native_video_adapter

__all__ = ["available_video_adapters", "select_native_video_adapter"]
''',
    "base.py": r'''from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import copy


@dataclass(slots=True)
class AdapterPrepareResult:
    payload: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


class VideoFamilyAdapter:
    family: str = "generic"
    display_name: str = "Generic Video"
    required_nodes: tuple[str, ...] = ()

    def score(self, req: dict[str, Any], object_info: dict[str, Any], *, command: str, family: str) -> int:
        return 0

    def is_available(self, object_info: dict[str, Any]) -> bool:
        if not self.required_nodes:
            return True
        return all(node in object_info for node in self.required_nodes)

    def prepare_request(self, req: dict[str, Any], object_info: dict[str, Any], *, command: str, family: str) -> AdapterPrepareResult:
        return AdapterPrepareResult(payload=copy.deepcopy(req), warnings=[])


def input_choices(object_info: dict[str, Any], class_name: str, input_name: str) -> list[str]:
    info = object_info.get(class_name) if isinstance(object_info, dict) else None
    if not isinstance(info, dict):
        return []

    input_info = info.get("input")
    if not isinstance(input_info, dict):
        return []

    for bucket in ("required", "optional"):
        values = input_info.get(bucket)
        if not isinstance(values, dict):
            continue

        spec = values.get(input_name)
        if not isinstance(spec, (list, tuple)) or not spec:
            continue

        first = spec[0]
        if isinstance(first, (list, tuple)):
            return [str(item).strip() for item in first if str(item).strip()]

    return []


def choose_from_object_info(
    object_info: dict[str, Any],
    class_name: str,
    input_name: str,
    requested: Any,
    default: str = "",
) -> tuple[str, bool, list[str]]:
    choices = input_choices(object_info, class_name, input_name)
    by_lower = {choice.lower(): choice for choice in choices}

    requested_text = str(requested or "").strip()
    if requested_text:
        found = by_lower.get(requested_text.lower())
        if found:
            return found, False, choices

    default_text = str(default or "").strip()
    if default_text:
        found = by_lower.get(default_text.lower())
        if found:
            return found, requested_text.lower() != found.lower(), choices

    if choices:
        return choices[0], requested_text.lower() != choices[0].lower(), choices

    return default_text, bool(requested_text and requested_text != default_text), choices


def stack_dict_from_request(req: dict[str, Any]) -> dict[str, Any]:
    for key in ("video_model_stack", "model_stack", "stack"):
        value = req.get(key)
        if isinstance(value, dict):
            return copy.deepcopy(value)
    return {}


def haystack_for_detection(req: dict[str, Any], family: str = "") -> str:
    parts: list[str] = [str(family or "")]

    for key in (
        "model",
        "model_path",
        "selected_model",
        "model_display",
        "model_family",
        "video_family",
        "family",
        "backend_kind",
        "stack_kind",
    ):
        value = req.get(key)
        if value:
            parts.append(str(value))

    stack = stack_dict_from_request(req)
    for key, value in stack.items():
        if value:
            parts.append(f"{key}={value}")

    return " ".join(parts).lower().replace("\\", "/")
''',
    "generic_adapter.py": r'''from __future__ import annotations

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
''',
    "wan_adapter.py": r'''from __future__ import annotations

from typing import Any

from .base import (
    AdapterPrepareResult,
    VideoFamilyAdapter,
    choose_from_object_info,
    haystack_for_detection,
    stack_dict_from_request,
)


class WanVideoAdapter(VideoFamilyAdapter):
    family = "wan"
    display_name = "WAN Video"
    required_nodes = (
        "WanVideoModelLoader",
        "LoadWanVideoT5TextEncoder",
        "WanVideoTextEncode",
        "WanVideoSampler",
        "WanVideoVAELoader",
        "WanVideoDecode",
    )

    def score(self, req: dict[str, Any], object_info: dict[str, Any], *, command: str, family: str) -> int:
        haystack = haystack_for_detection(req, family)
        if "wan" not in haystack and "wan2" not in haystack and "wan22" not in haystack:
            return 0
        if not self.is_available(object_info):
            return 0
        return 100

    def prepare_request(self, req: dict[str, Any], object_info: dict[str, Any], *, command: str, family: str) -> AdapterPrepareResult:
        payload = dict(req)
        warnings: list[str] = []

        payload["native_video_adapter_family"] = self.family
        payload["resolved_native_video_family"] = self.family
        payload["model_family"] = self.family
        payload["video_family"] = self.family
        payload.setdefault("backend_kind", "native_video")
        payload.setdefault("stack_kind", "split_stack")

        stack = stack_dict_from_request(payload)
        stack["family"] = self.family
        stack["model_family"] = self.family
        stack["video_family"] = self.family
        stack.setdefault("backend_kind", "native_video")
        stack.setdefault("stack_kind", "split_stack")
        payload["video_model_stack"] = stack
        payload["model_stack"] = stack

        scheduler, changed, choices = choose_from_object_info(
            object_info,
            "WanVideoSampler",
            "scheduler",
            payload.get("scheduler"),
            "unipc",
        )
        if scheduler:
            if changed:
                original = str(payload.get("scheduler") or "").strip() or "<empty>"
                warnings.append(
                    f"WAN scheduler '{original}' is not valid for WanVideoSampler; using '{scheduler}'."
                )
            payload["scheduler"] = scheduler

        sampler, sampler_changed, sampler_choices = choose_from_object_info(
            object_info,
            "WanVideoSampler",
            "sampler",
            payload.get("sampler"),
            "",
        )
        if sampler:
            if sampler_changed:
                original = str(payload.get("sampler") or "").strip() or "<empty>"
                warnings.append(
                    f"WAN sampler '{original}' is not valid for WanVideoSampler; using '{sampler}'."
                )
            payload["sampler"] = sampler

        payload["native_video_adapter_warnings"] = warnings
        payload["native_video_scheduler_choices"] = choices
        if sampler_choices:
            payload["native_video_sampler_choices"] = sampler_choices

        return AdapterPrepareResult(payload=payload, warnings=warnings)
''',
    "registry.py": r'''from __future__ import annotations

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
''',
}

HELPER = r'''

def _prepare_native_video_adapter_request(
    req: dict[str, Any],
    object_info: dict[str, Any],
    *,
    command: str,
    family: str,
) -> dict[str, Any]:
    """Apply the family adapter before native video prompt construction.

    This keeps generic image/sampler defaults from leaking into family-specific
    Comfy nodes, such as WAN's sampler scheduler vocabulary.
    """
    try:
        from video_adapters.registry import select_native_video_adapter
    except Exception as exc:
        adapted = dict(req)
        warnings = list(adapted.get("native_video_adapter_warnings") or [])
        warnings.append(f"Native video adapter registry unavailable: {exc}")
        adapted["native_video_adapter_warnings"] = warnings
        return adapted

    adapter = select_native_video_adapter(req, object_info, command=command, family=family)
    result = adapter.prepare_request(req, object_info, command=command, family=family)
    adapted = result.payload
    adapted["native_video_adapter_family"] = adapter.family
    if result.warnings:
        adapted["native_video_adapter_warnings"] = result.warnings
    return adapted
'''


def write_adapter_files() -> None:
    ADAPTER_ROOT.mkdir(parents=True, exist_ok=True)
    for name, content in FILES.items():
        (ADAPTER_ROOT / name).write_text(content, encoding="utf-8")


def patch_worker_service() -> None:
    path = PYTHON_ROOT / "worker_service.py"
    text = path.read_text(encoding="utf-8")

    if "def _prepare_native_video_adapter_request" not in text:
        marker = "\ndef run_native_split_stack_video("
        if marker not in text:
            raise SystemExit("Could not find run_native_split_stack_video marker in worker_service.py")
        text = text.replace(marker, HELPER + marker, 1)

    if "_prepare_native_video_adapter_request(req, object_info" not in text:
        pattern = re.compile(
            r'(?P<indent>\s*)workflow\s*=\s*_build_native_split_video_prompt\(\s*req,\s*object_info,\s*command=command,\s*family=family,\s*job_id=job\.job_id\s*\)'
        )
        match = pattern.search(text)
        if not match:
            raise SystemExit("Could not find native split-stack prompt construction call in worker_service.py")

        indent = match.group("indent")
        replacement = (
            f'{indent}req = _prepare_native_video_adapter_request(req, object_info, command=command, family=family)\n'
            f'{indent}family = str(req.get("resolved_native_video_family") or req.get("video_family") or req.get("model_family") or family)\n'
            f'{indent}workflow = _build_native_split_video_prompt(req, object_info, command=command, family=family, job_id=job.job_id)'
        )
        text = text[: match.start()] + replacement + text[match.end():]

    path.write_text(text, encoding="utf-8")


def main() -> None:
    write_adapter_files()
    patch_worker_service()
    print("Applied Native Video Adapter Registry pass.")
    print("Wrote python/video_adapters/* and patched worker_service.py prompt preparation.")


if __name__ == "__main__":
    main()
