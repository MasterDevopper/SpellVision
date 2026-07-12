#include "chain/ChainConfigPanelWidget.h"

// --- CHAIN STUDIO PASS 9: model picker dependencies ---
#include "assets/AssetCatalogScanner.h"
#include "assets/CatalogPickerDialog.h"
#include "generation/OutputPathHelpers.h"

// --- CHAIN STUDIO PASS 9.5: LoRA stack dependencies ---
#include "assets/LoraStackController.h"

// --- PASS 7D1 FIXUP CLICKONLY INCLUDE ---
#include "widgets/ClickOnlyComboBox.h"
#include "ThemeManager.h"
#include "widgets/SectionCardWidgets.h"

#include <QAbstractSpinBox>
#include <QComboBox>
#include <QDoubleSpinBox>
#include <QFileInfo>
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

// --- CHAIN STUDIO PASS 9.5: engine <-> controller LoRA translators ---
// engine's LoraEntry and controller's LoraStackEntry have the same 4
// fields with the same types; this is a field-by-field memcpy in
// spirit. Kept as free functions so the type translation is local to
// this TU and doesn't pollute the chain or assets namespaces.
spellvision::assets::LoraStackEntry toLoraStackEntry(
    const spellvision::chain::LoraEntry &e)
{
    return {e.display, e.value, e.weight, e.enabled};
}

