# SpellVision Wan 2.2 Stack / Metadata / Video Preview Fix

This bundle contains the fixed UI files plus a safe worker patcher.

## Why the worker is a patcher instead of a replacement file

The current worker uploaded through the conversation contains the native video functions (`run_native_video`, `run_native_split_stack_video`, and the Wan prompt builders), but the sandbox copy available on disk resolved to an older image/comfy-only worker. Replacing your local worker from that disk copy would silently remove the video path.

So the safe route is:

1. Replace the C++/Qt files from this bundle directly.
2. Run the Python patcher against your actual local `python/worker_service.py`.

The patcher refuses to run unless it detects the native video functions, so it will not downgrade your worker.

## Files to replace

Copy these into your project:

```text
CMakeLists.txt
qt_ui/ImageGenerationPage.h
qt_ui/ImageGenerationPage.cpp
qt_ui/MainWindow.h
qt_ui/MainWindow.cpp
qt_ui/QueueManager.h
qt_ui/QueueManager.cpp
qt_ui/QueueTableModel.h
qt_ui/QueueTableModel.cpp
python/worker_client.py
```

Then copy this into your project root or keep it anywhere:

```text
apply_worker_service_wan_fix.py
```

## Apply the worker patch

From the SpellVision project root:

```powershell
& .\.venv\Scripts\Activate.ps1
python .\apply_worker_service_wan_fix.py .\python\worker_service.py
python -m py_compile .\python\worker_service.py
```

The script creates:

```text
python/worker_service.py.pre_wan_fix.bak
```

## Build and run

```powershell
.\scripts\dev\run_ui.ps1
```

## Expected result

Wan T2V should now require both high-noise and low-noise models, metadata should finish as `completed`, and MP4 outputs should play in the generation canvas.
