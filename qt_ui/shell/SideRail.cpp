#include "shell/SideRail.h"

#include "ThemeManager.h"
#include "shell/ShellNavigationController.h"
#include "style/SvKit.h"
#include "style/SvStyle.h"

#include <QAbstractButton>
#include <QByteArray>
#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QFont>
#include <QFrame>
#include <QHash>
#include <QIcon>
#include <QPaintEvent>
#include <QPainter>
#include <QPixmap>
#include <QScrollArea>
#include <QScrollBar>
#include <QStyle>
#include <QStyleOption>
#include <QSvgRenderer>
#include <QToolButton>
#include <QVBoxLayout>

namespace spellvision::shell
{
namespace
{
QStringList railIconSearchRoots()
{
    QStringList roots;
    const QString appDir = QCoreApplication::applicationDirPath();
    roots << appDir
          << QDir(appDir).filePath(QStringLiteral("icons"))
          << QDir(appDir).filePath(QStringLiteral("../icons"))
          << QDir(appDir).filePath(QStringLiteral("../../qt_ui/icons"))
          << QDir(appDir).filePath(QStringLiteral("../../../qt_ui/icons"))
          << QDir::current().filePath(QStringLiteral("qt_ui/icons"))
          << QDir::current().filePath(QStringLiteral("icons"));
    // Walk up from app dir for source-tree qt_ui/icons during Debug runs.
    QDir climb(appDir);
    for (int i = 0; i < 6; ++i) {
        const QString candidate = climb.filePath(QStringLiteral("qt_ui/icons"));
        if (QDir(candidate).exists())
            roots << candidate;
        if (!climb.cdUp())
            break;
    }
    roots.removeDuplicates();
    return roots;
}

// The rail SVGs are authored with one fixed light stroke (#dfe6ef), which is
// ~1.1:1 against the Ivory Holograph surfaces -- i.e. invisible on the light
// preset. Re-ink them from the active theme instead of shipping per-theme
// asset pairs. Mirrors what CustomTitleBar::applyThemeStyling already does
// for its painted chrome glyphs.
QIcon tintedRailSvg(const QString &path)
{
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly))
        return {};
    QByteArray svg = file.readAll();
    file.close();
    if (svg.isEmpty())
        return {};

    const QByteArray ink =
        ThemeManager::instance().color(ThemeManager::Color::TextMid).name(QColor::HexRgb).toUtf8();
    svg.replace(QByteArrayLiteral("#dfe6ef"), ink);
    svg.replace(QByteArrayLiteral("#DFE6EF"), ink);
    svg.replace(QByteArrayLiteral("currentColor"), ink);

    QSvgRenderer renderer(svg);
    if (!renderer.isValid())
        return {};

    // Rail draws at 18px; carry 2x/3x frames so HiDPI stays crisp.
    QIcon icon;
    for (int px : {18, 24, 36, 54}) {
        QPixmap pm(px, px);
        pm.fill(Qt::transparent);
        QPainter painter(&pm);
        painter.setRenderHint(QPainter::Antialiasing, true);
        renderer.render(&painter);
        painter.end();
        icon.addPixmap(pm);
    }
    return icon;
}

QIcon loadRailIcon(const QString &iconName)
{
    // Map modeId → icon basename (SVG under qt_ui/icons/).
    static const QHash<QString, QString> kIconByMode = {
        {QStringLiteral("home"), QStringLiteral("home")},
        {QStringLiteral("chain"), QStringLiteral("chain")},
        {QStringLiteral("t2i"), QStringLiteral("t2i")},
        {QStringLiteral("i2i"), QStringLiteral("i2i")},
        {QStringLiteral("t2v"), QStringLiteral("t2v")},
        {QStringLiteral("i2v"), QStringLiteral("i2v")},
        {QStringLiteral("character"), QStringLiteral("character")},
        {QStringLiteral("concept"), QStringLiteral("concept")},
        {QStringLiteral("comic"), QStringLiteral("comic")},
        {QStringLiteral("gen3d"), QStringLiteral("gen3d")},
        {QStringLiteral("dataset"), QStringLiteral("dataset")},
        {QStringLiteral("workflows"), QStringLiteral("workflows")},
        {QStringLiteral("history"), QStringLiteral("history")},
        {QStringLiteral("inspiration"), QStringLiteral("inspiration")},
        {QStringLiteral("models"), QStringLiteral("models")},
        {QStringLiteral("settings"), QStringLiteral("settings")},
        {QStringLiteral("runtime"), QStringLiteral("runtime")},
        {QStringLiteral("train"), QStringLiteral("train")},
    };

    const QString base = kIconByMode.value(iconName.trimmed().toLower(), iconName.trimmed().toLower());
    if (base.isEmpty())
        return {};

    const QStringList exts = {QStringLiteral("svg"), QStringLiteral("png")};
    for (const QString &root : railIconSearchRoots()) {
        for (const QString &ext : exts) {
            const QString path = QDir(root).filePath(base + QLatin1Char('.') + ext);
            if (QFileInfo::exists(path)) {
                if (ext == QLatin1String("svg")) {
                    const QIcon tinted = tintedRailSvg(path);
                    if (!tinted.isNull())
                        return tinted;
                }
                QIcon icon(path);
                if (!icon.isNull())
                    return icon;
            }
        }
    }
    return {};
}
} // namespace

