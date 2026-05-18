# Sprint MOCKUP — Pass 1: Asset Intelligence redesign

This pass closes the largest visible gap between the live T2I/I2I/T2V/I2V page
and `spellvision_target_mockup.html`: the right-rail **Asset Intelligence**
panel.

## What's changing

Before this pass, Asset Intelligence was rendered into a single `QLabel`
(`modelsRootLabel_`, object name `AssetIntelligenceBody`) holding an HTML
`<table>` of 9–20 `key:value` rows. Dense, comprehensive, hard to scan.

After this pass, the same data is rendered as a structured surface
matching the mockup:

| Surface element                | Object name(s)                                 | Visibility    |
| ------------------------------ | ---------------------------------------------- | ------------- |
| Readiness pill                 | `AiReadinessStrip`, `AiReadinessDot`, `AiReadinessText`, `AiReadinessSub` | always        |
| Stack chip group               | `AiGroupLabel`, `AiChipsRow`, `AiChip[is="set"|"auto"]` | always        |
| Components chip group          | (same selectors, inside `AiComponentsGroupContainer`) | video modes   |
| Timing block                   | `AiTimingRow`, `AiTimingValue`, `AiTimingKey`  | video modes   |
| "Show all fields" disclosure   | `AiDetailsToggle`                              | always        |
| Legacy full HTML dump (kept)   | `AiDetailsBody` (was `AssetIntelligenceBody`)  | collapsed     |

The legacy HTML dump is **not removed** — it lives behind the
"Show all fields" disclosure, so no information surface is lost. Users
who want the dense view click the disclosure to expand it.

## Files touched

| File                              | What                                                                 |
| --------------------------------- | -------------------------------------------------------------------- |
| `qt_ui/ImageGenerationPage.h`     | adds `class QFrame;` forward decl + 19 new member pointers           |
| `qt_ui/ImageGenerationPage.cpp`   | replaces the AI section in `buildUi()` + rewrites `updateAssetIntelligenceUi()` |
| `qt_ui/ThemeManager.cpp`          | adds 18 new QSS selectors to `imageGenerationStyleSheet()` + 12 new `.arg()` color slots |

## QSS color slots

The Pass adds 12 new format args (positions 34–45) to the
`imageGenerationStyleSheet()` `.arg()` chain. All are derived from existing
theme-preset colors — nothing hardcoded:

| Slot   | Source                                       | Used for                                       |
| ------ | -------------------------------------------- | ---------------------------------------------- |
| 34, 35 | `successColor()` at 10% / 34% alpha          | Ready-state readiness pill (bg, border)        |
| 36     | `successColor().name()`                      | Ready-state dot                                |
| 37, 38 | `warningColor()` at 10% / 34% alpha          | Warn-state readiness pill                      |
| 39     | `warningColor().name()`                      | Warn-state dot                                 |
| 40, 41 | `errorColor()` at 10% / 34% alpha            | Block-state readiness pill                     |
| 42     | `errorColor().name()`                        | Block-state dot                                |
| 43, 44 | `accentColor()` at 10% / 42% alpha           | `AiChip[is="set"]` (bg, border)                |
| 45     | `accentColor().name()`                       | `AiDetailsToggle` text + chip value emphasis   |

Every preset (Arcane Glass, Obsidian Studio, **Neon Forge**,
Ivory Holograph) automatically gets a tonally-correct AI panel because
nothing hardcodes hex values — the mockup colors are what
`successColor()` / `accentColor()` etc. produce in Neon Forge.

## How to apply

```powershell
python .\apply_sprint_mockup_pass1_asset_intelligence.py
.\scripts\dev\run_ui.ps1
```

The script is idempotent — re-running prints "Already patched" for each
file. Backups are written once per file with the
`.pre_sprint_mockup_pass1.bak` suffix.

## Visual self-check after rebuild

Switch to T2V mode and verify:

1. **Readiness pill** appears at the top of the right-rail Asset
   Intelligence card with a green dot + "Ready to generate" headline.
   If no checkpoint is selected, the dot turns warning-yellow and the
   sub reads "Select a checkpoint to generate."
2. **STACK chip group** shows three chips: `Family`, `Mode`, `Primary`.
   Chips with real values render `is="set"` (accent-tinted bg, accent-
   colored value). Chips with `auto` value render `is="auto"`
   (dashed border, muted text).
3. **COMPONENTS chip group** appears only in T2V / I2V — three chips
   for Text / VAE / Vision.
4. **Timing block** (video only) shows three metric pairs over a
   top border: `81 frames | LENGTH`, `16 fps | RATE`, `5.1 s | DURATION`.
5. **"▾ Show all fields"** toggle at the bottom expands a collapsed
   `AiDetailsBody` containing the legacy HTML key:value table.

In T2I / I2I, the COMPONENTS group and timing row are hidden; the STACK
group instead shows `Checkpoint`, `Family`, `LoRAs` chips.

## What this pass does NOT touch

- Splitter sizes, column proportions — unchanged.
- The left-rail Quick Controls layout — still label-on-left rows.
  (That's Sprint MOCKUP Pass 2: mini-grid.)
- LTX Launch Options / Sampler & Scheduler card promotion — still
  inline. (That's Sprint MOCKUP Pass 3: disclosure cards.)
- Canvas card head row / empty-state stage — still single-string label.
  (That's Sprint MOCKUP Pass 4: canvas + family-card polish.)

## Rollback

Each touched file has a `.pre_sprint_mockup_pass1.bak` next to it. To
revert: replace the touched file with its backup, then delete the
backup. The patch script will then re-apply cleanly.
