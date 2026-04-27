#include "GenerationStatusController.h"

#include "../workers/WorkerResponseParser.h"

namespace spellvision::generation
{
namespace
{

using WorkerResponseParser = spellvision::workers::WorkerResponseParser;

void setBusyIfBound(const GenerationStatusController::Bindings &bindings, bool busy, const QString &message)
{
    if (!bindings.setBusy)
        return;

    bindings.setBusy(busy, message);
}

void routeOutputIfBound(const GenerationStatusController::Bindings &bindings,
                        const WorkerResponseParser::ParsedMessage &message,
                        const QString &fallbackCaption)
{
    if (!bindings.routeOutput)
        return;

    const QString outputPath = message.outputPath.trimmed();
    if (outputPath.isEmpty())
        return;

    QString caption = message.message.trimmed();
    if (caption.isEmpty())
        caption = fallbackCaption;

    bindings.routeOutput(outputPath, caption);
}

void showProblemIfBound(const GenerationStatusController::Bindings &bindings, const QString &message)
{
    if (!bindings.showProblem)
        return;

    const QString trimmed = message.trimmed();
    if (trimmed.isEmpty())
        return;

    bindings.showProblem(trimmed);
}

QString workerProblemText(const WorkerResponseParser::ParsedMessage &message)
{
    if (!message.errorText.trimmed().isEmpty())
        return message.errorText.trimmed();

    return message.message.trimmed();
}

bool isActiveJobState(WorkerResponseParser::JobState state)
{
    return state == WorkerResponseParser::JobState::Queued ||
           state == WorkerResponseParser::JobState::Starting ||
           state == WorkerResponseParser::JobState::Running;
}

QString progressMessageOrDefault(const WorkerResponseParser::ParsedMessage &message)
{
    const QString trimmed = message.message.trimmed();
    if (!trimmed.isEmpty())
        return trimmed;

    return QStringLiteral("Generation in progress…");
}

} // namespace

void GenerationStatusController::applyWorkerPayload(const QJsonObject &payload, const Bindings &bindings)
{
    const WorkerResponseParser::ParsedMessage message = WorkerResponseParser::parseObject(payload);

    switch (message.kind)
    {
    case WorkerResponseParser::MessageKind::Status:
        if (!message.message.trimmed().isEmpty())
            setBusyIfBound(bindings, true, message.message.trimmed());
        return;

    case WorkerResponseParser::MessageKind::Progress:
        setBusyIfBound(bindings, true, progressMessageOrDefault(message));
        return;

    case WorkerResponseParser::MessageKind::JobUpdate:
        if (message.successfulTerminal)
        {
            setBusyIfBound(bindings, false, QString());
            routeOutputIfBound(bindings, message, QStringLiteral("Generation complete"));
            return;
        }

        if (message.failedTerminal)
        {
            setBusyIfBound(bindings, false, QString());
            showProblemIfBound(bindings, workerProblemText(message));
            return;
        }

        if (message.hasProgress || isActiveJobState(message.jobState))
            setBusyIfBound(bindings, true, progressMessageOrDefault(message));
        return;

    case WorkerResponseParser::MessageKind::Result:
        setBusyIfBound(bindings, false, QString());
        routeOutputIfBound(bindings, message, QStringLiteral("Generation complete"));
        return;

    case WorkerResponseParser::MessageKind::Error:
    case WorkerResponseParser::MessageKind::ClientError:
        setBusyIfBound(bindings, false, QString());
        showProblemIfBound(bindings, workerProblemText(message));
        return;

    case WorkerResponseParser::MessageKind::QueueSnapshot:
    case WorkerResponseParser::MessageKind::QueueAck:
    case WorkerResponseParser::MessageKind::RuntimeStatus:
    case WorkerResponseParser::MessageKind::RuntimeAck:
    case WorkerResponseParser::MessageKind::WorkflowImportResult:
    case WorkerResponseParser::MessageKind::WorkflowProfiles:
    case WorkerResponseParser::MessageKind::Unknown:
    default:
        return;
    }
}

} // namespace spellvision::generation
