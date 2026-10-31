# Doc 63 — Live feature census

**Status:** present-tense map of what the tree *is*, not a roadmap.
**Inspected:** 2026-09-19, branch `feat/t5-defaults-everywhere` (`72bec37`).
**Method:** source first (`qt_ui/shell/ShellNavigationController.cpp`, `python/video_family_contracts.py`, `python/native_image_graphs.py`, `python/family_capability.py`, `python/worker_auth.py`, `python/model_registry.py`). Prose (CLAUDE.md, Doc 27/28, the 2026-08-24 Current State Ledger, the 2026-07-17 v1.0 roadmap) is cited only when it agrees with code, or called out when it does not.
**Not run for this document:** pytest, ctest, a generate, a clean-machine install. Where a cell says *render-proven*, that is retained evidence from CLAUDE.md §6 / Doc 28, not a fresh stamp.

---

## How to read this

Four independent axes. Do not collapse them.

| Axis | Means |
|---|---|
| **Decision** | In v1 bar, cut to v2, parked 1.1, or post-v1 additive |
| **Implementation** | Code exists and is wired into the composition root (rail / dispatch / generate path) |
| **Product-complete** | A non-expert can state intent and get the promised result without node graphs |
| **Acceptance** | Retained render, owner-eyes, clean-machine, or none |

Status words used below:

| Word | Means |
|---|---|
| **Built** | Wired, reachable on the default rail (or the documented generate path), and the promised loop works |
| **Partial** | Meaningful implementation; a named capability is missing, hidden, or dishonest |
| **Stub** | Page, command, or module exists; it does not deliver the product |
| **Not started** | No meaningful product path |
| **Cut / parked** | Owner decision: not a v1 ship gate. The surface may still exist |

**Complete looks like** is the product bar, not “a class exists.”

---

## 1. What the product is

SpellVision is a desktop generation studio. The promise:

> ComfyUI / A1111-class power **without node graphs.** The user states intent; SpellVision wires nodes, resolves deps, runs.

Three processes: Qt6 UI (`qt_ui/`) ↔ worker TCP `:8765` (`python/worker_service.py`) ↔ ComfyUI HTTP `:8188`. Native families use `backend_route="native_comfy_template"` — Comfy executes; SpellVision owns the graph. Diffusers is the image fast-path for SD/SDXL lineage only. ComfyUI is not being replaced.

Live Comfy (CLAUDE.md §9.2): `C:\sv_comfynext_v034\ComfyUI`, isolated venv, core v0.34.0. Models: `D:/AI_ASSETS/models`.

---

## 2. The rail (what a user can open)

Source: `qt_ui/shell/ShellNavigationController.cpp` `railButtonSpecs()` + `kV1HiddenModes`.

Hidden unless `SPELLVISION_SHOW_ALL_MODES=1`: **`chain`**, **`gen3d`**, **`train`**.

| Rail | modeId | Page | v1 visible | Status |
|---|---|---|---|---|
| Home | `home` | Home gallery | yes | Built |
| T2I | `t2i` | `ImageGenerationPage` TextToImage | yes | Built |
| I2I | `i2i` | same, ImageToImage | yes | Built |
| T2V | `t2v` | same, video | yes | Built |
| I2V | `i2v` | same, video + keyframe | yes | Built |
| Character | `character` | `CharacterStudioPage` | yes | Partial (A on rail; B cut to v2) |
| Concept | `concept` | `ConceptReferencePage` | yes | Built as T2I/I2I handoff lab |
| Comic | `comic` | `ComicStudioPage` | yes | Partial (stills/pages; I2V cut to v2) |
| Dataset | `dataset` | `DatasetGenerationPage` | yes | Partial |
| Flows | `workflows` | `WorkflowLibraryPage` | yes | Partial (import/readiness work; drop/download holes remain) |
| History | `history` | History page | yes | Partial (schema v2 landed; page voice still T2V) |
| Inspire | `inspiration` | `InspirationPage` | yes | Built (real moodboard, not `ModePage`) |
| Models | `models` | `ModelManagerPage` | yes | Partial (Stage-1 inventory) |
| Runtime | `runtime` | `ManagerPage` | yes | Built as Comfy manager |
| Prefs | `settings` | Settings | yes | Built |
| Chain | `chain` | Chain Studio | **hidden** | Engine proven; not a v1 surface |
| 3D | `gen3d` | `Gen3DPage` | **hidden** | Stub: Comfy-workflow passthrough |
| Train | `train` | `TrainPage` | **hidden** | Parked 1.1 (external Sohya launcher) |

