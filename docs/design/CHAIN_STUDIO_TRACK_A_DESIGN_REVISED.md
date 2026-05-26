# Chain Studio — Track A: Chaining Engine Design (REVISED — build-from contract)

**Status:** all 8 open questions resolved with code-confirmed facts.
This is the contract Track B (UI) builds against. Supersedes the
earlier draft.

Resolution summary (every item settled, no remaining leans):

| # | Question | Resolution | Basis |
|---|----------|-----------|-------|
| Q0 | Completion event path? | **None exists — build `ChainCompletionWatcher`** | Confirmed: `QueueManager` passive, `WorkerQueueController` poll-only, no `jobCompleted` signal |
| Q1 | Audio = stage or modifier? | **Stage** | Young decision |
| Q2 | Thumbnails source? | **Engine-generated** | Confirmed: `worker_service.py:464` aliases `preview_path` to the full output; no separate thumb emitted |
| Q3 | Locked-stage edit semantics? | **Immutable + explicit unlock cascades downstream** | Young decision (option c) |
| Q4 | `chainRef` on `QueueItem`? | **Add the field** | Young decision |
| Q5 | `GenerationRequestBuilder` reusable? | **Yes — already widget-free** | Confirmed: `GenerationRequestBuilder.h` takes a plain `GenerationRequestDraft` struct, zero widget deps |
| Q6 | Persistence convention? | **`QSettings("DarkDuck","SpellVision")` pointer + JSON chain document** | Confirmed: `ImageGenerationPage::saveSnapshot` uses exactly this QSettings org/app |
| Q7 | Multi-chain v1? | **Single chain for v1** | Young decision |
| — | UltraShape scope | **3D-only config field, NOT a general modifier** | Young clarification |

---

## 1. Architectural anchor (unchanged, restated)

The backend is **poll-based, not event-based**. Therefore the chain
engine is a **state machine driven by queue-snapshot transitions**,
fronted by a new `ChainCompletionWatcher` that turns polled state
diffs into real Qt signals. The engine never polls directly; it
consumes the watcher's signals. This keeps snapshot-diffing in one
isolated place instead of smeared through the engine.

---

## 2. Data model

### 2.1 Chain

```
Chain
  id               : QString (uuid)
  createdAt         : QDateTime
  updatedAt         : QDateTime
  entryKind         : enum { DescribedText, UploadedImage }
  sourceImagePath   : QString          // iff entryKind == UploadedImage
  stages            : QVector<Stage>   // ordered = execution order
  selectedStageId   : QString          // UI focus
```

Linear only (v7 locked). One active chain per v1 (Q7).

### 2.2 Stage

```
Stage
  id              : QString (uuid)
  index           : int
  kind            : enum StageKind
  config          : StageConfig
  variations      : QVector<Variation>
  selectedVarIdx  : int          // -1 if none
  lockedVarIdx    : int          // -1 unlocked; else frozen output
  status          : enum StageStatus
  inputRef        : InputRef
```

```
StageKind = { T2I, T2V, I2I, I2V, I2_3D, Audio }
```
- `I2_3D` and `Audio` are **defined but execution-disabled** until
  their Python workers exist. The engine rejects a generate request
  for a disabled kind with a clear, surfaced error. Model + UI carry
  them now so neither needs rework when the workers land.

```
StageStatus = { Draft, Queued, Generating, Completed, Failed, Locked }
```
Transitions in §3.

### 2.3 Variation (append-only, never replaced)

```
Variation
  id             : QString (uuid)
  createdAt       : QDateTime
  outputPath      : QString      // full-res image/video from worker
  metadataPath    : QString
  thumbnailPath   : QString      // ENGINE-GENERATED (Q2) — see §5
  configSnapshot  : StageConfig  // exact config that produced this
  queueItemId     : QString      // QueueItem.id that produced it
  chainRef        : QString      // "chainId/stageId/variationId" (Q4)
  mediaType       : enum { Image, Video, Mesh }
```

**Hard rule:** Regenerate **appends** a Variation. The list only
grows; `selectedVarIdx` moves. `configSnapshot` lets the UI show
"settings that made variation N" and offer restore.

### 2.4 InputRef — the routing spine

```
InputRef
  kind         : enum { None, ChainSource, PriorStageLocked }
  priorStageId : QString   // iff kind == PriorStageLocked
```

- `None`             → entry stage, no image input (T2I / T2V)
- `ChainSource`      → entry stage consuming `chain.sourceImagePath`
                       (the uploaded image: I2I / I2V / I2_3D entry)
- `PriorStageLocked` → non-entry stage; input is exactly
                       `stages[index-1]`'s `lockedVarIdx` variation
                       `outputPath`

**Routing invariant:** a non-entry stage is runnable **iff its
immediate predecessor is `Locked`.** No locked predecessor →
`canGenerate == false`. Locking is the single commit boundary.

### 2.5 StageConfig — a persisted `GenerationRequestDraft` + chain bits

