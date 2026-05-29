# Sprint 14B Pass 10 — Extract local widget helpers

This pass moves the remaining local layout helper widgets out of `ImageGenerationPage.cpp` and into reusable widget files:

- `spellvision::widgets::DropTargetFrame`
- `spellvision::widgets::ClickOnlyComboBox`

The behavior is intended to be unchanged:

- drag/drop image input still works through `DropTargetFrame`
- combo boxes still ignore mouse wheel changes unless their popup is open
- `ImageGenerationPage` keeps page layout ownership, but no longer owns these reusable widget implementations

No `Q_OBJECT` macro is introduced in the new helper classes.
