#pragma once

#include <QByteArray>
#include <QJsonObject>
#include <QString>

namespace spellvision::workers
{

class WorkerResponseParser
{
public:
    enum class MessageKind
    {
        Unknown,
        Status,
        Progress,
        Result,
        Error,
        JobUpdate,
        QueueSnapshot,
        QueueAck,
        RuntimeStatus,
        RuntimeAck,
        WorkflowImportResult,
        WorkflowProfiles,
        ClientError
    };

    enum class JobState
    {
        Unknown,
        Queued,
        Starting,
        Running,
        Completed,
        Failed,
        Cancelled
    };

    struct ParsedMessage
    {
        MessageKind kind = MessageKind::Unknown;
        JobState jobState = JobState::Unknown;

        QString jobId;
        QString message;
        QString outputPath;
        QString metadataPath;
        QString errorText;

        bool hasOk = false;
        bool ok = false;
        bool terminal = false;
        bool successfulTerminal = false;
        bool failedTerminal = false;

        bool hasProgress = false;
        int progressPercent = -1;
        int progressCurrent = -1;
        int progressTotal = -1;

        QJsonObject raw;
        QJsonObject progress;
        QJsonObject result;
        QJsonObject error;
    };

    static ParsedMessage parseObject(const QJsonObject &payload);
    static ParsedMessage parseJsonLine(const QByteArray &line, QString *parseError = nullptr);

    static MessageKind kindFromString(const QString &value);
    static JobState stateFromString(const QString &value);

    static bool isTerminalState(JobState state);
    static bool isSuccessfulTerminal(JobState state);
    static bool isFailedTerminal(JobState state);

    static QString kindName(MessageKind kind);
    static QString stateName(JobState state);

private:
    static void applyOk(ParsedMessage &message, const QJsonObject &payload);
    static void applyJobIdentity(ParsedMessage &message, const QJsonObject &payload);
    static void applyProgress(ParsedMessage &message, const QJsonObject &payload);
    static void applyResult(ParsedMessage &message, const QJsonObject &payload);
    static void applyError(ParsedMessage &message, const QJsonObject &payload);
    static QString firstStringValue(const QJsonObject &payload, const QStringList &keys);
};

} // namespace spellvision::workers
