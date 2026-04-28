# Sprint 14C Pass 9 — Queue UI Presenter

This pass introduces `spellvision::shell::QueueUiPresenter` as the first queue/details tray presentation extraction.

## Scope

- Adds `qt_ui/shell/QueueUiPresenter.h/.cpp`.
- Moves selected queue ID resolution into a reusable presenter helper.
- Moves active queue strip text composition into a reusable presenter helper.
- Provides reusable filter binding helpers for queue search/state controls.
- Keeps MainWindow responsible for owning the widgets and shell flow.

## Safety

This is a narrow behavior-preserving pass. It does not replace the queue table, queue model, queue manager, or tray layout. It only moves presentation helpers and delegates the easiest call sites first.
