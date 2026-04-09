#include "HomeDashboardPage.h"

#include "DashboardGlassPanel.h"
#include "DashboardMetricChip.h"
#include "DashboardPreviewPlate.h"
#include "DashboardSurfaceTokens.h"
#include "HomeDashboardModuleRegistry.h"
#include "HomeModuleBase.h"
#include "HomeModuleFrame.h"
#include "ThemeManager.h"

#include <QAbstractButton>
#include <QBoxLayout>
#include <QButtonGroup>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QLabel>
#include <QLayout>
#include <QPushButton>
#include <QResizeEvent>
#include <QSizePolicy>
#include <QVBoxLayout>

#include <algorithm>

namespace
{
QLabel *headline(const QString &text, const QString &name)
{
    auto *label = new QLabel(text);
    label->setObjectName(name);
    label->setWordWrap(true);
    return label;
}

QPushButton *actionButton(const QString &text, const QString &name)
{
    auto *button = new QPushButton(text);
    button->setObjectName(name);
    button->setCursor(Qt::PointingHandCursor);
    return button;
}

DashboardGlassPanel *glassPanel(DashboardGlassPanel::Variant variant,
                                const QString &objectName,
                                int minHeight = 0,
                                QWidget *parent = nullptr)
{
    auto *panel = new DashboardGlassPanel(parent);
    panel->setObjectName(objectName);
    panel->setVariant(variant);
    panel->setCornerRadius(variant == DashboardGlassPanel::Variant::Hero ? 24 : 18);
    panel->setGlowStrength(variant == DashboardGlassPanel::Variant::Hero ? 1.48 : (variant == DashboardGlassPanel::Variant::Utility ? 0.50 : 0.60));
    if (minHeight > 0)
        panel->setMinimumHeight(minHeight);
    panel->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
    return panel;
}

DashboardPreviewPlate *previewPlate(DashboardPreviewPlate::Style style,
                                    int minHeight,
                                    qreal phase = 0.0,
                                    QWidget *parent = nullptr)
{
    auto *plate = new DashboardPreviewPlate(parent);
    plate->setObjectName(QStringLiteral("DashboardPreviewPlate"));
    plate->setStyle(style);
    plate->setPhase(phase);
    plate->setMinimumHeight(minHeight);
    plate->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    return plate;
}

QColor modeTint(const QString &modeId)
{
    if (modeId == QStringLiteral("t2i"))
        return QColor(QStringLiteral("#7e7cff"));
    if (modeId == QStringLiteral("i2i"))
        return QColor(QStringLiteral("#4db6ff"));
    if (modeId == QStringLiteral("t2v"))
        return QColor(QStringLiteral("#25d0ff"));
    if (modeId == QStringLiteral("i2v"))
        return QColor(QStringLiteral("#8e7cff"));
    return QColor(QStringLiteral("#7e7cff"));
}

void clearLayoutAndDeleteWidgets(QLayout *layout)
{
    if (!layout)
        return;

    while (QLayoutItem *item = layout->takeAt(0))
    {
        if (QWidget *widget = item->widget())
            widget->deleteLater();
        delete item;
    }
}

void clearLayoutItemsOnly(QLayout *layout)
{
    if (!layout)
        return;

    while (QLayoutItem *item = layout->takeAt(0))
        delete item;
}

HomeStarterPreview defaultStarterPreview()
{
    HomeStarterPreview preview;
    preview.modeId = QStringLiteral("t2i");
    return preview;
}

QVector<HomeWorkflowCard> defaultWorkflowCards()
{
    return {
        {QStringLiteral("RECENT WORKFLOW"),
         QStringLiteral("Stylized Portraits"),
         QStringLiteral("Portrait starter with polished composition and lighting cues."),
         QStringLiteral("t2i"),
         QStringLiteral("Recent Workflow"),
         QStringLiteral("Preview in Hero"),
         0.18},
        {QStringLiteral("IMPORTED WORKFLOW"),
         QStringLiteral("Fantasy Art Generator"),
         QStringLiteral("Broad fantasy preset that primes the hero without leaving Home."),
         QStringLiteral("t2i"),
         QStringLiteral("Imported Workflow"),
         QStringLiteral("Preview in Hero"),
         0.52}
    };
}

QVector<HomeRecentOutputCard> defaultRecentOutputCards()
{
    return {
        {QStringLiteral("Character Portrait"),
         QStringLiteral("Send this still back into I2I for refinement."),
         QStringLiteral("i2i"),
         QStringLiteral("history"),
         0.08},
        {QStringLiteral("Open Landscape"),
         QStringLiteral("Route the world concept into T2V or open it for review."),
         QStringLiteral("t2v"),
         QStringLiteral("history"),
         0.32},
        {QStringLiteral("Motion Test"),
         QStringLiteral("Inspect the sequence and reopen the motion workspace."),
         QStringLiteral("i2v"),
         QStringLiteral("history"),
         0.58}
    };
}

QVector<HomeFavoriteCard> defaultFavoriteCards()
{
    return {
        {QStringLiteral("FAVORITE"),
         QStringLiteral("Portrait Armor"),
         QStringLiteral("Character concept starter with cinematic edge lighting."),
         QStringLiteral("t2i"),
         QStringLiteral("Favorite"),
         QStringLiteral("Preview in Hero"),
         0.10},
        {QStringLiteral("FAVORITE"),
         QStringLiteral("Open Landscape"),
         QStringLiteral("Environment mood starter for wide world concepts."),
         QStringLiteral("t2v"),
         QStringLiteral("Favorite"),
         QStringLiteral("Preview in Hero"),
         0.35},
        {QStringLiteral("FAVORITE"),
         QStringLiteral("Sci-Fi City"),
         QStringLiteral("Urban neon starting point for future-world sequences."),
         QStringLiteral("t2v"),
         QStringLiteral("Favorite"),
         QStringLiteral("Preview in Hero"),
         0.64}
    };
}

class HomeHeroModule final : public HomeModuleBase
{
public:
    explicit HomeHeroModule(QWidget *parent = nullptr)
        : HomeModuleBase(parent)
    {
        setObjectName(QStringLiteral("HomeHeroModule"));

        auto *root = new QVBoxLayout(this);
        root->setContentsMargins(2, 2, 2, 2);
        root->setSpacing(10);

        eyebrowLabel_ = headline(QStringLiteral("START CREATING"), QStringLiteral("DashboardEyebrow"));
        titleLabel_ = headline(QStringLiteral("Text to Image"), QStringLiteral("DashboardHeroTitle"));
        subtitleLabel_ = headline(QString(), QStringLiteral("DashboardBody"));

        auto *modeSegment = glassPanel(DashboardGlassPanel::Variant::Inset,
                                       QStringLiteral("DashboardModeSegment"),
                                       48,
                                       this);
        auto *modeRow = new QHBoxLayout(modeSegment);
        modeRow->setContentsMargins(5, 5, 5, 5);
        modeRow->setSpacing(4);

        modeButtons_ = new QButtonGroup(this);
        modeButtons_->setExclusive(true);

        struct ModeSpec
        {
            QString id;
            QString label;
        };

        const ModeSpec modes[] = {
            {QStringLiteral("t2i"), QStringLiteral("Text to Image")},
            {QStringLiteral("i2i"), QStringLiteral("Image to Image")},
            {QStringLiteral("t2v"), QStringLiteral("Text to Video")},
            {QStringLiteral("i2v"), QStringLiteral("Image to Video")},
        };

        for (const ModeSpec &mode : modes)
        {
            auto *button = actionButton(mode.label, QStringLiteral("DashboardModeButton"));
            button->setCheckable(true);
            button->setChecked(mode.id == currentMode_);
            modeButtons_->addButton(button);
            connect(button, &QPushButton::clicked, this, [this, mode]() {
                currentMode_ = mode.id;
                updateUi();
            });
            modeRow->addWidget(button, 1);
        }

        dependencyBannerLabel_ = headline(QString(), QStringLiteral("DashboardBanner"));

        auto *bandsHost = new QWidget(this);
        bandsLayout_ = new QBoxLayout(QBoxLayout::LeftToRight, bandsHost);
        bandsLayout_->setContentsMargins(0, 0, 0, 0);
        bandsLayout_->setSpacing(10);

        inputPanel_ = glassPanel(DashboardGlassPanel::Variant::Hero, QStringLiteral("DashboardInputPanel"), 118, bandsHost);
        auto *inputLayout = new QVBoxLayout(inputPanel_);
        inputLayout->setContentsMargins(14, 12, 14, 12);
        inputLayout->setSpacing(10);
        inputLabel_ = headline(QString(), QStringLiteral("DashboardInputBand"));
        heroWavePlate_ = previewPlate(DashboardPreviewPlate::Style::HeroBand, 56, 0.0, inputPanel_);
        inputLayout->addWidget(inputLabel_);
        inputLayout->addWidget(heroWavePlate_);

        summaryPanel_ = glassPanel(DashboardGlassPanel::Variant::Inset, QStringLiteral("DashboardSummaryPanel"), 118, bandsHost);
        auto *summaryLayout = new QVBoxLayout(summaryPanel_);
        summaryLayout->setContentsMargins(14, 12, 14, 12);
        summaryLayout->setSpacing(8);
        summaryLayout->addWidget(headline(QStringLiteral("Live Stack Snapshot"), QStringLiteral("DashboardMetaEyebrow")));
        summaryLabel_ = headline(QString(), QStringLiteral("DashboardSummaryBand"));
        summaryLayout->addWidget(summaryLabel_);
        summaryLayout->addStretch(1);

        bandsLayout_->addWidget(inputPanel_, 3);
        bandsLayout_->addWidget(summaryPanel_, 2);

        auto *actions = new QHBoxLayout;
        actions->setContentsMargins(0, 0, 0, 0);
        actions->setSpacing(8);

        primaryButton_ = actionButton(QString(), QStringLiteral("DashboardPrimaryButton"));
        auto *workflowButton = actionButton(QStringLiteral("Open Workflow Library"), QStringLiteral("DashboardSecondaryButton"));
        auto *inspirationButton = actionButton(QStringLiteral("Browse Inspiration"), QStringLiteral("DashboardSecondaryButton"));

        connect(primaryButton_, &QPushButton::clicked, this, [this]()
                {
                    emit launchRequested(currentMode_,
                                         starterTitle_,
                                         starterSubtitle_,
                                         starterSource_);
                });
        connect(workflowButton, &QPushButton::clicked, this, [this]() { emit managerRequested(QStringLiteral("workflows")); });
        connect(inspirationButton, &QPushButton::clicked, this, [this]() { emit managerRequested(QStringLiteral("inspiration")); });

        actions->addWidget(primaryButton_);
        actions->addWidget(workflowButton);
        actions->addWidget(inspirationButton);
        actions->addStretch(1);

        hintLabel_ = headline(QStringLiteral("Idle · 0%%. Home stays launcher-first."), QStringLiteral("DashboardHint"));

        root->addWidget(eyebrowLabel_);
        root->addWidget(titleLabel_);
        root->addWidget(subtitleLabel_);
        root->addSpacing(2);
        root->addWidget(modeSegment);
        root->addWidget(dependencyBannerLabel_);
        root->addWidget(bandsHost);
        root->addLayout(actions);
        root->addWidget(hintLabel_);
        root->addStretch(1);

        updateUi();
    }

