# Sprint 15C Pass 29I — Fix LTX Queue Dispatch

## Root cause

`QueueManager.enqueue()` rewrote every queued request to `command=t2v` and removed the worker dispatch fields. `_run_queue_item()` then dispatched from `item.command`, so LTX Prompt API jobs were still sent into `run_native_video()`.

## Fix

- Preserve execution command separately from display command.
- Keep queue display as `t2v`.
- Execute LTX with `ltx_prompt_api_gated_submission`.
- Add `run_ltx_prompt_api_queued_job()` so queued LTX jobs complete/fail through the same queue lifecycle as other jobs.

## Expected result

LTX Generate should stop failing at `loading native video pipeline`.
