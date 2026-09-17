// "What kind of generation is this workflow?" -- asked once.
//
// Three C++ sites answered it independently: WorkflowLaunchController::resolveDraftModeId,
// HomePage::inferModeFromWorkflowProfile and WorkflowLibraryPage's own normalisation. The Home one
// ended in a loop over the FILE PATH looking for the substrings "i2v"/"t2v"/"i2i"/"t2i", and then
// returned t2i regardless -- so a workflow whose classification failed was routed by its filename
// and landed on a page whose graph it does not belong to. Nothing told the user; the page just
// looked wrong.
//
// The worker already decides this properly, by what the graph OUTPUTS rather than by node family
// (python/workflow_scanner.py:955-1033): a video output with an image source is i2v, a video output
// alone is t2v, an image output with an image source is i2i. That verdict comes back as
// inferred_task_command / capability_report.primary_task / classification_confidence, and these
// cases are written against that vocabulary rather than a parallel one.
//
// Case 5 is the one that matters: a workflow with NO classification resolves to nothing. Routing by
// filename is worse than refusing, because refusing can be explained.

#include <QtTest>

#include "workflows/WorkflowLaunchController.h"

using spellvision::workflows::WorkflowLaunchController;

namespace
{

QJsonObject profileWith(std::initializer_list<std::pair<QString, QJsonValue>> fields)
{
    QJsonObject object;
    for (const auto &field : fields)
        object.insert(field.first, field.second);
    return object;
}

} // namespace

class WorkflowModeResolverTest : public QObject
{
    Q_OBJECT

private slots:
    void theImporterVerdictIsTheAnswer();
    void theCapabilityReportAnswersWhenTheImporterFieldIsAbsent();
    void aUserOverrideBeatsTheInference();
    void aVerdictWithNoGenerationPageResolvesToNothingAndSaysWhy();
    void aWorkflowWithNoClassificationResolvesToNothingNotToItsFilename();
    void aHiddenModeResolvesToNothingAndNamesItselfUnavailable();
    void anUnavailableModeIsRefusedRatherThanSubstituted();
    void theReasonIsNeverEmpty();
};

// --- 1 -------------------------------------------------------------------------------------------

void WorkflowModeResolverTest::theImporterVerdictIsTheAnswer()
{
    const QJsonObject reply = profileWith({
        {QStringLiteral("inferred_task_command"), QStringLiteral("i2v")},
        {QStringLiteral("inferred_media_type"), QStringLiteral("video")},
        {QStringLiteral("classification_confidence"), 0.87},
    });

    QCOMPARE(WorkflowLaunchController::resolveModeId(reply), QStringLiteral("i2v"));

    const auto resolution = WorkflowLaunchController::modeResolution(reply);
    QCOMPARE(resolution.modeId, QStringLiteral("i2v"));
    QVERIFY(resolution.routable);
    QCOMPARE(resolution.confidence, 0.87);
    QVERIFY(!resolution.reason.isEmpty());

    // The worker's own spellings, which reach the UI unchanged on some paths.
    QCOMPARE(WorkflowLaunchController::resolveModeId(profileWith({
                 {QStringLiteral("inferred_task_command"), QStringLiteral("image_to_video")}})),
             QStringLiteral("i2v"));
    QCOMPARE(WorkflowLaunchController::resolveModeId(profileWith({
                 {QStringLiteral("task_command"), QStringLiteral("Text-To-Image")}})),
             QStringLiteral("t2i"));
}

// --- 2 -------------------------------------------------------------------------------------------

void WorkflowModeResolverTest::theCapabilityReportAnswersWhenTheImporterFieldIsAbsent()
{
    // Exactly the shape of a profile.json on disk: no inferred_task_command (that field lives on the
    // import REPLY), a capability_report that carries the verdict, and the confidence beside it.
    QJsonObject capability;
    capability.insert(QStringLiteral("primary_task"), QStringLiteral("t2v"));
    capability.insert(QStringLiteral("media_type"), QStringLiteral("video"));
    capability.insert(QStringLiteral("confidence"), 0.72);

    const QJsonObject profile = profileWith({
        {QStringLiteral("capability_report"), capability},
    });

    QCOMPARE(WorkflowLaunchController::resolveModeId(profile), QStringLiteral("t2v"));

    const auto resolution = WorkflowLaunchController::modeResolution(profile);
    QVERIFY(resolution.routable);
    QCOMPARE(resolution.confidence, 0.72);

    // The same report nested under metadata, which is where a re-saved profile also keeps it.
    QJsonObject metadata;
    metadata.insert(QStringLiteral("capability_report"), capability);
    QCOMPARE(WorkflowLaunchController::resolveModeId(profileWith({
                 {QStringLiteral("metadata"), metadata}})),
             QStringLiteral("t2v"));
}

