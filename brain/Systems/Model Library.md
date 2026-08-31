---
title: Model Library
type: system
status: partial
sources:
  - qt_ui/ModelManagerPage.*
  - docs/SPELLVISION_MODEL_MANAGER_SPEC.md
  - docs/design/22_model_library_arc.md
  - CLAUDE.md §6
updated: 2026-07-25
---

# Model Library

## Stage-1 (implemented)

`ModelManagerPage` — recursive scan of models root (`D:/AI_ASSETS/models`), tree (Name/Type/Family/Size/Status), details panel, disk cache `model_inventory_cache.json`.

Verified live historically at scale (700+ assets). Visual polish lags cockpit (pre token sweeps).

## Not yet full spec

Full `SPELLVISION_MODEL_MANAGER_SPEC.md` includes downloads, dependency health, compatibility cues — Stage 1 only. Cache root “not configured” for downloads historically.

## License surfacing

Family specs carry `commercial_use` / `license_note` — UI badge + commercial-use warning still scoped for v1.0 ([[v1.0 Roadmap Synthesis]]).

## Related

[[Image Families and Memory]] · [[Video Families]] · [[Open Questions Register]]
