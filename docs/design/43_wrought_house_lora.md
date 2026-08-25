# 43 — WROUGHT House LoRA

SSOT for the SpellSword house-style pipeline.

**Working files**
- Prompt pack: `runtime/style/SpellSword_WROUGHT_Race_Prompt_Pack.md`
- Body language: `runtime/style/WROUGHT_Body_Control_Cheatsheet.md`
- Dataset: `runtime/style/datasets/wrought_house_v1/`

## Workflow

1. Generate the dataset on **Krea 2 RAW** (or the **Lox Utopic World Krea2 BF16** merge — live 2026-08-18: first corpus-hip hit).
2. Train a style LoRA on those stills. Trigger: `wrought style`.
3. Daily work: **Krea 2 Turbo + LoRA**.

Do **not** train on Turbo.

## Live fork (do not paper over)

| UNET | Evidence |
|---|---|
| Stock `krea2_raw_fp8_scaled` | House T-pose language (r5). Slim vs corpus. |
| Official style LoRAs | Work. Pull *away* from the house sheet (ink wash / DBZ). |
| `loxsUtopicWorldKrea2_v10BF16` | First plate with corpus hips + ink + paint. Use this for the v1 dataset unless owner A says otherwise. |

## Dataset layout

```
runtime/style/datasets/wrought_house_v1/
  images/     001.png …
  captions/   001.txt …   (same stem)
```

40–80 stills. No near-duplicates. Mix races, roles, clothes, lighting, full-body + portraits.

**Beauty bell (owner):** 6–7 ~25% · 7–8 ~40% · 8–9 ~25% · 9–10 ~10%. No ugly. Not everyone a 10.

Caption: `wrought style, [subject], [materials], [pose], [light]` — content, not style prose.

## Train (Krea 2 RAW / Utopic)

| | Start |
|---|---|
| Type | LoRA or LoKr |
| Rank | 32 (64 if the set is large) |
| Alpha | half of rank |
| LR | 1e-4 → 5e-5 |
| Res | 1024 |
| Batch | 2–4 |
| Steps | 1500–2500, ckpt every 250–500 |
| Prec | bf16 |

Test at 0.6 / 0.75 / 0.85 / 1.0. Daily default ~0.7–0.85.
