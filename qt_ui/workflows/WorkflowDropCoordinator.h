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
//     import_workflow
//       -> missing nodes or models?          -> the Download dialog, then re-import with consent
//       -> WorkflowLaunchController          -> which page, or a refusal with a reason
//       -> compile_workflow_prompt           -> the API prompt, against the LIVE schema
//       -> check_workflow_launch_readiness   -> can this actually run here
//       -> WorkflowDraftBuilder              -> the cockpit's values
//       -> open on the resolved page
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

    Bindings bindings_;
};

} // namespace spellvision::workflows
