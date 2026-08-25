# 33 — Billion-Dollar Rebuild: Full Surface Analysis + Scrutinized Build Plan

**Status:** APPROVAL-GATED — analysis + plan + mockup only. **No product code overwritten.**  
**Date:** 2026-07-25  
**Mode:** Operate (desktop product UI) + Platform  
**Authority:** live code + CLAUDE.md + brain ledgers > FEATURE_MATRIX / stale README  
**Mockup:** `docs/design/mockups/spellvision_vnext_approval_mockup.html`  
**Constraint from owner:** do not overwrite/remove code until mockup is ratified.

---

## 0. Executive verdict (read this first)

SpellVision is **not a greenfield toy**. It already has the hard product core that most AI startups never reach:

- Local GPU execution via ComfyUI with **SpellVision-owned graph construction**
- Production **native LTX AV** + Wan video paths (`backend_route=native_comfy_template`)
- Shared-weight fp16 image path + non-destructive LoRA adapters
- A real VS Code–style shell, progressive disclosure, studios, Flows dependency layer

What it is **missing** for a multi-billion-dollar company bar is not “more vibes.” It is:

1. **Shipping product** (installer, first-run, clean-machine proof) — ~15% today  
2. **Modular architecture** (god files: `worker_service.py` ~10k, `ImageGenerationPage.cpp` ~6.3k, `MainWindow.cpp` ~5.2k)  
3. **Unified Operate shell craft** at Linear/Cursor density with **consistent ArcaneGlass law** on every surface  
4. **IA honesty** (hidden/orphan surfaces, stub pages, Stage-1 Models vs full manager)  
5. **Trust layer** (licenses, model safety, guided deps, update gates)

### Winning strategy (after killing weaker options)

**Evolutionary Product Rebuild** — keep the three-layer architecture and Comfy execution engine; rebuild the *product shell, IA, modularity, shipping, and design system enforcement* until the app feels inevitable. Do **not** rewrite in Electron/web. Do **not** rip Comfy. Do **not** “just polish.”

---

## 1. Product truth (what exists)

| Layer | Path | Role |
|-------|------|------|
| Qt6 UI | `qt_ui/` | Shell, pages, request build, queue UX, theme |
| Python worker | `python/worker_service.py` + friends | Jobs, routing, builders, Comfy lifecycle |
| ComfyUI | LIVE `C:\sv_comfynext\ComfyUI` | Node execution |

**Promise:** Comfy/A1111 power **without node graphs**. Abstraction layer *is* the product.

**Settings:** QSettings org=`DarkDuck`, app=`SpellVision`  
**Ports:** worker `127.0.0.1:8765`, Comfy `127.0.0.1:8188`  
**Models root (canonical):** `D:/AI_ASSETS/models`

### Rail inventory (live `ShellNavigationController::railButtonSpecs`)

| modeId | Label | Section | Shortcut | v1 visible? |
|--------|-------|---------|----------|-------------|
| home | Home | Create | Ctrl+1 | yes |
| chain | Chain | Create | Ctrl+2 | **hidden** unless `SPELLVISION_SHOW_ALL_MODES=1` |
| t2i | T2I | Create | Ctrl+3 | yes |
| i2i | I2I | Create | Ctrl+4 | yes |
| t2v | T2V | Create | Ctrl+5 | yes |
| i2v | I2V | Create | Ctrl+6 | yes |
| character | Char | Create | Ctrl+Shift+C | yes |
| concept | Concept | Create | Ctrl+Shift+R | yes |
| comic | Comic | Create | Ctrl+Shift+M | yes |
| workflows | Flows | Manage | Ctrl+7 | yes |
| history | History | Manage | Ctrl+8 | yes |
| inspiration | Inspire | Manage | Ctrl+9 | **hidden** (same gate) |
| models | Models | Manage | Ctrl+0 | yes |
| settings | Prefs | System | Ctrl+, | yes |

Section headers CREATE/MANAGE/SYSTEM are **not** rendered on the rail (owner chrome pass) — section strings still exist in specs for grouping logic only.

### Orphan / not-on-rail surfaces

| Surface | Status |
|---------|--------|
| `ManagerPage` | Built (~785 LOC); **not** in `modePages_` / rail — Comfy Manager / node install UI orphaned |
| `DatasetGenerationPage` | Built; **not** wired |
| `HomePage` vs `HomeDashboardPage` | Dual home lineage; dashboard modules real; risk of split identity |
| Chain Studio engine | Compiled + proven; nav-gated for v1 |
| Inspire | `ModePage` stub only |

