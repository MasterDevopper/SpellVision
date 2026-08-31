# Recon: Trellis 2 + Pixal3D → SpellVision 3D page

**Status:** Spike pipeline **implemented + validated** outside SpellVision. Engine policy **ADR-0051 accepted**. SpellVision Character Studio **probes + partial QProcess wire**. Dedicated `i23d`/`gen3d` page **not started** (Phase D plan only).

---

## 1. Where things live

### Authoritative runtime (not under SpellBound-Engine tree)

| Role | Absolute path |
|------|----------------|
| Spike root | `C:\Users\xXste\pixal3d-spike` |
| Conda env | `C:\Users\xXste\miniforge3\envs\pixal3d-spike\python.exe` |
| Pixal3D code | `C:\Users\xXste\pixal3d-spike\Pixal3D\` (`pixal3d` package) |
| TRELLIS.2 code | `C:\Users\xXste\pixal3d-spike\TRELLIS.2\` (`trellis2` package) |
| UltraShape code | `C:\Users\xXste\pixal3d-spike\ComfyUI-UltraShape\UltraShape-1.0\` |
| MV-Adapter | `C:\Users\xXste\pixal3d-spike\MV-Adapter\` |
| MoGe / utils3d | `...\MoGe_src\`, `...\utils3d_src\` |
| CuMesh / FlexGEMM / natten / cubvh | spike sibling source trees + built into env |

### Weights

| Model | Path |
|-------|------|
| Pixal3D | `C:\Users\xXste\pixal3d-spike\weights\TencentARC__Pixal3D\` |
| TRELLIS.2-4B | `C:\Users\xXste\pixal3d-spike\weights\microsoft__TRELLIS.2-4B\` (~16 GB) |
| UltraShape | `C:\Users\xXste\pixal3d-spike\weights\ultrashape\ultrashape_v1.pt` (7.4 GB) |
| DINOv3 | `...\weights\facebook__dinov3-vitl16-pretrain-lvd1689m\` |
| BiRefNet | `...\weights\ZhengPeng7__BiRefNet\` |

### Drivers (CLI entrypoints)

| Script | Purpose |
|--------|---------|
| `...\pixal3d_generate.py` | **Default I2-3D** — Pixal3D proj+MoGe, geometry-only `.glb` |
| `...\trellis2_generate.py` | Alt I2-3D — base TRELLIS.2-4B token cond (1..N views) |
| `...\turnaround_generate.py` | 1 image → 6 orbit views (MV-Adapter) for multiview Trellis |
| `...\ultrashape_refine.py` | Coarse mesh + image → watertight refine |
| `...\retopo_adaptive.py` | pymeshlab adaptive remesh (game density) |
| `...\retopo_lod.py` | Blender headless quad + LOD0–3 |
| `...\bake_uv.py` / `bake_maps.py` | xatlas UV + Blender OPTIX bake |
| `...\vram_budget.py` | Probe/plan/OOM ladder for all GPU stages |

### SpellBound-Engine (policy + docs only — no invoker binary)

- `C:\Users\xXste\Code_Projects\SpellBound-Engine\docs\decisions\0051-pixal3d-generation-backend.md` — **Pixal3D offline backend**, geometry-only, native Windows worker, spawn-per-job, licence gates (`o_voxel` without `postprocess`/`io`)
- `C:\Users\xXste\Code_Projects\SpellBound-Engine\docs\pipeline\pixal3d-env-plan.md` — full operating procedure
- `C:\Users\xXste\Code_Projects\SpellBound-Engine\docs\pipeline\vram_budget_spec.md`
- **No** Trellis/Pixal code under `tools/` beyond general authoring tools

### SpellVision stale / unused trees

- `C:\Users\xXste\Code_Projects\SpellVision\Trellis\` — old TRELLIS v1 clone (Mar), **not** the spike path
- `C:\Users\xXste\Code_Projects\SpellVision\UltraShape\` — empty-ish git stub
- `python/runtime_paths.py` → `SPELLVISION_TRELLIS` default `external_assets/trellis/Trellis` — **legacy**, unused by Character Studio

### Blender

- Prefer: `C:\Program Files\Blender Foundation\Blender 5.0\blender.exe`
- Fallback: `...\Blender 4.5\blender.exe`
- CharacterStudio probes 5.0 → 4.5 → 5.2

---

## 2. Exact CLIs

**Env always:**
```bash
export HF_TOKEN=...   # or ~/.cache/huggingface/token
# Python: C:/Users/xXste/miniforge3/envs/pixal3d-spike/python.exe
cd /c/Users/xXste/pixal3d-spike
```

### Image → 3D (Pixal3D — default / Character Studio BaseMesh)

```bash
IMG_NAME=0_img.png USE_MOGE=1 DEC_TARGET=200000 OUT_TAG=naf1 \
  python pixal3d_generate.py 1536
