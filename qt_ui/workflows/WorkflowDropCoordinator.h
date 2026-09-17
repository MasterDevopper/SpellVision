#pragma once

#include "WorkflowDraftBuilder.h"

#include <QJsonObject>
#include <QObject>
#include <QString>
#include <QStringList>

#include <functional>

namespace spellvision::workflows
{

// One dropped workflow, asked of the worker in full.
//
// Every step below already existed. None of them were chained. A dropped workflow was imported and
// then abandoned: the classification the importer returns (inferred_task_command, capability_report,
// supported_modes) was read by nobody, compile_workflow_prompt was never called so there was no
// compiled prompt to extract values from, check_workflow_launch_readiness was called by Flows and
// not by this path, and `safe_to_submit` was the literal `false` with a comment saying the IMPORTER
// reports no readiness -- true of the importer, false of the system.
//
// So the workflow landed on whatever page the mouse happened to be over, with nothing filled in, and
// could not be run. Three answers the app already had, thrown away at the point of use.
//
//     import_workflow                        -- now ALSO answers "can this run here"
//       -> missing nodes or models?          -> the Download dialog, then re-import with consent
//       -> WorkflowLaunchController          -> which page, or a refusal with a reason
//       -> compile_workflow_prompt           -> the API prompt, against the LIVE schema
//       -> WorkflowDraftBuilder              -> the cockpit's values
//       -> open on the resolved page
//
// The readiness verdict rides on the import reply (`launch_readiness`). It used to be a separate
// command that only Flows sent, so this path asked for it a third time; one drop now has ONE author
// for "can this run here", and two workers cannot disagree about the same workflow inside one
// sequence. `check_workflow_launch_readiness` is still sent when the import reply does not carry the
// block -- a worker older than this field -- and that is the only remaining case for it here.
//
// It is a separate unit because MainWindow is a god file and this was a 186-line lambda inside it;
// it is bindings-driven for the same reason WorkerQueueController is -- the decisions can then be
// tested against a fake worker, with no socket and no ComfyUI.
class WorkflowDropCoordinator final : public QObject
{
    Q_OBJECT

public:
    using RequestCompletion =
        std::function<void(const QJsonObject &response, const QString &stderrText, bool startedOk)>;

    // Three answers, not two. "Could not be established" is NOT "not ready" (which would cry wolf on
    // every drop made while ComfyUI is starting) and it is emphatically not "ready" -- the bug this
    // whole path is fixing was an absent signal read as a verdict, and the import reply once fell
    // through to .toBool(true) on an object that was never there and queue-launched regardless.
    enum class Readiness
    {
        Unknown = 0,
        Ready,
        NotReady,
    };

    struct Bindings
    {
        std::function<void(const QJsonObject &request, RequestCompletion completion)> sendRequestAsync;
        std::function<void(const QString &text)> appendLogLine;
        std::function<bool(const QString &modeId)> isModeAvailable;
        // The Download dialog. True when the user accepted it, which is the only thing that may
        // start a fetch. `needsCivitai` / `needsHf` say which HOSTS the missing models come from;
        // whether to ASK for a key is the shell's call, because only it knows what is already stored.
        std::function<bool(const QStringList &missingNodes, const QStringList &missingModels,
                           bool needsCivitai, bool needsHf)> requestDownloads;
        // Extra request fields for the re-import after consent -- the credentials the dialog just
        // collected. Kept as a callback so the coordinator never touches the credential store.
        std::function<QJsonObject()> downloadCredentials;
        std::function<void(const QString &title, const QString &message)> showRefusal;
        std::function<void(const QString &modeId, const QJsonObject &draft)> openDraftOnMode;
        std::function<void(bool busy, const QString &message)> setBusy;
        std::function<void()> refreshWorkflowLibrary;
    };

    explicit WorkflowDropCoordinator(QObject *parent = nullptr);

    void bind(Bindings bindings);

    // The whole sequence, from a path to a page.
    void handleDroppedWorkflow(const QString &path);

    // --- the decisions, each one a pure function so it can be asserted on its own ---

    static QJsonObject buildImportRequest(const QString &path, bool autoApplyNodes, bool autoApplyModels);
    static QJsonObject buildCompileRequest(const QJsonObject &importReply);
    static QJsonObject buildReadinessRequest(const QJsonObject &importReply, const QString &modeId);

    static QString importRoot(const QJsonObject &importReply);
    // Packs already on disk (action=already_installed / already_present) are not missing, whatever
    // missing_custom_nodes says -- that list is an /object_info gap, not an install verdict.
    static QStringList missingNodeNames(const QJsonObject &importReply);
    static QStringList missingModelNames(const QJsonObject &importReply);
    static bool needsCivitaiCredential(const QJsonObject &importReply);
    static bool needsHuggingFaceCredential(const QJsonObject &importReply);

