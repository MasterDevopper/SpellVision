# Sprint 14B Pass 6 — Model / LoRA stack state helpers

This pass introduces `qt_ui/assets/ModelStackState.*` as a behavior-preserving extraction point for model and LoRA stack state logic.

## What moved

- LoRA stack entry storage type now lives in `spellvision::assets::LoraStackEntry`.
- `ImageGenerationPage::LoraStackEntry` remains available as a type alias for compatibility.
- First-enabled LoRA resolution moved to `ModelStackState::firstEnabledLoraValue`.
- Enabled LoRA count moved to `ModelStackState::enabledLoraCount`.
- Add/update LoRA stack behavior moved to `ModelStackState::upsertLora`.
- Summary text generation moved to `ModelStackState::summaryText`.

## What intentionally did not change

- Picker dialogs still live in `ImageGenerationPage` for now.
- Model catalog scanning still lives in `ImageGenerationPage` for now.
- Video stack component controls still live in `ImageGenerationPage` for now.
- Payload shape, queue behavior, T2I/I2I/T2V/I2V behavior, and preview behavior are unchanged.
