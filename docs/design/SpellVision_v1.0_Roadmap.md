# SpellVision v1.0 Roadmap

*Scope decision, current-state ledger, and critical path to a shippable v1.0.*
*Generated 2026-07-17. Reconcile against the existing Codebook (docs 09–18). The v1.0 release-readiness checklist is **Doc 28** (`28_release_readiness_checklist.md`) — NOT Doc 13, which is the Simple/Advanced disclosure doc (the original "Doc 13 = release-readiness" reference was stale). See also Doc 26 (families-done) + Doc 27 (v1.0 backlog).*

---

## Scope decision (the three forks — settled)

| Fork | Decision |
|---|---|
| **3D pipeline** (non-character props / TRELLIS → retopo → rig) | **v2.0** unless Character B consumes a slice |
| **Comic Studio + Character Studio** | **v1.0 — in bar (2026-08-17 lock).** Product-complete **and** Character mesh / garments / hair / beauty |
| **UI polish** (mode-aware history, palettes, glassmorphism, layout-to-mockup, upscale tiers) | **v1.0 — all in** |
| **Installer** | **v1.0 hybrid** — engines in the box, models on demand |

This is now **four** arcs: families, UI polish, shipping, and **Character product (A+B)**. Shipping is still the public-ship gate. Character B is the largest remaining product unknown.

Note: the audio pipeline stays a stub (v2.0+). Chain Studio stays nav-hidden. Character/Comic are on the rail and in the v1 bar (2026-08-17 lock).

---

## Arc 1 — Generation families (closest to done)

**Image families — CLOSED.** Pony/Illustrious, Flux, PixArt, Lumina, Z-Image, Anima all render-verified. The 4-family image arc is closed.

**Video families — substantially done, render-verified:**

| Family | T2V | I2V | Long-video (native) | License |
|---|---|---|---|---|
| LTX-2.3 (two-stage) | ✅ | ✅ | ✅ LoopingSampler | permissive |
| Wan 2.2 | ✅ | ⚠️ partial | ✅ context-windows | permissive |
| Hunyuan | ✅ | ✅ (kijai wrapper) | ✅ context-windows | ⛔ non-commercial (Tencent) |
| Mochi-1 | ✅ | — (t2v-only model) | n/a | ✅ Apache-2.0 |

**Open items for v1.0:**
- **Wan i2v** — was "partly blocked"; confirm whether the remaining gap is a real v1.0 defect or acceptable. This is the one unresolved cell in the video matrix.
- **Remaining build-order families** — decide which (if any) beyond Mochi are v1.0-required vs post-v1.0. Mochi was #5; #6+ need a scope call. Likely most are additive, not v1.0 gates.
- **Hunyuan license gating** — Hunyuan (T2V + i2v) is non-commercial. The UI must surface this clearly (license badge, and ideally a gate on commercial-use flows). Mochi is the Apache-2.0 commercial-clean video option; that distinction should be visible to users.
- **God-file decomposition** — relocating builders to `families/<x>.py` is health, not a feature. Deferrable within or past v1.0 at your discretion; it does not gate shipping.

**State: ~90% for v1.0 scope (2026-08-24).** Wan 2.1 i2v + VAE guard done. Remaining ship cells: Wan 2.2 dual-noise i2v render-proof, license badges. LTX default is distilled two-stage.

---

## Arc 2 — UI polish (all v1.0)

The shell is substantially built (Home outputs gallery, canvas fill + session strip, theme migration complete with 5 themes, lazy page construction 9.8s→3s, Simple/Advanced disclosure shipped, command palette with fuzzy matching, model library S0–S5, studio layout migration phased). What remains — pulled from the polish backlog — is the v1.0 finish:

**#12 — Mode-aware history manager (the structural one).**
Today's history *widens the video schema* to cover image+video — it works for two modes by luck ("image • 35 steps" is steps wearing duration's clothes) but has no field to borrow for future modes. Rebuild into a **core + per-mode detail-payload + per-mode renderer** spine. Even though 3D/audio are v2.0, this is v1.0 because the current widen-hack is fragile and the History multi-mode conformance rework (wave 4) depends on it. This is the largest single UI-polish item and it's backend-dependent — sequence it early.

