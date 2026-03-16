from __future__ import annotations

from runtime_adapters.base import RuntimeAdapter, RuntimeRequest, RuntimeResult


class DiffusersAdapter(RuntimeAdapter):
    backend_kind = "diffusers"

    def supports(self, request: RuntimeRequest) -> bool:
        return request.backend_kind == self.backend_kind

    def run(self, request: RuntimeRequest) -> RuntimeResult:
        raise NotImplementedError(
            f"Diffusers adapter stub for {request.model_family}/{request.command} is not wired yet"
        )
