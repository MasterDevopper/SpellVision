---
title: Known Bugs and Footguns
type: reference
status: living
updated: 2026-07-25
---

# Known Bugs and Footguns

| Item | Detail |
|------|--------|
| QUEUED→COMPLETED | Silent fail; need STARTING→RUNNING→COMPLETED |
| logging.info | Invisible (root WARNING) |
| LNK1168 | Kill SpellVision before rebuild |
| QString::arg %10+ | Breaks QSS; use @token@ replace |
| shellStyleSheet on content pages | Parse spam + flat chrome |
| Inspector readiness | Must manually sync label |
| Stale I2I/I2V paths | Clear with setInputImagePath empty |
| IMG stub on T2I/T2V | Forbidden |
| Wan VAE mismatch | 2.1 needs wan_2.1_vae not 2.2 48-ch |
| fp32 checkpoints | Cast before device; shared weights |
| Hermes pytest | Force project venv or Pillow breaks |
| Half-screen | Functional parity required |
| object_info resets | Retry + Connection close |

## Related

[[Job Lifecycle Contract]] · [[Theme System ArcaneGlass]] · [[Dev Environment]]
