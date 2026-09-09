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

### T6 — Dual PC + multi-GPU: research, test, optimize, enable

**Research lock 2026-09-09 (this LAN, live core v0.34.0):**

| Path | What it is | Fits this hardware? |
|------|------------|---------------------|
| **NVPAIR** | Routes **Ollama/LM Studio** jobs. mTLS cluster. | **LLM only.** `pinnedPeers>0` does **not** run Comfy / Wan / LTX on SpellNode. |
| **Native `MultiGPU_WorkUnits` / CFG Split** | Core `comfy_extras/nodes_multigpu.py` (PR #7063). Splits CFG cond/uncond across **identical** GPUs **in one box**. Wan ~1.89× on dual 4090. **CFG must be >1.** | **No.** This PC is **1× RTX 5090**. SpellNode is a **different machine** and a **3090 Ti** (heterogeneous). Official docs: mixing GPU types unsupported. Class **is** in live `/object_info`. |
| **ComfyUI-Distributed** (robertvoy) | Fan-out **whole jobs** to local extra GPUs / **LAN workers** / cloud. Two nodes convert a graph. Does **not** pool VRAM. | **Yes — 1.0 dual-PC candidate.** Second Comfy on SpellNode `--listen`, master collects stills/video. 5090 and 3090 Ti can each run a **full** job they fit. |
| **ComfyUI-MultiGPU / DisTorch** | Offload UNet layers to RAM / other **local** devices. | Local RAM offload only; not SpellNode over ethernet. |
| **ComfyUI-Mesh** (Icarus/Daedalus) | Split **one** FLUX.2 / LTX 2.3 model across two GPUs, LAN or same box, NVENC on the wire. | **v1.1+** unless we adopt it for LTX/FLUX specifically. Not a general family router. |
| **ComfyUI_NetDist** (city96) | Queue remote Comfy instances. Older, janky seeds. | Fallback if Distributed fails. |
| **SwarmUI backends** | Second frontend. | Do not replace SpellVision. |

**1.0 enable path:** productize **ComfyUI-Distributed** (or NetDist if Distributed fails closed): SpellVision Runtime lists workers (127.0.0.1:8188 master + `192.168.1.127:<port>` SpellNode). Generate can **queue** a job there. Fail-closed if worker offline. Do **not** claim VRAM adds (32+24 ≠ 56).

**Not started as product:** SpellVision Runtime does not list workers yet. Pack not in Windows `custom_nodes`.

**Live probe 2026-09-09 (this LAN):**

| Fact | Evidence |
|------|----------|
| SpellNode Comfy | `/opt/comfyui` **0.34.0**, `.venv`, torch **2.13.0+cu130**, 3090 Ti 24 GB, aimdo 0.4.15 |
| Listen | `--listen 0.0.0.0 --port 8188 --enable-cors-header` |
| Windows → node | `GET http://192.168.1.127:8188/system_stats` → **200**, `os=linux`, `comfyui_version=0.34.0` |
| First start hang | `extra_model_paths.yaml` CIFS `//192.168.1.182/AI_ASSETS_models` → `cifs_wait_for_server_reconnect` (**host down**). Listen only after yaml moved aside. |
| PAIR | ollama + nvpair-* running on SpellNode; GPU compute empty during probe. Comfy **stopped** after proof so PAIR keeps the card. |
| Generate on node | **not run** — model shares down. |

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

## 3. v1.1+ (do not start until 1.0 is green)

Owner 2026-09-09: park real capability here if it is **not** explicit 1.0 and **not** this chat’s requirement list. Add anything that would actually improve the product.

### Generation / engine
- Native **same-box MultiGPU CFG Split** when a second **identical** GPU exists (not this LAN)
- **ComfyUI-Mesh** model-split over LAN for FLUX.2 / LTX 2.3
- **DisTorch / ComfyUI-MultiGPU** layer offload as a Runtime toggle
- **ParallelAnything** batch replica (needs N× VRAM of the same model)
- Long videos (no spec yet)
- Audio pipeline depth
- Ultimate SD Upscale as a first-class Simple control (tiled diffusion, not ESRGAN)
- Qwen-Image / Z-Image Turbo as first-class families on the rail
- ControlNet / IP-Adapter as Simple intent (pose / face / depth) without a node graph
- TeaCache (or successor) per family, generate-proven; MagCache stays dead on this core

### Surfaces
- Character B (mesh / garments / hair / beauty) — cut from v1 2026-09-04
- Native 3D (TRELLIS.2)
- Comic page → crop → I2V → stitch (Doc 40)
- Chain Studio unhide
- CivitAI/HF browse-and-import inside Models (LoRA Manager’s library, not a webview of Comfy)
- PNGInfo / CivitAI metadata on **every** dest still (SaveImageWithMetaData behaviour, SpellVision-owned)
- History as a real media library (rename off `T2VHistoryPage`)
- LLM node-orchestration

### Do not
- Replace ComfyUI with pure diffusers
- Pretend NVPAIR runs diffusion
- Add 16+24 GB VRAM as one pool

---

## 4. Sequence (critical path)

```
S-grade cockpit leftovers (overlay leftover AI chip, dest/SaveImage, T2V honesty)
    → T5 optimal defaults (unblocks honest Simple)
    → T4 optimizations proven on live generates
    → T2 workflow drop dialog + keys (Doc 46/52 productized)
    → T3 Models page (teachers, not a rewrite of the rail)
    → T6 dual-PC via ComfyUI-Distributed (feeds T1 defaults)
    → T1 Train (family recipes + hardware/PAIR presets)
    → T7 walkthrough + pictures  (requires S + T1–T6 green)
```

Installer / clean-machine (Doc 27 #11–13) still sits on the original Arc 3 path. This wave does **not** replace MSI; it **feeds** it.

---

## 5. Live progress (2026-09-09)

| Item | Evidence |
|------|----------|
| Overlay **Generating…** | Live T2I pid 2964: canvas `Generating…`, footer `Readiness — Generating…`, bar Busy/Running/Queue 1. Asset Intelligence chip still said Submitting (leftover). `d2d2000`+`e41e543`. |
| T4 imports | Isolated Comfy venv: sageattention OK, triton **3.7.1**, torch **2.10.0+cu128**, comfy-aimdo **0.4.15**. xformers **absent**. |
| T4 live argv | Adopted `:8188` had **no** `--use-sage-attention`. Restarted with sage. `start_comfy.ps1` from Hermes shell probes sage as missing (PYTHONPATH/sitecustomize). |
| T4 generate | **krea2 T2I used.** Job `ff63ff28` on Comfy PID 34960 argv `--use-sage-attention`. UNETLoader `loxsUtopicWorldKrea2_v20Quants`. Dest `C:/Users/xXste/OneDrive/Pictures/spellvision_render/plate_queue_81757e624975.png` (3,217,373 bytes). Canvas Ready / Idle / Queue 0 / two thumbs / VRAM 21.6. Comfy leftover `output/spellvision_render_job_7b1f406d05b0_00001_.png` still there — live worker predates `ea67539` unlink. **Wan/LTX generate-proven still open.** xformers absent. |
| T6 research | Native `MultiGPU_WorkUnits` in `/object_info`. **1× 5090** locally. Dual-PC = **ComfyUI-Distributed**, not PAIR. **HTTP proven:** SpellNode `/opt/comfyui` 0.34.0 listen `:8188`; Windows `192.168.1.127:8188/system_stats` 200. CIFS `192.168.1.182` host-down blocks models. Comfy stopped after proof. |

---

## Related

Doc 19, 22, 27, 28, 46, 52 · `brain/Planning/Planned Additions.md` · CLAUDE.md §5–6
