# Doc 18 — Part B: 9-Model Integration Scoping & Build Plan

> **Status: survey complete (2026-07-07). No code changed — this is the map that sequences Part B.**
> Part B of the [generation completeness + model-expansion arc]; Part A (Doc 17) is done, base is
> ready. Surveyed live via 4 parallel agents (registry, adapters+Wan, node-deps, Qt-side).

## The 9 models (regrouped after survey)

**Mochi verdict: it is a VIDEO model** (`model_registry.py:133` `task_family="video"`, repo
`genmo/mochi`, node `ComfyUI-MochiWrapper`). It moves out of the image group.

- **Image (6):** Pony, Flux, PixArt, Lumina, Z-Image, Anima
- **Video (3):** Wan, Hunyuan Video, Mochi

Already registered: **Flux** (image, diffusers, done), **Wan** (video, `production`), **Hunyuan
Video** + **Mochi** (video, `detected`/gate-blocked). Net-new registration: **Pony, PixArt, Lumina,
Z-Image, Anima** (all image).

---

## 1. What one integration touches — current vs. clean target

Model discovery is **already generic**: the UI scans `<root>/checkpoints` (`AssetCatalogScanner::
scanImageModelCatalog` ~`:293`) — a new checkpoint just appears; family is an inferred string, not a
gate. **Image models are UI-free.** Registration = **3 hand-kept dicts** (`MODEL_FAMILIES`
`model_registry.py:43` + `DEFAULT_VIDEO_RUNTIME_HINTS` `:12` + `VIDEO_FAMILY_CONTRACTS`
`video_family_contracts.py:47`), each a self-contained entry — no unified register call.

