# Manager Cache Symbol Fix

This fixes the compile error:

- `g_managerStatusCacheOrigin`: undeclared identifier

It also safely repairs the related helper functions if they are missing:

- `managerStatusDisplaySource(...)`
- `managerStatusLastCheckedText()`

## Why this happened

Your Manager cache UI patches landed partially on the local file. Some code now references:

- the cache-origin global
- cache helper functions

but the corresponding symbol block did not fully insert into the anonymous namespace in `qt_ui/ManagerPage.cpp`.

## What this fix does

- Inserts `g_managerStatusCacheOrigin` next to the other cache globals if missing
- Inserts forward declarations for the cache helper functions if missing
- Inserts helper definitions if missing

## Apply

```powershell
cd C:\Users\xXste\Code_Projects\SpellVision

$bundle = "$env:USERPROFILE\Downloads\manager_cache_symbol_fix_patch.zip"
$extract = "$env:TEMP\manager_cache_symbol_fix"

if (Test-Path $extract) {
    Remove-Item $extract -Recurse -Force
}

Expand-Archive -Path $bundle -DestinationPath $extract -Force

Copy-Item "$extract\apply_manager_cache_symbol_fix.py" .\apply_manager_cache_symbol_fix.py -Force
Copy-Item "$extract\Manager_Cache_Symbol_Fix_README.md" .\Manager_Cache_Symbol_Fix_README.md -Force

& .\.venv\Scripts\python.exe .\apply_manager_cache_symbol_fix.py .

.\scripts\dev\run_ui.ps1
```