Roadmap (2026-07-17) still lists Gen3D and Train on “current rail in v1.” Code hid them. **Code wins.**

---

## 3. Create — generation cockpits

One page class, four modes: `qt_ui/ImageGenerationPage*`. Simple/Advanced is global; Advanced **reveals in place**. Sampling lives in `SamplingController` (samplers, schedulers, steps, CFG, distilled **Guidance**, seed). Canvas, upscale, model stack, queue submit go through `GenerationRequestBuilder` → worker.

**Complete looks like:** prompt → model → Generate → canvas media, no node graph, Simple usable at half-screen, Advanced does not relocate knobs, family defaults reach the render (T5).

| Surface | Status | Built means | Left for “complete” |
|---|---|---|---|
| T2I cockpit | **Built** | Native + diffusers image graphs; fp16 shared-weight; LoRA named adapters; Guidance for Flux | Owner S-grade / half-screen sign-off (Doc 30 matrix unrun) |
| I2I cockpit | **Built** | Same page; denoise/strength; keyframe-less | Same visual gate |
| T2V cockpit | **Built** | Family bar Auto/Wan/LTX/…; native templates; MP4 in canvas | Same; LTX Simple copy/caps honesty |
| I2V cockpit | **Built** | Keyframe upload → `LoadImage`; six aliases now gated (`i2v_source_image` included) | Same |
| T5 model defaults | **Built** (this branch) | Sidecar `recommended` → widgets → request → graph. Preset wins until model change. Card settings fill video families CivitAI left empty | Library coverage: LTX/Hunyuan/Mochi settings still thin until cards are backfilled |
| Distilled Guidance | **Built** | Flux + Hunyuan; Auto follows family table then CFG; spin zeros when the family does not offer it | — |
| Pixel upscale | **Partial** | Engine + cockpit controls; pixel graft render-proven 2026-09-02 (`UpscaleModelLoader` V3 combo reader) | Latent-per-family (a) not a product path; Scale box vs `ImageUpscaleWithModel` having no scale input is still a honesty seam |
| Queue / progress | **Built** | `QueueManager`, cancel, history handoff | Observer still sees `queued → completed` without intermediate frames (reporting gap, not SM bug) |

---

## 4. Image families

Route table: `NATIVE_IMAGE_FAMILIES` in `native_image_graphs.py`; `DIFFUSERS_FAMILIES` / `LINEAGE_FAMILIES` in `family_capability.py`.

| Family | Route | Status | Complete looks like |
|---|---|---|---|
| SD 1.x / SD2 | diffusers | **Built** | T2I/I2I on cockpit |
| SDXL | diffusers | **Built** | Shared UNet + fp16 cast; LoRA adapters |
| Pony / Illustrious | lineage → SDXL | **Built** | Same path, family OP table |
| Flux | native Comfy | **Built** | KSampler cfg pinned 1; `FluxGuidance` from published guidance |
| Krea2 | native | **Built** | `er_sde` OP; regional inpaint exists |
| SD3.5 | native (not gated HF diffusers) | **Built** as native graph | First-run must not require Stability licence click |
| PixArt / Lumina / Z-Image / Anima | native | **Built** (Doc 26 closed) | Anima: non-commercial badge (registry `commercial_use`) |
| Qwen / others | — | **Not a v1 family** | Would be a new native family: `/object_info` → template → adapter → contract |

---

## 5. Video families

Source: `VIDEO_FAMILY_CONTRACTS`. `validation_status` is the contract word, not a vibe.

