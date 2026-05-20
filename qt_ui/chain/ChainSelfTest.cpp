#include "chain/ChainSelfTest.h"

#include "QueueManager.h"
#include "chain/ChainCompletionWatcher.h"
#include "chain/ChainEngine.h"
#include "chain/ChainStore.h"

#include <QCoreApplication>
#include <QDir>
#include <QEventLoop>
#include <QJsonArray>
#include <QJsonObject>
#include <QObject>
#include <QStandardPaths>
#include <QString>
#include <QTextStream>
#include <QTimer>

#include <functional>
#include <vector>

namespace spellvision::chain
{

namespace
{

// ---------------------------------------------------------------------------
// Tiny assertion mechanism — no Qt Test dependency. Each scenario
// reports PASS or FAIL with the first failing predicate.
// ---------------------------------------------------------------------------

struct ScenarioResult
{
    QString name;
    bool ok = true;
    QString firstFailure;
};

// Formatting helpers — render values for the FAIL message in a way
// that's useful to a human. QVariant::fromValue() doesn't know how to
// print enum class values without explicit metatype registration; this
// overload set covers the types we actually compare.
inline QString toDisplay(const QString &s)        { return QStringLiteral("'") + s + QStringLiteral("'"); }
inline QString toDisplay(const char *s)           { return QStringLiteral("'") + QString::fromUtf8(s) + QStringLiteral("'"); }
inline QString toDisplay(bool b)                  { return b ? QStringLiteral("true") : QStringLiteral("false"); }
inline QString toDisplay(int v)                   { return QString::number(v); }
inline QString toDisplay(qsizetype v)             { return QString::number(v); }
inline QString toDisplay(StageStatus s)           { return spellvision::chain::toString(s); }
inline QString toDisplay(StageKind k)             { return spellvision::chain::toString(k); }
inline QString toDisplay(EntryKind e)             { return spellvision::chain::toString(e); }
inline QString toDisplay(MediaType m)             { return spellvision::chain::toString(m); }
inline QString toDisplay(InputRefKind k)          { return spellvision::chain::toString(k); }

class Scenario
{
public:
    explicit Scenario(QString name) : name_(std::move(name)) {}

    template <typename T, typename U>
    void check_eq(const QString &label, const T &actual, const U &expected)
    {
        if (!(actual == expected))
        {
            if (ok_)
            {
                ok_ = false;
                firstFailure_ = label
                    + QStringLiteral(": expected [")
                    + toDisplay(expected)
                    + QStringLiteral("] got [")
                    + toDisplay(actual)
                    + QStringLiteral("]");
            }
        }
    }

    void check_true(const QString &label, bool value)
    {
        if (!value && ok_)
        {
            ok_ = false;
            firstFailure_ = label + QStringLiteral(": expected true, got false");
        }
    }

    void check_false(const QString &label, bool value)
    {
        if (value && ok_)
        {
            ok_ = false;
            firstFailure_ = label + QStringLiteral(": expected false, got true");
        }
    }

    ScenarioResult finalize() const
    {
        return {name_, ok_, firstFailure_};
    }

private:
    QString name_;
    bool ok_ = true;
    QString firstFailure_;
};

// ---------------------------------------------------------------------------
// Synthetic snapshot helpers — build the QJsonObject shapes
// QueueManager::applyQueueSnapshot expects (per QueueManager.cpp:595
// itemFromSnapshotObject).
// ---------------------------------------------------------------------------

QJsonObject makeSnapshotItem(const QString &queueItemId,
                             const QString &state,
                             const QString &outputPath = {},
                             const QString &metadataPath = {})
{
    QJsonObject item;
    item.insert(QStringLiteral("queue_item_id"), queueItemId);
    item.insert(QStringLiteral("worker_job_id"), queueItemId);
    item.insert(QStringLiteral("source_job_id"), queueItemId);
    item.insert(QStringLiteral("state"), state);

    QJsonObject result;
    if (!outputPath.isEmpty())
        result.insert(QStringLiteral("output"), outputPath);
    if (!metadataPath.isEmpty())
        result.insert(QStringLiteral("metadata_output"), metadataPath);
    item.insert(QStringLiteral("result"), result);

    return item;
}

QJsonObject makeSnapshotWith(const std::vector<QJsonObject> &items)
{
    QJsonArray arr;
    for (const QJsonObject &it : items)
        arr.append(it);
    QJsonObject snap;
    snap.insert(QStringLiteral("items"), arr);
    return snap;
}

// Process pending Qt events so queued signal connections (the engine's
// watcher subscriptions) actually deliver. The harness drives events
// synchronously; we just need to drain the loop between submits and
// assertions.
void pumpEvents(int iterations = 3)
{
    for (int i = 0; i < iterations; ++i)
        QCoreApplication::processEvents(QEventLoop::AllEvents, 10);
}

// Lightweight signal counter — avoids pulling in Qt6::Test just to
// use QSignalSpy. Connects a lambda that increments a public counter
// each time the signal fires.
template <typename Sender, typename Signal>
class QSignalSpyLite : public QObject
{
public:
    int count = 0;

