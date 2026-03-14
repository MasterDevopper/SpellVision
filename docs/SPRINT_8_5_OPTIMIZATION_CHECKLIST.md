# Sprint 8.5 Checklist — Performance and Memory Optimization

## Sprint Goal
Improve local generation throughput, reduce model-switch overhead, stabilize VRAM usage, and make queue execution more efficient.

## Highest Priority
- [ ] Add explicit model unload when switching base models
- [ ] Add GPU memory cleanup during model swap
- [ ] Add cache hit / miss telemetry
- [ ] Add model load time telemetry
- [ ] Add VRAM before/after telemetry
- [ ] Add LoRA reuse detection
- [ ] Prevent queued/retried jobs from overwriting outputs

## Model Lifecycle
- [ ] Detect when requested base model differs from active cached model
- [ ] Explicitly delete old T2I pipeline
- [ ] Explicitly delete old I2I pipeline
- [ ] Reset cache metadata before reload
- [ ] Run `gc.collect()` after model unload
- [ ] Run `torch.cuda.empty_cache()` when CUDA is active
- [ ] Run `torch.cuda.ipc_collect()` when safe
- [ ] Measure cleanup time
- [ ] Measure subsequent model load time

## Queue-Aware Throughput
- [ ] Keep same-model jobs warm when possible
- [ ] Avoid unnecessary model swaps between adjacent queue items
- [ ] Record cache hits for queued jobs
- [ ] Record cache misses for queued jobs
- [ ] Add queue wait time metrics
- [ ] Add active model display to worker status

## LoRA Optimization
- [ ] Track active LoRA path
- [ ] Track active LoRA scale
- [ ] Skip LoRA reload when request is unchanged
- [ ] Reset LoRA only when switching LoRAs or clearing LoRA
- [ ] Add LoRA reload telemetry

## Output Path Safety
- [ ] Generate unique output filenames for queued jobs
- [ ] Generate unique output filenames for retries
- [ ] Ensure metadata filenames are also unique
- [ ] Include queue item or retry suffix in output naming

## Background/Deferred Work
- [ ] Reduce hot-path blocking after generation
- [ ] Defer metadata/history refresh when practical
- [ ] Keep queue handoff fast between consecutive jobs

## Telemetry and Observability
- [ ] Log model swap start/end
- [ ] Log cleanup time
- [ ] Log model load time
- [ ] Log first-step latency
- [ ] Log total generation time
- [ ] Log allocated/reserved VRAM before and after run
- [ ] Surface cache hit/miss in UI metadata if practical

## Validation
- [ ] Generate twice on the same model and confirm cache hit
- [ ] Switch to a different model and confirm cleanup happens first
- [ ] Measure faster repeated same-model generations
- [ ] Confirm no memory leak trend across repeated swaps
- [ ] Confirm queue jobs do not overwrite each other
- [ ] Confirm retry creates a new output path
