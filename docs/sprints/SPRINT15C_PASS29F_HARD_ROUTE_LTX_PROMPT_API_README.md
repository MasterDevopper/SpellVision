# Sprint 15C Pass 29F — Hard Route LTX Prompt API

## Problem

The UI showed LTX readiness, but the queue failed with:

- command: `t2v`
- status: `loading native video pipeline`

That means the request still entered the native video worker route.

## Fix

GenerationRequestBuilder now hard-routes any LTX video request to:

- `command = ltx_prompt_api_gated_submission`
- `backend = comfy_prompt_api`
- `video_backend_route = prompt_api`
- `video_backend_name = LTX Prompt API`

It also emits the explicit LTX component aliases again inside the final route block so downstream worker code cannot lose them.

## Expected behavior

LTX Generate should no longer say `loading native video pipeline`.

The queue/log status should identify the request as LTX Prompt API / Prompt API video.