# argv[1]=start cascade res (default from vram plan, usually 1536)
# Input:  Pixal3D/assets/images/$IMG_NAME
# Output: out/asset_${OUT_TAG}_${actual_res}.glb
```

### Image → 3D (TRELLIS.2 — multiview-capable alt)

```bash
# single view
IMG_NAMES=0_img.png OUT_TAG=t2 DEC_TARGET=1000000 TARGET_RES=1536 \
  python trellis2_generate.py

# multi-view (absolute paths preferred for turnaround feed)
IMG_PATHS_ABS="C:/path/front.png,C:/path/side.png,C:/path/back.png" \
OUT_TAG=t2mv TARGET_RES=1536 DEC_TARGET=1000000 \
  python trellis2_generate.py
# Output: out/asset_${OUT_TAG}_${res}.glb  (+ Rx(-90) Y-up fix baked in)
```

### Turnaround (feeds Trellis multi-image)

```bash
IMG=Orc_Red.png TAG=orcR SEED=42 STEPS=50 \
  python turnaround_generate.py
# → out/turnaround/${TAG}_az000.png ... az315, _grid.png, _manifest.json
```

### Refine / retopo / LOD / bake

```bash
python ultrashape_refine.py --image <img.png> --mesh <coarse.glb> --out <refined.glb> \
  [--steps 12] [--octree_res 1024] [--no_low_vram] [--no_strip]

python retopo_adaptive.py --in <high.glb> --out <adaptive.glb> --pct 0.4 --iters 6

"/c/Program Files/Blender Foundation/Blender 5.0/blender.exe" --background \
  --python retopo_lod.py -- <adaptive.glb> <out/lod> <name>
# → name_LOD0.glb ... LOD3.glb

