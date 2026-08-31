---
title: Python Worker Architecture Redesign Notes
type: planning
status: analysis
updated: 2026-07-25
authority: code + contracts > CLAUDE/brain > design 25–28 > ARCHITECTURE/README
scope: redesign notes only — no code changes in this analysis pass
---

# SpellVision Python Worker + Architecture + Contracts — Deep Redesign Notes

**Evidence date:** 2026-07-25  
**Repo:** `C:\Users\xXste\Code_Projects\SpellVision`  
**Promise (product):** ComfyUI/A1111-class power without node graphs; SpellVision owns graph construction.

---

## 0. Executive snapshot

| Layer | Live path | Owns |
|-------|-----------|------|
| Qt6 UI | `qt_ui/` (single CMake target `SpellVision`) | Shell, cockpits, request build, queue UX |
| Python worker | `python/worker_service.py` (~**10,067** LOC god file) + satellites | Jobs, routing, builders, Comfy lifecycle |
| ComfyUI | **LIVE** `C:\sv_comfynext\ComfyUI` + `C:\sv_comfynext\.venv` | Node execution |
| Transport | NDJSON TCP `127.0.0.1:8765` → Comfy HTTP `:8188` | UI never talks to Comfy |

**v1.0 arcs (authoritative synthesis):** Families ~85% · UI polish ~70% · **Shipping ~15% (true gate)**.

**Redesign principle:** Keep Comfy as execution engine + native template ownership. Split the god file; fix path/docs drift; finish shipping arc. Do **not** replace Comfy with pure-diffusers product path.

---

## 1. End-to-end generation flows

### 1.1 T2I (image)

```
UI GenerationRequestBuilder
  → WorkerCommandRunner / enqueue_job (typical) OR bare command (tests/TCP)
  → worker_service WorkerTCPHandler.handle
  → QueueManager.enqueue → _run_queue_item  OR  direct dispatch
  → dispatch_generation("t2i", …)   # single dispatcher (Doc 21 C1 landed)
       ├─ request_has_workflow_binding? → run_comfy_workflow
       ├─ _should_route_native_image?   → run_native_image  (Flux/PixArt/Lumina/Z-Image/Anima via Comfy graph)
       └─ else → run_t2i               (diffusers pipeline path)
  → prepare_runtime_for_request (image vs video cache unload)
  → get_or_load_pipelines / memory_optimization shared-weight+fp16
  → maybe_load_lora (named adapters, never fuse)
  → pipe(**kwargs) → PNG + metadata sidecar
  → complete_job → job_update + result → archive
```

**Evidence:**
- `dispatch_generation` @ `python/worker_service.py:398–432`
- `run_t2i` @ `:3544–3664` — STARTING→load→RUNNING→save→`complete_job`
- Native image fork @ `_should_route_native_image` `:7510` + `run_native_image` `:7524` (Comfy graph; unloads diffusers cache first)
- Product UI path is **enqueue-first** (Doc 21 I-1: `worker_client` maps generation → `enqueue`)

### 1.2 LTX T2V (native Comfy template — production default)

```
UI T2V cockpit (family=ltx, stack, frames/w/h/steps…)
  → enqueue t2v
  → dispatch_generation → run_native_video
  → _infer_native_video_family → contract gate (_raise_if_unvalidated)
  → _is_split_video_stack_request?  # true for safetensors / split_stack / wan_dual_noise / LTX templates
       → run_native_split_stack_video
            → ensure_comfy_runtime → /object_info (retry×5)
            → video_adapters.select → LtxVideoAdapter.prepare_request
                 snaps w/h ÷32, frames (N×8)+1
            → _build_native_ltx_* (template patch: ltx_av_native.json / ltx23_two_stage.json)
            → validate graph vs object_info
            → POST /prompt → poll history → download asset → metadata
            → complete_job + video_completion_diagnostics + runtime cache
  [legacy] ltx_prompt_api_gated_submission still exists for history requeue / fallback only
```

