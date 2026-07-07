# Doc 17 — Generation Completeness Audit (Part A of the model-expansion arc)

> **Status: survey complete (2026-07-07). No code changed — this is the map.**
> Part A of the [generation completeness + model-expansion arc]. Before adding the 9 new
> models (Part B), finish the base gaps below. This doc is the authoritative reference +
> the checklist to tick off during the arc.

## Verdict

**The base is SOLID.** T2I, I2I, T2V (Wan+LTX), and I2V (LTX) all generate **end-to-end
today**, with **zero code stubs** (no `TODO`/`FIXME`/`NotImplementedError`/`pass`-only in the
UI or the 7481-line worker) and **production-grade dependency resolvers** that actually copy
model files and install custom nodes. The real gaps are concentrated in **two shared
cross-cutting layers (error surfacing, history) and the video-family wiring** — not in core
generation. Finish those and the base is genuinely ready for Part B.

All four modes are one C++ class (`ImageGenerationPage`, parameterized by `mode_`) →
`GenerationRequestBuilder` → TCP/JSON → `worker_service.py` command dispatch
(`t2i`/`i2i`/`t2v`/`i2v`/`comfy_workflow`). `VideoGenerationPage.{h,cpp}` exists but is never
instantiated (dead code).

---

## Master gap table (path × dimension)

| Dimension | T2I | I2I | T2V | I2V |
|---|---|---|---|---|
| **1. End-to-end** | ✅ works | ✅ works | ✅ Wan+LTX ¹ | ✅ **LTX only** · ❌ Wan/others hard-raise |
| **2. Control wiring** | ✅ complete | ✅ complete | ⚠️ family combo dead; LTX panel unreachable in Simple | ⚠️ inherits T2V + Denoise over-exposure |
| **3. Stubs/TODOs** | ✅ none ² | ✅ none ² | ✅ none (intentional gate-raises) | ✅ none (intentional raises) |
| **4a. Result routing** | ✅ | ⚠️ payload omits contract ³ | ✅ | ✅ |
| **4b. History** | ❌ no image history | ❌ no image history | ✅ | ✅ |
| **4c. Preview** | ✅ | ✅ | ✅ (no thumbnail) | ✅ (no thumbnail) |
| **5. Error handling** | ❌ broken ⁴ | ❌ broken ⁴ | ❌ broken ⁴ | ❌ broken ⁴ |
| **6. Mode parity** | ✅ | ✅ | ⚠️ family ignored | ⚠️ family + Denoise unclear |

1. Contingent on the request resolving as a split-stack/single-file stack so it takes
   `run_native_split_stack_video`; the pure-diffusers video fallback (`_load_native_video_pipeline`,
   `worker_service.py:5269`) is dead/unproven and **raises** for single-file stacks (`:5278-5283`).
2. No literal `TODO`/`FIXME`/`NotImplementedError`/`pass`-only in UI (`ImageGenerationPage.cpp`,
   `qt_ui/generation/`) or worker (`worker_service.py`). The "raises" that exist are intentional
   guardrails, not stubs.
3. `run_i2i` sidecar file **is** written (`save_metadata`, `worker_service.py:5727`); only the
   result *message* (`:5748-5775`) omits the `output_finalization_contract`/`metadata_write_deferred`
   block that the other three paths emit (T2I at `:3402-3432`).
4. See "Cross-cutting #1" below — the intended page-banner error path is dead code.

---

## Cross-cutting findings

### 1. Error surfacing is effectively broken for ALL paths (P0)
The designed inline-error surface is **dead code**, and the live path never reads failures.
This is the concrete root cause of the **"worker-down scare"** (all modes appear dead with no
reason) seen repeatedly this session.
- `ImageGenerationPage::applyWorkerMessage` (`ImageGenerationPage.cpp:3260`) wires
  `GenerationStatusController::showProblem` → `readinessHintLabel_` (an inline banner) for
  `error`/`traceback` — **but `applyWorkerMessage` has ZERO callers.**
- `GenerationStatusController` intended error path: `GenerationStatusController.cpp:76-131` (unreached).
- The live sync `syncGenerationPreviewsFromQueue` (`MainWindow.cpp:2151-2232`) binds only
  `item.completed` (`:2184`); it never reads `item.failed`/`item.errorText`. `"traceback"` is
  never read anywhere in `qt_ui`.
