# SPELLVISION_WORKER_PROTOCOL.md

## Purpose

This document defines the communication protocol between:

-   Qt UI
-   Rust core
-   Python worker client
-   Python worker service

The protocol must remain stable, explicit, and easy to debug.

------------------------------------------------------------------------

## Primary Goals

-   simple local communication
-   JSON-based messages
-   line-delimited streaming
-   clear progress events
-   reliable success/failure reporting
-   reproducible request payloads

------------------------------------------------------------------------

## Transport

Current transport:

-   local TCP
-   loopback address `127.0.0.1`
-   default port `8765`

The client sends one JSON request per line.\
The service responds with newline-delimited JSON events.

------------------------------------------------------------------------

## Message Framing

All messages must be UTF-8 JSON encoded and terminated with `\n`.

### Important Rule

Each logical event must occupy exactly one line.

This allows Qt and helper scripts to parse streaming events
incrementally.

------------------------------------------------------------------------

## High-Level Flow

``` text
Qt UI
  -> worker_client.py
  -> worker_service.py
  -> model pipeline
  -> progress events
  -> result or error event
  -> Qt UI
```

------------------------------------------------------------------------

## Protocol Roles

### Qt UI

Responsible for:

-   constructing requests
-   launching client process
-   consuming streaming events
-   updating progress UI
-   updating logs and status
-   showing final results

### worker_client.py

Responsible for:

-   connecting to worker service
-   forwarding request payload
-   relaying returned event lines to stdout
-   failing clearly if service is unavailable

### worker_service.py

Responsible for:

-   validating request
-   loading/caching pipelines
-   executing generation
-   emitting progress events
-   emitting final result or error

### Rust core

Responsible for:

-   local queue state
-   job summary
-   light orchestration
-   not model execution

------------------------------------------------------------------------

## Event Types

Suggested event types:

-   `status`
-   `progress`
-   `log`
-   `warning`
-   `error`
-   `result`
-   `pong`

------------------------------------------------------------------------

## Common Event Envelope

All events should include at least:

``` json
{
  "type": "status",
  "ok": true,
  "timestamp": "2026-03-11T12:00:00"
}
```

Recommended shared fields:

-   `type`
-   `ok`
-   `timestamp`
-   `job_id` if available
-   `task_type` if available

------------------------------------------------------------------------

## Ping Request

### Request

``` json
{"command":"ping"}
```

### Response

``` json
{"type":"pong","ok":true,"pong":true}
```

------------------------------------------------------------------------

## Text-to-Image Request

### Request

``` json
{
  "command": "t2i",
  "task_type": "t2i",
  "job_id": 12,
  "prompt": "fantasy goblin rogue, leather armor, confident pose",
  "negative_prompt": "blurry, low quality, distorted anatomy",
  "model": "C:/Models/checkpoints/novaExanimeXL_ilV50.safetensors",
  "lora": "C:/Models/loras/shexyo_style_trigger.safetensors",
  "lora_scale": 1.0,
  "width": 1024,
  "height": 1024,
  "steps": 30,
  "cfg": 7.5,
  "seed": 42,
  "output": "C:/Outputs/image.png",
  "metadata_output": "C:/Outputs/image.json"
}
```

------------------------------------------------------------------------

## Image-to-Image Request

### Request

``` json
{
  "command": "i2i",
  "task_type": "i2i",
  "job_id": 13,
  "prompt": "fantasy goblin rogue, upgraded armor",
  "negative_prompt": "blurry, low quality",
  "model": "C:/Models/checkpoints/novaExanimeXL_ilV50.safetensors",
  "lora": "C:/Models/loras/shexyo_style_trigger.safetensors",
  "lora_scale": 0.9,
  "steps": 30,
  "cfg": 7.5,
  "seed": 12345,
  "input_image": "C:/Inputs/goblin.png",
  "strength": 0.6,
  "output": "C:/Outputs/goblin_i2i.png",
  "metadata_output": "C:/Outputs/goblin_i2i.json"
}
```

------------------------------------------------------------------------

## Future Request Types

Planned commands:

-   `t2v`
-   `i2v`
-   `t23d`
-   `i23d`
-   `tts`
-   `rig`
-   `optimize_prompt`

These should follow the same event model.

------------------------------------------------------------------------

## Status Event

Used for human-readable phase updates.

### Example

``` json
{
  "type": "status",
  "ok": true,
  "job_id": 12,
  "task_type": "t2i",
  "message": "loading pipeline"
}
```

Examples of status messages:

-   `loading pipeline`
-   `loading lora`
-   `preparing generator`
-   `running inference`
-   `saving image`
-   `writing metadata`

------------------------------------------------------------------------

## Progress Event

Used for determinate progress display.

### Example

``` json
{
  "type": "progress",
  "ok": true,
  "job_id": 12,
  "task_type": "t2i",
  "step": 12,
  "total": 30,
  "percent": 40.0
}
```

### Requirements

-   `step` and `total` must be integers
-   `percent` should be a float between `0` and `100`
-   if exact progress is unavailable, emit `status` events and let UI
    use indeterminate mode

------------------------------------------------------------------------

## Log Event

Used for low-importance informational messages.

### Example

