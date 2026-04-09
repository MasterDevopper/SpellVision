#pragma once

#include "HomeDashboardTypes.h"

#include <QMap>
#include <QWidget>

class QGridLayout;
class HomeModuleBase;
class HomeModuleFrame;

class HomeDashboardPage : public QWidget
{
    Q_OBJECT

public:
    explicit HomeDashboardPage(QWidget *parent = nullptr);

    void setConfig(const HomeDashboardConfig &config);
    const HomeDashboardConfig &config() const;

    void setCustomizeMode(bool enabled);
    bool isCustomizeMode() const;

    void setRuntimeSummary(const HomeRuntimeSummary &summary);

    void setHeroStarterPreview(const HomeStarterPreview &preview);
    void setWorkflowCards(const QVector<HomeWorkflowCard> &cards);
    void setRecentOutputCards(const QVector<HomeRecentOutputCard> &cards);
    void setFavoriteCards(const QVector<HomeFavoriteCard> &cards);
    void resetContentToDefaults();

signals:
    void modeRequested(const QString &modeId);
    void managerRequested(const QString &managerId);
    void launchRequested(const QString &modeId,
                         const QString &title,
                         const QString &subtitle,
                         const QString &sourceLabel);
    void configEdited(const HomeDashboardConfig &config);

protected:
    void resizeEvent(QResizeEvent *event) override;

private:
    void rebuildDashboard();
    void registerBuiltinModules();
    QVector<HomeModulePlacement> effectivePlacements() const;
    bool adjustPlacement(const QString &moduleId, int dx, int dy);
    bool resizePlacement(const QString &moduleId, int dw, int dh);
    bool setPlacementVisibility(const QString &moduleId, bool visible);
    HomeModulePreferences preferencesFor(const QString &moduleId) const;
    void applyTheme();

    QWidget *gridHost_ = nullptr;
    QGridLayout *grid_ = nullptr;
    HomeDashboardConfig config_;
    HomeRuntimeSummary runtimeSummary_;
    bool customizeMode_ = false;
    QMap<QString, HomeModuleFrame *> framesById_;

    bool compactLayout_ = false;
    bool rebuildInProgress_ = false;

    HomeStarterPreview heroStarterPreview_;
    QVector<HomeWorkflowCard> workflowCards_;
    QVector<HomeRecentOutputCard> recentOutputCards_;
    QVector<HomeFavoriteCard> favoriteCards_;
};
