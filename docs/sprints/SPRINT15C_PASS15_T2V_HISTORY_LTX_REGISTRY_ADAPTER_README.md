# Sprint 15C Pass 15 — T2V History Page LTX Registry Adapter

## Goal

Make the T2V History page consume completed LTX registry results.

## What changed

- `T2VHistoryPage` still reads the existing Wan/native index:
  - `runtime/history/video_history_index.json`
- It now also reads the Pass 12 LTX registry:
  - `D:\AI_ASSETS\comfy_runtime\spellvision_registry\history\records.jsonl`
- LTX records are mapped into the existing `VideoHistoryItem` structure.
- Duplicate output paths are ignored.
- History details now show LTX output path, metadata path, model summary, and contract status through the existing details panel.

## Environment overrides

The registry path can be controlled with:

- `SPELLVISION_LTX_HISTORY_RECORDS_JSONL`
- `SPELLVISION_COMFY_RUNTIME_ROOT`
- `SPELLVISION_ASSET_ROOT`

Fallback path:

`D:\AI_ASSETS\comfy_runtime\spellvision_registry\history\records.jsonl`

## Expected UI behavior

The History page should show the same completed LTX video that is already visible in Queue.
