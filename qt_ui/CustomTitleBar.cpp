#include "CustomTitleBar.h"

#include <QContextMenuEvent>
#include <QEvent>
#include <QFrame>
#include <QHBoxLayout>
#include <QLabel>
#include <QMouseEvent>
#include <QPainter>
#include <QPainterPath>
#include <QPen>
#include <QPushButton>
#include <QSizePolicy>
#include <QToolButton>
#include <QWindow>

namespace
{
QPushButton *makeMenuButton(const QString &text, QWidget *parent)
{
    auto *button = new QPushButton(text, parent);
    button->setCursor(Qt::PointingHandCursor);
    button->setFlat(true);
    button->setFixedHeight(24);
    button->setMinimumWidth(30);
    button->setSizePolicy(QSizePolicy::Minimum, QSizePolicy::Fixed);
    return button;
}

QToolButton *makeIconButton(const QString &name, QWidget *parent)
{
    auto *button = new QToolButton(parent);
    button->setObjectName(name);
    button->setCursor(Qt::PointingHandCursor);
    button->setFixedSize(22, 22);
    button->setAutoRaise(true);
    return button;
}

QPixmap drawIcon(const QString &kind, const QColor &stroke)
{
    QPixmap pm(16, 16);
    pm.fill(Qt::transparent);
    QPainter p(&pm);
    p.setRenderHint(QPainter::Antialiasing, true);
    QPen pen(stroke, 1.7, Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin);
    p.setPen(pen);
    p.setBrush(Qt::NoBrush);

    if (kind == QStringLiteral("search"))
    {
        p.drawEllipse(QRectF(2.5, 2.5, 7.5, 7.5));
        p.drawLine(QPointF(9.3, 9.3), QPointF(13.0, 13.0));
    }
    else if (kind == QStringLiteral("layout"))
    {
        p.drawRoundedRect(QRectF(2.0, 2.0, 12.0, 12.0), 2, 2);
        p.drawLine(QPointF(6.0, 2.6), QPointF(6.0, 13.4));
        p.drawLine(QPointF(2.6, 6.0), QPointF(13.4, 6.0));
    }
    else if (kind == QStringLiteral("sidebar-left"))
    {
        p.drawRoundedRect(QRectF(2.0, 2.0, 12.0, 12.0), 2, 2);
        p.fillRect(QRectF(2.6, 2.6, 3.0, 10.8), stroke);
        p.drawLine(QPointF(7.2, 6.0), QPointF(12.8, 6.0));
        p.drawLine(QPointF(7.2, 10.0), QPointF(12.8, 10.0));
    }
    else if (kind == QStringLiteral("panel-bottom"))
    {
        p.drawRoundedRect(QRectF(2.0, 2.0, 12.0, 12.0), 2, 2);
        p.fillRect(QRectF(2.6, 10.0, 10.8, 3.0), stroke);
        p.drawLine(QPointF(3.5, 6.0), QPointF(12.5, 6.0));
    }
    else if (kind == QStringLiteral("sidebar-right"))
    {
        p.drawRoundedRect(QRectF(2.0, 2.0, 12.0, 12.0), 2, 2);
        p.fillRect(QRectF(10.4, 2.6, 3.0, 10.8), stroke);
        p.drawLine(QPointF(3.2, 6.0), QPointF(8.8, 6.0));
        p.drawLine(QPointF(3.2, 10.0), QPointF(8.8, 10.0));
    }
    else if (kind == QStringLiteral("min"))
    {
        p.drawLine(QPointF(4.0, 11.5), QPointF(12.0, 11.5));
    }
    else if (kind == QStringLiteral("max"))
    {
        p.drawRect(QRectF(4.0, 4.0, 8.0, 8.0));
    }
    else if (kind == QStringLiteral("restore"))
    {
        p.drawRect(QRectF(5.5, 3.5, 6.0, 6.0));
        p.drawLine(QPointF(4.0, 6.0), QPointF(4.0, 12.0));
        p.drawLine(QPointF(4.0, 12.0), QPointF(10.0, 12.0));
    }
    else if (kind == QStringLiteral("close"))
    {
        p.drawLine(QPointF(4.0, 4.0), QPointF(12.0, 12.0));
        p.drawLine(QPointF(12.0, 4.0), QPointF(4.0, 12.0));
    }

    return pm;
}
}

