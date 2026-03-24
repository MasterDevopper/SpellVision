#include "HomePage.h"

#include "ThemeManager.h"

#include <QAbstractButton>
#include <QBoxLayout>
#include <QButtonGroup>
#include <QFrame>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QLabel>
#include <QPushButton>
#include <QResizeEvent>
#include <QSizePolicy>
#include <QScrollArea>
#include <QVBoxLayout>

namespace
{
QFrame *cardFrame(const QString &objectName = QStringLiteral("HomeCard"))
{
    auto *frame = new QFrame;
    frame->setObjectName(objectName);
    frame->setFrameShape(QFrame::NoFrame);
    return frame;
}

QLabel *titleLabel(const QString &text, const QString &objectName)
{
    auto *label = new QLabel(text);
    label->setObjectName(objectName);
    return label;
}

QLabel *bodyLabel(const QString &text, const QString &objectName)
{
    auto *label = new QLabel(text);
    label->setObjectName(objectName);
    label->setWordWrap(true);
    return label;
}

QPushButton *modeChip(const QString &text, QWidget *parent = nullptr)
{
    auto *button = new QPushButton(text, parent);
    button->setObjectName(QStringLiteral("HomeModeButton"));
    button->setCheckable(true);
    button->setCursor(Qt::PointingHandCursor);
    return button;
}

QWidget *statRow(const QString &labelText, QLabel **valueTarget, QWidget *parent)
{
    auto *row = new QWidget(parent);
    auto *layout = new QHBoxLayout(row);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(8);

    auto *label = titleLabel(labelText, QStringLiteral("HomeStatLabel"));
    auto *value = titleLabel(QStringLiteral("none"), QStringLiteral("HomeStatValue"));
    value->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
    value->setSizePolicy(QSizePolicy::MinimumExpanding, QSizePolicy::Preferred);

    layout->addWidget(label);
    layout->addStretch(1);
    layout->addWidget(value);

    if (valueTarget)
        *valueTarget = value;
    return row;
}

void clearLayout(QLayout *layout)
{
    if (!layout)
        return;

    while (QLayoutItem *item = layout->takeAt(0))
        delete item;
}
}

