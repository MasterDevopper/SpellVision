# Sprint 15A Pass 1 — Video Generation Policy Contract

Adds `VideoGenerationPolicy` under `qt_ui/generation` and routes video payloads through it from `GenerationRequestBuilder`.

This pass prepares the final T2V/I2V feature work by making every video request carry explicit readiness and diagnostic fields:

- `video_request_kind`
- `video_requires_input_image`
- `video_has_input_image`
- `video_has_workflow_binding`
- `video_has_native_stack`
- `video_stack_ready`
- `video_duration_label`
- `video_readiness_ok`
- `video_diagnostic_summary`
- `video_readiness_warnings`

The pass is intentionally low-risk: it does not change worker execution behavior yet. It makes the UI/backend contract more explicit before the next passes harden I2V input handling and native video worker execution.
