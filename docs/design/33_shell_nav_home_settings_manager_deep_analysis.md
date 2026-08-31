# 33 — Shell + Nav + Home + Settings + Manager deep analysis

**Status:** Analysis only (no code changes)  
**Date:** 2026-07-25  
**Scope:** MainWindow shell, rail/nav, Home/dashboard, Settings, ManagerPage, ModePage (Inspire), Command palette, title bar, ThemeManager, glass/dashboard chrome  
**Authority:** live `qt_ui/*` + `docs/design/{16,30,32,ArcaneGlass}` + `brain/Product/UX Principles.md`  
**Owner grade context:** A- polish / S still owner-eyes gated (Doc 30)

---

## 0. Executive map (product job)

SpellVision sells **ComfyUI power without node graphs** inside a **VS Code–skeleton / ArcaneGlass-skin** desktop studio.

| Layer | Job-to-be-done |
|-------|----------------|
| **Shell** | Host every mode in one chrome: title bar, activity rail, page stack, bottom telemetry, queue overlay, details context |
| **Nav** | Instant mode switch + shortcuts + palette parity; gate unfinished modes |
| **Home** | Launch deck + “Your work” gallery; route into Create / Manage |
| **Settings** | Appearance, Simple/Advanced default, Home layout prefs |
| **Manager** *(orphaned)* | Comfy Manager + custom-node install/repair surface (shipping arc dependency) |

**Non-negotiables (UX Principles + CLAUDE §2):**
- Global Simple/Advanced; Advanced **reveals in place**
- Cockpit: no page scroll; content surfaces: **one** scroll
- Half-screen + restore = same functionality
- One hero violet accent; cyan = Success/ready only
- Owner visual QA > token-only polish

---

## 1. Full rail inventory + gating

### 1.1 Canonical specs

Source: `qt_ui/shell/ShellNavigationController::{railButtonSpecs,isModeHidden,pageContextForMode}`

| modeId | Label | Section (data only) | Shortcut | Default visible |
|--------|-------|---------------------|----------|-----------------|
| `home` | Home | Create | Ctrl+1 | yes |
| `chain` | Chain | Create | Ctrl+2 | **HIDDEN** |
| `t2i` | T2I | Create | Ctrl+3 | yes |
| `i2i` | I2I | Create | Ctrl+4 | yes |
| `t2v` | T2V | Create | Ctrl+5 | yes |
| `i2v` | I2V | Create | Ctrl+6 | yes |
| `character` | Char | Create | Ctrl+Shift+C | yes |
| `concept` | Concept | Create | Ctrl+Shift+R | yes |
| `comic` | Comic | Create | Ctrl+Shift+M | yes |
| `workflows` | Flows | Manage | Ctrl+7 | yes |
| `history` | History | Manage | Ctrl+8 | yes |
| `inspiration` | Inspire | Manage | Ctrl+9 | **HIDDEN** |
| `models` | Models | Manage | Ctrl+0 | yes |
| `settings` | Prefs | System | Ctrl+, | yes |

**v1.0 gate:** `kV1HiddenModes = { "chain", "inspiration" }` unless env `SPELLVISION_SHOW_ALL_MODES` is set (any non-empty value).

**Enforcement sites:**
1. `railButtonSpecs()` filters hidden specs out of the rail
2. `MainWindow::switchToMode` redirects hidden → `home` (non-recursive for home)
3. Command palette only adds Chain when `!isModeHidden("chain")`; **Inspire is not offered in palette at all** even when unhidden (asymmetry / bug)

**Section headers:** `RailButtonSpec.section` still carries Create/Manage/System, but `createSideRail()` intentionally emits **flat buttons only** (no CREATE/MANAGE/SYSTEM labels) — Doc 32 / shell-chrome pass.

**Not on rail (and not modeIds):**
- `ManagerPage` (Comfy Manager UI) — **no modeId, not in stack**
- Queue / Details / Logs — overlay / bottom utility, not modes
- Downloads — `openManager("downloads")` aliases → `models`

### 1.2 Page stack membership (`MainWindow::buildPages` / lazy gen)

| modeId | Page class | Build timing |
|--------|------------|--------------|
| home | `HomePage` | eager |
| chain | `spellvision::chain::ChainStudioPage` | eager (nav-gated) |
| character | `CharacterStudioPage` | eager |
| comic | `ComicStudioPage` | eager |
| concept | `ConceptReferencePage` | eager |
| workflows | `WorkflowLibraryPage` | eager |
| history | `T2VHistoryPage` | eager |
| inspiration | `ModePage` stub | eager (nav-gated) |
| models | `ModelManagerPage` | eager |
| settings | `SettingsPage` | eager |
| t2i/i2i/t2v/i2v | `ImageGenerationPage` | **lazy** via `ensureGenerationPageBuilt` + idle prewarm after `showEvent` |

