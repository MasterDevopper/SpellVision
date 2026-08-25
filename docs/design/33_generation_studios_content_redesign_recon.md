# 33 — Generation Cockpits + Studios + Content: Redesign Recon

**Status:** Analysis only (2026-07-25). **No code changes.**  
**Authority:** live `qt_ui/*` + docs 29/30/31/32 + skills `spellvision` / `spellvision-qt-studio-surfaces`.  
**Product grade context:** owner **A-**; showcase **S** still needs eyes (Doc 30 matrix). Arc 2 UI polish ~70%.

---

## 0. System map (one screen)

| Surface class | modeId(s) | Primary class | Built when | Generate path |
|---|---|---|---|---|
| Generation cockpits | `t2i` `i2i` `t2v` `i2v` | `ImageGenerationPage` (Mode enum) | **Lazy** `MainWindow::ensureGenerationPageBuilt` | `generateRequested` → `submitGenerationRequest` |
| Orphan video stub | *(none on rail)* | `VideoGenerationPage` | **Not wired** | emits `video_generation` — dead |
| Character Studio | `character` | `studios::CharacterStudioPage` | Eager `buildPages` | `generateRequested(mode,payload,enq)` → `submitStudioGenerationRequest` |
| Comic Studio | `comic` | `studios::ComicStudioPage` | Eager | same |
| Concept Lab | `concept` | `studios::ConceptReferencePage` | Eager | same |
| Chain Studio | `chain` | `chain::ChainStudioPage` | Eager; **v1-hidden** | `MainWindow::submitChainGenerationRequest` |
| Flows | `workflows` | `WorkflowLibraryPage` | Eager | launch/draft → cockpit |
| History | `history` | `T2VHistoryPage` | Eager | LTX requeue side path |
| Models | `models` | `ModelManagerPage` | Eager | `useModelRequested` handoff |
| Dataset stub | *(none)* | `DatasetGenerationPage` | **Not on rail** | `generate_dataset` orphan |
| Inspire stub | `inspiration` | `ModePage` | Eager; **v1-hidden** | none |
| Queue chrome | shell | `QueueManager` + overlay + `QueueTableModel` | Always | poll → previews |

**Rail (live):** Home · T2I · I2I · T2V · I2V · Char · Concept · Comic · Flows · History · Models · Prefs  
**Hidden (`kV1HiddenModes`):** `chain`, `inspiration` — override `SPELLVISION_SHOW_ALL_MODES=1`  
Source: `ShellNavigationController::{railButtonSpecs,isModeHidden,pageContextForMode}`

---

## 1. Generation request lifecycle (UI → worker)

```
[User Generate / Queue / Studio / Chain]
        │
        ▼
ImageGenerationPage::buildRequestPayload()
  → GenerationRequestDraft
  → GenerationRequestBuilder::build(draft)   // qt_ui/generation/GenerationRequestBuilder.*
        │  (studios build partial QJsonObject themselves)
        ▼
MainWindow::submitGenerationRequest(page, modeId, payload, enqueueOnly)
  OR submitStudioGenerationRequest(studioMode, modeId, payload, enqueueOnly)
  OR submitChainGenerationRequest(modeId, payload, queueItemId)
        │
        ├─ workerTaskCommandForMode(modeId)  → "t2i"|"i2i"|"t2v"|"i2v" only
        ├─ WorkerSubmissionPolicy checks (model / native stack / input_image)
        ├─ telemetry busy latches (svTelemetry*)
        └─ buildWorkerGenerationRequest(modeId, payload)
              command:        "enqueue"
              task_command:   mode command
              task_type:      same
              + prompt, negative, model*, loras, sampler, dims, frames…
              + output path stamp under project/output
              video unbound → backend_kind "native_video", runtime "diffusers_video" (legacy label; actual path is native_comfy_template)
        │
        ▼
sendWorkerRequest → python/worker_client.py → TCP worker_service :8765
        │
        ▼
applyWorkerQueueResponse → QueueManager upsert
pollWorkerQueueStatus (≈1800ms)
        ├─ syncGenerationPreviewsFromQueue → page->setPreviewImage
        └─ syncStudioPreviewsFromQueue → studio setPreview* / setPanelResult
```

### Worker-facing command names (visible from UI)

| UI origin | Request `command` | `task_command` / mode |
|---|---|---|
| Generate/Queue cockpits | `enqueue` | `t2i` `i2i` `t2v` `i2v` |
| Studio handoff | `enqueue` (via same builder) | effective mode (T2I→I2I if `input_image`) |
| Chain | `enqueue` | stage mode |
| Model classify (catalog) | `classify_models` | n/a |
| Video components A2 | `resolve_component_stack` | n/a |
| OP table cache | `video_family_contracts` | n/a |
| Orphan `VideoGenerationPage` | `video_generation` | **not** in workerTaskCommand map |
| Orphan `DatasetGenerationPage` | `generate_dataset` | not wired |

