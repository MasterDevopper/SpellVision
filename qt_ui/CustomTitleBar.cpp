#include "CustomTitleBar.h"
#include "ThemeManager.h"

#include <QContextMenuEvent>
#include <QCoreApplication>
#include <QDir>
#include <QEvent>
#include <QFileInfo>
#include <QButtonGroup>
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
    button->setObjectName(QStringLiteral("TitleBarMenuButton"));
    button->setCursor(Qt::PointingHandCursor);
    button->setFlat(true);
    button->setFixedHeight(26);
    button->setMinimumWidth(30);
    button->setSizePolicy(QSizePolicy::Minimum, QSizePolicy::Fixed);
    return button;
}

QToolButton *makeIconButton(const QString &name, QWidget *parent)
{
    auto *button = new QToolButton(parent);
    button->setObjectName(name);
    button->setCursor(Qt::PointingHandCursor);
    button->setFixedSize(24, 24);
    button->setAutoRaise(true);
    return button;
}



QStringList brandIconCandidates()
{
    QStringList starts = {QCoreApplication::applicationDirPath(), QDir::currentPath()};
    QStringList names = {
        QStringLiteral("icons/SpellVision.jpg"),
        QStringLiteral("icons/SpellVision.jpeg"),
        QStringLiteral("icons/SpellVision.png"),
        QStringLiteral("qt_ui/icons/SpellVision.jpg"),
        QStringLiteral("qt_ui/icons/SpellVision.jpeg"),
        QStringLiteral("qt_ui/icons/SpellVision.png"),
        QStringLiteral("SpellVision.jpg"),
        QStringLiteral("SpellVision.jpeg"),
        QStringLiteral("SpellVision.png")
    };

    QStringList out;
    for (const QString &start : starts)
    {
        QDir dir(start);
        for (int depth = 0; depth < 7; ++depth)
        {
            for (const QString &name : names)
                out << dir.filePath(name);
            if (!dir.cdUp())
                break;
        }
    }
    out.removeDuplicates();
    return out;
}

QPixmap loadBrandPixmap()
{
    for (const QString &path : brandIconCandidates())
    {
        if (!QFileInfo::exists(path))
            continue;
        QPixmap pm(path);
        if (!pm.isNull())
            return pm;
    }
    return {};
}

