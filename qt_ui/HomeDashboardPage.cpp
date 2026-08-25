#include "HomeDashboardPage.h"

#include "DashboardGlassPanel.h"
#include "DashboardMetricChip.h"
#include "DashboardPreviewPlate.h"
#include "DashboardSurfaceTokens.h"
#include "HomeDashboardModuleRegistry.h"
#include "HomeModuleBase.h"
#include "HomeModuleFrame.h"
#include "OutputCardModel.h"
#include "ThemeManager.h"
#include "shell/ShellNavigationController.h"
#include "assets/ModelCardDelegate.h"
#include "assets/ModelCardView.h"
#include "assets/ModelThumbnailCache.h"
#include "generation/OutputPathHelpers.h"

#include <QAbstractButton>
#include <QBoxLayout>
#include <QButtonGroup>
#include <QDate>
#include <QDateTime>
#include <QDir>
#include <QDirIterator>
#include <QElapsedTimer>
#include <QFile>
#include <QTextStream>
#include <QFileInfoList>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QLayout>
#include <QPushButton>
#include <QResizeEvent>
#include <QShowEvent>
#include <QSizePolicy>
#include <QStackedWidget>
#include <QStandardPaths>
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

double parseSizeText(const QString &s)
{
    const QStringList parts = s.trimmed().split(QLatin1Char(' '), Qt::SkipEmptyParts);
    if (parts.size() < 2)
        return 0.0;
    bool ok = false;
    const double n = parts.at(0).toDouble(&ok);
    if (!ok)
        return 0.0;
    const QString u = parts.at(1).toUpper();
    if (u.startsWith(QStringLiteral("TB"))) return n * 1099511627776.0;
    if (u.startsWith(QStringLiteral("GB"))) return n * 1073741824.0;
    if (u.startsWith(QStringLiteral("MB"))) return n * 1048576.0;
    if (u.startsWith(QStringLiteral("KB"))) return n * 1024.0;
    return n;
}

QString humanBytes(double b)
{
    if (b >= 1099511627776.0) return QStringLiteral("%1 TB").arg(b / 1099511627776.0, 0, 'f', 1);
    if (b >= 1073741824.0) return QStringLiteral("%1 GB").arg(b / 1073741824.0, 0, 'f', 0);
    if (b >= 1048576.0) return QStringLiteral("%1 MB").arg(b / 1048576.0, 0, 'f', 0);
    return QStringLiteral("%1 KB").arg(b / 1024.0, 0, 'f', 0);
}

