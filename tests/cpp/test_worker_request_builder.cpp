// 320 lines that decide what the worker receives, and no test could reach them.
//
// buildWorkerGenerationRequest and buildWorkflowLaunchRequest were private members of MainWindow.
// They touch no MainWindow state -- they are functions of their arguments that happened to be
// declared inside a QMainWindow -- but being members meant the only way to exercise them was to
// launch the GUI and render something. Every default in here (steps 28, cfg 7.0, 81 frames,
// 16 fps), every key that carries the model, and the five-way command stamping that routes a
// studio job were unasserted.
//
// The extraction is what makes this file possible; this file is why the extraction was worth
// doing. The bodies moved verbatim -- only the qualifier and the project-root parameter changed --
// so anything asserted here describes what already shipped, not a rewrite.

#include <QtTest>

#include <QDir>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonObject>
#include <QTemporaryDir>

#include "workers/WorkerRequestBuilder.h"

using spellvision::workers::buildWorkerGenerationRequest;
using spellvision::workers::buildWorkflowLaunchRequest;
using spellvision::workers::workerTaskCommandForMode;

class TestWorkerRequestBuilder : public QObject
{
    Q_OBJECT

private:
    QTemporaryDir tmp_;

    QJsonObject minimalPayload(const QString &folder) const
    {
        QJsonObject p;
        p.insert(QStringLiteral("prompt"), QStringLiteral("a knight"));
        p.insert(QStringLiteral("output_folder"), folder);
        p.insert(QStringLiteral("output_prefix"), QStringLiteral("test"));
        return p;
    }

private slots:
    void initTestCase();

    void theModeMapsToATaskCommand_data();
    void theModeMapsToATaskCommand();
    void anUnknownModeIsEmptyNotAGuess();

    void theDefaultsAreWhatShipped();
    void aStatedValueBeatsTheDefault();
    void theSeedSurvivesBeyondThirtyTwoBits();

    void imageModesCarryNoFrameCount();
    void videoModesCarryFramesAndFps();
    void framesAndNumFramesAgree();

    void aStudioCommandIsStampedFiveWays();
    void anOrdinaryCommandIsNot();

    void theChainQueueIdIsMirroredThreeWays();
    void noChainIdMeansNoChainKeys();

    void aLoraArrayIsNeverDropped();
    void aDisabledLoraIsNotPromoted();

    void theOutputFolderIsCreated();
    void aNotSetFolderIsTreatedAsAbsent();

    void theWorkflowLaunchTakesItsComfyRootFromTheCaller();
    void theWorkflowSlugIsFilesystemSafe();
};

void TestWorkerRequestBuilder::initTestCase()
{
    QVERIFY(tmp_.isValid());
}

// --- the mode table ---------------------------------------------------------------------------

void TestWorkerRequestBuilder::theModeMapsToATaskCommand_data()
{
    QTest::addColumn<QString>("mode");
    QTest::newRow("t2i") << QStringLiteral("t2i");
    QTest::newRow("i2i") << QStringLiteral("i2i");
    QTest::newRow("t2v") << QStringLiteral("t2v");
    QTest::newRow("i2v") << QStringLiteral("i2v");
}

void TestWorkerRequestBuilder::theModeMapsToATaskCommand()
{
    QFETCH(QString, mode);
    QCOMPARE(workerTaskCommandForMode(mode), mode);
}

void TestWorkerRequestBuilder::anUnknownModeIsEmptyNotAGuess()
{
    // Callers distinguish "not a generation mode" by the empty string. A fallback to t2i here would
    // route a Character Studio or Flows request into the image path silently.
    QCOMPARE(workerTaskCommandForMode(QStringLiteral("character")), QString());
    QCOMPARE(workerTaskCommandForMode(QString()), QString());
    QCOMPARE(workerTaskCommandForMode(QStringLiteral("T2I")), QString());
}

// --- the defaults -----------------------------------------------------------------------------

