# Sprint 13 Pass 3 — Manager Foundation + Dependency Repair Center

This pass adds the first functional Managers / Runtime page and worker commands for ComfyUI Manager and recommended video node packages.

## Added

- New `qt_ui/ManagerPage.h`
- New `qt_ui/ManagerPage.cpp`
- MainWindow route and side-rail entry for `Managers / Runtime`
- CMake registration for ManagerPage
- Worker commands:
  - `comfy_manager_status`
  - `install_comfy_manager`
  - `install_custom_node`
  - `install_recommended_video_nodes`
- Worker client support for manager response types
- Recommended-node display based on `python/starter_node_catalog.json`

## Why this pass exists

TeaCache, Wan wrappers, LTX wrappers, Hunyuan wrappers, CogVideoX wrappers, Mochi wrappers, and imported workflow repair all need one shared foundation:

1. Detect manager state.
2. Detect installed custom nodes.
3. Compare installed nodes against SpellVision's starter node catalog.
4. Install selected or missing recommended nodes.
5. Restart Comfy and verify the runtime again.

## Copy into project

From the project root:

```powershell
cd C:\Users\xXste\Code_Projects\SpellVision

$bundle = "$env:USERPROFILE\Downloads\spellvision_sprint13_pass3_manager_foundation.zip"
$extract = "$env:TEMP\spellvision_sprint13_pass3_manager_foundation"
$project = "C:\Users\xXste\Code_Projects\SpellVision"

if (Test-Path $extract) {
    Remove-Item $extract -Recurse -Force
}

Expand-Archive -Path $bundle -DestinationPath $extract -Force

Copy-Item "$extract\CMakeLists.txt" "$project\CMakeLists.txt" -Force
Copy-Item "$extract\qt_ui\*" "$project\qt_ui\" -Force
Copy-Item "$extract\python\worker_service.py" "$project\python\worker_service.py" -Force
Copy-Item "$extract\python\worker_client.py" "$project\python\worker_client.py" -Force
Copy-Item "$extract\python\starter_node_catalog.json" "$project\python\starter_node_catalog.json" -Force
Copy-Item "$extract\Sprint13_Pass3_Manager_Foundation_README.md" "$project\Sprint13_Pass3_Manager_Foundation_README.md" -Force
```

## Validate Python

```powershell
& .\.venv\Scripts\python.exe -m py_compile .\python\worker_service.py
& .\.venv\Scripts\python.exe -m py_compile .\python\worker_client.py
```

## Build and run

```powershell
.\scripts\dev\run_ui.ps1
```

Then open the new **Manage** rail item.

## Manager page actions

- **Detect / Refresh** checks Comfy root, ComfyUI Manager, runtime status, installed custom nodes, and recommended video node packages.
- **Install Manager** clones/repairs ComfyUI Manager and installs its requirements.
- **Install Selected Node** installs the selected catalog package using its preferred method.
- **Install Missing Video Nodes** installs all missing recommended video-related node packages from the catalog.
- **Restart Comfy** restarts the managed Comfy runtime after node changes.
- **Open Comfy Root** and **Open custom_nodes** open the relevant folders.

## Notes

This pass does not force TeaCache on. TeaCache remains optional and should be tested after Manager installation and object_info verification are working cleanly.
