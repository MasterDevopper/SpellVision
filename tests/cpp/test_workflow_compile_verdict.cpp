// A compiled prompt is something a compile said, not something a directory contains.
//
// WorkflowLibraryPage.cpp:1873 set `record.compiledPromptPath` to `<import_root>/prompt_api.json`
// unconditionally, on every refresh, for every row. Nothing in that assignment had ever seen a
// compile reply. The path then went to WorkflowDraftBuilder::Source, which reads values out of the
// file and puts them in the cockpit, from where the user renders.
//
// The reason a structural check does not close this: the seven stale artefacts on this box are
// well-formed JSON with no dangling ids. They were written by an older converter whose widget cursor
// did not advance past an input promoted to a link, so they carry a WIDTH in a `batch_size` field.
// Every validator downstream passes them. They are simply wrong.
//
// So the case that matters most is a NEGATIVE asserted against a real one: the file is on disk, it
// would build a perfectly healthy-looking draft if anyone read it, and after the worker refuses the
// compile it is still not read. That is the same shape fe3ad7d asserted for the drop path, and the
// refusal SENTENCE is asserted to be that path's own -- one cause, one message.
//
// Driven by compile replies whose shape was read off python/workflow_library_commands.py and by real
// artefacts under runtime/imported_workflows. No worker, no socket, no ComfyUI.

#include <QtTest>

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonValue>
#include <QString>

#include "shell/ProjectRoot.h"
#include "workflows/WorkflowCompileVerdict.h"
#include "workflows/WorkflowDraftBuilder.h"
#include "workflows/WorkflowDropCoordinator.h"

using spellvision::workflows::WorkflowCompileVerdict;
using spellvision::workflows::WorkflowDraftBuilder;
using spellvision::workflows::WorkflowDropCoordinator;

namespace
{

QString importedWorkflowDir(const QString &slug)
{
    return QDir(QDir(spellvision::shell::resolveProjectRoot())
                    .filePath(QStringLiteral("runtime/imported_workflows")))
        .filePath(slug);
}

QString stalePromptPath(const QString &slug)
{
    return QDir(importedWorkflowDir(slug)).filePath(QStringLiteral("prompt_api.json"));
}

// Exactly what compile_workflow_prompt replies when the converter refuses: a null path ON PURPOSE,
// the classes it could not resolve, and the packs the workflow itself declares for them.
QJsonObject refusedCompileReply()
{
    QJsonObject pack;
    pack.insert(QStringLiteral("pack"), QStringLiteral("ComfyUI_Comfyroll_CustomNodes"));
    pack.insert(QStringLiteral("repo_url"),
                QStringLiteral("https://github.com/Suzie1/ComfyUI_Comfyroll_CustomNodes"));
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

// What compile_workflow_prompt replies when ComfyUI is DOWN: `ok:false`, the flag, an empty
// missing_classes -- it must not claim to know what is missing -- and, because nothing about the
// FILE needs a schema, what kind of graph it is.
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

QJsonObject cleanCompileReply(const QString &slug)
{
    QJsonObject reply;
    reply.insert(QStringLiteral("type"), QStringLiteral("workflow_compile_result"));
    reply.insert(QStringLiteral("ok"), true);
    reply.insert(QStringLiteral("object_info_available"), true);
    reply.insert(QStringLiteral("graph_format"), QStringLiteral("comfy_ui_graph"));
    reply.insert(QStringLiteral("compiled_prompt_path"), stalePromptPath(slug));
    reply.insert(QStringLiteral("missing_classes"), QJsonArray());
    reply.insert(QStringLiteral("errors"), QJsonArray());
    return reply;
}

QJsonObject readJsonObject(const QString &path)
{
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly))
        return {};
    return QJsonDocument::fromJson(file.readAll()).object();
}

