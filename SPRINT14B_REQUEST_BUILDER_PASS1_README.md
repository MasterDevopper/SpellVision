# Sprint 14B Request Builder Pass 1

This package extracts the JSON payload assembly from `ImageGenerationPage::buildRequestPayload()` into a focused request-building component.

## New files

- `qt_ui/generation/GenerationRequestBuilder.h`
- `qt_ui/generation/GenerationRequestBuilder.cpp`

## Updated files

- `qt_ui/ImageGenerationPage.cpp`
- `qt_ui/ImageGenerationPage.h`

## Behavior target

This pass is intended to be behavior-preserving:

- T2I request payload keys remain unchanged.
- I2I request payload keys remain unchanged.
- T2V/I2V video payload keys remain unchanged.
- LoRA stack payload shape remains unchanged.
- Workflow draft payload keys remain unchanged.
- Output and metadata path behavior remains owned by the existing page/worker flow.

## Refactor result

`ImageGenerationPage` still reads UI state, but no longer owns the low-level JSON assembly rules. It creates a `GenerationRequestDraft` and delegates final payload construction to `GenerationRequestBuilder`.

## Guardrails preserved

- No `frameRateSpin_` regression.
- No `QMediaPlayer::MediaStatus` signature added to `ImageGenerationPage`.
- No `Q_OBJECT` macro added to `.cpp` helper classes.
- Existing Sprint 14A preview controllers are untouched.
