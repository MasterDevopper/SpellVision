# Sprint 13 Pass 2 — Video Acceleration with ComfyUI-TeaCache

This pass adds an optional TeaCache acceleration layer for native video generation.

## What it changes

- Adds `ComfyUI-TeaCache` to `python/starter_node_catalog.json`.
- Adds T2V Advanced controls:
  - Enable TeaCache
  - TeaCache profile: Off / Safe / Balanced / Fast / Custom
  - Cache model type
  - `rel_l1_thresh`
  - `start_percent`
  - `end_percent`
  - cache device: CPU / CUDA
- Sends TeaCache settings in the generation payload.
- Saves TeaCache settings into mode-segregated T2V recipes.
- Adds TeaCache state to Asset Intelligence.
- Adds backend TeaCache insertion as a post-process on generated native Wan/Video prompt graphs.
- Writes TeaCache state into generation metadata.

## Safety behavior

TeaCache is optional. If the TeaCache node is not present in ComfyUI `/object_info`, SpellVision generates normally and writes a `teacache_warning` in metadata.

## Apply

From the SpellVision project root:

```powershell
cd C:\Users\xXste\Code_Projects\SpellVision

Copy-Item "$env:USERPROFILE\Downloads\apply_sprint13_pass2_teacache.py" .\apply_sprint13_pass2_teacache.py -Force

& .\.venv\Scripts\Activate.ps1
python .\apply_sprint13_pass2_teacache.py .

python -m py_compile .\python\worker_service.py
python -m py_compile .\python\worker_client.py
```

Then rebuild/run:

```powershell
.\scripts\dev\run_ui.ps1
```

## Install TeaCache node

Use ComfyUI Manager and search for:

```text
ComfyUI-TeaCache
```

Or clone it manually into ComfyUI custom nodes:

```powershell
cd D:\AI_ASSETS\comfy_runtime\ComfyUI\custom_nodes
git clone https://github.com/welltop-cn/ComfyUI-TeaCache.git
cd .\ComfyUI-TeaCache
& C:\Users\xXste\Code_Projects\SpellVision\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Restart ComfyUI after install.

## Recommended first test

Keep your known-working T2V settings and set:

```text
TeaCache: Enabled
Profile: Safe
Cache Type: Wan2.1 T2V 14B / Wan2.2 closest
Cache L1: 0.14
Cache Start: 0.00
Cache End: 1.00
Cache Dev: CPU
```

If quality looks stable, try Balanced:

```text
Profile: Balanced
Cache L1: 0.20
Cache Dev: CUDA if you have spare VRAM, otherwise CPU
```

## Verify prompt insertion

After a run, inspect the latest native prompt:

```powershell
$latestPrompt = Get-ChildItem "D:\AI_ASSETS\comfy_runtime\ComfyUI\output" -Filter "*native_prompt_api.json" |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1

$p = Get-Content $latestPrompt.FullName | ConvertFrom-Json
$p.PSObject.Properties |
  Where-Object { $_.Value.class_type -like "*TeaCache*" } |
  ForEach-Object { $_.Name; $_.Value | ConvertTo-Json -Depth 10 }
```

You should see one TeaCache node per native diffusion model branch when enabled and installed.
