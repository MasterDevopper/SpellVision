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

**3m. The checkpoint a dropped workflow populates is often the wrong file — FIXED 2026-09-17** (`4c7e739`).

The original wording of 3a, "populates its checkpoint", was written from watching the field fill in. It filled in with **`1x-ITF-SkinDiffDetail-Lite-v1.pth`, an upscale model.** `extractCheckpointFromInputs` took `classType` as an **unnamed, ignored** parameter and matched purely on input name against `{ckpt_name, checkpoint, model, model_name}` — `model_name` is `UpscaleModelLoader`'s input, and `unet_name` was not in the set at all, so a `UNETLoader` could never be seen.

The fix follows the sampler's `model` input upstream — through LoRA loaders, `ModelSampling*`, patch nodes, rgthree power loaders and untyped passthroughs — to the first node that loads a model from a filename, and takes that node's filename input **whatever it is called**. An upscaler is not on the model path, so it stops being reachable by construction rather than by blacklist. `.gguf` and `.sft` now read as model extensions; their absence was why four Wan graphs on `UnetLoaderGGUF` came up empty. Wan 2.2 dual-noise reports **both** experts under `AssetCatalogScanner`'s own vocabulary (`stack_kind: "wan_dual_noise"`, `high_noise_path`, `low_noise_path`), anchored on the high expert, with the other half always named in `warnings`.

**Measured through the shipped builder over all 84 compiled prompts: 60 unchanged, 24 changed, empties 20 → 14.** All 13 this document named are fixed. **Seven more were wrong in the same way and had not been counted** — they only became visible once the walk existed: `film_net_fp32.pt` (frame interpolation), `sam2.1_hiera_large.pt` (segmentation), `rife49.pth` × 4, and `trying-t2v`, which was showing an SDXL checkpoint a third sampler uses rather than either Wan expert. The C++ suite went 14 → 20 cases, and planting the old scan back failed 4 of the 6 new cases with `the model row was filled with an UPSCALE model: 1x-ITF-SkinDiffDetail-Lite-v1.pth`.

**Ruling on a deviation from the brief.** The brief required keeping the name-based scan as a fallback so the 71 already-correct workflows could not regress. The implementer removed it instead, having measured that it protects **zero** correct answers while firing on exactly four graphs and answering `RealESRGAN_x4plus.pth` every time — the original symptom one tier down. **Accepted**, because it also collides with this document's own rule that a graph with no diffusion loader must report nothing and say so. But its stated reason — that those four graphs "lost their links wholesale" — is wrong, and the real reason is 3n below: their links are intact (36 of them), and what is missing is **12 nodes**, which orphans both `UNETLoader`s so that nothing references them. **If 3n is ever fixed, re-measure this decision** — the fallback was judged worthless against a library 8% of which carries broken compiled prompts.

**Two follow-ups it left deliberately:** nothing consumes the new `stack_kind`/`high_noise_path`/`low_noise_path` draft keys yet (the cockpit reads those off the catalog stack, not off a draft), and `applyWorkflowDraft` treats an empty checkpoint as "matched" but an unresolvable non-empty one as blocking — so ten Wan graphs that used to open with no model now name one, and open **blocked** if that file is not on disk. Honest, and visible on the drop path.

**3n. The converter silently dropped what it could not resolve — FIXED 2026-09-17** (`cd6d5ba`).

**The mechanism.** When `convert_ui_graph` met a node whose class it could not resolve, it **omitted the node, kept every reference to it, and returned `errors == []`.** ComfyUI rejects the result with `HTTP 400 prompt_outputs_failed_validation` and a `KeyError` on the missing id inside `validate_inputs` (`execution.py:1184`) — verified against the live server with a synthetic graph that cannot execute, queue confirmed empty afterwards. The dropped classes were Comfyroll, LoraManager, Image Saver, MagCache and a few display-name aliases; all were `mode: 0`, active, not bypassed.

**The fix refuses and names the pack.** Packs are read **offline** from the workflow's own `properties.cnr_id`/`aux_id`/`ver` through `workflow_pack_resolver.declared_packs`. Two new modules carry it: `python/comfy_graph_links.py` (the post-condition) and `python/comfy_missing_packs.py` (the naming).

**Measured over 92 import roots against the live `/object_info`:**

| | before | after |
|---|---|---|
| clean, no dangling ids | 76 | 70 |
| **emitted a prompt WITH dangling ids** | **14** | **0** |
| refused with a named cause | 0 | **20** |

