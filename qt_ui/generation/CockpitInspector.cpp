#include "CockpitInspector.h"
#include "../ThemeManager.h"
#include "../style/SvKit.h"

#include <QAbstractButton>
#include <QButtonGroup>
#include <QHBoxLayout>
#include <QLabel>
#include <QPushButton>
#include <QScrollArea>
#include <QStackedWidget>
#include <QVBoxLayout>
#include <QWidget>

#include <utility>

namespace
{
// The collapsed column: a strip of glyphs and nothing else. 48 px is the thickness the spec gives
// the collapsed activity rail (section 2.1), so the two vertical strips read as one system.
constexpr int kCollapsedWidth = 48;
constexpr int kCollapsedTile = 34;
// The un-budgeted range the inspector opens with, before the page's first adaptive pass has told it
// anything. Named because setCollapsed() has to be able to restore it: an inspector collapsed before
// a budget ever arrived must expand back to the range it had, not to a number invented here.
constexpr int kDefaultMinWidth = 300;
constexpr int kDefaultMaxWidth = 480;
constexpr int kBudgetFloor = 280;
constexpr int kBudgetCeiling = 460;

// One glyph per tab, in tab order. Chosen from the set this tree already ships and proves it can
// render; the name itself moves to the tooltip, which is the same bargain SideRail's icon-only rung
// strikes -- nothing becomes unidentifiable, it just stops spelling itself out.
const char *const kTabGlyphs[4] = {"\xE2\x97\x86",   // U+25C6 black diamond -- Model
                                   "\xE2\x9C\xA6",   // U+2726 black four-pointed star -- Sampling
                                   "\xE2\x96\xA3",   // U+25A3 square containing square -- Output
                                   "\xE2\x9A\x99"};  // U+2699 gear -- Advanced
} // namespace

