# Doc 62 — T2–T6 follow-ups

**Status:** open work list, opened 2026-09-17 on branch `fix/t2-t6-followups`, off the T2–T6 merge (`bd084ab`).

Every item here was found by the work that built T2–T6 and recorded rather than fixed, because fixing it belonged to a different wave or would have widened one already in flight. Each says what it is, where it lives, and how it was found — a list of symptoms is not a work list.

Ordered by what a user hits first.

---

## 1. Coverage, not code — the largest gap by far

Every gate reads PARTIAL for the same reason: the mechanism works and has been pointed at a fraction of the library.

| gate | proven on | the whole |
|---|---|---|
| T3 models | **680 identified of 759** (was 14) | 759 |
| T5 defaults | **706 models carry a `recommended` block**; 483 of them site-sourced | four pages × ~16 families |
| T4 optimizations | krea2, ltx | six shipped families |
| T2 drop | 5 workflows, **none video** | ~90 imported |
| T6 routing | SDXL on the node | every family it can run |

**The refresh has been run — 2026-09-17, 58.0 min over both roots.** `examined 759 · identified 680 · no_match 79 · lookup_failed 0 · errors 0`, 759 sidecars on disk, **2060 preview images** referenced, kinds resolved as 498 lora / 131 checkpoint / 51 diffusion_model / 20 vae / 18 text_encoder / 18 other / 8 embedding / 7 clip_vision / 6 upscaler / 2 style_model. Provenance across every resolved field: `site:image-meta-mode` 2591 · `table:family-default` 1738 · `site:trainedWords` 353 · `site:image-meta-weak` 243.

That last list is how item **3j** below was found: three of the nine precedence tiers scored zero, and the reason turned out not to be the library.

---

## 2. Regressions in honesty — things that now correctly look worse

These are not bugs. They are the old answer being wrong. Listed so nobody "fixes" them back.

- **`krea2-compact-t2i-v10` shows NOT ready in Flows**, where it used to show Ready. It has 1 of 4 models present. A UI graph with no compiled prompt yields zero model references, and zero read as "nothing missing".
- **The model-stack card's "Loaded: `<name>`" label no longer updates on a drag-drop**, because the window claims the drag first. The draft chip on the page the workflow lands on is better feedback and on the right page — but that card changed.

---

## 3. Real defects, in the order a user meets them

**3a. Pro Grade v17 lands with an empty prompt — FIXED 2026-09-17** (`8e550ab`, `490ba7e`).

Root cause: `WorkflowDraftBuilder` recovered sampling from `KSampler`/`KSamplerAdvanced` only. Pro Grade has neither — it is `SamplerCustomAdvanced` × 2 over `CFGGuider`, `KSamplerSelect`, `RandomNoise` and split sigmas, the core custom-sampler vocabulary every modern Flux/SD3/Krea graph uses. Its three `CLIPTextEncode` nodes are all `mode: 4` (bypassed) and correctly pruned, so the conditioning walk had nothing to find either; the real text sits on the author's own `LCPositive`/`LCNegative` nodes behind a custom pipe.

The builder now walks `guider` → `CFGGuider`/`DualCFGGuider`/`BasicGuider` for positive/negative/cfg, `noise` → `RandomNoise.noise_seed`, `sampler` → `sampler_name`, and the `sigmas` chain for steps and scheduler, each followed exactly one hop to a literal, refusing when ambiguous. The `KSampler` path is unchanged and still wins when both are present.

**And it no longer invents what it cannot read.** An unrecoverable field is absent from the draft rather than written as `0`/`0.0`/`100`, and each is named in `warnings`. A related bug surfaced in the same place: `applyWorkflowDraft` wrote the prompt boxes unconditionally, so an unreadable prompt **erased the user's own**. Pro Grade v17 still yields no prompt — correct, its text is behind a pack node — but now says so in eight named warnings instead of showing a fabricated canvas.

**One correction to this item's original wording.** The `100×100` was *not* a leftover zero: width/height came from the first `width` input **anywhere in the graph**, which in Pro Grade is an `LCImageCrop`. The canvas is now reached from the sampler's own `latent_image`. Measured over the 83 imported workflows carrying a compiled prompt: 60 unchanged, 18 both-nothing, 1 corrected, 4 now honestly absent.