SideRail::SideRail(QWidget *parent)
    : QWidget(parent)
{
    auto &tm = ThemeManager::instance();
    const int snug = tm.spacing(ThemeManager::Spacing::Snug);
    const int card = tm.spacing(ThemeManager::Spacing::Card);

    // Outer rail: fixed width, brand badge PINNED at the top, and the mode column below it lives in a
    // QScrollArea so the rail SCROLLS instead of clipping the bottom entries once there are more pages
    // than fit the viewport (it was a plain non-scrolling QVBoxLayout with fixed-height buttons).
    setObjectName(QStringLiteral("SideRail"));
    setFixedWidth(tm.chrome(ThemeManager::Chrome::ModeRailWidth));
    auto *railLayout = new QVBoxLayout(this);
    railLayout->setContentsMargins(0, card, 0, card);
    railLayout->setSpacing(snug);

    // Brand lives in the title bar only — no second logo above Home.
    scroll_ = new QScrollArea(this);
    scroll_->setObjectName(QStringLiteral("SideRailScroll"));
    scroll_->setWidgetResizable(true);
    scroll_->setFrameShape(QFrame::NoFrame);
    scroll_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    scroll_->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    scroll_->setAutoFillBackground(false);
    scroll_->viewport()->setAutoFillBackground(false); // let the #SideRail gradient show through
    // Three rules, and none of them paints: the first two keep SvStyle from drawing a field panel
    // behind the whole rail (a QScrollArea is a QAbstractScrollArea), and the third reserves the
    // gutter. The gutter is geometry the rail cannot spare -- 64px of rail carries a 56px tile, so
    // the style's 8px default takes three pixels off the viewport and clips "Concept" and "Runtime"
    // by their last column. It is the width the deleted rule already asked for; what went with that
    // rule is the paint, a fixed steel handle that could not follow the theme it claimed to.
    // (verticalScrollBar()->setFixedWidth() does NOT do this: QAbstractScrollArea lays the gutter
    // out from the bar's sizeHint, which a fixed width leaves at PM_ScrollBarExtent. Measured.)
    scroll_->setStyleSheet(QStringLiteral(
        "QScrollArea#SideRailScroll { background: transparent; border: none; }"
        "QWidget#SideRailColumn { background: transparent; }"
        "QScrollArea#SideRailScroll QScrollBar:vertical { width: 5px; margin: 2px 0; }"));

    column_ = new QWidget;
    column_->setObjectName(QStringLiteral("SideRailColumn"));
    auto *layout = new QVBoxLayout(column_);
    layout->setContentsMargins(snug, 0, snug, 0);
    layout->setSpacing(snug);
    columnLayout_ = layout;

    // The trailing stretch is added up front and every entry goes in AHEAD of it, so the column ends
    // with a stretch no matter how many times addMode() is called. The order of the items it holds is
    // exactly the order the old loop produced.
    layout->addStretch(1);

    scroll_->setWidget(column_);
    railLayout->addWidget(scroll_, 1);
}

QToolButton *SideRail::makeButton(const QString &id, const QString &label, const QString &iconName)
{
    auto *button = new QToolButton(column_);
    button->setObjectName(QStringLiteral("SideRailButton"));
    kit::setRole(button, style::Role::Rail);
    button->setText(label);
    button->setToolTip(label);
    button->setCheckable(true);
    button->setAutoRaise(true);
    button->setIconSize(QSize(18, 18));
    button->setCursor(Qt::PointingHandCursor);

    const QIcon icon = loadRailIcon(iconName);
    if (!icon.isNull())
        button->setIcon(icon);
    applyButtonMetrics(button, !icon.isNull());

    // Pre-empt the Qt-internal "QFont::setPointSize: Point size <= 0" warning that fires on
    // rail-button :hover recompute: an explicit pixelSize means Qt's hover restyle reads a
    // valid size instead of the -1 "unset point size" sentinel. This is also the ONLY place
    // the rail label's size is set now -- shellStyleSheet's rule carries no font, because a
    // font-size there beats this line and 11px clips "Runtime" in a 56px tile.
    QFont railButtonFont = button->font();
    railButtonFont.setPixelSize(10); // slightly tighter under-icon labels
    button->setFont(railButtonFont);

    connect(button, &QToolButton::clicked, this, [this, id]()
            { emit modeActivated(id); });
    return button;
}

