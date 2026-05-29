# Sprint 14B Request Builder Pass 2

This package extracts generation mode policy from `ImageGenerationPage` into a dedicated generation-layer component.

## New files

- `qt_ui/generation/GenerationModeState.h`
- `qt_ui/generation/GenerationModeState.cpp`

## Updated files

- `qt_ui/ImageGenerationPage.cpp`
- `qt_ui/ImageGenerationPage.h`

## Behavior target

This pass is behavior-preserving:

- T2I still maps to `t2i` and `Text to Image`.
- I2I still maps to `i2i` and requires image input.
- T2V still maps to `t2v` and is treated as video mode.
- I2V still maps to `i2v`, requires image input, and is treated as video mode.
- Strength control still follows image-input modes.

## Refactor result

`ImageGenerationPage` delegates mode key, title, image-input, video-mode, and strength-control decisions to `GenerationModeState` instead of hardcoding those policies directly in the page.

## Guardrails preserved

- No `frameRateSpin_` regression.
- No `QMediaPlayer::MediaStatus` signature added to `ImageGenerationPage`.
- No `Q_OBJECT` macro added to `.cpp` helper classes.
- Sprint 14A preview controllers and Sprint 14B request builder remain intact.
