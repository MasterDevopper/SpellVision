#include "ModelCardView.h"

#include "ModelCardDelegate.h"
#include "ModelCardModel.h"
#include "../ThemeManager.h"

#include <QEvent>
#include <QFrame>
#include <QHBoxLayout>
#include <QMouseEvent>
#include <QPushButton>
#include <QScrollBar>
#include <QTimer>

namespace spellvision::assets
{

ModelCardView::ModelCardView(QWidget *parent)
    : QListView(parent)
{
    setViewMode(QListView::IconMode);
    setFlow(QListView::LeftToRight);
    setWrapping(true);
    setResizeMode(QListView::Adjust);   // reflow columns on resize
    setMovement(QListView::Static);
    setUniformItemSizes(true);          // perf: fixed cell size, no per-item measuring
    setSelectionMode(QAbstractItemView::SingleSelection);
    setEditTriggers(QAbstractItemView::NoEditTriggers);
    setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    setMouseTracking(true);
    setSpacing(0);                      // the delegate draws its own gap
    setFrameShape(QFrame::NoFrame);
    verticalScrollBar()->setSingleStep(48);

    // Transparent viewport so the shell gradient shows through the gaps between cards.
    viewport()->setAutoFillBackground(false);
    QPalette pal = viewport()->palette();
    pal.setColor(QPalette::Base, Qt::transparent);
    pal.setColor(QPalette::Window, Qt::transparent);
    viewport()->setPalette(pal);

    hideTimer_ = new QTimer(this);
    hideTimer_->setSingleShot(true);
    hideTimer_->setInterval(140);
    connect(hideTimer_, &QTimer::timeout, this, [this]() { hideOverlay(); });

    buildOverlay();

    // Drive hover from viewport moves (indexAt); leave/scroll hide via the debounce.
    viewport()->installEventFilter(this);
    connect(this, &QListView::entered, this, [this](const QModelIndex &index) { showOverlayFor(index); });
    connect(verticalScrollBar(), &QScrollBar::valueChanged, this, [this]() { hideOverlay(); });

    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, [this]() { applyOverlayStyle(); });
}

void ModelCardView::buildOverlay()
{
    overlay_ = new QFrame(viewport());
    overlay_->setObjectName(QStringLiteral("ModelCardHoverOverlay"));
    overlay_->hide();

    auto *row = new QHBoxLayout(overlay_);
    row->setContentsMargins(6, 6, 6, 6);
    row->setSpacing(6);

    primaryButton_ = new QPushButton(QStringLiteral("Load Model"), overlay_);
    primaryButton_->setObjectName(QStringLiteral("ModelCardPrimaryButton"));
    primaryButton_->setCursor(Qt::PointingHandCursor);
    inspectButton_ = new QPushButton(QStringLiteral("Inspect"), overlay_);
    inspectButton_->setObjectName(QStringLiteral("ModelCardInspectButton"));
    inspectButton_->setCursor(Qt::PointingHandCursor);

    row->addWidget(primaryButton_);
    row->addWidget(inspectButton_);

    overlay_->installEventFilter(this);
    primaryButton_->installEventFilter(this);
    inspectButton_->installEventFilter(this);

    connect(primaryButton_, &QPushButton::clicked, this, [this]() {
        if (hoverIndex_.isValid())
            emit loadRequested(hoverIndex_);
    });
    connect(inspectButton_, &QPushButton::clicked, this, [this]() {
        if (hoverIndex_.isValid())
            emit inspectRequested(hoverIndex_);
    });

    applyOverlayStyle();
}

