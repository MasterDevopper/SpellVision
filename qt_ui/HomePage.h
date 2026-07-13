#pragma once

#include "HomeDashboardTypes.h"

#include <QWidget>

class GalleryOutputModel;
class GalleryCardDelegate;
class QLabel;
class QListView;
class QShowEvent;
class QStackedWidget;

namespace spellvision::assets
{
class ModelThumbnailCache;
}

// Home is your outputs, not a launchpad. A hero gallery of recent renders (rounded, thumbnail-forward
// cards over the REAL output dir) with a thin, subordinate system band on top. The old customizable
// module dashboard (HomeDashboardPage + modules) is bypassed; the legacy setters below are kept as
// no-ops / gallery refreshes so MainWindow's wiring keeps compiling.
class HomePage : public QWidget
{
    Q_OBJECT

public:
    explicit HomePage(QWidget *parent = nullptr);

    // Live system context for the dashboard band (pushed from MainWindow).
    void setRuntimeSummary(const QString &runtimeName,
                           int runningCount,
                           int pendingCount,
                           int errorCount,
                           const QString &vramText,
                           const QString &modelText,
                           const QString &loraText,
                           const QString &progressText,
                           int progressPercent);
    void setModelCount(int count); // model-library size -- an additive stat the bottom bar lacks

    // --- Legacy dashboard surface (kept for source compatibility; gallery-first Home ignores most) ---
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
    // A gallery card was activated: open the output in its originating cockpit.
    void openOutputRequested(const QString &modeId, const QString &path);

protected:
    void showEvent(QShowEvent *event) override;

private:
    void reloadGallery();
    void updateDashboardBand();
    void applyTheme();

    // Gallery (hero)
    spellvision::assets::ModelThumbnailCache *thumbs_ = nullptr;
    GalleryOutputModel *galleryModel_ = nullptr;
    GalleryCardDelegate *galleryDelegate_ = nullptr;
    QListView *galleryView_ = nullptr;
    QStackedWidget *galleryStack_ = nullptr; // 0 = grid, 1 = empty state

    // Dashboard band (subordinate context)
    QLabel *bandRenders_ = nullptr;
    QLabel *bandModels_ = nullptr;

    int modelCount_ = -1;
    HomeDashboardConfig config_;
    bool customizeMode_ = false;
};
