# Sprint 15C Pass 5 — LTX Workflow Materialization and Comfy Submission Dry Run

This pass adds a non-submitting LTX workflow materialization dry run.

## Purpose

- Load the LTX workflow selected by the Pass 3 workflow contract.
- Build the tiny T2V smoke request from Pass 4.
- Inspect workflow nodes and candidate input keys.
- Produce a materialized workflow preview.
- Report mutation candidates and missing mutation roles.
- Keep `submitted=false`; no Comfy `/prompt` call is made in this pass.

## New commands

- `ltx_workflow_materialization_dry_run`
- `ltx_materialize_workflow`
- `ltx_t2v_materialize_dry_run`
- `video_family_materialization_dry_run`

## Expected result

The command should return `type=ltx_workflow_materialization_dry_run`, `ok=true`, `gate_passed=true`, `submitted=false`, and a `submission_status` of either:

- `dry_run_validated`, or
- `dry_run_validated_submit_not_performed` if `submit=true` was provided.

This pass intentionally does not mutate the Wan production path and does not submit to ComfyUI.
