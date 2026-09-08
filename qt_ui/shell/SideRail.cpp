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
#include <QResizeEvent>
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
// An icon-only tile: the 18px glyph in the same breathing room, and nothing else. This is the
// narrowest a tile is allowed to be, and reaching it is what the whole density ladder is for.
constexpr int kIconOnlyTileWidth = 18 + kTileTextPadding;
// The STANDING rail collapsed to glyphs (spec section 2.1's Canvas column): 48 px of rail carrying a
// 40 px tile, which leaves the same 8 px the scroll gutter takes out of the 64 px form. The tile is
// square because there is no label under the glyph to make it taller than it is wide.
constexpr int kCompactRailWidth = 48;
constexpr int kCompactTileSide = 40;

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
        // The rail's thickness follows the rung it was asked for, because a 64 px column carrying a
        // 40 px glyph tile would reclaim nothing -- and reclaiming the widest piece of chrome on the
        // page is the whole reason Canvas asks.
        setFixedWidth(requested_ == Density::IconOnly
                          ? kCompactRailWidth
                          : tm.chrome(ThemeManager::Chrome::ModeRailWidth));
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

    // Standing up, the rail does not measure itself -- it wears the rung it was ASKED for, which is
    // Full unless a layout requested plainer. Lying down, the bar picks the richest form that fits
    // the width it currently has, and never richer than the request. Forced, because an orientation
    // change has to re-apply every tile even when the density it lands on is the one it was in.
    applyDensity(true);
}

// The bar decides from its own content. Nothing here reads a window size, and that is the point: a
// breakpoint at 1180 stops being true the day a mode is added, and this rail has already gone from
// eight modes to sixteen.
SideRail::Density SideRail::fittingDensity() const
{
    // Standing up the rail has never measured itself, and it still does not: it runs out of HEIGHT,
    // not width, and it already scrolls for that. What it now does is honour a request.
    if (orientation_ == Qt::Vertical)
        return requested_;
    const int available = width();
    if (available <= 0)
        return density_; // never laid out: keep what we have rather than degrade on a zero
    Density fits = Density::IconOnly;
    if (requiredWidthFor(Density::Full) <= available)
        fits = Density::Full;
    else if (requiredWidthFor(Density::NoCaptions) <= available)
        fits = Density::NoCaptions;
    // The PLAINER of the two, and the enum is ordered richest-to-plainest so that is a qMax. A
    // request may not make the bar richer than its width affords, and its width may not make it
    // richer than the layout asked for.
    return static_cast<Density>(qMax(static_cast<int>(fits), static_cast<int>(requested_)));
}

void SideRail::setDensityRequest(Density density)
{
    if (requested_ == density)
        return;
    requested_ = density;
    // Through applyOrientation, not applyDensity: the rail's FIXED DIMENSION now depends on the rung
    // as well as on the direction, and applyOrientation is the one function that decides the shape.
    // Two places setting the rail's width is exactly what this class was extracted to end.
    applyOrientation();
}

int SideRail::requiredWidthFor(Density density) const
{
    auto &tm = ThemeManager::instance();
    const int snug = tm.spacing(ThemeManager::Spacing::Snug);
    const int card = tm.spacing(ThemeManager::Spacing::Card);

    int items = 0;
    int total = 2 * card; // the strip's own left/right margins, lying down

    for (const ModeEntry &entry : modes_)
    {
        if (!entry.button)
            continue;
        const bool hasIcon = !entry.button->icon().isNull();
        // A tile with NO icon keeps its label at every density -- an empty tile is not a
        // degradation, it is a missing button.
        total += (density == Density::IconOnly && hasIcon)
            ? kIconOnlyTileWidth
            : labelledTileWidth(entry.button, hasIcon);
        ++items;
    }
    for (const GroupEntry &group : groups_)
    {
        const int boundary = groupBoundaryWidth(group.header, group.text, density);
        if (boundary <= 0)
            continue; // hidden, and a QBoxLayout skips a hidden item entirely, its spacing included
        total += boundary;
        ++items;
    }
    if (items > 1)
        total += snug * (items - 1);
    return total;
}

