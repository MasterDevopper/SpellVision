# Character Studio + Comic Studio

**Status:** Landed in tree (UI + shell wiring + generation handoff). Build verified Debug.  
**Skills:** `spellvision` + `spellvision-qt-studio-surfaces` (responsive + QSS pitfalls).  
**Related:** `docs/design/30_responsive_layout_final_cleanup.md`, `docs/design/11d_character_creation_end_to_end_runbook.md`

## What shipped

### Character Studio (`character` rail · Ctrl+Shift+C)
Guided 9-stage pipeline from `docs/design/11d_character_creation_end_to_end_runbook.md`:

0 Concept lock → 1 Multi-view → 2 Base mesh → 3 UltraShape refine → 4 Game-ready (retopo/UV/bake) → 5 Garments → 6 Compose → 7 Hair → 8 Export

- **Concept / multi-view / garment sheets** submit through the existing T2I/I2I worker path (model pulled from the live cockpit).
- **Jarvis pack authoring** lives in Multi-view: face front/optional 3q, clothed T/A-pose front/side/back/optional 3q, piece list, and named palette. The builder hashes stills, refuses byte-dupe angles, and writes `runtime/characters/<name>/jarvis_pack/` with honest downstream-blocker metadata. See `39_character_studio_jarvis_pack_contract.md`.
- **Mesh stages** invoke SpellBound’s Pixal3D spike when present (`~/pixal3d-spike` + `pixal3d-spike` conda env + Blender). Otherwise stages stay attachable / warning-honest.
- Project state under `runtime/characters/<name>/project.json`; export writes manifest + license sidecar + copies artifacts.
- Workspace stage stack is **scrollable** at short heights; stage rail min ~180px.

### Comic Studio (`comic` rail · Ctrl+Shift+M)
- Layout presets: 2×2, 3-strip, manga 6-up, splash+3, widescreen 4, 9-grid.
- Script → split beats → per-panel prompts with style scaffold + character lock + camera.
- Generate panel / generate-all (queues incomplete panels via T2I).
- Page composite export (`runtime/comics/<name>/export/page.png` + manifest).
- Simple/Advanced disclosure (sampling knobs revealed **in place**).
- **Left + right columns scroll** (`QScrollArea#ComicSideScroll`). Advanced Sampling stays reachable when Advanced is on at half-height.
- Splitter `reflowForWidth` at narrow widths; stacked Advanced fields (not QFormLayout alone).
- Theme: `@token@` replace only — never `QString::arg` past `%9` (live purple-panel incident).

### Glass depth
`DashboardGlassPanel` paint stack: drop shadow, glass-fill mix, specular top wash, dual-edge platinum rim, stronger hero glow — `GlassFill` / `GlassHighlight` tokens.

## Wiring
- `ShellNavigationController` rail + page context
- `MainWindow::buildPages` + command palette + details dock
- `submitStudioGenerationRequest` / `syncStudioPreviewsFromQueue`
- CMake sources under `qt_ui/studios/`

## Still maturing (honest scope)
| Area | State |
|------|--------|
| T2I/I2I/T2V/I2V/LTX/Wan | Working end-to-end (pre-existing) |
| Chain Studio | Built; hidden by v1 nav gate |
| Character mesh auto-run | Depends on external Pixal3D env |
| Jarvis concept-to-style cook | Pack authoring works; VL classification, per-piece clothes mesh reconstruction, Wrought transfer, bind/cook, Stage proof, and owner-eye remain downstream |
| Full garment drape / hair sim / ARKit | Authored gates + docs; not full backends |
| Comic multi-panel auto-queue | Generates one incomplete panel per click (re-run for next) |
| **Comic upload → video** | **v2.0** — `40_comic_page_to_video_v2.md`. Not now. |
| Inspire / Dataset pages | Still stub / orphan |
| Installer / first-run wizard | Arc 3 backlog |
| True backdrop blur (DWM acrylic) | Not used — painted glass; optional next |
| Owner showcase grade | C+ path; S requires half-screen + restore parity on all gen surfaces |

## How to try
```powershell
.\scripts\dev\run_ui.ps1
# Rail: Char · Comic
# Or command palette: "Character Studio" / "Comic Studio"
# QA: half-screen + Advanced ON on Comic — scroll to Sampling fields
```
