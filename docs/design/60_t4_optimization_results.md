# Doc 60 — T4 optimization results, measured

**Status:** measurement record, 2026-09-17. **Machine:** this box — RTX 5090 32 GB, ComfyUI 0.34.0, torch 2.10.0+cu128, `sageattention 1.0.6`, `comfy-aimdo 0.4.15`, `comfy-kitchen 0.2.31`.

Every number here came from a render through the product path, recorded with the ComfyUI argv that produced it. The ledger is `runtime/state/optimization_results.jsonl`; the harness is `scripts/dev/measure_optimizations.py`.

---

## 1. The correction this document exists to make

`docs/design/55_t7_ship_walkthrough.html` published **SageAttention 120.72 s vs SDPA 124.01 s** on krea2 — about a 3% win. That claim does not survive its own data.

**`runtime/state/job_archive.json` holds a third arm the walkthrough never mentions**: `t4_sage_queue_3d2236390c95` at **159.27 s**, same seed, same steps, same size, fifteen minutes before the quoted sage run. So the three recorded numbers were 159.27 / 120.72 / 124.01, and the published gap is **smaller than the spread between two runs of the same arm**.

The arms were distinguishable only because a human typed `t4_sage` and `t4_sdpa` into two output filenames. Nothing in the data said which build produced which number. That is fixed: every render now carries an `optimizations` block naming the running process's argv, and a sweep rule holds it there.

**Corrected answer: on a warm baseline, SageAttention is worth −0.3% on krea2 images — nothing. It is worth −10.2% on LTX video.**

---

## 2. Method, and the two things that had to be got right

- Each arm is one ComfyUI launch. The arm is **read back from the launched argv**, not assumed — a request for an arm is not evidence the arm took.
- A lever arm differs from the baseline in **exactly the lever under test**. An arm that names no attention inherits the baseline's.
- **A fresh seed on every render.** ComfyUI's node cache returns a cached result for an identical prompt; this project has a recorded "12.1 s" that was a cache hit.
- **One cold render per configuration is discarded**, then two are timed.
- The timing is the render's own `generation_time_sec` from its sidecar, not a stopwatch around the call — the round trip includes queue and upload, which are not under test.
- **The machine is idle.** A concurrent C++ build spoiled a full run: the LTX baseline moved 39.08 → 45.80 s and its within-cell spread went 0.4% → 5.6%, with one cell at 55%.

### The first-arm effect — the finding that changed every number

Five independent krea2 levers all read 6-8% "faster" than the baseline. Five levers do not win by the same amount; a baseline does. The baseline is measured **first**. Re-measuring it **last**, on the now fully warm session:

| baseline | measured first | measured last | the first is |
|---|---|---|---|
| krea2 t2i | 14.92 s | 13.79 s | **+8.2%** |
| ltx t2v | 43.00 s | 40.11 s | **+7.2%** |

**One discarded cold render is not enough. The first arm of a session runs 7-8% slow after it.** Every reading in this wave before that test — including two of my own interim ones — compared later arms against a first-arm baseline and over-credited every lever by that much. It also fully explains the original published A/B: 3% is less than half this effect.

Everything below is measured **against the trailing baseline**.

---

## 3. Results

**krea2 t2i** — 1024×1024, 10 steps, CFG 1, er_sde/simple. Trailing baseline **13.79 s**.

| lever | warm mean | vs baseline | spread |
|---|---|---|---|
| vae_tiling | 13.70 s | **−0.7%** | 0.27 s |
| fast_fp16_accumulation | 13.71 s | **−0.5%** | 0.11 s |
| sage_attention | 13.75 s | **−0.3%** | 0.20 s |
| fixed_vram_budget (22 GB reserve) | 13.97 s | **+1.3%** | 0.28 s |
| dynamic_vram_off | 21.34 s | **+54.8%** | 0.03 s |

**ltx t2v** — 832×480, 81 frames @ 16 fps, 30 steps. Trailing baseline **40.11 s**.

| lever | warm mean | vs baseline | spread |
|---|---|---|---|
| sage_attention | 36.02 s | **−10.2%** | 0.37 s |
| fast_fp16_accumulation | 39.93 s | **−0.4%** | 0.40 s |
| vae_tiling | 43.39 s | **+8.2%** | 1.26 s |
| fixed_vram_budget (22 GB reserve) | 68.30 s | **+70.3%** | 9.76 s |
| dynamic_vram_off | 895.96 s | **+2133.8%** | 0.00 s |

