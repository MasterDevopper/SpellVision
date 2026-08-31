# 40 — Comic page → video (v2)

**Status:** **Banked v2.0.** Not a now task. Not a v1 ship gate.  
**Owner (2026-08-17):** Comic Studio is the home. Upload a comic → produce per-panel / per-page videos.  
**Do not implement** until v2 is opened.

v1 Comic stays: script → beats → T2I panels → `page.png` + manifest.

---

## Intent

User uploads a comic (page or panel stills). Comic Studio crops/segments, then I2V (Wan production family) emits short clips and can stitch. Personal craft surface — not an official-show continuation factory.

## v1 vs v2

| | v1 (now) | v2 (this doc) |
|--|----------|----------------|
| Input | Script + generate panels | **Upload** existing page/panels |
| Output | Still page composite | **Video clips** (+ optional stitch) |
| Motion | None | I2V per panel; bubbles/grids are known failure modes |

## Honest constraints (do not greenwash later)

- One **full-bleed** panel works; a **grid page** must be cropped first
- Speech bubbles / SFX / screentone will warp
- Clips are **seconds**, not chapters
- Source must be **user-owned / user-made**. Do not fetch licensed books

## Likely slices when v2 opens (not scheduled)

1. Upload + panel crop (manual first)
2. Per-panel I2V handoff to existing Wan i2v
3. Optional concat
4. Only then: auto panel detect / bubble strip

## Related

- `29_character_comic_studios.md` — current Comic scope
- I2V rail already exists; this is Comic **ingest + batch**, not a new family