HomePage::HomePage(QWidget *parent)
    : QWidget(parent)
{
    setObjectName(QStringLiteral("HomePage"));

    auto *outer = new QVBoxLayout(this);
    outer->setContentsMargins(0, 0, 0, 0);
    outer->setSpacing(0);

    scrollArea_ = new QScrollArea(this);
    scrollArea_->setWidgetResizable(true);
    scrollArea_->setFrameShape(QFrame::NoFrame);
    scrollArea_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    outer->addWidget(scrollArea_);

    contentWidget_ = new QWidget(scrollArea_);
    auto *root = new QVBoxLayout(contentWidget_);
    root->setContentsMargins(10, 10, 10, 14);
    root->setSpacing(10);
    root->setAlignment(Qt::AlignTop);

    auto *heroCard = cardFrame(QStringLiteral("HomeHeroCard"));
    heroSplitLayout_ = new QBoxLayout(QBoxLayout::LeftToRight, heroCard);
    heroSplitLayout_->setContentsMargins(14, 14, 14, 14);
    heroSplitLayout_->setSpacing(12);
    heroCard->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Maximum);

    auto *heroMain = new QWidget(heroCard);
    auto *heroMainLayout = new QVBoxLayout(heroMain);
    heroMainLayout->setContentsMargins(0, 0, 0, 0);
    heroMainLayout->setSpacing(8);

    heroEyebrowLabel_ = titleLabel(QStringLiteral("Start Creating"), QStringLiteral("HomeHeroEyebrow"));
    heroTitleLabel_ = titleLabel(QString(), QStringLiteral("HomeHeroTitle"));
    heroSubtitleLabel_ = bodyLabel(QString(), QStringLiteral("HomeHeroBody"));

    modeButtonGroup_ = new QButtonGroup(this);
    modeButtonGroup_->setExclusive(true);

    auto *modeSegment = cardFrame(QStringLiteral("HomeModeSegment"));
    auto *modeRow = new QHBoxLayout(modeSegment);
    modeRow->setContentsMargins(4, 4, 4, 4);
    modeRow->setSpacing(4);

    const struct ModeSpec
    {
        QString id;
        QString label;
    } modes[] = {
        {QStringLiteral("t2i"), QStringLiteral("Text to Image")},
        {QStringLiteral("i2i"), QStringLiteral("Image to Image")},
        {QStringLiteral("t2v"), QStringLiteral("Text to Video")},
        {QStringLiteral("i2v"), QStringLiteral("Image to Video")}
    };

    for (const ModeSpec &mode : modes)
    {
        auto *button = modeChip(mode.label, heroCard);
        button->setChecked(mode.id == currentMode_);
        modeButtonGroup_->addButton(button);
        connect(button, &QPushButton::clicked, this, [this, mode]() { selectMode(mode.id); });
        modeRow->addWidget(button, 1);
    }

    dependencyBannerLabel_ = bodyLabel(QString(), QStringLiteral("HomeDependencyBanner"));
    dependencyBannerLabel_->setMinimumHeight(30);
    dependencyBannerLabel_->setMaximumHeight(34);

    auto *heroBandsHost = new QWidget(heroCard);
    heroContentLayout_ = new QBoxLayout(QBoxLayout::LeftToRight, heroBandsHost);
    heroContentLayout_->setContentsMargins(0, 0, 0, 0);
    heroContentLayout_->setSpacing(10);

    heroInputLabel_ = bodyLabel(QString(), QStringLiteral("HomeHeroInput"));
    heroInputLabel_->setMinimumHeight(76);
    heroInputLabel_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);

    stackSummaryLabel_ = bodyLabel(QString(), QStringLiteral("HomeStackSummary"));
    stackSummaryLabel_->setMinimumHeight(76);
    stackSummaryLabel_->setMinimumWidth(252);
    stackSummaryLabel_->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Preferred);

    heroContentLayout_->addWidget(heroInputLabel_, 3);
    heroContentLayout_->addWidget(stackSummaryLabel_, 2);

    heroHintLabel_ = bodyLabel(QStringLiteral("Idle · 0%%. Home stays launcher-first."),
                               QStringLiteral("HomeHeroHint"));
    heroHintLabel_->hide();
    heroInputLabel_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Maximum);
    stackSummaryLabel_->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Maximum);

    auto *actionRow = new QHBoxLayout;
    actionRow->setContentsMargins(0, 0, 0, 0);
    actionRow->setSpacing(8);

    primaryActionButton_ = new QPushButton(heroCard);
    primaryActionButton_->setObjectName(QStringLiteral("PrimaryActionButton"));
    auto *workflowButton = new QPushButton(QStringLiteral("Open Workflow Library"), heroCard);
    workflowButton->setObjectName(QStringLiteral("SecondaryActionButton"));
    auto *inspirationButton = new QPushButton(QStringLiteral("Browse Inspiration"), heroCard);
    inspirationButton->setObjectName(QStringLiteral("SecondaryActionButton"));

    connect(primaryActionButton_, &QPushButton::clicked, this, [this]() { emit modeRequested(currentMode_); });
    connect(workflowButton, &QPushButton::clicked, this, [this]() { emit managerRequested(QStringLiteral("workflows")); });
    connect(inspirationButton, &QPushButton::clicked, this, [this]() { emit managerRequested(QStringLiteral("inspiration")); });

    actionRow->addWidget(primaryActionButton_);
    actionRow->addWidget(workflowButton);
    actionRow->addWidget(inspirationButton);
    actionRow->addStretch(1);

    heroMainLayout->addWidget(heroEyebrowLabel_);
    heroMainLayout->addWidget(heroTitleLabel_);
    heroMainLayout->addWidget(heroSubtitleLabel_);
    heroMainLayout->addSpacing(2);
    heroMainLayout->addWidget(modeSegment);
    heroMainLayout->addWidget(dependencyBannerLabel_);
    heroMainLayout->addWidget(heroBandsHost);
    heroMainLayout->addLayout(actionRow);
    heroMainLayout->addWidget(heroHintLabel_);

    workflowLauncherCard_ = cardFrame(QStringLiteral("HomeCard"));
    auto *launcherLayout = new QVBoxLayout(workflowLauncherCard_);
    launcherLayout->setContentsMargins(10, 10, 10, 10);
    launcherLayout->setSpacing(8);
    launcherLayout->addWidget(titleLabel(QStringLiteral("Workflow Launcher"), QStringLiteral("HomeSectionTitle")));
    launcherLayout->addWidget(bodyLabel(QStringLiteral("Recent and imported starters preview into Home."),
                                        QStringLiteral("HomeSectionBody")));

    auto *launcherGridHost = new QWidget(workflowLauncherCard_);
    launcherGrid_ = new QGridLayout(launcherGridHost);
    launcherGrid_->setContentsMargins(0, 0, 0, 0);
    launcherGrid_->setHorizontalSpacing(6);
    launcherGrid_->setVerticalSpacing(6);

    launcherRecentCard_ = createWorkflowPreviewCard(
        QStringLiteral("Stylized Portraits"),
        QStringLiteral("Portrait starter with polished composition and lighting cues."),
        QStringLiteral("t2i"),
        QStringLiteral("Recent Workflow"),
        QStringLiteral("Preview in Hero"));
    launcherImportedCard_ = createWorkflowPreviewCard(
        QStringLiteral("Fantasy Art Generator"),
        QStringLiteral("Broad fantasy preset that primes the hero without leaving Home."),
        QStringLiteral("t2i"),
        QStringLiteral("Imported Workflow"),
        QStringLiteral("Preview in Hero"));

    launcherGridHost->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Maximum);
    workflowLauncherCard_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Maximum);
    launcherLayout->addWidget(launcherGridHost);

    auto *viewAllWorkflows = new QPushButton(QStringLiteral("View All Workflows"), workflowLauncherCard_);
    connect(viewAllWorkflows, &QPushButton::clicked, this, [this]() { emit managerRequested(QStringLiteral("workflows")); });
    launcherLayout->addWidget(viewAllWorkflows, 0, Qt::AlignLeft);

    heroSplitLayout_->addWidget(heroMain, 7);
    heroSplitLayout_->addWidget(workflowLauncherCard_, 4);
    root->addWidget(heroCard);

    quickGenerateCard_ = cardFrame(QStringLiteral("HomeCard"));
    auto *quickLayout = new QVBoxLayout(quickGenerateCard_);
    quickLayout->setContentsMargins(10, 10, 10, 10);
    quickLayout->setSpacing(8);
    quickLayout->addWidget(titleLabel(QStringLiteral("Quick Generate"), QStringLiteral("HomeSectionTitle")));
    quickLayout->addWidget(bodyLabel(QStringLiteral("Jump straight into larger, focused creation shells."),
                                     QStringLiteral("HomeSectionBody")));

    auto *quickGridHost = new QWidget(quickGenerateCard_);
    quickGenerateGrid_ = new QGridLayout(quickGridHost);
    quickGenerateGrid_->setContentsMargins(0, 0, 0, 0);
    quickGenerateGrid_->setHorizontalSpacing(6);
    quickGenerateGrid_->setVerticalSpacing(6);

    quickT2iCard_ = createQuickModeCard(
        QStringLiteral("Text to Image"),
        QStringLiteral("Prompt-first generation in the canvas workspace."),
        QStringLiteral("t2i"));
    quickI2iCard_ = createQuickModeCard(
        QStringLiteral("Image to Image"),
        QStringLiteral("Bring in a source image for focused restyle."),
        QStringLiteral("i2i"));
    quickT2vCard_ = createQuickModeCard(
        QStringLiteral("Text to Video"),
        QStringLiteral("Open the motion shell with timing controls."),
        QStringLiteral("t2v"));
    quickI2vCard_ = createQuickModeCard(
        QStringLiteral("Image to Video"),
        QStringLiteral("Start from a still image and expand into motion."),
        QStringLiteral("i2v"));

    quickGridHost->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Maximum);
    quickGenerateCard_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Maximum);
    quickLayout->addWidget(quickGridHost);
    root->addWidget(quickGenerateCard_);

    auto *discoveryWrap = new QWidget(contentWidget_);
    discoveryLayout_ = new QBoxLayout(QBoxLayout::LeftToRight, discoveryWrap);
    discoveryLayout_->setContentsMargins(0, 0, 0, 0);
    discoveryLayout_->setSpacing(10);

    recentOutputsCard_ = cardFrame(QStringLiteral("HomeCard"));
    auto *outputsLayout = new QVBoxLayout(recentOutputsCard_);
    outputsLayout->setContentsMargins(10, 10, 10, 10);
    outputsLayout->setSpacing(8);
    outputsLayout->addWidget(titleLabel(QStringLiteral("Recent Outputs"), QStringLiteral("HomeSectionTitle")));
    outputsLayout->addWidget(bodyLabel(QStringLiteral("Open, requeue, or route finished work into another mode with larger preview plates."),
                                       QStringLiteral("HomeSectionBody")));

    auto *outputsGridHost = new QWidget(recentOutputsCard_);
    recentOutputsGrid_ = new QGridLayout(outputsGridHost);
    recentOutputsGrid_->setContentsMargins(0, 0, 0, 0);
    recentOutputsGrid_->setHorizontalSpacing(6);
    recentOutputsGrid_->setVerticalSpacing(6);

    recentOutputPortrait_ = createRecentOutputCard(
        QStringLiteral("Character Portrait"),
        QStringLiteral("Send this still back into I2I for refinement."),
        QStringLiteral("i2i"));
    recentOutputLandscape_ = createRecentOutputCard(
        QStringLiteral("Open Landscape"),
        QStringLiteral("Requeue the world concept or route it into T2V."),
        QStringLiteral("t2v"));
    recentOutputVideo_ = createRecentOutputCard(
        QStringLiteral("Motion Test"),
        QStringLiteral("Inspect the sequence and reopen motion."),
        QStringLiteral("i2v"));

    outputsGridHost->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Maximum);
    outputsLayout->addWidget(outputsGridHost);
    recentOutputsCard_->setMinimumWidth(0);
    recentOutputsCard_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Maximum);
    discoveryLayout_->addWidget(recentOutputsCard_, 3);

    favoritesCard_ = cardFrame(QStringLiteral("HomeCard"));
    auto *favoritesLayout = new QVBoxLayout(favoritesCard_);
    favoritesLayout->setContentsMargins(10, 10, 10, 10);
    favoritesLayout->setSpacing(8);
    favoritesLayout->addWidget(titleLabel(QStringLiteral("Favorites Rail"), QStringLiteral("HomeSectionTitle")));
    favoritesLayout->addWidget(bodyLabel(QStringLiteral("Pinned starters return here as a curated rail with real card presence."),
                                         QStringLiteral("HomeSectionBody")));

    auto *favoritesGridHost = new QWidget(favoritesCard_);
    favoritesGrid_ = new QGridLayout(favoritesGridHost);
    favoritesGrid_->setContentsMargins(0, 0, 0, 0);
    favoritesGrid_->setHorizontalSpacing(6);
    favoritesGrid_->setVerticalSpacing(6);

    favoritePortraitCard_ = createWorkflowPreviewCard(
        QStringLiteral("Portrait Armor"),
        QStringLiteral("Character concept starter with cinematic edge lighting."),
        QStringLiteral("t2i"),
        QStringLiteral("Favorite"),
        QStringLiteral("Preview in Hero"));
    favoriteLandscapeCard_ = createWorkflowPreviewCard(
        QStringLiteral("Open Landscape"),
        QStringLiteral("Environment mood starter for wide world concepts."),
        QStringLiteral("t2v"),
        QStringLiteral("Favorite"),
        QStringLiteral("Preview in Hero"));
    favoriteCityCard_ = createWorkflowPreviewCard(
        QStringLiteral("Sci-Fi City"),
        QStringLiteral("Urban neon starting point for future-world sequences."),
        QStringLiteral("t2v"),
        QStringLiteral("Favorite"),
        QStringLiteral("Preview in Hero"));

    favoritesGridHost->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Maximum);
    favoritesLayout->addWidget(favoritesGridHost);

    auto *browseFavorites = new QPushButton(QStringLiteral("Browse Inspiration"), favoritesCard_);
    browseFavorites->setObjectName(QStringLiteral("SectionLinkButton"));
    connect(browseFavorites, &QPushButton::clicked, this, [this]() { emit managerRequested(QStringLiteral("inspiration")); });
    favoritesLayout->addWidget(browseFavorites, 0, Qt::AlignLeft);
    favoritesCard_->setMinimumWidth(0);
    favoritesCard_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Maximum);
    discoveryLayout_->addWidget(favoritesCard_, 3);

    activeModelsCard_ = cardFrame(QStringLiteral("HomeCard"));
    auto *activeLayout = new QVBoxLayout(activeModelsCard_);
    activeLayout->setContentsMargins(10, 10, 10, 10);
    activeLayout->setSpacing(6);
    activeLayout->addWidget(titleLabel(QStringLiteral("Active Models + Shortcuts"), QStringLiteral("HomeSectionTitle")));
    activeLayout->addWidget(bodyLabel(QStringLiteral("Keep the current stack visible while the main discovery surfaces stay visually dominant."),
                                      QStringLiteral("HomeSectionBody")));
    activeLayout->addWidget(statRow(QStringLiteral("Checkpoint"), &activeCheckpointValue_, activeModelsCard_));
    activeLayout->addWidget(statRow(QStringLiteral("LoRA"), &activeLoraValue_, activeModelsCard_));
    activeLayout->addWidget(statRow(QStringLiteral("Queue"), &activeQueueValue_, activeModelsCard_));
    activeLayout->addWidget(statRow(QStringLiteral("Runtime"), &activeRuntimeValue_, activeModelsCard_));

    auto *shortcutRow1 = new QHBoxLayout;
    shortcutRow1->setContentsMargins(0, 0, 0, 0);
    shortcutRow1->setSpacing(8);
    auto *modelsButton = new QPushButton(QStringLiteral("Models"), activeModelsCard_);
    modelsButton->setObjectName(QStringLiteral("UtilityActionButton"));
    auto *downloadsButton = new QPushButton(QStringLiteral("Downloads"), activeModelsCard_);
    downloadsButton->setObjectName(QStringLiteral("UtilityActionButton"));
    connect(modelsButton, &QPushButton::clicked, this, [this]() { emit managerRequested(QStringLiteral("models")); });
    connect(downloadsButton, &QPushButton::clicked, this, [this]() { emit managerRequested(QStringLiteral("downloads")); });
    shortcutRow1->addWidget(modelsButton);
    shortcutRow1->addWidget(downloadsButton);

    auto *shortcutRow2 = new QHBoxLayout;
    shortcutRow2->setContentsMargins(0, 0, 0, 0);
    shortcutRow2->setSpacing(8);
    auto *historyButton = new QPushButton(QStringLiteral("History"), activeModelsCard_);
    historyButton->setObjectName(QStringLiteral("UtilityActionButton"));
    auto *settingsButton = new QPushButton(QStringLiteral("Settings"), activeModelsCard_);
    settingsButton->setObjectName(QStringLiteral("UtilityActionButton"));
    connect(historyButton, &QPushButton::clicked, this, [this]() { emit managerRequested(QStringLiteral("history")); });
    connect(settingsButton, &QPushButton::clicked, this, [this]() { emit managerRequested(QStringLiteral("settings")); });
    shortcutRow2->addWidget(historyButton);
    shortcutRow2->addWidget(settingsButton);

    activeLayout->addLayout(shortcutRow1);
    activeLayout->addLayout(shortcutRow2);
    activeModelsCard_->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Maximum);
    activeModelsCard_->setMaximumWidth(308);
    activeModelsCard_->setMinimumWidth(238);
    discoveryLayout_->addWidget(activeModelsCard_, 1);

    root->addWidget(discoveryWrap);

    scrollArea_->setWidget(contentWidget_);

    updateHero();
    applyTheme();
    updateResponsiveLayout();
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, &HomePage::applyTheme);
}

