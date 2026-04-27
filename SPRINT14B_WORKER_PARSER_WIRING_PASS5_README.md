# Sprint 14B Pass 5 — Worker parser wiring

This pass wires `WorkerResponseParser` into `ImageGenerationPage` through a narrow `applyWorkerMessage(const QJsonObject&)` entry point.

The method parses raw worker JSON once, then delegates to existing page behavior:

- status/progress/job running messages keep the page busy without clearing previews
- completed job/result messages route output paths through the existing preview router
- error/client-error messages clear busy state and surface the problem in the readiness hint
- queue/runtime/workflow messages are ignored by this page and remain owned by shell-level systems

This keeps behavior stable while giving MainWindow or a future worker controller a typed page-level message entry point.
