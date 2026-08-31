# 32 — Showcase shell redesign (Linear density × ArcaneGlass)

**Status:** Code pass (2026-07-25) — ThemeManager choke-point rewrite  
**Mode:** Operate (product UI)  
**North star:** Linear density / precision on **kept ArcaneGlass** palette + glow progress

## Decision (ponytail)

Do **not** rewrite every page. Elevate `ThemeManager::{shell,imageGeneration}StyleSheet`,
type weights, radii, rail tiles, and glass defaults so **all surfaces inherit** the look.

## What changed

| Layer | Change |
|-------|--------|
| Type weights | 800→700 display/title; 700→600 label/caption/heading — no shout |
| Radii | Card 14→10, control 9→6 (Linear instrument) |
| Shell buttons | Quiet `rgba(255,255,255,0.03)` glass — not violet gradients |
| Generate CTA | Still sole chromatic control (violet gradient); radius 8; weight 700 |
| Side rail | 8px radius tiles, white/violet wash checked state, 2px left accent |
| Title bar | 6–8px controls; search pill 8px |
| Progress bar | 6px track, glow chunk kept |
| Glass panel default | radius 20→12, glow 1.0→0.85 |
| Rail buttons | 56×44 tiles |

## Preserved

- ArcaneGlass hex roles (violet hero, cyan = Success only)
- Glow progress bar effect
- Simple/Advanced, shell architecture, page structure

## Owner smoke

1. Full / half / restore: cockpit Generate still reads as hero
2. Rail active state legible, not blob
3. Status bar no pipes, Model/LoRA expandable
4. Content pages (History, Concept, Character) feel denser without re-skin fight
5. No stylesheet parse spam

## Pitfall — Qt multi-arg `QString::arg` is sequential by lowest `%N`

If a stylesheet uses multi-arg `.arg(a1, a2, … a62)` and you **delete mid placeholders**
(`%30`, `%44`…), Qt still walks args in order into the **lowest remaining** `%N`.
All later colors shift → broken rail, invisible buttons, Grade-F purple void.

**Rule:** never remove a `%N` from a multi-arg sheet without removing/reordering the
matching `.arg` value. Prefer quieter *values* over dropping slots. Verify with a
placeholder occupancy check before shipping ThemeManager QSS edits.

## Status

- **2026-07-25 F-grade incident:** showcase pass dropped shell `%30–34` and rail `%44–52`
  (and IGP `%20/21/24`). Restored placeholders; quiet density kept via lower arg alphas.
- Build after fix must show full rail (Home→…→Prefs) on dark ArcaneGlass, not lavender void.