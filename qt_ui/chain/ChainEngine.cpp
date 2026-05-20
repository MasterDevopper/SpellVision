#include "chain/ChainEngine.h"

#include "chain/ChainCompletionWatcher.h"
#include "chain/ChainStore.h"
#include "generation/GenerationRequestBuilder.h"

#include <QDateTime>
#include <QJsonObject>
#include <QUuid>

namespace spellvision::chain
{

namespace
{

// Canonical small helpers. UUIDs are stripped of braces for cleaner
// chainRef strings ("e91...3a" vs "{e91...3a}") and to keep them
// usable as filename fragments without escaping.
QString newUuid()
{
    return QUuid::createUuid().toString(QUuid::WithoutBraces);
}

QDateTime nowUtc()
{
    return QDateTime::currentDateTimeUtc();
}

// Is this stage kind one that produces video? Pure function of the
// enum; lives here next to the other free helpers rather than in the
// header so the engine class itself stays focused on state.
bool isVideoKind(StageKind k)
{
    return k == StageKind::T2V || k == StageKind::I2V || k == StageKind::Audio;
}

// Map StageConfig -> GenerationRequestDraft. The two structs were
// designed so this is a flat 1:1 copy (Q5 favorable resolution from
// the design doc). Done in one place so any future
// GenerationRequestDraft field additions get a single mirror edit.
spellvision::generation::GenerationRequestDraft
draftFromConfig(const StageConfig &c, StageKind kind, const QString &resolvedInput)
{
    using spellvision::generation::GenerationRequestDraft;
    using spellvision::generation::LoraRequestEntry;

    GenerationRequestDraft d;

    // The 'mode' string GenerationRequestBuilder expects mirrors what
    // ImageGenerationPage::modeKey() emits: lowercase task command.
    d.mode = toString(kind);

    d.prompt = c.prompt;
    d.negativePrompt = c.negativePrompt;
    d.preset = c.preset;

    d.model = c.model;
    d.modelDisplay = c.modelDisplay;
    d.modelFamily = c.modelFamily;
    d.modelModality = c.modelModality;
    d.modelRole = c.modelRole;
    d.selectedVideoStack = c.selectedVideoStack;

    d.workflowProfile = c.workflowProfile;
    d.workflowDraftSource = c.workflowDraftSource;
    d.workflowProfilePath = c.workflowProfilePath;
    d.workflowPath = c.workflowPath;
    d.compiledPromptPath = c.compiledPromptPath;
    d.workflowBackend = c.workflowBackend;
    d.workflowMediaType = c.workflowMediaType;
    d.promptApiExportPath = c.promptApiExportPath;

    d.ltxPrimaryModelName = c.ltxPrimaryModelName;
    d.ltxTextEncoderName = c.ltxTextEncoderName;
    d.ltxTextProjectionName = c.ltxTextProjectionName;
    d.ltxAudioVaeName = c.ltxAudioVaeName;
    d.ltxVideoVaeName = c.ltxVideoVaeName;
    d.ltxVisionEncoderName = c.ltxVisionEncoderName;
    d.ltxOutputVariant = c.ltxOutputVariant;

    d.loras.reserve(c.loras.size());
    for (const LoraEntry &le : c.loras)
    {
        LoraRequestEntry r;
        r.display = le.display;
        r.value = le.value;
        r.weight = le.weight;
        r.enabled = le.enabled;
        d.loras.append(r);
    }
    d.loraStackSummary = c.loraStackSummary;

    d.imageSampler = c.imageSampler;
    d.imageScheduler = c.imageScheduler;
    d.videoSampler = c.videoSampler;
    d.videoScheduler = c.videoScheduler;

    d.steps = c.steps;
    d.cfg = c.cfg;
    d.seed = c.seed;
    d.width = c.width;
    d.height = c.height;

    // The video-mode flag is intrinsic to the StageKind, not a
    // config field — derive it here rather than letting the caller
    // set c.isVideoMode out-of-sync with c.stageKind.
    d.isVideoMode = (kind == StageKind::T2V || kind == StageKind::I2V);
    d.frames = c.frames;
    d.fps = c.fps;
    d.videoStackMode = c.videoStackMode;
    d.wanSplit = c.wanSplit;
    d.highSteps = c.highSteps;
    d.lowSteps = c.lowSteps;
    d.splitStep = c.splitStep;
    d.highNoiseShift = c.highNoiseShift;
    d.lowNoiseShift = c.lowNoiseShift;
    d.enableVaeTiling = c.enableVaeTiling;

    d.batchCount = c.batchCount;
    d.outputPrefix = c.outputPrefix;
    d.outputFolder = c.outputFolder;
    d.modelsRoot = c.modelsRoot;

    // Image-input mode is derived from "does this stage consume an
    // image" + "do we have a resolved input path" rather than from
    // c.isImageInputMode, which the caller might leave stale.
    if (!resolvedInput.isEmpty() && consumesImageInput(kind))
    {
        d.isImageInputMode = true;
        d.inputImage = resolvedInput;
    }
    else
    {
        d.isImageInputMode = c.isImageInputMode;
        d.inputImage = c.inputImage;
    }
    d.denoiseStrength = c.denoiseStrength;

    return d;
}

} // namespace

// ---------------------------------------------------------------------------
// construction + binding
// ---------------------------------------------------------------------------

ChainEngine::ChainEngine(QObject *parent)
    : QObject(parent)
{
}

void ChainEngine::bind(ChainStore *store,
                       ChainCompletionWatcher *watcher,
                       SubmitFn submitFn)
{
    if (store_ != nullptr || watcher_ != nullptr)
    {
        // v1: bind once. Silent no-op on rebind keeps the engine
        // robust against test harness re-init, mirroring the
        // watcher's bind() policy.
        return;
    }
    store_ = store;
    watcher_ = watcher;
    submitFn_ = std::move(submitFn);

    if (watcher_ != nullptr)
    {
        connect(watcher_, &ChainCompletionWatcher::variationRunning,
                this, &ChainEngine::onVariationRunning);
        connect(watcher_, &ChainCompletionWatcher::variationCompleted,
                this, &ChainEngine::onVariationCompleted);
        connect(watcher_, &ChainCompletionWatcher::variationFailed,
                this, &ChainEngine::onVariationFailed);
    }
}

// ---------------------------------------------------------------------------
// chain lifecycle
// ---------------------------------------------------------------------------

void ChainEngine::newChain(EntryKind kind, QString sourceImagePath)
{
    chain_ = Chain{};
    chain_.id = newUuid();
    chain_.createdAt = nowUtc();
    chain_.updatedAt = chain_.createdAt;
    chain_.entryKind = kind;
    chain_.sourceImagePath = std::move(sourceImagePath);
    pendingByChainRef_.clear();

    persistAndNotify();

    if (store_ != nullptr)
        store_->setLastActiveChainId(chain_.id);
}

bool ChainEngine::loadChain(const QString &chainId)
{
    if (store_ == nullptr || chainId.trimmed().isEmpty())
        return false;

    const auto loaded = store_->load(chainId);
    if (!loaded.has_value())
        return false;

    chain_ = *loaded;
    pendingByChainRef_.clear();
    store_->setLastActiveChainId(chain_.id);
    emit chainMutated();
    return true;
}

const Chain &ChainEngine::chain() const
{
    return chain_;
}

// ---------------------------------------------------------------------------
// stage lifecycle
// ---------------------------------------------------------------------------

QString ChainEngine::addStage(StageKind kind)
{
    // First stage validation: must match the chain's entry kind.
    if (chain_.stages.isEmpty())
    {
        if (chain_.entryKind == EntryKind::DescribedText &&
            (kind != StageKind::T2I && kind != StageKind::T2V))
        {
            return QString();
        }
        if (chain_.entryKind == EntryKind::UploadedImage && !consumesImageInput(kind))
        {
            return QString();
        }
    }
    else
    {
        // Subsequent stage: predecessor must be Locked (it'll be Draft
        // /Failed until then; addStage doesn't run the stage, but the
        // user shouldn't be able to add downstream stages before
        // committing the prior one — the UI would offer that
        // affordance only after lock, but the engine validates too).
        const Stage &prev = chain_.stages.back();
        if (prev.status != StageStatus::Locked)
            return QString();

        // The new stage must consume what the prior stage produced.
        // For now, "prior stage produced an image" enables I2I / I2V
        // / I2_3D; "prior produced a video" enables Audio. T2I / T2V
        // are entry-only (no PriorStageLocked source).
        if (kind == StageKind::T2I || kind == StageKind::T2V)
            return QString();
    }

    Stage s;
    s.id = newUuid();
    s.index = static_cast<int>(chain_.stages.size());
    s.kind = kind;
    s.config.stageKind = kind;
    s.status = StageStatus::Draft;
    s.selectedVarIdx = -1;
    s.lockedVarIdx = -1;
    if (s.index == 0)
    {
        s.inputRef.kind = (chain_.entryKind == EntryKind::UploadedImage)
            ? InputRefKind::ChainSource
            : InputRefKind::None;
    }
    else
    {
        s.inputRef.kind = InputRefKind::PriorStageLocked;
        s.inputRef.priorStageId = chain_.stages.at(s.index - 1).id;
    }

    chain_.stages.append(s);
    if (chain_.selectedStageId.isEmpty())
        chain_.selectedStageId = s.id;
    persistAndNotify();
    return s.id;
}

bool ChainEngine::removeStage(const QString &stageId)
{
    int idx = -1;
    for (int i = 0; i < chain_.stages.size(); ++i)
    {
        if (chain_.stages.at(i).id == stageId)
        {
            idx = i;
            break;
        }
    }
    if (idx < 0)
        return false;

    // Linear chain — removing a stage removes everything after it.
    // We forget the stages (and their pending variations) but the
    // output files on disk are NOT deleted.
    while (chain_.stages.size() > idx)
        chain_.stages.removeLast();

    // Drop any pending tracking for vanished stages.
    auto it = pendingByChainRef_.begin();
    while (it != pendingByChainRef_.end())
    {
        bool stillAlive = false;
        for (const Stage &s : chain_.stages)
        {
            if (s.id == it->stageId)
            {
                stillAlive = true;
                break;
            }
        }
        if (!stillAlive)
            it = pendingByChainRef_.erase(it);
        else
            ++it;
    }

    // If selected stage was removed, point at the last remaining
    // stage (or clear if the chain is now empty).
    bool selectedFound = false;
    for (const Stage &s : chain_.stages)
    {
        if (s.id == chain_.selectedStageId)
        {
            selectedFound = true;
            break;
        }
    }
    if (!selectedFound)
    {
        chain_.selectedStageId = chain_.stages.isEmpty()
            ? QString()
            : chain_.stages.back().id;
    }

    persistAndNotify();
    return true;
}

// ---------------------------------------------------------------------------
// config editing
// ---------------------------------------------------------------------------

bool ChainEngine::setStageConfig(const QString &stageId, const StageConfig &cfg)
{
    Stage *s = findStage(stageId);
    if (s == nullptr)
        return false;
    if (s->status == StageStatus::Locked)
        return false;  // immutable per design §3 — caller must unlock()

    // Preserve the kind from the stage record — config.stageKind is a
    // hint but the stage itself is authoritative. Re-stamp it so a
    // caller mistake can't corrupt the stage.
    s->config = cfg;
    s->config.stageKind = s->kind;

    persistAndNotify();
    return true;
}

// ---------------------------------------------------------------------------
// generation
// ---------------------------------------------------------------------------

bool ChainEngine::canGenerate(const QString &stageId) const
{
    const Stage *s = findStage(stageId);
    if (s == nullptr)
        return false;
    if (!isExecutable(s->kind))
        return false;  // disabled kind (I2_3D / Audio for v1)
    if (s->index == 0)
        return true;
    const Stage &prev = chain_.stages.at(s->index - 1);
    return prev.status == StageStatus::Locked && prev.lockedVarIdx >= 0;
}

void ChainEngine::regenerate(const QString &stageId)
{
    Stage *s = findStage(stageId);
    if (s == nullptr)
        return;

    if (!canGenerate(stageId))
    {
        emit submissionRejected(stageId,
            isExecutable(s->kind)
                ? QStringLiteral("Cannot generate: prior stage is not locked.")
                : QStringLiteral("This stage kind is not yet supported."));
        return;
    }
    if (submitFn_ == nullptr)
    {
        emit submissionRejected(stageId,
            QStringLiteral("Engine is not wired to a submission handler."));
        return;
    }

    // Build the payload by mirroring ImageGenerationPage's pattern.
    const QJsonObject payload = buildPayloadForStage(*s);

    // Mint the engine-side ids. queue_item_id is what the Python
    // worker_service.py accepts as a client-supplied correlation id
    // (worker_service.py line 1672 uses req["queue_item_id"] if
    // present, else generates one). We rely on the host's submission
    // pipeline forwarding this field into the worker request. As of
    // Pass 4b that forwarding requires a one-line addition to
    // MainWindow::buildWorkerGenerationRequest — flagged in Pass 7
    // wiring. Until that lands, correlation via id alone may fail
    // and we'd fall back to the watcher's workerJobId/sourceJobId
    // handle — which is why Pass 3's three-handle correlation
    // strategy exists.
    const QString engineId = newUuid();
    const QString varId = newUuid();
    const QString cref = makeChainRef(chain_.id, s->id, varId);

    QJsonObject submitPayload = payload;
    submitPayload.insert(QStringLiteral("queue_item_id"), engineId);
    // Also stamp into worker_job_id / source_job_id so any of the
    // three watcher handles can find us — defensive belt-and-braces.
    submitPayload.insert(QStringLiteral("worker_job_id"), engineId);
    submitPayload.insert(QStringLiteral("source_job_id"), engineId);

    // Register a placeholder Variation NOW so a snapshot that arrives
    // before submitFn returns (very fast paths / harness scenarios)
    // has somewhere to finalize. We set outputPath to "" — it gets
    // populated on variationCompleted.
    Variation pending;
    pending.id = varId;
    pending.createdAt = nowUtc();
    pending.configSnapshot = s->config;
    pending.queueItemId = engineId;
    pending.chainRef = cref;
    pending.mediaType = isVideoKind(s->kind) ? MediaType::Video : MediaType::Image;
    s->variations.append(pending);
    const int pendingIdx = s->variations.size() - 1;

    // Pre-track BEFORE submit returns: if the snapshot arrives in the
    // same event loop iteration as submit, watcher already knows the
    // chainRef.
    if (watcher_ != nullptr)
        watcher_->track(engineId, cref);
    pendingByChainRef_.insert(cref, PendingRef{s->id, varId});

    s->status = StageStatus::Queued;
    emit stageStatusChanged(s->id, s->status);

    const bool accepted = submitFn_(submitPayload, engineId);
    if (!accepted)
    {
        // Roll back: remove the placeholder variation, untrack,
        // mark Failed, emit.
        if (watcher_ != nullptr)
            watcher_->untrack(engineId);
        pendingByChainRef_.remove(cref);
        if (pendingIdx >= 0 && pendingIdx < s->variations.size())
            s->variations.removeAt(pendingIdx);
        s->status = StageStatus::Failed;
        emit stageStatusChanged(s->id, s->status);
        emit submissionRejected(s->id,
            QStringLiteral("Submission was rejected by the host."));
        persistAndNotify();
        return;
    }

    persistAndNotify();
}

// ---------------------------------------------------------------------------
// variation selection / locking
// ---------------------------------------------------------------------------

bool ChainEngine::selectVariation(const QString &stageId, int idx)
{
    Stage *s = findStage(stageId);
    if (s == nullptr)
        return false;
    if (idx < 0 || idx >= s->variations.size())
        return false;
    s->selectedVarIdx = idx;
    persistAndNotify();
    return true;
}

bool ChainEngine::lock(const QString &stageId)
{
    Stage *s = findStage(stageId);
    if (s == nullptr)
        return false;
    if (s->status == StageStatus::Locked)
        return false;
    if (s->status != StageStatus::Completed)
        return false;  // can only lock from Completed (variations present)
    if (s->selectedVarIdx < 0 || s->selectedVarIdx >= s->variations.size())
        return false;

    s->lockedVarIdx = s->selectedVarIdx;
    s->status = StageStatus::Locked;
    emit stageStatusChanged(s->id, s->status);
    persistAndNotify();
    return true;
}

bool ChainEngine::unlock(const QString &stageId)
{
    Stage *s = findStage(stageId);
    if (s == nullptr)
        return false;
    if (s->status != StageStatus::Locked)
        return false;

    s->lockedVarIdx = -1;
    s->status = StageStatus::Completed;
    emit stageStatusChanged(s->id, s->status);

    // Per design §3: invalidate every stage with index > this one.
    cascadeInvalidate(s->index);

    persistAndNotify();
    return true;
}

// ---------------------------------------------------------------------------
// watcher signal handlers
// ---------------------------------------------------------------------------

void ChainEngine::onVariationRunning(QString chainRef)
{
    const auto it = pendingByChainRef_.find(chainRef);
    if (it == pendingByChainRef_.end())
        return;
    Stage *s = findStage(it->stageId);
    if (s == nullptr)
        return;
    if (s->status != StageStatus::Generating)
    {
        s->status = StageStatus::Generating;
        emit stageStatusChanged(s->id, s->status);
        persistAndNotify();
    }
}

void ChainEngine::onVariationCompleted(QString chainRef,
                                       QString outputPath,
                                       QString metadataPath)
{
    const auto it = pendingByChainRef_.find(chainRef);
    if (it == pendingByChainRef_.end())
        return;

    const QString stageId = it->stageId;
    const QString varId = it->variationId;
    pendingByChainRef_.erase(it);

    Stage *s = findStage(stageId);
    if (s == nullptr)
        return;

    // Find the placeholder Variation by id and finalize.
    int finalIdx = -1;
    for (int i = 0; i < s->variations.size(); ++i)
    {
        if (s->variations.at(i).id == varId)
        {
            finalIdx = i;
            break;
        }
    }
    if (finalIdx < 0)
        return;

    Variation &v = s->variations[finalIdx];
    v.outputPath = outputPath;
    v.metadataPath = metadataPath;
    // Thumbnail generation will plug in here in Pass 5
    // (ChainThumbnailer). For now, thumbnailPath stays empty and
    // the UI is responsible for falling back to a kind glyph.
    v.thumbnailPath = QString();

    s->selectedVarIdx = finalIdx;
    s->status = StageStatus::Completed;
    emit variationAppended(s->id, finalIdx);
    emit stageStatusChanged(s->id, s->status);
    persistAndNotify();
}

void ChainEngine::onVariationFailed(QString chainRef, QString errorText)
{
    const auto it = pendingByChainRef_.find(chainRef);
    if (it == pendingByChainRef_.end())
        return;

    const QString stageId = it->stageId;
    const QString varId = it->variationId;
    pendingByChainRef_.erase(it);

    Stage *s = findStage(stageId);
    if (s == nullptr)
        return;

    // Drop the placeholder variation since it never produced output.
    for (int i = 0; i < s->variations.size(); ++i)
    {
        if (s->variations.at(i).id == varId)
        {
            s->variations.removeAt(i);
            // Clamp selectedVarIdx if it pointed at or past the
            // removed slot.
            if (s->selectedVarIdx >= s->variations.size())
                s->selectedVarIdx = s->variations.size() - 1;
            break;
        }
    }

    s->status = StageStatus::Failed;
    emit stageStatusChanged(s->id, s->status);
    emit submissionRejected(stageId, errorText);
    persistAndNotify();
}

// ---------------------------------------------------------------------------
// internals
// ---------------------------------------------------------------------------

Stage *ChainEngine::findStage(const QString &stageId)
{
    for (Stage &s : chain_.stages)
    {
        if (s.id == stageId)
            return &s;
    }
    return nullptr;
}

const Stage *ChainEngine::findStage(const QString &stageId) const
{
    for (const Stage &s : chain_.stages)
    {
        if (s.id == stageId)
            return &s;
    }
    return nullptr;
}

QString ChainEngine::resolveStageInput(const Stage &stage) const
{
    switch (stage.inputRef.kind)
    {
        case InputRefKind::None:
            return QString();
        case InputRefKind::ChainSource:
            return chain_.sourceImagePath;
        case InputRefKind::PriorStageLocked:
        {
            const Stage *prior = nullptr;
            for (const Stage &p : chain_.stages)
            {
                if (p.id == stage.inputRef.priorStageId)
                {
                    prior = &p;
                    break;
                }
            }
            if (prior == nullptr || prior->lockedVarIdx < 0)
                return QString();
            if (prior->lockedVarIdx >= prior->variations.size())
                return QString();
            return prior->variations.at(prior->lockedVarIdx).outputPath;
        }
    }
    return QString();
}

QJsonObject ChainEngine::buildPayloadForStage(const Stage &stage) const
{
    using spellvision::generation::GenerationRequestBuilder;
    const QString resolvedInput = resolveStageInput(stage);
    const auto draft = draftFromConfig(stage.config, stage.kind, resolvedInput);
    return GenerationRequestBuilder::build(draft);
}

void ChainEngine::cascadeInvalidate(int pivotIndex)
{
    // Walk every stage with index > pivot and reset to Draft.
    // Variations on disk are kept; the stage just forgets them and
    // its lockedVarIdx is cleared. Per design §3 immutable-lock
    // semantics: the user explicitly requested this when they
    // unlocked, so we do not warn here — the UI is expected to
    // confirm before calling.
    for (int i = pivotIndex + 1; i < chain_.stages.size(); ++i)
    {
        Stage &s = chain_.stages[i];
        if (s.status == StageStatus::Locked || s.status == StageStatus::Completed ||
            s.status == StageStatus::Generating || s.status == StageStatus::Queued ||
            s.status == StageStatus::Failed)
        {
            s.status = StageStatus::Draft;
            s.lockedVarIdx = -1;
            emit stageStatusChanged(s.id, s.status);
        }
    }
}

void ChainEngine::persistAndNotify()
{
    chain_.updatedAt = nowUtc();
    if (store_ != nullptr && !chain_.id.isEmpty())
        store_->save(chain_);
    emit chainMutated();
}

} // namespace spellvision::chain
