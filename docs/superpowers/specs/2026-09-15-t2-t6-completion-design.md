# T2–T6 completion — design

**Date:** 2026-09-15. **Owner directive (`/goal`, 2026-09-14):** complete T2–T6 for 1.0.0; T1 moves to 1.1.0. Owner is not present for questions, so every fork below is a **ruling** with its reason, in the pattern of waves 2 and 3. The rulings are the approval surface: change one and the plan changes.

Research this design rests on is in `docs/superpowers/specs/2026-09-15-t2-t6-research/` (four code inventories, three web reports, all dated). Facts below marked **[V]** were verified on this box on 2026-09-15; the rest are cited from those reports.

## 0. Scope and rulings that cut across everything

| # | Ruling | Reason |
|---|---|---|
| R0.1 | This is **1.0.0** work. `CMakeLists.txt` stays 1.0.0. `CHANGELOG.md` gains no 1.0 line per feature (Doc 56: patch/minor rule applies after 1.0 ships). | Doc 54 §1 declares T2–T6 as 1.0 requirements. |
| R0.2 | **T1 → 1.1.0.** Doc 54 §1 T1 row and Doc 55 row are rewritten to "1.1.0"; `CHANGELOG.md [1.1.0]` gains "In-app trainer (T1)". Train stays in `kV1HiddenModes`. Existing Train page is untouched. | Owner directive. |
| R0.3 | One wave per T, in this order: **W1 Model Intelligence (T3 backend + T5 data) → W2 T5 defaults on pages → W3 T4 → W4 T2 → W5 T3 Models page UI → W6 T6.** Each wave is its own plan file, executed with subagent-driven development, reviewed by planted defects, committed on `main` behind green ctest + pytest + sweeps. | T5 cannot apply per-model defaults until a per-model store exists; T3's UI is the largest net-new surface and can wait for its backend; T6 is last because it is the only wave that needs the second box online. Matches Doc 54 §4 except T3 backend is pulled forward. |
| R0.4 | **Source green ≠ done.** Each wave ends with a live, pictured proof on this box written into `docs/design/55_t7_ship_walkthrough.html` under the T's section, with the queue id and dest path. A wave whose live proof cannot be taken (e.g. SpellNode offline) ships its code and records the gate as **PENDING**, never green. | Doc 59 lesson; owner rule. |
| R0.5 | New Python modules are small and single-purpose (Doc 50 rule); no additions to `worker_service.py` beyond registration lines. New worker commands trip three ratchets (wire-type registry, audience, protocol-doc counts) — each wave budgets for that. | Memory `v1-ui-mustfix-pass-2026-09-01`. |
| R0.6 | **Graphify:** the post-commit hook `.githooks/post-commit` (added 2026-09-15) runs `graphify update .` detached after every commit. A semantic (`--update` with docs) pass runs once at the end of W6. | Owner: "keep it updated". |

Doc 54 §1 T6 row and Doc 59 "T2/T6" paragraph are updated by W6 and W4 respectively; `ARCHITECTURE.md` module tables are updated by every wave that adds a module (`tests/test_governing_docs.py` enforces it).

---

## 1. W1 — Model Intelligence (T3 backend, T5 data)

### 1.1 Problem
Nothing in the tree identifies a local model file on the site that hosts it. There is no by-hash lookup, no HuggingFace metadata fetch, no per-model store; `ModelMetadata::previewUrl` is parsed and dropped (`assets/ModelSidecar.cpp:90`); the Models page guesses type/family from path substrings instead of the worker classifier; downloads from the Models page land in the asset cache with no post-download step.