CustomTitleBar::CustomTitleBar(QWidget *parent)
    : QWidget(parent)
{
    setFixedHeight(32);
    setObjectName(QStringLiteral("CustomTitleBar"));

    auto *layout = new QHBoxLayout(this);
    layout->setContentsMargins(10, 3, 10, 3);
    layout->setSpacing(3);

    logoBadge_ = new QWidget(this);
    logoBadge_->setObjectName(QStringLiteral("SpellVisionLogoBadge"));
    logoBadge_->setFixedSize(13, 13);
    logoBadge_->setToolTip(QStringLiteral("SpellVision"));

    titleLabel_ = new QLabel(QString(), this);
    titleLabel_->setObjectName(QStringLiteral("SpellVisionTitleLabel"));
    titleLabel_->hide();
    contextLabel_ = new QLabel(QString(), this);
    contextLabel_->setObjectName(QStringLiteral("SpellVisionContextLabel"));
    contextLabel_->hide();

    fileButton_ = makeMenuButton(QStringLiteral("File"), this);
    editButton_ = makeMenuButton(QStringLiteral("Edit"), this);
    viewButton_ = makeMenuButton(QStringLiteral("View"), this);
    generationButton_ = makeMenuButton(QStringLiteral("Generation"), this);
    modelsButton_ = makeMenuButton(QStringLiteral("Models"), this);
    workflowsButton_ = makeMenuButton(QStringLiteral("Workflows"), this);
    toolsButton_ = makeMenuButton(QStringLiteral("Tools"), this);
    helpButton_ = makeMenuButton(QStringLiteral("Help"), this);

    searchPill_ = new QFrame(this);
    searchPill_->setObjectName(QStringLiteral("TitleBarSearchPill"));
    searchPill_->setCursor(Qt::PointingHandCursor);
    searchPill_->setFixedHeight(24);
    searchPill_->setMinimumWidth(320);
    searchPill_->setMaximumWidth(480);
    searchPill_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

    auto *searchLayout = new QHBoxLayout(searchPill_);
    searchLayout->setContentsMargins(9, 0, 9, 0);
    searchLayout->setSpacing(6);
    searchIconLabel_ = new QLabel(searchPill_);
    searchIconLabel_->setPixmap(drawIcon(QStringLiteral("search"), QColor(QStringLiteral("#c7d4e7"))));
    searchTextLabel_ = new QLabel(QStringLiteral("Search SpellVision"), searchPill_);
    searchTextLabel_->setObjectName(QStringLiteral("TitleBarSearchText"));
    searchShortcutLabel_ = new QLabel(QStringLiteral("Ctrl+Shift+P"), searchPill_);
    searchShortcutLabel_->setObjectName(QStringLiteral("TitleBarSearchShortcut"));
    searchLayout->addWidget(searchIconLabel_);
    searchLayout->addWidget(searchTextLabel_);
    searchLayout->addStretch(1);
    searchLayout->addWidget(searchShortcutLabel_);

    for (QObject *watched : {static_cast<QObject *>(searchPill_), static_cast<QObject *>(searchIconLabel_), static_cast<QObject *>(searchTextLabel_), static_cast<QObject *>(searchShortcutLabel_)})
        watched->installEventFilter(this);

    auto *centerContainer = new QWidget(this);
    auto *centerLayout = new QHBoxLayout(centerContainer);
    centerLayout->setContentsMargins(0, 0, 0, 0);
    centerLayout->setSpacing(0);
    centerLayout->addStretch(1);
    centerLayout->addWidget(searchPill_);
    centerLayout->addStretch(1);

    layoutButton_ = makeIconButton(QStringLiteral("TitleBarLayoutButton"), this);
    primarySidebarButton_ = makeIconButton(QStringLiteral("TitleBarPrimarySidebarButton"), this);
    bottomPanelButton_ = makeIconButton(QStringLiteral("TitleBarBottomPanelButton"), this);
    secondarySidebarButton_ = makeIconButton(QStringLiteral("TitleBarSecondarySidebarButton"), this);
    minButton_ = makeIconButton(QStringLiteral("TitleBarMinButton"), this);
    maxButton_ = makeIconButton(QStringLiteral("TitleBarMaxButton"), this);
    closeButton_ = makeIconButton(QStringLiteral("TitleBarCloseButton"), this);

    for (QToolButton *b : {layoutButton_, primarySidebarButton_, bottomPanelButton_, secondarySidebarButton_, minButton_, maxButton_, closeButton_})
        b->setIconSize(QSize(10, 10));

    layoutButton_->setIcon(QIcon(drawIcon(QStringLiteral("layout"), QColor(QStringLiteral("#d7dce6")))));
    primarySidebarButton_->setIcon(QIcon(drawIcon(QStringLiteral("sidebar-left"), QColor(QStringLiteral("#d7dce6")))));
    bottomPanelButton_->setIcon(QIcon(drawIcon(QStringLiteral("panel-bottom"), QColor(QStringLiteral("#d7dce6")))));
    secondarySidebarButton_->setIcon(QIcon(drawIcon(QStringLiteral("sidebar-right"), QColor(QStringLiteral("#d7dce6")))));
    minButton_->setIcon(QIcon(drawIcon(QStringLiteral("min"), QColor(QStringLiteral("#d7dce6")))));
    maxButton_->setIcon(QIcon(drawIcon(QStringLiteral("max"), QColor(QStringLiteral("#d7dce6")))));
    closeButton_->setIcon(QIcon(drawIcon(QStringLiteral("close"), QColor(QStringLiteral("#d7dce6")))));

    layoutButton_->setToolTip(QStringLiteral("Customize Layout"));
    primarySidebarButton_->setToolTip(QStringLiteral("Toggle Primary Sidebar"));
    bottomPanelButton_->setToolTip(QStringLiteral("Toggle Bottom Panel"));
    secondarySidebarButton_->setToolTip(QStringLiteral("Toggle Secondary Sidebar"));
    minButton_->setToolTip(QStringLiteral("Minimize"));
    maxButton_->setToolTip(QStringLiteral("Maximize / Restore"));
    closeButton_->setToolTip(QStringLiteral("Close"));

    layout->addWidget(logoBadge_, 0, Qt::AlignVCenter);
    layout->addSpacing(4);
    layout->addWidget(fileButton_);
    layout->addWidget(editButton_);
    layout->addWidget(viewButton_);
    layout->addWidget(generationButton_);
    layout->addWidget(modelsButton_);
    layout->addWidget(workflowsButton_);
    layout->addWidget(toolsButton_);
    layout->addWidget(helpButton_);
    layout->addSpacing(6);
    layout->addWidget(centerContainer, 1);
    layout->addSpacing(4);
    layout->addWidget(layoutButton_);
    layout->addWidget(primarySidebarButton_);
    layout->addWidget(bottomPanelButton_);
    layout->addWidget(secondarySidebarButton_);
    layout->addSpacing(0);
    layout->addWidget(minButton_);
    layout->addWidget(maxButton_);
    layout->addWidget(closeButton_);

    connect(fileButton_, &QPushButton::clicked, this, [this]() { emitMenuSignal(QStringLiteral("file"), fileButton_); });
    connect(editButton_, &QPushButton::clicked, this, [this]() { emitMenuSignal(QStringLiteral("edit"), editButton_); });
    connect(viewButton_, &QPushButton::clicked, this, [this]() { emitMenuSignal(QStringLiteral("view"), viewButton_); });
    connect(generationButton_, &QPushButton::clicked, this, [this]() { emitMenuSignal(QStringLiteral("generation"), generationButton_); });
    connect(modelsButton_, &QPushButton::clicked, this, [this]() { emitMenuSignal(QStringLiteral("models"), modelsButton_); });
    connect(workflowsButton_, &QPushButton::clicked, this, [this]() { emitMenuSignal(QStringLiteral("workflows"), workflowsButton_); });
    connect(toolsButton_, &QPushButton::clicked, this, [this]() { emitMenuSignal(QStringLiteral("tools"), toolsButton_); });
    connect(helpButton_, &QPushButton::clicked, this, [this]() { emitMenuSignal(QStringLiteral("help"), helpButton_); });
    connect(layoutButton_, &QToolButton::clicked, this, [this]() { emit layoutMenuRequested(layoutButton_->mapToGlobal(layoutButton_->rect().bottomLeft())); });
    connect(primarySidebarButton_, &QToolButton::clicked, this, &CustomTitleBar::primarySidebarToggleRequested);
    connect(bottomPanelButton_, &QToolButton::clicked, this, &CustomTitleBar::bottomPanelToggleRequested);
    connect(secondarySidebarButton_, &QToolButton::clicked, this, &CustomTitleBar::secondarySidebarToggleRequested);
    connect(minButton_, &QToolButton::clicked, this, &CustomTitleBar::minimizeRequested);
    connect(maxButton_, &QToolButton::clicked, this, &CustomTitleBar::maximizeRestoreRequested);
    connect(closeButton_, &QToolButton::clicked, this, &CustomTitleBar::closeRequested);
}

