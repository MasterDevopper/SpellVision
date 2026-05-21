#include "chain/ChainConfigPanelWidget.h"

// --- PASS 7D1 FIXUP CLICKONLY INCLUDE ---
#include "widgets/ClickOnlyComboBox.h"
#include "ThemeManager.h"
#include "widgets/SectionCardWidgets.h"

#include <QAbstractSpinBox>
#include <QComboBox>
#include <QDoubleSpinBox>
#include <QFrame>
#include <QHBoxLayout>
#include <QLabel>
#include <QPushButton>
#include <QScrollArea>
#include <QSizePolicy>
#include <QSpinBox>
#include <QVBoxLayout>

namespace spellvision::chain
{

using spellvision::widgets::ClickOnlyComboBox;

namespace
{

// --- duplicated from ImageGenerationPage.cpp:298-340 ---
// These helpers aren't in a shared header yet. Pass 10 polish can
// promote them to widgets/SectionCardWidgets.h alongside createCard
// etc., at which point we delete these local copies.

void configureComboBoxLocal(QComboBox *combo)
{
    if (combo == nullptr)
        return;
    combo->setFocusPolicy(Qt::StrongFocus);
    combo->setMaxVisibleItems(18);
    combo->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon);
    combo->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
}

void configureSpinBoxLocal(QSpinBox *spin)
{
    if (spin == nullptr)
        return;
    spin->setAccelerated(true);
    spin->setKeyboardTracking(false);
    spin->setButtonSymbols(QAbstractSpinBox::UpDownArrows);
    spin->setAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    spin->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
}

void configureDoubleSpinBoxLocal(QDoubleSpinBox *spin)
{
    if (spin == nullptr)
        return;
    spin->setAccelerated(true);
    spin->setKeyboardTracking(false);
    spin->setButtonSymbols(QAbstractSpinBox::UpDownArrows);
    spin->setAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    spin->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
}

// Stacked-label group: a small caption label above a single control.
// The v3 mockup uses this pattern for each config field. Returns the
// outer widget so callers can add to their layout.
QWidget *makeLabeledControl(const QString &captionText, QWidget *control, QWidget *parent)
{
    auto *holder = new QWidget(parent);
    auto *layout = new QVBoxLayout(holder);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(4);

    const auto &tm = ThemeManager::instance();
    auto *caption = new QLabel(captionText, holder);
    caption->setStyleSheet(QStringLiteral(
        "QLabel { color: %1; font-size: 10px; font-weight: 700; "
        "letter-spacing: 0.6px; text-transform: uppercase; }"
    ).arg(tm.textMutedColor().name()));
    layout->addWidget(caption);
    layout->addWidget(control);
    return holder;
}

// Status label text for the header subtitle.
QString stageStatusSubtitle(StageStatus status)
{
    switch (status)
    {
        case StageStatus::Draft:      return QStringLiteral("Idle \u2014 ready to configure");
        case StageStatus::Queued:     return QStringLiteral("Queued");
        case StageStatus::Generating: return QStringLiteral("Generating");
        case StageStatus::Completed:  return QStringLiteral("Completed \u2014 click LOCK to commit");
        case StageStatus::Failed:     return QStringLiteral("Failed \u2014 adjust and retry");
        case StageStatus::Locked:     return QStringLiteral("Locked \u2014 display only");
    }
    return QStringLiteral("\u2014");
}

QString stageKindUpper(StageKind k)
{
    switch (k)
    {
        case StageKind::T2I:   return QStringLiteral("T2I");
        case StageKind::T2V:   return QStringLiteral("T2V");
        case StageKind::I2I:   return QStringLiteral("I2I");
        case StageKind::I2V:   return QStringLiteral("I2V");
        case StageKind::I2_3D: return QStringLiteral("I\u2192" "3D");
        case StageKind::Audio: return QStringLiteral("AUDIO");
    }
    return QStringLiteral("?");
}

QString panelChromeStyle()
{
    const auto &tm = ThemeManager::instance();
    return QStringLiteral(
        "QFrame#ChainConfigPanelRoot { "
        "  background: %1; "
        "  border: 1px solid %2; "
        "  border-radius: %3px; "
        "}"
    ).arg(tm.surface1Color().name(),
          tm.borderToneColor().name(),
          QString::number(tm.radiusCard()));
}

QString headerTitleStyle()
{
    const auto &tm = ThemeManager::instance();
    return QStringLiteral(
        "QLabel { color: %1; font-size: 12px; font-weight: 800; "
        "letter-spacing: 1.1px; }"
    ).arg(tm.accentColor().name());
}

QString headerSubtitleStyle()
{
    const auto &tm = ThemeManager::instance();
    return QStringLiteral(
        "QLabel { color: %1; font-size: 11px; }"
    ).arg(tm.textMutedColor().name());
}

QString headerDividerStyle()
{
    const auto &tm = ThemeManager::instance();
    return QStringLiteral(
        "QFrame { background: %1; max-height: 1px; min-height: 1px; "
        "border: none; }"
    ).arg(tm.borderToneColor().name());
}

QString emptyLabelStyle()
{
    const auto &tm = ThemeManager::instance();
    return QStringLiteral(
        "QLabel { color: %1; font-size: 12px; font-weight: 500; }"
    ).arg(tm.textMutedColor().name());
}

QString regenerateButtonStyle(bool enabled)
{
    const auto &tm = ThemeManager::instance();
    const QColor color = enabled ? tm.accentColor() : tm.textMutedColor();
    return QStringLiteral(
        "QPushButton { "
        "  color: %2; "
        "  background: transparent; "
        "  border: 1px solid %1; "
        "  border-radius: %3px; "
        "  padding: 8px 18px; "
        "  font-size: 11px; "
        "  font-weight: 800; "
        "  letter-spacing: 0.6px; "
        "}"
        "QPushButton:hover:enabled { background: %1; color: %4; }"
        "QPushButton:disabled { color: %5; border-color: %5; }"
    ).arg(color.name(),
          tm.textPrimaryColor().name(),
          QString::number(tm.radiusPill()),
          tm.surface0Color().name(),
          tm.background1Color().name());
}

} // anonymous namespace

