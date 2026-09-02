#include "AppVersion.h"

#include <QCoreApplication>
#include <QStringList>
#include <QVector>

namespace spellvision::shell
{

namespace
{

QVector<int> numericComponents(const QString &raw)
{
    QString text = raw.trimmed();
    if (text.startsWith(QLatin1Char('v'), Qt::CaseInsensitive))
        text.remove(0, 1);
    // "1.2.3-beta.1" and "1.2.3+build" compare as 1.2.3.
    for (const QChar sep : {QLatin1Char('-'), QLatin1Char('+')})
    {
        const qsizetype at = text.indexOf(sep);
        if (at >= 0)
            text.truncate(at);
    }
    QVector<int> out;
    for (const QString &part : text.split(QLatin1Char('.'), Qt::SkipEmptyParts))
    {
        bool ok = false;
        const int value = part.toInt(&ok);
        out.append(ok && value >= 0 ? value : 0);
    }
    return out;
}

} // namespace

QString appVersion()
{
    const QString fromApp = QCoreApplication::applicationVersion().trimmed();
    if (!fromApp.isEmpty())
        return fromApp;
#ifdef SPELLVISION_VERSION
    return QStringLiteral(SPELLVISION_VERSION);
#else
    return QStringLiteral("0.0.0");
#endif
}

int compareVersions(const QString &a, const QString &b)
{
    QVector<int> left = numericComponents(a);
    QVector<int> right = numericComponents(b);
    while (left.size() < right.size())
        left.append(0);
    while (right.size() < left.size())
        right.append(0);
    for (qsizetype i = 0; i < left.size(); ++i)
    {
        if (left[i] != right[i])
            return left[i] < right[i] ? -1 : 1;
    }
    return 0;
}

QString latestReleaseApiUrl()
{
    return QStringLiteral("https://api.github.com/repos/MasterDevopper/SpellVision/releases/latest");
}

QString releasesPageUrl()
{
    return QStringLiteral("https://github.com/MasterDevopper/SpellVision/releases");
}

} // namespace spellvision::shell