- Worker error payload itself is fine + uniform (`worker_service.py:3189-3198`, structured
  `type:"error"`). The swallow is **UI-side**.
- Worker-down: per-request `QProcess` (`worker_client.py`), not a live socket. Failure →
  `MainWindow.cpp:1579` (`startedOk==false`) or `:1585` (empty response) — **log-pane only**.
  `queuePollFailed` (`WorkerQueueController.cpp:480-488`) is **connected to nothing**.
- **The infra exists and is just unwired** — connecting the dead path + reading failed items +
  connecting `queuePollFailed` is the fix.

### 2. History is video-only by construction (P1)
T2I/I2I image results have **no persistent history at all** (only a transient queue-tray row).
- Backend: `archive_job` → `persist_video_history_entry(build_video_history_entry(...))`
  (`worker_service.py:2518`), but `build_video_history_entry` **returns `None` for any
  non-video request** (`:2369`, gated on `is_video_request`). Image results never reach
  `runtime/history/video_history_index.json`. The schema is video-shaped
  (`video_low_model_name`, `video_duration_label`, …).
- UI: sole surface is `T2VHistoryPage` (`MainWindow.cpp:946`); item struct `VideoHistoryItem`;
  reads only the video index (`T2VHistoryPage.cpp:968-973`); one reader hard-filters
  `task_type != "t2v"` (`:1005`); actions are Open-video/LTX-requeue. **No image-history page exists.**
- Fix = backend (remove the `is_video_request` gate / add an image index) **and**
  generalize `T2VHistoryPage`. A mini-project, not a one-liner.

### 3. Stale LTX contract — self-contradicting production signal (P0)
Not a runtime bug, but a landmine for Part B: the 2 new video models (Hunyuan, Wan Video) copy
the LTX template pattern and would inherit the contradiction.
- `ltx_workflow_contract.py:46-47, 224` still declares LTX `validation_status="experimental"`,
  `production_ready=False`, "not replacing the Wan production route" — the **old** contract.
- Canonical `video_family_contracts.py:64-79` says LTX = **`production`** — and this is what the
  live gate (`_raise_if_unvalidated_native_video_family`, `worker_service.py:5099`) actually reads.
