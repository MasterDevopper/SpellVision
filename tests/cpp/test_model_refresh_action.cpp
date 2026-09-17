// W5 Task 4 -- "Refresh metadata", from inside the app.
//
// The sentence W2 had to delete from the cockpit caption was "run Refresh metadata on the Models
// page", and it was deleted because the control did not exist: nothing in `qt_ui/` started a
// `model_intel_refresh` at all. This file holds the four properties that make restoring that
// sentence honest.
//
// **Background, because the job is 79 minutes.** The owner's library is 759 files and 2.09 TB. A
// foreground refresh holds the connection for the whole pass, which is indistinguishable from a
// hung worker. The request says `background: true` and the surface watches `model_intel_progress`.
//
// **Cancel is addressed by job id**, which arrives in the started event. A cancel offered before
// the id lands has nothing to name, so the controller refuses to offer one -- and a worker that
// answers `ok: false` (no such job) is repeated verbatim rather than swallowed, because a caller
// told "cancelled" for the wrong id watches the job carry on and concludes cancel is broken.
//
// **No API key.** Verified against the live API: CivitAI's by-hash reads are public and the
// anonymous and keyed replies were identical. A key buys downloads and mature previews, neither of
// which this action performs. So a refresh must START with no credential configured, and the
// request must not carry a key field at all -- an empty key on the wire reads to the worker like a
// caller that thinks it has one.
//
// **One model means one file.** `RefreshJob` has supported a narrow `files` list since it was
// written and nothing passed one until W5. Dropping it does not FAIL -- it succeeds, slowly, over
// every root. That is the shape of defect a green suite hides, so it gets a case of its own.
//
// No socket: the controller builds requests and consumes replies, and these cases play the worker.

#include <QtTest>

#include <QJsonArray>
#include <QJsonObject>
#include <QSignalSpy>
#include <QStringList>

#include "assets/ModelRefreshController.h"

using spellvision::assets::ModelRefreshController;

namespace
{
QJsonObject firstRequest(const QSignalSpy &spy, int index = 0)
{
    if (spy.count() <= index)
        return QJsonObject();
    return spy.at(index).at(0).toJsonObject();
}

QStringList stringsAt(const QJsonObject &object, const char *key)
{
    QStringList out;
    for (const QJsonValue &value : object.value(QString::fromUtf8(key)).toArray())
        out << value.toString();
    return out;
}

QJsonObject started(const QString &jobId)
{
    return QJsonObject{{QStringLiteral("type"), QStringLiteral("model_intel_refresh_started")},
                       {QStringLiteral("ok"), true},
                       {QStringLiteral("job_id"), jobId}};
}

QJsonObject progress(const QString &jobId, int current, int total, const QString &message)
{
    return QJsonObject{{QStringLiteral("type"), QStringLiteral("model_intel_progress")},
                       {QStringLiteral("ok"), true},
                       {QStringLiteral("job_id"), jobId},
                       {QStringLiteral("current"), current},
                       {QStringLiteral("total"), total},
                       {QStringLiteral("percent"), total > 0 ? (100 * current) / total : 0},
                       {QStringLiteral("message"), message}};
}

QJsonObject finished(const QString &jobId, int examined, int identified, bool cancelled)
{
    return QJsonObject{{QStringLiteral("type"), QStringLiteral("model_intel_refresh")},
                       {QStringLiteral("ok"), true},
                       {QStringLiteral("job_id"), jobId},
                       {QStringLiteral("examined"), examined},
                       {QStringLiteral("identified"), identified},
                       {QStringLiteral("no_match"), examined - identified},
                       {QStringLiteral("lookup_failed"), 0},
                       {QStringLiteral("total"), 759},
                       {QStringLiteral("cancelled"), cancelled}};
}

const QStringList kRoots = {QStringLiteral("F:/AI_ASSETS/models")};
const QString kWeight = QStringLiteral("F:/AI_ASSETS/models/loras/Detailer-KREA2.safetensors");
} // namespace

class TestModelRefreshAction : public QObject
{
    Q_OBJECT

private slots:
    // ---- the wire ----

