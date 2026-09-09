// The bottom bar's busy/progress half, asserted as what is ON SCREEN.
//
// syncBottomTelemetry kept seven dynamic properties of client-invented state and had no test.
// Its flash bug was found by eye. Wave 3 writes those properties, so the guards come first.
//
// Constructing MainWindow to tick them also runs the 35 s venv probe (wave 3 task 8), so the
// state machine lives on TelemetryPresenter as a pure function. The labels below are the same
// strings MainWindow writes onto bottomReadyLabel_ / bottomStateLabel_ / the progress bar.

#include <QtTest>

#include <QCoreApplication>
#include <QLabel>
#include <QPushButton>
#include <QSettings>

#include "ImageGenerationPage.h"
#include "shell/TelemetryPresenter.h"
#include "workers/WorkerSubmissionPolicy.h"

using spellvision::shell::TelemetryJob;
using spellvision::shell::TelemetryLatch;
using spellvision::shell::TelemetryPresenter;
using spellvision::shell::TelemetryProgressView;
using spellvision::workers::WorkerSubmissionPolicy;

namespace
{

TelemetryLatch submittedImageLatch()
{
    TelemetryLatch latch;
    latch.explicitBusy = true;
    latch.busyMode = QStringLiteral("t2i");
    latch.currentMode = QStringLiteral("t2i");
    latch.busyState = QStringLiteral("Submitting");
    latch.completedRowsAtSubmit = 3;
    latch.sawActive = false;
    latch.completionPulse = false;
    latch.phaseRank = 1;
    latch.progressTarget = 3;
    return latch;
}

void assertOnScreen(const TelemetryProgressView &view,
                    const QString &ready,
                    const QString &state,
                    int progress)
{
    QLabel readyLabel;
    QLabel stateLabel;
    QLabel progressLabel;
    readyLabel.setText(view.readyText);
    stateLabel.setText(view.stateText);
    progressLabel.setText(view.indeterminate ? QString() : QStringLiteral("%1%").arg(view.progress));
    QCOMPARE(readyLabel.text(), ready);
    QCOMPARE(stateLabel.text(), state);
    if (!view.indeterminate)
        QCOMPARE(progressLabel.text(), QStringLiteral("%1%").arg(progress));
}

QPushButton *generateButtonOn(ImageGenerationPage &page)
{
    for (QPushButton *button : page.findChildren<QPushButton *>())
    {
        if (button->objectName() == QStringLiteral("PrimaryActionButton")
            && button->text().contains(QStringLiteral("Generate")))
            return button;
    }
    return nullptr;
}

} // namespace

class BottomTelemetryTest : public QObject
{
    Q_OBJECT

private slots:
    void the_rank_ratchet_cannot_be_walked_back();
    void an_empty_snapshot_after_submit_does_not_complete();
    void completed_rows_from_another_mode_do_not_trip_completion();
    void the_completion_pulse_holds_completed_then_returns_to_idle();
    void the_pulse_duration_is_the_product_number();
    void real_step_progress_is_not_lifted_to_the_floor();
    void a_successful_enqueue_ack_does_not_clear_busy();
    void a_failed_enqueue_ack_clears_busy();
    void generate_stays_disabled_across_a_successful_ack();
};

void BottomTelemetryTest::the_rank_ratchet_cannot_be_walked_back()
{
    TelemetryLatch latch = submittedImageLatch();
    latch.busyState = QStringLiteral("Queued"); // what the walked-back snapshot would claim
    latch.phaseRank = 3;
    latch.progressTarget = 12;
    latch.sawActive = true;

    TelemetryJob job;
    job.hasActiveItem = true;
    job.activeState = QueueItemState::Queued; // a snapshot that walked back
    job.activeProgress = 4;
    job.activeSteps = 20;

    const TelemetryProgressView view =
        TelemetryPresenter::progressView(true, 3, job, latch);

    assertOnScreen(view, QStringLiteral("Busy"), QStringLiteral("Running"), 12);
    QCOMPARE(view.phaseRank, 3);
}

void BottomTelemetryTest::an_empty_snapshot_after_submit_does_not_complete()
{
    // Submit latches busy; the first poll (0–1800 ms) often has no active row yet and the
    // completed-row count is unchanged. Completing here is the flash bug.
    const TelemetryLatch latch = submittedImageLatch();
    TelemetryJob job; // empty snapshot

    const TelemetryProgressView view =
        TelemetryPresenter::progressView(true, 3, job, latch);

    QVERIFY(!view.completedOutputObserved);
    QVERIFY(!view.startCompletionPulse);
    assertOnScreen(view, QStringLiteral("Busy"), QStringLiteral("Submitting"), 3);
}

