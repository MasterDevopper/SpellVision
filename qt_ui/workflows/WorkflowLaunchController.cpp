#include "WorkflowLaunchController.h"

#include "shell/ShellNavigationController.h"

#include <QDir>
#include <QJsonValue>
#include <QSet>
#include <QStringList>

namespace spellvision::workflows
{
namespace
{

// The modes a workflow can actually be opened on. Deliberately a SET rather than "anything that is
// not obviously wrong": v2v and audio are real verdicts the worker produces (four of the 88 imported
// profiles in this tree are v2v) and neither has a page, so both have to fall out here rather than
// be quietly rounded to the nearest video mode -- which is what happened when media_type decided.
const QSet<QString> &routableModes()
{
    static const QSet<QString> modes = {
        QStringLiteral("t2i"),
        QStringLiteral("i2i"),
        QStringLiteral("t2v"),
        QStringLiteral("i2v"),
        QStringLiteral("character"),
        QStringLiteral("comic"),
        QStringLiteral("concept"),
    };
    return modes;
}

// "unknown" is the worker's way of saying it could not tell (workflow_scanner's primary_task default),
// so it is an ABSENT answer, not a verdict to route on.
bool isAbsentVerdict(const QString &verdict)
{
    return verdict.isEmpty()
        || verdict == QStringLiteral("unknown")
        || verdict == QStringLiteral("none");
}

QString firstString(const QJsonObject &object, const QStringList &keys)
{
    for (const QString &key : keys)
    {
        const QString value = object.value(key).toString().trimmed();
        if (!value.isEmpty())
            return value;
    }
    return QString();
}

double firstDouble(const QJsonObject &object, const QStringList &keys)
{
    for (const QString &key : keys)
    {
        const QJsonValue value = object.value(key);
        if (value.isDouble())
            return value.toDouble();
    }
    return -1.0;
}

// A profile keeps the capability report at the top level; a re-saved one also keeps a copy under
// `metadata`, and the import reply puts it at the top level too. Same report, three homes.
QJsonObject capabilityReport(const QJsonObject &source)
{
    const QJsonObject direct = source.value(QStringLiteral("capability_report")).toObject();
    if (!direct.isEmpty())
        return direct;
    return source.value(QStringLiteral("metadata")).toObject()
        .value(QStringLiteral("capability_report")).toObject();
}

} // namespace

QString WorkflowLaunchController::normalizeModeId(const QString &modeId)
{
    QString normalized = modeId.trimmed().toLower();
    // Separators are noise: the worker writes "t2i", a profile may carry "text_to_image", a UI label
    // "Text-To-Image" and WorkflowLibraryPage's own pass strips them to "texttoimage". One spelling.
    normalized.remove(QLatin1Char(' '));
    normalized.remove(QLatin1Char('_'));
    normalized.remove(QLatin1Char('-'));

    if (normalized == QStringLiteral("texttoimage"))
        return QStringLiteral("t2i");
    if (normalized == QStringLiteral("imagetoimage"))
        return QStringLiteral("i2i");
    if (normalized == QStringLiteral("texttovideo"))
        return QStringLiteral("t2v");
    if (normalized == QStringLiteral("imagetovideo"))
        return QStringLiteral("i2v");
    if (normalized == QStringLiteral("videotovideo"))
        return QStringLiteral("v2v");
    if (normalized == QStringLiteral("characterstudio"))
        return QStringLiteral("character");
    if (normalized == QStringLiteral("comicstudio"))
        return QStringLiteral("comic");
    if (normalized == QStringLiteral("conceptreference") || normalized == QStringLiteral("conceptlab"))
        return QStringLiteral("concept");

    return normalized;
}

WorkflowLaunchController::ModeResolution
WorkflowLaunchController::modeResolution(const QJsonObject &source, const ModeAvailability &isModeAvailable)
{
    ModeResolution resolution;

    const QJsonObject capability = capabilityReport(source);
    const double recorded = firstDouble(source, {QStringLiteral("classification_confidence"),
                                                 QStringLiteral("confidence")});
    const double fromReport = firstDouble(capability, {QStringLiteral("confidence")});
    resolution.confidence = recorded >= 0.0 ? recorded : (fromReport >= 0.0 ? fromReport : 0.0);

    // Precedence, highest first. Every one of these is a verdict somebody DECIDED -- the owner, or
    // the worker's output-based classifier. None of them is read off a filename.
    QString verdict;
    QString origin;

    // 1. The owner's own correction. Flows lets a misclassification be overridden, and an override
    //    that the consolidation dropped would silently un-fix every workflow it had been used on.
    verdict = normalizeModeId(firstString(source, {QStringLiteral("user_task_override"),
                                                   QStringLiteral("task_override")}));
    if (!isAbsentVerdict(verdict))
    {
        origin = QStringLiteral("an override you set");
        // Not an inference, so the classifier's number does not describe it.
        resolution.confidence = 1.0;
    }
    else
    {
        // 2. The importer's verdict, as it comes back on the import reply.
        verdict = normalizeModeId(firstString(source, {QStringLiteral("inferred_task_command")}));
        origin = QStringLiteral("the importer's classification of what this graph outputs");

        // 3. The capability report, which is where a profile on disk keeps the same answer.
        if (isAbsentVerdict(verdict))
        {
            verdict = normalizeModeId(firstString(capability, {QStringLiteral("primary_task"),
                                                               QStringLiteral("task_command"),
                                                               QStringLiteral("mode_id"),
                                                               QStringLiteral("task")}));
            origin = QStringLiteral("the workflow's capability report");
        }

        // 4. The verdict already written onto the profile / draft by a previous import.
        if (isAbsentVerdict(verdict))
        {
            verdict = normalizeModeId(firstString(source, {QStringLiteral("task_command"),
                                                           QStringLiteral("workflow_task_command"),
                                                           QStringLiteral("task_type"),
                                                           QStringLiteral("mode_id"),
                                                           QStringLiteral("mode"),
                                                           QStringLiteral("task")}));
            origin = QStringLiteral("the task recorded on this workflow");
        }
    }

    // 5. There is no step 5. The old Home resolver's next move was to look for "t2i"/"i2v"/... inside
    //    workflow_path, workflow_source, name and profile_name, and then to answer t2i regardless --
    //    so an unclassified graph opened a cockpit chosen by its filename. Refusing is the fix: a
    //    refusal can be explained, a wrong page cannot.
    if (isAbsentVerdict(verdict))
    {
        resolution.confidence = 0.0;
        resolution.reason = QStringLiteral(
            "This workflow has no classification, so there is no way to tell which generation it is. "
            "Re-import it, or set its task by hand in Flows. It will not be routed by its filename.");
        return resolution;
    }

    resolution.verdict = verdict;

    if (shell::ShellNavigationController::isModeHidden(verdict))
    {
        resolution.reason = QStringLiteral(
            "This workflow is a %1 workflow, and %1 is not available in this build -- there is no "
            "page to open it on.").arg(verdict);
        return resolution;
    }

    if (!routableModes().contains(verdict))
    {
        resolution.reason = QStringLiteral(
            "This workflow is classified as %1, which has no generation page in SpellVision. "
            "It can be inspected in Flows, but not opened as a draft.").arg(verdict);
        return resolution;
    }

    if (isModeAvailable && !isModeAvailable(verdict))
    {
        resolution.reason = QStringLiteral(
            "This workflow is a %1 workflow and %1 is not available here, so it is not being opened "
            "somewhere else instead.").arg(verdict);
        return resolution;
    }

    resolution.modeId = verdict;
    resolution.routable = true;
    resolution.reason = QStringLiteral("Opening on %1, from %2.").arg(verdict.toUpper(), origin);
    return resolution;
}

QString WorkflowLaunchController::resolveModeId(const QJsonObject &source,
                                                const ModeAvailability &isModeAvailable)
{
    return modeResolution(source, isModeAvailable).modeId;
}

QString WorkflowLaunchController::resolveDraftModeId(const QJsonObject &draft,
                                                     const ModeAvailability &isModeAvailable)
{
    // A draft is one more spelling of the same question, so it asks the same resolver. It used to
    // answer an unavailable or unclassified draft with defaultModeForMedia() -- a guess from
    // media_type that landed a graph on a page it was never classified for.
    return resolveModeId(draft, isModeAvailable);
}

QString WorkflowLaunchController::draftSourceName(const QJsonObject &draft)
{
    const QString sourceName = draft.value(QStringLiteral("source_name")).toString().trimmed();
    return sourceName.isEmpty() ? QStringLiteral("workflow") : sourceName;
}

QString WorkflowLaunchController::draftOpenedLogLine(const QJsonObject &draft, const QString &modeId)
{
    return QStringLiteral("Workflow draft opened: %1 -> %2")
        .arg(draftSourceName(draft), modeId.toUpper());
}

QString WorkflowLaunchController::draftRequiresReviewLogLine(const QString &modeId)
{
    return QStringLiteral("Draft requires review before submission on %1.")
        .arg(modeId.toUpper());
}

QJsonObject WorkflowLaunchController::buildWorkflowLaunchRequest(const QJsonObject &profile,
                                                                 const QString &projectRoot,
                                                                 const QString &pythonExecutable)
{
    QJsonObject request;
    request.insert(QStringLiteral("command"), QStringLiteral("launch_workflow"));
    request.insert(QStringLiteral("profile"), profile);
    request.insert(QStringLiteral("project_root"), QDir::fromNativeSeparators(projectRoot));
    request.insert(QStringLiteral("python_executable"), QDir::fromNativeSeparators(pythonExecutable));

    const QString profilePath = profile.value(QStringLiteral("profile_path")).toString().trimmed();
    if (!profilePath.isEmpty())
        request.insert(QStringLiteral("profile_path"), QDir::fromNativeSeparators(profilePath));

    const QString workflowPath = profile.value(QStringLiteral("workflow_path")).toString().trimmed();
    if (!workflowPath.isEmpty())
        request.insert(QStringLiteral("workflow_path"), QDir::fromNativeSeparators(workflowPath));

    const QString compiledPromptPath = profile.value(QStringLiteral("compiled_prompt_path")).toString().trimmed();
    if (!compiledPromptPath.isEmpty())
        request.insert(QStringLiteral("compiled_prompt_path"), QDir::fromNativeSeparators(compiledPromptPath));

    return request;
}

} // namespace spellvision::workflows