    QString moduleId() const override { return HomeDashboardIds::HeroLauncher; }
    QString displayName() const override { return QStringLiteral("Hero Launcher"); }
    QSize minimumDashboardSpan() const override { return QSize(6, 4); }
    QSize preferredDashboardSpan() const override { return QSize(8, 4); }

    void applyPreferences(const HomeModulePreferences &prefs) override
    {
        if (eyebrowLabel_)
            eyebrowLabel_->setVisible(prefs.showTitle);
        if (subtitleLabel_)
            subtitleLabel_->setVisible(prefs.showSubtitle);
        if (heroWavePlate_)
            heroWavePlate_->setVisible(prefs.showPreviewPlate);
    }

    void setRuntimeSummary(const HomeRuntimeSummary &summary) override
    {
        HomeModuleBase::setRuntimeSummary(summary);
        if (!hintLabel_)
            return;

        const QString progressSummary =
            summary.progressText.trimmed().isEmpty() ? QStringLiteral("Idle") : summary.progressText;

        hintLabel_->setText(
            QStringLiteral("%1 · %2%%. Home stays launcher-first.")
                .arg(progressSummary)
                .arg(summary.progressPercent));
    }

    void setStarterPreviewContract(const HomeStarterPreview &preview)
    {
        starterTitle_ = preview.title;
        starterSubtitle_ = preview.subtitle;
        starterSource_ = preview.sourceLabel;
        if (!preview.modeId.trimmed().isEmpty())
            currentMode_ = preview.modeId.trimmed();
        updateUi();
    }

private:
    void updateUi()
    {
        if (modeButtons_)
        {
            for (QAbstractButton *button : modeButtons_->buttons())
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

        if (inputPanel_)
            inputPanel_->setAccentTint(modeTint(currentMode_));
        if (summaryPanel_)
            summaryPanel_->setAccentTint(modeTint(currentMode_));
        if (heroWavePlate_)
            heroWavePlate_->setAccentTint(modeTint(currentMode_));

        const QString sourcePrefix = starterSource_.trimmed().isEmpty()
                                         ? QStringLiteral("Start with a prompt, image, or workflow preview.")
                                         : QStringLiteral("%1 selected:").arg(starterSource_);

        if (currentMode_ == QStringLiteral("t2i"))
        {
            titleLabel_->setText(QStringLiteral("Text to Image"));
            subtitleLabel_->setText(QStringLiteral("Lead with the prompt, keep the stack visible, and launch straight into the focused canvas workspace."));
            dependencyBannerLabel_->setText(QStringLiteral("Dependency check: core image-generation requirements look ready."));
            primaryButton_->setText(QStringLiteral("Open Text to Image"));
            summaryLabel_->setText(QStringLiteral("Checkpoint: none selected\nLoRA: none\nWorkflow profile: Default Canvas"));
            inputLabel_->setText(
                starterTitle_.trimmed().isEmpty()
                    ? QStringLiteral("Prompt-first launch\nPaste a concept prompt, drag references, or start from a saved workflow.")
                    : QStringLiteral("%1\n%2\n%3").arg(sourcePrefix, starterTitle_, starterSubtitle_));
            return;
        }

        if (currentMode_ == QStringLiteral("i2i"))
        {
            titleLabel_->setText(QStringLiteral("Image to Image"));
            subtitleLabel_->setText(QStringLiteral("Bring a source image into the guided workspace for restyle and refinement."));
            dependencyBannerLabel_->setText(QStringLiteral("Dependency check: add a source image to prime the restyle flow."));
            primaryButton_->setText(QStringLiteral("Open Image to Image"));
            summaryLabel_->setText(QStringLiteral("Checkpoint: none selected\nLoRA: optional\nWorkflow profile: Restyle"));
            inputLabel_->setText(
                starterTitle_.trimmed().isEmpty()
                    ? QStringLiteral("Image-guided launch\nDrop a source image or preview a starter before opening I2I.")
                    : QStringLiteral("%1\n%2\n%3").arg(sourcePrefix, starterTitle_, starterSubtitle_));
            return;
        }

        if (currentMode_ == QStringLiteral("t2v"))
        {
            titleLabel_->setText(QStringLiteral("Text to Video"));
            subtitleLabel_->setText(QStringLiteral("Open the motion-first shell with room for prompt, duration, and cadence controls."));
            dependencyBannerLabel_->setText(QStringLiteral("Dependency check: the motion shell is ready for prompt-first planning."));
            primaryButton_->setText(QStringLiteral("Open Text to Video"));
            summaryLabel_->setText(QStringLiteral("Model: none selected\nFrames / FPS: guided defaults\nWorkflow profile: Motion Starter"));
            inputLabel_->setText(
                starterTitle_.trimmed().isEmpty()
                    ? QStringLiteral("Sequence starter\nDefine motion intent and duration before opening T2V.")
                    : QStringLiteral("%1\n%2\n%3").arg(sourcePrefix, starterTitle_, starterSubtitle_));
            return;
        }

        titleLabel_->setText(QStringLiteral("Image to Video"));
        subtitleLabel_->setText(QStringLiteral("Start from a still image or keyframe, then move into the motion workspace."));
        dependencyBannerLabel_->setText(QStringLiteral("Dependency check: add a keyframe image to unlock the motion path."));
        primaryButton_->setText(QStringLiteral("Open Image to Video"));
        summaryLabel_->setText(QStringLiteral("Model: none selected\nMotion guidance: waiting for keyframe\nWorkflow profile: Keyframe Motion"));
        inputLabel_->setText(
            starterTitle_.trimmed().isEmpty()
                ? QStringLiteral("Keyframe starter\nDrop a still image or preview a motion starter before opening I2V.")
                : QStringLiteral("%1\n%2\n%3").arg(sourcePrefix, starterTitle_, starterSubtitle_));
    }

    QString currentMode_ = QStringLiteral("t2i");
    QString starterTitle_;
    QString starterSubtitle_;
    QString starterSource_;

    QLabel *eyebrowLabel_ = nullptr;
    QLabel *titleLabel_ = nullptr;
    QLabel *subtitleLabel_ = nullptr;
    QLabel *dependencyBannerLabel_ = nullptr;
    QLabel *inputLabel_ = nullptr;
    QLabel *summaryLabel_ = nullptr;
    QLabel *hintLabel_ = nullptr;
    QPushButton *primaryButton_ = nullptr;
    QButtonGroup *modeButtons_ = nullptr;
    QBoxLayout *bandsLayout_ = nullptr;
    DashboardGlassPanel *inputPanel_ = nullptr;
    DashboardGlassPanel *summaryPanel_ = nullptr;
    DashboardPreviewPlate *heroWavePlate_ = nullptr;
};

class HomeWorkflowLauncherModule final : public HomeModuleBase
{
public:
    explicit HomeWorkflowLauncherModule(QWidget *parent = nullptr)
        : HomeModuleBase(parent)
    {
        setObjectName(QStringLiteral("HomeWorkflowLauncherModule"));

        auto *root = new QVBoxLayout(this);
        root->setContentsMargins(2, 2, 2, 2);
        root->setSpacing(8);

        titleLabel_ = headline(QStringLiteral("Workflow Launcher"), QStringLiteral("DashboardSectionTitle"));
        subtitleLabel_ = headline(QStringLiteral("Recent and imported starters stay visible here, not buried under generic widgets."),
                                  QStringLiteral("DashboardBody"));

        cardsHost_ = new QWidget(this);
        cardsLayout_ = new QVBoxLayout(cardsHost_);
        cardsLayout_->setContentsMargins(0, 0, 0, 0);
        cardsLayout_->setSpacing(8);

        auto *viewAll = actionButton(QStringLiteral("View All Workflows"), QStringLiteral("DashboardSecondaryButton"));
        connect(viewAll, &QPushButton::clicked, this, [this]() { emit managerRequested(QStringLiteral("workflows")); });

        root->addWidget(titleLabel_);
        root->addWidget(subtitleLabel_);
        root->addWidget(cardsHost_);
        root->addWidget(viewAll, 0, Qt::AlignLeft);
    }

