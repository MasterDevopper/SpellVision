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

---

## 5. Simple/Advanced coherence (audited 2026-08-28)

Audited against CLAUDE.md §2: *"Advanced reveals in place. It never relocates controls to a
different screen."*

**Relocation: no violations.** Every disclosure implementation is a plain `setVisible` on an
in-place block — the cockpit (`ImageGenerationPage::updateDisclosure`, which also AND-composes each
gate with the row's existing mode guard) and all three studios.

**The real defect is a different one: state that changes the output while invisible.**

Hide-not-delete is the right rule, and it is exactly what creates the gap — a value set in Advanced
still drives generation, and Simple showed nothing. Fixed by *stating* the override rather than
discarding it, so both halves stay true:

| surface | invisible state | fixed |
|---|---|---|
| cockpit | pinned seed, batch > 1, embeddings, upscale | `59a22b2` |
| Character Studio | seed lock, style LoRA | `a42d6f2` |
| Concept Lab | **seed was hardcoded 42 with no randomize control at all** | `d4a4db3` |
| Comic Studio | none — every advanced read is gated on `advanced_` | n/a |

Presets do not close this: `applyPreset` writes steps, cfg, width, height, sampler and scheduler,
and touches seed, batch, embeddings and upscale **zero** times.

### Open: the two studios disagree on what Simple means

- Cockpit and Concept Lab: **hide-not-delete** — an Advanced value still drives generation.
- Comic Studio: **discard** — each read is gated on `advanced_`, so Simple falls back to defaults.

CLAUDE.md §2 describes the first. Only one can be right, and the difference is user-visible: the
same action produces different output depending on which page you are on. Left as a product
decision rather than resolved unilaterally.

### Method note

This section was nearly wrong. Having fixed the cockpit and Character Studio, a commit message
asserted Comic and Concept "were checked and need nothing" — neither had been. Concept Lab turned
out to hold the worst defect on this list. Rule 8 of Doc 50, violated while documenting the audit
that produced it.

---

## 6. Settled by render comparison (2026-08-28)

Two questions had been left open pending renders. Settling them found two bugs first — in both
cases the *measurement* was what exposed the defect, not the reading that preceded it.

### 6a. Krea 2 sampler → **er_sde**, and the dropdown that did nothing

The first `er_sde` submission rendered **euler** and returned in 2.0s off ComfyUI's node cache.
All six native image builders hardcoded their sampler, so `req["sampler"]` was silently dropped —
while the diffusers path (`image_runners.apply_sampler_and_scheduler`, wired at two call sites) and
the video path both honoured it. A visible, per-family-populated Advanced dropdown that changed
nothing for flux, pixart, lumina, z_image, anima and krea2.

Fixed through `family_sampling_choices` — the same resolver the UI populates the dropdown from, so
the two cannot disagree about what is selectable. The family's own default is validated against the
live list too, or an unavailable default would reach ComfyUI by the other door.

With that fixed the comparison could run. Three pairs, identical seed/steps/cfg/scheduler with the
sampler as the only variable:

| operating point | prompt | result |
|---|---|---|
| raw 52 / 3.5 | astrolabe | er_sde: legible graduation ticks + coordinate grid; euler smeared both |
| raw 52 / 3.5 | fisherman's net | er_sde: mesh countable knot by knot; euler a haze |
| turbo 8 / 1.0 | fisherman's net | er_sde: crisper mesh and rope braid, more resolved background |

**Cost is nil** — the one clean timing pair (both model-resident) was 56.5s euler vs 56.2s er_sde.
The turbo pair's 34.5s/6.0s split is *not* a speed claim; the euler run there included a checkpoint
reload. Turbo was verified separately rather than assumed from the raw result. Both operating
points move to `er_sde`; euler stays selectable.

Corroborating but not the reason: the reference workflow samples with er_sde, and SpellVision's own
`anima` family already defaulted to it.

### 6b. SDXL operating points → **none needed**

The question was based on a false premise. **Nothing on the diffusers path reads
`FAMILY_OPERATING_POINTS.`** `image_runners` passes `req["steps"]` / `req["cfg"]` straight into the
pipeline and never imports the table; `worker_service` consults it only for video family status.
A row for sdxl would sit there looking authoritative and change nothing.

What those families *do* owe is a sampler allowlist, and that genuinely works — verified by render,
not by call-site reading: the same SDXL prompt and seed through `dpmpp_2m/karras` and `euler/normal`
produced images differing by a **mean absolute 30.6** per channel. Effective steps/cfg defaults are
the cockpit's 28 / 7.0, the standard SDXL baseline, which renders well.

So the *expectation* moved rather than the values being invented: `EXPECTED_LAYERS` no longer
demands operating points for diffusers/lineage routing, and a test pins the reason so nobody closes
the "gap" with an inert row. **Family parity 10 → 14 of 16.** The two remaining are honest —
`cogvideox` is unrouted, and `sd3` needs a sampler allowlist that is deliberately *not* filled by
copying sdxl's, because SD3 is flow-matching and `dpmpp_2m/karras` are wrong for it, with no SD3
checkpoint here to validate against.

Wiring diffusers to the table is a product change, not a gap fix — it would alter defaults for the
highest-volume families on this box (112 sdxl checkpoints), each needing its own render validation.
Left undone on purpose.

### 6c. Two bugs the measurement runs exposed

- **`KeyError: 'output'`.** Two consecutive SDXL runs died on `output` then `metadata_output`, one
  field per attempt, each after a full model load. 33 bare `req["..."]` subscripts.
  `require_request_keys` now reports all missing fields before the pipeline loads — and runs *after*
  the `QUEUED → STARTING` transition, because raising while still QUEUED cannot be recorded as
  FAILED and strands the item at `queued` forever.
- **The metadata sidecar records no sampler or scheduler.** Both SDXL renders wrote JSON with
  neither key, so an image on disk cannot say what produced it. Not fixed here; a provenance gap
  worth its own pass.