QString relativeTime(const QDateTime &then)
{
    const qint64 secs = then.secsTo(QDateTime::currentDateTime());
    if (secs < 60) return QStringLiteral("just now");
    if (secs < 3600) return QStringLiteral("%1m ago").arg(secs / 60);
    if (secs < 86400) return QStringLiteral("%1h ago").arg(secs / 3600);
    return QStringLiteral("%1d ago").arg(secs / 86400);
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
    // Home glass density: instrument scale (not marketing dashboard). Hero keeps presence;
    // utility/standard tighten toward cockpit card radii (~14–18).
    panel->setCornerRadius(variant == DashboardGlassPanel::Variant::Hero ? 18
                          : (variant == DashboardGlassPanel::Variant::Utility ? 12 : 14));
    panel->setGlowStrength(variant == DashboardGlassPanel::Variant::Hero ? 1.20
                          : (variant == DashboardGlassPanel::Variant::Utility ? 0.50 : 0.60));
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
    // Phase 5 (unify decision): all modes tint toward the single canonical accent. The old
    // per-mode tints (violet for image, cyan/blue for video) were sub-perceptual (~+10 B-R
    // overlay) AND off the ArcaneGlass "one violet accent, cyan=semantic-only" identity.
    // Returning the accent marks the card "tinted"; the paint widgets read the live accent
    // token so it also switches with the theme (see DashboardGlassPanel/PreviewPlate paint).
    Q_UNUSED(modeId)
    return ThemeManager::instance().color(ThemeManager::Color::Accent);
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
        root->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));

        eyebrowLabel_ = headline(QStringLiteral("START CREATING"), QStringLiteral("DashboardEyebrow"));
        titleLabel_ = headline(QStringLiteral("Text to Image"), QStringLiteral("DashboardHeroTitle"));
        subtitleLabel_ = headline(QString(), QStringLiteral("DashboardBody"));

        auto *modeSegment = glassPanel(DashboardGlassPanel::Variant::Inset,
                                       QStringLiteral("DashboardModeSegment"),
                                       48,
                                       this);
        auto *modeRow = new QHBoxLayout(modeSegment);
        modeRow->setContentsMargins(5, 5, 5, 5);
        modeRow->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Hairline));

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
        bandsLayout_->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));

        inputPanel_ = glassPanel(DashboardGlassPanel::Variant::Hero, QStringLiteral("DashboardInputPanel"), 118, bandsHost);
        auto *inputLayout = new QVBoxLayout(inputPanel_);
        inputLayout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Card), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Card), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
        inputLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
        inputLabel_ = headline(QString(), QStringLiteral("DashboardInputBand"));
        heroWavePlate_ = previewPlate(DashboardPreviewPlate::Style::HeroBand, 56, 0.0, inputPanel_);
        inputLayout->addWidget(inputLabel_);
        inputLayout->addWidget(heroWavePlate_);

        summaryPanel_ = glassPanel(DashboardGlassPanel::Variant::Inset, QStringLiteral("DashboardSummaryPanel"), 118, bandsHost);
        auto *summaryLayout = new QVBoxLayout(summaryPanel_);
        summaryLayout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Card), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Card), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
        summaryLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
        summaryLayout->addWidget(headline(QStringLiteral("Live Stack Snapshot"), QStringLiteral("DashboardMetaEyebrow")));
        summaryLabel_ = headline(QString(), QStringLiteral("DashboardSummaryBand"));
        summaryLayout->addWidget(summaryLabel_);
        summaryLayout->addStretch(1);

        bandsLayout_->addWidget(inputPanel_, 3);
        bandsLayout_->addWidget(summaryPanel_, 2);

        auto *actions = new QHBoxLayout;
        actions->setContentsMargins(0, 0, 0, 0);
        actions->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

        primaryButton_ = actionButton(QString(), QStringLiteral("DashboardPrimaryButton"));
        auto *workflowButton = actionButton(QStringLiteral("Open Workflow Library"), QStringLiteral("DashboardSecondaryButton"));
        auto *inspirationButton = actionButton(QStringLiteral("Browse Inspiration"), QStringLiteral("DashboardSecondaryButton"));
        // v1.0 nav gate: hide the Inspire entry point when the mode is gated (see isModeHidden).
        inspirationButton->setVisible(!spellvision::shell::ShellNavigationController::isModeHidden(QStringLiteral("inspiration")));

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
        root->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

        titleLabel_ = headline(QStringLiteral("Workflow Launcher"), QStringLiteral("DashboardSectionTitle"));
        subtitleLabel_ = headline(QStringLiteral("Recent and imported starters stay visible here, not buried under generic widgets."),
                                  QStringLiteral("DashboardBody"));

        cardsHost_ = new QWidget(this);
        cardsLayout_ = new QVBoxLayout(cardsHost_);
        cardsLayout_->setContentsMargins(0, 0, 0, 0);
        cardsLayout_->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

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
        layout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight), ThemeManager::instance().spacing(ThemeManager::Spacing::Tight), ThemeManager::instance().spacing(ThemeManager::Spacing::Tight), ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
        layout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

        layout->addWidget(headline(card.eyebrow, QStringLiteral("DashboardEyebrow")));
        auto *plate = previewPlate(card.phase < 0.3 ? DashboardPreviewPlate::Style::ContourBand : DashboardPreviewPlate::Style::HorizonBand, 16, card.phase, widget);
        plate->setAccentTint(modeTint(card.modeId));
        layout->addWidget(plate);
        layout->addWidget(headline(card.title, QStringLiteral("DashboardPreviewTitle")));
        layout->addWidget(headline(card.body, QStringLiteral("DashboardBody")));

        auto *buttons = new QHBoxLayout;
        buttons->setContentsMargins(0, 0, 0, 0);
        buttons->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

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