void CustomTitleBar::setWindowTitleText(const QString &text)
{
    if (!titleLabel_)
        return;

    titleLabel_->setText(text);
    titleLabel_->setVisible(!text.trimmed().isEmpty());
}

void CustomTitleBar::setContextText(const QString &text)
{
    if (!contextLabel_)
        return;

    contextLabel_->setText(text);
    contextLabel_->setVisible(!text.trimmed().isEmpty());
}

void CustomTitleBar::setMaximized(bool maximized)
{
    if (maxButton_)
        maxButton_->setIcon(QIcon(drawIcon(maximized ? QStringLiteral("restore") : QStringLiteral("max"), QColor(QStringLiteral("#d7dce6")))));
}

QRect CustomTitleBar::commandPaletteAnchorRect() const
{
    if (!searchPill_)
        return {};
    const QPoint topLeft = searchPill_->mapToGlobal(QPoint(0, 0));
    return QRect(topLeft, searchPill_->size());
}

void CustomTitleBar::emitMenuSignal(const QString &menuId, QWidget *anchor)
{
    if (anchor)
        emit menuRequested(menuId, anchor->mapToGlobal(anchor->rect().bottomLeft()));
}

bool CustomTitleBar::isDraggableArea(const QPoint &pos) const
{
    QWidget *child = childAt(pos);
    if (!child)
        return true;

    for (QWidget *w = child; w && w != this; w = w->parentWidget())
    {
        if (w == searchPill_
            || w == fileButton_
            || w == editButton_
            || w == viewButton_
            || w == generationButton_
            || w == modelsButton_
            || w == workflowsButton_
            || w == toolsButton_
            || w == helpButton_
            || w == layoutButton_
            || w == primarySidebarButton_
            || w == bottomPanelButton_
            || w == secondarySidebarButton_
            || w == minButton_
            || w == maxButton_
            || w == closeButton_)
        {
            return false;
        }
    }

    return true;
}

