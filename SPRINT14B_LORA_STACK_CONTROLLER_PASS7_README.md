# Sprint 14B Pass 7 — LoRA Stack Controller

This pass extracts the remaining LoRA stack row/UI mutation behavior from `ImageGenerationPage` into `qt_ui/assets/LoraStackController`.

Behavior should remain unchanged:

- Add LoRA
- Clear stack
- Enable/disable entries
- Weight changes
- Replace entry
- Remove entry
- Move entries up/down
- T2I/I2I/T2V/I2V request payload behavior
- Generated video no-reload playback behavior

The page still owns the asset picker dialog because `CatalogPickerDialog` is currently local to `ImageGenerationPage.cpp`.