python bake_uv.py --in <low.glb> --out <low_uv.obj>
blender --background --python bake_maps.py -- <low_uv.obj> <high.glb> <out/bake> [2048]
# → normal.png ao.png curvature.png validate_*.png
```

### Text → 3D

**None native in spike.** Path = T2I (SpellVision/Comfy) → image → I2-3D. TRELLIS.2 upstream has text paths in-repo; **not wired** in drivers.

---

## 3. I/O contract

| Stage | In | Out | Notes |
|-------|----|-----|-------|
| Pixal3D gen | RGB image (assets dir basename) | `out/asset_*.glb` UV’d tris, **geometry-only** (no baked PBR) | MoGe camera; cascade res; `DEC_TARGET` faces |
| Trellis2 gen | 1..N images | same pattern; upright Y-up | token cond; skip tex models |
| UltraShape | image + coarse glb | refined glb, watertight | keep_largest strips MC flecks |
| Adaptive remesh | high glb | ~365k game mesh | silhouette-preserving |
| LOD | adaptive glb | LOD0–3 glb | Blender hygiene critical |
| Bake | low UV + high | normal/AO/curvature PNG | residual normal gashes known |

**Proven samples:** `C:\Users\xXste\pixal3d-spike\out\asset_*.glb` (many), `out\lod\humanoid_LOD*.glb`, `out\turnaround\orcR_*`.

**Thumbnails:** none automated in spike — Blender viewport / engine viewer required (Phase D2).

---

## 4. VRAM / env

| Item | Value |
|------|--------|
| Anchor GPU | RTX 5090 **32 GiB**, sm_120 Blackwell |
| Pixal3D peak (`res=1536`, `low_vram=True`) | **~22.4–22.7 GB** smi (DINOv3@1024 peak owner ~16 GB) |
| Headroom | ~9–10 GB; large resident LLMs must unload |
| Token ceiling | ~49152 (plan derives ~48910 on 5090) |
| UltraShape | octree **1024** (2048 impractical); ~2–3 min/mesh; low_vram cpu-offload |
| Refuse floor | usable budget **&lt; ~6–9 GB** |
| Worker model (ADR) | **spawn-per-job**, not long-lived daemon |
| Key env | `HF_TOKEN`, `IMG_NAME`/`IMG_NAMES`/`IMG_PATHS_ABS`, `USE_MOGE`, `DEC_TARGET`, `OUT_TAG`, `TARGET_RES`, `TOKEN_CEIL`, `ATTN_BACKEND` (set by plan), `USE_NAF=1`, `VRAM_PREFER_SPEED=1` (opt), `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` (US) |
| Licence fingerprint | after job: `o_voxel=True`, **`nvdiffrast=False`**, `plyfile=False` |

---

## 5. CharacterStudioPage mesh probes (already real)

**Files:**  
`C:\Users\xXste\Code_Projects\SpellVision\qt_ui\studios\CharacterStudioPage.{h,cpp}`  
Rail `modeId`: **`character`**

**`probeExternalTools()`**
- Spike: `C:/Users/xXste/pixal3d-spike` (+ home / sibling)
- Requires `pixal3d_generate.py` present
- Python: `miniforge3/envs/pixal3d-spike/python.exe`
- UltraShape: `ultrashape_refine.py` exists
- Blender: 5.0 / 4.5 / 5.2

**Stages:** Concept → MultiView → **BaseMesh** → **Refine** → **GameReady** → Garments → … → Export  

**`runMeshPipeline` (QProcess, fire-and-forget):**

| Stage | Script | Args/env |
|-------|--------|----------|
| BaseMesh | `pixal3d_generate.py` | env `IMG_NAME`, `USE_MOGE=1`, `DEC_TARGET` 200k/1M, `OUT_PATH` |
| Refine | `ultrashape_refine.py` | `--image --mesh --out` |
| GameReady | `retopo_adaptive.py` only | `--in --out --pct 0.4` |

**Backend combo:**  
0 = Pixal3D/TRELLIS.2 · 1 = “ComfyUI native (when wired)” **stub** · 2 = import mesh  

**Bugs / gaps vs spike (block honest E2E):**
1. `IMG_NAME` set to **full concept path**; driver expects **basename under** `Pixal3D/assets/images/`
2. `OUT_PATH` **ignored** by `pixal3d_generate.py` → always `out/asset_*.glb`; UI looks for `project/coarse.glb`
3. Backend index 0 never calls **`trellis2_generate.py`**
4. LOD/bake checkboxes **not chained**; Blender path probed but unused in pipeline
5. No worker TCP command — bypasses queue/history

---

## 6. ComfyUI 3D vs external scripts

| Path | Available? | Role for SpellVision |
|------|------------|----------------------|
| **External spike scripts** | **Yes, proven** | Character Studio + recommended first I2-3D |
| Comfy core docs nodes | Hunyuan3D-v2 conditioning/VAE, Load3D/Preview3D, Rodin/Meshy API, VoxelToMesh | **docs/templates in venv** |
| `C:\Users\xXste\Comfy` | `models/checkpoints/hunyuan_3d_v2.1.safetensors` + workflow templates | candidate **native_comfy_template** family |
| Comfy-UltraShape pack | vendored **inside spike**, not SpellVision Comfy custom_nodes | refine stage external |
| Pixal3D / TRELLIS.2 Comfy nodes | **Not** the production path | ADR deliberately bypasses texture/`nvdiffrast` |

**CLAUDE Phase D (2026-06)** still says “import Hunyuan Comfy workflow → LtxVideoAdapter pattern.” **Later reality (2026-07):** SpellBound locked **Pixal3D external worker**; Character Studio already follows that. Treat Comfy Hunyuan as **optional second family**, not milestone-1.

---

## 7. Recommended architecture

### Page / modeId
- **One cockpit page** `modeId = gen3d` (rail Create), with Simple modes:
  - **I2-3D** (`command: i23d`)
  - **T2-3D** (`command: t23d` = T2I chain then i23d, or label as “via image”)
- Keep **`character`** as multi-stage product surface (orchestrates gen3d + garments)
- Do **not** ship separate `i23d`/`t23d` rails first — mirrors video single page + family adapters

### Adapter pattern (mirror LTX, but **subprocess backend**)

```
UI gen3d / CharacterStudio
  → worker command run_native_mesh | run_i23d
  → MeshFamilyAdapter registry
       Pixal3DAdapter      (default, ADR-0051)
       Trellis2Adapter     (multiview)
       HunyuanComfyAdapter (future native_comfy_template)
  → spawn pixal3d-spike env process (or Comfy /prompt)
  → result: { glb_path, thumb_path?, provenance, vram_plan }
  → MediaPreviewController 3D viewer + history