// The Source Flows builds for a row, minus the compiled prompt -- which is the whole question.
WorkflowDraftBuilder::Source sourceForImport(const QString &slug)
{
    const QString root = importedWorkflowDir(slug);
    const QJsonObject profile = readJsonObject(QDir(root).filePath(QStringLiteral("profile.json")));

    WorkflowDraftBuilder::Source source;
    source.displayName = profile.value(QStringLiteral("profile_name")).toString(slug);
    source.profilePath = QDir(root).filePath(QStringLiteral("profile.json"));
    source.sourceWorkflowPath = QDir(root).filePath(QStringLiteral("workflow.json"));
    source.sourceWorkflowFormat = QStringLiteral("comfy_ui_graph");
    source.modeId = profile.value(QStringLiteral("task_command")).toString();
    source.mediaType = profile.value(QStringLiteral("media_type")).toString();
    source.backend = profile.value(QStringLiteral("backend_kind")).toString();
    return source;
}

} // namespace

class WorkflowCompileVerdictTest : public QObject
{
    Q_OBJECT

private slots:
    void initTestCase();

    void aRefusedCompileNamesNoPathThoughTheStalePromptIsRightThere();
    void thatSameStaleFileWouldHaveBuiltAPerfectlyHealthyLookingDraft();
    void theRefusalIsTheDropPathsOwnSentenceAndCarriesThePack();
    void anOldWorkerThatNamesAPathBesideItsRefusalIsStillRefused();
    void anUnreachableSchemaIsUnverifiedRatherThanRefused();
    void theOfflineDraftOpensUnsubmittableAndStillDoesNotReadTheStaleFile();
    void bothSurfacesSayTheSameThingAboutAnOfflineComfy();
    void aRefusalSurvivesTheSchemaFlagSayingUnreachable();
    void aCleanCompileVerifiesTheFileItJustWrote();
    void aCleanCompileStillBuildsTheDraftItBuiltBefore();
    void anApiPromptGraphIsItsOwnPromptAndOutranksTheDirectorysOlderFile();
    void silenceIsNotAVerdictAndThereIsNoFallbackHere();
    void theCompileRequestCarriesBothRoots();

private:
    // A real owner t2i import that has a prompt_api.json sitting beside it. Without that file every
    // negative below is vacuous, which initTestCase refuses to let happen quietly.
    QString slug_ = QStringLiteral("asteral-json");
};

void WorkflowCompileVerdictTest::initTestCase()
{
    QVERIFY2(QFileInfo::exists(stalePromptPath(slug_)),
             qPrintable(QStringLiteral("this suite asserts that %1 is NOT read; it must exist")
                            .arg(stalePromptPath(slug_))));
}

// --- 1: the door --------------------------------------------------------------------------------

void WorkflowCompileVerdictTest::aRefusedCompileNamesNoPathThoughTheStalePromptIsRightThere()
{
    const auto compiled =
        WorkflowCompileVerdict::fromCompileReply(refusedCompileReply(),
                                                 QDir(importedWorkflowDir(slug_))
                                                     .filePath(QStringLiteral("workflow.json")));

    QVERIFY2(compiled.path.isEmpty(), qPrintable(compiled.path));
    QVERIFY(!compiled.verified);
    QVERIFY(!compiled.refusal.isEmpty());

    // And the file the old code would have handed over is still sitting there, untouched. Asserting
    // this is the difference between "no draft was produced" and "no draft was produced FROM IT".
    QVERIFY(QFileInfo::exists(stalePromptPath(slug_)));
    QVERIFY2(!compiled.path.contains(QStringLiteral("prompt_api.json")), qPrintable(compiled.path));
}

void WorkflowCompileVerdictTest::thatSameStaleFileWouldHaveBuiltAPerfectlyHealthyLookingDraft()
{
    // The counterweight, and the reason a dangling-id check is not enough. Read the artefact the
    // refusal just declined to use and the extractor is perfectly happy with it -- a present draft,
    // with values, ready for the cockpit. Nothing about the FILE says stop. Only the verdict does.
    WorkflowDraftBuilder::Source source = sourceForImport(slug_);
    source.compiledPromptPath = stalePromptPath(slug_);

    const auto direct = WorkflowDraftBuilder::build(source);
    QVERIFY2(direct.present, qPrintable(direct.reason));
    QVERIFY(!direct.draft.isEmpty());
}

