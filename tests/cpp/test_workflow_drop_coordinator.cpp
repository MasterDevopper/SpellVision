// The drop asks for everything the worker already knows.
//
// Each of these commands existed before this wave and none of them were chained. import_workflow ran
// and its answer -- inferred_task_command, capability_report, supported_modes, a confidence -- was
// read by nobody. compile_workflow_prompt was never called from the drop path, so there was no
// compiled prompt and therefore nothing to fill the cockpit from. check_workflow_launch_readiness
// was called by Flows and not here. And `safe_to_submit` was the literal `false`, under a comment
// saying the IMPORTER reports no launch readiness -- which is true of the importer and false of the
// system, because the readiness command was two files away.
//
// So a dropped workflow landed on whatever page the mouse was over, with nothing filled in, and
// could not be run. These cases drive the whole sequence against a FAKE worker that answers each
// command in turn: no socket, no worker process, no ComfyUI.
//
// The case that matters most is the absent one. A readiness signal that is missing must read as
// UNKNOWN and keep submission closed -- this path has already been bitten once by an absent object
// falling through to .toBool(true) and queue-launching a workflow whose nodes were missing.

#include <QtTest>

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSignalSpy>
#include <QStringList>

#include "shell/ProjectRoot.h"
#include "workflows/WorkflowDropCoordinator.h"

using spellvision::workflows::WorkflowDropCoordinator;

namespace
{

using Readiness = WorkflowDropCoordinator::Readiness;

QString importedWorkflowDir(const QString &slug)
{
    return QDir(QDir(spellvision::shell::resolveProjectRoot())
                    .filePath(QStringLiteral("runtime/imported_workflows")))
        .filePath(slug);
}

// An import reply shaped like the one handle_import_workflow_command actually sends: FLAT, with the
// paths under `artifacts`. (The drop path once looked for response["draft"] and response["result"],
// neither of which the worker emits, and every lookup silently resolved empty.)
QJsonObject importReplyFor(const QString &slug, const QString &task, const QString &media)
{
    const QString dir = importedWorkflowDir(slug);
    QJsonObject artifacts;
    artifacts.insert(QStringLiteral("import_root"), dir);
    artifacts.insert(QStringLiteral("profile_path"), QDir(dir).filePath(QStringLiteral("profile.json")));
    artifacts.insert(QStringLiteral("workflow_path"), QDir(dir).filePath(QStringLiteral("workflow.json")));

    QJsonObject reply;
    reply.insert(QStringLiteral("type"), QStringLiteral("workflow_import_result"));
    reply.insert(QStringLiteral("ok"), true);
    reply.insert(QStringLiteral("import_slug"), slug);
    reply.insert(QStringLiteral("inferred_task_command"), task);
    reply.insert(QStringLiteral("inferred_media_type"), media);
    reply.insert(QStringLiteral("classification_confidence"), 0.9);
    reply.insert(QStringLiteral("artifacts"), artifacts);
    reply.insert(QStringLiteral("missing_custom_nodes"), QJsonArray());
    return reply;
}

// The readiness block the worker now puts on the import reply. `ready` is a tri-state on the wire:
// true, false, or JSON null when the worker looked and could not tell.
QJsonObject withReadiness(QJsonObject importReply, const QJsonValue &ready, const QString &summary = QString())
{
    QJsonObject block;
    block.insert(QStringLiteral("ready"), ready);
    block.insert(QStringLiteral("readiness_determined"), ready.isBool());
    if (!summary.isEmpty())
        block.insert(QStringLiteral("summary"), summary);
    importReply.insert(QStringLiteral("launch_readiness"), block);
    return importReply;
}

QJsonObject compileReplyFor(const QString &slug)
{
    QJsonObject reply;
    reply.insert(QStringLiteral("type"), QStringLiteral("workflow_compile_result"));
    reply.insert(QStringLiteral("ok"), true);
    reply.insert(QStringLiteral("object_info_available"), true);
    reply.insert(QStringLiteral("graph_format"), QStringLiteral("comfy_ui_graph"));
    reply.insert(QStringLiteral("compiled_prompt_path"),
                 QDir(importedWorkflowDir(slug)).filePath(QStringLiteral("prompt_api.json")));
    reply.insert(QStringLiteral("missing_classes"), QJsonArray());
    return reply;
}

// What compile_workflow_prompt replies when the converter REFUSES: a null path on purpose, the
// classes it could not resolve, and the packs the workflow itself declares for them. This is the
// reply shape cd6d5ba introduced -- read off python/workflow_library_commands.py, not guessed.
QJsonObject refusedCompileReply()
{
    QJsonObject pack;
    pack.insert(QStringLiteral("pack"), QStringLiteral("ComfyUI_Comfyroll_CustomNodes"));
    pack.insert(QStringLiteral("repo_url"),
                QStringLiteral("https://github.com/Suzie1/ComfyUI_Comfyroll_CustomNodes"));
    pack.insert(QStringLiteral("version"), QStringLiteral("d78b780"));
    pack.insert(QStringLiteral("classes"), QJsonArray{QStringLiteral("CR Text Concatenate")});

    const QString refusal = QStringLiteral(
        "Cannot convert UI-graph workflow: object_info has no schema for node class(es): "
        "CR Text Concatenate. Install the missing custom nodes first.\n"
        "The workflow names the pack(s) it needs:\n"
        "  - ComfyUI_Comfyroll_CustomNodes "
        "(https://github.com/Suzie1/ComfyUI_Comfyroll_CustomNodes) -- supplies CR Text Concatenate");

    QJsonObject reply;
    reply.insert(QStringLiteral("type"), QStringLiteral("workflow_compile_result"));
    reply.insert(QStringLiteral("ok"), false);
    reply.insert(QStringLiteral("object_info_available"), true);
    reply.insert(QStringLiteral("graph_format"), QStringLiteral("comfy_ui_graph"));
    reply.insert(QStringLiteral("compiled_prompt_path"), QJsonValue());
    reply.insert(QStringLiteral("missing_classes"), QJsonArray{QStringLiteral("CR Text Concatenate")});
    reply.insert(QStringLiteral("missing_packs"), QJsonArray{pack});
    reply.insert(QStringLiteral("errors"), QJsonArray{refusal});
    reply.insert(QStringLiteral("dangling_links"), QJsonArray());
    reply.insert(QStringLiteral("reason"), refusal);
    reply.insert(QStringLiteral("node_count"), 0);
    return reply;
}

// What compile_workflow_prompt replies when ComfyUI is DOWN. Read off
// python/workflow_library_commands.py: `ok:false`, the flag, an empty missing_classes (it must not
// claim to know what is missing), and -- since nothing about the FILE needs a schema -- what kind of
// graph it is and where it lives.
QJsonObject unreachableCompileReply()
{
    QJsonObject reply;
    reply.insert(QStringLiteral("type"), QStringLiteral("workflow_compile_result"));
    reply.insert(QStringLiteral("ok"), false);
    reply.insert(QStringLiteral("object_info_available"), false);
    reply.insert(QStringLiteral("graph_format"), QStringLiteral("comfy_ui_graph"));
    reply.insert(QStringLiteral("missing_classes"), QJsonArray());
    reply.insert(QStringLiteral("reason"),
                 QStringLiteral("ComfyUI is not reachable, so node availability could not be checked."));
    return reply;
}

QJsonObject readinessReply(bool ready, const QString &summary = QString())
{
    QJsonObject reply;
    reply.insert(QStringLiteral("type"), QStringLiteral("workflow_readiness_result"));
    reply.insert(QStringLiteral("ok"), true);
    reply.insert(QStringLiteral("ready"), ready);
    if (!summary.isEmpty())
        reply.insert(QStringLiteral("summary"), summary);
    return reply;
}

// The worker, reduced to a lookup table plus a transcript. Replies are delivered synchronously, so
// the whole sequence runs inside handleDroppedWorkflow and there is nothing to wait for.
class FakeWorker
{
public:
    QHash<QString, QJsonObject> replies;
    QStringList commands;
    QList<QJsonObject> requests;