    QString moduleId() const override { return HomeDashboardIds::WorkflowLauncher; }
    QString displayName() const override { return QStringLiteral("Workflow Launcher"); }
    QSize minimumDashboardSpan() const override { return QSize(4, 3); }
    QSize preferredDashboardSpan() const override { return QSize(4, 3); }

    void applyPreferences(const HomeModulePreferences &prefs) override
    {
        titleLabel_->setVisible(prefs.showTitle);
        subtitleLabel_->setVisible(prefs.showSubtitle);
    }

    void setCards(const QVector<HomeWorkflowCard> &cards)
    {
        cards_ = cards;
        rebuildCards();
    }

private:
    QWidget *createCard(const HomeWorkflowCard &card)
    {
        auto *widget = glassPanel(DashboardGlassPanel::Variant::Inset,
                                  QStringLiteral("DashboardPreviewCard"),
                                  92,
                                  this);
        widget->setAccentTint(modeTint(card.modeId));

        auto *layout = new QVBoxLayout(widget);
        layout->setContentsMargins(8, 8, 8, 8);
        layout->setSpacing(6);

        layout->addWidget(headline(card.eyebrow, QStringLiteral("DashboardEyebrow")));
        auto *plate = previewPlate(card.phase < 0.3 ? DashboardPreviewPlate::Style::ContourBand : DashboardPreviewPlate::Style::HorizonBand, 16, card.phase, widget);
        plate->setAccentTint(modeTint(card.modeId));
        layout->addWidget(plate);
        layout->addWidget(headline(card.title, QStringLiteral("DashboardPreviewTitle")));
        layout->addWidget(headline(card.body, QStringLiteral("DashboardBody")));

        auto *buttons = new QHBoxLayout;
        buttons->setContentsMargins(0, 0, 0, 0);
        buttons->setSpacing(8);

        auto *previewButton = actionButton(card.actionLabel.isEmpty() ? QStringLiteral("Preview in Hero") : card.actionLabel,
                                           QStringLiteral("DashboardSecondaryButton"));
        auto *openButton = actionButton(QStringLiteral("Open Library"), QStringLiteral("DashboardActionButton"));

        connect(previewButton, &QPushButton::clicked, this, [this, card]() {
            emit starterPreviewRequested(card.title, card.body, card.modeId, card.sourceLabel);
        });
        connect(openButton, &QPushButton::clicked, this, [this]() {
            emit managerRequested(QStringLiteral("workflows"));
        });

        buttons->addWidget(previewButton);
        buttons->addWidget(openButton);
        buttons->addStretch(1);
        layout->addLayout(buttons);

        return widget;
    }