**Key symbols:**  
`MainWindow::{submitGenerationRequest,submitStudioGenerationRequest,submitChainGenerationRequest,buildWorkerGenerationRequest,workerTaskCommandForMode,ensureGenerationPageBuilt,connectGenerationPage,syncStudioPreviewsFromQueue,syncGenerationPreviewsFromQueue}`  
`ImageGenerationPage::{buildRequestPayload,triggerGenerate,generateRequested,queueRequested}`  
`spellvision::generation::GenerationRequestBuilder::build`

### Studio merge fallback (critical product bug surface)

`MainWindow::submitStudioGenerationRequest` (≈2766–2822):

1. `ensureGenerationPageBuilt(genMode)`
2. Stash `pendingStudioMode_`, `_comic_panel_index`
3. **`takeIfMissing`** from cockpit `page->buildRequestPayload()`:  
   `model`, `model_display`, `model_family`, `model_modality`, `sampler`, `scheduler`, `loras`, `model_stack`
4. If `t2i` + `input_image` → force `i2i`
5. `submitGenerationRequest(page, effectiveMode, payload, …)`

**Implication:** Character + Comic **omit model on payload** → silently inherit whatever T2I last had (or none). Concept Lab **does** set model/LoRA on-page (correct pattern). Owner rule: *merge is fallback, not UX.*

### Preview return

- Cockpits: newest completed queue item → `setPreviewImage` / video surface via `MediaPreviewController`
- Studios: `pendingStudioMode_` + optional `preferPrefix = "concept_ref_"` then fallback any newest completed
- Comic: `setPanelResult(pendingComicPanelIndex_, path)`
- **Race:** single pending slot — concurrent multi-panel / multi-studio jobs can mis-route previews

---

## 2. GENERATION COCKPITS

### 2.1 ImageGenerationPage — T2I / I2I / T2V / I2V

**Files:** `qt_ui/ImageGenerationPage.{h,cpp}` (~300KB cpp), `generation/CockpitInspector.*`, `generation/GenerationRequestBuilder.*`, `generation/VideoGenerationPolicy.*`, `preview/{Media,Image}PreviewController.*`, `assets/{LoraStackController,CatalogPickerDialog,ModelThumbnailCache}.*`

#### Purpose / JTBD
Primary instrument for one-shot generation. User states prompt + picks checkpoint/stack; SpellVision builds worker payload / Comfy graph. Four mode instances share one class (`Mode::{TextToImage,ImageToImage,TextToVideo,ImageToVideo}`).

#### Wiring
| modeId | Mode enum | Rail shortcut |
|---|---|---|
| `t2i` | TextToImage | Ctrl+3 |
| `i2i` | ImageToImage | Ctrl+4 |
| `t2v` | TextToVideo | Ctrl+5 |
| `i2v` | ImageToVideo | Ctrl+6 |

- Lazy construct: `MainWindow::ensureGenerationPageBuilt` → `new ImageGenerationPage(mode)` → `connectGenerationPage`  
- Signals: `generateRequested(QJsonObject)`, `queueRequested`, `openModelsRequested`, `openWorkflowsRequested`, `prepForI2IRequested`  
- Disclosure: `MainWindow::disclosureModeChanged` → `updateDisclosure(bool)`  
- Handoffs in: Home gallery, Models send-to, Flows draft, Command palette

#### Produces
`buildRequestPayload()` → keys include:  
`mode, prompt, negative_prompt, preset, model, model_display, model_family, model_modality, model_role, loras[], sampler/scheduler, steps, cfg, seed, width, height, batch_count, output_prefix, output_folder, models_root`  
Video: `frames, fps, video_model_stack / model_stack, native_video_stack_kind, video_family, wan split/high/low steps/shifts, operating_point, VAE tiling, LTX name overrides + prompt_api paths`  
I2I/I2V: `input_image, denoise_strength`  
Runtime outputs: `output/<prefix>_<task>_<utc>.{png|mp4}` + `.json` sidecar (MainWindow stamps paths).

