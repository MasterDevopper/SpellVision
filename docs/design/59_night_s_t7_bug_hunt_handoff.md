# Doc 59 — `night/s-t7-bug-hunt` merge handoff

**Merged into `main`:** 2026-09-12.  
**Tip at merge:** `e6a4f62` (`fix(worker): imported workflow honors cockpit FPS`) plus this doc.  
**This is not a ship certificate.** T7 / Grade S stay **OPEN**. Do not treat the merge as 1.0.0 shipped.

Night hunt: silent Generate drops — cockpit knobs / stills / family names that never entered the graph. Honesty banner on the still chip is 1.0 and **landed**. Installer wizard + tutorial is a **separate** product, not this merge.

---

## Landed on this branch (source-proven; pytest GREEN unless noted)

### Honesty (1.0)

- T2I+still **stays remapped to I2I** (do not rip). Chip + preflight name it: **Edit (I2I)**.
- T2V still chip: **Unused (T2V)** + empty-state copy that stills belong on I2V.
- I2V still chip: **Keyframe**.
- Empty prompt blocks Generate (`Write a prompt to generate.`). Imported-workflow drafts still allowed.

### Still / keyframe actually used

- T2I+still remap at builder, enqueue, TCP-direct, `task_of`, queue display.
- Wan / LTX / Hunyuan i2v `LoadImage` reads `i2v_source_image` (LTX no longer bypasses to t2v).
- Native i2i upload / SDXL / look_complete accept `source_image` aliases.
- Canvas drop fills T2I/I2I/I2V reference; canvas `.json` imports a workflow; prompt QTextEdit does not steal drops.

### Cockpit knobs that used to be lies

- I2I Output size: diffusers resize; Krea2 / Flux / PixArt `ImageScale` lanczos.
- I2I Denoise **0 and 1** sayable (diffusers). Flux i2i denoise reads `denoise_strength`.
- Advanced **VAE Tiling**: C++ stamps it on image payloads; SDXL/diffusers `enable_tiling`; Wan dual-noise + core + LTX decode via `vae_decode_node`; checkbox visible on dual-noise/LTX.
- Wan dual-noise High/Low **Shift 0** sayable.
- LTX empty Negative **clears** template `pc game, cartoon…`.
- LTX Preferred output=**full** selects native single-stage.
- LTX two-stage **and** single-stage use cockpit `ltx/` checkpoint / Gemma / VAE names (no `Path.name` strip).
- Hunyuan / Mochi honor cockpit **frames**; FLUX.3 duration reads `frame_count`.
- FluxGuidance / clothes_only read **`cfg_scale`**.
- Flux native T2I/I2I splices cockpit **LoRA** (`LoraLoaderModelOnly`).
- Imported-workflow Generate honors cockpit **Sampler / Scheduler / FPS**.
- Dataset **Save Metadata** checkbox actually skips sidecars.
- Character `ipadapter_weight` / `reference_mode` forwarded.
- `extra_models_roots` as a **string** is honored.
- +Pos/+Neg embeddings reach CLIPTextEncode (native + diffusers).
- Quantized Flux (`fluxmania_legacy`) fail-closes on the **diffusers** path (live Generate fail-close **not** pictured).

### Hidden knobs that the graph ignores

- I2V no longer offers **Denoise**.
- Distilled LTX hides **Steps / CFG**.
- FLUX.3 hosted API hides **Steps / CFG / Upscale** (payload states Upscale Off).
- Hunyuan T2V hides **Negative** (BasicGuider has nowhere for it).

### T2 / T6 (source; not live-complete)

- T2 Download / Flows Launch / Home cards / import dialog / launch log follow `node_plan` / genuine missing, not the raw object_info gap.
- `import_workflow` scans live `/object_info`.
- T6 Dual-PC consent + share folder; Enable installs Distributed via **zipball**, refuses while Comfy queue is running. Pack is **not** on disk until Enable.

### Docs on this merge (not certificates)

- `docs/design/57_current_state_report.html` + Ember captures (Home / T2I / I2I / T2V / Settings). Other palettes **not** pictured — do not cycle owner theme.
- `docs/design/58_peer_review_and_roadmap.md` — ingested peer review. Ember stays. No sixth theme. No GL overlay as 1.0. Verbs Lock / Restyle / Turn / Mood = **1.1**.

---

## Live dests pictured (evidence, not Grade S)

| Surface | Evidence | Caveat |
|---------|----------|--------|
| T2I krea2 | `t2i_krea2_live.png` | Sage vs SDPA ~3% only on this family |
| I2I SDXL | `i2i_sdxl_live.png` | |
| Wan T2V | `t2v_wan_live.mp4` | |
| Wan I2V following | `i2v_wan_i2v_experts_live.mp4` MAE **9.25** | Bad ignore-keyframe clip kept as counterexample |
| LTX T2V | `ltx_t2v_live.mp4` | Dest exists; frame 0 **not** paper-boat — not prompt-S |
| Character | `character_concept_live.png` | |
| Comic panel | `comic_panel_live.png` | Lettered-page dest **not** pictured |
| Concept | `concept_ref_live.png` | Dest exists; clay mannequin ≠ orc |
| Dataset | `dataset_live.png` | |

Grade S needs **every page × every family** dest matching intent. T2I-only dest is not enough. I2V that ignores the still is not S.

---

## Still open — do not call 1.0 / T7 / S

### Product / T7

- T7 HTML (`docs/design/55_t7_ship_walkthrough.html`) is a **review**, not a ship certificate. Do not paint T1/T3/T6/S green.
- **T1 Train** — family + last Dataset folder + hardware rank. Still **external Sohya** launcher.
- **T2** — dialog + skip chain source-landed. Live **drop** of owner workflow **not pictured**.
- **T3** — drop local weight or URL + sidecar display name. **Not** Stage-2 LoRA Manager (parked 1.1 / Doc 58).
- **T4** — krea2 sage vs SDPA pictured (~3%). Wan/LTX sage used, **not** timed vs unopt.
- **T5** — Simple restore + family OP re-apply source-landed. Full family×page Simple=optimal **not live-proven**.
- **T6** — consent UI + Enable zipball landed. Distributed pack **absent** until Enable click.
- Installer window/wizard + first-run tutorial — **separate**, not this merge.

### Generate holes not closed (or not live-proven)

- `fluxmania_legacy.safetensors` live Generate **fail-close not pictured**.
- Batch N dests **not pictured**.
- T2I-with-reference dest **not pictured** (honesty is source-landed).
- Worker reconnect after `:8765` bounce **not live-proven**.
- Dest-unlink: native + imported + clothes_only + look_complete + omitted `comfy_root` landed; `krea2_regional_inpaint` / `garment_shrinkwrap` last looked **missing**.
- Imported-workflow **frame length** still a possible silent drop (FPS landed; length not separately proven).
- Hunt was still open for a **new** silent-drop class at merge (not another canvas-size / hide-knob / still-alias / imported-sampler pass).

### Parked — 1.1.0+, not this merge

- Named verbs **Lock / Restyle / Turn / Mood** + OpenPose Turn.
- Ember Field motes, sixth theme, GL overlay.
- LoRA Manager, look folders, in-app trainer.
- Character B (mesh / garments / hair / beauty), TRELLIS.2, Chain unhide.
- AirLLM: annotate-only, never 1.0.

---

## How to continue after merge

Stay honest: source GREEN ≠ live dest. Next work is remaining Generate silent-drops **or** pictured dests for Batch / T2I-reference / T2 drop / fluxmania fail-close — not T7 green paint, not 1.1 verbs, not cycling the owner’s Ember theme.
