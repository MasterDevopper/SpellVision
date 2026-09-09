# Doc 54 — Owner-chat 1.0 additions (2026-09-09)

**Status:** backlog lock, not built. **Source:** owner chat 2026-09-09.  
**Classification rule (owner):** anything **explicit 1.0** *or* **added in chat** is a **1.0 requirement**. Everything else is **v1.1+**. The ship walkthrough lists **1.0 nice-to-haves** separately. **All 1.0 requirements must be green** before ship. The walkthrough itself **requires grade S** first.

This document is the list. Do not start the walkthrough, MSI, or “1.0 complete” claim until the requirements below are green **and** the cockpit is S.

---

## 0. What this is / is not

| This is | This is not |
|---------|-------------|
| Owner-added **1.0 requirements** from chat | A go-ahead to implement all of it this session |
| Teachers to **learn from** (LoRA Manager, rgthree, SaveImageWithMetaData, Qwen LoRA loader) | Drop those packs into the product as the UI |
| PAIR + multi-GPU as a **SpellVision generation** problem | Re-using NVPAIR’s LLM cluster as if it already splits Comfy |

**Already in tree (do not re-spec as blank):** Doc 46 workflow pack resolver + pinned GitHub zipball installs; Doc 52 model identity / Civitai variant dialog; Train rail = Sohya_kk **launcher**; Models Stage-1 inventory; video `applyOptimalVideoSamplingDefaults`; LTX/Wan family OP tables; sageattention / DynamicVRAM / fp16. The work below is **product-complete those surfaces**, not invent them.

---

## 1. 1.0 requirements (must be green)

### T1 — Train: LoRAs and checkpoints, per family, hardware-smart

Wire Train as a real trainer for **LoRAs and checkpoints of each shipped family**, not only “launch Sohya if a path exists.”

- Defaults **computed from this machine**: VRAM, host RAM, GPU count, whether PAIR / a second node is present.
- Single-GPU (RTX 5090 32 GB) gets a working preset without the user knowing batch/rank/optimizer.
- **Multiple GPUs** and **PAIR (dual PC)** get a **separate, covered** parameter set — not the single-GPU form with a checkbox. Batch, device map, gradient checkpointing, offload, and which node holds which stage must be explicit and fail-closed when the cluster is not joined.
- Family recipes (Krea2 / SDXL / Flux / Wan / LTX / …) are **data**, not a second UI per family.
- Honest empty: no house checkpoint, no house LoRA, no invented Sohya path.

**Today:** `TrainPage` launches external Sohya_kk. Dataset remains **image generation**, not the trainer.

### T2 — Workflow drop: graph + missing deps + download dialog + keys

Drop / paste a workflow → SpellVision **wires the graph** (existing import path) **and** lists everything missing:

| Missing | Source | Action |
|---------|--------|--------|
| Node pack / custom node | Comfy registry, GitHub (pinned zipball — Doc 46, no git) | Dialog: Download |
| Checkpoint / UNET / LoRA / VAE / CLIP | HuggingFace, CivitAI, workflow-declared URL | Dialog: Download (never on a guess — Doc 19/52) |
| Already present | — | Not in the dialog |

- One dialog. User clicks **Download**. Nothing fetches until that click.
- **API keys:** if a needed key is already in the store, **do not prompt**. If it is missing, ask, and put a **link to the page that creates that key** (HF / CivitAI / …) in the same dialog.
- Preflight three-state (resolved / unresolved / unknown) stays; “could not check” never renders Ready.

**Today:** import + pack resolver + model plan exist; the product dialog + key UX + “auto-populate the right graph” still need to be one user-visible path.

### T3 — Models page: learn from these teachers (do not vendor them)

Make Models **Stage-2+ product**, taking *behaviour* from:

