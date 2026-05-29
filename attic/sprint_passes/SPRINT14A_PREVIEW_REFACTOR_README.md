# SpellVision Sprint 14A Preview Refactor Files

This package adds the first behavior-preserving refactor scaffolding for the Image Generation preview system.

## New files

```text
qt_ui/preview/PreviewFileSettler.h
qt_ui/preview/PreviewFileSettler.cpp
qt_ui/preview/MediaPreviewController.h
qt_ui/preview/MediaPreviewController.cpp
```

## Purpose

These files isolate the generated media preview lifecycle that currently lives inside `ImageGenerationPage`.

The controller is designed to preserve the known-good video behavior from `sprint13-video-preview-stable`:

- avoid same-path reload loops
- avoid tearing down `QMediaPlayer` during repeated status/result refreshes
- wait for MP4 outputs to settle before first load
- keep transport controls, speed, seek, loop, and caption updates together
- avoid placing `Q_OBJECT` in a `.cpp` file
- keep Qt media status handling inside a dedicated QObject header-managed class

## Integration note

This package intentionally adds new files only. It does not modify `ImageGenerationPage.cpp`, `ImageGenerationPage.h`, or `CMakeLists.txt` yet.

Next refactor pass should:

1. Add these `.cpp` files to the SpellVision target in `CMakeLists.txt`.
2. Include `qt_ui/preview/MediaPreviewController.h` from `ImageGenerationPage.h` or `.cpp`.
3. Create one `MediaPreviewController *mediaPreviewController_` member in `ImageGenerationPage`.
4. Bind existing preview widgets to the controller after the preview UI is constructed.
5. Replace page-level video methods with delegating wrappers.
6. Build and run before removing old page-level members.

## CMake entries to add later

```cmake
qt_ui/preview/PreviewFileSettler.cpp
qt_ui/preview/PreviewFileSettler.h
qt_ui/preview/MediaPreviewController.cpp
qt_ui/preview/MediaPreviewController.h
```