    void serve(const QJsonObject &request, WorkflowDropCoordinator::RequestCompletion completion)
    {
        const QString command = request.value(QStringLiteral("command")).toString();
        commands << command;
        requests << request;
        completion(replies.value(command), QString(), true);
    }
};

// Everything the shell would have done, recorded instead of done.
struct Shell
{
    QStringList log;
    QStringList refusals;
    QString openedMode;
    QJsonObject openedDraft;
    int opens = 0;
    int downloadPrompts = 0;
    QStringList offeredNodes;
    QStringList offeredModels;
    bool acceptDownloads = false;
    bool sawCivitaiAsk = false;
    bool sawHfAsk = false;
    int libraryRefreshes = 0;
};

WorkflowDropCoordinator::Bindings bindingsFor(FakeWorker &worker, Shell &shell)
{
    WorkflowDropCoordinator::Bindings bindings;
    bindings.sendRequestAsync = [&worker](const QJsonObject &request,
                                          WorkflowDropCoordinator::RequestCompletion completion) {
        worker.serve(request, std::move(completion));
    };
    bindings.appendLogLine = [&shell](const QString &text) { shell.log << text; };
    bindings.isModeAvailable = [](const QString &modeId) {
        // The four generation pages this build has.
        return modeId == QStringLiteral("t2i") || modeId == QStringLiteral("i2i")
            || modeId == QStringLiteral("t2v") || modeId == QStringLiteral("i2v");
    };
    bindings.requestDownloads = [&shell](const QStringList &nodes, const QStringList &models,
                                         bool needsCivitai, bool needsHf) {
        ++shell.downloadPrompts;
        shell.offeredNodes = nodes;
        shell.offeredModels = models;
        shell.sawCivitaiAsk = needsCivitai;
        shell.sawHfAsk = needsHf;
        return shell.acceptDownloads;
    };
    bindings.showRefusal = [&shell](const QString &, const QString &message) { shell.refusals << message; };
    bindings.openDraftOnMode = [&shell](const QString &modeId, const QJsonObject &draft) {
        ++shell.opens;
        shell.openedMode = modeId;
        shell.openedDraft = draft;
    };
    bindings.setBusy = [](bool, const QString &) {};
    bindings.refreshWorkflowLibrary = [&shell]() { ++shell.libraryRefreshes; };
    return bindings;
}

bool hasCompiledPrompt(const QString &slug)
{
    return QFileInfo::exists(QDir(importedWorkflowDir(slug)).filePath(QStringLiteral("prompt_api.json")));
}

} // namespace

class WorkflowDropCoordinatorTest : public QObject
{
    Q_OBJECT

private slots:
    void initTestCase();

    void theDropAsksEveryCommandInOrderAndLandsOnTheClassifiedPage();
    void safeToSubmitTracksTheReadinessVerdict();
    void anAbsentReadinessSignalReadsAsUnknownAndKeepsSubmissionClosed();
    void aWorkerThatSendsNoReadinessBlockIsStillAskedForOne();
    void aWorkflowThatIsNotRoutableRefusesWithTheResolversReasonAndOpensNoPage();
    void aWorkflowNeedingNodesOffersTheDownloadDialogBeforeAnythingIsFetched();
    void decliningTheDownloadStillOpensTheWorkflowAsItIs();
    void acceptingTheDownloadReimportsWithConsentAndUsesTheRETRYsAnswer();
    void aFailedImportRefusesInsteadOfOpeningAnEmptyDraft();
    void packsAlreadyOnDiskAreNotMissing();
    void aRefusedCompileYieldsNoPathEvenWithAStalePromptSittingInTheImportRoot();
    void aRefusedCompileRefusesTheDropWithThePackItNamed();
    void anOldWorkerThatWroteAPathBesideItsRefusalIsStillRefused();
    void anUnreachableSchemaOpensTheDropInsteadOfRefusingIt();
    void theOfflineDropNeverReadsThePromptApiJsonSittingRightThere();
    void offlineSubmissionStaysClosedEvenWhenReadinessSaysReady();
    void aRefusalIsStillARefusalWhenTheSchemaFlagAlsoSaysUnreachable();
    void anOfflineApiPromptGraphResolvesToTheGraphAndNotToTheArtefact();
    void anApiPromptGraphStillResolvesToTheImportsOwnWorkflowPath();
    void aReplyThatCarriesNothingAtAllStillFallsBackAndSaysSoInTheLog();

private:
    QString slug_ = QStringLiteral("asteral-json"); // a real owner t2i workflow with a compiled prompt
};

