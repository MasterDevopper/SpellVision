# Sprint 14B Pass 3 — Generation Result Router Extraction

This pass extracts completed-output preview routing decisions out of `ImageGenerationPage::setPreviewImage()` and into `qt_ui/generation/GenerationResultRouter`.

## New files

- `qt_ui/generation/GenerationResultRouter.h`
- `qt_ui/generation/GenerationResultRouter.cpp`

## Updated files

- `qt_ui/ImageGenerationPage.cpp`
- `qt_ui/ImageGenerationPage.h` is included as a consistency copy, but this pass does not require a header API change.

## Behavior preserved

- Empty result paths clear preview state.
- Image result paths stop video playback and route to image preview.
- Video result paths preserve the working Sprint 13/14A MP4 lifecycle.
- Same-path video result refreshes do not tear down `QMediaPlayer`.
- Repeated worker/status/result updates continue to avoid reload flicker.
- GIF remains treated as image for preview routing because it is recognized as an image path and the video route requires `video && !image`.

## Acceptance checks

- App builds.
- T2I preview still works.
- T2V generated MP4 loads once and plays in-app.
- No reload flicker returns.
- `ImageGenerationPage` no longer directly owns the path-to-preview route policy inside `setPreviewImage()`.