ChainConfigPanelWidget::ChainConfigPanelWidget(QWidget *parent)
    : QWidget(parent)
{
    const auto &tm = ThemeManager::instance();

    // ---- Outer card chrome on `this` (no inner styled child needed) ----
    setObjectName(QStringLiteral("ChainConfigPanelRoot"));
    setStyleSheet(panelChromeStyle());
    // We set border styling on a QWidget via stylesheet; for that to
    // paint correctly we need autoFillBackground OR for the stylesheet
    // to fully cover the widget. Stylesheet alone works here because
    // we've targeted ChainConfigPanelRoot by object name.

    auto *root = new QVBoxLayout(this);
    root->setContentsMargins(0, 0, 0, 0);
    root->setSpacing(0);

    // ---- Header (cfg-h) ----
    auto *header = new QWidget(this);
    auto *headerLayout = new QVBoxLayout(header);
    const int hpad = tm.spacing(ThemeManager::Spacing::Card);
    headerLayout->setContentsMargins(hpad, hpad, hpad,
                                     tm.spacing(ThemeManager::Spacing::Snug));
    headerLayout->setSpacing(4);

    headerTitle_ = new QLabel(QStringLiteral("CONFIG"), header);
    headerTitle_->setStyleSheet(headerTitleStyle());
    headerLayout->addWidget(headerTitle_);

    headerSubtitle_ = new QLabel(QStringLiteral("\u2014"), header);
    headerSubtitle_->setStyleSheet(headerSubtitleStyle());
    headerLayout->addWidget(headerSubtitle_);

    root->addWidget(header, 0);

    auto *headerDivider = new QFrame(this);
    headerDivider->setStyleSheet(headerDividerStyle());
    root->addWidget(headerDivider, 0);

    // ---- Body (cfg-body) — scrollable, holds the seven controls ----
    auto *scroll = new QScrollArea(this);
    scroll->setWidgetResizable(true);
    scroll->setFrameShape(QFrame::NoFrame);
    scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    scroll->setStyleSheet(QStringLiteral("QScrollArea { background: transparent; }"));

    bodyHolder_ = new QFrame;
    bodyHolder_->setStyleSheet(QStringLiteral("QFrame { background: transparent; }"));
    auto *bodyLayout = new QVBoxLayout(bodyHolder_);
    bodyLayout->setContentsMargins(hpad, tm.spacing(ThemeManager::Spacing::Snug),
                                   hpad, hpad);
    bodyLayout->setSpacing(tm.spacing(ThemeManager::Spacing::Snug));

    // Empty-state label sits inside the body, shown when no stage is
    // selected or selection is unresolvable.
    emptyLabel_ = new QLabel(
        QStringLiteral("Select a stage from the rail above to view its configuration."),
        bodyHolder_);
    emptyLabel_->setStyleSheet(emptyLabelStyle());
    emptyLabel_->setAlignment(Qt::AlignCenter);
    emptyLabel_->setWordWrap(true);
    bodyLayout->addWidget(emptyLabel_);

    // ---- The seven controls ----
    samplerCombo_ = new ClickOnlyComboBox(bodyHolder_);
    samplerCombo_->addItem(QStringLiteral("euler"),           QStringLiteral("euler"));
    samplerCombo_->addItem(QStringLiteral("euler_ancestral"), QStringLiteral("euler_ancestral"));
    samplerCombo_->addItem(QStringLiteral("heun"),            QStringLiteral("heun"));
    samplerCombo_->addItem(QStringLiteral("dpmpp_2m"),        QStringLiteral("dpmpp_2m"));
    samplerCombo_->addItem(QStringLiteral("dpmpp_sde"),       QStringLiteral("dpmpp_sde"));
    samplerCombo_->addItem(QStringLiteral("uni_pc"),          QStringLiteral("uni_pc"));
    configureComboBoxLocal(samplerCombo_);
    bodyLayout->addWidget(makeLabeledControl(QStringLiteral("Sampler"), samplerCombo_, bodyHolder_));

    schedulerCombo_ = new ClickOnlyComboBox(bodyHolder_);
    schedulerCombo_->addItem(QStringLiteral("normal"),      QStringLiteral("normal"));
    schedulerCombo_->addItem(QStringLiteral("karras"),      QStringLiteral("karras"));
    schedulerCombo_->addItem(QStringLiteral("sgm_uniform"), QStringLiteral("sgm_uniform"));
    configureComboBoxLocal(schedulerCombo_);
    bodyLayout->addWidget(makeLabeledControl(QStringLiteral("Scheduler"), schedulerCombo_, bodyHolder_));

    stepsSpin_ = new QSpinBox(bodyHolder_);
    stepsSpin_->setRange(1, 500);
    stepsSpin_->setValue(20);
    configureSpinBoxLocal(stepsSpin_);
    bodyLayout->addWidget(makeLabeledControl(QStringLiteral("Steps"), stepsSpin_, bodyHolder_));

    cfgSpin_ = new QDoubleSpinBox(bodyHolder_);
    cfgSpin_->setRange(0.0, 30.0);
    cfgSpin_->setSingleStep(0.5);
    cfgSpin_->setDecimals(1);
    cfgSpin_->setValue(7.0);
    configureDoubleSpinBoxLocal(cfgSpin_);
    bodyLayout->addWidget(makeLabeledControl(QStringLiteral("CFG"), cfgSpin_, bodyHolder_));

    seedSpin_ = new QSpinBox(bodyHolder_);
    seedSpin_->setRange(-1, 2147483647);   // -1 conventionally means "random"
    seedSpin_->setValue(-1);
    seedSpin_->setSpecialValueText(QStringLiteral("random (-1)"));
    configureSpinBoxLocal(seedSpin_);
    bodyLayout->addWidget(makeLabeledControl(QStringLiteral("Seed"), seedSpin_, bodyHolder_));

    // Width / Height in a side-by-side row to economize vertical space.
    auto *dimRow = new QWidget(bodyHolder_);
    auto *dimRowLayout = new QHBoxLayout(dimRow);
    dimRowLayout->setContentsMargins(0, 0, 0, 0);
    dimRowLayout->setSpacing(tm.spacing(ThemeManager::Spacing::Tight));

    widthSpin_ = new QSpinBox(dimRow);
    widthSpin_->setRange(64, 8192);
    widthSpin_->setSingleStep(64);
    widthSpin_->setValue(1024);
    configureSpinBoxLocal(widthSpin_);
    dimRowLayout->addWidget(makeLabeledControl(QStringLiteral("Width"), widthSpin_, dimRow), 1);

    heightSpin_ = new QSpinBox(dimRow);
    heightSpin_->setRange(64, 8192);
    heightSpin_->setSingleStep(64);
    heightSpin_->setValue(1024);
    configureSpinBoxLocal(heightSpin_);
    dimRowLayout->addWidget(makeLabeledControl(QStringLiteral("Height"), heightSpin_, dimRow), 1);

    bodyLayout->addWidget(dimRow);

    bodyLayout->addStretch(1);

    scroll->setWidget(bodyHolder_);
    root->addWidget(scroll, 1);

    // ---- Footer (cfg-foot) ----
    auto *footerDivider = new QFrame(this);
    footerDivider->setStyleSheet(headerDividerStyle());
    root->addWidget(footerDivider, 0);

    auto *footer = new QWidget(this);
    auto *footerLayout = new QHBoxLayout(footer);
    footerLayout->setContentsMargins(hpad, tm.spacing(ThemeManager::Spacing::Snug),
                                     hpad, tm.spacing(ThemeManager::Spacing::Snug));
    footerLayout->setSpacing(tm.spacing(ThemeManager::Spacing::Snug));

    regenerateButton_ = new QPushButton(QStringLiteral("REGENERATE"), footer);
    regenerateButton_->setCursor(Qt::PointingHandCursor);
    regenerateButton_->setStyleSheet(regenerateButtonStyle(true));
    connect(regenerateButton_, &QPushButton::clicked,
            this, &ChainConfigPanelWidget::onRegenerateClicked);

    footerLayout->addStretch(1);
    footerLayout->addWidget(regenerateButton_);
    footerLayout->addStretch(1);

    root->addWidget(footer, 0);

    refresh();
}