#### Layout
```
root QVBox
└── contentSplitter_ (H)
    ├── leftScrollArea_ (Prompt rail)  min 320 max 470
    │     VideoFamily card (video)
    │     PromptCard (prompt + optional I2I dropzone chip)
    │     negative collapse row
    │     action row (Generate #PrimaryActionButton, Queue, …)
    │     session strip (in-memory thumbs)
    ├── centerContainer_  canvas / MediaPreviewController
    └── cockpitInspector_  tabs Model | Sampling | Output | Advanced
          + readiness strip (must be synced from readinessBlockReason)
```
- **Policy:** cockpit should fit viewport; tab bodies scroll internally (`InspectorTabScroll`).  
- **Reality:** left rail is also a `QScrollArea` — dual vertical scroll regions possible.  
- Adaptive: `updateAdaptiveLayout` → `cockpitInspector_->setWidthBudget(280–460)`; `showEvent` + `singleShot(0)` reflow.  
- No inert IMG stub on T2I/T2V (`promptSourceSlot == nullptr` unless `isImageInputMode()`).

#### Simple / Advanced
`updateDisclosure` (hide-not-delete; values still payload):

| Area | Simple | Advanced |
|---|---|---|
| Output | Preset/Quality | Width, Height, Batch, Prefix |
| Sampling | Aspect; video Frames/FPS | Steps, CFG, Seed, Sampler/Scheduler |
| Model | Checkpoint, LoRA, Asset Intelligence | Workflow combo; video Components panel |
| Advanced tab | **Hidden for image modes** | Visible video-only (WAN dual-noise / LTX launch) when Advanced |

Global toggle: title bar + Settings (`MainWindow::advancedMode_`).

#### Model / LoRA picker
**Yes — first class.**  
`showCheckpointPicker` / `showLoraPicker` via `CatalogPickerDialog`; `LoraStackController`; video family Auto/Wan/LTX segmented bar; component combos + A2 `resolve_component_stack`; operating points provider.

#### POSITIVES
- Single class → four modes; lazy build solves ~6s startup
- Real progressive disclosure (in-place hide)
- Asset Intelligence strip + readiness gating
- Media preview: QLabel+QVideoSink (portable), full transport
- Session strip + duplicate-submit lock fingerprint
- Combo sizeHint discipline + stacked video rows (Doc 30 P0 fixes landed)
- Theme via `ThemeManager::imageGenerationStyleSheet()`
- Workflow draft apply without clobbering unrelated fields on model handoff APIs

#### NEGATIVES
1. **God file** — 6k+ lines; hard to redesign without surgical extraction  
2. **Left rail scroll** vs “no page scroll” doctrine — tension  
3. **leftScrollArea maxWidth 470** can fight half-screen with inspector budget  
4. Readiness strip defaults sticky unless `updatePrimaryActionAvailability` writes it  
5. Stale I2I/I2V path blocks forever if not cleared via `setInputImagePath({})`  
6. Video `backend_kind`/`runtime` labels still say diffusers while product is native Comfy  
7. LTX launch options still Advanced power-user clutter  
8. `qWarning` spam on every disclosure toggle  
9. Four nearly-identical pages still ×4 memory once prewarmed  
10. Empty canvas / glass density still owner-gated to S

#### Industry comparison
| Peer | SpellVision vs |
|---|---|
| **ComfyUI desktop** | Far better intent UX; weaker node escape hatch (Flows is the relief valve) |
| **A1111 / Forge** | Similar cockpit density; better progressive disclosure; weaker extension ecosystem surface |
| **Midjourney** | Heavier (parameters visible); stronger local model control; weaker social/prompt culture |
| **Leonardo / Firefly** | More “pro local studio”; less polished marketing empty states |
| **Runway / Kling** | Video family bar + OP selector competitive; timeline/edit suite absent |
| **InvokeAI** | Similar canvas+inspector; SpellVision theme more branded |

#### Defects
| Pri | Defect |
|---|---|
| P0 | Half-screen / restore matrix not owner-closed (Doc 30) |
| P0 | Combo sizeHint regressions if new long-path combos added without `minimumContentsLength`+elide |
| P1 | Dual scroll (left + inspector) can nest-feel |
| P1 | Telemetry/queue chip width thrash if sync paths reintroduce fixed widths |
| P2 | God-file maintainability blocks redesign velocity |
| P2 | Diffusers-named runtime fields confuse debug |
| P3 | Disclosure `qWarning` noise |

---

### 2.2 VideoGenerationPage (ORPHAN STUB)

**Files:** `qt_ui/VideoGenerationPage.{h,cpp}` (~7.8KB)  
**Purpose:** Legacy prototype; **not** on rail; **not** in `modePages_`.  
**Produces:** payload `command: "video_generation"` — **not** `enqueue`/`t2v`.  
**Layout:** simple form + generate button.  
**Simple/Advanced / pickers:** none.  
**Verdict for redesign:** **Delete or quarantine** after confirming CMake-only residue. Real video = `ImageGenerationPage` T2V/I2V.

