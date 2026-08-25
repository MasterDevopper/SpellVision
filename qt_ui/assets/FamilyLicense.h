#pragma once

#include <QString>

namespace spellvision::assets
{

inline bool familyAllowsCommercialUse(const QString &family, const QString &modelHint = QString())
{
    const QString key = family.trimmed().toLower();
    const QString hay = key.isEmpty() ? modelHint.trimmed().toLower() : key;
    return !(hay.contains(QLatin1String("anima")) || hay.contains(QLatin1String("hunyuan")));
}

inline QString familyLicenseBadgeText(const QString &family, const QString &modelHint = QString())
{
    if (familyAllowsCommercialUse(family, modelHint))
        return {};
    return QStringLiteral("Non-commercial");
}

} // namespace spellvision::assets