// The gallery -- the hero. Reuses the model-library grid whole: ModelCardView (rounding, hover
// overlay, lazy virtualized loading) + ModelCardDelegate (UNMODIFIED) painting an OutputCardModel that
// exposes the same roles. Scans the real output roots; the generalized ModelThumbnailCache turns a
// video into an ffmpeg poster transparently.
class HomeRecentOutputsModule final : public HomeModuleBase
{
public:
    explicit HomeRecentOutputsModule(QWidget *parent = nullptr)
        : HomeModuleBase(parent)
    {
        setObjectName(QStringLiteral("HomeRecentOutputsModule"));

        auto *root = new QVBoxLayout(this);
        root->setContentsMargins(2, 2, 2, 2);
        root->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

        titleLabel_ = headline(QStringLiteral("Your work"), QStringLiteral("DashboardSectionTitle"));
        subtitleLabel_ = headline(QStringLiteral("Recent renders — open one to keep working on it, or send an image to Image-to-Image."),
                                  QStringLiteral("DashboardBody"));

        thumbs_ = new spellvision::assets::ModelThumbnailCache(this);
        model_ = new OutputCardModel(this);
        view_ = new spellvision::assets::ModelCardView(this);
        view_->setModel(model_);
        view_->setItemDelegate(new spellvision::assets::ModelCardDelegate(thumbs_, view_));

        stack_ = new QStackedWidget(this);
        stack_->addWidget(view_);              // 0 = grid
        stack_->addWidget(buildEmptyState());  // 1 = empty state

        root->addWidget(titleLabel_);
        root->addWidget(subtitleLabel_);
        root->addWidget(stack_, 1);

        // A thumbnail landed -> repaint exactly that card.
        connect(thumbs_, &spellvision::assets::ModelThumbnailCache::thumbnailReady, this,
                [this](const QString &key, int) { model_->noteThumbnailReady(key); });

        // Primary (Open) = loadRequested / double-click; secondary (To I2I) = inspectRequested.
        connect(view_, &spellvision::assets::ModelCardView::loadRequested, this, [this](const QModelIndex &idx) {
            if (const auto *o = model_->outputAt(idx.row()))
                emit openOutputRequested(o->modeId, o->path);
        });
        connect(view_, &spellvision::assets::ModelCardView::inspectRequested, this, [this](const QModelIndex &idx) {
            if (const auto *o = model_->outputAt(idx.row()); o && !o->isVideo)
                emit sendOutputToInputRequested(QStringLiteral("i2i"), o->path);
        });

        reload();
    }

    QString moduleId() const override { return HomeDashboardIds::RecentOutputs; }
    QString displayName() const override { return QStringLiteral("Recent Outputs"); }
    QSize minimumDashboardSpan() const override { return QSize(6, 5); }
    QSize preferredDashboardSpan() const override { return QSize(12, 14); } // Your work fills Home

    void applyPreferences(const HomeModulePreferences &prefs) override
    {
        titleLabel_->setVisible(prefs.showTitle);
        subtitleLabel_->setVisible(prefs.showSubtitle);
    }

