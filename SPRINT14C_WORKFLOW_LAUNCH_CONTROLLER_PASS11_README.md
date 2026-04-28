# Sprint 14C Pass 11 — Workflow Launch Controller

Adds `qt_ui/workflows/WorkflowLaunchController` and moves workflow draft routing policy out of `MainWindow::openWorkflowDraft`.

This pass intentionally keeps the workflow import process and final launch dispatch behavior stable while establishing the workflows-layer controller boundary.

Extracted responsibilities:

- workflow draft mode normalization
- media/input-image fallback mode selection
- draft mode availability fallback
- workflow draft log message formatting
- workflow launch request helper scaffold
