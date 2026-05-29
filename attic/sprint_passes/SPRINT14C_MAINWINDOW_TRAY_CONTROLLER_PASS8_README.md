# Sprint 14C Pass 8 — MainWindow Tray Controller

Adds `qt_ui/shell/MainWindowTrayController` and wires `MainWindow::buildPersistentDocks()` through it.

This moves persistent dock construction out of the shell file while preserving the existing bottom utility widget, details/logs null ownership, dock chrome call, and queue dock behavior.

Smoke-test after applying:

1. App builds and launches.
2. Bottom utility tray appears.
3. Queue tab still opens and updates.
4. Details/logs tray actions still work.
5. T2I/T2V generation and playback behavior remain unchanged.