// --- 3 -------------------------------------------------------------------------------------------

void WorkflowModeResolverTest::aUserOverrideBeatsTheInference()
{
    // Flows lets the owner correct a misclassification (WorkflowLibraryPage :2093-2098). That has to
    // survive the consolidation: the whole point of an override is that it outranks the classifier.
    QJsonObject capability;
    capability.insert(QStringLiteral("primary_task"), QStringLiteral("t2i"));
    capability.insert(QStringLiteral("confidence"), 0.91);

    const QJsonObject profile = profileWith({
        {QStringLiteral("inferred_task_command"), QStringLiteral("t2i")},
        {QStringLiteral("capability_report"), capability},
        {QStringLiteral("classification_confidence"), 0.91},
        {QStringLiteral("user_task_override"), QStringLiteral("i2i")},
    });

    QCOMPARE(WorkflowLaunchController::resolveModeId(profile), QStringLiteral("i2i"));

    const auto resolution = WorkflowLaunchController::modeResolution(profile);
    QCOMPARE(resolution.modeId, QStringLiteral("i2i"));
    QVERIFY(resolution.routable);
    // An override is not an inference, so the classifier's number is not what is reported for it.
    QCOMPARE(resolution.confidence, 1.0);
    QVERIFY2(resolution.reason.contains(QStringLiteral("override"), Qt::CaseInsensitive),
             qPrintable(resolution.reason));

    // The older key spelling, and an override that is itself unroutable is still refused rather than
    // waved through -- an override outranks the classifier, not the question of whether a page exists.
    QCOMPARE(WorkflowLaunchController::resolveModeId(profileWith({
                 {QStringLiteral("inferred_task_command"), QStringLiteral("t2i")},
                 {QStringLiteral("task_override"), QStringLiteral("image_to_video")}})),
             QStringLiteral("i2v"));
    QVERIFY(WorkflowLaunchController::resolveModeId(profileWith({
                {QStringLiteral("inferred_task_command"), QStringLiteral("t2i")},
                {QStringLiteral("user_task_override"), QStringLiteral("v2v")}})).isEmpty());
}

// --- 4 -------------------------------------------------------------------------------------------

void WorkflowModeResolverTest::aVerdictWithNoGenerationPageResolvesToNothingAndSaysWhy()
{
    // v2v is a REAL verdict the worker produces -- four of the 88 imported profiles in this tree
    // carry it -- and there is no video-to-video page. Before this, HomePage turned it into t2v via
    // media_type and the owner got a text-to-video cockpit holding a video-to-video graph.
    for (const QString &verdict : {QStringLiteral("v2v"), QStringLiteral("audio"),
                                   QStringLiteral("sorcery"), QStringLiteral("unknown")})
    {
        const QJsonObject profile = profileWith({
            {QStringLiteral("inferred_task_command"), verdict},
            {QStringLiteral("workflow_path"), QStringLiteral("D:/wf/my_t2i_favourite.json")},
        });

        const auto resolution = WorkflowLaunchController::modeResolution(profile);
        QVERIFY2(resolution.modeId.isEmpty(), qPrintable(verdict + " -> " + resolution.modeId));
        QVERIFY2(!resolution.routable, qPrintable(verdict));
        QVERIFY2(!resolution.reason.isEmpty(), qPrintable(verdict));
        QCOMPARE(WorkflowLaunchController::resolveModeId(profile), QString());
    }

    // The reason names the verdict, so the refusal can be explained rather than merely reported.
    const auto v2v = WorkflowLaunchController::modeResolution(profileWith({
        {QStringLiteral("inferred_task_command"), QStringLiteral("v2v")}}));
    QVERIFY2(v2v.reason.contains(QStringLiteral("v2v"), Qt::CaseInsensitive), qPrintable(v2v.reason));
}

// --- 5: the one that matters ---------------------------------------------------------------------