    void reload()
    {
        const int n = model_->reload();
        stack_->setCurrentIndex(n > 0 ? 0 : 1);
    }

protected:
    void showEvent(QShowEvent *event) override
    {
        HomeModuleBase::showEvent(event);
        reload(); // fresh scan whenever Home is shown, so new renders appear
    }

private:
    QWidget *buildEmptyState()
    {
        auto *empty = new QWidget(this);
        auto *lay = new QVBoxLayout(empty);
        lay->addStretch(1);
        auto *t = headline(QStringLiteral("No renders yet"), QStringLiteral("DashboardSectionTitle"));
        t->setAlignment(Qt::AlignHCenter);
        auto *s = headline(QStringLiteral("Your images and videos will appear here.\nHead to Text to Image on the rail to make your first."),
                           QStringLiteral("DashboardBody"));
        s->setAlignment(Qt::AlignHCenter);
        lay->addWidget(t);
        lay->addWidget(s);
        lay->addStretch(1);
        return empty;
    }

    QLabel *titleLabel_ = nullptr;
    QLabel *subtitleLabel_ = nullptr;
    spellvision::assets::ModelThumbnailCache *thumbs_ = nullptr;
    OutputCardModel *model_ = nullptr;
    spellvision::assets::ModelCardView *view_ = nullptr;
    QStackedWidget *stack_ = nullptr;
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
        root->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

        titleLabel_ = headline(QStringLiteral("Favorites Rail"), QStringLiteral("DashboardSectionTitle"));
        subtitleLabel_ = headline(QStringLiteral("Pinned starters get real surface area instead of being crushed into a utility strip."),
                                  QStringLiteral("DashboardBody"));

        gridHost_ = new QWidget(this);
        grid_ = new QGridLayout(gridHost_);
        grid_->setContentsMargins(0, 0, 0, 0);
        grid_->setHorizontalSpacing(10);
        grid_->setVerticalSpacing(10);

        auto *browseButton = actionButton(QStringLiteral("Browse Inspiration"), QStringLiteral("DashboardSecondaryButton"));
        // v1.0 nav gate: hide the Inspire entry point when the mode is gated (see isModeHidden).
        browseButton->setVisible(!spellvision::shell::ShellNavigationController::isModeHidden(QStringLiteral("inspiration")));
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
        layout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
        layout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

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
        buttons->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

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

// The dashboard band -- a subordinate footnote, deliberately NON-duplicative of the bottom bar
// (which already shows VRAM / queue / health / ETA). It carries what the bottom bar does not: library
// scale (models by type + total disk) and session/history (renders today + last render). Self-computed
// from the model-inventory cache + the real output dir.
class HomeActiveModelsModule final : public HomeModuleBase
{
public:
    explicit HomeActiveModelsModule(QWidget *parent = nullptr)
        : HomeModuleBase(parent)
    {
        setObjectName(QStringLiteral("HomeActiveModelsModule"));
        setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Maximum); // stay a thin band

        auto *root = new QHBoxLayout(this);
        root->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), 2,
                                 ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), 2);
        root->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

        auto *heading = headline(QStringLiteral("Library"), QStringLiteral("DashboardSectionTitle"));
        heading->setMaximumWidth(90);
        root->addWidget(heading);
        checkpointsChip_ = createChip(QStringLiteral("Checkpoints"));
        lorasChip_ = createChip(QStringLiteral("LoRAs"));
        vaesChip_ = createChip(QStringLiteral("VAEs"));
        upscalersChip_ = createChip(QStringLiteral("Upscalers"));
        diskChip_ = createChip(QStringLiteral("On disk"));
        root->addWidget(checkpointsChip_);
        root->addWidget(lorasChip_);
        root->addWidget(vaesChip_);
        root->addWidget(upscalersChip_);
        root->addWidget(diskChip_);

        root->addStretch(1);
        auto *sessionHeading = headline(QStringLiteral("Session"), QStringLiteral("DashboardSectionTitle"));
        sessionHeading->setMaximumWidth(80);
        root->addWidget(sessionHeading);
        todayChip_ = createChip(QStringLiteral("Renders today"));
        lastChip_ = createChip(QStringLiteral("Last render"));
        root->addWidget(todayChip_);
        root->addWidget(lastChip_);

        refresh();
    }

    QString moduleId() const override { return HomeDashboardIds::ActiveModels; }
    QString displayName() const override { return QStringLiteral("Library & Session"); }
    QSize minimumDashboardSpan() const override { return QSize(6, 1); }
    QSize preferredDashboardSpan() const override { return QSize(12, 1); }

    void applyPreferences(const HomeModulePreferences &) override {}

