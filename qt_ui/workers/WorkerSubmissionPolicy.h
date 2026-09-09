#pragma once

#include <QJsonObject>
#include <QString>
#include <QStringList>

namespace spellvision::workers
{

class WorkerSubmissionPolicy final
{
public:
    WorkerSubmissionPolicy() = delete;

    static QJsonObject videoStackFromPayload(const QJsonObject &payload);
    static QString resolvedModelValueFromPayload(const QJsonObject &payload);
    static bool hasNativeVideoStackPayload(const QJsonObject &payload);
    static bool hasWorkflowBinding(const QJsonObject &payload);

    static QString videoSubmitLogLine(const QString &modeId,
                                      const QJsonObject &payload,
                                      const QString &modelValue,
                                      bool hasNativeVideoStack,
                                      bool hasWorkflowBinding);

    static QString missingModelMessage(const QString &modeId, bool videoMode);

    static QString acceptedRequestLogLine(const QString &modeId,
                                          bool videoMode,
                                          bool hasWorkflowBinding,
                                          const QString &modelValue);

    // Generate is disabled at click. The enqueue ACK must not re-enable it: that fires ~2 ms
    // later while the job is still queued. Only a failed enqueue (no worker, empty body, or
    // ok=false) re-enables, because there is then no job to wait for.
    static bool clearBusyOnEnqueueAck(bool startedOk, bool ok);

private:
    static QString firstStackString(const QJsonObject &stack, const QStringList &keys);
};

} // namespace spellvision::workers
