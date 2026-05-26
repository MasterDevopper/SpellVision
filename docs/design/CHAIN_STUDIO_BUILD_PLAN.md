# Chain Studio — Concrete Build Plan

**Status:** the build-from plan. Follows the revised Track A design,
corrected by the read-first finding (no `QueueItem` change needed —
engine owns correlation). One concern per pass, each pass ends on a
compiling, verifiable state, same discipline that kept Sprint MOCKUP
from spiraling.

**Read-first correction folded in:** `QueueItem` is read-only
(rebuilt from worker snapshot every poll; no C++→JSON write path).
The original "item 2: add `QueueItem::chainRef`" is **deleted** — it
would be wiped every poll. Correlation lives entirely in the new
engine via a submission→id map. No core-struct change, no Python
change, no serialization ripple.

---

## 0. Ground rules (carry from Sprint MOCKUP)

- One pass = one component = one compiling checkpoint. Never batch.
- Every pass: build clean before the next starts. No proceeding on a
  broken build (there is no existing behavior to fall back on here).
- Headless-verifiable: the engine is exercised by a test harness
  *before* any UI depends on it (Young's explicit call).
- New files only until Pass 7. Nothing existing is modified in
  Passes 1–6 except additive wiring. `HomePage` is not touched until
  Track B and even then it is *replaced by routing*, not edited in
  place (decided at Pass 7 planning).
- File locations follow repo convention: engine under
  `qt_ui/chain/` (new dir), mirroring how `qt_ui/shell/` namespaces
  the shell controllers.

---

## 1. Component dependency order (the spine)

```
Pass 1  ChainModel            (pure data headers, zero behavior)
Pass 2  ChainStore            (model <-> JSON + QSettings pointer)
Pass 3  ChainCompletionWatcher(poll snapshot -> Qt signals)
Pass 4  ChainEngine           (submit/track/gate/route/cascade)
Pass 5  ChainThumbnailer      (image scale + reuse video framegrab)
Pass 6  Headless harness      (exercise 1-5, no UI)  <-- CHECKPOINT
--- Track A complete, engine proven ---
Pass 7  ChainStudioPage scaffold (v3 workspace shell, stub data)
Pass 8  Wire page -> engine    (real model, real generation)
Pass 9  Shell routing          (Home rail -> ChainStudioPage)
Pass 10 Polish + edge cases
```

Passes 1–6 are Track A. 7–10 are Track B. The Pass 6 checkpoint is a
deliberate stop-and-reassess: the engine works headlessly before the
UI is built on it.

---

## PASS 1 — ChainModel (pure data)

**Files (new):**
`qt_ui/chain/ChainModel.h` (+ `.cpp` only if non-inline helpers
needed; aim header-only for the structs).

**Contents:** the §2 model from the revised design, as plain structs:
`StageKind`, `StageStatus`, `Chain`, `Stage`, `Variation`,
`InputRef`, `StageConfig`, `UltraShapeConfig`.

**Key decisions baked in:**
- `StageConfig` mirrors `spellvision::generation::GenerationRequestDraft`
  field-for-field, plus `stageKind` and `ultraShape`. It does **not**
  inherit from it (avoid coupling the model header to the generation
  header); it carries the same fields so a 1:1 copy function is
  trivial in Pass 4.
- `UltraShapeConfig` is a standalone struct referenced only when
  `stageKind == I2_3D`.
- All enums `enum class`, with a `toString`/`fromString` free
  function pair per enum (needed by Pass 2 JSON).
- No Qt widget includes. `QString`, `QVector`, `QDateTime`,
  `QJsonObject` only.

**Verification:** compiles as a standalone TU. A throwaway
`static_assert`-style sanity check (sizeof, default-construct) in the
Pass 6 harness, not here. Pass 1 success = it builds and is
code-reviewable as a faithful encoding of the design §2.

**Risk:** low. Pure data. The only way this is "wrong" is if it
mis-encodes the design — which is a review catch, not a runtime bug.

---

## PASS 2 — ChainStore (persistence)

**Files (new):** `qt_ui/chain/ChainStore.h/.cpp`

**Interface:**
```
class ChainStore {
public:
  // JSON document <-> model
  static QJsonObject toJson(const Chain&);
  static std::optional<Chain> fromJson(const QJsonObject&);

  // disk
  bool save(const Chain&);                 // writes <dir>/<id>.json
  std::optional<Chain> load(const QString& chainId);

  // QSettings pointer (mirrors ImageGenerationPage convention)
  void setLastActiveChainId(const QString&);
  QString lastActiveChainId() const;       // "" if none
private:
  QString chainsDir() const;               // see note
};
```

**Convention (confirmed):**
- Pointer → `QSettings("DarkDuck","SpellVision")`, group
  `ChainStudio/`, key `lastActiveChainId`. Exactly mirrors
  `ImageGenerationPage::saveSnapshot`.
- Document → JSON file per chain.

**The one residual lookup (do this IN this pass, not before):**
`chainsDir()` must match wherever the queue snapshot JSON is written.
At the start of Pass 2, read the queue-snapshot write path
(`QueueManager`/related) and point `chainsDir()` at a `chains/`
sibling of it. This is a 1-line lookup, scoped here so the convention
is settled with code in hand, not guessed.

**Verification:** round-trip test in Pass 6 harness
(`fromJson(toJson(chain)) == chain` for a hand-built chain with 2
stages, variations, locked indices). Pass 2 alone = compiles + the
toJson/fromJson are reviewable against the model.

**Risk:** low-moderate. JSON round-trip omissions are the classic
bug. Mitigation: the Pass 6 harness does a field-complete equality
check, not a smoke check.

---

## PASS 3 — ChainCompletionWatcher (poll → signal)

**Files (new):** `qt_ui/chain/ChainCompletionWatcher.h/.cpp`

**Interface:**
```
class ChainCompletionWatcher : public QObject {
  Q_OBJECT
public:
  void bind(QueueManager*, WorkerQueueController*);
  // engine registers interest by the queue item id it got at submit
  void track(const QString& queueItemId, const QString& chainRef);
  void untrack(const QString& queueItemId);
signals:
  void variationRunning(QString chainRef);
  void variationCompleted(QString chainRef,
                          QString outputPath, QString metadataPath);
  void variationFailed(QString chainRef, QString errorText);
};
```

**Mechanism (correction from read-first):** correlation is **not**
via a `QueueItem` field. The engine tells the watcher
"`queueItemId X` is chainRef Y" via `track()`. The watcher listens to
`QueueManager::queueItemUpdated`/`queueChanged`, keeps last-seen
`state` per tracked id, and on transition into running/terminal emits
the mapped signal carrying the chainRef the engine registered. On
terminal, auto-untracks.

**Open detail to resolve IN this pass:** the id the engine has at
submit time (return of `QueueManager::addItem`) must be the same id
that appears in subsequent snapshots. Verify by reading `addItem`
+ `itemFromSnapshotObject` id assignment at Pass 3 start. If
submit-time id ≠ snapshot id, the watcher correlates on
`workerJobId`/`sourceJobId` instead — the design already anticipated
this; confirm which handle is stable before writing the match.

**Verification:** Pass 6 harness feeds synthetic snapshots
(Queued→Running→Completed and →Failed) and asserts the right signals
fire once each with the right chainRef. This is the highest-value
test in the whole plan — the poll-state-machine is the part most
likely to be subtly wrong.

**Risk:** moderate-high. This is the load-bearing correctness piece.
It gets the most thorough harness coverage. Isolated by design so a
bug here can't smear into the engine.

---

## PASS 4 — ChainEngine (the brain)

**Files (new):** `qt_ui/chain/ChainEngine.h/.cpp`

**Interface (the contract Track B binds to):**
```
class ChainEngine : public QObject {
  Q_OBJECT
public:
  void bind(QueueManager*, WorkerQueueController*,
            ChainCompletionWatcher*, ChainStore*);

  // chain lifecycle
  Chain& chain();                          // the single v1 chain
  void newChain(EntryKind, QString sourceImagePath = {});
  QString addStage(StageKind);             // returns new stage id
  void removeStage(const QString& stageId);

  // generation
  bool canGenerate(const QString& stageId) const;  // §2.4 invariant
  void regenerate(const QString& stageId);          // appends variation
  void selectVariation(const QString& stageId, int idx);
  void lock(const QString& stageId);
  void unlock(const QString& stageId);              // §3 cascade

signals:
  void stageStatusChanged(QString stageId, StageStatus);
  void variationAppended(QString stageId, int newIdx);
  void chainMutated();                     // UI re-render hint
};
```

**Internals:**
- Owns `QHash<QString /*queueItemId*/, ChainRef>` — the correlation
  map that replaces the deleted QueueItem field.
- `regenerate`: `StageConfig` → copy into a
  `GenerationRequestDraft` → `GenerationRequestBuilder::build()`
  (reused verbatim) → `QueueManager::addItem` → get id →
  `watcher->track(id, chainRef)` → record pending Variation.
- Connect watcher signals: on `variationCompleted`, finalize the
  pending Variation (set paths, call Pass 5 thumbnailer, append, bump
  selected, status→Completed, persist via ChainStore).
- `canGenerate`: entry stage OR predecessor `Locked`.
- `lock`/`unlock`: §3 state machine incl. the immutable-lock cascade
  (unlock walks `index >` and resets to Draft, clears lockedVarIdx).
- Every mutation → `ChainStore::save` + `chainMutated()`.

**Verification:** Pass 6 harness drives a full scripted chain:
new chain → addStage(T2I) → regenerate (synthetic completion via the
watcher harness) → 3 variations appended → lock → addStage(I2V) →
canGenerate true only after lock → regenerate → unlock T2I → assert
I2V cascaded to Draft. This proves the whole engine headlessly.

**Risk:** high (it's the brain) but **de-risked**: every dependency
(model, store, watcher, request builder) is already proven by the
time this pass runs. Its own logic is the only new risk surface.

---

## PASS 5 — ChainThumbnailer

**Files (new):** `qt_ui/chain/ChainThumbnailer.h/.cpp`

**Interface:**
```
class ChainThumbnailer {
public:
  // returns thumb path, or "" on failure (never throws, never blocks)
  static QString makeImageThumb(const QString& outputPath,
                                const QString& outId);
  static QString makeVideoPoster(const QString& outputPath,
                                 const QString& outId);
};
```

**Mechanism (confirmed, reuse-only):**
- Image: `QImage(path).scaled(...)` → write `<outId>.thumb.jpg`
  beside the output.
- Video: reuse the **existing** `MediaPreviewController` frame-grab
  path (do not write a new extractor). At Pass 5 start, read
  `MediaPreviewController` to find the exact reusable entry point.
- Failure → return `""`; engine falls back to a kind glyph. A bad
  thumb never blocks the pipeline (explicit rule).

**Verification:** Pass 6 harness points it at a sample image + sample
video, asserts a thumb file appears and is smaller; asserts `""` on a
bogus path (no crash).

**Risk:** low. Self-contained, failure-tolerant by contract.

---

## PASS 6 — Headless harness  ★ CHECKPOINT ★

**Files (new):** `qt_ui/chain/chain_harness_main.cpp` (a separate
tiny executable target, or a `--chain-selftest` flag on the existing
binary — decide at Pass 6 start based on CMake structure).

**What it does:** no UI. Constructs the real engine + store +
watcher + thumbnailer wired together, plus a *fake snapshot feeder*
standing in for the worker (emits synthetic queue snapshots so
completions can be driven deterministically). Runs the scripted
scenarios from Passes 2/3/4/5 verifications as assertions, prints
PASS/FAIL per scenario, exits non-zero on any fail.

**Why this is the checkpoint:** after Pass 6, the entire chaining
engine is **proven to work without a single line of UI**. If the
model, persistence, poll-correlation, or state machine is wrong, it
is caught here — cheaply, deterministically, before Track B exists.
This is the structural equivalent of the Sprint MOCKUP dry-run, scaled
to a subsystem.

**Stop-and-reassess gate:** we do not start Pass 7 until the harness
is green. If the engine needs design changes, this is where we learn
it — and the cost is contained because nothing is built on it yet.

**Risk:** the harness itself is low risk; its *value* is catching the
high-risk bugs from Passes 3–4 before they compound.

---

## PASS 7 — ChainStudioPage scaffold (Track B begins)

**Files (new):** `qt_ui/ChainStudioPage.h/.cpp`

The v3 fixed-workspace mockup as a real `QWidget`, but **bound to a
stubbed engine** (an in-memory fake `Chain` with hardcoded stages/
variations). No real generation yet. This is pure layout/structure:
fixed viewport, pinned top (upload + dialog + thin rail), dominant
canvas, single config panel, one variation pager.

Reuses Sprint MOCKUP's proven primitives: `createCard`,
`ThemeManager` tokens, the disclosure pattern, chip styling. Built in
sub-passes if it gets large (like ImageGenerationPage's Sprint
MOCKUP), each compiling.

**Verification:** visual, against the v3 mockup. Stub data so layout
can be judged without the engine.

---

## PASS 8 — Wire page → engine

Replace the stub with the real `ChainEngine`. Connect:
config panel edits → `StageConfig`; Regenerate →
`engine.regenerate`; pager → `selectVariation`; Lock →
`engine.lock`; rail node selection → `selectedStageId`; engine
signals → UI refresh. Canvas shows last *completed* variation;
rail nodes show live status (the Q1 split).

**Verification:** real end-to-end — describe, add T2I stage,
generate, get variations, lock, add I2V, generate from locked
output, on a real machine. The first point real generation flows
through the chain.

**Risk:** integration risk concentrated here, but both sides
(engine, UI) are independently proven by now, so failures localize to
the wiring.

---

## PASS 9 — Shell routing

Point the Home rail entry at `ChainStudioPage` instead of the old
`HomePage`. Decide at Pass 9 planning: route-swap vs. delete old
HomePage (lean: route-swap first, keep old page dormant one release
for safety, delete later — mirrors the "keep the .bak" caution from
Sprint MOCKUP).

**Verification:** Home rail opens Chain Studio; nothing else in the
shell regresses.

---

## PASS 10 — Polish + edge cases

Empty chain state, failed-stage UI, unlock-cascade confirmation
dialog, disabled-kind (I2_3D/Audio) messaging, persistence across
restart, thumbnail-failure glyph fallback. One concern per sub-pass.

---

## 2. What is explicitly NOT in this plan (v1 non-goals, locked)

Branching · I2_3D/Audio execution · UltraShape outside 3D ·
multi-chain · unattended full-chain auto-run. The model carries the
disabled kinds; the engine rejects executing them with a surfaced
error.

---

## 3. Honest framing

This is **10 passes across multiple sessions**, not one sprint. Each
pass ends on a compiling, reviewable state you could stop at. Passes
1–6 produce a headless-proven engine with zero UI risk absorbed.
Pass 6 is a real gate — green harness or we fix the design before
proceeding. The single biggest original risk (QueueItem struct
change) was eliminated by reading first. The second biggest
(GenerationRequestBuilder reuse) resolved favorably. What remains is
ordinary, sequenced, verifiable work.

**Next action:** Pass 1 — `ChainModel.h`. Smallest, lowest-risk,
purely reviewable, and everything else depends on it. Say go and I
write it as the first concrete artifact.
