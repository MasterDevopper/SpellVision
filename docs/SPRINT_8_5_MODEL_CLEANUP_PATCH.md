# Sprint 8.5 First Patch — Model Unload and VRAM Cleanup

This patch is designed for `python/worker_service.py`.

## 1. Add these helpers near the top of the file

```python
import gc
import time


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def cuda_memory_snapshot() -> dict[str, float]:
    if not torch.cuda.is_available():
        return {
            "allocated_gb": 0.0,
            "reserved_gb": 0.0,
            "max_allocated_gb": 0.0,
            "max_reserved_gb": 0.0,
        }

    return {
        "allocated_gb": round(torch.cuda.memory_allocated() / (1024 ** 3), 2),
        "reserved_gb": round(torch.cuda.memory_reserved() / (1024 ** 3), 2),
        "max_allocated_gb": round(torch.cuda.max_memory_allocated() / (1024 ** 3), 2),
        "max_reserved_gb": round(torch.cuda.max_memory_reserved() / (1024 ** 3), 2),
    }


def clear_cuda_memory() -> dict[str, float]:
    gc.collect()

    if torch.cuda.is_available():
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass
        try:
            torch.cuda.ipc_collect()
        except Exception:
            pass

    return cuda_memory_snapshot()


def unload_cached_pipelines() -> dict[str, Any]:
    before = cuda_memory_snapshot()
    start = time.perf_counter()

    with CACHE_LOCK:
        old_key = MODEL_CACHE.get("key")
        old_t2i = MODEL_CACHE.get("pipe")
        old_i2i = MODEL_CACHE.get("img2img_pipe")

        MODEL_CACHE["pipe"] = None
        MODEL_CACHE["img2img_pipe"] = None
        MODEL_CACHE["key"] = None
        MODEL_CACHE["pipeline_type"] = None

    try:
        if old_t2i is not None:
            del old_t2i
    except Exception:
        pass

    try:
        if old_i2i is not None:
            del old_i2i
    except Exception:
        pass

    after = clear_cuda_memory()
    elapsed = round(time.perf_counter() - start, 3)

    return {
        "old_key": old_key,
        "cleanup_time_sec": elapsed,
        "memory_before": before,
        "memory_after": after,
    }


def cleanup_for_model_swap(requested_key: str) -> dict[str, Any] | None:
    with CACHE_LOCK:
        active_key = MODEL_CACHE.get("key")

    if not active_key or active_key == requested_key:
        return None

    stats = unload_cached_pipelines()
    stats["requested_key"] = requested_key
    return stats
```

## 2. In `get_or_load_pipelines()`, add model-swap cleanup before loading a different model

Right after computing the request key, add:

```python
swap_cleanup_stats = cleanup_for_model_swap(model_name_or_path)
```

Then include telemetry in your eventual load/result metadata:

```python
load_start = time.perf_counter()

# existing pipeline load code here

load_time_sec = round(time.perf_counter() - load_start, 3)
memory_after_load = cuda_memory_snapshot()
```

## 3. Keep same-model requests as normal cache hits

Do not change the same-key cache-hit path. Only run cleanup when:
- a cached key exists
- requested key differs from the cached key

## 4. Add the telemetry into your result/log payloads

Suggested metadata keys:
- `cache_hit`
- `model_swap_cleanup`
- `model_load_time_sec`
- `memory_after_load`

Example:

```python
payload["cache_hit"] = cache_hit
payload["model_swap_cleanup"] = swap_cleanup_stats
payload["model_load_time_sec"] = load_time_sec
payload["memory_after_load"] = memory_after_load
```

## 5. Validation steps

### Same-model repeat
Run the same model twice and confirm:
- second run is a cache hit
- no cleanup occurs

### Different-model switch
Run model A, then model B, and confirm:
- cleanup occurs before new load
- old key is reported
- cleanup timing is recorded
- VRAM snapshot changes are visible

### Queue behavior
Queue multiple items and confirm:
- repeated same-model items remain warm
- different-model items trigger cleanup once per swap
```