**Palettes.** Author Obsidian / Neon / Ivory. ⚠️ Reconcile the ArcaneGlass blue-vs-shipped-violet discrepancy while doing this.

**Glassmorphism** — the glass-active states and treatment pass.

**Layout-to-mockup** — conform the Qt shell to the HTML prototype (responsive/proportions).

**Simple copy** — the Simple-mode copy pass.

**Resolution / upscale tiers** — the user-facing upscale tier selector. Note: this does **double-duty** with the post-v1.0 upscaling build and the (v2.0) 3D pipeline, so the *tier UI* is v1.0 while the deeper upscaling engine can be post-v1.0. The duration/resolution VRAM characterization already done feeds this — you know where the native res ceiling is and which base-res reaches 1080p/1440p/4K, so the tier selector can be grounded in real numbers.

**Cosmetic tail** — animations + quality-tiers, toolbar buttons, drawer square-corners (QFrame wrapper/mask). Low-risk, do last.

**State: ~70% for v1.0 scope (2026-08-24).** SamplingController + Random seed + studios/Inspire/Runtime landed. #12 is still the load-bearing open item.

---

## Arc 3 — Shipping (the true v1.0 gate)

This is what makes it "v1.0" rather than "a dev setup that works on your machine." It correctly sits *last* — you don't build the installer until there's a stable thing to install — but it's the arc that gates release, and this session **made it more complex**, so it needs explicit attention.

**Installer + uninstaller (Win/Linux).** The installer *shell* is standard tooling (Inno Setup / NSIS / WiX for Windows; AppImage or .deb/.rpm/Flatpak for Linux). The **hard spike is what it bundles**: not just the Qt exe, but a full Python 3.12 + torch/diffusers/CUDA environment + ComfyUI + the worker. Packaging a multi-GB Python+CUDA runtime that "just works" on a stranger's machine (CUDA/driver detection, Python bundling, the ComfyUI dependency) is the real engineering.

> **⚠️ New complexity from this session's ComfyUI cutover:** the bundle target is no longer the old single build. The installer must ship the **isolated-venv arrangement** (torch 2.10+cu128, **kornia pinned 0.8.2**, sageattention + triton-windows) and the **PYTHONUTF8=1 launch requirement** (the RES4LYF non-ASCII crash). The venv-decoupling (worker on project venv, ComfyUI on isolated venv, HTTP-bridged) is now part of what "install correctly" means. Doc 25 (comfyui-gated-update) is the reference; CLAUDE.md §9 was updated to reflect C:=live, D:=rollback.

**First-run wizard.** Mostly a Qt *assembly* job — most pieces already exist:
- GPU-detect-and-suggest-precision = the precision selector already specified (`gpu_info.py` + Auto-recommend + per-option explanations).
- Model-folder auto-detect = existing `AssetCatalogScanner`.
- Install-location + QSettings persistence = in place.
- Wizard UX rules already specified and worth preserving exactly: back-all-the-way / forward-only-on-choice; download list stays readable after completion, disappears only on Run.
- Load-video overlay = looping decorative video backdrop with a **real** load-progress overlay widget reading actual init state (option (a), not compositing text into video).