---

### 2.3 CockpitInspector

**Files:** `qt_ui/generation/CockpitInspector.{h,cpp}`  
**JTBD:** Right column host — tab bar + 4 scroll bodies + readiness footer.  
**API:** `tabContentLayout(Tab)`, `setTabVisible`, `setWidthBudget`, `readinessLabel()`.  
**Layout:** min/max width clamped equal to budget (280–460); content `setMaximumWidth(budget-8)`.  
**POSITIVES:** Correct half-screen primitive; tab minWidth 0.  
**NEGATIVES:** Not auto-synced readiness; no built-in Simple sections; depends entirely on parent reparenting.  
**P0–P1:** If parent forgets budget/reflow → T2V clip returns.

---

### 2.4 generation/* helpers

| File | Role |
|---|---|
| `GenerationRequestBuilder` | Draft → JSON (loras dual keys, video stack, LTX aliases) |
| `GenerationModeState` | Small mode state helper |
| `GenerationResultRouter` | Route result paths |
| `GenerationStatusController` | Busy/error/output from worker msgs |
| `OutputPathHelpers` | Path utilities |
| `VideoGenerationPolicy` | Family resolution, stack mode |
| `VideoReadinessPresenter` | Video readiness copy |

---

### 2.5 preview/*

| Class | Role |
|---|---|
| `MediaPreviewController` | Video via QMediaPlayer+QVideoSink→QLabel; transport; posters |
| `ImagePreviewController` | Image canvas |
| `PreviewFileSettler` | Wait for file settle before load |

**POSITIVES:** Avoids QVideoWidget native-window black hole.  
**NEGATIVES:** Poster extraction timing; Windows path normalize still fragile on studio side.

---

### 2.6 Queue surface

**Files:** `QueueManager.*`, `QueueTableModel.*`, `QueueFilterProxyModel.*`, `OutputCardModel.*`, MainWindow queue overlay  

**JTBD:** Live job list + Home “Your work” cards + studio/cockpit preview source of truth.

**QueueItem** carries rich video telemetry (family, stack, LTX dual outputs, runtime reuse flags).

**POSITIVES:** Upsert model; filter proxy; overlay drawer (not bottom dock fight).  
**NEGATIVES:**  
- Studio pending is single-flight  
- Home `OutputCardModel` historically empty without sidecars (fixed path noted in skill)  
- Queue overlay vs bottom utility tray cognitive load  

**Defects:** P1 multi-job studio routing; P2 mode-aware history still “load-bearing” unfinished per umbrella skill.

---

## 3. STUDIOS

### 3.1 CharacterStudioPage

**Files:** `qt_ui/studios/CharacterStudioPage.{h,cpp}`, packs via `ConceptReferencePacks.h`  
**Design:** Doc 29, Doc 11d  
**modeId:** `character` · Ctrl+Shift+C

#### Purpose / JTBD
Guided 9-stage character pipeline: Concept → MultiView → BaseMesh → Refine → GameReady → Garments → Compose → Hair → Export. Image stages hit T2I/I2I; mesh stages probe SpellBound/Pixal3D spike.

#### Wiring
- Rail + palette + details dock  
- `generateRequested(modeId,payload,enq)` → `submitStudioGenerationRequest("character",…)`  
- `navigateRequested`, `openModelsRequested`, `openWorkflowsRequested`  
- `acceptConceptReference(path,prompt)` from Concept Lab  
- Persist: `runtime/characters/<name>/project.json` + export/

#### Produces
- Concept/multi-view/garment sheets → PNG under output with prefix `character_<name>_…`  
- Mesh: external scripts if env present; else Warning + attach artifact  
- Export: manifest + license sidecar  

`buildConceptPayload()`: prompt pack SFW body + dims/steps/cfg/seed/`output_prefix` — **no model/loras**.

#### Layout
```
hero strip
mainSplit_
  stageRail_ (list ~200–260 reflow)
  workspace QScrollArea + QStackedWidget stages
action row
```
`reflowForWidth`; stacked fields (QFormLayout removed).

#### Simple / Advanced
`advancedConceptBlock_`, `advancedMeshBlock_` revealed in place.

#### Model / LoRA picker
**NO on-page picker.** Relies on T2I merge fallback. **Product bug per owner 2026-07-25 rule.**

#### POSITIVES
- Honest mesh tool probe (no fake success)  
- Concept packs shared with Concept Lab  
- Stage rail status machine  
- Scroll + reflow pattern  

