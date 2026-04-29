#include "ImageGenerationPage.h"

#include "ThemeManager.h"
#include "preview/MediaPreviewController.h"
#include "preview/ImagePreviewController.h"
#include "generation/GenerationRequestBuilder.h"
#include "generation/VideoReadinessPresenter.h"
#include "generation/GenerationModeState.h"
#include "generation/GenerationResultRouter.h"
#include "generation/GenerationStatusController.h"
#include "generation/OutputPathHelpers.h"
#include "workers/WorkerCommandRunner.h"
#include "assets/ModelStackState.h"
#include "assets/LoraStackController.h"
#include "assets/CatalogPickerDialog.h"
#include "assets/AssetCatalogScanner.h"
#include "widgets/DropTargetFrame.h"
#include "widgets/ClickOnlyComboBox.h"
#include "widgets/SectionCardWidgets.h"


#include <QAbstractItemView>
#include <QAbstractSpinBox>
#include <QComboBox>
#include <QListWidget>
#include <QDialogButtonBox>
#include <QDialog>
#include <QCheckBox>
#include <QCompleter>
#include <QDateTime>
#include <QDir>
#include <QDirIterator>
#include <QDoubleSpinBox>
#include <QCheckBox>
#include <QDialog>
#include <QDialogButtonBox>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QFrame>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QJsonObject>
#include <QJsonDocument>
#include <QJsonArray>
#include <QLabel>
#include <QListWidget>
#include <QLineEdit>
#include <QMessageBox>
#include <QMediaPlayer>
#include <QAudioOutput>
#include <QVideoWidget>
#include <QPixmap>
#include <QPushButton>
#include <QResizeEvent>
#include <QScrollArea>
#include <QScrollBar>
#include <QSettings>
#include <QSet>
#include <QSizePolicy>
#include <QSignalBlocker>
#include <QSlider>
#include <QSpinBox>
#include <QStandardPaths>
#include <QSplitter>
#include <QStackedWidget>
#include <QStyle>
#include <QTextEdit>
#include <QToolButton>
#include <QTimer>
#include <QVBoxLayout>

#include <algorithm>
#include <functional>

namespace
{
using spellvision::assets::CatalogEntry;
using spellvision::assets::compactCatalogDisplay;
using spellvision::assets::findBestCompanionPath;
using spellvision::assets::humanImageFamily;
using spellvision::assets::humanVideoFamily;
using spellvision::assets::inferImageFamilyFromText;
using spellvision::assets::inferVideoFamilyFromText;
using spellvision::assets::looksLikeWanHighNoisePath;
using spellvision::assets::looksLikeWanLowNoisePath;
using spellvision::assets::modelNameFilters;
using spellvision::assets::normalizedPathText;
using spellvision::assets::resolveCatalogValueByCandidates;
using spellvision::assets::scanCatalog;
using spellvision::assets::scanDiffusersVideoFolders;
using spellvision::assets::scanImageModelCatalog;
using spellvision::assets::scanVideoModelStackCatalog;
using spellvision::assets::shortDisplayFromValue;
using spellvision::assets::CatalogPickerDialog;
using spellvision::assets::persistRecentSelection;
using spellvision::widgets::ClickOnlyComboBox;
using spellvision::widgets::DropTargetFrame;
using spellvision::widgets::createCard;
using spellvision::widgets::createSectionBody;
using spellvision::widgets::createSectionTitle;
using spellvision::widgets::repolishWidget;

using SpellGenerationMode = spellvision::generation::GenerationMode;
using spellvision::assets::ModelStackState;
using spellvision::generation::chooseModelsRootPath;
using spellvision::generation::chooseComfyOutputPath;
using spellvision::generation::isImageAssetPath;
using spellvision::generation::isVideoAssetPath;
using spellvision::workers::WorkerCommandRunner;

SpellGenerationMode toGenerationMode(ImageGenerationPage::Mode mode)
{
    switch (mode)
    {
    case ImageGenerationPage::Mode::TextToImage:
        return SpellGenerationMode::TextToImage;
    case ImageGenerationPage::Mode::ImageToImage:
        return SpellGenerationMode::ImageToImage;
    case ImageGenerationPage::Mode::TextToVideo:
        return SpellGenerationMode::TextToVideo;
    case ImageGenerationPage::Mode::ImageToVideo:
        return SpellGenerationMode::ImageToVideo;
    }
    return SpellGenerationMode::TextToImage;
}



QString comboStoredValue(const QComboBox *combo)
{
    if (!combo)
        return QString();

    const QString dataValue = combo->currentData(Qt::UserRole).toString().trimmed();
    if (!dataValue.isEmpty())
        return dataValue;

    return combo->currentText().trimmed();
}

QString comboDisplayValue(const QComboBox *combo)
{
    return combo ? combo->currentText().trimmed() : QString();
}

QString normalizedVideoStackModeToken(const QString &value)
{
    const QString token = value.trimmed().toLower();
    if (token.isEmpty() || token == QStringLiteral("auto") || token == QStringLiteral("auto_detect"))
        return QStringLiteral("auto");
    if (token.contains(QStringLiteral("wan")) || token.contains(QStringLiteral("dual")) || token.contains(QStringLiteral("high_noise")) || token.contains(QStringLiteral("low_noise")))
        return QStringLiteral("wan_dual_noise");
    if (token.contains(QStringLiteral("single")))
        return QStringLiteral("single_model");
    return token;
}

QString serializeLoraStack(const QVector<ImageGenerationPage::LoraStackEntry> &stack)
{
    QJsonArray array;
    for (const auto &entry : stack)
    {
        QJsonObject obj;
        obj.insert(QStringLiteral("display"), entry.display);
        obj.insert(QStringLiteral("value"), entry.value);
        obj.insert(QStringLiteral("weight"), entry.weight);
        obj.insert(QStringLiteral("enabled"), entry.enabled);
        array.append(obj);
    }
    return QString::fromUtf8(QJsonDocument(array).toJson(QJsonDocument::Compact));
}

QVector<ImageGenerationPage::LoraStackEntry> deserializeLoraStack(const QString &json)
{
    QVector<ImageGenerationPage::LoraStackEntry> stack;
    const QJsonDocument doc = QJsonDocument::fromJson(json.toUtf8());
    if (!doc.isArray())
        return stack;

    for (const QJsonValue &value : doc.array())
    {
        if (!value.isObject())
            continue;
        const QJsonObject obj = value.toObject();
        ImageGenerationPage::LoraStackEntry entry;
        entry.display = obj.value(QStringLiteral("display")).toString().trimmed();
        entry.value = obj.value(QStringLiteral("value")).toString().trimmed();
        entry.weight = obj.value(QStringLiteral("weight")).toDouble(1.0);
        entry.enabled = obj.value(QStringLiteral("enabled")).toBool(true);
        if (!entry.value.isEmpty())
            stack.push_back(entry);
    }

    return stack;
}
void populateComboFromCatalog(QComboBox *combo,
                              const QVector<CatalogEntry> &entries,
                              const QStringList &fallbackItems = {})
{
    if (!combo)
        return;

    const QString priorValue = comboStoredValue(combo);
    const QSignalBlocker blocker(combo);
    combo->clear();

    for (const CatalogEntry &entry : entries)
        combo->addItem(entry.display, entry.value);

    if (combo->count() == 0)
    {
        for (const QString &fallback : fallbackItems)
            combo->addItem(fallback, fallback);
    }

    if (!priorValue.isEmpty())
    {
        for (int index = 0; index < combo->count(); ++index)
        {
            if (combo->itemData(index, Qt::UserRole).toString().compare(priorValue, Qt::CaseInsensitive) == 0 ||
                combo->itemText(index).compare(priorValue, Qt::CaseInsensitive) == 0)
            {
                combo->setCurrentIndex(index);
                return;
            }
        }

        if (combo->isEditable())
            combo->setEditText(priorValue);
    }
    else if (combo->count() > 0)
    {
        combo->setCurrentIndex(0);
    }
}

bool selectComboByContains(QComboBox *combo, const QStringList &needles)
{
    if (!combo)
        return false;

    for (int index = 0; index < combo->count(); ++index)
    {
        const QString haystack = (combo->itemText(index) + QStringLiteral(" ") + combo->itemData(index, Qt::UserRole).toString()).toLower();
        for (const QString &needle : needles)
        {
            if (!needle.trimmed().isEmpty() && haystack.contains(needle.toLower()))
            {
                combo->setCurrentIndex(index);
                return true;
            }
        }
    }

    return false;
}

void configureComboBox(QComboBox *combo)
{
    if (!combo)
        return;

    combo->setFocusPolicy(Qt::StrongFocus);
    combo->setMaxVisibleItems(18);
    combo->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon);
    combo->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

    if (combo->view())
    {
        combo->view()->setVerticalScrollMode(QAbstractItemView::ScrollPerPixel);
        combo->view()->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
        combo->view()->setTextElideMode(Qt::ElideMiddle);
    }
}

void configureSpinBox(QSpinBox *spin)
{
    if (!spin)
        return;

    spin->setAccelerated(true);
    spin->setKeyboardTracking(false);
    spin->setButtonSymbols(QAbstractSpinBox::UpDownArrows);
    spin->setAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    spin->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
}

void configureDoubleSpinBox(QDoubleSpinBox *spin)
{
    if (!spin)
        return;

    spin->setAccelerated(true);
    spin->setKeyboardTracking(false);
    spin->setButtonSymbols(QAbstractSpinBox::UpDownArrows);
    spin->setAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    spin->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
}


} // namespace

ImageGenerationPage::ImageGenerationPage(Mode mode, QWidget *parent)
    : QWidget(parent),
      mode_(mode)
{
    uiRefreshTimer_ = new QTimer(this);
    uiRefreshTimer_->setSingleShot(true);
    connect(uiRefreshTimer_, &QTimer::timeout, this, [this]() {
        updateAssetIntelligenceUi();
        refreshPreview();
    });

    previewResizeTimer_ = new QTimer(this);
    previewResizeTimer_->setSingleShot(true);
    connect(previewResizeTimer_, &QTimer::timeout, this, [this]() { refreshPreview(); });

    buildUi();
    applyTheme();
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, [this]() { applyTheme(); });
    reloadCatalogs();
    restoreSnapshot();
    updateAdaptiveLayout();
    updatePrimaryActionAvailability();
    schedulePreviewRefresh(busy_ ? 0 : 30);

    QTimer::singleShot(0, this, [this]() {
        if (leftScrollArea_ && leftScrollArea_->verticalScrollBar())
            leftScrollArea_->verticalScrollBar()->setValue(0);
    });
}

QJsonObject ImageGenerationPage::buildRequestPayload() const
{
    using spellvision::generation::GenerationRequestBuilder;
    using spellvision::generation::GenerationRequestDraft;
    using spellvision::generation::LoraRequestEntry;

    GenerationRequestDraft draft;
    draft.mode = modeKey();
    draft.prompt = promptEdit_ ? promptEdit_->toPlainText().trimmed() : QString();
    draft.negativePrompt = negativePromptEdit_ ? negativePromptEdit_->toPlainText().trimmed() : QString();
    draft.preset = currentComboValue(presetCombo_);

    draft.model = selectedModelValue();
    draft.modelDisplay = selectedModelDisplay_;
    draft.modelFamily = modelFamilyByValue_.value(selectedModelPath_);
    draft.modelModality = modelModalityByValue_.value(selectedModelPath_, isVideoMode() ? QStringLiteral("video") : QStringLiteral("image"));
    draft.modelRole = modelRoleByValue_.value(selectedModelPath_);
    draft.selectedVideoStack = selectedVideoStackForPayload();

    draft.workflowProfile = currentComboValue(workflowCombo_);
    draft.workflowDraftSource = workflowDraftSource_;
    draft.workflowProfilePath = workflowDraftProfilePath_;
    draft.workflowPath = workflowDraftWorkflowPath_;
    draft.compiledPromptPath = workflowDraftCompiledPromptPath_;
    draft.workflowBackend = workflowDraftBackend_;
    draft.workflowMediaType = workflowDraftMediaType_;

    for (const LoraStackEntry &entry : loraStack_)
    {
        LoraRequestEntry item;
        item.display = entry.display;
        item.value = entry.value;
        item.weight = entry.weight;
        item.enabled = entry.enabled;
        draft.loras.append(item);
    }
    draft.loraStackSummary = loraStackSummaryLabel_ ? loraStackSummaryLabel_->text() : QString();

    draft.imageSampler = currentComboValue(samplerCombo_);
    draft.imageScheduler = currentComboValue(schedulerCombo_);
    draft.videoSampler = videoSamplerCombo_ ? currentComboValue(videoSamplerCombo_) : QStringLiteral("auto");
    draft.videoScheduler = videoSchedulerCombo_ ? currentComboValue(videoSchedulerCombo_) : QStringLiteral("auto");

    draft.steps = stepsSpin_ ? stepsSpin_->value() : 0;
    draft.cfg = cfgSpin_ ? cfgSpin_->value() : 0.0;
    draft.seed = seedSpin_ ? seedSpin_->value() : 0;
    draft.width = widthSpin_ ? widthSpin_->value() : 0;
    draft.height = heightSpin_ ? heightSpin_->value() : 0;

    draft.isVideoMode = isVideoMode();
    if (draft.isVideoMode)
    {
        draft.frames = frameCountSpin_ ? frameCountSpin_->value() : 81;
        draft.fps = fpsSpin_ ? fpsSpin_->value() : 16;
        draft.videoStackMode = effectiveVideoStackMode();
        draft.wanSplit = wanSplitCombo_ ? currentComboValue(wanSplitCombo_) : QStringLiteral("auto");
        draft.highSteps = highNoiseStepsSpin_ ? highNoiseStepsSpin_->value() : 14;
        draft.lowSteps = lowNoiseStepsSpin_ ? lowNoiseStepsSpin_->value() : 14;
        draft.splitStep = splitStepSpin_ ? splitStepSpin_->value() : 14;
        draft.highNoiseShift = highNoiseShiftSpin_ ? highNoiseShiftSpin_->value() : 5.0;
        draft.lowNoiseShift = lowNoiseShiftSpin_ ? lowNoiseShiftSpin_->value() : 5.0;
        draft.enableVaeTiling = enableVaeTilingCheck_ && enableVaeTilingCheck_->isChecked();
    }

    draft.batchCount = batchSpin_ ? batchSpin_->value() : 1;
    draft.outputPrefix = outputPrefixEdit_ ? outputPrefixEdit_->text().trimmed() : QString();
    draft.outputFolder = outputFolderLabel_ ? outputFolderLabel_->text() : QString();
    draft.modelsRoot = modelsRootDir_;

    draft.isImageInputMode = isImageInputMode();
    if (draft.isImageInputMode)
    {
        draft.inputImage = inputImageEdit_ ? inputImageEdit_->text().trimmed() : QString();
        draft.denoiseStrength = denoiseSpin_ ? denoiseSpin_->value() : 0.0;
    }

    return GenerationRequestBuilder::build(draft);
}
void ImageGenerationPage::applyTheme()
{
    setStyleSheet(ThemeManager::instance().imageGenerationStyleSheet());
}


