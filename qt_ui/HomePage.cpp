#include "HomePage.h"

#include "GalleryCardDelegate.h"
#include "GalleryOutputModel.h"
#include "ThemeManager.h"
#include "assets/ModelThumbnailCache.h"

#include <QFrame>
#include <QHBoxLayout>
#include <QLabel>
#include <QListView>
#include <QShowEvent>
#include <QStackedWidget>
#include <QVBoxLayout>

namespace
{
QLabel *makeStatChip(QWidget *parent)
{
    auto *chip = new QLabel(parent);
    chip->setObjectName(QStringLiteral("HomeStatChip"));
    chip->setAlignment(Qt::AlignVCenter | Qt::AlignLeft);
    return chip;
}
} // namespace

HomePage::HomePage(QWidget *parent)
    : QWidget(parent)
{
    setObjectName(QStringLiteral("HomePage"));

    auto *outer = new QVBoxLayout(this);
    const int m = ThemeManager::instance().spacing(ThemeManager::Spacing::Card);
    outer->setContentsMargins(m, m, m, m);
    outer->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));

    // --- Dashboard band (subordinate context) --------------------------------------------------
    auto *band = new QFrame(this);
    band->setObjectName(QStringLiteral("HomeDashboardBand"));
    auto *bandLayout = new QHBoxLayout(band);
    bandLayout->setContentsMargins(m, ThemeManager::instance().spacing(ThemeManager::Spacing::Tight),
                                   m, ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
    bandLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));

    auto *heading = new QLabel(QStringLiteral("Your work"), band);
    heading->setObjectName(QStringLiteral("HomeBandHeading"));
    bandLayout->addWidget(heading);
    bandLayout->addStretch(1);
    // Only the genuinely-additive stats live here: the bottom bar already carries VRAM / queue /
    // backend health, so the band doesn't duplicate them -- it carries your body of work + library.
    bandRenders_ = makeStatChip(band);
    bandModels_ = makeStatChip(band);
    bandLayout->addWidget(bandRenders_);
    bandLayout->addWidget(bandModels_);
    outer->addWidget(band, 0);

    // --- Gallery (hero) ------------------------------------------------------------------------
    thumbs_ = new spellvision::assets::ModelThumbnailCache(this);
    galleryModel_ = new GalleryOutputModel(this);
    galleryDelegate_ = new GalleryCardDelegate(thumbs_, this);

    galleryView_ = new QListView(this);
    galleryView_->setObjectName(QStringLiteral("HomeGallery"));
    galleryView_->setModel(galleryModel_);
    galleryView_->setItemDelegate(galleryDelegate_);
    galleryView_->setViewMode(QListView::IconMode);
    galleryView_->setResizeMode(QListView::Adjust); // reflow columns on resize
    galleryView_->setMovement(QListView::Static);
    galleryView_->setUniformItemSizes(true);
    galleryView_->setSelectionMode(QAbstractItemView::SingleSelection);
    galleryView_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    galleryView_->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    galleryView_->setFrameShape(QFrame::NoFrame);
    galleryView_->setMouseTracking(true);
    galleryView_->setSpacing(0); // inter-card gap lives in the delegate sizeHint
    galleryView_->viewport()->setAttribute(Qt::WA_Hover, true);

    // A landed thumbnail repaints the visible cards (the cache returns non-null on the next paint).
    connect(thumbs_, &spellvision::assets::ModelThumbnailCache::thumbnailReady, this,
            [this](const QString &, int) {
                if (galleryView_)
                    galleryView_->viewport()->update();
            });

    // Click an output -> open it in its originating cockpit.
    connect(galleryView_, &QListView::clicked, this, [this](const QModelIndex &index) {
        if (!index.isValid())
            return;
        const QString path = index.data(GalleryOutputModel::PathRole).toString();
        const QString mode = index.data(GalleryOutputModel::ModeIdRole).toString();
        if (!path.isEmpty())
            emit openOutputRequested(mode, path);
    });

    // --- Empty state ---------------------------------------------------------------------------
    auto *empty = new QWidget(this);
    empty->setObjectName(QStringLiteral("HomeGalleryEmpty"));
    auto *emptyLayout = new QVBoxLayout(empty);
    emptyLayout->addStretch(1);
    auto *emptyTitle = new QLabel(QStringLiteral("No renders yet"), empty);
    emptyTitle->setObjectName(QStringLiteral("HomeEmptyTitle"));
    emptyTitle->setAlignment(Qt::AlignHCenter);
    auto *emptySub = new QLabel(
        QStringLiteral("Your generated images and videos land here.\nHead to Text to Image on the left rail to make your first."),
        empty);
    emptySub->setObjectName(QStringLiteral("HomeEmptySub"));
    emptySub->setAlignment(Qt::AlignHCenter);
    emptySub->setWordWrap(true);
    emptyLayout->addWidget(emptyTitle, 0, Qt::AlignHCenter);
    emptyLayout->addSpacing(6);
    emptyLayout->addWidget(emptySub, 0, Qt::AlignHCenter);
    emptyLayout->addStretch(1);

    galleryStack_ = new QStackedWidget(this);
    galleryStack_->addWidget(galleryView_); // 0
    galleryStack_->addWidget(empty);        // 1
    outer->addWidget(galleryStack_, 1);

    applyTheme();
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, &HomePage::applyTheme);

    reloadGallery();
}