**Startup rationale (commented in header):** four ImageGenerationPages ~6s construct cost; window paint delayed ~9.8s when eager. Pattern is load-bearing.

---

## 2. SHELL surface

### 2.1 Purpose / JTBD
Provide the **always-on studio chrome**: brand, search/command entry, Simple/Advanced, layout toggles, window chrome, mode host, global queue/progress/VRAM/backend health.

### 2.2 Wiring

**Entry:** `MainWindow` ctor → worker queue controller → `buildShell` → `buildPages` → `buildPersistentDocks` → `buildBottomTelemetryBar` → restore `ui/advancedMode` → `switchToMode("home")` → `setMinimumSize(1180,760)` / `resize(1760,1020)`.

**Composition (`buildShell`):**
```
QMainWindow
├── menuWidget: [CustomTitleBar + TitleBarTransitionStrip(12px)]
├── central: HBox [ SideRail(74px) | QStackedWidget#MainPageStack ]
├── statusBar: BottomTelemetryContainer (fixed 40px bar / 34px chip row)
└── queueOverlay_ (frameless slide-up; queueDock_ retired = nullptr)
```

**Theme:** `MainWindow` applies **only** `ThemeManager::shellStyleSheet()` on itself; content pages own dedicated sheets (critical pitfall: never push shell QSS into nested pages).

**QSettings org/app:** `DarkDuck` / `SpellVision`.

| Key | Owner | Purpose |
|-----|-------|---------|
| `ui/advancedMode` | `MainWindow::setDisclosureMode` | global Simple/Advanced |
| `appearance/themePreset` | ThemeManager | preset enum int |
| `appearance/usePresetAccent` | ThemeManager | bool |
| `appearance/accentOverride` | ThemeManager | QColor |
| `appearance/effectsWeight` | ThemeManager | 0–100 (default 68, showcase floor ≥74) |
| `appearance/showcaseMaturityPass_v1` | ThemeManager::load | one-time ArcaneGlass force |
| `ui/animationQuality` | ThemeManager | Minimal/Standard/Rich/Lavish |
| `ui/home_dashboard/*` | HomeDashboardSettings | layout JSON + migrations |
| `ui/home_dashboard/favorites_json` (+ legacy `ui/home/…`) | HomePage | favorites/hero preview |

**Signals (shell-critical):**
- Title bar → layout menu, palette, disclosure, sidebar/bottom/details toggles, window controls, system menu
- `disclosureModeChanged(bool)` fan-out → Settings, Character/Comic/Concept, each ImageGenerationPage
- Worker poll 1800ms → queue UI + telemetry; VRAM nvidia-smi 2s; Comfy GET `/system_stats`
- Queue label click → activity drawer (`eventFilter` on `bottomQueueLabel_`)

### 2.3 What it produces
- UI state only (no generation artifacts directly)
- Routes generation via `submitGenerationRequest` / `submitStudioGenerationRequest` / chain submit API
- Comfy teardown on `aboutToQuit` (`tearDownComfyOnExit`)
- Logs via details/logs overlay

### 2.4 Layout architecture
- **No** main content splitter at shell level — horizontal rail + stack
- Bottom utility = overlay over page area (`positionQueueOverlay` on resize)
- Adaptive: `reflowBottomTelemetryWidths`, title bar `reflowForWidth`, compact shell helpers (`isCompactShellWidth`)
- Min window 1180×760 — still may lose to child `minimumSizeHint` (commented belt-and-suspenders)

### 2.5 Theme / QSS
- Central choke point: `ThemeManager::shellStyleSheet()` multi-arg `%N` (Doc 32 pitfall: never delete mid placeholders)
- Showcase pass: radii card 10 / control 6; rail 8px tiles + 2px left accent; quiet glass buttons; Generate sole chromatic CTA in IGP sheet
- Telemetry: `#BottomTelemetryContainer` glass strip; **no pipe separators** (separators nulled)
- Title bar: `WA_StyledBackground` required for QWidget subclass gradient paint
- Transition strip softens bar→body seam

### 2.6 Positives
1. **Lazy generation pages** — real product latency engineering with single idempotent path
2. **Nav gate reversible** without deleting Chain/Inspire code
3. **Telemetry maturity** — mode-filtered queue, completion pulse, video vs image completion paths, monotonic progress, env `SPELLVISION_TELEMETRY_LOG`
4. **Shell vs content QSS separation** learned the hard way
5. **Flat rail + single brand mark** (title badge only) — dual-chrome debt intentionally killed
6. **Studio handoff** pattern (`submitStudioGenerationRequest` + pending mode/panel) avoids N worker clients
7. **Command palette** with fuzzy subsequence + model picker submode + Esc back

