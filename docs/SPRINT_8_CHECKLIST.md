# Sprint 8 Checklist — Generation Queue and Multi-Job Orchestration

## Sprint Goal
Move SpellVision from single active job handling to a real queued generation system with sequential execution, queue controls, and stronger job management.

## Core Queue Foundation
- [ ] Define queue item model
- [ ] Define queue states
  - [ ] queued
  - [ ] preparing
  - [ ] running
  - [ ] completed
  - [ ] failed
  - [ ] cancelled
  - [ ] skipped
- [ ] Add queue entry IDs separate from worker job IDs
- [ ] Store original request payload per queue item
- [ ] Track created/started/finished timestamps per queue item
- [ ] Track retry count per queue item

## Backend Orchestration
- [ ] Add queue manager in worker service
- [ ] Allow enqueueing multiple jobs
- [ ] Run queued jobs sequentially
- [ ] Prevent multiple active generation jobs from conflicting
- [ ] Support dequeue/remove before execution
- [ ] Support cancel active queue item
- [ ] Support cancel all pending queue items
- [ ] Support retry of failed/cancelled queue items
- [ ] Emit queue-aware lifecycle updates to UI

## Worker/Client Contract
- [ ] Add enqueue request type
- [ ] Add dequeue/remove request type
- [ ] Add retry queued job request type
- [ ] Add clear queue request type
- [ ] Add queue status snapshot request
- [ ] Add active queue item + pending count reporting
- [ ] Ensure every queue update includes queue item id and worker job id when applicable

## UI Queue Experience
- [ ] Add visible queue panel
- [ ] Show pending/running/completed items
- [ ] Show task type for each item
- [ ] Show prompt preview or request summary
- [ ] Show queue item state badges
- [ ] Show retry count
- [ ] Add remove selected queue item action
- [ ] Add cancel active queue item action
- [ ] Add clear pending queue action
- [ ] Add retry selected queue item action
- [ ] Add requeue from history action

## UX / Safety Improvements
- [ ] Disable invalid actions based on queue state
- [ ] Prevent accidental duplicate enqueue spam
- [ ] Show worker offline behavior clearly
- [ ] Recover UI cleanly after worker disconnect
- [ ] Show empty-queue state clearly
- [ ] Preserve selected history/preview state while queue changes

## Persistence
- [ ] Decide whether queue persists across app restarts
- [ ] Persist pending queue items to disk
- [ ] Restore queue on startup when safe
- [ ] Skip restoring stale running states
- [ ] Mark incomplete restored items appropriately

## Testing
- [ ] Test one queued job
- [ ] Test multiple queued jobs
- [ ] Test cancel active queued job
- [ ] Test remove pending queued job
- [ ] Test retry failed queued job
- [ ] Test clear pending queue
- [ ] Test queue after worker restart
- [ ] Test queue state recovery after app restart
- [ ] Test malformed queue updates
- [ ] Test UI remains responsive during queue execution

## Documentation
- [ ] Add queue lifecycle reference doc
- [ ] Document queue request/response contract
- [ ] Document retry/cancel semantics for queued jobs
- [ ] Add developer notes for future parallel execution support
