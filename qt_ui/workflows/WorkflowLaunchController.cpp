#include "WorkflowLaunchController.h"

#include <QDir>

namespace spellvision::workflows
{

QString WorkflowLaunchController::normalizeModeId(const QString &modeId)
{
    const QString normalized = modeId.trimmed().toLower();

    if (normalized == QStringLiteral("texttoimage"))
        return QStringLiteral("t2i");
    if (normalized == QStringLiteral("imagetoimage"))
        return QStringLiteral("i2i");
    if (normalized == QStringLiteral("texttovideo"))
        return QStringLiteral("t2v");
    if (normalized == QStringLiteral("imagetovideo"))
        return QStringLiteral("i2v");

    return normalized;
}

QString WorkflowLaunchController::defaultModeForMedia(const QString &mediaType, bool hasInputImage)
{
    const QString media = mediaType.trimmed().toLower();

    if (media == QStringLiteral("image"))
        return hasInputImage ? QStringLiteral("i2i") : QStringLiteral("t2i");
    if (media == QStringLiteral("video"))
        return hasInputImage ? QStringLiteral("i2v") : QStringLiteral("t2v");

    return QString();
}

QString WorkflowLaunchController::resolveDraftModeId(const QJsonObject &draft, const ModeAvailability &isModeAvailable)
{
    const QString mediaType = draft.value(QStringLiteral("media_type")).toString().trimmed().toLower();
    const bool hasInputImage = !draft.value(QStringLiteral("input_image")).toString().trimmed().isEmpty();

    QString modeId = normalizeModeId(draft.value(QStringLiteral("mode_id")).toString());

    if (modeId.isEmpty())
        modeId = defaultModeForMedia(mediaType, hasInputImage);

    const auto available = [&isModeAvailable](const QString &candidate) {
        if (candidate.trimmed().isEmpty())
            return false;
        return isModeAvailable ? isModeAvailable(candidate) : true;
    };

    if (available(modeId))
        return modeId;

    const QString fallback = defaultModeForMedia(mediaType, hasInputImage);
    if (available(fallback))
        return fallback;

    return modeId;
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