### God-file gravity (LOC evidence)

| File | ~LOC | Risk |
|------|------|------|
| `python/worker_service.py` | 10,067 | Every generation path, TCP, queue, adapters spill |
| `qt_ui/ImageGenerationPage.cpp` | 6,361 | Four modes in one mega-widget |
| `qt_ui/MainWindow.cpp` | 5,196 | Shell + submit + telemetry + palette + docks |
| `qt_ui/WorkflowLibraryPage.cpp` | 4,082 | Content page mega |
| `qt_ui/T2VHistoryPage.cpp` | 2,254 | History mega |
| `qt_ui/HomeDashboardPage.cpp` | 1,547 | Home density |
| `qt_ui/studios/CharacterStudioPage.cpp` | 1,524 | Stage pipeline |
| `qt_ui/ThemeManager.cpp` | 1,429 | Token + shell QSS choke-point |

---

## 2. Per-surface analysis

Scoring key: **P**ositive craft · **N**egative debt · industry bar = Linear / Cursor / VS Code shell + Runway media canvas + Adobe Firefly/Leonardo clarity.

### 2.1 Shell — `MainWindow` + `ShellNavigationController` + `CustomTitleBar` + telemetry

**JTBD:** Stable app frame: navigate modes, show global status, host pages, route generation.

**Wiring:**
- `buildShell()` → title bar + side rail + `pageStack_` + docks/overlay + bottom telemetry
- `buildPages()` constructs Home, Chain, Character, Comic, Concept, Flows, History, Inspire stub, Models, Settings; generation pages **lazy** via `ensureGenerationPageBuilt`
- `switchToMode(modeId)` + `modePages_` map + `modeButtons_`
- Global Simple/Advanced: `setDisclosureMode` → QSettings + `disclosureModeChanged`
- Generation: `submitGenerationRequest` / `submitStudioGenerationRequest` / `submitChainGenerationRequest`
- Telemetry: Ready, page, backend (worker+Comfy), queue, VRAM, model, LoRA, ETA, glow progress
- Command palette: `CommandPaletteDialog` + model picker second level
- Comfy tear-down on `aboutToQuit`

**Produces:** Navigation state, queue polling, health probes, worker TCP JSON, window chrome.

**Positives**
- Correct **VS Code skeleton** (title bar, rail, stack, utility tray)
- Lazy generation pages solve real ~6s construction tax — industry-grade startup thinking
- Studio handoff pattern is the right abstraction (studios don’t own transport)
- Telemetry as **product chrome**, not bare QStatusBar
- Nav gate for unfinished modes is honest and reversible
- Worker/Comfy dual health is the right ops signal

**Negatives**
- `MainWindow` is a **god object** (shell + transport + docks + palette + VRAM + Comfy HTTP)
- Dual home (`HomePage` + dashboard) can confuse identity
- Details dock + queue overlay + logs = power-user chrome that can feel **bolted on** vs instrumented
- `ManagerPage` / Dataset orphaned while still compiling → dead code surface area
- Qt QSS multi-arg `%N` footgun already caused Grade-F purple void (Doc 32)
- Owner grade still A- not S; half-screen matrix remains owner eyes

**Industry gap:** Linear/Cursor shells feel **empty of accident**. SpellVision shell is close but still carries multi-era dock debt and mega-file fragility.

**Defects**
- P1: MainWindow decomposition  
- P1: Orphan Manager/Dataset wiring decision (ship or delete from target)  
- P2: Details dock IA (contextual inspector vs permanent clutter)  
- P2: Telemetry width thrash history (skill notes fixed patterns — must stay law)

---

### 2.2 Theme — `ThemeManager` + `DashboardGlassPanel` + Doc 32 showcase pass

**JTBD:** One visual law for the whole app (ArcaneGlass default).

**Positives**
- Central choke-point strategy is **correct** for multi-surface Qt apps (Doc 32)
- ArcaneGlass roles: one violet hero; cyan = Success/ready only
- Painted glass stack (not fake CSS blur chase) is the right Qt engineering choice
- Spacing/Chrome tokens exist; showcase pass tightened radii toward Linear instrument

**Negatives**
- Multi-arg `QString::arg` sequential rewrite hazard is a **production landmine**
- Content pages still own bespoke sheets — drift risk
- Fonts: design wants Space Grotesk / Inter / JetBrains Mono; runtime may still lean Segoe
- Four presets (ArcaneGlass, Obsidian, Neon Forge, Ivory) expand QA surface before S is locked

