#include "ModelCardDelegate.h"

#include "ModelCardModel.h"
#include "ModelThumbnailCache.h"
#include "../ThemeManager.h"

#include <QAbstractItemView>
#include <QFontMetrics>
#include <QPainter>
#include <QPainterPath>
#include <QPixmap>

namespace spellvision::assets
{

namespace
{
constexpr int kCardW = 208;
constexpr int kCardH = 300;
constexpr int kGap = 16;
constexpr int kPad = 8;
constexpr int kThumbMaster = 256; // Amendment A.4 — single 256px master, the card is the only consumer
} // namespace

int ModelCardDelegate::cardWidth() { return kCardW; }
int ModelCardDelegate::cardHeight() { return kCardH; }
int ModelCardDelegate::cellGap() { return kGap; }

ModelCardDelegate::ModelCardDelegate(ModelThumbnailCache *cache, QObject *parent)
    : QStyledItemDelegate(parent), cache_(cache)
{
    refreshTokens();
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, [this]() { refreshTokens(); });
}

void ModelCardDelegate::refreshTokens()
{
    tokens_ = DashboardSurfaceTokens::fromTheme(ThemeManager::instance());
}

QSize ModelCardDelegate::sizeHint(const QStyleOptionViewItem &, const QModelIndex &) const
{
    return QSize(kCardW + kGap, kCardH + kGap);
}

void ModelCardDelegate::paint(QPainter *painter, const QStyleOptionViewItem &option, const QModelIndex &index) const
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

    QColor borderCol = selected ? accent : (hovered ? t.borderStrong : t.borderSoft);
    painter->setPen(QPen(borderCol, selected ? 1.6 : 1.0));
    painter->drawPath(cardPath);

    // --- preview area (top 2/3), rounded + clipped ---
    const qreal previewH = card.height() * (2.0 / 3.0) - kPad * 1.5;
    const QRectF preview(card.left() + kPad, card.top() + kPad, card.width() - 2 * kPad, previewH);

    const QString previewPath = index.data(ModelCardModel::PreviewPathRole).toString();
    const QString type = index.data(ModelCardModel::TypeRole).toString();
    const QString family = index.data(ModelCardModel::FamilyRole).toString();

    // Viewport-driven: only kick thumbnail generation for cards actually on screen. QListView can
    // paint a margin of off-screen items during layout/repaint; without this guard the whole library
    // would transcode in the background (the exact "never pre-generate all" failure).
    bool onScreen = true;
    if (const auto *view = qobject_cast<const QAbstractItemView *>(option.widget))
        onScreen = view->viewport()->rect().intersects(option.rect);

    QPixmap pm;
    if (!previewPath.isEmpty() && cache_ && onScreen)
        pm = cache_->thumbnail(previewPath, previewPath, kThumbMaster);

    if (!pm.isNull())
    {
        // Cover-crop into the rounded preview rect (fills the area, no letterbox).
        painter->save();
        QPainterPath clip;
        clip.addRoundedRect(preview, t.radiusInset, t.radiusInset);
        painter->setClipPath(clip);
        QSizeF scaled(pm.size());
        scaled.scale(preview.size(), Qt::KeepAspectRatioByExpanding);
        QRectF target(QPointF(0, 0), scaled);
        target.moveCenter(preview.center());
        painter->drawPixmap(target, pm, QRectF(pm.rect()));
        painter->restore();
    }
    else if (previewPath.isEmpty() || (cache_ && cache_->isFailed(previewPath, kThumbMaster)))
    {
        // No sidecar (~43%), or the preview was undecodable -> the type-colored fallback tile,
        // card-proportioned (Amendment A.2). Never leave a card stuck loading.
        paintModelPlaceholder(painter, preview, t.radiusInset, type, family);
    }
    else
    {
        // Has a preview but the thumb is still generating -> quiet recessed surface (repaints when
        // thumbnailReady fires). Not the type tile, so it doesn't flash a color then swap to the image.
        QPainterPath loadPath;
        loadPath.addRoundedRect(preview, t.radiusInset, t.radiusInset);
        painter->fillPath(loadPath, t.panelInsetA);
    }

    // --- type badge (top-left of preview), subordinate to the preview ---
    if (!type.trimmed().isEmpty())
    {
        QFont badgeFont = theme.font(ThemeManager::Type::Caption);
        painter->setFont(badgeFont);
        const QFontMetrics bfm(badgeFont);
        const QString badge = type;
        const int bw = bfm.horizontalAdvance(badge) + 14;
        const int bh = bfm.height() + 6;
        const QRectF badgeRect(preview.left() + 6, preview.top() + 6, bw, bh);
        QPainterPath badgePath;
        badgePath.addRoundedRect(badgeRect, t.radiusChip, t.radiusChip);
        painter->fillPath(badgePath, dashboardWithAlpha(t.panelBaseB, 0.82));
        painter->setPen(QPen(dashboardWithAlpha(t.borderSoft, 0.9), 1.0));
        painter->drawPath(badgePath);
        painter->setPen(t.textSecondary);
        painter->drawText(badgeRect, Qt::AlignCenter, badge);
    }

    // --- name band (bottom 1/3) ---
    const QRectF band(card.left() + kPad, preview.bottom() + 8, card.width() - 2 * kPad,
                      card.bottom() - preview.bottom() - kPad - 8);

    const QString name = index.data(ModelCardModel::StrippedNameRole).toString();
    QFont nameFont = theme.font(ThemeManager::Type::Subtitle);
    painter->setFont(nameFont);
    const QFontMetrics nfm(nameFont);
    const QString elided = nfm.elidedText(name, Qt::ElideRight, static_cast<int>(band.width()));
    painter->setPen(t.textPrimary);
    painter->drawText(QRectF(band.left(), band.top(), band.width(), nfm.height() + 2),
                      Qt::AlignLeft | Qt::AlignVCenter, elided);

    if (!family.trimmed().isEmpty())
    {
        QFont famFont = theme.font(ThemeManager::Type::Caption);
        painter->setFont(famFont);
        painter->setPen(t.textMuted);
        painter->drawText(QRectF(band.left(), band.top() + nfm.height() + 4, band.width(), band.height() - nfm.height() - 4),
                          Qt::AlignLeft | Qt::AlignTop, family);
    }

    painter->restore();
}

} // namespace spellvision::assets
