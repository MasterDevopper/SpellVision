# Doc 20 — Worker Runtime Ground-Truth Map (evidence-only)

**Surveyed 2026-07-10. All line anchors are point-in-time and drift with edits.** Facts from live `grep`/`wc`. `[inferred]` marks intent read indirectly rather than author-stated. Where ambiguous, flagged rather than resolved. **No restructure is proposed here** — this map exists so a later refactor plan can be judged against it.

**Scope statement:** this map covers the **Python worker runtime** (`python/`, 44 files) — where the god-file, the mutable state, and the family builders live. The **C++/Qt frontend** (`qt_ui/`, 134 files / 42,329 LoC) is flagged **by measurement only** (§4); its import/state analysis is a separate pass, because breakdowns A/B/C are worker-side and C++ "module state" is a different idiom.

---

## 0. Exclusion set (auditable)

Only files that do work for the running worker are included. Excluded, with counts and reason:

| Exclusion | Count | Why |
|---|---|---|
| `attic/**` (incl. `apply_*.py`, `t2i_worker.py`) | 61 `.py` + scripts | archived one-shots / prior-intent, unwired from build |
| `*.bak` | 86 | backups (all under `attic/`) |
| `*_README.md` | 39 | docs, not executed |
| `pass*.json` | 2 | pass snapshots |
| `scripts/dev/*.ps1` | 10 | build/launch orchestration — *operate* the app but are not imported/executed as app code [borderline; noted] |
| `refactor_baseline/_capture.py`, `tests/**` | — | harnesses, not runtime (their edges were traced only to avoid false "dead" verdicts) |
| `python/video/{i2v_worker,t2v_worker,video_job_schema}.py` | 3 | **empty (0 LoC)** — see §5 (confirmed dead) |

---

## 1. CONSTRAINTS THE PLAN MUST RESOLVE FIRST

These are not observations to route around — they are preconditions. A split that ignores any of them will either duplicate logic or corrupt shared state. Each is a decision the refactor plan must make *before* moving code.

### C1 — Dual generation dispatchers that are NOT behaviorally identical
There are **two** places that switch a command string onto a `run_*` function, and they diverge:

- **Dispatcher #1 — QueueManager execute** (`worker_service.py:1776–1795`): `ltx_gated→run_ltx_prompt_api_queued_job`; `t2i→(`**`_should_route_native_image`**`? run_native_image : run_t2i)`; `i2i→(… : run_i2i)`; `comfy_workflow→run_comfy_workflow`; `t2v/i2v→(binding? run_comfy_workflow : run_native_video)`.
- **Dispatcher #2 — WorkerTCPHandler direct** (`worker_service.py:8625–8637`): `t2i→run_t2i`; `i2i→run_i2i`; `comfy_workflow`; `t2v/i2v→…run_native_video`. **⚠ This path has NO `_should_route_native_image` fork** — native-image families (flux/pixart/lumina/z_image/anima) only route natively through the queue path.

**The plan must decide:** collapse to one dispatcher, or declare the direct path legacy/removed. Until then any "unify the dispatch" work has two masters and native-image generation silently depends on which entrypoint is used. [inferred: direct path is legacy — confirm before relying on it.]

### C2 — The `req` dict is an unowned shared mutable bag threaded through every layer
A single `dict` is passed by reference enqueue → dispatch → builder → run, and **mutated in place across concern boundaries**:
- Queue writes the command keys + `queue_*`/`generation_mode`/`task_type`/`mode` (`:1618–1640`).
- Builders write `req["resolved_native_video_family"]`, `req["native_video_route"]`, `req["input_image_comfy_name"]`, `req["native_prompt_api_path"]` (e.g. `:5217/5238/5356`, `:6210`, `run_native_split_stack_video:5597`).
- Run/finalize read those back to build history, affinity, metadata.

