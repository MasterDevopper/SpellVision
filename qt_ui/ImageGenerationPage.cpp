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
#include "generation/CockpitInspector.h"
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
#include <QDebug>
#include <QDir>
#include <QDirIterator>
#include <QDoubleSpinBox>
#include <QCheckBox>
#include <QDialog>
#include <QDialogButtonBox>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QButtonGroup>
#include <QFontMetrics>
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
#include <QPainter>
#include <QPixmap>
#include <QPushButton>
#include <QResizeEvent>
#include <QShowEvent>
#include <QSvgRenderer>
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



QLineEdit *createLtxComponentEdit(QWidget *parent,
                                  QVBoxLayout *layout,
                                  const QString &label,
                                  const QString &defaultValue,
                                  const QString &tooltip)
{
    if (!parent || !layout)
        return nullptr;

    auto *caption = createSectionBody(label, parent);
    caption->setMaximumHeight(18);
    layout->addWidget(caption);

    auto *edit = new QLineEdit(parent);
    edit->setText(defaultValue);
    edit->setPlaceholderText(defaultValue);
    edit->setToolTip(tooltip);
    edit->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    layout->addWidget(edit);

    return edit;
}


QString defaultLtxPromptApiExportPath()
{
    const QString envPath = QString::fromLocal8Bit(qgetenv("SPELLVISION_LTX_PROMPT_API_EXPORT")).trimmed();
    if (!envPath.isEmpty())
        return QDir::fromNativeSeparators(envPath);

    const QString legacyEnvPath = QString::fromLocal8Bit(qgetenv("SPELLVISION_LTX_API_WORKFLOW")).trimmed();
    if (!legacyEnvPath.isEmpty())
        return QDir::fromNativeSeparators(legacyEnvPath);

    return QStringLiteral("D:/AI_ASSETS/comfy_runtime/ComfyUI/user/default/workflows/ltx_api.json");
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

    if (isVideoMode())
        suppressStartupVideoPreviewRestore_ = true;

    restoreSnapshot();

    // Sprint 15C Pass 25B:
    // Restoring the last generated video into T2V on startup is not intended.
    // Keep restored controls/prompts, but do not bind persisted media automatically.
    // Users can still open History or Queue to inspect prior outputs explicitly.
    if (isVideoMode())
    {
        generatedPreviewPath_.clear();
        generatedPreviewCaption_.clear();

        if (mediaPreviewController_)
            mediaPreviewController_->clearVideoPreview();
    }

    updateAdaptiveLayout();
    updatePrimaryActionAvailability();

    if (!isVideoMode())
        schedulePreviewRefresh(busy_ ? 0 : 30);
    else
        refreshPreview();
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
    draft.promptApiExportPath = ltxPromptApiExportPathEdit_
                                    ? ltxPromptApiExportPathEdit_->text().trimmed()
                                    : QString();
    draft.ltxPrimaryModelName = ltxPrimaryModelNameEdit_ ? ltxPrimaryModelNameEdit_->text().trimmed() : QString();
    draft.ltxTextEncoderName = ltxTextEncoderNameEdit_ ? ltxTextEncoderNameEdit_->text().trimmed() : QString();
    draft.ltxTextProjectionName = ltxTextProjectionNameEdit_ ? ltxTextProjectionNameEdit_->text().trimmed() : QString();
    draft.ltxAudioVaeName = ltxAudioVaeNameEdit_ ? ltxAudioVaeNameEdit_->text().trimmed() : QString();
    draft.ltxVideoVaeName = ltxVideoVaeNameEdit_ ? ltxVideoVaeNameEdit_->text().trimmed() : QString();
    draft.ltxVisionEncoderName = ltxVisionEncoderNameEdit_ ? ltxVisionEncoderNameEdit_->text().trimmed() : QString();
    // Sprint 15C Pass 29P v4: copy preferred LTX output variant into generation draft.
    if (ltxOutputVariantEdit_)
        draft.ltxOutputVariant = ltxOutputVariantEdit_->text().trimmed();
    draft.ltxOutputVariant = ltxOutputVariantEdit_ ? ltxOutputVariantEdit_->text().trimmed() : QString();

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
    root->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Tight), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
    root->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));

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
    leftScrollArea_->setMinimumWidth(320);
    leftScrollArea_->setMaximumWidth(470);
    leftScrollArea_->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Expanding);

    auto *leftContainer = new QWidget(leftScrollArea_);
    auto *leftLayout = new QVBoxLayout(leftContainer);
    leftLayout->setContentsMargins(0, 0, ThemeManager::instance().spacing(ThemeManager::Spacing::Hairline), 0);
    leftLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
    leftLayout->setSizeConstraint(QLayout::SetMinAndMaxSize);

    // Sprint V Pass 2:
    // VideoFamily card. Top-of-left-rail so the family choice is the
    // first decision users see in T2V/I2V. Visible only in video modes.
    // The combo's currentData() is one of {"auto", "ltx", "wan"}; Auto
    // resolves via resolvedVideoFamily() which builds on the existing
    // suggestedVideoStackMode() (path hints + modelFamilyByValue_).
    videoFamilyCard_ = createCard(QStringLiteral("VideoFamilyCard"));
    {
        // Mockup I2V L98-107: a horizontal selector bar -- [ "Video family" | segmented Auto/Wan/LTX
        // | resolves -> X ]. videoFamilyCombo_ is RETAINED as a hidden state-model: its currentData
        // ({auto,ltx,wan}) is the single source of truth read by videoFamilySelection(), so every
        // family-resolution path (LTX panel, WAN rows, route, status strip) is unchanged. The
        // segmented buttons just drive the combo.
        auto *familyLayout = new QHBoxLayout(videoFamilyCard_);
        familyLayout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
        familyLayout->setSpacing(12);

        auto *familyLabel = new QLabel(QStringLiteral("Video family"), videoFamilyCard_);
        familyLabel->setStyleSheet(QStringLiteral("color:#9DA3B8;font-size:11px;background:transparent;border:0;"));
        familyLayout->addWidget(familyLabel, 0, Qt::AlignVCenter);

        // Hidden backing combo (state model) -- not added to the visible layout.
        videoFamilyCombo_ = new ClickOnlyComboBox(videoFamilyCard_);
        videoFamilyCombo_->setEditable(false);
        videoFamilyCombo_->addItem(QStringLiteral("Auto (resolve from checkpoint)"), QStringLiteral("auto"));
        videoFamilyCombo_->addItem(QStringLiteral("LTX"), QStringLiteral("ltx"));
        videoFamilyCombo_->addItem(QStringLiteral("WAN"), QStringLiteral("wan"));
        configureComboBox(videoFamilyCombo_);
        videoFamilyCombo_->setVisible(false);

        // Segmented bar: tight rounded container of 3 exclusive, checkable buttons.
        auto *segmented = new QWidget(videoFamilyCard_);
        segmented->setObjectName(QStringLiteral("VideoFamilySegmented"));
        segmented->setStyleSheet(QStringLiteral(
            "#VideoFamilySegmented{background:rgba(10,11,18,0.7);border:1px solid rgba(150,160,186,0.22);"
            "border-radius:8px;}"));
        auto *segLayout = new QHBoxLayout(segmented);
        segLayout->setContentsMargins(2, 2, 2, 2);
        segLayout->setSpacing(2);

        auto *familyGroup = new QButtonGroup(this);
        familyGroup->setExclusive(true);
        const QString segButtonStyle = QStringLiteral(
            "QPushButton{border:1px solid transparent;border-radius:6px;padding:3px 13px;font-size:11px;"
            "color:#9DA3B8;background:transparent;}"
            "QPushButton:checked{color:#E9EBF4;background:rgba(124,92,255,0.10);"
            "border:1px solid rgba(124,92,255,0.40);}");
        const auto makeFamilyButton = [&](const QString &label) {
            auto *btn = new QPushButton(label, segmented);
            btn->setCheckable(true);
            btn->setCursor(Qt::PointingHandCursor);
            btn->setStyleSheet(segButtonStyle);
            familyGroup->addButton(btn);
            segLayout->addWidget(btn);
            return btn;
        };
        videoFamilyAutoButton_ = makeFamilyButton(QStringLiteral("Auto"));
        videoFamilyWanButton_ = makeFamilyButton(QStringLiteral("Wan"));
        videoFamilyLtxButton_ = makeFamilyButton(QStringLiteral("LTX"));
        videoFamilyAutoButton_->setChecked(true);

        // USER clicks only (clicked, NOT toggled) drive the backing combo, whose currentIndexChanged
        // fires the SAME handler the dropdown used. No programmatic-set path for the family exists
        // (restore/reset never touch it), so there is no re-fire to guard against.
        connect(videoFamilyAutoButton_, &QPushButton::clicked, this, [this]() { selectComboValue(videoFamilyCombo_, QStringLiteral("auto")); });
        connect(videoFamilyWanButton_, &QPushButton::clicked, this, [this]() { selectComboValue(videoFamilyCombo_, QStringLiteral("wan")); });
        connect(videoFamilyLtxButton_, &QPushButton::clicked, this, [this]() { selectComboValue(videoFamilyCombo_, QStringLiteral("ltx")); });

        familyLayout->addWidget(segmented, 0, Qt::AlignVCenter);
        familyLayout->addStretch(1);

        videoFamilyResolvesLabel_ = new QLabel(videoFamilyCard_);
        videoFamilyResolvesLabel_->setObjectName(QStringLiteral("VideoFamilyResolves"));
        videoFamilyResolvesLabel_->setStyleSheet(QStringLiteral(
            "font-family:'JetBrains Mono',monospace;font-size:10px;color:#646A82;background:transparent;border:0;"));
        familyLayout->addWidget(videoFamilyResolvesLabel_, 0, Qt::AlignVCenter);

        videoFamilyCard_->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Maximum);
        videoFamilyCard_->setVisible(isVideoMode());
        leftLayout->addWidget(videoFamilyCard_);

        connect(videoFamilyCombo_, qOverload<int>(&QComboBox::currentIndexChanged), this, [this]() {
            updateVideoFamilyUi();
            // The stack-mode UI consults resolvedVideoFamily() to decide
            // whether to show WAN advanced rows, so refresh it too.
            updateVideoStackModeUi();
            scheduleUiRefresh(0);
        });
    }

    auto *promptCard = createCard(QStringLiteral("PromptCard"));
    auto *promptLayout = new QVBoxLayout(promptCard);
    promptLayout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
    promptLayout->setSpacing(8);

    // Preset combo is BUILT here but lives in the OUTPUT inspector tab (reparented below at the
    // inspector-population step), NOT in the prompt card -- mockup keeps the card to prompt-only.
    presetCombo_ = new ClickOnlyComboBox(promptCard);
    presetCombo_->setEditable(false);
    presetCombo_->addItem(QStringLiteral("Balanced"), QStringLiteral("Balanced"));
    presetCombo_->addItem(QStringLiteral("Portrait Detail"), QStringLiteral("Portrait Detail"));
    presetCombo_->addItem(QStringLiteral("Stylized Concept"), QStringLiteral("Stylized Concept"));
    presetCombo_->addItem(QStringLiteral("Upscale / Repair"), QStringLiteral("Upscale / Repair"));
    presetCombo_->addItem(QStringLiteral("Custom"), QStringLiteral("Custom"));
    configureComboBox(presetCombo_);
    // Apply-on-select. *** activated, NOT currentIndexChanged *** -- activated fires ONLY on user
    // interaction, so the programmatic selectComboValue/setCurrentText calls in restore/reset paths
    // do NOT re-fire applyPreset (which would clobber a just-restored prompt). No Apply button.
    connect(presetCombo_, QOverload<int>::of(&QComboBox::activated), this,
            [this](int) { applyPreset(presetCombo_->currentText()); });

    // Prompt-row left slot. In T2I/T2V it is the inert 48x48 IMG chip; in i2i/i2v it is the live
    // 84x84 input dropzone (the separate Input card is merged up into this slot, per mockup). Mode
    // is fixed per page instance, so this construction-time branch is final -- T2I never grows a
    // live dropzone (no leak). The dropzone is a VIEW over the untouched inputImageEdit_ /
    // setInputImagePath model+writer: drop/click/clear all funnel into setInputImagePath().
    QWidget *promptSourceSlot = nullptr;
    if (isImageInputMode())
    {
        inputChipDropzone_ = new DropTargetFrame(promptCard);
        inputChipDropzone_->setObjectName(QStringLiteral("PromptInputDropzone"));
        inputChipDropzone_->setFixedSize(84, 84);
        inputChipDropzone_->setCursor(Qt::PointingHandCursor);
        inputChipDropzone_->onFileDropped = [this](const QString &path) { setInputImagePath(path); };

        // Transparent full-size click-catcher (bottom child) -> browse. The labels above set
        // WA_TransparentForMouseEvents so the click falls through; the clear button is raised on top.
        inputChipClickCatcher_ = new QPushButton(inputChipDropzone_);
        inputChipClickCatcher_->setObjectName(QStringLiteral("PromptInputClickCatcher"));
        inputChipClickCatcher_->setGeometry(0, 0, 84, 84);
        inputChipClickCatcher_->setFlat(true);
        inputChipClickCatcher_->setCursor(Qt::PointingHandCursor);
        inputChipClickCatcher_->setStyleSheet(QStringLiteral("#PromptInputClickCatcher{background:transparent;border:0;}"));
        connect(inputChipClickCatcher_, &QPushButton::clicked, this, [this]() { openInputImageBrowse(); });

        inputChipThumb_ = new QLabel(inputChipDropzone_);
        inputChipThumb_->setGeometry(1, 1, 82, 82);
        inputChipThumb_->setAlignment(Qt::AlignCenter);
        inputChipThumb_->setAttribute(Qt::WA_TransparentForMouseEvents);
        inputChipThumb_->setVisible(false);

        inputChipHint_ = new QLabel(isVideoMode() ? QStringLiteral("⬆\nDrop keyframe\nor browse")
                                                  : QStringLiteral("⬆\nDrop image\nor browse"),
                                    inputChipDropzone_);
        inputChipHint_->setGeometry(0, 0, 84, 84);
        inputChipHint_->setAlignment(Qt::AlignCenter);
        inputChipHint_->setAttribute(Qt::WA_TransparentForMouseEvents);
        inputChipHint_->setStyleSheet(QStringLiteral("color:#9DA3B8;font-size:9px;background:transparent;border:0;"));

        inputChipClear_ = new QPushButton(QStringLiteral("×"), inputChipDropzone_);
        inputChipClear_->setObjectName(QStringLiteral("PromptInputClear"));
        inputChipClear_->setGeometry(84 - 21, 3, 18, 18);
        inputChipClear_->setCursor(Qt::PointingHandCursor);
        inputChipClear_->setStyleSheet(QStringLiteral(
            "#PromptInputClear{background:rgba(10,11,18,0.78);color:#E9EBF4;border:0;border-radius:5px;font-size:12px;}"));
        inputChipClear_->setVisible(false);
        inputChipClear_->raise();
        connect(inputChipClear_, &QPushButton::clicked, this, [this]() { setInputImagePath(QString()); });

        inputChipDropzone_->setStyleSheet(QStringLiteral(
            "#PromptInputDropzone{border:1px dashed rgba(150,160,186,0.30);border-radius:9px;background:rgba(10,11,18,0.30);}"));
        promptSourceSlot = inputChipDropzone_;
    }
    else
    {
        auto *promptSourceChip = new QFrame(promptCard);
        promptSourceChip->setObjectName(QStringLiteral("PromptSourceChip"));
        promptSourceChip->setFixedSize(48, 48);
        promptSourceChip->setStyleSheet(QStringLiteral(
            "#PromptSourceChip{border:1px dashed rgba(150,160,186,0.22);border-radius:9px;background:transparent;}"));
        auto *chipLayout = new QVBoxLayout(promptSourceChip);
        chipLayout->setContentsMargins(0, 0, 0, 0);
        chipLayout->setSpacing(1);
        auto *chipIcon = new QLabel(QStringLiteral("◇"), promptSourceChip);
        chipIcon->setAlignment(Qt::AlignCenter);
        chipIcon->setStyleSheet(QStringLiteral("color:#8B92A8;font-size:15px;background:transparent;border:0;"));
        auto *chipText = new QLabel(QStringLiteral("IMG"), promptSourceChip);
        chipText->setAlignment(Qt::AlignCenter);
        chipText->setStyleSheet(QStringLiteral("color:#646A82;font-size:9px;background:transparent;border:0;"));
        chipLayout->addWidget(chipIcon);
        chipLayout->addWidget(chipText);
        promptSourceSlot = promptSourceChip;
    }

    // 3-line envelope (measured from the polished theme line-height, not hardcoded), scroll beyond.
    const auto applyThreeLineEnvelope = [](QTextEdit *edit) {
        edit->ensurePolished();
        const QFontMetrics fm = edit->fontMetrics();
        const int h = fm.lineSpacing() * 3
            + 2 * static_cast<int>(edit->document()->documentMargin())
            + 2 * edit->frameWidth()
            + 6;
        edit->setMinimumHeight(h);
        edit->setMaximumHeight(h);
        edit->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
        edit->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
        edit->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    };

    promptEdit_ = new QTextEdit(promptCard);
    promptEdit_->setPlaceholderText(QStringLiteral("Describe — subject, framing, lighting, style cues…"));
    applyThreeLineEnvelope(promptEdit_);

    // "Negative" toggle button (mockup ti-circle-minus): collapses/reveals the negative row.
    negativeToggleButton_ = new QPushButton(QStringLiteral("⊖  Negative"), promptCard);
    negativeToggleButton_->setObjectName(QStringLiteral("NegativeToggleButton"));
    negativeToggleButton_->setCursor(Qt::PointingHandCursor);
    negativeToggleButton_->setFixedHeight(30);
    connect(negativeToggleButton_, &QPushButton::clicked, this, [this]() {
        setNegativePromptVisible(!(negativeRow_ && negativeRow_->isVisible()));
    });

    auto *promptRow = new QHBoxLayout;
    promptRow->setContentsMargins(0, 0, 0, 0);
    promptRow->setSpacing(10);
    promptRow->addWidget(promptSourceSlot, 0, Qt::AlignTop);
    promptRow->addWidget(promptEdit_, 1);
    promptRow->addWidget(negativeToggleButton_, 0, Qt::AlignTop);

    // Negative row: [NEG label | negativePromptEdit_], wrapped so HIDE-not-delete is one setVisible.
    negativePromptEdit_ = new QTextEdit(promptCard);
    negativePromptEdit_->setPlaceholderText(QStringLiteral("Exclude — blur, watermark, extra fingers, low quality…"));
    applyThreeLineEnvelope(negativePromptEdit_);

    negativeRow_ = new QWidget(promptCard);
    negativeRow_->setObjectName(QStringLiteral("NegativeRow"));
    auto *negativeRowLayout = new QHBoxLayout(negativeRow_);
    negativeRowLayout->setContentsMargins(0, 8, 0, 0);
    negativeRowLayout->setSpacing(10);
    auto *negLabel = new QLabel(QStringLiteral("NEG"), negativeRow_);
    negLabel->setFixedWidth(48);
    negLabel->setAlignment(Qt::AlignHCenter | Qt::AlignTop);
    negLabel->setStyleSheet(QStringLiteral(
        "color:#646A82;font-family:'JetBrains Mono',monospace;font-size:9px;letter-spacing:1px;background:transparent;border:0;"));
    negativeRowLayout->addWidget(negLabel, 0, Qt::AlignTop);
    negativeRowLayout->addWidget(negativePromptEdit_, 1);

    promptLayout->addLayout(promptRow);
    promptLayout->addWidget(negativeRow_);
    promptCard->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Maximum);
    leftLayout->addWidget(promptCard);

    setNegativePromptVisible(false); // collapsed by default (mockup negOpen=false)

    inputCard_ = createCard(QStringLiteral("InputCard"));
    auto *inputLayout = new QVBoxLayout(inputCard_);
    inputLayout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
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

    // The Input card is now merged into the prompt-row chip-dropzone (i2i/i2v); keep it constructed
    // but always hidden -- it remains the live home of inputImageEdit_/inputDropLabel_ (the model
    // + the label setInputImagePath updates), so all input wiring is unchanged.
    inputCard_->setVisible(false);
    leftLayout->addWidget(inputCard_);

    auto *quickControlsCard = createCard(QStringLiteral("QuickControlsCard"));
    auto *quickControlsLayout = new QVBoxLayout(quickControlsCard);
    quickControlsLayout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
    quickControlsLayout->setSpacing(8);
    quickControlsLayout->addWidget(createSectionTitle(QStringLiteral("Generation Controls"), quickControlsCard));
    auto *quickControlsHint = createSectionBody(QStringLiteral("Core controls stay visible. The rest collapses."), quickControlsCard);
    quickControlsHint->setMaximumHeight(22);
    quickControlsLayout->addWidget(quickControlsHint);

    // --- SPRINT MOCKUP PASS 3 DISCLOSURE PROMOTION: Sampler & Scheduler disclosure card ---
    auto *samplerSchedulerCard = createCard(QStringLiteral("SamplerSchedulerCard"));
    auto *samplerSchedulerCardLayout = new QVBoxLayout(samplerSchedulerCard);
    samplerSchedulerCardLayout->setContentsMargins(
        ThemeManager::instance().spacing(ThemeManager::Spacing::Snug),
        ThemeManager::instance().spacing(ThemeManager::Spacing::Snug),
        ThemeManager::instance().spacing(ThemeManager::Spacing::Snug),
        ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
    samplerSchedulerCardLayout->setSpacing(8);
    auto *samplerSchedulerHeader = new QWidget(samplerSchedulerCard);
    auto *samplerSchedulerHeaderLayout = new QHBoxLayout(samplerSchedulerHeader);
    samplerSchedulerHeaderLayout->setContentsMargins(0, 0, 0, 0);
    samplerSchedulerHeaderLayout->setSpacing(8);
    samplerSchedulerHeaderLayout->addWidget(createSectionTitle(QStringLiteral("Sampler & Scheduler"), samplerSchedulerCard), 1);
    samplerSchedulerCardLayout->addWidget(samplerSchedulerHeader);
    auto *samplerSchedulerHint = createSectionBody(QStringLiteral("Sampler, scheduler and aspect. Collapsed to protect rail space."), samplerSchedulerCard);
    samplerSchedulerHint->setObjectName(QStringLiteral("SamplerSchedulerBodyHint"));
    samplerSchedulerHint->setMaximumHeight(24);
    samplerSchedulerCardLayout->addWidget(samplerSchedulerHint);

    // Sprint 15C Pass 29C:
    // LTX Prompt API generation requires a real Comfy API-format workflow.
    // Expose that path directly in the T2V/I2V surface instead of hiding it
    // behind requeue-only tooling.
    ltxLaunchOptionsPanel_ = createCard(QStringLiteral("LtxLaunchOptionsPanel"));
    auto *ltxLaunchLayout = new QVBoxLayout(ltxLaunchOptionsPanel_);
    ltxLaunchLayout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
    ltxLaunchLayout->setSpacing(8);

    // --- SPRINT MOCKUP PASS 3 DISCLOSURE PROMOTION: LTX disclosure header ---
    auto *ltxLaunchHeader = new QWidget(ltxLaunchOptionsPanel_);
    ltxLaunchHeader->setObjectName(QStringLiteral("LtxLaunchHeader"));  // SPRINT MOCKUP PASS 4 COLLAPSE FIX
    auto *ltxLaunchHeaderLayout = new QHBoxLayout(ltxLaunchHeader);
    ltxLaunchHeaderLayout->setContentsMargins(0, 0, 0, 0);
    ltxLaunchHeaderLayout->setSpacing(8);
    ltxLaunchHeaderLayout->addWidget(createSectionTitle(QStringLiteral("LTX Launch Options"), ltxLaunchOptionsPanel_), 1);
    ltxLaunchLayout->addWidget(ltxLaunchHeader);

    ltxPromptApiHintLabel_ = createSectionBody(
        QStringLiteral("Required: Comfy Prompt API export. Default: user/default/workflows/ltx_api.json"),
        ltxLaunchOptionsPanel_);
    ltxPromptApiHintLabel_->setWordWrap(true);
    ltxLaunchLayout->addWidget(ltxPromptApiHintLabel_);

    ltxPromptApiExportPathEdit_ = new QLineEdit(ltxLaunchOptionsPanel_);
    ltxPromptApiExportPathEdit_->setObjectName(QStringLiteral("LtxPromptApiExportPathEdit"));
    ltxPromptApiExportPathEdit_->setPlaceholderText(QStringLiteral("Path to ltx_api.json Prompt API export"));
    ltxPromptApiExportPathEdit_->setText(defaultLtxPromptApiExportPath());
    ltxPromptApiExportPathEdit_->setToolTip(QStringLiteral("LTX requires a Comfy Prompt API-format export. This path is sent as prompt_api_export_path."));
    ltxLaunchLayout->addWidget(ltxPromptApiExportPathEdit_);

    ltxPrimaryModelNameEdit_ = createLtxComponentEdit(
        ltxLaunchOptionsPanel_,
        ltxLaunchLayout,
        QStringLiteral("Primary checkpoint"),
        QStringLiteral("ltx/ltx-2.3-22b-dev.safetensors"),
        QStringLiteral("LTX primary checkpoint sent as video_primary_model_name."));

    ltxTextEncoderNameEdit_ = createLtxComponentEdit(
        ltxLaunchOptionsPanel_,
        ltxLaunchLayout,
        QStringLiteral("Text encoder"),
        QStringLiteral("ltx/comfy_gemma_3_12B_it.safetensors"),
        QStringLiteral("Gemma text encoder for LTX."));

    ltxTextProjectionNameEdit_ = createLtxComponentEdit(
        ltxLaunchOptionsPanel_,
        ltxLaunchLayout,
        QStringLiteral("Text projection"),
        QStringLiteral("ltx-2.3_text_projection_bf16.safetensors"),
        QStringLiteral("LTX 2.3 text projection model."));

    ltxAudioVaeNameEdit_ = createLtxComponentEdit(
        ltxLaunchOptionsPanel_,
        ltxLaunchLayout,
        QStringLiteral("Audio VAE"),
        QStringLiteral("ltx/LTX23_audio_vae_bf16.safetensors"),
        QStringLiteral("LTX audio VAE component."));

    ltxVideoVaeNameEdit_ = createLtxComponentEdit(
        ltxLaunchOptionsPanel_,
        ltxLaunchLayout,
        QStringLiteral("Video VAE"),
        QStringLiteral("ltx/LTX23_video_vae_bf16.safetensors"),
        QStringLiteral("LTX video VAE component."));

    ltxVisionEncoderNameEdit_ = createLtxComponentEdit(
        ltxLaunchOptionsPanel_,
        ltxLaunchLayout,
        QStringLiteral("Vision encoder"),
        QStringLiteral("clip_vision_g"),
        QStringLiteral("Vision encoder used by LTX/I2V-capable graphs."));

    ltxOutputVariantEdit_ = createLtxComponentEdit(
        ltxLaunchOptionsPanel_,
        ltxLaunchLayout,
        QStringLiteral("Preferred output"),
        QStringLiteral("distilled"),
        QStringLiteral("Preferred LTX output variant. Use distilled for the better preview/output when available."));

    auto *ltxButtonsRow = new QHBoxLayout;
    ltxButtonsRow->setContentsMargins(0, 0, 0, 0);
    ltxButtonsRow->setSpacing(8);

    ltxBrowsePromptApiButton_ = new QPushButton(QStringLiteral("Browse API JSON"), ltxLaunchOptionsPanel_);
    ltxBrowsePromptApiButton_->setObjectName(QStringLiteral("SecondaryActionButton"));

    ltxUseDefaultPromptApiButton_ = new QPushButton(QStringLiteral("Use Default"), ltxLaunchOptionsPanel_);
    ltxUseDefaultPromptApiButton_->setObjectName(QStringLiteral("TertiaryActionButton"));

    ltxApplySafeDefaultsButton_ = new QPushButton(QStringLiteral("LTX Defaults"), ltxLaunchOptionsPanel_);
    ltxApplySafeDefaultsButton_->setObjectName(QStringLiteral("TertiaryActionButton"));
    ltxApplySafeDefaultsButton_->setToolTip(QStringLiteral("Apply safe LTX test defaults: 512x320, 33 frames, 24 fps."));

    ltxButtonsRow->addWidget(ltxBrowsePromptApiButton_);
    ltxButtonsRow->addWidget(ltxUseDefaultPromptApiButton_);
    ltxButtonsRow->addWidget(ltxApplySafeDefaultsButton_);
    ltxButtonsRow->addStretch(1);
    ltxLaunchLayout->addLayout(ltxButtonsRow);

    connect(ltxBrowsePromptApiButton_, &QPushButton::clicked, this, [this]() {
        const QString filePath = QFileDialog::getOpenFileName(
            this,
            QStringLiteral("Choose LTX Prompt API export"),
            ltxPromptApiExportPathEdit_ ? QFileInfo(ltxPromptApiExportPathEdit_->text().trimmed()).absolutePath() : QString(),
            QStringLiteral("Comfy Prompt API JSON (*.json);;All Files (*)"));

        if (filePath.isEmpty() || !ltxPromptApiExportPathEdit_)
            return;

        ltxPromptApiExportPathEdit_->setText(QDir::fromNativeSeparators(filePath));
        scheduleUiRefresh();
    });

    connect(ltxUseDefaultPromptApiButton_, &QPushButton::clicked, this, [this]() {
        if (!ltxPromptApiExportPathEdit_)
            return;

        ltxPromptApiExportPathEdit_->setText(defaultLtxPromptApiExportPath());
        scheduleUiRefresh();
    });

    connect(ltxApplySafeDefaultsButton_, &QPushButton::clicked, this, [this]() {
        if (widthSpin_)
            widthSpin_->setValue(512);
        if (heightSpin_)
            heightSpin_->setValue(320);
        if (frameCountSpin_)
            frameCountSpin_->setValue(33);
        if (fpsSpin_)
            fpsSpin_->setValue(24);
        if (stepsSpin_)
            stepsSpin_->setValue(28);
        if (cfgSpin_)
            cfgSpin_->setValue(7.0);

        if (ltxPromptApiExportPathEdit_)
            ltxPromptApiExportPathEdit_->setText(defaultLtxPromptApiExportPath());
        if (ltxPrimaryModelNameEdit_)
            ltxPrimaryModelNameEdit_->setText(QStringLiteral("ltx/ltx-2.3-22b-dev.safetensors"));
        if (ltxTextEncoderNameEdit_)
            ltxTextEncoderNameEdit_->setText(QStringLiteral("ltx/comfy_gemma_3_12B_it.safetensors"));
        if (ltxTextProjectionNameEdit_)
            ltxTextProjectionNameEdit_->setText(QStringLiteral("ltx-2.3_text_projection_bf16.safetensors"));
        if (ltxAudioVaeNameEdit_)
            ltxAudioVaeNameEdit_->setText(QStringLiteral("ltx/LTX23_audio_vae_bf16.safetensors"));
        if (ltxVideoVaeNameEdit_)
            ltxVideoVaeNameEdit_->setText(QStringLiteral("ltx/LTX23_video_vae_bf16.safetensors"));
        if (ltxVisionEncoderNameEdit_)
            ltxVisionEncoderNameEdit_->setText(QStringLiteral("clip_vision_g"));
        if (ltxOutputVariantEdit_)
            ltxOutputVariantEdit_->setText(QStringLiteral("distilled"));

        // Also try to select the matching model stack if the catalog contains it.
        trySetSelectedModelByCandidate({
            QStringLiteral("ltx-2.3-22b-dev"),
            QStringLiteral("ltx/ltx-2.3-22b-dev"),
            QStringLiteral("ltx-2.3"),
            QStringLiteral("ltx")
        });
        syncVideoComponentControlsFromSelectedStack();
        updateAssetIntelligenceUi();

        scheduleUiRefresh();
    });

    connect(ltxPromptApiExportPathEdit_, &QLineEdit::textChanged, this, [this]() {
        scheduleUiRefresh();
    });

    const QList<QLineEdit *> ltxOptionEdits = {
        ltxPrimaryModelNameEdit_,
        ltxTextEncoderNameEdit_,
        ltxTextProjectionNameEdit_,
        ltxAudioVaeNameEdit_,
        ltxVideoVaeNameEdit_,
        ltxVisionEncoderNameEdit_,
        ltxOutputVariantEdit_
    };

    for (QLineEdit *edit : ltxOptionEdits)
    {
        if (!edit)
            continue;

        connect(edit, &QLineEdit::textChanged, this, [this]() {
            scheduleUiRefresh();
        });
    }

    // Sprint V Pass 2: LTX panel visible only when the resolved family is LTX.
    // updateVideoFamilyUi() will re-apply this on every family change.
    // --- SPRINT MOCKUP PASS 3 DISCLOSURE PROMOTION: LTX panel moved out of Quick Controls flow ---
    ltxLaunchOptionsPanel_->setVisible(isVideoMode() && resolvedVideoFamilyToken() == QStringLiteral("ltx"));

    leftLayout->addWidget(quickControlsCard);
    // --- SPRINT MOCKUP PASS 3 DISCLOSURE PROMOTION: disclosure cards added after Quick Controls ---
    leftLayout->addWidget(samplerSchedulerCard);
    leftLayout->addWidget(ltxLaunchOptionsPanel_);

    auto *outputQueueCard = createCard(QStringLiteral("OutputQueueCard"));
    auto *outputQueueLayout = new QVBoxLayout(outputQueueCard);
    outputQueueLayout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
    outputQueueLayout->setSpacing(8);
    auto *outputQueueHeader = new QWidget(outputQueueCard);
    auto *outputQueueHeaderLayout = new QHBoxLayout(outputQueueHeader);
    outputQueueHeaderLayout->setContentsMargins(0, 0, 0, 0);
    outputQueueHeaderLayout->setSpacing(8);
    outputQueueHeaderLayout->addWidget(createSectionTitle(QStringLiteral("Output / Queue"), outputQueueCard), 1);
    outputQueueLayout->addWidget(outputQueueHeader);
    leftLayout->addWidget(outputQueueCard);

    auto *advancedCard = createCard(QStringLiteral("AdvancedCard"));
    auto *advancedLayout = new QVBoxLayout(advancedCard);
    advancedLayout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
    advancedLayout->setSpacing(8);
    auto *advancedHeader = new QWidget(advancedCard);
    advancedHeader->setObjectName(QStringLiteral("AdvancedHeader"));  // SPRINT MOCKUP PASS 4 COLLAPSE FIX
    auto *advancedHeaderLayout = new QHBoxLayout(advancedHeader);
    advancedHeaderLayout->setContentsMargins(0, 0, 0, 0);
    advancedHeaderLayout->setSpacing(8);
    advancedHeaderLayout->addWidget(createSectionTitle(QStringLiteral("Advanced"), advancedCard), 1);
    advancedLayout->addWidget(advancedHeader);
    auto *advancedHint = createSectionBody(QStringLiteral("Mode-specific controls."), advancedCard);
    advancedHint->setObjectName(QStringLiteral("AdvancedBodyHint"));
    advancedHint->setMaximumHeight(24);
    advancedLayout->addWidget(advancedHint);
    leftLayout->addWidget(advancedCard);
    leftLayout->addStretch(1);

    leftScrollArea_->setWidget(leftContainer);

    centerContainer_ = new QWidget(contentSplitter_);
    // Sprint R Pass 1:
    // Cap the canvas width. Without this, QSplitter's stretch factors
    // (0 / 1 / 0) hand every surplus pixel at ultrawide/fullscreen to the
    // center column, leaving a barren preview field while the rails stay
    // pinned narrow. 1280 px comfortably fits a 1024x1024 image preview
    // plus card chrome and typical video preview sizes. Pass 3's computed
    // splitter sizing redistributes anything beyond this into the rails.
    centerContainer_->setMaximumWidth(1600);
    auto *centerLayout = new QVBoxLayout(centerContainer_);
    centerLayout->setContentsMargins(0, 0, 0, 0);
    centerLayout->setSpacing(0);

    auto *canvasCard = createCard(QStringLiteral("CanvasCard"));
    auto *canvasLayout = new QVBoxLayout(canvasCard);
    canvasLayout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Card), ThemeManager::instance().spacing(ThemeManager::Spacing::Card), ThemeManager::instance().spacing(ThemeManager::Spacing::Card), ThemeManager::instance().spacing(ThemeManager::Spacing::Card));
    canvasLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

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
    // Pass 28E preview surface geometry lock:
    // Generated image pixmap dimensions must not become the QLabel size hint that
    // resizes the splitter/window. The layout owns the canvas size; refreshPreview()
    // scales the pixmap into the existing canvas.
    previewLabel_->setMinimumSize(0, 0);
    previewLabel_->setSizePolicy(QSizePolicy::Ignored, QSizePolicy::Ignored);
    previewLabel_->setWordWrap(true);

    // --- Studio-layout §A: arcane empty-state (sigil + glow + title/sub + metric chips). ---
    // Mockup T2I L125-143. previewLabel_ stays the IMAGE surface; this is the no-image surface.
    // The two share an inner QStackedWidget so a rendered image cleanly replaces the sigil.
    canvasEmptyState_ = new QWidget(previewImagePage_);
    canvasEmptyState_->setObjectName(QStringLiteral("CanvasEmptyState"));
    auto *emptyLayout = new QVBoxLayout(canvasEmptyState_);
    emptyLayout->setContentsMargins(0, 0, 0, 0);
    emptyLayout->setSpacing(0);
    emptyLayout->addStretch(1);

    // Sigil + glow: a fixed 240px container with a radial violet glow behind a 190px sigil.
    auto *sigilStack = new QWidget(canvasEmptyState_);
    sigilStack->setFixedSize(240, 240);
    auto *canvasEmptyGlow = new QLabel(sigilStack);
    canvasEmptyGlow->setGeometry(0, 0, 240, 240);
    canvasEmptyGlow->setAttribute(Qt::WA_TransparentForMouseEvents);
    // Static glow (no arcanePulse animation -- intentionally skipped, see commit msg).
    canvasEmptyGlow->setStyleSheet(QStringLiteral(
        "background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,"
        " stop:0 rgba(124,92,255,64), stop:0.62 rgba(124,92,255,0)); border:0;"));
    auto *canvasEmptySigil = new QLabel(sigilStack);
    canvasEmptySigil->setGeometry(25, 25, 190, 190);
    canvasEmptySigil->setAttribute(Qt::WA_TransparentForMouseEvents);
    canvasEmptySigil->setAlignment(Qt::AlignCenter);
    {
        // Mockup's exact sigil path data; rgba() rewritten as hex + *-opacity for QtSvg's parser.
        static const char *kSigilSvg =
            "<svg viewBox='0 0 48 48' fill='none' xmlns='http://www.w3.org/2000/svg'>"
            "<circle cx='24' cy='24' r='22' stroke='#96A0BA' stroke-opacity='0.18' stroke-width='0.6'/>"
            "<circle cx='24' cy='24' r='18' stroke='#96A0BA' stroke-opacity='0.12' stroke-width='0.6'/>"
            "<path d='M24 6 L31 14 L24 14 Z M24 6 L17 14 L24 14 Z M7 24 C13 16 35 16 41 24 C35 32 13 32 7 24 Z M24 42 L31 34 L24 34 Z M24 42 L17 34 L24 34 Z' stroke='#C3C9DC' stroke-opacity='0.5' stroke-width='1.1' stroke-linejoin='round'/>"
            "<circle cx='24' cy='24' r='6' fill='#7C5CFF' fill-opacity='0.35'/>"
            "<circle cx='24' cy='24' r='6' stroke='#34D6E6' stroke-opacity='0.4' stroke-width='0.8'/>"
            "</svg>";
        const QByteArray sigilBytes(kSigilSvg);
        QSvgRenderer sigilRenderer(sigilBytes);
        const qreal dpr = 2.0;
        QPixmap sigilPm(static_cast<int>(190 * dpr), static_cast<int>(190 * dpr));
        sigilPm.fill(Qt::transparent);
        QPainter sigilPainter(&sigilPm);
        sigilPainter.setRenderHint(QPainter::Antialiasing, true);
        sigilPainter.setOpacity(0.55); // mockup sigil opacity
        sigilRenderer.render(&sigilPainter);
        sigilPainter.end();
        sigilPm.setDevicePixelRatio(dpr);
        canvasEmptySigil->setPixmap(sigilPm);
    }
    emptyLayout->addWidget(sigilStack, 0, Qt::AlignHCenter);

    canvasEmptyTitle_ = new QLabel(QStringLiteral("Canvas ready."), canvasEmptyState_);
    canvasEmptyTitle_->setObjectName(QStringLiteral("CanvasEmptyTitle"));
    canvasEmptyTitle_->setAlignment(Qt::AlignHCenter);
    canvasEmptyTitle_->setStyleSheet(QStringLiteral(
        "color:#9DA3B8;font-size:15px;letter-spacing:0.3px;background:transparent;border:0;"));
    canvasEmptySub_ = new QLabel(QString(), canvasEmptyState_);
    canvasEmptySub_->setObjectName(QStringLiteral("CanvasEmptySub"));
    canvasEmptySub_->setAlignment(Qt::AlignHCenter);
    canvasEmptySub_->setWordWrap(true);
    canvasEmptySub_->setStyleSheet(QStringLiteral(
        "color:#646A82;font-size:12px;background:transparent;border:0;"));
    emptyLayout->addSpacing(14);
    emptyLayout->addWidget(canvasEmptyTitle_, 0, Qt::AlignHCenter);
    emptyLayout->addSpacing(5);
    emptyLayout->addWidget(canvasEmptySub_, 0, Qt::AlignHCenter);
    emptyLayout->addStretch(1);

    // Metric chips (live values, refreshed in updateCanvasEmptyState).
    auto *chipsRow = new QWidget(canvasEmptyState_);
    auto *chipsLayout = new QHBoxLayout(chipsRow);
    chipsLayout->setContentsMargins(0, 0, 0, 10);
    chipsLayout->setSpacing(6);
    const auto makeChip = [chipsRow, chipsLayout]() {
        auto *chip = new QLabel(chipsRow);
        chip->setStyleSheet(QStringLiteral(
            "font-family:'JetBrains Mono',monospace;font-size:10px;color:#646A82;"
            "border:1px solid rgba(150,160,186,0.14);border-radius:5px;padding:3px 8px;background:transparent;"));
        chipsLayout->addWidget(chip);
        return chip;
    };
    canvasEmptyChipDim_ = makeChip();
    canvasEmptyChipSteps_ = makeChip();
    canvasEmptyChipCfg_ = makeChip();
    canvasEmptyChipSeed_ = makeChip();
    emptyLayout->addWidget(chipsRow, 0, Qt::AlignHCenter);

    previewImageInnerStack_ = new QStackedWidget(previewImagePage_);
    previewImageInnerStack_->setObjectName(QStringLiteral("PreviewImageInnerStack"));
    previewImageInnerStack_->addWidget(canvasEmptyState_); // index 0 = empty-state
    previewImageInnerStack_->addWidget(previewLabel_);      // index 1 = image / transient text
    previewImageInnerStack_->setCurrentWidget(canvasEmptyState_);
    previewImageLayout->addWidget(previewImageInnerStack_, 1);

    previewVideoPage_ = new QWidget(previewStack_);
    auto *previewVideoLayout = new QVBoxLayout(previewVideoPage_);
    previewVideoLayout->setContentsMargins(0, 0, 0, 0);
    previewVideoLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

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
    previewTransportLayout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight), ThemeManager::instance().spacing(ThemeManager::Spacing::Tight), ThemeManager::instance().spacing(ThemeManager::Spacing::Tight), ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
    previewTransportLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

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

    // Glyph prefixes stand in for the mockup's Tabler icons (unicode stand-ins; a real
    // SVG icon set is a follow-up). Generate's violet-hero look comes from the #PrimaryActionButton
    // theme + readiness styling, so it is NOT restyled inline here.
    generateButton_ = new QPushButton(QStringLiteral("✦  Generate"), canvasCard);
    generateButton_->setObjectName(QStringLiteral("PrimaryActionButton"));
    queueButton_ = new QPushButton(QStringLiteral("≡  Queue"), canvasCard);
    queueButton_->setObjectName(QStringLiteral("SecondaryActionButton"));
    prepLatestForI2IButton_ = new QPushButton(QStringLiteral("Prep for I2I"), canvasCard);
    prepLatestForI2IButton_->setObjectName(QStringLiteral("SecondaryActionButton"));
    useLatestT2IButton_ = new QPushButton(QStringLiteral("Use Last Image"), canvasCard);
    useLatestT2IButton_->setObjectName(QStringLiteral("SecondaryActionButton"));
    savePresetButton_ = new QPushButton(QStringLiteral("❖  Save Snapshot"), canvasCard);
    savePresetButton_->setObjectName(QStringLiteral("TertiaryActionButton"));
    clearButton_ = new QPushButton(QStringLiteral("⟳  Reset"), canvasCard);
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
        updateAdaptiveLayout();
    });
    connect(prepLatestForI2IButton_, &QPushButton::clicked, this, &ImageGenerationPage::prepLatestForI2I);
    connect(useLatestT2IButton_, &QPushButton::clicked, this, &ImageGenerationPage::useLatestForI2I);

    auto *actionRow = new QHBoxLayout;
    actionRow->setContentsMargins(0, 0, 0, 0);
    actionRow->setSpacing(8);
    // Mockup action row: secondary actions grouped LEFT, Generate pinned FAR RIGHT (violet hero).
    // Same button instances -- pure re-layout, connections untouched. Prep/Use-Last stay (working
    // controls the mockup doesn't show; kept in the left group).
    actionRow->addWidget(queueButton_);
    actionRow->addWidget(savePresetButton_);
    actionRow->addWidget(clearButton_);
    actionRow->addWidget(prepLatestForI2IButton_);
    actionRow->addWidget(useLatestT2IButton_);
    actionRow->addWidget(toggleControlsButton_);
    actionRow->addStretch(1);
    actionRow->addWidget(readinessHintLabel_, 0, Qt::AlignVCenter);
    actionRow->addWidget(generateButton_);

    canvasLayout->addWidget(previewStack_, 1);
    canvasLayout->addLayout(actionRow, 0);
    centerLayout->addWidget(canvasCard, 1);

    rightScrollArea_ = new QScrollArea(contentSplitter_);
    rightScrollArea_->setWidgetResizable(true);
    rightScrollArea_->setFrameShape(QFrame::NoFrame);
    rightScrollArea_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    rightScrollArea_->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    rightScrollArea_->setMinimumWidth(320);
    rightScrollArea_->setMaximumWidth(460);
    rightScrollArea_->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Expanding);

    auto *rightContainer = new QWidget(rightScrollArea_);
    auto *rightLayout = new QVBoxLayout(rightContainer);
    rightLayout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Hairline), 0, 0, 0);
    rightLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));

    stackCard_ = createCard(QStringLiteral("SettingsCard"));
    auto *stackCardLayout = new QVBoxLayout(stackCard_);
    stackCardLayout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Card), ThemeManager::instance().spacing(ThemeManager::Spacing::Card), ThemeManager::instance().spacing(ThemeManager::Spacing::Card), ThemeManager::instance().spacing(ThemeManager::Spacing::Card));
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
        componentsRowLabel_ = new QLabel(QStringLiteral("Components"), stackCard_);
        stackForm->addWidget(componentsRowLabel_, stackRow, 0, Qt::AlignTop);
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

    workflowRowLabel_ = new QLabel(QStringLiteral("Workflow"), stackCard_);
    stackForm->addWidget(workflowRowLabel_, stackRow, 0);
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
    settingsCardLayout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
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
        rowLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

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

    // --- SPRINT MOCKUP PASS 2 QUICK CONTROLS STACKED: label-above-field stacked cells (mockup pattern) ---
    auto makeStackedField = [this](QWidget *parent, const QString &labelText, QWidget *field) -> QWidget * {
        auto *cellWidget = new QWidget(parent);
        cellWidget->setMinimumHeight(48);
        auto *cellLayout = new QVBoxLayout(cellWidget);
        cellLayout->setContentsMargins(0, 0, 0, 0);
        cellLayout->setSpacing(2);

        auto *label = new QLabel(labelText, cellWidget);
        label->setObjectName(QStringLiteral("StackedFieldLabel"));
        label->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
        label->setToolTip(labelText);

        field->setParent(cellWidget);
        field->setMinimumWidth(qMax(field->minimumWidth(), 110));
        field->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

        cellLayout->addWidget(label);
        cellLayout->addWidget(field);
        return cellWidget;
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

    QWidget *aspectRow = makeStackedField(quickControlsCard, QStringLiteral("Aspect"), aspectPresetCombo);
    samplerRow_ = makeStackedField(quickControlsCard, QStringLiteral("Image Sampler"), samplerCombo_);
    schedulerRow_ = makeStackedField(quickControlsCard, QStringLiteral("Image Scheduler"), schedulerCombo_);
    videoSamplerRow_ = makeStackedField(quickControlsCard, QStringLiteral("Video Sampler"), videoSamplerCombo_);
    videoSchedulerRow_ = makeStackedField(quickControlsCard, QStringLiteral("Video Scheduler"), videoSchedulerCombo_);
    // Base mode guard (image-only / video-only). updateDisclosure() then AND-composes the disclosure
    // gate on top of these (Advanced-only), so it can never reveal a row the mode already hides.
    samplerRow_->setVisible(!isVideoMode());
    schedulerRow_->setVisible(!isVideoMode());
    videoSamplerRow_->setVisible(isVideoMode());
    videoSchedulerRow_->setVisible(isVideoMode());
    stepsRow_ = makeStackedField(quickControlsCard, QStringLiteral("Steps"), stepsSpin_);
    cfgRow_ = makeStackedField(quickControlsCard, QStringLiteral("CFG"), cfgSpin_);
    seedRow_ = makeStackedField(quickControlsCard, QStringLiteral("Seed"), seedSpin_);
    widthRow_ = makeStackedField(quickControlsCard, QStringLiteral("Width"), widthSpin_);
    heightRow_ = makeStackedField(quickControlsCard, QStringLiteral("Height"), heightSpin_);
    QWidget *framesRow = makeStackedField(quickControlsCard, QStringLiteral("Frames"), frameCountSpin_);
    QWidget *fpsRow = makeStackedField(quickControlsCard, QStringLiteral("FPS"), fpsSpin_);
    framesRow->setVisible(isVideoMode());
    fpsRow->setVisible(isVideoMode());
    batchRow_ = makeSettingsRow(outputQueueCard, QStringLiteral("Batch"), batchSpin_);
    batchRow_->setObjectName(QStringLiteral("OutputQueueBodyRow"));

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
    samplerSchedulerLayout_->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
    samplerSchedulerLayout_->addWidget(aspectRow);
    samplerSchedulerLayout_->addWidget(samplerRow_);
    samplerSchedulerLayout_->addWidget(schedulerRow_);
    samplerSchedulerLayout_->addWidget(videoSamplerRow_);
    samplerSchedulerLayout_->addWidget(videoSchedulerRow_);

    stepsCfgLayout_ = new QBoxLayout(QBoxLayout::TopToBottom);
    stepsCfgLayout_->setContentsMargins(0, 0, 0, 0);
    stepsCfgLayout_->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
    stepsCfgLayout_->addWidget(stepsRow_);
    stepsCfgLayout_->addWidget(cfgRow_);
    // Phase 7 D7: denoise/strength is intent-level for i2i, so it RELOCATES out of the Advanced tab
    // into the Sampling tab here (this layout moves into the Sampling tab). Reparent the EXISTING
    // row -- the read (denoiseSpin_->value() -> draft.denoiseStrength) is by member, untouched. It
    // keeps its usesStrengthControl() guard and is NOT disclosure-gated (visible in both modes when i2i).
    stepsCfgLayout_->addWidget(denoiseRow_);

    seedBatchLayout_ = new QBoxLayout(QBoxLayout::TopToBottom);
    seedBatchLayout_->setContentsMargins(0, 0, 0, 0);
    seedBatchLayout_->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
    seedBatchLayout_->addWidget(seedRow_);
    seedBatchLayout_->addWidget(framesRow);
    seedBatchLayout_->addWidget(fpsRow);

    sizeLayout_ = new QBoxLayout(QBoxLayout::TopToBottom);
    sizeLayout_->setContentsMargins(0, 0, 0, 0);
    sizeLayout_->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
    sizeLayout_->addWidget(widthRow_);
    sizeLayout_->addWidget(heightRow_);

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

    // --- SPRINT MOCKUP PASS 3 DISCLOSURE PROMOTION: samplerSchedulerLayout_ re-homed into its own card ---
    samplerSchedulerCardLayout->addLayout(samplerSchedulerLayout_);
    quickControlsLayout->addLayout(sizeLayout_);
    quickControlsLayout->addLayout(stepsCfgLayout_);
    quickControlsLayout->addLayout(seedBatchLayout_);

    prefixRow_ = makeSettingsRow(outputQueueCard, QStringLiteral("Prefix"), outputPrefixEdit_);
    prefixRow_->setObjectName(QStringLiteral("OutputQueueBodyRow"));
    auto *outputFolderTitle = new QLabel(QStringLiteral("Output Folder"), outputQueueCard);
    outputFolderTitle->setObjectName(QStringLiteral("OutputQueueBodyLabel"));

    outputQueueLayout->addWidget(batchRow_);
    outputQueueLayout->addWidget(prefixRow_);
    outputQueueLayout->addWidget(outputFolderTitle);
    outputQueueLayout->addWidget(outputFolderLabel_);

    // denoiseRow_ relocated to the Sampling tab (above). The Advanced card now holds only the video
    // dual-noise rows, so it has no content in image modes -> hide it for all image modes (the
    // Advanced TAB is also hidden for image modes via updateDisclosure's setTabVisible).
    advancedLayout->addWidget(wanSplitRow_);
    advancedLayout->addWidget(highNoiseStepsRow_);
    advancedLayout->addWidget(lowNoiseStepsRow_);
    advancedLayout->addWidget(splitStepRow_);
    advancedLayout->addWidget(highNoiseShiftRow_);
    advancedLayout->addWidget(lowNoiseShiftRow_);
    advancedLayout->addWidget(enableVaeTilingRow_);
    if (!isVideoMode())
        advancedCard->setVisible(false);

    // --- SPRINT MOCKUP PASS 1 ASSET INTELLIGENCE: structured AI surface ---
    settingsCardLayout->addWidget(createSectionTitle(QStringLiteral("Asset Intelligence"), settingsCard_));
    auto *assetHint = createSectionBody(QStringLiteral("Readiness first. Details on demand."), settingsCard_);
    assetHint->setMaximumHeight(36);
    settingsCardLayout->addWidget(assetHint);

    // Readiness strip: colored dot + headline + right-aligned sub.
    aiReadinessStrip_ = new QFrame(settingsCard_);
    aiReadinessStrip_->setObjectName(QStringLiteral("AiReadinessStrip"));
    aiReadinessStrip_->setProperty("readiness", QStringLiteral("ready"));
    {
        auto *stripLayout = new QHBoxLayout(aiReadinessStrip_);
        stripLayout->setContentsMargins(
            ThemeManager::instance().spacing(ThemeManager::Spacing::Snug),
            6,
            ThemeManager::instance().spacing(ThemeManager::Spacing::Snug),
            6);
        stripLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));

        aiReadinessDot_ = new QLabel(aiReadinessStrip_);
        aiReadinessDot_->setObjectName(QStringLiteral("AiReadinessDot"));
        aiReadinessDot_->setProperty("readiness", QStringLiteral("ready"));
        aiReadinessDot_->setFixedSize(10, 10);
        stripLayout->addWidget(aiReadinessDot_, 0, Qt::AlignVCenter);

        aiReadinessText_ = new QLabel(QStringLiteral("Ready to generate"), aiReadinessStrip_);
        aiReadinessText_->setObjectName(QStringLiteral("AiReadinessText"));
        stripLayout->addWidget(aiReadinessText_, 0, Qt::AlignVCenter);

        stripLayout->addStretch(1);

        aiReadinessSub_ = new QLabel(QString(), aiReadinessStrip_);
        aiReadinessSub_->setObjectName(QStringLiteral("AiReadinessSub"));
        stripLayout->addWidget(aiReadinessSub_, 0, Qt::AlignVCenter | Qt::AlignRight);
    }
    settingsCardLayout->addWidget(aiReadinessStrip_);

    // Stack group: small uppercase label + flow row of chips.
    settingsCardLayout->addSpacing(6);
    aiStackGroupLabel_ = new QLabel(QStringLiteral("STACK"), settingsCard_);
    aiStackGroupLabel_->setObjectName(QStringLiteral("AiGroupLabel"));
    settingsCardLayout->addWidget(aiStackGroupLabel_);

    aiStackChipsRow_ = new QWidget(settingsCard_);
    aiStackChipsRow_->setObjectName(QStringLiteral("AiChipsRow"));
    aiStackChipsLayout_ = new QHBoxLayout(aiStackChipsRow_);
    aiStackChipsLayout_->setContentsMargins(0, 2, 0, 0);
    aiStackChipsLayout_->setSpacing(6);
    aiStackChipsLayout_->addStretch(1);
    settingsCardLayout->addWidget(aiStackChipsRow_);

    // Components group: video modes only (visibility set in update).
    aiComponentsGroupContainer_ = new QWidget(settingsCard_);
    aiComponentsGroupContainer_->setObjectName(QStringLiteral("AiComponentsGroupContainer"));
    {
        auto *componentsLayout = new QVBoxLayout(aiComponentsGroupContainer_);
        componentsLayout->setContentsMargins(0, 6, 0, 0);
        componentsLayout->setSpacing(2);

        aiComponentsGroupLabel_ = new QLabel(QStringLiteral("COMPONENTS"), aiComponentsGroupContainer_);
        aiComponentsGroupLabel_->setObjectName(QStringLiteral("AiGroupLabel"));
        componentsLayout->addWidget(aiComponentsGroupLabel_);

        aiComponentsChipsRow_ = new QWidget(aiComponentsGroupContainer_);
        aiComponentsChipsRow_->setObjectName(QStringLiteral("AiChipsRow"));
        aiComponentsChipsLayout_ = new QHBoxLayout(aiComponentsChipsRow_);
        aiComponentsChipsLayout_->setContentsMargins(0, 2, 0, 0);
        aiComponentsChipsLayout_->setSpacing(6);
        aiComponentsChipsLayout_->addStretch(1);
        componentsLayout->addWidget(aiComponentsChipsRow_);
    }
    settingsCardLayout->addWidget(aiComponentsGroupContainer_);

    // Timing row (video modes only): three metric pairs over a top border.
    aiTimingRow_ = new QFrame(settingsCard_);
    aiTimingRow_->setObjectName(QStringLiteral("AiTimingRow"));
    {
        auto *timingLayout = new QHBoxLayout(aiTimingRow_);
        timingLayout->setContentsMargins(0, 8, 0, 0);
        timingLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Card));

        auto makeTimingItem = [&](QLabel *&valueLbl, QLabel *&keyLbl, const QString &keyText) {
            auto *item = new QWidget(aiTimingRow_);
            auto *itemLayout = new QVBoxLayout(item);
            itemLayout->setContentsMargins(0, 0, 0, 0);
            itemLayout->setSpacing(0);
            valueLbl = new QLabel(QStringLiteral("\u2014"), item);
            valueLbl->setObjectName(QStringLiteral("AiTimingValue"));
            keyLbl = new QLabel(keyText, item);
            keyLbl->setObjectName(QStringLiteral("AiTimingKey"));
            itemLayout->addWidget(valueLbl);
            itemLayout->addWidget(keyLbl);
            timingLayout->addWidget(item, 0, Qt::AlignLeft);
        };
        makeTimingItem(aiTimingFramesValue_, aiTimingFramesKey_, QStringLiteral("LENGTH"));
        makeTimingItem(aiTimingFpsValue_, aiTimingFpsKey_, QStringLiteral("RATE"));
        makeTimingItem(aiTimingDurationValue_, aiTimingDurationKey_, QStringLiteral("DURATION"));
        timingLayout->addStretch(1);
    }
    settingsCardLayout->addWidget(aiTimingRow_);

    // "Show all fields" disclosure: toggles modelsRootLabel_ visibility.
    settingsCardLayout->addSpacing(4);
    aiDetailsToggle_ = new QToolButton(settingsCard_);
    aiDetailsToggle_->setObjectName(QStringLiteral("AiDetailsToggle"));
    aiDetailsToggle_->setToolButtonStyle(Qt::ToolButtonTextOnly);
    aiDetailsToggle_->setText(QString::fromUtf8("\xE2\x96\xBE Show all fields"));
    aiDetailsToggle_->setCursor(Qt::PointingHandCursor);
    aiDetailsToggle_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    connect(aiDetailsToggle_, &QToolButton::clicked, this, [this]() {
        aiDetailsExpanded_ = !aiDetailsExpanded_;
        if (modelsRootLabel_)
            modelsRootLabel_->setVisible(aiDetailsExpanded_);
        if (aiDetailsToggle_)
        {
            aiDetailsToggle_->setText(aiDetailsExpanded_
                ? QString::fromUtf8("\xE2\x96\xB4 Hide details")
                : QString::fromUtf8("\xE2\x96\xBE Show all fields"));
        }
    });
    settingsCardLayout->addWidget(aiDetailsToggle_);

    // Legacy details body — kept for the disclosure, hidden by default.
    modelsRootLabel_->setObjectName(QStringLiteral("AiDetailsBody"));
    modelsRootLabel_->setVisible(false);
    settingsCardLayout->addWidget(modelsRootLabel_);
    // --- END SPRINT MOCKUP PASS 1 ASSET INTELLIGENCE: structured AI surface ---
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

    // --- Studio-layout phase 3a: relocate the cockpit controls INTO the CockpitInspector tabs. ---
    // We move the EXISTING widget instances (not recreate them): signal/slot connections live on
    // the instances, and the request builder reads control VALUES by member pointer (not by
    // widget-tree position), so reparenting preserves the wiring by construction. Whole cards move
    // via addWidget; the loose QuickControls row-widgets move via takeAt->addWidget (which also
    // reparents + keeps their child spin/combo connections). Prompt/Input/VideoFamily stay in the
    // left-scroll; the splitter stays (phase 3b removes it).
    cockpitInspector_ = new CockpitInspector(this);

    const auto moveRowWidgets = [](QLayout *from, QVBoxLayout *to) {
        QList<QWidget *> rows;
        while (QLayoutItem *item = from->takeAt(0))
        {
            if (QWidget *w = item->widget())
                rows.append(w);
            delete item; // deletes the layout-item wrapper only, not the widget
        }
        for (QWidget *row : rows)
            to->addWidget(row);
    };

    // Model tab <- the whole model-stack container (checkpoint/workflow/LoRA/components +
    // asset intelligence). takeWidget() detaches it from the (now empty) right scroll pane.
    QVBoxLayout *modelTab = cockpitInspector_->tabContentLayout(CockpitInspector::Model);
    if (QWidget *modelStack = rightScrollArea_->takeWidget())
        modelTab->addWidget(modelStack);
    modelTab->addStretch(1);

    // Sampling tab <- steps/cfg + seed/frames/fps (moved out of QuickControls) + sampler card.
    QVBoxLayout *samplingTab = cockpitInspector_->tabContentLayout(CockpitInspector::Sampling);
    moveRowWidgets(stepsCfgLayout_, samplingTab);
    moveRowWidgets(seedBatchLayout_, samplingTab);
    samplingTab->addWidget(samplerSchedulerCard);
    samplingTab->addStretch(1);

    // Output tab <- width/height (moved out of QuickControls) + Output/Queue card.
    QVBoxLayout *outputTab = cockpitInspector_->tabContentLayout(CockpitInspector::Output);
    // Preset (the mockup's "Quality" control) lives at the TOP of the Output tab -- reparents
    // presetCombo_ out of the prompt card; its state refs survive (member pointer).
    outputTab->addWidget(createSectionTitle(QStringLiteral("Preset"), cockpitInspector_));
    outputTab->addWidget(presetCombo_);
    moveRowWidgets(sizeLayout_, outputTab);
    outputTab->addWidget(outputQueueCard);
    outputTab->addStretch(1);

    // Advanced tab <- advanced card + LTX launch options (mode-gated visibility preserved).
    QVBoxLayout *advancedTab = cockpitInspector_->tabContentLayout(CockpitInspector::Advanced);
    advancedTab->addWidget(advancedCard);
    advancedTab->addWidget(ltxLaunchOptionsPanel_);
    advancedTab->addStretch(1);

    // --- Studio-layout phase 3b: pin the Prompt to the center; the splitter/left-scroll is excised. ---
    // Move the prompt / input / video-family cards from the (defunct) left-scroll into the CENTER
    // column, ABOVE the preview (existing instances; the prompt textedit's wiring lives on the
    // instance). VideoFamily/Input remain mode-gated via their own setVisible.
    centerLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
    centerLayout->insertWidget(0, videoFamilyCard_);
    centerLayout->insertWidget(1, promptCard);
    centerLayout->insertWidget(2, inputCard_);

    // The center fills the space between rail and inspector (the old 1600px cap was a splitter-era
    // device to push overflow into the now-gone side rails).
    centerContainer_->setMaximumWidth(QWIDGETSIZE_MAX);

    // Cockpit root = [center | inspector]. root->addLayout reparents centerContainer_ out of the
    // splitter onto the page.
    auto *cockpitRow = new QHBoxLayout;
    cockpitRow->setContentsMargins(0, 0, 0, 0);
    cockpitRow->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
    cockpitRow->addWidget(centerContainer_, 1);
    cockpitRow->addWidget(cockpitInspector_, 0);
    root->addLayout(cockpitRow, 1);

    // 3b-2: centerContainer_ is now reparented out (above), so DELETE the splitter husk -- the
    // left/right scroll areas, leftContainer, and the emptied QuickControls card with its now-empty
    // sub-layouts. Part a removed the only post-construction derefs of those sub-layouts (the
    // configureAdaptivePair calls), so this no longer dangles anything. Null the pointers; the
    // remaining husk-guarded paths in updateAdaptiveLayout stay null-safe until part b removes them.
    // The relocated inspector cards live in the inspector tabs (not the husk), so they survive.
    delete contentSplitter_;
    contentSplitter_ = nullptr;
    leftScrollArea_ = nullptr;
    rightScrollArea_ = nullptr;

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

