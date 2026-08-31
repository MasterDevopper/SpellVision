---
title: Dev Environment
type: reference
status: accepted
sources:
  - CLAUDE.md §4
  - scripts/dev/*.ps1
updated: 2026-07-25
---

# Dev Environment

## Host

- Windows, PowerShell for launchers
- CMake ≥3.21, Visual Studio 17 2022 generator
- Qt 6.10.2 primary (`C:\\Qt\\6.10.2\\msvc2022_64\\`), fallbacks 6.8.2 → 6.7.3
- Python 3.12+ project `.venv`; Torch 2.10+cu128; CUDA 12.8; GPU class RTX 5090 32GB

## Ports

| Service | Default |
|---------|---------|
| Worker | `127.0.0.1:8765` |
| ComfyUI | `127.0.0.1:8188` |

## Commands

```powershell
Stop-Process -Name SpellVision -Force -ErrorAction SilentlyContinue  # before rebuild (LNK1168)
.\scripts\dev\run_ui.ps1
# switches: -NoComfy -NoBackend -FastDeploy -QtRoot
.\scripts\dev\rebuild_ui.ps1
.\scripts\dev\start_backend.ps1 / stop_backend.ps1
.\scripts\dev\start_comfy.ps1 / stop_comfy.ps1
```

## Logs

- `build/worker_service.{stdout,stderr}.log`
- `build/comfy_runtime.{stdout,stderr}.log`
- Session JSON under `build/.*.session.json`

## Settings

QSettings org=`DarkDuck`, app=`SpellVision`.

## Env vars (observed)

`SPELLVISION_COMFY_PYTHON`, `SPELLVISION_WORKER_HOST`, `SPELLVISION_WORKER_PORT`, `SPELLVISION_COMFY_PORT`, `SPELLVISION_ROOT`, `SPELLVISION_SHOW_ALL_MODES`, `PYTHONUTF8` (Comfy).

## Related

[[ComfyUI Runtime]] · [[Build and Verify Commands]] · [[Known Bugs and Footguns]]