**The plan must define an owner (or an immutable contract) for `req`.** No builder can be extracted to a module without deciding whether it returns a graph + a delta, or continues to mutate a shared dict. This is the single heaviest cross-cutting constraint.

### C3 — Command identity is smeared across 6 aliased keys
`command`, `worker_command`, `execution_command`, `dispatch_command`, `task_command`, `workflow_task_command` — written as a block (`:240–245`, `:1618–1623`) and read interchangeably via `_queue_ltx_execution_command:298` (loops all 6) + ad-hoc fallback chains (`:653–659`, `:2055–2057`, `:3183`). **The plan must normalize command identity to one field** before any dispatcher extraction, or the split inherits six-way aliasing. Enqueue validation (`:1604–1608`) and both dispatchers all key off this smear.

### C4 — Shared caches are written by one concern and read by another
| State | Written by (concern) | Read by (other concern) |
|---|---|---|
| `MODEL_CACHE:143` | pipeline-load, LoRA, memory-unload | queue-affinity (`active_affinity_signature_for_command:2157`), status (`image_runtime_cache_active:1021`) |
| `VIDEO_RUNTIME_CACHE:169` | run-result finalization | affinity + status/diagnostics |
| `QUEUE_MANAGER:2037` | 13 TCP handlers (queue concern) | drives `_run_queue_item` → builders/run_* (generation concern) |

**The plan must assign each cache to exactly one owning module** and give the other concerns a read-only accessor. `MODEL_CACHE["lora_adapters"]` is a nested dict handed out live by `_lora_adapter_registry:2774` — it aliases the outer cache and must be de-aliased or its ownership pinned.

### C5 — No hard import cycle, but lazy imports are load-bearing cycle-breaks
`model_dependency_manifest → model_registry` is deliberately function-local (`:401`); `worker_service` lazy-imports ~9 modules (`component_resolver`, `model_classification`, `model_dependency_manifest`, `video_adapters.registry:5526`, `workflow_importer:7100`, `workflow_scanner:7223`, `node/model_dependency_resolver`, `comfy_manager_bridge`). **A plan that promotes any of these to top-level imports risks reintroducing a cycle** — treat the lazy imports as intentional until proven otherwise. The LTX cluster is a deep 6-module acyclic chain; splitting there ripples.

---

## 2. Per-file map: responsibility + dependency edges

44 files. `→` = imports out (intra-repo); `←` = imported by. "lazy" = function-local import.

