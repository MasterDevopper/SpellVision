# Sprint 15C Pass 29H2 — Redirect LTX Before Native Video

## Problem

LTX requests were accepted by Qt as Prompt API video but still reached the native video executor and failed at:

`loading native video pipeline`

## Fix

Before the native video pipeline status line runs, worker_service now checks whether the request is an LTX Prompt API request. If so, it normalizes the request and directly calls:

`ltx_prompt_api_gated_submission_snapshot`

## Expected result

LTX Generate should no longer fail with `loading native video pipeline`. The next failure, if any, should be from the actual LTX Prompt API adapter or Comfy submission layer.