void BottomTelemetryTest::completed_rows_from_another_mode_do_not_trip_completion()
{
    TelemetryLatch latch = submittedImageLatch();
    latch.currentMode = QStringLiteral("i2i"); // proxy-filtered row count belongs to i2i now
    TelemetryJob job;

    const TelemetryProgressView view =
        TelemetryPresenter::progressView(true, 99, job, latch);

    QVERIFY(!view.completedOutputObserved);
    QCOMPARE(view.stateText, QStringLiteral("Idle"));
    QCOMPARE(view.readyText, QStringLiteral("Ready"));
}

void BottomTelemetryTest::the_completion_pulse_holds_completed_then_returns_to_idle()
{
    TelemetryLatch latch = submittedImageLatch();
    latch.sawActive = true;
    TelemetryJob job;

    // A new completed row after we actually saw the job run.
    TelemetryProgressView view =
        TelemetryPresenter::progressView(true, 4, job, latch);
    QVERIFY(view.completedOutputObserved);
    QVERIFY(view.startCompletionPulse);
    assertOnScreen(view, QStringLiteral("Busy"), QStringLiteral("Completed"), 100);

    latch.completionPulse = true;
    latch.explicitBusy = false;
    view = TelemetryPresenter::progressView(true, 4, job, latch);
    QVERIFY(!view.startCompletionPulse);
    assertOnScreen(view, QStringLiteral("Busy"), QStringLiteral("Completed"), 100);

    latch.completionPulse = false;
    latch.sawActive = false;
    latch.phaseRank = 0;
    latch.progressTarget = 0;
    view = TelemetryPresenter::progressView(true, 4, job, latch);
    assertOnScreen(view, QStringLiteral("Ready"), QStringLiteral("Idle"), 0);
}

void BottomTelemetryTest::the_pulse_duration_is_the_product_number()
{
    // 900 is the number in the wave-3 spec, written here, not read back from itself via a
    // second alias. MainWindow must use this constant for the QTimer; a literal 900 elsewhere
    // is a second copy.
    QCOMPARE(TelemetryPresenter::kCompletionPulseMs, 900);
}

void BottomTelemetryTest::real_step_progress_is_not_lifted_to_the_floor()
{
    // 1 of 20 steps is 5 %. The Running floor is 12 %. A bar that shows 12 is inventing.
    TelemetryLatch latch = submittedImageLatch();
    latch.busyState = QStringLiteral("Running");
    latch.phaseRank = 3;
    latch.progressTarget = 0;
    latch.sawActive = true;

    TelemetryJob job;
    job.hasActiveItem = true;
    job.activeState = QueueItemState::Running;
    job.activeProgress = 5;
    job.activeSteps = 20;

    const TelemetryProgressView view =
        TelemetryPresenter::progressView(true, 3, job, latch);
    assertOnScreen(view, QStringLiteral("Busy"), QStringLiteral("Running"), 5);
}

void BottomTelemetryTest::a_successful_enqueue_ack_does_not_clear_busy()
{
    QVERIFY2(!WorkerSubmissionPolicy::clearBusyOnEnqueueAck(true, true),
             "a successful enqueue still has a job; Generate must stay disabled");
}

void BottomTelemetryTest::a_failed_enqueue_ack_clears_busy()
{
    QVERIFY(WorkerSubmissionPolicy::clearBusyOnEnqueueAck(false, false));
    QVERIFY(WorkerSubmissionPolicy::clearBusyOnEnqueueAck(true, false));
    QVERIFY(WorkerSubmissionPolicy::clearBusyOnEnqueueAck(false, true));
}

void BottomTelemetryTest::generate_stays_disabled_across_a_successful_ack()
{
    QCoreApplication::setOrganizationName(QStringLiteral("DarkDuckTest"));
    QCoreApplication::setApplicationName(QStringLiteral("SpellVisionGenerateBusyTest"));
    QSettings settings;
    settings.clear();
    settings.sync();

    ImageGenerationPage page(ImageGenerationPage::Mode::TextToImage);
    QPushButton *generate = generateButtonOn(page);
    QVERIFY2(generate, "the Generate button is PrimaryActionButton containing \"Generate\"");

    page.setBusy(true, QStringLiteral("Submitting generation…"));
    QVERIFY2(!generate->isEnabled(), "setBusy(true) hard-disables Generate");

    if (WorkerSubmissionPolicy::clearBusyOnEnqueueAck(true, true))
        page.setBusy(false, QString());
    QVERIFY2(!generate->isEnabled(), "a successful ack must not re-enable Generate");

    page.setBusy(false, QStringLiteral("Ready"));
    QVERIFY2(generate->isEnabled(), "completion re-enables Generate");
}

QTEST_MAIN(BottomTelemetryTest)
#include "test_bottom_telemetry.moc"
