# Model Library Arc — Local library → Remote browse → Download manager (design only)

**Status:** DESIGN. No implementation. Build per §7 (incrementally, gated, one stage at a time).
**Date:** 2026-07-12
**Inputs:** the restored `ModelManagerPage` (Stage-1 inventory browser, commit `c12e5f8`, polished to the
token system `949efa8`) + a live filesystem recon of `D:/AI_ASSETS/models` (710 model files) + the live
cockpit API surface (`ImageGenerationPage.h`). All coverage/fill-rate numbers below are measured, not
estimated.

> **Why this doc exists.** The card + sidecar + metadata format defined in §2 is *the contract the
> download manager (§5, Pass 3) must produce.* If the downloader writes sidecars before the consumer's
> contract is written down, it will guess the schema wrong and the local library won't pick its files up
> for free. This is "ground before you build" at the feature level: freeze the format here, then both the
> consumer (local library) and the producer (downloader) build against the same frozen thing.

---

## 0. Three corrections — bank these (they get re-discovered painfully otherwise)

> 1. **Trigger words are NOT in `usage_tips`.** That field is the literal string `"{}"` in **100%** of
>    sampled sidecars. Trigger words live in **`civitai.trainedWords`** (nested array). Read from there.
> 2. **`favorite` / `exclude` are SpellVision-owned, not scraped.** `favorite` is `false` in **100%** of
>    sidecars — the scraper never sets it. Favoriting/hiding/user-tags are an **app-owned overlay** stored
>    in SpellVision's own cache (§2.4). **Never write them back to the sidecar** (the downloader would
>    clobber them, and it's not our file to own).
> 3. **No VAE slot exists in the cockpit.** `ImageGenerationPage` has zero `vae` in its surface; VAE is
>    auto-resolved by the video component-resolver only. So "VAE → set VAE slot" (§3.3) has **nowhere to
>    land today** and is deferred until a manual VAE slot ships.

---

## 1. The arc

A four-stage feature line. Each stage stands on the one before; the **local contract (§2) is the spine.**

1. **Local library** — launcher-first, browser-capable. The page you look at, filter, and launch models
   from. *This is what exists today (Stage-1) + S0–S5 below.*
2. **Remote browse** — Civitai + HF search inside the same card UI (§5, Pass 2).
3. **Download manager** — pull a remote model **and write the §2 sidecar format**, so the local library
   picks it up for free on next scan (§5, Pass 3). **This is the stage the whole doc is aimed at.**
4. **Browser extension** (later, arc tail) — capture a model page in the browser, hand the URL/id to the
   download manager. Out of scope here; noted so the arc is legible.

**Grounding — what the local library is today:** `ModelManagerPage`, a Stage-1 inventory browser.
`resolveModelsRoot()` → `D:/AI_ASSETS/models`; async `QFutureWatcher` scan (non-blocking); path-heuristic
`detectFamily()` / `detectType()`; disk cache at
`%LOCALAPPDATA%/Dark Duck Studio/SpellVision/model_inventory_cache.json`. No thumbnails, no metadata panel,
no send-to. This doc is the plan from here.

**Measured reality (710 model files under the models root):**

| Signal | Files | Coverage |
|---|---|---|
| Any sidecar | 404 | **57%** |
| Image preview (`.png`/`.jpg`/`.jpeg`/`.webp`) | 297 | 42% |
| Video preview (`.mp4`) | 88 | **12%** |
| `.metadata.json` | 399 | 56% |
| **No sidecar at all** | ~306 | **43%** |

Two design consequences: **the fallback (§2.2) is first-class, not an edge case** (43% of the library),
and **video hover-play (§4) is a minority delight** (12%) — real for Wan/video models, absent for most.

Of the 406 metadata sidecars, the *rich* fields are well-populated — so the metadata panel (§S3) is worth
building:

| Field | Non-empty | Note |
|---|---|---|
| `base_model` | 95% | "Unknown" counted as empty |
| `tags` | 94% | |
| `modelDescription` | 94% | may be markdown/HTML |
| `civitai.trainedWords` (trigger words) | — | correction #1; `usage_tips` is **0%** |
| `from_civitai` | 97% | the sidecars are the "civitai model manager" scraper format |

---

## 2. The data layer (S0) — shared foundation

One data layer feeds both views (§4) and both the local and remote passes. Build it once.

### 2.1 Sidecar resolver contract

