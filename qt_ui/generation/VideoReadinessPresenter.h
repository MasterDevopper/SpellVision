#pragma once

#include <QJsonObject>
#include <QString>
#include <QStringList>

namespace spellvision::generation
{

class VideoReadinessPresenter final
{
public:
    VideoReadinessPresenter() = delete;

    static bool isVideoPayload(const QJsonObject &payload);
    static QStringList warnings(const QJsonObject &payload);
    static QString diagnosticSummary(const QJsonObject &payload);
    static QString blockingMessage(const QJsonObject &payload);
    static QString readyMessage(const QJsonObject &payload);
};

} // namespace spellvision::generation