void HomePage::setRuntimeSummary(const QString &runtimeName,
                                 int runningCount,
                                 int pendingCount,
                                 int errorCount,
                                 const QString &vramText,
                                 const QString &modelText,
                                 const QString &loraText,
                                 const QString &progressText,
                                 int progressPercent)
{
    Q_UNUSED(vramText);

    if (activeCheckpointValue_)
        activeCheckpointValue_->setText(modelText.trimmed().isEmpty() ? QStringLiteral("none") : modelText);
    if (activeLoraValue_)
        activeLoraValue_->setText(loraText.trimmed().isEmpty() ? QStringLiteral("none") : loraText);
    if (activeQueueValue_)
        activeQueueValue_->setText(QStringLiteral("%1 run • %2 pending • %3 errors").arg(runningCount).arg(pendingCount).arg(errorCount));
    if (activeRuntimeValue_)
        activeRuntimeValue_->setText(runtimeName.trimmed().isEmpty() ? QStringLiteral("Managed runtime") : runtimeName);

    if (heroHintLabel_)
    {
        const QString progressSummary = progressText.trimmed().isEmpty() ? QStringLiteral("Idle") : progressText;
        heroHintLabel_->setText(
            QStringLiteral("%1 · %2%%. Home stays launcher-first.")
                .arg(progressSummary)
                .arg(progressPercent));
    }
}