void WorkflowCompileVerdictTest::theRefusalIsTheDropPathsOwnSentenceAndCarriesThePack()
{
    const QJsonObject reply = refusedCompileReply();
    const auto compiled = WorkflowCompileVerdict::fromCompileReply(reply, QString());

    // Not a second vocabulary for the same condition: literally the drop path's function.
    QCOMPARE(compiled.refusal, WorkflowDropCoordinator::compileRefusal(reply));

    // The Python side already resolved the pack to a repository URL. Swallowing that and saying "no
    // compiled prompt is available" is how the user ends up with nowhere to go.
    QVERIFY2(compiled.refusal.contains(QStringLiteral("CR Text Concatenate")), qPrintable(compiled.refusal));
    QVERIFY2(compiled.refusal.contains(QStringLiteral("ComfyUI_Comfyroll_CustomNodes")),
             qPrintable(compiled.refusal));
    QVERIFY2(compiled.refusal.contains(QStringLiteral("https://github.com/Suzie1/ComfyUI_Comfyroll_CustomNodes")),
             qPrintable(compiled.refusal));
}

void WorkflowCompileVerdictTest::anOldWorkerThatNamesAPathBesideItsRefusalIsStillRefused()
{
    // Before the worker learned to refuse, compile_workflow_prompt wrote prompt_api.json
    // UNCONDITIONALLY and replied ok:false beside it. Such a reply names a path and refuses in the
    // same breath, and the file it names is the rotten one -- so the refusal is read first.
    QJsonObject reply = cleanCompileReply(slug_);
    reply.insert(QStringLiteral("ok"), false);
    reply.insert(QStringLiteral("missing_classes"), QJsonArray{QStringLiteral("CR Text Concatenate")});

    const auto compiled = WorkflowCompileVerdict::fromCompileReply(reply, QString());
    QVERIFY2(compiled.path.isEmpty(), qPrintable(compiled.path));
    QVERIFY(!compiled.verified);
    QVERIFY2(compiled.refusal.contains(QStringLiteral("CR Text Concatenate")), qPrintable(compiled.refusal));
}

void WorkflowCompileVerdictTest::anUnreachableSchemaIsUnverifiedRatherThanRefused()
{
    // Not a refusal. Nothing checked this graph, and nothing found it broken -- those are different
    // answers, and only the second has nothing to show. The row still opens; what it may NOT do is
    // claim to be verified, and what it may not read is the artefact in the folder.
    const auto compiled = WorkflowCompileVerdict::fromCompileReply(
        unreachableCompileReply(),
        QDir(importedWorkflowDir(slug_)).filePath(QStringLiteral("workflow.json")));

    QVERIFY2(compiled.refusal.isEmpty(), qPrintable(compiled.refusal));
    QVERIFY(compiled.schemaUnavailable);
    QVERIFY(!compiled.verified);
    QVERIFY2(compiled.unverifiedReason.contains(QStringLiteral("ComfyUI is offline")),
             qPrintable(compiled.unverifiedReason));
    // A UI graph needs the live schema to become a prompt, so offline there is no file to read --
    // and above all not this one, which is sitting right there.
    QVERIFY2(compiled.path.isEmpty(), qPrintable(compiled.path));
    QVERIFY(QFileInfo::exists(stalePromptPath(slug_)));
}