**Industry gap:** Billion-dollar design systems ship **one default** to excellence, then optional skins. SpellVision should lock ArcaneGlass S before celebrating multi-theme breadth.

---

### 2.3 Home — `HomePage` / `HomeDashboardPage` + modules + `OutputCardModel`

**JTBD:** Start creating fast; show recent work; feel like a studio HQ.

**Positives**
- Dashboard module registry is extensible  
- Recent outputs / Your work expand pass (cinematic layout)  
- Glass tokens shared with rest of shell  

**Negatives**
- Dual page lineage (HomePage vs HomeDashboardPage) is architectural smell  
- Empty gallery historically possible when History had files (sidecar-only model) — skill notes a fix path  
- Risk of marketing density (large glass radii) fighting instrument density  

**Industry gap:** Runway/home of creative tools lead with **last work + one obvious Create**. Home must not be a second settings page.

**Defects:** P1 unify Home; P2 empty-state honesty; P2 one-click create to last mode.

---

### 2.4 Generation cockpits — `ImageGenerationPage` (T2I/I2I/T2V/I2V) + `generation/*`

**JTBD:** Intent → ready stack → generate → canvas result. Simple for novices; Advanced in place.

**Wiring:**
- One class, four `Mode` enum values  
- `CockpitInspector` tabbed Model/Sampling/Output/Advanced + width budget  
- `buildRequestPayload` → MainWindow → worker command  
- `MediaPreviewController` image+video  
- Asset Intelligence / readiness / component stack resolver / operating points  
- Adaptive Wide/Medium/Compact  

**Produces:** JSON payloads (`prompt`, dims, steps, cfg, seed, model, loras, video stack…), previews, errors on action row.

**Positives**
- Progressive disclosure design is **product-correct**  
- Lazy construct + idle prewarm  
- Video family contracts + operating points are enterprise-grade abstraction  
- Combo sizeHint / stacked Components / `setWidthBudget` fixes are hard-won real craft  
- No inert IMG stub on T2I/T2V  

**Negatives**
- 6.3k LOC single page = untestable UI ball of mud  
- Four modes share one tree → mode-specific bugs (video stacked row hosts) leak  
- Inspector readiness not auto-synced unless caller remembers  
- Stale I2I/I2V input paths can hard-block  
- Visual density still varies vs studios  

**Industry gap:** Firefly/Leonardo: fewer controls visible, stronger presets, clearer cost/time. Runway: canvas is hero. SpellVision cockpit is closer to Resolve/Comfy power-user — good for power, needs Simple-mode ruthlessness.

**Defects**
- P0: half-screen / restore owner matrix still open for S  
- P1: split into mode controllers + shared shell host  
- P1: readiness always-synced contract tests  
- P2: Simple presets that hide VRAM cliffs (esp. LTX)

---

### 2.5 Character Studio — `studios/CharacterStudioPage`

**JTBD:** Guided character pipeline from concept → multi-view → mesh → garments → export.

**Wiring:** Stages enum Concept→…→Export; `generateRequested(modeId,payload)` → MainWindow studio submit; `acceptConceptReference` from Concept Lab; mesh stages probe Pixal3D spike honesty.

**Produces:** `runtime/characters/<name>/` projects, gen payloads with prefixes, export manifest.

**Positives**
- Stage rail matches real production pipelines (not a fake single button)  
- Honest mesh-missing warnings (not fake success) — solo-UI honesty gold  
- Concept pack reuse  
- `reflowForWidth` + scroll rails  

**Negatives**
- Product depth incomplete (hair/retopo external) vs rail presence can overpromise  
- Model/LoRA on-page requirement must stay enforced  
- Stage UI can still feel “form-heavy” vs cinematic brief  

**Industry gap:** Character.AI / Artbreeder / Meshy — clearer “you are here” and outcome preview. SpellVision is more pipeline-correct for game assets; needs **outcome-first** stage chrome.

---

### 2.6 Comic Studio — `studios/ComicStudioPage`

**JTBD:** Script → panel grid → generate panels → composite page.

**Produces:** panel images + `runtime/comics/<name>/export/page.png`

**Positives**
- Real composite export  
- Layout presets  
- Side-column scroll for Advanced  

