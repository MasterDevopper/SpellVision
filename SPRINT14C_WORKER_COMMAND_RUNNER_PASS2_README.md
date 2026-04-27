# Sprint 14C Pass 2 - Worker Command Runner Extraction

This pass adds `WorkerCommandRunner` and routes Generate / Queue button submission through it.

The goal is behavior-preserving extraction:

- `ImageGenerationPage` still owns button layout and signals.
- `WorkerCommandRunner` owns submission payload decoration.
- The existing payload keys are preserved:
  - `submit_origin`
  - `client_readiness_block`
  - `client_video_mode`
  - `client_selected_model`
  - `client_has_video_workflow_binding`

This is a narrow pass before deeper worker/process orchestration extraction.
