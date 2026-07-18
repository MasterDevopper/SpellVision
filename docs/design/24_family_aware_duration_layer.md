# Doc 24 — Family-Aware Duration Layer (design)

Status: **DESIGN ONLY** (no pipeline code committed). Grounded in the render-verification arc
(sessions 1–4) captured in memory `duration-long-video-verification.md`. Every per-family claim below
was verified live, not assumed.

---

## 1. The one promise

> User states **how many seconds** of video they want. SpellVision picks the right per-family
> long-video mechanism, wires it, sets its parameters, caps it to VRAM, and renders — **the user never
> learns "context windows", "looping sampler", "temporal tiling", "adain", or "block swap".**

That abstraction *is* the feature (CLAUDE.md §1). This doc specifies the layer that delivers it across
all video families, on evidence.

**Non-goal:** a per-family bespoke UI. One duration concept, family-agnostic surface, family-specific
resolution underneath (mirrors the Simple/Advanced global system, Doc 13).

---

## 2. Three levers — never conflate them

The whole arc proved these are **three separate tools for three separate goals**. The layer must keep
them distinct in the model AND the UI:

| lever | user intent | tool | NOT |
|---|---|---|---|
| **Duration** | "make it longer (more seconds)" | native long-video (looping / context-windows) → i2v-chain beyond ceiling | ✗ not fps, ✗ not resolution |
| **Resolution** | "make it sharper / full-screen" | native base-res + built-in upscalers (Doc: VRAM sweep) | ✗ not duration |
| **Smoothness** | "make motion silky" | RIFE frame-interpolation (fps↑, same seconds) | ✗ adds NO duration |

RIFE was explicitly verified to **not** extend duration (more frames, same wall-clock). Surfacing it as
a "Smoothness" finish, never a "longer" control, is a hard rule.

---

## 3. Evidence base (what is verified)

All three families ship a **native in-loop long-video mechanism** and all three **render-verified**
coherent long video. RIFE tested. This is the factual floor the design stands on.

| family | native mechanism | render-verified | seam quality | headline gotcha |
|---|---|---|---|---|
| **ltx** | `LTXVLoopingSampler` (video-only graph) | ✅ 361f/15s | **cleanest** (adain holds drift) | rejects AV latents → needs a video-only graph, distinct from the AV two-stage |
| **hunyuan** | `HyVideoContextOptions` | ✅ 129f/5.4s | **clean, highest visual quality** | needs **kijai-format** transformer + **core** VAE nodes + `quantization=disabled`; **license-gated** |
| **wan** | `WanVideoContextOptions` (+RIFLEx, framepack) | ✅ 161f/10s | soft-blend, mild window-ghost | wrapper rejects fp8-scaled umt5 → core `CLIPLoader(wan)`+bridge; block-swap tuning |

Seam-quality ordering: **LTX ≈ Hunyuan (cleanest) > Wan.**

RIFE: installed torch-safe. (a) general 24→48fps = clean, same duration. (b) seam-smoothing = a
**morph-bridge** — softens a hard join, does **not** repair it. Verdict: **polish on native paths
(all blend in-loop), load-bearing only on the cruder i2v-chain fallback.**

i2v-chain (last-frame → i2v-continue → stitch): render-proven for **LTX**; **Wan i2v partly blocked,
Hunyuan i2v blocked at render** (per `generation-completeness-and-model-expansion-arc`).

VRAM/time (from the sweep + these renders): native duration is **bounded-VRAM per tile/window** (the
structural win — length grows, VRAM stays flat, time scales sub-linearly). Single-clip generation hits
the 32GB wall as size grows; native long-video trades that wall for gentle time growth.

---

## 4. Architecture — where the layer lives

Five seams, each already existing in the codebase:

1. **Contract (data).** Extend `VideoFamilyContract` (`python/video_family_contracts.py`) with a
   `duration` capability block (§5). Declarative, per-family. This is the single source of truth the
   UI, resolver, and readiness all read.
2. **Resolver (worker).** A `DurationResolver` maps **intent (seconds, fps, quality)** → **per-family
   render params** (which mechanism, window/tile size, overlap, adain, block-swap, frame count) → a
   request the native builder consumes. Pure function over the contract + a VRAM budget.
