---
title: Build and Verify Commands
type: planning
updated: 2026-07-25
---

# Build and Verify Commands

Canonical ops live in [[Dev Environment]]. Short list:

```powershell
Stop-Process -Name SpellVision -Force -ErrorAction SilentlyContinue
.\scripts\dev\run_ui.ps1          # build + backend + Comfy + UI
.\scripts\dev\rebuild_ui.ps1
.\scripts\dev\start_comfy.ps1
.\scripts\dev\start_backend.ps1
```

```bash
# pytest — force project venv on Windows/Hermes
export PATH="$(pwd)/.venv/Scripts:$PATH"
export VIRTUAL_ENV="$(pwd)/.venv"
export PYTHONNOUSERSITE=1
unset PYTHONPATH
.venv/Scripts/python.exe -m pytest tests/ -q
```

## Related

[[Dev Environment]] · [[Known Bugs and Footguns]]
