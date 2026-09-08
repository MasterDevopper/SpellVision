#include "shell/SideRail.h"

#include "ThemeManager.h"
#include "shell/ShellNavigationController.h"
#include "style/SvKit.h"
#include "style/SvStyle.h"

#include <QAbstractButton>
#include <QBoxLayout>
#include <QByteArray>
#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QFont>
#include <QFontMetrics>
#include <QFrame>
#include <QHash>
#include <QIcon>
#include <QLabel>
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

// The vertical tile: icon over label, the shape the rail has always had. It is 56 wide inside a
// 64 px rail, which is the 8 px the scroll gutter needs -- see the gutter note in the constructor.
constexpr int kVerticalTileWidth = 56;
constexpr int kVerticalTileHeight = 48;
// The horizontal tile is as wide as its label, and never narrower than this. The floor is what makes
// a horizontal tile unambiguously WIDER than the vertical one at every label the rail ships ("3D" is
// two characters), which is the property the shape test asserts.
constexpr int kHorizontalTileMinWidth = 72;
constexpr int kIconTextGap = 6;      // glyph to label, text-beside-icon
constexpr int kTileTextPadding = 20; // 10 each side, matching Role::Rail's tile breathing room

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
    // The mode strip lives in a QScrollArea so the rail SCROLLS instead of clipping its last entries
    // once there are more pages than fit (it was a plain non-scrolling QVBoxLayout with fixed-height
    // buttons). The brand lives in the title bar only -- no second logo above Home.
    //
    // NOTHING here decides the rail's SHAPE. Its direction, its fixed dimension, its margins, its
    // scrollbar policies and its button metrics all come from applyOrientation(), which runs once at
    // the end of this constructor and again on every setOrientation(). That is the point of the
    // class: one place answers "which way does the rail lie", instead of a constructor and a setter
    // that have to be kept saying the same thing.
    setObjectName(QStringLiteral("SideRail"));
    railLayout_ = new QVBoxLayout(this);

    scroll_ = new QScrollArea(this);
    scroll_->setObjectName(QStringLiteral("SideRailScroll"));
    scroll_->setWidgetResizable(true);
    scroll_->setFrameShape(QFrame::NoFrame);
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
        "QScrollArea#SideRailScroll QScrollBar:vertical { width: 5px; margin: 2px 0; }"
        "QScrollArea#SideRailScroll QScrollBar:horizontal { height: 5px; margin: 0 2px; }"));

    column_ = new QWidget;
    column_->setObjectName(QStringLiteral("SideRailColumn"));
    columnLayout_ = new QVBoxLayout(column_);

    // The trailing stretch is added up front and every entry goes in AHEAD of it, so the strip ends
    // with a stretch no matter how many times addMode() is called. The order of the items it holds is
    // exactly the order the old loop produced.
    columnLayout_->addStretch(1);

    scroll_->setWidget(column_);
    railLayout_->addWidget(scroll_, 1);

    applyOrientation();
}

// One function decides the rail's shape, and both the constructor and setOrientation() go through it.
void SideRail::applyOrientation()
{
    auto &tm = ThemeManager::instance();
    const int snug = tm.spacing(ThemeManager::Spacing::Snug);
    const int card = tm.spacing(ThemeManager::Spacing::Card);
    const bool vertical = orientation_ == Qt::Vertical;

    // A QVBoxLayout IS a QBoxLayout with a direction -- the subclasses differ by nothing else -- so
    // the swap is setDirection(), not a new layout object. Building a fresh QHBoxLayout would have to
    // re-parent every button and re-insert the trailing stretch in the right place, which is three
    // chances to drop a button in exchange for nothing.
    railLayout_->setDirection(vertical ? QBoxLayout::TopToBottom : QBoxLayout::LeftToRight);
    railLayout_->setContentsMargins(vertical ? 0 : card, vertical ? card : 0,
                                    vertical ? 0 : card, vertical ? card : 0);
    railLayout_->setSpacing(snug);

    columnLayout_->setDirection(railLayout_->direction());
    columnLayout_->setContentsMargins(vertical ? snug : 0, vertical ? 0 : snug,
                                      vertical ? snug : 0, vertical ? 0 : snug);
    columnLayout_->setSpacing(snug);

    // The rail is fixed ACROSS its thickness and free ALONG its length, so the constraint it is no
    // longer using has to be released. setFixedWidth/setFixedHeight each write a min AND a max, and a
    // max that survives the turn silently keeps the rail in the shape it just left -- with every
    // other symptom (the layouts, the tiles, contentOrigin) saying it turned.
    if (vertical)
    {
        setMinimumHeight(0);
        setMaximumHeight(QWIDGETSIZE_MAX);
        setFixedWidth(tm.chrome(ThemeManager::Chrome::ModeRailWidth));
    }
    else
    {
        setMinimumWidth(0);
        setMaximumWidth(QWIDGETSIZE_MAX);
        setFixedHeight(tm.chrome(ThemeManager::Chrome::RailBarHeight));
    }

    // The strip scrolls ALONG its length, never across it: a bar that could scroll vertically inside
    // 44 px would hide half a tile rather than reveal one.
    scroll_->setHorizontalScrollBarPolicy(vertical ? Qt::ScrollBarAlwaysOff : Qt::ScrollBarAsNeeded);
    scroll_->setVerticalScrollBarPolicy(vertical ? Qt::ScrollBarAsNeeded : Qt::ScrollBarAlwaysOff);

    for (const ModeEntry &entry : modes_)
    {
        if (!entry.button)
            continue;
        applyButtonMetrics(entry.button, !entry.button->icon().isNull());
        columnLayout_->setAlignment(entry.button, crossAxisAlignment());
    }
    for (const GroupEntry &group : groups_)
    {
        applyGroupHeaderForm(group.header, group.text);
        columnLayout_->setAlignment(group.header, crossAxisAlignment());
    }
}