- Stale comment also at `worker_service.py:5421` ("blocked by the gate (experimental) until
  flipped to production" — it IS production now).

### 4. Dead widgets / inert code (P1/P3)
- **`videoFamilyCombo_`** (`ImageGenerationPage.cpp:622-693`) — a **lying control**: the user's
  explicit Auto/Wan/LTX pick is **never read into the draft**. Payload `video_family`
  (`GenerationRequestBuilder` ~:222) comes from `VideoGenerationPolicy::resolvedVideoFamily`
  (`VideoGenerationPolicy.cpp:28-60`), which re-derives family from `modelFamily`/stack/name — it
  does not consult the combo. A manual override with a differently-named checkpoint won't stick. (P1)
- **`workflowCombo_`** (`ImageGenerationPage.cpp:1559-1564`) — four hardcoded placeholder profile
  names ("Default Canvas"/"Portrait Detail"/…), not real workflows; value reaches worker as
  `workflow_profile` (a meaningless string). Real binding comes from `applyWorkflowDraft`. (P3)
- **`toggleControlsButton_`** (`:1451-1453`) — `setVisible(false)` at construction, never re-shown. (P3)
- **`setWorkspaceTelemetry`** (`:3316-3321`) — all params `Q_UNUSED`; called but does nothing. (P3)
- **Hardcoded machine path** `D:/AI_ASSETS/comfy_runtime/ComfyUI/user/default/workflows/ltx_api.json`
  shipped as `ltxPromptApiExportPath` default in both UI (`:281`) and builder (~:53). (P3)

### 5. State machine — hazard present, not triggered (P3)
`worker_service_state.py`: `VALID_TRANSITIONS` (`:129-136`) allows `QUEUED → {STARTING,
CANCELLED}` only; `COMPLETED` reachable only from `RUNNING`. `complete_job` sets `job.result`
first (`:366-367`) then `transition_job(COMPLETED)` (`:491`) — if still QUEUED, the transition
returns `False` **silently** (`:332`) and the job keeps `QUEUED` with a populated result (the
"silent fail"; symptom = non-draining queue count). **No path hits it today** (all five `run_*`
pass `STARTING→RUNNING` first), but `complete_job` has **no guard** — a future early-return that
skips `RUNNING` would fail silently. Worth a defensive assert.

---

## Backend / adapter state (dimension 7)

**Generates today (real, exercised):**
- **SDXL/SD image (t2i + i2i)** — `build_paired_pipelines` (`memory_optimization.py:637`) →
  `build_pipelines` (`worker_service.py:2824`); shared-weight load + CPU fp32→fp16 cast.
- **LTX video t2v + i2v** — native AV template `video_templates/ltx_av_native.json` (31 nodes) +
  `_build_native_ltx_video_prompt` (`worker_service.py:4767`); LoRA opt-out by default
  (`:4846-4867`), i2v via LoadImage upload bridge + bypass (`:4869-4890`). Hard constraints
  (dims÷32, frames=(N×8)+1) enforced in `ltx_adapter.prepare_request` (`_snap_to_multiple`,
  `_snap_ltx_frame_length`) — **caveat:** the builder does not re-snap, so enforcement depends on
  the adapter having run (`_prepare_native_video_adapter_request`, `worker_service.py:5066`).
- **Wan video t2v** — graph built from code (`_build_native_wan_core_video_prompt` `:4510`;
  wrapper `_build_native_wan_split_video_prompt` `:4626`).
- **Any family with a comfy-workflow binding** — `run_comfy_workflow` (the escape hatch).
- **LTX Prompt-API fallback** — complete but reachable **only** by explicit
  `ltx_prompt_api_gated_submission` command (`worker_service.py:606`; no auto-promotion).

**Scaffolded / gate-blocked (intentional — this is Part B's surface):**
- **Wan i2v** — raises at `worker_service.py:4512` and `:5117-5122`.
- **Hunyuan / CogVideoX / Mochi** — `validation_status="detected"` (`video_family_contracts.py:80-127`);
  gate-blocked (`:5099`, `:5104`); registered + have pipeline-candidate names but **no builder/template**.
- **SD3 / Flux single-file** — raise (`memory_optimization.py:732`); repo-dir path exists but unexercised.
- **Generic video adapter** (`video_adapters/generic_adapter.py`) — tags only, builds no graph.

**Dependency resolvers are REAL (the load-bearing infra works):**
- `model_dependency_resolver.py` — parses `extra_model_paths.yaml` (`:65`), builds install plans,
  and `apply_model_install_plan` **actually copies/moves files** (`:233-254`). *Caveat:* HF-repo
  refs always land as `review` (`:347`), never auto-materialized.
- `node_dependency_resolver.py` — queries installed nodes (`:90`), and `apply_node_install_plan`
  **actually installs** via ComfyUI-Manager / git clone (`:127-176`). *Caveat:* quality depends on
  `starter_node_catalog.json` — a class with no catalog match returns `manual_review` (`:251-258`),
  so each new family's custom nodes need catalog entries.

**Adapter pattern is clean + additive.** A new family needs: (1) `ModelFamilySpec` in
`model_registry.py`, (2) a `production` `VideoFamilyContract` in `video_family_contracts.py`,
(3) a `VideoFamilyAdapter` subclass registered in `video_adapters/registry.py:12`, (4) a
repo-owned template JSON, (5) a `_build_native_*_prompt` builder branch. **LTX is the proven
template-to-follow — reconcile its stale contract (Cross-cutting #3) first.**
Note for the 3D goal: this is all t2v/i2v + `SaveVideo` plumbing; a `.glb`/mesh family needs a
parallel command + output-routing path, not just a new adapter entry.

---

## Prioritized "Finish First" checklist

Rank: **blocks/enables-Part-B first → user-facing-broken → incomplete → polish.**

### P0 — Fix before Part B (force-multipliers)
- [x] **#1 Wire up error surfacing (all 4 paths). — DONE (commits d3c92b1 + c0182aa).** New
  `ImageGenerationPage::showGenerationError()/clearGenerationError()` reuse the action-row
  `readinessHintLabel_` as a red error pill (short message + ⚠, full text in tooltip; traceback →
  log). Break 1: `syncGenerationPreviewsFromQueue` now scans for the newest FAILED item and surfaces
  `item.errorText` (deduped per mode; cleared on next submit / completed). Break 2: the three submit
  worker-down/error cases + the previously-unconnected `queuePollFailed` route to the same banner.
  **Verified LIVE:** worker killed → Generate → red "[WinError 10061] No connection…" banner instead
  of a silently-dead button (the scare, fixed). `applyWorkerMessage` intentionally stays dead (no
  live worker-message stream; one surface, not two). *Not the dead-code path the audit guessed — the
  live queue/submit paths were the right home.*
- [x] **#2 Reconcile the stale LTX contract. — DONE (commit ada2985).** Map-confirm proved the
  stale sites are NOT load-bearing: the live gate (`_raise_if_unvalidated_native_video_family`)
  reads the CANONICAL `video_family_contracts` (LTX already `production`), never
  `LtxTestWorkflowContract`; the latter's snapshot builder already overrode its defaults with the
  canonical values (dead defaults), and it's consumed only by a diagnostic command + the smoke-test
  route (nothing branches on it). Reconciled (metadata/comment only, zero behavior delta):
  `ltx_workflow_contract.py` dataclass defaults → production + its emitted `notes` reframed to
  "LTX is production native; this contract is test/smoke-path only"; the `worker_service.py`
  native-video comment updated (LTX passes the gate as production; only hunyuan/cog/mochi blocked).
  Left as-is: `worker_service.py:547` (Prompt-API fallback payload) is correctly experimental.

### P1 — User-facing broken (base degraded today)
- [ ] **#3 Image history.** Remove the `is_video_request` gate in `build_video_history_entry`
  (`worker_service.py:2369`) / add an image-history index; generalize `T2VHistoryPage`
  (`:968-973`, `:1005`). Mini-project. Gets worse with 7 new image models.
- [ ] **#4 Read `videoFamilyCombo_` into the draft** + have `VideoGenerationPolicy` honor an
  explicit override (`ImageGenerationPage.cpp:622-693`, `VideoGenerationPolicy.cpp:28-60`). Quick win.
- [ ] **#5 LTX Launch Options reachable in Simple mode.** Decouple the panel from the Advanced-tab
  disclosure gate (the family-driven visibility and the tab gate don't compose). Quick win.

### P2 — Incomplete but works on defaults
- [ ] **#6 Persist video fields** (family/video-sampler/components/LTX) in
  `saveSnapshot`/`restoreSnapshot` (`ImageGenerationPage.cpp:4120-4153`, `:4246-4309`) — they reset
  every launch.
- [ ] **#7 I2I result-payload parity** — emit `output_finalization_contract`/`metadata_write_deferred`
  (`worker_service.py:5748-5775`) like the other 3 paths.
- [ ] **#8 Verify the i2v Denoise control** — native LTX i2v uses a keyframe/bypass, not img2img
  denoise; confirm it does anything, hide if inert.

### P3 — Robustness / polish
- [ ] **#9** Output subfoldering (everything lands flat in `output/`, mode only in the filename;
  `MainWindow.cpp:1849-1862`).
- [ ] **#10** Video poster-frame thumbnails (history/preview show a live player, no still frame).
- [ ] **#11** Guard `complete_job` against the QUEUED→COMPLETED silent-fail
  (`worker_service_state.py:366-367,491`).
- [ ] **#12** Remove the hardcoded machine-path default (`ltxPromptApiExportPath`).
- [ ] **#13** Delete/replace dead widgets (`workflowCombo_` placeholders, `toggleControlsButton_`,
  `setWorkspaceTelemetry` no-op).

### Explicitly Part B (not "finish-first" — the new-model work itself)
Wan i2v; Hunyuan/CogVideoX/Mochi native (gate-blocked by design). Each also needs
`starter_node_catalog.json` entries for its custom nodes (resolver is ready; catalog needs
population per family).

---

**Recommended sequence:** P0 (#1–2) → P1 quick wins (#4, #5) → P1 image-history mini-project (#3)
→ **then open Part B.** That yields visible errors + honest family routing + a clean contract
signal — the three things that make integrating 9 models tractable rather than a blind slog.
