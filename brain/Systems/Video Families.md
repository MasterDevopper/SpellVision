---
title: Video Families
type: system
status: implemented
sources:
  - python/video_family_contracts.py
  - python/video_adapters/
  - docs/design/26_families_done_milestone.md
  - CLAUDE.md §6
updated: 2026-07-25
---

# Video Families

## Contract table (code)

| Family | validation_status | backend_route | Tasks |
|--------|-------------------|---------------|-------|
| wan | production | native_comfy_template | t2v, i2v |
| ltx | production | native_comfy_template | t2v, i2v |
| hunyuan_video | production | native_comfy_template | t2v, i2v |
| mochi | production | native_comfy_template | t2v |
| cogvideox | detected | future_comfy_profile | — |
| workflow | configured | comfy_workflow_profile | imported graphs |

## Practical matrix (product)

| Family | T2V | I2V | License notes |
|--------|-----|-----|---------------|
| LTX-2.3 | proven native AV | proven native | permissive |
| Wan 2.x | dual-noise production | 2.1 single-model green; 2.2 dual-noise i2v tracked | permissive |
| Hunyuan | production native | **reconcile docs** — Doc 26 claims kijai-proven; contract notes CLIPVision encode block pre/post Comfy cutover | non-commercial (Tencent) |
| Mochi-1 | production | n/a (t2v-only) | Apache-2.0 |

## LTX operating points

- Default: distilled two-stage (VRAM-safer); single-stage-full opt-in
- Full model wants higher steps (25–40); CFG ~3–5
- Caps: ÷32 spatial; frames `(N×8)+1`
- LoRA opt-in (no default chel)

## Related

[[Native Comfy Template Pattern]] · [[Acceptance Evidence Ledger]] · [[Contradiction Ledger]]