### 2.7 Negatives
1. **MainWindow.cpp god-file (~5200 LOC)** — shell, queue, worker, workflows, telemetry, palette, details copy
2. **Settings partial wiring** — only `presetChanged` + disclosure connected; accent/effects/restore/home-dashboard/customize **emit into void**
3. **Home runtime summary never fed** — `HomePage::setRuntimeSummary` has no MainWindow caller
4. **applyShellStateForMode** briefly sets `bottomPageLabel_` to `modeId.toUpper()` then `syncBottomTelemetry` overwrites with full context — dual writers
5. **Chrome token drift:** `Chrome::ModeRailWidth=76` vs live rail `setFixedWidth(74)`; `TitleBarHeight=32` vs CustomTitleBar `34`
6. **DashboardSurfaceTokens** still default `radiusHero=26/panel=20` while Home glass helper forces 18/14 and ThemeManager card=10 — three radius systems
7. **Details dock prose** still marketing/legacy (“production launch deck”, Wan-specific body) — not instrument-grade
8. **ManagerPage orphan** while shipping arc needs dep resolution UI
9. **Inspire palette gap** when unhidden
10. **Dual QSettings constructors** — some sites use `QSettings("DarkDuck","SpellVision")`, Home uses bare `QSettings settings` (relies on app org/name set in main)

### 2.8 Industry comparison
| Pattern | SpellVision | Best practice peers |
|---------|-------------|---------------------|
| Activity rail | VS Code–like, text tiles 56×44 | VS Code icons+labels; Cursor icon rail; Linear no rail |
| Command palette | Ctrl+Shift+P fuzzy | VS Code/Cursor parity — good |
| Status bar | Dense telemetry chips | VS Code status; Runway sparse; Adobe denser timeline |
| Title custom chrome | Frameless-ish + custom | VS Code/Cursor yes; Midjourney web N/A |
| Queue | Overlay drawer | Runway job tray; Comfy queue panel |
| Density target | Linear × ArcaneGlass | Linear precision is right north star for premium DCC |

### 2.9 Severity-ranked defects

| Sev | Defect |
|-----|--------|
| **P0** | Settings accent / effects / restore / Home dashboard config / customize **not connected** in MainWindow — Settings UI is partially inert |
| **P0** | Shipping/first-run needs runtime manager; **ManagerPage unwired** (no rail, no stack, no open path) |
| **P1** | Home ActiveModels / runtime band never receives live `setRuntimeSummary` |
| **P1** | Three competing radius/density systems (ThemeManager, DashboardSurfaceTokens defaults, Home glass helper) |
| **P1** | Owner S matrix still open (Doc 30) — half-screen not formally signed |
| **P2** | Palette missing Inspire when unhidden; Chain gated consistently but Inspire asymmetric |
| **P2** | Details panel generic marketing copy + Models “Open Downloads” → models alias |
| **P2** | Chrome token vs live size drift (rail 74/76, title 32/34) |
| **P3** | MainWindow dual write of page label; dead `#SideRailBadge` QSS still in shell sheet |
| **P3** | QSettings bare vs explicit org inconsistency risk |

---

## 3. NAV (ShellNavigationController + switchToMode + palette)

### 3.1 Purpose
Single source of truth for mode inventory, visibility, human context strings, checked rail state.

### 3.2 Wiring
- `createSideRail` iterates `railButtonSpecs()`, `createRailButton` 56×44 `#SideRailButton`, shortcuts via `QAbstractButton::setShortcut`
- Scrollable column in `#SideRailScroll` (5px steel scrollbar) — prevents clipping when many modes
- `switchToMode` → gate → `ensureGenerationPageBuilt` → `modePages_` lookup → stack current → `applyShellStateForMode`
- Palette `populatePaletteTopLevel` categories: Navigation, Generation (if gen page active), Models, Prompt, Output, Workflows, System
- Studio pages emit `navigateRequested` → same `switchToMode`

### 3.3 Produces
Navigation UI state only; no files.

### 3.4 Layout
Rail fixed 74px; internal scroll; stretch after buttons.

### 3.5 Theme
Shell QSS `#SideRail` / `#SideRailButton:checked` with left accent bar.

### 3.6 Positives
- Gate design is clean and reversible
- Shortcuts + tooltip native text
- Scrollable rail was a real fix for mode count growth
- Checked state centralized in controller

### 3.7 Negatives
- Spec `section` unused in UI (dead data / future dual chrome temptation)
- Shortcut numbers (Ctrl+3…6) shift meaning when Chain hidden — **index ≠ mode** cognitive load
- Text labels truncated (“Char”, “Prefs”, “Flows”) vs palette long names
- No badges (queue count, update, error) on rail icons
- Concept/Character/Comic use modifier chords; discoverability depends on tooltip

