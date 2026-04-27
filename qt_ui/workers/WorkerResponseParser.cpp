#include "WorkerResponseParser.h"

#include <QJsonDocument>
#include <QJsonValue>
#include <QStringList>
#include <QtGlobal>

namespace spellvision::workers
{

namespace
{
QString normalizedType(const QJsonObject &payload)
{
    return payload.value(QStringLiteral("type")).toString().trimmed().toLower();
}

QString normalizedState(const QJsonObject &payload)
{
    return payload.value(QStringLiteral("state")).toString().trimmed().toLower();
}

int boundedPercent(int value)
{
    if (value < 0)
        return -1;
    return qBound(0, value, 100);
}

int percentFromProgressObject(const QJsonObject &progress)
{
    if (progress.contains(QStringLiteral("percent")))
        return boundedPercent(progress.value(QStringLiteral("percent")).toInt(-1));

    const int current = progress.value(QStringLiteral("current")).toInt(-1);
    const int total = progress.value(QStringLiteral("total")).toInt(-1);
    if (current < 0 || total <= 0)
        return -1;

    return boundedPercent(qRound((static_cast<double>(current) / static_cast<double>(total)) * 100.0));
}
} // namespace

WorkerResponseParser::ParsedMessage WorkerResponseParser::parseJsonLine(const QByteArray &line, QString *parseError)
{
    if (parseError)
        parseError->clear();

    const QByteArray trimmed = line.trimmed();
    if (trimmed.isEmpty())
    {
        if (parseError)
            *parseError = QStringLiteral("empty worker message");
        return ParsedMessage{};
    }

    QJsonParseError error;
    const QJsonDocument document = QJsonDocument::fromJson(trimmed, &error);
    if (error.error != QJsonParseError::NoError || !document.isObject())
    {
        if (parseError)
            *parseError = error.errorString();
        return ParsedMessage{};
    }

    return parseObject(document.object());
}

WorkerResponseParser::ParsedMessage WorkerResponseParser::parseObject(const QJsonObject &payload)
{
    ParsedMessage parsed;
    parsed.raw = payload;
    parsed.kind = kindFromString(normalizedType(payload));
    parsed.jobState = stateFromString(normalizedState(payload));
    parsed.terminal = isTerminalState(parsed.jobState);
    parsed.successfulTerminal = isSuccessfulTerminal(parsed.jobState);
    parsed.failedTerminal = isFailedTerminal(parsed.jobState);

    applyOk(parsed, payload);
    applyJobIdentity(parsed, payload);
    applyProgress(parsed, payload);
    applyResult(parsed, payload);
    applyError(parsed, payload);

    if (parsed.message.isEmpty())
    {
        parsed.message = firstStringValue(payload, {
            QStringLiteral("message"),
            QStringLiteral("status"),
            QStringLiteral("detail"),
        });
    }

    return parsed;
}

WorkerResponseParser::MessageKind WorkerResponseParser::kindFromString(const QString &value)
{
    const QString kind = value.trimmed().toLower();
    if (kind == QStringLiteral("status"))
        return MessageKind::Status;
    if (kind == QStringLiteral("progress"))
        return MessageKind::Progress;
    if (kind == QStringLiteral("result"))
        return MessageKind::Result;
    if (kind == QStringLiteral("error"))
        return MessageKind::Error;
    if (kind == QStringLiteral("job_update"))
        return MessageKind::JobUpdate;
    if (kind == QStringLiteral("queue_snapshot"))
        return MessageKind::QueueSnapshot;
    if (kind == QStringLiteral("queue_ack"))
        return MessageKind::QueueAck;
    if (kind == QStringLiteral("comfy_runtime_status"))
        return MessageKind::RuntimeStatus;
    if (kind == QStringLiteral("comfy_runtime_ack"))
        return MessageKind::RuntimeAck;
    if (kind == QStringLiteral("workflow_import_result"))
        return MessageKind::WorkflowImportResult;
    if (kind == QStringLiteral("workflow_profiles"))
        return MessageKind::WorkflowProfiles;
    if (kind == QStringLiteral("client_error"))
        return MessageKind::ClientError;
    return MessageKind::Unknown;
}

WorkerResponseParser::JobState WorkerResponseParser::stateFromString(const QString &value)
{
    const QString state = value.trimmed().toLower();
    if (state == QStringLiteral("queued"))
        return JobState::Queued;
    if (state == QStringLiteral("starting"))
        return JobState::Starting;
    if (state == QStringLiteral("running"))
        return JobState::Running;
    if (state == QStringLiteral("completed"))
        return JobState::Completed;
    if (state == QStringLiteral("failed"))
        return JobState::Failed;
    if (state == QStringLiteral("cancelled") || state == QStringLiteral("canceled"))
        return JobState::Cancelled;
    return JobState::Unknown;
}

bool WorkerResponseParser::isTerminalState(JobState state)
{
    return state == JobState::Completed || state == JobState::Failed || state == JobState::Cancelled;
}

bool WorkerResponseParser::isSuccessfulTerminal(JobState state)
{
    return state == JobState::Completed;
}

bool WorkerResponseParser::isFailedTerminal(JobState state)
{
    return state == JobState::Failed || state == JobState::Cancelled;
}

QString WorkerResponseParser::kindName(MessageKind kind)
{
    switch (kind)
    {
    case MessageKind::Status: return QStringLiteral("status");
    case MessageKind::Progress: return QStringLiteral("progress");
    case MessageKind::Result: return QStringLiteral("result");
    case MessageKind::Error: return QStringLiteral("error");
    case MessageKind::JobUpdate: return QStringLiteral("job_update");
    case MessageKind::QueueSnapshot: return QStringLiteral("queue_snapshot");
    case MessageKind::QueueAck: return QStringLiteral("queue_ack");
    case MessageKind::RuntimeStatus: return QStringLiteral("comfy_runtime_status");
    case MessageKind::RuntimeAck: return QStringLiteral("comfy_runtime_ack");
    case MessageKind::WorkflowImportResult: return QStringLiteral("workflow_import_result");
    case MessageKind::WorkflowProfiles: return QStringLiteral("workflow_profiles");
    case MessageKind::ClientError: return QStringLiteral("client_error");
    case MessageKind::Unknown:
    default: return QStringLiteral("unknown");
    }
}

QString WorkerResponseParser::stateName(JobState state)
{
    switch (state)
    {
    case JobState::Queued: return QStringLiteral("queued");
    case JobState::Starting: return QStringLiteral("starting");
    case JobState::Running: return QStringLiteral("running");
    case JobState::Completed: return QStringLiteral("completed");
    case JobState::Failed: return QStringLiteral("failed");
    case JobState::Cancelled: return QStringLiteral("cancelled");
    case JobState::Unknown:
    default: return QStringLiteral("unknown");
    }
}

void WorkerResponseParser::applyOk(ParsedMessage &message, const QJsonObject &payload)
{
    if (!payload.contains(QStringLiteral("ok")))
        return;

    message.hasOk = true;
    message.ok = payload.value(QStringLiteral("ok")).toBool(false);
}

void WorkerResponseParser::applyJobIdentity(ParsedMessage &message, const QJsonObject &payload)
{
    message.jobId = firstStringValue(payload, {
        QStringLiteral("job_id"),
        QStringLiteral("worker_job_id"),
        QStringLiteral("source_job_id"),
    });
}

void WorkerResponseParser::applyProgress(ParsedMessage &message, const QJsonObject &payload)
{
    QJsonObject progressObject;
    if (payload.value(QStringLiteral("progress")).isObject())
        progressObject = payload.value(QStringLiteral("progress")).toObject();

    if (!progressObject.isEmpty())
    {
        message.progress = progressObject;
        message.hasProgress = true;
        message.progressCurrent = progressObject.value(QStringLiteral("current")).toInt(-1);
        message.progressTotal = progressObject.value(QStringLiteral("total")).toInt(-1);
        message.progressPercent = percentFromProgressObject(progressObject);
        message.message = progressObject.value(QStringLiteral("message")).toString().trimmed();
        return;
    }

    if (payload.contains(QStringLiteral("percent")) || payload.contains(QStringLiteral("step")) || payload.contains(QStringLiteral("total")))
    {
        message.hasProgress = true;
        message.progressCurrent = payload.value(QStringLiteral("step")).toInt(payload.value(QStringLiteral("current")).toInt(-1));
        message.progressTotal = payload.value(QStringLiteral("total")).toInt(-1);
        message.progressPercent = boundedPercent(payload.value(QStringLiteral("percent")).toInt(-1));
    }
}

void WorkerResponseParser::applyResult(ParsedMessage &message, const QJsonObject &payload)
{
    if (payload.value(QStringLiteral("result")).isObject())
        message.result = payload.value(QStringLiteral("result")).toObject();
    else if (message.kind == MessageKind::Result)
        message.result = payload;

    const QJsonObject source = message.result.isEmpty() ? payload : message.result;
    message.outputPath = firstStringValue(source, {
        QStringLiteral("output"),
        QStringLiteral("output_path"),
        QStringLiteral("image_path"),
        QStringLiteral("video_path"),
        QStringLiteral("path"),
    });

    message.metadataPath = firstStringValue(source, {
        QStringLiteral("metadata_output"),
        QStringLiteral("metadata_path"),
    });
}

void WorkerResponseParser::applyError(ParsedMessage &message, const QJsonObject &payload)
{
    const QJsonValue errorValue = payload.value(QStringLiteral("error"));
    if (errorValue.isObject())
    {
        message.error = errorValue.toObject();
        message.errorText = firstStringValue(message.error, {
            QStringLiteral("message"),
            QStringLiteral("error"),
            QStringLiteral("details"),
        });
        return;
    }

    if (errorValue.isString())
    {
        message.errorText = errorValue.toString().trimmed();
        return;
    }

    if (message.kind == MessageKind::ClientError)
    {
        message.errorText = firstStringValue(payload, {
            QStringLiteral("message"),
            QStringLiteral("error"),
            QStringLiteral("details"),
        });
    }
}

QString WorkerResponseParser::firstStringValue(const QJsonObject &payload, const QStringList &keys)
{
    for (const QString &key : keys)
    {
        const QJsonValue value = payload.value(key);
        if (!value.isString())
            continue;

        const QString text = value.toString().trimmed();
        if (!text.isEmpty())
            return text;
    }

    return QString();
}

} // namespace spellvision::workers