Given a model file `<dir>/<base>.<ext>` where `ext ∈ {safetensors, ckpt, pt, pth, gguf, bin, onnx}`,
resolve siblings **by shared basename** `<dir>/<base>.<x>`:

| Asset | Lookup order (first found wins) | Coverage |
|---|---|---|
| Image preview | `.png` → `.jpg` → `.jpeg` → `.webp` | 42% |
| Video preview | `.mp4` | 12% |
| Metadata | `.metadata.json` → `.json` → `.civitai.info` | 56% |

- A model may have **both** an image and a video preview (Wan models do — the image is the poster, the mp4
  is the motion sample). Resolve both; the view decides which to show (poster in list, hover-play in grid).
- The resolver is pure and cheap (stat-only); it does **not** read file contents. It returns a
  `SidecarSet { QString imagePath; QString videoPath; QString metadataPath; }` with empty strings for
  misses. Absence is normal (43%), not an error.

### 2.2 Fallback for the 43% with nothing — specify it, don't leave it implicit

A **type-colored placeholder tile**, deterministic per type so the eye learns it:

- Rounded tile (same radius as a real thumbnail) filled with a **low-alpha accent-family tint** keyed by
  `detectType()`: `Checkpoint` / `LoRA` / `VAE` / `Upscaler` / `Encoder` / `ControlNet` / `Model`. Use
  `ThemeManager` tokens (no raw colors), one stable hue per type.
- A centered **type glyph or 1–2-letter monogram** (e.g. "LoRA" → "Lo") in `TextHi`.
- The **family** label small underneath (e.g. `sdxl`, `wan`, `upscale`).
- Same tile shape/size as a real thumbnail so grid/list layout never shifts between have-preview and
  not-have-preview rows.

### 2.3 Metadata model — the fields SpellVision reads (and the download manager must write)

Parsed from the metadata sidecar. This is the **frozen schema** the downloader (§5) targets.

| Field (JSON key) | Read as | Use |
|---|---|---|
| `base_model` | string ("Unknown" ok) | metadata panel, filter ("show SDXL only") |
| `tags` | string[] | metadata panel, filter/search |
| `modelDescription` | string (md/html) | metadata panel body |
| **`civitai.trainedWords`** | string[] | **trigger words** (correction #1) — panel + copy-to-clipboard |
| `model_type` | string | cross-check with path `detectType()` (path wins on conflict; log) |
| `sha256` | string | identity, thumbnail-cache key, download checksum verify |
| `size`, `model_name`, `file_name` | — | identity/display |
| `preview_url` | string | *remote* fallback if no **local** preview exists (§4 may fetch lazily) |

- Parsing must **degrade gracefully**: a model with no metadata sidecar (44% of models, ~46% of the
  library) shows the panel as "No metadata — local file only," never an error.
- `model_type` from the sidecar and `detectType()` from the path can disagree; **path-based detection is
  the authority** (it drives routing, §3) — the sidecar value is advisory. Log mismatches for later.

### 2.4 SpellVision-owned overlay (correction #2 — never in the sidecar)

Stored in SpellVision's own cache (extend `model_inventory_cache.json` with a per-model overlay keyed by
`sha256` or abspath, or a sibling `model_overlay.json`). **Never written to the sidecar** — it's the
downloader's file, and it would clobber user state.

- `favorite` (bool), `hidden`/`exclude` (bool), `userTags` (string[]), `lastUsedMode` (string),
  `useCount` (int). Keyed so it survives a re-scan and a model moving directories (prefer `sha256`).

### 2.5 Thumbnail cache

Civitai preview PNGs are large (often 400–1024px); a grid of hundreds cannot decode originals per paint.

- **Location:** `%LOCALAPPDATA%/Dark Duck Studio/SpellVision/model_thumbnails/` (sibling of the inventory
  cache, `QStandardPaths::AppLocalDataLocation`).
- **Key:** `<sha256 or hash(abspath)>_<w>x<h>.png`. Prefer `sha256` from metadata; fall back to a hash of
  abspath. Store the **source preview's mtime** (in a small index or the filename) for invalidation.
- **Invalidation:** regenerate when the model file's mtime **or** the source preview's mtime changes.
- **Sizes:** cache a single **~256px master**, scale in-widget to list-thumb (~44px) and grid-tile
  (~200px) with a smooth transform; or cache both explicit sizes. (One master is simpler; decide at S0.)
