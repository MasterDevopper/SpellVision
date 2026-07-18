# Phase 7 — Simple/Advanced Progressive Disclosure — Decision Record (design only)

**Status:** DESIGN. No implementation. Build per this record (incrementally, one tab at a time, gated).
**Date:** 2026-06-30
**Inputs:** CLAUDE.md §2 (the *principle*: Simple = intent-level; hides "pixel math, schedulers, CFG,
node internals"; **Advanced reveals in place, never relocates**) + the mockup's one concrete spec
(Output: Simple = Orientation+Quality, Advanced = Width/Height+Batch). Phase 6 (commit d75e438)
shipped the global title-bar toggle + `MainWindow::advancedMode_` + `disclosureModeChanged(bool)`
+ `isAdvancedMode()`, **inert** — this phase wires the behavior.

> The mockup only *demos* Output gating and leaves Sampling/Model ungated — that's an **incomplete
> prototype**, not a spec. Per the brief, CLAUDE.md §2 is the guide; the mockup's Output split is the
> one fixed anchor.

---

## 1. CONTROL CLASSIFICATION

`S` = Simple (visible in **both** modes). `A` = Advanced (visible **only** in Advanced).
"row member?" = is the gateable widget already a member, or a **local var to promote** (Q5).

### Cockpit (always-visible surfaces — NOT gated)
| Control | Surface | Class | row member? | Rationale |
|---|---|---|---|---|
| IMG chip / input dropzone | prompt card | **S** | n/a (members) | The subject/input — core intent. |
| Prompt | prompt card | **S** | members | The intent itself. |
| Negative (collapsible toggle) | prompt card | **S** | members | Its own disclosure already; orthogonal to mode. |
| Video-family bar (Auto/Wan/LTX + readout) | cockpit (T2V/I2V) | **S** ⚑ | members | "Auto" is the Simple default. **FLAG** — see Decision D1. |

### Model tab
| Control | Class | row member? | Rationale |
|---|---|---|---|
| Checkpoint (browse/clear) | **S** | members | The core "what model" — essential in both. |
| Asset Intelligence panel | **S** | `settingsCard_` member | Informational/readiness ("details on demand"), not a knob. |
| Workflow combo | **A** ⚑ | `workflowCombo_` member; **row in a grid** | A node-graph *profile* (§2 "node internals"); the Preset drives it in Simple ([[preset-workflow-coupling]]). **FLAG D2.** |
| LoRA stack (add/clear/list) | **A** ⚑ | `loraStackContainer_` member | Power-user creative layering. **FLAG D3** (some consider LoRAs essential). |
| Video components (primary/text/VAE/vision) | **A** | members (`videoPrimaryModelCombo_`…) | Raw model-component overrides; "Auto …" covers Simple. |

### Sampling tab
| Control | Class | row member? | Rationale |
|---|---|---|---|
| Aspect (orientation) | **S** ⚑ | `aspectRow` **local** | Orientation = intent (mockup's Simple). **FLAG D4** — app places Aspect in *Sampling*; mockup puts Orientation in *Output*. |
| Sampler | **A** | `samplerRow` **local** | §2: scheduler-class raw knob. |
| Scheduler | **A** | `schedulerRow` **local** | §2 explicitly "schedulers". |
| Steps | **A** | `stepsRow` **local** | Raw knob; the Quality preset sets it in Simple. |
| CFG | **A** | `cfgRow` **local** | §2 explicitly "CFG". |
| Seed | **A** ⚑ | `seedRow` **local** | Default "random". **FLAG D5** (reproducibility users want it visible). |
| Frames | **S** ⚑ (video) | `framesRow` **local** | Duration = intent for video. **FLAG D6.** |
| FPS | **S** ⚑ (video) | `fpsRow` **local** | Cadence = intent for video. **FLAG D6.** |
| Video Sampler / Scheduler | **A** (video) | `videoSamplerRow`/`videoSchedulerRow` **local** | Same as image sampler/scheduler. |

### Output tab
| Control | Class | row member? | Rationale |
|---|---|---|---|
| Preset (Quality) | **S** | `presetCombo_` member | Mockup fixed point: Quality = Simple. |
| Width | **A** | `widthRow` **local** | Mockup fixed point + §2 pixel math. |
| Height | **A** | `heightRow` **local** | Mockup fixed point + §2 pixel math. |
| Batch | **A** | `batchRow` **local** | Mockup fixed point: Batch = Advanced. |
| Prefix | **A** | `prefixRow` **local** | Output-filename detail. |
| Output Folder (label) | **A** | `outputFolderLabel_` member (+title local) | Path detail; declutter in Simple. |

### Advanced tab — **A by definition** (the whole tab is power-user knobs)
| Control | Class | row member? | Rationale |
|---|---|---|---|
| Denoise / Strength | **S** ⚑ (i2i) | `denoiseRow_` member | **FLAG D7** — strength is *intent* for i2i but lives in the Advanced tab. The one classification that breaks "Advanced tab = all advanced". |
| Wan Split, High/Low Steps, Split Step, High/Low Shift | **A** | members (`wanSplitRow_`…) | Video dual-noise internals. |
| VAE Tiling | **A** | `enableVaeTilingRow_` member | Memory internal. |
| LTX Launch Options panel | **A** | `ltxLaunchOptionsPanel_` member | Raw native-template launch config. |

**Net:** in Simple, the **Advanced inspector tab** is essentially empty (only Denoise, and only for
i2i) → **hide the Advanced tab in Simple** (Decision D7 resolves Denoise).

---

## 2. "REVEALS IN PLACE" FEASIBILITY → **pure hide-in-place is sufficient**

Every Advanced control is **already in its final layout position**, and the rows are already
conditionally `setVisible()`-d by mode/family logic (e.g. `framesRow->setVisible(isVideoMode())`,
`denoiseRow_->setVisible(usesStrengthControl())`). Adding a disclosure gate is therefore a per-row
`setVisible(advanced && …)` — **no control relocates between modes**. §2's "reveals in place" holds
by construction.

**Two OPTIONAL alignments that WOULD relocate (defer — not required for the behavior):**
- **D4 — Aspect tab placement:** app has Aspect in *Sampling*; the mockup shows Orientation in
  *Output*. Matching the mockup means moving `aspectRow` Sampling→Output (a relocation). **Recommend:
  don't** — gate Aspect as Simple *in place* (Sampling). Tab-alignment is a separate cosmetic pass.
- **D7 — Denoise for i2i:** if we want i2i-Simple to keep strength, either (a) relocate `denoiseRow_`
  out of the Advanced tab into a Simple-visible spot, or (b) keep the Advanced tab conditionally
  visible when it has Simple content. Both touch layout. See D7.

So: **hide-in-place covers 100% of the mode behavior.** The only relocations are optional polish.

---

## 3. VALUE PERSISTENCE ON MODE-SWITCH → **HIDE (recommended)**

When Simple hides a control, its **value is retained**; the request builder reads it **by member,
not by visibility** (already true — `draft.width = widthSpin_->value()` etc., never visibility-gated).
Flipping back to Advanced shows the retained value. A user's Advanced tweaks survive a Simple detour.

- **Why HIDE, not DEFAULT:** this is the exact [[mockup-fidelity-rule]] / negative-prompt /
  fp16-LoRA lesson — **hiding is a view concern, never a data concern.** "Simple" means *fewer knobs
  visible*, **same generation** — not "simpler results." DEFAULT (force hidden controls to defaults
  for generation) is a different, surprising product (a Simple user who set W/H=1344 in Advanced
  would silently get 1024). Reject DEFAULT.
- **Consequence to gate at build:** generation in Simple uses whatever the controls currently hold
  (their last Advanced values, or construction defaults if never touched). That's correct and
  predictable. No builder change needed — only visibility changes.

---

## 4. PER-SURFACE vs GLOBAL → **GLOBAL for Phase 7** (per-surface stays possible)

Phase 7 keeps the single global title-bar toggle (Phase 6's `advancedMode_` + signal). CLAUDE.md §2's
"per-surface checkbox + Settings default" is **not precluded**: Phase 6 left the state global +
signal-based, so a later per-surface override is additive — each page (or surface) gains an optional
local override that **defaults to "follow global"**, consulting `isAdvancedMode()` only when not
overridden. Don't bake assumptions that fight that (e.g. don't make pages *own* the mode — they
*consume* it).

- **Recommend:** global now; document the per-surface extension point (a future `page-local override,
  default follow-global`). Simpler, ships the §2 intent (one master), defers the nuance.

---

## 5. CONSUMPTION ARCHITECTURE

**Signal path:** `MainWindow::disclosureModeChanged(bool)` → each page. Wire in
`MainWindow::connectGenerationPage(page, modeId)` (where other page signals are connected):
`connect(this, &MainWindow::disclosureModeChanged, page, &ImageGenerationPage::updateDisclosure)`,
**and** push the initial state right after connecting (`page->updateDisclosure(isAdvancedMode())`) so
a page built/visited later starts in the right mode.

**Per page:** one `void ImageGenerationPage::updateDisclosure(bool advanced)` that `setVisible()`-s
the **A**-classified rows (and `cockpitInspector_->setTabVisible(Advanced, advanced)`), respecting the
existing mode/family guards (Simple hide must AND with them, never *show* a row the mode already
hides — e.g. `framesRow->setVisible(isVideoMode())` must stay false in image modes regardless of
disclosure). Store `bool advanced_` on the page; re-apply on any rebuild that recreates rows.

**Member-promotion map (currently local → promote to members for gating):**
- **Sampling:** `samplerRow`, `schedulerRow`, `videoSamplerRow`, `videoSchedulerRow`, `stepsRow`,
  `cfgRow`, `seedRow`, (`framesRow`, `fpsRow`, `aspectRow` only if we gate/relocate them).
- **Output:** `widthRow`, `heightRow`, `batchRow`, `prefixRow` (+ `outputFolderTitle` local).
- **Already members (no promotion):** all Advanced-tab rows (`denoiseRow_`, `wanSplitRow_`,
  `highNoiseStepsRow_`, `lowNoiseStepsRow_`, `splitStepRow_`, `highNoiseShiftRow_`,
  `lowNoiseShiftRow_`, `enableVaeTilingRow_`, `ltxLaunchOptionsPanel_`), `presetCombo_`,
  `workflowCombo_`, `loraStackContainer_`, `settingsCard_`, the video-component combos,
  `outputFolderLabel_`.

**Two ripples to budget at build:**
- **CockpitInspector tab visibility:** there is no `setTabVisible(Tab, bool)` yet — add one (hide the
  *Advanced* tab in Simple; hide its tab-bar button + skip it in selection). Small addition to
  `CockpitInspector`.
- **Model-tab controls are in a GRID** (`stackForm`), not free QWidget rows — gating Workflow/LoRA
  there needs per-row wrapper handles (label+field), which is fiddlier than the Sampling/Output rows.
  Assess when D2/D3 are decided; may defer Model-tab gating to a later sub-step.

---

## OPEN DECISIONS (resolve before/within the build — flagged borderlines)

| # | Decision | Recommendation |
|---|---|---|
| **D1** | Video-family bar in Simple — visible (Auto default) or hide manual Wan/LTX? | **Visible in both** (Auto covers Simple; forcing Auto removes a legit choice). |
| **D2** | Workflow combo — Advanced or Simple? | **Advanced** (node-graph profile; Preset drives it). |
| **D3** | LoRA stack — Advanced or Simple? | **Advanced** (power-user); revisit if user deems LoRAs essential. |
| **D4** | Aspect tab placement (Sampling vs mockup's Output) | Gate **Simple in place** (Sampling); don't relocate now. |
| **D5** | Seed — Advanced or Simple? | **Advanced** (random default); reproducibility is a power feature. |
| **D6** | Frames/FPS (video) — Simple or Advanced? | **Simple** (duration/cadence = video intent). |
| **D7** | Denoise/Strength (i2i) — it's intent but lives in the Advanced tab | **Classify Simple for i2i**; resolve placement by **(a) relocating `denoiseRow_` to a Simple spot** *or* **(b) conditional Advanced-tab visibility**. Lean (a). This is the one real layout touch. |
| **D8** | Does the **Advanced inspector tab** show in Simple? | **Hide it in Simple** (all-Advanced content), contingent on D7. |

These (esp. D7) are the items needing your call before building — none block the *architecture*,
only the per-control table.

---

## BUILD PLAN (when scheduled — incremental, gated, NOT big-bang)
1. **Plumbing:** `updateDisclosure(bool)` skeleton + connect in `connectGenerationPage` + push initial
   state. No controls gated yet → verify the signal arrives (log/no-op). Gate: toggle flips, page
   receives it.
2. **Output tab** (the mockup's fixed point): promote `widthRow`/`heightRow`/`batchRow`/`prefixRow`;
   gate them A; Preset stays S. Gate: Advanced shows W/H/Batch, Simple hides; values persist across a
   flip (the HIDE proof — set W/H in Advanced → Simple → Advanced → value retained → generate uses it).
3. **Sampling tab:** promote + gate Sampler/Scheduler/Steps/CFG/Seed (A); Aspect S; Frames/FPS S.
4. **Advanced tab + Model tab:** resolve D7 (Denoise), add `CockpitInspector::setTabVisible`, hide the
   Advanced tab in Simple; gate Workflow/LoRA/components (needs the grid row-handles).
Each step its own commit + gate; per-step "value persists across mode flip" is the recurring check.

**Cross-refs:** the HIDE persistence decision is the [[mockup-fidelity-rule]] negative-prompt pattern
at scale; the global-state plumbing is Phase 6 (d75e438); [[studio-layout-migration]] Phase 7.
