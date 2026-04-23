# Sprint 13 Pass 4 — UI Responsiveness and Async Page Activation

## Goal

This pass removes the most visible UI freeze introduced by the Manager Foundation pass.

The problem was not video generation. It was page activation doing blocking work:

```cpp
ManagerPage::refreshStatus()
  -> sendWorkerRequest()
  -> QProcess::waitForStarted()
  -> QProcess::waitForFinished()
```

That blocked the Qt UI thread every time the Manage page was opened.

## What this patch changes

- Manager page refresh now uses async `QProcess` callbacks.
- Manager install / selected-node install / missing-video-node install / restart Comfy now run async.
- The Manage page appears immediately, then refreshes in the background.
- The Manage page only auto-refreshes the first time you open it.
- Later refreshes are manual through **Detect / Refresh**.
- Folder buttons remain usable while a manager task is running.
- The global wait cursor is removed for long manager tasks so the app does not feel frozen.

## Apply

```powershell
cd C:\Users\xXste\Code_Projects\SpellVision

Copy-Item "$env:USERPROFILE\Downloads\apply_sprint13_pass4_responsiveness.py" .\apply_sprint13_pass4_responsiveness.py -Force

& .\.venv\Scripts\python.exe .\apply_sprint13_pass4_responsiveness.py .

.\scripts\dev\run_ui.ps1
```

## Expected behavior

When you click **Manage**:

1. The page should appear immediately.
2. The log should say the manager status request started in the background.
3. The app should remain responsive while detection runs.
4. The table and labels update when the worker response returns.

## Notes

This pass focuses on the worst hitch first: Manager page activation.

The next responsiveness layer should add the same pattern to Models, Workflows, History indexing, Downloads, and any future page that performs file scanning, Python calls, Comfy `/object_info`, or network work.
