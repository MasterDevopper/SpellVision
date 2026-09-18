#include "WorkflowDropCoordinator.h"

#include "WorkflowLaunchController.h"

#include <QDateTime>
#include <QDir>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonValue>
#include <QPointer>

namespace spellvision::workflows
{
namespace
{

QString stringAt(const QJsonObject &object, const QString &key)
{
    return object.value(key).toString().trimmed();
}

QStringList stringListAt(const QJsonObject &object, const QString &key)
{
    QStringList out;
    for (const QJsonValue &value : object.value(key).toArray())
    {
        const QString text = value.toString().trimmed();
        if (!text.isEmpty())
            out << text;
    }
    return out;
}

QString firstNonEmpty(const QStringList &candidates)
{
    for (const QString &candidate : candidates)
    {
        if (!candidate.trimmed().isEmpty())
            return candidate.trimmed();
    }
    return {};
}

QJsonObject artifactsOf(const QJsonObject &importReply)
{
    return importReply.value(QStringLiteral("artifacts")).toObject();
}

QJsonArray nodeDependencies(const QJsonObject &importReply)
{
    return importReply.value(QStringLiteral("dependency_plan")).toObject()
        .value(QStringLiteral("node_plan")).toObject()
        .value(QStringLiteral("dependencies")).toArray();
}

QJsonArray modelInstallActions(const QJsonObject &importReply)
{
    return importReply.value(QStringLiteral("dependency_plan")).toObject()
        .value(QStringLiteral("model_plan")).toObject()
        .value(QStringLiteral("install_actions")).toArray();
}

// Everything an install action can say about WHERE the file comes from, flattened, so the host sniff
// reads one string instead of four optional ones.
QString installActionHostBlob(const QJsonObject &action)
{
    QString blob = stringAt(action, QStringLiteral("source_value"));
    for (const QJsonValue &note : action.value(QStringLiteral("notes")).toArray())
        blob += note.toString();
    const QJsonObject materialized = action.value(QStringLiteral("materialized")).toObject();
    blob += materialized.value(QStringLiteral("url")).toString();
    blob += materialized.value(QStringLiteral("kind")).toString();
    blob += materialized.value(QStringLiteral("value")).toString();
    return blob;
}

void appendWarning(QJsonObject &draft, const QString &warning)
{
    if (warning.trimmed().isEmpty())
        return;
    QJsonArray warnings = draft.value(QStringLiteral("warnings")).toArray();
    warnings.append(warning.trimmed());
    draft.insert(QStringLiteral("warnings"), warnings);
}

} // namespace

WorkflowDropCoordinator::WorkflowDropCoordinator(QObject *parent)
    : QObject(parent)
{
}

void WorkflowDropCoordinator::bind(Bindings bindings)
{
    bindings_ = std::move(bindings);
}

// --- requests ------------------------------------------------------------------------------------

QJsonObject WorkflowDropCoordinator::buildImportRequest(const QString &path,
                                                        bool autoApplyNodes,
                                                        bool autoApplyModels)
{
    QJsonObject request;
    request.insert(QStringLiteral("command"), QStringLiteral("import_workflow"));
    request.insert(QStringLiteral("source"), path);
    // Default CLOSED on both. Nothing is fetched until the user has seen what would be fetched and
    // said yes, which is the promise the Download dialog makes in so many words.
    request.insert(QStringLiteral("auto_apply_node_deps"), autoApplyNodes);
    request.insert(QStringLiteral("auto_apply_model_deps"), autoApplyModels);
    return request;
}

QString WorkflowDropCoordinator::importRoot(const QJsonObject &importReply)
{
    const QJsonObject artifacts = artifactsOf(importReply);
    const QString root = stringAt(artifacts, QStringLiteral("import_root"));
    if (!root.isEmpty())
        return root;
    // Older replies carry only the file paths; the import root is the directory they sit in.
    const QString profilePath = stringAt(artifacts, QStringLiteral("profile_path"));
    if (!profilePath.isEmpty())
        return QFileInfo(profilePath).absolutePath();
    const QString workflowPath = stringAt(artifacts, QStringLiteral("workflow_path"));
    if (!workflowPath.isEmpty())
        return QFileInfo(workflowPath).absolutePath();
    return {};
}

QJsonObject WorkflowDropCoordinator::buildCompileRequest(const QJsonObject &importReply)
{
    const QJsonObject artifacts = artifactsOf(importReply);
    QJsonObject request;
    request.insert(QStringLiteral("command"), QStringLiteral("compile_workflow_prompt"));
    // The worker resolves the import root from either, and a reply that carries only one of them
    // still has to work.
    request.insert(QStringLiteral("import_root"), importRoot(importReply));
    request.insert(QStringLiteral("profile_path"), stringAt(artifacts, QStringLiteral("profile_path")));
    return request;
}

QJsonObject WorkflowDropCoordinator::buildReadinessRequest(const QJsonObject &importReply,
                                                           const QString &modeId)
{
    const QJsonObject artifacts = artifactsOf(importReply);
    QJsonObject request;
    request.insert(QStringLiteral("command"), QStringLiteral("check_workflow_launch_readiness"));
    request.insert(QStringLiteral("import_root"), importRoot(importReply));
    request.insert(QStringLiteral("profile_path"), stringAt(artifacts, QStringLiteral("profile_path")));
    request.insert(QStringLiteral("workflow_path"), stringAt(artifacts, QStringLiteral("workflow_path")));
    request.insert(QStringLiteral("workflow_task_command"), modeId);
    request.insert(QStringLiteral("workflow_media_type"),
                   stringAt(importReply, QStringLiteral("inferred_media_type")));
    // Flows' copy of this request also sends `ensure_runtime: true`, and nothing on the worker side
    // reads it -- the request-keys-have-readers sweep says so, and it is right. Not carried here: a
    // key that does nothing is a control that does nothing, one caller later.
    return request;
}

// --- what is missing -----------------------------------------------------------------------------

QStringList WorkflowDropCoordinator::missingNodeNames(const QJsonObject &importReply)
{
    QStringList names;
    const QJsonArray dependencies = nodeDependencies(importReply);
    if (!dependencies.isEmpty())
    {
        for (const QJsonValue &value : dependencies)
        {
            const QJsonObject dependency = value.toObject();
            const QString action = stringAt(dependency, QStringLiteral("action"));
            if (action == QStringLiteral("already_installed") || action == QStringLiteral("already_present"))
                continue;
            const QString name = stringAt(dependency, QStringLiteral("class_name"));
            if (!name.isEmpty() && !names.contains(name))
                names << name;
        }
        return names;
    }

    // No dependency plan at all: fall back to the scanner's raw list.
    for (const QJsonValue &value : importReply.value(QStringLiteral("missing_custom_nodes")).toArray())
    {
        const QString name = value.toString().trimmed();
        if (!name.isEmpty() && !names.contains(name))
            names << name;
    }
    return names;
}

QStringList WorkflowDropCoordinator::missingModelNames(const QJsonObject &importReply)
{
    QStringList names;
    for (const QJsonValue &value : modelInstallActions(importReply))
    {
        const QJsonObject action = value.toObject();
        if (stringAt(action, QStringLiteral("kind")) == QStringLiteral("already_present"))
            continue;
        const QString name = stringAt(action, QStringLiteral("source_value"));
        if (!name.isEmpty() && !names.contains(name))
            names << name;
    }
    return names;
}

bool WorkflowDropCoordinator::needsCivitaiCredential(const QJsonObject &importReply)
{
    for (const QJsonValue &value : modelInstallActions(importReply))
    {
        const QJsonObject action = value.toObject();
        if (stringAt(action, QStringLiteral("kind")) == QStringLiteral("already_present"))
            continue;
        if (installActionHostBlob(action).contains(QStringLiteral("civitai"), Qt::CaseInsensitive))
            return true;
    }
    return false;
}

bool WorkflowDropCoordinator::needsHuggingFaceCredential(const QJsonObject &importReply)
{
    for (const QJsonValue &value : modelInstallActions(importReply))
    {
        const QJsonObject action = value.toObject();
        if (stringAt(action, QStringLiteral("kind")) == QStringLiteral("already_present"))
            continue;
        const QString blob = installActionHostBlob(action);
        if (blob.contains(QStringLiteral("huggingface"), Qt::CaseInsensitive)
            || blob.contains(QStringLiteral("hf.co"), Qt::CaseInsensitive))
            return true;
    }
    return false;
}

// --- readiness -----------------------------------------------------------------------------------

QJsonObject WorkflowDropCoordinator::launchReadinessOf(const QJsonObject &importReply)
{
    return importReply.value(QStringLiteral("launch_readiness")).toObject();
}

WorkflowDropCoordinator::Readiness WorkflowDropCoordinator::readinessOfImportReply(const QJsonObject &importReply)
{
    const QJsonObject block = launchReadinessOf(importReply);
    if (block.isEmpty())
        return Readiness::Unknown;
    const QJsonValue ready = block.value(QStringLiteral("ready"));
    // JSON null is the worker's own third answer: it looked and could not tell. Same rule as the
    // command reply, deliberately -- one vocabulary for one question.
    if (!ready.isBool())
        return Readiness::Unknown;
    return ready.toBool() ? Readiness::Ready : Readiness::NotReady;
}

WorkflowDropCoordinator::Readiness WorkflowDropCoordinator::readinessOf(const QJsonObject &readinessReply)
{
    // ABSENT means unknown. Not ready, not unready. The readiness command answers with a bool named
    // `ready`; anything else -- a failed command, a reply from a worker that does not have this
    // command, an import reply that never carried readiness at all -- is the third answer, and the
    // caller keeps submission closed on it.
    if (!readinessReply.value(QStringLiteral("ok")).toBool(false))
        return Readiness::Unknown;
    const QJsonValue ready = readinessReply.value(QStringLiteral("ready"));
    if (!ready.isBool())
        return Readiness::Unknown;
    return ready.toBool() ? Readiness::Ready : Readiness::NotReady;
}

QString WorkflowDropCoordinator::schemaUnavailableWarning(const QJsonObject &compileReply)
{
    const QJsonValue schemaAvailable = compileReply.value(QStringLiteral("object_info_available"));
    if (!schemaAvailable.isBool() || schemaAvailable.toBool())
        return {};

    // A fault the reply NAMES outranks the flag. If classes are missing, links dangle or the
    // converter reported errors, then something did look at this graph and found it broken, and
    // that is a refusal whatever else the reply says about reachability.
    if (!stringListAt(compileReply, QStringLiteral("errors")).isEmpty()
        || !stringListAt(compileReply, QStringLiteral("missing_classes")).isEmpty()
        || !stringListAt(compileReply, QStringLiteral("dangling_links")).isEmpty())
        return {};

    // The user's words, not the worker's. The worker's own sentence ("ComfyUI is not reachable, so
    // node availability could not be checked") is a report; what the user needs is that plus what it
    // means for the page in front of them.
    return QStringLiteral(
        "ComfyUI is offline, so this workflow's nodes and models could not be checked. The values "
        "shown were read from the workflow file itself; nothing has verified that this graph can "
        "run, so it cannot be submitted until ComfyUI is running.");
}

QString WorkflowDropCoordinator::compileRefusal(const QJsonObject &compileReply)
{
    const QStringList errors = stringListAt(compileReply, QStringLiteral("errors"));
    const QStringList missingClasses = stringListAt(compileReply, QStringLiteral("missing_classes"));
    const QStringList dangling = stringListAt(compileReply, QStringLiteral("dangling_links"));
    const QJsonValue ok = compileReply.value(QStringLiteral("ok"));
    const QString said = firstNonEmpty({stringAt(compileReply, QStringLiteral("reason")),
                                        stringAt(compileReply, QStringLiteral("error"))});
    const bool failedWithAReason = ok.isBool() && !ok.toBool() && !said.isEmpty();

    // Not a refusal. "We could not check" is the third state, and it opens -- see
    // schemaUnavailableWarning. It is tested BEFORE failedWithAReason because the offline reply
    // carries `ok: false` and a reason of its own, which would otherwise read as a verdict on the
    // graph. It is tested AFTER the arrays above, which schemaUnavailableWarning re-reads, so a
    // reply that names a genuine fault still refuses.
    if (!schemaUnavailableWarning(compileReply).isEmpty())
        return {};

    if (errors.isEmpty() && missingClasses.isEmpty() && dangling.isEmpty() && !failedWithAReason)
        return {};

    // The worker authors this sentence; it already names the packs and their repository URLs, and
    // one cause must produce one message. Only when it sent none is one assembled here.
    QStringList lines = errors;
    if (lines.isEmpty() && !said.isEmpty())
        lines << said;
    if (lines.isEmpty() && !missingClasses.isEmpty())
        lines << QStringLiteral("This workflow cannot be compiled: the live ComfyUI schema has no "
                                "node class(es): %1.")
                     .arg(missingClasses.join(QStringLiteral(", ")));
    if (lines.isEmpty() && !dangling.isEmpty())
        lines << QStringLiteral("Internal error: the compiled prompt is not self-consistent (%1).")
                     .arg(dangling.join(QStringLiteral("; ")));
    if (lines.isEmpty())
        lines << QStringLiteral("The workflow could not be compiled against the live ComfyUI schema.");

    QString text = lines.join(QStringLiteral("\n"));

    // A reply that carries the pack array but not the prose still has to reach the user with the
    // packs attached -- that list is the whole difference between "something is missing" and
    // "install this repository".
    QStringList packLines;
    for (const QJsonValue &value : compileReply.value(QStringLiteral("missing_packs")).toArray())
    {
        const QJsonObject entry = value.toObject();
        const QString pack = stringAt(entry, QStringLiteral("pack"));
        if (pack.isEmpty() || text.contains(pack))
            continue;
        const QString url = stringAt(entry, QStringLiteral("repo_url"));
        QStringList classes;
        for (const QJsonValue &className : entry.value(QStringLiteral("classes")).toArray())
        {
            const QString name = className.toString().trimmed();
            if (!name.isEmpty())
                classes << name;
        }
        QString line = QStringLiteral("  - ") + pack;
        if (!url.isEmpty())
            line += QStringLiteral(" (") + url + QStringLiteral(")");
        if (!classes.isEmpty())
            line += QStringLiteral(" -- supplies ") + classes.join(QStringLiteral(", "));
        packLines << line;
    }
    if (!packLines.isEmpty())
        text += QStringLiteral("\nThe workflow names the pack(s) it needs:\n")
            + packLines.join(QStringLiteral("\n"));

    return text.trimmed();
}

WorkflowDropCoordinator::CompiledPrompt
WorkflowDropCoordinator::compiledPromptFor(const QJsonObject &compileReply,
                                           const QJsonObject &importReply)
{
    CompiledPrompt compiled;

    // FIRST, before the path is even looked at. A worker older than the refusal still WROTE a
    // prompt_api.json beside its `ok: false`, so a reply can name a path and refuse in the same
    // breath; the refusal is the answer, and the file it points at is the rotten one.
    compiled.refusal = compileRefusal(compileReply);
    if (!compiled.refusal.isEmpty())
        return compiled;

    // SECOND: nobody checked. The graph is not refused -- it is unverified, and it opens. The one
    // thing that must not happen here is the stale-artefact route coming back in through a different
    // door: no prompt_api.json is looked for, and the only file that may be read is the SOURCE graph
    // the user just dropped, and only when that graph is already an API prompt. A UI graph needs the
    // live schema to become one, so offline it yields no values at all -- fewer fields, honestly
    // empty, with the warning saying why.
    compiled.unverifiedReason = schemaUnavailableWarning(compileReply);
    if (!compiled.unverifiedReason.isEmpty())
    {
        if (stringAt(compileReply, QStringLiteral("graph_format")) == QStringLiteral("comfy_api_prompt"))
            compiled.path = stringAt(artifactsOf(importReply), QStringLiteral("workflow_path"));
        return compiled;
    }

    compiled.path = stringAt(compileReply, QStringLiteral("compiled_prompt_path"));
    if (!compiled.path.isEmpty())
        return compiled;

    // The graph was already an API prompt, so compile_workflow_prompt wrote nothing and the source
    // workflow IS the prompt. It reports that with graph_format, and the path is the import's own.
    if (stringAt(compileReply, QStringLiteral("graph_format")) == QStringLiteral("comfy_api_prompt"))
    {
        compiled.path = stringAt(artifactsOf(importReply), QStringLiteral("workflow_path"));
        return compiled;
    }

    // Only here -- a reply that says nothing at all, which is a worker older than every field above.
    // A prompt may still be on disk from an earlier import, and it is a GUESS: nothing in the reply
    // vouches for its age or for the converter that wrote it. It is taken, and it is announced.
    const QString root = importRoot(importReply);
    if (!root.isEmpty())
    {
        const QString candidate = QDir(root).filePath(QStringLiteral("prompt_api.json"));
        if (QFileInfo::exists(candidate))
        {
            compiled.path = candidate;
            compiled.fromStaleFallback = true;
        }
    }
    return compiled;
}

QString WorkflowDropCoordinator::compiledPromptPathFor(const QJsonObject &compileReply,
                                                        const QJsonObject &importReply)
{
    return compiledPromptFor(compileReply, importReply).path;
}

WorkflowDraftBuilder::Source WorkflowDropCoordinator::draftSourceFor(const QJsonObject &importReply,
                                                                      const QString &compiledPromptPath,
                                                                      const QString &modeId)
{
    const QJsonObject artifacts = artifactsOf(importReply);

    WorkflowDraftBuilder::Source source;
    source.displayName = stringAt(importReply, QStringLiteral("import_slug"));
    source.profilePath = stringAt(artifacts, QStringLiteral("profile_path"));
    source.sourceWorkflowPath = stringAt(artifacts, QStringLiteral("workflow_path"));
    source.compiledPromptPath = compiledPromptPath;
    // The source graph only stands in for a compiled prompt when it IS one; the compile step's own
    // answer is what decides that, and it has already been folded into compiledPromptPath.
    source.sourceWorkflowFormat = QStringLiteral("comfy_ui_graph");
    source.modeId = modeId;
    source.mediaType = stringAt(importReply, QStringLiteral("inferred_media_type"));
    source.backend = stringAt(importReply, QStringLiteral("backend_kind"));
    source.missingCustomNodes = missingNodeNames(importReply);
    return source;
}

QJsonObject WorkflowDropCoordinator::finalizeDraft(QJsonObject draft,
                                                   Readiness readiness,
                                                   const QString &readinessSummary)
{
    // The builder's verdict is a ceiling, not a starting point: a draft whose checkpoint could not
    // be inferred is not made submittable by a readiness pass that happens to say yes.
    const bool builderSaidSafe = draft.value(QStringLiteral("safe_to_submit")).toBool(false);

    bool safe = false;
    switch (readiness)
    {
    case Readiness::Ready:
        safe = builderSaidSafe;
        break;
    case Readiness::NotReady:
        appendWarning(draft, readinessSummary.trimmed().isEmpty()
                                 ? QStringLiteral("Launch readiness reported blockers for this workflow. "
                                                  "Review its nodes and models in Flows before generating.")
                                 : readinessSummary);
        break;
    case Readiness::Unknown:
        appendWarning(draft, QStringLiteral(
                                 "Launch readiness could not be established for this workflow, so it is "
                                 "opened for review rather than as ready to run."));
        break;
    }

    draft.insert(QStringLiteral("safe_to_submit"), safe);
    return draft;
}

// --- the sequence --------------------------------------------------------------------------------

void WorkflowDropCoordinator::send(const QJsonObject &request, RequestCompletion completion)
{
    if (bindings_.sendRequestAsync)
        bindings_.sendRequestAsync(request, std::move(completion));
}

void WorkflowDropCoordinator::log(const QString &text) const
{
    if (bindings_.appendLogLine && !text.trimmed().isEmpty())
        bindings_.appendLogLine(text.trimmed());
}

void WorkflowDropCoordinator::setBusy(bool busy, const QString &message) const
{
    if (bindings_.setBusy)
        bindings_.setBusy(busy, message);
}

void WorkflowDropCoordinator::refuse(const QString &reason)
{
    setBusy(false, QString());
    log(reason);
    if (bindings_.showRefusal)
        bindings_.showRefusal(QStringLiteral("Workflow Drop"), reason);
    emit refused(reason);
}

void WorkflowDropCoordinator::handleDroppedWorkflow(const QString &path)
{
    if (!bindings_.sendRequestAsync)
        return;

    setBusy(true, QStringLiteral("Importing workflow…"));
    const QPointer<WorkflowDropCoordinator> guard(this);
    send(buildImportRequest(path, false, false),
         [guard, path](const QJsonObject &reply, const QString &stderrText, bool startedOk) {
             if (guard)
                 guard->onImportReply(path, /*alreadyOfferedDownloads=*/false, reply, stderrText, startedOk);
         });
}

void WorkflowDropCoordinator::onImportReply(const QString &path,
                                             bool alreadyOfferedDownloads,
                                             const QJsonObject &reply,
                                             const QString &stderrText,
                                             bool startedOk)
{
    log(stderrText);

    if (!startedOk || reply.isEmpty() || !reply.value(QStringLiteral("ok")).toBool(false))
    {
        const QString error = reply.value(QStringLiteral("error"))
                                  .toString(QStringLiteral("the worker did not complete the import"));
        refuse(QStringLiteral("This workflow could not be imported: %1").arg(error));
        return;
    }

    const QStringList missingNodes = missingNodeNames(reply);
    const QStringList missingModels = missingModelNames(reply);
    if (!alreadyOfferedDownloads && (!missingNodes.isEmpty() || !missingModels.isEmpty())
        && bindings_.requestDownloads)
    {
        if (bindings_.requestDownloads(missingNodes, missingModels,
                                       needsCivitaiCredential(reply), needsHuggingFaceCredential(reply)))
        {
            log(QStringLiteral("Download requested for missing workflow files."));
            const QPointer<WorkflowDropCoordinator> guard(this);
            QJsonObject retry = buildImportRequest(path, !missingNodes.isEmpty(), !missingModels.isEmpty());
            if (bindings_.downloadCredentials)
            {
                const QJsonObject credentials = bindings_.downloadCredentials();
                for (auto it = credentials.constBegin(); it != credentials.constEnd(); ++it)
                    retry.insert(it.key(), it.value());
            }
            send(retry,
                 [guard, path](const QJsonObject &retry, const QString &retryErr, bool retryOk) {
                     if (!guard)
                         return;
                     // The retry's reply is the one to carry on with -- the old path sent it and then
                     // threw it away, so a successful download still left the draft describing the
                     // pre-download world.
                     guard->onImportReply(path, /*alreadyOfferedDownloads=*/true, retry, retryErr, retryOk);
                 });
            return;
        }
    }

    DropContext context;
    context.path = path;
    context.importReply = reply;
    continueWithImport(context);
}

void WorkflowDropCoordinator::continueWithImport(DropContext context)
{
    // THE resolver, the one task 1 consolidated. Not a second reading of media_type, and not the
    // page the mouse was over.
    const auto resolution = WorkflowLaunchController::modeResolution(
        context.importReply,
        bindings_.isModeAvailable);

    if (!resolution.routable)
    {
        if (bindings_.refreshWorkflowLibrary)
            bindings_.refreshWorkflowLibrary();
        // The resolver's own sentence. A v2v graph is refused here for the same reason and in the
        // same words the draft builder would refuse it, so one cause produces one message.
        refuse(resolution.reason);
        return;
    }

    context.modeId = resolution.modeId;
    log(resolution.reason);

    const QPointer<WorkflowDropCoordinator> guard(this);
    setBusy(true, QStringLiteral("Compiling workflow…"));
    send(buildCompileRequest(context.importReply),
         [guard, context](const QJsonObject &reply, const QString &stderrText, bool) {
             if (!guard)
                 return;
             guard->log(stderrText);
             guard->onCompileReply(context, reply);
         });
}

void WorkflowDropCoordinator::onCompileReply(DropContext context, const QJsonObject &reply)
{
    const CompiledPrompt compiled = compiledPromptFor(reply, context.importReply);

    // "Compiled with N node class(es) missing from the live schema" used to stand here and the
    // sequence carried on. That was the old world's sentence, from when an unresolvable class was a
    // note: there is no such thing as compiling WITH a class missing any more. The worker refuses,
    // and the refusal -- with the packs it names and their repository URLs -- is what the user gets.
    if (!compiled.refusal.isEmpty())
    {
        if (bindings_.refreshWorkflowLibrary)
            bindings_.refreshWorkflowLibrary();
        refuse(compiled.refusal);
        return;
    }

    // Not a refusal: nobody could check. The page opens with whatever the source graph yields, the
    // reason rides into the draft as a warning, and `finish` builds it through the unverified route
    // so that submission is closed by construction rather than by a label.
    context.unverifiedReason = compiled.unverifiedReason;
    if (!context.unverifiedReason.isEmpty())
        log(context.unverifiedReason);

    if (compiled.fromStaleFallback)
    {
        // Never silent. This file was not written by the compile that just ran, and nothing in the
        // reply vouches for the converter that produced it.
        log(QStringLiteral("No compiled prompt came back, so a previously compiled %1 (written %2) "
                           "is being used. Nothing vouches for its age -- recompile the workflow if "
                           "the values look wrong.")
                .arg(compiled.path,
                     QFileInfo(compiled.path).lastModified().toString(Qt::ISODate)));
    }

    context.compiledPromptPath = compiled.path;

    // The import already answered this. Asking a second time inside one drop is not a second
    // opinion -- it is the same function run twice, and two answers to one question is the defect
    // this wave spent task 1 removing one level up. The command survives only for a worker whose
    // import reply does not carry the block at all.
    const QJsonObject readinessBlock = launchReadinessOf(context.importReply);
    if (!readinessBlock.isEmpty())
    {
        QStringList missingAssets;
        for (const QJsonValue &value : readinessBlock.value(QStringLiteral("missing_runtime_assets")).toArray())
        {
            const QString name = value.toString().trimmed();
            if (!name.isEmpty())
                missingAssets << name;
        }
        finish(context, readinessOfImportReply(context.importReply),
               readinessBlock.value(QStringLiteral("summary")).toString(), missingAssets);
        return;
    }

    const QPointer<WorkflowDropCoordinator> guard(this);
    setBusy(true, QStringLiteral("Checking launch readiness…"));
    send(buildReadinessRequest(context.importReply, context.modeId),
         [guard, context](const QJsonObject &readinessReply, const QString &stderrText, bool) {
             if (!guard)
                 return;
             guard->log(stderrText);
             guard->onReadinessReply(context, readinessReply);
         });
}

void WorkflowDropCoordinator::onReadinessReply(DropContext context, const QJsonObject &reply)
{
    QStringList missingAssets;
    for (const QJsonValue &value : reply.value(QStringLiteral("missing_runtime_assets")).toArray())
    {
        const QString name = value.toString().trimmed();
        if (!name.isEmpty())
            missingAssets << name;
    }
    finish(context, readinessOf(reply), reply.value(QStringLiteral("summary")).toString(), missingAssets);
}

void WorkflowDropCoordinator::finish(const DropContext &context,
                                      Readiness readiness,
                                      const QString &summary,
                                      const QStringList &missingRuntimeAssets)
{
    WorkflowDraftBuilder::Source source =
        draftSourceFor(context.importReply, context.compiledPromptPath, context.modeId);
    source.missingRuntimeAssets << missingRuntimeAssets;

    // Two routes, one builder. The unverified route ignores any compiled artefact and never returns
    // a submittable draft, which `finalizeDraft` then keeps as a ceiling -- so a readiness pass that
    // happens to answer "ready" cannot reopen submission on a graph nothing has verified.
    const auto built = context.unverifiedReason.isEmpty()
        ? WorkflowDraftBuilder::build(source)
        : WorkflowDraftBuilder::buildUnverified(source, context.unverifiedReason);
    if (!built.present)
    {
        if (bindings_.refreshWorkflowLibrary)
            bindings_.refreshWorkflowLibrary();
        refuse(built.reason);
        return;
    }

    QJsonObject draft = finalizeDraft(built.draft, readiness, summary);

    setBusy(false, QString());
    if (bindings_.openDraftOnMode)
        bindings_.openDraftOnMode(context.modeId, draft);
    if (bindings_.refreshWorkflowLibrary)
        bindings_.refreshWorkflowLibrary();
    emit draftOpened(context.modeId);
}

} // namespace spellvision::workflows
