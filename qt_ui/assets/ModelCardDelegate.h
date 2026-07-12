#pragma once

// Model Library Arc — S1 (design doc 22, Amendment A.2). Paints one uniform card: rounded card
// (radiusPanel), a top-2/3 rounded preview (image cover-cropped, or the type-colored fallback tile
// at card proportions), a bottom-1/3 stripped-name band, and a small type badge. Pure paint — hover
// actions live on the view's overlay (ModelCardView), so the delegate stays fast + virtualized.

#include "../DashboardSurfaceTokens.h"

#include <QStyledItemDelegate>

namespace spellvision::assets
{

class ModelThumbnailCache;

class ModelCardDelegate : public QStyledItemDelegate
{
    Q_OBJECT
public:
    explicit ModelCardDelegate(ModelThumbnailCache *cache, QObject *parent = nullptr);

    static int cardWidth();
    static int cardHeight();
    static int cellGap();
    // The favorite-star hit rect for an item cell, in the same coords as QListView::visualRect —
    // shared with ModelCardView so paint + click-hit-test agree.
    static QRect starRect(const QRect &cellRect);

    void paint(QPainter *painter, const QStyleOptionViewItem &option, const QModelIndex &index) const override;
    QSize sizeHint(const QStyleOptionViewItem &option, const QModelIndex &index) const override;

private:
    void refreshTokens();

    ModelThumbnailCache *cache_ = nullptr;
    DashboardSurfaceTokens tokens_;
};

} // namespace spellvision::assets