void WorkflowDropCoordinatorTest::initTestCase()
{
    if (!hasCompiledPrompt(slug_))
        QSKIP("asteral-json has no compiled prompt in this checkout");
}

// --- 1: the sequence -----------------------------------------------------------------------------

void WorkflowDropCoordinatorTest::theDropAsksEveryCommandInOrderAndLandsOnTheClassifiedPage()
{
    FakeWorker worker;
    worker.replies[QStringLiteral("import_workflow")] = withReadiness(
        importReplyFor(slug_, QStringLiteral("t2i"), QStringLiteral("image")), true);
    worker.replies[QStringLiteral("compile_workflow_prompt")] = compileReplyFor(slug_);

    Shell shell;
    WorkflowDropCoordinator coordinator;
    coordinator.bind(bindingsFor(worker, shell));
    QSignalSpy opened(&coordinator, &WorkflowDropCoordinator::draftOpened);

    coordinator.handleDroppedWorkflow(QStringLiteral("D:/drops/asteral.json"));

    // compile_workflow_prompt -- the command the drop path never sent -- is in the transcript, and
    // check_workflow_launch_readiness is NOT: the import reply already carried that verdict, and one
    // drop asks one worker one time for one answer.
    QCOMPARE(worker.commands, (QStringList{QStringLiteral("import_workflow"),
                                           QStringLiteral("compile_workflow_prompt")}));

    // Nothing is fetched on the first import: consent comes first, every time.
    QCOMPARE(worker.requests.at(0).value(QStringLiteral("auto_apply_node_deps")).toBool(), false);
    QCOMPARE(worker.requests.at(0).value(QStringLiteral("auto_apply_model_deps")).toBool(), false);

    // Routed by the importer's classification, not by the page that happened to be in front.
    QCOMPARE(shell.opens, 1);
    QCOMPARE(shell.openedMode, QStringLiteral("t2i"));
    QCOMPARE(opened.count(), 1);
    QVERIFY(shell.refusals.isEmpty());

    // And the draft carries VALUES, which is the whole difference from four paths and a warning.
    const QJsonObject draft = shell.openedDraft;
    QVERIFY(!draft.value(QStringLiteral("prompt")).toString().trimmed().isEmpty());
    QVERIFY(!draft.value(QStringLiteral("checkpoint")).toString().trimmed().isEmpty());
    QVERIFY(!draft.value(QStringLiteral("sampler")).toString().trimmed().isEmpty());
    QVERIFY(draft.value(QStringLiteral("steps")).toInt() > 0);
    QVERIFY(draft.value(QStringLiteral("width")).toInt() > 0);
    QVERIFY(!draft.value(QStringLiteral("lora_stack")).toArray().isEmpty());
}

// --- 2: safe_to_submit stops being a literal ------------------------------------------------------

void WorkflowDropCoordinatorTest::safeToSubmitTracksTheReadinessVerdict()
{
    for (const bool ready : {true, false})
    {
        FakeWorker worker;
        worker.replies[QStringLiteral("import_workflow")] = withReadiness(
            importReplyFor(slug_, QStringLiteral("t2i"), QStringLiteral("image")), ready,
            ready ? QString() : QStringLiteral("2 node classes are missing."));
        worker.replies[QStringLiteral("compile_workflow_prompt")] = compileReplyFor(slug_);

        Shell shell;
        WorkflowDropCoordinator coordinator;
        coordinator.bind(bindingsFor(worker, shell));
        coordinator.handleDroppedWorkflow(QStringLiteral("D:/drops/asteral.json"));

        QCOMPARE(shell.opens, 1);
        // A not-ready workflow still OPENS -- a state the user cannot inspect is worse than one they
        // cannot run -- but it cannot be submitted.
        QCOMPARE(shell.openedDraft.value(QStringLiteral("safe_to_submit")).toBool(), ready);

        if (!ready)
        {
            bool explained = false;
            for (const QJsonValue &warning : shell.openedDraft.value(QStringLiteral("warnings")).toArray())
                explained = explained
                    || warning.toString().contains(QStringLiteral("node classes are missing"));
            QVERIFY2(explained, "the readiness summary never reached the user");
        }
    }
}

// --- 3: the absent answer -------------------------------------------------------------------------

