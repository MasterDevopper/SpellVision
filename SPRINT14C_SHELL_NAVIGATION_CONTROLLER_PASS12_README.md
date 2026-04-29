# Sprint 14C Pass 12 — Shell Navigation Controller

Adds `qt_ui/shell/ShellNavigationController` and routes the first shell/navigation responsibilities out of `MainWindow`.

This pass moves:
- side rail button specs
- page context title mapping
- mode button checked-state presentation

`MainWindow` still owns the actual widgets and page-switching lifecycle. This keeps the patch narrow and behavior-preserving before returning to feature work.
