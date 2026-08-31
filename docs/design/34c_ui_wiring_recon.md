# SpellVision UI wiring recon (pinpoint only)

Repo: `C:\Users\xXste\Code_Projects\SpellVision` · no product changes made.

---

## 1. Rail icons

| Concern | Location |
|--------|----------|
| Specs (modeId/label/tooltip/section/shortcut) | `qt_ui/shell/ShellNavigationController::{railButtonSpecs,isModeHidden,pageContextForMode}` · `ShellNavigationController.cpp:9–54,56–91` · `.h:15–33` |
| Draw rail | `MainWindow::createSideRail` · `MainWindow.cpp:982–1048` (called `:965`) |
| Button factory | anonymous `createRailButton` · `MainWindow.cpp:413–437` |
| Theme QSS | `ThemeManager.cpp` `#SideRail` / `QToolButton#SideRailButton` (~:899–952); token `Chrome::ModeRailWidth=76` **stale** (live width **74**) |
| State checked | `ShellNavigationController::updateModeButtonState` |

**Current icon mechanism: text-only.**  
`createRailButton` → `setToolButtonStyle(Qt::ToolButtonTextOnly)`, `setText(spec.text)`, **no** `setIcon`, **no** SVG load. SVG assets exist but are **unwired**:

`qt_ui/icons/`: `home.svg`, `t2i.svg`, `i2i.svg`, `t2v.svg`, `i2v.svg`, `inspiration.svg`, `models.svg`, `workflows.svg`, `history.svg`, `settings.svg`, `managers.svg`, `system.svg`, `profile.svg`, brand jpgs.

Brand path search only for title-bar (`brandIconCandidates` · `MainWindow.cpp:489+`), not rail.

**Change points to add icons:**
1. Extend `RailButtonSpec` with `iconName`/`iconPath` (`ShellNavigationController.h:15–22`)
2. Map modeId → SVG in `railButtonSpecs()` or a helper
3. `createRailButton` / loop in `createSideRail` (`MainWindow.cpp:1027–1041`): `QIcon` + `QSvgRenderer` or `QIcon("…/icons/<name>.svg")`, style `ToolButtonTextUnderIcon` (or icon-only + tooltip)
4. Optionally ship/copy icons via CMake / runtime dir (today not referenced in CMake from grep)
5. QSS `#SideRailButton` icon padding in `ThemeManager.cpp`

---

## 2. ModelManagerPage filters + AssetCatalogScanner

| Piece | Symbol / lines |
|-------|----------------|
| Page | `qt_ui/ModelManagerPage.{h,cpp}` · UI build `~:930–1197` |
| Tree columns | Name/Type/Family/Size/Status · `:1021–1026` (**display**, not filter chips) |
| Search | `searchModelEdit_` → tree hide by needle `:1180–1193`; grid `cardProxy_->setNeedle` |
| Favorites | `favoritesToggleButton_` → `ModelCardFilterProxy::setFavoritesOnly` `:1079–1081` |
| Grid proxy | `qt_ui/assets/ModelCardModel.h:67–82` · `.cpp:94–132` — **only** `needle_` + `favoritesOnly_` |
| Type/family detect | `ModelManagerPage::detectType` `:243–257`, `detectFamily` `:215–241` (path heuristics; **no** `embeddings` type) |
| Types today | Model, LoRA, VAE, Encoder, Upscaler, ControlNet |
| Catalog (gen pickers, not Models page inventory) | `qt_ui/assets/AssetCatalogScanner.{h,cpp}` — `scanCatalog(root, subDir)`, `scanImageModelCatalog`, `scanVideoModelStackCatalog`; **not** Models inventory source |
| Worker classify | `python/model_classification.py:85–86` maps `upscale_models`→upscaler, `embeddings`→embedding |
| Send-to | `useModelRequested` → `MainWindow::sendModelToGeneration` `:4547–4594` — VAE no-op; LoRA vs checkpoint only; **no** embedding/upscaler slots |

**Present:** free-text search (name/type/family), ★ Favorites, Grid/List.

**Missing filter UI:** dedicated Type / Family / baseModel dropdowns or chip filters; `ModelCardFilterProxy` has no `setType`/`setFamily`; list view has no type combo; embeddings not in `detectType`; no filter for modality image/video.

**Change points:**
- `ModelCardFilterProxy` + toolbar in `ModelManagerPage` ctor (~`:980–1016`)
- Optional: drive type/family from `model_classification` / worker instead of path `detect*`
- `sendModelToGeneration` if embeddings/upscalers become actionable

---

## 3. Inspiration (Inspire)