void WorkflowDropCoordinatorTest::anAbsentReadinessSignalReadsAsUnknownAndKeepsSubmissionClosed()
{
    // Three ways the signal can be absent, and not one of them may read as "go".
    QCOMPARE(WorkflowDropCoordinator::readinessOf(QJsonObject()), Readiness::Unknown);

    QJsonObject okButSilent;
    okButSilent.insert(QStringLiteral("ok"), true);
    QCOMPARE(WorkflowDropCoordinator::readinessOf(okButSilent), Readiness::Unknown);

    QJsonObject failed;
    failed.insert(QStringLiteral("ok"), false);
    failed.insert(QStringLiteral("error"), QStringLiteral("ComfyUI is not reachable"));
    QCOMPARE(WorkflowDropCoordinator::readinessOf(failed), Readiness::Unknown);

    // "ready": "yes" is a string, not the bool this contract is written in.
    QJsonObject wrongType;
    wrongType.insert(QStringLiteral("ok"), true);
    wrongType.insert(QStringLiteral("ready"), QStringLiteral("yes"));
    QCOMPARE(WorkflowDropCoordinator::readinessOf(wrongType), Readiness::Unknown);

    // And the same three-state on the IMPORT reply's block. An import reply with no block is a
    // worker older than the field; a block whose `ready` is JSON null is the worker saying it looked
    // and could not tell -- which is the answer a UI graph with no live schema produces, and the
    // answer that used to be silently reported as READY over `models 0/0 present`.
    QCOMPARE(WorkflowDropCoordinator::readinessOfImportReply(QJsonObject()), Readiness::Unknown);
    QCOMPARE(WorkflowDropCoordinator::readinessOfImportReply(
                 importReplyFor(slug_, QStringLiteral("t2i"), QStringLiteral("image"))),
             Readiness::Unknown);
    QCOMPARE(WorkflowDropCoordinator::readinessOfImportReply(withReadiness(
                 importReplyFor(slug_, QStringLiteral("t2i"), QStringLiteral("image")), QJsonValue())),
             Readiness::Unknown);
    QCOMPARE(WorkflowDropCoordinator::readinessOfImportReply(withReadiness(
                 importReplyFor(slug_, QStringLiteral("t2i"), QStringLiteral("image")), true)),
             Readiness::Ready);
    QCOMPARE(WorkflowDropCoordinator::readinessOfImportReply(withReadiness(
                 importReplyFor(slug_, QStringLiteral("t2i"), QStringLiteral("image")), false)),
             Readiness::NotReady);

    FakeWorker worker;
    worker.replies[QStringLiteral("import_workflow")] = withReadiness(
        importReplyFor(slug_, QStringLiteral("t2i"), QStringLiteral("image")), QJsonValue());
    worker.replies[QStringLiteral("compile_workflow_prompt")] = compileReplyFor(slug_);

    Shell shell;
    WorkflowDropCoordinator coordinator;
    coordinator.bind(bindingsFor(worker, shell));
    coordinator.handleDroppedWorkflow(QStringLiteral("D:/drops/asteral.json"));

    QCOMPARE(shell.opens, 1);
    QCOMPARE(shell.openedDraft.value(QStringLiteral("safe_to_submit")).toBool(), false);
    bool explained = false;
    for (const QJsonValue &warning : shell.openedDraft.value(QStringLiteral("warnings")).toArray())
        explained = explained || warning.toString().contains(QStringLiteral("could not be established"));
    QVERIFY2(explained, "an unknown readiness has to SAY it is unknown, not look like a refusal");

    // And the builder's own verdict is a ceiling: a ready reply cannot promote a draft the builder
    // already refused to vouch for.
    QJsonObject unsafeDraft;
    unsafeDraft.insert(QStringLiteral("safe_to_submit"), false);
    const QJsonObject finalized =
        WorkflowDropCoordinator::finalizeDraft(unsafeDraft, Readiness::Ready, QString());
    QCOMPARE(finalized.value(QStringLiteral("safe_to_submit")).toBool(), false);
}

// --- 3b: the fallback for a worker older than the field -------------------------------------------

void WorkflowDropCoordinatorTest::aWorkerThatSendsNoReadinessBlockIsStillAskedForOne()
{
    // The command is not deleted, it is demoted. A worker whose import reply predates
    // `launch_readiness` still gets asked, and its answer still decides submission -- otherwise this
    // change would have turned a known verdict into an unknown one on every older worker.
    FakeWorker worker;
    worker.replies[QStringLiteral("import_workflow")] =
        importReplyFor(slug_, QStringLiteral("t2i"), QStringLiteral("image"));
    worker.replies[QStringLiteral("compile_workflow_prompt")] = compileReplyFor(slug_);
    worker.replies[QStringLiteral("check_workflow_launch_readiness")] = readinessReply(true);

    Shell shell;
    WorkflowDropCoordinator coordinator;
    coordinator.bind(bindingsFor(worker, shell));
    coordinator.handleDroppedWorkflow(QStringLiteral("D:/drops/asteral.json"));

    QCOMPARE(worker.commands, (QStringList{QStringLiteral("import_workflow"),
                                           QStringLiteral("compile_workflow_prompt"),
                                           QStringLiteral("check_workflow_launch_readiness")}));
    QCOMPARE(shell.opens, 1);
    QCOMPARE(shell.openedDraft.value(QStringLiteral("safe_to_submit")).toBool(), true);
}

// --- 4: not routable ------------------------------------------------------------------------------

void WorkflowDropCoordinatorTest::aWorkflowThatIsNotRoutableRefusesWithTheResolversReasonAndOpensNoPage()
{
    FakeWorker worker;
    worker.replies[QStringLiteral("import_workflow")] =
        importReplyFor(QStringLiteral("mmaudio-json"), QStringLiteral("v2v"), QStringLiteral("video"));

    Shell shell;
    WorkflowDropCoordinator coordinator;
    coordinator.bind(bindingsFor(worker, shell));
    QSignalSpy refused(&coordinator, &WorkflowDropCoordinator::refused);

    coordinator.handleDroppedWorkflow(QStringLiteral("D:/drops/mmaudio.json"));

    // No page, and no pointless work: the sequence stops at the classification rather than compiling
    // a graph it has nowhere to put.
    QCOMPARE(shell.opens, 0);
    QCOMPARE(worker.commands, QStringList{QStringLiteral("import_workflow")});

    // ONE message for one cause. The draft builder would refuse a v2v graph too, and if the
    // coordinator asked it first the user would see a different sentence for the same fact.
    QCOMPARE(refused.count(), 1);
    QCOMPARE(shell.refusals.size(), 1);
    QVERIFY2(shell.refusals.first().contains(QStringLiteral("v2v")), qPrintable(shell.refusals.first()));
}

// --- 5: missing nodes -----------------------------------------------------------------------------