void ChainConfigPanelWidget::setChain(const Chain &chain)
{
    chain_ = chain;
    refresh();
}

void ChainConfigPanelWidget::setSelectedStageId(const QString &stageId)
{
    if (selectedStageId_ == stageId)
        return;
    selectedStageId_ = stageId;
    refresh();
}

const Stage *ChainConfigPanelWidget::currentStage() const
{
    if (selectedStageId_.isEmpty())
        return nullptr;
    for (const Stage &s : chain_.stages)
    {
        if (s.id == selectedStageId_)
            return &s;
    }
    return nullptr;
}

void ChainConfigPanelWidget::setEmptyState(bool empty)
{
    if (emptyLabel_ != nullptr)
        emptyLabel_->setVisible(empty);
    // The seven controls live under labeled holders which are siblings
    // of emptyLabel_ in bodyHolder_'s layout. Hide/show them all.
    for (auto *spin : {stepsSpin_, seedSpin_, widthSpin_, heightSpin_})
    {
        if (spin != nullptr && spin->parentWidget() != nullptr)
            spin->parentWidget()->setVisible(!empty);
    }
    if (cfgSpin_ != nullptr && cfgSpin_->parentWidget() != nullptr)
        cfgSpin_->parentWidget()->setVisible(!empty);
    for (auto *combo : {samplerCombo_, schedulerCombo_})
    {
        if (combo != nullptr && combo->parentWidget() != nullptr)
            combo->parentWidget()->setVisible(!empty);
    }
    if (regenerateButton_ != nullptr)
        regenerateButton_->setEnabled(!empty);
}

