# Sprint 15C Pass 28 — Stable Queue Completion and Preview Rebind Guard

Fixes post-completion state instability after successful T2I jobs.

Files changed:

- `qt_ui/QueueManager.cpp`
- `qt_ui/workers/WorkerQueueController.cpp`
- `qt_ui/MainWindow.cpp`
- `qt_ui/MainWindow.h`
- `qt_ui/ImageGenerationPage.cpp`

Fixes:

- Queue item identity now falls back to `id`, `job_id`, `worker_job_id`, and `source_job_id` when `queue_item_id` is missing.
- LTX registry queue items now publish `queue_item_id` directly.
- Completed/failed/cancelled queue items normalize terminal `updatedAt` so polling timestamp jitter does not retrigger preview sync.
- Terminal queue comparison ignores timestamp-only jitter.
- `MainWindow::syncGenerationPreviewsFromQueue()` now only updates the currently visible generation workspace.
- Preview binding is deduplicated by mode/output/job key.
- `ImageGenerationPage` clears stale busy/submit-lock state on terminal worker messages and on `setBusy(false)`.

Expected runtime behavior:

- First T2I generation completes.
- Preview updates once.
- Generate becomes available again.
- Second T2I generation can start without restarting SpellVision.