#### NEGATIVES
- Missing model/LoRA UI (P0 product)  
- Merge can pull wrong/stale cockpit model  
- Stages past multi-view mostly gates/docs  
- No showEvent deferred reflow (only resizeEvent) vs cockpits  
- Thin multi-view prompt path still has hardcoded “clean product sheet…” strings in places  
- Project name UX shallow  

#### Industry
Closer to **Cascadeur/Character Creator wizards** + **Meshy/Tripo** image-to-3D than to Midjourney. Firefly/Leonardo have lighter “character reference” not full mesh pipeline.

#### Defects
| Pri | |
|---|---|
| P0 | No on-page model/LoRA; Generate can ship Model:none or wrong merge |
| P1 | Preview path Windows normalization |
| P1 | Mesh stages depend on external env — empty UX for pure image users |
| P2 | Concurrent generate preview clobber |
| P3 | Stage copy density / hero marketing residue |

---

### 3.2 ComicStudioPage

**Files:** `qt_ui/studios/ComicStudioPage.{h,cpp}`  
**modeId:** `comic` · Ctrl+Shift+M

#### Purpose / JTBD
Script → panel grid → per-panel T2I → composite page export.

#### Wiring
Same studio generate path; tags `_comic_panel_index` stripped in MainWindow; `setPanelResult`.

#### Produces
- Per-panel PNG prefix `comic_<name>_pNN`  
- Export `runtime/comics/<name>/export/page.png` + manifest  
`buildPanelPayload`: prompt+style scaffold, negative hard-coded anti-collage, steps/cfg/seed; **no model**.

#### Layout
```
hero
mainSplit_ left | canvas | right
  left: script/style/layout (QScrollArea#ComicSideScroll)
  center: panel grid hit targets
  right: panel inspector + preview (scroll)
action row
```
Advanced Sampling in left body; stacked fields.

#### Simple / Advanced
Advanced block: sampler, steps, cfg, seed, w/h.

#### Model / LoRA picker
**NO** — same merge bug class as Character.

#### POSITIVES
- Layout presets (2×2, strip, manga 6, splash+3, etc.)  
- Side scrolls fix Advanced-at-short-height  
- One generate-all incomplete panel per click (honest, if slow)  
- `@token@` QSS  

#### NEGATIVES
- No model picker (P0)  
- Generate-all is sequential manual re-click, not true queue-all  
- No character reference image lock into I2I consistency  
- QFormLayout include still present (may be residual)  
- Dialogue/caption not composited into bubbles (text fields only)  
- Style consistency across panels weak without IP-Adapter/ref  

#### Industry
| Peer | |
|---|---|
| Midjourney `--cref` / `--sref` | Stronger identity lock |
| ComicAI / PanelForge tools | Stronger balloon/lettering |
| Runway | Motion comics path absent |
| Leonardo motion | Not multi-panel page composer |

#### Defects
| Pri | |
|---|---|
| P0 | No model/LoRA picker |
| P1 | No batch queue of all panels |
| P1 | Weak cross-panel identity |
| P2 | Lettering/composite incomplete |
| P3 | Canvas hit-target density |

---

### 3.3 ConceptReferencePage + ConceptReferencePacks

**Files:** `ConceptReferencePage.*`, `ConceptReferencePacks.h`  
**Design:** Doc 31  
**modeId:** `concept` · Ctrl+Shift+R

#### Purpose / JTBD
Produce multi-view / mesh-adherent concept plates (light, bg, angle discipline) for Character/TRELLIS-class pipelines.

#### Wiring
- `submitStudioGenerationRequest("concept",…)`  
- Prefix filter `concept_ref_` on preview sync  
- `sendToCharacterStudioRequested` → `acceptConceptReference`  
- Persist `runtime/concept_references/`

#### Produces
Payload with pack scaffolds + **model/model_display/loras** + optional `input_image` from locked hero; T2I or I2I.

#### Layout
Hero · left controls (asset/content/view chips, model row, prompts) · center/right preview · actions  
Both sides scroll; `reflowForWidth`; `showEvent` present.

#### Simple / Advanced
Advanced: seed/steps/cfg line edits.

#### Model / LoRA picker
**YES** — `CatalogPickerDialog` + scan; block generate if empty. **Reference implementation for other studios.**

#### POSITIVES
- Packs header-only shared API  
- SFW/NSFW body semantics explicit  
- On-page model stack  
- Turnaround + lock hero → I2I angles  
- Correct output_prefix for queue filter  