### 1.2 Sources of truth (verified)
- **CivitAI** `GET /api/v1/model-versions/by-hash/{sha256|AutoV2}` is **public** (no key) and returns version + `model{name,type}` + `files[].hashes` + `images[].meta` + `trainedWords` + `baseModel` + description HTML. Bulk `POST by-hash` ≤100. There is **no structured recommended-settings field**; the only structured signal is `images[].meta` (A1111 infotext: `steps, sampler, cfgScale, Size, clipSkip`, no `scheduler` key). **Downloads always need a token**; reads do not. `civitai.red` is Civitai's official NSFW front door on the same API; base URL stays `civitai.com`, host is a setting, never hardcoded to `.red`.
- **HuggingFace** `GET /api/models/{repo}?blobs=true` gives `cardData` (frontmatter) and `siblings[].lfs.sha256`. **No by-hash lookup exists**; identification is via a local `sha256 → (repo, path)` index built from repos we already know (family manifests, download history).
- **Family seed table** (official cards, in `t3-t5-metadata-research.md` §5) is the floor when no site data exists.

### 1.3 Design
New package `python/model_intelligence/` (each file < 300 lines):

| Module | Purpose |
|---|---|
| `hashing.py` | Streaming sha256 + AutoV2 (first 10 hex). Cache keyed `(path, size, mtime)` in `runtime/state/model_hash_index.json`. Never hashes a file on a BitLocker-locked / unreadable root (reuse `ModelsLibraryPaths::scannableModelsRoots` semantics: a Python twin `readable_models_roots`). |
| `civitai_lookup.py` | by-hash (single + bulk), `/model-versions/{id}`, `/models/{id}`. Bearer from `credential_store` when present. `browsing_level` from settings (default SFW `1|2`). 429 → jittered backoff, max 3. Raw JSON cached at `<models root>/.spellvision/raw/civitai-<version_id>.json`. |
| `hf_lookup.py` | `/api/models/{repo}?blobs=true`, README fetch, sha256 index maintenance. Token always sent when stored. |
| `recommended.py` | Builds the `recommended` block: mode over `images[].meta` (needs n≥3, records n), diffusers-snippet regex from README, description-prose regex, then `family_seed_table`. Each field carries `{value, provenance, confidence, n}`. Sampler strings are normalised to ComfyUI names via the existing `FAMILY_SAMPLER_ALLOWLISTS` aliases; A1111 "Karras" suffix splits into `scheduler`. |
| `family_seed_table.py` | The verified table as data (steps/cfg/guidance/shift/sampler/scheduler/width/height/frames/fps per family and variant). `family_operating_points.py` keeps owning the *runtime* OP tables; this file is the *metadata floor* and W2 reconciles the two (see §2). |
| `sidecar.py` | Schema `spellvision.model-sidecar/1` at `<stem>.spellvision.json` beside the weight (see research §6 for the full shape). Atomic write. A field with `user_override: true` is never rewritten by a refresh. `_unknown_fields` preserved. |
| `previews.py` | Downloads up to 6 preview images to `<models root>/.spellvision/previews/<sha256>/<i>.jpg`; writes the cover as `<stem>.preview.jpg` **only if no `<stem>.{png,jpg,jpeg,webp}` exists** (so hand-placed pictures win). `set_user_picture(path, image)` copies the user's image to `<stem>.preview.jpg` and marks `images[cover].user_override=true`. |
| `refresh.py` | `refresh_models(paths|all, force=False)`: readable roots → hash → lookup (CivitAI first, HF index second) → recommended → sidecar → previews. Runs as a **queue-visible background job** (reuses the download lane's progress plumbing) so the UI shows "Fetching metadata 37/759". |

Worker commands (all in a new `python/model_intelligence_commands.py`, registered in `worker_tcp.py`): `model_intel_refresh`, `model_intel_get` (one path → sidecar dict + resolved `recommended`), `model_intel_set_user` (name / picture / notes), `model_recommended_settings` (path + family + mode → the merged block W2 consumes). `classify_models` output gains `kind` = `ModelClassification.model_type` normalised to the tab vocabulary below.

**Post-download hook (ruling R1.1):** a weight downloaded from the Models page or accepted in `WorkflowDownloadDialog` is moved from the asset cache into `<models root>/<kind subdir>/` (the same `destSubdirForWeight` mapping, moved to Python `model_intelligence/placement.py`), then `refresh_models([path])` runs. Workflow-declared model plans already write into Comfy's folders; they call the same refresh. *Reason:* a model the Models page cannot see is not "downloaded" from the user's point of view.

**Kind vocabulary (ruling R1.2):** `checkpoint, diffusion_model, lora, vae, text_encoder, clip_vision, embedding, upscaler, controlnet, other`. This is the classifier's `_L1_TYPE_CATEGORY` [V] plus `other`; the Models page tabs (W5) are exactly these.

### 1.4 Settings and keys
- `credential_store` keys unchanged (`civitai_api_key`, `hf_token`). Refresh works without keys; only mature previews and downloads need one. A 401 on download raises the existing key dialog once, never loops.
- New Prefs: **Civitai host** (`civitai.com` default), **Show mature previews** (off; when on and no key, the toggle explains why nothing changes).

### 1.5 Tests
- Unit: hashing cache invalidation; CivitAI response fixtures (recorded 2026-09-15 for DreamShaper XL and Pony V6, SFW) → sidecar; `recommended` precedence with planted conflicts; `user_override` survives refresh; unreadable root never hashed; preview cover never clobbers a hand-placed image.
- Live (marked `smoke`): one real by-hash lookup against `civitai.com` for a model on this box, asserting `model.name` non-empty.
- Ratchets: new module reachable (`every-module-is-reachable`), commands in wire-type registry + audience + protocol doc.

### 1.6 Live proof
`model_intel_refresh` over the D:/F: libraries; walkthrough shows the count resolved / unresolved / no-site and one sidecar opened.

---

## 2. W2 — T5: the model's known settings are the default everywhere

### 2.1 Problem
Defaults today are per-family (`family_operating_points.py`), duplicated by a hardcoded C++ block (`applyOptimalVideoSamplingDefaults`, `_video.cpp:219-279`) and a krea2 filename hack (`_units.h:171`). The schema has no size/aspect, frames or fps. Per-model data has nowhere to land.

### 2.2 Design
- **Schema:** `family_operating_points.py` operating points gain optional `width, height, aspect, frames, fps, clip_skip, guidance` (image families gain `shift` where the card defines it). The C++ `applyOptimalVideoSamplingDefaults` values are moved into the table; the function becomes a thin "apply the resolved point" call. The krea2 filename hack is deleted; krea2 Raw/Turbo variants come from the sidecar's `recommended` (CivitAI/HF name) with the filename substring as the last fallback inside `recommended.py`.
- **Resolver (Python, single source):** `model_recommended_settings(path, family, mode)` = family OP (with variant) **overlaid by** the sidecar `recommended` block **overlaid by** `user` overrides. Returns every field with provenance. Hardware caps (VRAM/host RAM) snap **with a warning field**, never silently (Doc 54 T5).
- **C++:** on every checkpoint change on T2I/I2I/T2V/I2V (and the studios' checkpoint pickers, which already forward to the same `applyOperatingPoint` path) the page requests `model_recommended_settings` async (cached per path in `MainWindow` beside the family cache) and applies it through the existing `applyOperatingPoint`. **Ruling R2.1: Simple applies always; Advanced applies on model change too and shows the values pre-selected**, with a one-line provenance caption under the Sampling card ("Defaults from CivitAI examples · n=12" / "Family default"). Advanced users then edit in place. The Speed chip row stays for families with >1 variant.
- **Canvas:** `width/height` from the resolved point becomes the canvas default (Simple) or pre-filled value (Advanced), snapped to the family multiple. Portrait/Landscape orientation in Simple swaps the pair.
- **Preset guard:** the existing first-run honesty rule (presets must not invent a model) holds; the resolver never names a model, only settings.

### 2.3 Tests
- pytest: resolver precedence table (family < sidecar < user), warning on cap, every family in the registry has a complete point (steps/cfg/sampler/scheduler/width/height; frames/fps for video) — ratchet `family-op-is-complete`.
- C++ (`tests/cpp/test_model_defaults_apply.cpp`): a fake worker returns a point; selecting a checkpoint in Simple sets the sampling widgets and canvas; in Advanced the widgets show the same values and the caption names the provenance; a planted "apply only in Simple" defect fails the Advanced case.
- The hardcoded C++ block is gone: sweep rule `no-sampling-literals-in-cpp` (values live in Python data).

### 2.4 Live proof
T2I krea2 Raw → Turbo swap pictured in Simple and Advanced with the caption; one video family (LTX) pictured with frames/fps/size pre-filled.

---

## 3. W3 — T4: every optimization timed against its unoptimized twin

### 3.1 Problem
Seconds per job already persist twice (`runtime/state/job_archive.json`, `runtime/state/history/video_history.jsonl`) but **nothing records which optimization produced them** — the only published A/B is distinguishable by a hand-typed filename, and a third arm at 159 s (cold) shows the published 3 % delta is smaller than load variance. The worker cannot restart Comfy into a different argv; the worker-managed launch drops `PYTHONUTF8` and cannot pass `--reserve-vram`.

### 3.2 Levers (from the 2026-09-15 landscape research)
Reachable on core 0.34.0 + torch 2.10/cu128 [V argv: `--use-sage-attention` is the only opt flag live today]:

| Lever | Enable | Note |
|---|---|---|
| SDPA (baseline) | `--use-pytorch-cross-attention` pinned explicitly | |
| SageAttention **2.2** | install woct0rdho abi3 wheel (torch ≥2.10, cu12.x, sm120) into the Comfy venv; `--use-sage-attention` | shipped `sageattention 1.0.6` is SA1 Triton-only [V]; this is the first real measurement |
| `--fast fp16_accumulation` | flag | autotune / cublas_ops excluded (first-run cost, extra package) |
| `--fast fp8_matrix_mult` | flag | fp8 e4m3 checkpoints only (Flux fp8, Wan fp8) |
| Comfy-Kitchen INT8 attention | `--use-ck-attention` | kitchen 0.2.31 present [V]; likely Triton path on cu128 |
| EasyCache | core node, defaults | Wan / Flux / LTX / Hunyuan-t2v / Lumina2; quality-gated |
| VAE tiling | request flag (exists) | "no number" comment gets its number |
| fp16 cast (diffusers) | make `cast_fp32_to_fp16` a request field | SDXL only |
| PrunaVAED | LTX-2.3 decoder file | decode-side |
| lightx2v 4-step | Wan 2.2 LoRA | quality gate: frame-0 MAE + motion, not just seconds |
| DynamicVRAM off | `--disable-dynamic-vram` | one lane, to show what aimdo buys |
| torch.compile | `TorchCompileModel`, only in a `--disable-dynamic-vram` lane | open aimdo × dynamo limitation |

Cut with reasons recorded in the results doc: flash-attn (no verified wheel, ≤ SDPA), SA3 (needs torch 2.12/cu131), NVFP4 (needs cu130, slower on cu128), TeaCache/MagCache (dead since 2026-01-05), GGUF, radial/sparse (wrapper-only).

### 3.3 Design
- **Provenance block (ruling R3.1):** `worker_metadata.build_metadata_payload` writes `optimizations: {attention_backend, comfy_argv, comfy_version, torch, cuda, sageattention, comfy_kitchen, dynamic_vram, fast_flags, vae_tiling, fp16_cast, cache_node, wrapper_attention_mode, warm}` beside `generation_time_sec`. `comfy_argv` and versions come from `/system_stats` (`system.argv`, `pytorch_version`, `comfy_package_versions` [V]); `warm` = "same checkpoint was resident at submit" from the runtime cache truth. Lands in both stores automatically.
- **Restart with argv:** `restart_comfy_runtime` accepts `attention` (`sdpa|sage|ck`), `fast` (list), `dynamic_vram` (bool), `vram_headroom`; threads through `bootstrap_comfy_runtime` → `build_launch_command(extra_args=…)`; `ComfyRuntimeManager.start` passes `env=launch_env()` (fixes the dropped `PYTHONUTF8`). The Qt first-launch SDPA race is closed by making the sage probe synchronous *on the launch thread* (not the GUI thread), so the arm is always what the profile says.
- **Harness `scripts/dev/measure_optimizations.py`:** matrix rows = shipped families × levers above; per cell: restart Comfy into the arm → one warm run (discarded, recorded as `warm=false`) → **two** timed runs with different seeds → quality guard (frame-0 MAE for i2v, black-frame detector for attention overflow, MoE artefact check on Wan 2.2) → row appended to `runtime/state/optimization_results.jsonl` `{family, lever, arm, seconds[], mean, baseline_mean, delta_pct, quality, provenance, dest}`. Runs **through the worker** (the product path), so every row also exists as a job with a sidecar. Same job = same prompt/size/steps/cfg/frames; only seed and the lever change. VRAM is reported only for cells run at a fixed `--reserve-vram`.
- **Runtime page "Optimizations" panel:** one row per lever: *installed* (venv probe) / *active* (live argv) / *measured* (best delta from the jsonl, or "not timed") / *verdict* used | skipped | broke. Reads the jsonl through a new `optimization_results` worker command.
- **Doc:** `docs/design/60_t4_optimization_results.md` generated from the jsonl by the harness (`--write-doc`), with the cut list and the measurement rules. Doc 55 T4 row links to it.

### 3.4 Tests
- pytest: provenance block present and complete on a fake render; restart command builds the expected argv for each arm; `launch_env` reaches `Popen`; harness row schema; the results→doc generator is deterministic.
- Planted: a sidecar without `optimizations` fails the ratchet `every-render-names-its-argv`.

### 3.5 Live proof
The harness runs the full matrix on this box (long: hours) as a background job; the walkthrough shows the generated doc and the Runtime panel. Rows that could not run (missing checkpoint, OOM) are recorded as such.

---

## 4. W4 — T2: drop a workflow anywhere, it opens on the right page, populated

### 4.1 Problem
Only cockpit sub-widgets accept a `.json`; the drop applies to whatever page it landed on; the importer's `inferred_task_command` / `capability_report` are computed and discarded by the drop draft; the draft carries paths only (no prompt, model, sampler, size, LoRA, input image); `safe_to_submit` is hardcoded false; three C++ classifiers diverge.

### 4.2 Design
- **Window-level drop (ruling R4.1):** `MainWindow::setAcceptDrops(true)` plus an application-level event filter so the title bar, rail, drawer, Flows, Home, History, Settings and the studios all accept `.json` / `.api.json` / `.zip` (the importer already handles zip). A glass overlay "Drop to load workflow" appears on drag-enter. Prompt editors keep `setAcceptDrops(false)`; the filter routes their drops to the window handler instead of letting them swallow the file. Image drops keep today's per-page behaviour.
- **One classifier (ruling R4.2):** `WorkflowLaunchController::resolveDraftModeId` becomes the only C++ mode resolver; `HomePage::inferModeFromWorkflowProfile` and `WorkflowLibraryPage::normalizedModeId` call it. Input is the worker's `inferred_task_command` + `inferred_media_type` + `supported_modes` (from `workflow_scanner.py`, decision-by-output), never a path substring. Unknown → Flows page with the record selected and the reason shown; never a silent `t2i`.
- **Rich draft (ruling R4.3):** `WorkflowLibraryPage::buildReusableDraft` moves to `qt_ui/workflows/WorkflowDraftBuilder.{h,cpp}` and is used by both Flows Apply and the drop path. The drop flow becomes: `import_workflow` → if missing nodes/models → `WorkflowDownloadDialog` (existing) → `compile_workflow_prompt` → `check_workflow_launch_readiness` → `WorkflowDraftBuilder` → `ensureGenerationPageBuilt(modeId)` → `applyWorkflowDraft` → `switchToMode(modeId)`. `safe_to_submit` = the readiness verdict. Generate then runs the imported graph through the existing `run_comfy_workflow` route with cockpit overrides (sampler/scheduler/FPS/LoRA/frames already honoured).
- **Populated means:** prompt, negative, checkpoint (via `trySetSelectedModelByCandidate`), LoRA stack, sampler/scheduler/steps/cfg/seed, width/height, frames/fps, input image (I2I/I2V), and the "Loaded from workflow: <name>" chip with a **Detach** action that returns the page to native graphs.
- **Owner drop test:** the two owner workflows already imported (Compact T2I v10, Krea2 Pro Grade v17) plus the Character Forge sheet are the fixtures; the walkthrough pictures the dialog and the landed page for each.

### 4.3 Tests
- C++ `tests/cpp/test_workflow_drop_routing.cpp`: a synthetic `QDropEvent` on the title bar with a t2v fixture switches to T2V and fills frames/fps; an i2i fixture fills the reference chip; an audio fixture lands on Flows with a message; a planted "always t2i" classifier fails.
- pytest: classification fixtures for the three owner workflows; drop flow contract (import → compile → readiness) over the live worker.
- Sweep: `one-workflow-mode-resolver` (no other function derives a mode from a workflow).

### 4.4 Live proof
Pictured: drop on the title bar, dialog, T2I populated, Generate dest.

---

## 5. W5 — T3: the Models page as a library

### 5.1 Design
- **Tabs (ruling R5.1):** a `QTabBar` above the grid with the kind vocabulary from R1.2 (Checkpoints · Diffusion models · LoRAs · VAE · Text encoders · Vision · Embeddings · Upscalers · ControlNet · Other) plus **All**. Counts in the tab labels. Family combo and search stay; the Type combo is deleted (the tab is the type). Kind and family come from the worker classifier (`classify_models` with `kind`), not path guesses — `scanModelInventory` keeps the filesystem walk and asks the worker to classify the batch.
- **Card:** cover from `<stem>.preview.jpg` / existing sidecar image through the unchanged thumbnail cache; display name from the sidecar; site badge (CivitAI / HF / local); NSFW blur when the preview's level exceeds the setting.
- **Inspector:** gallery strip (≤6, from `previews/`), description (HTML-stripped, expandable), trigger words with copy, license line, **Recommended settings** panel with provenance captions and "Apply to <mode>", **Use my picture…** (file dialog → `model_intel_set_user`), **Refresh metadata** (force), **Open on site**.
- **Drop anywhere on the page:** unchanged (weights copy in; URLs download) but both now end in the W1 post-download hook, so the card appears with its picture and settings.
- **Not in scope (1.1.0, Doc 58):** recipes, favorites sync, CivitAI/HF *browse* inside the app, LoRA Manager parity.

### 5.2 Tests
- C++ `tests/cpp/test_models_page_tabs.cpp`: a fixture inventory with every kind shows the right counts per tab; switching tabs filters; the user picture replaces the cover and survives a refresh; recommended panel shows provenance.
- pytest: `classify_models` returns `kind` for every fixture path; inventory batch classification matches the routing family (the display==routing invariant already in memory).

### 5.3 Live proof
Models page pictured on this box: tabs with counts, one CivitAI-identified checkpoint with site pictures, one user-replaced picture.

---

## 6. W6 — T6: queue whole jobs on the second box, honestly

### 6.1 Research verdict (2026-09-15, `t6-research.md`)
ComfyUI-Distributed is server-side and API-callable, but (a) every graph must carry its Collector/Seed nodes, (b) with no reachable worker it **silently falls back to the master** (issue #48 open) — the opposite of fail-closed, (c) no model-availability check, (d) pack must live on both boxes. NetDist is unmaintained since 2024-02 and substitutes a black image on failure. Every mature multi-backend product (SwarmUI backends, Comfy Deploy) is a client-side scheduler over plain `/prompt`. **Ruling R6.1: SpellVision-native routing.** The Distributed "Enable" button, its zipball install and the share-folder UI are removed; Doc 54 T6 row is rewritten; Distributed stays a documented future option for seed/tile fan-out.

### 6.2 Design
- **Endpoint registry (data, not literals):** QSettings `runtime/endpoints` = JSON list `{id, label, base_url, enabled, families_allowed[]}`; the local master is always entry 0. `RuntimeProfile` exposes it; the Python worker receives it per request as `comfy_endpoints` (so the worker holds no second copy of the truth).
- **Runtime page:** endpoint list (label, URL, status pill, Comfy version, GPU name/VRAM from `/system_stats`, "models visible" count from `/models/checkpoints`), Add / Edit / Remove / Enable, "Allow queuing to remote workers" consent (replaces the dual-PC consent), and a per-endpoint **Families** checklist that is *empty until a gate render passes on that endpoint* (the app writes `families_allowed` from a successful gate, the user may only untick). Honesty line stays: whole jobs only, VRAM does not pool.
- **Cockpit:** Advanced action row gains **Run on** (Auto · Local · <endpoint>); Simple is Auto. **Ruling R6.2: Auto = first idle, enabled endpoint in registry order whose capability check passes; Local is entry 0, so a free master always wins.** A remote pick that fails the check refuses *before enqueue* with the reason (offline / missing model X / family not gated).
- **Capability check (Python `endpoint_capability.py`):** health `GET /system_stats` (never touches model dirs, so a hung CIFS mount on the node cannot hang the probe), then every model the compiled prompt references must appear in `GET /models/{folder}` on that endpoint [V route], then the node-contract diff (existing) against that endpoint's `/object_info` (already cached per `api_url`).
- **Worker lanes:** `QueueItem.endpoint`; `QueueManager` keeps `active_by_endpoint: dict`, starts one job per endpoint; `get_comfy_runtime_manager` becomes a dict keyed by endpoint, and `ensure_comfy_runtime` for a non-local endpoint is the health probe only (it never starts a process); `request_comfy_free_memory` / `wait_until_comfy_queue_idle` callers pass `api_url`; image/video runtime caches and `transition` keys are per endpoint. Outputs come back over `/view` into the local history dir (R18 already enforces HTTP-not-disk for remote).
- **Models on the node:** out of band. `docs/design/61_spellnode_setup.md` records the fstab recipe (`soft,echo_interval=10,noserverino,_netdev,nofail,x-systemd.automount,x-systemd.mount-timeout=15`) and the rsync alternative; the app never mounts anything (share-folder consent UI is deleted).
- **Gate:** SDXL and Krea2 first on the 3090 Ti (fp8 stored, bf16 compute; ~5× slower than the 5090 per research); video families are added only after their own gate render on that box.

### 6.3 Tests
- pytest with a fake Comfy HTTP server: capability check refuses offline / missing model / ungated family; two lanes run concurrently on two fake endpoints; `/free` goes to the right endpoint; a remote job never calls the local process manager.
- C++ `tests/cpp/test_endpoint_registry.cpp`: registry round-trip; Auto picks local when free; an unreachable remote is refused with the reason in the pill.
- Sweep: `no-hardcoded-endpoint-literal` (no `192.168.` / `:8188` string in `qt_ui/` outside `RuntimeProfile` defaults).

### 6.4 Live proof
If SpellNode is reachable: SDXL job queued from the cockpit with Run on = SpellNode, dest fetched over `/view`, pictured, and `families_allowed` written. If not: the code ships, fake-server tests are green, the walkthrough row says **PENDING — node offline on <date>**.

---

## 7. What is deliberately not in this design
- T1 in-app trainer (1.1.0). Prompt blocks, workflow houses, verbs (1.1.0, Doc 58). LoRA Manager parity, CivitAI/HF browse (1.2.0). Installer/first-run (separate). Same-box CFG split, ComfyUI-Mesh, VRAM pooling (never / 1.2.0+).

## 8. Success criteria (measured into Doc 55 by each wave)
1. W1: every readable weight on D:/F: has a sidecar or a recorded "no site match"; refresh never hashes a locked root.
2. W2: on every generation page, selecting any checkpoint in Simple lands the resolved point (pictured for one image and one video family); no sampling literal remains in C++.
3. W3: `optimization_results.jsonl` has a baseline and at least one lever row for every shipped family the box can render; every sidecar carries `optimizations`; Runtime panel shows them.
4. W4: the three owner workflows dropped on the title bar land on the right page populated; Generate from that state produces a dest.
5. W5: Models page tabs with counts, site pictures on identified models, a user-replaced picture that survives refresh.
6. W6: capability-gated dispatch to a second endpoint over fake servers; live SpellNode render pictured or recorded PENDING.