void ChainConfigPanelWidget::applyConfigToControls(const StageConfig &config)
{
    // Block signals while updating to prevent edit-signal cascades.
    // (Pass 7d.1 doesn't yet connect editing signals, but doing this
    // now means Pass 8 can wire them without thinking about loops.)
    const auto blockOn = [](QObject *o) { if (o) o->blockSignals(true); };
    const auto blockOff = [](QObject *o) { if (o) o->blockSignals(false); };

    for (QObject *o : QList<QObject *>{samplerCombo_, schedulerCombo_,
                                       stepsSpin_, cfgSpin_, seedSpin_,
                                       widthSpin_, heightSpin_})
        blockOn(o);

    if (samplerCombo_ != nullptr)
    {
        const QString s = config.imageSampler.isEmpty()
            ? QStringLiteral("dpmpp_2m") : config.imageSampler;
        const int idx = samplerCombo_->findData(s);
        samplerCombo_->setCurrentIndex(idx >= 0 ? idx : 0);
    }
    if (schedulerCombo_ != nullptr)
    {
        const QString s = config.imageScheduler.isEmpty()
            ? QStringLiteral("karras") : config.imageScheduler;
        const int idx = schedulerCombo_->findData(s);
        schedulerCombo_->setCurrentIndex(idx >= 0 ? idx : 0);
    }
    if (stepsSpin_ != nullptr)
        stepsSpin_->setValue(config.steps > 0 ? config.steps : 20);
    if (cfgSpin_ != nullptr)
        cfgSpin_->setValue(config.cfg > 0.0 ? config.cfg : 7.0);
    if (seedSpin_ != nullptr)
        seedSpin_->setValue(config.seed);
    if (widthSpin_ != nullptr)
        widthSpin_->setValue(config.width > 0 ? config.width : 1024);
    if (heightSpin_ != nullptr)
        heightSpin_->setValue(config.height > 0 ? config.height : 1024);

    for (QObject *o : QList<QObject *>{samplerCombo_, schedulerCombo_,
                                       stepsSpin_, cfgSpin_, seedSpin_,
                                       widthSpin_, heightSpin_})
        blockOff(o);
}

