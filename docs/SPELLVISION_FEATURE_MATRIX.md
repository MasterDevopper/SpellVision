# SPELLVISION_FEATURE_MATRIX.md

> **Authority:** Prefer live code + `CLAUDE.md` + `brain/Planning/Current State Ledger.md` over this file when they conflict.
> Rebuilt 2026-06-28; **refreshed 2026-08-24** against the three-reviewer audit.

Status from source: worker `run_*` entrypoints, Flows handlers, rail specs, page instantiation, CMake. **Backend** = `diffusers` / `native_comfy_template` / `comfy_workflow` / hosted API / — (n/a).

## Generation surfaces

| Surface | Modality | Backend | Status | Note |
|---|---|---|---|---|
| **T2I** | Image | `diffusers` + native image graphs | ✅ Working | SDXL/Flux/Krea2/etc.; shared-weight fp16; non-destructive LoRA adapters; no inert IMG stub |
| **I2I** | Image | `diffusers` + native image graphs | ✅ Working | Shares T2I UNet; per-role LoRA adapter selection |
| **Chain Studio** | Image (multi-stage) | `diffusers` | ✅ Working | Engine proven; **v1 nav-hidden** unless `SPELLVISION_SHOW_ALL_MODES=1` |
| **T2V — Wan** | Video | `native_comfy_template` | ✅ Working | Dual-noise t2v production |
| **T2V — LTX** | Video | `native_comfy_template` | ✅ Working | **Default = `two_stage_distilled`**; AV; production |
| **I2V — LTX** | Video | `native_comfy_template` | ✅ Working | Keyframe-upload bridge; frame 0 pins (live MAE ~3.5) |
| **I2V — Wan 2.1** | Video | `native_comfy_template` | ✅ Working | VAE version-match guard landed |
| **I2V — Wan 2.2 dual-noise** | Video | `native_comfy_template` | ✅ Working | Render-proven 2026-08-24; frame-0 MAE 5.54 |
| **T2V/I2V — Hunyuan** | Video | `native_comfy_template` | ⚠️ Partial | t2v production; i2v = wrapper (CLIPVision 768-vs-1024) |
| **T2V — Mochi** | Video | `native_comfy_template` | ✅ Working | t2v-only model |
| **FLUX.3 video** | Video | hosted BFL API | ✅ Wired | Needs `BFL_API_KEY`; not local weights |
| **Flows / Workflow Library** | Workflow | `comfy_workflow` | ✅ Working | Import + discovery + dependency re-check |
| **Character Studio** | Image (+ look/clothes cmds) | T2I/I2I + worker cmds | ✅ UI wired | Rail `character`. Look-complete / clothes-only / shrinkwrap exist. Character B product gates open |
| **Comic Studio** | Image (panels) | T2I handoff | ✅ UI wired | Rail `comic`; v1 = script → stills → `page.png`. Upload→I2V is v2 |
| **Concept Reference** | Image | T2I/I2I handoff | ✅ UI wired | Rail `concept`; packs + send-to-Character |

## Shell surfaces

| Surface | Status | Note |
|---|---|---|
| **Home** | ✅ Working | Dashboard; gallery includes media without sidecars |
| **History** | ✅ Working | Image+video; KEEP/NO via `EyePickStore`; mode-aware spine polish open |
| **Settings / Prefs** | ✅ Working | `QSettings` org=DarkDuck; ArcaneGlass default |
| **Inspire** | ✅ Working | `InspirationPage` moodboard — **not** `ModePage` |
| **Models** | ✅ Working (Stage-1) | `ModelManagerPage` inventory + Inspect + import-url |
| **Runtime** (`ManagerPage`) | ✅ Working | Rail `runtime`; Comfy manager / nodes / restart |
| **Dataset Generation** | ✅ Working | Rail `dataset`; worker `generate_dataset` |
| **Train** | ✅ Launcher | Rail `train`; Sohya_kk |
| **Gen3D** | 🧩 Hidden stub | Comfy workflow passthrough only; no native 3D adapter |
| **Bottom telemetry** | ✅ Working | Themed glass strip |
| **Theme default** | ✅ ArcaneGlass | One-time migration `appearance/showcaseMaturityPass_v1` |

## Frontiers (not v1 ship-complete)

| Surface | Modality | Status | Note |
|---|---|---|---|
| **Native Image-to-3D** | 3D | 📋 Planned | Phase D D1; `Gen3DPage` is not this |
| **Native Text-to-3D** | 3D | 📋 Planned | Phase D D3 |
| **Comic upload → video** | Video | 📋 v2 | Doc 40 |
| **Long videos** | Video | 📋 No spec | |

## Infrastructure (working)

Worker TCP/JSON · job queue + `worker_service_state.py` · `RuntimeProfile` persist · non-destructive LoRA adapters · shared-weight fp16 · `SamplingController` family allow-lists · pytest harness (423 passed 2026-08-24, `PYTHONPATH=""`) · CockpitInspector adaptive width · studio scroll rails · model/node/component resolvers.

## Responsive / showcase gate

Half-screen + default restore must keep the same functionality (scroll OK; clip not OK). Cleanup map: `docs/design/30_responsive_layout_final_cleanup.md`. Owner grade C+ → S still open.

## Removed / not features

- **Rust bridge** — ❌ removed. `attic/rust_original_intent/`, unwired from CMake.
- **`VideoGenerationPage`** — dead; not in CMakeLists.
- **`ModePage`** — unused Coming-soon chrome.

## Beyond v0.1.0 (deferred)

Voice Generation · Rigging Pipeline · Asset Library · Ollama assistant · palettes Obsidian/Neon/Ivory as ship-critical. **v1.0 critical path** is shipping (guided deps / installer / first-run / Doc 28) plus remaining Arc-1 gates (license badge, Wan 2.2 dual-noise i2v) and Character B product depth.
