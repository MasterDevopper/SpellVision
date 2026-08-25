---
title: Planned Additions
type: planning
status: living
updated: 2026-08-24
---

# Planned Additions

Owner-locked or specified work that is **not** already product-wired. Blank is not a start.

Reconciled 2026-08-24. Surfaces that exist on the rail are **not** listed here as “to build.”

## v1 ship gates (open)

| Item | Status | Notes |
|------|--------|-------|
| License badges + soft warn | **landed** | ModelCard badge + generate soft-warn + Settings checkbox. Character stack caption 2026-08-24. Comic/Concept caption leftover |
| Wan 2.2 dual-noise **i2v** | **render-proven 2026-08-24** | Official experts. Frame-0 MAE **5.54**. Motion vs last frame MAE 32. Smoke job completed the clip; metadata re-export hole fixed (`output_media_type_for_metadata`). |
| Hunyuan i2v | **reconcile** | Doc 26 vs contract CLIPVision notes |
| Character A+B product depth | **v1 gate; UI wired, execution incomplete** | Mesh/garments/hair/beauty. Clothes-only + shrinkwrap commands exist; pack/create CLI unwired |
| Mode-aware history (#12) | **partial** | Image+video filters live; core+payload+renderer spine not rebuilt |
| Guided dependency resolver | **not built** | Doc 19; blocks first-run |
| Hybrid installer / MSI | **not built** | Doc 27 #11; top date risk |
| First-run wizard | **diagnostic only** | Doc 37 one-time check exists; not the wizard |
| Clean-machine proof | **missing** | Doc 28 unrun |
| One runtime identity | **proven 2026-08-24** | `SpellVision.exe` (no `run_ui.ps1`) started worker; typed pong `service=spellvision_worker` protocol 1 |

## v1 finish (not ship-blocking by themselves)

| Item | Status | Notes |
|------|--------|-------|
| Upscaler engine | **specified** | Doc 27 §2.1; nodes on disk |
| Palettes / glass / layout / Simple copy | **open** | Owner C+ → S |
| Half-screen parity | **partial** | Budget/scroll landed; owner-eyes matrix open |
| Models Stage-3 auto-download | **open** | Stage-1 inventory live |
| Docs refresh | **open** | CLAUDE §6, FEATURE_MATRIX, README, Full Roadmap lag code |
| Dead-code cleanup | **open** | `runtime_adapters/` unused; `VideoGenerationPage` unregistered; `ModePage` unused |

## Explicitly parked / v2

| Item | Reopen trigger |
|------|----------------|
| Comic page upload → crop → I2V → stitch | v2 — Doc 40; v1 = script → stills → `page.png` |
| Phase D native 3D (non-character) | After Phase C closed **and** Character B does not consume the slice. `Gen3DPage` stays hidden Comfy-passthrough |
| Chain Studio unhide | Recipe UX ready; engine already proven |
| Hybrid breast B1+ | Resume **only** at Character Studio — not a MorphLayer on `female.glb` |
| LLM orchestration | v2 |
| Audio depth | v2 |
| Long videos | No spec |
| `ImageGenerationPage` type-level split | After facade ceilings hold; TUs already landed |

## Not planned (do not start)

- Replacing ComfyUI with pure diffusers
- Ingesting unlicensed manga pages / episode factory
- Comic upload-to-video as v1
- Reinventing family sampler menus on the page (worker contract is SSOT)
- Krea unofficial bases as shipped defaults
- Wiring `runtime_adapters/` as a second dispatch path without deleting the live one
- Treating FEATURE_MATRIX / CLAUDE §6 as current inventory

## Related

[[Current State Ledger]] · [[v1.0 Roadmap Synthesis]] · [[Open Questions Register]] · [[Phase D 3D Plan]] · [[Character and Comic Studios]]
