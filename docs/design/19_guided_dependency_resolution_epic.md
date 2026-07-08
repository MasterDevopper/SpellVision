# Doc 19 — Guided Dependency Resolution + Assisted Download (epic)

> **Status: MAP + REPORT complete; not built (pre-wiring). Amended 2026-07-07 after Wan i2v landed.**
> Filenames extracted from code; source refs web-verified against real HF repos (flagged where unconfirmed).
> **Prerequisite MET (af0396c):** native Wan i2v shipped — `clip_vision` row is now FROZEN (§2). The i2v
> wire live-validated this epic twice: it was blocked on two missing deps that had to be hand-fetched
> (`wan2.1_i2v_480p_14B` + `clip_vision_h`), and it hit the VAE variant crash (§3(c)) — interim fixed
> resolver-side (`wan-vae-variant-match-interim`, 92d6f37), full producer-side resolution supersedes (§5b).
>
> **Consolidated 2026-07-08 → §6 (Component Auto-Population System):** the producer-side design is unified
> into one engine (manifest-as-data + generic resolver + constrained auto-populate). Amendments A1–A4 are
> folded into **§6.6**, and the reactively-built one-off resolvers (`wan-vae-variant-match`, `clip_vision`)
> are recorded there as the fragments Pass A converts into manifest rows (retaining them as a worker backstop).
> §3(c)/§4/§5/§5b remain the detailed anchors; §6 is the coherent system view over them.

## Objective
Turn the greyed-generate-button / cryptic-error dead-end into "here's what this model is missing → **Download** or **Locate**," including authenticated HF/Civitai fetches.

---

## Principle — Requirements vs. specifics (the reframe that makes unknowns safe)
Because SpellVision **owns graph construction**, the split-stack template/contract for a family declares its **slots** (VAE, text-encoder, clip-vision, …). Those slots ARE the requirement list, and they exist whether or not the manifest has ever seen the user's checkpoint. So the feature **never** says "no idea what this needs" — worst case: "needs a VAE, text encoder, clip-vision; I can auto-fetch two, Locate/link the third."

The manifest is an **accelerator** that resolves slots → specific downloadable files; it is **never** the thing that defines requirements.

**Hard rule: never auto-download on a guess.** Confidently wrong (fetching the canonical Wan VAE for a fine-tune that needs a custom one) is worse than honestly unsure — it burns a multi-GB download and ships broken output that reads as SpellVision's fault. **Automation gates on confidence.** The Download button and the manual-assist path are the same UI surface at different confidence tiers — not a happy path plus an error state.

## Definitions — Resolution tiers (per missing component)
The readiness producer emits a **tier + confidence per component, never a boolean**:
- **known-canonical** — high-confidence family (classifier verdict) + a canonical file present in the manifest → offer one-click **Download** (still an offer, not silent).
- **family-recommended** — known family, unknown variant/specifics (e.g. Wan but 2.1-vs-2.2 VAE undetermined) → recommend with explicit "for [family]; override if you know better"; no silent fetch.
- **unresolved-slot** — unknown family, or no manifest hit → **manual assist only**: Locate existing / paste source link / open the model's source page. First-class, not a fallback.

## Scoping boundary — Missing-required vs. incompatible-choice
This feature resolves **missing required files** (downloadable). A LoRA trained for a base you didn't load, or a mismatched encoder, is an **incompatibility** — a *warning*, not a download (no fetch fixes it). The producer must **tag these distinctly**; never let "Download to fix" leak onto a compatibility mismatch. (No such tagging exists today — net-new.)

---

## 1. Confirmed-map anchors (verified live)