The plant bit: with the old behaviour restored, 3 of the 5 new cases failed with the owner's screen verbatim — `draft claims prompt=, negative_prompt=, sampler=, scheduler=, steps=0, cfg=0, seed=0, width=100, height=100 from a graph that says nothing about any of them`.

**3m. The checkpoint a dropped workflow populates is often the wrong file, and this item's own text above was wrong about it.** "Populates its checkpoint" was written from watching the field fill in. It fills in with **`1x-ITF-SkinDiffDetail-Lite-v1.pth`, an upscale model** — the real one is a `UNETLoader.unet_name` (`Krealism_V1.0.safetensors`) the scan never looks at.

`extractCheckpointFromInputs` (`WorkflowDraftBuilder.cpp:228`) takes `classType` as an **unnamed, ignored parameter** and matches purely on input name against `kCheckpointInputNames = {ckpt_name, checkpoint, model, model_name}`. `model_name` is `UpscaleModelLoader`'s input; `unet_name` is not in the set at all. So an upscaler wins and a `UNETLoader` can never be seen.

Measured across the 84 compiled/API prompts in the imported library: **13 are wrong (15%)** — 3 pick an upscale model as the checkpoint (`krea2-pro-grade-v17`, `t2i-dexters-mom`, `t2i-mirko`), and **10 pick nothing although a `UNETLoader` is right there**, including **every Wan 2.2 video graph** (`t2v-14b-40min`, `video-wan2-2-14b-t2v`, `wan-simple-t2v`, `working-t2v`, `minimal-wan`, `image-to-video-wan22-14b`, `wangpt-optimizedv3`, `nsfw-t2v-14b-40min`) and the owner's own `krea2-compact-t2i-v10` and `krea2-character-forge-sheet`. This is the highest-value remaining follow-up in the drop path.

**3n. The UI→API converter drops nodes and mis-assigns widget values.** Converting Pro Grade v17 through the live converter produces a prompt with **24 distinct missing node ids referenced by 30 inputs** — including three `LCPipeOut` pipes, the `SaveImage` source and the `UltimateSDUpscale` source. ComfyUI would reject that prompt outright. Separately, the same converter assigns widget values to the wrong slots: `EmptyHunyuanLatentVideo` with `batch_size: 480`, `WanImageToVideo` with `batch_size: 960, length: 640` — numbers that are plainly a width and a height landing in the wrong fields, so probably one root cause. `python/comfy_graph_converter.py`.

**3b. A first-ever import of a workflow with missing node packs times out at 120 s.** cm-cli cold is ~128 s; the cache is why the *second* drop works. Either raise the budget for a cold import or make the first call warm the cache without holding the request. `python/node_dependency_resolver.py`.

**3c. The Download dialog cannot see a UI graph's missing models.** It reads the import's own model plan; readiness sees them and closes submission. So the user is told the workflow is not ready and is not offered the download that would fix it. `MainWindow.cpp` drop path + `workflow_library_commands.py`.

**3d. A file that is not a workflow is refused for the wrong reason** — treated as an API prompt and timing out, rather than "this is not a workflow".

**3e. `clip_skip` and `guidance` are resolved and never reach a render.** Unblocked by 4a. Traced 2026-09-17, and the two are **not the same defect** — this bullet was one line covering two:

- **`guidance` has a consumer and no producer.** `native_image_graphs.py:104` reads `req.get("guidance")` and wires it into a `FluxGuidance` node. But **no site in `qt_ui/` ever puts `guidance` in a request** — the only C++ mentions are the inspector's display list. So a Flux model's published guidance is fetched from its card, shown to the user in the Models inspector, and then silently replaced by the builder's default at render time. One widget closes it.
- **`clip_skip` has neither.** No graph builder emits a `CLIPSetLastLayer` node anywhere in `python/` — grep finds zero occurrences of the class. So clip_skip is resolved by the model-intelligence stack, displayed in the inspector, and there is nothing in the tree that could apply it. Adding a widget would not make it work; it needs the node in the builder too, or the field should stop being resolved and displayed.

The honesty problem is the same in both cases and is worse for `clip_skip`: the inspector shows a value under a provenance caption naming the site it came from, which reads as a promise that the value is in force.

