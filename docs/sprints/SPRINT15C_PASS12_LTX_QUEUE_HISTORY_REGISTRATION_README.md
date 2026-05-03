# Sprint 15C Pass 12 — LTX Queue Job Integration and History Registration

## Goal

Register completed LTX Prompt API results into stable SpellVision queue/history/result registry files.

## Builds on

Pass 11 surfaced:

- `spellvision_result`
- `queue_result_event`
- `history_record`
- `primary_output`
- `ui_outputs`

Pass 12 persists those contracts so UI layers can consume them without parsing raw Comfy history.

## Registry location

Default:

`D:\AI_ASSETS\comfy_runtime\spellvision_registry`

## Written files

- `results/ltx/<prompt_id>.json`
- `results/ltx/latest.json`
- `queue/events.jsonl`
- `history/records.jsonl`

## Updated response fields

- `result_registration`
- `registered_result`

## New read commands

- `ltx_registry_history`
- `ltx_registry_queue`

## Safety

This pass does not alter Wan routing or production queue behavior. It registers only completed LTX experimental results.
