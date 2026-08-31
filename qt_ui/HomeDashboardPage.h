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
    // rebuild=false loads the default content WITHOUT redrawing the grid -- used by the ctor,
    // which leaves the first build to setConfig(). See dashboardBuilt_ below.
    void resetContentToDefaults(bool rebuild = true);

signals:
    void modeRequested(const QString &modeId);
    void managerRequested(const QString &managerId);
    void launchRequested(const QString &modeId,
                         const QString &title,
                         const QString &subtitle,
                         const QString &sourceLabel);
    void openOutputRequested(const QString &modeId, const QString &path);
    void sendOutputToInputRequested(const QString &targetModeId, const QString &path);
    void configEdited(const HomeDashboardConfig &config);

protected:
    void resizeEvent(QResizeEvent *event) override;
    void showEvent(QShowEvent *event) override;

private:
    void rebuildDashboard();
    void registerBuiltinModules();
    QVector<HomeModulePlacement> effectivePlacements() const;
    bool adjustPlacement(const QString &moduleId, int dx, int dy);
    bool resizePlacement(const QString &moduleId, int dw, int dh);
    bool setPlacementVisibility(const QString &moduleId, bool visible);
    HomeModulePreferences preferencesFor(const QString &moduleId) const;
    void applyTheme();

    // The ctor no longer builds the grid: HomePage constructs this page and immediately calls
    // setConfig() with the saved config, which rebuilds it anyway. Building once in the ctor with
    // defaults and once again a moment later cost ~933ms of the startup path for a result that was
    // discarded. Guarded so a standalone user (no setConfig) still gets a grid, on first show.
    bool dashboardBuilt_ = false;

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
