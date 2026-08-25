#include "chain/ChainCompletionWatcher.h"

#include "QueueManager.h"
#include "workers/WorkerQueueController.h"

#include <QDateTime>
#include <QJsonObject>
#include <QSet>
#include <QTimer>

namespace spellvision::chain
{

namespace
{
constexpr qint64 kMissingSnapshotGraceMs = 5000;
constexpr int kUnseenSuccessfulPollLimit = 8;
}

ChainCompletionWatcher::ChainCompletionWatcher(QObject *parent)
    : QObject(parent)
{
}

void ChainCompletionWatcher::bind(
    QueueManager *queue,
    spellvision::workers::WorkerQueueController *worker)
{
    // v1: bind once. Rebinding would orphan in-flight correlations and
    // we have no use case for it. Silent no-op on a second call rather
    // than asserting, to keep the watcher robust against test
    // harnesses that may re-init.
    if (queue_ != nullptr)
        return;

    queue_ = queue;
    worker_ = worker;

    if (queue_ == nullptr)
        return;

    // Connect both signals: queueChanged is the bulk-update notifier
    // applied snapshots fire; queueItemUpdated is the per-item
    // notifier. Either may carry the transition we care about, so
    // we listen to both and let rescan() de-duplicate via the
    // per-tracked LastSeen state.
    connect(queue_, &QueueManager::queueChanged,
            this, &ChainCompletionWatcher::onQueueChanged);
    connect(queue_, &QueueManager::queueItemUpdated,
            this, &ChainCompletionWatcher::onQueueItemUpdated);
    connect(queue_, &QueueManager::queueItemRemoved,
            this, &ChainCompletionWatcher::onQueueItemRemoved);
    if (worker_)
    {
        connect(worker_, &spellvision::workers::WorkerQueueController::queuePollSucceeded,
                this, &ChainCompletionWatcher::onQueuePollSucceeded);
    }
}

void ChainCompletionWatcher::track(const QString &engineId, const QString &chainRef)
{
    if (engineId.trimmed().isEmpty())
        return;
    Tracked t;
    t.chainRef = chainRef;
    t.lastSeen = LastSeen::Unseen;
    tracked_.insert(engineId, t);

    // Scan immediately in case the item already exists in the queue
    // and is already running/terminal — covers the race where the
    // engine tracks after submission and a poll has already fired.
    rescan();
}

void ChainCompletionWatcher::untrack(const QString &engineId)
{
    tracked_.remove(engineId);
}

bool ChainCompletionWatcher::isTracked(const QString &engineId) const
{
    return tracked_.contains(engineId);
}

int ChainCompletionWatcher::trackedCount() const
{
    return tracked_.size();
}

// ----- slots -----------------------------------------------------------

void ChainCompletionWatcher::onQueueChanged()
{
    rescan();
}

void ChainCompletionWatcher::onQueueItemUpdated(const QString & /*itemId*/)
{
    // Don't bother filtering by itemId here — rescan() short-circuits
    // by lastSeen state for every tracked id, so it's cheap. If the
    // tracked set grows large enough that a full rescan is too much,
    // we can switch to per-item dispatch later; not worth the
    // complexity at this scale.
    rescan();
}

void ChainCompletionWatcher::onQueueItemRemoved(const QString &itemId)
{
    // Items are removed from the queue store on terminal cleanup. If
    // a tracked id is removed before we observed a terminal state —
    // for instance the worker dropped it without echoing a result —
    // treat it as a Failed transition so the engine isn't stuck
    // waiting forever. Correlate via all three handles same as scan.
    if (itemId.trimmed().isEmpty() || queue_ == nullptr)
        return;
    if (tracked_.isEmpty())
        return;
    // We can't recover the QueueItem here (already removed). Best we
    // can do is check whether the removed itemId directly matches any
    // tracked engineId or — by convention — was tracked via its id
    // alone. If we have no record we silently ignore; the engine has
    // its own timeout/cleanup paths that catch genuine ghosts.
    const auto it = tracked_.find(itemId);
    if (it == tracked_.end())
        return;
    const QString chainRef = it->chainRef;
    tracked_.erase(it);
    emit variationFailed(chainRef,
        QStringLiteral("Queue item removed before completion."));
}

void ChainCompletionWatcher::onQueuePollSucceeded()
{
    rescan();
    const QList<QString> engineIds = tracked_.keys();
    for (const QString &engineId : engineIds)
    {
        auto it = tracked_.find(engineId);
        if (it == tracked_.end() || it->lastSeen != LastSeen::Unseen)
            continue;
        ++it->unseenSuccessfulPolls;
        if (it->unseenSuccessfulPolls < kUnseenSuccessfulPollLimit)
            continue;
        const QString chainRef = it->chainRef;
        tracked_.erase(it);
        emit variationFailed(
            chainRef,
            QStringLiteral("Accepted queue item never appeared in worker queue snapshots."));
    }
}

// ----- internal --------------------------------------------------------

QString ChainCompletionWatcher::matchTrackedEngineId(const QueueItem &item) const
{
    // Try the three handles in priority order. Engine code is
    // expected to stamp its UUID on item.id (always) and at least
    // workerJobId on submission, but a Python worker may rewrite
    // id and only echo the original in workerJobId/sourceJobId.
    if (!item.id.isEmpty() && tracked_.contains(item.id))
        return item.id;
    if (!item.workerJobId.isEmpty() && tracked_.contains(item.workerJobId))
        return item.workerJobId;
    if (!item.sourceJobId.isEmpty() && tracked_.contains(item.sourceJobId))
        return item.sourceJobId;
    return QString();
}

void ChainCompletionWatcher::rescan()
{
    if (queue_ == nullptr || tracked_.isEmpty())
        return;

    // Items vector is const-ref so we don't copy. Emits during the
    // loop will call back into the engine, which may call
    // track()/untrack(), mutating tracked_ mid-iteration. Reading
    // tracked_ via .find() each lookup protects against that;
    // QueueManager itself shouldn't mutate its items vector during
    // the synchronous signal dispatch this rescan is reacting to.
    const QVector<QueueItem> &items = queue_->items();
    QSet<QString> matchedEngineIds;

    for (const QueueItem &item : items)
    {
        const QString engineId = matchTrackedEngineId(item);
        if (engineId.isEmpty())
            continue;
        matchedEngineIds.insert(engineId);

        auto it = tracked_.find(engineId);
        if (it == tracked_.end())
            continue; // raced with untrack; nothing to do

        const ChainCompletionWatcher::LastSeen seen = it->lastSeen;
        const QString chainRef = it->chainRef;
        it->missingSinceMs = 0;

        const bool isRunning =
            item.state == QueueItemState::Running ||
            item.running;
        const bool isCompleted =
            item.state == QueueItemState::Completed ||
            item.completed;
        const bool isFailed =
            item.state == QueueItemState::Failed ||
            item.state == QueueItemState::Cancelled ||
            item.failed ||
            item.cancelled;

        // Terminal states auto-untrack and emit the matching signal
        // exactly once. We check completed/failed before running so a
        // single rescan can take an item from Unseen straight to a
        // terminal (which happens with very fast jobs).
        if (isCompleted)
        {
            // outputPath is set on the QueueItem; metadataPath is in
            // metadataPath if the snapshot populated it.
            const QString outputPath = item.outputPath;
            const QString metadataPath = item.metadataPath;
            tracked_.erase(it);
            emit variationCompleted(chainRef, outputPath, metadataPath);
            continue;
        }
        if (isFailed)
        {
            QString err = item.errorText;
            if (err.trimmed().isEmpty())
                err = QStringLiteral("Generation failed without an error message.");
            tracked_.erase(it);
            emit variationFailed(chainRef, err);
            continue;
        }
        if (isRunning && seen != LastSeen::Running)
        {
            it->lastSeen = LastSeen::Running;
            emit variationRunning(chainRef);
            continue;
        }
        if (seen == LastSeen::Unseen)
            it->lastSeen = LastSeen::Observed;
    }

    const qint64 nowMs = QDateTime::currentMSecsSinceEpoch();
    const QStringList trackedIds = tracked_.keys();
    for (const QString &engineId : trackedIds)
    {
        if (matchedEngineIds.contains(engineId))
            continue;

        auto it = tracked_.find(engineId);
        if (it == tracked_.end() || it->lastSeen == LastSeen::Unseen)
            continue;

        if (it->missingSinceMs <= 0)
        {
            it->missingSinceMs = nowMs;
            QTimer::singleShot(kMissingSnapshotGraceMs, this, [this]() {
                rescan();
            });
            continue;
        }

        if (nowMs - it->missingSinceMs < kMissingSnapshotGraceMs)
            continue;

        const QString chainRef = it->chainRef;
        tracked_.erase(it);
        emit variationFailed(
            chainRef,
            QStringLiteral("Generation disappeared from worker queue snapshots before completion."));
    }
}

} // namespace spellvision::chain