Qt::Alignment SideRail::crossAxisAlignment() const
{
    return orientation_ == Qt::Vertical ? Qt::Alignment(Qt::AlignHCenter)
                                        : Qt::Alignment(Qt::AlignVCenter);
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
    // Without an icon the label carries the tile on its own -- the graceful fallback the rail has
    // always had, in either orientation.
    if (orientation_ == Qt::Vertical)
    {
        button->setFixedSize(kVerticalTileWidth, kVerticalTileHeight); // icon + label room
        button->setToolButtonStyle(hasIcon ? Qt::ToolButtonTextUnderIcon : Qt::ToolButtonTextOnly);
        return;
    }
    // Lying down, the label moves BESIDE the glyph: the tile gets wider and, at RailBarHeight, shorter.
    button->setToolButtonStyle(hasIcon ? Qt::ToolButtonTextBesideIcon : Qt::ToolButtonTextOnly);
    button->setFixedSize(horizontalTileWidth(button, hasIcon),
                         ThemeManager::instance().chrome(ThemeManager::Chrome::RailBarHeight));
}

int SideRail::horizontalTileWidth(const QToolButton *button, bool hasIcon) const
{
    if (!button)
        return kHorizontalTileMinWidth;
    const QFontMetrics metrics(button->font());
    const int glyph = hasIcon ? button->iconSize().width() + kIconTextGap : 0;
    return qMax(kHorizontalTileMinWidth,
                metrics.horizontalAdvance(button->text()) + glyph + kTileTextPadding);
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

    columnLayout_->insertWidget(columnLayout_->count() - 1, button, 0, crossAxisAlignment());
    modes_.append(ModeEntry{id, iconName.isEmpty() ? id : iconName, button});
    buttonsById_.insert(id, button);
}

void SideRail::addGroupHeader(const QString &text)
{
    // A QLabel IS a QFrame, which is the whole reason one widget carries both forms: with a frame
    // shape and no text it draws exactly the hairline the vertical rail wants, and with text and no
    // frame it draws the caption the horizontal one wants. Two widgets swapped by orientation would
    // be two things to keep in step for a boundary that is one thing.
    auto *header = new QLabel(column_);
    // #SideRailCaption is the rail's small-caption rule in shellStyleSheet (colour, type and letter
    // spacing -- no paint), so the boundary follows the preset instead of carrying its own ink.
    header->setObjectName(QStringLiteral("SideRailCaption"));
    // A widget the style can paint has to say what it IS. It is rail furniture; Role::Rail is what
    // the rail's own buttons declare, and on a label the style reads the role and draws nothing.
    kit::setRole(header, style::Role::Rail);
    header->setProperty("svGroupLabel", text);
    applyGroupHeaderForm(header, text);
    columnLayout_->insertWidget(columnLayout_->count() - 1, header, 0, crossAxisAlignment());
    groups_.append(GroupEntry{text, header});
}

void SideRail::applyGroupHeaderForm(QLabel *header, const QString &text) const
{
    if (!header)
        return;
    if (orientation_ == Qt::Vertical)
    {
        // The rail that ships is FLAT -- MainWindow has said so since the CREATE/MANAGE/SYSTEM chrome
        // was removed -- so the vertical boundary is a hairline that is kept and not drawn. Showing it
        // moves every Manage and System tile down by 1 px plus a spacing step, and an orientation task
        // does not get to restyle the rail that ships. setVisible(true) is the whole of un-hiding it.
        header->setText(QString());
        header->setContentsMargins(0, 0, 0, 0);
        header->setFrameShape(QFrame::HLine);
        header->setFixedHeight(1);
        header->setVisible(false);
        return;
    }
    // Lying down, the boundary is a labelled one: CREATE / MANAGE / SYSTEM between the groups. The
    // fixed height the hairline took has to be released or the caption is one pixel tall.
    const int snug = ThemeManager::instance().spacing(ThemeManager::Spacing::Snug);
    header->setFrameShape(QFrame::NoFrame);
    header->setMinimumHeight(0);
    header->setMaximumHeight(QWIDGETSIZE_MAX);
    header->setContentsMargins(snug, 0, snug, 0);
    header->setAlignment(Qt::AlignCenter);
    header->setText(text.toUpper());
    header->setVisible(true);
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
    orientation_ = orientation;
    applyOrientation();
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
