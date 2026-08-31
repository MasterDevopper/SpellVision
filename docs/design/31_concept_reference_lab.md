# Concept Reference Lab

**Status:** Landed (UI + shell + T2I/I2I handoff)  
**Rail:** Create → **Concept** (`concept`, Ctrl+Shift+R)  
**Purpose:** Produce concept plates that multi-view / TRELLIS-class meshers **accept and adhere to** — correct light, empty backgrounds, locked identity across angles.

## Why this exists

Doc 11d concept lock fails when plates have cinematic light, busy environments, or inconsistent angles. This page is a **prompt-pack cockpit** that always injects the adherence scaffolds.

## Asset type buttons

| Type | Intent |
|------|--------|
| **Character body** | Isolated full-body figure for basemesh (minimal clothing / form suit) |
| **Clothing** | Separable garment product sheet (no full character portrait) |
| **Building** | Single structure massing plate |
| **Prop** | Single weapon/tool/object product plate |

Each type presses in a **positive + negative scaffold** tuned for that class.

## SFW / NSFW (character body)

| Mode | Positive intent | Negative intent |
|------|-----------------|-----------------|
| **SFW body** | Anatomically correct proportions + massing; **smooth genital region without genitals** — game-safe under clothing | Explicit genitals, porn framing, NSFW pose |
| **NSFW anatomy** | Full anatomical fidelity when unclothed detail is required | Censor bars / forced Barbie crotch when detail was requested |

Clothing / building / prop: content chips disabled (no-op packs).

## View chips

- Hero front (lock)
- Turnaround sheet
- Front / back / left / right / 3-4 angle singles

Turnaround forces multi-panel orthographic sheet language. Locked hero → further angles prefer **I2I** from the locked path.

## Always-on scaffolds (all types)

- Even soft studio light (no dramatic rim / cinematic contrast)
- Pure solid empty background (no room / landscape)
- Single identity; no text/watermark/UI
- Full subject in frame with margin

## Actions

- **Apply pack → prompts** — fills positive/negative editors
- **Generate reference** — T2I (or I2I if hero locked)
- **Generate turnaround sheet**
- **Lock as hero reference**
- **Send to Character Studio** — calls `acceptConceptReference` (locks Concept stage)
- Persist under `runtime/concept_references/<name>.json`

## Shared code

`qt_ui/studios/ConceptReferencePacks.h` — also used by Character Studio concept + multi-view payload builders.

## Try

```powershell
.\scripts\dev\run_ui.ps1
# Rail: Concept  ·  or palette "Concept Reference Lab"
```
