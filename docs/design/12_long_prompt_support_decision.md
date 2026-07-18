# Long-Prompt Support — Decision Record (design only)

**Status:** DESIGN / scoping. No implementation. The build is a separate task gated on the open
questions below.
**Date:** 2026-06-30
**Problem:** The 77-token CLIP window silently truncates prompts on the diffusers path. Diagnosed
earlier: there is **no app-side character cap** anywhere (C++ → JSON → worker all pass the prompt
verbatim); the truncation is the SDXL tokenizer's `truncation=True, max_length=77` inside
diffusers' `encode_prompt`, triggered because the worker hands raw `prompt=` text to the pipe with
no long-prompt helper.

---

## 1. SCOPE — which paths truncate? (the bound on the whole build)

**Result: the diffusers SDXL `T2I` and `I2I` paths ONLY. The native-ComfyUI video path
(LTX/Wan, T2V/I2V) does NOT truncate.** This is a **diffusers-only fix** — the smaller of the two
possible builds.

Evidence (code/config inspection — the "inspect the submitted graph's text node" probe taken down
to the encoder implementation):

- **Diffusers T2I + I2I — TRUNCATES.** Both `run_t2i` ([worker_service.py L3254](../../python/worker_service.py))
  and `run_i2i` ([L5596](../../python/worker_service.py)) build their pipe args via the **shared**
  `build_generation_kwargs` ([L3200](../../python/worker_service.py)), which sets
  `kwargs["prompt"] = req["prompt"]` (L3206) and `kwargs["negative_prompt"] = req["negative_prompt"]`
  (L3212-13), then calls `pipe(**kwargs)` (L3300 t2i / L5645 i2i). Raw strings → diffusers
  `encode_prompt` → CLIP tokenizer default `max_length=77, truncation=True` → silent drop of the
  tail. **One shared change-point covers both modes.**
- **Native video — does NOT truncate (chunks + large-context encoders).**
  - ComfyUI's tokenizer **chunks**, it does not truncate: `comfy/sd1_clip.py` builds
    `batched_tokens` — when a token group would exceed `max_length - has_end_token` it starts a NEW
    77-token batch (L632-650), and `encode_token_weights` encodes **all** sections and concatenates
    (`sections = len(to_encode)`, L38-46). `CLIPTextEncode.encode` does
    `clip.encode_from_tokens_scheduled(clip.tokenize(text))` (nodes.py L76-80) — every chunk
    survives into the conditioning.
  - The video families don't even use the 77-token CLIP encoder: **LTX** loads **Gemma** via
    `LTXAVTextEncoderLoader` (`ltx_av_native.json` nodes 2483/2612 `CLIPTextEncode` + 4960 encoder
    loader; [ltx_prompt_api_adapter.py L151](../../python/ltx_prompt_api_adapter.py)); **Wan** loads
    **umt5_xxl** (T5) via `LoadWanVideoT5TextEncoder`
    ([wan_adapter.py L45/L62](../../python/video_adapters/wan_adapter.py)). T5/Gemma have
    512+-token contexts.

**Open question (low priority, belt-and-suspenders):** a live >77-token **T2V** generation, then
read the tail back from the submitted graph / output, would *seal* the "video is fine" conclusion.
The code is conclusive; skip unless a regression surfaces. **Settling needs the live stack +
one video gen.**

---

## 2. LIBRARY CHOICE (diffusers path) — RECOMMEND: **sd_embed**