    void rebuildCards()
    {
        clearLayoutAndDeleteWidgets(cardsLayout_);

        if (cards_.isEmpty())
        {
            cardsLayout_->addWidget(headline(QStringLiteral("No workflows surfaced yet. Imported and recent starters will appear here."),
                                             QStringLiteral("DashboardBody")));
            return;
        }

        for (const HomeWorkflowCard &card : cards_)
            cardsLayout_->addWidget(createCard(card));
    }

    QLabel *titleLabel_ = nullptr;
    QLabel *subtitleLabel_ = nullptr;
    QWidget *cardsHost_ = nullptr;
    QVBoxLayout *cardsLayout_ = nullptr;
    QVector<HomeWorkflowCard> cards_;
};

class HomeRecentOutputsModule final : public HomeModuleBase
{
public:
    explicit HomeRecentOutputsModule(QWidget *parent = nullptr)
        : HomeModuleBase(parent)
    {
        setObjectName(QStringLiteral("HomeRecentOutputsModule"));

        auto *root = new QVBoxLayout(this);
        root->setContentsMargins(2, 2, 2, 2);
        root->setSpacing(8);

        titleLabel_ = headline(QStringLiteral("Recent Outputs"), QStringLiteral("DashboardSectionTitle"));
        subtitleLabel_ = headline(QStringLiteral("Larger review plates stay on Home so finished work feels alive instead of tucked away."),
                                  QStringLiteral("DashboardBody"));

        gridHost_ = new QWidget(this);
        grid_ = new QGridLayout(gridHost_);
        grid_->setContentsMargins(0, 0, 0, 0);
        grid_->setHorizontalSpacing(10);
        grid_->setVerticalSpacing(10);

        root->addWidget(titleLabel_);
        root->addWidget(subtitleLabel_);
        root->addWidget(gridHost_, 1);
    }

    QString moduleId() const override { return HomeDashboardIds::RecentOutputs; }
    QString displayName() const override { return QStringLiteral("Recent Outputs"); }
    QSize minimumDashboardSpan() const override { return QSize(4, 4); }
    QSize preferredDashboardSpan() const override { return QSize(6, 5); }

    void applyPreferences(const HomeModulePreferences &prefs) override
    {
        titleLabel_->setVisible(prefs.showTitle);
        subtitleLabel_->setVisible(prefs.showSubtitle);
    }

    void setItems(const QVector<HomeRecentOutputCard> &items)
    {
        items_ = items;
        rebuildGrid(width());
    }

protected:
    void resizeEvent(QResizeEvent *event) override
    {
        HomeModuleBase::resizeEvent(event);
        rebuildGrid(event->size().width());
    }

private:
    QWidget *createCard(const HomeRecentOutputCard &item)
    {
        auto *card = glassPanel(DashboardGlassPanel::Variant::Raised,
                                QStringLiteral("DashboardPreviewCard"),
                                164,
                                this);
        card->setAccentTint(modeTint(item.routeModeId));

        auto *layout = new QVBoxLayout(card);
        layout->setContentsMargins(12, 12, 12, 12);
        layout->setSpacing(8);

        auto *plate = previewPlate(item.title == QStringLiteral("Character Portrait")
                                       ? DashboardPreviewPlate::Style::WidePreview
                                       : (item.title == QStringLiteral("Open Landscape")
                                              ? DashboardPreviewPlate::Style::ContourBand
                                              : DashboardPreviewPlate::Style::DataShimmer),
                                   96,
                                   item.phase,
                                   card);
        plate->setAccentTint(modeTint(item.routeModeId));
        layout->addWidget(plate);
        layout->addWidget(headline(item.title, QStringLiteral("DashboardPreviewTitle")));
        layout->addWidget(headline(item.body, QStringLiteral("DashboardBody")));

        auto *actions = new QHBoxLayout;
        actions->setContentsMargins(0, 0, 0, 0);
        actions->setSpacing(8);

        auto *openButton = actionButton(QStringLiteral("Open"), QStringLiteral("DashboardSecondaryButton"));
        auto *routeButton = actionButton(QStringLiteral("Send to Mode"), QStringLiteral("DashboardActionButton"));

        connect(openButton, &QPushButton::clicked, this, [this, item]() {
            emit managerRequested(item.openManagerId.trimmed().isEmpty() ? QStringLiteral("history") : item.openManagerId);
        });
        connect(routeButton, &QPushButton::clicked, this, [this, item]() {
            emit modeRequested(item.routeModeId);
        });

        actions->addWidget(openButton);
        actions->addWidget(routeButton);
        actions->addStretch(1);
        layout->addLayout(actions);

        return card;
    }