void SideRail::applyButtonMetrics(QToolButton *button, bool hasIcon) const
{
    if (!button)
        return;
    // Vertical only in this build; task 3 adds the horizontal metrics (ToolButtonTextBesideIcon at
    // Chrome::RailBarHeight). Without an icon the label has to carry the tile on its own -- the
    // graceful fallback the rail has always had.
    button->setFixedSize(56, 48); // icon + label room
    button->setToolButtonStyle(hasIcon ? Qt::ToolButtonTextUnderIcon : Qt::ToolButtonTextOnly);
}

void SideRail::addMode(const QString &id,
                       const QString &label,
                       const QString &iconName,
                       const QString &toolTip,
                       const QKeySequence &shortcut)
{
    if (id.isEmpty() || buttonsById_.contains(id))
        return;

    QToolButton *button = makeButton(id, label, iconName.isEmpty() ? id : iconName);
    if (!toolTip.isEmpty())
        button->setToolTip(toolTip);
    // VSCode-style hover: the tooltip shows the name + shortcut, and the shortcut actually
    // navigates (window-wide). QAbstractButton::setShortcut fires click() -> modeActivated.
    if (!shortcut.isEmpty())
    {
        button->setShortcut(shortcut);
        button->setToolTip(QStringLiteral("%1  (%2)")
                               .arg(toolTip.isEmpty() ? label : toolTip,
                                    shortcut.toString(QKeySequence::NativeText)));
    }

    columnLayout_->insertWidget(columnLayout_->count() - 1, button, 0, Qt::AlignHCenter);
    modes_.append(ModeEntry{id, iconName.isEmpty() ? id : iconName, button});
    buttonsById_.insert(id, button);
}

void SideRail::addGroupHeader(const QString &text)
{
    groupHeaders_.append(text);

    auto *separator = new QFrame(column_);
    separator->setObjectName(QStringLiteral("SideRailGroupSeparator"));
    separator->setFrameShape(QFrame::HLine);
    separator->setFixedHeight(1);
    separator->setProperty("svGroupLabel", text); // task 3 renders it as a label when horizontal
    columnLayout_->insertWidget(columnLayout_->count() - 1, separator);
}

void SideRail::setCurrentMode(const QString &id)
{
    // One rule decides which rail button is checked, and it is not duplicated here.
    QMap<QString, QAbstractButton *> buttons;
    for (const ModeEntry &entry : modes_)
        buttons.insert(entry.id, entry.button);
    ShellNavigationController::updateModeButtonState(buttons, id);
    currentMode_ = id;
}

void SideRail::setOrientation(Qt::Orientation orientation)
{
    if (orientation == orientation_)
        return;
    // Task 3 of the wave owns the horizontal rail. Refusing loudly beats half-turning: a rail that
    // silently accepted Qt::Horizontal here would keep its fixed width and its under-icon tiles and
    // look like a layout bug somewhere else.
    qWarning("SideRail::setOrientation: only Qt::Vertical is implemented in this build");
}

void SideRail::paintEvent(QPaintEvent *event)
{
    // QStyleSheetStyle fills a widget it recognises as a bare QWidget; a subclass has to ask for
    // PE_Widget itself or the #SideRail rule -- the rail's whole gradient and its edge hairline --
    // is simply not drawn.
    QStyleOption opt;
    opt.initFrom(this);
    QPainter painter(this);
    style()->drawPrimitive(QStyle::PE_Widget, &opt, &painter, this);
    QWidget::paintEvent(event);
}

QPoint SideRail::contentOrigin() const
{
    return orientation_ == Qt::Vertical ? QPoint(width(), 0) : QPoint(0, height());
}

QToolButton *SideRail::buttonFor(const QString &id) const
{
    return buttonsById_.value(id, nullptr);
}

QStringList SideRail::modeIds() const
{
    QStringList ids;
    ids.reserve(modes_.size());
    for (const ModeEntry &entry : modes_)
        ids << entry.id;
    return ids;
}

void SideRail::refreshIcons()
{
    for (const ModeEntry &entry : modes_)
    {
        const QIcon icon = loadRailIcon(entry.iconName);
        if (icon.isNull() || !entry.button)
            continue;
        entry.button->setIcon(icon);
        applyButtonMetrics(entry.button, true);
    }
}

} // namespace spellvision::shell
