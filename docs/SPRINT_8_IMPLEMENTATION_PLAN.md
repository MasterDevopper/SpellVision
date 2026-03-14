# Sprint 8 Implementation Plan — Queue Orchestration

## High-Level Goal
Introduce a queue manager that lets SpellVision accept multiple generation requests, execute them sequentially, and expose queue state cleanly in both the backend and UI.

## Recommended Build Order

### Phase 1 — Data Model and Contract
Start with a queue model before changing behavior.

#### Add queue concepts
- `queue_item_id`
- `worker_job_id`
- `task_type`
- `request_payload`
- `queue_state`
- timestamps
- retry count
- last error
- output path

#### Add queue state values
- queued
- preparing
- running
- completed
- failed
- cancelled
- skipped

#### Deliverables
- queue item dataclass / struct
- queue state enum
- queue update payload shape
- queue snapshot payload shape

## Phase 2 — Backend Queue Manager
Add a queue manager in `worker_service.py`.

### Responsibilities
- accept enqueue requests
- store pending items
- launch next job when idle
- update queue state as jobs progress
- handle cancel/remove/clear/retry actions
- keep one active worker job at a time for now

### Suggested internal model
- `deque` for pending items
- `dict` for all queue items by id
- `active_queue_item_id`
- `active_job_handle`
- `queue_lock`

### First backend milestone
Support:
1. enqueue one or more jobs
2. start next job automatically
3. move finished job out of active state
4. trigger next queued item

## Phase 3 — Worker Event Bridging
Translate generation lifecycle events into queue lifecycle events.

### Mapping idea
- queue item enters `preparing` when selected for execution
- worker job `starting/running` maps to queue item `running`
- worker job `completed` maps to queue item `completed`
- worker job `failed` maps to queue item `failed`
- worker job `cancelled` maps to queue item `cancelled`

### Deliverables
- queue-aware event emitter helpers
- queue snapshot emitter
- active/pending count emitter

## Phase 4 — UI Queue Panel
Add a queue dock/panel in `MainWindow`.

### Minimum UI features
- queue list widget
- state label per item
- selected item details
- remove selected
- retry selected
- clear pending
- cancel active

### Recommended first layout
Use a simple list first:
- `[STATE] [TASK] short prompt preview`
- separate details in metadata/inspector area

Do not overbuild the visual design yet. Functionality first.

## Phase 5 — Retry and Requeue Behavior
Extend existing retry logic so it works with queue items instead of only the last generation.

### Add support for:
- retry selected failed item
- requeue completed item from history
- duplicate selected item into queue

## Phase 6 — Persistence
Persist queue state to disk only after the live queue works well.

### Persist only:
- queued items
- safe metadata for cancelled/failed items if useful

### Do not restore:
- active running item as running
Instead restore it as:
- failed_recovered
or
- cancelled_recovered
depending on your chosen semantics

## Suggested File Touch Order
1. `python/worker_service.py`
2. `python/worker_client.py`
3. `qt_ui/MainWindow.h`
4. `qt_ui/MainWindow.cpp`
5. queue lifecycle doc
6. persistence helpers

## First Practical Milestone
The smallest real Sprint 8 win is:

### “Single queue lane”
- enqueue multiple jobs
- show them in UI
- run one at a time
- auto-start next when current finishes
- allow cancel current
- allow remove pending

If this milestone is solid, the rest of Sprint 8 becomes much easier.

## Suggested Commit Sequence
```bash
git commit -m "feat(queue): add queue item model and lifecycle states"
git commit -m "feat(worker-service): add sequential queue manager"
git commit -m "feat(worker-client): add enqueue and queue control requests"
git commit -m "feat(ui): add queue panel and queue state rendering"
git commit -m "feat(queue): support cancel remove and retry for queued jobs"
git commit -m "docs(sprint-8): document queue lifecycle and orchestration flow"
```

## Success Criteria
Sprint 8 is successful when:
- multiple jobs can be added without starting manually one by one
- only one generation runs at a time
- next queued job starts automatically
- queue controls work reliably
- queue state is visible and trustworthy in the UI
- failures/cancels do not corrupt later queue execution