---

## 4. What this says

**SageAttention earns its place on video and does nothing on images.** −10.2% on LTX, −0.3% on krea2. The published "~3% on krea2" is not supported. Note that the installed package is `sageattention 1.0.6` — that is SA1, Triton kernels. The research puts the first *real* measurement at SA2.2, whose wheel is not installed; installing it in the live ComfyUI venv is the owner's call, not a wave's. **Read every sage number here as SA1.**

**DynamicVRAM is not an optimization. It is load-bearing.** LTX without it is **22× slower** — 895.96 s against 40.11 s — and krea2 is 55% slower. `comfy-aimdo` is doing enormous work on every render, silently, and the only way to see it is to turn it off.

**Constraining VRAM costs video time.** A 22 GB reserve costs LTX 70% and krea2 nothing. The reserve buys headroom for something else on the card; on this box, with nothing else on the card, it buys a slower render.

**`--fast fp16_accumulation` does nothing measurable** on either family: −0.5% and −0.4%, both inside the spread.

**VAE tiling is free on a small image and costs 8% on video.** Its docstring said no number backed it. Now one does.

---

## 5. Not measured, and why

| lever | why not |
|---|---|
| SageAttention 3 | FP4 kernels need torch 2.12 / cu131. This stack is 2.10 / cu128. |
| NVFP4 | Requires cu130. On cu128 the research measures it up to 2× *slower* than fp8 — it would measure the emulation. |
| FlashAttention 2 | No verified wheel for torch 2.10 / cu128 / sm120, and the research rates it at or below SDPA for diffusion. |
| TeaCache | Dead. Last upstream commit 2025-07-12; fails to import since the 2026-01-05 core change. |
| MagCache | Dead. Already removed from this box as a dead end against the v0.34.0 rope change. |
| GGUF | Measured elsewhere as the slowest weight format. Nothing to win. |
| radial / sparse attention | Wrapper-only; the core's Block Sparse is Hunyuan3D-only, not the native Wan or LTX routes this project ships. |
| torch.compile | Not cut on merit — **deferred.** `torch.compile` × DynamicVRAM is an open upstream limitation, so it needs its own `--disable-dynamic-vram` lane rather than a column in a matrix whose every other cell runs with DynamicVRAM on. |
| ck_int8_attention | `comfy_launch_policy.normalize_backend` accepts only sage and sdpa spellings. An arm naming `ck` would launch something else and label it `ck`. One launch-policy change from measurable. |
| EasyCache · PrunaVAED | No builder inserts the node and no request key reaches one. Measuring them needs a graph change first, which is separate work from measuring. |
| fp16 cast | `CAST_FP32_TO_FP16` is a module constant, not a request key, so both arms cannot run in one session. Needs a worker restart between arms, which this harness deliberately does not do — it restarts ComfyUI, not the product. |

**Memory was not compared.** Under DynamicVRAM a peak measures what was *available*, not what was needed, and `JobResult` carries no peak. The `fixed_vram_budget` row measures the **time** cost of a reserve, not its memory effect.

---

## 6. How to re-run

```
PYTHONPATH="" ./.venv/Scripts/python.exe scripts/dev/measure_optimizations.py \
  --family krea2 --family ltx --requests runtime/optimization_requests.json --force
```

Rows append per cell, so an interrupted run keeps what it measured. The harness restarts ComfyUI once per arm and hands the stack back on every exit, including Ctrl+C. **Run it on an idle machine** — see §2.

Two earlier runs are kept beside the ledger as evidence rather than deleted: `optimization_results.confounded.jsonl` (correct timings, three arms silently on sage) and `optimization_results.cpu-contended.jsonl` (correct arms, a build running).

---

## Related

Doc 54 §1 T4 · Doc 55 §T4 (the claim this corrects) · `docs/superpowers/plans/2026-09-16-w3-optimization-evidence.md` · `docs/superpowers/specs/2026-09-15-t2-t6-research/t4-research.md` · `python/optimization_provenance.py` · `python/optimization_levers.py`