bool CustomTitleBar::eventFilter(QObject *watched, QEvent *event)
{
    if ((watched == searchPill_ || watched == searchIconLabel_ || watched == searchTextLabel_ || watched == searchShortcutLabel_) && event && event->type() == QEvent::MouseButtonRelease)
    {
        emit commandPaletteRequested();
        return true;
    }
    return QWidget::eventFilter(watched, event);
}

void CustomTitleBar::mousePressEvent(QMouseEvent *event)
{
    if (!event || event->button() != Qt::LeftButton || !isDraggableArea(event->pos()))
    {
        QWidget::mousePressEvent(event);
        return;
    }
    if (QWindow *handle = window() ? window()->windowHandle() : nullptr)
    {
        if (handle->startSystemMove())
        {
            event->accept();
            return;
        }
    }
    QWidget::mousePressEvent(event);
}

void CustomTitleBar::mouseDoubleClickEvent(QMouseEvent *event)
{
    if (event && event->button() == Qt::LeftButton && isDraggableArea(event->pos()))
    {
        emit maximizeRestoreRequested();
        event->accept();
        return;
    }
    QWidget::mouseDoubleClickEvent(event);
}

void CustomTitleBar::contextMenuEvent(QContextMenuEvent *event)
{
    if (!event)
    {
        QWidget::contextMenuEvent(event);
        return;
    }

    emit systemMenuRequested(event->globalPos());
    event->accept();
}
