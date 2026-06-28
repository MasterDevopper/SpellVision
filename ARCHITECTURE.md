# SpellVision Architecture

This document describes how SpellVision is organized today — what lives where and why. It is intentionally a *map*, not a tutorial. It complements the high-level summary in [README.md](README.md).

## Two-process design

SpellVision is two cooperating processes, plus a third managed process for actual generation:

| Process | Code | Role |
| --- | --- | --- |
| `spellvision_ui` | `qt_ui/` (C++17, Qt6) | Frontend: shell, pages, queue UI, theming, asset management |
| `worker_service` | `python/worker_service.py` | Backend: job lifecycle, ComfyUI orchestration, per-family routing |
| `ComfyUI` | `runtime/comfy/ComfyUI/` (not part of this repo's source) | Generation runtime spawned by the worker |

The frontend connects to the worker on `127.0.0.1:8765` (configurable via the `SPELLVISION_WORKER_HOST` and `SPELLVISION_WORKER_PORT` env vars) and sends newline-delimited JSON requests. The worker spawns a thread per connection and streams back newline-delimited JSON messages (`job_update`, `progress`, `status`, `result`, `error`, plus queue/runtime messages) until the response stream is closed.

The worker manages ComfyUI's lifecycle: bootstrap, start, stop, and health probes. The frontend never talks to ComfyUI directly.

## Python (`python/`)

The Python side is organized by concern, though `worker_service.py` is still very large (~6,700 lines after extraction) and contains several concerns that should be further split. The current layout:

| File / directory | Concern |
| --- | --- |
| `worker_service.py` | Entry point. Contains the TCP handler dispatch, queue manager, command handlers, and per-family runners (`run_t2i`, `run_i2i`, `run_comfy_workflow`, `run_native_video`). |
| `worker_service_state.py` | Job state machine: `JobState`, `JobRecord`, `JobResult`, `JobProgress`, `JobError`, `JobTimestamps`, `transition_job`, `update_job_progress`, `complete_job`, `fail_job`, `cancel_job`, and the active-job registry. Self-contained, stdlib-only. |
| `worker_client.py` | CLI client used as a subprocess by the frontend's `WorkerCommandRunner`. Mirrors the wire protocol. |
| `comfy_bootstrap.py`, `comfy_runtime_manager.py`, `comfy_manager_bridge.py`, `comfy_slot_mapper.py` | ComfyUI process lifecycle and node graph construction. |
| `model_registry.py`, `model_sources.py`, `model_dependency_resolver.py`, `node_dependency_resolver.py` | Model and node metadata. |
| `runtime_paths.py`, `runtime_adapters/` | Path resolution and adapter base classes for different generation backends. |
| `video/` | Video-specific workers (`t2v_worker.py`, `i2v_worker.py`) and job schema. |
| `video_adapters/` | Per-family video adapters: `wan_adapter.py` (production), `generic_adapter.py`. |
| `video_family_contracts.py`, `video_family_readiness.py` | Family-level capability and readiness probing. |
| `ltx_*.py` | LTX-specific (experimental) workflow handling: prompt API, materialization, queue history, smoke tests. |
| `workflow_importer.py`, `workflow_scanner.py`, `workflow_profile_registry.py` | ComfyUI workflow file import and discovery. |
| `memory_optimization.py` | CUDA memory management helpers. |
| `gpu_info.py` | GPU detection and reporting. |

## C++ (`qt_ui/`)

The Qt frontend is structured around a shell + pages + controllers/presenters pattern. The top level of `qt_ui/` is currently mostly flat, with some recent extractions into subdirectories:

| Area | Files / directories | Concern |
| --- | --- | --- |
| Shell | `MainWindow.{h,cpp}`, `CustomTitleBar.{h,cpp}`, `shell/` | Top-level window, mode rail, title bar, status strip, telemetry bar |
| Pages | `HomePage`, `HomeDashboardPage`, `ImageGenerationPage`, `VideoGenerationPage`, `ManagerPage`, `ModelManagerPage`, `ModePage`, `SettingsPage`, `WorkflowLibraryPage`, `T2VHistoryPage`, `DatasetGenerationPage` | Per-feature top-level pages |
| Theming | `ThemeManager.{h,cpp}` | Dark theme, accent colors, icon recoloring at runtime |
| Queue | `QueueManager.{h,cpp}`, `QueueTableModel.{h,cpp}`, `QueueFilterProxyModel.{h,cpp}` | Local queue model and view |
| Generation flow | `generation/` (`GenerationRequestBuilder`, `GenerationResultRouter`, `GenerationStatusController`, `GenerationModeState`, `OutputPathHelpers`, `VideoGenerationPolicy`, `VideoReadinessPresenter`) | Building requests, routing results, status, video-specific policy |
| Workers (UI side) | `workers/` (`WorkerCommandRunner`, `WorkerProcessController`, `WorkerQueueController`, `WorkerResponseParser`, `WorkerSubmissionPolicy`) | Talking to `python/worker_client.py` and parsing responses |
| Preview | `preview/` (`ImagePreviewController`, `MediaPreviewController`, `PreviewFileSettler`) | Image/video preview lifecycle |
| Assets | `assets/` (`AssetCatalogScanner`, `CatalogPickerDialog`, `ModelStackState`, `LoraStackController`) | Model/LoRA discovery and selection |
| Widgets | `widgets/` (`ClickOnlyComboBox`, `DropTargetFrame`, `SectionCardWidgets`) | Reusable UI primitives |
| Workflows | `workflows/` (`WorkflowImportDialog`, `WorkflowLaunchController`, `WorkflowLibraryPage`) | ComfyUI workflow file import and launch |
| Chain | `chain/` | (In progress) chain-of-stages dataset/generation studio |
| Dashboard primitives | `DashboardGlassPanel`, `DashboardMetricChip`, `DashboardPreviewPlate`, `DashboardSurfaceTokens`, `HomeDashboardModuleRegistry`, `HomeDashboardSettings`, `HomeModuleBase`, `HomeModuleFrame` | Home page composition primitives |
| Misc | `CommandPaletteDialog`, `BottomTelemetryPresenter`, `QueueUiPresenter`, `ShellNavigationController`, `MainWindowTrayController` | Standalone shell utilities |

## Tests (`tests/`)

| File | Concern |
| --- | --- |
| `conftest.py` | Session-scoped fixtures: spawns `worker_service.py` on a free port via env vars, exposes `worker_client` (a callable that sends a JSON request and returns all worker messages). |
| `test_worker_ping.py` | Pins the ping contract: result with `ok=true`, `pong=true`, `job_id` round-tripping. Includes a strict-xfail test documenting the known ping state-machine bug (see [Known issues](#known-issues)). |
| `test_worker_queue.py` | Uses the test-only `noop_slow` command (added to `worker_service.py`) to exercise the full queued → starting → running → completed path, progress monotonicity, and cancellation. |

The project-root `conftest.py` registers the `contract` and `slow` marks and prevents pytest from descending into vendored ComfyUI tests under `runtime/`.

## Known issues

- **Ping state-machine bug.** `worker_service.py`'s ping handler calls `transition_job(job, JobState.COMPLETED)` directly from `QUEUED`. The state machine's `VALID_TRANSITIONS` table only allows `QUEUED → STARTING` or `QUEUED → CANCELLED`, so `transition_job` silently returns `False` and the job stays in `QUEUED`. The terminal `result` message therefore reports `state: "queued"` even though `ok: true` and `pong: true` are correctly set. Pinned by `test_ping_terminal_state_reaches_completed` (strict-xfail). Fix: route ping through `STARTING → RUNNING → COMPLETED` like every other command, or relax the state machine to allow the fast path.

- **`worker_service.py` is still ~6,700 lines.** The state extraction is just the first cut. Natural follow-ups: extract the queue manager, the TCP command dispatch table, and per-family runners into separate modules.

- **C++ side has many flat files in `qt_ui/`.** Some subdirectories exist (`generation/`, `workers/`, `assets/`, `widgets/`, etc.) but a significant amount still lives at the top level of `qt_ui/`. Not blocking.

## What's in `attic/`

Material that's kept in git for history but is not part of the active build:

- `attic/apply_scripts/` — single-purpose patch scripts used during sprint passes
- `attic/sprint_passes/` — per-pass README files documenting incremental changes
- `attic/cmake_backups/` — pre-edit copies of `CMakeLists.txt`
- `attic/code_backups/` — pre-edit copies of `.cpp` / `.h` / `.py` files
- `attic/debug_dumps/` — ad-hoc JSON captures from runtime debugging
- `attic/old_archives/` — historical project zip snapshots
- `attic/applied_patches/` — `.patch` files for changes that are already in the codebase
- `attic/rust_original_intent/` — the original Rust scaffolding from before the pivot to C++/Python
