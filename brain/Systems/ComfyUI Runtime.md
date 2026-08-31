---
title: ComfyUI Runtime
type: system
status: implemented
sources:
  - CLAUDE.md §4 §9
  - docs/design/25_gated_comfyui_update_plan.md
  - python/comfy_bootstrap.py
updated: 2026-07-25
---

# ComfyUI Runtime

## Live vs rollback (resolved 2026-07-17)

| Role | Path |
|------|------|
| **LIVE** | `C:\\sv_comfynext\\ComfyUI` (core ~2026-07-10), isolated venv `C:\\sv_comfynext\\.venv` |
| **ROLLBACK** | `D:\\AI_ASSETS\\comfy_runtime\\ComfyUI` (May core) + backup under `F:\\comfy_backup\\…` |
| Models/assets | **`D:/AI_ASSETS/models`** (shared via `extra_model_paths.yaml`) |
| Imported workflows | `<projectRoot>/runtime/imported_workflows` (project-relative, by design) |

## Process

- Port `:8188`; health `GET /system_stats`; ~90s startup timeout
- Launchers: `scripts/dev/start_comfy.ps1`, `run_ui.ps1`
- **PYTHONUTF8=1 required** on Jul-core or RES4LYF can crash stderr logging
- Kornia **pinned 0.8.2** in Comfy venv; sageattention/triton-windows present
- Worker stays on **project** `.venv` — venvs decoupled; HTTP-bridged

## Drift

`runtime_paths.py:default_comfy_root()` (`runtime/comfy/ComfyUI`) is unused drift — do not treat as live.

## Related

[[Dev Environment]] · [[Native Comfy Template Pattern]] · [[ADR-004 Asset and Comfy roots]]
