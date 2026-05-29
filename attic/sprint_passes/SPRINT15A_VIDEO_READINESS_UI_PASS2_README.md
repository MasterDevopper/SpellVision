# Sprint 15A Pass 2 — Video Readiness UI Diagnostics

Adds `VideoReadinessPresenter` and wires `ImageGenerationPage::readinessBlockReason()` to use the video readiness contract produced by `GenerationRequestBuilder`.

The pass surfaces T2V/I2V readiness warnings through the existing readiness path without changing worker execution or preview playback behavior.
