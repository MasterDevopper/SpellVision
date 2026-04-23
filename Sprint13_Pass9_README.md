# Sprint 13 Pass 9 — True Background Refresh for Workflows and Models

This pass converts **manual refresh** on the Workflows and Models pages into true background refresh.

## What changes

### Models page
- `Refresh Models` now runs in the background using `QtConcurrent`.
- The page remains responsive while the inventory scan runs.
- Cached entries continue to show until the new scan completes.
- The button text changes to `Refreshing...` while work is in progress.

### Workflows page
- `Refresh Library` now runs in the background using `QtConcurrent`.
- The page remains responsive while imported workflows are rescanned.
- Cached entries remain visible until the refreshed snapshot is ready.
- The button text changes to `Refreshing...` while work is in progress.

## Notes

This pass keeps the existing cache-first behavior from Pass 8:
- warm cache on setup
- nonblocking page open
- disk cache reuse when available

It only changes the **explicit refresh path** so clicking refresh no longer stalls the UI.

## Apply

```powershell
cd C:\Users\xXste\Code_Projects\SpellVision

$bundle = "$env:USERPROFILE\Downloads\spellvision_sprint13_pass9_cache_activation_bundle.zip"
$extract = "$env:TEMP\spellvision_sprint13_pass9_cache_activation"

if (Test-Path $extract) {
    Remove-Item $extract -Recurse -Force
}

Expand-Archive -Path $bundle -DestinationPath $extract -Force

Copy-Item "$extract\qt_ui\WorkflowLibraryPage.h" .\qt_ui\WorkflowLibraryPage.h -Force
Copy-Item "$extract\qt_ui\WorkflowLibraryPage.cpp" .\qt_ui\WorkflowLibraryPage.cpp -Force
Copy-Item "$extract\qt_ui\ModelManagerPage.h" .\qt_ui\ModelManagerPage.h -Force
Copy-Item "$extract\qt_ui\ModelManagerPage.cpp" .\qt_ui\ModelManagerPage.cpp -Force
Copy-Item "$extract\apply_sprint13_pass9_background_refresh.py" .\apply_sprint13_pass9_background_refresh.py -Force
Copy-Item "$extract\Sprint13_Pass9_README.md" .\Sprint13_Pass9_README.md -Force

& .\.venv\Scripts\python.exe .\apply_sprint13_pass9_background_refresh.py .

.\scripts\dev\run_ui.ps1
```
