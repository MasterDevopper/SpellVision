# SpellVision Architecture

How SpellVision is put together and how it runs — what lives where, what happens when someone
presses Generate, and what keeps the guarantees true between passes. It is a *map*, not a tutorial,
and it complements the summary in [README.md](README.md) and the working rules in
[CLAUDE.md](CLAUDE.md).

Everything here was checked against the tree on 2026-09-02. `tests/test_governing_docs.py` keeps
that honest: every source file this document names has to exist. It exists because this document
routed readers to four modules that had been deleted four passes earlier.

---

## 1. Three processes

| Process | Code | Role |
| --- | --- | --- |
| `SpellVision` | `qt_ui/` (C++17, Qt 6.10.2) | Shell, pages, queue UI, theming, asset discovery |
| `worker_service` | `python/worker_service.py` | Job lifecycle, graph construction, ComfyUI orchestration |
| `ComfyUI` | `C:\sv_comfynext_v034\ComfyUI` (not in this repo) | The execution engine |

The UI connects to the worker on `127.0.0.1:8765` and sends newline-delimited JSON; the worker
answers with a stream of newline-delimited messages (`job_update`, `progress`, `status`, `result`,
`error`, plus queue and runtime messages) until it closes the response. The worker owns ComfyUI's
lifecycle — bootstrap, start, health-probe, stop — on `127.0.0.1:8188`. **The UI never talks to
ComfyUI directly.** Both ports bind loopback only.

Two facts about that middle row are load-bearing and are easy to get wrong:

- **The live ComfyUI root is a resolved value, not a path you type.** `python/comfy_root.py` owns it
  (`LIVE_COMFY`), `qt_ui/shell/RuntimeProfile.cpp` mirrors it for the C++ side, and both know the
  superseded trees so a stored path carrying an old root is redirected rather than probed. There
  were eight resolvers for this before the consistency pass; there is now one per side, enforced by
  the `one-comfy-root-resolver` sweep. CLAUDE.md §9.2 lists the rollback trees — never edit or probe
  one as live.
- **The two virtual environments are decoupled.** ComfyUI runs from `C:\sv_comfynext_v034\.venv`
  (kornia pinned 0.8.2, `PYTHONUTF8=1` required); the worker runs from the project's `.venv`. A
  package installed for one is not installed for the other, and that separation is deliberate — it
  is also what the security gate means by "Comfy interpreter ≠ worker interpreter".

---

## 2. What happens when someone presses Generate

The path is worth reading once end to end, because most defects this project has found lived in a
seam between two of these steps rather than inside any one of them.

1. **The page builds a request.** `qt_ui/workers/WorkerRequestBuilder` turns the cockpit's state into
   the JSON the worker receives. It is tested directly (`ctest -R worker_request_builder`) —
   which is only possible because it was moved out of `MainWindow`, where reaching it meant
   launching the GUI. Note it has side effects despite its name: it creates the output directory.
2. **The submission policy decides whether to send it.** `qt_ui/workers/WorkerSubmissionPolicy`.
3. **It goes over the socket.** `qt_ui/workers/WorkerSocketClient` carries every one-shot command.
   (It replaced spawning `python worker_client.py` per RPC: ~79 ms → ~1.4 ms, on a 1.8 s poll.)
4. **The worker dispatches it.** `python/worker_tcp.py::handle` — one entry point for all 125
   commands. `python/worker_command_audience.py` classifies every one of them as user-facing,
   diagnostic or internal, and `tests/test_protocol_doc.py` holds the protocol document to that set.
5. **The job enters the state machine.** `python/worker_service_state.py` owns `JobState` and
   `transition_job`; `python/worker_queue.py` owns the queue; `python/worker_durable_state.py`
   persists the manifest so a restart does not lose work. The legal path is
   `QUEUED → STARTING → RUNNING → {COMPLETED, FAILED, CANCELLED}` — `QUEUED → COMPLETED` is not a
   transition, and code that assumes it silently leaves the job queued.
6. **A family builds the graph.** Diffusers routes run in-process (`python/image_runners.py`);
   native routes build a ComfyUI graph and submit it (`python/native_image_graphs.py`,
   `python/native_video_graphs.py`, `python/native_runners.py`). Which family handles a request is
   decided by a `NativeFamilyPlugin` registry, not by an `if/elif` chain.
