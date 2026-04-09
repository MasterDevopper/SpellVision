# SpellVision UI File Mapping
## Checklist-to-File Ownership Map

This document maps the UI implementation checklist directly into the current and planned Qt/C++ file structure so each UI sprint has clear ownership.

---

# 1. Main Shell

## MainWindow.h / MainWindow.cpp
### Owns
- application shell composition
- page stack registration and routing
- right dock orchestration
- bottom telemetry bar placement
- queue dock integration
- global command triggers
- persisted dock/layout restoration
- page-to-page send actions

### Build tasks
- [ ] build stable shell layout
- [ ] remove repeated page headers from page surfaces
- [ ] wire command palette shortcut
- [ ] wire dock resizing and saved geometry/state
- [ ] route Home / Generation / History / Queue / Settings / Workflows / Models / Downloads / Managers / System
- [ ] expose send-to-T2I / send-to-I2I / send-to-Home actions
- [ ] bind bottom telemetry widgets to runtime payloads
- [ ] keep title bar and shell window behavior correct

## CustomTitleBar.h / CustomTitleBar.cpp
### Owns
- title bar chrome
- window controls
- drag/maximize behavior
- command palette entry surface
- app-level quick actions if present

### Build tasks
- [ ] final premium title bar layout
- [ ] remove redundant app title text if shell branding covers it elsewhere
- [ ] preserve snap/maximize/minimize behavior
- [ ] add command palette entry affordance

## ThemeManager.h / ThemeManager.cpp
### Owns
- design tokens
- color roles
- typography roles
- density tokens
- button variants
- input styles
- card/panel styling
- rail and dock styling

### Build tasks
- [ ] define density presets
- [ ] define button variants
- [ ] define panel/card styles
- [ ] define focus/hover/pressed states
- [ ] define rail active state styling
- [ ] define telemetry bar styling
- [ ] define settings tree styling

---

# 2. Navigation

## NavigationRail.h / NavigationRail.cpp (or MainWindow-owned rail if still inline)
### Owns
- left rail widget
- icon buttons
- active indicator
- tooltips
- optional expanded mode

### Build tasks
- [ ] icon-first rail layout
- [ ] active page accent line
- [ ] hover state polish
- [ ] tooltip labels
- [ ] reserve slots for future pages

---

# 3. Home Page

## HomePage.h / HomePage.cpp
### Owns
- adaptive Start Creating hero
- mode switcher
- dependency banner
- current model stack summary
- recent workflow cards
- favorites carousel
- launch and handoff actions

### Build tasks
- [ ] remove decorative oversized page header
- [ ] build T2I / I2I / T2V / I2V mode switch
- [ ] build hero input area
- [ ] build dependency banner area
- [ ] build model stack summary strip
- [ ] render recent workflow cards
- [ ] render favorites carousel
- [ ] emit populate-generation-page signals instead of silent launching

---

# 4. Image Generation

## ImageGenerationPage.h / ImageGenerationPage.cpp
### Owns
- full generation workspace
- prompt editor
- negative prompt editor
- model stack controls
- LoRA stack controls
- output and queue actions
- resolution/sampling controls
- advanced section
- preview canvas and quick actions

### Build tasks
#### Prompt section
- [ ] large prompt editor
- [ ] token insertion hooks
- [ ] visible family defaults area
- [ ] visible applied trigger words area

#### Negative prompt section
- [ ] large negative prompt editor
- [ ] negative token insertion hooks
- [ ] family-default negatives visibility

#### Model stack section
- [ ] checkpoint picker
- [ ] VAE picker
- [ ] LoRA stack list
- [ ] upscaler type/picker
- [ ] control modules area placeholder or implementation

#### LoRA stack subsection
- [ ] add row
- [ ] remove row
- [ ] enable/disable row
- [ ] reorder rows
- [ ] weight slider + numeric input
- [ ] trigger word chip display
- [ ] recommended negative chip display
- [ ] click-to-add token actions
- [ ] compatibility badge per LoRA
- [ ] stack summary state for telemetry/history metadata