void ImageGenerationPage::updateDisclosure(bool advanced)
{
    advanced_ = advanced;

    // Phase 7 step 2: Output-tab raw knobs are Advanced-only (Width / Height / Batch / Prefix);
    // Preset (Quality) stays Simple. HIDE-not-delete -- the rows keep their values and the request
    // builder reads by member (draft.width = widthSpin_->value(), never visibility-gated), so a
    // value set in Advanced still drives generation in Simple. These rows carry NO existing
    // visibility guard, so the gate is a plain setVisible(advanced) (rows that DO have a mode/family
    // guard must AND with it -- handled per-row as later tabs are added).
    if (widthRow_)
        widthRow_->setVisible(advanced);
    if (heightRow_)
        heightRow_->setVisible(advanced);
    if (batchRow_)
        batchRow_->setVisible(advanced);
    if (prefixRow_)
        prefixRow_->setVisible(advanced);

    // Phase 7 step 3: Sampling-tab raw knobs are Advanced-only. Aspect + Frames/FPS stay Simple
    // (untouched here). GUARD COMPOSITION -- AND the disclosure gate with the row's existing
    // mode guard so disclosure can never reveal a row the mode already hides (image sampler stays
    // hidden in video; video sampler stays hidden in image).
    const bool image = !isVideoMode();
    if (stepsRow_)
        stepsRow_->setVisible(advanced);
    if (cfgRow_)
        cfgRow_->setVisible(advanced);
    if (seedRow_)
        seedRow_->setVisible(advanced);
    if (samplerRow_)
        samplerRow_->setVisible(advanced && image);
    if (schedulerRow_)
        schedulerRow_->setVisible(advanced && image);
    if (videoSamplerRow_)
        videoSamplerRow_->setVisible(advanced && !image);
    if (videoSchedulerRow_)
        videoSchedulerRow_->setVisible(advanced && !image);

    // Phase 7 step 4 -- Model tab: Workflow (D2) is Advanced; Checkpoint / LoRA / Asset Intelligence
    // stay Simple (untouched). Video Components are Advanced too (AND with their isVideoMode guard).
    // Both live in a QGridLayout, so hide BOTH the captured inline label AND the field -> the grid
    // row collapses. Denoise is NOT here -- it relocated to the Sampling tab (visible in both modes).
    if (workflowRowLabel_)
        workflowRowLabel_->setVisible(advanced);
    if (workflowCombo_)
        workflowCombo_->setVisible(advanced);
    if (componentsRowLabel_)
        componentsRowLabel_->setVisible(advanced && !image);
    if (videoComponentPanel_)
        videoComponentPanel_->setVisible(advanced && !image);

    // Piece A (D8): hide the Advanced inspector TAB in Simple. After the denoise relocation the
    // Advanced tab has content only in video modes (wan dual-noise / LTX launch), so it is hidden
    // for image modes entirely -- which also clears the pre-existing empty-Advanced-tab-in-T2I.
    if (cockpitInspector_)
        cockpitInspector_->setTabVisible(CockpitInspector::Advanced, advanced && !image);

    qWarning().noquote() << QStringLiteral("[disclosure] page=%1 advanced=%2")
                                .arg(modeKey(), advanced ? QStringLiteral("true") : QStringLiteral("false"));
}