| Claim | Verdict | Anchor |
|---|---|---|
| `materialize_asset` parses hf_repo/civitai/url/local; Civitai `Bearer` + `CIVITAI_API_KEY` env | ✅ | `model_sources.py:195, 367-369, 238` |
| `build/apply_model_install_plan` = fetch engine, driven by `workflow_importer` | ✅ but **workflow-scan-shaped** | `model_dependency_resolver.py:167, 211`; `workflow_importer.py:99-105` |
| Preferred filenames exist (VAE, umt5) but carry **no source** | ✅ | `worker_service.py:4246` (`_preferred_video_vae_name`), `:4326` (`_sv_video_text_encoder_name`) |
| `ModelFamilySpec` has no dependency/source fields | ✅ (10 routing-only fields) | `model_registry.py:26-40` |
| Contracts declare component types | ✅ | `video_family_contracts.py:47-127` |
| Readiness is LTX-shaped | ✅ **LTX-only** | `video_family_readiness.py` (`LtxReadinessSnapshot:44`, `missing_assets:77`) |
| Qt readiness surface is thin | ✅ static text presenter | `VideoReadinessPresenter` (`readyMessage`/`blockingMessage`) |
| Credential store greenfield | ✅ **absent** | no QtKeychain anywhere; SettingsPage has no token handling; no secrets in QSettings |

**Three findings that shape the epic:**
1. **HF gated-repo auth is the one real engine gap.** `hf_repo` refs are returned **unfetched** (`model_sources.py:219-221`) or flagged `install_action="review"` (`model_dependency_resolver.py:347-354`). Only actual HF fetch = diffusers `from_pretrained` with **no token** (`memory_optimization.py:774/781`, `worker_service.py:5389`). Civitai is fully wired; HF is not.
2. **Install-plan producer is workflow-scan-shaped** — `build_model_install_plan(report: WorkflowScanReport)` iterates `report.model_references`. No equivalent producer from `contract.required_components` for the generation page.
3. **Nothing reads `required_components`.** They're descriptive tuples; only LTX computes "missing" (regex scan → `missing_assets: list[str]`). Wan/Hunyuan compute nothing.

---

## 2. THE MANIFEST TABLE (the crux) — v1.0-local families
`[HAVE]` = extractable from code. Source refs = net-new authoring (✅ = web-verified against the live HF repo tree API).

### Wan — canonical repos `Comfy-Org/Wan_2.2_ComfyUI_Repackaged` + `Comfy-Org/Wan_2.1_ComfyUI_repackaged`
| Component | Canonical filename | [HAVE?] | Source ref (verified ✅) | Confidence / variant |
|---|---|---|---|---|
| high_noise_model (t2v) | `wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors` | ❌ (stack key only) | ✅ Wan_2.2 `/split_files/diffusion_models/` | version-pinned |
| low_noise_model (t2v) | `wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors` | ❌ | ✅ same | version-pinned |
| high_noise_model (i2v) | `wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors` | ❌ | ✅ same | version-pinned |
| low_noise_model (i2v) | `wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors` | ❌ | ✅ same | version-pinned |
| vae | `wan2.2_vae.safetensors` **or** `wan_2.1_vae.safetensors` | ✅ (`_preferred_video_vae_name`) | ✅ Wan_2.2 `/split_files/vae/` (both present) | **variant-dependent (2.1 vs 2.2)** |
| text_encoder | `umt5_xxl_fp8_e4m3fn_scaled.safetensors` | ✅ (`_sv_video_text_encoder_name`) | ✅ Wan_2.1 `/split_files/text_encoders/` (also in 2.2) | family-default |
| **clip_vision** (i2v optional) | `clip_vision_h.safetensors` (CLIP-ViT-H) | ✅ (`_sv_core_wan_clip_vision_name`, af0396c) | ✅ Wan_2.1 `/split_files/clip_vision/` | **FROZEN (live, af0396c):** family-default; Wan 2.1 i2v **requires** it, 2.2 **omits** it — `WanImageToVideo.clip_vision_output` is optional so one node covers both (confirmed vs live `/object_info`) |

### LTX — `Lightricks/LTX-2.3` (already production + files on-disk; low priority)
| Component | Filename | Source | Note |
|---|---|---|---|
| model | `ltx-2.3-22b-dev.safetensors` | ✅ `Lightricks/LTX-2.3` | version-pinned (46 GB) |
| video vae | `LTX23_video_vae_bf16.safetensors` | ⚠ **not in LTX-2.3 root** (likely a ComfyUI-repackaged LTX repo) — unconfirmed | `_preferred_video_vae_name` has **no LTX branch** |
| text projection | `ltx-2.3_text_projection_bf16.safetensors` | ⚠ unconfirmed | — |
| audio vae (optional) | `LTX23_audio_vae_bf16.safetensors` | ⚠ unconfirmed | — |