CockpitInspector::CockpitInspector(QWidget *parent)
    : QFrame(parent)
{
    setObjectName(QStringLiteral("CockpitInspector"));
    setAttribute(Qt::WA_StyledBackground, true);

    // Adaptive default — callers refine via setWidthBudget() from the page layout pass.
    // Floor stays high enough for the Model Stack form; ceiling leaves canvas room at half-screen.
    setMinimumWidth(kDefaultMinWidth);
    setMaximumWidth(kDefaultMaxWidth);
    setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Expanding);

    auto *col = new QVBoxLayout(this);
    col->setContentsMargins(0, 0, 0, 0);
    col->setSpacing(0);

    tabNames_ = {QStringLiteral("Model"),
                 QStringLiteral("Sampling"),
                 QStringLiteral("Output"),
                 QStringLiteral("Advanced")};

    auto *tabBar = new QWidget(this);
    tabBar->setObjectName(QStringLiteral("InspectorTabBar"));
    tabBar_ = tabBar;
    // A QHBoxLayout IS a QBoxLayout with a direction, so the tab bar's turn into a vertical strip is
    // a setDirection() and not a second layout -- no button is re-parented, re-created or dropped,
    // which is the whole reason the collapse can be lossless.
    auto *tabRow = new QHBoxLayout(tabBar);
    tabRow_ = tabRow;
    tabRow->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight),
                               ThemeManager::instance().spacing(ThemeManager::Spacing::Tight),
                               ThemeManager::instance().spacing(ThemeManager::Spacing::Tight), 0);
    tabRow->setSpacing(2);

    tabGroup_ = new QButtonGroup(this);
    tabGroup_->setExclusive(true);

    stack_ = new QStackedWidget(this);
    stack_->setObjectName(QStringLiteral("InspectorStack"));

    int index = 0;
    for (const QString &name : std::as_const(tabNames_))
    {
        auto *btn = new QPushButton(name, tabBar);
        btn->setObjectName(QStringLiteral("InspectorTab"));
        btn->setProperty("svRole", QStringLiteral("tab"));
        btn->setCheckable(true);
        btn->setCursor(Qt::PointingHandCursor);
        btn->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
        // Allow tabs to compress at half-screen instead of forcing the column wider than the canvas.
        btn->setMinimumWidth(0);
        if (index == 0)
            btn->setChecked(true);
        tabGroup_->addButton(btn, index);
        tabRow->addWidget(btn, 1);

        // Scrollable body — relocated control sets (Model stack, Advanced rows) can be tall.
        auto *scroll = new QScrollArea(stack_);
        scroll->setObjectName(QStringLiteral("InspectorTabScroll"));
        scroll->setWidgetResizable(true);
        scroll->setFrameShape(QFrame::NoFrame);
        // Prefer vertical scroll over horizontal clip; content should reflow but keep a safety net.
        scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
        scroll->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
        scroll->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);

        auto *content = new QWidget(scroll);
        content->setObjectName(QStringLiteral("InspectorTabContent"));
        auto *contentLayout = new QVBoxLayout(content);
        contentLayout->setContentsMargins(10, 10, 10, 12);
        contentLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
        content->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Minimum);
        content->setMinimumWidth(0);
        scroll->setWidget(content);

        stack_->addWidget(scroll);
        tabLayouts_[index] = contentLayout;
        ++index;
    }

    // Always in the strip, inert until the strip is a strip -- see the header. Added after the tabs
    // so it is the tail of the row in either direction.
    tabTail_ = new QWidget(tabBar);
    tabTail_->setObjectName(QStringLiteral("InspectorTabTail"));
    // HIDDEN, not zero-sized. A QBoxLayout skips a hidden widget and the spacing that would have
    // gone with it; a 0x0 visible one still costs the row its 2 px seam, which measured as a real
    // 0.0005 of the frame between an Instrument capture taken with this widget and one taken
    // without. Instrument has to come back to the pixel, so the tail is not there at all.
    tabTail_->setVisible(false);
    tabRow->addWidget(tabTail_, 0);

    col->addWidget(tabBar, 0);
    col->addWidget(stack_, 1);

    // A glyph in the collapsed strip does two things: it selects its tab and it opens the column.
    // Clicking the glyph that is ALREADY selected closes it again, so the push is a toggle the user
    // can always get out of -- the strip never leaves the canvas in a state with no way back.
    connect(tabGroup_, &QButtonGroup::idClicked, this, [this](int id) {
        const int previous = stack_ ? stack_->currentIndex() : -1;
        if (stack_)
            stack_->setCurrentIndex(id);
        if (collapsed_)
        {
            collapsed_ = false;
            applyExpandedForm();
            peeking_ = true;
            emit collapsedChanged(false);
        }
        else if (peeking_ && id == previous)
        {
            collapsed_ = true;
            peeking_ = false;
            applyCollapsedForm();
            emit collapsedChanged(true);
        }
    });

    auto *readiness = new QFrame(this);
    readinessStrip_ = readiness;
    readiness->setObjectName(QStringLiteral("InspectorReadinessStrip"));
    spellvision::kit::setSurface(readiness, spellvision::style::Surface::Inset);
    auto *readinessLayout = new QHBoxLayout(readiness);
    readinessLayout->setContentsMargins(12, 8, 12, 8);
    readinessText_ = new QLabel(QStringLiteral("Readiness — select a checkpoint to generate."), readiness);
    readinessText_->setObjectName(QStringLiteral("InspectorReadinessText"));
    readinessText_->setWordWrap(true);
    readinessLayout->addWidget(readinessText_, 1);
    col->addWidget(readiness, 0);
}

QVBoxLayout *CockpitInspector::tabContentLayout(Tab tab) const
{
    return tabLayouts_[static_cast<int>(tab)];
}

void CockpitInspector::setTabVisible(Tab tab, bool visible)
{
    const int id = static_cast<int>(tab);
    if (auto *btn = tabGroup_->button(id))
        btn->setVisible(visible);

    // Edge case: never leave a hidden tab selected (the body would show blank). Move selection to
    // the first still-visible tab.
    if (!visible && stack_ && stack_->currentIndex() == id)
    {
        for (int i = 0; i < stack_->count(); ++i)
        {
            QAbstractButton *b = tabGroup_->button(i);
            if (b && b->isVisible())
            {
                b->setChecked(true);
                stack_->setCurrentIndex(i);
                break;
            }
        }
    }
}

void CockpitInspector::setWidthBudget(int preferredWidth)
{
    // Floor: Model Stack form + chips still readable.
    // Ceiling: leave canvas breathing room at ~half of a 1440-class desktop restore width.
    budget_ = qBound(kBudgetFloor, preferredWidth, kBudgetCeiling);
    // THE TRAP IN THIS CLASS. The budget is recomputed from the page's width on every resize, so it
    // keeps arriving while the column is a 48 px strip. Recording it and NOT applying it is what
    // lets the strip stay a strip through a window resize and still expand back to a real budget.
    if (collapsed_)
        return;
    applyWidthBudget();
}