void ImageGenerationPage::setNegativePromptVisible(bool open)
{
    // HIDE-not-delete: only flips visibility of the wrapper -- negativePromptEdit_ and its text
    // persist while hidden, and the request builder reads it null-guarded (not visibility-guarded),
    // so a typed-then-collapsed negative still reaches generation.
    if (negativeRow_)
        negativeRow_->setVisible(open);
    if (negativeToggleButton_)
    {
        negativeToggleButton_->setStyleSheet(QStringLiteral(
            "#NegativeToggleButton{padding:0 12px;border-radius:8px;font-size:12px;color:%1;"
            "background:%2;border:1px solid %3;}")
            .arg(open ? QStringLiteral("#9A7DFF") : QStringLiteral("#9DA3B8"),
                 open ? QStringLiteral("rgba(124,92,255,0.10)") : QStringLiteral("rgba(10,11,18,0.4)"),
                 open ? QStringLiteral("rgba(124,92,255,0.4)") : QStringLiteral("rgba(150,160,186,0.22)")));
    }
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
    suppressStartupVideoPreviewRestore_ = false;

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

    // Pass 28E:
    // Busy state must not collapse or reshape the preview canvas.
    // Visual empty-state styling can ignore busy, but geometry should be based on
    // whether there is a usable preview/input asset. This prevents the window from
    // breathing while progress/status messages arrive during generation.
    const bool visualEmptyState = !busy_ && !hasRenderedPreview && !hasInputPreview;
    const bool geometryNeedsEmptyCanvas = !hasRenderedPreview && !hasInputPreview;

    bool changed = false;

    if (imagePreviewController_)
    {
        const bool before = previewLabel_->property("emptyState").toBool();
        imagePreviewController_->setEmptyState(visualEmptyState);
        changed = changed || (before != visualEmptyState);
    }
    else if (previewLabel_->property("emptyState").toBool() != visualEmptyState)
    {
        previewLabel_->setProperty("emptyState", visualEmptyState);
        changed = true;
    }

    // Show the arcane empty-state surface only when there is no image/input; a rendered image
    // flips to previewLabel_ (the single source of truth: visualEmptyState). This is the gate-#2
    // guarantee that the sigil never overlays a result.
    if (previewImageInnerStack_ && canvasEmptyState_)
        previewImageInnerStack_->setCurrentWidget(visualEmptyState
                                                      ? canvasEmptyState_
                                                      : static_cast<QWidget *>(previewLabel_));

    const AdaptiveLayoutMode mode = currentAdaptiveLayoutMode();
    const int desiredMinHeight = geometryNeedsEmptyCanvas
        ? (mode == AdaptiveLayoutMode::Compact ? 340 : 420)
        : 0;

    if (previewLabel_->minimumHeight() != desiredMinHeight)
    {
        previewLabel_->setMinimumHeight(desiredMinHeight);
        changed = true;
    }
    // The inner stack (not just the label) carries the empty-canvas floor, since the empty-state
    // page -- not previewLabel_ -- is current when there is no image.
    if (previewImageInnerStack_ && previewImageInnerStack_->minimumHeight() != desiredMinHeight)
        previewImageInnerStack_->setMinimumHeight(desiredMinHeight);

    if (previewLabel_->maximumHeight() != QWIDGETSIZE_MAX)
    {
        previewLabel_->setMaximumHeight(QWIDGETSIZE_MAX);
        changed = true;
    }

    if (changed)
        repolishWidget(previewLabel_);
}

