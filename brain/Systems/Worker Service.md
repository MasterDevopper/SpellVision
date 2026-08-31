---
title: Worker Service
type: system
status: implemented
sources:
  - python/worker_service.py
  - python/worker_service_state.py
  - python/worker_runtime.py
  - python/worker_queue.py
  - python/worker_tcp.py
  - docs/design/20_worker_runtime_ground_truth_map.md
  - docs/design/21_worker_refactor_plan.md
updated: 2026-08-17
---

# Worker Service

## Role

Backend process: TCP handler, queue, command dispatch, family runners, Comfy orchestration.

`worker_service.py` is the **import facade** (~2104 lines, ceiling 2800). Runners, graphs, queue, TCP, runtime cache, and metadata live in dedicated modules. See [[Worker Facade Split]].

## Major modules

| Module | Concern |
|--------|---------|
| `worker_service.py` | Facade + `dispatch_generation` + TeaCache |
| `worker_service_state.py` | Job SM + records (stdlib-only) |
| `worker_queue.py` | `QueueManager` |
| `worker_tcp.py` | `WorkerTCPHandler` + `EventEmitter` |
| `worker_runtime.py` | Pipeline cache, CUDA cleanup, unload + Comfy `/free` |
| `worker_metadata.py` | History sidecars + `save_metadata` |
| `workflow_library_commands.py` | Flows import / discover / recheck |
| `image_runners.py` | `run_t2i` / `run_i2i` + LoRA adapters |
| `native_runners.py` | Native image/video / FLUX.3 runners |
| `native_image_graphs.py` / `native_video_graphs.py` | Family graph builders |
| `comfy_prompt_client.py` | Submit / poll / upload / `/free` |
| `worker_client.py` | CLI bridge for UI |
| `video_adapters/` | Wan, LTX, generic + registry |
| `video_family_contracts.py` | Family capability contracts |
| `memory_optimization.py` | Shared-weight + fp16 cast path |
| `ltx_*.py` | Prompt-API fallback + history/requeue |

## Shutdown

`aboutToQuit` → `unload_all_runtimes` (worker cache + Comfy `/free`) → kill Comfy only if SpellVision started it.

## Logging gotcha

Root logger defaults to **WARNING** — `logging.info` is invisible. Promote diagnostics to WARNING+.

## Health / tests

- Pytest session fixture spawns worker on free port (`tests/conftest.py`)
- Contract tests: ping, queue/`noop_slow`, LoRA adapters, god-file ceilings, unload-on-exit, family builders
- Smoke tier deselected by default (`-m "not smoke"`)

## Related

[[Job Lifecycle Contract]] · [[Native Comfy Template Pattern]] · [[Image Families and Memory]] · [[Worker Facade Split]]
