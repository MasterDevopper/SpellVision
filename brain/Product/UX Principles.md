---
title: UX Principles
type: product
status: accepted
sources:
  - CLAUDE.md §2
  - docs/design/13_simple_advanced_disclosure_phase7.md
  - docs/design/ArcaneGlass_token_spec.md
updated: 2026-07-25
---

# UX Principles (non-negotiable)

## Progressive disclosure — global Simple / Advanced

- One app-wide concept — not per-feature reinventions.
- **Simple** = intent (Portrait/Landscape, quality presets); hide pixel math, schedulers, CFG, nodes.
- **Advanced** = raw knobs.
- Toggle per-surface; default in Settings.
- **Rule: Advanced reveals in place. Never relocates controls to another screen.** Muscle memory survives upgrade.

## Scrolling discipline

| Surface | Rule |
|---------|------|
| Generation cockpit | Fits viewport — **no scroll**. Tabbed inspector (Prompt pinned + Model/Sampling/Output/Advanced stack). |
| Content surfaces | **Exactly one** scroll region (library, gallery, history, datasets). Never nested. |
| Studio side rails | Body in `QScrollArea`; Advanced must remain reachable at half-screen. |

## Design language

- Skeleton: **VSCode** — custom title bar, left activity rail, high density that breathes.
- Skin: **ArcaneGlass** via `ThemeManager`. Brand: metallic-framed violet arcane-eye.
- One hero accent (violet eye-glow); platinum/steel hairlines; cyan = **semantic ready/online only**.
- Owner visual QA is harsh: token polish alone is a C. Instrument quality > half-themed chrome.

## Responsive parity

Fullscreen-only polish is not showcase. Half-screen + default restore must keep **same functionality** (scroll OK; clip/hide not OK). See skill `spellvision-qt-studio-surfaces` + [[Theme System ArcaneGlass]].

## Related

[[Audience and Shipping Bar]] · [[Generation Cockpit]] · [[Theme System ArcaneGlass]]

In-repo cleanup map: `docs/design/30_responsive_layout_final_cleanup.md`  
Hermes skills: `spellvision` · `spellvision-qt-studio-surfaces`