3. **Backend builder (native_comfy_template).** Each family's native long-video graph is a builder,
   plugged via the **`NativeFamilyPlugin` FamilySpec seam** (`god-file-decomposition-refactor`,
   commit 9679114). LTX = a new **video-only looping builder** (distinct from the AV two-stage);
   Wan/Hunyuan = context-window builders. A `duration_mode` on the request routes to the long-video
   builder vs the single-clip builder.
4. **Fallback (composition).** Beyond a family's native ceiling → **i2v-chain via Chain Studio**
   (the reusable composition spine, `phase-d-3d-chain-studio-spine`). Chain: render clip → last frame
   → i2v-continue → stitch → **RIFE at the seam** (here RIFE is load-bearing).
5. **Finishing (optional).** RIFE as a post-decode pass (`ComfyUI-Frame-Interpolation`, installed),
   exposed as "Smoothness".

```
[Cockpit: Length=Ns, Smoothness=on, Quality]   ← intent (Simple)
        │
        ▼
  DurationResolver  ──reads──▶  VideoFamilyContract.duration  (per-family capability + params + gotchas)
        │                          + VRAM budget (res×length, from the sweep)
        ▼
  is N ≤ native_ceiling(family, res)?
   ├─ YES → native long-video builder (looping | context_windows)  ──▶ ComfyUI /prompt
   └─ NO  → Chain Studio i2v-chain (K native clips stitched) ── RIFE at seams ──▶ output
        │
        ▼
  Smoothness? → RIFE fps pass (post-decode)
```

---

## 5. Data model — `DurationCapability`

Add to each `VideoFamilyContract` (fields chosen from what actually varied across the verified
families — nothing speculative):

```python
@dataclass(frozen=True)
class DurationCapability:
    native_long_video: bool            # True for ltx/wan/hunyuan
    mechanism: str                     # "looping" | "context_windows" | "none"
    # the tunables the resolver sets (names are the ComfyUI node inputs, kept internal):
    window_frames: int                 # LTX temporal_tile_size / Wan|Hy context_frames
    window_overlap: int                # temporal_overlap / context_overlap
    drift_control: str                 # "adain" (LTX) | "window_blend" (Wan/Hy) | ""
    seam_quality: str                  # "clean" | "soft" | "cruder"
    # ceilings — MEASURE per family before trusting (see §11):
    max_native_frames: int             # coherence/VRAM ceiling for native single-pass-of-windows
    fps: float                         # 24 (ltx/hy) | 16 (wan) — native output rate
    # fallback + finishing:
    fallback: str                      # "i2v_chain" | "none"   (Chain Studio path)
    finishing_rife: bool               # RIFE applicable (all True; polish)
    # provisioning gotchas — as DATA so readiness/auto-populate handle them (Doc 19):
    requires_model_format: str         # "" | "kijai"   (Hunyuan: kijai-only, native-Comfy NOT loadable)
    vae_nodes: str                     # "wrapper" | "core"   (Hunyuan MUST use core VAELoader/VAEDecode)
    quantization_rule: str             # "" | "disabled_if_fp8"  (don't double-quantize an fp8 file)
    text_encoder_note: str             # "" | "core_clip_bridge" (Wan) | "llm_folder_junction" (Hy)
    license_id: str                    # "" | "tencent-hunyuan-community"  (shipping gate, §9)
```

The **gotcha fields are the payoff of the arc** — every one caused a failed render before it was
learned. Encoding them as contract data means the resolver + readiness (Doc 19 guided dependency
resolution) refuse-with-reason instead of dying deep in ComfyUI.

### Per-family values (verified)

| field | ltx | wan | hunyuan |
|---|---|---|---|
| mechanism | looping | context_windows | context_windows |
| window_frames | 80 | 81 | 65 |
| window_overlap | 24 | 16 | 4 |
| drift_control | adain (0.15–0.2) | window_blend (linear) | window_blend |
| seam_quality | clean | soft | clean |
| fps | 24 | 16 | 24 |
| fallback | i2v_chain (proven) | i2v_chain (i2v partly blocked) | i2v_chain (i2v blocked) |
| requires_model_format | "" | "" (wrapper-format ok) | **kijai** |
| vae_nodes | core (LTX video VAE) | wrapper (WanVideoVAELoader) | **core** |
| quantization_rule | "" | "" | **disabled_if_fp8** |
| text_encoder_note | gemma loader | **core_clip_bridge** | **llm_folder_junction** |
| license_id | "" | "" | **tencent-hunyuan-community** |