void ImageGenerationPage::updateCanvasEmptyState(const QString &message)
{
    // Split the "Title\n\nSub" empty-state message into the mockup's title + subtitle.
    if (canvasEmptyTitle_)
    {
        const int sep = message.indexOf(QStringLiteral("\n\n"));
        if (sep >= 0)
        {
            canvasEmptyTitle_->setText(message.left(sep).trimmed());
            if (canvasEmptySub_)
                canvasEmptySub_->setText(message.mid(sep + 2).trimmed());
        }
        else
        {
            canvasEmptyTitle_->setText(message.trimmed());
            if (canvasEmptySub_)
                canvasEmptySub_->clear();
        }
    }

    // Metric chips reflect the LIVE control values (seed 0 == random, the app convention).
    if (canvasEmptyChipDim_)
        canvasEmptyChipDim_->setText(QStringLiteral("%1 × %2")
                                         .arg(widthSpin_ ? widthSpin_->value() : 1024)
                                         .arg(heightSpin_ ? heightSpin_->value() : 1024));
    if (canvasEmptyChipSteps_)
        canvasEmptyChipSteps_->setText(QStringLiteral("%1 steps").arg(stepsSpin_ ? stepsSpin_->value() : 28));
    if (canvasEmptyChipCfg_)
        canvasEmptyChipCfg_->setText(QStringLiteral("cfg %1")
                                         .arg(QString::number(cfgSpin_ ? cfgSpin_->value() : 7.0, 'f', 1)));
    if (canvasEmptyChipSeed_)
    {
        const int seed = seedSpin_ ? seedSpin_->value() : 0;
        canvasEmptyChipSeed_->setText(seed == 0 ? QStringLiteral("seed · random")
                                                : QStringLiteral("seed · %1").arg(seed));
    }
}