    void rebuildGrid(int width)
    {
        clearLayoutAndDeleteWidgets(grid_);

        if (items_.isEmpty())
        {
            grid_->addWidget(headline(QStringLiteral("Recent outputs will appear here once generation and history are linked."),
                                      QStringLiteral("DashboardBody")),
                             0,
                             0);
            return;
        }

        if (width < 920)
        {
            for (int i = 0; i < items_.size(); ++i)
                grid_->addWidget(createCard(items_[i]), i, 0);
            return;
        }

        if (width < 1400)
        {
            if (items_.size() > 0)
                grid_->addWidget(createCard(items_[0]), 0, 0);
            if (items_.size() > 1)
                grid_->addWidget(createCard(items_[1]), 0, 1);
            for (int i = 2; i < items_.size(); ++i)
                grid_->addWidget(createCard(items_[i]), 1 + (i - 2), 0, 1, 2);
            return;
        }

        for (int i = 0; i < items_.size(); ++i)
            grid_->addWidget(createCard(items_[i]), 0, i);
    }

    QLabel *titleLabel_ = nullptr;
    QLabel *subtitleLabel_ = nullptr;
    QWidget *gridHost_ = nullptr;
    QGridLayout *grid_ = nullptr;
    QVector<HomeRecentOutputCard> items_;
};

class HomeFavoritesModule final : public HomeModuleBase
{
public:
    explicit HomeFavoritesModule(QWidget *parent = nullptr)
        : HomeModuleBase(parent)
    {
        setObjectName(QStringLiteral("HomeFavoritesModule"));

        auto *root = new QVBoxLayout(this);
        root->setContentsMargins(2, 2, 2, 2);
        root->setSpacing(8);

        titleLabel_ = headline(QStringLiteral("Favorites Rail"), QStringLiteral("DashboardSectionTitle"));
        subtitleLabel_ = headline(QStringLiteral("Pinned starters get real surface area instead of being crushed into a utility strip."),
                                  QStringLiteral("DashboardBody"));

        gridHost_ = new QWidget(this);
        grid_ = new QGridLayout(gridHost_);
        grid_->setContentsMargins(0, 0, 0, 0);
        grid_->setHorizontalSpacing(10);
        grid_->setVerticalSpacing(10);

        auto *browseButton = actionButton(QStringLiteral("Browse Inspiration"), QStringLiteral("DashboardSecondaryButton"));
        connect(browseButton, &QPushButton::clicked, this, [this]() { emit managerRequested(QStringLiteral("inspiration")); });

        root->addWidget(titleLabel_);
        root->addWidget(subtitleLabel_);
        root->addWidget(gridHost_, 1);
        root->addWidget(browseButton, 0, Qt::AlignLeft);
    }

    QString moduleId() const override { return HomeDashboardIds::Favorites; }
    QString displayName() const override { return QStringLiteral("Favorites Rail"); }
    QSize minimumDashboardSpan() const override { return QSize(4, 4); }
    QSize preferredDashboardSpan() const override { return QSize(4, 5); }

    void applyPreferences(const HomeModulePreferences &prefs) override
    {
        titleLabel_->setVisible(prefs.showTitle);
        subtitleLabel_->setVisible(prefs.showSubtitle);
    }

    void setCards(const QVector<HomeFavoriteCard> &cards)
    {
        cards_ = cards;
        rebuildGrid(width());
    }

protected:
    void resizeEvent(QResizeEvent *event) override
    {
        HomeModuleBase::resizeEvent(event);
        rebuildGrid(event->size().width());
    }

private:
    QWidget *createCard(const HomeFavoriteCard &card)
    {
        auto *widget = glassPanel(DashboardGlassPanel::Variant::Standard,
                                  QStringLiteral("DashboardPreviewCard"),
                                  138,
                                  this);
        widget->setAccentTint(modeTint(card.modeId));

        auto *layout = new QVBoxLayout(widget);
        layout->setContentsMargins(12, 12, 12, 12);
        layout->setSpacing(6);

        layout->addWidget(headline(card.eyebrow, QStringLiteral("DashboardEyebrow")));
        auto *plate = previewPlate(card.title == QStringLiteral("Portrait Armor")
                                       ? DashboardPreviewPlate::Style::HorizonBand
                                       : (card.title == QStringLiteral("Open Landscape")
                                              ? DashboardPreviewPlate::Style::ContourBand
                                              : DashboardPreviewPlate::Style::DataShimmer),
                                   48,
                                   card.phase,
                                   widget);
        plate->setAccentTint(modeTint(card.modeId));
        layout->addWidget(plate);
        layout->addWidget(headline(card.title, QStringLiteral("DashboardPreviewTitle")));
        layout->addWidget(headline(card.body, QStringLiteral("DashboardBody")));

        auto *buttons = new QHBoxLayout;
        buttons->setContentsMargins(0, 0, 0, 0);
        buttons->setSpacing(8);

        auto *previewButton = actionButton(card.actionLabel.isEmpty() ? QStringLiteral("Preview in Hero") : card.actionLabel,
                                           QStringLiteral("DashboardSecondaryButton"));
        auto *launchButton = actionButton(QStringLiteral("Open Mode"), QStringLiteral("DashboardActionButton"));

        connect(previewButton, &QPushButton::clicked, this, [this, card]() {
            emit starterPreviewRequested(card.title, card.body, card.modeId, card.sourceLabel);
        });
        connect(launchButton, &QPushButton::clicked, this, [this, card]() {
            emit modeRequested(card.modeId);
        });

        buttons->addWidget(previewButton);
        buttons->addWidget(launchButton);
        buttons->addStretch(1);
        layout->addLayout(buttons);

        return widget;
    }

    void rebuildGrid(int width)
    {
        clearLayoutAndDeleteWidgets(grid_);

        if (cards_.isEmpty())
        {
            grid_->addWidget(headline(QStringLiteral("Pinned favorites will appear here once Home receives curated starters."),
                                      QStringLiteral("DashboardBody")),
                             0,
                             0);
            return;
        }

        if (width < 860)
        {
            for (int i = 0; i < cards_.size(); ++i)
                grid_->addWidget(createCard(cards_[i]), i, 0);
            return;
        }

        if (width < 1280)
        {
            if (cards_.size() > 0)
                grid_->addWidget(createCard(cards_[0]), 0, 0);
            if (cards_.size() > 1)
                grid_->addWidget(createCard(cards_[1]), 0, 1);
            for (int i = 2; i < cards_.size(); ++i)
                grid_->addWidget(createCard(cards_[i]), 1 + (i - 2), 0, 1, 2);
            return;
        }

        for (int i = 0; i < cards_.size(); ++i)
            grid_->addWidget(createCard(cards_[i]), 0, i);
    }