Independently re-measured: 90 UI graphs, 70 emitted, 20 refused, **zero emitting a dangling id.** The 70 clean conversions are **byte-identical** — of 90 hashes, exactly the 20 refusals changed.

**All 20 refusals name something actionable.** 14 name at least one installable pack with a repo URL (Comfyroll, ComfyUI-Image-Saver, efficiency-nodes, KJNodes, lora-manager, mmaudio, multigpu, dynamicprompts, tinyterranodes, krea2edit, LC123, QwenVL-Mod, EsesImageCompare, MagCache); 6 name bare classes because those graphs declare no pack — correct, since name-similarity ranking measures 0 of 16 in this repo.

**Six went clean → refused, and that is not a regression.** The "clean" baseline was the **non-strict** path; the **strict launch path has always raised** on an unresolvable class. Verified by running the pre-change converter out of `git show` against all six: every one raised `ValueError: object_info has no schema for node class…`. Nothing lost the ability to run — the compile path stopped disagreeing with the launch path. (Four are the `img-to-video-*` family on MagCache, which CLAUDE.md §9.2 records as removed and a dead end against v0.34.0, so their only real action is "delete the dead node".)

**The three plants bit, on disjoint failure sets** — silent drop restored: 11 failures across 3 files; the post-condition blinded with the refusal left intact: 5 failures, a *disjoint* set, proving the post-condition does not ride on the refusal; the old widget cursor restored: 3 failures including `assert 480 == 1 : a width must never land in batch_size`, the artifact's exact number.

