# 34 — Owner-approved additions implementation status

**Date:** 2026-07-25  
**Build:** Debug `SpellVision.exe` linked clean after Dataset + rail + Models filter + sampler pass.

## Done this session (compiled)

| Item | Status | Notes |
|------|--------|-------|
| **A3 Rail icons** | ✅ | Wired SVG under-icon rail buttons; new icons for character/concept/comic/gen3d/dataset; icons copied to `build/Debug/icons/` |
| **A4 Models filters** | ✅ | Type + Family combos + search + favorites; grid proxy + tree both filter |
| **A8 More samplers/schedulers** | ✅ | Expanded image + video combo lists (Comfy-style names) |
| **A2 Inspiration unhide** | ✅ partial | Removed from `kV1HiddenModes` — still `ModePage` stub content (real moodboard next) |
| **A1 Dataset page wired** | ✅ | Header + page rewrite; CMake; rail `dataset`; MainWindow → worker `generate_dataset`; merges T2I model; blocks if no checkpoint |

## Done after recon batch (compiled)

| Item | Status | Notes |
|------|--------|-------|
| **A2 Inspiration real page** | ✅ | `InspirationPage` moodboard (OutputCardModel), prompt/neg edit, Send→T2I/I2I |
| **A9 Gen3D page** | ✅ MVP | `Gen3DPage` rail `gen3d`; Pixal3D/TRELLIS.2 via spike QProcess; stages basename correctly; honest missing-tool; copies `.glb` to `runtime/meshes` |
| **B4 Character/Comic model pickers** | ✅ | On-page CatalogPicker + payload `model`/`loras`; generate blocked until checkpoint; project save/load |
| **A5 Workflow drop/run** | ✅ | Cockpit drop zone + Load/Run; MainWindow `import_workflow` → draft + optional queue launch with model override |
| **A6 Upscale** | ✅ | Advanced Output: enable + method (lanczos/nearest/bilinear/model) + scale + model combo; worker `maybe_apply_request_upscale` on t2i/i2i |
| **A7 Embeddings** | ✅ | Advanced Output: +Pos/+Neg TI pickers; inject names into prompt/neg + payload arrays |
| **Mockup chrome** | ✅ | Rail width 64, title bar 44 via ThemeManager Chrome tokens |

## Critical recon corrections (do not mis-integrate)

### Sohya_kk is **not** a synthetic dataset generator
- **Sohya_kk** = LoRA / DreamBooth / TI **trainer** UI over kohya_ss (ZIP/folder dataset prep for training).
- **SpellVision Dataset** = **prompts → many T2I jobs** via existing `worker_service.QueueManager.enqueue_dataset`.
- Integration choice: **wire SpellVision generator now**; optional later “Train with Sohya” launch for LoRA studio (separate product surface).

### 3D (A9) — spike ready, page not started
- Pixal3D + Trellis2 live under spike paths / SpellBound ADR-0051; Character Studio probes partially.
- Need dedicated `gen3d`/`i23d` page + worker command + path fixes (basename vs full path, OUT_PATH, Trellis backend index).
- Icon `gen3d.svg` already in rail map for when page lands.

### Cockpit power still open
- **A5** Workflow drop/run on generation pages  
- **A6** Upscale (model + algorithmic) UI+worker path  
- **A7** Embeddings pos/neg TI  
- **A2 full** Inspiration moodboard (send-to-T2I from recent outputs)

## How to smoke what landed
1. `Stop-Process SpellVision`; run `.\scripts\dev\run_ui.ps1` (or Debug exe).
2. Rail shows **icons under labels**; **Inspire** + **Dataset** entries visible.
3. Models: Type/Family dropdowns filter grid + list.
4. T2I Advanced: longer sampler/scheduler lists.
5. Dataset: pick model on T2I first → Dataset → prompts → Generate → queue fills with N jobs.

## Next implementation order (recommended)
1. Inspiration real page (recent outputs + prompt + send T2I)  
2. Character/Comic on-page model pickers (B4 P0)  
3. Workflow drop zone on cockpit + “Run workflow”  
4. Embeddings + upscale controls + worker apply  
5. Gen3D page (Pixal3D first E2E .glb)  
6. Optional Sohya launch for train path  