**Evidence:**
- LTX contract `validation_status="production"`, `backend_route="native_comfy_template"` — `video_family_contracts.py:64–82`
- Adapter snaps — `video_adapters/ltx_adapter.py:102–129`
- Templates — `python/video_templates/ltx_av_native.json`, `ltx23_two_stage.json`
- `run_native_video` no longer redirects LTX to prompt-api (`:7823–7836`)
- Split path is the real production path for on-disk `.safetensors` stacks (`_is_split_video_stack_request` `:4215–4227`)

### 1.3 Dual execution models still coexist

| Path | When | Engine |
|------|------|--------|
| Diffusers image | SDXL/Pony/etc. default T2I/I2I | Worker process torch |
| Native Comfy image | Flux/PixArt/… families | Comfy graph |
| Native Comfy video template | Wan/LTX/Hunyuan/Mochi production | Comfy graph (SpellVision-built) |
| Diffusers video residual | Non-split stack path in `run_native_video` | Worker torch + `export_to_video` |
| Imported workflow | Flows binding | Comfy profile + slot mapper |
| LTX prompt-API gated | Explicit commands / requeue | Legacy LTX modules |

**Redesign implication:** Product “native” already means **Comfy graph owned by SpellVision**, not pure diffusers. Diffusers image path remains a high-value fast path for classic SDXL; video product path should stay Comfy-template-first.

---

## 2. Job state machine + queued→completed bug

### 2.1 Canonical SM (`worker_service_state.py`)

```
VALID_TRANSITIONS:
  queued   → starting | cancelled
  starting → running | failed | cancelled
  running  → completed | failed | cancelled
  terminal → ∅
```

Helpers: `create_job`, `transition_job` (silent `False` on illegal), `complete_job` (builds fat `JobResult` then transitions COMPLETED), `fail_job`, `cancel_job`, `ACTIVE_JOBS` + cooperative cancel.

**Queue SM is parallel, not identical:** `QueueItemState` adds `preparing`/`skipped`; maps STARTING→PREPARING.

### 2.2 Known bug: `queued → completed` silent fail

**Where:** `WorkerTCPHandler` ping path `:10016–10020`:

```python
transition_job(job, JobState.COMPLETED)  # ILLEGAL from QUEUED
job.result = JobResult(task_type="ping")
# job.state stays queued; result still ok/pong
```

**Pinned:** `tests/test_worker_ping.py` strict-xfail `test_ping_terminal_state_reaches_completed`.  
**Docs:** `ARCHITECTURE.md` Known issues; brain `Known Bugs and Footguns`; skill/CLAUDE.

**Impact:** C++ keys off `ok`/`pong` for health — latent contract hole. Any future “fast complete” control command will hit the same trap if it skips STARTING/RUNNING.

**Fix (trivial, high ROI):**
1. Ping: `STARTING → RUNNING → COMPLETED` (or allow intentional fast-path transition in SM with audit log), **or**
2. `transition_job` logs WARNING on rejected transition (today silent).

**Do not** broaden to allow arbitrary `queued→completed` without message type discipline — that weakens the lifecycle contract UI buttons rely on (`docs/JOB_LIFECYCLE_CONTRACT.md`).

### 2.3 Lifecycle contract vs wire protocol drift

| Surface | Truth |
|---------|--------|
| `JOB_LIFECYCLE_CONTRACT.md` | `job_update` envelope; valid transitions; UI button rules |
| `SPELLVISION_WORKER_PROTOCOL.md` | Still lists T2V/I2V as **“Future”**; suggests event types `status/progress/result` without full `job_update` primacy |
| Live worker | Emits both job_update stream **and** legacy `result`/`error`; 50+ control commands; queue_* family |

**Redesign:** Promote protocol doc to versioned OpenAPI-ish NDJSON schema generated from a command registry; mark protocol doc current as **stale**.

---

## 3. Family contracts maturity matrix

Source of truth: `python/video_family_contracts.py` (+ `family_operating_points.py` folded into snapshot).

