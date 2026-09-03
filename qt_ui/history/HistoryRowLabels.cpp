#include "history/HistoryRowLabels.h"

namespace spellvision::history
{
namespace
{
QString modeOr(const QString &mode, const QString &fallback)
{
    const QString trimmed = mode.trimmed();
    return trimmed.isEmpty() ? fallback : trimmed.toUpper();
}
} // namespace

QString detailLabel(bool isImage, const QString &mode, const QString &imageSteps,
                    const QString &durationLabel)
{
    if (isImage)
    {
        const QString steps = imageSteps.trimmed();
        if (steps.isEmpty())
            return modeOr(mode, QStringLiteral("IMAGE"));
        return QStringLiteral("%1 • %2 steps").arg(modeOr(mode, QStringLiteral("IMAGE")), steps);
    }
    const QString duration = durationLabel.trimmed();
    if (duration.isEmpty())
        return modeOr(mode, QStringLiteral("VIDEO"));
    return duration;
}

QString stackLabel(bool isImage, const QString &modelName, const QString &stackSummary)
{
    if (isImage)
    {
        const QString name = modelName.trimmed();
        return name.isEmpty() ? QStringLiteral("image") : name;
    }
    const QString stack = stackSummary.trimmed();
    return stack.isEmpty() ? QStringLiteral("Wan stack") : stack;
}

} // namespace spellvision::history