| Family | T2V | I2V | Status | Notes / leftover |
|---|---|---|---|---|
| **Wan** | production | production | **Built** | 2.1 i2v + VAE guard; **2.2 dual-noise i2v render-proven** (Doc 28 / CLAUDE §6) |
| **LTX** | production | production | **Built** | Default `two_stage_distilled`; Prompt-API = history requeue / opt-in only; i2v keyframe MAE ~3.5 |
| **Hunyuan** | production | **wrapper** (not production-native) | **Partial** | T2V native + FluxGuidance; I2V is kijai wrapper. Native CLIPVision i2v blocked (768 vs 1024). **Non-commercial + EU/UK/KR territorial notice still a build task** (Doc 28) |
| **Mochi** | production | n/a (T2V-only model) | **Built** | Apache-2.0 commercial-clean video option |
| **FLUX.3** | preview | preview | **Partial** | Hosted BFL API (`bfl_api`); needs `BFL_API_KEY`; not local weights; paid/remote must stay labelled |
| **CogVideoX** | detected | detected | **Not started as a product route** | Contract only; `backend_route=future_comfy_profile`. **Post-v1 additive** (Doc 26) |
| **workflow** | configured | configured | **Partial** | Raw Comfy profile passthrough via Flows, not a family cockpit |
| Long video | — | — | **Not started** | CLAUDE §5: no spec. Complete = family-native context windows / looping as a first-class duration control, not a hidden node |

---

## 6. Studios

| Studio | Status | Built today | Complete looks like | After v1 |
|---|---|---|---|---|
| Character A (plates → T2I/I2I) | **Partial** | Rail page; generate handoff; `look_complete` / `clothes_only` / `garment_shrinkwrap` worker commands exist | Non-expert: concept → consistent character stills without graphs | **Character B cut to v2** (2026-09-04): mesh, separable garments, strand/card hair, beauty. Studio stays; the product bar does not |
| Comic | **Partial** | Script → stills → page path in tree | v1 = stills/pages. **Comic → I2V is v2** (owner) | Motion comics |
| Concept lab | **Built** as lab | Multi-view packs → T2I/I2I | Packs that actually drive generate | — |
| Chain Studio | **Partial / hidden** | Engine + `submitFn` bound | v1: stay hidden. Complete as a product = visible rail + dressed-character *orchestration* (layer 2 of 3D) | Unhide when 3D composition exists |
| Gen3D | **Stub / hidden** | `Gen3DPage` Comfy passthrough | v1: stay hidden. Complete = native `native_comfy_template` family (TRELLIS.2 first, re-survey), mesh viewer, `.glb` ≠ `.mp4` | Phase D v2 |

---

## 7. Manage

| Surface | Status | Built | Left |
|---|---|---|---|
| Flows | **Partial** | Import, list, readiness, compile-then-draft (unverified `prompt_api.json` no longer fills a draft — `881bb85`) | **3c** Download dialog cannot see a UI-graph’s missing models; **3d** non-workflow files timeout as fake API prompts; **3b** first missing-pack import was 120s — CLI now capped 20s; cold cm-cli on this box still wants >20s, folder walk answers |
| History | **Partial** | Image+video; KEEP/NO; schema v2 + `HistoryRowLabels` | Page chrome still says “video”; owner #12 copy |
| Inspire | **Built** | Moodboard KEEP/NO → send-to T2I/I2I | — |
| Models | **Partial** | Stage-1 inventory, Inspect, bind/use, import-url, licence badges from registry | Stage-3 auto-download / teacher-parity (Doc 54 T3); **3l** bundle-hash mislabel; **3g** card kind lags scan; **3h** NSFW blur has no reveal; **3i** 429 not surfaced as “wait” |
| Dataset | **Partial** | Rail page; worker `generate_dataset`; Simple inherits T2I canvas | Honest empty-dest; not a full dataset app |

---

## 8. System, runtime, shipping