QPixmap roundedBrandPixmap(const QSize &size, int radius)
{
    const QPixmap source = loadBrandPixmap();
    if (source.isNull())
        return {};

    QPixmap scaled = source.scaled(size, Qt::KeepAspectRatioByExpanding, Qt::SmoothTransformation);
    QPixmap out(size);
    out.fill(Qt::transparent);

    QPainter painter(&out);
    painter.setRenderHint(QPainter::Antialiasing, true);
    QPainterPath clipPath;
    clipPath.addRoundedRect(QRectF(0, 0, size.width(), size.height()), radius, radius);
    painter.setClipPath(clipPath);
    painter.drawPixmap(0, 0, scaled);

    painter.setClipping(false);
    // Pilot: brand-badge frame reads the canonical Accent token (identical to the old
    // accentColor() on ArcaneGlass, but switches with the themeChanged broadcast).
    QPen border(ThemeManager::instance().color(ThemeManager::Color::Accent));
    border.setWidthF(1.0);
    painter.setPen(border);
    painter.drawRoundedRect(QRectF(0.5, 0.5, size.width() - 1.0, size.height() - 1.0), radius, radius);
    return out;
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
    setFixedHeight(34);
    setObjectName(QStringLiteral("CustomTitleBar"));
    // QWidget subclass: Qt auto-enables styled-background painting only for direct QWidget
    // instances, not subclasses. Without this (and with no paintEvent), the #CustomTitleBar
    // stylesheet gradient/border is computed but never drawn -- the dark window bg shows through.
    setAttribute(Qt::WA_StyledBackground, true);

    auto *layout = new QHBoxLayout(this);
    layout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight), ThemeManager::instance().spacing(ThemeManager::Spacing::Hairline), ThemeManager::instance().spacing(ThemeManager::Spacing::Tight), ThemeManager::instance().spacing(ThemeManager::Spacing::Hairline));
    layout->setSpacing(3);

    logoBadge_ = new QLabel(this);
    logoBadge_->setObjectName(QStringLiteral("SpellVisionLogoBadge"));
    logoBadge_->setAlignment(Qt::AlignCenter);
    logoBadge_->setFixedSize(22, 22);
    logoBadge_->setToolTip(QStringLiteral("SpellVision"));
    // Themed pixmap (badge frame) is generated in applyThemeStyling() so it re-colors on switch.

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
    searchPill_->setFixedHeight(26);
    searchPill_->setMinimumWidth(340);
    searchPill_->setMaximumWidth(520);
    searchPill_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

    auto *searchLayout = new QHBoxLayout(searchPill_);
    searchLayout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), 0, ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), 0);
    searchLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
    searchIconLabel_ = new QLabel(searchPill_);
    searchTextLabel_ = new QLabel(QStringLiteral("Search SpellVision"), searchPill_);
    searchTextLabel_->setObjectName(QStringLiteral("TitleBarSearchText"));
    searchShortcutLabel_ = new QLabel(QStringLiteral("Ctrl+Shift+P"), searchPill_);
    searchShortcutLabel_->setObjectName(QStringLiteral("TitleBarSearchShortcut"));
    searchLayout->addWidget(searchIconLabel_);
    searchLayout->addWidget(searchTextLabel_);
    searchLayout->addStretch(1);
    searchLayout->addWidget(searchShortcutLabel_);

    for (QObject *watched : {static_cast<QObject *>(logoBadge_),
                             static_cast<QObject *>(searchPill_),
                             static_cast<QObject *>(searchIconLabel_),
                             static_cast<QObject *>(searchTextLabel_),
                             static_cast<QObject *>(searchShortcutLabel_)})
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

    // Themed icon pixmaps are generated in applyThemeStyling() (called at ctor end +
    // on every themeChanged) so they re-color live on a theme switch.

    layoutButton_->setToolTip(QStringLiteral("Customize Layout"));
    primarySidebarButton_->setToolTip(QStringLiteral("Toggle Primary Sidebar"));
    bottomPanelButton_->setToolTip(QStringLiteral("Toggle Bottom Panel"));
    secondarySidebarButton_->setToolTip(QStringLiteral("Toggle Secondary Sidebar"));
    minButton_->setToolTip(QStringLiteral("Minimize"));
    maxButton_->setToolTip(QStringLiteral("Maximize / Restore"));
    closeButton_->setToolTip(QStringLiteral("Close"));

    // Phase 6: Simple/Advanced disclosure toggle (segmented). CONTROL ONLY -- it flips + persists the
    // global mode; the controls it gates are wired in Phase 7. Placed right of the pill (mockup).
    modeToggle_ = new QFrame(this);
    modeToggle_->setObjectName(QStringLiteral("TitleBarModeToggle"));
    modeToggle_->setToolTip(QStringLiteral("Simple / Advanced controls"));
    auto *modeLayout = new QHBoxLayout(modeToggle_);
    modeLayout->setContentsMargins(2, 2, 2, 2);
    modeLayout->setSpacing(2);
    const auto makeModeButton = [this](const QString &text) {
        auto *b = new QToolButton(modeToggle_);
        b->setObjectName(QStringLiteral("TitleBarModeButton"));
        b->setText(text);
        b->setCheckable(true);
        b->setCursor(Qt::PointingHandCursor);
        b->setToolButtonStyle(Qt::ToolButtonTextOnly);
        b->setFixedHeight(22);
        return b;
    };
    simpleButton_ = makeModeButton(QStringLiteral("Simple"));
    advancedButton_ = makeModeButton(QStringLiteral("Advanced"));
    simpleButton_->setChecked(true);
    auto *modeGroup = new QButtonGroup(this);
    modeGroup->setExclusive(true);
    modeGroup->addButton(simpleButton_);
    modeGroup->addButton(advancedButton_);
    modeLayout->addWidget(simpleButton_);
    modeLayout->addWidget(advancedButton_);
    // USER clicks only (clicked, not toggled) request the change; setDisclosureMode() flips the
    // checked state programmatically on restore WITHOUT re-emitting (the recurring activated lesson).
    connect(simpleButton_, &QToolButton::clicked, this, [this]() { emit disclosureModeChangeRequested(false); });
    connect(advancedButton_, &QToolButton::clicked, this, [this]() { emit disclosureModeChangeRequested(true); });

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
    layout->addSpacing(6);
    layout->addWidget(modeToggle_, 0, Qt::AlignVCenter);
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

    // THEME PILOT: paint the themed visuals from canonical tokens now, and re-run on
    // every theme switch. This subscription is what makes the title bar re-color live.
    applyThemeStyling();
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, &CustomTitleBar::applyThemeStyling);
}

