# Sprint 14B Pass 11 — Section / Card Widget Helper Extraction

This pass extracts repeated section-card and small styling helpers from `ImageGenerationPage.cpp` into reusable widget helpers under `qt_ui/widgets`.

## Added

- `qt_ui/widgets/SectionCardWidgets.h`
- `qt_ui/widgets/SectionCardWidgets.cpp`

## Moved out of ImageGenerationPage.cpp

- `createCard(...)`
- `createSectionTitle(...)`
- `createSectionBody(...)`
- `repolishWidget(...)`
- `makeCollapsibleSection(...)`

## Behavior

This is intended to be behavior-neutral. It only moves helper construction/styling functions into the widgets layer while preserving generated image/video preview, catalog picker, LoRA stack, and generation flows.
