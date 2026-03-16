from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class RuntimeRequest:
    command: str
    task_family: str
    media_type: str
    model: str
    model_family: str
    backend_kind: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuntimeResult:
    ok: bool
    output: str | None = None
    metadata_output: str | None = None
    backend_name: str | None = None
    detected_pipeline: str | None = None
    task_type: str | None = None
    media_type: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class RuntimeAdapter(Protocol):
    backend_kind: str

    def supports(self, request: RuntimeRequest) -> bool:
        ...

    def run(self, request: RuntimeRequest) -> RuntimeResult:
        ...
