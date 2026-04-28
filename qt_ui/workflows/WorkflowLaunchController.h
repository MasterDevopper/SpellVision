#pragma once

#include <QJsonObject>
#include <QString>

#include <functional>

namespace spellvision::workflows
{

class WorkflowLaunchController final
{
public:
    using ModeAvailability = std::function<bool(const QString &modeId)>;

    WorkflowLaunchController() = delete;

    static QString normalizeModeId(const QString &modeId);
    static QString defaultModeForMedia(const QString &mediaType, bool hasInputImage);
    static QString resolveDraftModeId(const QJsonObject &draft, const ModeAvailability &isModeAvailable);

    static QString draftSourceName(const QJsonObject &draft);
    static QString draftOpenedLogLine(const QJsonObject &draft, const QString &modeId);
    static QString draftRequiresReviewLogLine(const QString &modeId);

    static QJsonObject buildWorkflowLaunchRequest(const QJsonObject &profile,
                                                  const QString &projectRoot,
                                                  const QString &pythonExecutable);
};

} // namespace spellvision::workflows
