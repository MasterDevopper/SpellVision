# CLAUDE.md — SpellVision

Guidance for Claude Code working in this repository. Read this fully before making changes.

> Provenance note: §4, §6, §8, and §9 were corrected against a documentation +
> live-config audit. Facts from live config (`.env`, `scripts/dev/*.ps1`,
> `python/runtime_paths.py`, `python/comfy_bootstrap.py`) are treated as canonical
> over prose docs. Genuinely unresolved forks are flagged in §9 — do not invent a
> canonical value for them.

---

## 1. What SpellVision is

SpellVision is a premium desktop AI generation studio. Its single defining promise:

> Give people the full power of ComfyUI / A1111-class generation **without making them learn node graphs.** The user states intent; SpellVision figures out which nodes are needed, wires them correctly, resolves model/node dependencies, and runs them.

That abstraction layer *is* the product. Every feature decision is judged against this: does it let a non-expert get a great result while letting a power user reach the raw knobs?

**Audience:** Eventually shipped openly to everyone. Build accordingly — showpiece *and* functional tool, not a personal script.

Abstraction-layer modules already in tree: `model_dependency_resolver.py`, `node_dependency_resolver.py`, `workflow_profile_registry.py`, `comfy_slot_mapper.py`, `workflow_importer.py`, `workflow_scanner.py`.

---

## 2. Core UX principles (non-negotiable)

### Progressive disclosure — global Simple / Advanced system
- A single app-wide **Simple / Advanced** concept, not per-feature reinventions.
- **Simple** = intent-level controls (orientation as *Portrait / Landscape*, quality presets); hides pixel math, schedulers, CFG, node internals.
- **Advanced** = the raw knobs.
- Toggleable per-surface via a checkbox; default set in Settings.
- **Rule: Advanced *reveals in place*. It never *relocates* controls to a different screen.** Muscle memory must survive the upgrade.

### Scrolling discipline
- The **generation cockpit** fits the viewport — **no scroll.** Home this in the tabbed-inspector pattern (pinned Prompt card + inspector tabs: Model / Sampling / Output / Advanced as a `QStackedWidget`).
- **Content surfaces** (model library, gallery, queue history, dataset browser) own **exactly one** scroll region — **never nested.**

### Design language
- North star is **VSCode**: custom title bar with built-in functionality, persistent left activity rail, high density that still breathes.
- Skeleton = VSCode-style shell. Skin = **ArcaneGlass**, driven entirely by `ThemeManager`. Brand anchor is the metallic-framed violet arcane-eye icon.
- Refined ArcaneGlass direction: one hero accent (violet eye-glow) as the only colored light source; platinum/steel hairlines as the structural device; cyan reserved for *semantic* ready/online signals only. (See the cockpit-shell design mockup.)

---

## 3. Architecture

Three layers, deliberate ownership split:

