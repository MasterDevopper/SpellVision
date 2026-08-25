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
        using RequestCompletion =
            std::function<void(const QJsonObject &response, const QString &stderrText, bool startedOk)>;

        QueueManager *queueManager = nullptr;
        std::function<QJsonObject()> buildPollRequest;
        std::function<void(const QJsonObject &request, RequestCompletion completion)> sendRequestAsync;
        std::function<void(const QString &text)> appendLogLine;
        std::function<void()> afterQueueSnapshotApplied;
    };

    explicit WorkerQueueController(QObject *parent = nullptr);

    void bind(Bindings bindings);

    static QJsonObject buildQueueStatusRequest();

    bool applyWorkerQueueResponse(const QJsonObject &response);
    bool pollOnce();
    void confirmWorkerLost(const QString &message);

    void startPolling(int intervalMs = 1800);
    void stopPolling();
    bool isPolling() const;

signals:
    void queueResponseApplied();
    // Fires on every poll that returns a valid queue snapshot (worker reachable),
    // independent of whether the queue CHANGED -- queueResponseApplied only fires
    // on a change, so it misses the worker coming up with an already-empty queue.
    void queuePollSucceeded();
    void queuePollFailed(const QString &message);
    void queueConnectivityLost(const QString &message);

private:
    QJsonObject normalizedQueueSnapshot(const QJsonObject &response) const;
    void logLine(const QString &text) const;
    void notifyPollFailure(const QString &message);
    void handlePrimaryPollResponse(const QJsonObject &response,
                                   const QString &stderrText,
                                   bool startedOk);

    Bindings bindings_;
    QTimer *pollTimer_ = nullptr;
    int consecutivePollFailures_ = 0;
    bool hasSuccessfulPoll_ = false;
    bool connectivityLost_ = false;
    bool pollInFlight_ = false;
};

} // namespace spellvision::workers