**Negatives**
- Generate-all = first incomplete per click (power incomplete)  
- Style lock / character consistency is soft (prompt scaffold, not identity model)  
- Density/QA still owner-gated  

**Industry gap:** Clip Studio / AI comic tools sell **consistency**. Without identity lock, Comic is a panel batcher.

---

### 2.7 Concept Reference Lab — `ConceptReferencePage` + `ConceptReferencePacks.h`

**JTBD:** Multi-view adherent concept plates (body/clothing/building/prop) with SFW/NSFW packs.

**Positives**
- Header-only packs are the right extension point  
- On-page model/LoRA pickers (product bug class fixed here)  
- Send→Character path  
- SFW massing rules explicit  

**Negatives**
- Still another parallel form language vs cockpit  
- Pack quality is the product; needs continuous curation  

**Industry gap:** Best-in-class is pack library as **content product**, not just UI.

---

### 2.8 Chain Studio — `qt_ui/chain/*`

**JTBD:** Multi-step generation composition graph (highest-finished engine historically).

**Status:** Engine proven; **nav-gated** for v1.0.

**Positives**
- Composition is the moat for “not a single-shot toy”  
- Separate engine/store/canvas modules (better modularity than ImageGenerationPage)  

**Negatives**
- Hidden while Character/Comic visible → IA inconsistency (composition spine hidden, leaf studios shown)  
- UX must not become Comfy clone  

**Industry gap:** Runway Gen-3 / Comfy workflows — Chain should feel like **recipes**, not nodes.

---

### 2.9 Flows — `WorkflowLibraryPage` + import dialog + Python workflow_*  

**JTBD:** Import proven Comfy workflows, check deps, launch with overrides.

**Positives**
- Core of the product promise (abstraction + import)  
- Dedicated content QSS (learned lesson vs shell sheet spam)  
- Dependency plan + readiness real  

**Negatives**
- 4k LOC page  
- Power-user vocabulary can scare Simple users  
- Launch paths multiple (cockpit draft, Models use-workflow, palette)  

**Industry gap:** Zapier/Make for workflows: status, missing deps, one big Run. Flows is close; needs consumer clarity.

---

### 2.10 Models — `ModelManagerPage` + assets/*

**JTBD:** Browse inventory; handoff model/LoRA to generation; (eventually) downloads/health.

**Positives**
- Restored Stage-1 browser (712 assets class of inventory)  
- Inspect overlay, send-to-generation, workflow bind hooks  
- Disk cache  

**Negatives**
- Not full 552-line Model Manager spec (no downloads, weak dependency health UI)  
- Cache root “not configured” class gaps  

**Industry gap:** Civitai/manager UIs sell **discovery + trust**. Stage-1 is inventory only.

---

### 2.11 History — `T2VHistoryPage`

**JTBD:** Browse past outputs; requeue; open folder; mode-aware filtering.

**Positives**
- Substantial surface; real media  
- `@token@` theme discipline after arg bug  

**Negatives**
- Name still T2V-centric while multi-mode  
- Details min-width historically crushed table  
- Mode-aware spine still polish item (brain ledger)  

---

### 2.12 Settings — `SettingsPage`

**JTBD:** Paths, theme, disclosure default, effects, workspace prefs.

**Positives**
- Dual entry for Simple/Advanced with MainWindow single writer  
- Theme migration hooks  

**Negatives**
- Settings sprawl risk; needs IA groups (Workspace / Runtime / Appearance / Privacy / Advanced)  
- Path drift reconciliation (models root, Comfy root) still a product trust issue  

---

### 2.13 Inspire — `ModePage` stub

**Honest Coming soon** — good. Hidden from rail for v1 — good.  
**N:** Do not build a grey forest of fake cards. When built: moodboard → send-to-cockpit only.

---

### 2.14 ManagerPage (orphaned)

**JTBD:** Comfy Manager node install, missing video nodes, restart runtime.

**N:** Extremely valuable for shipping **and** currently unreachable. Either wire under Prefs→Runtime / System or integrate into first-run + Flows deps. Leaving compiled-but-orphan is multi-billion-dollar product sin (dead surface area, dual paths).

---

### 2.15 DatasetGenerationPage (orphaned)

Deferred integration of external app. Keep out of rail until real.

---

### 2.16 Worker + contracts + abstraction layer

**JTBD:** Accept jobs, route families, build graphs, drive Comfy, emit progress/results.