    QLabel *titleLabel_ = nullptr;
    QLabel *subtitleLabel_ = nullptr;
    QWidget *gridHost_ = nullptr;
    QGridLayout *grid_ = nullptr;
    QVector<HomeFavoriteCard> cards_;
};

class HomeActiveModelsModule final : public HomeModuleBase
{
public:
    explicit HomeActiveModelsModule(QWidget *parent = nullptr)
        : HomeModuleBase(parent)
    {
        setObjectName(QStringLiteral("HomeActiveModelsModule"));

        auto *root = new QVBoxLayout(this);
        root->setContentsMargins(2, 2, 2, 2);
        root->setSpacing(2);

        titleLabel_ = headline(QStringLiteral("Active Models + Shortcuts"), QStringLiteral("DashboardSectionTitle"));
        subtitleLabel_ = headline(QStringLiteral("Keep the current stack visible while the discovery surfaces stay clean and image-first."),
                                  QStringLiteral("DashboardBody"));
        subtitleLabel_->setMaximumHeight(32);

        root->addWidget(titleLabel_);
        root->addWidget(subtitleLabel_);
        root->addSpacing(2);

        checkpointChip_ = createChip(QStringLiteral("Checkpoint"), QStringLiteral("none"), false);
        loraChip_ = createChip(QStringLiteral("LoRA"), QStringLiteral("none"), false);
        queueChip_ = createChip(QStringLiteral("Queue"), QStringLiteral("0 run • 0 pending • 0 errors"), true);
        runtimeChip_ = createChip(QStringLiteral("Runtime"), QStringLiteral("Managed runtime"), false);

        root->addWidget(checkpointChip_);
        root->addWidget(loraChip_);
        root->addWidget(queueChip_);
        root->addWidget(runtimeChip_);

        auto *buttonGrid = new QGridLayout;
        buttonGrid->setContentsMargins(0, 0, 0, 0);
        buttonGrid->setHorizontalSpacing(4);
        buttonGrid->setVerticalSpacing(3);

        auto *modelsButton = actionButton(QStringLiteral("Models"), QStringLiteral("DashboardUtilityButton"));
        auto *downloadsButton = actionButton(QStringLiteral("Downloads"), QStringLiteral("DashboardUtilityButton"));
        auto *historyButton = actionButton(QStringLiteral("History"), QStringLiteral("DashboardUtilityButton"));
        auto *settingsButton = actionButton(QStringLiteral("Settings"), QStringLiteral("DashboardUtilityButton"));

        connect(modelsButton, &QPushButton::clicked, this, [this]() { emit managerRequested(QStringLiteral("models")); });
        connect(downloadsButton, &QPushButton::clicked, this, [this]() { emit managerRequested(QStringLiteral("downloads")); });
        connect(historyButton, &QPushButton::clicked, this, [this]() { emit managerRequested(QStringLiteral("history")); });
        connect(settingsButton, &QPushButton::clicked, this, [this]() { emit managerRequested(QStringLiteral("settings")); });

        buttonGrid->addWidget(modelsButton, 0, 0);
        buttonGrid->addWidget(downloadsButton, 0, 1);
        buttonGrid->addWidget(historyButton, 1, 0);
        buttonGrid->addWidget(settingsButton, 1, 1);
        root->addLayout(buttonGrid);
        root->addStretch(1);
    }

    QString moduleId() const override { return HomeDashboardIds::ActiveModels; }
    QString displayName() const override { return QStringLiteral("Active Models + Shortcuts"); }
    QSize minimumDashboardSpan() const override { return QSize(2, 4); }
    QSize preferredDashboardSpan() const override { return QSize(2, 5); }

    void applyPreferences(const HomeModulePreferences &prefs) override
    {
        titleLabel_->setVisible(prefs.showTitle);
        subtitleLabel_->setVisible(prefs.showSubtitle);
    }

    void setRuntimeSummary(const HomeRuntimeSummary &summary) override
    {
        HomeModuleBase::setRuntimeSummary(summary);

        if (checkpointChip_)
            checkpointChip_->setValue(summary.modelText.trimmed().isEmpty() ? QStringLiteral("none") : summary.modelText);
        if (loraChip_)
            loraChip_->setValue(summary.loraText.trimmed().isEmpty() ? QStringLiteral("none") : summary.loraText);
        if (queueChip_)
            queueChip_->setValue(QStringLiteral("%1 run • %2 pending • %3 errors")
                                     .arg(summary.runningCount)
                                     .arg(summary.pendingCount)
                                     .arg(summary.errorCount));
        if (runtimeChip_)
            runtimeChip_->setValue(summary.runtimeName.trimmed().isEmpty() ? QStringLiteral("Managed runtime") : summary.runtimeName);
    }

private:
    DashboardMetricChip *createChip(const QString &title, const QString &value, bool emphasized)
    {
        auto *chip = new DashboardMetricChip(this);
        chip->setTitle(title);
        chip->setValue(value);
        chip->setEmphasized(emphasized);
        return chip;
    }

    QLabel *titleLabel_ = nullptr;
    QLabel *subtitleLabel_ = nullptr;
    DashboardMetricChip *checkpointChip_ = nullptr;
    DashboardMetricChip *loraChip_ = nullptr;
    DashboardMetricChip *queueChip_ = nullptr;
    DashboardMetricChip *runtimeChip_ = nullptr;
};

} // namespace

HomeDashboardPage::HomeDashboardPage(QWidget *parent)
    : QWidget(parent)
{
    setObjectName(QStringLiteral("HomeDashboardPage"));

    auto *root = new QVBoxLayout(this);
    root->setContentsMargins(0, 0, 0, 0);
    root->setSpacing(0);

    gridHost_ = new QWidget(this);
    gridHost_->setObjectName(QStringLiteral("HomeDashboardGridHost"));

    auto *hostLayout = new QVBoxLayout(gridHost_);
    hostLayout->setContentsMargins(14, 14, 14, 16);
    hostLayout->setSpacing(0);

    auto *gridWrap = new QWidget(gridHost_);
    grid_ = new QGridLayout(gridWrap);
    grid_->setContentsMargins(0, 0, 0, 0);
    grid_->setHorizontalSpacing(10);
    grid_->setVerticalSpacing(10);
    hostLayout->addWidget(gridWrap);

    root->addWidget(gridHost_);

    registerBuiltinModules();
    config_ = defaultHomeDashboardConfig(HomeDashboardPreset::CinematicStudio);
    compactLayout_ = width() < 1320;
    resetContentToDefaults();

    applyTheme();
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, &HomeDashboardPage::applyTheme);

    rebuildDashboard();
}

void HomeDashboardPage::setConfig(const HomeDashboardConfig &config)
{
    if (!isValidHomeDashboardConfig(config))
    {
        config_ = defaultHomeDashboardConfig(HomeDashboardPreset::CinematicStudio);
        rebuildDashboard();
        emit configEdited(config_);
        return;
    }

    config_ = config;
    rebuildDashboard();
}

const HomeDashboardConfig &HomeDashboardPage::config() const
{
    return config_;
}

void HomeDashboardPage::setCustomizeMode(bool enabled)
{
    if (customizeMode_ == enabled)
        return;

    customizeMode_ = enabled;

    for (HomeModuleFrame *frame : framesById_)
    {
        if (!frame)
            continue;
        frame->setCustomizeMode(customizeMode_);
    }
}

