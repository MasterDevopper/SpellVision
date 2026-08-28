# 49 — Reachability audit: worker capability the UI never exposes

**Status:** measured 2026-08-28 against `worker_client.CONTROL_COMMANDS ∪ STREAMING_COMMANDS`
(51 commands) versus every `.cpp` under `qt_ui/`. Sections 1 and 2 are **fixed**; 3 and 4 stand.

The owner's v0.1.0 bar includes *"features we added are reachable by users."* This is what that
question returns when asked mechanically.

---

## 1. The queue is append-only from the UI — FIXED (`4c51407`)

The worker implemented full queue management. The UI sent **`enqueue` and nothing else.**

A context menu on the queue table now reaches all ten commands. Actions stay visible and disabled
rather than hidden, so the menu is also the discovery surface; the row under the cursor is selected
before the menu opens (a right-click on row 5 would otherwise act on the previous selection, a
mis-target with no undo); Clear Pending and Cancel All confirm first.

**Proving it worked found two bugs that had been there the whole time.**

*Every queue command reported `ok: true`.* Each handler built its ack as
`{..., "ok": ok, **snapshot_payload()}`, and `snapshot_payload()` ends with
`{"type": "queue_snapshot", "ok": True}` — so the spread silently overrode the handler's own
result. `"queue item not found"` and `"retry source job not found"` both came back as success. The
`"type": "queue_ack"` label those handlers set was overridden by the same inversion and had never
reached the wire; it is removed rather than restored, because `WorkerQueueController` applies a
snapshot only when `type == "queue_snapshot"`.

*`retry_from_archive` with an empty job id retried an arbitrary job.* Its fallback matches the id
against a set containing `""` whenever an item has no worker job id yet, so a blank matched an
unrelated terminal item and re-ran it. Measured live: a retry with no `job_id` enqueued work.

`retry_queue_item` is also the one command keyed by `job_id` rather than `queue_item_id`. The first
version of the menu sent `queue_item_id` to all ten, which would have made Retry silently do
nothing — caught only because `tests/test_queue_commands_live.py` drives each command over the real
protocol with the key the menu actually sends.

The original table, for the record:

| worker command | reachable from the UI? |
|---|---|
| `enqueue` | yes |
| `cancel_queue_item` | **no** |
| `cancel_active_queue_item` | **no** |
| `cancel_all_queue_items` | **no** |
| `remove_queue_item` | **no** |
| `clear_pending_queue` | **no** |
| `pause_queue` / `resume_queue` | **no** |
| `move_queue_item_up` / `_down` | **no** |
| `retry_queue_item` | **no** |
| `duplicate_queue_item` | **no** |

Verified three ways: no literal command string appears in `qt_ui/`; no `cancelQueueItem`-style call
site exists; and the queue table has **no context menu** — the only `QMenu` in `MainWindow.cpp`
toggles panel visibility.

So a user can see the queue (there is a table, an overlay, and a `Queue: N` readout in the status
strip) and can add to it, but cannot cancel a running job, remove a pending one, reorder, pause, or
retry. Nine implemented, tested worker commands with no route to them.

**This is the single largest reachability gap in the app.** It is also not a bug to patch — it is a
feature to build, and it should be scoped as one: a context menu on the queue table plus Pause /
Clear in the queue header would reach all nine.

## 2. Runtime control is mostly unexposed — the recovery path FIXED (`38a038e`)

A **Free VRAM** button on the Runtime page now chains `unload_all_runtimes` → `clear_cuda_cache`.
Chained rather than parallel: dropping the cache before the runtimes have released their
allocations leaves exactly the blocks that cause the wedge.

This was not hypothetical. Comfy's accounting wedged during this build — 0.1 GB free reported
against an actual 29.8 GB — and Restart Comfy was the only reachable recovery, which discards the
process, its warm state, and everything queued behind it.

Still unreached, and plausibly fine as CLI-only: `start_comfy_runtime`, `stop_comfy_runtime`,
`ensure_comfy_runtime`, the two single-runtime unloads, `runtime_memory_status`,
`runtime_diagnostics`.

### Original finding

`ManagerPage` sends `restart_comfy_runtime` and `runtime_status`. Unreached:
`start_comfy_runtime`, `stop_comfy_runtime`, `ensure_comfy_runtime`, `unload_image_runtime`,
`unload_video_runtime`, `unload_all_runtimes`, `clear_cuda_cache`, `runtime_memory_status`,
`runtime_diagnostics`.

The unload/clear-cache ones matter on this box specifically: ComfyUI's memory accounting wedged
during this session (reporting 0.1 GB free against an actual 29.8 GB) and the only recovery was a
restart, while `unload_all_runtimes` and `clear_cuda_cache` existed the whole time.

## 3. Video-family contract and readiness commands

`ltx_readiness_status`, `ltx_runtime_readiness`, `ltx_workflow_contract`,
`ltx_test_workflow_contract`, `video_family_status`, `video_family_readiness`,
`video_family_readiness_status`, `video_family_workflow_contract`,
`video_family_test_workflow_contract` — none referenced from `qt_ui/`.

Some of these are plausibly dev/CLI diagnostics rather than user features. That distinction should
be **recorded**, because right now nothing separates "deliberately CLI-only" from "we forgot to
wire it", and the two look identical from outside.

## 4. Also CLI-only

- `comfy_node_contract.py` — the `/object_info` drift diff. Never wired to a worker command, so the
  guided-update gate cannot show it.
- `list_workflow_profiles` — the UI reads profile JSON off disk directly instead.

---

## What this audit is not

A count of unreferenced strings is not by itself a defect list. Four times in this session a
text-scan of source produced a confidently wrong conclusion (`sdxl` "missing a builder", image
families "having" a video contract, lumina/pixart "undetectable", the four video families
"missing" a display name). Every row above was therefore checked a second way — call sites, menus,
or the actual send path — before being listed.

The right follow-up is a **declared** capability surface: each worker command tagged
`user_facing` / `diagnostic` / `internal`, with a test asserting every `user_facing` one has a
route. That turns this from a one-off sweep into the same kind of ratchet
`tests/test_family_capability.py` gives the family layers.
