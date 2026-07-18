# Doc 26 — Arc 1 "Families Done" Milestone

*Scope-only. Turns the roadmap's Arc-1 loose ends into a checkable milestone. Grounded against the live tree + `/object_info` on 2026-07-18. Companion to `SpellVision_v1.0_Roadmap.md` (Arc 1) and Doc 17 (compatibility matrix).*

---

## 0. Milestone definition

**"Families done for v1.0"** = the generation-family matrix is complete enough to ship, every built family is render-verified, the one open video cell (Wan i2v) has an explicit accept/fix decision, and license status is surfaced in the UI. It does **not** require every conceivable model — additive families are explicitly post-v1.0.

---

## 1. Current matrix (grounded)

**Image — CLOSED.** SDXL/Pony/Illustrious, Flux (t2i+i2i), PixArt-Σ, Lumina 2.0, Z-Image Turbo, Anima — all render-verified, product-surface-verified. The 4-family image arc + Pony + Flux = 6 image families done.

**Video:**

| Family | T2V | I2V | License | Notes |
|---|---|---|---|---|
| LTX-2.3 | ✅ | ✅ | permissive | distilled two-stage default |
| Wan 2.2 | ✅ (dual-noise) | ⚠️ **see §2** | permissive | single-model 2.1 i2v works; 2.2 dual-noise i2v NOT wired |
| Hunyuan | ✅ | ✅ (kijai wrapper) | ⛔ non-commercial (Tencent) | i2v render-verified this era (commit eeb4d03) |
| Mochi-1 | ✅ | — (t2v-only model) | ✅ Apache-2.0 | commit 0fabe6a |

**The entire planned build-order (Doc 18: Pony→Wan-i2v→Flux→Hunyuan→Mochi→PixArt→Lumina→Z-Image→Anima, 9 items) is DONE.** There are no unbuilt families *in the plan*.

---

## 2. Wan i2v — the one open cell (investigated, NOT fixed)

**Actual state (read from `worker_service.py` + on-disk header-check):**
- **Single-model Wan 2.1 i2v = WIRED + render-verified.** `_build_native_wan_core_video_prompt` has an i2v branch (`WanImageToVideo`, conditional `clip_vision`); admitted to the i2v carve-out; commit af0396c, frame-0 MAE 3.54. On-disk `wan2.1_i2v_480p_14B_fp16.safetensors` is the correct native-Comfy format (`blocks/img_emb/text_embedding`).
- **Dual-noise Wan 2.2 i2v (the A14B MoE flagship) = NOT wired.** Only dual-noise *t2v* exists (`_build_native_wan_dual_noise_video_prompt`). The single-model builder **refuses a dual-noise half** by design (worker_service.py:5337 guard). The i2v experts `wan2.2_i2v_high/low_noise_14B_fp8_scaled.safetensors` are on disk, unused.
- **Known footgun (arc memory):** the shared VAE resolver prefers `wan2.2_vae` (48-ch) which mismatches Wan 2.1's 16-ch VAE — single-model 2.1 i2v needs the matched `wan_2.1_vae` explicitly in the stack, else a channel-mismatch failure.

**Is it a real v1.0 defect?** Partial. The Wan i2v *cell* is functionally satisfied by the single-model 2.1 path (a real, render-verified i2v). What's missing is the **flagship 2.2 dual-noise i2v** (higher quality). Two honest options:

| Option | Scope | Recommendation |
|---|---|---|
| **A — Accept single-model 2.1 i2v as the v1.0 Wan i2v** | Zero build. Fix only the VAE footgun (force `wan_2.1_vae` when the 2.1 i2v model is selected — a one-line resolver guard). | **Recommended for v1.0.** The cell is green; 2.2 dual-noise i2v is a quality upgrade, not a gap. |
| **B — Wire Wan 2.2 dual-noise i2v** | Mirror the dual-noise **t2v** builder + graft the single-model i2v conditioning (`WanImageToVideo`; the conditioning enters ONCE and is shared by both expert stages, not per-expert). Bounded (both halves on disk), but a real build + render-verify. | **Scheduled as an Arc-1 build task** (Doc 27 §Arc-1 item 2). |

