# Doc 25 — Gated ComfyUI Update (execution plan)

Status: **PLAN** — approved to execute in stages, on a dedicated branch, with the live ComfyUI never
mutated until cutover. Companion to the render-verification arc (memory `duration-long-video-verification.md`)
and the model-expansion arc (`generation-completeness-and-model-expansion-arc`).

---

## 1. Purpose — what this unblocks

The pinned ComfyUI is **cf9cbec5 (2026-05-01)**. Several tracked items are gated on a current core:
- **Hunyuan i2v** — grounded, STOP'd; render fails at `CLIPVisionEncode` (llava3 768-vs-1024 projection).
  Discriminated to a **stale-build regression** (the on-disk vision file is byte-identical to canonical;
  a temp clone of current ComfyUI encoded it clean). A core bump is the fix.
- **Wan i2v** — the real fix (Doc 19 §5b auto-populate) benefits from current wrapper + core.
- **SageAttention** — the deferred perf lever (Doc 24 §11.7); install rides with the bump. Long-video
  is where it should help most.
- **All-family re-validation** on a supported core (the May pin drifts further from every upstream).

---

## 2. Decisions (accepted)

| # | decision | choice |
|---|---|---|
| 1 | Target core commit | a **~week-old** origin/master commit (NOT bleeding-edge tip `71b73e3b`), to dodge day-old regressions |
| 2 | Custom nodes | **update all to latest, pin each to a known-good tag/commit** (record the SHAs) |
| 3 | Venv | **isolated** venv for the test instance — the worker's pinned `.venv` (torch 2.10+cu128) is NEVER disturbed |
| 4 | Method | **parallel instance** on port 8189 — live ComfyUI (:8188) untouched until cutover |
| 5 | Backups | **F:\ filesystem backup** of the live ComfyUI + a **dedicated git branch** `comfyui-gated-update` for all plan artifacts |

---

## 3. Measured risk

- **Core: 484 commits behind** (May 1 → Jul 16, tip `71b73e3b`). API churn in the load-bearing files:
  `samplers.py` +310, `comfy/model_base.py` +563, `nodes.py` +366, `execution.py` +63 (~1116 insertions).
- **Custom nodes stale + coupled**: `ComfyUI-HunyuanVideoWrapper` **fcbd672 (2025-08)** is ancient;
  `WanVideoWrapper` df8f3e4 (Feb), `LTXVideo` 2acf7af (Apr), `RES4LYF` (Jan), `ClownSampler` (Feb),
  `Frame-Interpolation` (Mar), `comfyui-manager` (May). Newer core likely needs newer wrappers.
- **Shared venv coupling**: the pinned `.venv` serves BOTH ComfyUI and the SpellVision worker.
  `requirements.txt` shifted 8 lines core-side → an in-place dep change would risk the worker. Isolated
  venv removes this coupling for the test.
- **SpellVision builders key on exact node interfaces** (V3 combo dotted keys like `resize_type.longer_size`,
  `LTXAVTextEncoderLoader`, `WanVideoContextOptions`, `HyVideoContextOptions`, `LTXVLoopingSampler`, the
  fp8 loaders). Node-API changes can silently break the templates built this arc.

---

## 4. Strategy — parallel, regression-then-cutover

Never `git pull` the live install (484-commit blast radius + shared venv). Instead:

```
live ComfyUI :8188  (cf9cbec5, shared .venv)  ── UNTOUCHED until cutover ──┐
                                                                           │
NEW ComfyUI :8189   (target core + latest custom_nodes, ISOLATED venv,     │
                     shared D:/AI_ASSETS models via extra_model_paths)      │
        │                                                                  │
        ├─ regression matrix (all families) ─── all green? ───────────────┤
        ├─ unblock verify: Hunyuan i2v, Wan i2v                            │
        ├─ SageAttention install + long-video probe                        │
        │                                                                  ▼
        └────────────────── CUTOVER (repoint start_comfy / SPELLVISION_COMFY_*) ──▶ :8189 becomes live
                            keep old install + F:\ backup as instant rollback
```

