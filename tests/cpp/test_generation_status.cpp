// The last hop of "an upscale either happens or is reported".
//
// The worker's refusal is written to `progress.message`. That is the field the cockpit shows while
// a job is busy -- and the field the NEXT status overwrites. A run that says "upscale skipped"
// mid-flight and then finishes with "Generation complete" beside a normal-looking image has told
// the user nothing they can act on.
//
// So the worker now leaves the note as the job's terminal message, and this test pins what the UI
// does with it: on a successful terminal update the message becomes the CAPTION beside the image
// the user is looking at, rather than being replaced by a cheerful default.
//
// The controller had no test at all, which is why "the user is told" was an assumption rather than
// a property.

#include <QtTest>

#include "generation/GenerationStatusController.h"

using spellvision::generation::GenerationStatusController;

namespace
{

struct Observed
{
    bool busyCalled = false;
    bool busy = false;
    QString busyMessage;

    bool routed = false;
    QString routedPath;
    QString routedCaption;

    bool problemShown = false;
    QString problemText;

    GenerationStatusController::Bindings bindings()
    {
        GenerationStatusController::Bindings b;
        b.setBusy = [this](bool isBusy, const QString &message) {
            busyCalled = true;
            busy = isBusy;
            busyMessage = message;
        };
        b.routeOutput = [this](const QString &path, const QString &caption) {
            routed = true;
            routedPath = path;
            routedCaption = caption;
        };
        b.showProblem = [this](const QString &message) {
            problemShown = true;
            problemText = message;
        };
        return b;
    }
};

QJsonObject terminalUpdate(const QString &message)
{
    QJsonObject progress;
    progress.insert(QStringLiteral("current"), 20);
    progress.insert(QStringLiteral("total"), 20);
    if (!message.isEmpty())
        progress.insert(QStringLiteral("message"), message);

    QJsonObject payload;
    payload.insert(QStringLiteral("type"), QStringLiteral("job_update"));
    payload.insert(QStringLiteral("ok"), true);
    payload.insert(QStringLiteral("state"), QStringLiteral("completed"));
    payload.insert(QStringLiteral("job_id"), QStringLiteral("job-1"));
    payload.insert(QStringLiteral("output"), QStringLiteral("C:/out/render.png"));
    payload.insert(QStringLiteral("progress"), progress);
    return payload;
}

} // namespace

class GenerationStatusTest : public QObject
{
    Q_OBJECT

private slots:
    void aTerminalNoteBecomesTheCaption();
    void aSilentRunGetsTheDefaultCaption();
    void aMidRunStatusIsShownWhileBusy();
    void aFailureIsAProblemNotACaption();
};

void GenerationStatusTest::aTerminalNoteBecomesTheCaption()
{
    Observed seen;
    const QString note = QStringLiteral(
        "Upscale skipped: this build cannot run a model upscale on a diffusers checkpoint. "
        "The image is unchanged.");

    GenerationStatusController::applyWorkerPayload(terminalUpdate(note), seen.bindings());

    QVERIFY(seen.routed);
    QCOMPARE(seen.routedPath, QStringLiteral("C:/out/render.png"));
    QCOMPARE(seen.routedCaption, note);
    QVERIFY2(!seen.routedCaption.contains(QStringLiteral("Generation complete")),
             "a partial success must not be captioned as a clean one");
    QVERIFY(seen.busyCalled && !seen.busy);
}

void GenerationStatusTest::aSilentRunGetsTheDefaultCaption()
{
    Observed seen;
    GenerationStatusController::applyWorkerPayload(terminalUpdate(QString()), seen.bindings());

    QVERIFY(seen.routed);
    QCOMPARE(seen.routedCaption, QStringLiteral("Generation complete"));
}

void GenerationStatusTest::aMidRunStatusIsShownWhileBusy()
{
    Observed seen;
    QJsonObject payload;
    payload.insert(QStringLiteral("type"), QStringLiteral("status"));
    payload.insert(QStringLiteral("message"), QStringLiteral("upscaling x2 (model)"));

    GenerationStatusController::applyWorkerPayload(payload, seen.bindings());

    QVERIFY(seen.busyCalled);
    QVERIFY(seen.busy);
    QCOMPARE(seen.busyMessage, QStringLiteral("upscaling x2 (model)"));
    QVERIFY2(!seen.routed, "a status is not an output");
}

void GenerationStatusTest::aFailureIsAProblemNotACaption()
{
    Observed seen;
    QJsonObject payload;
    payload.insert(QStringLiteral("type"), QStringLiteral("job_update"));
    payload.insert(QStringLiteral("ok"), false);
    payload.insert(QStringLiteral("state"), QStringLiteral("failed"));
    payload.insert(QStringLiteral("error"), QStringLiteral("Upscale model 'x.pth' is not one ComfyUI offers."));

    GenerationStatusController::applyWorkerPayload(payload, seen.bindings());

    QVERIFY(seen.problemShown);
    QVERIFY(seen.problemText.contains(QStringLiteral("not one ComfyUI offers")));
    QVERIFY2(!seen.routed, "a failed job routes no output");
}

QTEST_MAIN(GenerationStatusTest)
#include "test_generation_status.moc"