protected:
    void showEvent(QShowEvent *event) override
    {
        HomeModuleBase::showEvent(event);
        refresh();
    }

private:
    DashboardMetricChip *createChip(const QString &title)
    {
        auto *chip = new DashboardMetricChip(this);
        chip->setTitle(title);
        chip->setValue(QStringLiteral("—"));
        return chip;
    }

    void refresh()
    {
        // Library scale from the model-inventory cache (type counts + disk from sizeText).
        int checkpoints = 0, loras = 0, vaes = 0, upscalers = 0;
        double bytes = 0.0;
        const QString cachePath = QDir(QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation))
                                      .filePath(QStringLiteral("model_inventory_cache.json"));
        QFile cacheFile(cachePath);
        if (cacheFile.open(QIODevice::ReadOnly))
        {
            const QJsonArray entries = QJsonDocument::fromJson(cacheFile.readAll()).object().value(QStringLiteral("entries")).toArray();
            for (const QJsonValue &v : entries)
            {
                const QJsonObject e = v.toObject();
                const QString t = e.value(QStringLiteral("type")).toString().trimmed().toLower();
                if (t == QStringLiteral("model") || t == QStringLiteral("checkpoint")) ++checkpoints;
                else if (t == QStringLiteral("lora")) ++loras;
                else if (t == QStringLiteral("vae")) ++vaes;
                else if (t == QStringLiteral("upscaler")) ++upscalers;
                bytes += parseSizeText(e.value(QStringLiteral("sizeText")).toString());
            }
        }
        checkpointsChip_->setValue(QString::number(checkpoints));
        lorasChip_->setValue(QString::number(loras));
        vaesChip_->setValue(QString::number(vaes));
        upscalersChip_->setValue(QString::number(upscalers));
        diskChip_->setValue(bytes > 0.0 ? humanBytes(bytes) : QStringLiteral("—"));

        // Session from the real output dir: renders today + newest render time.
        int today = 0;
        QDateTime last;
        const QString destRoot = spellvision::generation::userGenerationDestFolder();
        const QString scanRoot = destRoot.isEmpty() ? spellvision::generation::chooseComfyOutputPath() : destRoot;
        QDir dir(scanRoot);
        if (dir.exists())
        {
            static const QStringList media = {QStringLiteral("*.png"), QStringLiteral("*.jpg"), QStringLiteral("*.jpeg"),
                                              QStringLiteral("*.webp"), QStringLiteral("*.mp4"), QStringLiteral("*.mov"),
                                              QStringLiteral("*.webm"), QStringLiteral("*.mkv")};
            static const QStringList plates = {QStringLiteral("plate.png"), QStringLiteral("plate_*.png")};
            const QDate todayDate = QDate::currentDate();
            if (!destRoot.isEmpty())
            {
                QDirIterator it(scanRoot, plates, QDir::Files, QDirIterator::Subdirectories);
                while (it.hasNext())
                {
                    it.next();
                    const QDateTime m = it.fileInfo().lastModified();
                    if (m.date() == todayDate)
                        ++today;
                    if (!last.isValid() || m > last)
                        last = m;
                }
            }
            else
            {
                const QFileInfoList files = dir.entryInfoList(media, QDir::Files);
                for (const QFileInfo &fi : files)
                {
                    const QDateTime m = fi.lastModified();
                    if (m.date() == todayDate)
                        ++today;
                    if (!last.isValid() || m > last)
                        last = m;
                }
            }
        }
        todayChip_->setValue(QString::number(today));
        lastChip_->setValue(last.isValid() ? relativeTime(last) : QStringLiteral("—"));
    }

    DashboardMetricChip *checkpointsChip_ = nullptr;
    DashboardMetricChip *lorasChip_ = nullptr;
    DashboardMetricChip *vaesChip_ = nullptr;
    DashboardMetricChip *upscalersChip_ = nullptr;
    DashboardMetricChip *diskChip_ = nullptr;
    DashboardMetricChip *todayChip_ = nullptr;
    DashboardMetricChip *lastChip_ = nullptr;
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
    hostLayout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Card), ThemeManager::instance().spacing(ThemeManager::Spacing::Card), ThemeManager::instance().spacing(ThemeManager::Spacing::Card), ThemeManager::instance().spacing(ThemeManager::Spacing::Card));
    hostLayout->setSpacing(0);

    auto *gridWrap = new QWidget(gridHost_);
    grid_ = new QGridLayout(gridWrap);
    grid_->setContentsMargins(0, 0, 0, 0);
    grid_->setHorizontalSpacing(10);
    grid_->setVerticalSpacing(10);
    hostLayout->addWidget(gridWrap);

    root->addWidget(gridHost_);

    // Startup attribution: Home is the landing page and cannot be deferred, so its
    // construction cost sits on the critical path. Gated on SPELLVISION_STARTUP_TRACE.
    static const bool traceEnabled = qEnvironmentVariableIsSet("SPELLVISION_STARTUP_TRACE");
    QElapsedTimer clock;
    clock.start();
    qint64 last = 0;
    const auto mark = [&clock, &last](const char *label) {
        if (!traceEnabled)
            return;
        const qint64 now = clock.elapsed();
        QFile f(QDir::currentPath() + QStringLiteral("/build/ui_startup_trace.log"));
        if (f.open(QIODevice::WriteOnly | QIODevice::Append | QIODevice::Text)) {
            QTextStream s(&f);
            s << QStringLiteral("    home:%1  +%2ms  (t=%3ms)\n")
                     .arg(QString::fromUtf8(label), -26).arg(now - last, 6).arg(now, 6);
        }
        last = now;
    };

    registerBuiltinModules();
    mark("registerBuiltinModules");
    config_ = defaultHomeDashboardConfig(HomeDashboardPreset::CinematicStudio);
    compactLayout_ = width() < 1320;
    resetContentToDefaults(/*rebuild=*/false);
    mark("resetContentToDefaults");

    applyTheme();
    mark("applyTheme");
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, &HomeDashboardPage::applyTheme);

    // Deliberately NOT rebuilding here -- see dashboardBuilt_ in the header. HomePage calls
    // setConfig() with the saved config immediately after constructing us, which rebuilds; doing
    // it here too meant building the whole grid twice on every launch and throwing the first away.
    mark("ctor end (rebuild deferred)");
}