**Positives**
- Extracted state machine module  
- Video family contracts (wan/ltx/hunyuan/mochi production-class rows; cogvideox detected)  
- Native template pattern proven (LTX grounded from `/object_info`)  
- Memory optimization wired  
- Resolvers: model/node deps, workflow scanner/importer, slot mapper  

**Negatives**
- 10k LOC god file remaining  
- Path drift in `runtime_paths.default_comfy_root` vs live C: cutover  
- `queued → completed` silent fail class bug  
- Dual venv (worker vs Comfy) complexity for shipping  
- Logging default WARNING hides info  

**Industry gap:** Cloud platforms hide runtime. Desktop billion-dollar product must make runtime **trustworthy and installable** (Bambu Studio / DaVinci / Unity Hub class first-run).

---

## 3. Positives portfolio (keep / double down)

1. Product promise clarity (abstraction layer)  
2. Comfy-as-engine + owned graphs (correct velocity strategy)  
3. Native LTX/Wan production path discipline  
4. Global Simple/Advanced reveal-in-place  
5. VS Code shell architecture  
6. ArcaneGlass single-hero-accent law  
7. Studio → MainWindow generation handoff  
8. Lazy cockpit construction  
9. Flows import + dependency readiness  
10. Honest missing-tool warnings (Character mesh)  
11. Half-screen as hard product requirement  
12. Brain vault + CLAUDE constitution (org maturity rare in solo apps)

---

## 4. Negatives portfolio (fix or plan around)

| ID | Issue | Sev | Industry principle violated |
|----|-------|-----|-----------------------------|
| N1 | God files (worker/MainWindow/IGP) | P0-P1 | Maintainability / team scale |
| N2 | Shipping ~15% | P0 | Clean-machine success |
| N3 | Orphan Manager/Dataset | P1 | No dead code paths |
| N4 | Dual Home lineage | P1 | One Home identity |
| N5 | Chain hidden vs leaf studios shown | P1 | IA coherence |
| N6 | Models Stage-1 vs promise | P1 | Discovery product |
| N7 | QSS `%arg` landmines | P0 historical / P1 process | Design system safety |
| N8 | Job transition silent fail | P1 | Reliability contract |
| N9 | Path drift / dual venv | P1 | Installer trust |
| N10 | Showcase not S | P1 | Premium bar |
| N11 | Feature matrix / docs stale | P2 | Org truth |
| N12 | Studio product depth incomplete | P2 | Overpromise risk |
| N13 | License badges incomplete | P1 for ship | Compliance |
| N14 | Nested scroll / clip history | P1 residual | Responsive parity |
| N15 | Multi-theme before one S default | P2 | Focus |

---

## 5. Options considered — scrutiny — kill list

### Option A — Full rewrite (Electron/Tauri/React + rewrite worker)

**Pitch:** Modern web design systems, faster UI iteration.  
**Kill reasons:**
- Throws away proven Comfy native paths and Qt shell investment  
- Local VRAM/GPU desktop products lose native feel and process control  
- 12–24 months to parity; competitors ship  
- Design craft is not caused by web tech; Linear density is achievable in Qt  

**Verdict:** **Reject.**

### Option B — Visual-only polish pass on current architecture

**Pitch:** ThemeManager + mockups until pretty.  
**Kill reasons:**
- Owner already proved token polish = grade C without architecture  
- God files block safe velocity  
- Shipping still 15% — pretty unshippable app fails market  

**Verdict:** **Reject as sole plan.** (Polish is Phase, not Strategy.)

### Option C — Rip ComfyUI for pure diffusers / custom engine

**Pitch:** Own full stack.  
**Kill reasons:** CLAUDE settled decision; model/node velocity impossible solo; LTX/Wan already native-on-Comfy successfully.

**Verdict:** **Reject.**

### Option D — Evolutionary Product Rebuild (WINNER)

**Keep:** 3-layer arch, Comfy engine, native templates, ArcaneGlass, Simple/Advanced, rail shell, contracts, resolvers.  
**Rebuild:** modular boundaries, IA, shipping, design-system enforcement, unified generation host, content surface maturity, trust/compliance.  
**Method:** strangler fig — extract modules behind stable APIs; no big-bang delete of working generation.

**Verdict:** **Adopt.**

### Option E — Cloud SaaS pivot

**Pitch:** Multi-billion via cloud margins.  
**Kill reasons:** Current moat is local power studio; cloud is a later SKU, not a rewrite of the desktop truth. Can add hybrid later.