**The widget/slot bug had no shared root cause** (3n's second half). The bad values exist **only in stored `prompt_api.json` artefacts**; every fresh conversion is already correct — `i2v` node 305 is `batch_size: 1` fresh against `480` stored. The cause was an already-fixed cursor bug: `WanImageToVideo`'s live input order is `positive, negative, vae, width, height, length, batch_size` with widgets `[832, 480, 81, 1]`, and with width and height promoted to links the old cursor did not advance, so `length` read slot 0 and `batch_size` slot 1.

What the two halves *do* share is a delivery channel: **a stale `prompt_api.json` that nothing invalidated.** Now closed on the write side (a refused compile writes nothing and sets `compiled_prompt_path: null`) and on the read side (readiness and `_load_graph` reject a stored prompt carrying dangling ids — 7 of 83 on this box).

**3o. The drop path's stale fallback — FIXED 2026-09-17** (`fe3ad7d`). `compiledPromptPathFor` is now a wrapper over `compiledPromptFor`, returning `{path, refusal, fromStaleFallback}`, and **the refusal is read before the path is even looked at** — a pre-`cd6d5ba` worker wrote `prompt_api.json` unconditionally beside its `ok:false`, so a reply can name a path *and* refuse in the same breath, and that named file is the rotten one.

- **Refusal** (`errors` / `missing_classes` / `dangling_links`, or `object_info_available: false`): no path, no file read, the drop refuses. No page opens, no draft is built, no readiness round trip. The old `"Compiled with N node class(es) missing from the live schema"` log line is deleted — it was the previous semantics written down.
- **Silence** (a reply carrying none of those fields, i.e. an older worker): the fallback survives but is no longer silent — it logs the path, the file's mtime, and *"Nothing vouches for its age — recompile the workflow if the values look wrong."*
- An API-prompt graph still resolves to the import's own `workflow_path`, unchanged and asserted.

**The pack names reach the user.** The refusal prefers the worker's own sentence, which already carries pack names and repo URLs, assembling one from the arrays only when the reply sent them without prose. The test asserts the dialog contains `CR Text Concatenate`, `ComfyUI_Comfyroll_CustomNodes` and the full GitHub URL. The plant — restoring the refusal/silence conflation — failed 4 of 6 new cases, the first naming the file by path.

**3p. A refusal over a core node's title — FIXED** in the same commit. `missing_class_message` now takes `object_info`, and a retitled core node reads as *"These are names the live schema does not publish, not packs to install"* with ``did you mean `LatentUpscale`?`` as text. The suggester is an **exact match after normalisation** (case, punctuation, spacing, plus at most one trailing parenthetical) against class and display names, ambiguous keys dropped — not a similarity ranking, and it never rewrites. Verified live: `wangpt-optimized` stops saying install, `krea2-pro-grade-v17` still names Comfyroll/KJNodes/QwenVL with URLs, `endercomic-v2` keeps "install" for `Int` while suggesting `Load Image Batch`.

**3q. Flows reaches the same stale artefact through a different door.** `qt_ui/WorkflowLibraryPage.cpp:1873` sets `record.compiledPromptPath` to `<importRoot>/prompt_api.json` **unconditionally** — it reads the directory and never a compile reply. Confirmed by inspection along with its consumers.

Its **render** path is not exposed the way the drop path was: `:1004` spends the value on `check_workflow_launch_readiness`, which now rejects a stored prompt carrying dangling ids. Its **draft** path still is: `:2494` hands the value straight to `WorkflowDraftBuilder::Source` for reusable drafts and send-to-cockpit, so a stale-but-well-formed artefact — the `batch_size: 480` shape, which no dangling-id check catches — still reaches the cockpit and from there a render.

Closing it needs Flows to carry a compile verdict it does not currently request. **Inferring one from the file's presence is exactly the mistake `fe3ad7d` just removed**, so this is a real change, not a one-liner.

**3r. A drop while ComfyUI is down — FIXED 2026-09-17, the owner's way.** Asked directly, the owner chose: **open with the values loaded, submission closed, the reason shown as a warning.** `object_info_available: false` is no longer a refusal. It is a **third state**, and the distinction it turns on is that *"we could not check"* is a fact about the **machine** while *"we checked and it is broken"* is a fact about the **graph** — folding them together was defensible and cost offline inspection for nothing.

- **Refused** (`errors` / `missing_classes` / `dangling_links`, or a failure carrying a reason): unchanged. No page, no draft, no readiness round trip, and the sentence naming the packs is the answer. **A fault the reply names outranks the offline flag**, so a reply that says both still refuses — asserted on both surfaces, because widening this path is the one way it could do harm.
- **Unverified** (`object_info_available: false` and no fault named): the page **opens**, submission is **closed**, and the warning is *"ComfyUI is offline, so this workflow's nodes and models could not be checked…"*.
- **Verified**: unchanged.

**Where the offline values come from.** The **source graph**, never a `prompt_api.json` of unknown age — opening offline must not be the door the stale artefact comes back through. `WorkflowDraftBuilder::buildUnverified` drops any named path that is not the source workflow *itself*, so a caller cannot hand it one; the worker's offline reply now carries `graph_format` (a fact about the file, needing no schema), so an **api-prompt** graph fills the cockpit completely while a **UI graph** opens with no values at all. Fewer fields, honestly empty, and the warning says why.

**Submission is closed by construction, not by a label.** The unverified draft carries `safe_to_submit: false`, and `finalizeDraft` treats the builder's verdict as a **ceiling** — so a readiness pass answering `ready` cannot reopen it. Asserted as that outcome on the draft the cockpit reads, not as a property beside it.

**One vocabulary.** `WorkflowDropCoordinator::schemaUnavailableWarning` is the single author of the sentence, called by `WorkflowCompileVerdict` exactly as `compileRefusal` already is, with a test asserting the two surfaces cannot drift. The plant — folding the offline state back into the refusal set — failed 6 of the new cases while both refusal guards kept passing.

Still true of the rest: the 7 stale `prompt_api.json` files are ignored by every reader but neither deleted nor recompiled. **Newly visible:** a drop made while ComfyUI is down pays the `/object_info` transport's full **120 s** retry budget before the page opens — correct for a mid-model-swap blip, far too slow for a ComfyUI that is simply not running, and not this fix's scope.

**3s. A drop while ComfyUI is down takes ~120 s to open.** The `/object_info` transport burns its full retry budget before giving up. That budget is right for a mid-model-swap blip and wrong for a server that is simply not running — a *refused* connection could short-circuit rather than being retried. Same timeout policy as 3b below; they should be fixed together.

**The seven stale `prompt_api.json` files are gone (2026-09-17).** Recompiled through the worker's own compile command so the semantics matched production rather than a script's guess at them. **All seven refused**, so none were rewritten and all seven were removed (backed up outside the repo first). Four are the `img-to-video-*` family on MagCache, which CLAUDE.md §9.2 records as removed and a dead end against v0.34.0, so their only real action was always "delete the dead node". **The library now holds 76 compiled prompts and zero carrying dangling ids** — the class is off the disk, not merely ignored by every reader.

**A sweep false-clearance that was backed out rather than banked — recorded because the near-miss teaches more than the fix.** While building 3r, an offline reply briefly gained a `source_workflow_path` key. Nothing read it, and it made `request-keys-have-readers` **drop `qt_ui/Gen3DPage.cpp` from 5 to 4**: that rule matches key names textually, and `Gen3DPage` sends a request key of the same name, so an unfixed violation looked fixed. Lowering the baseline would have banked a false clearance into the ratchet permanently. The key was removed instead, so the sweep sits at baseline because the key is gone rather than because the number moved. **`Gen3DPage.cpp:441` still sends `source_workflow_path` with no reader anywhere in `python/`** — confirmed by grep, a genuine open violation and the reason the number was allowed to look wrong.

**3b. A first-ever import of a workflow with missing node packs times out at 120 s.** cm-cli cold is ~128 s; the cache is why the *second* drop works. Either raise the budget for a cold import or make the first call warm the cache without holding the request. `python/node_dependency_resolver.py`.

**3c. The Download dialog cannot see a UI graph's missing models.** It reads the import's own model plan; readiness sees them and closes submission. So the user is told the workflow is not ready and is not offered the download that would fix it. `MainWindow.cpp` drop path + `workflow_library_commands.py`.

**3d. A file that is not a workflow is refused for the wrong reason** — treated as an API prompt and timing out, rather than "this is not a workflow".

**3e. `clip_skip` and `guidance` are resolved and never reach a render.** Unblocked by 4a. Traced 2026-09-17, and the two are **not the same defect** — this bullet was one line covering two:

- **`guidance` has a consumer and no producer.** `native_image_graphs.py:104` reads `req.get("guidance")` and wires it into a `FluxGuidance` node. But **no site in `qt_ui/` ever puts `guidance` in a request** — the only C++ mentions are the inspector's display list. So a Flux model's published guidance is fetched from its card, shown to the user in the Models inspector, and then silently replaced by the builder's default at render time. One widget closes it.
- **`clip_skip` has neither.** No graph builder emits a `CLIPSetLastLayer` node anywhere in `python/` — grep finds zero occurrences of the class. So clip_skip is resolved by the model-intelligence stack, displayed in the inspector, and there is nothing in the tree that could apply it. Adding a widget would not make it work; it needs the node in the builder too, or the field should stop being resolved and displayed.

The honesty problem is the same in both cases and is worse for `clip_skip`: the inspector shows a value under a provenance caption naming the site it came from, which reads as a promise that the value is in force.

**3f. A preset and a model's own defaults both write steps and CFG**, so which the user sees depends on the order they touched them. Unblocked by 4a. Traced 2026-09-17: the two writers are `applyPreset` (`ImageGenerationPage_catalog.cpp:1190`, fired from the preset combo at `ImageGenerationPage_ui.cpp:341`, writing steps/cfg/width/height/sampler/scheduler) and `applyModelDefaults` (`ImageGenerationPage_video.cpp:978`, fired on every model change, overlaying whatever the resolver answered through the same `applyResolvedSettings`). **Neither knows the other exists**, so the last one to fire wins and the user cannot tell which they are looking at.

The ruling stands: **a preset is a deliberate user choice and wins until the model changes.** Implementing it means `applyModelDefaults` must know whether a preset has been chosen since the last model change, and must skip exactly the fields that preset owns — not all of its fields, since the overlay's value is that a field the preset does not set still gets the model's answer.

**3j. The HuggingFace arm has never run — WIRED 2026-09-17, after measuring whether it could be.** `hf_lookup.py` was imported by `model_intelligence/__init__.py`, listed in `__all__`, covered by its own unit-test file — and called by nothing, so the three `card:*` tiers of the precedence order were unreachable, which is why all four provenance values in a 759-model run were `site:*` or `table:*`. The summary's `no_match: 79, lookup_failed: 0` read as "both sites were asked". One was.

The constraint the module's own docstring recorded is real and unchanged: **HF has no by-hash endpoint.** A weight is identifiable there only if a repo is already suspected, with `?blobs=true` supplying `siblings[].lfs.sha256` to confirm the guess. So the arm needed a repo-candidate step that did not exist. **It was measured before it was built**, over exactly those 79 weights, anonymously:

| candidate step | identified | |
|---|---|---|
| filename + folder search | **21 / 79** | 26.6% |
| + author-scoped search over the packagers that republish ComfyUI weights | **32 / 79** | 40.5% |
| + one shared repo index across the run | **38 / 79** | 48.1% |

Each step earns its place. Shortening the query is what finds `Lightricks/LTX-2.3` from `ltx-2.3-22b-distilled-lora-384-1.1`. The author-scoped pass is for files whose repo shares no token with them at all — `hunyuan_video_t2v_720p_bf16` lives in `Comfy-Org/HunyuanVideo_repackaged`. And the shared index is the cheapest of the three: once any weight confirms a repo, every other weight in the library matches against it for free, which is how `llava_llama3_vision` — same repo, no common search term — is identified without a single search.

**48.1% is not "near zero", so the arm was wired rather than deleted**, in `refresh.RefreshJob._hf` behind `hf_candidates.py`. The property that makes guessing safe is that a candidate is accepted ONLY on a sha256 match, so a wrong guess costs a request and can never mislabel a file — the opposite of 3l below, which is a *correct* hash match to a bundle. A `lookup_failed` never reaches the second arm. `identified_hf` is reported beside `identified` so a single total cannot hide which arm is working.

**Verified independently 2026-09-17, and one claim needs narrowing.** Over the live library: 759 sidecars, **27 now carry a HuggingFace source**, and the HF arm is genuinely supplying identity and licence for them — `sigclip_vision_patch14_384` reads `apache-2.0`, the three Hunyuan video weights read `other`. **19 sidecars now carry a `license.name`, all of them from HF card frontmatter**, where CivitAI supplies none.

But **the `card:*` settings tiers still contribute nothing to this library — the provenance histogram is unchanged at `site:image-meta-mode` 2591 · `table:family-default` 1738 · `site:trainedWords` 353 · `site:image-meta-weak` 243, with zero `card:*`.** The capability is real: asked directly, `settings_from_readme` on `Lightricks/LTX-2.3` returns **steps 8 / cfg 1 at `card:prose-regex`**, agreeing with the distilled two-stage route in CLAUDE.md §6. It simply never fires here, for two structural reasons worth writing down:

1. **HF is only consulted when CivitAI found nothing** — correct, and it means a weight CivitAI carries can never reach its HF card. `ltx-2.3-22b-dev`, the very model whose card parses cleanly, matched CivitAI, so its card is never read.
2. **`card:*` sits below `site:image-meta-mode` in the precedence order**, so even where both exist the site's own render metadata wins.

So: *reachable in code, unexercised in data.* Say it that way. A future reader who sees "wired" and assumes card values are flowing into defaults would be wrong, and would go looking for a bug that is not there.

The remaining misses are the honest answer, not a shortfall: the owner's own fused LoRAs (`Fused_*`, `Penis_*`, `st0m4chBulg3_*`) and CivitAI LoRAs nobody mirrored to HF. Live proof through the shipped path: `trellis_2_bf16` → `Comfy-Org/TRELLIS.2` (licence `mit`), `ip-adapter-plus_sd15` → `InvokeAI/ip_adapter_plus_sd15` (`apache-2.0`), and `Lightricks/LTX-2.3`'s card yields `steps 8 / cfg 1` at `card:prose-regex` — the first `card:*` provenance this project has ever resolved, and it agrees with the distilled two-stage route CLAUDE.md §6 records.

**3k. Creator and licence are null on all 680 identified models — FIXED 2026-09-17.** `CivitaiClient.model()` existed at `civitai_lookup.py:109` and had no caller anywhere in the tree. Measured live against the public API rather than assumed:

- the by-hash **version** payload carries no `creator` and no licence flag at all; its `model` sub-object holds only `name`, `type`, `nsfw`, `poi` — which is exactly what `build_payload` was reading, and why it produced four nulls rather than an error
- the **parent model** payload (`GET /api/v1/models/{id}`) carries `creator.username` and all four flags — `allowCommercialUse` as a LIST (`["Image", "RentCivit", "Rent"]`), `allowDerivatives` / `allowNoCredit` / `allowDifferentLicense` as booleans. It carries no licence NAME: CivitAI states permissions, not an SPDX identifier, so `display.license.name` stays the HuggingFace card's field.

The refresh now fetches the parent for every hit, memoised per model id on the client — **532 distinct ids behind 680 weights**, so it is one request per id rather than one per weight. `scripts/dev/backfill_model_metadata.py` fills the sidecars already on disk from the `identity.sources[].model_id` each one already stores: no re-hash, two fields written and nothing else.

**Run live over both roots: creator `0 → 675` and licence flags `0 → 677`, of 680 identified.** The remaining three are one model (`shade_slider`, three copies on disk) whose CivitAI id now answers 404 — recorded as `no_parent`, sidecar untouched. Two more carry flags but no creator, because the uploader's account is gone. **CivitAI answered 429 for 76 sidecars on the first pass**, which is why the script has `--only-missing`: a throttle must cost a re-run of what it missed, not of everything (see 3i — still unsurfaced to the user).

**Still open, and deliberately not done here because it needs a C++ build:** the Qt inspector reads `display.license.name` ALONE (`ModelIntelSidecar.cpp:224`), so `ModelInspectorPanel::licenceText()` still renders "Licence: not stated by the site" for a CivitAI weight whose permission flags are now in the file. The data is disclosed; the line does not read it yet.

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