spellvision::chain::LoraEntry toEngineLoraEntry(
    const spellvision::assets::LoraStackEntry &e)
{
    return {e.display, e.value, e.weight, e.enabled};
}

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
    layout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Hairline));

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
    headerLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Hairline));

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

    // --- CHAIN STUDIO PASS 9: MODEL row ---
    // Layout: caption "MODEL" sits above a horizontal row that has the
    // selected-model label (multi-line: display name on top, path
    // underneath) on the left and the Browse button on the right.
    // The whole assembly is wrapped in modelRow_ so setEmptyState can
    // hide it alongside the other control rows.
    modelRow_ = new QWidget(bodyHolder_);
    {
        auto *modelRowLayout = new QVBoxLayout(modelRow_);
        modelRowLayout->setContentsMargins(0, 0, 0, 0);
        modelRowLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Hairline));

        auto *caption = new QLabel(QStringLiteral("Model"), modelRow_);
        caption->setStyleSheet(QStringLiteral(
            "QLabel { color: %1; font-size: 10px; font-weight: 700; "
            "letter-spacing: 0.6px; text-transform: uppercase; }"
        ).arg(tm.textMutedColor().name()));
        modelRowLayout->addWidget(caption);

        auto *modelInnerRow = new QWidget(modelRow_);
        auto *modelInnerLayout = new QHBoxLayout(modelInnerRow);
        modelInnerLayout->setContentsMargins(0, 0, 0, 0);
        modelInnerLayout->setSpacing(tm.spacing(ThemeManager::Spacing::Tight));

        selectedModelLabel_ = new QLabel(
            QStringLiteral("No checkpoint selected"),
            modelInnerRow);
        selectedModelLabel_->setWordWrap(true);
        selectedModelLabel_->setTextInteractionFlags(Qt::TextSelectableByMouse);
        selectedModelLabel_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
        selectedModelLabel_->setStyleSheet(QStringLiteral(
            "QLabel { color: %1; font-size: 11px; }"
        ).arg(tm.textPrimaryColor().name()));
        modelInnerLayout->addWidget(selectedModelLabel_, 1);

        modelBrowseButton_ = new QPushButton(QStringLiteral("Browse"), modelInnerRow);
        modelBrowseButton_->setCursor(Qt::PointingHandCursor);
        modelBrowseButton_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
        // Connect once at construction; the slot reads the current
        // stage's kind to choose the right catalog.
        connect(modelBrowseButton_, &QPushButton::clicked,
                this, &ChainConfigPanelWidget::onBrowseCheckpointClicked);
        modelInnerLayout->addWidget(modelBrowseButton_, 0);

        modelRowLayout->addWidget(modelInnerRow);
    }
    bodyLayout->addWidget(modelRow_);

    // --- CHAIN STUDIO PASS 9.5: LORAS section ---
    // Section structure:
    //   [ LORAS — caption ]
    //   [ summary label: "No LoRAs in stack" / "N in stack, M enabled" ]
    //   [ container — controller renders rows here, one per LoRA ]
    //   [ [Add LoRA]  [Clear Stack] ]
    // The whole thing wrapped in loraSection_ so refresh() can hide
    // it on stages that don't accept LoRAs (I2_3D / Audio).
    loraSection_ = new QWidget(bodyHolder_);
    {
        auto *sectionLayout = new QVBoxLayout(loraSection_);
        sectionLayout->setContentsMargins(0, 0, 0, 0);
        sectionLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Hairline));

        auto *caption = new QLabel(QStringLiteral("LoRAs"), loraSection_);
        caption->setStyleSheet(QStringLiteral(
            "QLabel { color: %1; font-size: 10px; font-weight: 700; "
            "letter-spacing: 0.6px; text-transform: uppercase; }"
        ).arg(tm.textMutedColor().name()));
        sectionLayout->addWidget(caption);

        loraSummaryLabel_ = new QLabel(QStringLiteral("No LoRAs in stack"),
                                       loraSection_);
        loraSummaryLabel_->setWordWrap(true);
        loraSummaryLabel_->setStyleSheet(QStringLiteral(
            "QLabel { color: %1; font-size: 11px; }"
        ).arg(tm.textSecondaryColor().name()));
        sectionLayout->addWidget(loraSummaryLabel_);

        loraContainer_ = new QWidget(loraSection_);
        loraContainerLayout_ = new QVBoxLayout(loraContainer_);
        loraContainerLayout_->setContentsMargins(0, 0, 0, 0);
        loraContainerLayout_->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Hairline));
        sectionLayout->addWidget(loraContainer_);

        auto *buttonRow = new QWidget(loraSection_);
        auto *buttonRowLayout = new QHBoxLayout(buttonRow);
        buttonRowLayout->setContentsMargins(0, 0, 0, 0);
        buttonRowLayout->setSpacing(tm.spacing(ThemeManager::Spacing::Tight));

        addLoraButton_ = new QPushButton(QStringLiteral("Add LoRA"), buttonRow);
        addLoraButton_->setCursor(Qt::PointingHandCursor);
        connect(addLoraButton_, &QPushButton::clicked,
                this, &ChainConfigPanelWidget::onAddLoraClicked);
        buttonRowLayout->addWidget(addLoraButton_);

        clearLoraButton_ = new QPushButton(QStringLiteral("Clear"), buttonRow);
        clearLoraButton_->setCursor(Qt::PointingHandCursor);
        connect(clearLoraButton_, &QPushButton::clicked,
                this, &ChainConfigPanelWidget::onClearLorasClicked);
        buttonRowLayout->addWidget(clearLoraButton_);
        buttonRowLayout->addStretch(1);

        sectionLayout->addWidget(buttonRow);
    }
    bodyLayout->addWidget(loraSection_);

    // Construct the controller and bind it to our cache vector +
    // section widgets. The controller owns per-row UI; we own the
    // cache vector lifetime and the Add/Clear button connections.
    loraController_ = new spellvision::assets::LoraStackController(this);
    spellvision::assets::LoraStackBindings loraBindings;
    loraBindings.container    = loraContainer_;
    loraBindings.layout       = loraContainerLayout_;
    loraBindings.summaryLabel = loraSummaryLabel_;
    loraBindings.clearButton  = clearLoraButton_;
    loraController_->bind(&loraStack_, loraBindings);
    loraController_->setDisplayResolver([this](const QString &value) -> QString {
        auto it = loraDisplayByValue_.constFind(value);
        if (it != loraDisplayByValue_.constEnd() && !it.value().isEmpty())
            return it.value();
        return QFileInfo(value).fileName();
    });
    loraController_->setChangedCallback([]() {
        // Cache vector has changed; controller already rebuilt rows
        // and refreshed summary label. Engine push happens only at
        // Regenerate (Option A: harvest-on-Regenerate, no live binding).
    });
    loraController_->setReplaceRequestedCallback([this](int index) {
        onReplaceLora(index);
    });

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
    // --- CHAIN STUDIO PASS 9: MODEL row visibility ---
    if (modelRow_ != nullptr)
        modelRow_->setVisible(!empty);
    // --- CHAIN STUDIO PASS 9.5: LORAS section visibility ---
    // setEmptyState only handles the "no stage selected" hide. The
    // per-kind hide (I2_3D / Audio) happens in refresh() since those
    // require currentStage() and a kind switch.
    if (loraSection_ != nullptr)
        loraSection_->setVisible(!empty);
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

    // --- CHAIN STUDIO PASS 9: copy model fields into per-stage cache ---
    // No signals to block here; these are plain QString members. The
    // updateModelRowFromCache() call refreshes the MODEL row label.
    lastPickedModelValue_    = config.model;
    lastPickedModelDisplay_  = config.modelDisplay;
    lastPickedModelFamily_   = config.modelFamily;
    lastPickedModelModality_ = config.modelModality;
    lastPickedModelRole_     = config.modelRole;
    lastPickedModelMetadata_ = config.selectedVideoStack;
    updateModelRowFromCache();

    // --- CHAIN STUDIO PASS 9.5: refresh LoRA cache from stage ---
    // rebuildLoraCacheFromStage() reads currentStage()->config.loras
    // (the same Chain we just synced via setChain or setSelectedStageId)
    // and translates engine LoraEntry -> controller LoraStackEntry,
    // then asks the controller to rebuild rows. Safe to call here
    // because currentStage() is now the same stage `config` came from.
    rebuildLoraCacheFromStage();
}

