# Sprint 15C Pass 14 — Qt Queue/History LTX Registry Consumption

## Goal

Make the Qt shell consume the Pass 13 LTX UI contract.

## What changed

- `WorkerQueueController` now fetches `ltx_ui_queue_history_contract` after normal `queue_status`.
- The Pass 13 `queue_items` payload is converted into the existing `queue_snapshot` item shape.
- Existing `QueueManager::applyQueueSnapshot()` remains the only queue state mutation path.
- `WorkerResponseParser` recognizes `spellvision_ltx_ui_queue_history_contract`.

## Why this shape

The existing Qt queue path already uses:

- `WorkerQueueController`
- `QueueManager`
- `QueueTableModel`
- `QueueUiPresenter`

This pass avoids raw Comfy parsing and avoids direct registry-file parsing in Qt.

## Expected UI behavior

Completed LTX Prompt API outputs should appear as completed video queue rows with:

- command/task type `t2v`
- family `ltx`
- backend `comfy_prompt_api`
- output video path
- metadata sidecar path
- playback-ready summary

## History note

Pass 13 provides `history_items` in the same contract. This pass lands the queue ingestion first through the existing QueueManager path. A follow-up pass can wire `T2VHistoryPage` directly to the same worker contract or switch it to a shared history model.
