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

Six commands over `model_intelligence_commands.py` (W1): who a local weight is according to the
site that hosts it, and the settings it wants. `model_recommended_settings` is `USER_FACING` in
`worker_command_audience.py` -- the cockpit asks it on every checkpoint change
(`MainWindow::fetchModelDefaultsAsync`, W2). The other five are still filed `DIAGNOSTIC`: nothing
in `qt_ui/` reaches them yet, and W5 wires them into the Models page.

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

Walks the given roots, hashes what it finds, looks it up, and writes sidecars. The work runs on a
background thread and is always cancellable by `model_intel_cancel`; a full library pass is close
to 80 minutes, so a caller subsets `roots` rather than waiting for one giant result.

Two modes. By default the handler streams `model_intel_progress` events on the open connection and
replies with the result there, preceded by a `model_intel_refresh_started` event carrying the
`job_id`. With `"background": true` the reply IS that started event -- it returns immediately --
and progress plus the final `model_intel_refresh` result are published to `subscribe`rs instead.

#### Request

``` json
{
  "command": "model_intel_refresh",
  "roots": ["D:/AI_ASSETS/models/loras"],
  "background": false
}
```

#### Response

``` json
{
  "type": "model_intel_refresh",
  "ok": true,
  "job_id": "mi_4f1c9a2b7de0",
  "examined": 475,
  "identified": 402,
  "no_match": 73,
  "lookup_failed": 0,
  "cancelled": false,
  "skipped_unreadable": [],
  "errors": [],
  "total": 475
}
```

A root that cannot be read (missing, or BitLocker-locked) is named in `skipped_unreadable` rather
than silently contributing zero files to the total.

`no_match` and `lookup_failed` are different facts and are counted separately. `no_match` is the
site answering that it does not know this hash, and it is recorded in the sidecar. `lookup_failed`
is the lookup never completing -- offline, throttled, a malformed response -- and such a file
keeps whatever a previous successful refresh established: its name, trigger words, sources and
pictures are not overwritten by an empty answer.

### Model Intel Cancel Request

Stops a running refresh. The flag lives in `model_intelligence/jobs.py` rather than on either
connection, because a cancel necessarily arrives on a different one from the refresh it stops --
and in background mode the starting connection is already closed.

#### Request

``` json
{
  "command": "model_intel_cancel",
  "job_id": "mi_4f1c9a2b7de0"
}
```

Omit `job_id` to cancel every refresh that is running.

#### Response

``` json
{
  "type": "model_intel_cancel",
  "ok": true,
  "job_id": "mi_4f1c9a2b7de0",
  "cancelled": ["mi_4f1c9a2b7de0"],
  "running": []
}
```

`ok` is `false` with an `error` when no refresh is running under that id -- a caller told `ok`
for the wrong id would watch the refresh continue and conclude cancel is broken. The cancelled
run still returns its result, with `"cancelled": true` and the counts it reached.

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

`ok` is `false` with an `error` string when `path` does not carry a model extension (per
`model_intelligence/hashing.py`), and -- when the request also names `roots` (or `models_roots`)
-- when `path` or `picture` resolves outside every one of them.

**Be precise about what that does and does not guarantee.** A request that names NO roots gets no
location check at all: any path with a model extension is accepted, anywhere on the machine. That
is the honest state of the code, and this paragraph exists because the previous version of it
claimed the opposite -- it said a path outside the model roots was refused when only the extension
was ever examined, and a test named for the location check passed on the extension. The surface is
bounded instead by `worker_auth`: these commands are LOCAL_TRUSTED only, so a token holder is
denied and `LOCAL_PROBE` gets `ping`. A caller promoted to USER_FACING must send its configured
roots with every request: `MainWindow::fetchModelDefaultsAsync` (W2) sends `scannableModelsRoots`,
which is what makes the containment above real for the cockpit's own asks. W5's Models-page callers
must do the same when they land.

### Model Recommended Settings Request

Resolves the settings a model wants, through `model_intelligence/resolve.py` (W2): the sidecar
first, then this project's own runtime operating-point table, then the family's published floor
underneath it. A sampler or scheduler the family's graph cannot accept is dropped to the family's
own default with a warning rather than offered; a canvas beyond a (deliberately heuristic) VRAM
budget is snapped down with a warning instead of silently rendered smaller.

#### Request