#### NEGATIVES
- Still depends on merge for sampler/family metadata if missing  
- Single LoRA only (strength fixed 0.85)  
- Asset types clothing/building/prop less matured visually  
- No video concept path  

#### Industry
Closest to **Meshy/Tripo reference sheet generators** + **Leonardo character ref** packs; more disciplined negatives than MJ default.

#### Defects
| Pri | |
|---|---|
| P1 | LoRA stack depth 1 |
| P2 | Pack quality needs live mesher A/B |
| P3 | Advanced fields are QLineEdit not spins |

---

### 3.4 ChainStudioPage (v1-hidden)

**Files:** `qt_ui/chain/*` (Engine, Canvas, ConfigPanel, DialogBar, Rail, Store, Watcher, …)  
**modeId:** `chain` · Ctrl+2 (hidden)

#### Purpose / JTBD
Multi-stage creative chain (image→image→video…) with variation lock/canvas — composition engine without raw Comfy nodes.

#### Wiring
- Compiled + in stack; nav gated  
- `MainWindow::submitChainGenerationRequest` + `queueManager()` + `ChainCompletionWatcher`  
- Engine binds store/watcher/submitFn  

#### Produces
Per-stage payloads with engine `queue_item_id` stamped for watcher correlation.

#### Layout
Top strip · chain rail · canvas variations · config panel · dialog bar (v3 fixed workspace).

#### Simple / Advanced
Not integrated with global disclosure the same way as cockpits.

#### Model pickers
Via stage config panel (ChainConfigPanelWidget) — separate from CatalogPicker pattern.

#### POSITIVES
- Real engine + completion watcher architecture  
- Most finished multi-step composition surface historically  
- Queue item id correlation superior to studio pending flags  

#### NEGATIVES
- Hidden from v1 — dead product surface for most users  
- UI maturity uneven vs ArcaneGlass cockpits  
- Cognitive load high for Simple users  
- Docs/FEATURE_MATRIX historically omitted it  

#### Industry
Between **Comfy workflows** and **Runway Gen boards** / **Krea** canvas chains.

#### Defects
| Pri | |
|---|---|
| P1 | Nav-hidden without in-app “coming soon” discoverability |
| P2 | Visual polish drift vs Doc 32 shell |
| P2 | Disclosure not unified |
| P3 | Self-test surface only for power users |

---

## 4. CONTENT PAGES

### 4.1 ModelManagerPage + assets/*

**modeId:** `models` · Ctrl+0  
**Files:** `ModelManagerPage.*`, `assets/ModelCard{View,Model,Delegate}.*`, `ModelThumbnailCache`, `ModelOverlayStore`, `ModelSidecar`, `AssetCatalogScanner`, `CatalogPickerDialog`, `LoraStackController`, `ModelStackState`

#### Purpose / JTBD
Browse local inventory (checkpoints/LoRAs/VAE…), inspect sidecars/previews, send to generation, bind/launch workflows.

#### Wiring
- `useModelRequested` → `MainWindow::sendModelToGeneration`  
- `useWorkflowRequested` / `resolveWorkflowDependenciesRequested` ↔ Flows  
- `setImportedWorkflows` from library refresh  
- Inventory snapshot for command palette  

#### Produces
Handoff values (path/name) + trigger words; no direct enqueue.

#### Layout
Grid/list cards + details/Inspect overlay; async refresh watcher.

#### Simple / Advanced
N/A (content surface).

#### POSITIVES
- Card grid + thumbnails + favorites  
- Inspect overlay min-height discipline  
- Workflow bind arc  
- `@token@` theme  

#### NEGATIVES
- Large catalogs scan cost  
- Family display can lag until worker classify  
- Content page density still below cockpit instrument ideal  
- Nested scroll risk if details + grid both scroll poorly  

#### Industry
**Civitai desktop-lite** + **Comfy model manager**; weaker social metadata than Civitai web.

#### Defects
| Pri | |
|---|---|
| P1 | Family/classifier race at cold start |
| P2 | Inspect/details still QA-sensitive |
| P3 | Download root UX secondary |

---

### 4.2 WorkflowLibraryPage + import + workflows/*

**modeId:** `workflows` · Ctrl+7  
**Files:** `WorkflowLibraryPage.*`, `WorkflowImportDialog.*`, `workflows/WorkflowLaunchController.*`

#### Purpose / JTBD
Import Comfy graphs, readiness/deps, launch or open as cockpit draft — power-user escape hatch without living in nodes.

#### Wiring
- `importWorkflowRequested` → import dialog/process  
- `launchWorkflowRequested` → `launchWorkflowProfile` / WithModel  
- `workflowDraftRequested` → `openWorkflowDraft` → `page->applyWorkflowDraft`  
- Feeds Models bind list  