void ImageGenerationPage::refreshPreview()
{
    if (isVideoMode() && suppressStartupVideoPreviewRestore_)
    {
        if (mediaPreviewController_)
            mediaPreviewController_->clearVideoPreview();

        if (previewStack_ && previewImagePage_)
            previewStack_->setCurrentWidget(previewImagePage_);

        if (previewLabel_)
        {
            previewLabel_->setProperty("emptyState", true);
            previewLabel_->setText(QStringLiteral("No video preview loaded yet. Generate a video or choose one from History."));
        }
        // Specific startup message -> show the text surface, not the arcane empty-state.
        if (previewImageInnerStack_)
            previewImageInnerStack_->setCurrentWidget(previewLabel_);

        return;
    }


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
        const QString message =
            isImageInputMode()
                ? (isVideoMode()
                       ? QStringLiteral("No keyframe loaded yet.\n\nDrop or browse a source keyframe from the left rail.")
                       : QStringLiteral("No source image loaded yet.\n\nDrop or browse an input image from the left rail."))
                : (reason.isEmpty()
                       ? (isVideoMode()
                              ? QStringLiteral("Text to Video ready.\n\nGenerate or queue from the focused canvas when your prompt is set.")
                              : QStringLiteral("Canvas ready.\n\nGenerate or queue from the focused canvas when your prompt is set."))
                       : QStringLiteral("Ready for setup.\n\n%1").arg(reason));
        imagePreviewController_->showText(message);
        updateCanvasEmptyState(message); // arcane empty-state title/sub + live metric chips
        return;
    }

    imagePreviewController_->showText(
        busy_ ? (busyMessage_.isEmpty() ? QStringLiteral("Generation in progress…") : busyMessage_)
              : (isImageInputMode()
                     ? (isVideoMode()
                            ? QStringLiteral("No keyframe loaded yet.\n\nDrop a keyframe into the Input Image card or browse for one to begin image-to-video.")
                            : QStringLiteral("No source image loaded yet.\n\nDrop an image into the Input Image card or browse for one to begin."))
                     : (isVideoMode()
                            ? QStringLiteral("Text to Video ready.\n\nBuild the prompt and motion stack on the left, then press Generate or Queue.")
                            : QStringLiteral("Your generated image will appear here.\n\nBuild the prompt and stack on the left, then generate."))));
}

