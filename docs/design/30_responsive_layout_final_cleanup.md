# 30 — Responsive layout final cleanup

**Status:** A- polish pass (2026-07-25 late) — owner eyes still gate S  
**Grade context:** Owner **A-**; residual is live matrix + any remaining owner nits  
**Owner surface:** generation cockpits, Comic/Character studios, History, title bar, Home, telemetry

## Code landed (B+ → S track)

### P0 cockpit / resize
- Combo `minimumContentsLength` + elide; stacked video Components (cell-wrapped visibility)
- `CockpitInspector::setWidthBudget` + content max-width
- `showEvent` + deferred reflow on generation pages
- No T2I/T2V IMG stub; readiness footer sync; stale input path clear

### P1 studios / chrome
- Comic + Character `reflowForWidth` / scroll rails
- Character: **QFormLayout removed** → stacked label-above-field
- History: **@token@ QSS** (fixed `%10` disabled-button corruption), 14px density, details pane reflow
- Title bar: search pill compresses; shortcut + layout icons hide at narrow widths
- Telemetry: adaptive chip widths; LoRA/ETA + **their separators** hide together
- Home glass radii tightened to instrument scale (hero 18 / standard 14)
- ModePage (Inspire stub): honest “Coming soon”, @token@ sheet, denser cards

### Explicitly out of scope
- Bundled Space Grotesk / Inter / JetBrains Mono (Segoe UI interim)
- True OS acrylic (painted glass only)

## Manual matrix (owner eyes) — still open

| Surface | Full | Restore | Half W | Half H |
|---|---|---|---|---|
| T2I | | | | |
| T2V | | | | |
| I2V | | | | |
| Comic Advanced ON | | | | |
| Character concept | | | | |
| History details | | | | |
| Title bar + telemetry | | | | |

Pass = no clipped controls, no missing Advanced, Generate always reachable, status bar readable, no QSS parse spam.

## Skills / authority
- `spellvision` + `spellvision-qt-studio-surfaces`
- `references/responsive-half-screen.md`, `owner-visual-qa-checklist.md`
