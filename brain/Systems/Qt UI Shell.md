---
title: Qt UI Shell
type: system
status: implemented
sources:
  - qt_ui/MainWindow.*
  - qt_ui/shell/
  - CLAUDE.md §2 §6
updated: 2026-07-25
---

# Qt UI Shell

## Shape

VSCode-style desktop shell:

- Custom title bar (`CustomTitleBar`)
- Left activity rail (`ShellNavigationController`)
- Central page stack (`MainWindow::buildPages` / `switchToMode`)
- Bottom telemetry (`BottomTelemetryPresenter` / themed status strip)
- Command palette (`CommandPaletteDialog`)

## Rail

Flat entries (order evolves): Home, Chain, T2I, I2I, T2V, I2V, Flows, History, Inspire, Models, Prefs (+ Create studios when wired). Some modes nav-gated via `kV1HiddenModes` / `SPELLVISION_SHOW_ALL_MODES=1` (Chain/Inspire pattern).

## Page inventory (high level)

| Page | Status notes |
|------|----------------|
| Home / HomeDashboard | Outputs gallery; empty gallery ≠ no files if sidecars missing |
| ImageGenerationPage | T2I/I2I cockpit |
| VideoGenerationPage | T2V/I2V cockpit |
| ModelManagerPage | Stage-1 inventory browser (wired) |
| WorkflowLibraryPage | Import + readiness |
| SettingsPage | Theme, defaults, disclosure |
| CharacterStudioPage / ComicStudioPage | In tree under `qt_ui/studios/` |
| Chain studio (`qt_ui/chain/`) | Engine proven; may be nav-gated |
| ManagerPage / DatasetGenerationPage | Exist; historically under-wired |
| Inspire | Often ModePage stub |

## Theming

All chrome via `ThemeManager` tokens. Content pages own dedicated QSS — **never** apply `shellStyleSheet()` to nested pages.

## Related

[[Generation Cockpit]] · [[Theme System ArcaneGlass]] · [[Character and Comic Studios]]
