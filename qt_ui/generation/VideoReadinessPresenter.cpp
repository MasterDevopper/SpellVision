#include "VideoReadinessPresenter.h"

#include <QJsonArray>
#include <QJsonValue>

namespace spellvision::generation
{

bool VideoReadinessPresenter::isVideoPayload(const QJsonObject &payload)
{
    const QString mode = payload.value(QStringLiteral("mode")).toString().trimmed().toLower();
    if (mode == QStringLiteral("t2v") || mode == QStringLiteral("i2v"))
        return true;

    return payload.value(QStringLiteral("video_request_kind")).toString().trimmed().toLower() == QStringLiteral("video");
}

QStringList VideoReadinessPresenter::warnings(const QJsonObject &payload)
{
    QStringList out;
    const QJsonArray array = payload.value(QStringLiteral("video_readiness_warnings")).toArray();
    for (const QJsonValue &value : array)
    {
        const QString warning = value.toString().trimmed();
        if (!warning.isEmpty())
            out << warning;
    }
    out.removeDuplicates();
    return out;
}

QString VideoReadinessPresenter::diagnosticSummary(const QJsonObject &payload)
{
    const QString summary = payload.value(QStringLiteral("video_diagnostic_summary")).toString().trimmed();
    if (!summary.isEmpty())
        return summary;

    const QString duration = payload.value(QStringLiteral("video_duration_label")).toString().trimmed();
    const QString stackKind = payload.value(QStringLiteral("video_stack_kind")).toString().trimmed();
    if (!duration.isEmpty() && !stackKind.isEmpty())
        return QStringLiteral("Video ready • %1 • %2").arg(duration, stackKind);
    if (!duration.isEmpty())
        return QStringLiteral("Video ready • %1").arg(duration);
    if (!stackKind.isEmpty())
        return QStringLiteral("Video stack: %1").arg(stackKind);

    return QString();
}

QString VideoReadinessPresenter::blockingMessage(const QJsonObject &payload)
{
    if (!isVideoPayload(payload))
        return QString();

    if (payload.value(QStringLiteral("video_readiness_ok")).toBool(true))
        return QString();

    const QStringList warningList = warnings(payload);
    if (!warningList.isEmpty())
        return warningList.join(QStringLiteral(" • "));

    const QString summary = diagnosticSummary(payload);
    if (!summary.isEmpty())
        return summary;

    return QStringLiteral("Video request is not ready. Check the video model stack, input image, frame count, FPS, and dimensions.");
}

QString VideoReadinessPresenter::readyMessage(const QJsonObject &payload)
{
    if (!isVideoPayload(payload))
        return QString();
    if (!payload.value(QStringLiteral("video_readiness_ok")).toBool(false))
        return QString();

    const QString summary = diagnosticSummary(payload);
    if (!summary.isEmpty())
        return summary;

    return QStringLiteral("Video request ready.");
}

} // namespace spellvision::generation