void TestWorkerRequestBuilder::theDefaultsAreWhatShipped()
{
    // Pinned, not endorsed. These are the values a payload with no sampling block produces today,
    // and they were previously asserted nowhere -- so a change to any of them was invisible.
    const QJsonObject r = buildWorkerGenerationRequest(
        QStringLiteral("t2i"), minimalPayload(tmp_.path()), tmp_.path());
    QCOMPARE(r.value(QStringLiteral("steps")).toInt(), 28);
    QCOMPARE(r.value(QStringLiteral("cfg")).toDouble(), 7.0);
    QCOMPARE(r.value(QStringLiteral("width")).toInt(), 1024);
    QCOMPARE(r.value(QStringLiteral("height")).toInt(), 1024);
    QCOMPARE(r.value(QStringLiteral("command")).toString(), QStringLiteral("enqueue"));
    QCOMPARE(r.value(QStringLiteral("task_command")).toString(), QStringLiteral("t2i"));
}

void TestWorkerRequestBuilder::aStatedValueBeatsTheDefault()
{
    QJsonObject p = minimalPayload(tmp_.path());
    p.insert(QStringLiteral("steps"), 8);
    p.insert(QStringLiteral("cfg"), 1.0);
    const QJsonObject r = buildWorkerGenerationRequest(QStringLiteral("t2i"), p, tmp_.path());
    QCOMPARE(r.value(QStringLiteral("steps")).toInt(), 8);
    QCOMPARE(r.value(QStringLiteral("cfg")).toDouble(), 1.0);
}

void TestWorkerRequestBuilder::theSeedSurvivesBeyondThirtyTwoBits()
{
    // The seed goes through toVariant().toLongLong() rather than toInt(), and it matters: the
    // cockpit spin box reaches past 2^31 and a 32-bit read would silently wrap a stated seed into
    // a different render. Same class of defect as the seed box that could not express a value the
    // worker had just been taught to honour.
    QJsonObject p = minimalPayload(tmp_.path());
    const qint64 big = Q_INT64_C(4294967296);
    p.insert(QStringLiteral("seed"), big);
    const QJsonObject r = buildWorkerGenerationRequest(QStringLiteral("t2i"), p, tmp_.path());
    QCOMPARE(r.value(QStringLiteral("seed")).toVariant().toLongLong(), big);
}

// --- image against video ----------------------------------------------------------------------

void TestWorkerRequestBuilder::imageModesCarryNoFrameCount()
{
    const QJsonObject r = buildWorkerGenerationRequest(
        QStringLiteral("t2i"), minimalPayload(tmp_.path()), tmp_.path());
    QVERIFY(!r.contains(QStringLiteral("frames")));
    QVERIFY(!r.contains(QStringLiteral("fps")));
    QVERIFY(!r.contains(QStringLiteral("media_type")));
}

void TestWorkerRequestBuilder::videoModesCarryFramesAndFps()
{
    const QJsonObject r = buildWorkerGenerationRequest(
        QStringLiteral("t2v"), minimalPayload(tmp_.path()), tmp_.path());
    QCOMPARE(r.value(QStringLiteral("frames")).toInt(), 81);
    QCOMPARE(r.value(QStringLiteral("fps")).toInt(), 16);
    QCOMPARE(r.value(QStringLiteral("media_type")).toString(), QStringLiteral("video"));
    // No workflow binding, so the native video route is declared.
    QCOMPARE(r.value(QStringLiteral("backend_kind")).toString(), QStringLiteral("native_video"));
}

void TestWorkerRequestBuilder::framesAndNumFramesAgree()
{
    // Both keys ship, each defaulting to the other. A payload that states one must not leave the
    // other at 81, or the worker reads whichever it happens to prefer and gets a different length.
    QJsonObject p = minimalPayload(tmp_.path());
    p.insert(QStringLiteral("num_frames"), 49);
    const QJsonObject r = buildWorkerGenerationRequest(QStringLiteral("t2v"), p, tmp_.path());
    QCOMPARE(r.value(QStringLiteral("num_frames")).toInt(), 49);
    QCOMPARE(r.value(QStringLiteral("frames")).toInt(), 49);
}