| Family | validation_status | backend_route | T2V | I2V | Stack | Adapter module | Notes / blockers |
|--------|-------------------|---------------|-----|-----|-------|----------------|------------------|
| **wan** | production | native_comfy_template | ✅ dual-noise | ✅ 2.1 single; ⚠️ 2.2 dual-noise i2v open | wan_dual_noise | `wan_adapter.py` | VAE 2.1 vs 2.2 channel footgun mitigated; Option B still Arc-1 |
| **ltx** | production | native_comfy_template | ✅ | ✅ | ltx_av_single_pass | `ltx_adapter.py` | Default distilled two-stage; full single-stage near 32GB ceiling |
| **hunyuan_video** | production | native_comfy_template | ✅ | ⚠️ contract says **blocked** core CLIPVision 768-vs-1024; kijai wrapper path claimed render-verified in Doc 26 | single_transformer | builders in god file | **C8 contradiction** Doc26 vs contract notes — re-verify post cutover |
| **mochi** | production | native_comfy_template | ✅ | — | single | builders in god file | Apache-2.0; t2v-only |
| **cogvideox** | detected | future_comfy_profile | — | — | — | none | Post-v1.0 |
| **workflow** | configured | comfy_workflow_profile | depends | depends | profile | Flows | Import path |
| **unknown** | unsupported | unknown | — | — | — | generic | Hard refuse |

**Image families (not in video contracts):** SDXL/Pony path = diffusers; Flux/PixArt/Lumina/Z-Image/Anima = native Comfy image builders inside god file (`_build_flux_image_prompt` etc.).

**Adapter registry gap:** only Wan + LTX + Generic registered (`video_adapters/registry.py`). Hunyuan/Mochi are **builders-only** — incomplete adapter layer vs contract claim of uniform native pattern.

**Production gate code:** `_raise_if_unvalidated_native_video_family` refuses non-`production` — but comments in `run_native_video` still mention hunyuan/mochi as blocked, while contracts mark them production (comment drift).

---

## 4. Abstraction layer completeness vs product promise

### 4.1 What exists (real product spine)

| Module | Role | Maturity |
|--------|------|----------|
| `video_family_contracts.py` | Family capability SSOT | Strong for video |
| `video_adapters/*` | Request snaps + node presence | Partial (2 families) |
| `model_dependency_resolver.py` | Workflow model install plans + extra_model_paths | Solid for Flows |
| `node_dependency_resolver.py` | Missing node → manager/git plan | Solid for Flows |
| `workflow_scanner/importer/profile_registry` | Import → profile | Working |
| `comfy_slot_mapper.py` | Slot binding | Present |
| `component_resolver.py` / `model_classification.py` | Stack / family classify | Present |
| `family_operating_points.py` | Fast/quality tables in contracts snapshot | Present |
| `memory_optimization.py` (~950 LOC) | Shared-weight + fp16 image | Proven + tests |
| `comfy_bootstrap` / `comfy_runtime_manager` | Launch/health | Working on live machine |

### 4.2 Gaps vs promise (“user states intent; SV wires nodes + deps”)

