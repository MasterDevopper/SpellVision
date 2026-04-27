#include "WorkerCommandRunner.h"

namespace spellvision::workers
{

QString WorkerCommandRunner::submitOrigin(SubmitKind kind)
{
    switch (kind)
    {
    case SubmitKind::Generate:
        return QStringLiteral("generate_button");
    case SubmitKind::Queue:
        return QStringLiteral("queue_button");
    }
    return QStringLiteral("unknown");
}

void WorkerCommandRunner::submit(SubmitKind kind, const Bindings &bindings)
{
    if (!bindings.buildPayload)
        return;

    const QString blockReason = bindings.readinessBlockReason
                                    ? bindings.readinessBlockReason().trimmed()
                                    : QString();

    if (!blockReason.isEmpty() && bindings.showReadinessHint)
        bindings.showReadinessHint(blockReason);

    QJsonObject payload = bindings.buildPayload();
    payload.insert(QStringLiteral("submit_origin"), submitOrigin(kind));
    payload.insert(QStringLiteral("client_readiness_block"), blockReason);
    payload.insert(QStringLiteral("client_video_mode"), bindings.isVideoMode ? bindings.isVideoMode() : false);
    payload.insert(QStringLiteral("client_selected_model"), bindings.selectedModelValue ? bindings.selectedModelValue() : QString());
    payload.insert(QStringLiteral("client_has_video_workflow_binding"), bindings.hasVideoWorkflowBinding ? bindings.hasVideoWorkflowBinding() : false);

    if (kind == SubmitKind::Generate)
    {
        if (bindings.emitGenerate)
            bindings.emitGenerate(payload);
        return;
    }

    if (kind == SubmitKind::Queue && bindings.emitQueue)
        bindings.emitQueue(payload);
}

} // namespace spellvision::workers