void ImageGenerationPage::buildUi()
{
    setObjectName(QStringLiteral("ImageGenerationPage"));
    setAcceptDrops(isImageInputMode());

    auto *root = new QVBoxLayout(this);
    root->setContentsMargins(10, 8, 10, 10);
    root->setSpacing(10);

    contentSplitter_ = new QSplitter(Qt::Horizontal, this);
    contentSplitter_->setChildrenCollapsible(false);
    contentSplitter_->setOpaqueResize(false);
    contentSplitter_->setHandleWidth(8);

    leftScrollArea_ = new QScrollArea(contentSplitter_);
    leftScrollArea_->setObjectName(QStringLiteral("LeftRailScrollArea"));
    leftScrollArea_->setWidgetResizable(true);
    leftScrollArea_->setFrameShape(QFrame::NoFrame);
    leftScrollArea_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    leftScrollArea_->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    leftScrollArea_->setMinimumWidth(360);
    leftScrollArea_->setMaximumWidth(470);
    leftScrollArea_->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Expanding);

    auto *leftContainer = new QWidget(leftScrollArea_);
    auto *leftLayout = new QVBoxLayout(leftContainer);
    leftLayout->setContentsMargins(0, 0, 4, 0);
    leftLayout->setSpacing(8);
    leftLayout->setSizeConstraint(QLayout::SetMinAndMaxSize);

    auto *promptCard = createCard(QStringLiteral("PromptCard"));
    auto *promptLayout = new QVBoxLayout(promptCard);
    promptLayout->setContentsMargins(12, 12, 12, 12);
    promptLayout->setSpacing(8);

    presetCombo_ = new ClickOnlyComboBox(promptCard);
    presetCombo_->setEditable(false);
    presetCombo_->addItem(QStringLiteral("Balanced"), QStringLiteral("Balanced"));
    presetCombo_->addItem(QStringLiteral("Portrait Detail"), QStringLiteral("Portrait Detail"));
    presetCombo_->addItem(QStringLiteral("Stylized Concept"), QStringLiteral("Stylized Concept"));
    presetCombo_->addItem(QStringLiteral("Upscale / Repair"), QStringLiteral("Upscale / Repair"));
    presetCombo_->addItem(QStringLiteral("Custom"), QStringLiteral("Custom"));
    configureComboBox(presetCombo_);

    auto *presetRow = new QHBoxLayout;
    presetRow->setContentsMargins(0, 0, 0, 0);
    presetRow->setSpacing(8);
    presetRow->addWidget(createSectionTitle(QStringLiteral("Preset"), promptCard));
    presetRow->addStretch(1);
    auto *applyPresetButton = new QPushButton(QStringLiteral("Apply Preset"), promptCard);
    applyPresetButton->setObjectName(QStringLiteral("SecondaryActionButton"));
    applyPresetButton->setMinimumWidth(104);
    connect(applyPresetButton, &QPushButton::clicked, this, [this]() { applyPreset(presetCombo_->currentText()); });
    presetRow->addWidget(applyPresetButton);

    promptEdit_ = new QTextEdit(promptCard);
    promptEdit_->setPlaceholderText(QStringLiteral("Describe the subject, framing, lighting, materials, style cues, and production notes here…"));
    promptEdit_->setMinimumHeight(isVideoMode() ? 126 : 148);
    promptEdit_->setMaximumHeight(isVideoMode() ? 144 : 166);
    promptEdit_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

    negativePromptEdit_ = new QTextEdit(promptCard);
    negativePromptEdit_->setPlaceholderText(QStringLiteral("Low quality, blurry, extra fingers, watermark, text, duplicate limbs…"));
    negativePromptEdit_->setMinimumHeight(82);
    negativePromptEdit_->setMaximumHeight(100);
    negativePromptEdit_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

    promptLayout->addLayout(presetRow);
    promptLayout->addWidget(presetCombo_);
    promptLayout->addWidget(createSectionTitle(QStringLiteral("Prompt"), promptCard));
    promptLayout->addWidget(promptEdit_);
    promptLayout->addWidget(createSectionTitle(QStringLiteral("Negative Prompt"), promptCard));
    promptLayout->addWidget(negativePromptEdit_);
    promptCard->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Maximum);
    leftLayout->addWidget(promptCard);

    inputCard_ = createCard(QStringLiteral("InputCard"));
    auto *inputLayout = new QVBoxLayout(inputCard_);
    inputLayout->setContentsMargins(12, 12, 12, 12);
    inputLayout->setSpacing(8);
    inputLayout->addWidget(createSectionTitle(isVideoMode() ? QStringLiteral("Input Keyframe") : QStringLiteral("Input Image"), inputCard_));

    auto *dropFrame = new DropTargetFrame(inputCard_);
    dropFrame->setObjectName(QStringLiteral("InputDropCard"));
    auto *dropLayout = new QVBoxLayout(dropFrame);
    dropLayout->setContentsMargins(10, 10, 10, 10);
    dropLayout->setSpacing(6);

    inputDropLabel_ = new QLabel(
        isVideoMode() ? QStringLiteral("Drop a still image or keyframe here, or click Browse to select one.")
                      : QStringLiteral("Drop an image here or click Browse to select a source image."),
        dropFrame);
    inputDropLabel_->setObjectName(QStringLiteral("ImageGenHint"));
    inputDropLabel_->setWordWrap(true);
    dropLayout->addWidget(inputDropLabel_);

    inputImageEdit_ = new QLineEdit(inputCard_);
    inputImageEdit_->setPlaceholderText(isVideoMode() ? QStringLiteral("No keyframe selected") : QStringLiteral("No input image selected"));

    auto *inputButtons = new QHBoxLayout;
    inputButtons->setContentsMargins(0, 0, 0, 0);
    inputButtons->setSpacing(8);
    auto *browseButton = new QPushButton(QStringLiteral("Browse"), inputCard_);
    browseButton->setObjectName(QStringLiteral("SecondaryActionButton"));
    auto *clearInputButton = new QPushButton(QStringLiteral("Clear"), inputCard_);
    clearInputButton->setObjectName(QStringLiteral("TertiaryActionButton"));
    connect(browseButton, &QPushButton::clicked, this, [this]() {
        const QString filePath = QFileDialog::getOpenFileName(this,
                                                              QStringLiteral("Choose input image"),
                                                              QString(),
                                                              QStringLiteral("Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)"));
        if (!filePath.isEmpty())
            setInputImagePath(filePath);
    });
    connect(clearInputButton, &QPushButton::clicked, this, [this]() { setInputImagePath(QString()); });
    inputButtons->addWidget(browseButton);
    inputButtons->addWidget(clearInputButton);
    inputButtons->addStretch(1);

    dropFrame->onFileDropped = [this](const QString &path) { setInputImagePath(path); };

    inputLayout->addWidget(dropFrame);
    inputLayout->addWidget(inputImageEdit_);
    inputLayout->addLayout(inputButtons);

    inputCard_->setVisible(isImageInputMode());
    leftLayout->addWidget(inputCard_);

    auto *quickControlsCard = createCard(QStringLiteral("QuickControlsCard"));
    auto *quickControlsLayout = new QVBoxLayout(quickControlsCard);
    quickControlsLayout->setContentsMargins(12, 12, 12, 12);
    quickControlsLayout->setSpacing(8);
    quickControlsLayout->addWidget(createSectionTitle(QStringLiteral("Generation Quick Controls"), quickControlsCard));
    auto *quickControlsHint = createSectionBody(QStringLiteral("Core generation controls stay here."), quickControlsCard);
    quickControlsHint->setMaximumHeight(22);
    quickControlsLayout->addWidget(quickControlsHint);
    leftLayout->addWidget(quickControlsCard);

    auto *outputQueueCard = createCard(QStringLiteral("OutputQueueCard"));
    auto *outputQueueLayout = new QVBoxLayout(outputQueueCard);
    outputQueueLayout->setContentsMargins(12, 12, 12, 12);
    outputQueueLayout->setSpacing(8);
    auto *outputQueueHeader = new QWidget(outputQueueCard);
    auto *outputQueueHeaderLayout = new QHBoxLayout(outputQueueHeader);
    outputQueueHeaderLayout->setContentsMargins(0, 0, 0, 0);
    outputQueueHeaderLayout->setSpacing(8);
    outputQueueHeaderLayout->addWidget(createSectionTitle(QStringLiteral("Output / Queue"), outputQueueCard), 1);
    outputQueueToggleButton_ = new QToolButton(outputQueueCard);
    outputQueueToggleButton_->setObjectName(QStringLiteral("InspectorSectionToggle"));
    outputQueueToggleButton_->setToolButtonStyle(Qt::ToolButtonTextOnly);
    outputQueueToggleButton_->setText(QStringLiteral("Open"));
    outputQueueToggleButton_->setMinimumWidth(72);
    outputQueueToggleButton_->setMinimumHeight(26);
    outputQueueToggleButton_->setFixedHeight(26);
    outputQueueToggleButton_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
    outputQueueToggleButton_->setVisible(false);
    outputQueueHeaderLayout->addWidget(outputQueueToggleButton_, 0, Qt::AlignRight | Qt::AlignVCenter);
    outputQueueLayout->addWidget(outputQueueHeader);
    connect(outputQueueToggleButton_, &QToolButton::clicked, this, [this](bool) {
        outputQueueForceOpen_ = !outputQueueForceOpen_;

        updateAdaptiveLayout();

        if (!outputQueueForceOpen_ || !leftScrollArea_)
            return;

        QTimer::singleShot(0, this, [this]() {
            QWidget *card = findChild<QWidget *>(QStringLiteral("OutputQueueCard"));
            if (!card || !leftScrollArea_)
                return;
            leftScrollArea_->ensureWidgetVisible(card, 4, 8);
        });
    });
    leftLayout->addWidget(outputQueueCard);

    auto *advancedCard = createCard(QStringLiteral("AdvancedCard"));
    auto *advancedLayout = new QVBoxLayout(advancedCard);
    advancedLayout->setContentsMargins(12, 12, 12, 12);
    advancedLayout->setSpacing(8);
    auto *advancedHeader = new QWidget(advancedCard);
    auto *advancedHeaderLayout = new QHBoxLayout(advancedHeader);
    advancedHeaderLayout->setContentsMargins(0, 0, 0, 0);
    advancedHeaderLayout->setSpacing(8);
    advancedHeaderLayout->addWidget(createSectionTitle(QStringLiteral("Advanced"), advancedCard), 1);
    advancedToggleButton_ = new QToolButton(advancedCard);
    advancedToggleButton_->setObjectName(QStringLiteral("InspectorSectionToggle"));
    advancedToggleButton_->setToolButtonStyle(Qt::ToolButtonTextOnly);
    advancedToggleButton_->setText(QStringLiteral("Open"));
    advancedToggleButton_->setMinimumWidth(72);
    advancedToggleButton_->setMinimumHeight(26);
    advancedToggleButton_->setFixedHeight(26);
    advancedToggleButton_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
    advancedHeaderLayout->addWidget(advancedToggleButton_, 0, Qt::AlignRight | Qt::AlignVCenter);
    advancedLayout->addWidget(advancedHeader);
    connect(advancedToggleButton_, &QToolButton::clicked, this, [this](bool) {
        advancedForceOpen_ = !advancedForceOpen_;

        updateAdaptiveLayout();

        if (!advancedForceOpen_ || !leftScrollArea_)
            return;

        QTimer::singleShot(0, this, [this]() {
            QWidget *card = findChild<QWidget *>(QStringLiteral("AdvancedCard"));
            if (!card || !leftScrollArea_)
                return;
            leftScrollArea_->ensureWidgetVisible(card, 4, 8);
        });
    });
    auto *advancedHint = createSectionBody(QStringLiteral("Mode-specific controls."), advancedCard);
    advancedHint->setObjectName(QStringLiteral("AdvancedBodyHint"));
    advancedHint->setMaximumHeight(24);
    advancedLayout->addWidget(advancedHint);
    leftLayout->addWidget(advancedCard);
    leftLayout->addStretch(1);

    leftScrollArea_->setWidget(leftContainer);

    centerContainer_ = new QWidget(contentSplitter_);
    auto *centerLayout = new QVBoxLayout(centerContainer_);
    centerLayout->setContentsMargins(0, 0, 0, 0);
    centerLayout->setSpacing(0);

    auto *canvasCard = createCard(QStringLiteral("CanvasCard"));
    auto *canvasLayout = new QVBoxLayout(canvasCard);
    canvasLayout->setContentsMargins(16, 14, 16, 14);
    canvasLayout->setSpacing(8);

    previewStack_ = new QStackedWidget(canvasCard);
    previewStack_->setObjectName(QStringLiteral("PreviewStack"));
    previewStack_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);

    previewImagePage_ = new QWidget(previewStack_);
    auto *previewImageLayout = new QVBoxLayout(previewImagePage_);
    previewImageLayout->setContentsMargins(0, 0, 0, 0);
    previewImageLayout->setSpacing(0);

    previewLabel_ = new QLabel(previewImagePage_);
    previewLabel_->setObjectName(QStringLiteral("PreviewSurface"));
    previewLabel_->setProperty("emptyState", true);
    previewLabel_->setAlignment(Qt::AlignCenter);
    previewLabel_->setMinimumSize(0, 0);
    previewLabel_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    previewLabel_->setWordWrap(true);
    previewImageLayout->addWidget(previewLabel_, 1);

    previewVideoPage_ = new QWidget(previewStack_);
    auto *previewVideoLayout = new QVBoxLayout(previewVideoPage_);
    previewVideoLayout->setContentsMargins(0, 0, 0, 0);
    previewVideoLayout->setSpacing(6);

    previewVideoWidget_ = new QVideoWidget(previewVideoPage_);
    previewVideoWidget_->setObjectName(QStringLiteral("PreviewVideoSurface"));
    previewVideoWidget_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    previewVideoWidget_->setMinimumSize(0, 0);

    previewVideoCaptionLabel_ = new QLabel(previewVideoPage_);
    previewVideoCaptionLabel_->setObjectName(QStringLiteral("PreviewVideoCaption"));
    previewVideoCaptionLabel_->setWordWrap(true);
    previewVideoCaptionLabel_->setAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    previewVideoCaptionLabel_->setVisible(false);

    previewVideoTransportBar_ = new QWidget(previewVideoPage_);
    previewVideoTransportBar_->setObjectName(QStringLiteral("PreviewVideoTransportBar"));
    auto *previewTransportLayout = new QHBoxLayout(previewVideoTransportBar_);
    previewTransportLayout->setContentsMargins(8, 6, 8, 6);
    previewTransportLayout->setSpacing(8);

    previewRestartButton_ = new QPushButton(QStringLiteral("⏮"), previewVideoTransportBar_);
    previewRestartButton_->setObjectName(QStringLiteral("SecondaryActionButton"));
    previewRestartButton_->setToolTip(QStringLiteral("Restart from the beginning"));

    previewStepBackButton_ = new QPushButton(QStringLiteral("◀ 1f"), previewVideoTransportBar_);
    previewStepBackButton_->setObjectName(QStringLiteral("SecondaryActionButton"));
    previewStepBackButton_->setToolTip(QStringLiteral("Step back one frame"));

    previewPlayPauseButton_ = new QPushButton(QStringLiteral("Play"), previewVideoTransportBar_);
    previewPlayPauseButton_->setObjectName(QStringLiteral("PrimaryActionButton"));
    previewPlayPauseButton_->setToolTip(QStringLiteral("Play / Pause"));

    previewStepForwardButton_ = new QPushButton(QStringLiteral("1f ▶"), previewVideoTransportBar_);
    previewStepForwardButton_->setObjectName(QStringLiteral("SecondaryActionButton"));
    previewStepForwardButton_->setToolTip(QStringLiteral("Step forward one frame"));

    previewStopButton_ = new QPushButton(QStringLiteral("Stop"), previewVideoTransportBar_);
    previewStopButton_->setObjectName(QStringLiteral("SecondaryActionButton"));
    previewStopButton_->setToolTip(QStringLiteral("Stop and return to the first frame"));

    previewSeekSlider_ = new QSlider(Qt::Horizontal, previewVideoTransportBar_);
    previewSeekSlider_->setObjectName(QStringLiteral("PreviewVideoSeekSlider"));
    previewSeekSlider_->setRange(0, 0);
    previewSeekSlider_->setSingleStep(1000);
    previewSeekSlider_->setPageStep(5000);
    previewSeekSlider_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

    previewTimeLabel_ = new QLabel(QStringLiteral("00:00 / 00:00"), previewVideoTransportBar_);
    previewTimeLabel_->setObjectName(QStringLiteral("PreviewVideoTimeLabel"));
    previewTimeLabel_->setMinimumWidth(112);
    previewTimeLabel_->setAlignment(Qt::AlignRight | Qt::AlignVCenter);

    previewSpeedCombo_ = new QComboBox(previewVideoTransportBar_);
    previewSpeedCombo_->setObjectName(QStringLiteral("PreviewVideoSpeedCombo"));
    previewSpeedCombo_->addItem(QStringLiteral("0.25x"), 0.25);
    previewSpeedCombo_->addItem(QStringLiteral("0.5x"), 0.5);
    previewSpeedCombo_->addItem(QStringLiteral("1x"), 1.0);
    previewSpeedCombo_->addItem(QStringLiteral("1.5x"), 1.5);
    previewSpeedCombo_->addItem(QStringLiteral("2x"), 2.0);
    previewSpeedCombo_->setCurrentIndex(2);
    previewSpeedCombo_->setToolTip(QStringLiteral("Playback speed"));

    previewLoopCheck_ = new QCheckBox(QStringLiteral("Loop"), previewVideoTransportBar_);
    previewLoopCheck_->setObjectName(QStringLiteral("PreviewVideoLoopCheck"));
    previewLoopCheck_->setToolTip(QStringLiteral("Loop only when enabled; pause and stop are always respected."));

    previewTransportLayout->addWidget(previewRestartButton_, 0);
    previewTransportLayout->addWidget(previewStepBackButton_, 0);
    previewTransportLayout->addWidget(previewPlayPauseButton_, 0);
    previewTransportLayout->addWidget(previewStepForwardButton_, 0);
    previewTransportLayout->addWidget(previewStopButton_, 0);
    previewTransportLayout->addWidget(previewSeekSlider_, 1);
    previewTransportLayout->addWidget(previewTimeLabel_, 0);
    previewTransportLayout->addWidget(previewSpeedCombo_, 0);
    previewTransportLayout->addWidget(previewLoopCheck_, 0);
    previewVideoTransportBar_->setVisible(false);

    previewVideoLayout->addWidget(previewVideoWidget_, 1);
    previewVideoLayout->addWidget(previewVideoTransportBar_, 0);
    previewVideoLayout->addWidget(previewVideoCaptionLabel_, 0);

    previewStack_->addWidget(previewImagePage_);
    previewStack_->addWidget(previewVideoPage_);
    previewStack_->setCurrentWidget(previewImagePage_);

    mediaPreviewController_ = new spellvision::preview::MediaPreviewController(this);
    spellvision::preview::MediaPreviewBindings previewBindings;
    previewBindings.previewStack = previewStack_;
    previewBindings.imagePage = previewImagePage_;
    previewBindings.videoPage = previewVideoPage_;
    previewBindings.videoWidget = previewVideoWidget_;
    previewBindings.captionLabel = previewVideoCaptionLabel_;
    previewBindings.transportBar = previewVideoTransportBar_;
    previewBindings.playPauseButton = previewPlayPauseButton_;
    previewBindings.stopButton = previewStopButton_;
    previewBindings.stepBackButton = previewStepBackButton_;
    previewBindings.stepForwardButton = previewStepForwardButton_;
    previewBindings.restartButton = previewRestartButton_;
    previewBindings.seekSlider = previewSeekSlider_;
    previewBindings.timeLabel = previewTimeLabel_;
    previewBindings.speedCombo = previewSpeedCombo_;
    previewBindings.loopCheck = previewLoopCheck_;
    previewBindings.framesPerSecondProvider = [this]() {
        return fpsSpin_ ? fpsSpin_->value() : 24;
    };
    mediaPreviewController_->bind(previewBindings);
    connect(mediaPreviewController_, &spellvision::preview::MediaPreviewController::stateChanged, this, [this]() {
        updatePreviewEmptyStateSizing();
    });
    connect(mediaPreviewController_, &spellvision::preview::MediaPreviewController::mediaError, this, [this](const QString &message) {
        if (readinessHintLabel_)
            readinessHintLabel_->setText(message);
    });

    imagePreviewController_ = new spellvision::preview::ImagePreviewController(this);
    spellvision::preview::ImagePreviewBindings imagePreviewBindings;
    imagePreviewBindings.previewLabel = previewLabel_;
    imagePreviewBindings.mediaPreviewController = mediaPreviewController_;
    imagePreviewBindings.repolishWidget = [](QWidget *widget) { repolishWidget(widget); };
    imagePreviewController_->bind(imagePreviewBindings);

    updateVideoTransportUi();

    generateButton_ = new QPushButton(QStringLiteral("Generate"), canvasCard);
    generateButton_->setObjectName(QStringLiteral("PrimaryActionButton"));
    queueButton_ = new QPushButton(QStringLiteral("Queue"), canvasCard);
    queueButton_->setObjectName(QStringLiteral("SecondaryActionButton"));
    prepLatestForI2IButton_ = new QPushButton(QStringLiteral("Prep for I2I"), canvasCard);
    prepLatestForI2IButton_->setObjectName(QStringLiteral("SecondaryActionButton"));
    useLatestT2IButton_ = new QPushButton(QStringLiteral("Use Last Image"), canvasCard);
    useLatestT2IButton_->setObjectName(QStringLiteral("SecondaryActionButton"));
    savePresetButton_ = new QPushButton(QStringLiteral("Save Snapshot"), canvasCard);
    savePresetButton_->setObjectName(QStringLiteral("TertiaryActionButton"));
    clearButton_ = new QPushButton(QStringLiteral("Reset"), canvasCard);
    clearButton_->setObjectName(QStringLiteral("TertiaryActionButton"));
    toggleControlsButton_ = new QPushButton(QStringLiteral("Hide Controls"), canvasCard);
    toggleControlsButton_->setObjectName(QStringLiteral("SecondaryActionButton"));
    toggleControlsButton_->setVisible(false);

    readinessHintLabel_ = new QLabel(canvasCard);
    readinessHintLabel_->setObjectName(QStringLiteral("ReadinessHint"));
    readinessHintLabel_->setWordWrap(false);
    readinessHintLabel_->setMaximumWidth(280);
    readinessHintLabel_->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Fixed);
    readinessHintLabel_->setVisible(false);

    auto buildCommandBindings = [this]() {
        WorkerCommandRunner::Bindings bindings;
        bindings.buildPayload = [this]() { return buildRequestPayload(); };
        bindings.readinessBlockReason = [this]() { return readinessBlockReason(); };
        bindings.showReadinessHint = [this](const QString &blockReason) {
            if (blockReason.trimmed().isEmpty())
                return;
            if (!readinessHintLabel_)
                return;

            readinessHintLabel_->setText(blockReason);
            readinessHintLabel_->setToolTip(blockReason);
            readinessHintLabel_->setVisible(true);
        };
        bindings.isVideoMode = [this]() { return isVideoMode(); };
        bindings.selectedModelValue = [this]() { return selectedModelValue(); };
        bindings.hasVideoWorkflowBinding = [this]() { return hasVideoWorkflowBinding(); };
        bindings.emitGenerate = [this](const QJsonObject &payload) { emit generateRequested(payload); };
        bindings.emitQueue = [this](const QJsonObject &payload) { emit queueRequested(payload); };
        return bindings;
    };

    connect(generateButton_, &QPushButton::clicked, this, [this, buildCommandBindings]() {
        // Do not short-circuit here. MainWindow owns the final submission gate
        // and has richer context about native video stacks vs workflow-backed
        // generation. Keeping this signal hot also makes failed submissions
        // visible in the Logs panel instead of making the button feel dead.
        WorkerCommandRunner::submit(WorkerCommandRunner::SubmitKind::Generate, buildCommandBindings());
    });
    connect(queueButton_, &QPushButton::clicked, this, [this, buildCommandBindings]() {
        WorkerCommandRunner::submit(WorkerCommandRunner::SubmitKind::Queue, buildCommandBindings());
    });
    connect(savePresetButton_, &QPushButton::clicked, this, [this]() { saveSnapshot(); });
    connect(clearButton_, &QPushButton::clicked, this, [this]() { clearForm(); });
    connect(toggleControlsButton_, &QPushButton::clicked, this, [this]() {
        rightControlsVisible_ = !rightControlsVisible_;
        updateAdaptiveLayout();
    });
    connect(prepLatestForI2IButton_, &QPushButton::clicked, this, &ImageGenerationPage::prepLatestForI2I);
    connect(useLatestT2IButton_, &QPushButton::clicked, this, &ImageGenerationPage::useLatestForI2I);

    auto *actionRow = new QHBoxLayout;
    actionRow->setContentsMargins(0, 0, 0, 0);
    actionRow->setSpacing(8);
    actionRow->addWidget(generateButton_);
    actionRow->addWidget(queueButton_);
    actionRow->addWidget(toggleControlsButton_);
    actionRow->addWidget(readinessHintLabel_, 0, Qt::AlignVCenter);
    actionRow->addStretch(1);
    actionRow->addWidget(prepLatestForI2IButton_);
    actionRow->addWidget(useLatestT2IButton_);
    actionRow->addWidget(savePresetButton_);
    actionRow->addWidget(clearButton_);

    canvasLayout->addWidget(previewStack_, 1);
    canvasLayout->addLayout(actionRow, 0);
    centerLayout->addWidget(canvasCard, 1);

    rightScrollArea_ = new QScrollArea(contentSplitter_);
    rightScrollArea_->setWidgetResizable(true);
    rightScrollArea_->setFrameShape(QFrame::NoFrame);
    rightScrollArea_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    rightScrollArea_->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    rightScrollArea_->setMinimumWidth(340);
    rightScrollArea_->setMaximumWidth(460);
    rightScrollArea_->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Expanding);

    auto *rightContainer = new QWidget(rightScrollArea_);
    auto *rightLayout = new QVBoxLayout(rightContainer);
    rightLayout->setContentsMargins(4, 0, 0, 0);
    rightLayout->setSpacing(12);

    stackCard_ = createCard(QStringLiteral("SettingsCard"));
    auto *stackCardLayout = new QVBoxLayout(stackCard_);
    stackCardLayout->setContentsMargins(16, 16, 16, 16);
    stackCardLayout->setSpacing(8);

    auto *checkpointValueCard = new QFrame(stackCard_);
    checkpointValueCard->setObjectName(QStringLiteral("InputDropCard"));
    auto *checkpointValueLayout = new QHBoxLayout(checkpointValueCard);
    checkpointValueLayout->setContentsMargins(12, 10, 12, 10);
    checkpointValueLayout->setSpacing(8);

    selectedModelLabel_ = new QLabel(isVideoMode() ? QStringLiteral("No video model stack selected") : QStringLiteral("No checkpoint selected"), checkpointValueCard);
    selectedModelLabel_->setObjectName(QStringLiteral("SectionBody"));
    selectedModelLabel_->setWordWrap(true);
    checkpointValueLayout->addWidget(selectedModelLabel_, 1);

    browseModelButton_ = new QPushButton(QStringLiteral("Browse"), stackCard_);
    browseModelButton_->setObjectName(QStringLiteral("SecondaryActionButton"));
    clearModelButton_ = new QPushButton(QStringLiteral("Clear"), stackCard_);
    clearModelButton_->setObjectName(QStringLiteral("TertiaryActionButton"));
    connect(browseModelButton_, &QPushButton::clicked, this, &ImageGenerationPage::showCheckpointPicker);
    connect(clearModelButton_, &QPushButton::clicked, this, [this]() { setSelectedModel(QString(), QString()); });

    workflowCombo_ = new ClickOnlyComboBox(stackCard_);
    workflowCombo_->setEditable(false);
    workflowCombo_->addItem(QStringLiteral("Default Canvas"), QStringLiteral("Default Canvas"));
    workflowCombo_->addItem(QStringLiteral("Portrait Detail"), QStringLiteral("Portrait Detail"));
    workflowCombo_->addItem(QStringLiteral("Stylized Concept"), QStringLiteral("Stylized Concept"));
    workflowCombo_->addItem(QStringLiteral("Upscale / Repair"), QStringLiteral("Upscale / Repair"));
    configureComboBox(workflowCombo_);

    loraStackContainer_ = new QWidget(stackCard_);
    loraStackLayout_ = new QVBoxLayout(loraStackContainer_);
    loraStackLayout_->setContentsMargins(0, 0, 0, 0);
    loraStackLayout_->setSpacing(8);

    loraStackSummaryLabel_ = new QLabel(QStringLiteral("No LoRAs in stack"), stackCard_);
    loraStackSummaryLabel_->setObjectName(QStringLiteral("ImageGenHint"));
    loraStackSummaryLabel_->setWordWrap(true);

    addLoraButton_ = new QPushButton(QStringLiteral("Add LoRA"), stackCard_);
    addLoraButton_->setObjectName(QStringLiteral("SecondaryActionButton"));
    clearLorasButton_ = new QPushButton(QStringLiteral("Clear Stack"), stackCard_);
    clearLorasButton_->setObjectName(QStringLiteral("TertiaryActionButton"));

    loraStackController_ = new spellvision::assets::LoraStackController(this);
    spellvision::assets::LoraStackBindings loraBindings;
    loraBindings.container = loraStackContainer_;
    loraBindings.layout = loraStackLayout_;
    loraBindings.summaryLabel = loraStackSummaryLabel_;
    loraBindings.clearButton = clearLorasButton_;
    loraStackController_->bind(&loraStack_, loraBindings);
    loraStackController_->setDisplayResolver([this](const QString &value) { return resolveLoraDisplay(value); });
    loraStackController_->setChangedCallback([this]() { scheduleUiRefresh(0); });
    loraStackController_->setReplaceRequestedCallback([this](int index) { replaceLoraStackEntry(index); });

    connect(addLoraButton_, &QPushButton::clicked, this, &ImageGenerationPage::showLoraPicker);
    connect(clearLorasButton_, &QPushButton::clicked, this, [this]() {
        if (loraStackController_)
            loraStackController_->clear();
        else
        {
            loraStack_.clear();
            rebuildLoraStackUi();
            scheduleUiRefresh(0);
        }
    });

    auto *stackForm = new QGridLayout;
    stackForm->setHorizontalSpacing(10);
    stackForm->setVerticalSpacing(8);
    stackForm->setColumnStretch(1, 1);

    int stackRow = 0;
    stackForm->addWidget(new QLabel(isVideoMode() ? QStringLiteral("Model Stack") : QStringLiteral("Checkpoint"), stackCard_), stackRow, 0);
    stackForm->addWidget(checkpointValueCard, stackRow, 1);
    ++stackRow;
    auto *checkpointActions = new QWidget(stackCard_);
    auto *checkpointActionsLayout = new QHBoxLayout(checkpointActions);
    checkpointActionsLayout->setContentsMargins(0, 0, 0, 0);
    checkpointActionsLayout->setSpacing(8);
    checkpointActionsLayout->addWidget(browseModelButton_);
    checkpointActionsLayout->addWidget(clearModelButton_);
    checkpointActionsLayout->addStretch(1);
    stackForm->addWidget(checkpointActions, stackRow, 1);
    ++stackRow;

    videoComponentPanel_ = new QWidget(stackCard_);
    auto *videoComponentLayout = new QGridLayout(videoComponentPanel_);
    videoComponentLayout->setContentsMargins(0, 0, 0, 0);
    videoComponentLayout->setHorizontalSpacing(8);
    videoComponentLayout->setVerticalSpacing(6);

    videoStackModeCombo_ = new ClickOnlyComboBox(videoComponentPanel_);
    videoStackModeCombo_->addItem(QStringLiteral("Auto detect from selection"), QStringLiteral("auto"));
    videoStackModeCombo_->addItem(QStringLiteral("Single model"), QStringLiteral("single_model"));
    videoStackModeCombo_->addItem(QStringLiteral("WAN dual-noise"), QStringLiteral("wan_dual_noise"));

    videoPrimaryModelCombo_ = new ClickOnlyComboBox(videoComponentPanel_);
    videoHighNoiseModelCombo_ = new ClickOnlyComboBox(videoComponentPanel_);
    videoLowNoiseModelCombo_ = new ClickOnlyComboBox(videoComponentPanel_);
    videoTextEncoderCombo_ = new ClickOnlyComboBox(videoComponentPanel_);
    videoVaeCombo_ = new ClickOnlyComboBox(videoComponentPanel_);
    videoClipVisionCombo_ = new ClickOnlyComboBox(videoComponentPanel_);
    for (QComboBox *combo : {videoStackModeCombo_, videoPrimaryModelCombo_, videoHighNoiseModelCombo_, videoLowNoiseModelCombo_, videoTextEncoderCombo_, videoVaeCombo_, videoClipVisionCombo_})
        configureComboBox(combo);

    videoStackModeRow_ = new QLabel(QStringLiteral("Stack Mode"), videoComponentPanel_);
    videoComponentLayout->addWidget(videoStackModeRow_, 0, 0);
    videoComponentLayout->addWidget(videoStackModeCombo_, 0, 1);
    videoComponentLayout->addWidget(new QLabel(QStringLiteral("Primary"), videoComponentPanel_), 1, 0);
    videoComponentLayout->addWidget(videoPrimaryModelCombo_, 1, 1);

    videoHighNoiseRow_ = new QLabel(QStringLiteral("High Noise"), videoComponentPanel_);
    videoComponentLayout->addWidget(videoHighNoiseRow_, 2, 0);
    videoComponentLayout->addWidget(videoHighNoiseModelCombo_, 2, 1);

    videoLowNoiseRow_ = new QLabel(QStringLiteral("Low Noise"), videoComponentPanel_);
    videoComponentLayout->addWidget(videoLowNoiseRow_, 3, 0);
    videoComponentLayout->addWidget(videoLowNoiseModelCombo_, 3, 1);

    videoComponentLayout->addWidget(new QLabel(QStringLiteral("Text"), videoComponentPanel_), 4, 0);
    videoComponentLayout->addWidget(videoTextEncoderCombo_, 4, 1);
    videoComponentLayout->addWidget(new QLabel(QStringLiteral("VAE"), videoComponentPanel_), 5, 0);
    videoComponentLayout->addWidget(videoVaeCombo_, 5, 1);
    videoComponentLayout->addWidget(new QLabel(QStringLiteral("Vision"), videoComponentPanel_), 6, 0);
    videoComponentLayout->addWidget(videoClipVisionCombo_, 6, 1);
    videoComponentLayout->setColumnStretch(1, 1);
    videoComponentPanel_->setVisible(isVideoMode());

    if (isVideoMode())
    {
        stackForm->addWidget(new QLabel(QStringLiteral("Components"), stackCard_), stackRow, 0, Qt::AlignTop);
        stackForm->addWidget(videoComponentPanel_, stackRow, 1);
        ++stackRow;
    }

    connect(videoStackModeCombo_, qOverload<int>(&QComboBox::currentIndexChanged), this, [this]() {
        if (syncingVideoComponentControls_ || !isVideoMode())
            return;
        updateVideoStackModeUi();
        applyVideoComponentOverridesToSelectedStack();
        scheduleUiRefresh(0);
    });
    connect(videoPrimaryModelCombo_, qOverload<int>(&QComboBox::currentIndexChanged), this, [this]() {
        if (syncingVideoComponentControls_ || !isVideoMode())
            return;
        const QString value = videoComponentValue(videoPrimaryModelCombo_);
        if (!value.trimmed().isEmpty() && value.compare(selectedModelPath_, Qt::CaseInsensitive) != 0)
        {
            setSelectedModel(value, comboDisplayValue(videoPrimaryModelCombo_));
            persistRecentSelection(QStringLiteral("image_generation/recent_video_model_stacks"), value);
            return;
        }
        applyVideoComponentOverridesToSelectedStack();
    });
    for (QComboBox *combo : {videoHighNoiseModelCombo_, videoLowNoiseModelCombo_, videoTextEncoderCombo_, videoVaeCombo_, videoClipVisionCombo_})
    {
        connect(combo, qOverload<int>(&QComboBox::currentIndexChanged), this, [this]() {
            if (syncingVideoComponentControls_ || !isVideoMode())
                return;
            applyVideoComponentOverridesToSelectedStack();
        });
    }

    stackForm->addWidget(new QLabel(QStringLiteral("Workflow"), stackCard_), stackRow, 0);
    stackForm->addWidget(workflowCombo_, stackRow, 1);
    ++stackRow;
    stackForm->addWidget(new QLabel(QStringLiteral("LoRA Stack"), stackCard_), stackRow, 0, Qt::AlignTop);
    stackForm->addWidget(loraStackContainer_, stackRow, 1);
    ++stackRow;
    auto *loraActions = new QWidget(stackCard_);
    auto *loraActionsLayout = new QHBoxLayout(loraActions);
    loraActionsLayout->setContentsMargins(0, 0, 0, 0);
    loraActionsLayout->setSpacing(8);
    loraActionsLayout->addWidget(addLoraButton_);
    loraActionsLayout->addWidget(clearLorasButton_);
    loraActionsLayout->addStretch(1);
    stackForm->addWidget(loraActions, stackRow, 1);
    ++stackRow;
    stackForm->addWidget(new QLabel(QStringLiteral("Stack Summary"), stackCard_), stackRow, 0, Qt::AlignTop);
    stackForm->addWidget(loraStackSummaryLabel_, stackRow, 1);
    stackToolsLayout_ = new QBoxLayout(QBoxLayout::TopToBottom);
    stackToolsLayout_->setContentsMargins(0, 0, 0, 0);
    stackToolsLayout_->setSpacing(8);
    openModelsButton_ = new QPushButton(QStringLiteral("Open Models"), stackCard_);
    openModelsButton_->setObjectName(QStringLiteral("SecondaryActionButton"));
    openModelsButton_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    openWorkflowsButton_ = new QPushButton(QStringLiteral("Open Workflows"), stackCard_);
    openWorkflowsButton_->setObjectName(QStringLiteral("SecondaryActionButton"));
    openWorkflowsButton_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    connect(openModelsButton_, &QPushButton::clicked, this, &ImageGenerationPage::openModelsRequested);
    connect(openWorkflowsButton_, &QPushButton::clicked, this, &ImageGenerationPage::openWorkflowsRequested);
    stackToolsLayout_->addWidget(openModelsButton_);
    stackToolsLayout_->addWidget(openWorkflowsButton_);

    stackCardLayout->addWidget(createSectionTitle(QStringLiteral("Model Stack"), stackCard_));
    stackCardLayout->addLayout(stackForm);
    stackCardLayout->addLayout(stackToolsLayout_);
    rightLayout->addWidget(stackCard_);

    settingsCard_ = createCard(QStringLiteral("OutputCard"));
    auto *settingsCardLayout = new QVBoxLayout(settingsCard_);
    settingsCardLayout->setContentsMargins(12, 12, 12, 12);
    settingsCardLayout->setSpacing(8);

    samplerCombo_ = new ClickOnlyComboBox(quickControlsCard);
    samplerCombo_->addItem(QStringLiteral("euler"), QStringLiteral("euler"));
    samplerCombo_->addItem(QStringLiteral("euler_ancestral"), QStringLiteral("euler_ancestral"));
    samplerCombo_->addItem(QStringLiteral("heun"), QStringLiteral("heun"));
    samplerCombo_->addItem(QStringLiteral("dpmpp_2m"), QStringLiteral("dpmpp_2m"));
    samplerCombo_->addItem(QStringLiteral("dpmpp_sde"), QStringLiteral("dpmpp_sde"));
    samplerCombo_->addItem(QStringLiteral("uni_pc"), QStringLiteral("uni_pc"));
    configureComboBox(samplerCombo_);

    schedulerCombo_ = new ClickOnlyComboBox(quickControlsCard);
    schedulerCombo_->addItem(QStringLiteral("normal"), QStringLiteral("normal"));
    schedulerCombo_->addItem(QStringLiteral("karras"), QStringLiteral("karras"));
    schedulerCombo_->addItem(QStringLiteral("sgm_uniform"), QStringLiteral("sgm_uniform"));
    configureComboBox(schedulerCombo_);

    videoSamplerCombo_ = new ClickOnlyComboBox(quickControlsCard);
    videoSamplerCombo_->addItem(QStringLiteral("Auto / family default"), QStringLiteral("auto"));
    videoSamplerCombo_->addItem(QStringLiteral("Euler"), QStringLiteral("euler"));
    videoSamplerCombo_->addItem(QStringLiteral("Euler ancestral"), QStringLiteral("euler_ancestral"));
    videoSamplerCombo_->addItem(QStringLiteral("DPM++ 2M"), QStringLiteral("dpmpp_2m"));
    videoSamplerCombo_->addItem(QStringLiteral("UniPC"), QStringLiteral("uni_pc"));
    configureComboBox(videoSamplerCombo_);

    videoSchedulerCombo_ = new ClickOnlyComboBox(quickControlsCard);
    videoSchedulerCombo_->addItem(QStringLiteral("Auto / family default"), QStringLiteral("auto"));
    videoSchedulerCombo_->addItem(QStringLiteral("Normal"), QStringLiteral("normal"));
    videoSchedulerCombo_->addItem(QStringLiteral("Simple"), QStringLiteral("simple"));
    videoSchedulerCombo_->addItem(QStringLiteral("SGM uniform"), QStringLiteral("sgm_uniform"));
    videoSchedulerCombo_->addItem(QStringLiteral("FlowMatch / CausVid"), QStringLiteral("flowmatch_causvid"));
    configureComboBox(videoSchedulerCombo_);

    stepsSpin_ = new QSpinBox(quickControlsCard);
    stepsSpin_->setRange(1, 200);
    stepsSpin_->setValue(28);
    configureSpinBox(stepsSpin_);

    cfgSpin_ = new QDoubleSpinBox(quickControlsCard);
    cfgSpin_->setDecimals(1);
    cfgSpin_->setSingleStep(0.5);
    cfgSpin_->setRange(1.0, 30.0);
    cfgSpin_->setValue(7.0);
    configureDoubleSpinBox(cfgSpin_);

    seedSpin_ = new QSpinBox(quickControlsCard);
    seedSpin_->setRange(0, 999999999);
    seedSpin_->setSpecialValueText(QStringLiteral("Random"));
    seedSpin_->setValue(0);
    configureSpinBox(seedSpin_);

    widthSpin_ = new QSpinBox(quickControlsCard);
    widthSpin_->setRange(64, 8192);
    widthSpin_->setSingleStep(64);
    widthSpin_->setValue(isVideoMode() ? 832 : 1024);
    configureSpinBox(widthSpin_);

    heightSpin_ = new QSpinBox(quickControlsCard);
    heightSpin_->setRange(64, 8192);
    heightSpin_->setSingleStep(64);
    heightSpin_->setValue(isVideoMode() ? 480 : 1024);
    configureSpinBox(heightSpin_);

    frameCountSpin_ = new QSpinBox(quickControlsCard);
    frameCountSpin_->setRange(1, 2400);
    frameCountSpin_->setSingleStep(8);
    frameCountSpin_->setValue(81);
    frameCountSpin_->setToolTip(QStringLiteral("Total frames requested from the video workflow."));
    configureSpinBox(frameCountSpin_);

    fpsSpin_ = new QSpinBox(quickControlsCard);
    fpsSpin_->setRange(1, 120);
    fpsSpin_->setValue(16);
    fpsSpin_->setToolTip(QStringLiteral("Playback frames per second for the generated clip."));
    configureSpinBox(fpsSpin_);

    batchSpin_ = new QSpinBox(outputQueueCard);
    batchSpin_->setRange(1, 32);
    batchSpin_->setValue(1);
    configureSpinBox(batchSpin_);

    denoiseSpin_ = new QDoubleSpinBox(advancedCard);
    denoiseSpin_->setDecimals(2);
    denoiseSpin_->setSingleStep(0.05);
    denoiseSpin_->setRange(0.0, 1.0);
    denoiseSpin_->setValue(0.45);
    configureDoubleSpinBox(denoiseSpin_);

    wanSplitCombo_ = new ClickOnlyComboBox(advancedCard);
    wanSplitCombo_->addItem(QStringLiteral("Auto midpoint"), QStringLiteral("auto"));
    wanSplitCombo_->addItem(QStringLiteral("Manual split step"), QStringLiteral("manual"));
    wanSplitCombo_->addItem(QStringLiteral("Favor high-noise"), QStringLiteral("high_bias"));
    wanSplitCombo_->addItem(QStringLiteral("Favor low-noise"), QStringLiteral("low_bias"));
    configureComboBox(wanSplitCombo_);

    highNoiseStepsSpin_ = new QSpinBox(advancedCard);
    highNoiseStepsSpin_->setRange(1, 512);
    highNoiseStepsSpin_->setValue(14);
    configureSpinBox(highNoiseStepsSpin_);

    lowNoiseStepsSpin_ = new QSpinBox(advancedCard);
    lowNoiseStepsSpin_->setRange(1, 512);
    lowNoiseStepsSpin_->setValue(14);
    configureSpinBox(lowNoiseStepsSpin_);

    splitStepSpin_ = new QSpinBox(advancedCard);
    splitStepSpin_->setRange(1, 511);
    splitStepSpin_->setValue(14);
    configureSpinBox(splitStepSpin_);

    highNoiseShiftSpin_ = new QDoubleSpinBox(advancedCard);
    highNoiseShiftSpin_->setDecimals(2);
    highNoiseShiftSpin_->setSingleStep(0.25);
    highNoiseShiftSpin_->setRange(0.0, 30.0);
    highNoiseShiftSpin_->setValue(5.0);
    configureDoubleSpinBox(highNoiseShiftSpin_);

    lowNoiseShiftSpin_ = new QDoubleSpinBox(advancedCard);
    lowNoiseShiftSpin_->setDecimals(2);
    lowNoiseShiftSpin_->setSingleStep(0.25);
    lowNoiseShiftSpin_->setRange(0.0, 30.0);
    lowNoiseShiftSpin_->setValue(5.0);
    configureDoubleSpinBox(lowNoiseShiftSpin_);

    enableVaeTilingCheck_ = new QCheckBox(QStringLiteral("Enable"), advancedCard);

    auto makeSettingsRow = [this](QWidget *parent, const QString &labelText, QWidget *field) -> QWidget * {
        auto *rowWidget = new QWidget(parent);
        rowWidget->setMinimumHeight(30);
        auto *rowLayout = new QHBoxLayout(rowWidget);
        rowLayout->setContentsMargins(0, 0, 0, 0);
        rowLayout->setSpacing(7);

        auto *label = new QLabel(labelText, rowWidget);
        label->setMinimumWidth(62);
        label->setMaximumWidth(78);
        label->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Preferred);
        label->setObjectName(QStringLiteral("CompactFieldLabel"));
        label->setToolTip(labelText);

        field->setParent(rowWidget);
        field->setMinimumWidth(qMax(field->minimumWidth(), 120));
        field->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

        rowLayout->addWidget(label);
        rowLayout->addWidget(field, 1);
        return rowWidget;
    };

    auto *aspectPresetCombo = new ClickOnlyComboBox(quickControlsCard);
    aspectPresetCombo->addItem(QStringLiteral("Custom"), QString());
    aspectPresetCombo->addItem(QStringLiteral("Square 1:1"), QStringLiteral("1024x1024"));
    aspectPresetCombo->addItem(QStringLiteral("Portrait 3:4"), QStringLiteral("1024x1344"));
    aspectPresetCombo->addItem(QStringLiteral("Landscape 3:2"), QStringLiteral("1216x832"));
    aspectPresetCombo->addItem(QStringLiteral("Wide 16:9"), QStringLiteral("1344x768"));
    configureComboBox(aspectPresetCombo);
    connect(aspectPresetCombo, QOverload<int>::of(&QComboBox::currentIndexChanged), this, [this, aspectPresetCombo](int index) {
        const QString value = aspectPresetCombo->itemData(index, Qt::UserRole).toString();
        if (value.isEmpty() || !widthSpin_ || !heightSpin_)
            return;

        const QStringList parts = value.split(QLatin1Char('x'));
        if (parts.size() != 2)
            return;

        widthSpin_->setValue(parts.at(0).toInt());
        heightSpin_->setValue(parts.at(1).toInt());
    });

    QWidget *aspectRow = makeSettingsRow(quickControlsCard, QStringLiteral("Aspect"), aspectPresetCombo);
    QWidget *samplerRow = makeSettingsRow(quickControlsCard, QStringLiteral("Image Sampler"), samplerCombo_);
    QWidget *schedulerRow = makeSettingsRow(quickControlsCard, QStringLiteral("Image Scheduler"), schedulerCombo_);
    QWidget *videoSamplerRow = makeSettingsRow(quickControlsCard, QStringLiteral("Video Sampler"), videoSamplerCombo_);
    QWidget *videoSchedulerRow = makeSettingsRow(quickControlsCard, QStringLiteral("Video Scheduler"), videoSchedulerCombo_);
    samplerRow->setVisible(!isVideoMode());
    schedulerRow->setVisible(!isVideoMode());
    videoSamplerRow->setVisible(isVideoMode());
    videoSchedulerRow->setVisible(isVideoMode());
    QWidget *stepsRow = makeSettingsRow(quickControlsCard, QStringLiteral("Steps"), stepsSpin_);
    QWidget *cfgRow = makeSettingsRow(quickControlsCard, QStringLiteral("CFG"), cfgSpin_);
    QWidget *seedRow = makeSettingsRow(quickControlsCard, QStringLiteral("Seed"), seedSpin_);
    QWidget *widthRow = makeSettingsRow(quickControlsCard, QStringLiteral("Width"), widthSpin_);
    QWidget *heightRow = makeSettingsRow(quickControlsCard, QStringLiteral("Height"), heightSpin_);
    QWidget *framesRow = makeSettingsRow(quickControlsCard, QStringLiteral("Frames"), frameCountSpin_);
    QWidget *fpsRow = makeSettingsRow(quickControlsCard, QStringLiteral("FPS"), fpsSpin_);
    framesRow->setVisible(isVideoMode());
    fpsRow->setVisible(isVideoMode());
    QWidget *batchRow = makeSettingsRow(outputQueueCard, QStringLiteral("Batch"), batchSpin_);
    batchRow->setObjectName(QStringLiteral("OutputQueueBodyRow"));

    denoiseRow_ = makeSettingsRow(advancedCard, QStringLiteral("Denoise"), denoiseSpin_);
    denoiseRow_->setObjectName(QStringLiteral("AdvancedBodyRow"));
    denoiseRow_->setVisible(usesStrengthControl());

    wanSplitRow_ = makeSettingsRow(advancedCard, QStringLiteral("Wan Split"), wanSplitCombo_);
    wanSplitRow_->setObjectName(QStringLiteral("AdvancedBodyRow"));
    highNoiseStepsRow_ = makeSettingsRow(advancedCard, QStringLiteral("High Steps"), highNoiseStepsSpin_);
    highNoiseStepsRow_->setObjectName(QStringLiteral("AdvancedBodyRow"));
    lowNoiseStepsRow_ = makeSettingsRow(advancedCard, QStringLiteral("Low Steps"), lowNoiseStepsSpin_);
    lowNoiseStepsRow_->setObjectName(QStringLiteral("AdvancedBodyRow"));
    splitStepRow_ = makeSettingsRow(advancedCard, QStringLiteral("Split Step"), splitStepSpin_);
    splitStepRow_->setObjectName(QStringLiteral("AdvancedBodyRow"));
    highNoiseShiftRow_ = makeSettingsRow(advancedCard, QStringLiteral("High Shift"), highNoiseShiftSpin_);
    highNoiseShiftRow_->setObjectName(QStringLiteral("AdvancedBodyRow"));
    lowNoiseShiftRow_ = makeSettingsRow(advancedCard, QStringLiteral("Low Shift"), lowNoiseShiftSpin_);
    lowNoiseShiftRow_->setObjectName(QStringLiteral("AdvancedBodyRow"));
    enableVaeTilingRow_ = makeSettingsRow(advancedCard, QStringLiteral("VAE Tiling"), enableVaeTilingCheck_);
    enableVaeTilingRow_->setObjectName(QStringLiteral("AdvancedBodyRow"));

    samplerSchedulerLayout_ = new QBoxLayout(QBoxLayout::TopToBottom);
    samplerSchedulerLayout_->setContentsMargins(0, 0, 0, 0);
    samplerSchedulerLayout_->setSpacing(6);
    samplerSchedulerLayout_->addWidget(aspectRow);
    samplerSchedulerLayout_->addWidget(samplerRow);
    samplerSchedulerLayout_->addWidget(schedulerRow);
    samplerSchedulerLayout_->addWidget(videoSamplerRow);
    samplerSchedulerLayout_->addWidget(videoSchedulerRow);

    stepsCfgLayout_ = new QBoxLayout(QBoxLayout::TopToBottom);
    stepsCfgLayout_->setContentsMargins(0, 0, 0, 0);
    stepsCfgLayout_->setSpacing(6);
    stepsCfgLayout_->addWidget(stepsRow);
    stepsCfgLayout_->addWidget(cfgRow);

    seedBatchLayout_ = new QBoxLayout(QBoxLayout::TopToBottom);
    seedBatchLayout_->setContentsMargins(0, 0, 0, 0);
    seedBatchLayout_->setSpacing(6);
    seedBatchLayout_->addWidget(seedRow);
    seedBatchLayout_->addWidget(framesRow);
    seedBatchLayout_->addWidget(fpsRow);

    sizeLayout_ = new QBoxLayout(QBoxLayout::TopToBottom);
    sizeLayout_->setContentsMargins(0, 0, 0, 0);
    sizeLayout_->setSpacing(6);
    sizeLayout_->addWidget(widthRow);
    sizeLayout_->addWidget(heightRow);

    outputPrefixEdit_ = new QLineEdit(outputQueueCard);
    outputPrefixEdit_->setPlaceholderText(QStringLiteral("spellvision_render"));

    outputFolderLabel_ = new QLabel(QDir::toNativeSeparators(chooseComfyOutputPath()), outputQueueCard);
    outputFolderLabel_->setObjectName(QStringLiteral("OutputQueueBodyHint"));
    outputFolderLabel_->setWordWrap(true);

    modelsRootLabel_ = new QLabel(settingsCard_);
    modelsRootLabel_->setObjectName(QStringLiteral("ImageGenHint"));
    modelsRootLabel_->setWordWrap(true);
    modelsRootLabel_->setTextFormat(Qt::RichText);
    modelsRootLabel_->setTextInteractionFlags(Qt::TextSelectableByMouse);

    quickControlsLayout->addLayout(samplerSchedulerLayout_);
    quickControlsLayout->addLayout(sizeLayout_);
    quickControlsLayout->addLayout(stepsCfgLayout_);
    quickControlsLayout->addLayout(seedBatchLayout_);

    auto *prefixRow = makeSettingsRow(outputQueueCard, QStringLiteral("Prefix"), outputPrefixEdit_);
    prefixRow->setObjectName(QStringLiteral("OutputQueueBodyRow"));
    auto *outputFolderTitle = new QLabel(QStringLiteral("Output Folder"), outputQueueCard);
    outputFolderTitle->setObjectName(QStringLiteral("OutputQueueBodyLabel"));

    outputQueueLayout->addWidget(batchRow);
    outputQueueLayout->addWidget(prefixRow);
    outputQueueLayout->addWidget(outputFolderTitle);
    outputQueueLayout->addWidget(outputFolderLabel_);

    advancedLayout->addWidget(denoiseRow_);
    advancedLayout->addWidget(wanSplitRow_);
    advancedLayout->addWidget(highNoiseStepsRow_);
    advancedLayout->addWidget(lowNoiseStepsRow_);
    advancedLayout->addWidget(splitStepRow_);
    advancedLayout->addWidget(highNoiseShiftRow_);
    advancedLayout->addWidget(lowNoiseShiftRow_);
    advancedLayout->addWidget(enableVaeTilingRow_);
    if (!usesStrengthControl() && !isVideoMode())
        advancedCard->setVisible(false);

    settingsCardLayout->addWidget(createSectionTitle(QStringLiteral("Asset Intelligence"), settingsCard_));
    auto *assetHint = createSectionBody(QStringLiteral("Live model, LoRA, workflow, and draft readiness."), settingsCard_);
    assetHint->setMaximumHeight(36);
    settingsCardLayout->addWidget(assetHint);
    modelsRootLabel_->setObjectName(QStringLiteral("AssetIntelligenceBody"));
    settingsCardLayout->addWidget(modelsRootLabel_);
    rightLayout->addWidget(settingsCard_);
    rightLayout->addStretch(1);

    rightScrollArea_->setWidget(rightContainer);

    contentSplitter_->addWidget(leftScrollArea_);
    contentSplitter_->addWidget(centerContainer_);
    contentSplitter_->addWidget(rightScrollArea_);
    contentSplitter_->setStretchFactor(0, 0);
    contentSplitter_->setStretchFactor(1, 1);
    contentSplitter_->setStretchFactor(2, 0);
    contentSplitter_->setSizes({395, 880, 465});

    root->addWidget(contentSplitter_, 1);

    if (prepLatestForI2IButton_)
        prepLatestForI2IButton_->setVisible(mode_ == Mode::TextToImage);
    if (useLatestT2IButton_)
    {
        useLatestT2IButton_->setVisible(isImageInputMode());
        useLatestT2IButton_->setToolTip(isVideoMode()
                                           ? QStringLiteral("Use the latest generated still image as the I2V keyframe.")
                                           : QStringLiteral("Use the latest generated still image as the I2I source."));
    }

    const auto refreshers = [this]() { scheduleUiRefresh(); };

    connect(promptEdit_, &QTextEdit::textChanged, this, refreshers);
    connect(negativePromptEdit_, &QTextEdit::textChanged, this, refreshers);
    connect(workflowCombo_, &QComboBox::currentTextChanged, this, refreshers);
    connect(samplerCombo_, &QComboBox::currentTextChanged, this, refreshers);
    connect(schedulerCombo_, &QComboBox::currentTextChanged, this, refreshers);
    if (videoSamplerCombo_)
        connect(videoSamplerCombo_, &QComboBox::currentTextChanged, this, refreshers);
    if (videoSchedulerCombo_)
        connect(videoSchedulerCombo_, &QComboBox::currentTextChanged, this, refreshers);
    connect(stepsSpin_, qOverload<int>(&QSpinBox::valueChanged), this, refreshers);
    connect(cfgSpin_, qOverload<double>(&QDoubleSpinBox::valueChanged), this, refreshers);
    connect(seedSpin_, qOverload<int>(&QSpinBox::valueChanged), this, refreshers);
    connect(widthSpin_, qOverload<int>(&QSpinBox::valueChanged), this, refreshers);
    connect(heightSpin_, qOverload<int>(&QSpinBox::valueChanged), this, refreshers);
    if (frameCountSpin_)
        connect(frameCountSpin_, qOverload<int>(&QSpinBox::valueChanged), this, refreshers);
    if (fpsSpin_)
        connect(fpsSpin_, qOverload<int>(&QSpinBox::valueChanged), this, refreshers);
    connect(batchSpin_, qOverload<int>(&QSpinBox::valueChanged), this, refreshers);
    connect(outputPrefixEdit_, &QLineEdit::textChanged, this, refreshers);
    if (denoiseSpin_)
        connect(denoiseSpin_, qOverload<double>(&QDoubleSpinBox::valueChanged), this, refreshers);
    if (wanSplitCombo_)
        connect(wanSplitCombo_, &QComboBox::currentTextChanged, this, refreshers);
    if (highNoiseStepsSpin_)
        connect(highNoiseStepsSpin_, qOverload<int>(&QSpinBox::valueChanged), this, refreshers);
    if (lowNoiseStepsSpin_)
        connect(lowNoiseStepsSpin_, qOverload<int>(&QSpinBox::valueChanged), this, refreshers);
    if (splitStepSpin_)
        connect(splitStepSpin_, qOverload<int>(&QSpinBox::valueChanged), this, refreshers);
    if (highNoiseShiftSpin_)
        connect(highNoiseShiftSpin_, qOverload<double>(&QDoubleSpinBox::valueChanged), this, refreshers);
    if (lowNoiseShiftSpin_)
        connect(lowNoiseShiftSpin_, qOverload<double>(&QDoubleSpinBox::valueChanged), this, refreshers);
    if (enableVaeTilingCheck_)
        connect(enableVaeTilingCheck_, &QCheckBox::toggled, this, refreshers);
    if (inputImageEdit_)
        connect(inputImageEdit_, &QLineEdit::textChanged, this, refreshers);

    connect(workflowCombo_, &QComboBox::currentTextChanged, this, [this]() {
        if (workflowCombo_)
            workflowCombo_->setToolTip(currentComboValue(workflowCombo_));
    });

    refreshSelectedModelUi();
    rebuildLoraStackUi();

    setWorkspaceTelemetry(QStringLiteral("Runtime: Managed ComfyUI"),
                          QStringLiteral("Queue: 0 running | 0 pending"),
                          QStringLiteral("Model: none"),
                          QStringLiteral("LoRA: none"),
                          0,
                          QStringLiteral("Idle"));

    updateAdaptiveLayout();
}