### 3.8 Industry
VS Code keeps stable order with separators; Cursor uses icons; Adobe apps use named workspaces. SpellVision’s **acronym rail** is power-user dense but onboarding-hostile vs Midjourney/Runway named modes.

### 3.9 Defects
| Sev | Defect |
|-----|--------|
| **P2** | Shortcut ordinals misleading when modes gated |
| **P2** | No rail visual hierarchy beyond order (Create vs Manage) |
| **P3** | Truncated labels vs full pageContext mismatch |

---

## 4. TITLE BAR (`CustomTitleBar`)

### 4.1 Purpose
Custom window chrome + command search affordance + Simple/Advanced + layout toggles.

### 4.2 Wiring
- Height 34, objectName `CustomTitleBar`
- Search pill → `commandPaletteRequested` (click filter)
- Mode toggle → `disclosureModeChangeRequested`
- Layout icons → sidebar/bottom/details toggles
- Window drag via `isDraggableArea` / mouse events; double-click maximize
- Context menu → system menu
- `setContextText` from `applyShellStateForMode` (breadcrumb; titleLabel empty/hidden)
- Brand: rounded pixmap from icon path walk; accent frame from `Color::Accent`

### 4.3 Layout / adaptive
`reflowForWidth`:
- `<1180` hide shortcut chip
- `<980` hide layout sidebar icons (keep Simple/Advanced + min/max/close)
- pill min 280→220→180 by width

### 4.4 Theme
`applyThemeStyling` regenerates painted icons + local label styles; shell still owns bar gradient.

### 4.5 Positives
- Half-screen reflow learned from showcase defects
- Disclosure dual-entry disciplined (clicked not toggled)
- Menu bar removed — reduced dual chrome (comment Phase 2)
- Brand badge sole logo

### 4.6 Negatives
- Context breadcrumb + bottom page chip + details title = **triple context**
- Layout menu / system menu contents not as rich as VS Code
- Search is fake field (not type-in-place) — click opens modal palette (acceptable VS Code pattern)
- Icon buttons 24px with 10px glyphs — can read sparse

### 4.7 Defects
| Sev | Defect |
|-----|--------|
| **P2** | Triple context repetition |
| **P3** | Chrome::TitleBarHeight token unused |

---

## 5. THEME SYSTEM (`ThemeManager` + glass tokens)

### 5.1 Purpose
Single theming choke point: colors, spacing, type, radii, shell/IGP/settings/home/mode sheets, animation quality, effects weight.

### 5.2 Presets
`ArcaneGlass`, `ObsidianStudio`, `NeonForge`, `IvoryHolograph`, `Ember`

### 5.3 Tokens
- **Color:** 26 canonical (`Surface0–3`, text, accent family, borders, semantic, glass)
- **Spacing:** Hairline 4 → Gutter 32
- **Type:** Display→Micro with weights reduced in showcase (800→700 display etc.)
- **Chrome:** TitleBarHeight, MenuBarHeight, ModeRailWidth (partially stale)
- **Radii:** card 10, control 6, pill 999

### 5.4 Migrations
`appearance/showcaseMaturityPass_v1`: force ArcaneGlass, effects ≥74, lift Minimal→Rich once.

### 5.5 Glass paint stack (`DashboardGlassPanel::paintEvent`)
Shadow → GlassFill mix → body gradient → specular → radial glow → hero side falloff → vignette → outer hairline → inner platinum rim → optional arc → top rim light. Variants: Standard/Raised/Hero/Inset/Utility.

### 5.6 Positives
- Token architecture is multi-billion-dollar correct direction
- WCAG contrast self-check (debug)
- Application overlay palette for menus/tooltips
- Live `themeChanged` subscription pattern
- Doc 16 + ArcaneGlass role correction (cyan out of accent)

### 5.7 Negatives
- Shell stylesheet still **mega multi-arg** (fragile — F-grade incident Doc 32)
- Content pages mixed: some `@token@` replace (good), generators still `.arg` chains
- `DashboardSurfaceTokens` radii/glow defaults lag instrument density
- Fonts still Segoe interim — Space Grotesk/Inter/JetBrains not bundled
- Settings effects slider may not reach ThemeManager if unwired (see P0)

### 5.8 Defects
| Sev | Defect |
|-----|--------|
| **P0** | Effects/accent path from Settings may not mutate ThemeManager |
| **P1** | Multi-arg shell QSS remains footgun |
| **P2** | Token radius triad inconsistency |
| **P2** | Bundled fonts not shipped |

---

## 6. HOME surface (`HomePage` + `HomeDashboardPage` + modules)

