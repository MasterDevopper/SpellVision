#include "CockpitInspector.h"

#include <QButtonGroup>
#include <QHBoxLayout>
#include <QLabel>
#include <QPushButton>
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

    // Tab bar — buttons swap the stack in place; no scroll.
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

        // Placeholder body — real controls relocate here in Phase 3.
        auto *page = new QWidget(stack_);
        auto *pageLayout = new QVBoxLayout(page);
        pageLayout->setContentsMargins(13, 12, 13, 12);
        auto *placeholder = new QLabel(name + QStringLiteral(" controls move here in Phase 3."), page);
        placeholder->setObjectName(QStringLiteral("InspectorPlaceholder"));
        placeholder->setWordWrap(true);
        placeholder->setAlignment(Qt::AlignTop | Qt::AlignLeft);
        pageLayout->addWidget(placeholder);
        pageLayout->addStretch(1);
        stack_->addWidget(page);

        ++index;
    }

    col->addWidget(tabBar, 0);
    col->addWidget(stack_, 1);

    connect(tabGroup_, &QButtonGroup::idClicked, stack_, &QStackedWidget::setCurrentIndex);

    // Readiness strip — pinned to the bottom of the inspector.
    auto *readiness = new QFrame(this);
    readiness->setObjectName(QStringLiteral("InspectorReadinessStrip"));
    auto *readinessLayout = new QHBoxLayout(readiness);
    readinessLayout->setContentsMargins(13, 8, 13, 8);
    auto *readinessText = new QLabel(QStringLiteral("Readiness — select a checkpoint to generate."), readiness);
    readinessText->setObjectName(QStringLiteral("InspectorReadinessText"));
    readinessLayout->addWidget(readinessText, 1);
    col->addWidget(readiness, 0);
}