    void a_library_refresh_asks_the_worker_to_run_it_in_the_background()
    {
        const QJsonObject request = ModelRefreshController::buildLibraryRequest(kRoots);
        QCOMPARE(request.value(QStringLiteral("command")).toString(),
                 QStringLiteral("model_intel_refresh"));
        QCOMPARE(stringsAt(request, "roots"), kRoots);
        // Not a nicety. Foreground mode replies on the open connection, and the connection would
        // have to stay open for the ~79 minutes the owner's library takes.
        QVERIFY2(request.value(QStringLiteral("background")).toBool(false),
                 "a library refresh must not hold the connection for 79 minutes");
        // A library pass is every weight under the roots; naming files here would silently narrow
        // the action the button advertises.
        QVERIFY(!request.contains(QStringLiteral("files")));
    }

    void a_per_model_refresh_names_exactly_the_one_file()
    {
        const QJsonObject request = ModelRefreshController::buildModelRequest(kRoots, kWeight);
        QCOMPARE(request.value(QStringLiteral("command")).toString(),
                 QStringLiteral("model_intel_refresh"));
        // THE case. Without `files` the worker walks every root: 759 files and 2.09 TB of hashing
        // for a button that names one model. It does not fail -- it succeeds slowly -- so nothing
        // else in the suite would notice.
        QVERIFY2(request.contains(QStringLiteral("files")),
                 "a per-model refresh with no `files` walks the whole library");
        QCOMPARE(stringsAt(request, "files"), QStringList{kWeight});
        // The worker checks `files` against `roots`, so both have to be there.
        QCOMPARE(stringsAt(request, "roots"), kRoots);
        QVERIFY(request.value(QStringLiteral("background")).toBool(false));
    }

    void a_per_model_refresh_with_no_roots_is_bounded_by_the_weights_own_folder()
    {
        const QJsonObject request = ModelRefreshController::buildModelRequest(QStringList(), kWeight);
        QCOMPARE(stringsAt(request, "roots"),
                 QStringList{QStringLiteral("F:/AI_ASSETS/models/loras")});
        QCOMPARE(stringsAt(request, "files"), QStringList{kWeight});
    }

    // ---- no key ----

    void a_refresh_starts_with_no_api_key_configured()
    {
        // Nothing here configures a credential, and nothing in the controller looks for one. This
        // is the requirement: CivitAI's by-hash reads are public, and the anonymous and keyed
        // replies were verified identical against the live API. A key buys downloads and mature
        // previews -- neither of which a refresh performs.
        ModelRefreshController controller;
        QSignalSpy sent(&controller, &ModelRefreshController::workerRequested);

        QVERIFY2(controller.startLibraryRefresh(kRoots),
                 "the refresh must not be blocked by a missing API key");
        QCOMPARE(sent.count(), 1);
        QVERIFY(controller.isRunning());

        const QJsonObject request = firstRequest(sent);
        // An empty key on the wire reads like a caller that believes it has one.
        QVERIFY(!request.contains(QStringLiteral("civitai_api_key")));
        QVERIFY(!request.contains(QStringLiteral("api_key")));

        // And the surface must not TELL the user to go and get one either.
        const QString status = controller.statusText().toLower();
        QVERIFY2(!status.contains(QStringLiteral("key")),
                 qPrintable(QStringLiteral("status asked for a key: %1").arg(controller.statusText())));
        QVERIFY(!controller.statusIsError());
    }

    void a_library_refresh_with_no_roots_says_so_instead_of_asking_for_a_key()
    {
        // The one refusal that IS real. It has to name the actual missing thing, or the user goes
        // looking for a credential problem that does not exist.
        ModelRefreshController controller;
        QSignalSpy sent(&controller, &ModelRefreshController::workerRequested);
        QVERIFY(!controller.startLibraryRefresh(QStringList()));
        QCOMPARE(sent.count(), 0);
        QVERIFY(controller.statusText().contains(QStringLiteral("folder")));
        QVERIFY(!controller.statusText().toLower().contains(QStringLiteral("key")));
    }

    // ---- progress ----

    void progress_events_move_the_row()
    {
        ModelRefreshController controller;
        QSignalSpy changed(&controller, &ModelRefreshController::stateChanged);
        QVERIFY(controller.startLibraryRefresh(kRoots));

        // Before the first progress event nothing has been counted, so the bar has no total to
        // sit at. -1 is "unknown", not 0% -- a bar at 0% claims a denominator nobody produced.
        QCOMPARE(controller.percent(), -1);

        controller.applyWorkerReply(started(QStringLiteral("mi_4f1c9a2b7de0")));
        QCOMPARE(controller.jobId(), QStringLiteral("mi_4f1c9a2b7de0"));

        const int before = changed.count();
        QVERIFY(controller.applyWorkerReply(
            progress(QStringLiteral("mi_4f1c9a2b7de0"), 24, 759, QStringLiteral("krea2_base.safetensors"))));
        QVERIFY2(changed.count() > before, "a progress event that changes nothing on screen is not progress");
        QCOMPARE(controller.current(), 24);
        QCOMPARE(controller.total(), 759);
        QCOMPARE(controller.percent(), 3);
        QVERIFY(controller.progressText().contains(QStringLiteral("24 of 759")));
        QVERIFY(controller.progressText().contains(QStringLiteral("krea2_base.safetensors")));
    }