bool HomeDashboardPage::isCustomizeMode() const
{
    return customizeMode_;
}

void HomeDashboardPage::setRuntimeSummary(const HomeRuntimeSummary &summary)
{
    runtimeSummary_ = summary;

    for (HomeModuleFrame *frame : framesById_)
    {
        if (!frame)
            continue;

        if (HomeModuleBase *module = frame->findChild<HomeModuleBase *>())
            module->setRuntimeSummary(runtimeSummary_);
    }
}

void HomeDashboardPage::setHeroStarterPreview(const HomeStarterPreview &preview)
{
    heroStarterPreview_ = preview;
    rebuildDashboard();
}

void HomeDashboardPage::setWorkflowCards(const QVector<HomeWorkflowCard> &cards)
{
    workflowCards_ = cards;
    rebuildDashboard();
}

void HomeDashboardPage::setRecentOutputCards(const QVector<HomeRecentOutputCard> &cards)
{
    recentOutputCards_ = cards;
    rebuildDashboard();
}

void HomeDashboardPage::setFavoriteCards(const QVector<HomeFavoriteCard> &cards)
{
    favoriteCards_ = cards;
    rebuildDashboard();
}

void HomeDashboardPage::resetContentToDefaults()
{
    heroStarterPreview_ = defaultStarterPreview();
    workflowCards_ = defaultWorkflowCards();
    recentOutputCards_ = defaultRecentOutputCards();
    favoriteCards_ = defaultFavoriteCards();
    if (!rebuildInProgress_)
        rebuildDashboard();
}

void HomeDashboardPage::resizeEvent(QResizeEvent *event)
{
    QWidget::resizeEvent(event);

    const int width = event ? event->size().width() : this->width();
    const bool compactNow = width < 1320;
    if (compactNow == compactLayout_)
        return;

    compactLayout_ = compactNow;
    rebuildDashboard();
}

void HomeDashboardPage::rebuildDashboard()
{
    if (rebuildInProgress_)
        return;

    rebuildInProgress_ = true;

    clearLayoutAndDeleteWidgets(grid_);
    framesById_.clear();

    const QVector<HomeModulePlacement> placements = effectivePlacements();
    HomeHeroModule *heroModule = nullptr;
    QVector<HomeModuleBase *> modules;

    for (const HomeModulePlacement &placement : placements)
    {
        if (!placement.visible)
            continue;
        if (!HomeDashboardModuleRegistry::instance().contains(placement.moduleId))
            continue;

        HomeModuleBase *module = HomeDashboardModuleRegistry::instance().create(placement.moduleId, gridHost_);
        if (!module)
            continue;

        module->applyPreferences(preferencesFor(placement.moduleId));
        module->setRuntimeSummary(runtimeSummary_);
        module->setCustomizeMode(customizeMode_);

        if (auto *hero = dynamic_cast<HomeHeroModule *>(module))
        {
            hero->setStarterPreviewContract(heroStarterPreview_);
            heroModule = hero;
        }
        else if (auto *workflow = dynamic_cast<HomeWorkflowLauncherModule *>(module))
        {
            workflow->setCards(workflowCards_);
        }
        else if (auto *recent = dynamic_cast<HomeRecentOutputsModule *>(module))
        {
            recent->setItems(recentOutputCards_);
        }
        else if (auto *favorites = dynamic_cast<HomeFavoritesModule *>(module))
        {
            favorites->setCards(favoriteCards_);
        }

        connect(module, &HomeModuleBase::modeRequested, this, &HomeDashboardPage::modeRequested);
        connect(module, &HomeModuleBase::managerRequested, this, &HomeDashboardPage::managerRequested);
        connect(module, &HomeModuleBase::launchRequested, this, &HomeDashboardPage::launchRequested);

        modules.push_back(module);

        auto *frame = new HomeModuleFrame(placement.moduleId, module->displayName(), module, gridHost_);
        frame->setCustomizeMode(customizeMode_);

        connect(frame, &HomeModuleFrame::moveRequested, this, [this](const QString &moduleId, int dx, int dy) {
            if (!adjustPlacement(moduleId, dx, dy))
                return;
            rebuildDashboard();
            emit configEdited(config_);
        });

        connect(frame, &HomeModuleFrame::resizeRequested, this, [this](const QString &moduleId, int dw, int dh) {
            if (!resizePlacement(moduleId, dw, dh))
                return;
            rebuildDashboard();
            emit configEdited(config_);
        });

        connect(frame, &HomeModuleFrame::visibilityRequested, this, [this](const QString &moduleId, bool visible) {
            if (!setPlacementVisibility(moduleId, visible))
                return;
            rebuildDashboard();
            emit configEdited(config_);
        });

        framesById_.insert(placement.moduleId, frame);
        grid_->addWidget(frame, placement.y, placement.x, placement.h, placement.w);
    }

    if (heroModule)
    {
        for (HomeModuleBase *module : modules)
        {
            if (!module || module == heroModule)
                continue;

            connect(module,
                    &HomeModuleBase::starterPreviewRequested,
                    this,
                    [heroModule](const QString &title,
                                 const QString &subtitle,
                                 const QString &modeId,
                                 const QString &sourceLabel)
                    {
                        if (!heroModule)
                            return;

                        HomeStarterPreview preview;
                        preview.title = title;
                        preview.subtitle = subtitle;
                        preview.modeId = modeId;
                        preview.sourceLabel = sourceLabel;
                        heroModule->setStarterPreviewContract(preview);
                    });
        }
    }

    int maxRow = 0;
    for (const HomeModulePlacement &placement : placements)
        maxRow = qMax(maxRow, placement.y + placement.h);
    maxRow = qMax(maxRow, 1);

    for (int col = 0; col < 12; ++col)
        grid_->setColumnStretch(col, 1);
    for (int row = 0; row < maxRow; ++row)
        grid_->setRowStretch(row, 1);

    rebuildInProgress_ = false;
}

void HomeDashboardPage::registerBuiltinModules()
{
    static bool registered = false;
    if (registered)
        return;

    auto &registry = HomeDashboardModuleRegistry::instance();
    registry.registerModule(HomeDashboardIds::HeroLauncher, [](QWidget *parent) {
        return new HomeHeroModule(parent);
    });
    registry.registerModule(HomeDashboardIds::WorkflowLauncher, [](QWidget *parent) {
        return new HomeWorkflowLauncherModule(parent);
    });
    registry.registerModule(HomeDashboardIds::RecentOutputs, [](QWidget *parent) {
        return new HomeRecentOutputsModule(parent);
    });
    registry.registerModule(HomeDashboardIds::Favorites, [](QWidget *parent) {
        return new HomeFavoritesModule(parent);
    });
    registry.registerModule(HomeDashboardIds::ActiveModels, [](QWidget *parent) {
        return new HomeActiveModelsModule(parent);
    });

    registered = true;
}