void ImageGenerationPage::reloadCatalogs()
{
    modelsRootDir_ = chooseModelsRootPath();

    updateAssetIntelligenceUi();

    const QVector<CatalogEntry> modelEntries = isVideoMode()
                                                   ? scanVideoModelStackCatalog(modelsRootDir_)
                                                   : scanImageModelCatalog(modelsRootDir_);
    modelDisplayByValue_.clear();
    modelFamilyByValue_.clear();
    modelModalityByValue_.clear();
    modelRoleByValue_.clear();
    modelNoteByValue_.clear();
    modelStackByValue_.clear();
    for (const CatalogEntry &entry : modelEntries)
    {
        modelDisplayByValue_.insert(entry.value, entry.display);
        modelFamilyByValue_.insert(entry.value, entry.family);
        modelModalityByValue_.insert(entry.value, entry.modality);
        modelRoleByValue_.insert(entry.value, entry.role);
        modelNoteByValue_.insert(entry.value, entry.note);
        if (!entry.metadata.isEmpty())
            modelStackByValue_.insert(entry.value, entry.metadata);
    }

    populateVideoComponentControls();

    const QString priorModel = selectedModelPath_;
    if (!priorModel.trimmed().isEmpty())
        setSelectedModel(priorModel, resolveSelectedModelDisplay(priorModel));
    else if (!modelEntries.isEmpty())
        setSelectedModel(modelEntries.first().value, modelEntries.first().display);
    else
        setSelectedModel(QString(), QString());

    const QVector<CatalogEntry> loras = scanCatalog(modelsRootDir_, QStringLiteral("loras"));
    loraDisplayByValue_.clear();
    for (const CatalogEntry &entry : loras)
        loraDisplayByValue_.insert(entry.value, entry.display);

    for (LoraStackEntry &entry : loraStack_)
    {
        if (entry.display.trimmed().isEmpty())
            entry.display = resolveLoraDisplay(entry.value);
    }

    refreshSelectedModelUi();
    rebuildLoraStackUi();

    if (workflowCombo_)
        workflowCombo_->setToolTip(currentComboValue(workflowCombo_));
}