| Path | LoC | Actual responsibility (from reading) | → out | ← in |
|---|---|---|---|---|
| `worker_service.py` | **8666** | TCP/JSON server + job state machine + ALL generation dispatch/build/run | 17 module + 9 lazy | `refactor_baseline/_capture.py` only (harness) → **entrypoint** |
| `worker_service_state.py` | 548 | Pure job state machine (JobState enum, transitions, Job* dataclasses, `ACTIVE_JOBS`); no torch/net | — | `worker_service:50` |
| `memory_optimization.py` | 950 | Diffusers VRAM opt: `build_paired_pipelines` (shared-UNet t2i+i2i), fp32→fp16 cast | — | `worker_service` |
| `model_sources.py` | 504 | Asset ref parse + materialize (local/HF/Civitai → file) | `runtime_paths` | `model_dependency_resolver`, all 3 `runtime_adapters/*` |
| `ltx_prompt_api_submission.py` | 796 | LTX Prompt-API gated submission engine (dead-but-available fallback route) | `ltx_prompt_api_adapter`, `ltx_queue_history_registry` | `ltx_requeue_draft_submission`, `worker_service` |
| `workflow_scanner.py` | 726 | Scan ComfyUI workflow JSON → node/model/slot discovery + capability report | — | `comfy_slot_mapper`, `model_dependency_resolver`, `node_dependency_resolver`, `workflow_importer`, `worker_service`(lazy) |
| `comfy_runtime_manager.py` | 423 | `ComfyRuntimeManager`: start/stop/health-check ComfyUI subprocess | `comfy_bootstrap` | `worker_service` |
| `ltx_prompt_api_adapter.py` | 411 | LTX Prompt-API → adapter-preview contract | `ltx_workflow_graph_inspection` | `ltx_prompt_api_submission`, `worker_service` |
| `model_dependency_manifest.py` | 408 | DATA-only per-family/slot resolution rules (`COMPONENT_MANIFEST`) | `model_registry`(lazy `:401`) | `component_resolver`, `worker_service` |
| `ltx_workflow_graph_inspection.py` | 393 | Inspect LTX workflow graph (roles/nodes/links/asset extraction) | `ltx_smoke_test_route` | `ltx_prompt_api_adapter`, `worker_service` |
| `video_family_readiness.py` | 378 | Video-family readiness snapshot (LTX required-node detection via `/object_info`) | — | `ltx_workflow_contract`, `worker_service:39` |
| `model_dependency_resolver.py` | 371 | Build/apply model-install plan from a scan | `model_sources`, `workflow_scanner` | `workflow_importer`, `worker_service`(lazy), test |
| `model_registry.py` | 357 | `ModelFamilySpec` + `MODEL_FAMILIES`, `infer_model_family`, license dims | — | `model_classification`, `model_dependency_manifest`(lazy), `runtime_adapters/diffusers_adapter`, `worker_service` |
| `comfy_manager_bridge.py` | 325 | ComfyUI-Manager detect/install + custom-node clone/list | — | `node_dependency_resolver`, `worker_service`(lazy) |
| `component_resolver.py` | 318 | Generic family-agnostic component-resolution engine (T1/T2/T3), **zero family branches** | `model_dependency_manifest`, `model_classification`(lazy) | `worker_service`(lazy ×3) |
| `ltx_workflow_materialization.py` | 309 | Dry-run: patch user inputs into an LTX graph, record mutations | `ltx_smoke_test_route` | `worker_service` |
| `model_classification.py` | 299 | Layered classifier (metadata→request→dir→filename); `classify_model` | `model_registry` | `component_resolver`(lazy), `worker_service`(lazy) |
| `runtime_adapters/comfy_workflow_adapter.py` | 282 | `ComfyWorkflowAdapter` (backend=comfy_workflow) | `model_sources`, `runtime_adapters.base` | **none — orphaned (§5)** |
| `node_dependency_resolver.py` | 270 | Build/apply custom-node install plan | `comfy_manager_bridge`, `workflow_scanner` | `workflow_importer`, `worker_service`(lazy) |
| `ltx_workflow_contract.py` | 255 | Canonical LTX workflow/asset contract | `video_family_contracts`, `video_family_readiness` | `ltx_smoke_test_route`, `worker_service` |
| `ltx_smoke_test_route.py` | 234 | Contract-only T2V smoke-test route | `ltx_workflow_contract` | `ltx_workflow_materialization`, `ltx_workflow_graph_inspection`, `worker_service` |
| `ltx_requeue_draft_submission.py` | 229 | Re-submit latest requeue draft via gated LTX path | `ltx_prompt_api_submission` | `worker_service` |
| `ltx_ui_queue_history_contract.py` | 223 | Shape LTX queue/history → UI contract | `ltx_queue_history_registry` | `worker_service` |
| `comfy_bootstrap.py` | 217 | Resolve SpellVision/ComfyUI roots + managed venv python [inferred — no docstring] | — | `comfy_runtime_manager`, `worker_service` |
| `video_adapters/wan_adapter.py` | 209 | `WanVideoAdapter`: clip/scheduler/sampler selection, fp8 detection | `video_adapters.base` | `video_adapters/registry` |
| `runtime_adapters/native_video_adapter.py` | 192 | `NativeVideoAdapter` (backend=native_python) | `model_sources`, `runtime_adapters.base` | **none — orphaned (§5)** |
| `workflow_importer.py` | 188 | End-to-end import: scan→profile→node/model plans→save | `comfy_slot_mapper`, `model_dependency_resolver`, `node_dependency_resolver`, `workflow_scanner` | `worker_service`(lazy) |
| `ltx_queue_history_registry.py` | 177 | JSONL/JSON registry for LTX queue/history | — | `ltx_prompt_api_submission`, `ltx_ui_queue_history_contract`, `worker_service` |
| `video_adapters/base.py` | 175 | `VideoFamilyAdapter` base + object_info/choice helpers | — | `video_adapters/{generic,ltx,wan}_adapter`, `registry` |
| `runtime_adapters/diffusers_adapter.py` | 166 | `DiffusersAdapter` (backend=diffusers, subprocess) | `model_registry`, `model_sources`, `runtime_adapters.base` | **none — orphaned (§5)** |
| `comfy_slot_mapper.py` | 141 | Map scanned slots → saveable `WorkflowProfile` [inferred] | `workflow_scanner` | `workflow_importer` |
| `ltx_adapter.py` (`video_adapters/`) | 134 | `LtxVideoAdapter`: dim/frame snapping, node gating, LTX-template tag | `video_adapters.base` | `video_adapters/registry` |
| `runtime_adapters/base.py` | 73 | Adapter protocol dataclasses | — | 3 `runtime_adapters/*` only (self-contained) |
| `worker_client.py` | 453 | Client TCP/JSON helpers + protocol constant sets [inferred] | — | **none in Python** — consumed by Qt/scripts → protocol shim |
| `workflow_profile_registry.py` | 54 | Load/list saved workflow profiles | — | **none — verify (§5)** |
| `gpu_info.py` | 39 | Standalone: print JSON CUDA/VRAM (runs at import, no `__main__` guard) | — | **none — verify (§5)** |
| `runtime_paths.py` | 35 | `RuntimePaths` env-overridable path constants | — | `model_sources` |
| `video_adapters/registry.py` | 32 | `available_video_adapters()` + score-based `select_native_video_adapter()` | `video_adapters.{base,generic,ltx,wan}` | `video_adapters/__init__`, `worker_service`(lazy `:5526`) |
| `video_adapters/generic_adapter.py` | 19 | Fallback adapter (score 1) | `video_adapters.base` | `registry` |
| `video_adapters/__init__.py` | 3 | Re-export registry fns | `video_adapters.registry` | — |
| `video_family_contracts.py` | 233 | `VideoFamilyContract` + `VIDEO_FAMILY_CONTRACTS` | — | `ltx_workflow_contract`, `worker_service` |
| `python/video/{i2v_worker,t2v_worker,video_job_schema}.py` | 0×3 | **empty stubs** | — | none — **confirmed dead (§5)** |