QWidget *HomePage::createWorkflowPreviewCard(const QString &title,
                                             const QString &subtitle,
                                             const QString &modeId,
                                             const QString &sourceLabel,
                                             const QString &buttonText)
{
    auto *card = cardFrame(QStringLiteral("HomePreviewCard"));
    auto *layout = new QVBoxLayout(card);
    layout->setContentsMargins(10, 10, 10, 10);
    layout->setSpacing(4);
    card->setMinimumHeight(104);
    card->setMaximumHeight(138);

    auto *source = titleLabel(sourceLabel, QStringLiteral("HomePreviewEyebrow"));
    auto *titleWidget = titleLabel(title, QStringLiteral("HomePreviewTitle"));
    auto *bodyWidget = bodyLabel(subtitle, QStringLiteral("HomePreviewBody"));
    auto *button = new QPushButton(buttonText, card);
    button->setObjectName(QStringLiteral("SurfaceActionButton"));

    connect(button, &QPushButton::clicked, this, [this, titleWidget, bodyWidget, modeId, source]() {
        previewStarter(titleWidget->text(), bodyWidget->text(), modeId, source->text());
    });

    layout->addWidget(source);
    layout->addWidget(titleWidget);
    layout->addWidget(bodyWidget);
    layout->addWidget(button, 0, Qt::AlignLeft);
    return card;
}