// --- one question, five answers -----------------------------------------------------------------

void TestWorkerRequestBuilder::aStudioCommandIsStampedFiveWays()
{
    // Documented in the source as belt-and-braces, and pinned here rather than tidied: the worker
    // dispatch reads one of these and the audit has not established which, so removing four would
    // be a guess. What the test buys is that they can never DISAGREE, which is the failure that
    // would be hard to see.
    QJsonObject p = minimalPayload(tmp_.path());
    p.insert(QStringLiteral("task_command"), QStringLiteral("look_complete"));
    const QJsonObject r = buildWorkerGenerationRequest(QStringLiteral("character"), p, tmp_.path());
    for (const auto &key : {"task_command", "execution_command", "worker_command",
                            "dispatch_command", "task_type"})
        QCOMPARE(r.value(QLatin1String(key)).toString(), QStringLiteral("look_complete"));
}

void TestWorkerRequestBuilder::anOrdinaryCommandIsNot()
{
    const QJsonObject r = buildWorkerGenerationRequest(
        QStringLiteral("t2i"), minimalPayload(tmp_.path()), tmp_.path());
    QVERIFY(!r.contains(QStringLiteral("execution_command")));
    QCOMPARE(r.value(QStringLiteral("task_type")).toString(), QStringLiteral("t2i"));
}

// --- chain correlation --------------------------------------------------------------------------

void TestWorkerRequestBuilder::theChainQueueIdIsMirroredThreeWays()
{
    QJsonObject p = minimalPayload(tmp_.path());
    p.insert(QStringLiteral("queue_item_id"), QStringLiteral("abc-123"));
    const QJsonObject r = buildWorkerGenerationRequest(QStringLiteral("t2i"), p, tmp_.path());
    QCOMPARE(r.value(QStringLiteral("queue_item_id")).toString(), QStringLiteral("abc-123"));
    QCOMPARE(r.value(QStringLiteral("worker_job_id")).toString(), QStringLiteral("abc-123"));
    QCOMPARE(r.value(QStringLiteral("source_job_id")).toString(), QStringLiteral("abc-123"));
}

void TestWorkerRequestBuilder::noChainIdMeansNoChainKeys()
{
    // An empty id must not ship as an empty string: ChainCompletionWatcher matches on first hit, and
    // an empty value in the first field it checks would match the wrong item.
    const QJsonObject r = buildWorkerGenerationRequest(
        QStringLiteral("t2i"), minimalPayload(tmp_.path()), tmp_.path());
    QVERIFY(!r.contains(QStringLiteral("queue_item_id")));
    QVERIFY(!r.contains(QStringLiteral("worker_job_id")));
}

// --- LoRA -------------------------------------------------------------------------------------

void TestWorkerRequestBuilder::aLoraArrayIsNeverDropped()
{
    QJsonObject lora;
    lora.insert(QStringLiteral("path"), QStringLiteral("loras/style.safetensors"));
    lora.insert(QStringLiteral("weight"), 0.8);
    QJsonObject p = minimalPayload(tmp_.path());
    p.insert(QStringLiteral("loras"), QJsonArray{lora});

    const QJsonObject r = buildWorkerGenerationRequest(QStringLiteral("t2i"), p, tmp_.path());
    QCOMPARE(r.value(QStringLiteral("loras")).toArray().size(), 1);
    // The first enabled entry is also promoted to the scalar key older routes read.
    QCOMPARE(r.value(QStringLiteral("lora")).toString(), QStringLiteral("loras/style.safetensors"));
    QCOMPARE(r.value(QStringLiteral("lora_scale")).toDouble(), 0.8);
}