void ImageGenerationPage::applyPreset(const QString &presetName)
{
    if (isVideoMode())
    {
        if (presetName == QStringLiteral("Portrait Detail"))
        {
            promptEdit_->setPlainText(QStringLiteral("cinematic character motion, subtle camera movement, expressive face, clean animation, coherent lighting, detailed environment"));
            negativePromptEdit_->setPlainText(QStringLiteral("flicker, morphing anatomy, broken hands, jitter, low quality, blurry, text, watermark"));
        }
        else if (presetName == QStringLiteral("Stylized Concept"))
        {
            promptEdit_->setPlainText(QStringLiteral("stylized cinematic shot, elegant motion, strong silhouette, clean temporal coherence, dramatic lighting, production concept animation"));
            negativePromptEdit_->setPlainText(QStringLiteral("muddy colors, frame flicker, unstable subject, duplicate limbs, heavy blur, low detail"));
        }
        else if (presetName == QStringLiteral("Upscale / Repair"))
        {
            promptEdit_->setPlainText(QStringLiteral("stabilize motion, restore details, preserve composition, improve temporal consistency, clean edges"));
            negativePromptEdit_->setPlainText(QStringLiteral("new objects, warped anatomy, heavy flicker, jitter, ghosting, blur"));
        }
        else
        {
            promptEdit_->setPlainText(QStringLiteral("cinematic animated scene, clean motion, strong subject read, consistent lighting, high quality video"));
            negativePromptEdit_->setPlainText(QStringLiteral("flicker, jitter, low quality, blurry, text, watermark, warped anatomy"));
        }

        trySetSelectedModelByCandidate({QStringLiteral("wan"), QStringLiteral("ltx"), QStringLiteral("hunyuan"), QStringLiteral("video"), QStringLiteral("sdxl")});
        selectComboValue(samplerCombo_, QStringLiteral("dpmpp_2m"));
        selectComboValue(schedulerCombo_, QStringLiteral("karras"));
        if (stepsSpin_)
            stepsSpin_->setValue(30);
        if (cfgSpin_)
            cfgSpin_->setValue(5.0);
        if (widthSpin_)
            widthSpin_->setValue(832);
        if (heightSpin_)
            heightSpin_->setValue(480);
        if (frameCountSpin_)
            frameCountSpin_->setValue(81);
        if (fpsSpin_)
            fpsSpin_->setValue(16);
        if (denoiseSpin_)
            denoiseSpin_->setValue(0.55);

        schedulePreviewRefresh(0);
        scheduleUiRefresh(0);
        return;
    }
    if (presetName == QStringLiteral("Portrait Detail"))
    {
        promptEdit_->setPlainText(QStringLiteral("portrait of a confident fantasy heroine, detailed face, studio rim lighting, shallow depth of field, high micro-detail"));
        negativePromptEdit_->setPlainText(QStringLiteral("blurry, low quality, extra fingers, malformed hands, watermark, text"));
        trySetSelectedModelByCandidate({QStringLiteral("sdxl"), QStringLiteral("xl")});
        selectComboValue(workflowCombo_, QStringLiteral("Portrait Detail"));
        loraStack_.clear();
        rebuildLoraStackUi();
        selectComboValue(samplerCombo_, QStringLiteral("dpmpp_2m"));
        selectComboValue(schedulerCombo_, QStringLiteral("karras"));
        stepsSpin_->setValue(35);
        cfgSpin_->setValue(6.5);
        widthSpin_->setValue(1024);
        heightSpin_->setValue(1344);
    }
    else if (presetName == QStringLiteral("Stylized Concept"))
    {
        promptEdit_->setPlainText(QStringLiteral("stylized concept art, dynamic pose, cinematic lighting, strong silhouette, clean material read, production concept render"));
        negativePromptEdit_->setPlainText(QStringLiteral("muddy colors, blurry, oversaturated, low detail, duplicate limbs"));
        trySetSelectedModelByCandidate({QStringLiteral("flux"), QStringLiteral("sdxl"), QStringLiteral("xl")});
        selectComboValue(workflowCombo_, QStringLiteral("Stylized Concept"));
        loraStack_.clear();
        rebuildLoraStackUi();
        selectComboValue(samplerCombo_, QStringLiteral("dpmpp_sde"));
        selectComboValue(schedulerCombo_, QStringLiteral("karras"));
        stepsSpin_->setValue(30);
        cfgSpin_->setValue(5.0);
        widthSpin_->setValue(1216);
        heightSpin_->setValue(832);
    }
    else if (presetName == QStringLiteral("Upscale / Repair"))
    {
        promptEdit_->setPlainText(QStringLiteral("restore detail, clean edges, improve texture fidelity, maintain original composition, crisp focus"));
        negativePromptEdit_->setPlainText(QStringLiteral("new objects, warped anatomy, duplicated features, heavy noise, blur"));
        trySetSelectedModelByCandidate({QStringLiteral("juggernaut"), QStringLiteral("sdxl"), QStringLiteral("xl")});
        selectComboValue(workflowCombo_, QStringLiteral("Upscale / Repair"));
        loraStack_.clear();
        rebuildLoraStackUi();
        if (!selectComboValue(samplerCombo_, QStringLiteral("uni_pc")))
            selectComboValue(samplerCombo_, QStringLiteral("dpmpp_2m"));
        selectComboValue(schedulerCombo_, QStringLiteral("normal"));
        stepsSpin_->setValue(24);
        cfgSpin_->setValue(5.5);
        if (denoiseSpin_)
            denoiseSpin_->setValue(0.35);
    }
    else
    {
        promptEdit_->setPlainText(QStringLiteral("high quality image, clean composition, strong subject read, balanced lighting"));
        negativePromptEdit_->setPlainText(QStringLiteral("low quality, blurry, text, watermark"));
        if (!modelDisplayByValue_.isEmpty())
            setSelectedModel(modelDisplayByValue_.firstKey(), modelDisplayByValue_.value(modelDisplayByValue_.firstKey()));
        selectComboValue(workflowCombo_, QStringLiteral("Default Canvas"));
        loraStack_.clear();
        rebuildLoraStackUi();
        selectComboValue(samplerCombo_, QStringLiteral("dpmpp_2m"));
        selectComboValue(schedulerCombo_, QStringLiteral("karras"));
        stepsSpin_->setValue(28);
        cfgSpin_->setValue(7.0);
        widthSpin_->setValue(1024);
        heightSpin_->setValue(1024);
        if (denoiseSpin_)
            denoiseSpin_->setValue(0.45);
    }

    schedulePreviewRefresh(0);
}

void ImageGenerationPage::scheduleUiRefresh(int delayMs)
{
    if (!uiRefreshTimer_)
    {
        refreshPreview();
        return;
    }

    uiRefreshTimer_->start(qBound(0, delayMs, 250));
}

void ImageGenerationPage::schedulePreviewRefresh(int delayMs)
{
    if (!previewResizeTimer_)
    {
        refreshPreview();
        return;
    }

    previewResizeTimer_->start(qBound(0, delayMs, 250));
}

void ImageGenerationPage::showImagePreviewSurface()
{
    if (mediaPreviewController_)
    {
        mediaPreviewController_->showImageSurface();
        return;
    }

    if (previewStack_ && previewImagePage_)
        previewStack_->setCurrentWidget(previewImagePage_);
}


void ImageGenerationPage::playPreviewVideo()
{
    if (mediaPreviewController_)
        mediaPreviewController_->play();
}

void ImageGenerationPage::pausePreviewVideo()
{
    if (mediaPreviewController_)
        mediaPreviewController_->pause();
}

void ImageGenerationPage::stopPreviewVideoPlayback()
{
    if (mediaPreviewController_)
        mediaPreviewController_->stopPlayback();
}

void ImageGenerationPage::restartPreviewVideo()
{
    if (mediaPreviewController_)
        mediaPreviewController_->restart();
}

void ImageGenerationPage::stepPreviewVideoFrames(int frameDelta)
{
    if (mediaPreviewController_)
        mediaPreviewController_->stepFrames(frameDelta);
}

void ImageGenerationPage::seekPreviewVideo(qint64 positionMs, bool preservePlaybackState)
{
    if (mediaPreviewController_)
        mediaPreviewController_->seek(positionMs, preservePlaybackState);
}

void ImageGenerationPage::setPreviewPlaybackRate(double rate)
{
    if (mediaPreviewController_)
        mediaPreviewController_->setPlaybackRate(rate);
}

void ImageGenerationPage::handlePreviewMediaStatus(int)
{
    updateVideoTransportUi();
}

void ImageGenerationPage::updateVideoTransportUi()
{
    if (mediaPreviewController_)
        mediaPreviewController_->updateTransportUi();
}

QString ImageGenerationPage::formatDurationLabel(qint64 milliseconds) const
{
    return spellvision::preview::MediaPreviewController::formatDurationLabel(milliseconds);
}

QString ImageGenerationPage::formatFileSizeLabel(qint64 bytes) const
{
    return spellvision::preview::MediaPreviewController::formatFileSizeLabel(bytes);
}

void ImageGenerationPage::updateVideoCaption(const QString &, const QString &)
{
    if (mediaPreviewController_)
        mediaPreviewController_->updateCaption();
}

void ImageGenerationPage::showVideoPreviewSurface(const QString &videoPath, const QString &caption)
{
    if (!mediaPreviewController_)
    {
        showImagePreviewSurface();
        return;
    }

    mediaPreviewController_->showVideoSurface(videoPath, caption);
}

void ImageGenerationPage::stopVideoPreview()
{
    if (mediaPreviewController_)
        mediaPreviewController_->clearVideoPreview();
}


void ImageGenerationPage::updatePreviewEmptyStateSizing()
{
    if (!previewLabel_)
        return;

    const bool hasRenderedPreview = !generatedPreviewPath_.trimmed().isEmpty() && QFileInfo::exists(generatedPreviewPath_.trimmed());
    const bool hasInputPreview = isImageInputMode() && inputImageEdit_ && !inputImageEdit_->text().trimmed().isEmpty();
    const bool emptyState = !busy_ && !hasRenderedPreview && !hasInputPreview;

    if (imagePreviewController_)
        imagePreviewController_->setEmptyState(emptyState);
    else if (previewLabel_->property("emptyState").toBool() != emptyState)
        previewLabel_->setProperty("emptyState", emptyState);

    if (emptyState)
    {
        const AdaptiveLayoutMode mode = currentAdaptiveLayoutMode();
        // Empty/readiness states should still feel like the main preview surface.
        // Keep the instructional copy, but do not cap the preview label into a small
        // floating island inside the canvas card. The preview surface owns the
        // available center canvas whether it is empty, waiting for a checkpoint,
        // or showing a generated result.
        previewLabel_->setMinimumHeight(mode == AdaptiveLayoutMode::Compact ? 340 : 420);
        previewLabel_->setMaximumHeight(QWIDGETSIZE_MAX);
    }
    else
    {
        previewLabel_->setMinimumHeight(0);
        previewLabel_->setMaximumHeight(QWIDGETSIZE_MAX);
    }

    repolishWidget(previewLabel_);
}

void ImageGenerationPage::refreshPreview()
{
    if (!previewLabel_)
        return;

    if (!imagePreviewController_)
    {
        previewLabel_->setPixmap(QPixmap());
        previewLabel_->setText(QStringLiteral("Preview controller unavailable."));
        return;
    }

    if (!generatedPreviewPath_.trimmed().isEmpty() && QFileInfo::exists(generatedPreviewPath_))
    {
        if (isVideoAssetPath(generatedPreviewPath_) && !isImageAssetPath(generatedPreviewPath_))
        {
            imagePreviewController_->clearLabelPixmap();
            imagePreviewController_->clearCache(false);
            imagePreviewController_->markVideoRendered(generatedPreviewPath_, generatedPreviewCaption_);
            imagePreviewController_->setEmptyState(false);

            const QString summary = generatedPreviewCaption_.trimmed().isEmpty()
                                        ? QStringLiteral("Video output ready.")
                                        : generatedPreviewCaption_.trimmed();
            showVideoPreviewSurface(generatedPreviewPath_, summary);
            return;
        }

        if (!imagePreviewController_->loadPixmapIntoCache(generatedPreviewPath_))
        {
            stopVideoPreview();
            showImagePreviewSurface();
            imagePreviewController_->showText(QStringLiteral("Loading latest output preview…"));
            schedulePreviewRefresh(120);
            return;
        }

        const QPixmap &pixmap = imagePreviewController_->cachedPixmap();
        if (!pixmap.isNull())
        {
            const QString summary = !generatedPreviewCaption_.trimmed().isEmpty()
                                        ? generatedPreviewCaption_.trimmed()
                                        : QStringLiteral("Latest result: %1\n%2 × %3")
                                              .arg(QFileInfo(generatedPreviewPath_).fileName())
                                              .arg(pixmap.width())
                                              .arg(pixmap.height());

            imagePreviewController_->showPixmap(generatedPreviewPath_, pixmap, summary);
            return;
        }
    }

    if (isImageInputMode())
    {
        const QString path = inputImageEdit_ ? inputImageEdit_->text().trimmed() : QString();
        if (!path.isEmpty() && QFileInfo::exists(path) && imagePreviewController_->loadPixmapIntoCache(path))
        {
            const QPixmap &pixmap = imagePreviewController_->cachedPixmap();
            if (!pixmap.isNull())
            {
                imagePreviewController_->showPixmap(path,
                                                    pixmap,
                                                    QStringLiteral("%1: %2\nStrength: %3    Sampler: %4    Steps: %5")
                                                        .arg(isVideoMode() ? QStringLiteral("Keyframe") : QStringLiteral("Source image"))
                                                        .arg(QFileInfo(path).fileName())
                                                        .arg(denoiseSpin_ ? QString::number(denoiseSpin_->value(), 'f', 2) : QStringLiteral("n/a"))
                                                        .arg(comboDisplayValue(samplerCombo_))
                                                        .arg(stepsSpin_ ? stepsSpin_->value() : 0));
                return;
            }
        }
    }

    stopVideoPreview();
    showImagePreviewSurface();
    imagePreviewController_->clearLabelPixmap();
    imagePreviewController_->resetTargetSize();
    imagePreviewController_->clearRenderedFingerprint();

    if (generatedPreviewPath_.trimmed().isEmpty())
        imagePreviewController_->clearCache();

    updatePreviewEmptyStateSizing();

    if (previewLabel_->property("emptyState").toBool())
    {
        const QString reason = readinessBlockReason();
        imagePreviewController_->showText(
            isImageInputMode()
                ? QStringLiteral("No source image loaded yet.\n\nDrop or browse an input image from the left rail.")
                : (reason.isEmpty()
                       ? (isVideoMode()
                              ? QStringLiteral("Text to Video ready.\n\nGenerate or queue from the focused canvas when your prompt is set.")
                              : QStringLiteral("Canvas ready.\n\nGenerate or queue from the focused canvas when your prompt is set."))
                       : QStringLiteral("Ready for setup.\n\n%1").arg(reason)));
        return;
    }

    imagePreviewController_->showText(
        busy_ ? (busyMessage_.isEmpty() ? QStringLiteral("Generation in progress…") : busyMessage_)
              : (isImageInputMode()
                     ? QStringLiteral("No source image loaded yet.\n\nDrop an image into the Input Image card or browse for one to begin.")
                     : (isVideoMode()
                            ? QStringLiteral("Text to Video ready.\n\nBuild the prompt and motion stack on the left, then press Generate or Queue.")
                            : QStringLiteral("Your generated image will appear here.\n\nBuild the prompt and stack on the left, then generate."))));
}