void ModelCardView::applyOverlayStyle()
{
    ThemeManager &t = ThemeManager::instance();
    using C = ThemeManager::Color;
    const QString sheet = QStringLiteral(
        "#ModelCardHoverOverlay { background: %1; border: 1px solid %2; border-radius: 12px; }"
        "#ModelCardPrimaryButton { background: %3; color: %4; border: 1px solid %5; border-radius: 9px; padding: 6px 12px; %8 }"
        "#ModelCardPrimaryButton:hover { background: %6; }"
        "#ModelCardPrimaryButton:disabled { color: %7; background: %1; }"
        "#ModelCardInspectButton { background: %1; color: %4; border: 1px solid %5; border-radius: 9px; padding: 6px 12px; %8 }"
        "#ModelCardInspectButton:hover { background: %5; }")
        .arg(t.css(C::Surface2),      // %1 overlay bg / secondary btn
             t.css(C::BorderStrong),  // %2 overlay border
             t.css(C::Accent),        // %3 primary btn bg
             t.css(C::TextHi),        // %4 text
             t.css(C::Border),        // %5 borders / inspect hover
             t.css(C::AccentHover),   // %6 primary hover
             t.css(C::TextDisabled))  // %7 disabled text
        .arg(t.fontCss(ThemeManager::Type::Label)); // %8
    overlay_->setStyleSheet(sheet);
}

void ModelCardView::configureOverlayFor(const QModelIndex &index)
{
    const QString type = index.data(ModelCardModel::TypeRole).toString().trimmed().toLower();
    if (type == QStringLiteral("lora"))
    {
        primaryButton_->setText(QStringLiteral("Add LoRA"));
        primaryButton_->setEnabled(true);
        primaryButton_->setToolTip(QStringLiteral("Add to the LoRA stack (does not replace the model)"));
    }
    else if (type == QStringLiteral("vae"))
    {
        primaryButton_->setText(QStringLiteral("VAE"));
        primaryButton_->setEnabled(false);
        primaryButton_->setToolTip(QStringLiteral("No VAE slot yet — routing lands with a manual VAE slot"));
    }
    else
    {
        primaryButton_->setText(QStringLiteral("Load Model"));
        primaryButton_->setEnabled(true);
        primaryButton_->setToolTip(QStringLiteral("Load into the matching generation mode"));
    }
}

void ModelCardView::positionOverlay(const QModelIndex &index)
{
    const int gap = ModelCardDelegate::cellGap();
    const QRect cell = visualRect(index);
    const QRect card = cell.adjusted(gap / 2, gap / 2, -gap / 2, -gap / 2);
    const int previewH = card.height() * 2 / 3 - 12;
    const QRect preview(card.left(), card.top(), card.width(), previewH);

    const QSize os = overlay_->sizeHint();
    int ox = preview.center().x() - os.width() / 2;
    int oy = preview.bottom() - os.height() - 8;
    ox = qBound(card.left(), ox, card.right() - os.width());
    overlay_->setGeometry(ox, oy, os.width(), os.height());
    overlay_->raise();
}

void ModelCardView::showOverlayFor(const QModelIndex &index)
{
    if (!index.isValid())
        return;
    hideTimer_->stop();
    if (hoverIndex_ != index)
    {
        hoverIndex_ = index;
        configureOverlayFor(index);
    }
    positionOverlay(index);
    overlay_->show();
}

void ModelCardView::hideOverlay()
{
    if (overlay_)
        overlay_->hide();
    hoverIndex_ = QModelIndex();
}

bool ModelCardView::eventFilter(QObject *watched, QEvent *event)
{
    if (watched == viewport())
    {
        if (event->type() == QEvent::MouseMove)
        {
            auto *me = static_cast<QMouseEvent *>(event);
            const QModelIndex idx = indexAt(me->pos());
            if (idx.isValid())
                showOverlayFor(idx);
            else
                hideTimer_->start(); // over empty space -> debounce-hide
        }
        else if (event->type() == QEvent::Leave)
        {
            hideTimer_->start();
        }
    }
    else if (watched == overlay_ || watched == primaryButton_ || watched == inspectButton_)
    {
        // Cursor is on the overlay / its buttons -> keep it up.
        if (event->type() == QEvent::Enter)
            hideTimer_->stop();
        else if (event->type() == QEvent::Leave)
            hideTimer_->start();
    }
    return QListView::eventFilter(watched, event);
}

void ModelCardView::mouseDoubleClickEvent(QMouseEvent *event)
{
    const QModelIndex idx = indexAt(event->pos());
    if (idx.isValid())
    {
        emit loadRequested(idx);
        return;
    }
    QListView::mouseDoubleClickEvent(event);
}

} // namespace spellvision::assets
