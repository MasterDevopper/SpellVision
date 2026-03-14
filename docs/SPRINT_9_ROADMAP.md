# Sprint 9 Roadmap — Queue Maturity and Orchestration UX

## Sprint Theme
Turn the queue from a working backend-first feature into a stronger end-user orchestration system.

## High-Level Objective
SpellVision already has:
- queue foundations
- queue-aware telemetry
- warm-reuse hints
- cancel/retry support
- optimization groundwork

Sprint 9 should make the queue feel complete and trustworthy from the UI.

## Recommended Scope

### Phase 1 — Queue UX Stabilization
Improve the existing queue panel first.
Do not add too much new behavior until the current queue is easy to read and operate.

#### Deliverables
- clearer item formatting
- selected queue item details
- active item emphasis
- queue controls (remove, retry, clear pending, cancel active)
- clearer empty state

### Phase 2 — Queue Control Semantics
Make the queue controls predictable.

#### Key behaviors
- remove only affects pending items
- cancel affects the active item
- retry creates a fresh queue item with a fresh output path
- clear pending never destroys completed history
- history requeue creates a new queue item without mutating the old result

### Phase 3 — Scheduling Visibility
Keep Version A behavior (preserve order), but explain it better.

#### Deliverables
- queue ETA improvements
- wait-time estimate per active job / pending queue
- clearer warm-reuse wording
- explicit explanation that queue order is preserved

### Phase 4 — Persistence Decision
Decide whether pending queue items survive restart.

#### Recommended first approach
- persist only pending items
- restore them as queued on startup
- do not restore running state as running
- mark interrupted items clearly

This should be implemented only after queue UX and control semantics are stable.

### Phase 5 — History / Queue Integration
Bridge queue and history better.

#### Deliverables
- requeue selected history item
- queue item -> result history linkage
- better selection syncing between latest output, history, and queue

## Suggested Implementation Order

### Step 1
Queue panel polish:
- item formatting
- state badges
- selected details
- active item emphasis

### Step 2
Queue control actions:
- remove pending
- clear pending
- retry selected
- requeue from history

### Step 3
ETA / wait-time improvements:
- active ETA refinement
- queue ETA refinement
- clearer warm-reuse display

### Step 4
Worker disconnect / malformed message hardening for queue flows

### Step 5
Queue persistence (only if Steps 1–4 are stable)

## Suggested Commit Sequence
```bash
git commit -m "feat(sprint-9): improve queue panel readability and active item visibility"
git commit -m "feat(queue-ui): add remove retry clear and cancel controls"
git commit -m "feat(history): add requeue from history and queue/result linkage"
git commit -m "feat(queue): improve eta and wait-time messaging"
git commit -m "fix(queue): harden queue behavior for worker disconnects and malformed responses"
git commit -m "feat(queue): add pending queue persistence across restart"
```

## Success Criteria
Sprint 9 is successful when:
- queue operations feel intuitive from the UI
- queue status and ETA feel trustworthy
- remove/cancel/retry/requeue behaviors are clearly defined
- history and queue work together naturally
- queue behavior remains stable across edge cases
