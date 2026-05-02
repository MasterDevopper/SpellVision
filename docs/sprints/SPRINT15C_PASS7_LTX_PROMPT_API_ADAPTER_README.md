# Sprint 15C Pass 7 — LTX Prompt API Export/Conversion Adapter

This pass adds a conservative LTX Prompt API adapter preview.

## What it does

- Adds `python/ltx_prompt_api_adapter.py`.
- Adds worker commands:
  - `ltx_prompt_api_conversion_adapter`
  - `ltx_prompt_api_export_adapter`
  - `ltx_prompt_api_conversion_preview`
  - `video_family_prompt_api_conversion_adapter`
- Builds a UI-graph adapter map for the inspected LTX 2.3 workflow.
- Accepts an optional `prompt_api_export_path` for a real Comfy Prompt API workflow export.
- If a real Prompt API export is supplied, it creates a mutation preview.
- It does not submit to ComfyUI.

## Why

Sprint 15C Pass 6 confirmed the selected LTX workflow is a Comfy UI graph export, not a safe `/prompt` API graph. This pass creates the adapter bridge without enabling real submission.

## Smoke test

```powershell
'{"command":"ltx_prompt_api_conversion_adapter"}' | & .\.venv\Scripts\python.exe .\python\worker_client.py
```

Optional with a real Prompt API export:

```powershell
'{"command":"ltx_prompt_api_conversion_adapter","prompt_api_export_path":"D:\\AI_ASSETS\\comfy_runtime\\ComfyUI\\user\\default\\workflows\\ltx_api.json"}' | & .\.venv\Scripts\python.exe .\python\worker_client.py
```

## Expected result without a Prompt API export

- `adapter_ready: True`
- `normalization_ready: False`
- `safe_to_submit: False`
- `submission_status: adapter_preview_requires_prompt_api_export`
- `blocked_submit_reasons` includes `prompt_api_export_path_not_provided`

## Expected result with a valid Prompt API export

- `prompt_api_export_validation_status: prompt_api_graph_detected`
- `normalization_ready: True` only when required mutation roles are found
- `safe_to_submit: False` in this pass