    void a_progress_event_for_another_job_does_not_drive_this_row()
    {
        // `subscribe` is a fan-out to every listener, so frames from an unrelated refresh really
        // do arrive here.
        ModelRefreshController controller;
        QVERIFY(controller.startLibraryRefresh(kRoots));
        controller.applyWorkerReply(started(QStringLiteral("mi_mine")));
        controller.applyWorkerReply(progress(QStringLiteral("mi_mine"), 10, 100, QString()));
        QVERIFY(!controller.applyWorkerReply(
            progress(QStringLiteral("mi_someone_else"), 900, 1000, QString())));
        QCOMPARE(controller.current(), 10);
        QCOMPARE(controller.total(), 100);
    }

    // ---- cancel ----

    void cancel_is_not_offered_before_the_job_id_arrives()
    {
        ModelRefreshController controller;
        QSignalSpy sent(&controller, &ModelRefreshController::workerRequested);
        QVERIFY(controller.startLibraryRefresh(kRoots));
        // `background: true` returns the started event, but it has not arrived yet. A cancel now
        // has no id to address, and `model_intel_cancel` with an empty id cancels EVERY running
        // refresh.
        QVERIFY(!controller.canCancel());
        QVERIFY(!controller.cancel());
        QCOMPARE(sent.count(), 1);
    }

    void cancel_sends_model_intel_cancel_for_the_running_job()
    {
        ModelRefreshController controller;
        QSignalSpy sent(&controller, &ModelRefreshController::workerRequested);
        QVERIFY(controller.startLibraryRefresh(kRoots));
        controller.applyWorkerReply(started(QStringLiteral("mi_4f1c9a2b7de0")));
        QVERIFY(controller.canCancel());
        QVERIFY(controller.cancel());

        QCOMPARE(sent.count(), 2);
        const QJsonObject request = firstRequest(sent, 1);
        QCOMPARE(request.value(QStringLiteral("command")).toString(),
                 QStringLiteral("model_intel_cancel"));
        QCOMPARE(request.value(QStringLiteral("job_id")).toString(),
                 QStringLiteral("mi_4f1c9a2b7de0"));
        // Still running until the worker says the pass ended. The cancelled run still returns its
        // result with the counts it reached.
        QVERIFY(controller.isRunning());
    }

    void a_cancel_the_worker_refuses_is_repeated_rather_than_swallowed()
    {
        ModelRefreshController controller;
        QVERIFY(controller.startLibraryRefresh(kRoots));
        controller.applyWorkerReply(started(QStringLiteral("mi_a")));
        QVERIFY(controller.cancel());
        controller.applyWorkerReply(QJsonObject{
            {QStringLiteral("type"), QStringLiteral("model_intel_cancel")},
            {QStringLiteral("ok"), false},
            {QStringLiteral("error"), QStringLiteral("no refresh is running with job id 'mi_a'")}});
        QVERIFY(controller.statusIsError());
        QVERIFY(controller.statusText().contains(QStringLiteral("mi_a")));
        // And the offer comes back, because the job it names is evidently still there.
        QVERIFY(controller.canCancel());
    }

    void a_cancelled_refresh_ends_and_says_how_far_it_got()
    {
        ModelRefreshController controller;
        QSignalSpy done(&controller, &ModelRefreshController::refreshFinished);
        QVERIFY(controller.startLibraryRefresh(kRoots));
        controller.applyWorkerReply(started(QStringLiteral("mi_a")));
        controller.applyWorkerReply(progress(QStringLiteral("mi_a"), 31, 759, QString()));
        QVERIFY(controller.cancel());
        controller.applyWorkerReply(finished(QStringLiteral("mi_a"), 31, 20, /*cancelled=*/true));

        QVERIFY(!controller.isRunning());
        QVERIFY(!controller.canCancel());
        QCOMPARE(done.count(), 1);
        QVERIFY2(controller.statusText().contains(QStringLiteral("31")),
                 qPrintable(controller.statusText()));
        QVERIFY(controller.statusText().contains(QStringLiteral("Stopped")));
    }

