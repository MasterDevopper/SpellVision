#include "WorkerSubmissionPolicy.h"

#include <QFileInfo>
#include <QJsonValue>

namespace spellvision::workers
{

QString WorkerSubmissionPolicy::firstStackString(const QJsonObject &stack, const QStringList &keys)
{
    for (const QString &key : keys)
    {
        const QString value = stack.value(key).toString().trimmed();
        if (!value.isEmpty())
            return value;
    }
    return QString();
}

QJsonObject WorkerSubmissionPolicy::videoStackFromPayload(const QJsonObject &payload)
{
    const QJsonValue videoStackValue = payload.value(QStringLiteral("video_model_stack"));
    if (videoStackValue.isObject())
        return videoStackValue.toObject();

    const QJsonValue modelStackValue = payload.value(QStringLiteral("model_stack"));
    if (modelStackValue.isObject())
        return modelStackValue.toObject();

    return {};
}

QString WorkerSubmissionPolicy::resolvedModelValueFromPayload(const QJsonObject &payload)
{
    const QString modelValue = payload.value(QStringLiteral("model")).toString().trimmed();
    if (!modelValue.isEmpty())
        return modelValue;

    const QJsonObject stack = videoStackFromPayload(payload);
    if (stack.isEmpty())
        return QString();

    return firstStackString(stack,
                            {QStringLiteral("diffusers_path"),
                             QStringLiteral("model_dir"),
                             QStringLiteral("model_directory"),
                             QStringLiteral("primary_path"),
                             QStringLiteral("transformer_path"),
                             QStringLiteral("unet_path"),
                             QStringLiteral("model_path")});
}

bool WorkerSubmissionPolicy::hasNativeVideoStackPayload(const QJsonObject &payload)
{
    const QJsonObject stack = videoStackFromPayload(payload);
    if (!stack.isEmpty())
        return true;

    return !payload.value(QStringLiteral("native_video_stack_kind")).toString().trimmed().isEmpty();
}

bool WorkerSubmissionPolicy::hasWorkflowBinding(const QJsonObject &payload)
{
    return !payload.value(QStringLiteral("workflow_profile_path")).toString().trimmed().isEmpty() ||
           !payload.value(QStringLiteral("workflow_path")).toString().trimmed().isEmpty() ||
           !payload.value(QStringLiteral("compiled_prompt_path")).toString().trimmed().isEmpty();
}

QString WorkerSubmissionPolicy::videoSubmitLogLine(const QString &modeId,
                                                   const QJsonObject &payload,
                                                   const QString &modelValue,
                                                   bool hasNativeVideoStack,
                                                   bool hasWorkflowBinding)
{
    const QString origin = payload.value(QStringLiteral("submit_origin")).toString().trimmed();
    return QStringLiteral("%1 submit received%2 • model=%3 • stack=%4 • workflow=%5")
        .arg(modeId.toUpper(),
             origin.isEmpty() ? QString() : QStringLiteral(" from %1").arg(origin),
             modelValue.isEmpty() ? QStringLiteral("none") : QFileInfo(modelValue).fileName(),
             hasNativeVideoStack ? QStringLiteral("yes") : QStringLiteral("no"),
             hasWorkflowBinding ? QStringLiteral("yes") : QStringLiteral("no"));
}

QString WorkerSubmissionPolicy::missingModelMessage(const QString &modeId, bool videoMode)
{
    if (videoMode)
        return QStringLiteral("%1 request blocked: choose a native video model stack or open an imported workflow draft.").arg(modeId.toUpper());

    return QStringLiteral("%1 request blocked: choose a model first.").arg(modeId.toUpper());
}

QString WorkerSubmissionPolicy::acceptedRequestLogLine(const QString &modeId,
                                                       bool videoMode,
                                                       bool hasWorkflowBinding,
                                                       const QString &modelValue)
{
    const QString backendSummary = videoMode
                                       ? (hasWorkflowBinding ? QStringLiteral("workflow video") : QStringLiteral("native video"))
                                       : QStringLiteral("native image");

    return QStringLiteral("%1 request accepted: %2 • model=%3")
        .arg(modeId.toUpper(),
             backendSummary,
             modelValue.isEmpty() ? QStringLiteral("workflow-bound") : QFileInfo(modelValue).fileName());
}

} // namespace spellvision::workers
