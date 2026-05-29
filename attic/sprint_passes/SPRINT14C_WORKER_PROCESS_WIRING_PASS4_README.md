# Sprint 14C Pass 4 — Wire WorkerProcessController

This pass wires the reusable `WorkerProcessController` into `MainWindow::sendWorkerRequest()`.

## Intent

Move the direct synchronous `QProcess` command execution in `MainWindow` behind the workers-layer controller introduced in Pass 3.

## Behavior preserved

- Generate and Queue still route through `submitGenerationRequest()`.
- Worker payload shape stays unchanged.
- The response remains the last JSON object emitted by `worker_client.py`.
- stderr diagnostics are still surfaced through the existing `stderrText` path.
- T2I/T2V preview routing is unchanged.

## Files changed

- `qt_ui/MainWindow.cpp`

## Notes

The patch is applied through `scripts/refactors/apply_sprint14c_worker_process_controller_wiring_pass4.py` so it can safely operate on the current post-merge `MainWindow.cpp` without replacing unrelated shell or queue code.