QVector<HomeModulePlacement> HomeDashboardPage::effectivePlacements() const
{
    if (!compactLayout_)
        return config_.placements;

    QVector<HomeModulePlacement> placements;
    int y = 0;

    auto push = [&placements, &y](const QString &moduleId, int h, bool visible = true) {
        placements.push_back({moduleId, 0, y, 12, h, visible, false});
        y += h;
    };

    for (const QString &moduleId : {
             HomeDashboardIds::HeroLauncher,
             HomeDashboardIds::WorkflowLauncher,
             HomeDashboardIds::RecentOutputs,
             HomeDashboardIds::Favorites,
             HomeDashboardIds::ActiveModels,
         })
    {
        auto it = std::find_if(config_.placements.begin(),
                               config_.placements.end(),
                               [&moduleId](const HomeModulePlacement &placement) {
                                   return placement.moduleId == moduleId;
                               });

        if (it == config_.placements.end() || !it->visible)
            continue;

        const int spanH =
            moduleId == HomeDashboardIds::HeroLauncher ? 4
            : moduleId == HomeDashboardIds::ActiveModels ? 3
                                                         : 4;
        push(moduleId, spanH);
    }

    return placements.isEmpty()
               ? defaultHomeDashboardConfig(HomeDashboardPreset::CinematicStudio).placements
               : placements;
}

bool HomeDashboardPage::adjustPlacement(const QString &moduleId, int dx, int dy)
{
    if (dx == 0 && dy == 0)
        return false;

    for (HomeModulePlacement &placement : config_.placements)
    {
        if (placement.moduleId != moduleId)
            continue;
        if (placement.locked)
            return false;

        placement.x = qBound(0, placement.x + dx, qMax(0, 12 - placement.w));
        placement.y = qMax(0, placement.y + dy);
        return true;
    }

    return false;
}

bool HomeDashboardPage::resizePlacement(const QString &moduleId, int dw, int dh)
{
    if (dw == 0 && dh == 0)
        return false;

    for (HomeModulePlacement &placement : config_.placements)
    {
        if (placement.moduleId != moduleId)
            continue;
        if (placement.locked)
            return false;

        placement.w = qBound(1, placement.w + dw, 12 - placement.x);
        placement.h = qMax(1, placement.h + dh);
        return true;
    }

    return false;
}

bool HomeDashboardPage::setPlacementVisibility(const QString &moduleId, bool visible)
{
    for (HomeModulePlacement &placement : config_.placements)
    {
        if (placement.moduleId != moduleId)
            continue;
        placement.visible = visible;
        return true;
    }
    return false;
}

HomeModulePreferences HomeDashboardPage::preferencesFor(const QString &moduleId) const
{
    return config_.modulePrefs.value(moduleId, HomeModulePreferences{});
}

void HomeDashboardPage::applyTheme()
{
    const auto &theme = ThemeManager::instance();
    const DashboardSurfaceTokens tokens = DashboardSurfaceTokens::fromTheme(theme);

    setStyleSheet(QStringLiteral(R"(
#HomeDashboardPage {
    background: qlineargradient(x1:0, y1:0, x2:0.94, y2:1,
                                stop:0 %1,
                                stop:0.34 %2,
                                stop:1 %3);
}
#HomeDashboardGridHost {
    background: transparent;
}
#HomeModuleHeader {
    background: transparent;
}
#HomeModuleTitle {
    color: %4;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
}
#HomeModuleFrameButton {
    background: %5;
    color: %6;
    border: 1px solid %7;
    border-radius: 9px;
    padding: 4px 8px;
    min-height: 24px;
    font-size: 11px;
    font-weight: 700;
}
#HomeModuleFrameButton:hover {
    background: %8;
    border-color: %9;
}
#DashboardHeroTitle {
    color: %10;
    font-size: 29px;
    font-weight: 800;
}
#DashboardSectionTitle {
    color: %10;
    font-size: 14px;
    font-weight: 800;
}
#DashboardEyebrow,
#DashboardMetaEyebrow {
    color: %11;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 0.10em;
}
#DashboardBody,
#DashboardHint,
#DashboardInputBand,
#DashboardSummaryBand {
    color: %12;
    font-size: 12px;
}
#DashboardPreviewTitle {
    color: %10;
    font-size: 14px;
    font-weight: 700;
}
#DashboardBanner {
    background: %13;
    color: %10;
    border: 1px solid %14;
    border-radius: 12px;
    padding: 8px 12px;
    font-size: 12px;
    font-weight: 600;
}
#DashboardModeButton,
#DashboardPrimaryButton,
#DashboardSecondaryButton,
#DashboardActionButton,
#DashboardUtilityButton {
    min-height: 34px;
    border-radius: 12px;
    padding: 0 14px;
    font-size: 11px;
    font-weight: 700;
}
#DashboardModeButton {
    background: transparent;
    color: %12;
    border: 1px solid transparent;
}
#DashboardModeButton:checked {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 %15,
                                stop:1 %16);
    color: white;
    border: 1px solid %17;
}
#DashboardPrimaryButton,
#DashboardActionButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 %15,
                                stop:1 %16);
    color: white;
    border: 1px solid %17;
}
#DashboardSecondaryButton,
#DashboardUtilityButton {
    background: %5;
    color: %10;
    border: 1px solid %7;
}
#DashboardPrimaryButton:hover,
#DashboardSecondaryButton:hover,
#DashboardActionButton:hover,
#DashboardUtilityButton:hover,
#DashboardModeButton:hover {
    border-color: %9;
    background: %8;
}
)")
                      .arg(dashboardRgba(tokens.pageTop),
                           dashboardRgba(tokens.pageMiddle),
                           dashboardRgba(tokens.pageBottom),
                           dashboardRgba(tokens.textMuted),
                           dashboardRgba(tokens.utilityA),
                           dashboardRgba(tokens.textSecondary),
                           dashboardRgba(tokens.borderSoft),
                           dashboardRgba(dashboardMix(tokens.utilityA, tokens.glowPrimary, 0.10)),
                           dashboardRgba(tokens.borderStrong),
                           dashboardRgba(tokens.textPrimary),
                           dashboardRgba(tokens.textMuted),
                           dashboardRgba(tokens.textSecondary),
                           dashboardRgba(tokens.successFill),
                           dashboardRgba(tokens.successBorder),
                           dashboardRgba(tokens.glowPrimary),
                           dashboardRgba(tokens.glowSecondary),
                           dashboardRgba(tokens.borderStrong)));

    update();
    for (QWidget *widget : findChildren<QWidget *>())
        widget->update();
}