| Lib | Dep weight | SDXL dual-encoder + pooled | Weighting syntax | Verdict |
|---|---|---|---|---|
| **sd_embed** (`get_weighted_text_embeddings_sdxl`) | light — one function, `pip install sd-embed`; uses torch/transformers already present | **Yes, purpose-built** — returns the 4 tensors incl. `pooled_prompt_embeds` + `negative_pooled_prompt_embeds` directly | `(word:1.2)` — A1111/**civitai** | **CHOSEN** |
| **compel** | moderate — `pip install compel` | Yes — `Compel(tokenizer=[t1,t2], text_encoder=[te1,te2], requires_pooled=[False,True])` returns `(cond, pooled)` | `word++` / `(word)1.2` blend — *not* civitai-native | **FALLBACK** |
| **lpw_stable_diffusion_xl** | bundled (community pipeline) but swaps the **whole pipeline class** via `custom_pipeline=` | Yes | `(word:1.2)` | **REJECTED** |

**Rationale for sd_embed:**
1. **Correct SDXL pooled handling out of the box** — its signature *is* the 4 tensors the SDXL
   pipe wants: `(prompt_embeds, prompt_neg_embeds, pooled_prompt_embeds, negative_pooled_prompt_embeds)`.
2. **`(word:1.2)` matches the user's world** — the checkpoints/LoRAs come from civitai, where that
   weighting syntax is the lingua franca; users expect it to "just work".
3. **Composes with the existing architecture** — it's a *function call*, not a pipeline-class swap.
   It leaves `build_generation_kwargs` / `pipe(**kwargs)` / the shared-UNet + non-destructive LoRA
   adapters / scheduler-swap logic untouched. Only the conditioning args change.

**Why lpw is rejected:** `custom_pipeline="lpw_stable_diffusion_xl"` replaces the pipeline class at
load time. That collides with how this app constructs pipelines (`build_paired_pipelines`,
shared-weight load + fp32→fp16 cast, named LoRA adapters via `set_adapters`). Highest-surgery,
highest-risk path for no syntax advantage over sd_embed.

**Compel is the safe fallback** if, on the installed diffusers/torch (`2.10.0+cu128`), sd_embed's
pooled output proves off or its import is incompatible — compel is the more widely-integrated of the
two with diffusers SDXL.

**Open question (medium):** confirm `sd-embed` imports cleanly and produces a sane pooled tensor on
**this** diffusers/torch build — a 5-line smoke import + one encode. **Settling needs the venv.**

---

## 3. INTERFACE RIPPLE MAP

**Single change-point:** `build_generation_kwargs` ([L3200-3218](../../python/worker_service.py)).
Today:
```python
kwargs = { "prompt": req["prompt"], "num_inference_steps": ..., "guidance_scale": ..., "generator": ... }
if req.get("negative_prompt"): kwargs["negative_prompt"] = req["negative_prompt"]
```
After (conditioning only):
```python
pe, npe, ppe, nppe = get_weighted_text_embeddings_sdxl(pipe, prompt=p, neg_prompt=n)
kwargs["prompt_embeds"] = pe
kwargs["pooled_prompt_embeds"] = ppe
kwargs["negative_prompt_embeds"] = npe
kwargs["negative_pooled_prompt_embeds"] = nppe
# MUST NOT also pass prompt=/negative_prompt= — diffusers raises if both string and embeds are given.
```
Notes:
- **`build_generation_kwargs` takes the `pipe`** (so it can call the encoder) — it currently does
  not; it would need `pipe` threaded in (both callers already hold it: `run_t2i` L3260, `run_i2i`
  L5620-ish). Small signature change.
- **Order is already correct:** LoRA adapters are applied (`run_t2i` L3271-3276) **before**
  `build_generation_kwargs` (L3285), so embeddings computed inside it reflect any active
  text-encoder LoRA. Same shape in `run_i2i`.
- **i2i is covered for free** — it shares `build_generation_kwargs`. The img2img pipe
  (`StableDiffusionXLImg2ImgPipeline`) accepts the same 4 embed args; its `image=`/`strength=` extras
  are unaffected.
- **The progress callback** (`attach_progress_callback`) and `width/height` extras are orthogonal —
  untouched.

**Raw prompt STRING still flows everywhere except the pipe call — CONFIRMED.** History / metadata /
sidecar read the *request* string, not the kwargs: the video-history record's `prompt[:600]` /
`prompt[:160]` ([L2415-16](../../python/worker_service.py)) reads `request_snapshot["prompt"]`; the
image sidecar likewise records `req["prompt"]`. `build_generation_kwargs` only shapes the pipe call.
So the human-readable prompt (incl. any `(word:1.2)` markup) is still recorded; **only the
conditioning swaps to embeds.** No display/history/metadata change.

---

## 4. WEIGHTING SIDE EFFECT — DECISION: **enable weighting (intended benefit)**

Adopting sd_embed makes `(word:1.3)` emphasis **active**. This is the desired civitai behavior and
the reason to prefer sd_embed's syntax.

**Behavior change to document:** a prompt containing **literal parentheses** (e.g.
`a sign that reads (closed)`) would now be parsed as emphasis, not literal text. The A1111/civitai
convention is to **escape** literal parens as `\(` `\)`. This is a real semantic shift for existing
prompts that happen to contain parens.

- **Decision:** enable weighting; document the `\(` `\)` escape; surface a one-line hint near the
  prompt field when the Advanced surface is built. The target audience already expects `(word:1.2)`.
- **Rejected alternative (chunk-only, weighting disabled):** throws away the syntax benefit that
  justified sd_embed; if we wanted chunk-only we'd just as well hand-roll chunk-concatenate. Not
  worth it.

---

## 5. FALLBACK / ROUTING — RECOMMEND: **always route through the encoder (Option A)**, pending an
equivalence check

- **Option A — always route through sd_embed (one code path).** Every T2I/I2I prompt is encoded via
  sd_embed; weighting + long-prompt support everywhere; simplest, one path to maintain.
  - *Risk:* for a short, weight-free prompt, sd_embed's chunk-pad-concatenate may not be
    **bit-identical** to diffusers' native `encode_prompt`, so the same seed could yield a subtly
    different image — existing generations might shift.
- **Option B — gate the embed path.** Use the raw `prompt=` path (current output, byte-identical)
  when `token_count ≤ 77` **and** no weighting syntax is present; route through sd_embed only when
  `>77 tokens` **or** weighting syntax detected. Preserves reproducibility for simple prompts at the
  cost of a branch + two paths.

**Recommendation:** **Option A** for simplicity and consistent (weighting-everywhere) behavior —
**but make the final call contingent on an equivalence test.** sd_embed *should* be ~equivalent for
a single (≤77-token) weight-free chunk (it computes the same dual-encoder hidden states + pooled),
so drift is expected to be negligible. If a same-seed A/B shows meaningful drift, **fall back to
Option B**.

**Open question (medium — decides A vs B):** same-seed A/B — fixed seed + short weight-free prompt,
raw `prompt=` vs sd_embed embeds → compare output (MAE / eyeball). Negligible drift → ship A;
meaningful drift → ship B. **Settling needs one paired test generation.**

---

## OPEN QUESTIONS (carry into the build task)

| # | Question | Priority | How to settle |
|---|---|---|---|
| Q1 | Live >77-token **T2V** gen confirms video really keeps the tail | low | live stack + 1 video gen (code already conclusive) |
| Q2 | `sd-embed` imports + gives sane pooled on diffusers/torch `2.10.0+cu128` | medium | 5-line smoke import in the venv |
| Q3 | **A vs B** — does sd_embed drift from raw `prompt=` for a short weight-free prompt at fixed seed? | medium | 1 paired (same-seed) test gen |
| Q4 | sd_embed reflects **active text-encoder LoRA adapter** weights when called post-adapter | low | inspect during build; order is already adapter-then-encode |

## BUILD SHAPE (when scheduled — NOT now)
1. `pip install sd-embed`; pin in `requirements`. Smoke import (Q2).
2. Thread `pipe` into `build_generation_kwargs`; compute the 4 tensors; drop the `prompt=`/
   `negative_prompt=` string kwargs. Covers T2I + I2I in one place.
3. Equivalence A/B (Q3) → confirm Option A or fall back to Option B's gate.
4. Document the `\(` `\)` escape (weighting now active).
5. Guard: `tests/` — a >77-token prompt whose tail token provably reaches conditioning (e.g. a rare
   token that visibly changes output), + a weighting smoke (`(x:1.4)` vs `(x:0.6)` diverge).

**Cross-refs:** the no-app-cap diagnosis (this is the tokenizer, not a `.left(N)`); the shared
`build_generation_kwargs` is also where the fp16/LoRA-adapter discipline lives (don't disturb it).
