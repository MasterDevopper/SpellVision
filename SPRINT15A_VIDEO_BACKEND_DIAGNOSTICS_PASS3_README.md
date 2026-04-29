# Sprint 15A Pass 3 — Video backend diagnostics and completion hardening

This pass hardens the T2V/I2V backend contract without changing preview playback.

## Adds / changes

- Adds I2V input aliases to `GenerationRequestBuilder` payloads:
  - `video_input_image`
  - `input_keyframe`
  - `keyframe_image`
  - `source_image`
- Adds video completion diagnostics in `python/worker_service.py`:
  - backend type/name
  - output and metadata paths
  - request kind
  - stack kind/mode/readiness
  - frames/FPS/duration
  - input image presence/path
  - Comfy prompt id when available
- Improves Comfy wait progress messages for video renders.
- Extends `JobResult` so queue snapshots keep video diagnostics after completion.