#### Output / queue section
- [ ] output path controls
- [ ] Generate button
- [ ] Queue button
- [ ] Save Snapshot
- [ ] Reset
- [ ] job status feedback

#### Resolution / sampling
- [ ] width / height
- [ ] steps
- [ ] cfg
- [ ] seed
- [ ] sampler
- [ ] scheduler

#### Canvas
- [ ] preview frame
- [ ] loading/empty state
- [ ] hover quick actions
- [ ] send-to-history / open-folder / compare hooks

## ModelCompatibility.h / ModelCompatibility.cpp
### Owns
- compatibility filtering results used by UI
- family-aware logic for checkpoints / LoRAs / upscalers / controls
- visibility rules for incompatible assets

### Build tasks
- [ ] checkpoint family inference
- [ ] compatibility filtering APIs for LoRAs
- [ ] compatibility metadata for trigger/default display
- [ ] support “show incompatible” setting

## AssetCatalog.h / AssetCatalog.cpp
### Owns
- normalized asset metadata for UI consumption
- checkpoint inventory
- LoRA inventory
- VAE inventory
- upscaler inventory
- later trigger-word metadata store and asset annotations

### Build tasks
- [ ] expose model catalog
- [ ] expose LoRA catalog
- [ ] expose trigger words / recommended negatives per LoRA
- [ ] expose tags/source metadata
- [ ] expose thumbnails/previews where available

---

# 5. History

## HistoryPage.h / HistoryPage.cpp
### Owns
- results browser
- grid/list mode
- preview pane
- clean metadata summary
- expanded metadata
- compare mode
- actions back to generation pages

### Build tasks
- [ ] history grid/list
- [ ] grouping by Day / Session / None
- [ ] preview panel
- [ ] metadata summary
- [ ] expandable advanced metadata
- [ ] send-to-T2I
- [ ] send-to-I2I
- [ ] rerun
- [ ] compare mode
- [ ] favorites/bookmark hooks later

## MetadataPanel.h / MetadataPanel.cpp (new recommended)
### Owns
- reusable metadata viewer widget for History/right dock

### Build tasks
- [ ] clean summary mode
- [ ] advanced JSON/details mode
- [ ] provenance/lineage badge area
- [ ] copy/reveal actions

---

# 6. Queue

## QueueManager.h / QueueManager.cpp
### Owns (Qt-side)
- queue-facing UI integration model
- queue commands from UI
- current queue widgets coordination
- detail sync into right dock

### Build tasks
- [ ] queue action wiring
- [ ] pause/resume/cancel/retry/remove from UI
- [ ] active job strip feed
- [ ] persistent-state handoff to core layer later

## QueueTableModel.h / QueueTableModel.cpp
### Owns
- table representation of queue items
- column formatting
- sort/filter integration

### Build tasks
- [ ] visible state, progress, prompt summary, affinity summary
- [ ] badge/status formatting
- [ ] drag/drop reorder support

## QueueFilterProxyModel.h / QueueFilterProxyModel.cpp
### Owns
- filtering/sorting of queue items

### Build tasks
- [ ] sort by state / created / active
- [ ] search/filter support
- [ ] status filters

## QueuePage.h / QueuePage.cpp or QueueDock widget (recommended if added)
### Owns
- active job strip
- grouped controls
- queue table/cards host

### Build tasks
- [ ] top active strip
- [ ] control row grouping
- [ ] batch action bar
- [ ] optional card mode later

---

# 7. Settings

## SettingsPage.h / SettingsPage.cpp
### Owns
- settings tree navigation
- search bar
- category pages/content modules
- family prompt defaults UI
- workspace behavior UI
- appearance UI
- runtime/integration settings UI

### Build tasks
#### shell
- [ ] tree navigation
- [ ] search bar
- [ ] category content panel
- [ ] expandable subsections

