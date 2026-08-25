# 35 — Owner fix wave (Character / Video / Gen3D)

**Date:** 2026-07-25  
**Build:** Debug green · pytest non-smoke green

## Character Studio
| Issue | Fix |
|-------|-----|
| Preview not populating after gen | `syncStudioPreviewsFromQueue` now matches `output_prefix` + prefers jobs finished after submit time (no stale steal) |
| Small preview | Load path normalize + larger target floor; rescale on resize |
| Body suits every gen | Concept packs: bare skin / undergarments; negatives for bodysuit/catsuit/unitard |
| House LoRA checkbox with no way to set | Advanced: **Choose house LoRA…** + persist path; applied when checked |
| Reference sticks too hard vs pose | I2I denoise default **0.62** (Reference freedom); pose directive prepended; `ipadapter_weight` payload for future node |

## Video
| Issue | Fix |
|-------|-----|
| Over-engineered / LTX disjoint | LTX Prompt-API panel **hidden** from primary path (native LTX); components stay on shared Model stack |
| Auto-pop hidden in Simple | Video Components **visible in Simple** |
| Fake workflow preset | Combo hidden; real drop/load remains |
| Optimal split/shift | `applyOptimalVideoSamplingDefaults()` on family change: WAN 14/14 split auto shift 5.0; LTX 30 steps CFG 3.5 — Advanced still editable |

## Gen3D
| Issue | Fix |
|-------|-----|
| External process crashed host | **QProcess spike path removed** |
| Trellis not selectable / multi-view | Backend combo Pixal3D / TRELLIS.2; TRELLIS shows multi-view angle slots (front/back/L/R/¾/top) wired as `multi_view_images` + `comfy_slot` |
| Comfy-only | Generate → worker `i23d` enqueue; requires Comfy online + workflow binding; honest error if missing nodes/workflow |

## Worker
- `i23d`/`t23d`/`gen3d` admitted in enqueue + dispatch
- Without workflow binding → clear RuntimeError (no external CLI)

## Smoke
1. Char: generate → image appears large without second run
2. Char Advanced: house LoRA pick; ref image + raise denoise for pose freedom  
3. T2V/I2V: family Auto/Wan/LTX; components visible Simple; no LTX API clutter
4. Gen3D: Trellis2 multi-view UI; Generate refuses without Comfy; no system-wide spike process