void ImageGenerationPage::setInputImagePath(const QString &path)
{
    if (!inputImageEdit_ || !inputDropLabel_)
        return;

    generatedPreviewPath_.clear();
    generatedPreviewCaption_.clear();
    stopVideoPreview();
    showImagePreviewSurface();
    if (imagePreviewController_)
        imagePreviewController_->clearCache();

    inputImageEdit_->setText(path);
    inputDropLabel_->setText(path.isEmpty()
                                 ? (isVideoMode() ? QStringLiteral("Drop a keyframe here or click Browse to select one.")
                                                  : QStringLiteral("Drop an image here or click Browse to select a source image."))
                                 : QStringLiteral("Current source image:\n%1").arg(path));
    updatePrimaryActionAvailability();
    updatePreviewEmptyStateSizing();
    schedulePreviewRefresh(0);
}

void ImageGenerationPage::setPreviewImage(const QString &imagePath, const QString &caption)
{
    using spellvision::generation::GenerationResultRouter;

    const GenerationResultRouter::Route route = GenerationResultRouter::routePreviewResult({
        imagePath,
        caption,
        generatedPreviewPath_,
    });

    if (route.kind == GenerationResultRouter::RouteKind::Clear)
    {
        generatedPreviewPath_.clear();
        generatedPreviewCaption_.clear();
        if (route.shouldStopVideo)
            stopVideoPreview();
        if (route.shouldShowImageSurface)
            showImagePreviewSurface();
        if (imagePreviewController_ && route.shouldClearImageCache)
            imagePreviewController_->clearCache();
        busy_ = false;
        busyMessage_.clear();
        schedulePreviewRefresh(route.previewRefreshDelayMs);
        return;
    }

    generatedPreviewPath_ = route.normalizedPath;
    generatedPreviewCaption_ = route.normalizedCaption;
    busy_ = false;
    busyMessage_.clear();

    if (route.shouldPersistOutput)
        persistLatestGeneratedOutput(route.normalizedPath);

    if (route.kind == GenerationResultRouter::RouteKind::VideoPreview)
    {
        // Video result/status messages may repeat the same output path many times.
        // Do not clear the player or force image mode for the same MP4; refreshPreview()
        // will decide whether the file is stable enough to load or can be left alone.
        if (imagePreviewController_ && route.shouldClearImageCache)
        {
            imagePreviewController_->clearCache(!route.shouldClearImageCachePreserveVideoMarker);
            if (route.shouldMarkVideoRendered)
                imagePreviewController_->markVideoRendered(generatedPreviewPath_, generatedPreviewCaption_);
        }
        schedulePreviewRefresh(route.previewRefreshDelayMs);
        return;
    }

    if (route.shouldStopVideo)
        stopVideoPreview();
    if (route.shouldShowImageSurface)
        showImagePreviewSurface();
    if (imagePreviewController_ && route.shouldClearImageCache)
        imagePreviewController_->clearCache();
    schedulePreviewRefresh(route.previewRefreshDelayMs);
}

void ImageGenerationPage::setBusy(bool busy, const QString &message)
{
    busy_ = busy;
    busyMessage_ = message.trimmed();

    if (busy)
    {
        // Starting/progress updates should not destroy an existing preview. For video,
        // tearing down QMediaPlayer here causes the same completed/partial MP4 to reload
        // on every queue/status refresh. Leave generatedPreviewPath_ and the current
        // player source intact; refreshPreview() will show the busy text only when there
        // is no usable output to show.
        const bool hasCurrentPreviewVideo = mediaPreviewController_ && !mediaPreviewController_->currentVideoPath().trimmed().isEmpty();
        if (generatedPreviewPath_.trimmed().isEmpty() && !hasCurrentPreviewVideo)
        {
            if (imagePreviewController_)
                imagePreviewController_->clearCache(false);
        }
    }

    updatePrimaryActionAvailability();
    updatePreviewEmptyStateSizing();
    if (savePresetButton_)
        savePresetButton_->setEnabled(!busy);
    if (clearButton_)
        clearButton_->setEnabled(!busy);

    schedulePreviewRefresh(busy ? 120 : 30);
}



int ImageGenerationPage::measuredContentWidth() const
{
    if (contentSplitter_)
        return contentSplitter_->contentsRect().width();

    return contentsRect().width();
}

int ImageGenerationPage::measuredRightRailWidth() const
{
    if (!rightScrollArea_)
        return 0;

    if (QWidget *viewport = rightScrollArea_->viewport())
        return std::max(0, viewport->contentsRect().width());

    return std::max(0, rightScrollArea_->contentsRect().width());
}

bool ImageGenerationPage::isCompactLayout() const
{
    return measuredContentWidth() < 1340;
}

bool ImageGenerationPage::isMediumLayout() const
{
    const int contentWidth = measuredContentWidth();
    return contentWidth >= 1340 && contentWidth < 1680;
}

ImageGenerationPage::AdaptiveLayoutMode ImageGenerationPage::currentAdaptiveLayoutMode() const
{
    if (isCompactLayout())
        return AdaptiveLayoutMode::Compact;
    if (isMediumLayout())
        return AdaptiveLayoutMode::Medium;
    return AdaptiveLayoutMode::Wide;
}

void ImageGenerationPage::setRightControlsVisible(bool visible)
{
    if (!rightScrollArea_)
        return;

    rightScrollArea_->setVisible(visible);
}

void ImageGenerationPage::applyRightPanelReflow(AdaptiveLayoutMode mode)
{
    const int railWidth = measuredRightRailWidth();
    const bool compactRail = (mode == AdaptiveLayoutMode::Compact) || railWidth < 380;
    const bool verticalActions = compactRail || railWidth < 430;

    if (stackToolsLayout_)
    {
        stackToolsLayout_->setDirection(verticalActions ? QBoxLayout::TopToBottom : QBoxLayout::LeftToRight);
        stackToolsLayout_->setSpacing(verticalActions ? 6 : 8);
    }

    const int buttonHeight = verticalActions ? 38 : 36;
    if (openModelsButton_)
    {
        openModelsButton_->setMinimumHeight(buttonHeight);
        openModelsButton_->setMinimumWidth(0);
    }
    if (openWorkflowsButton_)
    {
        openWorkflowsButton_->setMinimumHeight(buttonHeight);
        openWorkflowsButton_->setMinimumWidth(0);
    }
}

void ImageGenerationPage::applyAdaptiveSplitterSizes(AdaptiveLayoutMode mode)
{
    if (!contentSplitter_)
        return;

    if (mode == AdaptiveLayoutMode::Compact)
    {
        if (rightScrollArea_ && rightScrollArea_->isVisible())
            contentSplitter_->setSizes({345, 690, 390});
        else
            contentSplitter_->setSizes({360, 900, 0});
        return;
    }

    if (mode == AdaptiveLayoutMode::Medium)
    {
        contentSplitter_->setSizes({385, 760, 425});
        return;
    }

    contentSplitter_->setSizes({395, 850, 465});
}

void ImageGenerationPage::updateAdaptiveLayout()
{
    const AdaptiveLayoutMode mode = currentAdaptiveLayoutMode();
    adaptiveCompact_ = mode == AdaptiveLayoutMode::Compact;

    if (mode != lastAdaptiveLayoutMode_)
    {
        if (mode == AdaptiveLayoutMode::Compact)
            rightControlsVisible_ = false;
        else if (lastAdaptiveLayoutMode_ == AdaptiveLayoutMode::Compact)
            rightControlsVisible_ = true;

        lastAdaptiveLayoutMode_ = mode;
        QTimer::singleShot(0, this, [this]() {
            if (leftScrollArea_ && leftScrollArea_->verticalScrollBar())
                leftScrollArea_->verticalScrollBar()->setValue(0);
        });
    }

    if (leftScrollArea_)
    {
        if (mode == AdaptiveLayoutMode::Compact)
        {
            leftScrollArea_->setMinimumWidth(330);
            leftScrollArea_->setMaximumWidth(390);
        }
        else if (mode == AdaptiveLayoutMode::Medium)
        {
            leftScrollArea_->setMinimumWidth(360);
            leftScrollArea_->setMaximumWidth(420);
        }
        else
        {
            leftScrollArea_->setMinimumWidth(380);
            leftScrollArea_->setMaximumWidth(440);
        }
    }

    const bool showRightControls = (mode != AdaptiveLayoutMode::Compact) || rightControlsVisible_;
    setRightControlsVisible(showRightControls);

    if (rightScrollArea_)
    {
        if (mode == AdaptiveLayoutMode::Compact)
        {
            rightScrollArea_->setMinimumWidth(360);
            rightScrollArea_->setMaximumWidth(440);
        }
        else if (mode == AdaptiveLayoutMode::Medium)
        {
            rightScrollArea_->setMinimumWidth(390);
            rightScrollArea_->setMaximumWidth(470);
        }
        else
        {
            rightScrollArea_->setMinimumWidth(410);
            rightScrollArea_->setMaximumWidth(500);
        }
    }

    applyRightPanelReflow(mode);

    const int leftRailWidth = leftScrollArea_ ? leftScrollArea_->viewport()->width() : 0;
    const int leftRailHeight = leftScrollArea_ ? leftScrollArea_->viewport()->height() : height();
    const bool narrowLeftRail = (mode == AdaptiveLayoutMode::Compact) || leftRailWidth < 390;
    const bool wideLeftRail = (mode == AdaptiveLayoutMode::Wide) && leftRailWidth >= 410;
    const bool constrainedLeftHeight = leftRailHeight > 0 && leftRailHeight < 900;
    const bool veryConstrainedLeftHeight = leftRailHeight > 0 && leftRailHeight < 780;
    const bool shortGenerationRail = leftRailHeight > 0 && leftRailHeight < 960;
    Q_UNUSED(veryConstrainedLeftHeight);
    Q_UNUSED(shortGenerationRail);

    auto configureStackedGroup = [narrowLeftRail](QBoxLayout *layout) {
        if (!layout)
            return;
        layout->setDirection(QBoxLayout::TopToBottom);
        layout->setSpacing(narrowLeftRail ? 3 : 4);
    };
    auto configureAdaptivePair = [wideLeftRail, constrainedLeftHeight](QBoxLayout *layout) {
        if (!layout)
            return;
        const bool useTwoColumns = wideLeftRail && !constrainedLeftHeight;
        layout->setDirection(useTwoColumns ? QBoxLayout::LeftToRight : QBoxLayout::TopToBottom);
        layout->setSpacing(useTwoColumns ? 8 : 3);
    };

    configureStackedGroup(samplerSchedulerLayout_);
    configureAdaptivePair(sizeLayout_);
    configureAdaptivePair(stepsCfgLayout_);
    configureStackedGroup(seedBatchLayout_);

    if (QFrame *quickControlsCard = findChild<QFrame *>(QStringLiteral("QuickControlsCard")))
        quickControlsCard->setToolTip(QStringLiteral("High-frequency generation controls stay prioritized in the left inspector."));

    if (QFrame *outputQueueCard = findChild<QFrame *>(QStringLiteral("OutputQueueCard")))
    {
        const bool outputAutoCollapsed = true;
        const bool collapseOutput = outputAutoCollapsed && !outputQueueForceOpen_;
        outputQueueCard->setMinimumHeight(collapseOutput ? 58 : 0);
        outputQueueCard->setMaximumHeight(collapseOutput ? 58 : QWIDGETSIZE_MAX);
        outputQueueCard->setToolTip(collapseOutput
            ? QStringLiteral("Output / Queue is collapsed to protect prompt space. Click Open to edit batch, prefix, and output folder.")
            : QString());

        const auto bodyRows = outputQueueCard->findChildren<QWidget *>(QStringLiteral("OutputQueueBodyRow"));
        for (QWidget *body : bodyRows)
            body->setVisible(!collapseOutput);

        if (QWidget *label = outputQueueCard->findChild<QWidget *>(QStringLiteral("OutputQueueBodyLabel")))
            label->setVisible(!collapseOutput);
        if (QWidget *hint = outputQueueCard->findChild<QWidget *>(QStringLiteral("OutputQueueBodyHint")))
            hint->setVisible(!collapseOutput);

        if (outputQueueToggleButton_)
        {
            outputQueueToggleButton_->setVisible(true);
            outputQueueToggleButton_->setMinimumWidth(collapseOutput ? 72 : 74);
            outputQueueToggleButton_->setText(collapseOutput ? QStringLiteral("Open") : QStringLiteral("Close"));
            outputQueueToggleButton_->setToolTip(collapseOutput
                ? QStringLiteral("Open Output / Queue controls.")
                : QStringLiteral("Close Output / Queue controls and return space to the rail."));
        }
    }

    if (QFrame *advancedCard = findChild<QFrame *>(QStringLiteral("AdvancedCard")))
    {
        const bool advancedAutoCollapsed = true;
        const bool collapseAdvanced = advancedAutoCollapsed && !advancedForceOpen_;
        advancedCard->setMinimumHeight(collapseAdvanced ? 58 : 0);
        advancedCard->setMaximumHeight(collapseAdvanced ? 58 : QWIDGETSIZE_MAX);
        advancedCard->setToolTip(collapseAdvanced
            ? QStringLiteral("Advanced controls are collapsed by default to protect prompt space. Click Open to edit mode-specific controls.")
            : QString());

        const auto bodyRows = advancedCard->findChildren<QWidget *>(QStringLiteral("AdvancedBodyRow"));
        for (QWidget *body : bodyRows)
            body->setVisible(!collapseAdvanced);
        if (QWidget *hint = advancedCard->findChild<QWidget *>(QStringLiteral("AdvancedBodyHint")))
            hint->setVisible(!collapseAdvanced);

        if (advancedToggleButton_)
        {
            advancedToggleButton_->setVisible(advancedCard->isVisible());
            advancedToggleButton_->setMinimumWidth(collapseAdvanced ? 72 : 74);
            advancedToggleButton_->setText(collapseAdvanced ? QStringLiteral("Open") : QStringLiteral("Close"));
            advancedToggleButton_->setToolTip(collapseAdvanced
                ? QStringLiteral("Open Advanced controls.")
                : QStringLiteral("Close Advanced controls and return space to the rail."));
        }
    }

    if (toggleControlsButton_)
    {
        toggleControlsButton_->setVisible(mode == AdaptiveLayoutMode::Compact);
        toggleControlsButton_->setText(showRightControls ? QStringLiteral("Hide Controls")
                                                         : QStringLiteral("Show Controls"));
    }

    if (promptEdit_)
    {
        const bool shortRail = leftRailHeight > 0 && leftRailHeight < 760;
        const int promptMin = shortRail ? (isVideoMode() ? 110 : 128)
                                        : (mode == AdaptiveLayoutMode::Wide ? (isVideoMode() ? 132 : 156)
                                                                           : (isVideoMode() ? 118 : 140));
        promptEdit_->setMinimumHeight(promptMin);
        promptEdit_->setMaximumHeight(promptMin + 18);
    }
    if (negativePromptEdit_)
    {
        const bool shortRail = leftRailHeight > 0 && leftRailHeight < 760;
        const int negativeMin = shortRail ? 68 : (mode == AdaptiveLayoutMode::Wide ? 84 : 76);
        negativePromptEdit_->setMinimumHeight(negativeMin);
        negativePromptEdit_->setMaximumHeight(negativeMin + 16);
    }

    updatePreviewEmptyStateSizing();
    applyAdaptiveSplitterSizes(mode);
}

void ImageGenerationPage::applyWorkerMessage(const QJsonObject &payload)
{
    spellvision::generation::GenerationStatusController::Bindings bindings;
    bindings.setBusy = [this](bool busy, const QString &message) {
        setBusy(busy, message);
    };
    bindings.routeOutput = [this](const QString &outputPath, const QString &caption) {
        setPreviewImage(outputPath, caption);
    };
    bindings.showProblem = [this](const QString &text) {
        const QString trimmed = text.trimmed();
        if (trimmed.isEmpty())
            return;

        if (!readinessHintLabel_)
            return;

        readinessHintLabel_->setText(trimmed);
        readinessHintLabel_->setToolTip(trimmed);
        readinessHintLabel_->setVisible(true);
    };

    spellvision::generation::GenerationStatusController::applyWorkerPayload(payload, bindings);
}

void ImageGenerationPage::setWorkspaceTelemetry(const QString &runtime,
                                                const QString &queue,
                                                const QString &model,
                                                const QString &lora,
                                                int progressPercent,
                                                const QString &progressText)
{
    Q_UNUSED(runtime);
    Q_UNUSED(queue);
    Q_UNUSED(model);
    Q_UNUSED(lora);
    Q_UNUSED(progressPercent);
    Q_UNUSED(progressText);
}

void ImageGenerationPage::applyHomeStarter(const QString &title,
                                           const QString &subtitle,
                                           const QString &sourceLabel)
{
    QStringList lines;
    const QString trimmedTitle = title.trimmed();
    const QString trimmedSubtitle = subtitle.trimmed();
    const QString trimmedSource = sourceLabel.trimmed();

    if (!trimmedTitle.isEmpty())
        lines << trimmedTitle;
    if (!trimmedSubtitle.isEmpty())
        lines << trimmedSubtitle;

    const QString starterText = lines.join(QStringLiteral("\n")).trimmed();
    if (!starterText.isEmpty() && promptEdit_)
        promptEdit_->setPlainText(starterText);

    if (presetCombo_)
        selectComboValue(presetCombo_, QStringLiteral("Balanced"));

    if (workflowCombo_ && trimmedSource.contains(QStringLiteral("workflow"), Qt::CaseInsensitive))
        selectComboValue(workflowCombo_, QStringLiteral("Default Canvas"));

    if (inputImageEdit_ && isImageInputMode() && inputImageEdit_->text().trimmed().isEmpty())
        inputDropLabel_->setText(QStringLiteral("Starter selected from Home. Add a source image or keyframe to continue."));

    generatedPreviewCaption_.clear();
    busy_ = false;
    busyMessage_.clear();
    workflowDraftSource_.clear();
    workflowDraftWarnings_.clear();
    workflowDraftBlocking_ = false;
    updateDraftCompatibilityUi();
    updatePrimaryActionAvailability();

    scheduleUiRefresh(0);
    schedulePreviewRefresh(0);
}


QString ImageGenerationPage::selectedModelValue() const
{
    return selectedModelPath_.trimmed();
}

QString ImageGenerationPage::selectedLoraValue() const
{
    return resolveLoraValue();
}

bool ImageGenerationPage::workflowDraftCanSubmit() const
{
    return !workflowDraftBlocking_;
}

void ImageGenerationPage::applyWorkflowDraft(const QJsonObject &draft)
{
    workflowDraftSource_ = draft.value(QStringLiteral("source_name")).toString().trimmed();
    workflowDraftProfilePath_ = draft.value(QStringLiteral("source_profile_path")).toString().trimmed();
    workflowDraftWorkflowPath_ = draft.value(QStringLiteral("source_workflow_path")).toString().trimmed();
    workflowDraftCompiledPromptPath_ = draft.value(QStringLiteral("compiled_prompt_path")).toString().trimmed();
    workflowDraftBackend_ = draft.value(QStringLiteral("backend")).toString().trimmed();
    workflowDraftMediaType_ = draft.value(QStringLiteral("media_type")).toString().trimmed();
    workflowDraftWarnings_.clear();
    workflowDraftBlocking_ = false;

    if (promptEdit_)
        promptEdit_->setPlainText(draft.value(QStringLiteral("prompt")).toString());
    if (negativePromptEdit_)
        negativePromptEdit_->setPlainText(draft.value(QStringLiteral("negative_prompt")).toString());

    if (presetCombo_)
        selectComboValue(presetCombo_, QStringLiteral("Custom"));

    const QString checkpoint = draft.value(QStringLiteral("checkpoint")).toString().trimmed();
    const QString checkpointDisplay = draft.value(QStringLiteral("checkpoint_display")).toString().trimmed();
    bool checkpointMatched = checkpoint.isEmpty();
    if (!checkpoint.isEmpty())
        checkpointMatched = trySetSelectedModelByCandidate({checkpoint, checkpointDisplay, shortDisplayFromValue(checkpoint)});

    const QString sampler = draft.value(QStringLiteral("sampler")).toString().trimmed();
    if (!sampler.isEmpty())
    {
        if (!selectComboValue(samplerCombo_, sampler))
            selectComboByContains(samplerCombo_, {sampler});
    }

    const QString scheduler = draft.value(QStringLiteral("scheduler")).toString().trimmed();
    if (!scheduler.isEmpty())
    {
        if (!selectComboValue(schedulerCombo_, scheduler))
            selectComboByContains(schedulerCombo_, {scheduler});
    }

    const int steps = draft.value(QStringLiteral("steps")).toInt(0);
    if (steps > 0 && stepsSpin_)
        stepsSpin_->setValue(steps);

    const double cfg = draft.value(QStringLiteral("cfg")).toDouble(0.0);
    if (cfg > 0.0 && cfgSpin_)
        cfgSpin_->setValue(cfg);

    const qlonglong seed = draft.value(QStringLiteral("seed")).toVariant().toLongLong();
    if (seed > 0 && seedSpin_)
        seedSpin_->setValue(static_cast<int>(qMin<qlonglong>(seed, 999999999LL)));

    const int width = draft.value(QStringLiteral("width")).toInt(0);
    if (width > 0 && widthSpin_)
        widthSpin_->setValue(width);

    const int height = draft.value(QStringLiteral("height")).toInt(0);
    if (height > 0 && heightSpin_)
        heightSpin_->setValue(height);

    const int frames = draft.value(QStringLiteral("frames")).toInt(draft.value(QStringLiteral("num_frames")).toInt(0));
    if (frames > 0 && frameCountSpin_)
        frameCountSpin_->setValue(frames);

    const int fps = draft.value(QStringLiteral("fps")).toInt(0);
    if (fps > 0 && fpsSpin_)
        fpsSpin_->setValue(fps);

    if (isImageInputMode())
    {
        const QString inputImage = draft.value(QStringLiteral("input_image")).toString().trimmed();
        if (!inputImage.isEmpty())
            setInputImagePath(inputImage);
    }

    loraStack_.clear();
    const QJsonArray loraStack = draft.value(QStringLiteral("lora_stack")).toArray();
    int matchedLoras = 0;
    for (const QJsonValue &value : loraStack)
    {
        if (!value.isObject())
            continue;
        const QJsonObject obj = value.toObject();
        const QString loraName = obj.value(QStringLiteral("name")).toString().trimmed();
        const QString loraDisplay = obj.value(QStringLiteral("display")).toString().trimmed();
        const double loraStrength = obj.value(QStringLiteral("strength")).toDouble(1.0);
        const bool enabled = obj.value(QStringLiteral("enabled")).toBool(true);
        if (tryAddLoraByCandidate({loraName, loraDisplay, shortDisplayFromValue(loraName)}, loraStrength, enabled))
            ++matchedLoras;
        else if (!loraName.isEmpty())
            workflowDraftWarnings_.push_back(QStringLiteral("Imported LoRA could not be matched in the current LoRA catalog: %1").arg(loraName));
    }

    if (!checkpointMatched)
    {
        workflowDraftBlocking_ = true;
        workflowDraftWarnings_.push_back(QStringLiteral("Imported checkpoint could not be matched in the current model catalog: %1").arg(checkpoint));
    }

    if (matchedLoras == 0 && !loraStack.isEmpty())
        workflowDraftBlocking_ = true;

    const bool safeToSubmit = draft.value(QStringLiteral("safe_to_submit")).toBool(true);
    const QJsonArray draftWarnings = draft.value(QStringLiteral("warnings")).toArray();
    for (const QJsonValue &warning : draftWarnings)
    {
        const QString text = warning.toString().trimmed();
        if (!text.isEmpty())
            workflowDraftWarnings_.push_back(text);
    }
    if (!safeToSubmit)
        workflowDraftBlocking_ = true;

    rebuildLoraStackUi();
    updateDraftCompatibilityUi();
    updatePrimaryActionAvailability();
    scheduleUiRefresh(0);
    schedulePreviewRefresh(0);
}

