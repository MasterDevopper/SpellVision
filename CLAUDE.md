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

**"Native" path clarification:** the Wan and LTX "native" paths are **not pure diffusers.** They use ComfyUI but build the graph dynamically from an internal template (`backend_route="native_comfy_template"`). Wan builds its graph from code; LTX patches a repo-owned template JSON (`ltx_av_native.json`). Both are now native/production (see §6). Any future native family should **mirror this mode**, not bypass ComfyUI.

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
- **Phase C — Video.** **T2V** and **I2V** are landed (LTX + Wan native; Hunyuan/Mochi; FLUX.3 hosted API). **Long videos** layer on once base video is solid (no spec yet).
- **Phase D — Hard frontiers (last).** Native **Text-to-3D** / **Image-to-3D** adapters are not started. `Gen3DPage` exists as a **hidden** Comfy-workflow passthrough. **Dataset generation** is on the rail (`dataset`) and talks to the worker — not “integrate an existing standalone app” anymore. Character B (mesh / garments / hair / beauty) is the v1 product unknown, not a Phase-D-only item.

---

## 6. Current state (2026-08-24 code audit — still verify in code before relying on it)

- **Working end-to-end:** T2I / I2I (diffusers + native image graphs), T2V / I2V (LTX / Wan / Hunyuan / Mochi native templates + FLUX.3 hosted API), Chain Studio engine (nav-hidden), Character / Comic / Concept studios, Flows, History, Inspiration, Models Stage-1, Runtime, Dataset, Train. Debug build green 2026-08-24. Pytest **423 passed**, 2 skipped, 5 smoke deselected (`PYTHONPATH=""` required).
- **T2I / I2I:** functional cockpit (prompt → Model Stack → Asset Intelligence → action row). Shared-weight fp16 + non-destructive LoRA adapters.
- **T2V / I2V:** **functional** in-app. Older FEATURE_MATRIX “Planned” / Full-Roadmap-v0.5 lines are stale.
- **Wan video:** native template path works; MP4 plays in canvas. `backend_route="native_comfy_template"`. Wan **2.1 i2v** + VAE version-match guard landed. Wan **2.2 dual-noise i2v is RENDER-PROVEN (2026-08-28)** — the Doc 28 owner-lock ship gate is cleared. Live run through the shipped builder: 49f @ 832×480, 20 steps (10 high / 10 low), 130.4s. Frame-0 MAE **5.19** against the centre-cropped keyframe (LTX ~3.5, Hunyuan 5.55), motion monotonic (f0→f24 23.1, f0→f48 38.4), subject coherent at the last frame. The MoE handoff is correct — high `0→10` `return_with_leftover_noise=enable`, low `10→20` `add_noise=disable` — and the VAE resolved to **`wan_2.1_vae`** (16-ch), confirming the `force_version` override beats the `high_noise`/`low_noise` filename probe that would otherwise pick the 48-ch 2.2 VAE.
- **LTX video: native, production. Default route = `two_stage_distilled`** (`native_video_graphs._ltx_route_for`). Opt in to single-stage-full with `ltx_route='single_stage_full'`. LTX renders audio+video through `run_native_video` → `LtxVideoAdapter` → ComfyUI `/prompt`. Contract `validation_status="production"`. Prompt-API is **history-requeue / explicit opt-in only**. Both t2v and i2v are proven native — i2v uses a keyframe-upload bridge (`_upload_comfy_image` → `LoadImage` → `LTXVImgToVideoConditionOnly`); live frame-0 MAE ~3.5.
  - **Templates:** default distilled two-stage is `python/video_templates/ltx23_two_stage.json`. Single-stage-full still uses `python/video_templates/ltx_av_native.json` (31-node AV graph). Builders patch user inputs only. Source node IDs/inputs from a **live `/object_info` dump**, never from memory.
  - **LoRA is opt-in, no default.** `chel_ltx23` was a lora-application *test only* and skewed composition (NSFW/people regardless of prompt) — a no-lora request now bypasses node `4968` (clean rewire to the checkpoint MODEL output, no dangling ref) and renders the unbiased base. A request *with* a lora name (+ optional strength) wires `4968` with it; chel remains in the template JSON only as an explicitly-reselectable fallback. (Base `ltx-2.3-22b` still tends to insert a figure / busy foreground — that's base-model behavior, an open prompt-adherence axis, not the lora.)
  - **LTX quality & VRAM (from the native smoke test + community configs):**
    - **Steps:** the full `ltx-2.3-22b-dev` wants **25–40 steps**; our first smoke test ran **12** (explains the softness). *Distilled* variants run ~4–8 steps via `ManualSigmas` (the **Pass-B path we pruned** from `ltx_av_native.json`) — we are on the **full** model, so it needs the higher step count.
    - **CFG:** stay in the **3–5** band; the embedded template's VIDEO-modality guider default (3, node `4964`) is in-pocket. The AUDIO guider (`4963`) stays fixed.
    - **VRAM / resolution:** 768×512×97f / 12 steps peaked **~31.4 / 32 GB**. Higher native resolution improves detail but **will OOM at 97 frames on 32 GB** — LTX is a **premium, near-ceiling** path. Simple-mode defaults must **cap res×frames** accordingly. **Generate at target resolution; do not upscale.**
    - **Hard constraints (enforced in `LtxVideoAdapter.prepare_request`):** width/height **divisible by 32**; frame length must be **(N×8)+1** (49/65/97/121…). Invalid values are **snapped with a warning** rather than left to ComfyUI's 400.
    - **Prompts:** **1–2 motions max.**
    - **The 31.4 GB peak is the FULL-PRECISION 22B path** (`ltx-2.3-22b-dev`, no quantization, no offload, AV with **both** VAEs resident). Community configs report comfortable headroom at equal/larger frames on 24 GB cards — but those run **FP8 / NVFP4 quantized or distilled** variants and/or **model offload**, not the full fp16/bf16 22B. So our number is plausible for the heaviest config, and there is likely **large headroom** via (a) an **FP8/NVFP4 quantized** LTX checkpoint, or (b) **model offload** (transformer→RAM during VAE decode). **RESOLVED 2026-08-26 — quantization is NOT the resolution unlock.** A quantized variant *is* present (`ltx\dasiwa-ltx-2.3-lightspeed-treasurechest.safetensors`, 21 GB, header-probed as genuine **F8_E4M3 + U8 scales**). Measured A/B on the default two-stage route, identical prompt/dims/frames/seed, output 1536×1024×97f AV: **fp8 peak 29.49 GB vs bf16 peak 30.94 GB — only ~1.5 GB saved**, not the "large headroom" assumed above. Reason: with DynamicVRAM staging the transformer, peak is driven by **activations + VAE decode**, which quantized weights do not shrink; a 46 GB checkpoint never sits resident. **So an FP8 checkpoint alone does not buy meaningfully higher native resolution — do not plan around it.** The remaining levers are decode-side (tiled VAE decode, the **PrunaVAED** decoder from core v0.30.0) and offload during decode, not the checkpoint. Timings (fp8 81.1 s vs bf16 108.5 s) are **not** a clean speed claim — the two runs had different model-load state. **Cache trap:** a re-submit that changes only the output filename gets ComfyUI's node cache, which returned a fake "12.1 s / 23.62 GB" for fp8; vary the **seed** to force real sampling.
  - **`_comfy_object_info` — the `Connection: close` "fix" WAS the bug (corrected 2026-08-27).** The old note here said to send `Connection: close` and retry, because the ~2MB `/object_info` body reset mid-read (`ConnectionResetError`, an `OSError` not a `urllib.URLError`, so a single `urlopen` slipped it through and aborted native video gen). Measured against core v0.34.0 (6.76MB body), otherwise-identical requests: **bare / `Accept-Encoding: identity` / `gzip` → 3 of 3 succeeded; `Connection: close` (± gzip) → 3 of 3 reset.** The server closes at its end before the body flushes; the older 2.4MB core tolerated it, which is why it read as "one run in three" flakiness. **`urllib` ALWAYS sends that header** (`AbstractHTTPHandler.do_open` puts it unconditionally), so deleting the explicit one changes nothing and no `urlopen`-based fetch can avoid it — the fix is a different client. Now `comfy_prompt_client._http_get_json` (`http.client` + gzip), keeping the time-budget retry + raise-never-a-partial-dict. Result: 3/3 failures after burning the full 120s budget → 8/8 successes under 0.6s on both cores; one test 20.9s → 0.12s. Guarded by `tests/test_comfy_object_info_transport.py`.
  - **Workflow dependency resolution (Doc 46).** A ComfyUI workflow names its own deps: `properties.cnr_id` / `aux_id` / `ver` per node, and `properties.models` `[{name,url,directory}]` on loaders. `workflow_pack_resolver.py` resolves packs from those (aux_id → GitHub, cnr_id → `api.comfy.org`, then a cached `ClassPackIndex`); `node_pack_installer.py` installs from a **pinned GitHub zipball — no git** — with requirements under a **torch constraints file** and a post-install assert. **Licence is disclosed, never a gate**: kjnodes/VHS/rgthree/easy-use all normalise to `UNKNOWN`, so `is_auto_installable()` would block exactly the packs that matter — it is reserved for a future unattended toggle. 34 of 40 blocking classes now resolve to a repo URL; the rest are reported with a reason.

### Phase D — 3D generation (game assets) — PLAN ONLY, not started

Planning-grade map (surveyed 2026-06). **Re-survey live before building** — the 3D model/node landscape churns ~every 6 months; treat the chosen model as a *swappable component*, never a load-bearing assumption. Do NOT take node class names or model specifics from this note into code — pull the actual ComfyUI workflow JSON + an `/object_info` dump and ground the template the way LTX was grounded (that discipline caught the LTX prefix bug).

**Goal (developer's, specific):** game assets — buildings, weapons, animals (coarse strand/card hair), clothing, and characters where **clothing is a separate mesh, not glued to the body.**

**Core split — 3D is two layers, each with an existing home:**
- **Layer 1 — single-asset generation** = a new `native_comfy_template` family, *identical pattern to the LTX migration*: import a proven ComfyUI 3D workflow through Flows → discover → dependency-check → templatize the working graph → 3D adapter (mirror `LtxVideoAdapter`) → route by family → readiness gate. The entire on-ramp already exists.
- **Layer 2 — composition** = orchestration, belongs in **Chain Studio**. A "dressed character" is a *chain* of single-asset generations (body, garment, weapon — each generated separately) then assembled. NOT a single model call.

**Hard truths to carry forward (so they aren't relearned):**
- Open single-shot image-to-3D (Hunyuan3D / TRELLIS family, the 2026 mainstream) produces **one fused watertight mesh**. A dressed character comes out as a single surface — clothing *is* the body geometry, i.e. "glued on." **Separable garments are not a single-model capability**; they require generating each garment as its own asset (from a clean garment image) and composing — this is *why* Layer 2 exists.
- These models reconstruct **surfaces** — hair becomes sculpted geometry blobs, never strands. Strand/card hair grooming is a **post-generation Blender step**, not a generator output. Same for clean character retopo.
- VRAM: leading models are **two-stage (shape + texture/paint)** — structurally like Wan's dual-core, unlike LTX's single transformer. On the 32 GB card apply the LTX lesson: **measure, don't assume**; the texture/paint stage may stack.
- Today's candidates (will drift): **Hunyuan3D-2.1** (two-stage shape→texture, ComfyUI-native with shipped workflow templates, `.glb`+PBR out — natural *first* import-and-templatize target) and **TRELLIS.2** (MIT-licensed, thin/transparent geometry, mesh/splat/NeRF out). License matters if SpellVision ships commercially (TRELLIS MIT vs Hunyuan community).

**Build order (when Phase D opens — Phase C must be genuinely closed first):**
- **D1 — single-asset Image-to-3D, one family.** Re-survey, pick the then-best ComfyUI-native model, import workflow, templatize, adapter, gate. Scope: buildings/weapons/props/single characters. The end-to-end milestone (the `.glb` equivalent of LTX's AV `.mp4`).
- **D2 — the 3D output surface (largest net-new UI; reuses nothing from LTX).** A mesh **viewer** (orbit/turntable, not a video player), **mesh→thumbnail** rendering for history/previews, result-routing that knows a `.glb` ≠ `.mp4`. `MediaPreviewController` handles image+video only.
- **D3 — Text-to-3D** (T2I→image→I2-3D, or native T2-3D if the then-model supports it). Thin once D1+D2 exist.
- **D4 — composition layer (the separable-garment goal).** Chain-Studio orchestration: garments generated as standalone meshes + assembled. Depends on D1+D2. Hair/retopo remain explicit external Blender steps.

- **Runtime / Dataset / Train — on rail.** `ManagerPage` is rail mode `runtime` (Comfy manager, nodes, restart, paste-link import). `DatasetGenerationPage` is rail mode `dataset` (worker `generate_dataset`). `TrainPage` is a Sohya_kk launcher. Not orphans.
- **Character Studio + Comic Studio + Concept Lab — REAL, on rail.** `qt_ui/studios/CharacterStudioPage` / `ComicStudioPage` / `ConceptReferencePage`; modeIds `character` / `comic` / `concept`. Generation handoff through existing T2I/I2I path. Design: `docs/design/29_character_comic_studios.md`, `31_concept_reference_lab.md`. Look/clothes commands (`look_complete`, `clothes_only`, `garment_shrinkwrap`) are wired. **Character B** (mesh / garments / hair / beauty product gates) is **not** ship-complete — UI-exists ≠ product-complete.
- **Models page — REAL.** Rail hosts **`ModelManagerPage`** Stage-1 inventory + Inspect + bind/use + import-url. **Not** the full download/compat spec.
- **Inspiration — REAL.** `InspirationPage` moodboard + KEEP/NO + send-to-T2I/I2I. `ModePage` is leftover unused chrome.
- **Flows / Workflow Library:** works — list/detail/readiness with real imports. Dedicated content QSS.
- **The rail:** Create: **T2I, I2I, T2V, I2V, Character, Comic, Concept**. Manage: Flows, History, **Inspire**, Models, Dataset. System: **Runtime**, **Train**, Prefs. Home always present. **Chain + Gen3D hidden** unless `SPELLVISION_SHOW_ALL_MODES=1`.
- **Theme:** presets are Arcane Glass, Obsidian Studio, Neon Forge, Ivory Holograph. **Default is ArcaneGlass** via one-time QSettings migration (`appearance/showcaseMaturityPass_v1` + `appearance/themePreset`). Cyan = Success/ready only.
- **UI polish / responsive (2026-07+):** owner grades C→C+ toward S. Half-screen + restore must keep same functionality. Cleanup map: `docs/design/30_responsive_layout_final_cleanup.md`. Skills: `spellvision` + `spellvision-qt-studio-surfaces`. `SamplingController` owns sampler/scheduler/steps/CFG/seed/Random. Cockpit inspector uses adaptive `setWidthBudget`. Studio rails scroll. Bottom telemetry is themed glass strip.

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

### Qt stylesheets
- **`QString::arg` only safe for `%1`–`%9`.** Multi-token sheets use `@token@` + `.replace()` (Comic/Character, Models, Flows). Never `%10+`.
- **Never apply `shellStyleSheet()` to nested content pages** — shell stays on MainWindow.

### Responsive / half-screen
- Owner C+ gate: same functionality at half-screen and default restore. See `docs/design/30_responsive_layout_final_cleanup.md` and skill `spellvision-qt-studio-surfaces`.
- Combo boxes: `setMinimumContentsLength(10)` + elide; never let model paths inflate inspector width.
- Studio Advanced blocks live inside scroll rails.

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
- ComfyUI — execution backend (LIVE = `C:\sv_comfynext\ComfyUI`, isolated venv, post-2026-07-17 cutover; D: build = rollback — see §9.2)

**Documentation (real names — there is no numbered "Codebook").** Start here: `README.md`, `CLAUDE.md`, `brain/00 Home.md`, `docs/SPELLVISION_WORKER_PROTOCOL.md`, `docs/design/27_v1.0_task_backlog.md`, `docs/design/28_release_readiness_checklist.md`, `docs/design/SpellVision_v1.0_Roadmap.md`, `docs/design/16_theme_token_reference.md`. `docs/SPELLVISION_FEATURE_MATRIX.md` is a map — prefer code + Current State Ledger when they conflict. Many historically cited root files (`ARCHITECTURE.md`, `SPELLVISION_DEV_GUIDE.md`, `SPELLVISION_INSTALLATION_GUIDE.md`, `SPELLVISION_MODEL_MANAGER_SPEC.md`, `JOB_LIFECYCLE_CONTRACT.md`, `PINNED_VENV_COMFY_README.md`, `DEV_WORKFLOW.md`) **are not in tree**. `docs/sprints/*` are historical pass READMEs — intent, not current truth.

---

## 9. Unresolved / canonical-truth audit targets

These are genuinely forked in the codebase. **Do not assume a value — resolve in code, then update this section and `.env`/`runtime_paths.py` to match.**

1. **RESOLVED — Asset / model root = `D:/AI_ASSETS/`** (user-confirmed; models, checkpoints live there). **(NOTE: after the 2026-07-17 cutover the ComfyUI *install* moved to `C:\sv_comfynext\ComfyUI` — see §9.2 — but MODELS/checkpoints/assets stay `D:/AI_ASSETS/models`, shared into the new install via the copied `extra_model_paths.yaml`.)** The `.env` (`${SPELLVISION_ROOT}/models`) and `runtime_paths.py` (`external_assets/`) values are drift to reconcile against this, not alternatives. **Exception:** the imported-workflow library root is deliberately `<projectRoot>\runtime\imported_workflows` — project-relative on C:, by design (verified populated + working **2026-07-06**; Flows is **not** a §9 audit target — the earlier "0 workflows" was a stale empty-dir state, see §6).
2. **RESOLVED (2026-07-17 gated-ComfyUI-update cutover, `docs/design/25_gated_comfyui_update_plan.md`) — LIVE ComfyUI = `C:\sv_comfynext\ComfyUI`** (Comfy-Org core `206b9245`, 2026-07-10), run from the **ISOLATED venv `C:\sv_comfynext\.venv`** (kornia **pinned 0.8.2** + sageattention/triton-windows; **`PYTHONUTF8=1` required** or the Jul-core RES4LYF crashes stderr logging), on **:8188** (worker :8765 unchanged). Launchers (`run_ui.ps1` / `start_comfy.ps1`) repointed; the worker keeps the project `.venv` — venvs decoupled. **`D:\AI_ASSETS\comfy_runtime\ComfyUI` (cf9cbec5, May) is now the OLD build kept as ROLLBACK ONLY** (+ `F:\comfy_backup\ComfyUI_cf9cbec5_20260717`) — do NOT edit/probe it as live. `runtime_paths.py:default_comfy_root()` (`runtime/comfy/ComfyUI`) is unused drift. See the `comfyui-update-cutover` memory.
3. **`FEATURE_MATRIX` refreshed 2026-08-24** — still a map, not SSOT. Prefer this file + `brain/Planning/Current State Ledger.md`.
4. **RESOLVED — LTX is native/production.** Default route is **distilled two-stage**. Prompt-API engine kept as explicit fallback only. Both t2v and i2v are proven native. See §6.
5. **Stale Rust prerequisites** in `DEV_GUIDE` + `SPELLVISION_ARCHITECTURE.md` — purge.
6. **RESOLVED — `rebuild_ui.ps1` generator** now `Visual Studio 17 2022`, matching `run_ui.ps1` (was the non-existent `Visual Studio 18 2026`, which corrupted `CMakeCache.txt`).