void ImageGenerationPage::openInputImageBrowse()
{
    // Same picker the (now-hidden) Input-card Browse button used; funnels into setInputImagePath.
    const QString filePath = QFileDialog::getOpenFileName(this,
        QStringLiteral("Choose input image"),
        QString(),
        QStringLiteral("Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)"));
    if (!filePath.isEmpty())
        setInputImagePath(filePath);
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
    if (path.isEmpty())
    {
        inputDropLabel_->setText(isVideoMode()
                                     ? QStringLiteral("Drop a keyframe here or click Browse to select one.")
                                     : QStringLiteral("Drop an image here or click Browse to select a source image."));
    }
    else
    {
        const QString labelTemplate = isVideoMode()
                                          ? QStringLiteral("Current keyframe:\n%1")
                                          : QStringLiteral("Current source image:\n%1");
        inputDropLabel_->setText(labelTemplate.arg(path));
    }

    // Reflect into the prompt-row input chip-dropzone (i2i/i2v): thumbnail + clear when loaded,
    // dashed hint when empty. Pure presentation -- the path already lives in inputImageEdit_ above.
    if (inputChipDropzone_)
    {
        const bool loaded = !path.isEmpty();
        if (loaded && inputChipThumb_)
        {
            const QPixmap source(path);
            inputChipThumb_->setPixmap(source.isNull()
                                           ? QPixmap()
                                           : source.scaled(82, 82, Qt::KeepAspectRatioByExpanding, Qt::SmoothTransformation));
        }
        inputChipDropzone_->setStyleSheet(loaded
            ? QStringLiteral("#PromptInputDropzone{border:1px solid rgba(52,214,230,0.35);border-radius:9px;background:rgba(10,11,18,0.5);}")
            : QStringLiteral("#PromptInputDropzone{border:1px dashed rgba(150,160,186,0.30);border-radius:9px;background:rgba(10,11,18,0.30);}"));
        if (inputChipThumb_)
            inputChipThumb_->setVisible(loaded);
        if (inputChipHint_)
            inputChipHint_->setVisible(!loaded);
        if (inputChipClear_)
        {
            inputChipClear_->setVisible(loaded);
            inputChipClear_->raise();
        }
    }

    updatePrimaryActionAvailability();
    updatePreviewEmptyStateSizing();
    schedulePreviewRefresh(0);
}

