# SPELLVISION_WORKER_PROTOCOL.md

## Purpose

This document defines the communication protocol between:

-   Qt UI
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

> The original "Rust core" that owned local queue state / job summary was removed
> (archived to `attic/rust_original_intent/`). Queue and job-state ownership now
> live in the Python worker (`worker_service_state.py`).

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
{"type":"result","ok":true,"pong":true,"service":"spellvision_worker","protocol_version":1}
```

The UI adopts an already-running worker only when `service` and
`protocol_version` match exactly. A listener with a missing or incompatible
identity is left untouched and is not treated as a usable SpellVision worker.

------------------------------------------------------------------------

## Text-to-Image Request

### Request

``` json
{
  "command": "t2i",
  "task_type": "t2i",
  "job_id": "7f3c1a24-9d10-4b2e-9a55-6b1e0c8f4d31",
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
  "job_id": "b41d7e08-2c6f-4a19-8f77-15a9d0e3c882",
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

## Model Intelligence Commands

Five commands over `model_intelligence_commands.py` (W1): who a local weight is according to the
site that hosts it, and the settings it wants. Filed `DIAGNOSTIC` in
`worker_command_audience.py` -- nothing in `qt_ui/` reaches them yet; W2 wires
`model_recommended_settings` into the cockpit and W5 wires the rest into the Models page.

### Model Intel Get Request

Reads the sidecar for one weight, if one exists.

#### Request

``` json
{
  "command": "model_intel_get",
  "path": "D:/AI_ASSETS/models/checkpoints/novaExanimeXL_ilV50.safetensors"
}
```

#### Response

``` json
{
  "type": "model_intel",
  "ok": true,
  "path": "D:/AI_ASSETS/models/checkpoints/novaExanimeXL_ilV50.safetensors",
  "sidecar": null,
  "recommended": {}
}
```

`sidecar` is `null` and `recommended` is `{}` when no `<stem>.spellvision.json` exists yet --
never invented, per `model_intelligence/recommended.py`.

### Model Intel Refresh Request

Walks the given roots, hashes what it finds, looks it up, and writes sidecars. Reports progress
through `model_intel_progress` events as it goes; a full library pass is close to 80 minutes, so a
caller subsets `roots` rather than waiting for one giant result.

#### Request

``` json
{
  "command": "model_intel_refresh",
  "roots": ["D:/AI_ASSETS/models/loras"]
}
```

#### Response

``` json
{
  "type": "model_intel_refresh",
  "ok": true,
  "examined": 475,
  "identified": 402,
  "no_match": 73,
  "skipped_unreadable": [],
  "errors": [],
  "total": 475
}
```

A root that cannot be read (missing, or BitLocker-locked) is named in `skipped_unreadable` rather
than silently contributing zero files to the total.

### Model Intel Set User Request

Records a user override -- name, picture, notes, or a specific setting -- that a later refresh
must never revert.

#### Request

``` json
{
  "command": "model_intel_set_user",
  "path": "D:/AI_ASSETS/models/checkpoints/house_v1.safetensors",
  "name": "My Favourite"
}
```

#### Response

``` json
{
  "type": "model_intel_set_user",
  "ok": true,
  "path": "D:/AI_ASSETS/models/checkpoints/house_v1.safetensors",
  "changed": ["name"]
}
```

`ok` is `false` with an `error` string when `path` does not resolve to a model file (a model
extension per `model_intelligence/hashing.py`) -- for example a path outside the model roots.

### Model Recommended Settings Request

Resolves the settings a model wants: sidecar first, family table as fallback for anything the
sidecar does not cover.

#### Request

``` json
{
  "command": "model_recommended_settings",
  "path": "D:/AI_ASSETS/models/checkpoints/krea2_base.safetensors",
  "family": "krea2"
}
```

#### Response

``` json
{
  "type": "model_recommended_settings",
  "ok": true,
  "path": "D:/AI_ASSETS/models/checkpoints/krea2_base.safetensors",
  "family": "krea2",
  "settings": {
    "steps": {
      "value": 28,
      "provenance": "table:family-default",
      "confidence": 1.0,
      "n": null,
      "total": null
    }
  },
  "warnings": []
}
```

A field's `provenance` is one of `user`, `site:image-meta-mode`, `site:trainedWords`,
`card:frontmatter`, `card:snippet-regex`, `card:prose-regex` or `table:family-default` -- the
site's own example images outrank a card snippet, per `model_intelligence/recommended.py`.

### Model Roots Status Request

Reports which of the given model roots can be read right now.

#### Request

``` json
{
  "command": "model_roots_status",
  "roots": ["D:/AI_ASSETS/models"]
}
```

#### Response

``` json
{
  "type": "model_roots_status",
  "ok": true,
  "roots": [
    {"path": "D:/AI_ASSETS/models", "readable": true, "reason": ""}
  ]
}
```

`reason` is `"missing"`, `"locked"` (BitLocker) or `"error"` when `readable` is `false`.

------------------------------------------------------------------------

## Command Coverage

**This document details 8 of 132 commands.** The two examples above the Model Intelligence
Commands section are the shape every command follows, not the set of commands that exist -- and
the difference matters, because a reader who took the old "Future Request Types" list at face
value would have believed `t2v` and `i2v` were unimplemented. Both have been shipping and
render-proven since 2026-08.

The authoritative list is `python/worker_command_audience.py`, which classifies every command by who
it is for. `tests/test_protocol_doc.py` asserts these counts against that module, so this section
cannot quietly go stale the way the "Planned commands" list did.

| audience | count | what it means |
|---|---|---|
| user-facing | 57 | reachable from the UI by a normal user action |
| diagnostic | 59 | for inspecting state; safe, but not part of a normal flow |
| internal | 16 | worker-to-worker or test-only; not a public surface |
| **total** | **132** | |

Commands not detailed here still follow the envelope and event model described above: a `command`
field, an optional `job_id`, and the same status / progress / result / error events.

------------------------------------------------------------------------

## Status Event

Used for human-readable phase updates.

### Example

``` json
{
  "type": "status",
  "ok": true,
  "job_id": "7f3c1a24-9d10-4b2e-9a55-6b1e0c8f4d31",
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
  "job_id": "7f3c1a24-9d10-4b2e-9a55-6b1e0c8f4d31",
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
  "job_id": "7f3c1a24-9d10-4b2e-9a55-6b1e0c8f4d31",
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
  "job_id": "7f3c1a24-9d10-4b2e-9a55-6b1e0c8f4d31",
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
  "job_id": "7f3c1a24-9d10-4b2e-9a55-6b1e0c8f4d31",
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
  "job_id": "7f3c1a24-9d10-4b2e-9a55-6b1e0c8f4d31",
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
