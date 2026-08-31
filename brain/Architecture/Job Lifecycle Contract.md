---
title: Job Lifecycle Contract
type: contract
status: accepted
sources:
  - docs/JOB_LIFECYCLE_CONTRACT.md
  - python/worker_service_state.py
updated: 2026-07-25
---

# Job Lifecycle Contract

## States

`queued` → `starting` → `running` → `completed` | `failed` | `cancelled`

Also: `queued` → `cancelled`; `starting` → `failed`.

## Valid transitions

```text
queued -> starting | cancelled
starting -> running | failed
running -> completed | failed | cancelled
```

Invalid transitions ignored/logged — **do not assume completion** unless full path ran.

## Known bug

**Ping / fast-path:** `QUEUED → COMPLETED` silently fails. Terminal message can show `ok: true` while `state: queued`. Strict xfail in tests. Fix: route through STARTING→RUNNING→COMPLETED or relax SM for ping only.

## Related

[[Worker Protocol]] · [[Worker Service]] · [[Known Bugs and Footguns]]