void WorkflowCompileVerdictTest::theOfflineDraftOpensUnsubmittableAndStillDoesNotReadTheStaleFile()
{
    // The Flows row carries the constructed prompt_api.json path on the record, so the builder is
    // handed it on purpose here: an offline open must drop it unread rather than trust the caller.
    WorkflowDraftBuilder::Source source = sourceForImport(slug_);
    source.compiledPromptPath = stalePromptPath(slug_);

    const auto unverified = WorkflowDraftBuilder::buildUnverified(
        source, WorkflowDropCoordinator::schemaUnavailableWarning(unreachableCompileReply()));

    QVERIFY2(unverified.present, qPrintable(unverified.reason));
    QVERIFY(!unverified.safeToSubmit);
    QCOMPARE(unverified.draft.value(QStringLiteral("safe_to_submit")).toBool(true), false);

    // Present, and still unused. thatSameStaleFileWouldHaveBuiltAPerfectlyHealthyLookingDraft above
    // is the counterweight: read it and the extractor is delighted with it.
    QVERIFY(QFileInfo::exists(stalePromptPath(slug_)));
    const QString carried = unverified.draft.value(QStringLiteral("compiled_prompt_path")).toString();
    QVERIFY2(!carried.contains(QStringLiteral("prompt_api.json")), qPrintable(carried));
    QVERIFY(!unverified.draft.contains(QStringLiteral("steps")));
    QVERIFY(!unverified.draft.contains(QStringLiteral("sampler")));

    bool warned = false;
    for (const QJsonValue &value : unverified.draft.value(QStringLiteral("warnings")).toArray())
        warned = warned || value.toString().contains(QStringLiteral("ComfyUI is offline"));
    QVERIFY(warned);
}

void WorkflowCompileVerdictTest::bothSurfacesSayTheSameThingAboutAnOfflineComfy()
{
    // One vocabulary, not two. The drop path and Flows meet the same condition and must hand the
    // user the same sentence -- the same property the refusal already has, asserted the same way,
    // because two wordings for "ComfyUI is down" start disagreeing on the first user who sees both.
    const QJsonObject reply = unreachableCompileReply();

    const auto flows = WorkflowCompileVerdict::fromCompileReply(
        reply, QDir(importedWorkflowDir(slug_)).filePath(QStringLiteral("workflow.json")));
    const auto drop = WorkflowDropCoordinator::compiledPromptFor(reply, QJsonObject());

    QVERIFY(!flows.unverifiedReason.isEmpty());
    QCOMPARE(flows.unverifiedReason, drop.unverifiedReason);
    QCOMPARE(flows.unverifiedReason, WorkflowDropCoordinator::schemaUnavailableWarning(reply));
    QCOMPARE(flows.refusal, drop.refusal);
}

void WorkflowCompileVerdictTest::aRefusalSurvivesTheSchemaFlagSayingUnreachable()
{
    // The regression guard. Widening the offline path must not hand a refused graph a way through:
    // a reply that NAMES a fault has checked something, whatever it says about reachability.
    QJsonObject reply = refusedCompileReply();
    reply.insert(QStringLiteral("object_info_available"), false);

    const auto compiled = WorkflowCompileVerdict::fromCompileReply(
        reply, QDir(importedWorkflowDir(slug_)).filePath(QStringLiteral("workflow.json")));

    QVERIFY(!compiled.schemaUnavailable);
    QVERIFY(!compiled.verified);
    QVERIFY(compiled.path.isEmpty());
    QVERIFY2(compiled.refusal.contains(QStringLiteral("CR Text Concatenate")), qPrintable(compiled.refusal));
}

// --- 2: the regression --------------------------------------------------------------------------

void WorkflowCompileVerdictTest::aCleanCompileVerifiesTheFileItJustWrote()
{
    const auto compiled = WorkflowCompileVerdict::fromCompileReply(cleanCompileReply(slug_), QString());

    QVERIFY(compiled.refusal.isEmpty());
    QVERIFY(compiled.verified);
    QCOMPARE(compiled.path, stalePromptPath(slug_));
}