Q5 confirmed `GenerationRequestBuilder::build()` is a pure
`GenerationRequestDraft → QJsonObject` function with no widget
dependencies. Therefore:

> **`StageConfig` is modeled as a superset of
> `spellvision::generation::GenerationRequestDraft`.** The engine
> fills a `GenerationRequestDraft` from a `StageConfig` and calls the
> *existing* `GenerationRequestBuilder::build()` — the same path
> `ImageGenerationPage` uses. No parallel request logic, no
> translation-layer bugs.

```
StageConfig
  // --- mirrors GenerationRequestDraft 1:1 ---
  description / negativePrompt / preset
  model / modelDisplay / modelFamily / modelModality / modelRole
  selectedVideoStack (QJsonObject)
  workflow* fields, ltx* fields            (carried through verbatim)
  loras : QVector<LoraRequestEntry>        (LoRA = general modifier)
  imageSampler/Scheduler, videoSampler/Scheduler
  steps / cfg / seed / width / height
  isVideoMode / frames / fps / videoStackMode / wanSplit / split*
  batchCount / outputPrefix / outputFolder / modelsRoot
  isImageInputMode / inputImage / denoiseStrength

  // --- chain-only additions ---
  stageKind        : StageKind
  ultraShape       : UltraShapeConfig   // ONLY meaningful when
                                        // stageKind == I2_3D; ignored
                                        // and UI-hidden otherwise
```

```
UltraShapeConfig            // 3D-ONLY (Young clarification)
  path    : QString
  weight  : double
  enabled : bool
```