#### Produces
Imported under `runtime/imported_workflows/<slug>`; launch profiles JSON; drafts with modeId.

#### Layout
List + detail + readiness + import candidates; dedicated `applyTheme()` (must not use shell QSS).

#### POSITIVES
- Readiness state machine rich  
- Dual-loader awareness  
- Draft path into cockpits  

#### NEGATIVES
- Complexity wall for Simple users  
- Import/compile failures hard to explain  
- Visual density historically flat until dedicated QSS  
- Long file (166KB) god-page  

#### Industry
**ComfyUI Manager + workflow browser** with friendlier packaging; not yet **Invoke** board elegance.

#### Defects
| Pri | |
|---|---|
| P1 | First-run empty library dead-end without guided import |
| P2 | God-page maintainability |
| P2 | Error copy / readiness pedagogy |
| P3 | Search/filter IA |

---

### 4.3 T2VHistoryPage

**modeId:** `history` · Ctrl+8  
**Files:** `T2VHistoryPage.*` (~94KB)

#### Purpose / JTBD
Browse past generations (video-first heritage; P1 image fields added), open/reveal, copy prompt, LTX requeue validate/submit.

#### Wiring
- Project root history index + LTX registry merge  
- LTX requeue via side processes + contracts  
- Not full “send to cockpit” redesign yet (mode-aware history still open)

#### Layout
Table + details card (`detailsCard_`); `reflowForWidth` ~260–360 details; `@token@` QSS (fixed %10 bug).

#### POSITIVES
- Contract filters; dual LTX outputs awareness  
- Theme/reflow fixes landed  
- Image mediaType generalization started  

#### NEGATIVES
- Name still T2V* while multi-media  
- Requeue path LTX-specialized  
- Weak “reload into T2I with all params”  
- Table+details still fights half-width  

#### Industry
**Runway assets** / **MJ gallery** / **Comfy history** — SpellVision more contract/debug heavy, less delightful browse.

#### Defects
| Pri | |
|---|---|
| P0/P1 | Mode-aware “open in originating cockpit with full payload” incomplete |
| P1 | Rename/reframe as unified History |
| P2 | LTX-only deep tools vs other families |
| P3 | Table column priority at half-width |

---

### 4.4 DatasetGenerationPage (ORPHAN)

**Files:** `DatasetGenerationPage.cpp` (~7.8KB)  
Not on rail / not in MainWindow page stack (verify CMake residual).  
Emits `generate_dataset`. Phase D / v2 territory.  
**Redesign:** hide from product mind; don’t polish.

---

### 4.5 ModePage Inspire (hidden stub)

Honest “Coming soon”; `@token@`. Keep gated.

---

## 5. Cross-cutting redesign principles (from live defects)

### 5.1 Must preserve
1. Global Simple/Advanced — reveal in place  
2. Cockpit instrument density + Generate sole chromatic CTA  
3. ArcaneGlass tokens; cyan = Success only  
4. Half-screen + restore = same functionality (scroll OK, clip not OK)  
5. Studios never reimplement worker transport  
6. `@token@` QSS replace — never `QString::arg` past %9; never drop mid `%N` in multi-arg ThemeManager sheets  
7. Lazy generation pages  
8. Concept packs as shared adherence layer  

### 5.2 Must fix in redesign
1. **Every generating studio has on-page model+LoRA** (Character, Comic) — clone Concept pattern  
2. **Studio job correlation** — replace single `pendingStudioMode_` with queue_item_id / output_prefix map (steal Chain watcher pattern)  
3. **Unified History** open-in-cockpit with full param restore  
4. **One scroll doctrine** applied consistently (document cockpit left-rail exception or kill it)  
5. **Extract ImageGenerationPage** into PromptRail / Canvas / InspectorHost / VideoStack modules without behavior change  
6. Delete or attic `VideoGenerationPage` + `DatasetGenerationPage` if unwired  
7. Telemetry width ownership: reflow only, never poll-time fixed widths  
8. ShowEvent+deferred reflow on all studio pages  

### 5.3 Showcase shell (Doc 32)
ThemeManager choke-point: radii card10/control6; quiet glass buttons; rail 8px tiles; type 400/600/700. Prefer shell inheritance over per-page skin fights.

---

## 6. Industry north stars (redesign targets)