void TestWorkerRequestBuilder::aDisabledLoraIsNotPromoted()
{
    QJsonObject off;
    off.insert(QStringLiteral("path"), QStringLiteral("loras/off.safetensors"));
    off.insert(QStringLiteral("enabled"), false);
    QJsonObject on;
    on.insert(QStringLiteral("path"), QStringLiteral("loras/on.safetensors"));

    QJsonObject p = minimalPayload(tmp_.path());
    p.insert(QStringLiteral("loras"), QJsonArray{off, on});
    const QJsonObject r = buildWorkerGenerationRequest(QStringLiteral("t2i"), p, tmp_.path());
    QCOMPARE(r.value(QStringLiteral("lora")).toString(), QStringLiteral("loras/on.safetensors"));
}

// --- the side effects the name does not advertise -----------------------------------------------

void TestWorkerRequestBuilder::theOutputFolderIsCreated()
{
    // "build" reads as pure and this is not. Asserted so the behaviour is on record: a caller that
    // builds a request in order to inspect it will have touched the disk.
    const QString folder = QDir(tmp_.path()).filePath(QStringLiteral("made/by/the/builder"));
    QVERIFY(!QDir(folder).exists());
    buildWorkerGenerationRequest(QStringLiteral("t2i"), minimalPayload(folder), tmp_.path());
    QVERIFY(QDir(folder).exists());
}

void TestWorkerRequestBuilder::aNotSetFolderIsTreatedAsAbsent()
{
    // The cockpit shows "Not set" as placeholder text and it reaches the payload as a value. Taken
    // literally it would create a directory called "Not set".
    QJsonObject p = minimalPayload(QStringLiteral("Not set"));
    const QJsonObject r = buildWorkerGenerationRequest(QStringLiteral("t2i"), p, tmp_.path());
    QVERIFY(!r.value(QStringLiteral("output")).toString().contains(QStringLiteral("Not set")));
}

// --- the workflow launch -------------------------------------------------------------------------

void TestWorkerRequestBuilder::theWorkflowLaunchTakesItsComfyRootFromTheCaller()
{
    // The root arrives as a parameter rather than being resolved here, so this function cannot
    // become a sixth resolver -- the defect the previous commit removed five copies of.
    QJsonObject profile;
    profile.insert(QStringLiteral("profile_name"), QStringLiteral("My Workflow"));
    profile.insert(QStringLiteral("task_command"), QStringLiteral("t2i"));
    const QJsonObject r = buildWorkflowLaunchRequest(
        profile, QString(), QString(), QString(), tmp_.path(),
        QStringLiteral("C:/sv_comfynext/ComfyUI"));
    QCOMPARE(r.value(QStringLiteral("comfy_root")).toString(),
             QStringLiteral("C:/sv_comfynext/ComfyUI"));
    QCOMPARE(r.value(QStringLiteral("task_command")).toString(), QStringLiteral("comfy_workflow"));
    QCOMPARE(r.value(QStringLiteral("task_type")).toString(), QStringLiteral("t2i"));
}

void TestWorkerRequestBuilder::theWorkflowSlugIsFilesystemSafe()
{
    // The slug becomes a filename. A profile named from an imported workflow can carry anything.
    QJsonObject profile;
    profile.insert(QStringLiteral("profile_name"), QStringLiteral("Flux / SDXL: v2.1 (final!)"));
    profile.insert(QStringLiteral("task_command"), QStringLiteral("t2i"));
    const QJsonObject r = buildWorkflowLaunchRequest(
        profile, QString(), QString(), QString(), tmp_.path(), QString());
    const QString name = QFileInfo(r.value(QStringLiteral("output")).toString()).fileName();
    const QString forbidden = QStringLiteral("/\\:*?\"<>|");
    for (const QChar bad : forbidden)
        QVERIFY2(!name.contains(bad), qPrintable(name));
    QVERIFY2(name.startsWith(QStringLiteral("flux-sdxl-v2-1-final")), qPrintable(name));
}

QTEST_MAIN(TestWorkerRequestBuilder)
#include "test_worker_request_builder.moc"