| Piece | Status | Built | Complete looks like |
|---|---|---|---|
| Runtime (Comfy manager) | **Built** | Nodes, restart, paste-link install (pinned zipball, no git) | Guided first-missing-pack on a stranger machine (Doc 46 + Doc 28 “workflow from a link”) |
| Prefs / theme | **Built** | QSettings `DarkDuck/SpellVision`; ArcaneGlass default; four presets exist in tree | Owner visual sign-off; WCAG self-check on every preset; Obsidian/Neon/Ivory as *finished* palettes still open in older polish lists |
| First-run dialog | **Partial** | Exists; CHECKING badges; no hardcoded “Comfy dead” | Stranger reaches Generate **without** `run_ui.ps1` |
| RuntimeProfile | **Partial** | Persist + prefer-live Comfy roots | One identity tuple on every path (exe, worker interpreter, Comfy root, models root) |
| Worker auth | **Built** for loopback | `LOCAL_TRUSTED` vs `INTEGRATION` token; path containment; `i2v_source_image` gated | Integration still **image-only** (`INTEGRATION_QUEUE_TASKS` = t2i/i2i). Video/studio commands are not the integration surface |
| Train | **Parked 1.1** | `TrainPage` is a Sohya_kk *launcher*; hidden on v1 rail | In-app LoRA+checkpoint trainer (Doc 54 T1) is 1.1, not v1 |
| Installer / MSI | **Not started** | No Inno/NSIS/WiX in tree | Hybrid payload (engines in box, models on demand) **proven**, then wrapped. Isolated Comfy venv + `PYTHONUTF8=1` + kornia 0.8.2 is part of “install correctly” |
| Clean-machine smoke | **Not started** | — | Doc 28 gate; evidence empty |
| Host RAM telemetry | **Not started** | CLAUDE §6: host RAM is LTX’s real ceiling; nothing measures it | A number, or drop the parameter (`host_ram_gb` accepted and unwired) |

---

## 9. Cross-cutting that *is* the product

| Concern | Status |
|---|---|
| Simple / Advanced | **Built** as one app-wide rule. Sampler short-list in Simple; rest under a labelled separator in Advanced. Steps/CFG stay Advanced on video. |
| No nested scroll on cockpits | **Partial** — intended; owner C+ half-screen matrix never executed |
| Theme / ArcaneGlass | **Built** as default; S-grade not signed |
| Model intelligence (T3) | **Partial** — 680/759 identified on last refresh; HF arm wired; card settings for silent CivitAI hits; creator/licence flags backfilled. Inspector still reads `license.name` more than CivitAI permission flags |
| Family OP table (T5) | **Built** into Simple + overlay; video supply still mostly `table:family-default` until cards land |
| Optimizations (T4) | **Partial** — Sage 1.0.6 in Comfy venv (not SA2.2); DynamicVRAM on; fp16 image path proven. Matrix not a ship-cert |
| PAIR / multi-GPU (T6) | **Partial / research** — LAN exists in the owner’s world; product enablement is not a closed v1 gate in code |
| Dependency honesty | **Partial** — compile refuses dangling ids; offline is a third state. Remaining: 3c/3d, 120s object_info on mid-swap (generation, by design), refused port now ~8s wall-clock |
| Licence surfacing | **Partial** — badge + soft warn from `model_registry` (green 2026-09-02). Hunyuan territorial notice **not built** |

---

## 10. v1 ship gate (what “1.0 shipped” means)

Owner-facing bar is Doc 28, **minus later cuts**. Do not treat the 2026-08-17 lock as current where CLAUDE.md / rail code superseded it.

**Still the v1 gate (code + Doc 28 that were not cut):**

1. Hybrid installer of a **proven** payload (not a shell exe).
2. First-run on a machine that never had the dev stack → Generate.
3. Image + video families in §4–§5 that are marked Built/production actually generate on the product surface (retained proofs exist for Wan 2.2 i2v / LTX / etc.; clean-machine does not).
4. Current **visible** rail has no dead chrome.
5. Dependency honesty (no Ready without preflight; “could not check” ≠ fine).
6. Licence badges; Hunyuan territorial notice still to build.
7. Owner visual sign-off (Grade S). Doc 54 T7 walkthrough blocked on this.
8. Cut list respected: Chain / Gen3D / Train stay hidden or honestly labelled.

**Explicitly not v1 (owner):**