void WorkflowCompileVerdictTest::aCleanCompileStillBuildsTheDraftItBuiltBefore()
{
    // The same path, the same file, the same draft. What changed is who named the path -- and after
    // a clean compile the file on disk IS the one the compile just wrote.
    WorkflowDraftBuilder::Source before = sourceForImport(slug_);
    before.compiledPromptPath = stalePromptPath(slug_);
    const auto asItWas = WorkflowDraftBuilder::build(before);

    const auto compiled = WorkflowCompileVerdict::fromCompileReply(cleanCompileReply(slug_), QString());
    QVERIFY(compiled.verified);

    WorkflowDraftBuilder::Source after = sourceForImport(slug_);
    after.compiledPromptPath = compiled.path;
    const auto asItIs = WorkflowDraftBuilder::build(after);

    QCOMPARE(asItIs.present, asItWas.present);
    QCOMPARE(asItIs.safeToSubmit, asItWas.safeToSubmit);
    QCOMPARE(asItIs.reason, asItWas.reason);
    QCOMPARE(QJsonDocument(asItIs.draft).toJson(QJsonDocument::Compact),
             QJsonDocument(asItWas.draft).toJson(QJsonDocument::Compact));
}

void WorkflowCompileVerdictTest::anApiPromptGraphIsItsOwnPromptAndOutranksTheDirectorysOlderFile()
{
    // The one legitimate reply with a null path: the graph WAS an API prompt, so nothing was
    // compiled. The answer is the imported graph -- NOT the prompt_api.json beside it, which is the
    // second door the unconditional assignment held open (ensureCompiledPrompt only clears the path
    // for a source the disk walk already decided was an api prompt).
    QJsonObject reply;
    reply.insert(QStringLiteral("type"), QStringLiteral("workflow_compile_result"));
    reply.insert(QStringLiteral("ok"), true);
    reply.insert(QStringLiteral("object_info_available"), true);
    reply.insert(QStringLiteral("graph_format"), QStringLiteral("comfy_api_prompt"));
    reply.insert(QStringLiteral("compiled_prompt_path"), QJsonValue());
    reply.insert(QStringLiteral("missing_classes"), QJsonArray());

    const QString workflowPath = QDir(importedWorkflowDir(slug_)).filePath(QStringLiteral("workflow.json"));
    const auto compiled = WorkflowCompileVerdict::fromCompileReply(reply, workflowPath);

    QVERIFY(compiled.verified);
    QCOMPARE(compiled.path, workflowPath);
    QVERIFY2(compiled.path != stalePromptPath(slug_), qPrintable(compiled.path));
}

// --- 3: silence ---------------------------------------------------------------------------------

void WorkflowCompileVerdictTest::silenceIsNotAVerdictAndThereIsNoFallbackHere()
{
    // The drop path keeps a stale-file fallback for a reply carrying nothing at all, announced in
    // the log; Flows does not, deliberately. The drop path is handed a file the user chose seconds
    // ago; Flows is looking at a directory that has been accumulating artefacts since the workflow
    // was imported, and treating one of them as an answer is the whole defect being closed.
    const auto compiled = WorkflowCompileVerdict::fromCompileReply(
        QJsonObject{},
        QDir(importedWorkflowDir(slug_)).filePath(QStringLiteral("workflow.json")));

    QVERIFY2(compiled.path.isEmpty(), qPrintable(compiled.path));
    QVERIFY(!compiled.verified);
    QVERIFY(compiled.refusal.isEmpty());
    QVERIFY2(!compiled.unverifiedReason.isEmpty(), "an unanswered question must still say something");
    QVERIFY(QFileInfo::exists(stalePromptPath(slug_)));
}

void WorkflowCompileVerdictTest::theCompileRequestCarriesBothRoots()
{
    // The worker resolves the import root from either key, and a Flows row that carries only one of
    // them still has to work.
    const QJsonObject request = WorkflowCompileVerdict::buildCompileRequest(
        QStringLiteral("  D:/imports/asteral-json  "),
        QStringLiteral("D:/imports/asteral-json/profile.json"));

    QCOMPARE(request.value(QStringLiteral("command")).toString(), QStringLiteral("compile_workflow_prompt"));
    QCOMPARE(request.value(QStringLiteral("import_root")).toString(), QStringLiteral("D:/imports/asteral-json"));
    QCOMPARE(request.value(QStringLiteral("profile_path")).toString(),
             QStringLiteral("D:/imports/asteral-json/profile.json"));
}

QTEST_MAIN(WorkflowCompileVerdictTest)
#include "test_workflow_compile_verdict.moc"
