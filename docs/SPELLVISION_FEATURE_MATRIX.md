# SPELLVISION_FEATURE_MATRIX.md

> Rebuilt from code 2026-06-28; status derived from source, not prior doc.

Status was derived by reading the actual source: worker `run_*` entrypoints, the i2v carve-out, the Flows handlers, the rail specs (`railButtonSpecs`), `openManager`, page instantiation (`new …`), and CMake membership. **Backend** = `diffusers` / `native_comfy_template` / `comfy_workflow` / — (n/a).

## Generation surfaces

| Surface | Modality | Backend | Status | Note |
|---|---|---|---|---|
| **T2I** | Image | `diffusers` | ✅ Working | SDXL via `run_t2i`; shared-weight fp16 (~6.6 GB), non-destructive LoRA adapters |
| **I2I** | Image | `diffusers` | ✅ Working | `run_i2i`; shares the T2I UNet, per-role LoRA adapter selection |
| **Chain Studio** | Image (multi-stage) | `diffusers` | ✅ Working | **Most-finished surface** (Track B, passes 8a–9.5); orchestrates t2i/i2i chains. 3D stages defined but execution-disabled |
| **T2V — Wan** | Video | `native_comfy_template` | ✅ Working | `run_native_split_stack_video` (wan_core/wrapper); contract `production` |
| **T2V — LTX** | Video | `native_comfy_template` | ✅ Working | Embedded `ltx_av_native.json` + `LtxVideoAdapter`; **audio+video**; verified live |
| **I2V — LTX** | Video | `native_comfy_template` | ✅ Working | Keyframe-upload bridge (`_upload_comfy_image`→`LoadImage`→`LTXVImgToVideoConditionOnly`); frame 0 pins to input (MAE 3.5), verified live |
| **I2V — Wan** | Video | `native_comfy_template` | ⛔ Stubbed | LTX-only carve-out in `run_native_split_stack_video` raises — the Wan builder has no image-conditioning graph |
| **Flows / Workflow Library** | Workflow | `comfy_workflow` | ✅ Working | Import + auto-discovery + dependency re-check (extra_model_paths-aware); `run_comfy_workflow` executes |

## Shell surfaces

| Surface | Status | Note |
|---|---|---|
| **Home** | ✅ Working | Dashboard (in-place updates, no flicker) |
| **History** | ✅ Working | Job history + video history index |
| **Settings / Prefs** | ✅ Working | `QSettings` org=DarkDuck |
| **Inspire** (rail) | ◻️ Placeholder | `ModePage` "Coming Soon" stub |
| **Models** (rail) | ◻️ Placeholder | `ModePage` stub; `openManager("models")`/rail → `switchToMode("models")` (the stub) |
| **Manager** (`ManagerPage`) | 🧩 Built-unreachable | Compiled (in CMake) but **never instantiated** (`new ManagerPage` = none) |
| **Model Manager** (`ModelManagerPage`) | 🧩 Built-unreachable | Compiled, never instantiated; Stage-1 spec only. Distinct from the "Models" rail stub above |

## Frontiers (Phase D — planned, not started)

| Surface | Modality | Status | Note |
|---|---|---|---|
| **Image-to-3D** | 3D | 📋 Planned | Phase D **D1** entry point; new `native_comfy_template` family mirroring the LTX migration. See CLAUDE.md §6 3D plan |
| **Text-to-3D** | 3D | 📋 Planned | Phase D **D3** (T2I→image→I2-3D). Thin once D1+D2 exist |
| **Dataset Generation** | Dataset | 📋 Planned | `DatasetGenerationPage.cpp` exists but is **not in CMakeLists (uncompiled)** *and* not wired; integrates an external app (TBD) |

## Infrastructure (working)

Worker TCP/JSON protocol · job queue + extracted state machine (`worker_service_state.py`) · job/video history · metadata system · non-destructive LoRA adapters · shared-weight fp16 VRAM optimization · hardened `_comfy_object_info` · spacing-token theme system · pytest TCP harness.

## Removed / not features

- **Rust bridge** — ❌ removed. Archived to `attic/rust_original_intent/`, unwired from CMake. (The prior matrix listed it "Complete" — it is gone.)

## Beyond v0.1.0 (deferred, unstarted)

Voice Generation · Rigging Pipeline · Asset Library · Character Profiles · LoRA Browser · Ollama AI Assistant · Node Pipelines · UI Redesign — all carried from the prior sprint matrix as "Planned"; none started. Listed so they aren't silently dropped, but they are not part of the v0.1.0 spine (CLAUDE.md §5).
