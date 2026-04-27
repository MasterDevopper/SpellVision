#include "WorkerQueueController.h"

#include "../QueueManager.h"

#include <QJsonArray>
#include <QJsonValue>
#include <QTimer>

namespace spellvision::workers
{

WorkerQueueController::WorkerQueueController(QObject *parent)
    : QObject(parent),
      pollTimer_(new QTimer(this))
{
    pollTimer_->setInterval(1800);
    connect(pollTimer_, &QTimer::timeout, this, [this]() {
        pollOnce();
    });
}

void WorkerQueueController::bind(Bindings bindings)
{
    bindings_ = std::move(bindings);
}

QJsonObject WorkerQueueController::buildQueueStatusRequest()
{
    QJsonObject request;
    request.insert(QStringLiteral("command"), QStringLiteral("queue_status"));
    return request;
}

bool WorkerQueueController::applyWorkerQueueResponse(const QJsonObject &response)
{
    if (!bindings_.queueManager)
        return false;

    const QJsonObject snapshot = normalizedQueueSnapshot(response);
    if (snapshot.isEmpty())
        return false;

    const bool changed = bindings_.queueManager->applyQueueSnapshot(snapshot);
    if (changed)
    {
        if (bindings_.afterQueueSnapshotApplied)
            bindings_.afterQueueSnapshotApplied();

        emit queueResponseApplied();
    }

    return changed;
}

bool WorkerQueueController::pollOnce()
{
    if (!bindings_.sendRequest)
    {
        notifyPollFailure(QStringLiteral("Worker queue poll skipped: no request sender is bound."));
        return false;
    }

    const QJsonObject request = bindings_.buildPollRequest
                                    ? bindings_.buildPollRequest()
                                    : buildQueueStatusRequest();

    QString stderrText;
    bool startedOk = false;
    const QJsonObject response = bindings_.sendRequest(request, &stderrText, &startedOk);

    const QString trimmedStderr = stderrText.trimmed();
    if (!trimmedStderr.isEmpty())
        logLine(trimmedStderr);

    if (!startedOk)
    {
        notifyPollFailure(QStringLiteral("Worker queue poll failed: worker_client.py did not start."));
        return false;
    }

    if (response.isEmpty())
    {
        notifyPollFailure(QStringLiteral("Worker queue poll failed: worker returned no JSON payload."));
        return false;
    }

    return applyWorkerQueueResponse(response);
}

void WorkerQueueController::startPolling(int intervalMs)
{
    const int safeIntervalMs = qMax(250, intervalMs);
    if (pollTimer_->interval() != safeIntervalMs)
        pollTimer_->setInterval(safeIntervalMs);

    if (!pollTimer_->isActive())
        pollTimer_->start();
}

void WorkerQueueController::stopPolling()
{
    pollTimer_->stop();
}

bool WorkerQueueController::isPolling() const
{
    return pollTimer_->isActive();
}

QJsonObject WorkerQueueController::normalizedQueueSnapshot(const QJsonObject &response) const
{
    if (response.value(QStringLiteral("items")).isArray())
        return response;

    const QJsonValue queueValue = response.value(QStringLiteral("queue"));
    if (queueValue.isObject())
    {
        const QJsonObject queueObject = queueValue.toObject();
        if (queueObject.value(QStringLiteral("items")).isArray())
            return queueObject;
    }

    const QJsonValue snapshotValue = response.value(QStringLiteral("snapshot"));
    if (snapshotValue.isObject())
    {
        const QJsonObject snapshotObject = snapshotValue.toObject();
        if (snapshotObject.value(QStringLiteral("items")).isArray())
            return snapshotObject;
    }

    const QString type = response.value(QStringLiteral("type")).toString().trimmed().toLower();
    if ((type == QStringLiteral("queue_snapshot") || type == QStringLiteral("queue_status")) &&
        response.value(QStringLiteral("items")).isArray())
    {
        return response;
    }

    return {};
}

void WorkerQueueController::logLine(const QString &text) const
{
    if (text.trimmed().isEmpty())
        return;

    if (bindings_.appendLogLine)
        bindings_.appendLogLine(text.trimmed());
}

void WorkerQueueController::notifyPollFailure(const QString &message)
{
    const QString trimmed = message.trimmed();
    if (trimmed.isEmpty())
        return;

    logLine(trimmed);
    emit queuePollFailed(trimmed);
}

} // namespace spellvision::workers