void WorkflowDropCoordinatorTest::aWorkflowNeedingNodesOffersTheDownloadDialogBeforeAnythingIsFetched()
{
    QJsonObject dependency;
    dependency.insert(QStringLiteral("class_name"), QStringLiteral("LayerUtility: ImageBlend"));
    dependency.insert(QStringLiteral("action"), QStringLiteral("install"));
    QJsonObject nodePlan;
    nodePlan.insert(QStringLiteral("dependencies"), QJsonArray{dependency});

    QJsonObject modelAction;
    modelAction.insert(QStringLiteral("kind"), QStringLiteral("download"));
    modelAction.insert(QStringLiteral("source_value"), QStringLiteral("hyperRealism_v20.safetensors"));
    QJsonObject materialized;
    materialized.insert(QStringLiteral("url"), QStringLiteral("https://civitai.com/api/download/models/1"));
    modelAction.insert(QStringLiteral("materialized"), materialized);
    QJsonObject modelPlan;
    modelPlan.insert(QStringLiteral("install_actions"), QJsonArray{modelAction});

    QJsonObject plan;
    plan.insert(QStringLiteral("node_plan"), nodePlan);
    plan.insert(QStringLiteral("model_plan"), modelPlan);

    QJsonObject import = importReplyFor(slug_, QStringLiteral("t2i"), QStringLiteral("image"));
    import.insert(QStringLiteral("dependency_plan"), plan);

    FakeWorker worker;
    worker.replies[QStringLiteral("import_workflow")] = withReadiness(import, true);
    worker.replies[QStringLiteral("compile_workflow_prompt")] = compileReplyFor(slug_);

    Shell shell;
    shell.acceptDownloads = false;
    WorkflowDropCoordinator coordinator;
    coordinator.bind(bindingsFor(worker, shell));
    coordinator.handleDroppedWorkflow(QStringLiteral("D:/drops/asteral.json"));

    QCOMPARE(shell.downloadPrompts, 1);
    QCOMPARE(shell.offeredNodes, QStringList{QStringLiteral("LayerUtility: ImageBlend")});
    QCOMPARE(shell.offeredModels, QStringList{QStringLiteral("hyperRealism_v20.safetensors")});
    // The host the file comes from decides which key is worth asking for.
    QVERIFY(shell.sawCivitaiAsk);
    QVERIFY(!shell.sawHfAsk);
}

void WorkflowDropCoordinatorTest::decliningTheDownloadStillOpensTheWorkflowAsItIs()
{
    QJsonObject dependency;
    dependency.insert(QStringLiteral("class_name"), QStringLiteral("SomeMissingNode"));
    dependency.insert(QStringLiteral("action"), QStringLiteral("install"));
    QJsonObject nodePlan;
    nodePlan.insert(QStringLiteral("dependencies"), QJsonArray{dependency});
    QJsonObject plan;
    plan.insert(QStringLiteral("node_plan"), nodePlan);

    QJsonObject import = importReplyFor(slug_, QStringLiteral("t2i"), QStringLiteral("image"));
    import.insert(QStringLiteral("dependency_plan"), plan);

    FakeWorker worker;
    worker.replies[QStringLiteral("import_workflow")] =
        withReadiness(import, false, QStringLiteral("1 node class is missing."));
    worker.replies[QStringLiteral("compile_workflow_prompt")] = compileReplyFor(slug_);

    Shell shell;
    shell.acceptDownloads = false;
    WorkflowDropCoordinator coordinator;
    coordinator.bind(bindingsFor(worker, shell));
    coordinator.handleDroppedWorkflow(QStringLiteral("D:/drops/asteral.json"));

    // Saying no to a download is not saying no to the workflow: it opens, for review, and exactly one
    // import was sent -- nothing was fetched.
    QCOMPARE(worker.commands.count(QStringLiteral("import_workflow")), 1);
    QCOMPARE(shell.opens, 1);
    QCOMPARE(shell.openedDraft.value(QStringLiteral("safe_to_submit")).toBool(), false);
}

void WorkflowDropCoordinatorTest::acceptingTheDownloadReimportsWithConsentAndUsesTheRETRYsAnswer()
{
    QJsonObject dependency;
    dependency.insert(QStringLiteral("class_name"), QStringLiteral("SomeMissingNode"));
    dependency.insert(QStringLiteral("action"), QStringLiteral("install"));
    QJsonObject nodePlan;
    nodePlan.insert(QStringLiteral("dependencies"), QJsonArray{dependency});
    QJsonObject plan;
    plan.insert(QStringLiteral("node_plan"), nodePlan);

    QJsonObject firstImport = importReplyFor(slug_, QStringLiteral("t2i"), QStringLiteral("image"));
    firstImport.insert(QStringLiteral("dependency_plan"), plan);

    FakeWorker worker;
    worker.replies[QStringLiteral("import_workflow")] = withReadiness(firstImport, false);
    worker.replies[QStringLiteral("compile_workflow_prompt")] = compileReplyFor(slug_);

    Shell shell;
    shell.acceptDownloads = true;
    WorkflowDropCoordinator coordinator;
    coordinator.bind(bindingsFor(worker, shell));

    // After consent the SECOND import is the one carried forward. The old path sent the retry and
    // then threw its reply away, so a successful download still left the draft describing the
    // pre-download world.
    bool served = false;
    QJsonObject afterDownload = withReadiness(
        importReplyFor(slug_, QStringLiteral("t2i"), QStringLiteral("image")), true);
    WorkflowDropCoordinator::Bindings bindings = bindingsFor(worker, shell);
    bindings.sendRequestAsync = [&](const QJsonObject &request,
                                    WorkflowDropCoordinator::RequestCompletion completion) {
        const QString command = request.value(QStringLiteral("command")).toString();
        worker.commands << command;
        worker.requests << request;
        if (command == QStringLiteral("import_workflow") && served)
        {
            completion(afterDownload, QString(), true);
            return;
        }
        if (command == QStringLiteral("import_workflow"))
            served = true;
        completion(worker.replies.value(command), QString(), true);
    };
    coordinator.bind(bindings);
    coordinator.handleDroppedWorkflow(QStringLiteral("D:/drops/asteral.json"));

    QCOMPARE(shell.downloadPrompts, 1);
    QCOMPARE(worker.commands.count(QStringLiteral("import_workflow")), 2);
    // The re-import is the ONLY one that carries consent.
    QCOMPARE(worker.requests.at(0).value(QStringLiteral("auto_apply_node_deps")).toBool(), false);
    QCOMPARE(worker.requests.at(1).value(QStringLiteral("auto_apply_node_deps")).toBool(), true);
    // The dialog is offered once, not again on the re-import.
    QCOMPARE(shell.downloadPrompts, 1);
    QCOMPARE(shell.opens, 1);
    // ... and the RETRY's readiness is the one that reaches the draft: the first import said not
    // ready because the pack was missing, the download installed it, and the re-import said ready.
    // Carrying the first answer forward would describe the pre-download world.
    QCOMPARE(shell.openedDraft.value(QStringLiteral("safe_to_submit")).toBool(), true);
}