void ImageGenerationPage::setPreviewImage(const QString &imagePath, const QString &caption)
{
    // Pass 28G result output unlocks busy canvas geometry before binding a new preview.
    auto unlockHeightForResult = [](QWidget *widget) {
        if (!widget || !widget->property("svBusyHeightLocked").toBool())
            return;

        const QVariant oldMin = widget->property("svBusyOldMinHeight");
        const QVariant oldMax = widget->property("svBusyOldMaxHeight");

        widget->setMinimumHeight(oldMin.isValid() ? oldMin.toInt() : 0);
        widget->setMaximumHeight(oldMax.isValid() ? oldMax.toInt() : QWIDGETSIZE_MAX);

        widget->setProperty("svBusyHeightLocked", false);
        widget->setProperty("svBusyOldMinHeight", QVariant());
        widget->setProperty("svBusyOldMaxHeight", QVariant());
    };

    unlockHeightForResult(previewStack_);
    unlockHeightForResult(findChild<QWidget *>(QStringLiteral("CanvasCard")));

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
    const QString normalizedMessage = message.trimmed();
    const bool stateChanged = busy_ != busy;
    const bool messageChanged = busyMessage_ != normalizedMessage;

    if (!stateChanged && !messageChanged)
        return;

    // Pass 28G:
    // Message-only busy updates must not touch geometry, preview refresh, styles,
    // splitter state, or side-panel content. Keep the new text internally and
    // return. Direct worker telemetry owns progress display elsewhere.
    if (busy && !stateChanged && messageChanged)
    {
        busyMessage_ = normalizedMessage;
        return;
    }

    auto lockHeightForBusy = [](QWidget *widget) {
        if (!widget)
            return;

        if (widget->property("svBusyHeightLocked").toBool())
            return;

        const int currentHeight = widget->height();
        if (currentHeight < 120)
            return;

        widget->setProperty("svBusyOldMinHeight", widget->minimumHeight());
        widget->setProperty("svBusyOldMaxHeight", widget->maximumHeight());
        widget->setMinimumHeight(currentHeight);
        widget->setMaximumHeight(currentHeight);
        widget->setProperty("svBusyHeightLocked", true);
    };

    auto unlockHeightForBusy = [](QWidget *widget) {
        if (!widget)
            return;

        if (!widget->property("svBusyHeightLocked").toBool())
            return;

        const QVariant oldMin = widget->property("svBusyOldMinHeight");
        const QVariant oldMax = widget->property("svBusyOldMaxHeight");

        widget->setMinimumHeight(oldMin.isValid() ? oldMin.toInt() : 0);
        widget->setMaximumHeight(oldMax.isValid() ? oldMax.toInt() : QWIDGETSIZE_MAX);

        widget->setProperty("svBusyHeightLocked", false);
        widget->setProperty("svBusyOldMinHeight", QVariant());
        widget->setProperty("svBusyOldMaxHeight", QVariant());
    };

    QWidget *canvasCard = findChild<QWidget *>(QStringLiteral("CanvasCard"));

    if (stateChanged && busy)
    {
        lockHeightForBusy(canvasCard);
        lockHeightForBusy(previewStack_);
    }
    else if (stateChanged && !busy)
    {
        unlockHeightForBusy(previewStack_);
        unlockHeightForBusy(canvasCard);
    }

    busy_ = busy;
    busyMessage_ = normalizedMessage;

    if (!busy_)
    {
        generateSubmitLocked_ = false;
        busyMessage_.clear();
    }

    if (busy_)
    {
        const bool hasCurrentPreviewVideo =
            mediaPreviewController_ && !mediaPreviewController_->currentVideoPath().trimmed().isEmpty();

        if (generatedPreviewPath_.trimmed().isEmpty() && !hasCurrentPreviewVideo)
        {
            if (imagePreviewController_)
                imagePreviewController_->clearCache(false);
        }
    }

    updatePrimaryActionAvailability();
    updatePreviewEmptyStateSizing();

    if (savePresetButton_)
        savePresetButton_->setEnabled(!busy_);
    if (clearButton_)
        clearButton_->setEnabled(!busy_);

    schedulePreviewRefresh(busy_ ? 120 : 30);
}





