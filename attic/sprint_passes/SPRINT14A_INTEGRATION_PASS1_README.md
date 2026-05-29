# Sprint 14A Integration Pass 1 — Media Preview Controller Wiring

This package wires `ImageGenerationPage` to the new preview controller scaffold.

Files included:

```text
qt_ui/ImageGenerationPage.cpp
qt_ui/ImageGenerationPage.h
qt_ui/preview/MediaPreviewController.cpp
qt_ui/preview/MediaPreviewController.h
qt_ui/preview/PreviewFileSettler.cpp
qt_ui/preview/PreviewFileSettler.h
docs/SPRINT14A_CMAKE_SNIPPET.txt
```

Expected behavior remains unchanged from `sprint13-video-preview-stable`:

- generated MP4s load once after file settling
- repeated same-path worker updates do not reload the video
- Play/Pause/Stop/Restart/Step/Seek still work
- busy/progress updates do not tear down the preview

Guardrails preserved:

- no `frameRateSpin_`
- no `Q_OBJECT` in a `.cpp` helper
- no media-status enum mismatch in `ImageGenerationPage`
- preview file-size / modified-time tracking now belongs to `MediaPreviewController`