// --- 6: the import that fails ---------------------------------------------------------------------

void WorkflowDropCoordinatorTest::aFailedImportRefusesInsteadOfOpeningAnEmptyDraft()
{
    QJsonObject failure;
    failure.insert(QStringLiteral("ok"), false);
    failure.insert(QStringLiteral("error"), QStringLiteral("workflow.json is not a ComfyUI graph"));

    FakeWorker worker;
    worker.replies[QStringLiteral("import_workflow")] = failure;

    Shell shell;
    WorkflowDropCoordinator coordinator;
    coordinator.bind(bindingsFor(worker, shell));
    coordinator.handleDroppedWorkflow(QStringLiteral("D:/drops/not-a-workflow.json"));

    QCOMPARE(shell.opens, 0);
    QCOMPARE(shell.refusals.size(), 1);
    QVERIFY2(shell.refusals.first().contains(QStringLiteral("not a ComfyUI graph")),
             qPrintable(shell.refusals.first()));
    QCOMPARE(worker.commands, QStringList{QStringLiteral("import_workflow")});
}

// --- 7: the already-installed trap ----------------------------------------------------------------

void WorkflowDropCoordinatorTest::packsAlreadyOnDiskAreNotMissing()
{
    // BasicT2I_V23 listed 16 missing_custom_nodes whose packs were already installed:
    // missing_custom_nodes is an /object_info gap, not an install verdict, and a dialog that offered
    // to download what is already on disk is a dialog people learn to dismiss.
    QJsonObject installed;
    installed.insert(QStringLiteral("class_name"), QStringLiteral("ImpactWildcardProcessor"));
    installed.insert(QStringLiteral("action"), QStringLiteral("already_installed"));
    QJsonObject present;
    present.insert(QStringLiteral("class_name"), QStringLiteral("VHS_VideoCombine"));
    present.insert(QStringLiteral("action"), QStringLiteral("already_present"));
    QJsonObject genuinelyMissing;
    genuinelyMissing.insert(QStringLiteral("class_name"), QStringLiteral("LayerUtility: ImageBlend"));
    genuinelyMissing.insert(QStringLiteral("action"), QStringLiteral("install"));

    QJsonObject nodePlan;
    nodePlan.insert(QStringLiteral("dependencies"), QJsonArray{installed, present, genuinelyMissing});
    QJsonObject plan;
    plan.insert(QStringLiteral("node_plan"), nodePlan);

    QJsonObject reply = importReplyFor(slug_, QStringLiteral("t2i"), QStringLiteral("image"));
    reply.insert(QStringLiteral("dependency_plan"), plan);
    reply.insert(QStringLiteral("missing_custom_nodes"),
                 QJsonArray{QStringLiteral("ImpactWildcardProcessor"),
                            QStringLiteral("VHS_VideoCombine"),
                            QStringLiteral("LayerUtility: ImageBlend")});

    QCOMPARE(WorkflowDropCoordinator::missingNodeNames(reply),
             QStringList{QStringLiteral("LayerUtility: ImageBlend")});

    // With no dependency plan at all there is nothing better than the scanner's raw list.
    QJsonObject noPlan = importReplyFor(slug_, QStringLiteral("t2i"), QStringLiteral("image"));
    noPlan.insert(QStringLiteral("missing_custom_nodes"), QJsonArray{QStringLiteral("SomeNode")});
    QCOMPARE(WorkflowDropCoordinator::missingNodeNames(noPlan), QStringList{QStringLiteral("SomeNode")});
}

// --- 8: a refusal is not a silence ---------------------------------------------------------------
//
// compiledPromptPathFor fell back to whatever prompt_api.json sat in the import root whenever the
// reply carried no path. That was written when "no path" meant "the worker did not answer". Since
// the converter began refusing a graph whose classes it cannot resolve, "no path" ALSO means "the
// worker just said this must not be compiled" -- so the fallback fired exactly then, and answered
// with the older file from the same directory. Seven of those exist on this box, carrying a width
// in a batch_size field. They are well-formed JSON, so nothing downstream rejects them.

void WorkflowDropCoordinatorTest::aRefusedCompileYieldsNoPathEvenWithAStalePromptSittingInTheImportRoot()
{
    // The whole point: the file IS there, and it still is not used.
    QVERIFY2(hasCompiledPrompt(slug_), "this case is vacuous without a prompt_api.json to fall back to");

    const QJsonObject importReply =
        withReadiness(importReplyFor(slug_, QStringLiteral("t2i"), QStringLiteral("image")), true);
    const auto compiled = WorkflowDropCoordinator::compiledPromptFor(refusedCompileReply(), importReply);

    QVERIFY2(compiled.path.isEmpty(), qPrintable(compiled.path));
    QVERIFY(!compiled.fromStaleFallback);
    QVERIFY(!compiled.refusal.isEmpty());
    QCOMPARE(WorkflowDropCoordinator::compiledPromptPathFor(refusedCompileReply(), importReply), QString());
}

void WorkflowDropCoordinatorTest::aRefusedCompileRefusesTheDropWithThePackItNamed()
{
    FakeWorker worker;
    worker.replies[QStringLiteral("import_workflow")] = withReadiness(
        importReplyFor(slug_, QStringLiteral("t2i"), QStringLiteral("image")), true);
    worker.replies[QStringLiteral("compile_workflow_prompt")] = refusedCompileReply();

    Shell shell;
    WorkflowDropCoordinator coordinator;
    coordinator.bind(bindingsFor(worker, shell));
    QSignalSpy refused(&coordinator, &WorkflowDropCoordinator::refused);

    coordinator.handleDroppedWorkflow(QStringLiteral("D:/drops/asteral.json"));

    // No page, and emphatically no draft built from the stale file.
    QCOMPARE(shell.opens, 0);
    QCOMPARE(refused.count(), 1);
    QCOMPARE(shell.refusals.size(), 1);

    // The Python side already resolved the pack to a repository URL. Swallowing that and showing
    // "no compiled prompt is available" is how the user ends up with nowhere to go.
    const QString message = shell.refusals.first();
    QVERIFY2(message.contains(QStringLiteral("CR Text Concatenate")), qPrintable(message));
    QVERIFY2(message.contains(QStringLiteral("ComfyUI_Comfyroll_CustomNodes")), qPrintable(message));
    QVERIFY2(message.contains(QStringLiteral("https://github.com/Suzie1/ComfyUI_Comfyroll_CustomNodes")),
             qPrintable(message));

    // And no readiness round trip after a refusal: there is nothing left to be ready for.
    QCOMPARE(worker.commands, (QStringList{QStringLiteral("import_workflow"),
                                           QStringLiteral("compile_workflow_prompt")}));
}