// --- CHAIN STUDIO PASS 8C.2: panel -> config harvest ---
// Mirror image of applyConfigToControls above. Reads the 7 controls,
// overlays them onto currentStage()->config, returns the result.
//
// Why start from currentStage()->config rather than a fresh default?
// Because StageConfig has ~20 fields (prompt, negativePrompt, model,
// modelDisplay, modelFamily, modelModality, modelRole,
// selectedVideoStack, workflow* paths, ltx* fields, loras, video
// sampler/scheduler, frames, fps, etc.) and the panel only exposes 7
// of them. Starting from the existing config preserves the other
// ~13 untouched -- they came from setStageConfig or from the engine's
// default seed, and the user has no UI to edit them.
// --- CHAIN STUDIO PASS 9: Browse handler ---
// Opens CatalogPickerDialog with the catalog matching the current
// stage's kind. Image stages get scanImageModelCatalog; video stages
// get scanVideoModelStackCatalog. I2_3D / Audio are not supported.
//
// On accept, the picker's selectedValue / selectedDisplay (plus the
// matching CatalogEntry's family / modality / role / metadata fields)
// land in the per-stage cache, and updateModelRowFromCache refreshes
// the MODEL row UI. The harvested config flows into the engine only
// when the user clicks Regenerate.
void ChainConfigPanelWidget::onBrowseCheckpointClicked()
{
    using spellvision::assets::CatalogEntry;
    using spellvision::assets::CatalogPickerDialog;
    using spellvision::assets::persistRecentSelection;
    using spellvision::assets::scanImageModelCatalog;
    using spellvision::assets::scanVideoModelStackCatalog;
    using spellvision::generation::chooseModelsRootPath;

    const Stage *s = currentStage();
    if (s == nullptr)
        return;

    const QString modelsRoot = chooseModelsRootPath();

    QVector<CatalogEntry> entries;
    QString dialogTitle;
    QString recentKey;

    switch (s->kind)
    {
        case StageKind::T2I:
        case StageKind::I2I:
            entries     = scanImageModelCatalog(modelsRoot);
            dialogTitle = QStringLiteral("Choose Checkpoint");
            recentKey   = QStringLiteral("chain_studio/recent_checkpoints");
            break;
        case StageKind::T2V:
        case StageKind::I2V:
            entries     = scanVideoModelStackCatalog(modelsRoot);
            dialogTitle = QStringLiteral("Choose Video Model Stack");
            recentKey   = QStringLiteral("chain_studio/recent_video_model_stacks");
            break;
        case StageKind::I2_3D:
        case StageKind::Audio:
            // Engine refuses to execute these (per isExecutable in
            // ChainModel.h). No catalog scan, no dialog -- the Browse
            // button click is a silent no-op for these kinds. Pass 10
            // polish can disable the button proactively when these
            // kinds are selected.
            return;
    }

    CatalogPickerDialog dialog(dialogTitle, entries, lastPickedModelValue_,
                               recentKey, this);
    if (dialog.exec() != QDialog::Accepted)
        return;

    const QString chosenValue   = dialog.selectedValue();
    const QString chosenDisplay = dialog.selectedDisplay();

    // Look up the matching CatalogEntry to capture family / modality /
    // role / metadata. (CatalogPickerDialog only returns value and
    // display; the rest we resolve here from the scan results.)
    QString family;
    QString modality;
    QString role;
    QJsonObject metadata;
    for (const CatalogEntry &entry : entries)
    {
        if (entry.value == chosenValue)
        {
            family   = entry.family;
            modality = entry.modality;
            role     = entry.role;
            metadata = entry.metadata;
            break;
        }
    }

    lastPickedModelValue_    = chosenValue;
    lastPickedModelDisplay_  = chosenDisplay;
    lastPickedModelFamily_   = family;
    lastPickedModelModality_ = modality;
    lastPickedModelRole_     = role;
    lastPickedModelMetadata_ = metadata;

    persistRecentSelection(recentKey, chosenValue);
    updateModelRowFromCache();
}