**3f. A preset and a model's own defaults both write steps and CFG**, so which the user sees depends on the order they touched them. Unblocked by 4a. Traced 2026-09-17: the two writers are `applyPreset` (`ImageGenerationPage_catalog.cpp:1190`, fired from the preset combo at `ImageGenerationPage_ui.cpp:341`, writing steps/cfg/width/height/sampler/scheduler) and `applyModelDefaults` (`ImageGenerationPage_video.cpp:978`, fired on every model change, overlaying whatever the resolver answered through the same `applyResolvedSettings`). **Neither knows the other exists**, so the last one to fire wins and the user cannot tell which they are looking at.

The ruling stands: **a preset is a deliberate user choice and wins until the model changes.** Implementing it means `applyModelDefaults` must know whether a preset has been chosen since the last model change, and must skip exactly the fields that preset owns — not all of its fields, since the overlay's value is that a field the preset does not set still gets the model's answer.

**3j. The HuggingFace arm has never run. `python/model_intelligence/hf_lookup.py` is imported by `model_intelligence/__init__.py`, listed in `__all__`, covered by its own unit-test file — and called by nothing.** A tree-wide grep for `hf_lookup`, `HfClient`, `card_identity`, `settings_from_readme` and `sha256_index` returns the module itself, the package re-export, one comment in `resolve.py`, and `tests/test_model_intelligence_hf.py`. No production path. So the three `card:*` tiers of the precedence order — `card:frontmatter`, `card:snippet-regex`, `card:prose-regex` — are unreachable, which is why all four provenance values that appeared in a 759-model run are `site:*` or `table:*`.

**The 79 `no_match` models are exactly the HuggingFace-origin ones**: `hunyuan_video_t2v_720p_bf16`, `hunyuan_video_I2V_720_fixed_fp8_e4m3fn`, `wan2.1_i2v_480p_14B_fp16`, both Wan 2.2 GGUF experts, `dino_v3_vit_l`, `sigclip_vision_patch14_384`, `llava_llama3_vision`, `open_clip_model`, `ip-adapter-plus_sd15`. Every one of them is a weight CivitAI would never carry, and every one has a model card the `card:*` tiers exist to read.

**The honesty cost is the part that matters**: the summary reports `no_match: 79, lookup_failed: 0`, which reads as "both sites were asked and neither had it." One site was asked. The count is true and the impression it gives is false.

Note the real constraint before fixing it — the module's own docstring records it: **HF has no by-hash endpoint** (verified 2026-09-16), so a weight can only be identified there if a repo is already suspected, with `?blobs=true` supplying `siblings[].lfs.sha256` to confirm the guess. Wiring this arm therefore needs a repo-candidate step that does not exist yet; it is not a one-line call. That is presumably why it was left, but it was left silently.

**3k. Creator and licence are null on all 680 identified models, because the parent-model fetch is never made.** `CivitaiClient.model()` exists in `python/model_intelligence/civitai_lookup.py:109` and, like `hf_lookup`, **has no caller anywhere in the tree.** Measured live against the public API rather than assumed:

- the by-hash **version** payload carries no `creator` and no licence flags at all; its `model` sub-object holds only `name`, `type`, `nsfw`, `poi`
- the **parent model** payload (`GET /api/v1/models/{id}`) carries `creator` (`{"username": "CivitaiOfficial", …}`) and all four flags — for the probed model, `allowCommercialUse: ["RentCivit", "Image"]`, `allowDerivatives: true`, `allowNoCredit: true`, `allowDifferentLicense: true`

So every sidecar writes `"creator": null` and a `license` object whose four fields are all null, 680 for 680, and W5's promised inspector "licence line" can only ever render blank. **This is the cheapest of the three to close and the one with the most downstream weight** — Doc 28's release-readiness checklist has a licence section, and the repo already carries the lesson that licence must be *disclosed*. Disclosing a blank is worse than not having the line.

**The backfill does not need a re-hash.** Every sidecar already stores `identity.sources[].model_id`, and the distinct model-id count is far below 680, so this is one extra GET per distinct model and a sidecar rewrite — seconds to minutes, against the 58 minutes the hashing pass cost.

**3l. A by-hash match to a bundle mislabels a component weight.** `clip_vision_g.safetensors` now displays as **"ControlNetXL (CNXL)"**. The hash match is genuinely correct — those bytes are in that CivitAI upload — but the name belongs to the bundle, not to the file, and the Models page shows the display name in place of the filename by owner requirement. A component weight matching a bundle should keep its filename, or show both. Low frequency, high confusion.

