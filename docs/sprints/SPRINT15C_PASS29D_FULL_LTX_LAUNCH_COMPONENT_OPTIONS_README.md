# Sprint 15C Pass 29D — Full LTX Launch Component Options

## Goal

Expose the remaining LTX runtime options that are required for first-class Generate, instead of relying on hidden requeue-only defaults.

## Added to the T2V/I2V LTX panel

- Primary checkpoint
- Text encoder
- Text projection
- Audio VAE
- Video VAE
- Vision encoder
- Preferred output variant

## Payload aliases emitted

- `video_primary_model_name`
- `video_text_encoder_name`
- `video_text_projection_name`
- `video_audio_vae_name`
- `video_video_vae_name`
- `video_vae_name`
- `video_vision_encoder_name`
- `preferred_ltx_output_variant`

## Defaults

- `ltx/ltx-2.3-22b-dev.safetensors`
- `ltx/comfy_gemma_3_12B_it.safetensors`
- `ltx-2.3_text_projection_bf16.safetensors`
- `ltx/LTX23_audio_vae_bf16.safetensors`
- `ltx/LTX23_video_vae_bf16.safetensors`
- `clip_vision_g`
- `distilled`

## Expected result

T2V/I2V LTX now exposes the user-editable launch requirements needed by the Prompt API adapter before submission.