int SideRail::groupBoundaryWidth(const QLabel *header, const QString &text, Density density) const
{
    if (!header || orientation_ == Qt::Vertical)
        return 0; // the vertical rail ships flat: the boundary is kept and not drawn
    if (density == Density::Full)
    {
        const QFontMetrics metrics(header->font());
        return metrics.horizontalAdvance(text.toUpper())
            + 2 * ThemeManager::instance().spacing(ThemeManager::Spacing::Snug);
    }
    // The caption is the first thing the bar gives up, and a 1px hairline is what replaces it --
    // the grouping has to keep reading from order AND separation, or dropping the words has quietly
    // dropped the grouping too.
    //
    // The hairline then survives the LAST rung as well, which is a correction: it used to be hidden
    // at IconOnly, so Create / Manage / System read from order alone at exactly the width where the
    // tiles have also lost their labels -- the rung that needs the structure most was the one
    // without it. It costs 1px plus a spacing step per boundary, 39px over the three the shell
    // ships, and it does not move either threshold this app can reach.
    return 1;
}

void SideRail::applyDensity(bool force)
{
    if (applyingDensity_)
        return;
    const Density wanted = fittingDensity();
    if (!force && wanted == density_)
        return;

    applyingDensity_ = true;
    density_ = wanted;
    for (const ModeEntry &entry : modes_)
    {
        if (!entry.button)
            continue;
        applyButtonMetrics(entry.button, !entry.button->icon().isNull());
        entry.button->setToolTip(toolTipFor(entry));
        columnLayout_->setAlignment(entry.button, crossAxisAlignment());
    }
    for (const GroupEntry &group : groups_)
    {
        applyGroupHeaderForm(group.header, group.text);
        columnLayout_->setAlignment(group.header, crossAxisAlignment());
    }
    applyingDensity_ = false;
}

// A tile that has given up its label says its name in its tooltip instead. Composed from the two
// halves the entry kept, never from whatever the last density left on the button, so a bar that
// degrades and recovers twenty times still reads the same.
QString SideRail::toolTipFor(const ModeEntry &entry) const
{
    // Keyed to the DENSITY and nothing else. It used to short-circuit on `orientation_ == Vertical`,
    // which was true only for as long as a standing rail could not reach IconOnly: the moment Canvas
    // asks it to, that test would drop the label from the tile AND from the tooltip, and sixteen
    // unlabelled glyphs is precisely the "nothing becomes unidentifiable" promise being broken.
    if (density_ != Density::IconOnly || entry.label.isEmpty())
        return entry.toolTip;
    if (entry.toolTip.isEmpty())
        return entry.label;
    if (entry.toolTip.startsWith(entry.label))
        return entry.toolTip; // the label already opens the tooltip; do not say it twice
    return QStringLiteral("%1  -  %2").arg(entry.label, entry.toolTip);
}

void SideRail::resizeEvent(QResizeEvent *event)
{
    QWidget::resizeEvent(event);
    applyDensity();
}

Qt::Alignment SideRail::crossAxisAlignment() const
{
    // Standing up, a tile is 56 wide in a 64 rail and is centred in the slack. Lying down there IS
    // no slack to centre in, so the answer is NO ALIGNMENT, which in a QBoxLayout means "fill the
    // cross axis" -- the tile becomes exactly as tall as the strip can give it.
    //
    // That is not a preference. A 44 px tile inside a 44 px bar cannot also carry the strip's 8 px
    // margins, and an alignment pins the tile at its own height and lets the layout clip the
    // difference: measured on the shipped Workspaces capture, a tile asking for 44 was drawn 26 tall
    // and the checked marker along its bottom edge was simply not on screen. Filling also absorbs
    // the horizontal scrollbar when the bar overflows, which takes another five rows -- a fixed
    // height would have to know about that and would be wrong again the day the scrollbar changed.
    return orientation_ == Qt::Vertical ? Qt::Alignment(Qt::AlignHCenter) : Qt::Alignment();
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
    // The checked-tile marker follows the rail's axis, and SvStyle draws it (Role::Rail in
    // paintButtonPanel) with no way to see the rail from the button it is painting. So the button
    // carries the answer, re-stated on every turn. Vertical leaves it false, which is the branch the
    // shipped rail has always taken.
    button->setProperty("svRailHorizontal", orientation_ == Qt::Horizontal);
    button->update();
    // Without an icon the label carries the tile on its own -- the graceful fallback the rail has
    // always had, in either orientation.
    if (orientation_ == Qt::Vertical)
    {
        // A tile with NO icon keeps its label at every rung -- an empty tile is not a degradation,
        // it is a missing button. Same rule requiredWidthFor() applies lying down.
        if (density_ == Density::IconOnly && hasIcon)
        {
            button->setFixedSize(kCompactTileSide, kCompactTileSide);
            button->setToolButtonStyle(Qt::ToolButtonIconOnly);
            return;
        }
        button->setFixedSize(kVerticalTileWidth, kVerticalTileHeight); // icon + label room
        button->setToolButtonStyle(hasIcon ? Qt::ToolButtonTextUnderIcon : Qt::ToolButtonTextOnly);
        return;
    }
    // Lying down, the label moves BESIDE the glyph: the tile is as wide as its label needs and as
    // tall as the strip has left, which is the bar's height less its margins and less the horizontal
    // scrollbar when there is one. Only the WIDTH is fixed here -- the height is released so the
    // layout can fill it (see crossAxisAlignment), because a tile that names its own height is a
    // tile the strip clips.
    if (!hasIcon)
        button->setToolButtonStyle(Qt::ToolButtonTextOnly);
    else
        button->setToolButtonStyle(density_ == Density::IconOnly ? Qt::ToolButtonIconOnly
                                                                 : Qt::ToolButtonTextBesideIcon);
    button->setMinimumHeight(0);
    button->setMaximumHeight(QWIDGETSIZE_MAX);
    button->setFixedWidth(horizontalTileWidth(button, hasIcon));
}