| Cut | When | What remains in tree |
|---|---|---|
| Character B | 2026-09-04 | Character Studio page + look/clothes commands |
| Native 3D | Phase D / v2 | Hidden `Gen3DPage` |
| Train in-app | parked 1.1 | Hidden Sohya launcher |
| Comic → video | v2 | Comic stills/pages |
| CogVideoX as a family | post-v1 additive | Contract row `detected` |
| Audio depth | v2+ | — |
| God-file split | health, not a gate | Worker already facaded; not a ship item |

---

## 11. After v1.0 ships

These are real product directions already written in CLAUDE.md / Phase D / owner cuts. Re-survey 3D before building; node names from old notes are forbidden.

### 1.1 (named)

- **In-app trainer (T1)** — LoRA + checkpoint per family; Train page becomes the product, not a launcher.
- Remaining Models teacher-parity (T3) if it missed v1.
- SA2.2 / optimization matrix if v1 shipped on SA1.

### v2 — 3D (Phase D)

Two layers:

1. **Single-asset Image-to-3D** — same LTX pattern: import proven Comfy workflow → `/object_info` → template → adapter → contract. Direction: **TRELLIS.2 first** (MIT, thin/transparent), not Hunyuan3D-2.1. Output: mesh viewer, thumbnails, `.glb` routing. `MediaPreviewController` is image+video only today.
2. **Composition** — Chain Studio. A dressed character is a *chain* of separate assets, not one fused watertight mesh. Open I2-3D models glue clothes to the body; separable garments are not a single-model capability.

Also v2: Text-to-3D once D1+D2 exist; hair/retopo remain Blender, not generator output.

### v2 — Character B

Mesh, separable garments, strand/card hair, beauty. Not a v1 ship gate. The studio is already on the rail so this is depth, not a new page.

### v2 — Comic motion

Script→stills→page is v1; I2V from pages is later.

### Later / unspecified

- Long videos (no spec).
- Audio as a first-class family.
- LLM orchestration.
- Extra video families (CogVideoX and whatever the 2027 board is).
- Host RAM as a first-class constraint.
- Queue lanes keyed on endpoint **id**, not URL string.

---

## 12. Honesty debt still open (not new features)

From Doc 62, still open after `feat/t5-defaults-everywhere`:

| ID | What |
|---|---|
| 3c | Download dialog vs UI-graph missing models |
| 3d | Non-workflow file refused as API prompt / 120s timeout |
| 3l | By-hash match to a bundle mislabels a component weight |
| 3g | Card kind only moves on next inventory scan |
| 3h | NSFW blur has no click-to-reveal |
| 3i | CivitAI 429 not surfaced as “wait, then retry” |
| 4b | `shell_layout` two cases fail on unmet preconditions (should skip, not fail) |
| 4d | Pre-commit ratchet (211 tests) hides a red full suite |

Closed on this branch (do not re-open as “unbuilt”): T5 defaults, Guidance, preset-vs-model, HF card settings, sampler Simple list, Comfy busy-on-exit, first-run CHECKING, `i2v_source_image` containment, dataset T2I canvas, CivitAI stem grouping, Flows unverified prompt, refused-port ~8s, cm-cli 20s cap.

---

## 13. Inspection scope

- Read: `ShellNavigationController.cpp`, `video_family_contracts.py`, `native_image_graphs.py` (`NATIVE_IMAGE_FAMILIES`), `family_capability.py`, `worker_auth.py`, `model_registry.py` (`MODEL_FAMILIES` head), Doc 27/28, CLAUDE.md §§5–6, Current State Ledger (dated **2026-08-24** — Comfy path, Inspire, Train-on-rail, and Character B are stale in that ledger).
- Not re-verified: live generate, MSI, Doc 30 matrix, pytest count.
- Ledger vs code: Comfy live is `C:\sv_comfynext_v034\ComfyUI`, not `C:\sv_comfynext\ComfyUI`. Train is hidden. Character B is v2. Upscale pixel path exists. T5 exists.

When this file and CLAUDE.md disagree, **re-read the symbols above**, then patch both. This census is allowed to go stale the same way the ledger did; the rail and the contracts are the check.
