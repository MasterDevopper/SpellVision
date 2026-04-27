# Sprint 14A Integration Pass 2 - Image Preview Controller

This pass continues the behavior-preserving preview refactor. It introduces `ImagePreviewController` and moves image pixmap caching/rendering state out of `ImageGenerationPage`.

## Adds

- `qt_ui/preview/ImagePreviewController.h`
- `qt_ui/preview/ImagePreviewController.cpp`

## Preserved behavior

- T2I preview still renders through the image page.
- T2V preview still routes through `MediaPreviewController`.
- The sprint13/sprint14a pass1 video lifecycle remains intact: no busy-state teardown and no same-path reload loop for healthy MP4s.
- `ImageGenerationPage` keeps generation/result ownership for now, but no longer owns pixmap cache/fingerprint state.