void CockpitInspector::applyWidthBudget()
{
    if (budget_ <= 0)
    {
        // No adaptive pass has run yet, so the range the constructor opened with is still the truth.
        setMinimumWidth(kDefaultMinWidth);
        setMaximumWidth(kDefaultMaxWidth);
        updateGeometry();
        return;
    }
    const int w = budget_;
    // Preferred width with equal min/max so HBox stretch doesn't over-grow the inspector
    // (canvas keeps the remaining space). Avoid setFixedWidth so layout can still settle.
    setMinimumWidth(w);
    setMaximumWidth(w);
    updateGeometry();

    // Keep tab scroll content from reporting a preferred width larger than the budget —
    // that was still able to push the whole cockpit row past the window edge.
    if (stack_) {
        for (int i = 0; i < stack_->count(); ++i) {
            if (auto *scroll = qobject_cast<QScrollArea *>(stack_->widget(i))) {
                scroll->setMinimumWidth(0);
                if (QWidget *inner = scroll->widget()) {
                    inner->setMinimumWidth(0);
                    inner->setMaximumWidth(QWIDGETSIZE_MAX);
                    // Cap the content's effective width to the viewport so sizeHint cannot
                    // outgrow the inspector (combo long-path sizeHints were the main offender).
                    inner->setMaximumWidth(qMax(200, w - 8));
                }
            }
        }
    }
}

// Canvas's inspector. The state is one bool and the two forms are stated in full, so this is
// idempotent by ASKING rather than by remembering: called twice with the same value it re-asserts
// the shape, which is what makes it safe at the tail of a page builder and safe to call from a
// layout that may or may not have been applied already.
void CockpitInspector::setCollapsed(bool collapsed)
{
    const bool changed = collapsed_ != collapsed;
    collapsed_ = collapsed;
    // A peek is a click on a glyph, and the layout deciding the form ends one either way.
    peeking_ = false;
    if (collapsed)
        applyCollapsedForm();
    else
        applyExpandedForm();
    if (changed)
        emit collapsedChanged(collapsed);
}

void CockpitInspector::applyCollapsedForm()
{
    auto &theme = ThemeManager::instance();
    const int tight = theme.spacing(ThemeManager::Spacing::Tight);
    if (tabRow_)
    {
        tabRow_->setDirection(QBoxLayout::TopToBottom);
        tabRow_->setContentsMargins(tight, tight, tight, tight);
    }
    for (int i = 0; i < tabNames_.size(); ++i)
    {
        QAbstractButton *btn = tabGroup_ ? tabGroup_->button(i) : nullptr;
        if (!btn)
            continue;
        btn->setText(QString::fromUtf8(kTabGlyphs[i]));
        // The label is not lost, it moves. An icon-only tile that cannot say its own name is a tile
        // the user has to click to identify.
        btn->setToolTip(tabNames_.at(i));
        btn->setFixedSize(kCollapsedTile, kCollapsedTile);
    }
    if (tabTail_)
    {
        tabTail_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Expanding);
        tabTail_->setVisible(true);
    }
    // HIDDEN, NOT DESTROYED. Every control in every tab keeps its value, its signal connections and
    // its place in its layout; all that changes is whether the column is on screen.
    if (stack_)
        stack_->setVisible(false);
    if (readinessStrip_)
        readinessStrip_->setVisible(false);
    setMinimumWidth(kCollapsedWidth);
    setMaximumWidth(kCollapsedWidth);
    updateGeometry();
}

void CockpitInspector::applyExpandedForm()
{
    auto &theme = ThemeManager::instance();
    const int tight = theme.spacing(ThemeManager::Spacing::Tight);
    if (tabRow_)
    {
        tabRow_->setDirection(QBoxLayout::LeftToRight);
        tabRow_->setContentsMargins(tight, tight, tight, 0);
    }
    for (int i = 0; i < tabNames_.size(); ++i)
    {
        QAbstractButton *btn = tabGroup_ ? tabGroup_->button(i) : nullptr;
        if (!btn)
            continue;
        btn->setText(tabNames_.at(i));
        btn->setToolTip(QString());
        // setFixedSize wrote a min AND a max on both axes; a max that survived the return would keep
        // the tab bar in the strip's shape while everything else said it had expanded -- the same
        // trap SideRail::applyOrientation documents on the rail's own thickness.
        btn->setMinimumSize(0, 0);
        btn->setMaximumSize(QWIDGETSIZE_MAX, QWIDGETSIZE_MAX);
        btn->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    }
    if (tabTail_)
        tabTail_->setVisible(false);
    if (stack_)
        stack_->setVisible(true);
    if (readinessStrip_)
        readinessStrip_->setVisible(true);
    applyWidthBudget();
}