1. **C++ / Qt6 UI** (frontend) — lives flat in `qt_ui\` (plus subfolders: `generation/`, `assets/`, `widgets/`, `workers/`, `shell/`, `workflows/`, `preview/`, `chain/`).
2. **Python worker** (`python\`) — `worker_service.py` talks to the UI over a **local TCP/JSON protocol**.
3. **ComfyUI backend** — the execution engine.

**Settled architectural decision:** ComfyUI stays the execution engine (not replaced by native diffusers). **SpellVision owns all graph construction**, with a thin hybrid fast-path for common operations. A solo developer cannot match ComfyUI's model-support velocity. Do not propose ripping ComfyUI out.

**"Native" path clarification:** the Wan "native" path is **not pure diffusers.** It uses ComfyUI but builds the graph dynamically from an internal template (`backend_route="native_comfy_template"`). Future native work (LTX) should **mirror this mode**, not bypass ComfyUI.

**The Rust core is gone.** An early vestigial Rust job-queue stub (`spellvision_rust` / `spellvision_core`) was archived to `attic/rust_original_intent/` and unwired from `CMakeLists.txt`. Nothing in C++ references it. Note: `SPELLVISION_DEV_GUIDE.md` and `SPELLVISION_ARCHITECTURE.md` still list Rust as a prerequisite — those references are **stale** and should be purged.

---

## 4. Build & run environment

- **OS / shell:** Windows / PowerShell. **Build:** CMake (≥3.21) + MSVC / Visual Studio 2022.
- **Qt:** 6.10.2 primary (run_ui.ps1 falls back to 6.8.2 → 6.7.3). Path `C:\Qt\6.10.2\msvc2022_64\`; `Qt6_DIR = …\lib\cmake\Qt6`; `CMAKE_PREFIX_PATH` = Qt root. Components: Widgets, Svg, Multimedia, MultimediaWidgets, Concurrent.
- **CMake generator:** `Visual Studio 17 2022` — used by both `run_ui.ps1` and `rebuild_ui.ps1`.
- **Python:** 3.12+. venv at `.\.venv` (a stale `.venv_old` also exists on disk — ignore it). Torch `2.10.0+cu128`, torchvision `0.25.0`, torchaudio `2.10.0`, **CUDA 12.8**. GPU: RTX 5090, 32 GB VRAM.
- **Pinned venv:** ComfyUI runs from the same venv. Python resolution order: `SPELLVISION_COMFY_PYTHON` → `.venv/Scripts/python.exe` → `.venv/bin/python` → `sys.executable` (`PINNED_VENV_COMFY_README.md`, `comfy_bootstrap.py`).
- **Settings:** `QSettings` org=`DarkDuck`, app=`SpellVision`.

### Ports & processes
- **Worker service:** `127.0.0.1:8765` (`SPELLVISION_WORKER_HOST` / `SPELLVISION_WORKER_PORT`).
- **ComfyUI:** `127.0.0.1:8188` (`SPELLVISION_COMFY_PORT`); health-checked via `GET /system_stats`, 90 s startup timeout.

### Commands
- Build & run everything: `.\scripts\dev\run_ui.ps1` (activates venv, syntax-checks worker, configures+builds Debug, starts backend + ComfyUI, launches the exe, tears them down on close). Switches: `-NoComfy`, `-NoBackend`, `-FastDeploy`, `-QtRoot`.
- **Always `Stop-Process -Name SpellVision` before rebuilding** — prevents `LNK1168` file-lock.
- Backend/Comfy lifecycle scripts: `start_backend.ps1` / `stop_backend.ps1`, `start_comfy.ps1` / `stop_comfy.ps1`.

### Logs & a critical logging gotcha
- `build\worker_service.{stdout,stderr}.log`, `build\comfy_runtime.{stdout,stderr}.log`; session JSON in `build\.{worker_service,comfy_runtime}.session.json`.
- **`logging.info` is invisible** — root logger defaults to `WARNING`. Promote needed diagnostics to `log.warning` or above.

### Environment variables (observed)
`SPELLVISION_COMFY_PYTHON`, `SPELLVISION_WORKER_HOST`, `SPELLVISION_WORKER_PORT`, `SPELLVISION_COMFY_PORT`, `SPELLVISION_ROOT`. (Asset/Comfy roots are forked — see §9.)

### Testing
- Pytest harness against the **live** worker: session-scoped fixture spawns `worker_service.py` on a free port; `worker_client` fixture handles TCP/JSON; `noop_slow` test command exercises the full job state path.

---

## 5. v0.1.0 scope & build order

Feature spine, sequenced by dependency and current maturity. Phase A produces something demoable; later phases can't block earlier ones.

- **Phase A — Shell + proven surface.** Home, Settings, Model page, cockpit shell (rail + title bar + tabbed inspector). Land **T2I** properly in the new shell first.
- **Phase B — Image family.** **I2I** and **Chain Studio** folded into the same cockpit and Simple/Advanced model.
- **Phase C — Video.** **T2V** and **I2V** (Wan native works; LTX native move is the goal — see §6). **Long videos** layer on once base video is solid (no spec yet).
- **Phase D — Hard frontiers (last).** **Text-to-3D**, **Image-to-3D**, **Dataset generation**. 3D stages are defined in Chain Studio but execution-disabled until Python workers exist. Dataset generation will **integrate an existing standalone app** (internals TBD until shared).

---

## 6. Current state (audit-corrected — still verify in code before relying on it)

- **Working end-to-end:** SDXL image generation via **Chain Studio** (Track B, passes 8a–9.5; Track A engine proven). The most-finished surface. Note: Chain Studio is *absent* from `SPELLVISION_FEATURE_MATRIX.md` — docs badly under-represent it.
- **T2I:** functional cockpit (prompt → Model Stack → Asset Intelligence → action row). Docs under-claim it (file-mapping tasks unchecked).
- **T2V / I2V:** **functional** in-app. The `FEATURE_MATRIX` calls them "Planned" and the Full Roadmap defers them to v0.5 — **both are stale; the surfaces work.**
- **Wan video:** native template path works; MP4 plays in canvas. `backend_route="native_comfy_template"`. ✓
- **LTX video:** currently **hard-routed to the ComfyUI Prompt-API path** (`ltx_prompt_api_gated_submission`). Passes 29F (hard-route), 29H2 (redirect-before-native), 29I (queue-dispatch fix) deliberately locked it there. The LTX **UI already exposes native-style component pickers** (passes 29C/29D) — a real **UI-vs-backend divergence**.
  **Native LTX is still the goal**: route LTX through `native_comfy_template` mirroring Wan. Four-step plan: (1) `LtxVideoAdapter` + LTX branch in `_build_native_split_video_prompt()` (single transformer, `linear_quadratic` scheduler); (2) native smoke test of `run_native_split_stack_video()`; (3) update LTX contract `validation_status` + production gate; (4) remove the four LTX→Prompt-API redirects (29F/29H2/29I and the policy promotion).
- **Built but unreachable:** `ManagerPage` and `DatasetGenerationPage` exist but aren't wired into rail/Home; they have **zero documentation**.
- **Placeholder pages:** **Inspire** and **Models** render as generic `ModePage` "Planned Section / Coming Soon" stubs (the 552-line `SPELLVISION_MODEL_MANAGER_SPEC.md` is at Stage 1 only; `ModelsPage.{h,cpp}` don't exist).
- **Flows / Workflow Library:** UI shows **0 imported workflows** despite docs calling it "a usable real workflow browser." Likely tied to the asset-root fork (§9) — top audit target.
- **The rail:** **11 flat entries** (Home, Chain, T2I, I2I, T2V, I2V, Flows, History, Inspire, Models, Prefs) with no sectioning. There is **no "15-slot CREATE/MANAGE/SYSTEM" spec in the docs** — that was an erroneous claim in a prior version of this file. Sectioning is a *proposed* ArcaneGlass design direction, not an implemented or documented spec.
- **Theme:** presets are Arcane Glass, Obsidian Studio, Neon Forge, Ivory Holograph. Current default is **Neon Forge**; ArcaneGlass is the intended north-star skin — standardizing on it is pending.

Infra done: state machine extracted to `python/worker_service_state.py`; pytest TCP harness; `attic/` cleanup; fp16 + shared-weight VRAM optimization (`build_paired_pipelines` from `memory_optimization.py` NOW actually wired into `build_pipelines` in `worker_service.py` — was previously dead code; confirmed 28.5GB → 6.57GB resident on a 1024×1536 fp32-checkpoint T2I, single load plateau, resident dtype float16, no CPU offload); spacing-token system.

---

## 7. Working conventions & hard-won lessons

### Patch / edit discipline
- **Patch atomicity:** validate **ALL** anchors in **ALL** files before writing **ANY** file. A partial write that desynced a header and its `.cpp` cost a full-session detour. Apply scripts use `SystemExit` guards + `ast.parse` validation.
- **Source needles from live output:** `Select-String` against the on-disk file immediately before generating a patch; prior patches shift line numbers. **Request/read the actual current file before patching.**
- **One change at a time:** deliver a single patch, let the build confirm, then proceed. `Stop-Process` before each rebuild.
- **Commit discipline:** pass-based; commit + tag each sub-pass after a clean build. Remote `origin/main`.

### Theme spacing tokens
- From `ThemeManager` `Spacing`/`Chrome` enums. **Literal zero stays literal** (`setSpacing(0)`, `setContentsMargins(0,…)`). Off-scale snaps to nearest token (6→8, 7→8, 10→12, 14→16). Conditional/ternary spacing stays literal.

### Known bugs to respect
- **`QUEUED → COMPLETED` silently fails.** Valid: `QUEUED → {STARTING, CANCELLED}`. Strict xfail. Never assume completion unless it ran `QUEUED → STARTING → RUNNING → COMPLETED`. (A persistent non-draining queue count is a symptom worth checking.)
- **fp32 → fp16:** local SDXL fp32 checkpoints make diffusers silently ignore fp16. Fix is a runtime CPU cast before device move (~18.9 → ~11.7 GB), gated by `cast_fp32_to_fp16: bool = True`. Cast logged at `WARNING` to survive the root-logger filter.
  The cast lives in `build_pipelines` via `build_paired_pipelines`; before it was wired in, `build_pipelines` loaded TWO independent full SDXL copies (`t2i_pipe` + `i2i_pipe`) and applied no cast — fp32 × 2 copies = ~28.5GB on a single T2I. Now one shared-weight load + cast = ~6.6GB. **Resolved:** t2i and i2i share one UNet, but LoRAs are now applied as non-destructive named adapters (`load_lora_weights` + `set_adapters`, never `fuse_lora`), so each role selects its own adapter at call time and the shared UNet is correct by construction. The per-role LoRA cache (`active_lora_path_t2i` / `_i2i`) now selects/activates an adapter rather than recording a fuse. Guarded by `tests/test_worker_lora_adapters.py` (chain T2I(A)→I2I(B)→T2I(A) + no-LoRA-after-LoRA, asserting the active adapter + pixel-distance with a ~13.7× margin).

### Communication style with the developer
- Execution-focused: runnable commands and `git apply` patches over instruction documents. Concise prose; artifacts carry the weight. Request the on-disk file before patching it. Fast directional decisions.

---

## 8. Repo topology

- `qt_ui\` — C++/Qt6 UI (flat + subfolders listed in §3)
- `python\` — Python worker, adapters, resolvers
- `scripts\dev\` — dev scripts (`run_ui.ps1`, lifecycle scripts)
- `attic\` — archived apply scripts, sprint READMEs, `rust_original_intent/`, debug dumps
- `docs\` — documentation (see below)
- ComfyUI — execution backend (location forked, §9)

**Documentation (real names — there is no numbered "Codebook").** Key docs: `README.md`, `ARCHITECTURE.md` (root); `docs/SPELLVISION_ARCHITECTURE.md`, `SPELLVISION_AI_PIPELINES.md`, `SPELLVISION_DEV_GUIDE.md`, `SPELLVISION_INSTALLATION_GUIDE.md`, `SPELLVISION_FEATURE_MATRIX.md` (stale on video, omits Chain Studio — rebuild before planning), `SPELLVISION_ROADMAP.md`, `SPELLVISION_MODEL_MANAGER_SPEC.md`, `SPELLVISION_UI_SHELL_README.md`, `SPELLVISION_WORKER_PROTOCOL.md`, `JOB_LIFECYCLE_CONTRACT.md`, `PINNED_VENV_COMFY_README.md`, `DEV_WORKFLOW.md`; `docs/design/*` (Chain Studio + UI design system); `docs/product/*` (roadmaps, sprint plan, QA); `docs/sprints/*` (historical pass READMEs — intent, not current truth). A "Theme Token Reference" doc does **not** exist yet.

---

## 9. Unresolved / canonical-truth audit targets

These are genuinely forked in the codebase. **Do not assume a value — resolve in code, then update this section and `.env`/`runtime_paths.py` to match.**

1. **RESOLVED — Asset / model / ComfyUI root = `D:/AI_ASSETS/`** (user-confirmed; models, checkpoints, ComfyUI all live there). The `.env` (`${SPELLVISION_ROOT}/models`) and `runtime_paths.py` (`external_assets/`) values are drift to reconcile against this, not alternatives. **Exception:** the imported-workflow library root is deliberately `<projectRoot>\runtime\imported_workflows` — project-relative on C:, by design.
2. **ComfyUI location — forked:** `D:\AI_ASSETS\comfy_runtime\ComfyUI` (`start_comfy.ps1`) vs `runtime/comfy/ComfyUI` (`runtime_paths.py:default_comfy_root()`); a `runtime\comfy\ComfyUI_old\` also exists. Confirm which is live.
3. **`FEATURE_MATRIX` is stale** — marks T2V/I2V "Planned" (they work), omits Chain Studio. Rebuild against reality before using to plan.
4. **LTX UI-vs-backend divergence** — native-style pickers over a Prompt-API-locked backend (see §6). Resolving toward native LTX is the goal.
5. **Stale Rust prerequisites** in `DEV_GUIDE` + `SPELLVISION_ARCHITECTURE.md` — purge.
6. **RESOLVED — `rebuild_ui.ps1` generator** now `Visual Studio 17 2022`, matching `run_ui.ps1` (was the non-existent `Visual Studio 18 2026`, which corrupted `CMakeCache.txt`).