    QSignalSpyLite(Sender *sender, Signal signal)
    {
        QObject::connect(sender, signal, this, [this]() { ++count; });
    }
};

// Returns a fresh path under a per-test temp dir (we use the OS temp +
// a "spellvision_chain_selftest" subdir). The harness cleans the dir
// up at the end of runChainSelfTest().
QString tempRoot()
{
    const QString base = QStandardPaths::writableLocation(QStandardPaths::TempLocation);
    QString root = QDir(base).filePath(QStringLiteral("spellvision_chain_selftest"));
    QDir().mkpath(root);
    return root;
}

void cleanTempRoot()
{
    QDir d(tempRoot());
    if (d.exists())
        d.removeRecursively();
}

// ---------------------------------------------------------------------------
// Scenario runner — sets up fresh engine+store+watcher+queue per
// scenario so state can't leak between scripts.
// ---------------------------------------------------------------------------

struct TestRig
{
    QueueManager queue;
    ChainCompletionWatcher watcher;
    ChainStore store;
    ChainEngine engine;

    // Records every payload submitFn received, in order.
    std::vector<QJsonObject> submittedPayloads;

    explicit TestRig(const QString &storeRoot)
        : store(storeRoot)
    {
        watcher.bind(&queue);
        engine.bind(&store, &watcher,
            [this](const QJsonObject &payload, const QString & /*engineId*/) {
                submittedPayloads.push_back(payload);
                return true;
            });
    }
};

// Drive the queue forward by replacing its current snapshot with a new
// set of items. QueueManager::applyQueueSnapshot is the public API
// the real worker poll uses, so the watcher experiences exactly the
// same signal sequence it will in production.
void pushSnapshot(QueueManager &q, const std::vector<QJsonObject> &items)
{
    q.applyQueueSnapshot(makeSnapshotWith(items));
}

} // anonymous namespace

// ---------------------------------------------------------------------------
// Scenarios
// ---------------------------------------------------------------------------

int runChainSelfTest()
{
    cleanTempRoot();
    QTextStream out(stdout);
    out << "=== Chain Studio Self-Test (Pass 6) ===" << Qt::endl;

    std::vector<ScenarioResult> results;

    // -------------------------------------------------------------------
    // 1. new chain + add T2I + regenerate -> status Queued, payload sent.
    // -------------------------------------------------------------------
    {
        Scenario s(QStringLiteral("01_new_chain_addT2I_regenerate_queued"));
        TestRig rig(tempRoot());
        rig.engine.newChain(EntryKind::DescribedText);
        s.check_false("chain id empty", rig.engine.chain().id.isEmpty());

        const QString stageId = rig.engine.addStage(StageKind::T2I);
        s.check_false("addStage(T2I) returned empty id", stageId.isEmpty());
        s.check_eq("stage count after addStage", rig.engine.chain().stages.size(), 1);
        s.check_true("canGenerate on entry stage", rig.engine.canGenerate(stageId));

        rig.engine.regenerate(stageId);
        pumpEvents();
        s.check_eq("submitFn called once", static_cast<int>(rig.submittedPayloads.size()), 1);
        s.check_eq("status went Queued",
                   rig.engine.chain().stages.first().status,
                   StageStatus::Queued);
        s.check_eq("variation appended (pending)",
                   rig.engine.chain().stages.first().variations.size(), 1);

        results.push_back(s.finalize());
    }

    // -------------------------------------------------------------------
    // 2. inject Running snapshot -> status Generating, no double-emit.
    // -------------------------------------------------------------------
    {
        Scenario s(QStringLiteral("02_running_snapshot_transitions_to_Generating"));
        TestRig rig(tempRoot());
        rig.engine.newChain(EntryKind::DescribedText);
        const QString stageId = rig.engine.addStage(StageKind::T2I);
        rig.engine.regenerate(stageId);
        pumpEvents();

        const QString engineId = rig.submittedPayloads.front()
            .value(QStringLiteral("queue_item_id")).toString();
        s.check_false("engineId in payload", engineId.isEmpty());

        QSignalSpyLite runningSpy(&rig.watcher,
            &ChainCompletionWatcher::variationRunning);
        pushSnapshot(rig.queue, {makeSnapshotItem(engineId, "running")});
        pumpEvents();
        s.check_eq("variationRunning fired once", runningSpy.count, 1);
        s.check_eq("status Generating",
                   rig.engine.chain().stages.first().status,
                   StageStatus::Generating);

        // Replay same Running snapshot -> must NOT re-emit.
        pushSnapshot(rig.queue, {makeSnapshotItem(engineId, "running")});
        pumpEvents();
        s.check_eq("variationRunning not re-emitted on duplicate", runningSpy.count, 1);

        results.push_back(s.finalize());
    }

    // -------------------------------------------------------------------
    // 3. inject Completed snapshot -> variation finalized + status Completed.
    // -------------------------------------------------------------------
    {
        Scenario s(QStringLiteral("03_completed_snapshot_finalizes_variation"));
        TestRig rig(tempRoot());
        rig.engine.newChain(EntryKind::DescribedText);
        const QString stageId = rig.engine.addStage(StageKind::T2I);
        rig.engine.regenerate(stageId);
        pumpEvents();
        const QString engineId = rig.submittedPayloads.front()
            .value(QStringLiteral("queue_item_id")).toString();

        const QString outPath = QStringLiteral("C:/tmp/spellvision/out_001.png");
        const QString metaPath = QStringLiteral("C:/tmp/spellvision/out_001.json");
        pushSnapshot(rig.queue, {makeSnapshotItem(engineId, "completed", outPath, metaPath)});
        pumpEvents();

        const Stage &st = rig.engine.chain().stages.first();
        s.check_eq("status Completed", st.status, StageStatus::Completed);
        s.check_eq("variation count == 1", st.variations.size(), 1);
        s.check_eq("variation.outputPath", st.variations.first().outputPath, outPath);
        s.check_eq("variation.metadataPath", st.variations.first().metadataPath, metaPath);
        s.check_eq("selectedVarIdx", st.selectedVarIdx, 0);
        results.push_back(s.finalize());
    }

    // -------------------------------------------------------------------
    // 4. regenerate twice -> variations appended (not replaced).
    // -------------------------------------------------------------------
    {
        Scenario s(QStringLiteral("04_regenerate_appends_variation"));
        TestRig rig(tempRoot());
        rig.engine.newChain(EntryKind::DescribedText);
        const QString stageId = rig.engine.addStage(StageKind::T2I);

        // First regen -> complete.
        rig.engine.regenerate(stageId);
        pumpEvents();
        QString id1 = rig.submittedPayloads.at(0).value(QStringLiteral("queue_item_id")).toString();
        pushSnapshot(rig.queue, {makeSnapshotItem(id1, "completed",
            QStringLiteral("/tmp/out1.png"))});
        pumpEvents();

        // Second regen -> complete.
        rig.engine.regenerate(stageId);
        pumpEvents();
        QString id2 = rig.submittedPayloads.at(1).value(QStringLiteral("queue_item_id")).toString();
        s.check_false("id1 != id2", id1 == id2);
        pushSnapshot(rig.queue, {
            makeSnapshotItem(id1, "completed", QStringLiteral("/tmp/out1.png")),
            makeSnapshotItem(id2, "completed", QStringLiteral("/tmp/out2.png"))
        });
        pumpEvents();

        const Stage &st = rig.engine.chain().stages.first();
        s.check_eq("variations count == 2", st.variations.size(), 2);
        s.check_eq("first variation path preserved",
                   st.variations.at(0).outputPath, QStringLiteral("/tmp/out1.png"));
        s.check_eq("second variation path",
                   st.variations.at(1).outputPath, QStringLiteral("/tmp/out2.png"));
        s.check_eq("selectedVarIdx points at last", st.selectedVarIdx, 1);
        results.push_back(s.finalize());
    }

    // -------------------------------------------------------------------
    // 5. lock a completed stage -> status Locked.
    // -------------------------------------------------------------------
    {
        Scenario s(QStringLiteral("05_lock_completed_stage"));
        TestRig rig(tempRoot());
        rig.engine.newChain(EntryKind::DescribedText);
        const QString stageId = rig.engine.addStage(StageKind::T2I);
        rig.engine.regenerate(stageId);
        pumpEvents();
        const QString eid = rig.submittedPayloads.front()
            .value(QStringLiteral("queue_item_id")).toString();
        pushSnapshot(rig.queue, {makeSnapshotItem(eid, "completed",
            QStringLiteral("/tmp/locked.png"))});
        pumpEvents();

        s.check_true("lock() returned true", rig.engine.lock(stageId));
        s.check_eq("status Locked",
                   rig.engine.chain().stages.first().status,
                   StageStatus::Locked);
        s.check_eq("lockedVarIdx == selected",
                   rig.engine.chain().stages.first().lockedVarIdx, 0);
        results.push_back(s.finalize());
    }

    // -------------------------------------------------------------------
    // 6. canGenerate gating on downstream stages.
    // -------------------------------------------------------------------
    {
        Scenario s(QStringLiteral("06_canGenerate_gates_on_predecessor_lock"));
        TestRig rig(tempRoot());
        rig.engine.newChain(EntryKind::DescribedText);
        const QString s1 = rig.engine.addStage(StageKind::T2I);
        rig.engine.regenerate(s1);
        pumpEvents();
        const QString eid = rig.submittedPayloads.front()
            .value(QStringLiteral("queue_item_id")).toString();
        pushSnapshot(rig.queue, {makeSnapshotItem(eid, "completed",
            QStringLiteral("/tmp/source.png"))});
        pumpEvents();
        rig.engine.lock(s1);

        const QString s2 = rig.engine.addStage(StageKind::I2V);
        s.check_false("addStage(I2V) succeeded after lock", s2.isEmpty());
        s.check_true("canGenerate(s2) true after s1 lock",
                     rig.engine.canGenerate(s2));
        results.push_back(s.finalize());
    }

    // -------------------------------------------------------------------
    // 7. downstream stage receives prior locked output as inputImage.
    // -------------------------------------------------------------------
    {
        Scenario s(QStringLiteral("07_downstream_payload_inputImage_is_locked_output"));
        TestRig rig(tempRoot());
        rig.engine.newChain(EntryKind::DescribedText);
        const QString s1 = rig.engine.addStage(StageKind::T2I);
        rig.engine.regenerate(s1);
        pumpEvents();
        const QString eid1 = rig.submittedPayloads.front()
            .value(QStringLiteral("queue_item_id")).toString();
        const QString sourceOut = QStringLiteral("/tmp/inputseed.png");
        pushSnapshot(rig.queue, {makeSnapshotItem(eid1, "completed", sourceOut)});
        pumpEvents();
        rig.engine.lock(s1);

        const QString s2 = rig.engine.addStage(StageKind::I2V);
        rig.engine.regenerate(s2);
        pumpEvents();
        s.check_eq("submitFn called twice (s1, s2)",
                   static_cast<int>(rig.submittedPayloads.size()), 2);

        // GenerationRequestBuilder.cpp:385 emits draft.inputImage at
        // the key "input_image" when draft.isImageInputMode is true.
        // We verified this directly so the assertion is exact rather
        // than heuristic — a regression in the field name will fail
        // here loudly.
        const QJsonObject downstream = rig.submittedPayloads.at(1);
        const QString inputImage = downstream.value(QStringLiteral("input_image")).toString();
        s.check_eq("downstream payload input_image is prior locked output",
                   inputImage, sourceOut);
        results.push_back(s.finalize());
    }

    // -------------------------------------------------------------------
    // 8. unlock cascades downstream stages to Draft.
    // -------------------------------------------------------------------
    {
        Scenario s(QStringLiteral("08_unlock_cascades_downstream_to_Draft"));
        TestRig rig(tempRoot());
        rig.engine.newChain(EntryKind::DescribedText);
        const QString s1 = rig.engine.addStage(StageKind::T2I);
        rig.engine.regenerate(s1);
        pumpEvents();
        const QString eid1 = rig.submittedPayloads.front()
            .value(QStringLiteral("queue_item_id")).toString();
        pushSnapshot(rig.queue, {makeSnapshotItem(eid1, "completed",
            QStringLiteral("/tmp/seed.png"))});
        pumpEvents();
        rig.engine.lock(s1);
        const QString s2 = rig.engine.addStage(StageKind::I2V);
        rig.engine.regenerate(s2);
        pumpEvents();
        const QString eid2 = rig.submittedPayloads.at(1)
            .value(QStringLiteral("queue_item_id")).toString();
        pushSnapshot(rig.queue, {
            makeSnapshotItem(eid1, "completed", QStringLiteral("/tmp/seed.png")),
            makeSnapshotItem(eid2, "completed", QStringLiteral("/tmp/clip.mp4"))
        });
        pumpEvents();
        rig.engine.lock(s2);

        s.check_true("unlock(s1) returned true", rig.engine.unlock(s1));
        s.check_eq("s1 status Completed after unlock",
                   rig.engine.chain().stages.at(0).status, StageStatus::Completed);
        s.check_eq("s1 lockedVarIdx cleared",
                   rig.engine.chain().stages.at(0).lockedVarIdx, -1);
        s.check_eq("s2 cascaded to Draft",
                   rig.engine.chain().stages.at(1).status, StageStatus::Draft);
        s.check_eq("s2 lockedVarIdx cleared",
                   rig.engine.chain().stages.at(1).lockedVarIdx, -1);
        results.push_back(s.finalize());
    }

    // -------------------------------------------------------------------
    // 9. failed snapshot -> placeholder removed, status Failed.
    // -------------------------------------------------------------------
    {
        Scenario s(QStringLiteral("09_failed_snapshot_drops_placeholder"));
        TestRig rig(tempRoot());
        rig.engine.newChain(EntryKind::DescribedText);
        const QString stageId = rig.engine.addStage(StageKind::T2I);
        rig.engine.regenerate(stageId);
        pumpEvents();
        const QString eid = rig.submittedPayloads.front()
            .value(QStringLiteral("queue_item_id")).toString();

        pushSnapshot(rig.queue, {makeSnapshotItem(eid, "failed")});
        pumpEvents();

        const Stage &st = rig.engine.chain().stages.first();
        s.check_eq("status Failed", st.status, StageStatus::Failed);
        s.check_eq("placeholder variation removed", st.variations.size(), 0);
        results.push_back(s.finalize());
    }

    // -------------------------------------------------------------------
    // 10. ChainStore round-trip — save then load via a fresh store.
    // -------------------------------------------------------------------
    {
        Scenario s(QStringLiteral("10_chain_store_round_trip"));
        TestRig rig(tempRoot());
        rig.engine.newChain(EntryKind::DescribedText);
        const QString stageId = rig.engine.addStage(StageKind::T2I);
        rig.engine.regenerate(stageId);
        pumpEvents();
        const QString eid = rig.submittedPayloads.front()
            .value(QStringLiteral("queue_item_id")).toString();
        pushSnapshot(rig.queue, {makeSnapshotItem(eid, "completed",
            QStringLiteral("/tmp/persisted.png"))});
        pumpEvents();

        const QString chainId = rig.engine.chain().id;
        const int variationsBefore = rig.engine.chain().stages.first().variations.size();

        // Build a fresh, unrelated store and load. Persistence is by
        // file, so a separate ChainStore instance with the same temp
        // root reaches the same on-disk artifact.
        ChainStore freshStore(tempRoot());
        const auto loaded = freshStore.load(chainId);
        s.check_true("load returned a chain", loaded.has_value());
        if (loaded.has_value())
        {
            s.check_eq("loaded chain id", loaded->id, chainId);
            s.check_eq("loaded stage count", loaded->stages.size(), 1);
            s.check_eq("loaded variation count",
                       loaded->stages.first().variations.size(),
                       variationsBefore);
            s.check_eq("loaded variation output",
                       loaded->stages.first().variations.first().outputPath,
                       QStringLiteral("/tmp/persisted.png"));
        }
        results.push_back(s.finalize());
    }

    // -------------------------------------------------------------------
    // Report
    // -------------------------------------------------------------------
    int failures = 0;
    for (const ScenarioResult &r : results)
    {
        if (r.ok)
        {
            out << "  PASS  " << r.name << Qt::endl;
        }
        else
        {
            out << "  FAIL  " << r.name << " -- " << r.firstFailure << Qt::endl;
            ++failures;
        }
    }
    out << "===" << Qt::endl;
    out << "Scenarios: " << results.size()
        << " | Passed: " << (results.size() - failures)
        << " | Failed: " << failures << Qt::endl;
    out.flush();

    cleanTempRoot();
    return failures;
}

} // namespace spellvision::chain