int ImageGenerationPage::measuredContentWidth() const
{
    return contentsRect().width();
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

void ImageGenerationPage::updateAdaptiveLayout()
{
    const AdaptiveLayoutMode mode = currentAdaptiveLayoutMode();
    const bool adaptiveModeChanged = mode != lastAdaptiveLayoutMode_;
    adaptiveCompact_ = mode == AdaptiveLayoutMode::Compact;

    // Pass 28G:
    // If generation is active and the adaptive mode did not actually change,
    // do not re-run the full adaptive rail/card sizing pass. Repeated internal
    // resize events during progress updates were causing visible in-window
    // breathing even after the outer window stopped resizing.
    if (busy_ && !adaptiveModeChanged)
        return;

    if (adaptiveModeChanged)
        lastAdaptiveLayoutMode_ = mode;

    // Prompt/negative are now a fixed 3-line envelope sized once at construction (mockup form);
    // no per-mode height reflow here anymore.
    updatePreviewEmptyStateSizing();

}


void ImageGenerationPage::applyWorkerMessage(const QJsonObject &payload)
{
    const QString workerType = payload.value(QStringLiteral("type")).toString().trimmed().toLower();
    const QString workerState = payload.value(QStringLiteral("state")).toString().trimmed().toLower();

    const bool terminalWorkerMessage =
        workerState == QStringLiteral("completed") ||
        workerState == QStringLiteral("failed") ||
        workerState == QStringLiteral("cancelled") ||
        workerState == QStringLiteral("canceled") ||
        workerType == QStringLiteral("result") ||
        workerType == QStringLiteral("error") ||
        workerType == QStringLiteral("client_error");

    if (terminalWorkerMessage)
    {
        busy_ = false;
        busyMessage_.clear();
        generateSubmitLocked_ = false;
    }

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

    // Pass 28 terminal safety repaint: terminal worker messages must always
    // leave the page able to submit the next generation.
    if (terminalWorkerMessage)
        updatePrimaryActionAvailability();
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
    // --- SPRINT MOCKUP PASS 1 ASSET INTELLIGENCE: structured population ---
    if (!modelsRootLabel_)
        return;

    // ---- Data (same shape as the pre-mockup implementation) ----
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

    QString stackSummary = stackNote.isEmpty() ? QStringLiteral("\u2014") : stackNote;
    if (!stackObject.isEmpty())
    {
        const QString kind = stackObject.value(QStringLiteral("stack_kind")).toString().trimmed();
        const bool readyStack = stackObject.value(QStringLiteral("stack_ready")).toBool(false);
        const QJsonArray missing = stackObject.value(QStringLiteral("missing_parts")).toArray();
        QStringList missingParts;
        for (const QJsonValue &item : missing)
            missingParts << item.toString();
        stackSummary = QStringLiteral("%1 \u2022 %2").arg(kind.isEmpty() ? QStringLiteral("stack") : kind, readyStack ? QStringLiteral("resolved") : QStringLiteral("partial"));
        if (!missingParts.isEmpty())
            stackSummary += QStringLiteral(" \u2022 missing %1").arg(missingParts.join(QStringLiteral(", ")));
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

    // ---- Surface: readiness strip ----
    if (aiReadinessStrip_)
    {
        const QString readinessState = ready ? QStringLiteral("ready") : QStringLiteral("warn");
        aiReadinessStrip_->setProperty("readiness", readinessState);
        spellvision::widgets::repolishWidget(aiReadinessStrip_);
        if (aiReadinessDot_)
        {
            aiReadinessDot_->setProperty("readiness", readinessState);
            spellvision::widgets::repolishWidget(aiReadinessDot_);
        }
        if (aiReadinessText_)
            aiReadinessText_->setText(ready ? QStringLiteral("Ready to generate") : blockReason);

        if (aiReadinessSub_)
        {
            // --- SPRINT MOCKUP PASS 1 FIXUP: empty sub when not ready ---
            // The headline already shows the block reason; leaving the
            // sub empty avoids a duplicate-text overlap in the pill.
            QString sub;
            if (!ready)
            {
                sub.clear();
            }
            else if (isVideoMode())
            {
                const QString backendLabel = hasVideoWorkflowBinding()
                    ? QStringLiteral("imported workflow")
                    : QStringLiteral("native");
                sub = QStringLiteral("%1 \u00B7 %2").arg(modelFamily, backendLabel);
            }
            else
            {
                sub = modelFamily;
            }
            aiReadinessSub_->setText(sub);
            // --- END SPRINT MOCKUP PASS 1 FIXUP ---
        }
    }

    // ---- Surface: chip rows (clear then rebuild) ----
    auto clearChips = [](QBoxLayout *layout) {
        if (!layout)
            return;
        while (layout->count() > 0)
        {
            QLayoutItem *item = layout->takeAt(0);
            if (item->widget())
                item->widget()->deleteLater();
            delete item;
        }
    };

    const QColor accentColor = ThemeManager::instance().accentColor();
    const QColor textMutedColor = ThemeManager::instance().textMutedColor();

    auto addChip = [&](QBoxLayout *layout, QWidget *parent,
                       const QString &label, const QString &value, bool isSet) {
        if (!layout || !parent)
            return;
        auto *chip = new QLabel(parent);
        // --- FIXUP 3: distinct object names, no attribute selector ---
        chip->setObjectName(isSet ? QStringLiteral("AiChipSet") : QStringLiteral("AiChipAuto"));
        chip->setTextFormat(Qt::RichText);
        chip->setToolTip(QStringLiteral("%1: %2").arg(label, value));
        const QString labelEsc = label.toHtmlEscaped();
        const QString valueEsc = value.toHtmlEscaped();
        if (isSet)
        {
            chip->setText(QStringLiteral("%1 <b style=\"color:%3;\">%2</b>")
                .arg(labelEsc, valueEsc, accentColor.name()));
        }
        else
        {
            chip->setText(QStringLiteral("%1 <span style=\"color:%3;\">%2</span>")
                .arg(labelEsc, valueEsc, textMutedColor.name()));
        }
        layout->insertWidget(layout->count() - 1, chip);
    };

    auto chipValueIsSet = [](const QString &v) {
        const QString t = v.trimmed();
        return !t.isEmpty()
            && t.compare(QStringLiteral("auto"), Qt::CaseInsensitive) != 0
            && t.compare(QStringLiteral("none"), Qt::CaseInsensitive) != 0
            && t != QStringLiteral("\u2014");
    };

    clearChips(aiStackChipsLayout_);
    if (aiStackChipsRow_ && aiStackChipsLayout_)
    {
        if (isVideoMode())
        {
            const QString stackMode = effectiveVideoStackMode();
            const QString famShort = resolvedVideoFamilyToken().toUpper();
            addChip(aiStackChipsLayout_, aiStackChipsRow_,
                    QStringLiteral("Family"),
                    famShort.isEmpty() ? QStringLiteral("auto") : famShort,
                    !famShort.isEmpty());
            addChip(aiStackChipsLayout_, aiStackChipsRow_,
                    QStringLiteral("Mode"),
                    stackMode == QStringLiteral("wan_dual_noise") ? QStringLiteral("dual-noise") : QStringLiteral("single"),
                    true);
            const QString primary = shortDisplayFromValue(stackObject.value(QStringLiteral("primary_path")).toString());
            addChip(aiStackChipsLayout_, aiStackChipsRow_,
                    QStringLiteral("Primary"),
                    chipValueIsSet(primary) ? primary : QStringLiteral("auto"),
                    chipValueIsSet(primary));
        }
        else
        {
            addChip(aiStackChipsLayout_, aiStackChipsRow_,
                    QStringLiteral("Checkpoint"),
                    modelDisplay,
                    !selectedModelPath_.trimmed().isEmpty());
            addChip(aiStackChipsLayout_, aiStackChipsRow_,
                    QStringLiteral("Family"),
                    modelFamily,
                    !rawFamily.isEmpty());
            addChip(aiStackChipsLayout_, aiStackChipsRow_,
                    QStringLiteral("LoRAs"),
                    QStringLiteral("%1 / %2").arg(loraStack_.size()).arg(enabledLoras),
                    enabledLoras > 0);
        }
        aiStackChipsLayout_->addStretch(1);
    }

    clearChips(aiComponentsChipsLayout_);
    if (aiComponentsGroupContainer_)
        aiComponentsGroupContainer_->setVisible(isVideoMode());
    if (isVideoMode() && aiComponentsChipsRow_ && aiComponentsChipsLayout_)
    {
        const QString textEnc = shortDisplayFromValue(stackObject.value(QStringLiteral("text_encoder_path")).toString());
        const QString vae = shortDisplayFromValue(stackObject.value(QStringLiteral("vae_path")).toString());
        const QString vision = shortDisplayFromValue(stackObject.value(QStringLiteral("clip_vision_path")).toString());
        addChip(aiComponentsChipsLayout_, aiComponentsChipsRow_,
                QStringLiteral("Text"),
                chipValueIsSet(textEnc) ? textEnc : QStringLiteral("auto"),
                chipValueIsSet(textEnc));
        addChip(aiComponentsChipsLayout_, aiComponentsChipsRow_,
                QStringLiteral("VAE"),
                chipValueIsSet(vae) ? vae : QStringLiteral("auto"),
                chipValueIsSet(vae));
        addChip(aiComponentsChipsLayout_, aiComponentsChipsRow_,
                QStringLiteral("Vision"),
                chipValueIsSet(vision) ? vision : QStringLiteral("auto"),
                chipValueIsSet(vision));
        aiComponentsChipsLayout_->addStretch(1);
    }

    // ---- Surface: timing row (video modes only) ----
    if (aiTimingRow_)
        aiTimingRow_->setVisible(isVideoMode());
    if (isVideoMode())
    {
        const int frames = frameCountSpin_ ? frameCountSpin_->value() : 0;
        const int fps = fpsSpin_ ? fpsSpin_->value() : 0;
        const double seconds = fps > 0 ? static_cast<double>(frames) / static_cast<double>(fps) : 0.0;
        if (aiTimingFramesValue_)
            aiTimingFramesValue_->setText(QStringLiteral("%1 frames").arg(frames));
        if (aiTimingFpsValue_)
            aiTimingFpsValue_->setText(QStringLiteral("%1 fps").arg(fps));
        if (aiTimingDurationValue_)
            aiTimingDurationValue_->setText(QStringLiteral("%1 s").arg(QString::number(seconds, 'f', 1)));
    }

    // ---- Legacy HTML dump (kept behind the "Show all fields" disclosure) ----
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
        const QString inputImagePath = inputImageEdit_ ? inputImageEdit_->text().trimmed() : QString();
        if (!inputImagePath.isEmpty())
            html += row(QStringLiteral("Keyframe"), shortDisplayFromValue(inputImagePath));
    }
    html += row(QStringLiteral("Draft"), draftState);
    html += row(QStringLiteral("Review"), warningState);
    html += row(QStringLiteral("Readiness"), readiness, true);
    html += row(QStringLiteral("Assets"), rootText);
    html += QStringLiteral("</table>");

    modelsRootLabel_->setText(html);

    // Tooltip on the readiness strip — exposes the full dump in plain text
    // so users get the data without having to expand the disclosure.
    QStringList plain;
    plain << QStringLiteral("%1: %2").arg(isVideoMode() ? QStringLiteral("Model Stack") : QStringLiteral("Checkpoint"), modelDisplay);
    plain << QStringLiteral("Family: %1").arg(modelFamily);
    plain << QStringLiteral("LoRAs: %1 in stack / %2 enabled").arg(loraStack_.size()).arg(enabledLoras);
    plain << QStringLiteral("Workflow: %1").arg(workflowName.trimmed().isEmpty() ? QStringLiteral("Default Canvas") : workflowName);
    plain << QStringLiteral("Draft: %1").arg(draftState);
    plain << QStringLiteral("Review: %1").arg(warningState);
    plain << QStringLiteral("Readiness: %1").arg(readiness);
    plain << QStringLiteral("Assets: %1").arg(rootText);
    const QString tooltip = plain.join(QStringLiteral("\n"));
    if (aiReadinessStrip_)
        aiReadinessStrip_->setToolTip(tooltip);
    modelsRootLabel_->setToolTip(tooltip);
    // --- END SPRINT MOCKUP PASS 1 ASSET INTELLIGENCE: structured population ---  // SPRINT MOCKUP PASS 1 FIXUP 2 + SPRINT MOCKUP PASS 1 FIXUP 3
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

    if (!inputImageEdit_)
        return false;

    const QString path = inputImageEdit_->text().trimmed();
    if (path.isEmpty())
        return false;

    const QFileInfo info(path);
    return info.exists() && info.isFile();
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

    if (isImageInputMode() && inputImageEdit_)
    {
        const QString inputPath = inputImageEdit_->text().trimmed();
        if (!inputPath.isEmpty())
        {
            const QFileInfo info(inputPath);
            if (!info.exists() || !info.isFile())
                return isVideoMode()
                           ? QStringLiteral("Selected keyframe file is missing. Re-select the source image.")
                           : QStringLiteral("Selected input image is missing. Re-select the source image.");
        }
    }

    if (!hasRequiredGenerationInput())
        return isVideoMode()
                   ? QStringLiteral("Add a source keyframe image to run image-to-video.")
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

void ImageGenerationPage::showEvent(QShowEvent *event)
{
    QWidget::showEvent(event);
    // Phase 7: re-assert the disclosure gate when the page becomes visible. The startup gate (pushed
    // while the page was still hidden) doesn't reliably stick for the reparented model-stack GRID
    // rows (Workflow/Components); re-applying on show fixes it for all gated controls. Idempotent.
    updateDisclosure(advanced_);
}

void ImageGenerationPage::resizeEvent(QResizeEvent *event)
{
    QWidget::resizeEvent(event);
    updateAdaptiveLayout();

    // Pass 28G:
    // Resize-driven preview refresh during active generation can repeatedly
    // mutate the preview stack and cause in-window breathing. Worker terminal
    // messages and setPreviewImage() refresh the preview when a real output
    // arrives.
    if (!busy_)
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
    setNegativePromptVisible(false); // mockup reset re-collapses the negative row
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
    updateVideoFamilyUi();
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

// Sprint V Pass 2: VideoFamily resolution helpers.
//
// videoFamilySelection() returns the literal combo choice (auto/ltx/wan).
// resolvedVideoFamily() resolves "auto" to a concrete family using the
// existing suggestedVideoStackMode() heuristic, which already inspects
// modelFamilyByValue_, path hints (looksLikeWanHighNoisePath, etc.), and
// stack_kind metadata. resolvedVideoFamilyToken() returns the lowercase
// string ("ltx" or "wan") for use in JSON payloads and qss/state checks.
ImageGenerationPage::VideoFamily ImageGenerationPage::videoFamilySelection() const
{
    if (!videoFamilyCombo_)
        return VideoFamily::Auto;
    const QString token = videoFamilyCombo_->currentData(Qt::UserRole).toString().trimmed().toLower();
    if (token == QStringLiteral("ltx"))
        return VideoFamily::Ltx;
    if (token == QStringLiteral("wan"))
        return VideoFamily::Wan;
    return VideoFamily::Auto;
}

ImageGenerationPage::VideoFamily ImageGenerationPage::resolvedVideoFamily() const
{
    const VideoFamily explicitChoice = videoFamilySelection();
    if (explicitChoice != VideoFamily::Auto)
        return explicitChoice;

    // Auto: lean on existing resolution. suggestedVideoStackMode() already
    // surfaces "wan_dual_noise" when a WAN checkpoint is selected. We also
    // sniff modelFamilyByValue_ directly because a single-model WAN
    // checkpoint won't trigger dual-noise detection but is still WAN.
    const QString family = modelFamilyByValue_.value(selectedModelPath_).trimmed().toLower();
    if (family == QStringLiteral("wan"))
        return VideoFamily::Wan;
    if (suggestedVideoStackMode() == QStringLiteral("wan_dual_noise"))
        return VideoFamily::Wan;

    // Fall back to LTX. Currently LTX is the other supported video family
    // in SpellVision; future families (CogVideoX, Hunyuan, Mochi) would
    // extend the enum and this resolution function.
    return VideoFamily::Ltx;
}

QString ImageGenerationPage::resolvedVideoFamilyToken() const
{
    switch (resolvedVideoFamily())
    {
    case VideoFamily::Ltx: return QStringLiteral("ltx");
    case VideoFamily::Wan: return QStringLiteral("wan");
    case VideoFamily::Auto: break;
    }
    return QStringLiteral("ltx");
}

void ImageGenerationPage::updateVideoFamilyUi()
{
    // Card visibility: only show in video modes.
    if (videoFamilyCard_)
        videoFamilyCard_->setVisible(isVideoMode());

    if (!isVideoMode())
    {
        // In image modes nothing video-specific should be visible regardless.
        if (ltxLaunchOptionsPanel_)
            ltxLaunchOptionsPanel_->setVisible(false);
        return;
    }

    const QString resolved = resolvedVideoFamilyToken();
    const bool isLtx = resolved == QStringLiteral("ltx");
    const bool isWan = resolved == QStringLiteral("wan");

    // LTX launch options panel: visible only for LTX family.
    if (ltxLaunchOptionsPanel_)
        ltxLaunchOptionsPanel_->setVisible(isLtx);

    // Tooltip on the family combo surfaces what Auto resolved to so users
    // can tell at a glance whether their selection is being treated as LTX
    // or WAN without having to look at the panels below.
    if (videoFamilyCombo_ && videoFamilySelection() == VideoFamily::Auto)
    {
        videoFamilyCombo_->setToolTip(QStringLiteral("Auto resolved to: %1")
            .arg(isWan ? QStringLiteral("WAN") : QStringLiteral("LTX")));
    }
    else if (videoFamilyCombo_)
    {
        videoFamilyCombo_->setToolTip(QStringLiteral("Manual family override active."));
    }

    // Sync the segmented bar to the backing combo's selection, and show what Auto resolves to
    // (mockup "resolves -> X"). setChecked emits toggled, not clicked, so it never re-drives
    // the combo -- no loop.
    const VideoFamily selection = videoFamilySelection();
    QPushButton *targetButton = selection == VideoFamily::Wan ? videoFamilyWanButton_
                              : selection == VideoFamily::Ltx ? videoFamilyLtxButton_
                                                              : videoFamilyAutoButton_;
    if (targetButton && !targetButton->isChecked())
        targetButton->setChecked(true);
    if (videoFamilyResolvesLabel_)
        videoFamilyResolvesLabel_->setText(QStringLiteral("resolves → %1").arg(resolved.toUpper()));
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
    updateVideoFamilyUi();
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

    updateVideoFamilyUi();
    updateVideoStackModeUi();
    updateAssetIntelligenceUi();
    updatePrimaryActionAvailability();
}

void ImageGenerationPage::updateVideoStackModeUi()
{
    if (!isVideoMode())
        return;

    // Sprint V Pass 3:
    // Family resolution gates WAN UI. Even if the stack mode combo would
    // technically allow dual-noise, an LTX family selection hides WAN
    // rows entirely so the user sees a coherent LTX-only surface.
    const bool familyIsWan = resolvedVideoFamilyToken() == QStringLiteral("wan");
    const bool wanDualNoise = usesWanDualNoiseMode() && familyIsWan;

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

    // The stack-mode row itself is only meaningful for WAN. Hide it when
    // family resolved to LTX so the right-rail Components panel doesn't
    // show a "Stack Mode: WAN dual-noise" choice that does nothing.
    if (videoStackModeRow_)
        videoStackModeRow_->setVisible(familyIsWan);
    if (videoStackModeCombo_)
        videoStackModeCombo_->setVisible(familyIsWan);

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
    updateVideoFamilyUi();
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
