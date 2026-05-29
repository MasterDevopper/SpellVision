# Sprint 13 Pass 7 Compile Fix

This fixes the build error:

- `managerStatusDisplaySource`: identifier not found
- `managerStatusLastCheckedText`: identifier not found

## Cause

Pass 7 updated `ManagerPage.cpp` to call these helpers, but in your local file the helper insertion did not land cleanly, so the references compiled but the functions were missing.

## Apply

```powershell
cd C:\Users\xXste\Code_Projects\SpellVision

$bundle = "$env:USERPROFILE\Downloads\spellvision_sprint13_pass7_compile_fix_patch.zip"
$extract = "$env:TEMP\spellvision_sprint13_pass7_compile_fix"

if (Test-Path $extract) {
    Remove-Item $extract -Recurse -Force
}

Expand-Archive -Path $bundle -DestinationPath $extract -Force

Copy-Item "$extract\apply_sprint13_pass7_compile_fix.py" .\apply_sprint13_pass7_compile_fix.py -Force
Copy-Item "$extract\Sprint13_Pass7_Compile_Fix_README.md" .\Sprint13_Pass7_Compile_Fix_README.md -Force

& .\.venv\Scripts\python.exe .\apply_sprint13_pass7_compile_fix.py .

.\scripts\dev\run_ui.ps1
```
