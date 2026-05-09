# Sprint 15C Pass 29B — LTX Generate Route

## Goal

Route Qt Generate for LTX T2V/I2V into the existing LTX Prompt API gated submission worker path.

## What changed

When the video readiness policy reports:

- `video_uses_prompt_api_backend=true`
- `video_family=ltx`

the generated worker payload is routed to:

- `ltx_prompt_api_gated_submission`

The payload also enables:

- `submit_to_comfy=true`
- `dry_run=false`
- `wait_for_result=true`
- `capture_metadata=true`
- `register_result=true`

## What remains unchanged

- Wan native routing remains unchanged.
- Non-LTX video families remain blocked unless separately validated.
- The LTX worker-side adapter remains the safety gate before Comfy submission.

## Expected behavior

Pressing Generate from T2V/I2V with an LTX-ready stack should submit through the LTX Prompt API path, capture Comfy outputs, and register results into queue/history.