---

## 3. Load-bearing module-level mutable state

All genuinely mutable state lives in **two files**. Only **2** `global` rebinds exist; everything else is a container mutated in place under a dedicated lock. Every other module's module-scope data is read-only config/registries.

### `worker_service.py`
| State | :line | Kind | Writers | Readers |
|---|---|---|---|---|
| `MODEL_CACHE` | 143 | diffusers pipeline + LoRA cache | `unload_cached_pipelines:960`, `get_or_load_pipelines:3012`, `set_cached_lora_state:2760`, `_lora_adapter_registry:2774` | `cleanup_for_model_swap:1004`, `image_runtime_cache_key/active:1016/1021`, `active_affinity_signature_for_command:2157`, `get_cached_lora_state:2754`, `get_or_load_pipelines:3012` |
| `MODEL_CACHE["lora_adapters"]` | nested | cache-within-cache (**aliases outer — see C4**) | `_lora_adapter_registry:2774` (lazy-init + handed out live) | same |
| `JOB_ARCHIVE`(+`_ORDER`) | 158/159 | job ring-buffer (cap 200) | `archive_job:2549` | `get_archived_job:2576` → retry paths |
| `VIDEO_RUNTIME_CACHE` | 169 | active video/comfy runtime tracker | `update_…_from_result:1141`, `reset_…:1279`, `invalidate_…_for_failure:1318` | `_video_runtime_cache_snapshot:1026`, `active_video_runtime_signature_for_command:1031` |
| `QUEUE_MANAGER` | 2037 | the one generation queue (instance state under `self.lock`) | 13 `WorkerTCPHandler.handle_*` `:8217–8283` | same + `snapshot_payload()` on most acks |
| `METADATA_WRITE_QUEUE` | 3187 | async write queue | `queue_metadata_write:3224` (put) | `_metadata_writer_loop:3201` (get) |
| `COMFY_RUNTIME_MANAGER` | 198 | ComfyUI process singleton (**`global`**) | `get_comfy_runtime_manager:7031` | same (sole accessor) |
| `_METADATA_WRITER_STARTED` | 3189 | writer-thread once-flag (**`global`**) | `ensure_metadata_writer:3212` | same |
| `CAST_FP32_TO_FP16` | 2959 | config bool, no writer | — | `build_pipelines:2962` |