QWidget *HomePage::createQuickModeCard(const QString &title,
                                       const QString &subtitle,
                                       const QString &modeId)
{
    auto *card = cardFrame(QStringLiteral("HomeQuickCard"));
    auto *layout = new QVBoxLayout(card);
    layout->setContentsMargins(10, 10, 10, 10);
    layout->setSpacing(4);
    card->setMinimumHeight(102);
    card->setMaximumHeight(126);

    layout->addWidget(titleLabel(title, QStringLiteral("HomePreviewTitle")));
    layout->addWidget(bodyLabel(subtitle, QStringLiteral("HomePreviewBody")));

    auto *buttons = new QHBoxLayout;
    buttons->setContentsMargins(0, 0, 0, 0);
    buttons->setSpacing(8);

    auto *previewButton = new QPushButton(QStringLiteral("Preview"), card);
    previewButton->setObjectName(QStringLiteral("SurfaceSecondaryButton"));
    auto *launchButton = new QPushButton(QStringLiteral("Open"), card);
    launchButton->setObjectName(QStringLiteral("SurfacePrimaryButton"));

    connect(previewButton, &QPushButton::clicked, this, [this, title, subtitle, modeId]() {
        previewStarter(title, subtitle, modeId, QStringLiteral("Quick Generate"));
    });
    connect(launchButton, &QPushButton::clicked, this, [this, modeId]() {
        emit modeRequested(modeId);
    });

    buttons->addWidget(previewButton);
    buttons->addWidget(launchButton);
    buttons->addStretch(1);

    layout->addLayout(buttons);
    return card;
}

QWidget *HomePage::createRecentOutputCard(const QString &title,
                                          const QString &subtitle,
                                          const QString &modeId)
{
    auto *card = cardFrame(QStringLiteral("HomePreviewCard"));
    auto *layout = new QVBoxLayout(card);
    layout->setContentsMargins(10, 10, 10, 10);
    layout->setSpacing(3);
    card->setMinimumHeight(132);
    card->setMaximumHeight(164);

    auto *thumb = cardFrame(QStringLiteral("HomeThumbnailPlate"));
    thumb->setMinimumHeight(42);
    thumb->setMaximumHeight(48);

    auto *titleText = titleLabel(title, QStringLiteral("HomePreviewTitle"));
    auto *bodyText = bodyLabel(subtitle, QStringLiteral("HomePreviewBody"));

    auto *actionRow = new QHBoxLayout;
    actionRow->setContentsMargins(0, 0, 0, 0);
    actionRow->setSpacing(8);

    auto *openButton = new QPushButton(QStringLiteral("Open"), card);
    openButton->setObjectName(QStringLiteral("SurfaceSecondaryButton"));
    auto *routeButton = new QPushButton(QStringLiteral("Send to Mode"), card);
    routeButton->setObjectName(QStringLiteral("SurfaceActionButton"));

    connect(openButton, &QPushButton::clicked, this, [this]() { emit managerRequested(QStringLiteral("history")); });
    connect(routeButton, &QPushButton::clicked, this, [this, modeId]() { emit modeRequested(modeId); });

    actionRow->addWidget(openButton);
    actionRow->addWidget(routeButton);
    actionRow->addStretch(1);

    layout->addWidget(thumb);
    layout->addWidget(titleText);
    layout->addWidget(bodyText);
    layout->addLayout(actionRow);
    return card;
}

void HomePage::selectMode(const QString &modeId)
{
    if (modeId.trimmed().isEmpty())
        return;

    currentMode_ = modeId;
    updateHero();
}

void HomePage::previewStarter(const QString &title,
                              const QString &subtitle,
                              const QString &modeId,
                              const QString &sourceLabel)
{
    starterTitle_ = title;
    starterSubtitle_ = subtitle;
    starterSource_ = sourceLabel;
    selectMode(modeId);
}

