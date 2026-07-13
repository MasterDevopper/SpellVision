#pragma once

// Home gallery card. A close cousin of ModelCardDelegate (same DashboardSurfaceTokens + the same
// ModelThumbnailCache with the "only transcode on-screen cards" guard), but thumbnail-forward for
// outputs: a big cover-cropped preview, a mode badge (T2I/T2V/…), a play badge on video, and a single
// caption line. No favorite star / type badge / family text -- an output is the hero, not chrome.

#include "DashboardSurfaceTokens.h"

#include <QStyledItemDelegate>

namespace spellvision::assets
{
class ModelThumbnailCache;
}

class GalleryCardDelegate : public QStyledItemDelegate
{
    Q_OBJECT
public:
    explicit GalleryCardDelegate(spellvision::assets::ModelThumbnailCache *cache, QObject *parent = nullptr);

    static int cardWidth();
    static int cardHeight();
    static int cellGap();

    void paint(QPainter *painter, const QStyleOptionViewItem &option, const QModelIndex &index) const override;
    QSize sizeHint(const QStyleOptionViewItem &option, const QModelIndex &index) const override;

private:
    void refreshTokens();

    spellvision::assets::ModelThumbnailCache *cache_ = nullptr;
    DashboardSurfaceTokens tokens_;
};
