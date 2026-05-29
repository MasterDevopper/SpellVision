# Sprint 14B Pass 9 — Extract Catalog Picker Dialog

This pass moves the catalog asset picker dialog out of `ImageGenerationPage.cpp` and into `qt_ui/assets/CatalogPickerDialog.*`.

## Extracted responsibility

- `CatalogEntry` asset-row data structure
- `CatalogPickerDialog` search/recent/detail browsing UI
- `persistRecentSelection()` recent-picker persistence helper

## Behavior intent

Behavior should remain unchanged. `ImageGenerationPage` still owns the page-level picker actions, but the reusable asset-picker UI now lives in the assets layer.

## Regression checks

- Checkpoint picker still opens and selects models.
- LoRA picker still opens and selects LoRAs.
- Replace LoRA picker still works.
- Recent selections still persist.
- T2I/T2V generation and generated MP4 playback still work.