void ImageGenerationPage::updateAssetIntelligenceUi()
{
    if (!modelsRootLabel_)
        return;

    const QString modelDisplay = selectedModelPath_.trimmed().isEmpty()
        ? QStringLiteral("none selected")
        : (selectedModelDisplay_.trimmed().isEmpty() ? shortDisplayFromValue(selectedModelPath_) : selectedModelDisplay_.trimmed());

    const QString rawFamily = modelFamilyByValue_.value(selectedModelPath_).trimmed();
    const QString rawModality = modelModalityByValue_.value(selectedModelPath_, isVideoMode() ? QStringLiteral("video") : QStringLiteral("image"));
    const QString rawRole = modelRoleByValue_.value(selectedModelPath_).trimmed();
    const QString stackNote = modelNoteByValue_.value(selectedModelPath_).trimmed();
    const QJsonObject stackObject = isVideoMode() ? selectedVideoStackForPayload() : modelStackByValue_.value(selectedModelPath_);
    const QString modelPathLower = selectedModelPath_.toLower();
    QString modelFamily = QStringLiteral("unknown");
    if (!rawFamily.isEmpty())
        modelFamily = isVideoMode() ? humanVideoFamily(rawFamily) : humanImageFamily(rawFamily);
    else if (modelPathLower.contains(QStringLiteral("pony")))
        modelFamily = QStringLiteral("Pony family");
    else if (modelPathLower.contains(QStringLiteral("illustri")))
        modelFamily = QStringLiteral("Illustrious family");
    else if (modelPathLower.contains(QStringLiteral("sdxl")) || modelPathLower.contains(QStringLiteral("xl")))
        modelFamily = QStringLiteral("SDXL / XL family");
    else if (modelPathLower.contains(QStringLiteral("flux")))
        modelFamily = QStringLiteral("Flux family");
    else if (modelPathLower.contains(QStringLiteral("wan")))
        modelFamily = QStringLiteral("WAN video family");
    else if (modelPathLower.contains(QStringLiteral("zimage")) || modelPathLower.contains(QStringLiteral("z-image")))
        modelFamily = QStringLiteral("Z-Image family");
    else if (!modelPathLower.trimmed().isEmpty())
        modelFamily = QStringLiteral("custom / uncategorized");

    QString stackSummary = stackNote.isEmpty() ? QStringLiteral("—") : stackNote;
    if (!stackObject.isEmpty())
    {
        const QString kind = stackObject.value(QStringLiteral("stack_kind")).toString().trimmed();
        const bool readyStack = stackObject.value(QStringLiteral("stack_ready")).toBool(false);
        const QJsonArray missing = stackObject.value(QStringLiteral("missing_parts")).toArray();
        QStringList missingParts;
        for (const QJsonValue &item : missing)
            missingParts << item.toString();
        stackSummary = QStringLiteral("%1 • %2").arg(kind.isEmpty() ? QStringLiteral("stack") : kind, readyStack ? QStringLiteral("resolved") : QStringLiteral("partial"));
        if (!missingParts.isEmpty())
            stackSummary += QStringLiteral(" • missing %1").arg(missingParts.join(QStringLiteral(", ")));
    }

    const int enabledLoras = ModelStackState::enabledLoraCount(loraStack_);

    const QString workflowName = workflowCombo_ ? currentComboValue(workflowCombo_) : QStringLiteral("Default Canvas");
    const QString draftState = workflowDraftSource_.trimmed().isEmpty()
        ? QStringLiteral("none")
        : (workflowDraftBlocking_ ? QStringLiteral("review required") : QStringLiteral("ready"));
    const QString warningState = workflowDraftWarnings_.isEmpty()
        ? QStringLiteral("none")
        : QStringLiteral("%1 review note%2").arg(workflowDraftWarnings_.size()).arg(workflowDraftWarnings_.size() == 1 ? QString() : QStringLiteral("s"));
    const QString rootText = modelsRootDir_.trimmed().isEmpty()
        ? QStringLiteral("not configured")
        : QDir::toNativeSeparators(modelsRootDir_);
    const QString blockReason = readinessBlockReason();
    const bool ready = blockReason.isEmpty();
    const QString readiness = ready ? QStringLiteral("ready") : blockReason;

    auto row = [ready](const QString &label, const QString &value, bool readinessRow = false) {
        const QString valueClass = readinessRow ? (ready ? QStringLiteral("v good") : QStringLiteral("v bad")) : QStringLiteral("v");
        return QStringLiteral("<tr><td class='k'>%1</td><td class='%2'>%3</td></tr>")
            .arg(label.toHtmlEscaped(), valueClass, value.toHtmlEscaped());
    };

    QString html;
    html += QStringLiteral("<style>"
                           "table{border-collapse:collapse;width:100%;}"
                           "td{padding:2px 0;vertical-align:top;}"
                           ".k{opacity:.74;font-weight:800;white-space:nowrap;padding-right:12px;}"
                           ".v{font-weight:650;}"
                           ".good{color:#9ff5ca;}"
                           ".bad{color:#ffd1dc;}"
                           "</style>");
    html += QStringLiteral("<table>");
    html += row(isVideoMode() ? QStringLiteral("Model Stack") : QStringLiteral("Checkpoint"), modelDisplay);
    html += row(QStringLiteral("Family"), modelFamily);
    if (isVideoMode())
    {
        const QString stackMode = effectiveVideoStackMode();
        html += row(QStringLiteral("Modality"), rawModality.trimmed().isEmpty() ? QStringLiteral("video") : rawModality);
        html += row(QStringLiteral("Stack Role"), rawRole.trimmed().isEmpty() ? QStringLiteral("native video") : rawRole);
        html += row(QStringLiteral("Stack Mode"), stackMode == QStringLiteral("wan_dual_noise") ? QStringLiteral("WAN dual-noise") : QStringLiteral("single model"));
        html += row(QStringLiteral("Stack"), stackSummary);
        html += row(QStringLiteral("Primary"), shortDisplayFromValue(stackObject.value(QStringLiteral("primary_path")).toString()));
        if (stackMode == QStringLiteral("wan_dual_noise"))
        {
            html += row(QStringLiteral("High Noise"), shortDisplayFromValue(stackObject.value(QStringLiteral("high_noise_path")).toString().trimmed().isEmpty() ? stackObject.value(QStringLiteral("high_noise_model_path")).toString() : stackObject.value(QStringLiteral("high_noise_path")).toString()));
            html += row(QStringLiteral("Low Noise"), shortDisplayFromValue(stackObject.value(QStringLiteral("low_noise_path")).toString().trimmed().isEmpty() ? stackObject.value(QStringLiteral("low_noise_model_path")).toString() : stackObject.value(QStringLiteral("low_noise_path")).toString()));
            html += row(QStringLiteral("Wan Split"), wanSplitCombo_ ? currentComboValue(wanSplitCombo_) : QStringLiteral("auto"));
        }
        html += row(QStringLiteral("Text Encoder"), shortDisplayFromValue(stackObject.value(QStringLiteral("text_encoder_path")).toString()));
        html += row(QStringLiteral("VAE"), shortDisplayFromValue(stackObject.value(QStringLiteral("vae_path")).toString()));
        const QString vision = stackObject.value(QStringLiteral("clip_vision_path")).toString().trimmed();
        if (!vision.isEmpty())
            html += row(QStringLiteral("Vision Encoder"), shortDisplayFromValue(vision));
        if (stackMode == QStringLiteral("wan_dual_noise"))
        {
            html += row(QStringLiteral("High Steps"), highNoiseStepsSpin_ ? QString::number(highNoiseStepsSpin_->value()) : QStringLiteral("14"));
            html += row(QStringLiteral("Low Steps"), lowNoiseStepsSpin_ ? QString::number(lowNoiseStepsSpin_->value()) : QStringLiteral("14"));
            html += row(QStringLiteral("Split Step"), splitStepSpin_ ? QString::number(splitStepSpin_->value()) : QStringLiteral("14"));
            html += row(QStringLiteral("High Shift"), highNoiseShiftSpin_ ? QString::number(highNoiseShiftSpin_->value(), 'f', 2) : QStringLiteral("5.00"));
            html += row(QStringLiteral("Low Shift"), lowNoiseShiftSpin_ ? QString::number(lowNoiseShiftSpin_->value(), 'f', 2) : QStringLiteral("5.00"));
            html += row(QStringLiteral("VAE Tiling"), enableVaeTilingCheck_ && enableVaeTilingCheck_->isChecked() ? QStringLiteral("enabled") : QStringLiteral("disabled"));
        }
    }
    html += row(QStringLiteral("LoRAs"), QStringLiteral("%1 stack / %2 enabled").arg(loraStack_.size()).arg(enabledLoras));
    html += row(QStringLiteral("Workflow"), workflowName.trimmed().isEmpty() ? QStringLiteral("Default Canvas") : workflowName);
    if (isVideoMode())
    {
        const int frames = frameCountSpin_ ? frameCountSpin_->value() : 0;
        const int fps = fpsSpin_ ? fpsSpin_->value() : 0;
        const double seconds = fps > 0 ? static_cast<double>(frames) / static_cast<double>(fps) : 0.0;
        html += row(QStringLiteral("Timing"), QStringLiteral("%1 frames @ %2 fps (%3s)").arg(frames).arg(fps).arg(QString::number(seconds, 'f', 1)));
        html += row(QStringLiteral("Backend"), hasVideoWorkflowBinding() ? QStringLiteral("Imported workflow") : QStringLiteral("Native video model"));
    }
    html += row(QStringLiteral("Draft"), draftState);
    html += row(QStringLiteral("Review"), warningState);
    html += row(QStringLiteral("Readiness"), readiness, true);
    html += row(QStringLiteral("Assets"), rootText);
    html += QStringLiteral("</table>");

    QStringList plain;
    plain << QStringLiteral("%1: %2").arg(isVideoMode() ? QStringLiteral("Model Stack") : QStringLiteral("Checkpoint"), modelDisplay);
    plain << QStringLiteral("Family: %1").arg(modelFamily);
    if (isVideoMode())
    {
        const QString stackMode = effectiveVideoStackMode();
        plain << QStringLiteral("Modality: %1").arg(rawModality.trimmed().isEmpty() ? QStringLiteral("video") : rawModality);
        plain << QStringLiteral("Stack Role: %1").arg(rawRole.trimmed().isEmpty() ? QStringLiteral("native video") : rawRole);
        plain << QStringLiteral("Stack Mode: %1").arg(stackMode == QStringLiteral("wan_dual_noise") ? QStringLiteral("WAN dual-noise") : QStringLiteral("single model"));
        plain << QStringLiteral("Stack: %1").arg(stackSummary);
        plain << QStringLiteral("Primary: %1").arg(stackObject.value(QStringLiteral("primary_path")).toString());
        if (stackMode == QStringLiteral("wan_dual_noise"))
        {
            plain << QStringLiteral("High Noise: %1").arg(stackObject.value(QStringLiteral("high_noise_path")).toString().trimmed().isEmpty() ? stackObject.value(QStringLiteral("high_noise_model_path")).toString() : stackObject.value(QStringLiteral("high_noise_path")).toString());
            plain << QStringLiteral("Low Noise: %1").arg(stackObject.value(QStringLiteral("low_noise_path")).toString().trimmed().isEmpty() ? stackObject.value(QStringLiteral("low_noise_model_path")).toString() : stackObject.value(QStringLiteral("low_noise_path")).toString());
            plain << QStringLiteral("Wan Split: %1").arg(wanSplitCombo_ ? currentComboValue(wanSplitCombo_) : QStringLiteral("auto"));
        }
        plain << QStringLiteral("Text Encoder: %1").arg(stackObject.value(QStringLiteral("text_encoder_path")).toString());
        plain << QStringLiteral("VAE: %1").arg(stackObject.value(QStringLiteral("vae_path")).toString());
        if (!stackObject.value(QStringLiteral("clip_vision_path")).toString().trimmed().isEmpty())
            plain << QStringLiteral("Vision Encoder: %1").arg(stackObject.value(QStringLiteral("clip_vision_path")).toString());
        if (stackMode == QStringLiteral("wan_dual_noise"))
        {
            plain << QStringLiteral("High Steps: %1").arg(highNoiseStepsSpin_ ? QString::number(highNoiseStepsSpin_->value()) : QStringLiteral("14"));
            plain << QStringLiteral("Low Steps: %1").arg(lowNoiseStepsSpin_ ? QString::number(lowNoiseStepsSpin_->value()) : QStringLiteral("14"));
            plain << QStringLiteral("Split Step: %1").arg(splitStepSpin_ ? QString::number(splitStepSpin_->value()) : QStringLiteral("14"));
            plain << QStringLiteral("High Shift: %1").arg(highNoiseShiftSpin_ ? QString::number(highNoiseShiftSpin_->value(), 'f', 2) : QStringLiteral("5.00"));
            plain << QStringLiteral("Low Shift: %1").arg(lowNoiseShiftSpin_ ? QString::number(lowNoiseShiftSpin_->value(), 'f', 2) : QStringLiteral("5.00"));
            plain << QStringLiteral("VAE Tiling: %1").arg(enableVaeTilingCheck_ && enableVaeTilingCheck_->isChecked() ? QStringLiteral("enabled") : QStringLiteral("disabled"));
        }
    }
    plain << QStringLiteral("LoRAs: %1 in stack / %2 enabled").arg(loraStack_.size()).arg(enabledLoras);
    plain << QStringLiteral("Workflow: %1").arg(workflowName.trimmed().isEmpty() ? QStringLiteral("Default Canvas") : workflowName);
    if (isVideoMode())
    {
        const int frames = frameCountSpin_ ? frameCountSpin_->value() : 0;
        const int fps = fpsSpin_ ? fpsSpin_->value() : 0;
        const double seconds = fps > 0 ? static_cast<double>(frames) / static_cast<double>(fps) : 0.0;
        plain << QStringLiteral("Timing: %1 frames @ %2 fps (%3s)").arg(frames).arg(fps).arg(QString::number(seconds, 'f', 1));
        plain << QStringLiteral("Backend: %1").arg(hasVideoWorkflowBinding() ? QStringLiteral("Imported workflow") : QStringLiteral("Native video model"));
    }
    plain << QStringLiteral("Draft: %1").arg(draftState);
    plain << QStringLiteral("Review: %1").arg(warningState);
    plain << QStringLiteral("Readiness: %1").arg(readiness);
    plain << QStringLiteral("Assets: %1").arg(rootText);

    modelsRootLabel_->setText(html);
    modelsRootLabel_->setToolTip(plain.join(QStringLiteral("\n")));
}

void ImageGenerationPage::updateDraftCompatibilityUi()
{
    QStringList lines;
    if (!workflowDraftSource_.isEmpty())
        lines << QStringLiteral("Loaded from workflow: %1").arg(workflowDraftSource_);
    for (const QString &warning : workflowDraftWarnings_)
    {
        if (!warning.trimmed().isEmpty())
            lines << warning.trimmed();
    }
    const QString tooltip = lines.join(QStringLiteral("\n"));

    if (!tooltip.isEmpty())
    {
        if (generateButton_)
            generateButton_->setToolTip(tooltip);
        if (queueButton_)
            queueButton_->setToolTip(tooltip);
        if (openWorkflowsButton_)
            openWorkflowsButton_->setToolTip(tooltip);
    }

    updateAssetIntelligenceUi();
}

bool ImageGenerationPage::hasReadyModelSelection() const
{
    if (!selectedModelValue().trimmed().isEmpty())
        return true;

    if (isVideoMode())
    {
        const QJsonObject stack = selectedVideoStackForPayload();
        const QString stackMode = stack.value(QStringLiteral("stack_mode")).toString().trimmed();
        const QString primary = stack.value(QStringLiteral("primary_path")).toString().trimmed();
        const QString highNoise = stack.value(QStringLiteral("high_noise_path")).toString().trimmed();
        const QString lowNoise = stack.value(QStringLiteral("low_noise_path")).toString().trimmed();

        if (stackMode == QStringLiteral("wan_dual_noise"))
        {
            if (!highNoise.isEmpty() || !lowNoise.isEmpty() || !primary.isEmpty())
                return true;
        }
        else if (!primary.isEmpty())
        {
            return true;
        }

        // Imported video workflow drafts may carry their own model stack inside the
        // compiled Comfy prompt. Native video generation still requires an explicit
        // model selection, but workflow-bound generation does not.
        return hasVideoWorkflowBinding();
    }

    return false;
}

bool ImageGenerationPage::hasRequiredGenerationInput() const
{
    if (!isImageInputMode())
        return true;

    return inputImageEdit_ && !inputImageEdit_->text().trimmed().isEmpty();
}

bool ImageGenerationPage::hasVideoWorkflowBinding() const
{
    if (!isVideoMode())
        return true;

    if (!workflowDraftProfilePath_.trimmed().isEmpty())
        return true;
    if (!workflowDraftWorkflowPath_.trimmed().isEmpty())
        return true;
    if (!workflowDraftCompiledPromptPath_.trimmed().isEmpty())
        return true;

    return false;
}

QString ImageGenerationPage::readinessBlockReason() const
{
    if (busy_)
        return busyMessage_.isEmpty() ? QStringLiteral("Generation in progress.") : busyMessage_;

    if (!hasReadyModelSelection())
    {
        if (isVideoMode())
            return QStringLiteral("Select a video model stack or open a video workflow draft.");
        return QStringLiteral("Select a checkpoint to generate.");
    }

    if (!hasRequiredGenerationInput())
        return isVideoMode()
                   ? QStringLiteral("Add an input keyframe to generate.")
                   : QStringLiteral("Add an input image to generate.");

    if (isVideoMode() && !hasVideoWorkflowBinding())
    {
        const QJsonObject stack = selectedVideoStackForPayload();
        QStringList missing;
        for (const QJsonValue &value : stack.value(QStringLiteral("missing_parts")).toArray())
        {
            const QString item = value.toString().trimmed();
            if (!item.isEmpty())
                missing << item;
        }
        if (!missing.isEmpty())
            return QStringLiteral("Complete the video stack: missing %1.").arg(missing.join(QStringLiteral(", ")));
    }

    if (workflowDraftBlocking_)
        return QStringLiteral("Resolve workflow draft review items.");


    if (isVideoMode())
    {
        const QJsonObject videoPayload = buildRequestPayload();
        const QString videoBlockReason = spellvision::generation::VideoReadinessPresenter::blockingMessage(videoPayload);
        if (!videoBlockReason.isEmpty())
            return videoBlockReason;
    }

    return QString();
}

void ImageGenerationPage::applyActionReadinessStyle(QPushButton *button, bool enabled, const QString &tooltip)
{
    if (!button)
        return;

    const bool blocked = !enabled;
    if (button->property("readinessBlocked").toBool() != blocked)
        button->setProperty("readinessBlocked", blocked);

    // Keep action buttons clickable when a request is blocked so the click can
    // surface the exact readiness reason instead of feeling dead. The click
    // handler still prevents submission while blocked. Busy state remains a
    // true hard-disable because the page is already handing work to the worker.
    button->setEnabled(!busy_);
    button->setToolTip(tooltip);
    repolishWidget(button);
}

void ImageGenerationPage::updatePrimaryActionAvailability()
{
    const QString blockReason = readinessBlockReason();
    const bool enabled = blockReason.isEmpty();

    applyActionReadinessStyle(generateButton_, enabled,
                              enabled ? QStringLiteral("Generate with the current prompt and model stack.")
                                      : blockReason);
    applyActionReadinessStyle(queueButton_, enabled,
                              enabled ? QStringLiteral("Add this job to the queue.")
                                      : blockReason);

    if (readinessHintLabel_)
    {
        readinessHintLabel_->setText(enabled ? QString() : blockReason);
        readinessHintLabel_->setToolTip(enabled ? QString() : blockReason);
        readinessHintLabel_->setVisible(!enabled && !blockReason.trimmed().isEmpty());
    }

    updateAssetIntelligenceUi();
}

void ImageGenerationPage::resizeEvent(QResizeEvent *event)
{
    QWidget::resizeEvent(event);
    updateAdaptiveLayout();
    schedulePreviewRefresh(60);
}

void ImageGenerationPage::clearForm()
{
    if (presetCombo_)
        presetCombo_->setCurrentText(QStringLiteral("Balanced"));

    if (promptEdit_)
        promptEdit_->clear();
    if (negativePromptEdit_)
        negativePromptEdit_->clear();
    if (inputImageEdit_)
        inputImageEdit_->clear();

    if (!modelDisplayByValue_.isEmpty())
        setSelectedModel(modelDisplayByValue_.firstKey(), modelDisplayByValue_.value(modelDisplayByValue_.firstKey()));
    else
        setSelectedModel(QString(), QString());

    if (workflowCombo_)
        selectComboValue(workflowCombo_, QStringLiteral("Default Canvas"));
    loraStack_.clear();
    rebuildLoraStackUi();
    if (samplerCombo_)
        selectComboValue(samplerCombo_, QStringLiteral("dpmpp_2m"));
    if (schedulerCombo_)
        selectComboValue(schedulerCombo_, QStringLiteral("karras"));
    if (stepsSpin_)
        stepsSpin_->setValue(isVideoMode() ? 30 : 28);
    if (cfgSpin_)
        cfgSpin_->setValue(isVideoMode() ? 5.0 : 7.0);
    if (seedSpin_)
        seedSpin_->setValue(0);
    if (widthSpin_)
        widthSpin_->setValue(isVideoMode() ? 832 : 1024);
    if (heightSpin_)
        heightSpin_->setValue(isVideoMode() ? 480 : 1024);
    if (frameCountSpin_)
        frameCountSpin_->setValue(81);
    if (fpsSpin_)
        fpsSpin_->setValue(16);
    if (videoStackModeCombo_)
        selectComboValue(videoStackModeCombo_, QStringLiteral("auto"));
    if (wanSplitCombo_)
        selectComboValue(wanSplitCombo_, QStringLiteral("auto"));
    if (highNoiseStepsSpin_)
        highNoiseStepsSpin_->setValue(14);
    if (lowNoiseStepsSpin_)
        lowNoiseStepsSpin_->setValue(14);
    if (splitStepSpin_)
        splitStepSpin_->setValue(14);
    if (highNoiseShiftSpin_)
        highNoiseShiftSpin_->setValue(5.0);
    if (lowNoiseShiftSpin_)
        lowNoiseShiftSpin_->setValue(5.0);
    if (enableVaeTilingCheck_)
        enableVaeTilingCheck_->setChecked(false);
    if (batchSpin_)
        batchSpin_->setValue(1);
    if (denoiseSpin_)
        denoiseSpin_->setValue(0.45);
    if (outputPrefixEdit_)
        outputPrefixEdit_->clear();

    workflowDraftSource_.clear();
    workflowDraftProfilePath_.clear();
    workflowDraftWorkflowPath_.clear();
    workflowDraftCompiledPromptPath_.clear();
    workflowDraftBackend_.clear();
    workflowDraftMediaType_.clear();
    workflowDraftWarnings_.clear();
    workflowDraftBlocking_ = false;

    generatedPreviewPath_.clear();
    generatedPreviewCaption_.clear();
    busy_ = false;
    busyMessage_.clear();

    setInputImagePath(QString());

    updatePrimaryActionAvailability();
    if (savePresetButton_)
        savePresetButton_->setEnabled(true);
    if (clearButton_)
        clearButton_->setEnabled(true);

    updateAssetIntelligenceUi();
    schedulePreviewRefresh(0);
}