| Teacher | Steal | Do not steal |
|---------|-------|----------------|
| [willmiao/ComfyUI-Lora-Manager](https://github.com/willmiao/ComfyUI-Lora-Manager) | Library UX: cache, rebuild-cache, favorites, CivitAI/HF metadata, example images, pause/resume downloads, recipes, trigger words | Becoming a Comfy custom-node web app |
| [rgthree/rgthree-comfy](https://github.com/rgthree/rgthree-comfy) | Power-LoRA-style stack (toggle + name + strength per row), seed control discipline, drop-workflow-onto-a-slot, corrupt-link honesty | Node-graph chrome inside SpellVision |
| [nkchocoai/ComfyUI-SaveImageWithMetaData](https://github.com/nkchocoai/ComfyUI-SaveImageWithMetaData) | PNGInfo that actually round-trips prompt / steps / CFG / seed / model / LoRA / VAE / hashes (CivitAI-shaped) | Requiring a KSampler node hunt in a graph the user never sees |
| [ussoewwin/ComfyUI-QwenImageLoraLoader](https://github.com/ussoewwin/ComfyUI-QwenImageLoraLoader) | Family-correct LoRA loaders (Qwen / Z-Image Turbo / Krea2 ControlNet LoRA) so a LoRA on the Models page **applies** on the family it belongs to | Nunchaku-only assumption as the product default |

### T4 — Optimizations installed and **confirmed working**

SageAttention, Triton, DynamicVRAM / comfy-aimdo, fp16 cast, TeaCache where a family uses it — **installed in the live Comfy venv and proven on a real generate**, not present in a requirements file. Record family × opt × “used / skipped / broke.”

### T5 — Optimal settings are the **default** on every family and every generation page

T2I / I2I / T2V / I2V (and studios that hand off to them): sampler, scheduler, steps, CFG, canvas, duration/frames — **family OP table is what Simple starts on**. Advanced reveals the knobs in place. Presets must not invent a model (existing first-run honesty). Hardware-smart caps (VRAM / host RAM) may snap **with a warning**, never silently.

**Today:** video family change already calls `applyOptimalVideoSamplingDefaults`. Image families still drift (Krea2 60/3.5 vs other stacks). One table, all four pages.

### T6 — Dual PC (PAIR) + multi-GPU: research, test, optimize, enable

This box: **YOUNGDARKDUCK 5090** (`192.168.1.205`) + **SPELLNODE 3090 Ti** (`192.168.1.127`) via NVPAIR. That cluster today moves **LLM jobs**, not Comfy graphs.

SpellVision 1.0 must:

1. **Research** what Comfy / this core actually does with two local GPUs vs two PCs (CUDA_VISIBLE_DEVICES, model split, sequential offload, PAIR as a job router).
2. **Test** on this LAN. Measure. No “should work.”
3. **Optimize** defaults (T1/T5 consume this).
4. **Enable** in product: Runtime/Train/Generate expose the topology they will use; fail-closed if PAIR is not joined or the second GPU is busy.

Do not pretend NVPAIR `pinnedPeers>0` means Wan dual-noise runs on the 3090.

### T7 — Ship walkthrough (last)

After **T1–T6 green** and **grade S** on the product surfaces:

- Deep peer-reviewed walkthrough **with pictures** (this document’s companion, or a new Doc 55).
- States **1.0 requirements** (this list) — all green.
- States **1.0 nice-to-haves** (optional; not blockers).
- States **v1.1+**: anything not explicit 1.0 and not added in chat.

No walkthrough before S. No “shipped” before the walkthrough.

---

## 2. 1.0 nice-to-haves (not blockers)

Fill at walkthrough time. Candidates already in Doc 27/28 that are **not** this chat:

- Target-res upscale tier; video upscale as a product control
- Taste pass on glass hover
- History page rename off `T2VHistoryPage`
- Cosmetic tail / animations

Do **not** promote a nice-to-have to a requirement without another owner chat line.

---

## 3. v1.1+ (do not start)

From Doc 28 cut list + owner locks, unless a later chat adds them:

- Character B (mesh / garments / hair / beauty)
- Native 3D (TRELLIS.2)
- Comic page → I2V stitch
- Chain Studio unhide
- LLM node-orchestration
- Long videos (no spec)
- Replacing ComfyUI with pure diffusers

---

## 4. Sequence (critical path)

```
S-grade cockpit leftovers (overlay, dest/SaveImage, T2V honesty)
    → T5 optimal defaults (unblocks honest Simple)
    → T4 optimizations proven on live generates
    → T2 workflow drop dialog + keys (Doc 46/52 productized)
    → T3 Models page (teachers, not a rewrite of the rail)
    → T6 PAIR / multi-GPU research+enable (feeds T1 defaults)
    → T1 Train (family recipes + hardware/PAIR presets)
    → T7 walkthrough + pictures  (requires S + T1–T6 green)
```

Installer / clean-machine (Doc 27 #11–13) still sits on the original Arc 3 path. This wave does **not** replace MSI; it **feeds** it.

---

## Related

Doc 19, 22, 27, 28, 46, 52 · `brain/Planning/Planned Additions.md` · CLAUDE.md §5–6