### 6.1 Purpose / JTBD
**Return surface + gallery:** “What did I make / what do I launch next?”  
Default cinematic layout: thin **Active Models** band + tall **Your work** (`recent_outputs` h=14). Launch modules hidden by default (rail/palette handle nav).

### 6.2 Wiring
```
HomePage
  QScrollArea
    HomeDashboardPage (12-col grid)
      HomeModuleFrame → HomeModuleBase implementations
```
- Config: `HomeDashboardSettings` load/save `ui/home_dashboard/layout_json` + preset/density/version
- Migration: `yourWorkExpand_v1` rewrites cinematic layout to gallery-first
- Signals → MainWindow: modeRequested, managerRequested, launchRequested, openOutputRequested, sendOutputToInputRequested
- Gallery uses `OutputCardModel` + self-scan (legacy card feed no-op)
- `showEvent` refreshes app data sources
- Theme: `homePageStyleSheet()` on HomePage; HomeDashboardPage own `@token@` sheet

**Modules (`HomeDashboardIds`):**
| Id | Role |
|----|------|
| `hero_launcher` | Starter hero + launch |
| `workflow_launcher` | Imported workflow cards |
| `recent_outputs` | Gallery “Your work” |
| `favorites` | Favorite starters |
| `active_models` | Runtime/model band |

**Presets:** CinematicStudio, ProductiveCompact, MotionWorkspace, ModelOps, Minimal  
**Density:** Compact, Comfortable, Cinematic

### 6.3 Produces
- Persisted dashboard layout JSON
- Favorites/hero preview JSON
- Navigation intents; no jobs directly (launches hand off to cockpits)

### 6.4 Layout
- Single outer scroll (content-surface rule) ✓
- 12-column `QGridLayout`; customize mode move/resize/visibility on frames
- `compactLayout_` rebuild at width < 1320
- Glass panels via helper radii Hero 18 / Standard 14 / Utility 12

### 6.5 Positives
- Modular dashboard architecture (registry + placements) is extensible
- Gallery-first default matches “studio home” better than marketing hero
- Output open + send-to-I2I paths wired carefully with deferred page build
- Equality guards on content setters avoid thrash
- One-time expand migration fixes empty void

### 6.6 Negatives
1. **Settings Home controls unwired** — preset/density/module checks/customize button don’t reach HomePage
2. **Runtime summary dead** — ActiveModels module static without MainWindow feed
3. **rebuildDashboard is destructive** — resize compact toggle tears widgets (perf/flicker risk)
4. **Customize mode entry** only via Settings signal (dead) — users may not discover
5. **Fallback cards** can mask empty real state
6. Nested conceptual chrome: module frames + glass + preview plates — density can feel “dashboard product” not “DCC home”
7. Favorites still settings-JSON, not first-class library

### 6.7 Industry
| Peer | Home pattern |
|------|----------------|
| Midjourney | Infinite feed + create CTA |
| Runway | Project/recents grid |
| Adobe Firefly | Feature tiles + recents |
| Linear | No home — last workspace |
| Cursor | No home — editor |

SpellVision’s customizable module grid is **ambitious** (closer to Adobe Start) but half-wired customization undercuts it. For redesign: either **commit to gallery+status instrument** (cinematic default) or **full layout editor** with live Settings bridge — not both half-done.

### 6.8 Defects
| Sev | Defect |
|-----|--------|
| **P0** | Home dashboard Settings bridge missing |
| **P1** | Runtime summary not connected |
| **P1** | Destructive rebuild on compact breakpoint |
| **P2** | Customize mode orphaned |
| **P3** | Fallback content honesty |

---

## 7. SETTINGS surface (`SettingsPage`)

### 7.1 Purpose / JTBD
Tune appearance + workspace disclosure default + Home dashboard shape. **Not** a full preferences app (no paths, GPU, accounts, shortcuts editor, privacy).

### 7.2 Wiring (intended vs actual)

**UI sections:**
1. Workspace Mode (Simple/Advanced combo)
2. Theme Presets
3. Accent Color (preset toggle + choose)
4. Effects Intensity slider + Restore Default Theme
5. Animation Quality
6. Home Dashboard (preset, density, module checkboxes, reset layout, customize Home)
7. Live Theme Preview card

**Connected in MainWindow today:**
- `disclosureModeChangeRequested` ↔ `setDisclosureMode` ✓
- `presetChanged` → `ThemeManager::setPresetByIndex` ✓
- `themeChanged` → `SettingsPage::applyTheme` (self) ✓
- `animationQuality` → ThemeManager **directly from Settings ctor** ✓

**NOT connected (signals exist, no slots in MainWindow):**
- `usePresetAccentChanged`
- `chooseAccentColorRequested`
- `effectsWeightChanged`
- `restoreDefaultsRequested`
- `homeDashboardConfigChanged`
- `homeDashboardCustomizeRequested`

