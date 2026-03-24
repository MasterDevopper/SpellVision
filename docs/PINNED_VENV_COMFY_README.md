# Managed Comfy Venv Pin Pass

This pass pins the managed Comfy runtime to the SpellVision project venv by default.

## What changed
- `comfy_bootstrap.py` now prefers:
  1. `SPELLVISION_COMFY_PYTHON`
  2. `./.venv/Scripts/python.exe` (Windows) or `./.venv/bin/python`
  3. `sys.executable`
- `comfy_runtime_manager.py` now defaults to `default_comfy_python(comfy_root)` instead of the ambient interpreter.
- `worker_service.py` now resolves managed Comfy Python the same way.

## Apply
Copy these files into your repo:
- `python/comfy_bootstrap.py`
- `python/comfy_runtime_manager.py`
- `python/worker_service.py`

Then restart SpellVision, click:
1. Stop Managed Comfy Runtime
2. Start Managed Comfy Runtime

## Verify
In PowerShell:
```powershell
$comfyPid = Get-NetTCPConnection -LocalPort 8188 -State Listen | Select-Object -ExpandProperty OwningProcess
Get-CimInstance Win32_Process -Filter "ProcessId = $comfyPid" | Select-Object ProcessId, Name, CommandLine
```

The command line should show:
`C:\Users\xXste\Code_Projects\SpellVision\.venv\Scripts\python.exe`
instead of:
`C:\Program Files\Python312\python.exe`

## Next workflow test
Once the interpreter is pinned correctly:
1. Open SpellVision
2. Refresh Workflow Profile list in the right inspector
3. Select an imported workflow profile from the dropdown instead of `Standard`
4. Generate once
5. Confirm the managed Comfy runtime stays `READY (MANAGED ...)`
6. Confirm output/metadata land in your normal history flow
