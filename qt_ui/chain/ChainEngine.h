#pragma once

// SpellVision — Chain Studio engine (Pass 4a: interface).
//
// The brain. Owns one Chain at a time (v1 single-chain), drives stage
// generation by reusing the existing GenerationRequestBuilder, tracks
// completion via ChainCompletionWatcher, persists via ChainStore.
//
// SUBMISSION CONTRACT (the most important design choice in this file)
// -------------------------------------------------------------------
// Read-first finding: ImageGenerationPage does NOT call
// QueueManager::addItem directly. It produces a QJsonObject payload
// via buildRequestPayload() and hands off to a parent through an
// emitGenerate / emitQueue callback (see WorkerCommandRunner.cpp).
// The actual QueueItem-construction / id-stamping / submission glue
// lives one layer up.
//
// We therefore do NOT reinvent that glue. The engine asks its OWNER
// (Track B page, or the headless harness) to submit on its behalf
// through an injected callback. The callback receives the JSON
// payload the engine built plus the engineId the engine generated;
// the owner is responsible for wrapping it into a QueueItem and
// calling QueueManager::addItem.
//
// The engine never touches QueueManager::addItem directly. This:
//   - keeps engine logic widget-free and queue-glue-free
//   - lets the existing app/worker pipeline handle submission the
//     way it already does (including readiness checks, etc.)
//   - makes the engine trivially testable in Pass 6: the harness
//     supplies a fake submitFn that synthesizes QueueItem state for
//     the watcher to react to
//
// EVENT FLOW
// ----------
//   user -> regenerate(stageId)
//     -> buildRequestPayload(stage)   // mirrors ImageGenerationPage's
//                                     // GenerationRequestBuilder path
//     -> submitFn(payload, engineId)  // owner submits
//     -> watcher->track(engineId, chainRef)
//     ...polling cycle...
//     -> watcher->variationCompleted(chainRef, output, metadata)
//     -> finalize the pending variation, append to stage, persist,
//        emit stageStatusChanged + variationAppended

#include "chain/ChainModel.h"

#include <QHash>
#include <QJsonObject>
#include <QObject>
#include <QString>
#include <functional>

namespace spellvision::chain
{

class ChainStore;
class ChainCompletionWatcher;

class ChainEngine final : public QObject
{
    Q_OBJECT

public:
    // The owner provides this to actually submit a built payload to
    // the queue. Returning true means "submission accepted" (engine
    // proceeds to track the engineId); false means "rejected" (engine
    // marks the stage Failed and emits, no tracking happens).
    using SubmitFn = std::function<bool(const QJsonObject &payload,
                                        const QString &engineId)>;

    explicit ChainEngine(QObject *parent = nullptr);

    // Wire dependencies. v1 binds once.
    //   store / watcher must outlive the engine.
    //   submitFn is copied; lambdas with captures are fine.
    void bind(ChainStore *store,
              ChainCompletionWatcher *watcher,
              SubmitFn submitFn);

    // ----- chain lifecycle -----

    // Replace the in-memory chain with a fresh one (clears the old
    // one — single-chain v1). entryKind dictates which stage kinds
    // the first stage may be (T2I/T2V vs I2I/I2V/I2_3D).
    void newChain(EntryKind kind, QString sourceImagePath = {});

    // Load a previously saved chain from disk. Returns false if no
    // such id exists or parse fails. On success, becomes the active
    // chain and pointer is updated in QSettings.
    bool loadChain(const QString &chainId);

    // The active chain. Const-ref so callers (Track B page) can bind
    // read-only against it; mutation goes through the engine API.
    const Chain &chain() const;

    // ----- stage lifecycle -----

    // Append a new stage to the chain. kind must be consistent with
    // the prior stage (or with EntryKind for the first stage) — the
    // engine validates and returns "" on rejection, otherwise the
    // new stage's id. Subsequent stages start in Draft, inputRef set
    // to PriorStageLocked pointing at the previous stage.
    QString addStage(StageKind kind);

    // Remove a stage and ALL stages after it (a chain is linear; you
    // cannot remove a middle stage and leave its children orphaned).
    // Variations on disk are NOT deleted — the engine only forgets
    // them. Returns false if stage not found.
    bool removeStage(const QString &stageId);

    // ----- config editing -----

