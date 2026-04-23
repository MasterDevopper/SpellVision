# Sprint 13 Pass 6 — Disk-Persisted Manager Cache

This pass extends the Manager warm-cache work so the cache survives closing and reopening SpellVision.

## Behavior

- Manager status is still preloaded in the background after startup.
- Successful manager status responses are now written to disk.
- On next app launch, SpellVision loads the last saved manager snapshot immediately.
- Opening **Manage** becomes cache-first and nonblocking:
  - shows disk cache immediately
  - treats fresh cache as done
  - treats stale cache as visible while a background refresh runs

## Cache location

Primary location:

- `QStandardPaths::AppLocalDataLocation/manager_status_cache.json`

Fallback:

- `<app folder>/runtime/cache/ui/manager_status_cache.json`

## Retention

- Fresh window: 5 minutes
- Retained for display across restarts: 7 days

## Apply

```powershell
cd C:\Users\xXste\Code_Projects\SpellVision

$bundle = "$env:USERPROFILE\Downloads\spellvision_sprint13_pass6_manager_disk_cache_patch.zip"
$extract = "$env:TEMP\spellvision_sprint13_pass6_manager_disk_cache"

if (Test-Path $extract) {
    Remove-Item $extract -Recurse -Force
}

Expand-Archive -Path $bundle -DestinationPath $extract -Force

Copy-Item "$extract\apply_sprint13_pass6_manager_disk_cache.py" .\apply_sprint13_pass6_manager_disk_cache.py -Force
Copy-Item "$extract\Sprint13_Pass6_Manager_Disk_Cache_README.md" .\Sprint13_Pass6_Manager_Disk_Cache_README.md -Force

& .\.venv\Scripts\python.exe .\apply_sprint13_pass6_manager_disk_cache.py .

.\scripts\dev\run_ui.ps1
```

## Notes

This pass only persists the **Manager status snapshot**. It does not yet persist every possible Models / Workflows / Downloads cache. The same pattern can be reused for those pages next.
