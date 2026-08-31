#include "CockpitInspector.h"
#include "../ThemeManager.h"

#include <QAbstractButton>
#include <QButtonGroup>
#include <QHBoxLayout>
#include <QLabel>
#include <QPushButton>
#include <QScrollArea>
#include <QStackedWidget>
#include <QVBoxLayout>
#include <QWidget>

CockpitInspector::CockpitInspector(QWidget *parent)
    : QFrame(parent)
{
    setObjectName(QStringLiteral("CockpitInspector"));
    setAttribute(Qt::WA_StyledBackground, true);

    // Adaptive default — callers refine via setWidthBudget() from the page layout pass.
    // Floor stays high enough for the Model Stack form; ceiling leaves canvas room at half-screen.
    setMinimumWidth(300);
    setMaximumWidth(480);
    setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Expanding);

    auto *col = new QVBoxLayout(this);
    col->setContentsMargins(0, 0, 0, 0);
    col->setSpacing(0);

    const QStringList tabs = {QStringLiteral("Model"),
                              QStringLiteral("Sampling"),
                              QStringLiteral("Output"),
                              QStringLiteral("Advanced")};

    auto *tabBar = new QWidget(this);
    tabBar->setObjectName(QStringLiteral("InspectorTabBar"));
    auto *tabRow = new QHBoxLayout(tabBar);
    tabRow->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight),
                               ThemeManager::instance().spacing(ThemeManager::Spacing::Tight),
                               ThemeManager::instance().spacing(ThemeManager::Spacing::Tight), 0);
    tabRow->setSpacing(2);

    tabGroup_ = new QButtonGroup(this);
    tabGroup_->setExclusive(true);

    stack_ = new QStackedWidget(this);

    int index = 0;
    for (const QString &name : tabs)
    {
        auto *btn = new QPushButton(name, tabBar);
        btn->setObjectName(QStringLiteral("InspectorTab"));
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

    col->addWidget(tabBar, 0);
    col->addWidget(stack_, 1);

    connect(tabGroup_, &QButtonGroup::idClicked, stack_, &QStackedWidget::setCurrentIndex);

    auto *readiness = new QFrame(this);
    readiness->setObjectName(QStringLiteral("InspectorReadinessStrip"));
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
    const int w = qBound(280, preferredWidth, 460);
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
