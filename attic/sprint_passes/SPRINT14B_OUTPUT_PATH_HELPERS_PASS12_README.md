# Sprint 14B Pass 12 — Output Path Helpers

This pass extracts output-path and metadata-path helper behavior from `ImageGenerationPage.cpp` into `qt_ui/generation/OutputPathHelpers.*`.

## New ownership

`OutputPathHelpers` now owns:

- Comfy output-folder discovery
- image/video output extension classification
- output-folder normalization
- output-prefix sanitization
- metadata sidecar path derivation
- persisted latest generated image/video output paths
- staged I2I input path persistence

## Behavior preserved

`ImageGenerationPage` still exposes its existing page-level methods, but those methods now delegate to the generation helper layer.