| Capability | Best-in-class reference | SpellVision gap |
|---|---|---|
| One-click T2I | MJ / Firefly | Local power OK; delight/empty states lag |
| Pro local params | Comfy / A1111 / Forge | Abstraction promise — keep; improve readiness pedagogy |
| Video gen | Runway / Kling / Luma | Family+OP good; edit/timeline none (OK for v1) |
| Character identity | MJ cref / IP-Adapter UIs / Leonardo | Comic/Character weak lock |
| Multi-view sheets | Meshy / Tripo ref tools | Concept Lab right direction |
| Workflow power | Comfy | Flows exists; onboarding harsh |
| Queue/history | Runway assets | Mode-aware reload incomplete |
| Multi-step canvas | Krea / Chain concept | Chain built but hidden |

---

## 7. P0–P3 defect register (aggregated)

### P0
- Character/Comic generate without on-page model/LoRA (silent merge / Model:none)  
- Owner half-screen matrix not closed → cannot claim S  
- ThemeManager multi-arg `%N` deletion risk (Grade-F void history)  
- Combo sizeHint regressions on any new long-path field  

### P1
- Studio single-pending preview mis-route under concurrency  
- History not full param restore into cockpits  
- Dual/nested scroll feelings (cockpit left + inspector; content pages)  
- Classifier/catalog cold-start family fallback  
- Chain/Inspire discoverability while hidden  
- Comic no true multi-panel queue + weak identity lock  
- Stale input path permanent block if clear API misused  

### P2
- ImageGenerationPage / WorkflowLibraryPage god-files  
- Diffusers-labeled native video fields  
- VideoGenerationPage / DatasetGenerationPage orphans  
- LTX-skewed History tools  
- Mesh stages env-gated empty states need guided install CTA  
- LoRA single-slot on Concept  

### P3
- Disclosure qWarning spam  
- Naming (T2VHistoryPage)  
- Hero marketing copy residue on studios  
- Advanced QLineEdit vs spin boxes on Concept  

---

## 8. Per-page checklist template (for redesign tickets)

For each page ship ticket, require:

1. Purpose sentence + JTBD user story  
2. modeId + rail + palette + details dock  
3. Payload schema + worker `command`/`task_command`  
4. Layout wire: splitters, scroll owners, inspector budget  
5. Simple vs Advanced matrix (in-place)  
6. Model/LoRA presence **or** explicit non-generate justification  
7. Half-screen QA (full / restore / half W / half H)  
8. Theme: `@token@` only; no shell QSS on content  
9. Preview correlation strategy (id or prefix)  
10. Industry parity note (what we won’t copy)

---

## 9. Suggested redesign sequencing (no implementation)

1. **P0 studio model stack** (Character + Comic) — copy ConceptReferencePage controls + payload keys + empty block  
2. **Studio job IDs** — ChainCompletionWatcher pattern generalized  
3. **History → cockpit reload** — closes Arc 2 “mode-aware history”  
4. **Cockpit modularization** behind same UI (enable redesign without 6k-line risk)  
5. **Orphan deletion** + rail IA pass (Concept placement, Char/Comic grouping)  
6. **Owner Doc 30 matrix** → S gate  
7. Chain unhide only after Simple path + glass parity  

---

## 10. File index (quick)

```
qt_ui/ImageGenerationPage.*          # T2I/I2I/T2V/I2V cockpits
qt_ui/VideoGenerationPage.*          # ORPHAN stub
qt_ui/generation/CockpitInspector.*
qt_ui/generation/GenerationRequestBuilder.*
qt_ui/generation/VideoGenerationPolicy.*
qt_ui/preview/MediaPreviewController.*
qt_ui/preview/ImagePreviewController.*
qt_ui/QueueManager.* QueueTableModel.* OutputCardModel.*
qt_ui/studios/CharacterStudioPage.*
qt_ui/studios/ComicStudioPage.*
qt_ui/studios/ConceptReferencePage.*
qt_ui/studios/ConceptReferencePacks.h
qt_ui/chain/ChainStudioPage.* (+ engine/canvas/…)
qt_ui/ModelManagerPage.* + assets/*
qt_ui/WorkflowLibraryPage.* WorkflowImportDialog.*
qt_ui/workflows/WorkflowLaunchController.*
qt_ui/T2VHistoryPage.*
qt_ui/DatasetGenerationPage.*        # ORPHAN
qt_ui/ModePage.*                     # Inspire stub
qt_ui/MainWindow.*                   # handoff hub
qt_ui/shell/ShellNavigationController.*
docs/design/29_character_comic_studios.md
docs/design/30_responsive_layout_final_cleanup.md
docs/design/31_concept_reference_lab.md
docs/design/32_showcase_shell_redesign.md
```

---

*End recon. Code untouched.*