void HomeDashboardPage::showEvent(QShowEvent *event)
{
    QWidget::showEvent(event);
    // Fallback for any owner that never calls setConfig: build on first show rather than never.
    if (!dashboardBuilt_)
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
    // In-place update of the existing hero module (mirrors setRuntimeSummary).
    // Only STRUCTURAL changes (placements / module set / config) go through the
    // destructive rebuildDashboard(); content updates must not tear down widgets.
    if (heroStarterPreview_ == preview)
        return;
    heroStarterPreview_ = preview;
    // The module subclasses have no Q_OBJECT, so findChild on HomeModuleBase
    // (which does) + dynamic_cast, exactly as rebuildDashboard() resolves them.
    for (HomeModuleFrame *frame : framesById_)
    {
        if (!frame)
            continue;
        if (auto *hero = dynamic_cast<HomeHeroModule *>(frame->findChild<HomeModuleBase *>()))
            hero->setStarterPreviewContract(heroStarterPreview_);
    }
}

void HomeDashboardPage::setWorkflowCards(const QVector<HomeWorkflowCard> &cards)
{
    if (workflowCards_ == cards)
        return;
    workflowCards_ = cards;
    for (HomeModuleFrame *frame : framesById_)
    {
        if (!frame)
            continue;
        if (auto *module = dynamic_cast<HomeWorkflowLauncherModule *>(frame->findChild<HomeModuleBase *>()))
            module->setCards(workflowCards_);
    }
}

