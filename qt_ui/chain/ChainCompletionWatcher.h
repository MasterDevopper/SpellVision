#pragma once

// SpellVision — Chain Studio completion watcher (Pass 3).
//
// Purpose
// -------
// The SpellVision backend is poll-based: QueueManager is a passive
// store, WorkerQueueController polls the worker and applies queue
// snapshots, and there is NO native jobCompleted/jobFailed signal.
// The chain engine needs event semantics ("variation N for stage Y
// finished") and must not smear snapshot-diffing logic across itself.
//
// This component is the ONLY place in the engine that knows about
// polling. It listens to QueueManager's change signals, keeps a small
// per-tracked-id state map, diffs against new snapshots, and emits
// real Qt signals when items transition into a running or terminal
// state.
//
// Correlation strategy (the critical detail — read-first finding)
// ----------------------------------------------------------------
// itemFromSnapshotObject (QueueManager.cpp:595) builds QueueItem.id
// from a prioritized list of snapshot fields:
//     queue_item_id, id, job_id, worker_job_id, source_job_id, prompt_id
// The engine submits with a UUID it generated — but whether that UUID
// appears in the worker's snapshot under `id` is up to the Python
// worker; it may instead appear in `workerJobId` or `sourceJobId`.
//
// To stay correct regardless of which field the worker echoes, the
// watcher correlates by matching the engine-submitted id against ALL
// THREE handles on each polled item:
//     item.id  OR  item.workerJobId  OR  item.sourceJobId
// First match wins. This means engine submission code is free to
// stamp its UUID into any (or all) of those three fields and the
// watcher will find it.
//
// Lifetime / threading
// --------------------
// Single-threaded, Qt main thread. The watcher does no I/O of its own
// and never blocks. All state is in-memory; nothing persists.

#include "chain/ChainModel.h"

#include <QHash>
#include <QObject>
#include <QString>

class QueueManager;
struct QueueItem;  // PASS 3 FIXUP QUEUEITEM FORWARD DECL: real ::QueueItem from QueueManager.h
namespace spellvision::workers { class WorkerQueueController; }

namespace spellvision::chain
{

class ChainCompletionWatcher final : public QObject
{
    Q_OBJECT

public:
    explicit ChainCompletionWatcher(QObject *parent = nullptr);

    // Bind to the live queue. Safe to call once; rebinding to a
    // different QueueManager is intentionally not supported in v1
    // (no use case, and it would invalidate tracked correlations).
    // WorkerQueueController is accepted for future use (snapshot-
    // application timing if needed); currently the watcher gets
    // everything it needs from QueueManager's signals.
    void bind(QueueManager *queue, spellvision::workers::WorkerQueueController *worker = nullptr);

    // Register interest in a queue submission. engineId is whatever
    // id the engine generated and put on the submitted QueueItem
    // (the same value it placed in QueueItem.id / .workerJobId /
    // .sourceJobId — the watcher will check all three on the items
    // it sees in snapshots). chainRef is the opaque correlation
    // string the engine wants echoed back in completion signals.
    void track(const QString &engineId, const QString &chainRef);

    // Drop a tracked id (engine calls this on its own cleanup paths;
    // the watcher also auto-untracks on terminal-state emit).
    void untrack(const QString &engineId);

    // Introspection (for the Pass 6 harness + debug surfaces).
    bool isTracked(const QString &engineId) const;
    int trackedCount() const;

signals:
    // Emitted once when a tracked item is first observed running.
    void variationRunning(QString chainRef);

    // Emitted once when a tracked item reaches Completed terminal.
    // outputPath is QueueItem.outputPath as observed in the snapshot.
    // metadataPath is the result.metadata field if present, "" else.
    void variationCompleted(QString chainRef,
                            QString outputPath,
                            QString metadataPath);

    // Emitted once when a tracked item reaches Failed/Cancelled
    // terminal. errorText is QueueItem.errorText if present.
    void variationFailed(QString chainRef, QString errorText);

private slots:
    void onQueueChanged();
    void onQueueItemUpdated(const QString &itemId);
    void onQueueItemRemoved(const QString &itemId);
    void onQueuePollSucceeded();

private:
    // Per-tracked-id state we maintain so we only emit each transition
    // signal ONCE even though queueChanged can fire many times.
    enum class LastSeen
    {
        Unseen,
        Observed,
        Running,
        // (Terminal emits auto-untrack — no need to store terminal.)
    };

    struct Tracked
    {
        QString chainRef;
        LastSeen lastSeen = LastSeen::Unseen;
        qint64 missingSinceMs = 0;
        int unseenSuccessfulPolls = 0;
    };

    // Map from engine-submitted id to its tracked state.
    QHash<QString, Tracked> tracked_;

    // Cached bindings.
    QueueManager *queue_ = nullptr;
    spellvision::workers::WorkerQueueController *worker_ = nullptr;

    // Single scanning entry point — called from both onQueueChanged
    // and onQueueItemUpdated to find any tracked item that has
    // transitioned. Kept private; tested via the public signals in
    // the Pass 6 harness.
    void rescan();

    // Match a polled item against tracked engine ids. Returns the
    // matching engineId on hit, "" on miss. Tries item.id,
    // workerJobId, sourceJobId in that order.
    QString matchTrackedEngineId(const QueueItem &item) const;
};

} // namespace spellvision::chain
