# Sprint 13 Pass 5 — Startup Warm Cache + Stale-Result Caching for Managers

## What this pass does

This pass moves manager detection off the **Manage** click path.

New behavior:

- App opens to Home normally.
- After startup, Managers begins a background warm-cache request.
- Manage page uses the last cached result immediately.
- If cached results are stale, Manage shows them first and refreshes in the background.
- Clicking **Manage** no longer initiates the expensive scan by itself.

## Scope

This pass implements **in-memory** warm cache / stale-result reuse for the current app session.

It does **not** yet persist the cache to disk across app restarts. That can be a later pass if you want it.

## Apply

```powershell
cd C:\Users\xXste\Code_Projects\SpellVision

$bundle = "$env:USERPROFILE\Downloads\spellvision_sprint13_pass5_manager_warm_cache_patch.zip"
$extract = "$env:TEMP\spellvision_sprint13_pass5_manager_warm_cache"

if (Test-Path $extract) {
    Remove-Item $extract -Recurse -Force
}

Expand-Archive -Path $bundle -DestinationPath $extract -Force

Copy-Item "$extract\apply_sprint13_pass5_manager_warm_cache.py" .\apply_sprint13_pass5_manager_warm_cache.py -Force
Copy-Item "$extract\Sprint13_Pass5_Manager_Warm_Cache_README.md" .\Sprint13_Pass5_Manager_Warm_Cache_README.md -Force

& .\.venv\Scripts\python.exe .\apply_sprint13_pass5_manager_warm_cache.py .

.\scripts\dev\run_ui.ps1
```

## Expected result

- Home loads normally.
- About 1.5 seconds after startup, manager warmup begins in the background.
- Opening **Manage** later should show already-populated data or cached stale data immediately.
- If cache is stale, a background refresh runs while old results remain visible.

## Next likely pass

- Disk-persisted manager cache
- Shared warm-cache service for Models / Workflows / Downloads / History
- Background object_info caching
