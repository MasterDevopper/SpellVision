# Sprint 7 Improvements — Generation Orchestration and Job Lifecycle Stabilization

## Overview
Sprint 7 builds directly on the Sprint 6 progress-streaming foundation. Sprint 6 gave SpellVision better real-time visibility into running work. Sprint 7 turns that visibility into a reliable generation workflow by standardizing how jobs are created, tracked, cancelled, retried, failed, and completed across the Python backend and the Qt UI.

This sprint is focused on making generation behave like a real product system instead of a loose collection of backend events and UI updates. The goal is to ensure that every generation request moves through a predictable lifecycle and that both the worker layer and the user interface agree on the current state of a job at all times.

---

## Why Sprint 7 Matters
Right now, progress streaming is useful, but progress alone is not enough for a production-ready generation pipeline. A job can still become difficult to manage if:

- the UI and backend disagree about the current state
- a failed job does not return a structured reason
- a running job cannot be cancelled cleanly
- retry behavior is inconsistent
- stale UI state remains after a job finishes
- malformed or partial payloads cause confusing behavior

Sprint 7 fixes that by introducing a formal job lifecycle contract and stronger coordination between these core components:

- `python/worker_service.py`
- `python/worker_client.py`
- `qt_ui/MainWindow.cpp`
- `qt_ui/MainWindow.h`

---

## Main Sprint 7 Improvements

### 1. Canonical Job Lifecycle States
Sprint 7 defines a single official set of job states that every layer of the application must use.

Recommended canonical states:

- `queued`
- `starting`
- `running`
- `completed`
- `failed`
- `cancelled`

This improvement matters because it removes ambiguity. Instead of one part of the app saying a job is “in progress” while another says “running” or “working,” the system will use one shared vocabulary.

### 2. Stable Job Identity
Each generation request should have a durable `job_id` that is created once and reused throughout the entire lifecycle.

This allows the system to:

- correlate progress events to the correct job
- cancel the correct running task
- retry a failed job without confusion
- prevent mixed UI updates when multiple jobs are run over time

### 3. Structured Backend Payload Contract
Sprint 7 improves the message contract between the Python worker layer and the Qt interface.

Every progress or result payload should consistently include fields such as:

- `job_id`
- `state`
- `progress`
- `message`
- `error`
- `created_at`
- `started_at`
- `finished_at`

This makes frontend behavior more reliable and gives the backend a predictable schema for reporting events.

### 4. Structured Error Reporting
Instead of sending vague failures or raw exceptions directly into the UI, Sprint 7 introduces structured error objects.

A structured error may include:

- machine-readable error code
- human-readable message
- optional technical details
- optional retryable flag

This makes failures easier to debug and helps the UI present clearer feedback to the user.

### 5. Cancel Job Support
Sprint 7 adds the ability to cancel a running generation task safely.

This is important for long-running generation flows and future model orchestration. A user should not be forced to wait for a bad prompt, wrong job, or hung operation to finish.

Expected behavior:

- user clicks cancel
- UI disables invalid follow-up actions
- cancel request is sent to backend with `job_id`
- backend transitions job to `cancelled` when confirmed
- UI resets to a clean post-job state

### 6. Retry Job Support
Retry support allows failed or cancelled jobs to be rerun without rebuilding the full request path from scratch.

This improves user experience and is especially useful once SpellVision begins routing more image, video, and 3D generation workloads through a shared orchestration layer.

### 7. Safer UI State Management
Sprint 7 improves how the Qt UI responds to job transitions.

The UI should:

- show accurate status text for every canonical state
- enable or disable controls appropriately
- clear stale progress data when a job ends
- show failure reasons clearly
- avoid remaining stuck in a “running” state after completion or error

This is one of the most visible improvements in the sprint because it directly affects how reliable the application feels.

### 8. Protection Against Invalid State Transitions
Sprint 7 adds guard rails so jobs do not move through impossible or conflicting paths.

Examples of invalid behavior that should be prevented:

- `completed` -> `running`
- `failed` -> `starting` without retry flow
- missing `job_id` on progress update
- progress updates arriving after terminal state

This helps prevent hard-to-debug synchronization issues.

### 9. Reliability and Disconnect Handling
The system should behave safely when the backend disconnects, times out, or returns malformed data.

Sprint 7 should improve resilience by:

- handling missing payload fields
- handling malformed payloads without crashing the UI
- detecting backend unavailability
- surfacing meaningful status to the user
- keeping the application recoverable after failure

### 10. Logging and Developer Observability
Sprint 7 should make debugging easier by improving lifecycle logging.

Useful log points include:

- job creation
- state transition events
- cancel requests
- retry requests
- backend failures
- malformed payload rejection
- final job outcome

This will help support future orchestration work for image, video, voice, rigging, and 3D generation.

---

## Files Most Likely Affected

### `python/worker_service.py`
This file should become the authoritative source for job lifecycle transitions and structured result/error reporting.

Likely improvements:

- canonical state emission
- cancel handling
- retry handling
- structured payload generation
- lifecycle timestamps
- stronger validation before emitting updates

### `python/worker_client.py`
This file should become the stable communication bridge between backend processing and the UI layer.

Likely improvements:

- normalized request/response handling
- job-aware progress updates
- cancel and retry request support
- safer parsing and validation
- graceful handling of disconnects or bad payloads

### `qt_ui/MainWindow.cpp` and `qt_ui/MainWindow.h`
These files should become responsible for accurate UI lifecycle presentation.

Likely improvements:

- state-aware UI updates
- clear progress messaging
- action button enable/disable rules
- cancel/retry button behavior
- status reset logic after terminal states
- cleaner signal-slot flow for generation lifecycle events

---

## Expected User-Facing Benefits
After Sprint 7, SpellVision should feel noticeably more stable and professional.

Users should experience:

- clearer generation status
- fewer confusing UI states
- better failure feedback
- reliable cleanup after job completion
- the ability to cancel bad runs
- easier retry of failed jobs

This sprint does not just add features. It makes the existing generation workflow trustworthy enough to serve as the base for later multi-modal generation systems.

---

## Expected Engineering Benefits
Sprint 7 also improves the internal architecture of the application.

Engineering gains include:

- one shared lifecycle model across backend and frontend
- easier debugging through structured logs and errors
- reduced state desynchronization bugs
- simpler future integration with image/video/3D/voice pipelines
- better foundation for queueing and orchestration in later sprints

---

## Relationship to Future Sprints
Sprint 7 is a bridge sprint. It connects the current progress-streaming work to the larger generation pipeline roadmap.

It prepares SpellVision for future additions such as:

- image generation routing
- video generation orchestration
- 3D asset generation jobs
- voice generation tasks
- rigging and post-processing workflows
- multi-stage generation pipelines with queue support

Without Sprint 7, those future systems would be built on unstable job handling. With Sprint 7 complete, later sprints can rely on a consistent lifecycle and cleaner orchestration behavior.

---

## Proposed Deliverables
By the end of Sprint 7, the project should ideally have:

- a defined canonical job state model
- a documented worker-client payload contract
- structured error objects
- cancel-job support
- retry-job support
- stable job-aware UI updates
- safer terminal state cleanup
- improved lifecycle logging

---

## Acceptance Criteria
Sprint 7 can be considered successful when:

1. A generation request receives a stable `job_id`.
2. The backend emits only valid canonical lifecycle states.
3. The UI displays the correct status for queued, starting, running, completed, failed, and cancelled states.
4. A running job can be cancelled without corrupting the UI.
5. A failed job can be retried through a defined path.
6. Errors are displayed in a structured and user-readable way.
7. Repeated runs do not leave stale progress or locked controls behind.
8. Malformed payloads do not crash the UI.

---

## Recommended Sprint Theme
**Sprint 7 Theme:** _Make generation reliable, controllable, and ready for orchestration._

That theme fits the project well because Sprint 7 is less about flashy new output and more about making the system dependable enough to support everything that comes next.