void ImageGenerationPage::saveSnapshot()
{
    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    const QString group = QStringLiteral("ImageGenerationPage/%1").arg(modeKey());

    settings.beginGroup(group);
    settings.setValue(QStringLiteral("preset"), currentComboValue(presetCombo_));
    settings.setValue(QStringLiteral("prompt"), promptEdit_ ? promptEdit_->toPlainText() : QString());
    settings.setValue(QStringLiteral("negativePrompt"), negativePromptEdit_ ? negativePromptEdit_->toPlainText() : QString());
    settings.setValue(QStringLiteral("inputImage"), inputImageEdit_ ? inputImageEdit_->text() : QString());
    settings.setValue(QStringLiteral("model"), selectedModelValue());
    settings.setValue(QStringLiteral("modelDisplay"), selectedModelDisplay_);
    settings.setValue(QStringLiteral("workflow"), currentComboValue(workflowCombo_));
    settings.setValue(QStringLiteral("loraStackJson"), serializeLoraStack(loraStack_));
    settings.setValue(QStringLiteral("sampler"), currentComboValue(samplerCombo_));
    settings.setValue(QStringLiteral("scheduler"), currentComboValue(schedulerCombo_));
    settings.setValue(QStringLiteral("steps"), stepsSpin_ ? stepsSpin_->value() : 28);
    settings.setValue(QStringLiteral("cfg"), cfgSpin_ ? cfgSpin_->value() : 7.0);
    settings.setValue(QStringLiteral("seed"), seedSpin_ ? seedSpin_->value() : 0);
    settings.setValue(QStringLiteral("width"), widthSpin_ ? widthSpin_->value() : 1024);
    settings.setValue(QStringLiteral("height"), heightSpin_ ? heightSpin_->value() : 1024);
    settings.setValue(QStringLiteral("frames"), frameCountSpin_ ? frameCountSpin_->value() : 81);
    settings.setValue(QStringLiteral("fps"), fpsSpin_ ? fpsSpin_->value() : 16);
    settings.setValue(QStringLiteral("batch"), batchSpin_ ? batchSpin_->value() : 1);
    settings.setValue(QStringLiteral("denoise"), denoiseSpin_ ? denoiseSpin_->value() : 0.45);
    settings.setValue(QStringLiteral("videoStackMode"), videoStackModeCombo_ ? videoStackModeSelection() : QStringLiteral("auto"));
    settings.setValue(QStringLiteral("wanSplit"), wanSplitCombo_ ? currentComboValue(wanSplitCombo_) : QStringLiteral("auto"));
    settings.setValue(QStringLiteral("highSteps"), highNoiseStepsSpin_ ? highNoiseStepsSpin_->value() : 14);
    settings.setValue(QStringLiteral("lowSteps"), lowNoiseStepsSpin_ ? lowNoiseStepsSpin_->value() : 14);
    settings.setValue(QStringLiteral("splitStep"), splitStepSpin_ ? splitStepSpin_->value() : 14);
    settings.setValue(QStringLiteral("highShift"), highNoiseShiftSpin_ ? highNoiseShiftSpin_->value() : 5.0);
    settings.setValue(QStringLiteral("lowShift"), lowNoiseShiftSpin_ ? lowNoiseShiftSpin_->value() : 5.0);
    settings.setValue(QStringLiteral("enableVaeTiling"), enableVaeTilingCheck_ && enableVaeTilingCheck_->isChecked());
    settings.setValue(QStringLiteral("outputPrefix"), outputPrefixEdit_ ? outputPrefixEdit_->text() : QString());
    settings.endGroup();
    settings.sync();

    QString sourcePath = generatedPreviewPath_.trimmed();
    if (sourcePath.isEmpty() && isImageInputMode() && inputImageEdit_)
        sourcePath = inputImageEdit_->text().trimmed();

    if (sourcePath.isEmpty() || !QFileInfo::exists(sourcePath))
    {
        QMessageBox::information(this,
                                 QStringLiteral("Save Snapshot"),
                                 QStringLiteral("Generation settings were saved. No rendered output is available to copy yet."));
        return;
    }

    QFileInfo sourceInfo(sourcePath);
    QString extension = sourceInfo.suffix().trimmed().toLower();
    const QStringList supportedSnapshotExtensions = {QStringLiteral("png"),
                                                     QStringLiteral("jpg"),
                                                     QStringLiteral("jpeg"),
                                                     QStringLiteral("webp"),
                                                     QStringLiteral("bmp"),
                                                     QStringLiteral("gif"),
                                                     QStringLiteral("mp4"),
                                                     QStringLiteral("webm"),
                                                     QStringLiteral("mov"),
                                                     QStringLiteral("mkv")};
    if (!supportedSnapshotExtensions.contains(extension))
        extension = isVideoMode() ? QStringLiteral("mp4") : QStringLiteral("png");

    QString picturesRoot = QStandardPaths::writableLocation(QStandardPaths::PicturesLocation);
    if (picturesRoot.trimmed().isEmpty())
        picturesRoot = QDir::homePath();

    QDir snapshotDir(QDir(picturesRoot).filePath(QStringLiteral("SpellVision/Snapshots")));
    snapshotDir.mkpath(QStringLiteral("."));

    const QString defaultName = QStringLiteral("%1_snapshot_%2.%3")
                                    .arg(modeKey(),
                                         QDateTime::currentDateTime().toString(QStringLiteral("yyyyMMdd_HHmmss")),
                                         extension);
    QString savePath = QFileDialog::getSaveFileName(this,
                                                    QStringLiteral("Save SpellVision Snapshot"),
                                                    snapshotDir.filePath(defaultName),
                                                    isVideoMode()
                                                        ? QStringLiteral("Video / Animated Outputs (*.mp4 *.webm *.mov *.mkv *.gif);;All Files (*)")
                                                        : QStringLiteral("Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif);;All Files (*)"));
    if (savePath.trimmed().isEmpty())
        return;

    if (QFileInfo(savePath).suffix().trimmed().isEmpty())
        savePath += QStringLiteral(".") + extension;

    QFileInfo targetInfo(savePath);
    const QString canonicalSource = sourceInfo.canonicalFilePath();
    const QString canonicalTarget = targetInfo.exists() ? targetInfo.canonicalFilePath() : targetInfo.absoluteFilePath();
    if (!canonicalSource.isEmpty() && canonicalSource == canonicalTarget)
    {
        QMessageBox::information(this,
                                 QStringLiteral("Save Snapshot"),
                                 QStringLiteral("Snapshot already exists at this location."));
        return;
    }

    if (QFileInfo::exists(savePath) && !QFile::remove(savePath))
    {
        QMessageBox::warning(this,
                             QStringLiteral("Save Snapshot"),
                             QStringLiteral("Could not replace the existing file:\n%1").arg(savePath));
        return;
    }

    bool saved = QFile::copy(sourcePath, savePath);
    if (!saved && imagePreviewController_ && imagePreviewController_->hasCachedPixmap())
        saved = imagePreviewController_->cachedPixmap().save(savePath);

    if (!saved)
    {
        QMessageBox::warning(this,
                             QStringLiteral("Save Snapshot"),
                             QStringLiteral("Could not save the snapshot:\n%1").arg(savePath));
        return;
    }

    QSettings workspaceSettings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    workspaceSettings.setValue(QStringLiteral("workspace/last_saved_snapshot_path"), savePath);
    workspaceSettings.sync();

    QMessageBox::information(this,
                             QStringLiteral("Save Snapshot"),
                             QStringLiteral("Snapshot saved:\n%1").arg(savePath));
}

void ImageGenerationPage::restoreSnapshot()
{
    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    const QString group = QStringLiteral("ImageGenerationPage/%1").arg(modeKey());
    settings.beginGroup(group);

    if (presetCombo_)
        selectComboValue(presetCombo_, settings.value(QStringLiteral("preset"), QStringLiteral("Balanced")).toString());
    if (promptEdit_)
        promptEdit_->setPlainText(settings.value(QStringLiteral("prompt")).toString());
    if (negativePromptEdit_)
        negativePromptEdit_->setPlainText(settings.value(QStringLiteral("negativePrompt")).toString());
    setSelectedModel(settings.value(QStringLiteral("model")).toString(),
                     settings.value(QStringLiteral("modelDisplay")).toString());
    if (workflowCombo_)
        selectComboValue(workflowCombo_, settings.value(QStringLiteral("workflow"), QStringLiteral("Default Canvas")).toString());
    loraStack_ = deserializeLoraStack(settings.value(QStringLiteral("loraStackJson")).toString());
    rebuildLoraStackUi();
    if (samplerCombo_)
        selectComboValue(samplerCombo_, settings.value(QStringLiteral("sampler"), QStringLiteral("dpmpp_2m")).toString());
    if (schedulerCombo_)
        selectComboValue(schedulerCombo_, settings.value(QStringLiteral("scheduler"), QStringLiteral("karras")).toString());
    if (stepsSpin_)
        stepsSpin_->setValue(settings.value(QStringLiteral("steps"), 28).toInt());
    if (cfgSpin_)
        cfgSpin_->setValue(settings.value(QStringLiteral("cfg"), 7.0).toDouble());
    if (seedSpin_)
        seedSpin_->setValue(settings.value(QStringLiteral("seed"), 0).toInt());
    if (widthSpin_)
        widthSpin_->setValue(settings.value(QStringLiteral("width"), isVideoMode() ? 832 : 1024).toInt());
    if (heightSpin_)
        heightSpin_->setValue(settings.value(QStringLiteral("height"), isVideoMode() ? 480 : 1024).toInt());
    if (frameCountSpin_)
        frameCountSpin_->setValue(settings.value(QStringLiteral("frames"), 81).toInt());
    if (fpsSpin_)
        fpsSpin_->setValue(settings.value(QStringLiteral("fps"), 16).toInt());
    if (batchSpin_)
        batchSpin_->setValue(settings.value(QStringLiteral("batch"), 1).toInt());
    if (denoiseSpin_)
        denoiseSpin_->setValue(settings.value(QStringLiteral("denoise"), 0.45).toDouble());
    if (videoStackModeCombo_)
        selectComboValue(videoStackModeCombo_, settings.value(QStringLiteral("videoStackMode"), QStringLiteral("auto")).toString());
    if (wanSplitCombo_)
        selectComboValue(wanSplitCombo_, settings.value(QStringLiteral("wanSplit"), QStringLiteral("auto")).toString());
    if (highNoiseStepsSpin_)
        highNoiseStepsSpin_->setValue(settings.value(QStringLiteral("highSteps"), 14).toInt());
    if (lowNoiseStepsSpin_)
        lowNoiseStepsSpin_->setValue(settings.value(QStringLiteral("lowSteps"), 14).toInt());
    if (splitStepSpin_)
        splitStepSpin_->setValue(settings.value(QStringLiteral("splitStep"), 14).toInt());
    if (highNoiseShiftSpin_)
        highNoiseShiftSpin_->setValue(settings.value(QStringLiteral("highShift"), 5.0).toDouble());
    if (lowNoiseShiftSpin_)
        lowNoiseShiftSpin_->setValue(settings.value(QStringLiteral("lowShift"), 5.0).toDouble());
    if (enableVaeTilingCheck_)
        enableVaeTilingCheck_->setChecked(settings.value(QStringLiteral("enableVaeTiling"), false).toBool());
    if (outputPrefixEdit_)
        outputPrefixEdit_->setText(settings.value(QStringLiteral("outputPrefix")).toString());

    setInputImagePath(settings.value(QStringLiteral("inputImage")).toString());
    updateVideoStackModeUi();
    settings.endGroup();
}

QString ImageGenerationPage::modeKey() const
{
    return spellvision::generation::GenerationModeState::key(toGenerationMode(mode_));
}

QString ImageGenerationPage::modeTitle() const
{
    return spellvision::generation::GenerationModeState::title(toGenerationMode(mode_));
}

bool ImageGenerationPage::isImageInputMode() const
{
    return spellvision::generation::GenerationModeState::requiresImageInput(toGenerationMode(mode_));
}

bool ImageGenerationPage::isVideoMode() const
{
    return spellvision::generation::GenerationModeState::isVideoMode(toGenerationMode(mode_));
}

bool ImageGenerationPage::usesStrengthControl() const
{
    return spellvision::generation::GenerationModeState::usesStrengthControl(toGenerationMode(mode_));
}


QString ImageGenerationPage::videoComponentValue(const QComboBox *combo) const
{
    return comboStoredValue(combo).trimmed();
}

QString ImageGenerationPage::videoStackModeSelection() const
{
    return normalizedVideoStackModeToken(comboStoredValue(videoStackModeCombo_));
}

QString ImageGenerationPage::suggestedVideoStackMode() const
{
    if (!isVideoMode())
        return QStringLiteral("single_model");

    const QJsonObject stack = modelStackByValue_.value(selectedModelPath_);
    const QString stackKind = normalizedVideoStackModeToken(stack.value(QStringLiteral("stack_kind")).toString());
    if (stackKind == QStringLiteral("wan_dual_noise"))
        return stackKind;

    if (!stack.value(QStringLiteral("high_noise_path")).toString().trimmed().isEmpty() ||
        !stack.value(QStringLiteral("low_noise_path")).toString().trimmed().isEmpty() ||
        !stack.value(QStringLiteral("high_noise_model_path")).toString().trimmed().isEmpty() ||
        !stack.value(QStringLiteral("low_noise_model_path")).toString().trimmed().isEmpty())
    {
        return QStringLiteral("wan_dual_noise");
    }

    const QString family = modelFamilyByValue_.value(selectedModelPath_).trimmed().toLower();
    const QString note = modelNoteByValue_.value(selectedModelPath_).trimmed().toLower();
    const QString haystack = QDir::fromNativeSeparators(selectedModelPath_ + QStringLiteral(" ") + selectedModelDisplay_ + QStringLiteral(" ") + note).toLower();

    if (family == QStringLiteral("wan") && (looksLikeWanHighNoisePath(selectedModelPath_) || looksLikeWanLowNoisePath(selectedModelPath_) || haystack.contains(QStringLiteral("dual-noise"))))
        return QStringLiteral("wan_dual_noise");

    return QStringLiteral("single_model");
}

QString ImageGenerationPage::effectiveVideoStackMode() const
{
    const QString explicitMode = videoStackModeSelection();
    if (explicitMode != QStringLiteral("auto"))
        return explicitMode;
    return suggestedVideoStackMode();
}

bool ImageGenerationPage::usesWanDualNoiseMode() const
{
    return isVideoMode() && effectiveVideoStackMode() == QStringLiteral("wan_dual_noise");
}

void ImageGenerationPage::setVideoComponentComboValue(QComboBox *combo, const QString &value)
{
    if (!combo)
        return;

    const QString trimmed = value.trimmed();
    if (trimmed.isEmpty())
    {
        combo->setCurrentIndex(combo->count() > 0 ? 0 : -1);
        return;
    }

    for (int index = 0; index < combo->count(); ++index)
    {
        if (combo->itemData(index, Qt::UserRole).toString().compare(trimmed, Qt::CaseInsensitive) == 0 ||
            combo->itemText(index).compare(trimmed, Qt::CaseInsensitive) == 0)
        {
            combo->setCurrentIndex(index);
            return;
        }
    }

    combo->addItem(QStringLiteral("Manual • %1").arg(shortDisplayFromValue(trimmed)), trimmed);
    combo->setCurrentIndex(combo->count() - 1);
}

void ImageGenerationPage::populateVideoComponentControls()
{
    if (!isVideoMode())
        return;
    if (!videoStackModeCombo_ || !videoPrimaryModelCombo_ || !videoHighNoiseModelCombo_ || !videoLowNoiseModelCombo_ || !videoTextEncoderCombo_ || !videoVaeCombo_ || !videoClipVisionCombo_)
        return;

    auto looksVideoPrimary = [](const CatalogEntry &entry) {
        const QString haystack = normalizedPathText(entry.value + QStringLiteral(" ") + entry.display);
        return haystack.contains(QStringLiteral("wan")) ||
               haystack.contains(QStringLiteral("ltx")) ||
               haystack.contains(QStringLiteral("hunyuan")) ||
               haystack.contains(QStringLiteral("hyvideo")) ||
               haystack.contains(QStringLiteral("cogvideo")) ||
               haystack.contains(QStringLiteral("mochi")) ||
               haystack.contains(QStringLiteral("animatediff")) ||
               haystack.contains(QStringLiteral("svd")) ||
               haystack.contains(QStringLiteral("video"));
    };

    auto appendUnique = [](QVector<CatalogEntry> &target, QVector<CatalogEntry> source, const QString &family, const QString &role) {
        QSet<QString> seen;
        for (const CatalogEntry &entry : target)
            seen.insert(entry.value.toLower());
        for (CatalogEntry entry : source)
        {
            const QString key = entry.value.toLower();
            if (seen.contains(key))
                continue;
            seen.insert(key);
            entry.family = family.isEmpty() ? inferVideoFamilyFromText(entry.value + QStringLiteral(" ") + entry.display) : family;
            entry.modality = QStringLiteral("video");
            entry.role = role;
            target.push_back(entry);
        }
    };

    QVector<CatalogEntry> primaryEntries;
    for (const QString &dir : {QStringLiteral("diffusion_models"), QStringLiteral("unet"), QStringLiteral("video"), QStringLiteral("wan"), QStringLiteral("ltx"), QStringLiteral("hunyuan_video"), QStringLiteral("checkpoints")})
    {
        QVector<CatalogEntry> filtered;
        for (CatalogEntry entry : scanCatalog(modelsRootDir_, dir))
        {
            if (!looksVideoPrimary(entry))
                continue;
            entry.note = QStringLiteral("Primary video diffusion model");
            filtered.push_back(entry);
        }
        appendUnique(primaryEntries, filtered, QString(), QStringLiteral("primary"));
    }

    QVector<CatalogEntry> textEntries;
    appendUnique(textEntries, scanCatalog(modelsRootDir_, QStringLiteral("text_encoders")), QString(), QStringLiteral("text_encoder"));
    appendUnique(textEntries, scanCatalog(modelsRootDir_, QStringLiteral("clip")), QString(), QStringLiteral("text_encoder"));

    QVector<CatalogEntry> vaeEntries;
    appendUnique(vaeEntries, scanCatalog(modelsRootDir_, QStringLiteral("vae")), QString(), QStringLiteral("vae"));

    QVector<CatalogEntry> visionEntries;
    appendUnique(visionEntries, scanCatalog(modelsRootDir_, QStringLiteral("clip_vision")), QString(), QStringLiteral("clip_vision"));
    appendUnique(visionEntries, scanCatalog(modelsRootDir_, QStringLiteral("image_encoders")), QString(), QStringLiteral("clip_vision"));

    auto fillCombo = [](QComboBox *combo, const QString &autoLabel, const QVector<CatalogEntry> &entries) {
        if (!combo)
            return;
        const QString prior = comboStoredValue(combo);
        const QSignalBlocker blocker(combo);
        combo->clear();
        combo->addItem(autoLabel, QString());
        for (const CatalogEntry &entry : entries)
            combo->addItem(entry.display, entry.value);
        if (!prior.trimmed().isEmpty())
        {
            for (int index = 0; index < combo->count(); ++index)
            {
                if (combo->itemData(index, Qt::UserRole).toString().compare(prior, Qt::CaseInsensitive) == 0)
                {
                    combo->setCurrentIndex(index);
                    return;
                }
            }
            combo->addItem(QStringLiteral("Manual • %1").arg(shortDisplayFromValue(prior)), prior);
            combo->setCurrentIndex(combo->count() - 1);
            return;
        }
        combo->setCurrentIndex(0);
    };

    fillCombo(videoPrimaryModelCombo_, QStringLiteral("Auto primary from selected stack"), primaryEntries);
    fillCombo(videoHighNoiseModelCombo_, QStringLiteral("Auto high-noise model"), primaryEntries);
    fillCombo(videoLowNoiseModelCombo_, QStringLiteral("Auto low-noise model"), primaryEntries);
    fillCombo(videoTextEncoderCombo_, QStringLiteral("Auto text encoder"), textEntries);
    fillCombo(videoVaeCombo_, QStringLiteral("Auto VAE"), vaeEntries);
    fillCombo(videoClipVisionCombo_, QStringLiteral("Auto vision encoder"), visionEntries);
    if (videoStackModeCombo_ && videoStackModeCombo_->count() > 0 && videoStackModeCombo_->currentIndex() < 0)
        videoStackModeCombo_->setCurrentIndex(0);
    updateVideoStackModeUi();
}

