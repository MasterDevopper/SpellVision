# Sprint 15C Pass 29C — LTX Launch Options Panel

## Goal

Expose the missing LTX launch requirement directly in the T2V/I2V UI: the Comfy Prompt API export path.

## What changed

- Added an LTX Launch Options panel to video generation pages.
- Added a Prompt API export path field.
- Added Browse API JSON.
- Added Use Default.
- Added LTX Defaults:
  - 512x320
  - 33 frames
  - 24 fps
  - 28 steps
  - CFG 7.0
- The generation payload now emits:
  - `prompt_api_export_path`
  - `api_workflow_path`
  - `ltx_prompt_api_export_path`

## Why this matters

The worker-side LTX adapter blocks submission unless a valid Prompt API graph is provided. Pass 29B routed LTX Generate to the right worker path, but the UI still did not expose the required API export field.

## Expected behavior

With an LTX model stack selected, T2V/I2V users can now provide or accept the default `ltx_api.json` Prompt API export path before pressing Generate.