```

LTX reference: `python/video_adapters/ltx_adapter.py` + `backend_route=native_comfy_template`.  
For Pixal3D: **`backend_route=external_spike_worker`** (not Comfy graph) — still “adapter + readiness gate + family routing.”

### Readiness gate
- Probe spike dir + conda python + weights dirs + free VRAM floor (reuse `vram_budget.plan`)
- Optional: Comfy `/object_info` for Hunyuan family only

---

## 8. Minimal first milestone (D1)

**Goal:** one family, image → `.glb` on a canvas/viewer stub.

1. Fix CharacterStudio BaseMesh bridge **or** add worker `i23d`:
   - Copy/symlink input → `Pixal3D/assets/images/<job_id>.png` **or** extend driver with `IMG_PATH` absolute
   - Parse stdout `FINAL exported <path>` / `FINAL_DONE`; copy glb → project `coarse.glb`
2. Python: `python/mesh_adapters/pixal3d_adapter.py` + `worker_service` spawn:
   ```
   pixalPython pixal3d_generate.py
   env: IMG_NAME, USE_MOGE=1, DEC_TARGET=200000, OUT_TAG=<job>
   cwd: spikeRoot
   ```
3. UI: `gen3d` page **or** Character BaseMesh Done → show path + simple orbit viewer (Qt 3D / QWebEngine glTF / temporary open-in-folder + Blender)
4. **Out of scope for M1:** UltraShape, LOD, bake, multiview Trellis, T2-3D, Comfy Hunyuan

**Acceptance:** drop PNG → job completes → `*.glb` exists → history entry with provenance (model=`TencentARC/Pixal3D`, seed, image hash, artifact hash per ADR-0051).

---

## 9. Wire plan (ordered)

| # | Work | Depends |
|---|------|---------|
| W0 | Fix I/O mismatch (path in, path out) on spike **or** CharacterStudio | — |
| W1 | Worker `i23d` + Pixal3DAdapter + readiness | W0 |
| W2 | `gen3d` ModePage / ImageGeneration-style cockpit (image drop + detail tier) | W1 |
| W3 | GLB preview stub + thumbnail render (Blender one-shot or offline) | W2 |
| W4 | Optional refine stage (`ultrashape_refine`) as Advanced checkbox | W1 |
| W5 | Game-ready chain: adaptive → Blender LOD (use probed `blenderPath_`) | W4 |
| W6 | Trellis2 + turnaround multiview family | W1 |
| W7 | T2-3D = T2I handoff → i23d | W2 |
| W8 | Optional Hunyuan `native_comfy_template` second family | Phase D re-survey |

**VRAM scheduling:** unload Comfy/large models before spike job (same GPU); spawn-per-job.

---

## 10. Decision summary

| Question | Answer |
|----------|--------|
| Where is Trellis 2? | Spike `TRELLIS.2` + weights; driver `trellis2_generate.py`; **not** in Engine binary |
| Where is Pixal3D? | Spike `Pixal3D` + `pixal3d_generate.py`; ADR-0051 engine backend |
| Comfy or external? | **External scripts first** (proven); Comfy Hunyuan optional later |
| Character Studio? | Probes OK; invoke **broken** on IMG path + output path |
| modeId? | Prefer single **`gen3d`** + commands `i23d`/`t23d`; keep `character` for pipeline |
| T2-3D? | No spike CLI — compose via T2I |
| Blender? | Required for LOD/bake only; gen+refine+adaptive run in conda alone |

**Files modified this recon:** none (read-only).