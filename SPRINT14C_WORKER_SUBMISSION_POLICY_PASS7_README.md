# Sprint 14C Pass 7 — Worker Submission Policy extraction

This pass extracts queue/generation submission policy helpers from `MainWindow.cpp` into `qt_ui/workers/WorkerSubmissionPolicy`.

It moves:

- video model stack payload inspection
- resolved model value lookup
- workflow-binding detection
- native video stack detection
- video submit log formatting
- missing model block-message formatting
- accepted request log formatting

It intentionally keeps `MainWindow` responsible for page/UI flow, logging, telemetry, and final worker request dispatch.