- **First scan of 710 must NOT block the UI.** The inventory scan is already async (`QFutureWatcher`).
  Thumbnails are generated **lazily, viewport-driven** — only for rows/cards actually visible, off-thread,
  placeholder (§2.2) shown until ready. **Never pre-generate all 710.** Feeding an `QAbstractItemView`
  delegate that requests a thumb → enqueue if missing → repaint the one row when it lands.

---

## 3. Send-to-generation router — type dispatch, grounded in the real methods

Send-to is **not one action** — it dispatches on asset type. The receiving primitives **already exist**
on `ImageGenerationPage` (today they are `private`; see the seam, §3.4):

- `setSelectedModel(value, display)` / `trySetSelectedModelByCandidate(candidates)`
- `addLoraToStack(value, display, weight, enabled)` / `tryAddLoraByCandidate(candidates, weight, enabled)`

So send-to is **wiring, not building.**

### 3.1 Checkpoint → derive mode from family → route → set model

`checkpoint`/`Model` type: `mode = familyToMode(family)` → `switchToMode(mode)` → set the model slot on
that page. Landing in the *right* cockpit with the stack pre-filled is the "feels smart" moment.

**`familyToMode(family)`** — the page already `detectFamily()`s, so this is a pure lookup:

| Family | Mode | Media |
|---|---|---|
| `wan` | **t2v** | video |
| `ltx` | t2v | video |
| `hunyuan_video` | t2v | video |
| `cogvideox` | t2v | video |
| `mochi` | t2v | video |
| *everything else* (`sdxl`, `flux`, `pixart`, `lumina`, `z_image`, `anima`, `illustrious`, `pony`, `upscale`, `unknown`, …) | **t2i** | image |

- **Honest ambiguity:** a Wan checkpoint is valid for **t2v and i2v**. **Default t2v** (text-first); the
  user switches to i2v once there (the model is already selected, and i2v shares the family). Do not try to
  guess i2v.
- Keep the set `{wan, ltx, hunyuan_video, cogvideox, mochi}` in **one place** (a `familyToMode()` free
  function) so it tracks the video-family list the rest of the app already knows.

### 3.2 LoRA → add to stack, never replace the model

`LoRA` type: `addLoraToStack(...)` on the **target image cockpit** — never touches the model slot.

- **Which cockpit?** From the Models page there is no "current" cockpit in view. **Decision (recorded):**
  default target **T2I**, but expose it as a **split action** — `Add to T2I ▾` with `I2I` in the dropdown
  — so I2I users aren't forced through T2I. Route to the chosen mode, then `addLoraToStack`.
  (If a generation page is *already* the last-used surface, `lastUsedMode` from the overlay §2.4 may seed
  the default — but the split action is the explicit control.)
- Weight defaults to `1.0`, enabled `true` (the `addLoraToStack` defaults).

### 3.3 VAE → deferred (correction #3)

`VAE` type has **no target** — there is no manual VAE slot in the image cockpit. For v1: the send action is
**absent/greyed for VAEs** with a tooltip ("VAE routing lands with a manual VAE slot"). Revisit when a VAE
slot ships (or wire it into the video component-resolver override, which is a larger surface).

### 3.4 The seam

- `ModelManagerPage` emits **`useModelRequested(QString value, QString family, QString type)`** — `value`
  is the catalog value the cockpit expects (model name / models-root-relative path), `family` =
  `detectFamily()`, `type` = `detectType()`.
- `MainWindow` owns the router **`sendModelToGeneration(value, family, type)`**: switch on `type` →
  LoRA (§3.2) / VAE (§3.3, no-op+toast) / else checkpoint (§3.1). It ensures the target page is built
  (lazy pages, see [[lazy-page-construction]]), `switchToMode(...)`, then calls the handoff.
- **Open 5-min question — the handoff entry point.** The `try*ByCandidate` primitives are exactly right
  (they resolve a name against the loaded catalog) but are `private`. Two options, decide at build:
  - **(a) Add a thin public `applyModelHandoff(value, display, role)`** on `ImageGenerationPage` that wraps
    `trySetSelectedModelByCandidate` / `tryAddLoraByCandidate`. *Recommended* — explicit, and candidate
    resolution is precisely a name→combo-entry handoff.
  - **(b) Reuse the existing public `applyWorkflowDraft(QJsonObject)`** with a minimal `{model, loras}`
    draft. Confirm what `applyWorkflowDraft` currently does before choosing (it may not route or may carry
    extra semantics).

---

## 4. The two views — same data layer, one toggle