| Layer | Isolated today? | Where it smears |
|---|---|---|
| Registry (`model_registry.py`, ~152 lines) | ✅ per-entry, small file | — |
| Video **adapter** (`video_adapters/<fam>_adapter.py`) | ✅ per-family file | — (adapters only *tag/normalize*; they don't build the graph) |
| Video **graph builder** (`_build_native_<fam>_video_prompt`, ~130 lines each) | ❌ | **inside `worker_service.py`** (7481-line god-file) + a growing `if family.startswith(...)` dispatch (`_build_native_split_video_prompt:4948`, branch `:4979`) |
| Image **pipeline loader** (`build_pipelines:2869` / `memory_optimization.build_paired_pipelines:637`) | ❌ | growing `if detected == "flux"/…` in the worker |
| Video **UI** (family enum, segmented bar, LTX/Wan panels) | ❌ | **`ImageGenerationPage.cpp`** (5200-line god-file, on the split list): `enum VideoFamily{Auto,Ltx,Wan}` (`.h:259`), ~200-line LTX panel (`:955-1150`), Wan split rows (`:4909-4957`) |

**The adapter/registration pattern (video, LTX = the template-to-follow):** (1) `video_adapters/
<fam>_adapter.py` subclass (`family`, `required_nodes`, `score`, `prepare_request` — `base.py:16-32`);
(2) repo-owned template JSON (`video_templates/ltx_av_native.json`, 31 nodes); (3) a
`_build_native_<fam>_video_prompt` builder branch in `worker_service.py` (~`:4812` for LTX); (4) one
line in `video_adapters/registry.py:12`; (5) a **`production`** `VideoFamilyContract` (anything else is
gate-blocked). The adapter *tags*; the worker builder *constructs* the graph — a deliberate two-part
split, but the builder currently lives in the god-file.

---

## 2. Per-model triage

| Model | Group | Backend | Effort | What it touches | Node-deps (catalog?) | Blockers |
|---|---|---|---|---|---|---|
| **Pony** | image | diffusers (SDXL finetune) | **near-free** | registry entry only; worker-side; **no UI** | none (diffusers) | Civitai weights; must trip `"xl"` detection (`detect_pipeline_type:2621`) or add a `pony` token, else mis-loads as SD1.5 |
| **Flux** | image | diffusers (registered) | **moderate** | new `flux` branch in `memory_optimization` (single-file/`from_pretrained` + `FluxImg2ImgPipeline` companion + flow-matching kwargs); no UI | none if diffusers; Flux comfy nodes **NOT** in catalog | raises today (`memory_optimization.py:732`); HF-gated repo (token); T5+CLIP+VAE assembly; no negative prompt |
| **PixArt** | image | diffusers (DiT) | **high** | new DiT loader (`PixArtSigmaPipeline`) + detect token + i2i companion (may not exist) in `build_pipelines` | none (diffusers) | own pipeline class; shared-weight `from_pipe` trick doesn't apply to DiT; HF weights |
| **Lumina** | image | diffusers (DiT) | **high** | same shape as PixArt (`LuminaText2ImgPipeline`) | none | own pipeline class; HF weights |
| **Z-Image** | image | diffusers? | **high + re-survey** | new loader | none (or comfy if no diffusers class) | **verify a diffusers pipeline exists** (recent model) before committing to the diffusers path |
| **Anima** | image | **unknown** | **high + re-survey** | TBD | TBD | **verify what Anima is** (arch/distribution/diffusers support) — most ambiguous of the nine |
| **Wan** | **video** | native template (partly done) | **t2v DONE; i2v moderate** | Wan i2v keyframe→conditioning graph (unblock 4 raise sites) + adapter i2v prep; Wan UI exists | WanVideoWrapper ✅ | the i2v conditioning graph (LTX has the pattern); Wan weights |
| **Hunyuan Video** | **video** | native template (`detected`, blocked) | **high** | full LTX-pattern: adapter + template JSON + builder (smears worker) + flip contract → `production` + **Qt video-family smear** | HunyuanVideoWrapper ✅ (core) | build+ground the template from `/object_info`; the Qt enum/panel smear; weights |
| **Mochi** | **video** | native template (`detected`, blocked) | **high** | LTX-pattern (as Hunyuan) | MochiWrapper ✅ (core) | template build; Qt smear; weights |

**Weight sources** (`model_sources.py` is a per-request materializer — HF repo / Civitai / URL /
local, `parse_asset_reference:59` → `materialize_asset:195`): PixArt/Lumina/Z-Image = HF repos;
Pony/Anima = Civitai/local; Flux = HF-gated (token). *`model_sources` locates weights but does NOT
guarantee a runnable pipeline* — the diffusers pipeline class is the real cost for bespoke image models.

---

## 3. Wan's real current state (partly-done, not from-scratch)

- **t2v GENERATES** — two builder routes: core (`_build_native_wan_core_video_prompt:4555`, the default,
  `_should_use_native_wan_core_route` currently always True) + wrapper (`:4671`, WanVideoWrapper path).
- **i2v RAISES at 4 sites** — `worker_service.py:4557` (core), `:4680` (wrapper), `:5167` (the primary
  gate in `run_native_split_stack_video`, which carves out LTX and blocks Wan i2v before any builder),
  `:5447` (diffusers path). The contract *claims* `tasks=("t2v","i2v")` but there is no i2v
  image-conditioning graph.
- **So Wan i2v = the LTX-pattern keyframe→conditioning chain + upload bridge** (LTX already has it:
  `LoadImage` → `LTXVImgToVideoConditionOnly` → bypass flag). The adapter/contract/routing/t2v scaffold
  all exist. `attic/debug_dumps/wan_node_object_info.json` is the grounding `/object_info` dump (not
  loaded at runtime).

## 4. Node-dependency coverage

`starter_node_catalog.json` = **6 packages**, all video: LTXVideo, WanVideoWrapper, CogVideoXWrapper,
HunyuanVideoWrapper, MochiWrapper, TeaCache. The resolver (`node_dependency_resolver.py`) **really
installs** (`apply_node_install_plan:127-176` → ComfyUI-Manager `cm-cli` / `git clone`).

- **Covered** (auto-install): Wan, Hunyuan, LTX, Cog, **Mochi** core wrappers.
- **NOT covered** (need catalog entries): **Flux** (only a TeaCache `model_families` tag, no node pack),
  **IPAdapter, Florence2, VideoHelperSuite, rgthree, ComfyUI-GGUF, UltimateSDUpscale, Impact-Pack,
  ControlNet-Aux, RIFE/FILM VFI, MMAudio** — each recurs in 12–16 of the 81 imports.
- **Caveat:** the **native template** path (Wan/Hunyuan/Mochi) needs only the core wrapper (covered).
  The companion gaps bite only the arbitrary **imported-workflow** (`comfy_workflow`) path.
- **⚠ Two resolver bugs to fix BEFORE Hunyuan (pre-Hunyuan fix):** (1) TeaCache's broad `model_families`
  produces a **0.2 false-positive on ~every node** (414/415 install actions mis-attributed to TeaCache;
  only ≥0.7 pattern hits are trustworthy — `_resolve_class_name:232-235`); (2) the scanner's small
  `BUILTIN_COMFY_CLASS_NAMES` allow-list (`workflow_scanner.py:16-43`) flags core classes (`Note`,
  `Reroute`, `PreviewImage`, `EmptySD3LatentImage`) as custom, inflating the missing-node lists.

---

## 5. Smear verdict + the isolation seams

**Verdict: PARTIALLY isolated.** Adapters + registry are isolated; **graph builders smear
`worker_service.py` and video UI smears `ImageGenerationPage.cpp`** (both god-files on the split list).
**Correction to the premise: Pony (model #1) is the CLEAN case — it touches nothing to isolate**
(SDXL diffusers path + generic picker). So the structure decision can't be "made on Pony"; the seams
must be established **just before the first model that needs each:**

- **Seam A — per-family image-loader (before PixArt):** a small `image_pipelines/<fam>.py` (or a
  loader-fn registry) that `build_pipelines` dispatches to, instead of a growing `if detected==…` chain.
- **Seam B — builder-in-adapter (before Hunyuan):** add `build_prompt(req, object_info)` to the
  `VideoFamilyAdapter` interface so each family's graph builder lives in its **own file** and
  `worker_service.py` dispatch becomes a thin `adapter.build_prompt(...)`.
- **Seam C — data-driven video-family UI (before Hunyuan):** drive the family list + launch-option
  fields from the registry/a descriptor table, replacing the hardcoded `enum VideoFamily` + inline
  ~200-line panels in `ImageGenerationPage.cpp`.

**These seams pair with the god-file-decomposition arc** — the LTX/Wan panels (`ImageGenerationPage`)
and the `_build_native_*` builders (`worker_service.py`) are the shared extraction targets. **Do them
in coordination, not twice.** Goal achieved once the seams exist: *add a model = a new isolated module
+ one registration line, touching no god-file.*

## 6. Confirmed build order

1. **Pony** — near-free SDXL finetune; proves the clean registry-only image path (no seam needed).
2. **Wan i2v** — completes an already-`production` family; cheapest video win (LTX i2v = the template).
   *First video-builder work → establish Seam B here.*
3. **Flux** — bounded diffusers branch; high value. *First bespoke-image loader → establish Seam A here.*
4. **Hunyuan Video** — full LTX-pattern native family. *Establish Seam C here (biggest UI smear); fix the
   2 resolver bugs first.*
5. **Mochi** — LTX-pattern, inherits Hunyuan's video seams.
6–9. **PixArt → Lumina → Z-Image → Anima** — bespoke DiT image, inherit Seam A; **re-survey Z-Image +
   Anima** for real diffusers support before committing.

*(Adjustment vs the arc note's original order: Mochi is video not image; Wan i2v jumps to #2
[partly-done, cheapest video]; the structure seams are pinned to the first model that needs each,
not to Pony.)*

Each model is its own gated integration (loads → generates → sidecar correct). Start with **#1 Pony**.