Locks (1:1 with each container): `CACHE_LOCK:156`, `JOB_ARCHIVE_LOCK:160`, `VIDEO_RUNTIME_LOCK:168`, `VIDEO_HISTORY_LOCK:162`, `_METADATA_WRITER_LOCK:3188`, `COMFY_RUNTIME_MANAGER_LOCK:199`, + `QueueManager.lock`, `ComfyRuntimeManager.lock`.

### `worker_service_state.py`
- `ACTIVE_JOBS:44` (job_id→handle, cancellation registry) + `ACTIVE_JOBS_LOCK:45`. Writers `register/unregister_active_job:517/522`; reader `get_active_job:527`.

### Read-only registries (consumed, never mutated)
`MODEL_FAMILIES` (`model_registry:50`), `COMPONENT_MANIFEST` (`model_dependency_manifest:72`), `VIDEO_FAMILY_CONTRACTS` (`video_family_contracts:47`), `NATIVE_IMAGE_FAMILIES` (`worker_service:5768`), classifier maps `_PIPELINE_TYPE_BY_FAMILY`/`_L2_DIR_FAMILY`/`_L1_TYPE_CATEGORY` (`model_classification`). **`DEFAULT_VIDEO_RUNTIME_HINTS` (`model_registry:12`): zero readers — dead (§5).**

---

## 4. C++/Qt frontend (measurement only)

Deep import/state analysis deferred (scope statement above). 134 files, 42,329 LoC. **>1,500-line files, responsibility grounded from source:**

| File | LoC | Responsibility (from source, not filename) |
|---|---|---|
| `qt_ui/ImageGenerationPage.cpp` | 5,546 | ONE `ImageGenerationPage` class, `Mode`-parameterized (`ImageGenerationPage(Mode mode,…):360`) serving all 4 modes T2I/I2I/T2V/I2V — cockpit + video-family panels |
| `qt_ui/MainWindow.cpp` | 4,482 | App shell: `buildShell:850`, `createSideRail:914` — window, rail, navigation, worker-process wiring |
| `qt_ui/WorkflowLibraryPage.cpp` | 3,945 | Flows/workflow library UI + cycle-safe upstream conditioning-graph walk (`:114`) |
| `qt_ui/T2VHistoryPage.cpp` | 2,208 | Video/History surface (`loadLtxRegistryHistoryItems:976`) — reads the worker's on-disk history |
| `qt_ui/HomeDashboardPage.cpp` | 1,512 | Home dashboard of modules (`HomeHeroModule`, `HomeWorkflowLauncherModule`, `HomeRecentOutputsModule`, `HomeFavoritesModule`) |

(Just under: `ThemeManager.cpp` 1,122; `chain/ChainConfigPanelWidget.cpp` 1,025.)

---

## 5. Dead code — confirmed vs. verify (with the specific grep per item)

Anchors/greps run 2026-07-10.