void HomePage::reloadGallery()
{
    if (!galleryModel_ || !galleryStack_)
        return;
    const int n = galleryModel_->reload();
    galleryStack_->setCurrentIndex(n > 0 ? 0 : 1);
    updateDashboardBand();
    if (galleryView_)
        galleryView_->viewport()->update();
}

void HomePage::updateDashboardBand()
{
    if (bandRenders_)
    {
        const int n = galleryModel_ ? galleryModel_->outputCount() : 0;
        bandRenders_->setText(QStringLiteral("%1%2 renders").arg(n).arg(n >= 120 ? QStringLiteral("+") : QString()));
    }
    if (bandModels_)
        bandModels_->setText(modelCount_ >= 0 ? QStringLiteral("%1 models").arg(modelCount_)
                                              : QStringLiteral("— models"));
}

void HomePage::setRuntimeSummary(const QString &, int, int, int, const QString &, const QString &,
                                 const QString &, const QString &, int)
{
    // Intentionally a no-op: VRAM / queue / backend health are the bottom bar's job; the Home band
    // deliberately doesn't duplicate them. Kept for MainWindow source compatibility.
}

void HomePage::setModelCount(int count)
{
    modelCount_ = count;
    updateDashboardBand();
}

void HomePage::showEvent(QShowEvent *event)
{
    QWidget::showEvent(event);
    reloadGallery(); // fresh scan every time Home is shown, so new renders appear
}

void HomePage::applyTheme()
{
    ThemeManager &tm = ThemeManager::instance();
    using C = ThemeManager::Color;
    setStyleSheet(QStringLiteral(
                      "#HomePage { background: %1; }"
                      "#HomeGallery { background: transparent; }"
                      "#HomeDashboardBand { background: %2; border: 1px solid %3; border-radius: 12px; }"
                      "#HomeBandHeading { color: %4; font-size: 15px; font-weight: 700; background: transparent; }"
                      "#HomeStatChip { color: %5; background: %6; border: 1px solid %3; border-radius: 11px;"
                      " padding: 3px 12px; font-size: 12px; }"
                      "#HomeEmptyTitle { color: %4; font-size: 18px; font-weight: 700; background: transparent; }"
                      "#HomeEmptySub { color: %5; font-size: 13px; background: transparent; }")
                      .arg(tm.css(C::Surface0))    // %1 page bg
                      .arg(tm.css(C::Surface1))    // %2 band bg
                      .arg(tm.css(C::Border))      // %3 borders
                      .arg(tm.css(C::TextHi))      // %4 headings
                      .arg(tm.css(C::TextMid))     // %5 secondary text
                      .arg(tm.css(C::Surface2)));  // %6 chip bg
    updateDashboardBand();
}

// --- Legacy dashboard surface: gallery-first Home ignores the launchpad content, but keeps these so
//     MainWindow's existing calls/connections compile. Card setters simply refresh the gallery. -------
void HomePage::setDashboardConfig(const HomeDashboardConfig &config) { config_ = config; }
HomeDashboardConfig HomePage::dashboardConfig() const { return config_; }
void HomePage::setCustomizeMode(bool enabled) { customizeMode_ = enabled; }
bool HomePage::isCustomizeMode() const { return customizeMode_; }
void HomePage::setHeroStarterPreview(const HomeStarterPreview &) {}
void HomePage::setWorkflowCards(const QVector<HomeWorkflowCard> &) {}
void HomePage::setRecentOutputCards(const QVector<HomeRecentOutputCard> &) {}
void HomePage::setFavoriteCards(const QVector<HomeFavoriteCard> &) {}
void HomePage::resetDashboardContentToDefaults() {}
void HomePage::refreshAppDataSources(bool) { reloadGallery(); }