``` json
{
  "command": "model_recommended_settings",
  "path": "D:/AI_ASSETS/models/checkpoints/krea2_base.safetensors",
  "family": "krea2",
  "mode": "t2i",
  "live_samplers": ["euler", "er_sde"],
  "live_schedulers": ["simple", "normal"],
  "vram_gb": 24,
  "host_ram_gb": 64
}
```

`family`, `mode`, `live_samplers`, `live_schedulers`, `vram_gb` and `host_ram_gb` are all optional.
`live_samplers`/`live_schedulers` narrow the family's own sampler/scheduler allowlist further (a
live `/object_info` dump, when the caller has one); `vram_gb` is the only input that can trigger a
canvas cap, and an absent/zero value means "hardware not known", which resolves with no cap and no
opinion.

#### Response

``` json
{
  "type": "model_recommended_settings",
  "ok": true,
  "path": "D:/AI_ASSETS/models/checkpoints/krea2_base.safetensors",
  "family": "krea2",
  "operating_point": "raw",
  "settings": {
    "steps": {
      "value": 52,
      "provenance": "table:family-operating-point",
      "confidence": 1.0,
      "n": null,
      "total": null
    }
  },
  "warnings": []
}
```

A field's `provenance` is one of `user`, `site:image-meta-mode`, `site:trainedWords`,
`card:frontmatter`, `card:snippet-regex`, `card:prose-regex`, `site:image-meta-weak`,
`table:family-operating-point` or `table:family-default` -- the site's own example images outrank
a card snippet, and this project's own render-tuned operating-point table outranks the family's
published floor, per `model_intelligence/resolve.py`. A capped field keeps its provenance with
`:capped` appended (e.g. `site:image-meta-mode:capped`), so the caption can say the number shown
is not the number the model asked for. `operating_point` names the operating point (`raw` /
`turbo` / `quality` / `fast` / ...) the settings were resolved against, `null` for a family with
none -- the cockpit's Speed chip reads it so the two never disagree.

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

## Comfy Runtime Commands

### Restart Comfy Runtime Request

Stops the managed ComfyUI process (if any) and starts it again. With no `arm`-shaped keys, this
launches exactly as `start_comfy_runtime` always has -- the same environment-driven attention/VRAM
defaults, unchanged. Naming any of `attention`, `fast`, `dynamic_vram` or `vram_headroom` launches
that arm explicitly instead, for a measured A/B: the flag for whichever side is named is written to
the command line rather than left to ComfyUI's own default, so a request for `sdpa` is
distinguishable on the wire from "nothing was asked for and SDPA happened to run".

#### Request

``` json
{
  "command": "restart_comfy_runtime",
  "startup_timeout_sec": 90,
  "attention": "sdpa",
  "fast": ["fp16_accumulation"],
  "dynamic_vram": false,
  "vram_headroom": 16
}
```