``` json
{
  "type": "log",
  "ok": true,
  "job_id": 12,
  "message": "xformers unavailable; using default attention"
}
```

------------------------------------------------------------------------

## Warning Event

Used for recoverable issues.

### Example

``` json
{
  "type": "warning",
  "ok": true,
  "job_id": 12,
  "message": "LoRA metadata missing; continuing without trigger hints"
}
```

------------------------------------------------------------------------

## Error Event

Used for failures that stop a job.

### Example

``` json
{
  "type": "error",
  "ok": false,
  "job_id": 12,
  "task_type": "t2i",
  "error": "LoRA file not found",
  "traceback": "Traceback ..."
}
```

### Requirements

-   `ok` must be `false`
-   `error` must contain a user-meaningful message
-   `traceback` is optional but strongly recommended for debug builds

------------------------------------------------------------------------

## Result Event

Used exactly once per successful job.

### Example

``` json
{
  "type": "result",
  "ok": true,
  "job_id": 12,
  "task_type": "t2i",
  "output": "C:/Outputs/image.png",
  "metadata_output": "C:/Outputs/image.json",
  "cache_hit": true,
  "backend": "StableDiffusionXLPipeline",
  "detected_pipeline": "sdxl",
  "device": "cuda",
  "dtype": "torch.float16",
  "generation_time_sec": 4.21,
  "steps_per_sec": 7.13,
  "cuda_allocated_gb": 8.15,
  "cuda_reserved_gb": 12.42
}
```

### Requirements

-   must be the final event for successful jobs
-   must contain output path
-   should include performance metrics if available

------------------------------------------------------------------------

## Request Validation Rules

The worker service should validate request payloads before running
generation.

### Common Required Fields

-   `command`
-   `task_type`
-   `model`
-   `output`
-   `metadata_output`

### T2I Required Fields

-   `prompt`
-   `steps`
-   `cfg`
-   `seed`
-   `width`
-   `height`

### I2I Required Fields

-   `prompt`
-   `steps`
-   `cfg`
-   `seed`
-   `input_image`
-   `strength`

If validation fails, emit an `error` event immediately.

------------------------------------------------------------------------

## Defaulting Rules

Where appropriate, the worker may apply defaults.

Suggested defaults:

-   `negative_prompt`: `""`
-   `lora`: `""`
-   `lora_scale`: `1.0`
-   `strength`: `0.6` for I2I if omitted

Any defaulted value should still be written to metadata.

------------------------------------------------------------------------

## Metadata Contract

Every successful generation must write metadata.

Suggested required metadata fields:

-   `task_type`
-   `generator`
-   `backend`
-   `detected_pipeline`
-   `timestamp`
-   `prompt`
-   `negative_prompt`
-   `model`
-   `lora_path`
-   `lora_scale`
-   `lora_used`
-   `width`
-   `height`
-   `steps`
-   `cfg`
-   `seed`
-   `device`
-   `dtype`
-   `image_path` or equivalent output field
-   `generation_time_sec`
-   `steps_per_sec`

------------------------------------------------------------------------

## Client Behavior Rules

`worker_client.py` should:

1.  read exactly one request payload
2.  send it to the worker service
3.  stream each returned line directly to stdout
4.  preserve line boundaries
5.  exit nonzero on client-side failures

### Important

The client should not collapse multiline worker output into a single
unreadable blob.

------------------------------------------------------------------------

## UI Behavior Rules

Qt UI should:

-   parse one event line at a time
-   update progress bar on `progress`
-   append messages on `status`, `log`, `warning`
-   show errors clearly on `error`
-   reset generating state on `result` or `error`

### UI State Guarantees

The UI must never stay stuck in generating mode after the terminal event
arrives.

------------------------------------------------------------------------

## Service Startup Rules

The worker service may need warmup time.

### Recommendation

The UI should treat service startup in phases:

-   `starting`
-   `checking`
-   `online`
-   `unresponsive`
-   `stopped`

Do not immediately mark the backend offline if the Python process has
started but the socket is not yet ready during import/model warmup.

------------------------------------------------------------------------

## Backward Compatibility

When the protocol changes:

-   prefer additive changes
-   do not silently rename critical fields
-   document new commands and events in this file

If a breaking change is unavoidable, version the protocol.

------------------------------------------------------------------------

## Future Protocol Versioning

Suggested future field:

``` json
{
  "protocol_version": 1
}
```

This can be added to requests and responses later.

------------------------------------------------------------------------

## Debug Recommendations

When debugging protocol issues:

-   log raw lines from worker client
-   validate each line as JSON independently
-   ensure each event ends with newline
-   verify final `result` or `error` always arrives
-   verify `task_type` is included consistently

------------------------------------------------------------------------

## Acceptance Criteria

The protocol is considered healthy when:

-   ping succeeds reliably
-   T2I requests stream progress correctly
-   I2I requests stream progress correctly
-   final results always arrive
-   error events are parseable and useful
-   UI state always resets correctly
-   metadata always includes the expected fields

------------------------------------------------------------------------

## Final Principle

The worker protocol is the backbone of SpellVision.

If this protocol stays simple, explicit, and stable, the rest of the
platform can scale without becoming fragile.