void HomeDashboardPage::setRecentOutputCards(const QVector<HomeRecentOutputCard> &cards)
{
    // The gallery module now self-scans the real output dir; this legacy feed is a no-op kept for
    // source compatibility (HomePage still calls it).
    recentOutputCards_ = cards;
}

void HomeDashboardPage::setFavoriteCards(const QVector<HomeFavoriteCard> &cards)
{
    if (favoriteCards_ == cards)
        return;
    favoriteCards_ = cards;
    for (HomeModuleFrame *frame : framesById_)
    {
        if (!frame)
            continue;
        if (auto *module = dynamic_cast<HomeFavoritesModule *>(frame->findChild<HomeModuleBase *>()))
            module->setCards(favoriteCards_);
    }
}

void HomeDashboardPage::resetContentToDefaults(bool rebuild)
{
    heroStarterPreview_ = defaultStarterPreview();
    workflowCards_ = defaultWorkflowCards();
    recentOutputCards_ = defaultRecentOutputCards();
    favoriteCards_ = defaultFavoriteCards();
    if (rebuild && !rebuildInProgress_)
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
    dashboardBuilt_ = true;
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
        else if (auto *favorites = dynamic_cast<HomeFavoritesModule *>(module))
        {
            favorites->setCards(favoriteCards_);
        }
        // HomeRecentOutputsModule (the gallery) self-scans -- no card feed needed.

        connect(module, &HomeModuleBase::modeRequested, this, &HomeDashboardPage::modeRequested);
        connect(module, &HomeModuleBase::managerRequested, this, &HomeDashboardPage::managerRequested);
        connect(module, &HomeModuleBase::launchRequested, this, &HomeDashboardPage::launchRequested);
        connect(module, &HomeModuleBase::openOutputRequested, this, &HomeDashboardPage::openOutputRequested);
        connect(module, &HomeModuleBase::sendOutputToInputRequested, this, &HomeDashboardPage::sendOutputToInputRequested);

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
                    moduleId == HomeDashboardIds::HeroLauncher ? 3
                    : moduleId == HomeDashboardIds::RecentOutputs ? 10
                    : moduleId == HomeDashboardIds::ActiveModels ? 2
                                                                 : 3;
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

    // @token@ replace — avoid %10+ entirely; denser radii match cockpit (~10–12).
    setStyleSheet(QStringLiteral(R"(
#HomeDashboardPage {
    background: qradialgradient(cx:0.5, cy:0.30, radius:1.2, fx:0.46, fy:0.24,
                                stop:0 @pageTop@,
                                stop:0.5 @pageMid@,
                                stop:1 @pageBot@);
}
#HomeDashboardGridHost {
    background: transparent;
}
#HomeModuleHeader {
    background: transparent;
}
#HomeModuleTitle {
    color: @textMuted@;
    @label@
    letter-spacing: 0.08em;
}
#HomeModuleFrameButton {
    background: @utilA@;
    color: @textSec@;
    border: 1px solid @borderSoft@;
    border-radius: 8px;
    padding: 4px 8px;
    min-height: 24px;
    @label@
}
#HomeModuleFrameButton:hover {
    background: @utilHover@;
    border-color: @borderStrong@;
}
#DashboardHeroTitle {
    color: @textHi@;
    @display@
}
#DashboardSectionTitle {
    color: @textHi@;
    @subtitle@
}
#DashboardEyebrow,
#DashboardMetaEyebrow {
    color: @textMuted@;
    @caption@
    letter-spacing: 0.10em;
}
#DashboardBody,
#DashboardHint,
#DashboardInputBand,
#DashboardSummaryBand {
    color: @textSec@;
    @body@
}
#DashboardPreviewTitle {
    color: @textHi@;
    @subtitle@
}
#DashboardBanner {
    background: @successFill@;
    color: @textHi@;
    border: 1px solid @successBd@;
    border-radius: 10px;
    padding: 8px 12px;
    @bodystrong@
}
#DashboardModeButton,
#DashboardPrimaryButton,
#DashboardSecondaryButton,
#DashboardActionButton,
#DashboardUtilityButton {
    min-height: 34px;
    border-radius: 10px;
    padding: 0 14px;
    @label@
}
#DashboardModeButton {
    background: transparent;
    color: @textSec@;
    border: 1px solid transparent;
}
#DashboardModeButton:checked {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 @glowA@,
                                stop:1 @glowB@);
    color: white;
    border: 1px solid @borderStrong@;
}
#DashboardPrimaryButton,
#DashboardActionButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 @glowA@,
                                stop:1 @glowB@);
    color: white;
    border: 1px solid @borderStrong@;
}
#DashboardSecondaryButton,
#DashboardUtilityButton {
    background: @utilA@;
    color: @textHi@;
    border: 1px solid @borderSoft@;
}
#DashboardPrimaryButton:hover,
#DashboardSecondaryButton:hover,
#DashboardActionButton:hover,
#DashboardUtilityButton:hover,
#DashboardModeButton:hover {
    border-color: @borderStrong@;
    background: @utilHover@;
}
)")
                      .replace(QLatin1String("@pageTop@"), dashboardRgba(tokens.pageTop))
                      .replace(QLatin1String("@pageMid@"), dashboardRgba(tokens.pageMiddle))
                      .replace(QLatin1String("@pageBot@"), dashboardRgba(tokens.pageBottom))
                      .replace(QLatin1String("@textMuted@"), dashboardRgba(tokens.textMuted))
                      .replace(QLatin1String("@utilA@"), dashboardRgba(tokens.utilityA))
                      .replace(QLatin1String("@textSec@"), dashboardRgba(tokens.textSecondary))
                      .replace(QLatin1String("@borderSoft@"), dashboardRgba(tokens.borderSoft))
                      .replace(QLatin1String("@utilHover@"), dashboardRgba(dashboardMix(tokens.utilityA, tokens.glowPrimary, 0.10)))
                      .replace(QLatin1String("@borderStrong@"), dashboardRgba(tokens.borderStrong))
                      .replace(QLatin1String("@textHi@"), dashboardRgba(tokens.textPrimary))
                      .replace(QLatin1String("@successFill@"), dashboardRgba(tokens.successFill))
                      .replace(QLatin1String("@successBd@"), dashboardRgba(tokens.successBorder))
                      .replace(QLatin1String("@glowA@"), dashboardRgba(tokens.glowPrimary))
                      .replace(QLatin1String("@glowB@"), dashboardRgba(tokens.glowSecondary))
                      .replace(QLatin1String("@display@"), theme.fontCss(ThemeManager::Type::Display))
                      .replace(QLatin1String("@subtitle@"), theme.fontCss(ThemeManager::Type::Subtitle))
                      .replace(QLatin1String("@bodystrong@"), theme.fontCss(ThemeManager::Type::BodyStrong))
                      .replace(QLatin1String("@body@"), theme.fontCss(ThemeManager::Type::Body))
                      .replace(QLatin1String("@label@"), theme.fontCss(ThemeManager::Type::Label))
                      .replace(QLatin1String("@caption@"), theme.fontCss(ThemeManager::Type::Caption)));

    update();
    for (QWidget *widget : findChildren<QWidget *>())
        widget->update();
}
