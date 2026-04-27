#pragma once

#include <QJsonObject>
#include <QObject>
#include <QString>

#include <functional>

class QueueManager;
class QTimer;

namespace spellvision::workers
{

class WorkerQueueController final : public QObject
{
    Q_OBJECT

public:
    struct Bindings
    {
        QueueManager *queueManager = nullptr;
        std::function<QJsonObject()> buildPollRequest;
        std::function<QJsonObject(const QJsonObject &request, QString *stderrText, bool *startedOk)> sendRequest;
        std::function<void(const QString &text)> appendLogLine;
        std::function<void()> afterQueueSnapshotApplied;
    };

    explicit WorkerQueueController(QObject *parent = nullptr);

    void bind(Bindings bindings);

    static QJsonObject buildQueueStatusRequest();

    bool applyWorkerQueueResponse(const QJsonObject &response);
    bool pollOnce();

    void startPolling(int intervalMs = 1800);
    void stopPolling();
    bool isPolling() const;

signals:
    void queueResponseApplied();
    void queuePollFailed(const QString &message);

private:
    QJsonObject normalizedQueueSnapshot(const QJsonObject &response) const;
    void logLine(const QString &text) const;
    void notifyPollFailure(const QString &message);

    Bindings bindings_;
    QTimer *pollTimer_ = nullptr;
};

} // namespace spellvision::workers
