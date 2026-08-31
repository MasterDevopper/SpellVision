---
title: ADR-004 Asset and Comfy roots
status: accepted
updated: 2026-07-25
---

# ADR-004 — Asset and Comfy roots

## Decision

| Resource | Canonical |
|----------|-----------|
| Models/assets | `D:/AI_ASSETS/` (`models` under it) |
| LIVE Comfy | `C:\\sv_comfynext\\ComfyUI` + isolated venv |
| Worker Python | Project `.venv` |
| Imported workflows | `<repo>/runtime/imported_workflows` |

`.env` / `runtime_paths.py` values that disagree are **drift to reconcile**, not alternate truths — except deliberate project-relative workflow library.

## Related

[[ComfyUI Runtime]] · [[Dev Environment]] · [[Contradiction Ledger]]
