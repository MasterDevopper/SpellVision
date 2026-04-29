# Sprint 15A Pass 4 — I2V input/keyframe handoff hardening

This pass is intended to be applied **after Sprint 15A Pass 3**.

## What this pass hardens

### 1) Explicit I2V input aliasing from UI payloads
`GenerationRequestBuilder.cpp` is patched so image-to-video submissions keep the source keyframe under multiple aliases:

- `input_image`
- `video_input_image`
- `input_keyframe`
- `keyframe_image`
- `source_image`
- `i2v_source_image`

It also stamps `video_has_input_image` in the payload for clearer downstream diagnostics.

### 2) Queue/retry survival for source keyframe paths
`worker_service.py` gets a `normalize_video_input_fields()` helper and routes `clone_request_snapshot()` through it.

That means queue snapshots, archived jobs, and retries keep the I2V keyframe path normalized even if the request originally used only one alias.

### 3) Better queue/result diagnostics
Queue item payloads now expose:

- `input_image`
- `video_input_image`
- `video_input_name`
- `video_has_input_image`
- `video_request_kind`
- `video_stack_kind`
- `video_duration_label`

Completed job payloads also add:

- `video_input_name`
- `video_completion_summary`

### 4) Clearer runtime messaging
Comfy waiting text becomes more explicit for video jobs and includes keyframe details when available.

Examples:
- `waiting for ComfyUI image-to-video render (...)`
- `waiting for ComfyUI text-to-video render (...)`

Completion messaging is also upgraded so I2V can report a more specific completion summary.

### 5) UI-side I2V readiness hardening
`ImageGenerationPage.cpp` is patched so:

- image/video input validity requires the file to still exist
- broken keyframe paths block generation with a clear message
- preview empty-state text says **keyframe** for I2V instead of the more generic **source image** wording
- the diagnostics summary includes the selected keyframe path

## Files patched

- `qt_ui/generation/GenerationRequestBuilder.cpp`
- `python/worker_service.py`
- `qt_ui/ImageGenerationPage.cpp`

## How to apply

From the repo root:

```powershell
python scripts/refactors/apply_sprint15a_i2v_input_keyframe_handoff_pass4.py
```

Then rebuild and run your normal validation flow.

## Recommended validation

1. **I2V with direct UI keyframe**
   - Select a keyframe in Image-to-Video mode.
   - Submit a run.
   - Confirm the request reaches the worker with a populated keyframe path.

2. **Queued I2V item**
   - Queue an I2V job.
   - Inspect `queue_status` and confirm `video_input_image` / `video_input_name` are present.

3. **Retry I2V job**
   - Retry a completed or failed I2V item.
   - Confirm the retried request still contains the normalized keyframe aliases.

4. **Broken file path**
   - Pick a keyframe, then move/delete the file.
   - Confirm the UI blocks generation with a missing-keyframe message.

5. **T2V regression check**
   - Run a text-to-video job.
   - Confirm no keyframe requirement appears and the preview/runtime behavior still works normally.