void ChainConfigPanelWidget::setControlsEditable(bool editable)
{
    for (QWidget *w : QList<QWidget *>{samplerCombo_, schedulerCombo_,
                                       stepsSpin_, cfgSpin_, seedSpin_,
                                       widthSpin_, heightSpin_})
    {
        if (w != nullptr)
            w->setEnabled(editable);
    }
}

void ChainConfigPanelWidget::refresh()
{
    const Stage *s = currentStage();
    const bool hasSelection = (s != nullptr);

    setEmptyState(!hasSelection);

    if (!hasSelection)
    {
        if (headerTitle_ != nullptr)
            headerTitle_->setText(QStringLiteral("CONFIG"));
        if (headerSubtitle_ != nullptr)
            headerSubtitle_->setText(QStringLiteral("\u2014"));
        if (regenerateButton_ != nullptr)
            regenerateButton_->setStyleSheet(regenerateButtonStyle(false));
        return;
    }

    if (headerTitle_ != nullptr)
        headerTitle_->setText(stageKindUpper(s->kind) +
                              QStringLiteral(" CONFIG"));
    if (headerSubtitle_ != nullptr)
    {
        const QString prefix =
            QStringLiteral("Stage %1 \u2014 ").arg(s->index + 1);
        headerSubtitle_->setText(prefix + stageStatusSubtitle(s->status));
    }

    applyConfigToControls(s->config);

    // Lock disables editing; everything else allows it. Generating /
    // Queued probably shouldn't be edited mid-flight, but the engine's
    // canGenerate / lifecycle is the source of truth for "can I run a
    // new generation" — config edits during Generating are harmless
    // since they only apply on the next regenerate.
    const bool editable = (s->status != StageStatus::Locked);
    setControlsEditable(editable);

    // Regenerate is enabled only when we'd actually accept a new
    // generation. Mirrors ChainEngine::canGenerate's spirit for the
    // header: Draft / Completed / Failed all permit regenerate; Locked
    // does not; Generating/Queued shouldn't double-queue.
    const bool canRegen =
        s->status == StageStatus::Draft ||
        s->status == StageStatus::Completed ||
        s->status == StageStatus::Failed;
    if (regenerateButton_ != nullptr)
    {
        regenerateButton_->setEnabled(canRegen);
        regenerateButton_->setStyleSheet(regenerateButtonStyle(canRegen));
    }
}

void ChainConfigPanelWidget::onRegenerateClicked()
{
    if (selectedStageId_.isEmpty())
        return;
    emit regenerateRequested(selectedStageId_);
}

} // namespace spellvision::chain