#### categories
- [ ] Appearance
- [ ] Workspace
- [ ] Generation Defaults
- [ ] Models & Assets
- [ ] Workflows
- [ ] Runtime & Performance
- [ ] Inspiration & Library
- [ ] Advanced

#### specific features
- [ ] density selector
- [ ] queue view settings
- [ ] history grouping settings
- [ ] workflow click behavior
- [ ] family prompt defaults editor
- [ ] LoRA trigger-word display behavior settings if needed
- [ ] theme/background settings
- [ ] runtime path/settings surfaces

---

# 8. Workflows

## WorkflowsPage.h / WorkflowsPage.cpp (new recommended)
### Owns
- imported workflows library
- workflow cards
- dependency status
- workflow detail preview
- launch and repair actions

### Build tasks
- [ ] workflow card grid/list
- [ ] dependency health badges
- [ ] profile summary view
- [ ] launch actions
- [ ] repair actions

## DependencyPrompt.h / DependencyPrompt.cpp
### Owns
- missing dependency banner/modal/prompt surface

### Build tasks
- [ ] reusable dependency banner
- [ ] install/repair CTA states
- [ ] missing nodes / models summary rendering

---

# 9. Models / Downloads / Managers / System

## ModelsPage.h / ModelsPage.cpp (new)
### Owns
- model inventory browser
- checkpoint cards
- LoRA browser
- compatibility and source metadata
- trigger word visibility per LoRA

### Build tasks
- [ ] checkpoints tab
- [ ] LoRAs tab
- [ ] details panel
- [ ] trigger words panel
- [ ] activation/send-to-generation actions

## DownloadsPage.h / DownloadsPage.cpp (new)
### Owns
- external model download UI
- queue of downloads
- source/provider inputs

### Build tasks
- [ ] Hugging Face input
- [ ] Civitai input
- [ ] direct URL input
- [ ] download queue view

## ManagersPage.h / ManagersPage.cpp (new)
### Owns
- runtime manager surface
- Comfy manager surface
- node/dependency manager summaries
- advanced system tools grouping

### Build tasks
- [ ] runtime controls
- [ ] Comfy manager status
- [ ] dependency repair summary
- [ ] node install status

## SystemPage.h / SystemPage.cpp (new)
### Owns
- static system diagnostics
- graphs/history if implemented later
- runtime diagnostics view

### Build tasks
- [ ] GPU/CPU/RAM info presentation
- [ ] storage roots display
- [ ] diagnostics snapshot view

---

# 10. Shared Reusable Widgets Recommended

## Recommended new shared widgets
- `TokenChipWidget.*`
- `PromptTokenBar.*`
- `LoraStackWidget.*`
- `ModelStackSummaryWidget.*`
- `BottomTelemetryBar.*`
- `ActiveJobStrip.*`
- `SectionCard.*`
- `SettingsTreePanel.*`
- `SearchBarWidget.*`
- `CompareViewer.*`
- `PreviewCanvasWidget.*`

### Why
These prevent `MainWindow.cpp` and `ImageGenerationPage.cpp` from becoming monoliths.

---

# 11. Immediate Build Priority Order

## First pass
1. `ThemeManager.*`
2. `MainWindow.*`
3. `HomePage.*`
4. `ImageGenerationPage.*`
5. `SettingsPage.*`

## Second pass
6. `HistoryPage.*`
7. `Queue*`
8. `DependencyPrompt.*`
9. `MetadataPanel.*`

## Third pass
10. `WorkflowsPage.*`
11. `ModelsPage.*`
12. `DownloadsPage.*`
13. `ManagersPage.*`
14. `SystemPage.*`

---

# 12. Final Rule

If a UI requirement changes:
- shell-wide behavior changes go to `MainWindow.*`
- visual tokens/styles go to `ThemeManager.*`
- page-specific layout stays in that page file
- shared controls become widgets, not duplicated hacks
