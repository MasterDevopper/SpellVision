---
title: Theme System ArcaneGlass
type: system
status: implemented
sources:
  - qt_ui/ThemeManager.*
  - qt_ui/DashboardGlassPanel.*
  - docs/design/16_theme_token_reference.md
  - docs/design/ArcaneGlass_token_spec.md
updated: 2026-07-25
---

# Theme System (ArcaneGlass)

## Tokens

`ThemeManager` exposes Color / Spacing / Type / Chrome enums. Spacing: snap off-scale literals to tokens; **literal zero stays zero**.

## Glass

`DashboardGlassPanel::paintEvent` stack (shadow → GlassFill mix → specular → accent glow → vignette → dual rim). Painted glass, not DWM acrylic.

## Presets

Arcane Glass, Obsidian Studio, Neon Forge, Ivory Holograph (+ others). **ArcaneGlass is north-star skin**; default may still be another preset until showcase migration.

## QSS pitfall

Never `QString::arg` past `%9` for multi-token sheets — use `@token@` + `replace`. Shell QSS only on MainWindow.

## Related

[[UX Principles]] · [[Qt UI Shell]] · [[Known Bugs and Footguns]]
