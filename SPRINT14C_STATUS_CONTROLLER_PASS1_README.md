# Sprint 14C Pass 1 — Generation Status Controller

This pass extracts worker/status-result routing out of `ImageGenerationPage::applyWorkerMessage()` and into `GenerationStatusController`.

## Intent

`ImageGenerationPage` should not directly switch over raw worker message kinds. The page now supplies small UI bindings:

- set busy state
- route completed output to preview
- show worker problems

`GenerationStatusController` owns the worker-message status policy while preserving the existing behavior path.

## Expected behavior

- T2I status/progress/result handling remains unchanged.
- T2V status/progress/result handling remains unchanged.
- Queue/runtime/workflow messages are ignored at the page layer.
- Busy/progress updates still do not clear the active preview.
- Generated MP4 playback and no-reload behavior remain stable.
