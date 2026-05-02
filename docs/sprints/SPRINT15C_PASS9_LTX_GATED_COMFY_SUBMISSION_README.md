# Sprint 15C Pass 9 — LTX Prompt API Gated Comfy Submission

## Goal

Add a guarded submission route for the validated LTX Prompt API payload.

## Command

`ltx_prompt_api_gated_submission`

## Safety rules

The route only submits to ComfyUI when all conditions are true:

- Pass 8 adapter reports `safe_to_submit=true`
- no blocked submit reasons
- no unresolved roles
- Comfy runtime is running
- Comfy runtime is healthy
- Comfy endpoint is alive
- Prompt API preview exists
- caller explicitly passes `submit_to_comfy=true`
- caller explicitly passes `dry_run=false`

## Default behavior

The command defaults to dry-run mode.

## Notes

This is still experimental LTX support and does not alter Wan production routing.