### Hunyuan — `Comfy-Org/HunyuanVideo_repackaged` (contract status `detected`/future → lighter)
| Component | Filename | Source |
|---|---|---|
| vae | `hunyuan_video_vae_bf16.safetensors` | ✅ `/split_files/vae/` |
| model / text_encoder | (drill-in needed) | `/split_files/{diffusion_models,text_encoders}/` |

### Gap quantification (the finding)
- **Filenames:** partial-extractable — only Wan **VAE + text_encoder** and Hunyuan **VAE** come from code. The **diffusion models** (stack keys, not names), **clip_vision** (no helper), and **all LTX components** (no `_preferred_video_vae_name` LTX branch) are NOT in the preferred helpers.
- **Source refs:** **100% net-new** — nothing in code carries a source. Web-verified: Wan (2.1+2.2) ✅, Hunyuan VAE ✅, LTX main ✅; LTX components need one confirmation pass (low priority — on disk).
- **Verdict:** the manifest is **mostly authored, lightly extracted** (filenames seed ~2 of ~6 Wan components), but **bounded and repo-verifiable.**

---

## 3. Tiering inputs — exist vs. build
| Signal | Status | Detail |
|---|---|---|
| **(a) Slot list** from template/contract (manifest-independent requirements) | ✅ EXISTS (declared) / ⚠ not yet read | `contract.required_components` per family; nothing consumes it — the producer must. Queryable static tuples. |
| **(b) Family + confidence** from the classifier | ✅ EXISTS, reusable | `model_classification.classify_model` → `family` + `source_layer` + `confidence`; **video families work** (verified `ltx-2.3-22b-dev → family=ltx via metadata`). metadata-sourced > filename-only maps onto the tiers. |
| **(c) Variant disambiguation** (Wan 2.1 vs 2.2 VAE) | 🔴 **ALREADY BIT THE SHIPPED PATH** | Not a future tier-c upgrade — this is the concrete failure **af0396c** hit: a Wan 2.1 model has a **16-channel** latent, but the resolver's blind 2.2-first preference wired `wan2.2_vae` (**48-channel**) → **VAEDecode crash** on the default (bare-stack) i2v path. **Interim shipped:** `wan-vae-variant-match-interim` (92d6f37) — resolver-side family-VAE match via a filename version probe (`_wan_vae_version_marker`/`_wan_vae_preference`) in `_sv_core_wan_vae_name` + `_preferred_video_vae_name`; recommended because it's **one site covering every entry path**. The full **producer-side** resolution (variant probe → `best_present_match` → cockpit auto-populate) supersedes it. |

---

## 4. The two forks — recommendations

**Fork 1 — Manifest home: (A) `ModelFamilySpec` fields vs (B) standalone data file → (B), strongly.**
`ModelFamilySpec` is a lean frozen routing descriptor (10 flat tuples). The manifest needs **per-variant** entries, **per-source** (HF primary + Civitai fallback), **confidence**, `version_pinned` flags — a nested shape that bloats the registry and couples routing to source data. **(B) a standalone `model_dependency_manifest` data file** keeps the registry lean and is **community-updatable**: an `unresolved-slot` a user resolves by hand ships as a new entry, steadily converting manual-assist → one-click. Shape:
```
family → component → [variant] → { canonical_filenames[], source: {hf_repo, path},
                                    civitai_fallback?, confidence, version_pinned }
```
Confirmed the data-file shape supports per-variant + confidence (the Wan VAE row needs exactly this).

**Fork 2 — Producer home: extend readiness vs new resolver → NEW family-agnostic resolver.**
`video_family_readiness` is LTX-hardcoded (LTX node names, regexes, `LtxReadinessSnapshot`); generalizing it means gutting it. A **new resolver** cleanly composes the existing pieces — `contract.required_components` (slots) + `classify_model` (family+confidence) + the manifest (slot→source) + an on-disk/`/object_info` diff — and emits the tiered structure. LTX readiness becomes one consumer (or is subsumed later), not the base class.

