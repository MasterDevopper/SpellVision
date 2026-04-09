#include "HomeDashboardSettings.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSettings>

namespace
{
QString presetToString(HomeDashboardPreset preset)
{
    switch (preset)
    {
    case HomeDashboardPreset::CinematicStudio: return QStringLiteral("cinematic_studio");
    case HomeDashboardPreset::ProductiveCompact: return QStringLiteral("productive_compact");
    case HomeDashboardPreset::MotionWorkspace: return QStringLiteral("motion_workspace");
    case HomeDashboardPreset::ModelOps: return QStringLiteral("model_ops");
    case HomeDashboardPreset::Minimal: return QStringLiteral("minimal");
    }
    return QStringLiteral("cinematic_studio");
}

HomeDashboardPreset presetFromString(const QString &value)
{
    if (value == QStringLiteral("productive_compact"))
        return HomeDashboardPreset::ProductiveCompact;
    if (value == QStringLiteral("motion_workspace"))
        return HomeDashboardPreset::MotionWorkspace;
    if (value == QStringLiteral("model_ops"))
        return HomeDashboardPreset::ModelOps;
    if (value == QStringLiteral("minimal"))
        return HomeDashboardPreset::Minimal;
    return HomeDashboardPreset::CinematicStudio;
}

QString densityToString(HomeDashboardDensity density)
{
    switch (density)
    {
    case HomeDashboardDensity::Compact: return QStringLiteral("compact");
    case HomeDashboardDensity::Comfortable: return QStringLiteral("comfortable");
    case HomeDashboardDensity::Cinematic: return QStringLiteral("cinematic");
    }
    return QStringLiteral("comfortable");
}

HomeDashboardDensity densityFromString(const QString &value)
{
    if (value == QStringLiteral("compact"))
        return HomeDashboardDensity::Compact;
    if (value == QStringLiteral("cinematic"))
        return HomeDashboardDensity::Cinematic;
    return HomeDashboardDensity::Comfortable;
}
}

HomeDashboardSettings::HomeDashboardSettings(QObject *parent)
    : QObject(parent)
{
}

HomeDashboardConfig HomeDashboardSettings::load() const
{
    QSettings settings;
    const QString jsonText = settings.value(QStringLiteral("ui/home_dashboard/layout_json")).toString();
    if (!jsonText.trimmed().isEmpty())
    {
        const HomeDashboardConfig config = deserialize(jsonText);
        if (isValidHomeDashboardConfig(config))
            return config;
    }

    return defaultHomeDashboardConfig(HomeDashboardPreset::CinematicStudio);
}

void HomeDashboardSettings::save(const HomeDashboardConfig &config)
{
    if (!isValidHomeDashboardConfig(config))
        return;

    QSettings settings;
    settings.setValue(QStringLiteral("ui/home_dashboard/version"), 1);
    settings.setValue(QStringLiteral("ui/home_dashboard/preset"), presetToString(config.preset));
    settings.setValue(QStringLiteral("ui/home_dashboard/density"), densityToString(config.density));
    settings.setValue(QStringLiteral("ui/home_dashboard/layout_json"), serialize(config));
}

void HomeDashboardSettings::reset(HomeDashboardPreset preset)
{
    save(defaultHomeDashboardConfig(preset));
}

QString HomeDashboardSettings::serialize(const HomeDashboardConfig &config) const
{
    QJsonObject root;
    root.insert(QStringLiteral("preset"), presetToString(config.preset));
    root.insert(QStringLiteral("density"), densityToString(config.density));

    QJsonArray placements;
    for (const HomeModulePlacement &placement : config.placements)
    {
        QJsonObject obj;
        obj.insert(QStringLiteral("moduleId"), placement.moduleId);
        obj.insert(QStringLiteral("x"), placement.x);
        obj.insert(QStringLiteral("y"), placement.y);
        obj.insert(QStringLiteral("w"), placement.w);
        obj.insert(QStringLiteral("h"), placement.h);
        obj.insert(QStringLiteral("visible"), placement.visible);
        obj.insert(QStringLiteral("locked"), placement.locked);
        placements.append(obj);
    }
    root.insert(QStringLiteral("placements"), placements);

    QJsonObject prefs;
    for (auto it = config.modulePrefs.constBegin(); it != config.modulePrefs.constEnd(); ++it)
    {
        QJsonObject obj;
        obj.insert(QStringLiteral("showTitle"), it.value().showTitle);
        obj.insert(QStringLiteral("showSubtitle"), it.value().showSubtitle);
        obj.insert(QStringLiteral("showPreviewPlate"), it.value().showPreviewPlate);
        obj.insert(QStringLiteral("variant"), it.value().variant);
        prefs.insert(it.key(), obj);
    }
    root.insert(QStringLiteral("modulePrefs"), prefs);

    return QString::fromUtf8(QJsonDocument(root).toJson(QJsonDocument::Compact));
}

HomeDashboardConfig HomeDashboardSettings::deserialize(const QString &jsonText) const
{
    const QJsonDocument doc = QJsonDocument::fromJson(jsonText.toUtf8());
    if (!doc.isObject())
        return defaultHomeDashboardConfig(HomeDashboardPreset::CinematicStudio);

    const QJsonObject root = doc.object();
    HomeDashboardConfig config;
    config.preset = presetFromString(root.value(QStringLiteral("preset")).toString());
    config.density = densityFromString(root.value(QStringLiteral("density")).toString());

    const QJsonArray placements = root.value(QStringLiteral("placements")).toArray();
    for (const QJsonValue &value : placements)
    {
        const QJsonObject obj = value.toObject();
        HomeModulePlacement placement;
        placement.moduleId = obj.value(QStringLiteral("moduleId")).toString();
        placement.x = obj.value(QStringLiteral("x")).toInt();
        placement.y = obj.value(QStringLiteral("y")).toInt();
        placement.w = obj.value(QStringLiteral("w")).toInt(1);
        placement.h = obj.value(QStringLiteral("h")).toInt(1);
        placement.visible = obj.value(QStringLiteral("visible")).toBool(true);
        placement.locked = obj.value(QStringLiteral("locked")).toBool(false);
        config.placements.push_back(placement);
    }

    const QJsonObject prefs = root.value(QStringLiteral("modulePrefs")).toObject();
    for (auto it = prefs.constBegin(); it != prefs.constEnd(); ++it)
    {
        const QJsonObject obj = it.value().toObject();
        HomeModulePreferences pref;
        pref.showTitle = obj.value(QStringLiteral("showTitle")).toBool(true);
        pref.showSubtitle = obj.value(QStringLiteral("showSubtitle")).toBool(true);
        pref.showPreviewPlate = obj.value(QStringLiteral("showPreviewPlate")).toBool(true);
        pref.variant = obj.value(QStringLiteral("variant")).toString();
        config.modulePrefs.insert(it.key(), pref);
    }

    if (!isValidHomeDashboardConfig(config))
        return defaultHomeDashboardConfig(config.preset);

    return config;
}
