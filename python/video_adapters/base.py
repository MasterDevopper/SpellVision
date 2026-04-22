from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence
import copy

AUTO_TOKENS = {"", "auto", "automatic", "default", "family_default", "adapter_default"}


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
        if not isinstance(object_info, dict):
            return False
        if not self.required_nodes:
            return True
        return all(node in object_info for node in self.required_nodes)

    def prepare_request(self, req: dict[str, Any], object_info: dict[str, Any], *, command: str, family: str) -> AdapterPrepareResult:
        return AdapterPrepareResult(payload=copy.deepcopy(req), warnings=[])


def normalize_choice(value: Any) -> str:
    text = str(value or "").strip()
    if text.lower() in AUTO_TOKENS:
        return ""
    return text


def input_choices(object_info: dict[str, Any], class_name: str, input_name: str) -> list[str]:
    """Return ComfyUI enum choices for class/input using guard clauses.

    Comfy's /object_info shape is not guaranteed across custom node packs, so this
    function deliberately avoids chained optional access. That keeps Pylance quiet
    and prevents the adapter registry from exploding when a node is missing.
    """
    if not isinstance(object_info, dict):
        return []

    info = object_info.get(class_name)
    if not isinstance(info, dict):
        return []

    raw_input_info = info.get("input")
    if not isinstance(raw_input_info, dict):
        return []

    for bucket in ("required", "optional"):
        values = raw_input_info.get(bucket)
        if not isinstance(values, dict):
            continue

        spec = values.get(input_name)
        if not isinstance(spec, (list, tuple)) or not spec:
            continue

        first = spec[0]
        if isinstance(first, (list, tuple)):
            return [str(item).strip() for item in first if str(item).strip()]

    return []


def first_choices_for_aliases(object_info: dict[str, Any], class_name: str, input_names: Sequence[str]) -> tuple[str, list[str]]:
    for input_name in input_names:
        choices = input_choices(object_info, class_name, input_name)
        if choices:
            return input_name, choices
    return "", []


def choose_from_choices(
    choices: Sequence[str],
    requested: Any,
    preferred_defaults: Iterable[str] = (),
) -> tuple[str, bool]:
    by_lower = {str(choice).strip().lower(): str(choice).strip() for choice in choices if str(choice).strip()}

    requested_text = normalize_choice(requested)
    if requested_text:
        found = by_lower.get(requested_text.lower())
        if found:
            return found, False

    for default in preferred_defaults:
        default_text = normalize_choice(default)
        if not default_text:
            continue
        found = by_lower.get(default_text.lower())
        if found:
            return found, requested_text.lower() != found.lower()

    if choices:
        first = str(choices[0]).strip()
        return first, requested_text.lower() != first.lower()

    return requested_text, False


def choose_from_object_info(
    object_info: dict[str, Any],
    class_name: str,
    input_name: str,
    requested: Any,
    default: str = "",
    *,
    preferred_defaults: Iterable[str] = (),
) -> tuple[str, bool, list[str]]:
    choices = input_choices(object_info, class_name, input_name)
    ordered_defaults = tuple(item for item in (default, *tuple(preferred_defaults)) if str(item or "").strip())
    value, changed = choose_from_choices(choices, requested, ordered_defaults)
    return value, changed, choices


def choose_from_object_info_aliases(
    object_info: dict[str, Any],
    class_name: str,
    input_names: Sequence[str],
    requested: Any,
    *,
    preferred_defaults: Iterable[str] = (),
) -> tuple[str, bool, list[str], str]:
    input_name, choices = first_choices_for_aliases(object_info, class_name, input_names)
    value, changed = choose_from_choices(choices, requested, preferred_defaults)
    return value, changed, choices, input_name


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
        "sampler",
        "scheduler",
        "video_sampler",
        "video_scheduler",
    ):
        value = req.get(key)
        if value:
            parts.append(str(value))

    stack = stack_dict_from_request(req)
    for key, value in stack.items():
        if value:
            parts.append(f"{key}={value}")

    return " ".join(parts).lower().replace("\\", "/")