---

## 6. Resolver logic (intent → params)

`DurationResolver.resolve(family, seconds, quality, res, smoothness) -> RenderPlan`:

1. `frames = round(seconds * fps)` snapped to the family frame law (LTX/Wan/Hy all ≈ 4k+1 or 8k+1).
2. `budget = vram_budget(res, frames)` from the sweep characterization (native long-video is
   bounded-per-window, so the cap is dominated by **base resolution**, not length — long is "cheap",
   big is "expensive"). Simple-mode presets pick a res tier that leaves headroom.
3. If `frames ≤ max_native_frames`: emit a **native plan** — mechanism + window_frames/overlap +
   drift_control default, block-swap sized to `budget` (learn from Wan: don't over-swap; peak had
   ~5–14GB headroom → start low, raise only on OOM).
4. Else: emit a **chain plan** — `ceil(frames / native_chunk)` native clips, i2v-continue between them,
   RIFE at each seam. Route to Chain Studio.
5. If `smoothness`: append a RIFE ×2 finish (fps→2×, duration unchanged).

RenderPlan carries the resolved node params AND the gotcha flags so the builder wires correctly
(kijai-format check, core-VAE, quantization=disabled, encoder junction, text bridge).

---

## 7. UX — Simple / Advanced (progressive disclosure, Doc 13)

**Reveals in place; never relocates (CLAUDE.md §2).**

**Simple** (intent only):
- **Length**: a seconds value or 3 presets (Short ~5s / Medium ~10s / Long ~15–20s). Presets encode
  the safe res×length budget per family.
- **Smoothness**: a toggle ("Silky motion") = RIFE ×2. Off by default.
- That is all. No window/tile/overlap/adain/block-swap/scheduler.

**Advanced** (same panel, extra rows appear):
- Window size, overlap, drift-control strength (adain / blend), block-swap, RIFE multiplier (×2/×4),
  native-vs-chain override, per-tile prompts (LTX `MultiPromptProvider` — a genuine power feature:
  narrative that evolves across the clip).

The cockpit shows a **live "≈N s at RxR, ~M min render"** estimate (the sweep + these renders give the
time model: LTX ~sub-linear, Wan slow-but-bounded, Hunyuan ~mid). Sets expectations before commit.

---

## 8. Readiness & auto-population (Doc 19 integration)