**Producer output shape (not a list of strings) — ONE resolver, TWO consumers (download panel + auto-populate):**
```
[{ component, slot, tier, confidence,
   best_present_match?,     # top-ranked ON-DISK candidate for dropdown pre-fill (ranked by the
                            # same preferred-filename logic) -- read by the auto-populate consumer
   candidate_source?,       # downloadable source ref -- read by the download-panel consumer
   kind: "missing_required" | "incompatible" }]
```

---

## 5. Recommended pass sequence (post-i2v) + gate

1. **Manifest data file** (fork 1B) — filenames [extract] + sources [author, repo-verified]. Gated on the §2 table. **Preamble — gated-repo check:** before authoring, verify **unauthenticated reachability** of every canonical file the manifest points at. If any is gated, **Pass 3 (HF-token) becomes a hard dependency of Pass 5a's happy path and moves up**; if all public, Pass 3 stays late (user-supplied gated models only). (Wan/LTX/Hunyuan canonicals verified public in §2.)
2. **Family-agnostic actionable readiness** (fork 2) — `required − on-disk → [{component, slot, tier, confidence, best_present_match?, candidate_source?, kind}]`; tags missing-required vs incompatible distinctly; driven by template-slots + classifier-confidence + variant-inspection. **Emits `best_present_match`** (top on-disk candidate per slot) **and the single-vs-dual verdict** (Wan 2.1 single vs 2.2 dual-noise — the variant signal §3(c) needs). **Floor confirmation:** verify `classify → family → contract → required_components` resolves for a checkpoint the manifest has **never seen** — that path is the **unresolved-slot floor**, the load-bearing link between "unknown model" and "known slots."
3. **HF-token auth in `materialize_asset`** — the confirmed gap; add `hf_hub_download`/token path for gated repos.
4. **QtKeychain credentials + Settings/first-run** — HF token + Civitai key fields (token/key, not user/password). New CMake `find_package(Qt6Keychain)` dependency (Windows Credential Manager backend); QSettings holds only the entry-point + "connected ✓", **never the secret**. (`wincred` wrapper is the fallback.)
5. **t2v/i2v UI surface** — one producer, **two consumers**, split into:
   - **5a — download panel** (reads `candidate_source` + `tier`): missing-components panel rendered **per tier**: **Download** (known-canonical) / **recommend-with-override** (family-recommended) / **Locate·link·open-source-page** (unresolved-slot). License shown before fetch; progress + cancel. **Manual assist is a designed state from the first cut.** Feeds the existing video `missing_parts` payload hook (`ImageGenerationPage.cpp:4086-4098`); reconcile with `install_actions`/`missing_runtime_assets` (`worker_service.py ~6161-6220`).
   - **5b — auto-populate** (reads `best_present_match` + `tier`): see §5b below — pre-fills the cockpit component dropdowns from what's already on disk. This is the pass that **makes the shipped Wan 2.1 i2v path work by default** (retires the interim resolver fix).

## 5b. Auto-populate — the UI-facing consumer of the same producer
> **Motivating failure (live, af0396c):** the shipped Wan 2.1 i2v path is **broken by default** — the cockpit sources the stack VAE only from `videoVaeCombo_` with **no family auto-fill**, and single_model video **never flags a missing VAE** (`requiresComponents = kind=="split_stack"` → false), so the button stays **green** with an empty `vae_path` and the worker guesses `wan2.2_vae` → **48-vs-16 VAEDecode crash**. Auto-populate is **not a convenience layer** here — it is the fix that makes an already-shipped model work by default. *(Interim resolver-side fix shipped as `wan-vae-variant-match-interim`, 92d6f37.)*

