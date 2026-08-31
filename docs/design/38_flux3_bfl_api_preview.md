# 38 — FLUX.3 BFL API Preview

**Status:** integrated preview path (T2V/I2V); live paid generation still requires an owner API-key smoke test  
**Source audit date:** 2026-08-17

## Product truth

FLUX.3 is exposed in SpellVision as **FLUX.3 (BFL API Preview)**. It is not a local checkpoint family and must not be described as local/native-weight inference.

Current authoritative Black Forest Labs documentation exposes FLUX.3 video through the hosted asynchronous endpoint:

- `POST https://api.bfl.ai/v1/flux-3-video`
- Text-to-video (`mode=t2v`)
- Image-to-video (`mode=i2v`, one opening keyframe in the current cockpit)
- 5–20 second duration
- `hd` or `fhd`; current SpellVision preview requests `hd`
- Synchronized audio enabled
- Poll the returned `polling_url` with `x-key` until `Ready`

Upstream references:

- <https://docs.bfl.ai/flux_3/flux3_video>
- <https://docs.bfl.ai/api-reference/utility/generate-a-video-with-flux-3>
- <https://docs.comfy.org/tutorials/partner-nodes/black-forest-labs/flux-3-video>

The ComfyUI templates use hosted partner nodes. They are corroborating references, not evidence of downloadable local weights.

## SpellVision route

1. T2V/I2V family selector chooses `flux3`.
2. `VideoGenerationPolicy` marks the family `preview_bfl_api` and route `bfl_api` without requiring a local model stack.
3. `GenerationRequestBuilder` emits the family and remote-route contract.
4. `MainWindow::buildWorkerGenerationRequest` forwards the routing fields.
5. `dispatch_generation` selects `run_flux3_video` before the local native-video path.
6. `python/flux3_video.py` validates and submits the request, polls, atomically downloads the MP4, and returns history-ready metadata.

For the production BFL endpoint, returned polling and result URLs must be HTTPS and must not contain embedded credentials. Low-level socket resets and other `OSError` network failures are normalized into a user-facing API error rather than escaping the worker.

## Credentials and billing

Set the API key in the worker process environment:

```text
BFL_API_KEY=<secret>
```

The key is never added to generation payloads, output metadata, logs, or source control. The UI labels this path as a **hosted paid preview** before submission.

## Current request mapping

| Cockpit field | BFL field |
|---|---|
| T2V / I2V mode | `mode` |
| Positive prompt | `prompt` |
| Width/height intent | nearest supported `aspect_ratio` |
| Frames/FPS | whole-second `duration`, clamped to 5–20 |
| I2V source image | `keyframes` as URL/data URI |
| Output quality | `resolution=hd` |
| Audio | `generate_audio=true` |

Unsupported image-only fields, local checkpoint paths, local samplers, CFG, LoRAs, and negative prompts are intentionally not sent.

## Verification

Offline contract verification:

```text
36 passed — FLUX.3 payload/client/worker/family/dispatch plus worker import-budget tests
155 passed, 1 skipped, 5 deselected, 1 expected xfail — full Python suite
Qt Debug target built successfully with MSVC/Qt 6
```

The API lifecycle test uses a local HTTP server and exercises submission, authenticated polling, `Ready` handling, and MP4 download. It does not incur BFL charges.

## Remaining promotion gate

Do not promote this route beyond preview until an owner-controlled paid smoke test proves:

- a real T2V request;
- a real I2V request with exact opening-frame behavior;
- cancellation semantics are acceptable (current cancellation is local and stops polling; upstream job cancellation is not documented);
- result playback and history re-open in the built desktop app;
- the owner accepts cost, moderation, and credential setup UX.