All fields are optional. `startup_timeout_sec` defaults to 60. `attention` accepts the same
spellings as `SPELLVISION_COMFY_ATTENTION` (`sage`/`sageattention`/`sage_attention`,
`sdpa`/`pytorch`/`torch`/`none`/`off`/`default`); naming `sage` when the package is not importable
in ComfyUI's own venv **fails the request** rather than silently launching SDPA -- a caller that
asked for sage must be told it did not get sage, not be handed a mislabelled row. `fast` is a list
of `comfy/cli_args.py` `PerformanceFeature` names (an empty list requests the bare `--fast`, which
enables all of them). `dynamic_vram: false` passes `--disable-dynamic-vram`; omitting the key, or
passing `true`, leaves DynamicVRAM on (this core's own default). `vram_headroom` is a number of GB
to reserve for the OS via `--reserve-vram`; omitted or `null` means "ComfyUI's own OS-dependent
reservation", which is not the same as reserving nothing.

An arm is **remembered for the session**. Naming no arm key does not mean "launch the environment
default" -- it means "keep whatever this session was last launched with", so a restart performed for
some other reason cannot silently replace the configuration a caller asked for. (It did: a rewritten
`extra_model_paths.yaml` restarts ComfyUI, and that restart used to re-resolve attention from the
environment, turning an explicitly requested `sdpa` session into a `sage` one with nothing in the
reply saying so.) The environment is the fallback only for the first launch of a session.

To go back to the environment, send a nested empty arm -- `{"command": "restart_comfy_runtime",
"arm": {}}`. The flat keys alone cannot express it, because "named no arm key" and "named an empty
arm" look identical in that form; a nested `arm` object may also carry the same four keys, and wins
over the flat ones when both are present.

#### Response

``` json
{
  "type": "comfy_runtime_ack",
  "action": "restart_comfy_runtime",
  "ok": true,
  "state": "ready_managed",
  "argv": [
    "C:/sv_comfynext_v034/.venv/Scripts/python.exe", "C:/sv_comfynext_v034/ComfyUI/main.py",
    "--listen", "127.0.0.1", "--port", "8188", "--dont-print-server",
    "--use-pytorch-cross-attention", "--fast", "fp16_accumulation",
    "--disable-dynamic-vram", "--reserve-vram", "16"
  ],
  "endpoint": "http://127.0.0.1:8188"
}
```

`argv` is the command line this restart actually launched -- read back from the same
`recommended_command`/`Popen` call, not recomputed from the request -- so a caller can verify the
arm took rather than trust that the request was honoured. This matters because the Qt sage probe
fails open to SDPA on a cold cache miss (`RuntimeProfile.cpp`): a request for `sage` can legitimately
launch a process running SDPA, and only reading the process back (here, or via
`optimization_provenance.probe()` against the running `/system_stats`) tells the two apart.

------------------------------------------------------------------------

## Optimization Results

Reads the optimization ledger (`runtime/state/optimization_results.jsonl`), whose only writer is
`scripts/dev/measure_optimizations.py`. DIAGNOSTIC: no UI route until W3 T6.

**Request**

```json
{
  "command": "optimization_results",
  "family": "krea2",
  "lever": "sage_attention",
  "limit": 50
}
```

`family`, `lever` and `limit` are all optional; with none of them the whole ledger comes back.

**Reply**

```json
{
  "type": "optimization_results",
  "ok": true,
  "rows": [
    {
      "family": "krea2", "mode": "t2i", "lever": "sage_attention", "arm": "sage",
      "seconds": [120.72, 122.10], "mean": 121.41,
      "baseline_mean": 124.01, "delta_pct": -2.1,
      "warm": true,
      "quality": {"guards": ["black_frame"], "status": "pass", "values": {}},
      "memory": {"peak_vram_gb": null, "comparable": false, "reason": "no --reserve-vram was passed"},
      "provenance": {"attention_backend": "sage", "comfy_argv": ["..."], "fast_flags": []},
      "exclusions": [], "excluded_from_delta": false,
      "dest": "...", "job_id": "...", "recorded_at": "2026-09-16T21:04:11"
    }
  ],
  "families": ["krea2"],
  "levers": ["sage_attention"],
  "unmeasured_levers": ["vae_tiling"],
  "blocked_levers": {"ck_int8_attention": "..."},
  "cut_levers": {"nvfp4": "..."},
  "path": "C:/.../runtime/state/optimization_results.jsonl"
}
```

Four properties of a row are enforced by `python/optimization_results.py` rather than left to the
writer, and each exists because a published number on this project violated it:

* **`seconds` is a list, never a scalar.** A single timing is not a measurement; a row with one
  timed run is recorded and excluded from every delta.
* **`warm` is explicit.** The archive holds the same configuration at 159.27 s cold and 120.72 s
  warm.
* **`baseline_mean` travels with the row**, so a delta can never be computed against a baseline
  from another session or another build. Nothing reads a baseline out of a different row.
* **A row whose `provenance.attention_backend` is `unknown` is recorded and excluded from every
  delta** -- the harness has to be able to say "this ran, and I cannot tell you on what".

`excluded_from_delta` is therefore never a silent drop: `exclusions` names every reason, and
`delta_pct` is `null` whenever it is set.

------------------------------------------------------------------------

## Command Coverage

**This document details 11 of 134 commands.** The two examples above the Model Intelligence
Commands section are the shape every command follows, not the set of commands that exist -- and
the difference matters, because a reader who took the old "Future Request Types" list at face
value would have believed `t2v` and `i2v` were unimplemented. Both have been shipping and
render-proven since 2026-08.

The authoritative list is `python/worker_command_audience.py`, which classifies every command by who
it is for. `tests/test_protocol_doc.py` asserts these counts against that module, so this section
cannot quietly go stale the way the "Planned commands" list did.

| audience | count | what it means |
|---|---|---|
| user-facing | 58 | reachable from the UI by a normal user action |
| diagnostic | 60 | for inspecting state; safe, but not part of a normal flow |
| internal | 16 | worker-to-worker or test-only; not a public surface |
| **total** | **134** | |

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