### Confirmed dead (provably no runtime path)
| Item | Evidence (grep + result) |
|---|---|
| `python/video/{i2v_worker,t2v_worker,video_job_schema}.py` | `wc -l` → **0, 0, 0**; `grep -rn "video\.i2v_worker\|video\.t2v_worker\|video_job_schema" python/` → **empty**. Empty files, imported nowhere — nothing to run. |
| `DEFAULT_VIDEO_RUNTIME_HINTS` (`model_registry.py:12`) | `grep -rn "DEFAULT_VIDEO_RUNTIME_HINTS" python/` → only the definition + a `.pyc` byte-match; **zero source readers**. Provably unused config. |

### Verify before removing (no static caller found, but a dynamic/out-of-band path can't be ruled out by grep alone — author call)
| Item | Evidence (grep + result) | What's unresolved |
|---|---|---|
| `runtime_adapters/` package (base + `comfy_workflow`/`diffusers`/`native_video` adapters) | `grep -rn "runtime_adapters" python/ tests/ scripts/ qt_ui/ --include=*.py --include=*.cpp --include=*.h --include=*.ps1` (excl. its own package) → **empty**; `grep -n "RuntimeAdapter\|select_adapter\|backend_kind ==\|adapter_for\|get_adapter" worker_service.py` → **empty**. | A coherent 4-file adapter package with **no importer and no dynamic-dispatch reacher**. `worker_service` uses the *separate* `video_adapters/` package instead. Strongly points to deprecated/parallel abstraction, but a whole functional package → needs an author call (deprecated vs. reserved-WIP), and rules out only grep-visible reflection. |
| `workflow_profile_registry.py` | `grep -rn "workflow_profile_registry" python/ tests/ scripts/ qt_ui/` (excl. self) → **empty**. | Zero references anywhere. Role overlaps `comfy_slot_mapper.save_profile` + worker profile-listing. Could be a planned/public API — confirm intent. |
| `gpu_info.py` | `grep -rn "gpu_info" python/ scripts/ qt_ui/ *.md` (excl. self) → only **`ARCHITECTURE.md:37`** (prose "GPU detection and reporting"). No live caller; no `__main__` guard. | Could be shelled out-of-band by a launcher/diagnostic not visible to grep. Confirm nothing execs it before treating as dead. |

---

## 6. §A — `worker_service.py` section inventory (8,666 lines)

Contiguous concern-groups by top-level `def`/`class` ranges; shared state each touches noted. ⟂ marks a natural fault line.

