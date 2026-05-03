# Sprint 15C Pass 13 — LTX UI Queue/History Consumption Contract

## Goal

Expose completed LTX registry records as a Qt-friendly worker payload.

## New command

`ltx_ui_queue_history_contract`

Aliases:

- `ltx_ui_registry_snapshot`
- `ltx_ui_results_contract`
- `video_family_ltx_ui_contract`

## Response type

`spellvision_ltx_ui_queue_history_contract`

## Main response fields

- `queue_items`
- `history_items`
- `latest_queue_item`
- `latest_history_item`
- `queue_count`
- `history_count`
- `ui_contract`

## Why this pass exists

The UI should consume compact, stable objects instead of raw Comfy history or raw registry files.

## Intended Qt consumers

- `QueueManager`
- `HistoryPage`
- future video result detail/preview pane

## Not included yet

This pass does not directly modify Qt widgets. The next pass should wire these fields into Queue/History UI models.