| Piece | Location |
|-------|----------|
| Gate | `kV1HiddenModes` includes `"inspiration"` · `ShellNavigationController.cpp:18–21`; unlock `SPELLVISION_SHOW_ALL_MODES` |
| Rail entry | still in `all` specs `:43`, filtered out `:47–52` |
| Page build | `MainWindow::buildPages` · `:1070–1076` — **`ModePage` stub** |
| Registration | `modePages_["inspiration"]` `:1155`; stack `:1139` |
| Nav block | `switchToMode` hidden → home · `:4525–4527` |
| Home CTAs | `HomeDashboardPage.cpp:324–336,739–741` gated by `isModeHidden("inspiration")` |
| `openManager("inspiration")` | `MainWindow.cpp:4608–4611` |
| Details dock copy | `:5026–5029` |
| Palette | **no** `nav.inspiration` (only chain is gated-in; Inspire absent even when unhidden) · palette `:3675–3690` |
| Stub class | `qt_ui/ModePage.{h,cpp}` — “Coming soon” + planned cards |

**Stub bullets (product intent for real page):** moodboard + prompt recipes; filter local/curated/online; editable prompt; Send→Home Hero / T2I / Save as Workflow.

**What to build:** real `InspirationPage` (or `studios/…`) replacing `ModePage`; remove `"inspiration"` from `kV1HiddenModes` when ready; add palette entry; wire send-to via `switchToMode` + `ImageGenerationPage` prompt APIs / Home.

---

## 4. ImageGenerationPage — workflows / samplers / embeddings / upscale

| Surface | Status | Symbols |
|---------|--------|---------|
| **Workflow combo** | Cosmetic named presets only (not imported Flows) | `workflowCombo_` `:1749–1755` — Default Canvas / Portrait Detail / Stylized Concept / Upscale / Repair; Advanced-only visibility `:2772–2775` |
| **Imported workflow drafts** | Via Flows → `MainWindow::openWorkflowDraft` → `applyWorkflowDraft` | `ImageGenerationPage::applyWorkflowDraft` ~`:3981+`; fields `workflowDraft*` |
| **Image sampler** | Hardcoded list | `:1955–1961` euler, euler_ancestral, heun, dpmpp_2m, dpmpp_sde, uni_pc |
| **Image scheduler** | Hardcoded | `:1964–1967` normal, karras, sgm_uniform |
| **Video sampler** | Hardcoded + auto | `:1970–1975` auto, euler, euler_ancestral, dpmpp_2m, uni_pc |
| **Video scheduler** | Hardcoded + auto | `:1978–1983` auto, normal, simple, sgm_uniform, flowmatch_causvid |
| Disclosure | Advanced + mode | `samplerRow_`/`schedulerRow_` image-only; video rows video-only ~`:2750–2762` |
| **Embeddings UI** | **None** | no members/slots |
| **Upscale model UI** | **None** | preset name `"Upscale / Repair"` only tweaks steps/CFG/denoise/workflow label (`applyPreset` ~`:2889–2903`) — **not** an upscaler picker |
| Denoise (i2i) | Exists | `denoiseSpin_` / `denoiseRow_` |
| LoRA stack | Full | `LoraStackController`, `loraStack_` |
| Model stack | Checkpoint + video components | Cockpit Model tab |

**Missing vs Comfy power-user:** embedding slots, real upscale model/scale/pass, dynamic sampler lists from `/object_info`, workflow combo ≠ Flows library.

---

## 5. GenerationRequestBuilder / draft fields

`qt_ui/generation/GenerationRequestBuilder.{h,cpp}`

**Draft has:** mode, prompts, model*, workflow*, **loras**, **imageSampler/imageScheduler/videoSampler/videoScheduler**, steps/cfg/seed/wh, video fields, batch/output, inputImage, **denoiseStrength**.

**Draft does NOT have:** embeddings[], embedding names, upscale_model, upscale_scale, hires/face restore.

**Payload emit (sampler):**
- Video: `sampler`/`scheduler`/`video_*` + keeps `image_*` · `:171–182`
- Image: `sampler`/`scheduler` · `:185–188`
- LoRA array · `:142–169`
- Denoise · `:274–275` (in rest of file)

**Fill site:** `ImageGenerationPage` build-request ~`:557–653` (`draft.imageSampler = currentComboValue(samplerCombo_)` etc.).

---

## 6. Worker support (python/)

| Capability | Support level | Where |
|------------|---------------|--------|
| Samplers/schedulers | Strong | `family_operating_points.py`; adapters `video_adapters/wan_adapter.py` `CORE_SAMPLERS`/`WRAPPER_*`; LTX materialization keys; many builders pin family defaults |
| Extra samplers (res_multistep, er_sde, linear_quadratic) | Worker/family pinned | **Not** in UI combo lists → user can’t pick unless auto/operating-point |
| LoRA | Full stack | model_sources, adapters, worker |
| Embeddings (TI files) | **Classify only** | `model_classification.py` `embeddings` subdir; **no** request field / loader wiring for user embeddings |
| “embedding” in worker | SDXL **weighted prompt** helpers | `worker_service.py` ~`:3487` `get_weighted_text_embeddings_sdxl` — not TI |
| Upscale model name key | Slot name list only | `worker_service.py:3869` `upscale_model_name` among generic model slots |
| LTX spatial upscaler | Family optional component | `model_dependency_manifest.py`, `video_family_contracts.py`, template patch ~`:5779` — not UI upscale panel |
| ImageScale in graphs | Builder internals | e.g. `:6172` lanczos resize — not user upscale control |