void HomePage::updateHero()
{
    if (!heroTitleLabel_ || !heroSubtitleLabel_ || !dependencyBannerLabel_ || !heroInputLabel_ || !stackSummaryLabel_ || !primaryActionButton_)
        return;

    if (modeButtonGroup_)
    {
        const auto buttons = modeButtonGroup_->buttons();
        for (QAbstractButton *button : buttons)
        {
            if (!button)
                continue;

            const QString text = button->text().toLower();
            const bool checked =
                (currentMode_ == QStringLiteral("t2i") && text == QStringLiteral("text to image")) ||
                (currentMode_ == QStringLiteral("i2i") && text == QStringLiteral("image to image")) ||
                (currentMode_ == QStringLiteral("t2v") && text == QStringLiteral("text to video")) ||
                (currentMode_ == QStringLiteral("i2v") && text == QStringLiteral("image to video"));
            button->setChecked(checked);
        }
    }

    const QString sourcePrefix = starterSource_.trimmed().isEmpty()
        ? QStringLiteral("Start with a prompt, image, or workflow preview.")
        : QStringLiteral("%1 selected:").arg(starterSource_);

    if (currentMode_ == QStringLiteral("t2i"))
    {
        heroTitleLabel_->setText(QStringLiteral("Text to Image"));
        heroSubtitleLabel_->setText(QStringLiteral("Lead with the prompt, keep the stack visible, and launch into the focused canvas workspace."));
        dependencyBannerLabel_->setText(QStringLiteral("Dependency check: core image-generation requirements look ready."));
        primaryActionButton_->setText(QStringLiteral("Open Text to Image"));
        stackSummaryLabel_->setText(QStringLiteral("Default stack summary\nCheckpoint: none selected\nLoRA: none\nWorkflow profile: Default Canvas"));
        if (starterTitle_.trimmed().isEmpty())
            heroInputLabel_->setText(QStringLiteral("Prompt-first launch\nPaste a concept prompt, drag references, or start from a saved workflow."));
        else
            heroInputLabel_->setText(QStringLiteral("%1\n%2\n%3").arg(sourcePrefix, starterTitle_, starterSubtitle_));
    }
    else if (currentMode_ == QStringLiteral("i2i"))
    {
        heroTitleLabel_->setText(QStringLiteral("Image to Image"));
        heroSubtitleLabel_->setText(QStringLiteral("Bring a source image into the guided workspace for restyle and refinement."));
        dependencyBannerLabel_->setText(QStringLiteral("Dependency check: add a source image to prime the restyle flow."));
        primaryActionButton_->setText(QStringLiteral("Open Image to Image"));
        stackSummaryLabel_->setText(QStringLiteral("Default stack summary\nCheckpoint: none selected\nLoRA: optional\nWorkflow profile: Restyle"));
        if (starterTitle_.trimmed().isEmpty())
            heroInputLabel_->setText(QStringLiteral("Image-guided launch\nDrop a source image or preview a starter before opening I2I."));
        else
            heroInputLabel_->setText(QStringLiteral("%1\n%2\n%3").arg(sourcePrefix, starterTitle_, starterSubtitle_));
    }
    else if (currentMode_ == QStringLiteral("t2v"))
    {
        heroTitleLabel_->setText(QStringLiteral("Text to Video"));
        heroSubtitleLabel_->setText(QStringLiteral("Open the motion-first shell with room for prompt and timing controls."));
        dependencyBannerLabel_->setText(QStringLiteral("Dependency check: the motion shell is ready for prompt-first planning."));
        primaryActionButton_->setText(QStringLiteral("Open Text to Video"));
        stackSummaryLabel_->setText(QStringLiteral("Default stack summary\nModel: none selected\nFrames / FPS: guided defaults\nWorkflow profile: Motion Starter"));
        if (starterTitle_.trimmed().isEmpty())
            heroInputLabel_->setText(QStringLiteral("Sequence starter\nDefine motion intent and duration before opening T2V."));
        else
            heroInputLabel_->setText(QStringLiteral("%1\n%2\n%3").arg(sourcePrefix, starterTitle_, starterSubtitle_));
    }
    else
    {
        heroTitleLabel_->setText(QStringLiteral("Image to Video"));
        heroSubtitleLabel_->setText(QStringLiteral("Start from a still image or keyframe, then move into the motion workspace."));
        dependencyBannerLabel_->setText(QStringLiteral("Dependency check: add a keyframe image to unlock the motion path."));
        primaryActionButton_->setText(QStringLiteral("Open Image to Video"));
        stackSummaryLabel_->setText(QStringLiteral("Default stack summary\nModel: none selected\nMotion guidance: waiting for keyframe\nWorkflow profile: Keyframe Motion"));
        if (starterTitle_.trimmed().isEmpty())
            heroInputLabel_->setText(QStringLiteral("Keyframe starter\nDrop a still image or preview a motion starter before opening I2V."));
        else
            heroInputLabel_->setText(QStringLiteral("%1\n%2\n%3").arg(sourcePrefix, starterTitle_, starterSubtitle_));
    }
}

void HomePage::resizeEvent(QResizeEvent *event)
{
    QWidget::resizeEvent(event);
    updateResponsiveLayout();
}