**LoRA stays the general modifier** (reusing
`GenerationRequestDraft::loras`). **UltraShape is NOT a general
modifier** — it is a 3D-stage-only config block, gated to
`stageKind == I2_3D`, hidden in the UI for every other kind. Modeling
it as a universal modifier (the earlier draft's mistake) is
explicitly rejected.

`batchCount` note: with the append-variation model, a single generate
with `batchCount > 1` should append N variations in one shot — a
natural fit. Engine maps each batch output to its own Variation.

---

## 3. State machine

Driven by `ChainCompletionWatcher` signals, not direct polling.

```
Draft       --user Regenerate-->            Queued
Queued      --watcher: item running-->      Generating
Generating  --watcher: item done-->         Completed   (append Variation)
            --watcher: item failed-->       Failed      (prior variations kept)
Completed   --user Regenerate-->            Queued      (append another)
Completed   --user Lock-->                  Locked
Failed      --user Regenerate-->            Queued
Locked      --user Unlock-->                Completed
              + CASCADE: every downstream stage -> invalidated
```

**Q3 cascade rule (immutable lock):** while `Locked`, a stage's
`config` and `lockedVarIdx` cannot change. To alter either, the user
must explicitly `Unlock`. Unlock sets this stage `Completed` and walks
**every** stage with `index >` this one, resetting each to `Draft`,
clearing their `lockedVarIdx`, and dropping their `inputRef` resolution
(their variations are retained on disk but the stages must be re-run
because their input is now stale). The UI must make this consequence
explicit before confirming an unlock.

Engine duties:
1. **Submit** — `StageConfig → GenerationRequestDraft →
   GenerationRequestBuilder::build() → QJsonObject`, wrap as a
   `QueueItem` (stamping `chainRef`), `QueueManager::addItem()`,
   record `queueItemId` on the pending Variation.
2. **Track** — consume `ChainCompletionWatcher` signals; on terminal
   state for a tracked `queueItemId`, finalize the Variation
   (set `outputPath`/`metadataPath` from the `QueueItem`, generate
   thumbnail per §5, append, bump `selectedVarIdx`, set `Completed`).
3. **Gate** — `bool canGenerate(stageId)` : entry stage OR
   predecessor `Locked`. UI Regenerate binds to this.
4. **Route** — `PriorStageLocked` submit resolves input =
   predecessor locked variation `outputPath`, injected as
   `inputImage` in the draft.
5. **Cascade** — Q3 unlock walk.

---

## 4. ChainCompletionWatcher (new component, Q0)

Small, isolated, the only place that knows about polling.

```
ChainCompletionWatcher : QObject
  bind(QueueManager*, WorkerQueueController*)
  // listens to QueueManager::queueItemUpdated / queueChanged
  // and WorkerQueueController::queueResponseApplied
signals:
  void stageVariationRunning(QString chainRef)
  void stageVariationCompleted(QString chainRef,
                               QString outputPath,
                               QString metadataPath)
  void stageVariationFailed(QString chainRef, QString errorText)
```

Mechanism: maintains last-seen state per tracked `QueueItem.id`
(filtered to items whose `chainRef` is non-empty). On each applied
snapshot, diffs state; emits the mapped signal on transition into a
terminal/running state. The engine connects to these three signals
and never touches `QueueManager` polling internals. Additive — does
not alter any existing queue behavior.

`chainRef` correlation (Q4): one new nullable `QString chainRef`
field on the `QueueItem` struct, format
`"<chainId>/<stageId>/<variationId>"`. Engine stamps it on submit;
watcher reads it back. Unambiguous; no field abuse.

---

## 5. Thumbnails (Q2 — engine-generated, confirmed necessary)

`worker_service.py:464` sets `preview_path` = the full output path;
**no separate thumbnail asset is ever written.** The engine must
produce its own, reusing existing mechanisms (no new infra):

- **Image variation:** `QImage(outputPath).scaled(...)` → write
  `<variationId>.thumb.jpg` beside the output. Trivial, synchronous-
  cheap, mode-agnostic.
- **Video variation:** grab one poster frame using the **same
  FFmpeg/QtMultimedia frame-extraction path ImageGenerationPage
  already uses for video previews** (do not invent a new extractor —
  reuse `MediaPreviewController` / the existing preview frame grab).
- **Mesh (I2_3D):** deferred with the disabled kind; placeholder
  glyph until a 3D preview path exists.

`thumbnailPath` stored on the Variation. If generation of the thumb
fails, fall back to a kind glyph — never block the pipeline on a
thumbnail.

---

## 6. Persistence (Q6 — confirmed convention)

`ImageGenerationPage::saveSnapshot` uses
`QSettings("DarkDuck","SpellVision")` with namespaced groups. The
queue separately persists structured state as snapshot JSON. The
chain store mirrors **both** precedents:

- **Chain document** (the full §2 model, structured/growing) →
  JSON file, one per chain, in the same app-data location the queue
  snapshot uses. *(One remaining concrete: confirm the queue
  snapshot's on-disk path by reading the queue-persistence code at
  build time — it's a 1-line lookup, not a design unknown; the
  convention is settled, only the literal directory needs reading.)*
- **Pointer** (`lastActiveChainId`, workspace reopen state) →
  `QSettings("DarkDuck","SpellVision")` under a new `ChainStudio/`
  group, mirroring the `ImageGenerationPage/<modeKey>` pattern
  exactly.

Engine stores **paths**, never copies media. Variations point at the
worker outputs already on disk plus the engine-made thumbnail.

---

## 7. Integration map (final)

| Concern | Existing component | Relationship |
|---|---|---|
| Request build | `GenerationRequestBuilder::build()` | **Reuse as-is.** `StageConfig`→`GenerationRequestDraft`→build. |
| Job submit | `QueueManager::addItem()` | Reuse; stamp `chainRef`. |
| Job execution/poll | `WorkerQueueController` | Watcher listens; engine never bypasses. |
| Completion events | *(none — new)* | Build `ChainCompletionWatcher`. |
| Output type check | `GenerationResultRouter::isImageAssetPath/isVideoAssetPath` | Reuse to validate before allowing Lock. |
| Video thumb frame | `MediaPreviewController` (existing preview frame grab) | Reuse for Variation poster frames. |
| Per-mode workers | `t2i/t2v/i2v_worker.py` | Unchanged for T2I/T2V/I2I/I2V. 3D/Audio = new workers, out of Track A. |
| `QueueItem` struct | `QueueManager.h` | Add one `QString chainRef`. |

---

## 8. Track A scope (now estimable)

Because Q5 resolved favorably (request builder reusable), Track A is
**moderate, not doubled**. New code, in dependency order:

1. **Model headers** — `Chain`, `Stage`, `Variation`, `InputRef`,
   `StageConfig`, `UltraShapeConfig`, enums. Pure data, no behavior.
2. **`QueueItem::chainRef`** — one field + plumb through
   add/update/snapshot serialization.
3. **`ChainCompletionWatcher`** — the isolated poll→signal adapter.
4. **`ChainEngine`** — submit / track / gate / route / cascade,
   consuming the watcher, reusing `GenerationRequestBuilder`.
5. **Thumbnail helper** — image scale + reuse video frame grab.
6. **`ChainStore`** — JSON document load/save + QSettings pointer.
7. **Track B UI** (`ChainStudioPage`) — built on 1–6, the v3
   fixed-workspace mockup, replacing HomePage content.

Items 1–6 are Track A (engine). Item 7 is Track B (UI), unblocked
once 1–6 expose their interfaces. 3D/Audio execution and multi-chain
are explicitly post-v1.

---

## 9. Non-goals for v1 (locked)

- No branching (linear only).
- No `I2_3D` / `Audio` *execution* (kinds defined, disabled).
- No UltraShape outside 3D stages.
- No multi-chain (single active chain).
- No unattended full-chain auto-run (human-in-the-loop: generate →
  judge variations → lock → advance).

---

The next artifact is the **concrete build plan**: file-by-file, the
order of 1–6, what each new class's interface is, the exact
`QueueItem` change, and where Track B's `ChainStudioPage` plugs into
the shell — sequenced with the same one-concern-per-pass discipline
that kept Sprint MOCKUP from spiraling. Say the word and I'll write it.