// --- CHAIN STUDIO PASS 9: refresh the MODEL row label ---
// Reads lastPickedModelValue_ / Display and rebuilds the label text.
// Mirrors ImageGenerationPage::refreshSelectedModelUi's format:
// "<display>\n<path>" if both are set, just the value if display is
// empty, or a placeholder string when nothing is selected.
void ChainConfigPanelWidget::updateModelRowFromCache()
{
    if (selectedModelLabel_ == nullptr)
        return;

    if (lastPickedModelValue_.trimmed().isEmpty())
    {
        selectedModelLabel_->setText(QStringLiteral("No checkpoint selected"));
        return;
    }

    if (lastPickedModelDisplay_.trimmed().isEmpty())
    {
        selectedModelLabel_->setText(lastPickedModelValue_);
        return;
    }

    selectedModelLabel_->setText(
        QStringLiteral("%1\n%2").arg(lastPickedModelDisplay_, lastPickedModelValue_));
}

StageConfig ChainConfigPanelWidget::harvestCurrentConfig() const
{
    const Stage *s = currentStage();
    StageConfig harvested = (s != nullptr) ? s->config : StageConfig{};

    if (samplerCombo_ != nullptr)
    {
        const QString val = samplerCombo_->currentData().toString();
        if (!val.isEmpty())
            harvested.imageSampler = val;
    }
    if (schedulerCombo_ != nullptr)
    {
        const QString val = schedulerCombo_->currentData().toString();
        if (!val.isEmpty())
            harvested.imageScheduler = val;
    }
    if (stepsSpin_ != nullptr)
        harvested.steps = stepsSpin_->value();
    if (cfgSpin_ != nullptr)
        harvested.cfg = cfgSpin_->value();
    if (seedSpin_ != nullptr)
        harvested.seed = seedSpin_->value();
    if (widthSpin_ != nullptr)
        harvested.width = widthSpin_->value();
    if (heightSpin_ != nullptr)
        harvested.height = heightSpin_->value();

    // --- CHAIN STUDIO PASS 9: harvest model fields from cache ---
    // These were populated by applyConfigToControls on stage switch
    // and by onBrowseCheckpointClicked on user pick. No null guards
    // needed since they are plain members, not pointer widgets.
    harvested.model              = lastPickedModelValue_;
    harvested.modelDisplay       = lastPickedModelDisplay_;
    harvested.modelFamily        = lastPickedModelFamily_;
    harvested.modelModality      = lastPickedModelModality_;
    harvested.modelRole          = lastPickedModelRole_;
    harvested.selectedVideoStack = lastPickedModelMetadata_;

    // --- CHAIN STUDIO PASS 9.5: harvest LoRA stack from cache ---
    // Translate controller LoraStackEntry -> engine LoraEntry. The
    // structs are field-identical; toEngineLoraEntry is a 1-liner.
    harvested.loras.clear();
    harvested.loras.reserve(loraStack_.size());
    for (const auto &e : loraStack_)
        harvested.loras.append(toEngineLoraEntry(e));

    return harvested;
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
    // --- CHAIN STUDIO PASS 9: Browse button follows lock state ---
    // Locked stages should not be re-pointed at a different model;
    // unlock the stage first.
    if (modelBrowseButton_ != nullptr)
        modelBrowseButton_->setEnabled(editable);
    // --- CHAIN STUDIO PASS 9.5: LoRA buttons follow lock state ---
    if (addLoraButton_ != nullptr)
        addLoraButton_->setEnabled(editable);
    if (clearLoraButton_ != nullptr)
        clearLoraButton_->setEnabled(editable);
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

    // --- CHAIN STUDIO PASS 9.5: per-kind LORAS visibility ---
    // LoRAs only meaningfully apply to image/video-producing stages.
    // UltraShape (3D-only) is its own future section. Audio gets
    // neither today.
    const bool kindAllowsLora =
        s->kind == StageKind::T2I ||
        s->kind == StageKind::I2I ||
        s->kind == StageKind::T2V ||
        s->kind == StageKind::I2V;
    if (loraSection_ != nullptr)
        loraSection_->setVisible(kindAllowsLora);

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

// --- CHAIN STUDIO PASS 9.5: Add LoRA handler ---
// Scan the loras/ subdirectory under the models root, populate the
// value->display map, open the CatalogPickerDialog, and on accept
// ask the controller to add the picked LoRA. The controller's
// changedCallback fires automatically; we don't need to do anything
// else here.
void ChainConfigPanelWidget::onAddLoraClicked()
{
    using spellvision::assets::CatalogEntry;
    using spellvision::assets::CatalogPickerDialog;
    using spellvision::assets::persistRecentSelection;
    using spellvision::assets::scanCatalog;
    using spellvision::generation::chooseModelsRootPath;

    if (loraController_ == nullptr)
        return;

    const QString modelsRoot = chooseModelsRootPath();
    const QVector<CatalogEntry> entries =
        scanCatalog(modelsRoot, QStringLiteral("loras"));

    // Refresh the display-resolver map so any already-stacked entries
    // (loaded from a saved StageConfig that we don't have full catalog
    // metadata for) can resolve their display names too.
    for (const CatalogEntry &entry : entries)
        loraDisplayByValue_.insert(entry.value, entry.display);

    const QString recentKey = QStringLiteral("chain_studio/recent_loras");
    CatalogPickerDialog dialog(QStringLiteral("Choose LoRA"), entries,
                               /*currentValue=*/QString(),
                               recentKey, this);
    if (dialog.exec() != QDialog::Accepted)
        return;

    const QString value   = dialog.selectedValue();
    const QString display = dialog.selectedDisplay();
    if (value.trimmed().isEmpty())
        return;

    loraController_->addOrUpdate(value, display);
    persistRecentSelection(recentKey, value);
}

// --- CHAIN STUDIO PASS 9.5: Clear handler ---
// Wraps controller->clear() so we have a stable connect target.
// (The Add/Clear button row's clearButton_ is also bound directly
// via the LoraStackBindings, but that path may try to clear via the
// bound clearButton_ raw click signal; routing through this method
// is the more explicit pattern.)
void ChainConfigPanelWidget::onClearLorasClicked()
{
    if (loraController_ != nullptr)
        loraController_->clear();
}

// --- CHAIN STUDIO PASS 9.5: Replace handler ---
// Fires when the user clicks an existing LoRA row in the stack. The
// controller passes the row index; we open the same picker dialog
// pre-selected to that row's current value, and on accept ask the
// controller to replace at that index.
void ChainConfigPanelWidget::onReplaceLora(int index)
{
    using spellvision::assets::CatalogEntry;
    using spellvision::assets::CatalogPickerDialog;
    using spellvision::assets::persistRecentSelection;
    using spellvision::assets::scanCatalog;
    using spellvision::generation::chooseModelsRootPath;

    if (loraController_ == nullptr)
        return;
    if (index < 0 || index >= loraStack_.size())
        return;

    const QString modelsRoot = chooseModelsRootPath();
    const QVector<CatalogEntry> entries =
        scanCatalog(modelsRoot, QStringLiteral("loras"));

    for (const CatalogEntry &entry : entries)
        loraDisplayByValue_.insert(entry.value, entry.display);

    const QString currentValue = loraStack_.at(index).value;
    const QString recentKey = QStringLiteral("chain_studio/recent_loras");
    CatalogPickerDialog dialog(QStringLiteral("Replace LoRA"), entries,
                               currentValue, recentKey, this);
    if (dialog.exec() != QDialog::Accepted)
        return;

    const QString value   = dialog.selectedValue();
    const QString display = dialog.selectedDisplay();
    if (value.trimmed().isEmpty())
        return;

    loraController_->replaceAt(index, value, display);
    persistRecentSelection(recentKey, value);
}

// --- CHAIN STUDIO PASS 9.5: Rebuild LoRA cache from current stage ---
// Called from applyConfigToControls. Translates currentStage()->
// config.loras (engine LoraEntry vector) into loraStack_ (controller
// LoraStackEntry vector), then asks the controller to rebuild rows.
//
// Also refreshes loraDisplayByValue_ by scanning the catalog, so any
// LoRAs loaded from a saved StageConfig (where we may not have a
// display name) can still resolve to a readable label.
void ChainConfigPanelWidget::rebuildLoraCacheFromStage()
{
    using spellvision::assets::CatalogEntry;
    using spellvision::assets::scanCatalog;
    using spellvision::generation::chooseModelsRootPath;

    if (loraController_ == nullptr)
        return;

    loraStack_.clear();

    const Stage *s = currentStage();
    if (s != nullptr)
    {
        loraStack_.reserve(s->config.loras.size());
        for (const LoraEntry &e : s->config.loras)
            loraStack_.append(toLoraStackEntry(e));
    }

    // Lazy catalog scan to backfill displays. Cheap; well under 100ms
    // on typical SSDs. Pass 11+ may cache this if profiling complains.
    const QVector<CatalogEntry> entries =
        scanCatalog(chooseModelsRootPath(), QStringLiteral("loras"));
    for (const CatalogEntry &entry : entries)
        loraDisplayByValue_.insert(entry.value, entry.display);

    loraController_->rebuild();
}

} // namespace spellvision::chain