    static Readiness readinessOf(const QJsonObject &readinessReply);
    // The readiness block on the import reply, empty when the worker does not send one.
    static QJsonObject launchReadinessOf(const QJsonObject &importReply);
    // `ready` inside that block, as the same three-state. A block whose `ready` is JSON null -- the
    // worker saying it could not measure the models -- is UNKNOWN, not false and emphatically not
    // true: a UI graph whose model names live in positional widget values once reported READY over
    // `models 0/0 present`, which is a green badge on a workflow nobody had checked.
    static Readiness readinessOfImportReply(const QJsonObject &importReply);

    // What the compile step answered, as outcomes that can be told apart.
    //
    // A REFUSAL and a SILENCE used to be the same thing here: both left `compiled_prompt_path`
    // empty, and the empty-path branch fell back to whatever prompt_api.json happened to sit in the
    // import root. Once the worker began REFUSING a conversion whose node classes it cannot resolve
    // -- replying with a null path on purpose -- that fallback fired in exactly the case where the
    // worker had just said this graph must not be compiled, and answered it with an older file from
    // the same directory. Seven such files exist on this box. They are well-formed JSON carrying a
    // width in a `batch_size` field, so nothing downstream rejects them: they are simply wrong, all
    // the way to a render.
    struct CompiledPrompt
    {
        QString path;                   // empty when there is nothing safe to read
        QString refusal;                // the worker's own sentence; non-empty means NEVER fall back
        // Non-empty means NOBODY CHECKED -- ComfyUI was unreachable. The draft still opens, from the
        // SOURCE graph and never from an artefact, and it is never submittable. See
        // schemaUnavailableWarning below for why this is not the same answer as a refusal.
        QString unverifiedReason;
        bool fromStaleFallback = false; // the path is an artefact of unknown age -- say so out loud
    };

    // "We could not check", which is a fact about the MACHINE. Empty unless the reply says
    // `object_info_available: false` AND names no fault in the graph itself.
    //
    // This used to be folded into compileRefusal, and the two answers are genuinely different. A
    // missing node class is a fact about the GRAPH: something looked, and what it found is broken,
    // so there is nothing to open and the sentence naming the packs is the whole answer. An
    // unreachable ComfyUI is a fact about the machine the user is sitting at -- the workflow is
    // exactly as readable as it was a minute ago, and refusing to show it teaches the user nothing.
    // Folding them together cost offline inspection, which is why they are split.
    //
    // A fault named IN the reply outranks the flag: a worker that reports missing classes while
    // saying it could not reach the schema has checked something, and that is a refusal.
    //
    // The sentence is shared, not re-typed, exactly as compileRefusal is: Flows asks this same
    // function, because one cause must produce one message and two vocabularies for "ComfyUI is
    // down" would start disagreeing on the first user who saw both.
    static QString schemaUnavailableWarning(const QJsonObject &compileReply);

    // The worker's reason there is no prompt AND no point opening one, or empty when it simply did
    // not say. Covers the refusal (`errors` / `missing_classes` / `dangling_links`) and the failure
    // that carries a reason, and names the packs `missing_packs` carries even when the reply sent
    // the arrays without the prose -- a worker older than that field still refuses, and its user
    // still needs to be told what to install. An unreachable schema is NOT in here; it is the third
    // state above.
    static QString compileRefusal(const QJsonObject &compileReply);
    static CompiledPrompt compiledPromptFor(const QJsonObject &compileReply,
                                            const QJsonObject &importReply);
    // The path alone, for callers that only want somewhere to read from. A refusal yields nothing.
    static QString compiledPromptPathFor(const QJsonObject &compileReply, const QJsonObject &importReply);
    static WorkflowDraftBuilder::Source draftSourceFor(const QJsonObject &importReply,
                                                       const QString &compiledPromptPath,
                                                       const QString &modeId);

    // Where `safe_to_submit` stops being a literal. The builder's own verdict is a CEILING -- a draft
    // it already refused to vouch for does not become submittable because readiness said yes.
    static QJsonObject finalizeDraft(QJsonObject draft, Readiness readiness, const QString &readinessSummary);

signals:
    void draftOpened(const QString &modeId);
    void refused(const QString &reason);

private:
    // Carried by value through the async hops, so a second drop cannot overwrite the first one's
    // state halfway through.
    struct DropContext
    {
        QString path;
        QJsonObject importReply;
        QString modeId;
        QString compiledPromptPath;
        // Set when the compile could not run because ComfyUI was unreachable. Carried through the
        // async hops so that `finish` builds an UNVERIFIED draft -- opened, warned about, and closed
        // to submission -- rather than the ordinary one.
        QString unverifiedReason;
    };

    void send(const QJsonObject &request, RequestCompletion completion);
    void log(const QString &text) const;
    void setBusy(bool busy, const QString &message) const;
    void refuse(const QString &reason);

    void onImportReply(const QString &path, bool alreadyOfferedDownloads,
                       const QJsonObject &reply, const QString &stderrText, bool startedOk);
    void continueWithImport(DropContext context);
    void onCompileReply(DropContext context, const QJsonObject &reply);
    void onReadinessReply(DropContext context, const QJsonObject &reply);
    void finish(const DropContext &context, Readiness readiness, const QString &summary,
                const QStringList &missingRuntimeAssets);

    Bindings bindings_;
};

} // namespace spellvision::workflows