QJsonObject ImageGenerationPage::selectedVideoStackForPayload() const
{
    if (!isVideoMode())
        return QJsonObject();

    QJsonObject stack = modelStackByValue_.value(selectedModelPath_);
    QString primary = videoComponentValue(videoPrimaryModelCombo_).trimmed();
    if (primary.isEmpty())
        primary = stack.value(QStringLiteral("primary_path")).toString().trimmed();
    if (primary.isEmpty())
        primary = selectedModelPath_.trimmed();
    if (stack.isEmpty() && primary.isEmpty())
        return QJsonObject();

    const QString family = !modelFamilyByValue_.value(selectedModelPath_).trimmed().isEmpty()
                               ? modelFamilyByValue_.value(selectedModelPath_).trimmed()
                               : inferVideoFamilyFromText(primary);

    const QString stackMode = effectiveVideoStackMode();
    stack.insert(QStringLiteral("family"), family);
    stack.insert(QStringLiteral("modality"), QStringLiteral("video"));
    stack.insert(QStringLiteral("stack_mode"), stackMode);

    const QString textEncoder = videoComponentValue(videoTextEncoderCombo_);
    const QString vae = videoComponentValue(videoVaeCombo_);
    const QString clipVision = videoComponentValue(videoClipVisionCombo_);

    if (stackMode == QStringLiteral("wan_dual_noise"))
    {
        QString highNoise = videoComponentValue(videoHighNoiseModelCombo_);
        QString lowNoise = videoComponentValue(videoLowNoiseModelCombo_);

        if (highNoise.isEmpty())
        {
            highNoise = stack.value(QStringLiteral("high_noise_path")).toString().trimmed();
            if (highNoise.isEmpty())
                highNoise = stack.value(QStringLiteral("high_noise_model_path")).toString().trimmed();
            if (highNoise.isEmpty() && looksLikeWanHighNoisePath(primary))
                highNoise = primary;
        }
        if (lowNoise.isEmpty())
        {
            lowNoise = stack.value(QStringLiteral("low_noise_path")).toString().trimmed();
            if (lowNoise.isEmpty())
                lowNoise = stack.value(QStringLiteral("low_noise_model_path")).toString().trimmed();
            if (lowNoise.isEmpty() && looksLikeWanLowNoisePath(primary))
                lowNoise = primary;
        }

        const QString resolvedPrimary = !primary.isEmpty() ? primary : (!lowNoise.isEmpty() ? lowNoise : highNoise);
        const QString resolvedRuntimeModel = !lowNoise.isEmpty() ? lowNoise : resolvedPrimary;
        stack.insert(QStringLiteral("role"), QStringLiteral("split_stack"));
        stack.insert(QStringLiteral("stack_kind"), QStringLiteral("wan_dual_noise"));
        stack.insert(QStringLiteral("primary_path"), resolvedPrimary);
        stack.insert(QStringLiteral("transformer_path"), resolvedRuntimeModel);
        stack.insert(QStringLiteral("unet_path"), resolvedRuntimeModel);
        stack.insert(QStringLiteral("model_path"), resolvedRuntimeModel);
        stack.insert(QStringLiteral("high_noise_path"), highNoise);
        stack.insert(QStringLiteral("high_noise_model_path"), highNoise);
        stack.insert(QStringLiteral("wan_high_noise_path"), highNoise);
        stack.insert(QStringLiteral("low_noise_path"), lowNoise);
        stack.insert(QStringLiteral("low_noise_model_path"), lowNoise);
        stack.insert(QStringLiteral("wan_low_noise_path"), lowNoise);
        if (!textEncoder.isEmpty())
            stack.insert(QStringLiteral("text_encoder_path"), textEncoder);
        if (!vae.isEmpty())
            stack.insert(QStringLiteral("vae_path"), vae);
        if (!clipVision.isEmpty())
            stack.insert(QStringLiteral("clip_vision_path"), clipVision);

        QJsonArray missing;
        if (stack.value(QStringLiteral("high_noise_path")).toString().trimmed().isEmpty())
            missing.append(QStringLiteral("high noise"));
        if (stack.value(QStringLiteral("low_noise_path")).toString().trimmed().isEmpty())
            missing.append(QStringLiteral("low noise"));
        if (stack.value(QStringLiteral("text_encoder_path")).toString().trimmed().isEmpty())
            missing.append(QStringLiteral("text encoder"));
        if (stack.value(QStringLiteral("vae_path")).toString().trimmed().isEmpty())
            missing.append(QStringLiteral("vae"));
        stack.insert(QStringLiteral("missing_parts"), missing);
        stack.insert(QStringLiteral("stack_ready"), missing.isEmpty());
        stack.insert(QStringLiteral("manual_component_selection"),
                     videoStackModeSelection() != QStringLiteral("auto") ||
                     !textEncoder.isEmpty() || !vae.isEmpty() || !clipVision.isEmpty() ||
                     !videoComponentValue(videoHighNoiseModelCombo_).isEmpty() ||
                     !videoComponentValue(videoLowNoiseModelCombo_).isEmpty());

        QJsonObject controls;
        controls.insert(QStringLiteral("stack_mode"), stackMode);
        controls.insert(QStringLiteral("primary_path"), resolvedPrimary);
        controls.insert(QStringLiteral("high_noise_path"), videoComponentValue(videoHighNoiseModelCombo_));
        controls.insert(QStringLiteral("low_noise_path"), videoComponentValue(videoLowNoiseModelCombo_));
        controls.insert(QStringLiteral("text_encoder_path"), textEncoder);
        controls.insert(QStringLiteral("vae_path"), vae);
        controls.insert(QStringLiteral("clip_vision_path"), clipVision);
        stack.insert(QStringLiteral("component_controls"), controls);
        return stack;
    }

    stack.insert(QStringLiteral("role"), stack.value(QStringLiteral("role")).toString().trimmed().isEmpty() ? QStringLiteral("model_stack") : stack.value(QStringLiteral("role")).toString());
    const QString currentKind = stack.value(QStringLiteral("stack_kind")).toString().trimmed();
    stack.insert(QStringLiteral("stack_kind"), currentKind.isEmpty() ? QStringLiteral("single_model") : currentKind);

    if (!primary.isEmpty())
    {
        stack.insert(QStringLiteral("primary_path"), primary);
        stack.insert(QStringLiteral("transformer_path"), primary);
        stack.insert(QStringLiteral("unet_path"), primary);
        stack.insert(QStringLiteral("model_path"), primary);
    }

    if (!textEncoder.isEmpty())
        stack.insert(QStringLiteral("text_encoder_path"), textEncoder);
    if (!vae.isEmpty())
        stack.insert(QStringLiteral("vae_path"), vae);
    if (!clipVision.isEmpty())
        stack.insert(QStringLiteral("clip_vision_path"), clipVision);

    QJsonArray missing;
    const QString kind = stack.value(QStringLiteral("stack_kind")).toString().trimmed();
    const bool requiresComponents = kind == QStringLiteral("split_stack");
    if (requiresComponents && stack.value(QStringLiteral("text_encoder_path")).toString().trimmed().isEmpty())
        missing.append(QStringLiteral("text encoder"));
    if (requiresComponents && stack.value(QStringLiteral("vae_path")).toString().trimmed().isEmpty())
        missing.append(QStringLiteral("vae"));
    stack.insert(QStringLiteral("missing_parts"), missing);
    stack.insert(QStringLiteral("stack_ready"), missing.isEmpty() || !requiresComponents);
    stack.insert(QStringLiteral("manual_component_selection"), videoStackModeSelection() != QStringLiteral("auto") || !textEncoder.isEmpty() || !vae.isEmpty() || !clipVision.isEmpty() || (!primary.isEmpty() && primary.compare(selectedModelPath_, Qt::CaseInsensitive) != 0));

    QJsonObject controls;
    controls.insert(QStringLiteral("stack_mode"), stackMode);
    controls.insert(QStringLiteral("primary_path"), primary);
    controls.insert(QStringLiteral("text_encoder_path"), textEncoder);
    controls.insert(QStringLiteral("vae_path"), vae);
    controls.insert(QStringLiteral("clip_vision_path"), clipVision);
    stack.insert(QStringLiteral("component_controls"), controls);

    return stack;
}

void ImageGenerationPage::syncVideoComponentControlsFromSelectedStack()
{
    if (!isVideoMode())
        return;
    if (!videoStackModeCombo_ || !videoPrimaryModelCombo_ || !videoHighNoiseModelCombo_ || !videoLowNoiseModelCombo_ || !videoTextEncoderCombo_ || !videoVaeCombo_ || !videoClipVisionCombo_)
        return;

    syncingVideoComponentControls_ = true;
    const QJsonObject stack = modelStackByValue_.value(selectedModelPath_);
    if (videoStackModeCombo_->currentIndex() < 0)
        videoStackModeCombo_->setCurrentIndex(0);
    setVideoComponentComboValue(videoPrimaryModelCombo_,
                                stack.value(QStringLiteral("primary_path")).toString().trimmed().isEmpty()
                                    ? selectedModelPath_
                                    : stack.value(QStringLiteral("primary_path")).toString().trimmed());
    setVideoComponentComboValue(videoHighNoiseModelCombo_,
                                stack.value(QStringLiteral("high_noise_path")).toString().trimmed().isEmpty()
                                    ? stack.value(QStringLiteral("high_noise_model_path")).toString()
                                    : stack.value(QStringLiteral("high_noise_path")).toString());
    setVideoComponentComboValue(videoLowNoiseModelCombo_,
                                stack.value(QStringLiteral("low_noise_path")).toString().trimmed().isEmpty()
                                    ? stack.value(QStringLiteral("low_noise_model_path")).toString()
                                    : stack.value(QStringLiteral("low_noise_path")).toString());
    if (videoComponentValue(videoHighNoiseModelCombo_).isEmpty() && looksLikeWanHighNoisePath(selectedModelPath_))
        setVideoComponentComboValue(videoHighNoiseModelCombo_, selectedModelPath_);
    if (videoComponentValue(videoLowNoiseModelCombo_).isEmpty() && looksLikeWanLowNoisePath(selectedModelPath_))
        setVideoComponentComboValue(videoLowNoiseModelCombo_, selectedModelPath_);
    setVideoComponentComboValue(videoTextEncoderCombo_, stack.value(QStringLiteral("text_encoder_path")).toString());
    setVideoComponentComboValue(videoVaeCombo_, stack.value(QStringLiteral("vae_path")).toString());
    setVideoComponentComboValue(videoClipVisionCombo_, stack.value(QStringLiteral("clip_vision_path")).toString());
    syncingVideoComponentControls_ = false;
}

void ImageGenerationPage::applyVideoComponentOverridesToSelectedStack()
{
    if (!isVideoMode() || syncingVideoComponentControls_ || selectedModelPath_.trimmed().isEmpty())
        return;

    const QJsonObject stack = selectedVideoStackForPayload();
    if (!stack.isEmpty())
    {
        modelStackByValue_.insert(selectedModelPath_, stack);
        const QString family = stack.value(QStringLiteral("family")).toString().trimmed();
        if (!family.isEmpty())
            modelFamilyByValue_.insert(selectedModelPath_, family);
        modelModalityByValue_.insert(selectedModelPath_, QStringLiteral("video"));
        modelRoleByValue_.insert(selectedModelPath_, stack.value(QStringLiteral("role")).toString().trimmed().isEmpty() ? QStringLiteral("model_stack") : stack.value(QStringLiteral("role")).toString().trimmed());

        QStringList pieces;
        const QString stackMode = stack.value(QStringLiteral("stack_mode")).toString().trimmed();
        if (stackMode == QStringLiteral("wan_dual_noise"))
        {
            if (!stack.value(QStringLiteral("high_noise_path")).toString().trimmed().isEmpty())
                pieces << QStringLiteral("high noise");
            if (!stack.value(QStringLiteral("low_noise_path")).toString().trimmed().isEmpty())
                pieces << QStringLiteral("low noise");
        }
        else if (!stack.value(QStringLiteral("primary_path")).toString().trimmed().isEmpty())
        {
            pieces << QStringLiteral("model");
        }
        if (!stack.value(QStringLiteral("text_encoder_path")).toString().trimmed().isEmpty())
            pieces << QStringLiteral("text");
        if (!stack.value(QStringLiteral("vae_path")).toString().trimmed().isEmpty())
            pieces << QStringLiteral("vae");
        if (!stack.value(QStringLiteral("clip_vision_path")).toString().trimmed().isEmpty())
            pieces << QStringLiteral("vision");

        QJsonArray missing = stack.value(QStringLiteral("missing_parts")).toArray();
        QStringList missingParts;
        for (const QJsonValue &item : missing)
            missingParts << item.toString();

        if (!missingParts.isEmpty())
            modelNoteByValue_.insert(selectedModelPath_, QStringLiteral("Manual %1 stack: missing %2").arg(stackMode == QStringLiteral("wan_dual_noise") ? QStringLiteral("WAN dual-noise") : QStringLiteral("video"), missingParts.join(QStringLiteral(", "))));
        else
            modelNoteByValue_.insert(selectedModelPath_, QStringLiteral("Manual %1 stack: %2").arg(stackMode == QStringLiteral("wan_dual_noise") ? QStringLiteral("WAN dual-noise") : QStringLiteral("video"), pieces.join(QStringLiteral(" + "))));
    }

    updateVideoStackModeUi();
    updateAssetIntelligenceUi();
    updatePrimaryActionAvailability();
}

void ImageGenerationPage::updateVideoStackModeUi()
{
    if (!isVideoMode())
        return;

    const bool wanDualNoise = usesWanDualNoiseMode();

    if (videoHighNoiseRow_)
        videoHighNoiseRow_->setVisible(wanDualNoise);
    if (videoHighNoiseModelCombo_)
        videoHighNoiseModelCombo_->setVisible(wanDualNoise);
    if (videoLowNoiseRow_)
        videoLowNoiseRow_->setVisible(wanDualNoise);
    if (videoLowNoiseModelCombo_)
        videoLowNoiseModelCombo_->setVisible(wanDualNoise);

    for (QWidget *row : {wanSplitRow_, highNoiseStepsRow_, lowNoiseStepsRow_, splitStepRow_, highNoiseShiftRow_, lowNoiseShiftRow_, enableVaeTilingRow_})
    {
        if (row)
            row->setVisible(wanDualNoise);
    }

    if (videoStackModeCombo_)
    {
        const QString suggested = suggestedVideoStackMode();
        const QString explicitMode = videoStackModeSelection();
        const QString effective = effectiveVideoStackMode();
        const QString suffix = explicitMode == QStringLiteral("auto")
                                   ? QStringLiteral("Auto detect (%1)").arg(suggested == QStringLiteral("wan_dual_noise") ? QStringLiteral("WAN dual-noise") : QStringLiteral("single model"))
                                   : (effective == QStringLiteral("wan_dual_noise") ? QStringLiteral("Manual WAN dual-noise override") : QStringLiteral("Manual single-model override"));
        videoStackModeCombo_->setToolTip(suffix);
    }

    if (wanSplitCombo_)
        wanSplitCombo_->setToolTip(wanDualNoise ? QStringLiteral("Controls how WAN dual-noise sampling is split between the high-noise and low-noise models.") : QStringLiteral("Available when WAN dual-noise mode is active."));
}

QString ImageGenerationPage::currentComboValue(const QComboBox *combo) const
{
    return comboStoredValue(combo);
}

bool ImageGenerationPage::selectComboValue(QComboBox *combo, const QString &value)
{
    if (!combo)
        return false;

    const QString trimmed = value.trimmed();
    if (trimmed.isEmpty())
        return false;

    for (int index = 0; index < combo->count(); ++index)
    {
        if (combo->itemData(index, Qt::UserRole).toString().compare(trimmed, Qt::CaseInsensitive) == 0 ||
            combo->itemText(index).compare(trimmed, Qt::CaseInsensitive) == 0)
        {
            combo->setCurrentIndex(index);
            return true;
        }
    }

    if (combo->isEditable())
    {
        combo->setEditText(trimmed);
        return true;
    }

    return false;
}

QString ImageGenerationPage::resolveLoraValue() const
{
    if (loraStackController_)
        return loraStackController_->firstEnabledValue();
    return ModelStackState::firstEnabledLoraValue(loraStack_);
}

void ImageGenerationPage::showCheckpointPicker()
{
    QVector<CatalogEntry> checkpoints;
    checkpoints.reserve(modelDisplayByValue_.size());
    for (auto it = modelDisplayByValue_.constBegin(); it != modelDisplayByValue_.constEnd(); ++it)
        checkpoints.push_back({it.value(), it.key()});

    CatalogPickerDialog dialog(isVideoMode() ? QStringLiteral("Choose Video Model Stack") : QStringLiteral("Choose Checkpoint"),
                                checkpoints,
                                selectedModelPath_,
                                isVideoMode() ? QStringLiteral("image_generation/recent_video_model_stacks") : QStringLiteral("image_generation/recent_checkpoints"),
                                this);
    if (dialog.exec() != QDialog::Accepted)
        return;

    setSelectedModel(dialog.selectedValue(), dialog.selectedDisplay());
    persistRecentSelection(isVideoMode() ? QStringLiteral("image_generation/recent_video_model_stacks") : QStringLiteral("image_generation/recent_checkpoints"), dialog.selectedValue());
    scheduleUiRefresh(0);
}

void ImageGenerationPage::showLoraPicker()
{
    QVector<CatalogEntry> loras;
    loras.reserve(loraDisplayByValue_.size());
    for (auto it = loraDisplayByValue_.constBegin(); it != loraDisplayByValue_.constEnd(); ++it)
        loras.push_back({it.value(), it.key()});

    CatalogPickerDialog dialog(QStringLiteral("Add LoRA to Stack"), loras, QString(), QStringLiteral("image_generation/recent_loras"), this);
    if (dialog.exec() != QDialog::Accepted)
        return;

    addLoraToStack(dialog.selectedValue(), dialog.selectedDisplay(), 1.0, true);
    persistRecentSelection(QStringLiteral("image_generation/recent_loras"), dialog.selectedValue());
    scheduleUiRefresh(0);
}

void ImageGenerationPage::setSelectedModel(const QString &value, const QString &display)
{
    selectedModelPath_ = value.trimmed();
    selectedModelDisplay_ = display.trimmed().isEmpty() ? resolveSelectedModelDisplay(selectedModelPath_) : display.trimmed();
    refreshSelectedModelUi();
    updatePrimaryActionAvailability();
}

void ImageGenerationPage::refreshSelectedModelUi()
{
    if (selectedModelLabel_)
    {
        if (selectedModelPath_.trimmed().isEmpty())
            selectedModelLabel_->setText(isVideoMode() ? QStringLiteral("No video model stack selected") : QStringLiteral("No checkpoint selected"));
        else
        {
            QString labelText = QStringLiteral("%1\n%2").arg(selectedModelDisplay_.isEmpty() ? shortDisplayFromValue(selectedModelPath_) : selectedModelDisplay_, selectedModelPath_);
            const QString note = modelNoteByValue_.value(selectedModelPath_).trimmed();
            if (isVideoMode() && !note.isEmpty())
                labelText += QStringLiteral("\n%1").arg(note);
            selectedModelLabel_->setText(labelText);
        }
        selectedModelLabel_->setToolTip(selectedModelPath_);
    }

    if (clearModelButton_)
        clearModelButton_->setEnabled(!selectedModelPath_.trimmed().isEmpty());

    syncVideoComponentControlsFromSelectedStack();
    updateVideoStackModeUi();
    updateAssetIntelligenceUi();
}

QString ImageGenerationPage::resolveSelectedModelDisplay(const QString &value) const
{
    const QString trimmed = value.trimmed();
    if (trimmed.isEmpty())
        return QString();

    const auto it = modelDisplayByValue_.constFind(trimmed);
    if (it != modelDisplayByValue_.constEnd())
        return it.value();

    return shortDisplayFromValue(trimmed);
}

QString ImageGenerationPage::resolveLoraDisplay(const QString &value) const
{
    const QString trimmed = value.trimmed();
    if (trimmed.isEmpty())
        return QString();

    const auto it = loraDisplayByValue_.constFind(trimmed);
    if (it != loraDisplayByValue_.constEnd())
        return it.value();

    return shortDisplayFromValue(trimmed);
}

bool ImageGenerationPage::trySetSelectedModelByCandidate(const QStringList &candidates)
{
    QVector<CatalogEntry> checkpoints;
    checkpoints.reserve(modelDisplayByValue_.size());
    for (auto it = modelDisplayByValue_.constBegin(); it != modelDisplayByValue_.constEnd(); ++it)
        checkpoints.push_back({it.value(), it.key()});

    const QString match = resolveCatalogValueByCandidates(checkpoints, candidates);
    if (match.isEmpty())
        return false;

    setSelectedModel(match, resolveSelectedModelDisplay(match));
    return true;
}

bool ImageGenerationPage::tryAddLoraByCandidate(const QStringList &candidates, double weight, bool enabled)
{
    QVector<CatalogEntry> loras;
    loras.reserve(loraDisplayByValue_.size());
    for (auto it = loraDisplayByValue_.constBegin(); it != loraDisplayByValue_.constEnd(); ++it)
        loras.push_back({it.value(), it.key()});

    const QString match = resolveCatalogValueByCandidates(loras, candidates);
    if (match.isEmpty())
        return false;

    addLoraToStack(match, resolveLoraDisplay(match), weight, enabled);
    return true;
}

void ImageGenerationPage::addLoraToStack(const QString &value, const QString &display, double weight, bool enabled)
{
    const QString trimmed = ModelStackState::normalizedPath(value);
    if (trimmed.isEmpty())
        return;

    const QString resolvedDisplay = display.trimmed().isEmpty() ? resolveLoraDisplay(trimmed) : display.trimmed();
    if (loraStackController_)
    {
        loraStackController_->addOrUpdate(trimmed, resolvedDisplay, weight, enabled);
        persistRecentSelection(QStringLiteral("image_generation/recent_loras"), trimmed);
        return;
    }

    LoraStackEntry entry;
    entry.value = trimmed;
    entry.display = resolvedDisplay;
    entry.weight = weight;
    entry.enabled = enabled;

    ModelStackState::upsertLora(loraStack_, entry);
    persistRecentSelection(QStringLiteral("image_generation/recent_loras"), trimmed);
    rebuildLoraStackUi();
}

void ImageGenerationPage::replaceLoraStackEntry(int index)
{
    if (index < 0 || index >= loraStack_.size())
        return;

    QVector<CatalogEntry> loras;
    loras.reserve(loraDisplayByValue_.size());
    for (auto it = loraDisplayByValue_.constBegin(); it != loraDisplayByValue_.constEnd(); ++it)
        loras.push_back({it.value(), it.key()});

    CatalogPickerDialog dialog(QStringLiteral("Replace LoRA"), loras, loraStack_[index].value, QStringLiteral("image_generation/recent_loras"), this);
    if (dialog.exec() != QDialog::Accepted)
        return;

    const QString value = dialog.selectedValue().trimmed();
    const QString display = dialog.selectedDisplay().trimmed().isEmpty() ? resolveLoraDisplay(value) : dialog.selectedDisplay().trimmed();
    if (loraStackController_)
        loraStackController_->replaceAt(index, value, display);
    else
    {
        loraStack_[index].value = value;
        loraStack_[index].display = display;
        rebuildLoraStackUi();
        scheduleUiRefresh(0);
    }

    persistRecentSelection(QStringLiteral("image_generation/recent_loras"), value);
}

void ImageGenerationPage::rebuildLoraStackUi()
{
    if (loraStackController_)
    {
        loraStackController_->rebuild();
        updateAssetIntelligenceUi();
        return;
    }

    if (loraStackSummaryLabel_)
        loraStackSummaryLabel_->setText(ModelStackState::summaryText(loraStack_));
    if (clearLorasButton_)
        clearLorasButton_->setEnabled(!loraStack_.isEmpty());

    updateAssetIntelligenceUi();
}

void ImageGenerationPage::persistLatestGeneratedOutput(const QString &path)
{
    spellvision::generation::persistLatestGeneratedOutput(path);
}

QString ImageGenerationPage::latestGeneratedOutputPath() const
{
    return spellvision::generation::latestGeneratedImageOutputPath();
}

void ImageGenerationPage::prepLatestForI2I()
{
    QString latest = generatedPreviewPath_.trimmed();
    if (latest.isEmpty())
        latest = latestGeneratedOutputPath();

    if (latest.isEmpty() || !QFileInfo::exists(latest))
    {
        QMessageBox::information(this,
                                 QStringLiteral("Prep for I2I"),
                                 QStringLiteral("No generated image is available yet. Generate or queue a T2I image first."));
        return;
    }

    spellvision::generation::persistStagedI2IInputPath(latest);

    if (prepLatestForI2IButton_)
    {
        prepLatestForI2IButton_->setText(QStringLiteral("Prepped"));
        QTimer::singleShot(1300, this, [this]() {
            if (prepLatestForI2IButton_)
                prepLatestForI2IButton_->setText(QStringLiteral("Prep for I2I"));
        });
    }

    emit prepForI2IRequested(latest);
}

void ImageGenerationPage::useLatestForI2I()
{
    QString staged = spellvision::generation::stagedI2IInputPath();

    if (staged.isEmpty())
        staged = latestGeneratedOutputPath();

    if (staged.isEmpty() || !QFileInfo::exists(staged))
    {
        QMessageBox::information(this,
                                 QStringLiteral("Use Last Image"),
                                 QStringLiteral("No staged or generated image is available yet."));
        return;
    }

    useImageAsInput(staged);
}

void ImageGenerationPage::useImageAsInput(const QString &path)
{
    const QString normalizedPath = path.trimmed();
    if (normalizedPath.isEmpty() || !QFileInfo::exists(normalizedPath))
        return;

    setInputImagePath(normalizedPath);
    updatePrimaryActionAvailability();
    scheduleUiRefresh(0);
    schedulePreviewRefresh(0);
}