void HomePage::updateResponsiveLayout()
{
    if (!heroSplitLayout_ || !heroContentLayout_ || !launcherGrid_ || !quickGenerateGrid_ || !recentOutputsGrid_ || !favoritesGrid_ || !discoveryLayout_)
        return;

    const int width = this->width();

    heroSplitLayout_->setDirection(width < 1300 ? QBoxLayout::TopToBottom : QBoxLayout::LeftToRight);
    heroContentLayout_->setDirection(width < 1180 ? QBoxLayout::TopToBottom : QBoxLayout::LeftToRight);
    const bool stackedDiscovery = width < 1380;
    discoveryLayout_->setDirection(stackedDiscovery ? QBoxLayout::TopToBottom : QBoxLayout::LeftToRight);
    if (stackedDiscovery)
    {
        activeModelsCard_->setMaximumWidth(QWIDGETSIZE_MAX);
        activeModelsCard_->setMinimumWidth(0);
        activeModelsCard_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Maximum);
    }
    else
    {
        activeModelsCard_->setMaximumWidth(286);
        activeModelsCard_->setMinimumWidth(228);
        activeModelsCard_->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Maximum);
    }

    if (width >= 1500)
    {
        heroInputLabel_->setMinimumHeight(88);
        stackSummaryLabel_->setMinimumHeight(88);
        workflowLauncherCard_->setMaximumHeight(256);
        quickGenerateCard_->setMaximumHeight(204);
    }
    else if (width >= 1180)
    {
        heroInputLabel_->setMinimumHeight(82);
        stackSummaryLabel_->setMinimumHeight(82);
        workflowLauncherCard_->setMaximumHeight(286);
        quickGenerateCard_->setMaximumHeight(236);
    }
    else
    {
        heroInputLabel_->setMinimumHeight(76);
        stackSummaryLabel_->setMinimumHeight(76);
        workflowLauncherCard_->setMaximumHeight(QWIDGETSIZE_MAX);
        quickGenerateCard_->setMaximumHeight(QWIDGETSIZE_MAX);
    }

    clearLayout(launcherGrid_);
    if (width < 1120)
    {
        launcherGrid_->addWidget(launcherRecentCard_, 0, 0);
        launcherGrid_->addWidget(launcherImportedCard_, 1, 0);
    }
    else
    {
        launcherGrid_->addWidget(launcherRecentCard_, 0, 0);
        launcherGrid_->addWidget(launcherImportedCard_, 0, 1);
    }

    clearLayout(quickGenerateGrid_);
    if (width < 920)
    {
        quickGenerateGrid_->addWidget(quickT2iCard_, 0, 0);
        quickGenerateGrid_->addWidget(quickI2iCard_, 1, 0);
        quickGenerateGrid_->addWidget(quickT2vCard_, 2, 0);
        quickGenerateGrid_->addWidget(quickI2vCard_, 3, 0);
    }
    else if (width < 1320)
    {
        quickGenerateGrid_->addWidget(quickT2iCard_, 0, 0);
        quickGenerateGrid_->addWidget(quickI2iCard_, 0, 1);
        quickGenerateGrid_->addWidget(quickT2vCard_, 1, 0);
        quickGenerateGrid_->addWidget(quickI2vCard_, 1, 1);
    }
    else
    {
        quickGenerateGrid_->addWidget(quickT2iCard_, 0, 0);
        quickGenerateGrid_->addWidget(quickI2iCard_, 0, 1);
        quickGenerateGrid_->addWidget(quickT2vCard_, 0, 2);
        quickGenerateGrid_->addWidget(quickI2vCard_, 0, 3);
    }

    clearLayout(recentOutputsGrid_);
    if (width < 1040)
    {
        recentOutputsGrid_->addWidget(recentOutputPortrait_, 0, 0);
        recentOutputsGrid_->addWidget(recentOutputLandscape_, 1, 0);
        recentOutputsGrid_->addWidget(recentOutputVideo_, 2, 0);
    }
    else if (width < 1360)
    {
        recentOutputsGrid_->addWidget(recentOutputPortrait_, 0, 0);
        recentOutputsGrid_->addWidget(recentOutputLandscape_, 0, 1);
        recentOutputsGrid_->addWidget(recentOutputVideo_, 1, 0, 1, 2);
    }
    else
    {
        recentOutputsGrid_->addWidget(recentOutputPortrait_, 0, 0);
        recentOutputsGrid_->addWidget(recentOutputLandscape_, 0, 1);
        recentOutputsGrid_->addWidget(recentOutputVideo_, 0, 2);
    }

    clearLayout(favoritesGrid_);
    if (width < 1100)
    {
        favoritesGrid_->addWidget(favoritePortraitCard_, 0, 0);
        favoritesGrid_->addWidget(favoriteLandscapeCard_, 1, 0);
        favoritesGrid_->addWidget(favoriteCityCard_, 2, 0);
    }
    else if (width < 1360)
    {
        favoritesGrid_->addWidget(favoritePortraitCard_, 0, 0);
        favoritesGrid_->addWidget(favoriteLandscapeCard_, 0, 1);
        favoritesGrid_->addWidget(favoriteCityCard_, 1, 0, 1, 2);
    }
    else
    {
        favoritesGrid_->addWidget(favoritePortraitCard_, 0, 0);
        favoritesGrid_->addWidget(favoriteLandscapeCard_, 0, 1);
        favoritesGrid_->addWidget(favoriteCityCard_, 0, 2);
    }
}