void WorkflowDropCoordinatorTest::anOldWorkerThatWroteAPathBesideItsRefusalIsStillRefused()
{
    // Before the worker learned to refuse, compile_workflow_prompt wrote prompt_api.json
    // UNCONDITIONALLY and replied ok:false beside it. Such a reply names a path and refuses in the
    // same breath, and the file it names is the rotten one -- so the refusal is read first.
    QJsonObject oldReply = compileReplyFor(slug_);
    oldReply.insert(QStringLiteral("ok"), false);
    oldReply.insert(QStringLiteral("missing_classes"), QJsonArray{QStringLiteral("CR Text Concatenate")});

    const QJsonObject importReply =
        withReadiness(importReplyFor(slug_, QStringLiteral("t2i"), QStringLiteral("image")), true);
    const auto compiled = WorkflowDropCoordinator::compiledPromptFor(oldReply, importReply);

    QVERIFY2(compiled.path.isEmpty(), qPrintable(compiled.path));
    QVERIFY2(compiled.refusal.contains(QStringLiteral("CR Text Concatenate")), qPrintable(compiled.refusal));
}

void WorkflowDropCoordinatorTest::anUnreachableSchemaOpensTheDropInsteadOfRefusingIt()
{
    // object_info_available:false is the worker saying it COULD NOT CHECK. It was briefly treated as
    // a refusal, which is defensible and wrong: "we could not check" is a fact about the machine and
    // "we checked and it is broken" is a fact about the graph, and only the second has nothing to
    // show. The workflow is exactly as readable as it was a minute ago, so the page opens.
    FakeWorker worker;
    worker.replies[QStringLiteral("import_workflow")] = withReadiness(
        importReplyFor(slug_, QStringLiteral("t2i"), QStringLiteral("image")), true);
    worker.replies[QStringLiteral("compile_workflow_prompt")] = unreachableCompileReply();

    Shell shell;
    WorkflowDropCoordinator coordinator;
    coordinator.bind(bindingsFor(worker, shell));
    coordinator.handleDroppedWorkflow(QStringLiteral("D:/drops/asteral.json"));

    QCOMPARE(shell.opens, 1);
    QVERIFY2(shell.refusals.isEmpty(), qPrintable(shell.refusals.join(QStringLiteral(" | "))));
    QCOMPARE(shell.openedMode, QStringLiteral("t2i"));

    // A warning, in the user's words, and not an error.
    bool warned = false;
    for (const QJsonValue &value : shell.openedDraft.value(QStringLiteral("warnings")).toArray())
        warned = warned || value.toString().contains(QStringLiteral("ComfyUI is offline"));
    QVERIFY2(warned, "an offline open has to say why it could not be checked");
}

void WorkflowDropCoordinatorTest::theOfflineDropNeverReadsThePromptApiJsonSittingRightThere()
{
    // The property that must survive widening the path: opening offline is NOT the door the stale
    // artefact comes back through. The file is on disk, it would build a perfectly healthy-looking
    // draft if anyone read it (test_workflow_compile_verdict asserts exactly that), and it is not
    // read. Values offline come from the SOURCE graph or from nowhere.
    const QJsonObject importReply =
        withReadiness(importReplyFor(slug_, QStringLiteral("t2i"), QStringLiteral("image")), true);
    const auto compiled = WorkflowDropCoordinator::compiledPromptFor(unreachableCompileReply(), importReply);

    QVERIFY2(compiled.path.isEmpty(), qPrintable(compiled.path));
    QVERIFY(compiled.refusal.isEmpty());
    QVERIFY(!compiled.unverifiedReason.isEmpty());
    QVERIFY(!compiled.fromStaleFallback);

    FakeWorker worker;
    worker.replies[QStringLiteral("import_workflow")] = importReply;
    worker.replies[QStringLiteral("compile_workflow_prompt")] = unreachableCompileReply();

    Shell shell;
    WorkflowDropCoordinator coordinator;
    coordinator.bind(bindingsFor(worker, shell));
    coordinator.handleDroppedWorkflow(QStringLiteral("D:/drops/asteral.json"));

    QCOMPARE(shell.opens, 1);
    // Present, and still unused -- the difference between "no draft was produced" and "no draft was
    // produced FROM IT".
    QVERIFY(hasCompiledPrompt(slug_));
    const QString carried =
        shell.openedDraft.value(QStringLiteral("compiled_prompt_path")).toString();
    QVERIFY2(!carried.contains(QStringLiteral("prompt_api.json")), qPrintable(carried));
    // And none of that file's values arrived by another route: a UI graph offline yields nothing.
    QVERIFY(!shell.openedDraft.contains(QStringLiteral("steps")));
    QVERIFY(!shell.openedDraft.contains(QStringLiteral("sampler")));
    QVERIFY(!shell.openedDraft.contains(QStringLiteral("prompt")));
}