Also no reverse seed of Home config into Settings on load (`setHomeDashboardConfig` never called from MainWindow).

### 7.3 Produces
Would produce ThemeManager persistence + Home layout JSON if wired. Today: preset + animation + disclosure only reliably.

### 7.4 Layout
Single `QScrollArea` + stacked section cards — correct content-surface pattern.

### 7.5 Theme
`settingsStyleSheet()` + preview helper styles; applyTheme syncs combo/slider from ThemeManager (so effects slider **shows** ThemeManager value even if user changes don’t stick).

### 7.6 Positives
- Correct dual-entry design for disclosure (`activated` only)
- Preview card concept
- Animation quality descriptions
- Section card structure readable

### 7.7 Negatives
- **Trust-breaking inert controls** (P0)
- Scope title “Appearance & Home Dashboard” admits missing: paths, models root, Comfy root, worker, shortcuts, telemetry, privacy, updates
- Theme list copy omits Ember
- No search within settings
- No restart-required badges

### 7.8 Industry
VS Code Settings: search + JSON + categories. Cursor: thin. Adobe: deep prefs. Linear: minimal.  
For premium AI studio: Settings must own **Paths / Runtime / Appearance / Keyboard / Privacy** — appearance-only is under-shipped vs product promise.

### 7.9 Defects
| Sev | Defect |
|-----|--------|
| **P0** | Majority of Settings signals unwired |
| **P1** | No Settings categories for runtime/paths (shipping blocker adjacency) |
| **P2** | Ember missing from marketing copy |
| **P3** | Preview not full shell fidelity |

---

## 8. MANAGER surface (`ManagerPage`)

### 8.1 Purpose / JTBD
**Runtime dependency console:** detect Comfy Manager, list custom node packages, install missing video nodes, restart Comfy, open roots. Critical for v1.0 shipping / guided deps (Doc 19/28).

### 8.2 Wiring — ORPHAN
- Compiled in `CMakeLists.txt` (`ManagerPage.cpp`)
- **Never constructed in MainWindow**
- **No modeId / rail / palette entry**
- `MainWindow::openManager` only maps managerIds → existing modes (models/workflows/history/settings/inspiration/downloads→models)

Worker commands used by the page (when it would run):
- `comfy_manager_status`
- `install_comfy_manager`
- (install selected / missing video / restart — see rest of cpp)

Transport: **spawns `python/worker_client.py` via QProcess** (not the live NDJSON TCP controller MainWindow uses for queue). Parallel client path = dual protocol debt.

Cache: `AppLocalDataLocation/manager_status_cache.json` (5 min fresh / 7 day retain).

**Comfy root resolution defaults include stale path** `D:/AI_ASSETS/comfy_runtime/ComfyUI` while live product uses `C:\sv_comfynext\ComfyUI` (CLAUDE/skill) — high risk wrong root.

### 8.3 Produces (if used)
- Node install side effects on disk
- Manager status cache file
- Log view text
- `statusMessageChanged` signal (nowhere connected)

### 8.4 Layout
Header + horizontal action button row (7 buttons) + status columns + `QTableWidget` + log — **functional but not ArcaneGlass instrument**. No scroll shell; table expands. No glass panels. Hard margins 22.

### 8.5 Theme
Relies on inherited objectNames (`PageTitle`, `ManagerStatusLabel`…) — **no dedicated applyTheme / settings-like sheet**. Likely flat / mismatched vs cockpit.

### 8.6 Positives
- Correct product capability for shipping
- Async request pattern with busy lock
- Disk+memory cache for status
- Table columns cover Status/Package/Method/Families/Repo/Notes

### 8.7 Negatives
1. **Completely unreachable** in product UI
2. Dual worker access path (QProcess client vs TCP)
3. Stale Comfy root default
4. Pre-ArcaneGlass visual language
5. No integration with Models readiness / Flows dependency_plan
6. Naming collision: “Manager” vs `ModelManagerPage` / `openManager` router

### 8.8 Industry
ComfyUI Manager web UI; Stability / Runway hide deps; Adobe manages engines in Creative Cloud.  
SpellVision needs a **first-class Runtime** surface (not a buried table) with health, installs, restart, path truth.

### 8.9 Defects
| Sev | Defect |
|-----|--------|
| **P0** | Unreachable ManagerPage while shipping depends on deps |
| **P0** | Possible wrong Comfy root default |
| **P1** | Dual worker transport |
| **P1** | No theme parity |
| **P2** | Naming collision Manager vs Models |
| **P3** | No empty/error empty-states design |

---

## 9. MODE PAGE / INSPIRE stub (`ModePage`)

### 9.1 Purpose
Honest “Coming soon” placeholder for unfinished modes (Inspiration).