The provisioning gotchas become readiness rules:
- **Hunyuan**: greys-out with "needs the kijai-format transformer (native-Comfy model won't load)" +
  a Download/Locate action → `Kijai/HunyuanVideo_comfy`. Gate incoming models by **header-peek**
  (top-level `img_in.proj.weight` + `t_embedder.mlp.0/2` = kijai; `model.model.` prefix +
  `in_layer/out_layer` = native-Comfy = reject). Also the **LLM encoder** placement
  (`<ComfyUI>/models/LLM` — `extra_model_paths` can't redirect; junction).
- **Wan**: prefer core `CLIPLoader(wan)` + bridge (wrapper's T5 loader rejects fp8-scaled umt5).
- These are **requirements-vs-specifics** (Doc 19): the contract states the requirement (a kijai-format
  transformer), the manifest resolves the specific file, never auto-download on a guess.

---

## 9. License gating — DECIDED

**Hunyuan transformer = tencent-hunyuan-community licensed.** **DECISION: ship it behind
license-acceptance — we provide the capability, the user accepts the license to enable it.** Not
omitted, not silently bundled. The `license_id` field feeds the same license dimension already on
`ModelFamilySpec` (first used for Anima, non-commercial). Behavior:
- **Hunyuan is present as a family, gated by an explicit one-time license-acceptance** (surface the
  license, user accepts → family enabled). Until accepted, Hunyuan is visible-but-locked with a
  "review & accept license" action, not hidden.
- LTX/Wan carry no such gate — default-on.
- Rationale: SpellVision provides the capability; the licensing obligation is the user's to accept. The
  acceptance is per-machine, recorded (same store as other one-time acknowledgements).

---

## 10. Build order (when this opens; Phase C must be genuinely closed first per CLAUDE.md §5)

- **D0 — contract + resolver.** Add `DurationCapability` to `VideoFamilyContract`, fill the verified
  values, write `DurationResolver` (pure, unit-testable). No render path yet.
- **D1 — LTX native looping (first; cleanest + proven).** Video-only looping builder behind the
  FamilySpec seam; wire the Simple Length control → resolver → builder. The end-to-end milestone.
- **D2 — Wan context-windows.** Second builder; block-swap tuning; the core-CLIP-bridge text path.
- **D3 — Hunyuan context-windows (license-gated).** kijai-format gate + core-VAE + encoder junction
  encoded in readiness. Ship behind the license flag.
- **D4 — i2v-chain fallback (Chain Studio).** Arbitrary length beyond native ceilings; RIFE at seams
  (load-bearing here). Depends on i2v render-status per family (LTX ready; Wan/Hunyuan i2v gated).
- **D5 — RIFE finishing pass.** The "Smoothness" toggle, family-agnostic post-decode.

Each stage: measure → render-verify → then wire (the discipline that carried the whole arc:
install ≠ renders).

---

## 11. Open questions / risks (measure, don't assume)

1. **Native ceiling per family (`max_native_frames`).** Verified points are 15s (LTX), 10s (Wan),
   5.4s (Hunyuan) — but those were *chosen*, not the *ceiling*. Sweep each family's frame count until
   coherence breaks or VRAM bites, to set `max_native_frames` honestly (that boundary decides
   native-vs-chain).
2. **Res × length shared budget.** The sweep showed native res drives VRAM; long video is bounded.
   Need a per-family res-tier × length table so Simple presets never OOM. (Long+big is the corner that
   will bite — the sweep tested one axis at a time.)
3. **Wan speed.** 2269s was block-swap-bound (overkill @17.6GB peak). Re-measure with low/zero swap
   and the dual-expert (high+low noise) for quality — single-expert was soft. Wan may be much faster
   than the first number suggests.
4. **Hunyuan license** (§9) — a product decision, not technical.
5. **i2v-chain seam reality.** RIFE softens but morphs hard joins; native looping seams are already
   clean. Chain-fallback quality depends on i2v adherence (LTX frame-0 pins well; Wan/Hunyuan i2v
   blocked). Measure chain seams before promising arbitrary length.
6. **Model-format gating is now a general risk** (native-Comfy vs wrapper vs kijai formats). The
   header-peek gate (§8) should generalize to any wrapper-backed family.
7. **SageAttention — deferred perf lever, revisit for LONG video especially.** The Wan/Hunyuan model
   loaders already expose `attention_mode = sageattn / sageattn_varlen` (verified in `/object_info`);
   all verification renders ran the default `sdpa`. SageAttention (quantized/fused attention) cuts
   attention compute + VRAM — and **its benefit scales with sequence length**, so **longer videos are
   exactly where it should help most** (more frames × more overlapping windows = more attention work;
   the Wan 38-min pain is partly attention-bound). When SageAttention is added (package install +
   kernel), re-measure per family: (a) render-time delta on long clips vs short, (b) any VRAM headroom
   that lifts `max_native_frames` / res tiers (§11.1–2), (c) quality delta from quantized attention
   (expected negligible — confirm on seams). Folds into the D2 Wan-speed and D-series ceiling passes,
   not a separate stage. Cross-ref §11.3 (Wan speed).

---

## 12. One-paragraph summary

Extend `VideoFamilyContract` with a verified `DurationCapability` block; a pure `DurationResolver` maps
intent-seconds → per-family window params + provisioning gotchas + VRAM budget; native long-video
builders (LTX looping, Wan/Hunyuan context-windows) plug in via the existing FamilySpec seam; beyond a
family's measured native ceiling, Chain Studio stitches i2v-chained clips with RIFE at the seams; a
Simple **Length** control and **Smoothness** toggle expose the whole thing as intent, with the raw
knobs revealed-in-place in Advanced. Duration, resolution, and fps stay three distinct levers.
Hunyuan ships behind one-time license-acceptance (capability provided, user accepts). SageAttention is a
deferred perf lever to revisit for long video especially (§11.7). Build LTX-first, measure every ceiling
before wiring.