7. **The graph is submitted and polled.** `python/comfy_prompt_client.py` posts `/prompt` and polls
   `/history/<prompt_id>`; `python/comfy_cancel.py` interrupts or dequeues on cancel.
   `python/comfy_node_aliases.py` rewrites known node renames just before submit, so a core bump
   does not silently break a template.
8. **The result comes back and is routed.** `qt_ui/generation/GenerationResultRouter` decides where
   the output goes; `qt_ui/preview/MediaPreviewController` shows it. Video is drawn through a
   `QVideoSink` → `QImage` → `QLabel` path, because `QVideoWidget` failed silently on this box.

---

## 3. Python (`python/`)

88 modules at the top level plus `video_adapters/`. `worker_service.py` is 2182 lines after the
extractions; `worker_tcp.py` is 864.

| Area | Modules | Concern |
| --- | --- | --- |
| Worker core | `worker_service.py`, `worker_tcp.py`, `worker_runtime.py`, `worker_service_state.py`, `worker_queue.py`, `worker_durable_state.py`, `worker_auth.py`, `worker_metadata.py` | Entry point, TCP dispatch, pipeline runtime, job state, queue, persistence, per-launch session secret |
| Protocol surface | `worker_client.py`, `worker_command_audience.py`, `request_payload.py` | The CLI mirror of the wire protocol, who each command is for, request coercion |
| ComfyUI lifecycle | `comfy_root.py`, `comfy_bootstrap.py`, `comfy_runtime_manager.py`, `comfy_launch_policy.py`, `comfy_endpoint.py`, `comfy_version_check.py`, `comfy_manager_bridge.py` | Where it is, how it starts, how it is reached, what version answered |
| ComfyUI graphs | `comfy_prompt_client.py`, `comfy_cancel.py`, `comfy_graph_helpers.py`, `comfy_graph_converter.py`, `comfy_slot_mapper.py`, `comfy_node_contract.py`, `comfy_node_aliases.py`, `comfy_subgraph_expander.py` | Submit, cancel, shared graph primitives, UI→API conversion, node contract diffing |
| Generation | `image_runners.py`, `native_runners.py`, `native_image_graphs.py`, `native_video_graphs.py`, `krea2_graph.py`, `krea2_regional_inpaint.py`, `qwen_image_edit_graph.py`, `upscale_engine.py`, `flux3_video.py` | The routes that actually render |
| Families | `family_capability.py`, `family_operating_points.py`, `family_install_plan.py`, `video_family_contracts.py`, `video_family_readiness.py`, `video_adapters/` | What a family can do, what it costs, whether it is ready, per-family video adapters |
| Models | `model_registry.py`, `model_classification.py`, `model_sources.py`, `model_import.py`, `model_delete.py`, `model_dependency_resolver.py`, `model_dependency_manifest.py`, `model_resolution_commands.py`, `model_resolution_offer.py`, `component_resolver.py` | Inventory, one classifier, resolution and substitution offers |
| Workflows | `workflow_importer.py`, `workflow_scanner.py`, `workflow_url_import.py`, `workflow_pack_resolver.py`, `workflow_model_declarations.py`, `workflow_architecture_inference.py`, `workflow_library_commands.py`, `node_pack_installer.py`, `node_dependency_resolver.py`, `node_registry_resolver.py` | Import a foreign workflow, resolve what it needs, install pinned |
| LTX | `ltx_workflow_contract.py`, `ltx_workflow_materialization.py`, `ltx_workflow_graph_inspection.py`, `ltx_prompt_api_*.py`, `ltx_queue_history_registry.py`, `ltx_requeue_draft_submission.py`, `ltx_smoke_test_route.py` | The LTX route and its prompt-API fallback |
| Character | `character_create.py`, `character_pack.py`, `character_export_validate.py`, `look_completion.py`, `clothes_only.py`, `garment_shrinkwrap.py`, `plate_to_sliders.py`, `lock_plate_blend.py` | The Character Studio commands |
| Resources | `runtime_paths.py`, `app_paths.py`, `runtime_identity.py`, `vram.py`, `memory_optimization.py`, `download_manager.py`, `download_commands.py`, `credential_store.py` | Paths, VRAM, memory profile, the download lane, secrets |

`python/video_adapters/` holds `base.py`, `registry.py`, `ltx_adapter.py`, `wan_adapter.py` and
`generic_adapter.py`.