### 9.2 Wiring
Built as `inspirationPage_` with title/subtitle/3 planned bullets. Hidden by nav gate. Still in stack.

### 9.3 Layout
Hero card + 2-col planned cards grid. No scroll (short content).

### 9.4 Theme
`@token@` sheet; eyebrow **Coming soon**; denser 14px cards (post B+ pass).

### 9.5 Positives
Stub honesty improved vs “Planned Section N” forest.

### 9.6 Negatives
- Still shows “Planned · area N” card titles
- Not in palette when unhidden
- Details panel still offers actions as if moodboard existed

### 9.7 Defects
| Sev | Defect |
|-----|--------|
| **P2** | Palette/details treat Inspire as real |
| **P3** | Planned area card chrome residual |

---

## 10. COMMAND PALETTE (`CommandPaletteDialog`)

### 10.1 Purpose
VS Code-style command launcher + model/LoRA picker submode.

### 10.2 Wiring
- Ctrl+Shift+P + title search pill
- Owner builds `Command` vector each open
- Fuzzy subsequence score; category headers; right-detail shortcut/subtitle
- `keepOpen` + `setBackHandler` for model picker
- Theme via `applyThemeStyling` + paint delegate tokens

### 10.3 Positives
Strong architecture; model inventory from `modelsPage_->inventorySnapshot()`; trigger words on handoff.

### 10.4 Negatives
- No recent commands
- No keybinding editor
- Generation actions only when already on gen page
- Missing nav.inspire
- Doesn’t list Character/Comic generate actions

### 10.5 Defects
| Sev | Defect |
|-----|--------|
| **P2** | Incomplete command coverage for studios |
| **P3** | No recents/pinned |

---

## 11. DASHBOARD CHROME PRIMITIVES

| Class | Role | Notes |
|-------|------|-------|
| `DashboardGlassPanel` | Painted glass plate | Real stack; theme live; variants |
| `DashboardMetricChip` | Title/value chip | Painted; used on Home modules |
| `DashboardPreviewPlate` | Abstract preview waves | Decorative; phase param |
| `DashboardSurfaceTokens` | Derived paint palette | fromTheme; legacy larger radii |

**Positives:** Custom paint > fake CSS blur; token-driven.  
**Negatives:** Defaults not fully aligned to ThemeManager radiusCard=10; still some hard-coded darks (`#01040a`, `#02050b`) in glass paint.

---

## 12. BOTTOM TELEMETRY (shell product chrome)

### Chips
Ready | Page | (stretch) | Backend(W+C dots) | Queue | VRAM | Model | LoRA | State | ETA | GlowProgressBar

### Adaptive
- Model/LoRA Expanding stretch 3/2
- Hide LoRA `<1000`, ETA `<1280`
- Progress 120/140/164
- **No** fixed width fight in `syncBottomTelemetry` (width owned by reflow)

### Backend
Worker latch + Comfy HTTP probe; rich-text dots; tooltip detail.

### Defects
| Sev | Defect |
|-----|--------|
| **P1** | Model/LoRA empty on Home/Settings/studios (only gen page) — expected but feels “none” dead |
| **P2** | Queue count mode-filtered may confuse vs global activity |
| **P3** | Ready/Busy vs State Idle/Running semantic overlap |

---

## 13. QUEUE / DETAILS OVERLAY (shell adjunct)

- Phase 5: dock retired → frameless overlay
- Tabs: queue / details / logs (utility tray)
- Details actions mode-specific (`configureDetailsActions` / `triggerDetailsAction`)
- Coalesced queue UI flush 140ms

**Redesign note:** Details panel is a **third inspector** competing with cockpit inspector and studio side rails — IA debt for multi-billion redesign (collapse into one context system).

---

## 14. CROSS-SURFACE QSETTINGS LEDGER

```
DarkDuck / SpellVision
├── ui/advancedMode
├── ui/animationQuality
├── ui/home_dashboard/version
├── ui/home_dashboard/preset
├── ui/home_dashboard/density
├── ui/home_dashboard/layout_json
├── ui/home_dashboard/yourWorkExpand_v1
├── ui/home_dashboard/favorites_json
├── ui/home_dashboard/hero_preview_json
├── ui/home/favorites_json          (legacy fallback)
├── ui/home/hero_preview_json       (legacy fallback)
├── appearance/themePreset
├── appearance/usePresetAccent
├── appearance/accentOverride
├── appearance/effectsWeight
└── appearance/showcaseMaturityPass_v1
```

AppLocalData: `manager_status_cache.json` (ManagerPage only).

---

## 15. REDESIGN PLAN HOOKS (multi-billion, non-prescriptive inventory)

