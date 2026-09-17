# W5 Models Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Models page becomes a library rather than a file list — each model shown with the name, pictures and description its host site publishes, sorted into tabs by what it actually is, with the user able to replace any picture with their own.

**Architecture:** W1 already fetches and stores all of this in `<stem>.spellvision.json` beside each weight, and already exposes it over four worker commands. W5 is almost entirely a consuming wave: tabs from the classifier's own vocabulary, cards and an inspector reading the sidecar, and the one action that is genuinely missing — a way to ask for a refresh from inside the app.

**Tech Stack:** C++17/Qt6, Python 3.12 stdlib, existing worker TCP protocol, QTest.

**Spec:** `docs/superpowers/specs/2026-09-15-t2-t6-completion-design.md` §5. **Code inventory with file:line: `docs/superpowers/specs/2026-09-15-t2-t6-research/t3-t5-context.md`. API and sidecar detail: `t3-t5-metadata-research.md` and `live-api-validation-2026-09-16.md`.** Owner requirement: Doc 54 §1 T3 and its "Owner T7 holes" note (drag-and-drop downloading; display name from metadata replacing the filename **on the page only**, never renaming the file).

## Global Constraints

- C++17, Qt 6.10.2; Python 3.12 **stdlib only**. Modules under 300 lines.
- **`Stop-Process -Name SpellVision` before every build** (`LNK1168`). `ctest` needs `-C Debug`.
- **Compare against the gate as you find it** — record the count before you start. `shell_layout` and `test_godfile_split` are pre-existing failures; ~20 Python failures also fail on a clean tree.
- **Do not add lines to `qt_ui/ImageGenerationPage.cpp`** — it already fails its 3000-line ceiling. `ModelManagerPage.cpp` is large too; new behaviour goes in new units.
- Theme tokens for colour, spacing tokens for spacing. For a caption prefer `ElidingLabel`; a second unnamed `ErrorPillLabel` steals an existing test's `findChild`.
- **No `Co-Authored-By` trailer.**
- **Never write an API key anywhere.** The owner's CivitAI and HuggingFace keys live in the DPAPI credential store; nothing may log, echo or persist them.
- **A measurement run may be executing on this machine.** Before any build, check for `MSBuild.exe`/`cl.exe`/`link.exe` **and** a running `measure_optimizations.py`. A build during a measurement contaminates it — that happened once already and cost a full 50-minute run.

## What already exists

W1 shipped `python/model_intelligence/` and four commands: `model_intel_get`, `model_intel_refresh`, `model_intel_set_user`, `model_recommended_settings` (plus `model_intel_cancel` and `model_roots_status`). A live run identified **34 of 35** weights on the F: root in 466 s and fetched **123 preview images**. Each sidecar carries identity (hashes, kind, family, quantisation, sources), display (name, description, creator, licence, trigger words, images) and a `recommended` block with per-field provenance.

The Models page reads **none** of it. It scans the filesystem itself, guesses type and family from path substrings, and shows the filename.

---

## Task 1: Tabs from the classifier, not from a substring

**Files:** `qt_ui/ModelManagerPage.{h,cpp}`, new `qt_ui/assets/ModelKindTabs.{h,cpp}`, `tests/cpp/test_model_kind_tabs.cpp`, `CMakeLists.txt`
**Read first:** `t3-t5-context.md` §"ModelManagerPage"

Today `detectType` (`ModelManagerPage.cpp:259-273`) yields six kinds from path substrings, collapsing `clip_vision` and `text_encoders` into one "Encoder" and giving embeddings no type at all. The worker's classifier already answers this properly and `classify_models` now returns a `kind` from the ten-value vocabulary (W1 Task 11).

**Tabs:** All · Checkpoints · Diffusion models · LoRAs · VAE · Text encoders · Vision · Embeddings · Upscalers · ControlNet · Other, with counts in the labels. The Type combo is deleted — the tab *is* the type. Family stays a combo; search stays.

**The rule that matters:** a model whose kind the classifier could not determine goes to **Other**, and Other is visible. A wrong tab is worse than an honest one, and a model that silently vanishes from every tab is worst.

- [ ] Steps: failing C++ test (a fixture inventory covering all ten kinds gives the right counts; switching tabs filters; an unclassifiable model appears under Other; every model appears in exactly one tab and in All) → implement → build → ctest → **prove the Other case bites** by planting a filter that drops unknown kinds → commit.

---

## Task 2: The card shows what the site says

**Files:** `qt_ui/assets/ModelCardModel.{h,cpp}`, `qt_ui/ModelManagerPage.cpp`, `qt_ui/assets/ModelThumbnailCache.*`, `tests/cpp/test_model_card_sidecar.cpp`
**Read first:** `t3-t5-context.md` §"Pictures", and a real sidecar on disk under `F:/AI_ASSETS/models/`

- Display name from `display.name`, **on the page only** — the file is never renamed (owner requirement).
- Cover from the sidecar's cover image through the existing `ModelThumbnailCache`, which is already keyed by sha256-or-path and already handles video posters.
- A site badge (CivitAI / HuggingFace / local) from `identity.sources`.
- Quantisation (`identity.quantisation`: nvfp4 / int8 / fp8 / bf16) as a chip, because on this library four Lox variants differ only by it.
- **NSFW blur** when the preview's level exceeds the setting.