void WorkflowDropCoordinatorTest::offlineSubmissionStaysClosedEvenWhenReadinessSaysReady()
{
    // Assert the OUTCOME, not a property beside it. Readiness answers READY here -- the models are
    // all on disk, which is a true statement and not a verdict on a graph nobody compiled -- and
    // submission still has to be closed on the draft the cockpit actually reads.
    FakeWorker worker;
    worker.replies[QStringLiteral("import_workflow")] = withReadiness(
        importReplyFor(slug_, QStringLiteral("t2i"), QStringLiteral("image")), true);
    worker.replies[QStringLiteral("compile_workflow_prompt")] = unreachableCompileReply();

    Shell shell;
    WorkflowDropCoordinator coordinator;
    coordinator.bind(bindingsFor(worker, shell));
    coordinator.handleDroppedWorkflow(QStringLiteral("D:/drops/asteral.json"));

    QCOMPARE(shell.opens, 1);
    QVERIFY(shell.openedDraft.contains(QStringLiteral("safe_to_submit")));
    QCOMPARE(shell.openedDraft.value(QStringLiteral("safe_to_submit")).toBool(true), false);
}

void WorkflowDropCoordinatorTest::aRefusalIsStillARefusalWhenTheSchemaFlagAlsoSaysUnreachable()
{
    // The regression guard, and the important one. Widening the offline path must not become a way
    // for a graph with unresolvable classes to open: a reply that NAMES a fault has checked
    // something, whatever it says about reachability, and that is still a refusal with no page.
    QJsonObject reply = refusedCompileReply();
    reply.insert(QStringLiteral("object_info_available"), false);

    QVERIFY(WorkflowDropCoordinator::schemaUnavailableWarning(reply).isEmpty());

    FakeWorker worker;
    worker.replies[QStringLiteral("import_workflow")] = withReadiness(
        importReplyFor(slug_, QStringLiteral("t2i"), QStringLiteral("image")), true);
    worker.replies[QStringLiteral("compile_workflow_prompt")] = reply;

    Shell shell;
    WorkflowDropCoordinator coordinator;
    coordinator.bind(bindingsFor(worker, shell));
    coordinator.handleDroppedWorkflow(QStringLiteral("D:/drops/asteral.json"));

    QCOMPARE(shell.opens, 0);
    QCOMPARE(shell.refusals.size(), 1);
    QVERIFY2(shell.refusals.first().contains(QStringLiteral("CR Text Concatenate")),
             qPrintable(shell.refusals.first()));
}

void WorkflowDropCoordinatorTest::anOfflineApiPromptGraphResolvesToTheGraphAndNotToTheArtefact()
{
    // Offline, the worker can still say WHAT the file is -- that needs no schema -- and a graph that
    // is already an API prompt is readable without one. So this case fills the cockpit properly
    // while still being unverified, and the path it names is the imported graph, never the artefact.
    QJsonObject reply = unreachableCompileReply();
    reply.insert(QStringLiteral("graph_format"), QStringLiteral("comfy_api_prompt"));

    const QJsonObject importReply =
        withReadiness(importReplyFor(slug_, QStringLiteral("t2i"), QStringLiteral("image")), true);
    const auto compiled = WorkflowDropCoordinator::compiledPromptFor(reply, importReply);

    QCOMPARE(compiled.path, QDir(importedWorkflowDir(slug_)).filePath(QStringLiteral("workflow.json")));
    QVERIFY(compiled.refusal.isEmpty());
    QVERIFY(!compiled.unverifiedReason.isEmpty());
    QVERIFY2(!compiled.path.contains(QStringLiteral("prompt_api.json")), qPrintable(compiled.path));
}

void WorkflowDropCoordinatorTest::anApiPromptGraphStillResolvesToTheImportsOwnWorkflowPath()
{
    // Unchanged, and asserted because it is the one legitimate reply with a null path: the graph WAS
    // an API prompt, so nothing was compiled and the source workflow is the prompt.
    QJsonObject apiPrompt;
    apiPrompt.insert(QStringLiteral("type"), QStringLiteral("workflow_compile_result"));
    apiPrompt.insert(QStringLiteral("ok"), true);
    apiPrompt.insert(QStringLiteral("object_info_available"), true);
    apiPrompt.insert(QStringLiteral("graph_format"), QStringLiteral("comfy_api_prompt"));
    apiPrompt.insert(QStringLiteral("missing_classes"), QJsonArray());
    apiPrompt.insert(QStringLiteral("compiled_prompt_path"), QJsonValue());

    const QJsonObject importReply =
        withReadiness(importReplyFor(slug_, QStringLiteral("t2i"), QStringLiteral("image")), true);
    const auto compiled = WorkflowDropCoordinator::compiledPromptFor(apiPrompt, importReply);

    QCOMPARE(compiled.path,
             QDir(importedWorkflowDir(slug_)).filePath(QStringLiteral("workflow.json")));
    QVERIFY(compiled.refusal.isEmpty());
    QVERIFY(!compiled.fromStaleFallback);
}

void WorkflowDropCoordinatorTest::aReplyThatCarriesNothingAtAllStillFallsBackAndSaysSoInTheLog()
{
    // The one case the fallback is still for: a worker older than every field above, which answers
    // nothing at all. The artefact is still a guess, so it is announced rather than used silently.
    const QJsonObject importReply =
        withReadiness(importReplyFor(slug_, QStringLiteral("t2i"), QStringLiteral("image")), true);
    const auto compiled = WorkflowDropCoordinator::compiledPromptFor(QJsonObject(), importReply);

    QCOMPARE(compiled.path, QDir(importedWorkflowDir(slug_)).filePath(QStringLiteral("prompt_api.json")));
    QVERIFY(compiled.refusal.isEmpty());
    QVERIFY(compiled.fromStaleFallback);

    FakeWorker worker;
    worker.replies[QStringLiteral("import_workflow")] = importReply;
    worker.replies[QStringLiteral("compile_workflow_prompt")] = QJsonObject();

    Shell shell;
    WorkflowDropCoordinator coordinator;
    coordinator.bind(bindingsFor(worker, shell));
    coordinator.handleDroppedWorkflow(QStringLiteral("D:/drops/asteral.json"));

    QCOMPARE(shell.opens, 1);
    bool announced = false;
    for (const QString &line : shell.log)
        announced = announced || line.contains(QStringLiteral("recompile the workflow"));
    QVERIFY2(announced, "a fallback to a file of unknown age has to say so, not happen silently");
}

QTEST_MAIN(WorkflowDropCoordinatorTest)
#include "test_workflow_drop_coordinator.moc"