    // ---- what finishing means to the rest of the app ----

    void finishing_a_per_model_refresh_names_the_model_so_its_cached_answer_can_be_dropped()
    {
        // W2 wired the per-model defaults cache eviction and left the caller to W5. The cache is
        // keyed on the model path, so the signal has to carry it -- a library pass carries nothing
        // and the caller drops everything, which is the correct reading of "look again".
        ModelRefreshController controller;
        QSignalSpy done(&controller, &ModelRefreshController::refreshFinished);

        QVERIFY(controller.startModelRefresh(kRoots, kWeight));
        controller.applyWorkerReply(started(QStringLiteral("mi_one")));
        controller.applyWorkerReply(finished(QStringLiteral("mi_one"), 1, 1, false));
        QCOMPARE(done.count(), 1);
        QCOMPARE(done.at(0).at(0).toString(), kWeight);

        QVERIFY(controller.startLibraryRefresh(kRoots));
        controller.applyWorkerReply(started(QStringLiteral("mi_all")));
        controller.applyWorkerReply(finished(QStringLiteral("mi_all"), 759, 402, false));
        QCOMPARE(done.count(), 2);
        QCOMPARE(done.at(1).at(0).toString(), QString());
    }

    void the_summary_keeps_not_on_the_site_and_could_not_be_looked_up_apart()
    {
        // The worker counts them separately on purpose: the site answering "I do not know this
        // hash" is an answer, and never reaching the site is not. Adding them together would
        // report an outage as a library full of unknown weights.
        ModelRefreshController controller;
        QVERIFY(controller.startLibraryRefresh(kRoots));
        controller.applyWorkerReply(started(QStringLiteral("mi_a")));
        QJsonObject result = finished(QStringLiteral("mi_a"), 475, 402, false);
        result.insert(QStringLiteral("no_match"), 70);
        result.insert(QStringLiteral("lookup_failed"), 3);
        controller.applyWorkerReply(result);

        QVERIFY(controller.statusText().contains(QStringLiteral("70 not on the site")));
        QVERIFY(controller.statusText().contains(QStringLiteral("3 could not be looked up")));
        // A pass that could not reach the site is not a clean result.
        QVERIFY(controller.statusIsError());
    }

    void a_second_refresh_while_one_runs_is_refused_out_loud()
    {
        ModelRefreshController controller;
        QSignalSpy sent(&controller, &ModelRefreshController::workerRequested);
        QVERIFY(controller.startLibraryRefresh(kRoots));
        QVERIFY(!controller.startModelRefresh(kRoots, kWeight));
        QCOMPARE(sent.count(), 1);
        QVERIFY(controller.statusText().contains(QStringLiteral("already running")));
    }

    void a_refresh_that_ends_in_an_error_still_ends()
    {
        // The handler wraps its thread body precisely so a crash cannot leave the caller waiting
        // out a 79-minute budget. The row has to match: an error is an ending.
        ModelRefreshController controller;
        QSignalSpy done(&controller, &ModelRefreshController::refreshFinished);
        QVERIFY(controller.startLibraryRefresh(kRoots));
        controller.applyWorkerReply(started(QStringLiteral("mi_a")));
        controller.applyWorkerReply(QJsonObject{
            {QStringLiteral("type"), QStringLiteral("model_intel_refresh")},
            {QStringLiteral("ok"), false},
            {QStringLiteral("job_id"), QStringLiteral("mi_a")},
            {QStringLiteral("error"), QStringLiteral("OSError: [WinError 21] The device is not ready")}});
        QVERIFY(!controller.isRunning());
        QCOMPARE(done.count(), 1);
        QVERIFY(controller.statusIsError());
        QVERIFY(controller.statusText().contains(QStringLiteral("WinError 21")));
    }

    void an_unrelated_worker_frame_is_not_ours()
    {
        ModelRefreshController controller;
        QVERIFY(!controller.applyWorkerReply(QJsonObject{
            {QStringLiteral("type"), QStringLiteral("progress")},
            {QStringLiteral("ok"), true},
            {QStringLiteral("step"), 3}}));
        QVERIFY(!controller.isRunning());
    }
};

QTEST_MAIN(TestModelRefreshAction)
#include "test_model_refresh_action.moc"
