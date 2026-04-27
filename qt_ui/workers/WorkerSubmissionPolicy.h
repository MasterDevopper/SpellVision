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

private:
    static QString firstStackString(const QJsonObject &stack, const QStringList &keys);
};

} // namespace spellvision::workers
