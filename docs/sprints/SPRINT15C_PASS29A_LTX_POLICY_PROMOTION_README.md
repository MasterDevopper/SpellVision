# Sprint 15C Pass 29A — LTX Policy Promotion

## Goal

Promote LTX from a recognized-but-blocked video family into an enabled experimental Prompt API family.

## What changed

- Wan remains the production native video family.
- LTX is now validated through the Prompt API gated submission path.
- LTX readiness can pass when a selected LTX model is present, even without Wan dual-noise native stack metadata.
- Video payloads now include route/status metadata:
  - `video_backend_route`
  - `video_validation_status`
  - `video_uses_prompt_api_backend`
  - `video_validated_prompt_api_family`
  - `video_validated_backend`

## Why this matters

This removes the policy-level block before Qt Generate routing is connected to the existing LTX Prompt API submission path.

## Expected status after this pass

- LTX T2V/I2V can be marked ready by the video readiness policy.
- Generate routing is not changed yet.
- Wan behavior is unchanged.

## Next pass

Sprint 15C Pass 29B — route Qt Generate for LTX T2V/I2V into `ltx_prompt_api_gated_submission`.
