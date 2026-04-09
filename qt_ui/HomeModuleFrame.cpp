#include "HomeModuleFrame.h"

#include "DashboardGlassPanel.h"

#include <QHBoxLayout>
#include <QLabel>
#include <QStyle>
#include <QToolButton>
#include <QVBoxLayout>

namespace
{
QToolButton *chromeButton(QWidget *parent, const QString &text, const QString &toolTip)
{
    auto *button = new QToolButton(parent);
    button->setObjectName(QStringLiteral("HomeModuleFrameButton"));
    button->setText(text);
    button->setToolTip(toolTip);
    button->setCursor(Qt::PointingHandCursor);
    button->setAutoRaise(false);
    return button;
}
}

HomeModuleFrame::HomeModuleFrame(const QString &moduleId,
                                 const QString &title,
                                 QWidget *content,
                                 QWidget *parent)
    : QWidget(parent)
    , moduleId_(moduleId)
    , content_(content)
{
    setObjectName(QStringLiteral("HomeModuleFrame"));

    auto *root = new QVBoxLayout(this);
    root->setContentsMargins(0, 0, 0, 0);
    root->setSpacing(0);

    surface_ = new DashboardGlassPanel(this);
    surface_->setObjectName(QStringLiteral("HomeModuleSurface"));
    surface_->setVariant(moduleId_ == QStringLiteral("hero_launcher")
                             ? DashboardGlassPanel::Variant::Hero
                         : moduleId_ == QStringLiteral("active_models")
                             ? DashboardGlassPanel::Variant::Utility
                             : DashboardGlassPanel::Variant::Standard);
    surface_->setCornerRadius(moduleId_ == QStringLiteral("hero_launcher") ? 24 : 20);
    surface_->setGlowStrength(moduleId_ == QStringLiteral("hero_launcher") ? 1.3 : 1.0);

    auto *surfaceLayout = new QVBoxLayout(surface_);
    surfaceLayout->setContentsMargins(10, 10, 10, 10);
    surfaceLayout->setSpacing(8);

    header_ = new QWidget(surface_);
    header_->setObjectName(QStringLiteral("HomeModuleHeader"));

    auto *headerLayout = new QHBoxLayout(header_);
    headerLayout->setContentsMargins(2, 0, 2, 0);
    headerLayout->setSpacing(6);

    titleLabel_ = new QLabel(title, header_);
    titleLabel_->setObjectName(QStringLiteral("HomeModuleTitle"));
    headerLayout->addWidget(titleLabel_);
    headerLayout->addStretch(1);

    auto *leftButton = chromeButton(header_, QStringLiteral("←"), QStringLiteral("Move left"));
    auto *rightButton = chromeButton(header_, QStringLiteral("→"), QStringLiteral("Move right"));
    auto *upButton = chromeButton(header_, QStringLiteral("↑"), QStringLiteral("Move up"));
    auto *downButton = chromeButton(header_, QStringLiteral("↓"), QStringLiteral("Move down"));
    auto *widePlusButton = chromeButton(header_, QStringLiteral("+W"), QStringLiteral("Make wider"));
    auto *wideMinusButton = chromeButton(header_, QStringLiteral("-W"), QStringLiteral("Make narrower"));
    auto *highPlusButton = chromeButton(header_, QStringLiteral("+H"), QStringLiteral("Make taller"));
    auto *highMinusButton = chromeButton(header_, QStringLiteral("-H"), QStringLiteral("Make shorter"));
    auto *hideButton = chromeButton(header_, QStringLiteral("Hide"), QStringLiteral("Hide module"));

    connect(leftButton, &QToolButton::clicked, this, [this]() { emit moveRequested(moduleId_, -1, 0); });
    connect(rightButton, &QToolButton::clicked, this, [this]() { emit moveRequested(moduleId_, 1, 0); });
    connect(upButton, &QToolButton::clicked, this, [this]() { emit moveRequested(moduleId_, 0, -1); });
    connect(downButton, &QToolButton::clicked, this, [this]() { emit moveRequested(moduleId_, 0, 1); });
    connect(widePlusButton, &QToolButton::clicked, this, [this]() { emit resizeRequested(moduleId_, 1, 0); });
    connect(wideMinusButton, &QToolButton::clicked, this, [this]() { emit resizeRequested(moduleId_, -1, 0); });
    connect(highPlusButton, &QToolButton::clicked, this, [this]() { emit resizeRequested(moduleId_, 0, 1); });
    connect(highMinusButton, &QToolButton::clicked, this, [this]() { emit resizeRequested(moduleId_, 0, -1); });
    connect(hideButton, &QToolButton::clicked, this, [this]() { emit visibilityRequested(moduleId_, false); });

    for (QToolButton *button : {leftButton,
                                rightButton,
                                upButton,
                                downButton,
                                widePlusButton,
                                wideMinusButton,
                                highPlusButton,
                                highMinusButton,
                                hideButton})
    {
        headerLayout->addWidget(button);
    }

    surfaceLayout->addWidget(header_);

    if (content_)
        surfaceLayout->addWidget(content_, 1);

    root->addWidget(surface_);

    setCustomizeMode(false);
}

QString HomeModuleFrame::moduleId() const
{
    return moduleId_;
}

void HomeModuleFrame::setCustomizeMode(bool enabled)
{
    if (header_)
        header_->setVisible(enabled);

    setProperty("customizeMode", enabled);

    if (QStyle *s = style())
    {
        s->unpolish(this);
        s->polish(this);
    }

    update();
}

bool HomeModuleFrame::isCustomizeMode() const
{
    return header_ && header_->isVisible();
}