**Gap:** UI→payload→worker path for TI embeddings and general image upscale model is **absent**; worker has hooks/classification fragments only.

---

## 7. DropTargetFrame patterns

| File | Role |
|------|------|
| `qt_ui/widgets/DropTargetFrame.{h,cpp}` | `QFrame` + `acceptDrops`; accepts **local file URLs only**; `std::function<void(const QString&)> onFileDropped` |
| I2I/I2V prompt chip | `ImageGenerationPage.cpp:898–902` → `setInputImagePath` |
| Input card | `:1016–1053` same |
| **Workflow JSON drop** | **Not implemented** on this widget |

**Workflow import path today:** Flows page button → `importWorkflowRequested` → `MainWindow::openWorkflowImportDialog` (`WorkflowImportDialog` + QProcess `worker_client.py` `import_workflow`) — file picker, not drag-drop.

**To add workflow JSON drop:** reuse `DropTargetFrame` with filter on `.json` in callback; route to import or `openWorkflowDraft` parser; or specialize `DropTargetFrame` with mime/extension predicate (currently none).

---

## 8. Prioritized implementation order + file list

### P0 — Shell chrome / icons (visual, low risk)
1. `qt_ui/shell/ShellNavigationController.{h,cpp}` — optional `icon` on `RailButtonSpec`
2. `qt_ui/MainWindow.cpp` — `createRailButton` / `createSideRail`
3. `qt_ui/ThemeManager.cpp` — rail button icon QSS
4. Wire `qt_ui/icons/*.svg` (CMake/runtime copy if needed)

### P1 — Models filters (product library)
1. `qt_ui/assets/ModelCardModel.{h,cpp}` — `ModelCardFilterProxy::setTypes/setFamilies` (or single enum filter)
2. `qt_ui/ModelManagerPage.{h,cpp}` — Type/Family combos or chips; enrich `detectType` for **Embedding** (`embeddings/` path)
3. Optional: `python/model_classification.py` + inventory path so type/family match worker
4. `MainWindow::sendModelToGeneration` only if new types become actionable

### P2 — Generation knobs (sampler/scheduler completeness)
1. `qt_ui/ImageGenerationPage.cpp` — expand `samplerCombo_` / `schedulerCombo_` / video lists (`res_multistep`, `er_sde`, `linear_quadratic`, `simple` on image side, etc.)
2. Longer-term: populate from Comfy `object_info` (new worker cmd + UI fill) — touch `worker_service.py` + page refresh
3. `GenerationRequestBuilder` already carries strings — **likely no draft schema change** for more names

### P3 — Embeddings + upscale (full stack)
1. Draft + builder: `GenerationRequestBuilder.h` fields + `GenerationRequestBuilder.cpp` payload keys  
2. UI: `ImageGenerationPage` slots (embedding multi-select via `scanCatalog(..., "embeddings")`; upscale model via `upscale_models`)  
3. Worker: load TI / UpscaleModelLoader (or graph nodes) in image builders — `worker_service.py` + any `comfy_slot_mapper.py`  
4. Models send-to for Embedding/Upscaler types

### P4 — Real workflow binding on cockpit
1. Replace cosmetic `workflowCombo_` items with imported profiles **or** keep combo cosmetic and surface binding only via Flows  
2. Optional: drop-target on cockpit/Flows for JSON → `openWorkflowImportDialog` / draft open  
3. Files: `ImageGenerationPage.cpp`, `WorkflowLibraryPage.cpp`, `MainWindow::{openWorkflowImportDialog,openWorkflowDraft}`, maybe `DropTargetFrame`

### P5 — Inspire product surface
1. New page class (replace `ModePage` at `MainWindow.cpp:1070`)  
2. Unhide: `ShellNavigationController.cpp` `kV1HiddenModes`  
3. Palette `nav.inspiration` in `MainWindow.cpp` ~`:3687`  
4. Send-to Home/T2I wiring  
5. Keep `ModePage` for other stubs if any

---

## Quick symbol index

```
createSideRail              MainWindow.cpp:982
createRailButton            MainWindow.cpp:413
railButtonSpecs             ShellNavigationController.cpp:25
isModeHidden / kV1HiddenModes  ShellNavigationController.cpp:9–22
inspirationPage_            MainWindow.h:263 · buildPages:1070
ModePage                    qt_ui/ModePage.{h,cpp}
ModelManagerPage            qt_ui/ModelManagerPage.*
ModelCardFilterProxy        assets/ModelCardModel.*
AssetCatalogScanner         assets/AssetCatalogScanner.*
ImageGenerationPage         qt_ui/ImageGenerationPage.*
GenerationRequestBuilder    generation/GenerationRequestBuilder.*
DropTargetFrame             widgets/DropTargetFrame.*
sendModelToGeneration       MainWindow.cpp:4547
openWorkflowDraft           MainWindow.cpp ~openWorkflowDraft
SVG icons (unwired)         qt_ui/icons/*.svg
```