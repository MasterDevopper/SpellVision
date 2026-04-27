# Sprint 14C Pass 6 Notes

`WorkerQueueController` was scaffolded in Pass 5. This pass connects it to the existing MainWindow queue lifecycle.

Expected ownership after this pass:

- `WorkerQueueController`: queue polling timer, queue status request, queue response normalization, QueueManager snapshot application.
- `MainWindow`: UI refresh callbacks, telemetry sync, generation page preview sync, logs.
