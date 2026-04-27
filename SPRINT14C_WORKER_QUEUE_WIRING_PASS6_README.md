# Sprint 14C Pass 6 — Wire WorkerQueueController into MainWindow

This pass wires the scaffolded `WorkerQueueController` into `MainWindow` without replacing the full shell file.

It moves ownership of queue polling and queue response application behind the workers-layer controller while preserving the current UI update behavior:

- `queue_status` polling still runs every 1800 ms.
- `MainWindow::pollWorkerQueueStatus()` becomes a thin wrapper.
- `MainWindow::applyWorkerQueueResponse()` becomes a thin wrapper.
- Queue snapshot application still updates previews and bottom telemetry.
- Existing generation and queue submission behavior remains unchanged.

The included Python patch script edits only `qt_ui/MainWindow.h` and `qt_ui/MainWindow.cpp`.