### 15.1 Information architecture target
```
Shell
├── Rail (icon+label, stable ids, badges)
├── Title (brand, workspace name, search, disclosure, window)
├── Stage (one primary surface)
├── Context system (ONE inspector: selection | job | page help)
└── Status (health, queue, resources, model stack)
```

**Kill dual/triple chrome:** details overlay vs cockpit inspector vs module frames.

### 15.2 Must-fix before polish spend
1. Wire Settings completely or remove inert controls
2. Promote Runtime Manager to real mode (or Settings → Runtime tab) with live Comfy path
3. Feed Home runtime from telemetry
4. Unify radius/type tokens
5. Owner half-screen matrix sign-off (Doc 30)

### 15.3 Nav redesign questions
- Keep acronyms or full words?
- Stable shortcuts by modeId not ordinal?
- Badge rail for queue/errors?
- Chain/Inspire: hide vs “Coming soon” rail disabled state?

### 15.4 Home redesign questions
- Gallery-only OS home (Midjourney-like) vs module dashboard (Adobe Start)?
- If modules stay: live customize + Settings must work
- ActiveModels should mirror bottom telemetry or die

### 15.5 Settings IA proposal (categories)
Appearance · Workspace · Paths & Runtime · Models Library · Keyboard · Privacy/Telemetry · Advanced

### 15.6 Competitive positioning (shell)
- **Win vs Comfy:** no graph, instrument chrome
- **Win vs Midjourney:** local power, models, workflows
- **Win vs Runway:** desktop density + offline GPU
- **Match Cursor/VS Code:** palette, rail, title search
- **Match Linear:** density/type precision (Doc 32)

---

## 16. FILE / SYMBOL INDEX (quick)

| Concern | Path / symbol |
|---------|----------------|
| Shell build | `MainWindow::buildShell` |
| Pages | `MainWindow::buildPages` |
| Mode switch | `MainWindow::switchToMode` |
| Nav specs | `ShellNavigationController::railButtonSpecs` |
| Gate | `ShellNavigationController::isModeHidden` |
| Telemetry | `buildBottomTelemetryBar`, `reflowBottomTelemetryWidths`, `syncBottomTelemetry` |
| Disclosure | `MainWindow::setDisclosureMode` → `ui/advancedMode` |
| Palette | `showCommandPalette`, `populatePaletteTopLevel`, `enterModelPickerMode` |
| Title bar | `CustomTitleBar::{reflowForWidth,applyThemeStyling,setDisclosureMode}` |
| Theme | `ThemeManager::{load,save,shellStyleSheet,rebuildColorTokens}` |
| Home host | `HomePage` |
| Dashboard | `HomeDashboardPage::rebuildDashboard` |
| Home persist | `HomeDashboardSettings` |
| Settings | `SettingsPage` |
| Manager orphan | `ManagerPage` |
| Inspire stub | `ModePage` |
| Glass | `DashboardGlassPanel::paintEvent` |
| Tokens | `DashboardSurfaceTokens::fromTheme` |
| Design | `docs/design/{16,30,32,ArcaneGlass_token_spec}` |
| UX | `brain/Product/UX Principles.md` |

---

## 17. SEVERITY ROLLUP (all surfaces)

### P0
1. Settings signals mostly unwired (accent/effects/restore/home/customize)
2. ManagerPage unreachable; shipping deps UI missing from shell
3. ManagerPage Comfy root default may point at rollback tree

### P1
4. Home runtime summary never pushed
5. Radius/token density triad drift
6. Dual worker transport if Manager revived without TCP unify
7. Owner half-screen S matrix open
8. Details/context triple system IA debt

### P2
9. Palette Inspire asymmetry; studio commands incomplete  
10. Shortcut ordinal confusion under gating  
11. Telemetry Model/LoRA “none” on non-gen pages  
12. Destructive Home rebuild on compact  
13. Manager visual/theme debt  
14. Fonts not bundled  

### P3
15. Dead SideRailBadge QSS / section field unused  
16. Chrome token size drift  
17. QSettings bare vs explicit  
18. ModePage planned-area residual  
19. Marketing details copy  

---

## 18. WHAT “DONE” LOOKS LIKE FOR REDESIGN DISCOVERY

- [ ] Every Settings control mutates a single owner and persists
- [ ] Runtime Manager is a first-class reachable surface with correct Comfy path
- [ ] Home Active band reflects live telemetry or is removed
- [ ] One context inspector model documented
- [ ] Rail inventory stable with badges + honest stubs
- [ ] Token single radius/type ramp; glass defaults match
- [ ] Doc 30 matrix signed S by owner eyes
- [ ] No dual chrome (logo, section headers, triple page title)
- [ ] Command palette covers all navigable modes + primary actions

---

*End of analysis. No code was modified for this document beyond creating this markdown report.*