int SideRail::horizontalTileWidth(const QToolButton *button, bool hasIcon) const
{
    if (!button)
        return kHorizontalTileMinWidth;
    if (density_ == Density::IconOnly && hasIcon)
        return kIconOnlyTileWidth;
    return labelledTileWidth(button, hasIcon);
}

int SideRail::labelledTileWidth(const QToolButton *button, bool hasIcon) const
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
    // The tooltip is captured AFTER the shortcut has been folded into it, because that composed
    // string is the one an icon-only tile has to prefix its label onto -- and the button's own
    // tooltip is not a safe place to read it back from, since a later density will have rewritten it.
    modes_.append(ModeEntry{id, iconName.isEmpty() ? id : iconName, button, label, button->toolTip()});
    buttonsById_.insert(id, button);
    // A new mode can be the one that no longer fits.
    applyDensity();
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
    applyDensity();
}

void SideRail::applyGroupHeaderForm(QLabel *header, const QString &text) const
{
    if (!header)
        return;

    // ONE widget, three forms, and every branch releases BOTH constraints before it sets its own.
    // A min/max left over from the form the boundary just left is how a caption ends up one pixel
    // tall -- it was already true of the height when the rail learned to lie down, and adding a
    // fixed WIDTH to the hairline made it true of the width too.
    header->setMinimumHeight(0);
    header->setMaximumHeight(QWIDGETSIZE_MAX);
    header->setMinimumWidth(0);
    header->setMaximumWidth(QWIDGETSIZE_MAX);
    header->setContentsMargins(0, 0, 0, 0);

    if (orientation_ == Qt::Vertical)
    {
        // The rail that ships is FLAT -- MainWindow has said so since the CREATE/MANAGE/SYSTEM chrome
        // was removed -- so the vertical boundary is a hairline that is kept and not drawn. Showing it
        // moves every Manage and System tile down by 1 px plus a spacing step, and an orientation task
        // does not get to restyle the rail that ships. setVisible(true) is the whole of un-hiding it.
        header->setText(QString());
        header->setFrameShape(QFrame::HLine);
        header->setFixedHeight(1);
        header->setVisible(false);
        return;
    }
    if (density_ != Density::Full)
    {
        // The caption is the first thing the bar gives up, and it is REPLACED rather than deleted:
        // dropping the words must not also drop the GROUPING, which then has to read from order and
        // separation. One pixel of separation, plus its spacing step, at every rung below Full --
        // including the narrowest, where the tiles have lost their labels too and the structure is
        // the only thing left saying where Create ends and Manage begins.
        header->setText(QString());
        header->setFrameShape(QFrame::VLine);
        header->setFixedWidth(1);
        header->setVisible(true);
        return;
    }
    // Lying down with room to spare, the boundary is a labelled one: CREATE / MANAGE / SYSTEM.
    const int snug = ThemeManager::instance().spacing(ThemeManager::Spacing::Snug);
    header->setFrameShape(QFrame::NoFrame);
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
    // And RE-DECIDE. This runs on every theme change, and a theme is free to hand the rail a
    // different icon size or a different label font -- either of which changes what a tile costs and
    // therefore which rung of the ladder fits. Without this the bar keeps the decision it made under
    // the old theme until something happens to resize it, which is the clipped bar coming back by a
    // second route: switching presets instead of narrowing the window.
    applyDensity(true);
}

} // namespace spellvision::shell