void CustomTitleBar::applyThemeStyling()
{
    const ThemeManager &tm = ThemeManager::instance();
    const QColor iconStroke = tm.color(ThemeManager::Color::TextMid);

    // Paint case: regenerate the drawn pixmaps from the current tokens.
    if (logoBadge_)
    {
        const QPixmap brandBadge = roundedBrandPixmap(QSize(22, 22), 6);
        if (!brandBadge.isNull())
            logoBadge_->setPixmap(brandBadge);
        else
            logoBadge_->setText(QStringLiteral("SV"));
    }
    if (searchIconLabel_)
        searchIconLabel_->setPixmap(drawIcon(QStringLiteral("search"), iconStroke));

    const struct IconSpec { QToolButton *button; QString kind; } iconSpecs[] = {
        {layoutButton_, QStringLiteral("layout")},
        {primarySidebarButton_, QStringLiteral("sidebar-left")},
        {bottomPanelButton_, QStringLiteral("panel-bottom")},
        {secondarySidebarButton_, QStringLiteral("sidebar-right")},
        {minButton_, QStringLiteral("min")},
        {maxButton_, QStringLiteral("max")},
        {closeButton_, QStringLiteral("close")},
    };
    for (const IconSpec &spec : iconSpecs)
        if (spec.button)
            spec.button->setIcon(QIcon(drawIcon(spec.kind, iconStroke)));

    // String case (setStyleSheet path). These labels are styled by the shell stylesheet
    // via their object names (#TitleBarSearchText / #TitleBarSearchShortcut) on an
    // ANCESTOR (MainWindow) -- and that ancestor ID rule wins over a local override no
    // matter its specificity. So to let this widget OWN and switch their color, detach
    // them from that ancestor rule (clear the object name) and style them locally from
    // css() tokens. This is exactly the migration move for any shell-styled element: the
    // widget takes over its own theming instead of the shared generator.
    if (searchTextLabel_)
    {
        searchTextLabel_->setObjectName(QString());
        searchTextLabel_->setStyleSheet(
            QStringLiteral("color:%1;font-size:12px;font-weight:600;background:transparent;").arg(tm.css(ThemeManager::Color::TextMid)));
    }
    if (searchShortcutLabel_)
    {
        searchShortcutLabel_->setObjectName(QString());
        searchShortcutLabel_->setStyleSheet(
            QStringLiteral("color:%1;font-size:11px;font-weight:700;background:transparent;").arg(tm.css(ThemeManager::Color::TextLo)));
    }
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
        maxButton_->setIcon(QIcon(drawIcon(maximized ? QStringLiteral("restore") : QStringLiteral("max"),
                                           ThemeManager::instance().color(ThemeManager::Color::TextMid))));
}

void CustomTitleBar::setDisclosureMode(bool advanced)
{
    // Programmatic reflect (restore/sync). Exclusive group auto-unchecks the other; clicked is the
    // user signal so this setChecked never re-requests a change.
    QToolButton *target = advanced ? advancedButton_ : simpleButton_;
    if (target && !target->isChecked())
        target->setChecked(true);
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

    const bool interactive =
        child == logoBadge_ ||
        child == fileButton_ || child == editButton_ || child == viewButton_ ||
        child == generationButton_ || child == modelsButton_ || child == workflowsButton_ ||
        child == toolsButton_ || child == helpButton_ ||
        child == searchPill_ || child == searchIconLabel_ || child == searchTextLabel_ || child == searchShortcutLabel_ ||
        child == layoutButton_ || child == primarySidebarButton_ || child == bottomPanelButton_ ||
        child == secondarySidebarButton_ || child == minButton_ || child == maxButton_ || child == closeButton_;

    return !interactive;
}

bool CustomTitleBar::eventFilter(QObject *watched, QEvent *event)
{
    if (!event)
        return QWidget::eventFilter(watched, event);

    if ((watched == searchPill_ || watched == searchIconLabel_ || watched == searchTextLabel_ || watched == searchShortcutLabel_) && event->type() == QEvent::MouseButtonRelease)
    {
        emit commandPaletteRequested();
        return true;
    }

    if (watched == logoBadge_)
    {
        if (event->type() == QEvent::MouseButtonRelease)
        {
            if (const auto *mouseEvent = static_cast<QMouseEvent *>(event);
                mouseEvent && (mouseEvent->button() == Qt::LeftButton || mouseEvent->button() == Qt::RightButton))
            {
                emit systemMenuRequested(logoBadge_->mapToGlobal(logoBadge_->rect().bottomLeft()));
                return true;
            }
        }
        if (event->type() == QEvent::MouseButtonDblClick)
        {
            if (const auto *mouseEvent = static_cast<QMouseEvent *>(event);
                mouseEvent && mouseEvent->button() == Qt::LeftButton)
            {
                emit closeRequested();
                return true;
            }
        }
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