- **Dense list (launcher — default).** The current tree + a **thumbnail column** (small delegate, §2.5
  fallback for the 43%), the existing **fast filter**, and a **send action per row** (button + double-click
  + Enter). In and out in five seconds. This is the daily driver.
- **Card grid (browser).** A view toggle: larger tiles (thumbnail hero + name + type/family chips +
  favorite star), a **metadata panel** on select (§S3), and **mp4 hover-to-play for the 12%** with an mp4
  preview. *Reuse the hard-won video lesson:* render frames via `QVideoSink → QImage → QLabel`, **not** a
  native `QVideoWidget` surface (it fails silently) — see [[video-playback-render-and-gate-lesson]].
- Same `SidecarSet` + metadata + thumbnail cache underneath. The toggle persists in `QSettings`.

---

## 5. Remote passes (sketch — not full spec)

### Pass 2 — Remote browse (Civitai + HF)

- **API keys:** Civitai API key + HF token, stored in **QtKeychain** (credentials are greenfield; the
  HF-token gap is already noted in [[guided-dependency-resolution-epic]]). A Settings surface to enter them;
  browse is gated on the relevant key present.
- **Same card component** renders remote results; the per-card action flips from **Send-to** (§3) to
  **Download** (Pass 3).
- **APIs:** Civitai public REST (`/models`, `/model-versions`; search/filter by type, base-model, sort).
  HF Hub API (model search, `siblings` for files, model card). Both documented and public.

### Pass 3 — Download manager (THE reason for §2)

- **The contract:** on download, write, next to the model file:
  `<base>.<ext>` + **`<base>.metadata.json` in the §2.3 schema** + `<base>.png` (preview) +
  `<base>.mp4` (if the version ships a video sample). Then the **local library picks it up for free** on
  next scan — zero special-casing, no separate "downloaded models" path.
- Resumable transfer, **sha256 verify** against the API value (§2.3), placement into the right subdir by
  type (`loras/`, `checkpoints/`, `vae/`, `upscale_models/`, …) so `detectType()`/`detectFamily()` classify
  it correctly on scan.

### License rule (prominent)

> Build against the **public, documented APIs directly.** Do **not** vendor, copy, or derive from
> GPL-licensed client source (existing Civitai downloaders/managers). The sidecar **format** we observed is
> a de-facto schema we **re-implement from our own field list (§2.3)** — a format is not code. Keep a clean
> provenance line: our fields, our parser, our writer.

---

## 6. (later) Browser extension

Arc tail, out of scope: a browser extension that captures a model page and hands the URL/id to the Pass-3
download manager. Listed only so the arc reads end-to-end.

---

## 7. Build order

| Stage | Scope | Notes |
|---|---|---|
| **S0** | Data layer: sidecar resolver (§2.1) + metadata model (§2.3) + overlay store (§2.4) + thumbnail cache (§2.5) + fallback tile (§2.2) | The shared foundation. Everything else consumes it. |
| **S1** | Thumbnails in the **list** (delegate + lazy viewport-driven cache + fallback) | Recognition, not browsing. |
| **S2** | **Send-to router** (§3): checkpoint + LoRA; VAE deferred | Wiring over existing primitives. |
| — | **← S1 + S2 is the daily-driver payoff. If you stop the arc anywhere, stop here.** | The launcher you'll actually use every day. |
| **S3** | **Metadata panel** (base_model / tags / description; trigger words from `civitai.trainedWords`; copy-triggers button) | Worth it — 94–95% fill on sidecar'd models. |
| **S4** | **Grid view** toggle + mp4 hover-play for the 12% | The browser half. |
| **S5** | **Favorites / user-tags overlay** (§2.4) | SpellVision-owned; enables favorite/hide/filter. |
| Pass 2/3 | Remote browse + download manager | Start **only after §2 is frozen** — that's the point of this doc. |

**Sequencing rule:** the metadata contract (§2.3) must be **frozen before Pass 3** — the downloader is the
producer, the local library is the consumer, and they must agree on the format written to disk. That
freeze is what this document is.

---

## 8. Open decisions to close at build time

1. **Handoff entry point** — public `applyModelHandoff()` (recommended) vs. reuse `applyWorkflowDraft()`
   (§3.4). Confirm `applyWorkflowDraft`'s current behavior first.
2. **LoRA target** — default T2I with a split `Add to T2I ▾ / I2I` action (§3.2); confirm the split-button
   affordance fits the row/tile.
