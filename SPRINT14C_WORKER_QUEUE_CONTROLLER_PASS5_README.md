# Sprint 14C Pass 5 — Worker Queue Controller scaffold

This pass introduces `WorkerQueueController` as the focused home for worker queue polling and queue snapshot application.

The scaffold is intentionally narrow and build-safe. It does not replace the current `MainWindow` queue path yet. The next pass should bind `MainWindow::sendWorkerRequest`, `QueueManager`, logging, telemetry sync, and preview sync through this controller.

## New files

- `qt_ui/workers/WorkerQueueController.h`
- `qt_ui/workers/WorkerQueueController.cpp`

## Responsibilities prepared

- Build the `queue_status` worker request.
- Poll the worker through a bound request sender.
- Normalize queue snapshot response shapes.
- Apply snapshots to `QueueManager`.
- Emit/log queue poll failures.
- Provide start/stop polling lifecycle around an internal `QTimer`.