**Verdict:** **Defer** as SKU, not foundation replace.

---

## 6. Final build plan — SpellVision VNext (Evolutionary Product Rebuild)

### North-star product definition

> The definitive **local creative operating system for generative media**: intent in, production assets out — image, video, character, comic, chain recipes — with Comfy-class power, Linear-class density, and installer-grade trust.

**Design synthesis (not clone):**
- **Skeleton:** VS Code  
- **Density/precision:** Linear  
- **Media canvas:** Runway  
- **Keyboard power:** Superhuman/Cursor  
- **Skin:** ArcaneGlass (violet hero, platinum structure, cyan ready-only)  
- **Never:** generic purple AI gradient slop, neon forge chaos as default, web-dashboard airiness

### Non-negotiables carried forward

1. Simple/Advanced reveal-in-place  
2. Cockpit no root scroll; content one scroll  
3. Half-screen + restore same functionality  
4. SpellVision owns graphs; Comfy executes  
5. No overwrite of working paths without parity tests  
6. Owner eyes = S gate  

### Phased program (dependency-ordered)

#### Phase 0 — Ratify (this doc + mockup) — **NOW**
- Owner approves visual direction + IA + phase order  
- Freeze cut list for first shippable milestone  
- **No code deletion**

**Exit:** written approval of mockup + plan.

#### Phase 1 — Truth & safety rails (1–2 weeks)
- Path canon: models `D:/AI_ASSETS/models`, Comfy live `C:\sv_comfynext` — kill drift in code/docs (**B3**)
- Job lifecycle: fix or strictly fence `queued→completed` (**B9**)
- Test harness: project venv pytest green for worker contracts
- Doc matrix rebuild (or delete trust in FEATURE_MATRIX)
- Process law: `@token@` only for multi-color QSS; occupancy check for ThemeManager multi-arg
- **Wire or absorb Settings signals** so accent/effects/restore/Home config are not void emitters (**B1**)
- **ManagerPage decision:** Prefs→Runtime surface or first-run only — never leave compiled-orphan (**B2**)
- **Character + Comic on-page model/LoRA pickers** (mirror Concept Lab) — block Generate if empty (**B4**)
- Home `setRuntimeSummary` actually fed from MainWindow telemetry (**B5**)

**Exit:** clean-machine path resolution doc matches runtime; lifecycle tests green; B1–B4 closed or explicitly scheduled with owner dates.

#### Phase 2 — Architecture strangler (2–4 weeks) — **behavior-preserving**
- Split `worker_service.py` by domain (already started with state): TCP, image, video, workflow, comfy lifecycle  
- Extract `MainWindow` into already-started `shell/*` controllers: Navigation, Telemetry, GenerationSubmitter, DockChrome, Palette  
- Split `ImageGenerationPage` into `GenerationShellHost` + mode controllers (T2I/I2I/T2V/I2V) sharing inspector/preview  
- No visual redesign required in this phase  

**Exit:** same UX, smaller files, tests for submit parity.

#### Phase 3 — Design system lock (2–3 weeks)
- Bundle fonts (Space Grotesk / Inter / JetBrains Mono)  
- ArcaneGlass token table complete; Neon Forge etc. secondary  
- Component kit: RailTile, GlassCard, Field, PrimaryGenerate, ReadyPill, Chip, EmptyState  
- Apply kit to Home + T2I first as reference surfaces  
- Owner half-screen S matrix for those two  

**Exit:** Home + T2I owner S; kit documented in DESIGN.md-equivalent repo doc.

#### Phase 4 — Shipping stack (parallel with 3, 3–5 weeks) — **true company gate**
- Installer (Qt + worker venv + Comfy pin OR first-run fetch)  
- First-run wizard: GPU detect, paths, minimal models, Comfy health  
- Guided dependency resolution (Doc 19) as product path  
- Wire **Manager** capabilities into first-run + Prefs→Runtime (absorb orphan)  
- License badges + NOTICE  
- Doc 28 gates filled with evidence  

**Exit:** clean machine → first successful T2I without dev scripts.

#### Phase 5 — Unified Create experience (2–3 weeks)
- One Generation Shell host for four modes (tabs or mode switcher inside host)  
- Ruthless Simple defaults + VRAM-safe LTX caps  
- Send-to graph: Models ↔ Cockpit ↔ Studios ↔ History  
- Command palette coverage parity with buttons  

**Exit:** one craft language across T2I/I2I/T2V/I2V.

