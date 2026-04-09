#pragma once

#include <QMap>
#include <QString>
#include <QVector>

struct HomeRuntimeSummary
{
    QString runtimeName;
    int runningCount = 0;
    int pendingCount = 0;
    int errorCount = 0;
    QString vramText;
    QString modelText;
    QString loraText;
    QString progressText;
    int progressPercent = 0;
};

enum class HomeDashboardDensity
{
    Compact,
    Comfortable,
    Cinematic
};

enum class HomeDashboardPreset
{
    CinematicStudio,
    ProductiveCompact,
    MotionWorkspace,
    ModelOps,
    Minimal
};

struct HomeModulePlacement
{
    QString moduleId;
    int x = 0;
    int y = 0;
    int w = 1;
    int h = 1;
    bool visible = true;
    bool locked = false;
};

struct HomeModulePreferences
{
    bool showTitle = true;
    bool showSubtitle = true;
    bool showPreviewPlate = true;
    QString variant;
};

struct HomeDashboardConfig
{
    HomeDashboardPreset preset = HomeDashboardPreset::CinematicStudio;
    HomeDashboardDensity density = HomeDashboardDensity::Comfortable;
    QVector<HomeModulePlacement> placements;
    QMap<QString, HomeModulePreferences> modulePrefs;
};

struct HomeStarterPreview
{
    QString title;
    QString subtitle;
    QString modeId;
    QString sourceLabel;
};

struct HomeWorkflowCard
{
    QString eyebrow;
    QString title;
    QString body;
    QString modeId;
    QString sourceLabel;
    QString actionLabel = QStringLiteral("Preview in Hero");
    qreal phase = 0.0;
};

struct HomeRecentOutputCard
{
    QString title;
    QString body;
    QString routeModeId;
    QString openManagerId = QStringLiteral("history");
    qreal phase = 0.0;
};

struct HomeFavoriteCard
{
    QString eyebrow;
    QString title;
    QString body;
    QString modeId;
    QString sourceLabel;
    QString actionLabel = QStringLiteral("Preview in Hero");
    qreal phase = 0.0;
};

namespace HomeDashboardIds
{
inline const QString HeroLauncher = QStringLiteral("hero_launcher");
inline const QString WorkflowLauncher = QStringLiteral("workflow_launcher");
inline const QString RecentOutputs = QStringLiteral("recent_outputs");
inline const QString Favorites = QStringLiteral("favorites");
inline const QString ActiveModels = QStringLiteral("active_models");
}

inline bool isKnownHomeModuleId(const QString &moduleId)
{
    return moduleId == HomeDashboardIds::HeroLauncher
        || moduleId == HomeDashboardIds::WorkflowLauncher
        || moduleId == HomeDashboardIds::RecentOutputs
        || moduleId == HomeDashboardIds::Favorites
        || moduleId == HomeDashboardIds::ActiveModels;
}

inline bool isValidHomeDashboardConfig(const HomeDashboardConfig &config)
{
    if (config.placements.isEmpty())
        return false;

    for (const HomeModulePlacement &placement : config.placements)
    {
        if (!isKnownHomeModuleId(placement.moduleId))
            return false;
        if (placement.w <= 0 || placement.h <= 0)
            return false;
        if (placement.x < 0 || placement.y < 0)
            return false;
        if (placement.x + placement.w > 12)
            return false;
    }

    return true;
}

inline HomeDashboardConfig defaultHomeDashboardConfig(HomeDashboardPreset preset)
{
    HomeDashboardConfig config;
    config.preset = preset;
    config.density = HomeDashboardDensity::Comfortable;

    using namespace HomeDashboardIds;
    switch (preset)
    {
    case HomeDashboardPreset::CinematicStudio:
        config.placements = {
            {HeroLauncher, 0, 0, 8, 4, true, false},
            {WorkflowLauncher, 8, 0, 4, 4, true, false},
            {RecentOutputs, 0, 4, 6, 5, true, false},
            {Favorites, 6, 4, 4, 5, true, false},
            {ActiveModels, 10, 4, 2, 5, true, false}
        };
        break;
    case HomeDashboardPreset::ProductiveCompact:
        config.placements = {
            {HeroLauncher, 0, 0, 6, 3, true, false},
            {WorkflowLauncher, 6, 0, 3, 3, true, false},
            {ActiveModels, 9, 0, 3, 3, true, false},
            {RecentOutputs, 0, 3, 6, 4, true, false},
            {Favorites, 6, 3, 6, 4, true, false}
        };
        break;
    case HomeDashboardPreset::MotionWorkspace:
        config.placements = {
            {HeroLauncher, 0, 0, 7, 4, true, false},
            {WorkflowLauncher, 7, 0, 3, 4, true, false},
            {ActiveModels, 10, 0, 2, 4, true, false},
            {RecentOutputs, 0, 4, 7, 5, true, false},
            {Favorites, 7, 4, 5, 5, true, false}
        };
        break;
    case HomeDashboardPreset::ModelOps:
        config.placements = {
            {WorkflowLauncher, 0, 0, 4, 4, true, false},
            {HeroLauncher, 4, 0, 4, 4, true, false},
            {ActiveModels, 8, 0, 4, 5, true, false},
            {RecentOutputs, 0, 4, 6, 5, true, false},
            {Favorites, 6, 5, 6, 4, true, false}
        };
        break;
    case HomeDashboardPreset::Minimal:
        config.placements = {
            {HeroLauncher, 0, 0, 8, 4, true, false},
            {RecentOutputs, 0, 4, 8, 5, true, false},
            {ActiveModels, 8, 0, 4, 4, true, false},
            {WorkflowLauncher, 8, 4, 4, 2, false, false},
            {Favorites, 8, 6, 4, 3, false, false}
        };
        break;
    }

    return config;
}
