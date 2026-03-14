# Sprint 9 Checklist — Queue Maturity and Orchestration UX

## Sprint Goal
Take the current queue foundation and optimization work and turn it into a more complete, user-friendly orchestration system.

## Queue UX
- [ ] Improve queue panel readability
- [ ] Show clearer state badges for queue items
- [ ] Show active item more prominently
- [ ] Show selected queue item details
- [ ] Add remove selected pending item action
- [ ] Add retry selected item action
- [ ] Add clear pending queue action
- [ ] Add cancel active queue item action
- [ ] Add requeue from history action

## Queue State and Control
- [ ] Strengthen queue lifecycle consistency
- [ ] Improve queue snapshot accuracy during rapid transitions
- [ ] Add clearer empty-queue state
- [ ] Add better failure/cancel messaging per queue item
- [ ] Make active/pending counts more visible
- [ ] Improve queue completion state handling

## Scheduling and Orchestration
- [ ] Keep sequential execution stable
- [ ] Improve warm-reuse signaling
- [ ] Add stronger queue wait-time estimates
- [ ] Consider optional queue grouping toggle for same-model jobs
- [ ] Make scheduling behavior easier to understand in the UI

## Persistence / Recovery
- [ ] Decide whether pending queue should persist across restart
- [ ] If yes, persist pending queue safely
- [ ] Restore queue state on launch when safe
- [ ] Mark interrupted jobs clearly after restart
- [ ] Avoid restoring stale running state incorrectly

## History and Preview Integration
- [ ] Add requeue from history
- [ ] Improve selection sync between history and preview
- [ ] Show richer queue/result linkage in history
- [ ] Preserve latest-result visibility during queue changes

## Telemetry / Feedback
- [ ] Improve queue ETA accuracy
- [ ] Improve wording consistency for queue state text
- [ ] Show active warm model / warm LoRA context more clearly
- [ ] Surface queue wait time and start delay if useful

## Reliability
- [ ] Harden queue behavior during worker disconnects
- [ ] Harden queue behavior during malformed worker responses
- [ ] Confirm cancel/retry/remove interactions are stable
- [ ] Confirm direct generation vs queued generation paths are consistent

## Testing
- [ ] Enqueue multiple same-model jobs
- [ ] Enqueue mixed-model jobs
- [ ] Cancel active queued job
- [ ] Remove pending queued job
- [ ] Retry completed job
- [ ] Retry failed job
- [ ] Clear pending queue
- [ ] Restart app and verify chosen persistence behavior
- [ ] Validate queue info and ETA remain trustworthy

## Documentation
- [ ] Add Sprint 9 orchestration doc
- [ ] Document queue persistence behavior
- [ ] Document queue control semantics
