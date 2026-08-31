# 37 — Phase-1 product completion (owner wave closed)

**Date:** 2026-07-25  
**Build:** Debug `SpellVision.exe` linked clean  
**pytest:** 138 passed, 1 skipped, 5 deselected, 1 xfailed  

This closes the **owner-approved product surface wave** (mockup Option D + Doc 33/34 additions + fix waves 35–36).  
**Not** in this completion set: full installer / first-run shipping arc (~15% — Doc 28), god-file extract, Phase D native 3D meshes without imported Comfy graphs.

---

## Product surfaces — complete for craft review

| Surface | modeId | Status |
|---------|--------|--------|
| Home | home | Live dashboard; Settings → Customize opens customize mode |
| T2I / I2I / T2V / I2V | * | Cockpit + workflow drop/load + embeddings + upscale; video components in Simple; LTX native path; optimal defaults on family/show |
| Character | character | Model/LoRA pickers; house LoRA choose; preview populate + size; suit bias packs; ref freedom denoise + IPAdapter soft path |
| Comic | comic | Model/LoRA pickers + payload |
| Concept | concept | Packs anti-bodysuit; model stack |
| Gen3D | gen3d | Comfy-only; workflow bind; TRELLIS multi-view; no QProcess spike |
| Dataset | dataset | Worker `generate_dataset` |
| Inspire | inspiration | Moodboard + send T2I/I2I |
| Flows | workflows | Import/run; feeds Gen3D workflow list |
| History | history | Media type filter (All/Images/Video) + contract filter |
| Models | models | Type/Family filters |
| **Runtime** | **runtime** | **ManagerPage wired** (was B2 orphan) — Comfy manager/nodes/restart; live root `C:/sv_comfynext/ComfyUI` |
| **Train** | **train** | **Sohya_kk launcher** for house LoRA creation |
| Prefs | settings | Theme/accent/effects/restore/home config wired (B1) |

Chain remains v1-hidden (`SPELLVISION_SHOW_ALL_MODES=1`).

---

## P0 bugs closed this arc

| ID | Item | Resolution |
|----|------|------------|
| B1 | Settings inert | Wired ThemeManager + Home |
| B2 | ManagerPage orphan | Rail `runtime` + warm cache + refresh on open |
| B3 | Comfy root → rollback D: | Prefer `C:/sv_comfynext/ComfyUI` in Manager + MainWindow managed root |
| B4 | Char/Comic silent merge | On-page pickers + blocked without checkpoint |
| Char preview | No populate / tiny | Prefix+time queue sync; large plate |
| Char suits | Bodysuit bias | Pack prompt/neg rewrite |
| Char house LoRA | No create path | Train page + Choose house LoRA |
| Char ref lock | Pose ignored | denoise floor + IPAdapter best-effort |
| Video over-eng | LTX API clutter | Hidden; components Simple; optimal defaults |
| Workflow presets | Fake | Hidden; real drop/load |
| Gen3D crash | External GPU process | Removed; Comfy workflow required |
| Mockup chrome | Rail/title | 64 / 44 tokens |

---

## Explicitly deferred (your final fixes / next arcs)

1. **Shipping** — installer, first-run wizard, clean-machine proof (Doc 28)  
2. **Gen3D E2E .glb** — needs real Trellis/Pixal/Hunyuan **Comfy custom nodes + workflow import**  
3. **True IP-Adapter node path** — soft path only; needs weights under `models/ipadapter`  
4. **God-file split** — worker / ImageGenerationPage / MainWindow modularity  
5. **Owner S-grade visual QA** — half-screen matrix per Doc 30  
6. **Chain Studio** v1 unhide when recipe UX ready  

---

## Smoke checklist for owner final pass

1. Rail: Runtime, Train, Dataset, Gen3D, Inspire all navigate  
2. Settings: theme/accent/effects/restore live; Customize → Home edit mode  
3. Runtime: Detect shows `C:\sv_comfynext\ComfyUI` (not D: rollback)  
4. Train: launches Sohya if path set; Character Advanced house LoRA pick after train  
5. T2V/I2V: components visible Simple; family Auto applies defaults; no LTX API panel  
6. Character generate → large preview without second run  
7. Gen3D: blocked without workflow; no system freeze  
8. History: Images vs Video filter  

**Ready for your final fix list.**

---

## 2026-08-17 continuation delta

This section updates the historical owner-wave snapshot above. It does not claim a clean-machine release.

- **First run:** a one-time runtime check now verifies the project Python, worker source/service, ComfyUI root, models root, and optional BFL credential. Missing required components enter an explicitly limited mode and link to Runtime setup.
- **Runtime paths:** Runtime now lets the owner choose and persist ComfyUI and models roots under `QSettings` keys `runtime/comfyRoot` and `runtime/modelsRoot`. Environment variables keep highest precedence. Generation output, workflow launch, runtime management, model inventory, and first-run checks consume the saved roots.
- **FLUX.3:** hosted BFL API preview routing for T2V/I2V is implemented and offline-tested. It is not represented as local/native weights. Paid owner smoke tests remain the promotion gate; see Doc 38.
- **Worker startup:** heavy Diffusers pipelines and schedulers are lazy-loaded. Five fresh-process samples measured a 1.734 s median worker import after the change, versus the earlier 6.106 s observation.
- **Current verification:** 155 passed, 1 skipped, 5 deselected, 1 expected xfail; 36 focused FLUX.3/import-budget tests passed; the Qt Debug target and `windeployqt` completed successfully.

Still deferred: a real MSI/clean-machine proof. The current `.venv` is roughly 5.8 GiB and generation also depends on ComfyUI, custom nodes, and model storage; packaging only the UI executable would be a false release artifact. Doc 28 remains the final ship gate.

---

## 2026-08-24 completion audit

Three-reviewer pass (UI / worker / docs). **Not** a clean-machine release.

- Debug `SpellVision.exe` rebuild green (13:30). Pytest **423 passed**, 2 skipped, 5 smoke deselected (`PYTHONPATH=""`).
- Inspire / Runtime / Dataset / Train are **on the rail**. CLAUDE §6 and FEATURE_MATRIX calling them stub/unreachable are stale.
- LTX production default is **`two_stage_distilled`**, not single-stage-full.
- `SamplingController` + Random seed are landed (Doc 27 §2.2 / §2.3).
- Character/Comic/Concept studios exist and generate. Character B (mesh/garments/hair/beauty) is **not** product-complete.
- Open ship path unchanged: Wan 2.2 dual-noise i2v render-proof → license badge → runtime-identity proof → guided deps → hybrid MSI → Doc 28.

Living plan: `brain/Planning/Current State Ledger.md` + `docs/design/27_v1.0_task_backlog.md`.
