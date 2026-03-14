# Sprint 8.5 Optimization Plan — Model Cleanup First

## Sprint Theme
Performance, memory, and throughput optimization.

## Why This Sprint Matters
Now that queue orchestration is starting to work, the next bottleneck is no longer just correctness. It is cost of:
- switching base models
- reloading LoRAs
- holding stale VRAM allocations
- synchronously finishing metadata/history work before next queue item starts

The fastest practical win is explicit model unload and GPU cleanup.

## First Milestone
### Safe model swap
When a request asks for a different base model than the one in cache:
1. stop treating the old model as just overwritten
2. explicitly destroy old pipeline objects
3. force Python garbage collection
4. free CUDA cache aggressively
5. then load the new model
6. record timing and VRAM metrics around the swap

## Implementation Order

### Phase 1 — Add cleanup helpers
Create helper functions in `worker_service.py`:
- `cuda_memory_snapshot()`
- `clear_cuda_memory()`
- `unload_cached_pipelines()`
- `cleanup_for_model_swap()`

These should be small, isolated, and safe to call repeatedly.

### Phase 2 — Integrate into model load path
In `get_or_load_pipelines()`:
- detect cache key change
- call cleanup before loading replacement pipelines
- keep same-model requests as cache hits

### Phase 3 — Add telemetry
Record:
- previous model key
- requested model key
- cache hit / miss
- cleanup duration
- load duration
- VRAM allocated/reserved before cleanup
- VRAM allocated/reserved after cleanup
- VRAM allocated/reserved after new load

### Phase 4 — Add LoRA reuse shortcut
When the requested LoRA path and scale match the active LoRA:
- skip reset
- skip reapply
- log `lora_cache_hit = true`

### Phase 5 — Unique output paths
Ensure queue/retry flows always produce a fresh output path so benchmarking and history remain trustworthy.

## Expected Immediate Benefit
- less VRAM fragmentation during model changes
- more predictable model-switch latency
- faster repeated same-model jobs
- cleaner queue throughput
- easier debugging because cache and cleanup behavior become observable

## Suggested Commit Sequence
```bash
git commit -m "feat(sprint-8.5): add explicit model unload and cuda memory cleanup"
git commit -m "feat(metrics): add model swap and vram telemetry"
git commit -m "feat(lora): skip redundant lora reloads"
git commit -m "fix(outputs): generate unique paths for queued and retried jobs"
```

## Success Criteria
Sprint 8.5 first milestone is successful when:
- same-model jobs remain cache hits
- different-model jobs trigger explicit cleanup
- cleanup happens before reload
- no stale output overwrites occur for queued/retried jobs
- telemetry clearly shows cleanup/load behavior