---

## 4. C++ (`qt_ui/`)

204 files: a flat top level plus ten subdirectories. `MainWindow.cpp` is 6941 lines over a single
coupled component — see §7 for why that has not been split.

| Area | Where | Concern |
| --- | --- | --- |
| Shell | `MainWindow.{h,cpp}`, `CustomTitleBar.{h,cpp}`, `shell/` | Window, rail, title bar, telemetry strip, runtime profile, project root, app version, first-run |
| Generation pages | `ImageGenerationPage`, `VideoGenerationPage` | The T2I/I2I and T2V/I2V cockpits |
| Studios | `studios/` (`CharacterStudioPage`, `ComicStudioPage`, `ConceptReferencePage`) | The three authored-content surfaces |
| Manage pages | `WorkflowLibraryPage`, `T2VHistoryPage`, `InspirationPage`, `ModelManagerPage`, `DatasetGenerationPage` | Flows, History, Inspire, Models, Dataset |
| System pages | `ManagerPage`, `TrainPage`, `SettingsPage` | Runtime, Train, Prefs |
| Home | `HomePage`, `HomeDashboardPage`, `HomeDashboardModuleRegistry`, `Dashboard*` | The outputs gallery and its module primitives |
| Theming | `ThemeManager.{h,cpp}` | 26 tokens, five presets, runtime icon recoloring, contrast self-check |
| Queue | `QueueManager`, `QueueTableModel`, `QueueFilterProxyModel`, `shell/QueueUiPresenter` | Local queue model, view and presentation |
| Generation flow | `generation/` | Request building, result routing, status, mode state, sampling, video policy and readiness |
| Worker transport | `workers/` | `WorkerSocketClient`, `WorkerRequestBuilder`, `WorkerResponseParser`, `WorkerCommandRunner`, `WorkerQueueController`, `WorkerProcessController`, `WorkerSubmissionPolicy` |
| Preview | `preview/` | Image and video preview lifecycle, aspect cap, file settling |
| Assets | `assets/` | Catalog scanning, model/LoRA stacks, family licence surfacing |
| Widgets | `widgets/` | `ElidingLabel` and other reusable primitives |
| Workflows | `workflows/` | Import dialog, launch controller |
| Chain | `chain/` | Chain Studio engine — built, hidden from the rail |

**The rail** is declared once, in `shell/ShellNavigationController.cpp`: Create (Home, T2I, I2I, T2V,
I2V, Character, Concept, Comic), Manage (Dataset, Flows, History, Inspire, Models), System (Runtime,
Train, Prefs). `chain` and `gen3d` are hidden by `kV1HiddenModes` and return with
`SPELLVISION_SHOW_ALL_MODES=1`.

---

## 5. How the guarantees run

This is the part that is easy to lose, because none of it is visible in the product.

**Test lanes.** A test that needs something outside this repository has to declare it —
`needs_worker`, `needs_comfy`, `needs_network`, `needs_gpu` (see `pytest.ini`). You do not have to
remember `needs_worker`: `tests/conftest.py` derives it from the fixtures a test requests. And you
cannot successfully forget the others, because conftest blocks outbound connections for any test
that declares none of them — so an undeclared dependency **fails** instead of passing on the days
ComfyUI happens to be up. Before this, 26% of test files needed an ambient service and "green" meant
something different on different days.

**Ratchets.** A ratchet is a test that sweeps the whole tree for a property instead of checking one
call site. They are marked `@pytest.mark.ratchet` and selected by that marker, never by filename —
a list of files would have exactly the scoping bug they exist to catch.

**The sweep harness** (`tests/sweeps/`) is where the tree-wide rules live:

- `sources.py` is the **only** source list, and no rule may name a file. It uses `rglob`, because the
  flat `glob('*.py')` in the previous generation of sweeps saw 82 of 92 modules — two whole packages
  were invisible to every sweep in the repo.
- `rules.py` holds each rule as `(name, citation, applies_to, check)`. There are 19.
- `exemptions.py` is keyed by site and valued by a **reason**, never a boolean, and a test pins the
  count so adding one has to be read by a reviewer.

**The commit gate** is `.githooks/pre-commit`, installed with `scripts/dev/install_hooks.ps1`
(it sets `core.hooksPath`, so the hook is versioned like any other file). It runs the ratchets in
about five seconds. A hook slower than that gets bypassed, and a bypassed hook is worse than none.

