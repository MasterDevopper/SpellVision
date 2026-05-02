# Sprint 15C Pass 10 — LTX Submission Result Polling and SpellVision Metadata Capture

## Goal

Extend the gated LTX Prompt API route so it can wait for Comfy completion, collect output paths, and write SpellVision metadata sidecars.

## Existing command

`ltx_prompt_api_gated_submission`

## New request flags

- `wait_for_result=true`
- `capture_metadata=true`
- `poll_timeout_seconds=900`
- `poll_interval_seconds=5`

## Behavior

The route still defaults to dry-run mode. Live submission still requires:

- `submit_to_comfy=true`
- `dry_run=false`

Result polling only happens when `wait_for_result=true`.

## Captured result fields

- `prompt_id`
- `history_status`
- `outputs`
- `metadata_sidecars`
- `model_stack`
- `result_polling`

## Sidecar naming

For each output file, SpellVision writes:

`<output filename>.spellvision.json`

Example:

`output_F_00003_.mp4.spellvision.json`

## Safety

This remains experimental LTX routing and does not change Wan or production queue behavior.
