#pragma once

#include "HomeDashboardTypes.h"

#include <QWidget>

class HomeDashboardPage;
class HomeDashboardSettings;
class QScrollArea;
class QShowEvent;

class HomePage : public QWidget
{
    Q_OBJECT

public:
    explicit HomePage(QWidget *parent = nullptr);

    void setRuntimeSummary(const QString &runtimeName,
                           int runningCount,
                           int pendingCount,
                           int errorCount,
                           const QString &vramText,
                           const QString &modelText,
                           const QString &loraText,
                           const QString &progressText,
                           int progressPercent);

    void setDashboardConfig(const HomeDashboardConfig &config);
    HomeDashboardConfig dashboardConfig() const;

    void setCustomizeMode(bool enabled);
    bool isCustomizeMode() const;

    void setHeroStarterPreview(const HomeStarterPreview &preview);
    void setWorkflowCards(const QVector<HomeWorkflowCard> &cards);
    void setRecentOutputCards(const QVector<HomeRecentOutputCard> &cards);
    void setFavoriteCards(const QVector<HomeFavoriteCard> &cards);
    void resetDashboardContentToDefaults();
    void refreshAppDataSources(bool refreshHeroPreview = true);

signals:
    void modeRequested(const QString &modeId);
    void managerRequested(const QString &managerId);
    void launchRequested(const QString &modeId,
                         const QString &title,
                         const QString &subtitle,
                         const QString &sourceLabel);
    void dashboardConfigChanged(const HomeDashboardConfig &config);

protected:
    void showEvent(QShowEvent *event) override;

private:
    void loadDashboardConfig();
    void applyTheme();

    QScrollArea *scrollArea_ = nullptr;
    HomeDashboardPage *dashboardPage_ = nullptr;
    HomeDashboardSettings *dashboardSettings_ = nullptr;
    HomeDashboardConfig config_;
    bool appDataInitialized_ = false;
};