| Lines | Concern | Key symbols | Touches state |
|---|---|---|---|
| 1–205 | Imports + constants + locks | 17 intra-repo imports; `LTX_PROMPT_API_DISPATCH_COMMANDS:221` | defines all locks + `MODEL_CACHE:143`, `JOB_ARCHIVE:158`, `VIDEO_RUNTIME_CACHE:169` |
| 206–650 | ⟂ **LTX Prompt-API** normalize + queued job | `_normalize_ltx…:238`, `_queue_ltx_execution_command:298`, `run_ltx_prompt_api_queued_job:608` | 6 command keys (C3) |
| 651–925 | Video request helpers | `is_video_request:672`, `_video_family_from_request_parts:774`, `video_request_metadata…:815` | `VIDEO_COMMANDS` |
| 927–1475 | ⟂ **Runtime/VRAM cache mgmt** | `unload_cached_pipelines:960`, `prepare_runtime_for_request:1214`, `reset/invalidate_video_runtime_cache:1279/1318`, `handle_runtime_memory_control_command:1414` | `MODEL_CACHE`, `VIDEO_RUNTIME_CACHE` |
| 1475–2041 | ⟂ **Queue management** | `QueueItem*:1475–1541`, `QueueManager:1542` (enqueue `:1599`, execute-dispatch `:1725`) | `QUEUE_MANAGER`, `ACTIVE_JOBS`, `JOB_ARCHIVE` |
| 2042–2611 | Request normalize / affinity / **history** / archive | `affinity_signature_for_request:2123`, `build_history_entry:2402`, `archive_job:2549` | `JOB_ARCHIVE(+ORDER)`, `VIDEO_HISTORY_*`, `MODEL_CACHE` |
| 2613–2888 | ⟂ **Pipeline detect + LoRA** | `detect_pipeline_type:2623`, `handle_classify_models/resolve_component_stack:2634/2664`, LoRA `2747–2888` | `MODEL_CACHE`(+`lora_adapters`) |
| 2889–3059 | ⟂ **Diffusers pipeline load** | `apply_sampler_and_scheduler:2898`, `build_pipelines:2962`, `get_or_load_pipelines:3012` | `MODEL_CACHE`, `CAST_FP32_TO_FP16` |
| 3060–3280 | ⟂ **Metadata** (payload + async writer) | `build_metadata_payload:3106`, `_metadata_writer_loop:3201`, `save_metadata:3229` | `METADATA_WRITE_QUEUE`, `_METADATA_WRITER_STARTED` |
| 3281–3454 | `EventEmitter:3281` + gen kwargs / weighted embeds | `build_generation_kwargs:3381`, `attach_progress_callback:3422` | — |
| 3455–3577 | **`run_t2i`** (diffusers) | | `MODEL_CACHE` |
| 3578–3918 | ⟂ **Comfy submit/poll/assets** + workflow bindings | `_submit_comfy_prompt:3707`, `_poll_comfy_history:3746`, `_download_comfy_asset:3815`, `_validate_comfy_prompt_against_object_info:3861` | — |
| 3919–4262 | ⟂ **Comfy object_info + node-build helpers** | `_comfy_object_info:4016`, `_upload_comfy_image:4046`, `_comfy_input_choices:4315`, `_build_clip_loader_node:4279` | — |
| 4343–4743 | ⟂ **Wan-private resolvers** (6× `_sv_core_wan_*`) | `_sv_core_wan_{choice,clip_name,vae_name,clip_vision_name}`, `_wan_vae_version_marker:4656`, `_should_use_native_wan_core_route:4701` | — |
| 4744–5052 | ⟂ **Wan builders** | `_build_native_wan_core_video_prompt:4744`, `_build_native_wan_split_video_prompt:4929` | mutates `req` (C2) |
| 5053–5205 | ⟂ **LTX builder** (template-patch) | `_build_native_ltx_video_prompt:5070` | mutates `req` |
| 5206–5345 | ⟂ **Hunyuan builder + generic video-resolve bridge** | `_resolve_native_video_stack:5206`, `_build_native_hunyuan_video_prompt:5236` | mutates `req` |
| 5346–5557 | ⟂ **Video dispatch + gates** | `_build_native_split_video_prompt:5346` (family switch), `_prepare_native_video_adapter_request:5513`, `_raise_if_unvalidated_native_video_family:5546` | mutates `req` |
| 5558–5726 | **`run_native_split_stack_video`** | | `req`, comfy |
| 5727–6298 | ⟂ **Image builders** (flux/pixart/lumina/zimage/anima) + dispatch | `_resolve_native_image_stack:5784`, `_build_*_image_prompt:5858–6255`, `_build_native_image_prompt:6265`, `_should_route_native_image:6285` | `NATIVE_IMAGE_FAMILIES` |
| 6299–6446 | **`run_native_image`** | | comfy |
| 6447–6705 | ⟂ Diffusers-native video + `run_native_video:6590` (→ delegates to split-stack at `:6610`) | | `MODEL_CACHE` |
| 6706–6960 | **`run_comfy_workflow:6706`**, **`run_i2i:6838`** | | `MODEL_CACHE` |
| 6961–7096 | `QueueEmitter:6961` + comfy-runtime glue | `get_comfy_runtime_manager:7031` | `COMFY_RUNTIME_MANAGER` |
| 7098–7621 | ⟂ Workflow import/profile/readiness commands | `handle_import_workflow:7098`, `…check_workflow_launch_readiness:7326`, `…discover_comfy_workflows:7553` | — |
| 7648–8132 | ⟂ TeaCache + node-catalog/manager/install commands | `_spellvision_teacache_*:7648–7872`, `handle_install_custom_node:8029` | — |
| 8133–8174 | `run_noop_slow` (test) | | |
| 8175–8650 | ⟂ **`WorkerTCPHandler`** — ~50-command TCP router + 15 queue handlers | dispatch `:8299–8640` | `QUEUE_MANAGER`, all `handle_*` |
| 8651–end | `ThreadedTCPServer:8651`, `main:8655` | | |

