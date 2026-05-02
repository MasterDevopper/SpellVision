# Sprint 15C Pass 3 — LTX Test Workflow Selection and Metadata Contract

## Goal

Add a conservative LTX test-workflow contract layer without enabling production LTX generation.

## Adds

- `python/ltx_workflow_contract.py`
- Worker commands:
  - `ltx_test_workflow_contract`
  - `ltx_workflow_contract`
  - `video_family_test_workflow_contract`
  - `video_family_workflow_contract`
- LTX workflow selection priority:
  1. `LTX-2.3_T2V_I2V_Single_Stage_Distilled_Full.json`
  2. `LTX-2.3_T2V_I2V_Two_Stage_Distilled.json`
  3. ComfyUI blueprint `Text to Video (LTX-2.3).json`
- Metadata contract fields for:
  - checkpoint
  - Gemma text encoder
  - text projection
  - video VAE
  - optional audio VAE
  - workflow source/name/path
  - recommended CFG/steps/sampler/scheduler
- Keeps LTX marked `experimental`.
- Keeps Wan production path untouched.
- Tightens LTX video/audio VAE candidate separation.

## Smoke test

```powershell
'{"command":"ltx_test_workflow_contract"}' | & .\.venv\Scripts\python.exe .\python\worker_client.py
```

Expected after Sprint 15C Pass 2 asset setup:

```text
type: ltx_test_workflow_contract
ready_to_test: true
generation_enabled: true
workflow_name: LTX-2.3_T2V_I2V_Single_Stage_Distilled_Full.json
```