void HomePage::applyTheme()
{
    const auto &theme = ThemeManager::instance();
    setStyleSheet(QStringLiteral(
        "#HomePage { background: transparent; }"
        "QFrame#HomeHeroCard, QFrame#HomeCard, QFrame#HomePreviewCard, QFrame#HomeQuickCard {"
        " background: rgba(18, 25, 39, 0.92);"
        " border: 1px solid rgba(120, 138, 172, 0.20);"
        " border-radius: 18px;"
        "}"
        "QFrame#HomeHeroCard {"
        " border-color: rgba(132, 148, 184, 0.24);"
        "}"
        "QFrame#HomeModeSegment {"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 rgba(255,255,255,0.028), stop:1 rgba(255,255,255,0.018));"
        " border: 1px solid rgba(124, 140, 176, 0.18);"
        " border-radius: 14px;"
        "}"
        "QFrame#HomeQuickCard {"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 rgba(22,32,49,0.94), stop:1 rgba(18,25,39,0.94));"
        "}"
        "QFrame#HomePreviewCard {"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 rgba(20,29,45,0.96), stop:1 rgba(16,22,35,0.96));"
        "}"
        "QFrame#HomeThumbnailPlate {"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 rgba(106,122,162,0.20), stop:1 rgba(55,65,92,0.12));"
        " border: 1px solid rgba(160,170,195,0.14);"
        " border-radius: 12px;"
        "}"
        "QLabel#HomeHeroEyebrow, QLabel#HomePreviewEyebrow { font-size: 11px; font-weight: 800; color: %1; text-transform: uppercase; }"
        "QLabel#HomeHeroTitle { font-size: 24px; font-weight: 800; color: %2; }"
        "QLabel#HomeHeroBody, QLabel#HomeSectionBody, QLabel#HomePreviewBody { font-size: 12px; color: %3; }"
        "QLabel#HomeHeroHint { font-size: 10px; color: %3; }"
        "QLabel#HomeSectionTitle { font-size: 18px; font-weight: 800; color: %2; }"
        "QLabel#HomePreviewTitle { font-size: 13px; font-weight: 700; color: %2; }"
        "QLabel#HomeDependencyBanner {"
        " background: rgba(78, 166, 114, 0.12);"
        " border: 1px solid rgba(78, 166, 114, 0.24);"
        " border-radius: 12px;"
        " padding: 6px 12px;"
        " color: %2;"
        "}"
        "QLabel#HomeHeroInput {"
        " background: rgba(255,255,255,0.03);"
        " border: 1px dashed rgba(138, 128, 255, 0.30);"
        " border-radius: 12px;"
        " padding: 10px 12px;"
        " font-size: 12px;"
        " color: %2;"
        "}"
        "QLabel#HomeStackSummary {"
        " background: rgba(255,255,255,0.03);"
        " border: 1px solid rgba(120, 138, 172, 0.18);"
        " border-radius: 12px;"
        " padding: 10px 12px;"
        " font-size: 11px;"
        " color: %3;"
        "}"
        "QLabel#HomeStatLabel { font-size: 10px; font-weight: 800; color: %3; text-transform: uppercase; }"
        "QLabel#HomeStatValue {"
        " font-size: 11px;"
        " font-weight: 700;"
        " color: %2;"
        " background: rgba(255,255,255,0.03);"
        " border: 1px solid rgba(120,138,172,0.14);"
        " border-radius: 9px;"
        " padding: 3px 8px;"
        "}"
        "QPushButton#HomeModeButton {"
        " min-height: 30px;"
        " padding: 0px 12px;"
        " border-radius: 10px;"
        " font-size: 11px;"
        " font-weight: 700;"
        " background: transparent;"
        " border: 1px solid transparent;"
        " color: %3;"
        "}"
        "QPushButton#HomeModeButton:hover {"
        " background: rgba(255,255,255,0.05);"
        " border-color: rgba(138, 128, 255, 0.22);"
        " color: %2;"
        "}"
        "QPushButton#HomeModeButton:checked {"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 rgba(128,98,255,0.34), stop:1 rgba(92,184,255,0.18));"
        " border: 1px solid rgba(177, 166, 255, 0.62);"
        " color: %2;"
        "}"
        "QPushButton#PrimaryActionButton, QPushButton#SurfacePrimaryButton {"
        " min-height: 32px;"
        " padding: 0px 14px;"
        " border-radius: 10px;"
        " font-weight: 800;"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 rgba(139,108,255,0.34), stop:1 rgba(111,211,255,0.24));"
        " border: 1px solid rgba(162, 151, 255, 0.58);"
        "}"
        "QPushButton#SecondaryActionButton, QPushButton#SurfaceActionButton, QPushButton#SectionLinkButton, QPushButton#UtilityActionButton, QPushButton#SurfaceSecondaryButton {"
        " min-height: 30px;"
        " padding: 0px 13px;"
        " border-radius: 10px;"
        " font-weight: 700;"
        " background: rgba(255,255,255,0.04);"
        " border: 1px solid rgba(120,138,172,0.18);"
        "}"
        "QPushButton#SurfaceSecondaryButton, QPushButton#SectionLinkButton {"
        " background: transparent;"
        "}"
        "QPushButton#SecondaryActionButton:hover, QPushButton#SurfaceActionButton:hover, QPushButton#SectionLinkButton:hover, QPushButton#UtilityActionButton:hover, QPushButton#SurfaceSecondaryButton:hover {"
        " border-color: rgba(138, 128, 255, 0.28);"
        " background: rgba(255,255,255,0.06);"
        "}"
        "QPushButton#SectionLinkButton { min-height: 28px; padding: 0px 10px; }"
        "QPushButton#UtilityActionButton { min-height: 28px; }")
        .arg(theme.accentColor().name(), theme.textPrimaryColor().name(), theme.textSecondaryColor().name()));
}