**3g. Card kinds are read at scan time**, so a sidecar written after a scan does not move the card between tabs until the next inventory refresh. The inspector updates immediately; the card does not.

**3h. NSFW blur has no reveal.** A blurred preview is a 10×10 downscale re-expanded — genuinely unreadable, and permanent until the setting changes. No click-to-reveal.

**3i. No rate-limit backoff is surfaced.** A CivitAI 429 lands in `lookup_failed` and the summary says so, but the user is not told to wait rather than retry.

---

## 4. Test-suite debt

**4a. `test_godfile_split` — FIXED 2026-09-17** (`9f1f318`, `759ba55`). `ImageGenerationPage.cpp` went 3135 → **1008** lines. `buildUi()` moved whole into a new `qt_ui/ImageGenerationPage_ui.cpp` (2211 lines), which now owns widget construction: the three splitter panes, every card and control in them, the controllers created alongside the widgets they drive, and construction-time connections. The parent keeps what the page *does*. A second commit removed 65 lines the earlier preview split had left dead. The header gained nothing — it was a move, not a refactor. Fourteen Python checks had spelled `ImageGenerationPage.cpp` and asserted on lines that merely happened to live there; they were restated as properties (`cpp_source.family_text()`, `definition_body("buildUi")`) rather than repointed at the new filename, and two sweep baselines were rekeyed, not raised. **3e and 3f are unblocked.**

**4b. `shell_layout` fails on two cases**, both **self-invalidating guards failing on an unmet precondition** — `a_control_inside_a_collapsed_tab_keeps_its_value` ("no inspector tab put a spin box on screen") and `a_deferred_rail_page_built_after_a_switch_arrives_into_the_switched_shell` ("train was already built; nothing was proved"). A test that cannot set up its subject should report that it could not try, not report failure. Its own defect class.

**4c. Ten more pre-existing failures** on main, mostly worker-timeout shaped. They predate this arc and were verified against a clean tree.

**4d. The pre-commit hook runs only the 211 ratchet-marked tests**, so a red full suite is invisible to it. That is how a set of failures swapped underneath a matching count during this arc.

---

## 5. Architecture debt this arc created or exposed

**5a. `kLeverProbes` is a second list of lever ids** in the Runtime panel's C++ (`qt_ui/shell/OptimizationEvidence.cpp:39`), mirroring `optimization_levers.ALL_LEVERS`. Re-verified 2026-09-17: **still in sync, 11 ids each, same order.** That is the whole problem — it is in sync because two people have checked it by hand twice, which is not a property of the tree. The fix is a sweep rule that reads both lists and compares them; the failure mode stays safe either way (an id added only in Python renders as an arm this build cannot read, never as "not active").

**5b. Queue lanes key on the endpoint URL string**, so `http://192.168.1.127:8188` and `http://spellnode:8188` would be two lanes for one machine. The registry gives an endpoint a stable id; lanes should key on that.

**5c. `INPUT_FOLDERS` is a table** mapping loader input → `/models/{folder}`. A missing entry costs a slower check and never a wrong verdict, but tables go stale.

**5d. The arm memory is process-wide and leaks between pytest tests.** A `forget_arm()` call sits in one fixture; no ratchet enforces it for future tests that launch a manager.

**5e. `host_ram_gb` is accepted and unwired.** Deliberate — CLAUDE.md §6 records host RAM as real but unmeasured, and inventing a threshold would repeat the VRAM mistake. Either measure it or drop the parameter.

---

## 6. Measurement follow-ups

**6a. The harness should measure the baseline twice — first and last — and report against the trailing one.** The first arm of a session runs 7–8% slow even after its cold render is discarded, which is larger than most effects being measured. Currently done by hand; it belongs in the harness.

**6b. SageAttention 2.2 is not installed.** The venv has `sageattention 1.0.6`, which is SA1 Triton kernels. The research puts the first real measurement at SA2.2. Installing it changes the owner's render environment, so it is the owner's call — but every sage number in Doc 60 should be read as SA1 until then.

**6c. Four families are untimed** — wan, hunyuan, mochi, flux — and video is where the only real attention win showed up.

---

## Related

Doc 54 (requirements) · Doc 55 (the walkthrough and its verdict table) · Doc 60 (T4 measurement) · Doc 61 (SpellNode setup) · the per-wave ledgers under `.superpowers/sdd/2026-09-1*/progress.md`, which hold every ruling and the reasoning behind it