**CI** is `.github/workflows/ci.yml`: the hermetic Python lane on Windows and Linux — Linux is not a
target, it is a cheap detector of path and case assumptions — plus a Windows job that configures,
builds and runs `ctest`. It installs `requirements_ci.txt` (CPU torch and pytest; no CUDA, no
diffusers, no weights) and runs with `PYTHONPATH` deliberately cleared, because an inherited
`PYTHONPATH` has masked real import failures on this project.

**C++ tests** are real tests, run by ctest: 17 of them, linked against `SpellVisionCore` — an
`OBJECT`-style library of everything but `main.cpp`, which is what makes widget-level testing
possible at all. Before it, one test executable was built by every configure and executed by nothing.
`responsive_matrix` is the largest: 9 surfaces × 4 window states, asserting no clipped control, no
missing Advanced, Generate reachable. Its baseline is **empty** — a known-failure list with entries
in it is a matrix that has stopped being a gate.

One trap that cost a day: **Qt test output is invisible without `QT_ASSUME_STDERR_HAS_CONSOLE=1`
in the ctest environment.** A failing widget test printed zero bytes. The console subsystem alone
was not enough.

---

## 6. Adding things

**A worker command.** Implement it, dispatch it in `worker_tcp.py::handle`, and classify it in
`worker_command_audience.py`. Three ratchets will then have opinions: the audience classification
must be complete, the wire types it emits must be registered, and the protocol document's coverage
counts must still add up. That is the intended amount of friction.

**A native family.** Register a `NativeFamilyPlugin` — do not add a branch. Ground the graph in a
live `/object_info` dump rather than in memory, and run the render before claiming the route: this
project has shipped node ids from recollection and paid for it. Templates live in
`python/video_templates/`; builders patch user inputs only.

**A sweep rule.** Add it to `tests/sweeps/rules.py` with its citation, and **measure it before it
ships** (Doc 50 rule 1). Report the naive count and the scoped count. A rule that flags 30 where 10
are real is not a rule yet.

**A C++ test.** Add the executable and an `add_test()` in `CMakeLists.txt` next to the others, link
`SpellVisionCore` and `Qt6::Test`. Widget tests need a `QApplication`; see `tests/cpp/` for the
established shape.

**A fix, in general.** Doc 50 rule 10: a rule is applied to the tree, not to the site. The
deliverable of a fix is the property that prevents its recurrence; the fix itself is the evidence.

---

## 7. What is deliberately unfinished

Each of these is a decision with a reason, not an oversight. Doc 53 §8 carries the full arguments.

- **`MainWindow.cpp` is 6941 lines** and was not split by line count. Clustering its methods by
  shared member field gives one component of 67 methods and 87 fields: there is no seam in the blob.
  What could move, moved — nine methods that touched no member field, including the request
  builders. `MainWindow.h` went from 443 to 437 lines, which is a small number and the honest one.
  The next move there is to break the coupling, not to relocate more lines.
- **`worker_tcp.py::handle` is 864 lines** and was not converted to a dispatch dict. The reason to
  do it was to make its ratchet exhaustive; measuring showed the ratchet already agrees with an AST
  reader on all 125 commands, so the failure class was closed without restructuring live protocol
  dispatch, where branch order is load-bearing.
- **TeaCache is not wired.** Its win is assumed and has never been measured here.
- **`sd3` and `cogvideox` sampler tables are empty.** Filling them by copying a neighbour would make
  an inert row look authoritative, which is worse than a gap.
- **Five family-key namespaces are pinned, not merged.** They sit at different layers; merging them
  would be applying a rule at the wrong level, which is this codebase's most expensive habit.
- **A stylesheet question is open.** A rule at the front of `ThemeManager::shellStyleSheet()` paints;
  a byte-identical rule later in the same 62-argument sheet does not. Three theories were tested and
  all three were wrong. If late rules are inert, more than one is.

---

## 8. `attic/`

Kept in git for history, not part of the build: `apply_scripts/`, `sprint_passes/`,
`cmake_backups/`, `code_backups/`, `debug_dumps/`, `old_archives/`, `applied_patches/`, and
`rust_original_intent/` — the original Rust scaffolding from before the pivot to C++/Python. There
is no Rust in the live build and it is not a prerequisite.
