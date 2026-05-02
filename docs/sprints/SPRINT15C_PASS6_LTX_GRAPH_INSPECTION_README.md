# Sprint 15C Pass 6 — LTX Workflow Graph Inspection and Prompt API Normalization

## Purpose

Pass 5 proved the selected LTX workflow loads but is not a direct Prompt API graph. Pass 6 adds a graph inspection and normalization-preview command so SpellVision can identify whether a workflow is a Comfy UI graph export or a prompt API graph before any `/prompt` submission is enabled.

## Adds

- `python/ltx_workflow_graph_inspection.py`
- Worker commands:
  - `ltx_workflow_graph_inspection`
  - `ltx_prompt_api_normalization_preview`
  - `video_family_graph_inspection`
  - `video_family_prompt_api_normalization_preview`

## Behavior

- Loads the selected LTX workflow from the Pass 4 smoke route.
- Detects workflow format:
  - `comfy_ui_graph`
  - `prompt_api_graph`
  - `unknown`
- Reports node class counts, graph node summaries, links, candidate role mappings, and conversion plan.
- Builds a Prompt API preview only when the graph is already Prompt API compatible.
- Does not submit to ComfyUI.
- Leaves Wan production routing untouched.

## Expected current state

The current LTX example workflow is expected to report:

```text
workflow_format: comfy_ui_graph
prompt_api_candidate: false
normalization_status: ui_graph_inspected_prompt_api_conversion_required
submitted: false
```

That is a correct result and means the next pass should either export Prompt API JSON or implement a safe UI-graph-to-prompt conversion adapter.
