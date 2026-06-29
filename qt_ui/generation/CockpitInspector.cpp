#include "CockpitInspector.h"

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
    setAttribute(Qt::WA_StyledBackground, true); // belt-and-suspenders (QFrame already paints)
    setFixedWidth(340);                          // prototype --inspector:340px

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
    tabRow->setContentsMargins(8, 8, 8, 0);
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
        if (index == 0)
            btn->setChecked(true);
        tabGroup_->addButton(btn, index);
        tabRow->addWidget(btn, 1);

        // Scrollable body — relocated control sets (Model stack, Advanced rows) can be tall.
        auto *scroll = new QScrollArea(stack_);
        scroll->setObjectName(QStringLiteral("InspectorTabScroll"));
        scroll->setWidgetResizable(true);
        scroll->setFrameShape(QFrame::NoFrame);
        scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
        scroll->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);

        auto *content = new QWidget(scroll);
        content->setObjectName(QStringLiteral("InspectorTabContent"));
        auto *contentLayout = new QVBoxLayout(content);
        contentLayout->setContentsMargins(11, 12, 11, 12);
        contentLayout->setSpacing(8);
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
    readinessLayout->setContentsMargins(13, 8, 13, 8);
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