**DECISION (recorded): BOTH.**
- **Option A — DONE + committed (`33f631d`).** The VAE version-match guard: for a Wan 2.1 primary, force `wan_2.1_vae` + strip a mismatched explicit 2.2 VAE (2.2 single-file untouched). Verified dry-run. The Wan i2v cell is **green now** via single-model 2.1 + this guard.
- **Option B — scheduled as a real Arc-1 BUILD task** (Doc 27 §Arc-1 item 2): wire Wan 2.2 dual-noise i2v (the flagship quality upgrade). Full grounded scope (base builder, where the image conditioning enters, routing widen, experts on disk, FAST-verify, gate bar) lives in Doc 27 — not a footnote.

---

## 3. Remaining build-order families (#6+) — scope call

The planned 9 are done, so "beyond Mochi" means **net-new** families, not leftovers:
- **CogVideoX** — present in `video_family_contracts` as `validation_status="detected"` (recognized, no validated route). **Post-v1.0 additive.** Not a v1.0 gate.
- **Additional community video models** (SkyReel, LTX variants, Wan finetunes on disk) — the native-family pattern makes each a manifest-row + builder, but none are v1.0-required.
- **Additional image checkpoints** — surface automatically via the classifier + Model Library; no per-model build needed.

**Recommendation:** v1.0 families are **feature-complete**. Everything beyond the built set is additive and post-v1.0. No #6+ family gates v1.0.

---

## 4. License-badge wiring (scope, don't build)

**Data already exists:** `ModelFamilySpec` carries `commercial_use` / `auto_download` / `license_note` (added in the Anima work). The gap is **surfacing** it.

Scope:
1. **Model-card badge** — thread `commercial_use` + `license_note` from the family spec through the classifier payload the Model Library already consumes → render a small badge on `ModelCard` (e.g. "Non-commercial" pill for Hunyuan; "Apache-2.0 / commercial-OK" for Mochi/LTX). Cosmetic + data-plumbing; no new model logic.
2. **Commercial-use flag / gate** — a Settings "commercial use" toggle; when on, non-commercial families (Hunyuan) show a warning at select/generate time (soft gate, not a hard block — the user owns the call). Ties to Doc 17's compatibility matrix as the license source of truth.
3. **Video families** — `video_family_contracts` also encodes license in `readiness_notes`; reconcile so the badge reads one source (prefer the family spec / Doc 17 matrix, not prose notes).

**Don't build.** This is a data-plumbing + small-UI task; scoped into Doc 27 Arc-1.

---

## 5. God-file decomposition — health, OUT of the bar

Relocating `_build_native_*` builders to `families/<x>.py` + threading `resolve_stack→builder` uniformly (Hunyuan is the reference impl) is **code health, not a feature**. It does not gate "families done" and does not gate shipping. **Out of the families-done acceptance bar;** deferrable within or past v1.0 at the developer's discretion. Tracked separately (god-file-decomposition memory).

---

## 6. CHECKABLE ACCEPTANCE — "families done for v1.0"

- [ ] **Image matrix:** SDXL/Pony, Flux (t2i+i2i), PixArt, Lumina, Z-Image, Anima — each renders on the product surface. ✅ (met)
- [ ] **Video matrix:** LTX (t2v+i2v), Wan t2v, Hunyuan (t2v+i2v), Mochi t2v — each render-verified. ✅ (met)
- [x] **Wan i2v decision = BOTH** (Doc 27 §Arc-1): Option A (VAE version-match guard) **DONE `33f631d`**; Option B (wire 2.2 dual-noise i2v) **tracked as an Arc-1 build task**. Cell is green via 2.1+guard; B is the tracked flagship upgrade.
- [ ] **No unbuilt family blocks v1.0** — CogVideoX + others confirmed post-v1.0 additive. ✅ (met)
- [ ] **License surfaced:** every model card shows commercial/non-commercial status; non-commercial families warn on commercial-use flows. ☐ (scoped, not built)
- [ ] **Option B built** — Wan 2.2 dual-noise i2v render-verified to the i2v bar. ☐ (Arc-1 build task, Doc 27 item 2)
- [ ] **God-file decomposition explicitly excluded** from this bar. ✅ (recorded)

**Status:** matrix ✅, Wan-i2v-decision ✅ (A done, B tracked), license-surfacing ☐, Option-B-build ☐. Remaining checkable items: license surfacing + the Option-B dual-noise-i2v build — both in Doc 27's Arc-1 head.
