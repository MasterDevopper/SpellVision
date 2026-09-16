# Live API validation, 2026-09-16 (owner-supplied read-only keys, stored DPAPI)

Keys are in `%LOCALAPPDATA%\DarkDuck\SpellVision\credentials.json` (DPAPI, `credential_store`).
They are NOT in the repo and must never be written to a tracked file.

## Environment as found
- **D: is BitLocker-LOCKED right now.** `os.listdir("D:/AI_ASSETS/models")` raises WinError -2144272384.
  The running Comfy (started 09-12) still lists 131 checkpoints from its startup scan, so the app is
  currently offering models that cannot be loaded. This is the `model-root-bitlocker-hazard` memory, live.
- F:/AI_ASSETS/models readable: 1 checkpoint, 8 diffusion_models, 23 loras, 2 text_encoders, 1 vae.
- `extra_model_paths.yaml` managed block lists BOTH roots (D: primary, F: extra_0).

## CivitAI by-hash: 4 of 4 local files hit, anonymously
| file | MB | sha256 time | hit |
|---|---|---|---|
| Detailer-KREA2.safetensors | 12 | 0.03 s | [KREA 2] Detail Slider v1.0 (LORA, Krea 2) |
| CharacterDesign-KREA2_v1.safetensors | 229 | 0.53 s | [KREA 2] Character Design V1 (LORA) |
| krea2DepthControlnet_v10.safetensors | 862 | 1.95 s | Krea 2 Depth ControlNet LoRA v1.0 (Controlnet) |
| loxsUtopicWorldKrea2_v20Quants.safetensors | 13 140 | 29.8 s | Lox's Utopic World Krea 2 · V2.0 Quants · modelId 2823011 |

- **Anonymous and keyed responses were identical** on all three LoRA probes. The key is needed for
  downloads and mature previews, not for reads. Confirms the research.
- **`civitai.red` returned byte-identical results** to `civitai.com` for the same hash. Host is
  interchangeable; keep `civitai.com` as the default and make it a setting.
- Hash throughput **375–442 MB/s** (disk-bound, 4–8 MB buffer). A 13 GB checkpoint costs ~30 s, so a
  full-library first pass is minutes, not seconds: the `(path,size,mtime)` cache and a
  progress-reporting background job are load-bearing, not polish.

## CORRECTION to the desk research: `images[].meta` DOES carry `scheduler`
The research said CivitAI meta is A1111 infotext with no `scheduler` key. **Two shapes occur:**
1. **Split** (Krea2 LoRA entries): `"sampler": "Euler"` + `"scheduler": "beta"`.
2. **Combined Comfy string** (Lox's checkpoint): `"sampler": "er_sde_simple"`, no `scheduler` key.
   The parser must split a trailing scheduler token off the sampler (`er_sde_simple` →
   `er_sde` + `simple`), as well as the A1111 `"DPM++ 2M Karras"` case.
Observed scalar keys on the checkpoint: `Model, Model hash, VAE, cfgScale, clipSkip, prompt, sampler, steps`.
`files[].metadata.fp` carries the quantisation (`nvfp4`, `int8`) — usable as a variant label.

## THE T5 DEFECT, MEASURED
`loxsUtopicWorldKrea2_v20Quants` is the owner's house checkpoint. Its author publishes, unanimously
across **10 of 10** example images:

| field | site says | SpellVision renders today |
|---|---|---|
| steps | **10** | **52** (`family_operating_points.py` krea2_image → default point `raw`) |
| cfg | **1** | **3.5** |
| sampler | er_sde | er_sde (agrees) |
| scheduler | simple | simple (agrees) |
| clip skip | 1 | n/a |

The family table's `raw` point was derived for base Krea 2 Raw; Lox's quantised fine-tune is a
short-step model and the filename carries no "turbo", so `krea2OperatingPointForPath` picks `raw`.
The pictured Doc 55 dest ("krea2 native · 52 steps · 179.9 s") and the T4 A/B (120.72 s vs 124.01 s,
52 steps) were therefore both run at **5.2× the author's step count**. Per-model defaults are not a
convenience feature here; they are a correctness fix worth ~5× on the owner's own model.

## HuggingFace
- `GET /api/models/{repo}` with Bearer: 200 for `krea/Krea-2-Turbo` (`gated=auto`, `library_name=diffusers`,
  `cardData.base_model=['krea/Krea-2-Raw']`) and `black-forest-labs/FLUX.1-dev`.
- `?blobs=true` returns `siblings[].lfs.sha256` (FLUX.1-dev: 11 of 29 siblings carry lfs). Without the
  query there is no lfs block — the flag is required to build the sha256 → repo index.