**Honesty rule:** a model with no sidecar shows its filename and reads as un-identified — not as identified-with-no-data. The two must look different, or the user cannot tell "we asked and found nothing" from "we never asked".

- [ ] Steps: failing test over real sidecars from the F: library → implement → prove the un-identified case renders differently by planting a fallback that shows a blank name → commit.

---

## Task 3: The inspector, and the user's own picture

**Files:** new `qt_ui/assets/ModelInspectorPanel.{h,cpp}`, `qt_ui/ModelManagerPage.cpp`, `tests/cpp/test_model_inspector.cpp`
**Read first:** `t3-t5-context.md` §"ModelManagerPage" (the `updateDetailsForRow` paragraph)

Gallery strip (up to 6 from `display.images`) · description (HTML-stripped, expandable) · trigger words with copy · licence line · **Recommended settings** with provenance captions and an Apply-to-mode button · **Use my picture…** · **Refresh metadata** · **Open on site**.

**"Use my picture…"** calls `model_intel_set_user` with a `picture` path. W1's containment check means the request must carry the model roots — a path outside them is refused, by design. Surface that refusal rather than failing silently.

**And the picture must survive a later refresh.** W1's sidecar marks it `user_override`; assert that end-to-end here, because it is the promise most likely to be quietly broken by a future change.

- [ ] Steps: failing tests (gallery renders N images; a user picture replaces the cover **and survives a refresh**; provenance captions name their source; a model with no `recommended` block shows the family fallback honestly) → implement → prove the survives-a-refresh case bites → commit.

---

## Task 4: Refresh metadata, from inside the app

**Files:** `qt_ui/ModelManagerPage.cpp`, `qt_ui/MainWindow.cpp`, `tests/cpp/test_model_refresh_action.cpp`
**Read first:** W2's ledger note on this — `.superpowers/sdd/2026-09-16-w2-model-defaults/progress.md`, ruling W2-F1

**This is the genuinely missing piece.** W2's cockpit caption told the user to "run Refresh metadata on the Models page" and had to have that sentence removed, because **there is no such control and nothing in `qt_ui/` starts a `model_intel_refresh` at all.** The cache invalidation it needs was wired then; the button was left to this wave.

Requirements:
- A **Refresh metadata** action, per-model and for the whole library.
- It is a **long job** — the full library is ~79 minutes — so use `background: true` and show progress from the `model_intel_progress` events, with a cancel that calls `model_intel_cancel`.
- **The keys**: reads work anonymously (verified — the anonymous and keyed CivitAI replies were identical), so the button must not demand a key. If a key is needed later (a download, mature previews), ask then, with a link to the page that creates it.
- When it finishes, invalidate the per-model defaults cache W2 wired, and **restore the cockpit caption's instruction** now that it is true.

- [ ] Steps: failing test (the action sends `background: true`; progress events update; cancel sends `model_intel_cancel`; no key is required to start) → implement → **restore the W2 caption sentence** → prove the no-key case bites → commit.

---

## Task 5: Download lands in the library

**Files:** `qt_ui/ModelManagerPage.cpp`, `python/download_commands.py`, `tests/test_models_download_lands.py`
**Read first:** `t3-t5-context.md` §"Download path"; W1 Task 10 built `placement.py` and the post-download hook

W1 made a downloaded weight move into the models library and refresh. W5 makes the **Models page's own download button** use that path — today it calls `start_download`, which historically left the file in the asset cache. Verify the wiring end to end and show the new model appearing in its tab with its picture.

Also: **drag-and-drop downloading** (owner requirement) — dropping a CivitAI or HuggingFace URL on the page downloads it. `handleDroppedReference` already accepts a URL; make it end in the library with a sidecar.

- [ ] Steps: failing test → wire → live check with one small real model → commit.

---

## Task 6: The live proof

**Files:** `docs/design/55_t7_ship_walkthrough.html`, captures

- [ ] Capture the Models page with tabs and counts over the real library; a CivitAI-identified checkpoint with its site pictures and trigger words; a user-replaced picture surviving a refresh; the Recommended-settings panel with provenance; a refresh running with progress and being cancelled.
- [ ] **Do not paint T3 green.** Say what is proven and what is not — this is Stage-2-shaped, not LoRA Manager parity, and the owner's bar should be quoted rather than paraphrased.

---

## Self-Review

**Spec §5 coverage:** tabs from the kind vocabulary (1) · cards from the sidecar with site pictures (2) · inspector, gallery, trigger words, licence, recommended settings, user picture (3) · refresh from inside the app (4) · download lands in the library + URL drop (5) · live proof (6).

**Carried in from earlier waves and scheduled here, not forgotten:**
- `clip_skip` and `guidance` are resolved by the worker and **discarded** because no widget exists (W2 ruling W2-E2). Add them to Advanced, or state in the walkthrough that they are resolved and unused — but stop leaving them silently dropped.
- A **preset and a model's own defaults can both write steps and CFG**, so which the user sees depends on the order they touched them (W2, open). Decide it here: a preset is a deliberate user choice and should win until the model changes.
- `kLeverProbes` in the Runtime panel is a second list of lever ids (W3). A sweep rule closing that drift belongs with whichever wave next touches it.

**Not in this wave:** CivitAI/HF browsing inside the app, recipes, and pause/resume downloads — all Doc 58's 1.2.0 line.
