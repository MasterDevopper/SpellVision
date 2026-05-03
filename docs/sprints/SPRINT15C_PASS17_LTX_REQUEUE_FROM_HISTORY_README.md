# Sprint 15C Pass 17 — LTX Requeue From History

## Goal

Add a safe requeue-from-history bridge for completed LTX records.

## What changed

- T2V History now has a `Prepare Requeue` action.
- The action is limited to LTX registry rows.
- It writes a durable requeue draft JSON under:

`D:\AI_ASSETS\comfy_runtime\spellvision_registry\requeue\ltx`

## Why this is safe

This pass does not immediately submit another expensive video generation job. It creates a draft with:

- prompt
- model
- source output path
- source metadata path
- registry prompt id when available
- `safe_to_requeue=true`
- `submit_immediately=false`

## Future pass

A later pass can read this draft, confirm workflow/model readiness, then call the gated LTX Prompt API submission route.
