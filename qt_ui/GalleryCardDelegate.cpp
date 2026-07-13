#include "GalleryCardDelegate.h"

#include "GalleryOutputModel.h"
#include "ThemeManager.h"
#include "assets/ModelThumbnailCache.h"

#include <QAbstractItemView>
#include <QFontMetrics>
#include <QPainter>
#include <QPainterPath>
#include <QPixmap>
#include <QPolygonF>

namespace
{
constexpr int kCardW = 204;
constexpr int kCardH = 220;
constexpr int kGap = 14;
constexpr int kPad = 8;
constexpr int kThumbMaster = 256;

void paintPlayGlyph(QPainter *painter, const QRectF &preview)
{
    const double d = qMin(preview.width(), preview.height()) * 0.30;
    QRectF badge(0, 0, d, d);
    badge.moveCenter(preview.center());
    painter->setPen(Qt::NoPen);
    painter->setBrush(QColor(0, 0, 0, 130));
    painter->drawEllipse(badge);
    painter->setBrush(QColor(255, 255, 255, 235));
    const double cx = badge.center().x();
    const double cy = badge.center().y();
    const double r = d * 0.24;
    QPolygonF tri;
    tri << QPointF(cx - r * 0.6, cy - r) << QPointF(cx - r * 0.6, cy + r) << QPointF(cx + r, cy);
    painter->drawPolygon(tri);
}
} // namespace

GalleryCardDelegate::GalleryCardDelegate(spellvision::assets::ModelThumbnailCache *cache, QObject *parent)
    : QStyledItemDelegate(parent), cache_(cache)
{
    refreshTokens();
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, [this]() { refreshTokens(); });
}

int GalleryCardDelegate::cardWidth() { return kCardW; }
int GalleryCardDelegate::cardHeight() { return kCardH; }
int GalleryCardDelegate::cellGap() { return kGap; }

void GalleryCardDelegate::refreshTokens()
{
    tokens_ = DashboardSurfaceTokens::fromTheme(ThemeManager::instance());
}

QSize GalleryCardDelegate::sizeHint(const QStyleOptionViewItem &, const QModelIndex &) const
{
    return QSize(kCardW + kGap, kCardH + kGap);
}

void GalleryCardDelegate::paint(QPainter *painter, const QStyleOptionViewItem &option, const QModelIndex &index) const
{
    painter->save();
    painter->setRenderHint(QPainter::Antialiasing, true);
    painter->setRenderHint(QPainter::SmoothPixmapTransform, true);

    ThemeManager &theme = ThemeManager::instance();
    const DashboardSurfaceTokens &t = tokens_;

    const QRectF card = QRectF(option.rect).adjusted(kGap / 2.0, kGap / 2.0, -kGap / 2.0, -kGap / 2.0);
    const bool selected = option.state & QStyle::State_Selected;
    const bool hovered = option.state & QStyle::State_MouseOver;
    const QColor accent = theme.color(ThemeManager::Color::Accent);

    // --- card surface ---
    QPainterPath cardPath;
    cardPath.addRoundedRect(card, t.radiusPanel, t.radiusPanel);
    QLinearGradient grad(card.topLeft(), card.bottomLeft());
    grad.setColorAt(0.0, t.panelRaisedA);
    grad.setColorAt(1.0, t.panelRaisedB);
    painter->fillPath(cardPath, grad);
    painter->setPen(QPen(selected ? accent : (hovered ? t.borderStrong : t.borderSoft), selected ? 1.8 : 1.0));
    painter->drawPath(cardPath);

    // --- preview (thumbnail-forward: the top ~78% of the card) ---
    const qreal previewH = card.height() * 0.78 - kPad;
    const QRectF preview(card.left() + kPad, card.top() + kPad, card.width() - 2 * kPad, previewH);

    const QString thumbPath = index.data(GalleryOutputModel::ThumbnailPathRole).toString();
    const bool isVideo = index.data(GalleryOutputModel::IsVideoRole).toBool();

    bool onScreen = true;
    if (const auto *view = qobject_cast<const QAbstractItemView *>(option.widget))
        onScreen = view->viewport()->rect().intersects(option.rect);

    QPixmap pm;
    if (!thumbPath.isEmpty() && cache_ && onScreen)
        pm = cache_->thumbnail(thumbPath, thumbPath, kThumbMaster);

    painter->save();
    QPainterPath clip;
    clip.addRoundedRect(preview, t.radiusInset, t.radiusInset);
    painter->setClipPath(clip);
    if (!pm.isNull())
    {
        // Cover-crop: fill the preview, crop overflow, no letterbox.
        QSizeF scaled(pm.size());
        scaled.scale(preview.size(), Qt::KeepAspectRatioByExpanding);
        QRectF target(QPointF(0, 0), scaled);
        target.moveCenter(preview.center());
        painter->drawPixmap(target, pm, QRectF(pm.rect()));
    }
    else
    {
        // Video without a poster, or an image whose thumb is still generating / undecodable: a quiet
        // recessed surface (repaints when thumbnailReady fires for images).
        painter->fillPath(clip, isVideo ? t.panelInsetB : t.panelInsetA);
    }
    painter->restore();

    // --- play badge on video ---
    if (isVideo)
        paintPlayGlyph(painter, preview);

    // --- mode badge (top-left of the preview) ---
    const QString mode = index.data(GalleryOutputModel::ModeIdRole).toString().toUpper();
    if (!mode.isEmpty())
    {
        QFont badgeFont = theme.font(ThemeManager::Type::Caption);
        painter->setFont(badgeFont);
        const QFontMetrics bfm(badgeFont);
        const int bw = bfm.horizontalAdvance(mode) + 14;
        const int bh = bfm.height() + 6;
        const QRectF badgeRect(preview.left() + 6, preview.top() + 6, bw, bh);
        QPainterPath badgePath;
        badgePath.addRoundedRect(badgeRect, t.radiusChip, t.radiusChip);
        painter->fillPath(badgePath, dashboardWithAlpha(t.panelBaseB, 0.84));
        painter->setPen(QPen(dashboardWithAlpha(t.borderSoft, 0.9), 1.0));
        painter->drawPath(badgePath);
        painter->setPen(t.textSecondary);
        painter->drawText(badgeRect, Qt::AlignCenter, mode);
    }

    // --- caption band (bottom): a single elided line (prompt snippet / filename) ---
    const QRectF band(card.left() + kPad + 2, preview.bottom() + 5, card.width() - 2 * kPad - 4,
                      card.bottom() - preview.bottom() - kPad - 5);
    const QString title = index.data(GalleryOutputModel::TitleRole).toString();
    QFont nameFont = theme.font(ThemeManager::Type::Caption);
    painter->setFont(nameFont);
    const QFontMetrics nfm(nameFont);
    painter->setPen(t.textSecondary);
    painter->drawText(band, Qt::AlignLeft | Qt::AlignVCenter,
                      nfm.elidedText(title, Qt::ElideRight, static_cast<int>(band.width())));

    painter->restore();
}