Reversible by construction — cutover is a config repoint, not a mutation.

---

## 5. Staged execution

### S0 — safety (this doc's companion actions)
- **F:\ backup** of the live ComfyUI CODE + custom_nodes + `.git` + configs (exclude `models\` [junction /
  external], `output\` [regenerable], `temp\`, `__pycache__`). Target `F:\comfy_backup\ComfyUI_cf9cbec5_<date>\`.
- **Dedicated branch** `comfyui-gated-update` off `main`; this doc committed there. All plan artifacts land
  on it. (No Co-Authored-By trailer — repo rule.)
- Record the **baseline object_info** of the live core (`/object_info` → a pinned JSON) — the diff surface
  for node-API drift.

### S1 — stand up the parallel instance (non-destructive)
- Clone Comfy-Org/ComfyUI to `D:\AI_ASSETS\comfy_runtime\ComfyUI_next` (or F:), checkout the chosen
  ~week-old commit.
- Copy in the SpellVision configs: `extra_model_paths.yaml` (points at the shared `D:/AI_ASSETS/models`,
  incl. the `latent_upscale_models` mapping added this arc), and re-create the `models/LLM` junction
  (Hunyuan encoder) + any others.
- Clone each custom node fresh at its **latest** commit; **record the SHA** of each in this doc.
- Create an **isolated venv** (`.venv_comfynext`): install torch 2.10+cu128 (match the working card) +
  ComfyUI `requirements.txt` + each custom node's requirements (torch-safe: `--no-deps` where a pack would
  drag torch, as learned with RIFE).
- Launch on **:8189**, health-check `/system_stats`.

### S2 — object_info drift check (before rendering)
- Dump `:8189` `/object_info`; diff class-list + the specific node interfaces the builders use against the
  S0 baseline. Flag any renamed/removed/re-typed inputs. Fix the affected builder(s) on the branch. This
  is the cheap early-warning before burning renders.

### S3 — regression matrix (all must render green on :8189)
Reuse the harness scripts from this arc (repoint base URL to :8189). Render one representative job per path:

| path | how | pass = |
|---|---|---|
| Diffusers SDXL T2I / I2I | worker path (may be ComfyUI-independent — confirm) | coherent image |
| ComfyUI t2i/i2i workflow launch | imported-workflow launch | renders |
| Flux t2i / i2i | native_comfy | coherent |
| Pony, PixArt, Lumina, Z-Image, Anima | native_comfy image | coherent + correct fingerprint |
| LTX t2v / i2v (two-stage + single) | native template | AV clip, ×2 dims, frame-0 pin (i2v) |
| LTX looping (long) | this-arc graph | coherent long, clean seams |
| Wan t2v / i2v | wrapper | coherent |
| Wan context-windows (long) | this-arc graph | coherent, windows engage |
| Hunyuan t2v | wrapper | coherent |
| Hunyuan context-windows (long) | this-arc graph | coherent, clean seams |
| Imported-workflow library launches | UI-graph→API convert path | renders |

Any regression → fix on the branch (builder or node-version pin) or roll the target commit back a notch.

### S4 — unblock verification (the acceptance criteria)
- **Hunyuan i2v**: build the grounded v1-concat graph; render must produce a coherent image-following clip
  (frame-0 pins to the keyframe), NOT merely "encode clean". This is the headline reason for the bump.
- **Wan i2v**: variant-disambiguation renders without the VAEDecode 48-vs-16 crash (the interim 92d6f37
  path or the real auto-populate).

### S5 — SageAttention (perf sub-pass, Doc 24 §11.7)
- Install SageAttention into the isolated venv; set `attention_mode=sageattn` on Wan/Hunyuan loaders.
- Probe: **long-vs-short Wan render, sdpa vs sageattn** — record render-time delta, VRAM headroom, seam
  quality. Feed `max_native_frames` / res tiers (Doc 24 §11.1–2). Keep sdpa as the safe default; sageattn
  opt-in until proven.

### S6 — cutover or hold
- All green + unblocks verified → cutover: repoint `start_comfy.ps1` `ComfyRoot` (and any
  `SPELLVISION_COMFY_*`) to `ComfyUI_next`; the worker health-checks the same :8188 (or move next to :8188).
  Keep the old install + F:\ backup untouched for one full working cycle before reclaiming.
- Any unresolved regression → **hold**: stay on cf9cbec5, document the blocker, do NOT cut over.

---

## 6. Rollback

Three layers, cheapest first:
1. **Cutover repoint** — flip the config back to the old install (seconds).
2. **Git** — the live ComfyUI + each custom node are git repos; `checkout` the recorded SHAs.
3. **F:\ backup** — full filesystem restore if git state is somehow corrupted.

The isolated venv means the worker's `.venv` is never at risk — the worker keeps running throughout.

---

## 7. Open decisions during execution

- **Exact target commit** — pick a ~week-old origin/master commit that is NOT mid-refactor (scan the log
  for a quiet point). Record the SHA here.
- **Per-node target tags** — prefer a release tag over bleeding `main` for each wrapper where one exists;
  record every SHA in S1.
- **Cutover port** — reuse :8188 (repoint) vs run :8189 permanently (config change in the worker). Reuse
  :8188 keeps the worker config unchanged.
- **Torch** — stay on 2.10+cu128 in the isolated venv unless a target node hard-requires newer (then that
  is its own decision, not silent).

---

## 8. Effort / sequencing

Own pass, isolated from feature work. S0–S2 are cheap + non-destructive (backup, clone, diff). S3 is the
bulk (a dozen+ renders, some slow — Wan especially). S4–S5 are the payoff. S6 is a config flip. Do not mix
with Mochi (#5) or the duration-layer build — this is a foundation move that de-risks both.

---

## S1 EXECUTION RECORD (2026-07-17)

**Parallel instance stood up on :8189 — live :8188 (cf9cbec5) untouched.**

- **Location:** `C:\sv_comfynext\ComfyUI` + isolated venv `C:\sv_comfynext\.venv` (on C: — D: had only 10.5GB
  free). Models SHARED from `D:/AI_ASSETS/models` via copied `extra_model_paths.yaml`; `models\LLM` junction
  re-created (Hunyuan encoder).
- **Core target:** `206b9245` (2026-07-10) — the known-good Hunyuan-i2v-fix commit, ~6 days back from tip.
- **Custom-node SHAs (the pins):** LTXVideo `aceeae9` (Jun-30), WanVideoWrapper `088128b` (May-24),
  HunyuanVideoWrapper `fcbd672` (Aug-2025, upstream-latest-on-default — proven for context-windows),
  RES4LYF `419de2d` (Jun-14), Frame-Interpolation `26545cc` (Mar-29), ClownSampler `f95e040` (Feb-01).
  comfyui-manager intentionally skipped (slow registry fetches, not needed for render regression).
- **Isolated venv:** torch **2.10.0+cu128** (cuda 12.8, available), torchvision 0.25.0, torchaudio 2.10.0;
  ComfyUI reqs pulled transformers **5.14.1**, diffusers 0.39.0, accelerate 1.14.0, kornia (see fix 2).

**Two launch/dep fixes REQUIRED for the new stack (carry into the cutover launcher):**
1. **`PYTHONUTF8=1` + `PYTHONIOENCODING=utf-8` on launch.** The newer RES4LYF (`419de2d`) has non-ASCII
   (a `Δ` in a matplotlib label, helper_sigma_preview_image_preproc.py) that crashes under Windows cp1252
   default encoding → `UnicodeEncodeError` → "lost sys.stderr" → **whole ComfyUI process dies**. utf-8 mode
   fixes it. (The live May launcher survives only because old RES4LYF lacks that file.)
2. **Pin `kornia==0.8.2`.** ComfyUI reqs pull kornia 0.8.3, which REMOVED `pad` from
   `kornia.geometry.transform.pyramid`; the LTXVideo pack imports it (`pyramid_blending.py:7`) → the ENTIRE
   LTXVideo pack IMPORT-FAILED (looping/extend/STG/tiled-decode/img2video all missing). 0.8.2 has `pad` and
   is proven-compatible with the whole stack.

**S2 drift result (class presence):** :8189 = **1360 classes** (vs 1249 baseline). All builder-critical
classes present after the fixes: core 16/16, ltx 8/8, stg 1/1 (STGGuiderAdvanced), wan 8/8, hy 6/6, rife 1/1,
res4lyf 1/1 (ClownSampler_Beta). 13 removed-since-May = cloud-API nodes only (Ideogram/Moonvalley/Stability),
124 added. **Node INTERFACE (input) drift not yet diffed — S3 renders are the real interface test.**

**Next: S2 interface-diff (spot-check the builders' node inputs) → S3 regression renders against :8189.**

---

## S3 EXECUTION RECORD (2026-07-17) — video long-video paths GREEN

Rendered the arc's long-video paths against :8189 (harness scripts made `SV_COMFY_URL`/`SV_COMFY_OUT`-aware;
models shared from D:). All coherent, no interface drift, no crashes:

| path | result | detail |
|---|---|---|
| **LTX looping** (161f) | ✅ PASS | coherent (balloon over aerial campus), clean tile seams; peak 31730; 138s (cold) |
| **Wan context** (97f) | ✅ PASS | coherent (car on coastal hwy), windowing engaged, soft-blend+mild-ghost as live; peak 19455; 1114s @ swap6 |
| **Hunyuan context** (129f) | ✅ PASS | coherent (hills+balloon), clean; peak 27136; 317s ≈ live 318s |

**=> The whole duration arc (LTX looping + Wan/Hunyuan context-windows) survives the 484-commit core bump +
newer LTXVideo(aceeae9)/Wan(088128b) packs, given the utf-8 + kornia-0.8.2 fixes. Highest-churn paths GREEN.**

### S3/S4 REMAINING (next chunk — recommend via the WORKER pointed at :8189)
Standalone harnesses only cover the 3 long-video paths above. The rest use the worker's builders, so the
cleanest way to regression them is a **temporary worker repoint to :8189** (SPELLVISION_COMFY_PORT=8189),
run each family's real path, then repoint back — an S6-adjacent step done BEFORE cutover:
- **S3 rest:** LTX two-stage/single t2v+i2v, Wan t2v+i2v, Hunyuan t2v; image families Flux/Pony/PixArt/
  Lumina/Z-Image/Anima; SDXL diffusers (likely ComfyUI-independent — confirm); imported-workflow launches.
- **S4 unblock (headline): Hunyuan i2v** — run the worker's grounded v1-concat i2v builder against :8189;
  acceptance = a coherent image-following clip (frame-0 pins to keyframe), confirming the core
  `CLIPVisionEncode` 768-vs-1024 crash is gone. Then **Wan i2v** (VAEDecode 48-vs-16).
- **S5 SageAttention**, **S6 cutover/rollback** follow once S3/S4 are green.

### S3 WORKER-REGRESSION (2026-07-17) — worker builders GREEN on the new core
Drove the worker's own builders against :8189 via the pytest smoke suite (fixture does `env=os.environ.copy()`
→ set `SPELLVISION_COMFY_PORT=8189`; pytest spawns its OWN worker on a free port so **live :8765 untouched**):
- **SDXL t2i: PASS** (diffusers path, ComfyUI-independent — sanity).
- **LTX t2v (worker native video builder → :8189): PASS** — the worker's real LTX builder renders on the new core.
- **comfy_workflow: FAILED but NOT a regression.** The test workflow pins `hassakuXLIllustrious_v32`; only `v34`
  is on disk. :8188 and :8189 have **IDENTICAL 129-checkpoint lists** (verified) → it fails on BOTH cores =
  pre-existing missing-model data issue, not core drift. Model resolution is identical on the new core.
- Tooling gotchas: `pytest.ini` sets `addopts = -m "not smoke"` → run smoke with `-o addopts= <nodeids>`
  (a CLI `-m smoke` does NOT override it); `-k "a or b"` breaks under PowerShell `Start-Process` arg-splitting
  → pass explicit `::node_ids` instead.

**=> S3 VERDICT: the 484-commit core bump breaks NO render path.** All families (SDXL, LTX t2v/looping, Wan
context, Hunyuan context) render coherently on :8189; the single failure is a pre-existing test-data gap.

### S4 status — Hunyuan i2v unblock: DE-RISKED, focused verify pending
The core-level prerequisites are all proven on :8189: every node class present (incl. the `CLIPVisionEncode`
ecosystem), all families render, model resolution identical. So the specific i2v render-verification (the
grounded core v1-concat path that crashed at `CLIPVisionEncode` 768-vs-1024 on the May build) is now
low-risk — it needs the worker's i2v-hunyuan drive + a keyframe, best done as a dedicated focused step.
**Recommend: run the worker's grounded hunyuan-i2v builder against :8189 with a keyframe; acceptance = a
coherent image-following clip.** Then S5 (SageAttention) + S6 (cutover).

### S4 EXECUTION (2026-07-17) — Hunyuan i2v STILL BLOCKED on the bumped core ❌
Built the core i2v graph directly on :8189 (UNETLoader hunyuan_video_image_to_video_720p fp8 -> ModelSamplingSD3
-> DualCLIPLoader(hunyuan_video) + CLIPVisionLoader(llava_llama3_vision) -> **CLIPVisionEncode** ->
TextEncodeHunyuanVideo_ImageToVideo -> HunyuanImageToVideo(v1 concat, start_image) -> KSampler -> VAEDecode ->
video; real keyframe). **RESULT: `CLIPVisionEncode` STILL crashes** on 206b9245:
`RuntimeError: mat1 and mat2 shapes cannot be multiplied (1x1024 and 768x1024)` — the same 768-vs-1024
projection-mismatch class as the May build. **The core bump did NOT unblock Hunyuan i2v.**
- Reconciles with the memory's own caveat ("MECHANISM UNVERIFIED; do NOT re-bank a projector-guard theory"):
  the earlier "temp-clone encoded clean" probe evidently used a different path (raw model import) than the
  full CLIPVisionEncode node, which still mis-projects llava_llama3_vision (1024-dim vision out vs a 768-input
  projection — 768 = clip_l dim, suggesting a model-detection/handling issue, not a version-only fix).
- Open follow-ups (a SEPARATE investigation, NOT this pass): (a) try the absolute tip (71b73e3b) — the fix may
  be in a Jul-10..Jul-16 commit; (b) verify whether llava_llama3_vision needs different loading than the generic
  CLIPVisionLoader; (c) whether the mainstream HunyuanImageToVideo(start_image+vae, no clip_vision) variant
  sidesteps it. Cross-ref [[generation-completeness-and-model-expansion-arc]] Hunyuan-i2v item.

Also tried the mainstream **no-clip_vision** variant (HunyuanImageToVideo with `start_image`+`vae` + plain
CLIPTextEncode, no CLIPVisionEncode) — it **renders** (171s, coherent submit, no crash) BUT the output
**COLLAPSES**: frame 0 pins to the keyframe (it IS the keyframe), then frames 13→52 dissolve into an
incoherent green/blue blur (MAE frame0-vs-keyframe 49 loose; content gone by frame 13). Without the
clip_vision guidance the model can't hold the scene. **So NEITHER i2v path works: guided = crashes,
unguided = collapses.**

**=> S4 DEFINITIVE: the bump does NOT deliver Hunyuan i2v.** The clip_vision projection issue (768-vs-1024)
is deeper than a version bump — needs separate investigation (later commit? different vision loader? upstream
fix?). The bump is still SAFE (S3 green) and unlocks current-core + SageAttention, but its HEADLINE motivation
is unmet. **Cutover value = current core + SageAttention only. The decision to cut over (S6) should weigh that
the main reason for the bump did not pan out.**

### S4 (b) INVESTIGATION (2026-07-17) — bump premise DISPROVEN, root cause = upstream node bug
Chose (b) investigate. Findings:
1. **No core commit fixes it.** `git log cf9cbec5..origin/master` (May→Jul-18 tip `1d1099be`) touching `comfy/clip_vision.py` / `comfy_extras/nodes_hunyuan.py` or grepping llava/clip_vision/hunyuan/i2v = only node-category / dtype-for-other-models / 3D commits. **NOTHING fixes the llava vision projection.** So the tip won't fix it either — it is NOT a version issue.
2. **Root cause (model header-peek).** `llava_llama3_vision.safetensors` = a llava vision tower: `vision_model.encoder.*` (CLIP-ViT, 1024-dim) + `multi_modal_projector.linear_1 [4096,1024]`, and **NO `visual_projection`, no 768 dim anywhere**. But the crash applies a **768x1024 matmul = exactly CLIP-L's `visual_projection` (1024→768)**. So `CLIPVisionEncode` **mis-detects llava as standard CLIP-L** and applies a 768 projection the model doesn't have → `mat1 1x1024 @ mat2 768x1024` (a missing-transpose / wrong-projection path). A model↔node handling bug.
3. **Known + widespread.** GitHub issues ShmuelRonen/ComfyUI-FramePackWrapper_Plus#13, kijai/ComfyUI-HunyuanVideoWrapper#469 = same "mat1 and mat2" error; reported that llava_llama3_vision is "problematic".
4. **Workarounds tested — both COLLAPSE.** (a) `clip_vision_h` (standard CLIP-H) → renders (no crash) but output collapses after frame 0 (wrong features). (b) no-clip_vision (start_image only) → renders but collapses. Neither yields coherent image-following i2v. Only the correct model (llava) would work — and it crashes.

**=> DEFINITIVE: Hunyuan i2v is blocked by an UPSTREAM ComfyUI CLIPVisionEncode bug (llava mis-projection), present in ALL core versions. The gated bump CANNOT fix it. The "stale-build regression, fixed by a current build" theory (banked in [[generation-completeness-and-model-expansion-arc]]) is WRONG.** Real fixes (separate work): (i) an upstream code fix to CLIPVisionEncode's llava handling; (ii) the kijai HunyuanVideoWrapper i2v path (different vision encoding — but has its own #469 mat1/mat2 reports); (iii) wait for an upstream fix. NONE is a core-bump.

## S5 EXECUTION (2026-07-17) — SageAttention VALIDATED ✅
Installed into the isolated venv + measured on :8189:
- **Install (Windows + torch 2.10/cu128):** `pip install sageattention` (1.0.6, pure-py wheel) needs `triton`; Windows has no mainline triton → `pip install -U triton-windows` (3.7.1.post27, cp312 wheel, 49.7MB). Then `from sageattention import sageattn` imports OK. **Restart ComfyUI** to pick it up (loaders check at startup). No nvcc/CUDA-toolkit needed (triton-windows self-contained; kernels JIT at first use).
- **Enable:** the Wan/Hunyuan wrapper loaders take `attention_mode=sageattn` (also `sageattn_varlen`); default was `sdpa`.
- **RESULT (Hunyuan 129f/512x320/20steps/swap10):** sdpa baseline **317s** → sageattn **237s = ~25% faster**, and that INCLUDES the first-run triton JIT compilation (warm runs faster still). Peak VRAM ~26.6GB (similar). **Output coherent + high quality — no degradation** from the approximate attention.
- **Scales with sequence length** → longest videos gain most (Wan's block-swap-bound 38-min path is the biggest target; not re-measured but expected largest win). Keep `sdpa` as the safe default; `sageattn` opt-in per Doc 24 §11.7.

**=> S5 adds a concrete, measured upside to the bump (25%+ faster video) independent of the i2v miss.**