Behavior: a **visible, tiered dropdown pre-fill**, **never a silent select** (silent hides what got chosen when it's wrong). Tiers map exactly:
- **known-canonical** → confident pre-fill.
- **family-recommended** → pre-fill tagged "for [family], override".
- **unresolved-slot** → open dropdown, slot labeled.

It reads `best_present_match` (the top-ranked on-disk candidate) from the same producer as 5a — one resolver, two consumers.

**Gate (per-pass):** manifest resolves each v1.0 family's missing set to a real source; a deliberately-incomplete Wan install shows the missing list and one-click Download fetches + places the right VAE/text-encoder so the button un-greys; **unknown-family shows template slots + manual assist (never a dead end, never a wrong auto-download)**; **known-family/unknown-variant shows recommend-with-override, not a silent wrong VAE**; the producer **never** surfaces Download below the confidence threshold; a **compatibility mismatch surfaces as a warning, not a download**; Locate-existing accepts an on-disk file with no download; a gated HF repo downloads only with a token and fails cleanly without one; credentials survive restart from the keychain (never QSettings/registry); t2v unaffected; `run_backend_checks.ps1` passes.

---

---

## 6. The Component Auto-Population System (consolidated design — the producer-side realization)

**Framing.** This is the producer-side realization of the §Principle: it turns *"user picks a model → the app knows and fills the complete compatible stack"* into an **invariant**. It consolidates the resolvers that were built reactively — `wan-vae-variant-match` (§3(c), 92d6f37) and the frozen `clip_vision` row (§2, af0396c) — into **one engine**, so the sophisticated-tool bar holds: **on model selection the complementing components auto-populate — without fail or error, for every family.** The one-off resolvers are not deleted; they become manifest rows and stay wired worker-side as a backstop.

### 6.1 Three-part architecture
1. **Per-family component manifest, as data** (Fork 1B, §4). Each family is *rows* declaring: **required components** (the contract slots, §3(a)), **valid-option predicates** (which on-disk files satisfy a slot), **preferred-match rules** (variant/precision ranking), and **optional/required flags**. **Adding a model is a manifest row, not a code branch** — the explicit anti-god-file constraint (the sibling of the `worker_service.py`/`ImageGenerationPage.cpp` god-file debt). Home: a **NEW standalone `model_dependency_manifest` data file** — NOT `ModelFamilySpec`, confirmed a lean frozen routing descriptor (10 routing-only fields, `model_registry.py:26-40`).
2. **Generic resolver engine** (Fork 2, §4). Manifest + on-disk probe → **completed stack + per-slot confidence tier**; family-agnostic. Composes `contract.required_components` (`video_family_contracts.py:47-127`) + `model_classification.classify_model` (family + confidence, §3(b)) + the manifest (slot → valid files/source) + an on-disk / `/object_info` diff. A **NEW module** — NOT `video_family_readiness.py` (LTX-hardcoded, §1). Emits the §4 producer shape (`best_present_match` + `candidate_source` + `tier` + `kind`), and reuses the fetch engine `model_dependency_resolver.build/apply_model_install_plan` (`:167`/`:211`) for the download hook.
3. **Producer-side auto-populate + worker-side backstop.** On model select, the cockpit stack UI is pre-filled from `best_present_match` (§5b). The reactive worker-side resolvers — `_wan_vae_version_marker`/`_wan_vae_preference` (in `_sv_core_wan_vae_name` + `_preferred_video_vae_name`) and `_sv_core_wan_clip_vision_name` — are **retained as a backstop** (belt + suspenders): a graph never submits with an empty/wrong slot even when the UI is bypassed (the socket/`enqueue` path has no cockpit).

### 6.2 Confidence tiers (the auto-fill contract)
Restates the §Definitions tiers as the **auto-fill outcome per slot**:
- **T1 — unambiguous** (single valid on-disk option, or a canonical family-default) → **silent auto-fill**.
- **T2 — preferred-match** (multiple valid, ranked — precision/variant: Flux T5 **fp16-vs-fp8**, Wan **2.1-vs-2.2** VAE) → **auto-fill the best, but visible + overridable within the valid set**.
- **T3 — missing** (no valid on-disk option) → **guidance + assisted-download hook** (the §5a per-tier download panel; gated repos need the §5-pass-3 HF token).

(T1 = known-canonical, T2 = family-recommended, T3 = unresolved-slot, from §Definitions.)

### 6.3 Override policy — constrain the menu, don't lock the field
Each slot's dropdown is **constrained to the valid set** (files the predicate accepts) → a wrong pick is **unrepresentable**. The field is **not locked**: an expert can still choose any *valid* option (a different valid VAE variant, a different T5 precision). **Wrong-by-construction, flexible-within-valid** — the sophisticated-tool bar without a straitjacket.

### 6.4 What it closes
- **Text-encoder mispick → structurally impossible.** The menu cannot offer CLIP-L / T5-XXL for a Wan slot whose predicate requires umt5. *(This is the exact live failure from the video-completion session: a Wan i2v submitted with `clip_l` / `t5xxl_fp16` died at `CLIPLoader` "invalid tokenizer" / `KSampler` 768-vs-4096 shape mismatch. The predicate makes it unpickable.)*
- **VAE variant mismatch** — the interim `wan-vae-variant-match` (92d6f37) promoted to producer-side **T2 preferred-match**; retired from the worker except as backstop.
- **clip_vision** — the FROZEN row (af0396c) becomes an in-engine manifest row (Wan 2.1 **requires**, 2.2 **omits** → the optional-flag predicate).
- **Every future family's component-matching** — a manifest row, resolved by the same engine.

### 6.5 Sequencing
- **Pass A — engine + shipped-family manifests + cockpit wiring.** Build the manifest data file + generic resolver + cockpit auto-populate; author rows for the **shipped, known-good families** (**Wan 2.1/2.2, SDXL**). **Gate on those families** (their stacks are proven end-to-end). This is where the interim Wan VAE / clip_vision resolvers fold into manifest rows.
- **Pass B — Flux (#3) as the first NEW consumer.** Flux's row exercises the **hardest case**: the T5 **fp16-vs-fp8 precision preferred-match** (T2) + transformer-only checkpoints needing T5 + CLIP-L + `ae` companions. Validates the engine on a genuinely-new family, not just the ones it was reverse-engineered from — Flux's manifest row *is* the engine's proof.
- **Ongoing — one manifest row per subsequent model**, each in its own pass: Hunyuan → Mochi → PixArt → Lumina → Z-Image → Anima. **"For all models" = the maintained invariant**, not a one-time build.

### 6.6 A1–A4 unified into this system
| Amendment | Was (scattered in Doc 19) | Now (in §6) |
|---|---|---|
| **A1** auto-populate (`best_present_match`; Pass 5 → 5a/5b split) | §4 producer shape (110-117) + §5 pass 5 (127-129) + §5b (131-139) | **Part 3** (producer-side auto-populate) reading **Part 2**'s `best_present_match` — the concrete producer architecture under §5b |
| **A2** variant-disambiguation as a **live failure** | §3(c) (93) + §5b motivating failure (132) | **Tier T2 preferred-match** (§6.2) — the Wan VAE-variant case is the canonical T2 example |
| **A3** gated-repo reachability | §5 pass 1 preamble (123) + §1 finding 1 (47) + pass 3 (125) | **Tier T3 missing → assisted-download** (§6.2), carrying the gated-repo/HF-token dependency (§5 pass 3) |
| **A4** classify → contract → slots **floor** | §5 pass 2 "Floor confirmation" (124) + §3(a)/(b) (91-92) | **Part 2's pipeline stages** — `classify → family → contract → required_components → on-disk diff`; the unresolved-slot floor is the engine's **guaranteed-non-empty** output for a never-seen checkpoint |

---

## Bottom line
The fetch engine is reusable (Civitai done, **HF-token is the one real gap**); the manifest is bounded authoring (Wan+Hunyuan sources verified; ~2/6 Wan filenames pre-extractable); readiness must be rebuilt family-agnostic; credentials are greenfield (QtKeychain); tiering rests on two existing signals (contract slots + classifier confidence) plus one new one (variant disambiguation). Both forks resolve to the **data-file manifest (B)** + **new family-agnostic producer**. **Land Wan i2v first** to freeze the clip_vision row before authoring. **The whole producer side is consolidated as the Component Auto-Population System (§6): manifest-as-data + generic engine + three tiers + constrained-override; Pass A (engine + Wan/SDXL manifests + cockpit) then Flux as the first new consumer; each later family adds one manifest row.**