**Largest coherent extractable block:** the per-family builders + dispatch + Wan resolvers (`4343–6446`, ~2,100 lines).

---

## 7. §C — Per-family video builders (facts; generalization is later)

| Family | Builder (:line) | Construction style | Companion resolution | Sampler / conditioning nodes | Shared helpers |
|---|---|---|---|---|---|
| **Wan core** | `_build_native_wan_core_video_prompt:4744` | imperative `_add_node` (×15) | **6 Wan-private** `_sv_core_wan_*` | `KSamplerAdvanced`, `WanImageToVideo`, `EmptyHunyuanLatentVideo` | `_first_available_class`(×14), teacache, `_filename_prefix_from_output` |
| **Wan wrapper** | `_build_native_wan_split_video_prompt:4929` | imperative `_add_node` (×8) | `_sv_video_*` + `_sv_add_wan_empty_embeds_node` | `WanVideoSampler` [inferred] | `_first_available_class`(×8), `_sv_set_default_required_inputs`(×8), teacache |
| **LTX** | `_build_native_ltx_video_prompt:5070` | **template-JSON patch** of `video_templates/ltx_av_native.json` (`json.loads:5081`) | hardcoded template defaults | `LTXVImgToVideoConditionOnly` (bypass flag) | `_filename_prefix_from_output` only |
| **Hunyuan** | `_build_native_hunyuan_video_prompt:5236` | inline dict literal | **generic `resolve_stack`** via `_resolve_native_video_stack:5206` | `SamplerCustomAdvanced`, `HunyuanImageToVideo`/`EmptyHunyuanLatentVideo`, `DualCLIPLoader` | `_filename_prefix_from_output` |
| dispatch | `_build_native_split_video_prompt:5346` | family `startswith` switch + intra-Wan route select (core/wrapper by installed nodes) | — | — | — |

**Shared across all four:** only `_filename_prefix_from_output` + the downstream run/submit/poll/download path (`run_native_split_stack_video` → `_submit_comfy_prompt`/`_poll_comfy_history`/`_extract`/`_download_comfy_asset`).

**What a common spine would have to abstract** [inferred — facts only]: **three incompatible resolution mechanisms** (Wan's 6 private resolvers · Hunyuan's generic `resolve_stack` · LTX's hardcoded template values) and **three incompatible construction styles** (`_add_node` imperative · inline dict · template-JSON patch), plus per-family sampler chains and per-family conditioning nodes. Hunyuan is the only video builder already on the generic resolver; the image path (`_resolve_native_image_stack:5784` + `_build_native_image_prompt:6265` dispatch, 5 families) is the closest existing model of a unified spine.

---

## 8. Method caveats
- `worker_service.py` is **8,666 lines**, not the ~7,151 cited at task time (grew with the Hunyuan builders). All anchors 2026-07-10; they drift with edits.
- "Importers IN" counts only runtime Python imports; two grep false-positives were falsified (`worker_service_state`/`worker_client` contain the literal string `"video_family_readiness"` in constants, not imports).
- No module docstring on `comfy_bootstrap.py`, `comfy_slot_mapper.py`, `worker_client.py` — their responsibilities are `[inferred]` from defs.
