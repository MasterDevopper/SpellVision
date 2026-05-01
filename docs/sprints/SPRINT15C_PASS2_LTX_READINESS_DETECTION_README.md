# Sprint 15C Pass 2 — LTX Runtime and Asset Readiness Detection

This pass adds a conservative LTX readiness probe without enabling LTX generation.

## Adds

- `python/video_family_readiness.py`
- Worker command aliases:
  - `ltx_readiness_status`
  - `ltx_runtime_readiness`
  - `video_family_readiness`
  - `video_family_readiness_status`
- Worker-client passthrough support for the new readiness response.

## Checks

- ComfyUI-LTXVideo node registration through `/object_info`
- LTX 2.3 Comfy blueprints
- LTX example workflows
- `extra_model_paths.yaml` pointing to `D:/AI_ASSETS/models`
- LTX checkpoint candidates in `D:/AI_ASSETS/models/diffusion_models`
- Gemma / LTX text encoder candidates
- LTX text projection candidates
- LTX video VAE candidates
- Optional LTX audio VAE candidates

## Readiness states

- `missing_nodes`
- `model_paths_not_ready`
- `missing_assets`
- `missing_blueprints`
- `ready_to_test`

LTX remains experimental. This pass does not enable production generation.
