# T4 optimization landscape research (2026-09-15). Live core v0.34.0; upstream v0.35.1 (2026-09-10). [V]/[I]/[?]

## cli_args.py master [V]
- Attention (mutually exclusive): --use-split-cross-attention, --use-quad-cross-attention, --use-pytorch-cross-attention (SDPA default NVIDIA), --use-sage-attention, --use-flash-attention, --use-ck-attention (Comfy Kitchen), --disable-xformers.
- --fast [fp16_accumulation fp8_matrix_mult cublas_ops autotune]; bare --fast = all. fp16_accumulation -> allow_fp16_accumulation; autotune -> cudnn.benchmark (first-run stall #9779); fp8_matrix_mult -> only when supports_fp8_compute AND weights float8_e4m3fn; cublas_ops needs pkg. #8689 Flux+fp16acc+SA2+compile -> noise.
- Memory: --reserve-vram GB, --vram-headroom GB, --enable/--disable-dynamic-vram, --async-offload (default on 2 streams), --disable-pinned-memory (pinned default, Win cap 40% RAM), --cuda-malloc default, --cache-ram/--cache-classic/--cache-lru/--cache-none, --disable-comfy-compiler (v0.35), --disable-cuda-graphs (v0.33.1), --fp16-intermediates.

## Levers table (abridged)
| Lever | Enable | Core/custom | Status on our stack |
| SDPA baseline | --use-pytorch-cross-attention | core | reference |
| SageAttention 2.2/2++ | --use-sage-attention (global) or KJ PathchSageAttentionKJ | pkg | WE SHIP sageattention 1.0.6 = SA1 Triton-only. woct0rdho abi3 wheels: torch>=2.10, cu12.x/13.x, sm120 bundled, triton-windows req. sm120 -> qk_int8_pv_fp8_cuda; sm86 -> Triton. head_dim>128 raise; overflow -> black frames (pv_accum_dtype). Community ~30-35% on 5090. |
| SageAttention 3 FP4 | core registers "sage3", no flag; KJ sageattn3 | pkg | needs torch 2.12/cu131 — out of reach on 2.10+cu128. |
| FlashAttention 2 | --use-flash-attention | pkg | no verified 2.10/cu128 sm120 wheel; <= SDPA for diffusion [I]. CUT. |
| Comfy-Kitchen INT8 attn | --use-ck-attention / node ModelAttentionBackend | core v0.32 | CUDA backend needs runtime >=13.0 / r580; on cu128 Triton path [I]. "might break some". |
| --fast fp16_accumulation | flag | core | RTX3090 SDXL 4->5 it/s (PR #6453). |
| --fast fp8_matrix_mult | flag + e4m3fn weights | core | Flux/Wan fp8 only; sm89+. |
| EasyCache | core node EasyCache (reuse 0.2, start 0.15, end 0.95) comfy_extras/nodes_easycache.py v0.3.52; LTX2 audio pairs v0.13 | core | Flux, Wan, Hunyuan, LTX, Qwen, Lumina2… 1.3-2x; poor with 4-step distill. |
| LazyCache | core node | core | "everything", worse than EasyCache. |
| TeaCache | custom | DEAD (last 2025-07-12; import break #11660 since 2026-01-05). |
| MagCache | custom | DEAD confirmed (last 2025-11-27). |
| FBCache (WaveSpeed) / TaylorSeer | custom | unverified on 0.34 [?]. |
| torch.compile | core TorchCompileModel; KJ TorchCompileModelAdvanced (disable_dynamic_vram), TorchCompileVAE, PatchTritonVAE | core+custom | DynamicVRAM x compile = OPEN limitation (aimdo #13, #14536 Wan slower). Dedicated lane with --disable-dynamic-vram only. |
| DynamicVRAM aimdo | default on v0.16; --disable-dynamic-vram, --reserve-vram, --vram-headroom | core | peak VRAM = available; one OOM report with --reserve-vram. |
| Comfy Compiler / CUDA graphs | v0.35 | core | converted models only (H3, LTX2 allocs); not in 0.34; irrelevant for Wan/Flux now. |
| Async offload + pinned | default | core | 10-50% ONLY if weights offload. |
| NVFP4 | checkpoints; sm>=10.0 | core v0.8 + kitchen | REQUIRES cu130; on cu128 up to 2x SLOWER than fp8. CUT until torch bump. |
| INT8 ConvRot / w4a8 | native ckpts (v0.27 / v0.31) | core | 1.5-2x vs fp8 on AMPERE (3090 Ti column). HF Winnougan/Wan2.2-INT8-Convrot. |
| fp8 scaled vs e4m3 | ckpt format | core | scaled +7-19% vs Q8. |
| GGUF | city96 | custom | slowest. CUT. |
| VAEDecodeTiled temporal | core node | core | VRAM only, slower. |
| PrunaVAED | LTX-2.3 decoder file (core v0.30.2) | core | 1.7x decode, ~50% decode VRAM. IN our core. |
| Wan 2.2 Lightning/lightx2v | LoRA high+low, 4 steps cfg1 | model | quality gate, motion artifacts. |
| LTX-2.3 distilled | default route | model | done. |
| Radial/sparse attn | wrapper-only; core Block Sparse = H3-only | — | not usable on native Wan. CUT. |

## Recommended matrix (rows families, cols levers reachable on 0.34 + torch 2.10/cu128)
SDXL/Pony native: SA2.2, ck-int8, fp16acc, LazyCache, compile, int8-convrot, DynVRAM. SDXL diffusers: fp16 cast (done), VAE tiling.
Flux/Krea2: SA2.2, ck-int8, fp16acc, fp8mm (fp8 only), EasyCache, compile, bf16/fp8/fp8-scaled/int8, DynVRAM.
PixArt/Lumina/Z-Image/Anima/SD3: SA2.2, ck-int8, fp16acc, Lumina2 EasyCache else LazyCache.
Wan 2.2 fp8: SA2.2, ck-int8, fp16acc, fp8mm, EasyCache, compile(DV off), int8-convrot, lightx2v 4-step, tiled/taew2_2.
LTX-2.3: SA2.2 (head_dim check), ck-int8, fp16acc, EasyCache (audio ok), distilled vs dev, PrunaVAED, tiled, --reserve-vram.
Hunyuan (kijai i2v): wrapper attention_mode, fp16acc, EasyCache (t2v native), tiled. Mochi: SA2.2, ck-int8, fp16acc, LazyCache, tiled.
3090 Ti node separate pass: int8-convrot vs fp8; SA2 (sm86 Triton).

## Baseline vs opt-in
Baseline = core defaults pinned explicitly: --use-pytorch-cross-attention, no --fast, DynamicVRAM on, async-offload/pinned defaults, no cache/compile nodes, shipped weight format, run 2+ after warm load. Record exact argv per row.
Opt-in initial (one lever per column, never stacked until solo row exists): --use-sage-attention with SA2.2 installed; --fast fp16_accumulation; EasyCache defaults Wan/Flux/LTX/Hunyuan; lightx2v 4-step Wan (quality gate); PrunaVAED LTX. Compile only in dedicated --disable-dynamic-vram lane.

## Discipline
1 vary SEED per run (node cache). 2 discard run 1 per config; report run 2+. 3 VRAM peaks meaningless under DynamicVRAM; compare memory only at fixed --reserve-vram both arms. 4 offload levers show 0% unless arms offload equally. 5 quality guard per row (frame-0 MAE, black-frame detector for SA overflow, MoE artefact check). 6 log torch/CUDA/driver/sage/kitchen/comfy versions per row.
Sources: cli_args.py, attention.py, nodes_easycache.py, nodes_torch_compile.py, docs.comfy.org changelog, PR #15861, PR #15479, comfy-kitchen, #12699, #12805, aimdo #13, Comfy NVIDIA blog 2026-01-09, woct0rdho/SageAttention, #11583, SA3 HF wheel, KJNodes model_optimization_nodes.py, #11660, Furkan format wiki, PrunaVAED wiki 2026-07-28, H3 sparse wiki 2026-09-08, lightx2v/Wan2.2-Lightning, #14722.