void WorkflowModeResolverTest::aWorkflowWithNoClassificationResolvesToNothingNotToItsFilename()
{
    // Every field the old Home fallback read from -- workflow_path, workflow_source, name,
    // profile_name -- spells a mode, and media_type spells another. A resolver that looked at any of
    // them would answer here, and every answer would be a guess about a graph nobody classified.
    const QJsonObject unclassified = profileWith({
        {QStringLiteral("profile_name"), QStringLiteral("wan_i2v_nightly")},
        {QStringLiteral("name"), QStringLiteral("t2v starter")},
        {QStringLiteral("workflow_path"), QStringLiteral("D:/AI_ASSETS/workflows/i2i/upscale_i2v.json")},
        {QStringLiteral("workflow_source"), QStringLiteral("C:/drops/t2i_portrait.json")},
        {QStringLiteral("media_type"), QStringLiteral("video")},
        {QStringLiteral("backend_kind"), QStringLiteral("comfy_workflow")},
    });

    QCOMPARE(WorkflowLaunchController::resolveModeId(unclassified), QString());

    const auto resolution = WorkflowLaunchController::modeResolution(unclassified);
    QVERIFY2(resolution.modeId.isEmpty(), qPrintable(resolution.modeId));
    QVERIFY(!resolution.routable);
    QCOMPARE(resolution.confidence, 0.0);
    QVERIFY(!resolution.reason.isEmpty());

    // An empty object is the same question with none of the bait.
    QCOMPARE(WorkflowLaunchController::resolveModeId(QJsonObject()), QString());
    QVERIFY(!WorkflowLaunchController::modeResolution(QJsonObject()).reason.isEmpty());

    // And a blank/whitespace verdict is an absent one, not a mode called "".
    QCOMPARE(WorkflowLaunchController::resolveModeId(profileWith({
                 {QStringLiteral("inferred_task_command"), QStringLiteral("   ")},
                 {QStringLiteral("workflow_path"), QStringLiteral("D:/wf/t2i.json")}})),
             QString());
}

// --- 6 -------------------------------------------------------------------------------------------

void WorkflowModeResolverTest::aHiddenModeResolvesToNothingAndNamesItselfUnavailable()
{
    // chain / gen3d / train are hidden from the rail for v1.0 (ShellNavigationController.h:17-36).
    // Switching to a page the rail does not show is worse than saying so, so the drop path gets a
    // reason it can put in front of the user instead of a mode id it cannot navigate to.
    for (const QString &hidden : {QStringLiteral("chain"), QStringLiteral("gen3d"), QStringLiteral("train")})
    {
        const auto resolution = WorkflowLaunchController::modeResolution(profileWith({
            {QStringLiteral("inferred_task_command"), hidden}}));

        QVERIFY2(resolution.modeId.isEmpty(), qPrintable(hidden + " -> " + resolution.modeId));
        QVERIFY2(!resolution.routable, qPrintable(hidden));
        QVERIFY2(resolution.reason.contains(hidden, Qt::CaseInsensitive), qPrintable(resolution.reason));
        QVERIFY2(resolution.reason.contains(QStringLiteral("not available"), Qt::CaseInsensitive),
                 qPrintable(resolution.reason));
    }
}

// --- availability ---------------------------------------------------------------------------------

void WorkflowModeResolverTest::anUnavailableModeIsRefusedRatherThanSubstituted()
{
    // resolveDraftModeId used to answer an unavailable mode with defaultModeForMedia -- a DIFFERENT
    // page than the one the graph was classified for. Same defect as the filename guess, one layer up.
    const QJsonObject profile = profileWith({
        {QStringLiteral("inferred_task_command"), QStringLiteral("i2v")},
        {QStringLiteral("media_type"), QStringLiteral("video")},
    });

    const auto none = [](const QString &) { return false; };
    const auto resolution = WorkflowLaunchController::modeResolution(profile, none);
    QVERIFY(resolution.modeId.isEmpty());
    QVERIFY(!resolution.routable);
    QVERIFY2(resolution.reason.contains(QStringLiteral("i2v"), Qt::CaseInsensitive),
             qPrintable(resolution.reason));

    const auto all = [](const QString &) { return true; };
    QCOMPARE(WorkflowLaunchController::resolveModeId(profile, all), QStringLiteral("i2v"));
}

void WorkflowModeResolverTest::theReasonIsNeverEmpty()
{
    // The UI has to be able to explain every outcome, so there is no input for which the resolver
    // says nothing at all.
    const QVector<QJsonObject> inputs = {
        QJsonObject(),
        profileWith({{QStringLiteral("inferred_task_command"), QStringLiteral("t2i")}}),
        profileWith({{QStringLiteral("inferred_task_command"), QStringLiteral("v2v")}}),
        profileWith({{QStringLiteral("inferred_task_command"), QStringLiteral("chain")}}),
        profileWith({{QStringLiteral("user_task_override"), QStringLiteral("i2i")}}),
    };
    for (const QJsonObject &input : inputs)
        QVERIFY(!WorkflowLaunchController::modeResolution(input).reason.trimmed().isEmpty());
}

QTEST_MAIN(WorkflowModeResolverTest)
#include "test_workflow_mode_resolver.moc"
