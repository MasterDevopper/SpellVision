from __future__ import annotations

from runtime_adapters.base import RuntimeAdapter, RuntimeRequest, RuntimeResult


class NativeVideoAdapter(RuntimeAdapter):
    backend_kind = "native_python"

    def supports(self, request: RuntimeRequest) -> bool:
        return request.backend_kind == self.backend_kind and request.task_family == "video"

    def run(self, request: RuntimeRequest) -> RuntimeResult:
        raise NotImplementedError(
            f"Native video adapter stub for {request.model_family}/{request.command} is not wired yet"
        )
