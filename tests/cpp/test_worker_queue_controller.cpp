// Idle polling used to cost ~8× the busy poll because a 13 ms LTX history request
// rode every idle tick. Busy should poll faster; idle should poll slower; the LTX
// request must not appear on a stretch of idle ticks.

#include <QtTest>

#include <QJsonArray>
#include <QJsonObject>
#include <QStringList>

#include "QueueManager.h"
#include "workers/WorkerQueueController.h"

using spellvision::workers::WorkerQueueController;

namespace
{

QJsonObject snapshotWithRunningJob()
{
    QJsonObject progress;
    progress.insert(QStringLiteral("current"), 1);
    progress.insert(QStringLiteral("total"), 20);
    progress.insert(QStringLiteral("message"), QStringLiteral("running"));

    QJsonObject item;
    item.insert(QStringLiteral("queue_item_id"), QStringLiteral("q-run"));
    item.insert(QStringLiteral("command"), QStringLiteral("t2i"));
    item.insert(QStringLiteral("state"), QStringLiteral("running"));
    item.insert(QStringLiteral("progress"), progress);

    QJsonArray items;
    items.append(item);

    QJsonObject snap;
    snap.insert(QStringLiteral("type"), QStringLiteral("queue_snapshot"));
    snap.insert(QStringLiteral("ok"), true);
    snap.insert(QStringLiteral("active_queue_item_id"), QStringLiteral("q-run"));
    snap.insert(QStringLiteral("items"), items);
    return snap;
}

QJsonObject emptySnapshot()
{
    QJsonObject snap;
    snap.insert(QStringLiteral("type"), QStringLiteral("queue_snapshot"));
    snap.insert(QStringLiteral("ok"), true);
    snap.insert(QStringLiteral("items"), QJsonArray());
    return snap;
}

} // namespace

class WorkerQueueControllerTest : public QObject
{
    Q_OBJECT

private slots:
    void five_idle_polls_never_send_the_ltx_contract();
    void an_active_job_polls_faster_than_idle();
};

void WorkerQueueControllerTest::five_idle_polls_never_send_the_ltx_contract()
{
    QueueManager queue;
    WorkerQueueController controller;
    QStringList commands;
    int queueStatusCount = 0;

    WorkerQueueController::Bindings bindings;
    bindings.queueManager = &queue;
    bindings.sendRequestAsync = [&](const QJsonObject &request,
                                    WorkerQueueController::Bindings::RequestCompletion completion) {
        const QString command = request.value(QStringLiteral("command")).toString();
        commands.append(command);
        if (command == QStringLiteral("queue_status"))
            ++queueStatusCount;
        if (completion)
            completion(emptySnapshot(), QString(), true);
    };
    controller.bind(bindings);

    for (int i = 0; i < 5; ++i)
        QVERIFY(controller.pollOnce());

    QCOMPARE(queueStatusCount, 5);
    QVERIFY2(!commands.contains(QStringLiteral("ltx_ui_queue_history_contract")),
             "the LTX contract must not ride idle ticks");
    QCOMPARE(controller.pollIntervalMs(), WorkerQueueController::kIdlePollIntervalMs);
}

void WorkerQueueControllerTest::an_active_job_polls_faster_than_idle()
{
    QueueManager queue;
    WorkerQueueController controller;
    QStringList commands;

    WorkerQueueController::Bindings bindings;
    bindings.queueManager = &queue;
    bindings.sendRequestAsync = [&](const QJsonObject &request,
                                    WorkerQueueController::Bindings::RequestCompletion completion) {
        commands.append(request.value(QStringLiteral("command")).toString());
        if (completion)
            completion(snapshotWithRunningJob(), QString(), true);
    };
    controller.bind(bindings);

    QVERIFY(controller.pollOnce());
    QVERIFY(controller.pollIntervalMs() < WorkerQueueController::kIdlePollIntervalMs);
    QCOMPARE(controller.pollIntervalMs(), WorkerQueueController::kActivePollIntervalMs);
    QVERIFY2(!commands.contains(QStringLiteral("ltx_ui_queue_history_contract")),
             "a live job must not be overwritten by the LTX idle snapshot");
}

QTEST_MAIN(WorkerQueueControllerTest)
#include "test_worker_queue_controller.moc"