3. **Thumbnail cache granularity** — single ~256px master scaled in-widget vs. two cached sizes (§2.5).
4. **Overlay store** — extend `model_inventory_cache.json` vs. a sibling `model_overlay.json` (§2.4);
   key on `sha256` (survives moves) vs. abspath.
5. **`familyToMode` home** — a free function shared with the existing video-family list so the set stays
   single-sourced (§3.1).

---

## Amendment A — Card grid is the primary view; the card spec (frozen)

**Date:** 2026-07-12 · **Amends:** §4 (the two views), §7 (build order), §8 (open decisions)

**Reason:** the intended visual target was specified after the doc was written. It is a **card grid**, not
a thumbnail column in a tree. Building the list-with-thumbnails first would be throwaway work; the data
layer (S0) is view-agnostic and unaffected.

### A.1 Re-sequencing (supersedes §7)

| Old | New | Change |
|---|---|---|
| S1 = thumbnails in the list (tree delegate) | **S1 = the card grid** | The grid is the view. The tree becomes a secondary/optional density toggle, or is dropped. |
| S4 = grid view toggle | folded into S1 | — |

New order: **S0 (data layer) → S1 (card grid) → S2 (send-to router) → S3 (inspect / metadata panel) →
S5 (favorites overlay).** The **S1 + S2 = daily-driver payoff** line still holds — it now means grid +
working Load Model. The existing `QTreeWidget` stays in the codebase for now (it works, it's polished) but
is not the surface receiving thumbnails. Decide at S1 whether to keep it as a "compact list" toggle or
retire it.

### A.2 The card — frozen spec

Uniform cards in a flow/grid layout. Every card is identical in shape regardless of what data backs it.

| Element | Spec |
|---|---|
| Card shape | Rounded rect, `radiusPanel` (20) from `DashboardSurfaceTokens`. Rounded cards **and** rounded images. |
| Preview area | Top **2/3** of the card. Rounded (`radiusInset` 16), clipped. Fills full card width. |
| Name area | Bottom **1/3**. Model name with extension stripped (`.safetensors`/`.gguf`/`.ckpt`/`.pt`/`.pth`). Right-elide long names, full name in tooltip. |
| Preview content | Image (42%) → poster frame. Video (12%) → poster still, hover-plays mp4 (S4/later). No sidecar (43%) → the fallback tile (§2.2) **filling the same 2/3 area** — type-colored, same rounding, same size. A grid of no-preview models must look **intentional, not broken.** |
| Hover state | Reveals two actions: **Load Model** and **Inspect Model**. Hidden until hover — the resting grid stays clean. |
| Type/family cue | Small badge/chip, subordinate to the preview. |

**Fallback tile at card proportions (amends §2.2):** the placeholder is **not** a small icon in a large
empty box — it **fills the full 2/3 preview area** at the same rounding, type-colored via theme tokens,
type glyph/monogram centered, family label beneath. Layout must **never shift** between a card that has a
preview and one that doesn't.

### A.3 "Load Model" is auto-routed — §3 restated as the card's behavior

The user never chooses a destination. The card's action calls the §3 router, dispatching on the type and
family the scan already detected. **Label the action honestly per type** (the card knows the type):

| Asset | Action label | Behavior |
|---|---|---|
| Checkpoint, video family (`wan`, `ltx`, `hunyuan_video`, `cogvideox`, `mochi`) | **Load Model** | → T2V, model selected |
| Checkpoint, everything else | **Load Model** | → T2I, model selected |
| LoRA | **Add LoRA** | adds to the LoRA stack (default T2I; split for I2I). Never replaces the model. |
| VAE | (disabled + tooltip) | no VAE slot exists (§3.3). No dead button. |

**Inspect Model** → opens the metadata panel (S3). Until S3 exists, Inspect opens the existing details pane.

### A.4 Consequences for S0 (parameter decisions, not architecture)

- **Thumbnail master size:** the card preview is the only consumer (~200–280px tiles) → a **256px master**
  is correct; the ~44px list-thumb is not needed. **Closes §8.3.**
- **Fallback renders at card proportions** (full 2/3 area), not a list-row icon.

### A.5 Open decisions (amends §8)

- **§8.3 thumbnail cache granularity → CLOSED:** single 256px master.
- **New — hover-action placement:** scrim-over-preview vs. name-band — pick at S1, keep consistent.
- **New — tree fate:** keep as a compact-list toggle, or retire — decide at S1.