**Guided dependency resolution (the sharpest new dependency).** The "download the right model, in the right format, to the right folder" problem you hit **three times manually this session** (kijai t2v transformer, llava encoder, per-family VAE) is *exactly* what first-run/dependency-resolution has to automate. The epic map exists (Doc 19); the **HF-token was named as the ONE gap**. This session added concrete requirements the resolver must handle:
- **Format-awareness** — native-Comfy vs kijai-wrapper vs diffusers format are *not* interchangeable; the resolver must fetch the right *format*, not just the right *name* (the re-key dead-end proved renaming can't bridge format gaps).
- **Per-family companion models** — kijai VAE (diffusers-key), llava text encoder (15GB sharded repo), per-family text encoders. These are hard dependencies the manifest must express.
- **Placement correctness** — `models_dir` vs `extra_model_paths` base is a real trap (the LLM-encoder junction lesson). The resolver must place files where the *node* looks, not just in a plausible folder.
- **License gating** — non-commercial families (Hunyuan) vs Apache/permissive (Mochi, LTX) should be flagged at download-time, tying into the model compatibility matrix (Doc 17).

**State: ~20% for v1.0 scope (2026-08-24).** `RuntimeProfile` + a first-run diagnostic exist. Guided resolver, hybrid payload, MSI, and the real wizard are unbuilt. **This is still the critical path.**

---

## Critical path & sequencing

The arcs are not independent. Suggested order:

1. **Finish Arc 1 loose ends** (Wan i2v confirmation, remaining-family scope call, license-badge wiring). Small, unblocks a clean "families done" milestone.
2. **Arc 2 #12 mode-aware history** early (backend-dependent, unblocks History wave-4 conformance). Then the rest of UI polish in parallel with…
3. **Arc 3 dependency resolution** — build this *before* the installer, because the installer's first-run wizard *consumes* it. The format/placement/license lessons from this session are the spec.
4. **Arc 3 installer bundling spike** — the hard engineering, done once features + polish + dependency-resolution are stable. Bundle the post-cutover isolated-venv arrangement.
5. **Arc 3 first-run wizard assembly** — wire the existing pieces (precision selector, AssetCatalogScanner, dependency resolver) into the flow with the specified UX rules.
6. **Release-readiness pass** — reconcile against **Doc 28**'s subsystem gates + cut list; run the gates; ship. (Author Doc 28 EARLY in Arc 3 so it sets the bar; RUN it last — see Doc 27 Arc-3 items 9 + 13.)

**The single biggest risk to a v1.0 date** is the installer-bundling spike (multi-GB Python+CUDA+ComfyUI packaging), now compounded by the isolated-venv/kornia-pin/UTF8 arrangement. Everything else is finish-work on solid foundations; that spike is genuine unknown-difficulty engineering. Consider a de-risking probe on it early even though it sequences last — knowing whether the bundle "just works" or fights you shapes the whole v1.0 timeline.

---

## Deferred to v2.0 (explicitly banked, not lost)

- 3D pipeline (Phase D) — the full TRELLIS 2 → retopo → rig → export arc, headless-bpy backend.
- **Non-character 3D pipeline** — TRELLIS/Hunyuan prop path beyond Character B.
- Audio pipeline — currently a stub holding the history-integration cross-link.
- LLM node-orchestration — the v2+ centerpiece.
- Deeper upscaling engine — the *tier UI* ships in v1.0; the algorithm/model engine can follow (double-duty with 3D).
- ComfyUI auto-update (safety-gated) — post-v1.0 addition.
- **Comic upload → video** — upload a page/panels, crop, I2V, optional stitch. Home = Comic Studio. Spec: `40_comic_page_to_video_v2.md`. **Not now.**
- Rust engine migration (cxx-qt) — the SpellBound-Engine integration arc.

---

## One-line status per arc

*Updated 2026-08-24 against code. Scope forks above are unchanged.*

- **Arc 1 (families):** ~90% — LTX/Wan/Hunyuan/Mochi + FLUX.3 API wired; Wan 2.1 i2v ✅; **left:** license badge, Wan 2.2 dual-noise i2v render-proof.
- **Arc 2 (UI polish):** ~70% — studios + Inspire + Runtime/Dataset/Train on rail; SamplingController + Random seed landed; **left:** #12 history, upscaler engine, S-grade.
- **Arc 3 (shipping):** ~20% — `RuntimeProfile` + first-run diagnostic exist; **left:** guided deps, hybrid payload, MSI, Doc 28 run.
- **Arc 4 (Character B):** ~30% — studio UI + clothes/shrinkwrap commands; **left:** mesh/garments/hair/beauty product gates.
