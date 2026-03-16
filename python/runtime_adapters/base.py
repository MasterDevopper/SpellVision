from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


class AdapterExecutionError(RuntimeError):
    pass


@dataclass
class RuntimeRequest:
    command: str
    task_family: str
    media_type: str
    model: str
    model_family: str
    backend_kind: str
    output_path: str | None = None
    metadata_output: str | None = None
    job_id: str | None = None
    params: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.params.get(key, default)


ProgressCallback = Callable[[int, int, str | None], None]
StatusCallback = Callable[[str], None]
CancelCallback = Callable[[], bool]


@dataclass
class RuntimeContext:
    status_cb: StatusCallback | None = None
    progress_cb: ProgressCallback | None = None
    cancel_cb: CancelCallback | None = None
    working_dir: str | None = None
    env: dict[str, str] | None = None

    def status(self, message: str) -> None:
        if self.status_cb is not None:
            self.status_cb(message)

    def progress(self, step: int, total: int, message: str | None = None) -> None:
        if self.progress_cb is not None:
            self.progress_cb(step, total, message)

    def check_cancelled(self) -> None:
        if self.cancel_cb is not None and self.cancel_cb():
            raise AdapterExecutionError('Generation cancelled')


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

    def run(self, request: RuntimeRequest, context: RuntimeContext) -> RuntimeResult:
        ...
