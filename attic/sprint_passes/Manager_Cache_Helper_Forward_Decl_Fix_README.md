# Manager Cache Helper Forward-Declaration Fix

This fixes the compile error:

- `managerStatusDisplaySource`: identifier not found
- `managerStatusLastCheckedText`: identifier not found

## Why this happened

C++ needs a function declaration before its first use.

Your Pass 7 cache UI changes introduced calls to these helper functions, but the local `ManagerPage.cpp` ended up without visible declarations before those call sites. Depending on how the earlier patch landed, the definitions may also be missing entirely.

This fixer does both:

- inserts forward declarations near the top anonymous namespace
- inserts the helper definitions into that same namespace if they are missing

## Apply

```powershell
cd C:\Users\xXste\Code_Projects\SpellVision

$bundle = "$env:USERPROFILE\Downloads\manager_cache_helper_forward_decl_fix_patch.zip"
$extract = "$env:TEMP\manager_cache_helper_forward_decl_fix"

if (Test-Path $extract) {
    Remove-Item $extract -Recurse -Force
}

Expand-Archive -Path $bundle -DestinationPath $extract -Force

Copy-Item "$extract\apply_manager_cache_helper_forward_decl_fix.py" .\apply_manager_cache_helper_forward_decl_fix.py -Force
Copy-Item "$extract\Manager_Cache_Helper_Forward_Decl_Fix_README.md" .\Manager_Cache_Helper_Forward_Decl_Fix_README.md -Force

& .\.venv\Scripts\python.exe .\apply_manager_cache_helper_forward_decl_fix.py .

.\scripts\dev\run_ui.ps1
```
