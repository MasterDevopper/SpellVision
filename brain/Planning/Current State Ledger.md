---
title: Current State Ledger
type: planning
status: living
updated: 2026-08-24
authority: CLAUDE.md + code over FEATURE_MATRIX
source: 2026-08-24 three-reviewer audit (UI / worker / docs)
---

# Current State Ledger

Reconciled **2026-08-24** against `qt_ui/`, `python/`, `tests/`, and a Debug rebuild. Re-verify consequential claims in code before acting.

**Build:** `cmake --build build --config Debug --target SpellVision` green; `build/Debug/SpellVision.exe` timestamped 2026-08-24 13:30.

**Pytest (project venv, `PYTHONPATH=""`):** 423 passed, 2 skipped, 5 smoke deselected. Hermes `PYTHONPATH` leak breaks numpy/torch if left set.

## Green — implemented + product-wired

| Area | Notes |
|------|-------|
| Shell + theme tokens | Rail, title bar, ThemeManager, glass; **ArcaneGlass default** via migration |
| T2I / I2I cockpits | `ImageGenerationPage` Mode::TextToImage / ImageToImage; no inert IMG stub |
| T2V / I2V cockpits | Same page, video family bar Auto/Wan/LTX; preview + transport |
| LTX native AV | **Default route = `two_stage_distilled`**. Opt-in `ltx_route='single_stage_full'` |
| Wan t2v dual-noise | Production |
| Wan i2v 2.1 + VAE guard | Cell green (commit 33f631d) |
| Wan 2.2 dual-noise i2v | **Render-proven 2026-08-24** — frame-0 MAE 5.54; motion 32. `runtime/proofs/wan22_dual_i2v_2026-08-24/` |
| Hunyuan / Mochi video | Contracts mark production; Hunyuan T2V native + i2v wrapper; Mochi T2V native |
| FLUX.3 video | Hosted BFL API via `flux3_video.py`; needs `BFL_API_KEY`; not local weights |
| Chain Studio engine | Proven; `submitFn` bound. **Rail hidden** unless `SPELLVISION_SHOW_ALL_MODES=1` |
| Character / Comic / Concept | On rail; generate handoff wired |
| Clothes-only / shrinkwrap / look-complete | Worker commands wired (`clothes_only.py`, `garment_shrinkwrap.py`, `look_completion.py`) |
| Flows import/readiness | Working; dedicated QSS |
| ModelManager Stage-1 | Inventory + Inspect + bind/use + import-url |
| History | `T2VHistoryPage`; image+video; KEEP/NO via `EyePickStore` |
| Inspiration | **Real** `InspirationPage` moodboard — not `ModePage` stub |
| Runtime / Dataset / Train | On rail (`runtime`, `dataset`, `train`) |
| SamplingController | Owns 4 combos + steps/CFG/seed + Random checkbox |
| Shared-weight fp16 image path | Wired + LoRA adapter tests |
| Worker SM / TCP / queue | `worker_service.py` + state/queue/tcp; e2e lifecycle test green |
| Comfy lifecycle | start/stop/restart/ensure_running; health `/system_stats` |
| Comfy cutover | Live on `C:\sv_comfynext\ComfyUI` |
| Resolvers | Model + node + component resolvers exist and are used |

## Partial

| Area | Gap |
|------|-----|
| Wan 2.2 dual-noise **i2v** | **render-proven 2026-08-24** — see Green table |
| Hunyuan i2v | Doc 26 vs contract CLIPVision notes — live-probe still open |
| Character product depth (A+B) | Studio **UI exists**. Mesh/garments/hair/beauty **not product-complete**. `character_create.py` / `character_pack.py` unwired CLI |
| Models Stage-3 | No auto-download / full dependency-health per Model Manager spec |
| History #12 | Mode-aware core+payload+renderer still polish item |
| UI showcase grade | Owner **C+** → S; half-screen / T2V matrix still owner-eyes |
| Runtime identity | `RuntimeProfile` + persist + first-run diagnostic exist. **Not** “exe works without `run_ui.ps1`” proven |
| Shipping | Hybrid engines + on-demand models specified. No MSI. No guided-dep wizard. No clean-machine proof |
| LTX Prompt-API | Kept for history re-queue only; not default |
| Node catalog | `starter_node_catalog.json` minimal |
| `look_completion.py` | Hardcodes `C:\sv_comfynext\ComfyUI\output` — house-path residue |

## Specified / not built (or stub)

| Item | Notes |
|------|-------|
| Native 3D (T2-3D / I2-3D) | `Gen3DPage` hidden; Comfy workflow passthrough only. No native adapter/template |
| Long videos | CLAUDE.md §5: no spec yet |
| Upscaler engine (Doc 27 §2.1) | Nodes/models on disk; no family builder + UI selector |
| Palettes Obsidian/Neon/Ivory | Open |
| Comic upload → video | Doc 40 — v2 |
| Guided dependency resolver | Doc 19 — Arc 3 |
| Hybrid installer / first-run wizard | Doc 27 #11–12; Doc 28 unrun |
| `runtime_adapters/` | Files exist, **not imported** by worker |
| `VideoGenerationPage` | In tree, **not in CMakeLists** — dead |
| `ModePage` | Unused “Coming soon” stub |

## Stale surfaces (do not trust alone)

- `docs/SPELLVISION_FEATURE_MATRIX.md` — Inspire/Manager/Dataset still called stub/unreachable
- `CLAUDE.md` §6 — Inspire stub; Manager/Dataset unreachable; LTX single-stage as default
- `README.md` — “Wan production, LTX experimental”; thin test claim; broken `ARCHITECTURE.md` / Trellis/UltraShape links
- Guides listing Rust as prereq
- `runtime_paths.default_comfy_root` path
- Old “worker is a 10k god file” prose — facade ~2104
- Doc 34 internal: Inspire both stub and real
- Full Roadmap 0.1→2.0 video-at-v0.5 timeline

## Related

[[Contradiction Ledger]] · [[Acceptance Evidence Ledger]] · [[v1.0 Roadmap Synthesis]] · [[Planned Additions]] · [[Worker Facade Split]]
