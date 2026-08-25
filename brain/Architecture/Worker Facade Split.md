---
title: Worker Facade Split
type: architecture
status: implemented
updated: 2026-08-17
sources:
  - python/worker_service.py
  - python/worker_runtime.py
  - python/worker_metadata.py
  - python/workflow_library_commands.py
  - python/image_runners.py
  - python/native_runners.py
  - python/comfy_prompt_client.py
  - qt_ui/ImageGenerationPage.cpp
  - qt_ui/generation/SamplingController.cpp
  - tests/test_godfile_split.py
  - .hermes/plans/2026-08-17_222628-godfile-optimize.md
---

# Worker Facade Split

**Implemented.** `worker_service.py` is the **import facade**, not the only home. Tests still import from it. Ceilings: worker **2104 / 2800**, `ImageGenerationPage.cpp` **2886 / 3000** (`tests/test_godfile_split.py`).

## Worker ownership

| Module | Owns |
|--------|------|
| `worker_service.py` | Facade, `dispatch_generation`, TeaCache, leftover orchestration |
| `worker_service_state.py` | Job SM + records |
| `worker_queue.py` | `QueueManager` |
| `worker_tcp.py` | `WorkerTCPHandler` + `EventEmitter` |
| `worker_runtime.py` | Pipeline cache, CUDA cleanup, `unload_all_runtimes` + Comfy `/free` |
| `worker_metadata.py` | History sidecars, `save_metadata` |
| `workflow_library_commands.py` | Flows import / discover / recheck commands |
| `native_image_graphs.py` | Flux / PixArt / Lumina / Z-Image / Anima / **Krea2** builders |
| `native_video_graphs.py` | Wan / LTX / Hunyuan / Mochi builders + family plugin table |
| `comfy_graph_helpers.py` | Shared Comfy node primitives |
| `comfy_prompt_client.py` | Submit / poll / upload + `request_comfy_free_memory` |
| `image_runners.py` | `run_t2i` / `run_i2i`, LoRA adapters, IP-Adapter, upscale |
| `native_runners.py` | `run_native_image` / `run_native_video` / FLUX.3 |
| `ltx_prompt_api_jobs.py` | Prompt-API job payload (fallback only) |

## Qt cockpit ownership

| File | Owns |
|------|------|
| `ImageGenerationPage.cpp` | Shell, `buildUi`, generate / payload |
| `ImageGenerationPage_preview.cpp` | Preview / session / transport |
| `ImageGenerationPage_video.cpp` | Family + operating-point presentation |
| `ImageGenerationPage_catalog.cpp` | Catalog, readiness, snapshots |
| `generation/SamplingController` | Sampler / scheduler / steps / CFG / seed from **worker family allow-lists** |
| `generation/CockpitWidgetKit` | Combo / spin / catalog helpers |

**Specified, not built:** type-level split of `ImageGenerationPage` into multiple QWidget types. TUs first was the safe cut.

## Shutdown

Close sends `unload_all_runtimes` **before** Comfy `taskkill`. That command unloads the worker cache and `POST /free` (`unload_models` + `free_memory`). Adopted Comfy is not killed. Guard: `tests/test_runtime_unload_on_exit.py`. Product VRAM proof is still owner-eyes.

## Related

[[Worker Service]] · [[Generation Cockpit]] · [[Current State Ledger]] · [[Planned Additions]]
