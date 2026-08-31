---
title: Image Families and Memory
type: system
status: implemented
sources:
  - CLAUDE.md §6–7
  - python/memory_optimization.py
  - tests/test_worker_lora_adapters.py
  - docs/design/26_families_done_milestone.md
updated: 2026-08-17
---

# Image Families and Memory

## Families (v1.0 matrix + Krea2)

SDXL/Pony/Illustrious, Flux (t2i+i2i), PixArt-Σ, Lumina 2.0, Z-Image Turbo, Anima — render-verified on product surface per Doc 26.

**Krea2** (2026-08-17 owner law, `tests/test_krea2_family.py`):

- **Raw is the default** — 52 steps / CFG 3.5
- **Turbo is a speed lane** — 8 steps / CFG 0
- LoRAs enabled, never required
- Official base models only (raw + turbo + TE + VAE)

## VRAM / shared weights

- `build_paired_pipelines` from `memory_optimization.py` wired into `build_pipelines`
- fp32 checkpoints: CPU cast to fp16 before device move (`cast_fp32_to_fp16`)
- Shared UNet for t2i+i2i; LoRAs as **non-destructive named adapters** (`load_lora_weights` + `set_adapters`, never `fuse_lora`)
- Guarded by `tests/test_worker_lora_adapters.py` (A→B→A + no-LoRA-after-LoRA)

## Related

[[Worker Service]] · [[Model Library]] · [[Known Bugs and Footguns]]