#### Phase 6 — Content surfaces parity (2–3 weeks)
- Models: Stage-2 discovery/health (subset of full spec that matters)  
- History: rename + mode-aware spine  
- Flows: Simple “Run recipe” path  
- Home: single identity, last work hero, one Create  

**Exit:** no Manage surface feels like a different app.

#### Phase 7 — Studios productization (3–5 weeks)
- Character: concept→multiview ship-complete; mesh honest optional  
- Comic: identity lock v1 + generate-all queue  
- Concept packs as curated content  
- Decision: Chain re-enable as **Recipes** (not graph fear) or keep gated until recipe UX  

**Exit:** studios match cockpit craft; no overpromise on 3D.

#### Phase 8 — Platform (ongoing)
- Crash reporting / diagnostics export  
- Gated Comfy update (Doc 25 pattern)  
- Performance budgets (startup, page switch, queue poll)  
- Optional cloud render SKU later  
- Phase D 3D only after video+ship solid  

---

## 7. Target IA (approved direction for mockup)

```
[Title bar: brand · search/palette · Simple/Advanced · window]
[Rail]  Home
        Create
          Image · Video · Character · Concept · Comic
          (+ Recipes/Chain when ready)
        Library
          Models · Flows · History
        System
          Prefs · Runtime (absorbs Manager)
[Main]  page host
[Bottom] Ready · Backend · Queue · VRAM · Model · LoRA · Progress
```

**Renames (product language, not code yet):**
- Prefs → Settings  
- Flows → Recipes (or keep Flows with subtitle “Imported workflows”)  
- T2I/I2V raw IDs stay power-user; Simple UI says Image / Video  

**Cut from first public ship (unchanged truth):**
- Phase D 3D execution  
- Dataset generation  
- Full character mesh auto  
- Audio depth  
- Inspire full (unless tiny moodboard v0)

---

## 8. Success metrics (company bar)

| Metric | Target |
|--------|--------|
| Clean-machine first image | < 30 min including downloads on reference SKU |
| Cold start to interactive shell | < 3 s (generation pages lazy) |
| T2I Simple path clicks to generate | ≤ 3 after model present |
| Owner visual grade | S on Home + Image cockpit + shell at full/half/restore |
| Crash-free generation sessions | 99% on smoke suite |
| God files | no UI/worker file > 2.5k without module split plan |
| Docs truth | FEATURE_MATRIX rebuilt or deleted |

---

## 9. Risk register

| Risk | Mitigation |
|------|------------|
| Strangler breaks generation | Parity pytest + golden payload tests before visual phases |
| Design thrash | One approved mockup; ArcaneGlass only for S lock |
| Installer scope explosion | Pin Comfy commit; staged download; rollback build kept |
| Overbuilding studios | Ship concept+image depth first |
| Solo bandwidth | Phase 4 shipping is the critical path; polish after install |

---

## 10. What this plan deliberately does **not** do

- Does not delete `qt_ui` or `python` trees  
- Does not replace Comfy  
- Does not require Electron  
- Does not implement code before mockup ratification  
- Does not claim FEATURE_MATRIX as truth  

---

## 11. Approval checklist (owner)

- [x] Accept **Option D** Evolutionary Product Rebuild
- [x] Accept ArcaneGlass × Linear density visual direction in mockup
- [x] Accept phase order (truth → strangler → design lock → **shipping** parallel) — with **scope expansion** below
- [x] Accept IA renames/Runtime absorption of Manager
- [ ] Accept original cut list — **SUPERSEDED** by owner 2026-07-25 approvals
- [x] Annotate mockup nits — **owner additions listed in §11b**
- [x] Explicit **GO** to begin implementation (approved with additions)

### 11b. Owner-approved scope additions (2026-07-25) — binding

| # | Addition | Notes / external refs |
|---|----------|------------------------|
| A1 | **Dataset generator page fully wired** | Integrate/adapt from `C:\Users\xXste\Code_Projects\Sohya_kk` as needed |
| A2 | **Build + wire Inspiration page** | Unhide `inspiration`; real moodboard/recipe surface, not ModePage stub |
| A3 | **Replace rail icons** with a better set | Premium/readable ArcaneGlass-compatible icons |
| A4 | **Models page filters** | Usable Type/Family/Status (+ search) filters beyond bare tree |
| A5 | **Generation pages: run workflows** and/or **drop workflow JSON to run** | Flows launch + drag-drop on cockpit |
| A6 | **Upscaling** — model + algorithmic | Cockpit + worker path |
| A7 | **Embeddings** — positive + negative | Cockpit stack + request payload + worker apply |
| A8 | **More samplers and schedulers** | Expand lists; ground in Comfy/diffusers reality |
| A9 | **3D generation page wired** | Trellis 2 + Pixal3D from `C:\Users\xXste\Code_Projects\SpellBound-Engine` (+ spike paths) |