1. **Guided dep resolution not productized** — Doc 19 epic + Doc 28/Arc-3; HF token/format/placement lessons not automated first-run.
2. **No single “FamilyPlugin” package** — contracts ≠ adapters ≠ builders (builders still god-file).
3. **License badges not UI-surfaced** — data exists; Doc 26 §4 open.
4. **Dual mental model** — “native” overloaded (diffusers residual vs Comfy template).
5. **runtime_adapters/** (diffusers/comfy_workflow/native_video) — Doc 21 marks **likely dead / unimported**; parallel incomplete abstraction.
6. **VRAM ceilings** encoded as comments/operating points, not a first-class resource planner with user-facing caps on Simple mode consistently for all families.
7. **Protocol/command surface** is a 200-line if-ladder, not a registry — hard for UI/docs/tests to stay honest.

**Verdict:** Abstraction layer is **~70% of the product promise for power users on a configured machine**, **~15% of the promise for a clean-machine stranger** (shipping/deps).

---

## 5. Shipping readiness (installer / first-run gaps)

From Doc 28 (skeleton), Roadmap Arc-3, Current State Ledger:

| Gate | Status | Evidence |
|------|--------|----------|
| Functional gen on **dev** machine | Strong | Ledgers green for T2I/T2V/I2V/native LTX/Wan |
| Clean-machine smoke | **Missing** | Doc 28 unchecked |
| Installer bundles Qt + py + torch + Comfy + custom nodes | **Missing / hard spike** | Multi-GB CUDA + dual venv |
| First-run wizard | Pieces exist (`gpu_info` mostly unused by UI; C++ nvidia-smi) | Not assembled |
| Guided deps (format-aware) | Map only (Doc 19) | Manual 3× this session history |
| License/compliance pack | Unfinished | Hunyuan NC badges; node licenses |
| Security: pin nodes to commits, safetensors preference, loopback bind | Partial | Binds 127.0.0.1; node install floats risk |
| Doc 28 itself | **SKELETON** | Not executable gate |

**Live vs packaged path drift (blocks shipping truth):**

| Resource | Live/dev | Code defaults |
|----------|----------|---------------|
| Comfy root | `C:\sv_comfynext\ComfyUI` (`start_comfy.ps1`, `run_ui.ps1`) | `runtime_paths.COMFY` → `external_assets/comfy_runtime/ComfyUI`; `default_comfy_root()` → `runtime/comfy/ComfyUI` |
| Comfy venv | `C:\sv_comfynext\.venv` | Often project `.venv` via `SPELLVISION_COMFY_PYTHON` / PINNED_VENV docs (partially stale vs dual-venv reality) |
| Models | `D:/AI_ASSETS/models` (brain ADR) | `SPELLVISION_MODELS` or `external_assets/models` |
| Worker venv | repo `.venv` | correct |

**Redesign shipping bar:** single **RuntimeManifest** (JSON) written by installer + first-run, read by worker/bootstrap/UI — kill path forking.

---

## 6. POSITIVES (keep)

1. **Correct architecture bet** — Comfy stays executor; SpellVision owns graphs (ADR-001/002). Solo-dev velocity match.
2. **Native LTX path** — template-owned AV, constraint snaps, two-stage default, production contract.
3. **Wan dual-noise + core/wrapper routes** — production t2v; adapter picks CLIP/samplers from live object_info.
4. **Job SM extraction** — `worker_service_state.py` pure/stdlib (Sprint16 Option A) — template for further splits.
5. **dispatch_generation unification** — Doc 21 C1 landed; TCP + queue share forks.
6. **LoRA as named adapters** — never fuse; tests `test_worker_lora_adapters.py`.
7. **memory_optimization** shared-weight + fp16 cast for image paired pipelines.
8. **object_info grounding culture** — retries, validation before submit, debug prompt dumps.
9. **Flows import + node/model resolvers** — real abstraction seed for guided deps.
10. **Family contracts + operating points snapshot** — UI can stay generic (`video_family_contracts` command).
11. **Characterization tests** — dispatch, wan dual-noise builder, queue/noop_slow, workflow import.
12. **Brain vault + authority order** — reduces stale-doc planning risk when followed.
13. **UI still CMake-only target** — clean process boundary (no Rust).

---

## 7. NEGATIVES (fix / replace)

1. **God file** — `worker_service.py` **10,067** LOC (ARCHITECTURE still says ~6700 — C11). Contains: TCP dispatch, QueueManager, image/video builders, Comfy HTTP, history, LTX command zoo, TeaCache, memory control…
2. **Path drift triad** — `runtime_paths.py` / `comfy_bootstrap.default_comfy_root` / scripts hardcoded `sv_comfynext` / worker `default_comfy_root()`.
3. **Stale docs** — README “LTX experimental”; FEATURE_MATRIX video Planned; protocol T2V “Future”; ARCHITECTURE missing LTX adapter & line counts; PINNED_VENV vs dual venv.
4. **Shipping ~15%** — no installer, no clean-machine proof.
5. **VRAM ceilings** — LTX full ~31.4GB on 32GB; Simple caps incomplete productization.
6. **Dual venv complexity** — worker `.venv` + Comfy isolated `.venv`; torch/kornia pins; PYTHONUTF8=1 required.
7. **JobResult god-dataclass** — 100+ optional video fields; complete_job is a copy-paste sink.
8. **LTX command alias explosion** — dozens of synonym commands in TCP handler for Sprint15C ladder still in production surface.
9. **Adapter incompleteness** — Hunyuan/Mochi not in `video_adapters/`.
10. **Silent transition_job failures** — observability hole beyond ping.
11. **logging.info invisible** — root WARNING.
12. **Dead-ish modules** — `runtime_adapters/`, possibly `gpu_info.py` (UI uses nvidia-smi).
13. **Hunyuan i2v truth fork** — contract vs Doc 26.
14. **Tests omit real GPU gen by default** — smoke deselected; no CI-grade render gate for ship.

---

## 8. Industry comparison

| Product | Model | Relevance to SpellVision |
|---------|-------|---------------------------|
| **Runway / Luma / Pika** | Cloud SaaS, closed models, no local graphs | UX bar for Simple mode; not architecture |
| **Fal / Replicate** | Stateless GPU APIs, versioned models | Pattern for **family contract as API surface**; versioned endpoints |
| **Comfy Desktop / ComfyUI** | Full node graph local | **Opposite UX**; SV sits as opinionated shell **on top** |
| **Stability / SD WebUI Forge** | Local, extension soup | Warns against extension-centric UX; keep graph ownership |
| **Midjourney** | Closed Discord/cloud, extreme Simple | Progressive disclosure target for non-experts |
| **InvokeAI / Fooocus** | Local app, reduced knobs | Closest peer class: desktop + local models |
| **Adobe Firefly** | Cloud, commercial license clarity | License badge + commercial toggle bar |

**Positioning niche:** Local, multi-family, **no nodes**, desktop showpiece — between Fooocus simplicity and Comfy power. Shipping quality must match Invoke/Fooocus installers, not “clone repo + venv”.

---

## 9. Multi-billion-$ architecture: keep vs replace

### KEEP (strategic assets)

- Three-process split: Qt shell ↔ thin job service ↔ Comfy executor  
- SpellVision-owned graph construction (native templates + code builders)  
- Family contracts as product catalog API  
- Progressive Simple/Advanced disclosure  
- Import/Flows + dep resolvers (seed of guided install)  
- Job lifecycle semantics (once ping fixed)  
- Local-first privacy / high-VRAM creative pro segment  

### REPLACE / REBUILD

| Current | Replace with |
|---------|----------------|
| 10k LOC god file | Package: `spellvision_worker/{api,queue,jobs,families/{wan,ltx,...},comfy,image_diffusers}` |
| if-ladder commands | Generated `CommandRegistry` + schema; versioned protocol |
| Fat `JobResult` | Core result + `details: dict` / typed extensions per media |
| Path env soup | Single `RuntimeManifest` + installer writes it |
| Dual ad-hoc venvs | Locked runtime bundle (uv/pixi or embedded python) with one Comfy runtime image |
| Docs sprawl + FEATURE_MATRIX | Brain ledgers + generated matrix from contracts |
| Partial adapters | Mandatory `FamilyPlugin`: contract + adapter + builder + tests + operating points |
| Silent SM rejects | Hard fail or structured transition events |
| LTX legacy command zoo | Collapse behind one `family.debug` / `family.requeue` namespace |
| Manual first-run deps | Guided resolver product (Doc 19) as core ship feature |

### DO NOT DO

- Rewrite UI in web/Electron “for shipping” mid-v1 (kills ArcaneGlass investment)  
- Rip Comfy for pure diffusers video (velocity suicide; ADR settled)  
- Big-bang rewrite without characterization harness (Doc 21 G-dispatch/G-graph pattern is correct)

---

## 10. Technical debt inventory (ranked)

| Rank | Debt | Severity | Effort | Ship-block? |
|------|------|----------|--------|-------------|
| 1 | **Installer + first-run + guided deps** (Arc-3) | P0 product | XL | **YES** |
| 2 | **Path/RuntimeManifest drift** (sv_comfynext vs runtime_paths vs env) | P0 reliability | M | Soft-yes (wrong machine fails) |
| 3 | **God-file split** along Doc 21 seams (queue, dispatch table, families, comfy http) | P1 maintainability | L | No (health) but burns velocity |
| 4 | **Protocol doc + command registry** drift | P1 | M | No |
| 5 | **Ping/SM silent transition** | P2 contract | S | No |
| 6 | **Hunyuan i2v truth + Comfy gated update** | P1 family | M | Partial (license + i2v cell) |
| 7 | **Wan 2.2 dual-noise i2v** | P2 quality | M | No (2.1 green) |
| 8 | **License badges UI** | P1 compliance | S–M | Soft-yes legal |
| 9 | **Adapter parity** (Hunyuan/Mochi plugins) | P2 | M | No |
| 10 | **JobResult / complete_job obesity** | P2 | M | No |
| 11 | **LTX alias command surface** | P2 | S | No |
| 12 | **Dead modules** (`runtime_adapters/`, `gpu_info`?) | P3 | S | No |
| 13 | **Stale README/FEATURE_MATRIX/ARCHITECTURE** | P2 planning hazard | S | No |
| 14 | **VRAM policy productization** | P2 UX | M | Soft |
| 15 | **Test pyramid: no default GPU golden renders in CI** | P2 | L | Soft for release confidence |
| 16 | **logging level / observability** | P3 | S | No |
| 17 | **Mode-aware history spine** (UI Arc-2 #12) | P1 UX | L | No for “runs” yes for polish bar |
| 18 | **Doc 28 fill-out + license audit of custom nodes** | P0 compliance | M | **YES** |

---

## 11. Worker structure map (for split plan)

```
worker_service.py (~10067)
├── LTX prompt-api bridge & queue special-case     ~245–745
├── video metadata / runtime cache / memory ctl    ~746–1575
├── QueueItem + QueueManager                       ~1577–2130
├── history / retry / affinity                     ~2131–2700
├── classify / component stack / LoRA / pipelines  ~2700–3540
├── run_t2i / comfy HTTP helpers                   ~3544–4500
├── Wan/LTX/Hunyuan/Mochi graph builders           ~4500–6740
├── run_native_split_stack_video                   ~6740–6897
├── native IMAGE builders + run_native_image       ~6899–7815
├── run_native_video (diffusers residual)          ~7816–7930
├── run_comfy_workflow / run_i2i                   ~7932–8224
├── Comfy runtime + workflow import handlers       ~8253–9525
├── WorkerTCPHandler command ladder                ~9569–10050
└── main TCP server                                ~10052–10067

Already extracted:
  worker_service_state.py  — SM
  video_adapters/*         — partial
  video_family_contracts   — catalog
  comfy_bootstrap/manager  — process
  model/node resolvers     — deps
  memory_optimization      — image mem
  ltx_*.py                 — legacy ladder backends
```

**Recommended extract order (behavior-preserving, Doc 21 style):**
1. Fix ping transition + log illegal transitions (S)  
2. `commands/registry.py` — move TCP if-ladder  
3. `queue/manager.py` — QueueManager block  
4. `comfy/http_client.py` — object_info/prompt/poll/upload  
5. `families/{wan,ltx,hunyuan,mochi,image_native}.py` — builders + plugins  
6. Collapse LTX debug commands behind registry aliases  
7. Delete or wire `runtime_adapters/`  

---

## 12. Docs truth table

| Doc | Trust | Issue |
|-----|-------|-------|
| Live code + `video_family_contracts.py` | **Canonical** | — |
| `.env` / `scripts/dev/*.ps1` | **Canonical for paths** | Dual with code defaults |
| CLAUDE.md + brain ledgers | High | Keep patched |
| Doc 25–28, v1.0 Roadmap | High for intent | Doc 28 skeleton; Character/Comic ship-scope vs code-exists (C7) |
| Doc 21 refactor plan | High for worker split | C1 done; C2 closed; rest pending |
| Doc 20 ground truth map | High historical | Re-anchor line numbers (file grew) |
| `JOB_LIFECYCLE_CONTRACT.md` | High for SM | Align emitters |
| `SPELLVISION_WORKER_PROTOCOL.md` | **Stale** | T2V future; incomplete events |
| `ARCHITECTURE.md` | Map + stale counts | LTX adapter missing; ~6700 LOC wrong |
| `README.md` | **Stale** | LTX experimental |
| `FEATURE_MATRIX` | **Do not plan from** | Video Planned; no Chain |
| PINNED_VENV README | Partially stale | Dual venv post-cutover |

---

## 13. Tests structure overview

| File | Role |
|------|------|
| `tests/conftest.py` | Session worker subprocess + client |
| `test_worker_ping.py` | Contract + xfail SM bug |
| `test_worker_queue.py` | noop_slow lifecycle/cancel |
| `test_dispatch_characterization.py` | C1/C3 pins |
| `test_wan_dual_noise_builder.py` | Graph builder |
| `test_worker_lora_adapters.py` | Image LoRA policy |
| `test_worker_workflow_import.py` | Flows |
| `test_family_operating_points.py` / image builders | OP tables |
| `test_e2e_lifecycle.py` / `test_e2e_smoke.py` | Heavier; smoke often deselected |
| `test_comfy_graph_converter.py`, teacache, node_registry | Unit seams |

**Gap:** no default CI render of LTX/Wan/SDXL; ship confidence is owner-machine smoke.

---

## 14. CMake top-level shape

- **Single target:** `qt_add_executable(SpellVision …)` — UI only  
- Qt6: Widgets Svg Multimedia MultimediaWidgets Concurrent Network  
- FetchContent **libwebp** v1.5.0 decode-only (thumbnails)  
- Sources: flat `qt_ui/*` + `generation/`, `workers/`, `shell/`, `assets/`, `chain/`, `studios/`, `workflows/`, `preview/`  
- **No** Python packaging target; **no** installer target; **no** Rust  

---

## 15. Redesign program (suggested phases)

### Phase R0 — Truth freeze (1–2 days)
- RuntimeManifest design; document live paths  
- Fix README LTX status + ARCHITECTURE line counts  
- Re-verify Hunyuan i2v live; close C8  
- Fill Doc 28 functional checkboxes against real smoke  

### Phase R1 — Contract hygiene (S)
- Ping SM fix + illegal transition logging  
- Protocol v2 draft from command registry extract (even if still one file)  

### Phase R2 — Worker modularization (L, no behavior change)
- Extract queue, comfy http, families packages  
- FamilyPlugin interface mandatory for production families  
- Keep characterization tests green every PR  

### Phase R3 — Shipping spine (XL, ship gate)
- Guided dependency resolver MVP (format + placement + license)  
- First-run wizard assembly  
- Installer spike (Win first): bundle layout + Comfy runtime image  
- Clean-machine Doc 28 run  

### Phase R4 — Product polish still open
- License badges; Wan 2.2 dual-noise i2v; mode-aware history; VRAM Simple caps  

---

## 16. Key file index (absolute)

| Path | Why |
|------|-----|
| `python/worker_service.py` | God worker |
| `python/worker_service_state.py` | Job SM |
| `python/video_family_contracts.py` | Video SSOT |
| `python/video_adapters/{base,wan,ltx,registry}.py` | Adapter layer |
| `python/video_templates/ltx_*.json` | LTX graphs |
| `python/comfy_bootstrap.py` | Path/launch defaults |
| `python/runtime_paths.py` | Drift source |
| `python/model_dependency_resolver.py` | Model deps |
| `python/node_dependency_resolver.py` | Node deps |
| `python/memory_optimization.py` | Image mem |
| `docs/JOB_LIFECYCLE_CONTRACT.md` | SM contract |
| `docs/SPELLVISION_WORKER_PROTOCOL.md` | Stale wire doc |
| `docs/design/21_worker_refactor_plan.md` | Split plan |
| `docs/design/25–28*` + `SpellVision_v1.0_Roadmap.md` | Ship arcs |
| `brain/Planning/Current State Ledger.md` | Status |
| `brain/Specification/Contradiction Ledger.md` | C1–C12 |
| `ARCHITECTURE.md` / `README.md` | Stale maps |
| `CMakeLists.txt` | UI-only target |
| `scripts/dev/start_comfy.ps1` / `run_ui.ps1` | Live Comfy root |
| `tests/test_worker_ping.py` | SM bug pin |

---

## 17. One-line redesign thesis

**SpellVision’s worker already implements the right product architecture (intent → owned Comfy graphs → local execution); the redesign is not a new engine but a modularization + runtime packaging + truth-surface cleanup so that architecture can leave one developer’s machine and become a shippable multi-family desktop studio.**
