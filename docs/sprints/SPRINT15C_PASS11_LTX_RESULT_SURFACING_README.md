# Sprint 15C Pass 11 — LTX Result Surfacing into Queue/History Contract

## Goal

Surface captured LTX Prompt API results as SpellVision-native queue/history/UI contracts.

## Builds on

Sprint 15C Pass 10 added:

- gated Prompt API submission
- result polling
- output path resolution
- `.spellvision.json` sidecar metadata

## New response fields

- `spellvision_result`
- `queue_result_event`
- `history_record`
- `primary_output`
- `ui_outputs`

## Contract intent

This pass does not yet insert records into the Qt History page or persistent queue store. It creates the stable payload those layers should consume in the next UI-facing pass.

## Why this matters

The UI should not parse raw Comfy history. SpellVision should consume its own normalized result objects.

## Expected status

A successful captured LTX run should return:

- `submission_status = submitted_completed_captured`
- `result_completed = true`
- `spellvision_result.completed = true`
- `spellvision_result.history_ready = true`
- `spellvision_result.preview_ready = true`
- `queue_result_event.state = completed`
- `history_record.primary_output_path` points to the primary mp4