**Still deferred unless owner reopens:** full installer/shipping spine perfection, audio depth, LLM orchestration, cloud SKU.

---

## 12. Artifact index

| Artifact | Path |
|----------|------|
| **This master plan (approval)** | `docs/design/33_billion_dollar_rebuild_analysis_and_plan.md` |
| **Approval mockup** | `docs/design/mockups/spellvision_vnext_approval_mockup.html` |
| Shell/nav/home deep recon (subagent) | `docs/design/33_shell_nav_home_settings_manager_deep_analysis.md` |
| Generation/studios/content deep recon (subagent) | `docs/design/33_generation_studios_content_redesign_recon.md` |
| Worker/architecture deep recon (subagent) | `brain/Planning/Python Worker Architecture Redesign Notes.md` |
| Incumbent UI law | `docs/design/SpellVision_UI_Design_System.md` |
| ArcaneGlass tokens | `docs/design/ArcaneGlass_token_spec.md` |
| Showcase shell | `docs/design/32_showcase_shell_redesign.md` |
| Release gates | `docs/design/28_release_readiness_checklist.md` |

### Extra findings folded from parallel recon (do not miss)

- **`VideoGenerationPage` is an orphan stub** — real T2V/I2V is `ImageGenerationPage` modes; dead `video_generation` command path.
- **Product UI generation is enqueue-first** (`command: "enqueue"` + `task_command` ∈ t2i/i2i/t2v/i2v).
- **T2I dispatch** branches: workflow binding → native Comfy image families → diffusers `run_t2i`.
- **LTX** goes `run_native_video` → split-stack → `LtxVideoAdapter` → template patch → Comfy `/prompt`.
- Orphans to absorb or explicitly cut: `ManagerPage`, `DatasetGenerationPage`, `VideoGenerationPage`.

### Batch completion upgrades (deleg_50569f38 — treat as P0/P1 canon)

| ID | Finding | Sev | Source |
|----|---------|-----|--------|
| B1 | **Settings mostly inert** — MainWindow only consumes `presetChanged` + disclosure; accent / effects / restore / Home dashboard config / customize often emit into the void | **P0** | shell recon |
| B2 | **`ManagerPage` orphaned** — compiled, never constructed; no modeId/rail/palette; shipping/deps UI missing from product | **P0** | shell recon |
| B3 | **Manager default Comfy root** may resolve to **rollback** `D:/AI_ASSETS/comfy_runtime/...` vs live `C:\sv_comfynext\ComfyUI` | **P0** | shell recon |
| B4 | **Character + Comic lack on-page model/LoRA pickers** — silent T2I `takeIfMissing` merge → “Model: none” / wrong stack class bug (Concept Lab already fixed this pattern) | **P0** | gen/studios recon |
| B5 | Home `setRuntimeSummary` never called from MainWindow | **P1** | shell recon |
| B6 | **Three radius systems** fight (ThemeManager 10/6 · DashboardSurfaceTokens 26/20 · Home glass 18/14) | **P1** | shell recon |
| B7 | Details overlay = third inspector competing with cockpit/studio rails | **P1** | shell recon |
| B8 | Studio previews use single `pendingStudioMode_` (race under concurrency); Chain `queue_item_id` watcher is the better pattern | **P1** | gen/studios recon |
| B9 | Job SM: ping illegal `queued→completed`; `transition_job` fails silently; state stays queued while `ok/pong` true | **P1** | worker recon |
| B10 | Contracts: wan/ltx/hunyuan/mochi = production labels; **adapters only Wan+LTX** (Hunyuan/Mochi builders-only gap) | **P1** | worker recon |
| B11 | Worker redesign target shape: **FamilyPlugin packages + RuntimeManifest + shipping spine** (keep Comfy ownership) | plan input | worker recon |

**Phase 1 must explicitly include B1–B4** before visual redesign work claims progress. B4 is a product honesty bug on live Create surfaces.

---

*End of plan. Awaiting owner ratification before any destructive or replacement implementation.*