    // Replace the config of a stage. Rejected with false if the
    // stage is Locked (immutable per design §3) — caller must
    // unlock() first.
    bool setStageConfig(const QString &stageId, const StageConfig &cfg);

    // ----- generation -----

    // True iff the stage is in a state from which Regenerate is
    // valid: entry stage OR the prior stage isLocked(). Track B
    // binds the Regenerate button to this.
    bool canGenerate(const QString &stageId) const;

    // True iff a new stage can be appended right now. Used by the
    // ChainStudioPage rail's trailing "+ add stage" button. Rule:
    // always true when chain has no stages (first stage); else
    // true only if the last stage is Locked. Mirrors the
    // validation in addStage() so the UI can predict rejection
    // without actually attempting the add.
    bool canAddStage() const;

    // Submit a new generation for this stage. Appends a new pending
    // Variation, marks the stage Queued, calls submitFn, and on
    // success registers the engineId with the watcher. If submitFn
    // returns false, the pending variation is removed and the stage
    // becomes Failed.
    void regenerate(const QString &stageId);

    // ----- variation selection / locking -----

    // Move the selected-variation pointer (does not mutate any
    // variation). Rejected if idx is out of range. The canvas in
    // Track B follows this.
    bool selectVariation(const QString &stageId, int idx);

    // Lock the currently-selected variation as this stage's
    // committed output. Rejected if no variation is selected, the
    // stage is Failed/Draft, or the stage is already Locked.
    bool lock(const QString &stageId);

    // Unlock a locked stage. Per design §3 immutable-lock semantics:
    // this CASCADES — every stage with index > this one is reset to
    // Draft, its lockedVarIdx cleared. Variations on disk are kept.
    // Returns false if not locked.
    bool unlock(const QString &stageId);

signals:
    // Fired any time the chain's stage list shape changes (added,
    // removed) or when a stage transition the UI cares about
    // happens. Track B uses these for incremental refresh.
    void chainMutated();
    void stageStatusChanged(QString stageId, StageStatus status);
    void variationAppended(QString stageId, int newIdx);

    // Fired when a variation generation request was rejected by the
    // submitFn (engine never tracked it). The chain's stage state is
    // already updated to Failed; this signal carries the error for
    // toast/log surfaces.
    void submissionRejected(QString stageId, QString reason);

private slots:
    // ChainCompletionWatcher signal handlers.
    void onVariationRunning(QString chainRef);
    void onVariationCompleted(QString chainRef,
                              QString outputPath,
                              QString metadataPath);
    void onVariationFailed(QString chainRef, QString errorText);

private:
    // Build the JSON payload for a stage by mirroring
    // ImageGenerationPage::buildRequestPayload's pattern: copy
    // StageConfig fields 1:1 into a GenerationRequestDraft, then
    // GenerationRequestBuilder::build(draft). Inputs (the previous
    // stage's locked variation outputPath) are spliced into the
    // draft.inputImage / isImageInputMode fields before build.
    QJsonObject buildPayloadForStage(const Stage &stage) const;

    // Locate a stage by id. Returns nullptr if not found.
    Stage *findStage(const QString &stageId);
    const Stage *findStage(const QString &stageId) const;

    // Resolve the input image path for a stage given its inputRef.
    // Returns "" for InputRefKind::None (entry text stages).
    QString resolveStageInput(const Stage &stage) const;

    // Cascade per design §3: invalidate every stage with index >
    // pivotIndex. Resets to Draft, clears lockedVarIdx. Emits
    // chainMutated + per-stage stageStatusChanged.
    void cascadeInvalidate(int pivotIndex);

    // Persist + emit chainMutated. Used by every mutation site so we
    // can't forget either step.
    void persistAndNotify();

    // ----- members -----

    Chain chain_;
    ChainStore *store_ = nullptr;
    ChainCompletionWatcher *watcher_ = nullptr;
    SubmitFn submitFn_;

    // Correlation map: chainRef string -> the pending Variation's id
    // within its stage. Populated when regenerate submits; cleared
    // when the watcher fires a terminal signal. The watcher itself
    // carries the engineId-to-chainRef mapping; the engine needs the
    // reverse lookup to finalize the right variation.
    struct PendingRef
    {
        QString stageId;
        QString variationId;
    };
    QHash<QString /*chainRef*/, PendingRef> pendingByChainRef_;
};

} // namespace spellvision::chain
