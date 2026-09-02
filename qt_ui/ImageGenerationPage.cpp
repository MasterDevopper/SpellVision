#include "shell/ShellNavigationController.h"
#include "ImageGenerationPage.h"

#include "ThemeManager.h"
#include "preview/MediaPreviewController.h"
#include "preview/ImagePreviewController.h"
#include "generation/GenerationRequestBuilder.h"
#include "shell/RuntimeProfile.h"
#include "generation/ErrorPillLabel.h"
#include "generation/VideoReadinessPresenter.h"
#include "generation/GenerationModeState.h"
#include "generation/GenerationResultRouter.h"
#include "generation/GenerationStatusController.h"
#include "generation/OutputPathHelpers.h"
#include "generation/CockpitInspector.h"
#include "generation/SamplingController.h"
#include "generation/CockpitWidgetKit.h"
#include "ImageGenerationPage_units.h"
#include "workers/WorkerCommandRunner.h"
#include "assets/ModelStackState.h"
#include "assets/LoraStackController.h"
#include "assets/ModelThumbnailCache.h"
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
#include <QCryptographicHash>
#include <QDateTime>
#include <QDebug>
#include <QDir>
#include <QDirIterator>
#include <QDoubleSpinBox>
#include <QRandomGenerator>
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
#include <QClipboard>
#include <QGuiApplication>
#include <QMessageBox>
#include <QMediaPlayer>
#include <QAudioOutput>
#include <QPainter>
#include <QPainterPath>
#include <QPointer>
#include <QPolygonF>
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

namespace
{
// --- Session strip visuals ---------------------------------------------------------------------
// Neutral rounded tile shown while a thumbnail is still generating (and as the video fallback).
QPixmap sessionLoadingTile(int size, bool video)
{
    QPixmap pm(size, size);
    pm.fill(Qt::transparent);
    QPainter p(&pm);
    p.setRenderHint(QPainter::Antialiasing, true);
    ThemeManager &tm = ThemeManager::instance();
    QPainterPath path;
    path.addRoundedRect(QRectF(0.5, 0.5, size - 1.0, size - 1.0), 8, 8);
    p.fillPath(path, tm.color(ThemeManager::Color::Surface2));
    p.setPen(QPen(tm.color(ThemeManager::Color::Border), 1.0));
    p.drawPath(path);
    if (video)
    {
        p.setBrush(tm.color(ThemeManager::Color::TextMid));
        p.setPen(Qt::NoPen);
        const double c = size / 2.0;
        const double r = size * 0.16;
        QPolygonF tri;
        tri << QPointF(c - r * 0.6, c - r) << QPointF(c - r * 0.6, c + r) << QPointF(c + r, c);
        p.drawPolygon(tri);
    }
    p.end();
    return pm;
}

// Composite a small play badge (bottom-left) onto a video item's poster thumbnail.
void paintPlayBadge(QPixmap &pm)
{
    QPainter p(&pm);
    p.setRenderHint(QPainter::Antialiasing, true);
    const int s = qMin(pm.width(), pm.height());
    const double d = s * 0.34;
    const QRectF badge(6.0, pm.height() - d - 6.0, d, d);
    p.setPen(Qt::NoPen);
    p.setBrush(QColor(0, 0, 0, 150));
    p.drawEllipse(badge);
    p.setBrush(QColor(255, 255, 255, 235));
    const double cx = badge.center().x();
    const double cy = badge.center().y();
    const double r = d * 0.22;
    QPolygonF tri;
    tri << QPointF(cx - r * 0.6, cy - r) << QPointF(cx - r * 0.6, cy + r) << QPointF(cx + r, cy);
    p.drawPolygon(tri);
    p.end();
}

// Write an extracted video frame to a stable per-video poster PNG; returns its path ("" on failure).
QString writeSessionPoster(const QString &videoPath, const QImage &frame)
{
    if (frame.isNull())
        return {};
    QString base = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation);
    if (base.trimmed().isEmpty())
        base = QDir::current().filePath(QStringLiteral("runtime/cache/ui"));
    QDir dir(base);
    dir.mkpath(QStringLiteral("session_posters"));
    const QString name = QString::fromLatin1(
                             QCryptographicHash::hash(videoPath.toUtf8(), QCryptographicHash::Md5).toHex())
                         + QStringLiteral(".png");
    const QString out = QDir(dir.filePath(QStringLiteral("session_posters"))).filePath(name);
    return frame.save(out, "PNG") ? out : QString();
}
} // namespace

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

    // The C++ twin of three Python literals that all named the ROLLBACK tree. Derived from the
    // resolved install, so it looks where the running ComfyUI actually writes its workflows.
    const QString comfyRoot = spellvision::shell::resolvePreferredComfyRoot(QString());
    if (comfyRoot.isEmpty())
        return {};
    return QDir(comfyRoot).filePath(QStringLiteral("user/default/workflows/ltx_api.json"));
}

} // namespace

ImageGenerationPage::ImageGenerationPage(Mode mode, QWidget *parent)
    : QWidget(parent),
      mode_(mode),
      sampling_(new spellvision::generation::SamplingController(this))
{
    uiRefreshTimer_ = new QTimer(this);
    uiRefreshTimer_->setSingleShot(true);
    connect(uiRefreshTimer_, &QTimer::timeout, this, [this]() {
        updateAssetIntelligenceUi();
        refreshPreview();
        // Riding the existing coalesced refresh rather than subscribing to four controls
        // individually: the values also change from session restore and preset application, which
        // no per-widget signal would cover without duplicating every one of those call sites.
        refreshAdvancedOverrideNotice();
    });

    previewResizeTimer_ = new QTimer(this);
    previewResizeTimer_->setSingleShot(true);
    connect(previewResizeTimer_, &QTimer::timeout, this, [this]() { refreshPreview(); });

    catalogRefreshWatcher_ = new QFutureWatcher<CatalogRefreshResult>(this);
    connect(catalogRefreshWatcher_, &QFutureWatcher<CatalogRefreshResult>::finished,
            this, &ImageGenerationPage::onCatalogRefreshFinished);
    catalogSignatureWatcher_ = new QFutureWatcher<QString>(this);
    connect(catalogSignatureWatcher_, &QFutureWatcher<QString>::finished,
            this, &ImageGenerationPage::onCatalogSignatureFinished);

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
    ensureCanvasSizeDefault();
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

    // Embeddings: also inject bare token names into prompt/negative for A1111-compatible paths.
    draft.positiveEmbeddings = positiveEmbeddings_;
    draft.negativeEmbeddings = negativeEmbeddings_;
    if (!positiveEmbeddings_.isEmpty() && promptEdit_) {
        QString p = draft.prompt;
        for (const QString &token : positiveEmbeddings_) {
            const QString bare = QFileInfo(token).completeBaseName();
            if (!bare.isEmpty() && !p.contains(bare, Qt::CaseInsensitive))
                p = p.isEmpty() ? bare : (p + QStringLiteral(", ") + bare);
        }
        draft.prompt = p;
    }
    if (!negativeEmbeddings_.isEmpty()) {
        QString n = draft.negativePrompt;
        for (const QString &token : negativeEmbeddings_) {
            const QString bare = QFileInfo(token).completeBaseName();
            if (!bare.isEmpty() && !n.contains(bare, Qt::CaseInsensitive))
                n = n.isEmpty() ? bare : (n + QStringLiteral(", ") + bare);
        }
        draft.negativePrompt = n;
    }

    draft.upscaleEnabled = upscaleEnableCheck_ && upscaleEnableCheck_->isChecked();
    draft.upscaleMethod = (upscaleMethodCombo_ ? currentComboValue(upscaleMethodCombo_) : QStringLiteral("none"));
    if (!draft.upscaleEnabled)
        draft.upscaleMethod = QStringLiteral("none");
    draft.upscaleScale = upscaleScaleSpin_ ? upscaleScaleSpin_->value() : 1.0;
    draft.upscaleModel = upscaleModelCombo_ ? currentComboValue(upscaleModelCombo_) : QString();

    draft.imageSampler = sampling_->imageSampler();
    draft.imageScheduler = sampling_->imageScheduler();
    draft.videoSampler = sampling_->videoSampler();
    draft.videoScheduler = sampling_->videoScheduler();
    draft.steps = sampling_->steps();
    draft.cfg = sampling_->cfg();
    draft.seed = sampling_->draftSeed();
    draft.width = widthSpin_ ? widthSpin_->value() : 0;
    draft.height = heightSpin_ ? heightSpin_->value() : 0;

    draft.isVideoMode = isVideoMode();
    if (draft.isVideoMode)
    {
        draft.frames = frameCountSpin_ ? frameCountSpin_->value() : 81;
        draft.fps = fpsSpin_ ? fpsSpin_->value() : 16;
        draft.videoStackMode = effectiveVideoStackMode();
        // P1 #4: thread the explicit video-family combo pick (Auto/Wan/LTX) into the draft so the
        // payload's resolved family honors it. Auto -> empty -> the policy derives from the model
        // (unchanged behavior); Wan/LTX -> that family overrides the derived one.
        switch (videoFamilySelection())
        {
        case VideoFamily::Wan: draft.videoFamilyOverride = QStringLiteral("wan"); break;
        case VideoFamily::Ltx: draft.videoFamilyOverride = QStringLiteral("ltx"); break;
        case VideoFamily::Flux3:
            draft.videoFamilyOverride = QStringLiteral("flux3");
            draft.model.clear();
            draft.modelDisplay.clear();
            draft.modelFamily.clear();
            draft.modelModality.clear();
            draft.modelRole.clear();
            draft.selectedVideoStack = QJsonObject();
            draft.videoStackMode.clear();
            break;
        case VideoFamily::Auto: break; // leave empty -> derive from the model
        }
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

    QJsonObject payload = GenerationRequestBuilder::build(draft);
    // Phase 3b: send the chosen operating point so the worker resolves the SAME bundle the UI shows.
    // Only when the selector is actually offered (>1 point, visible) and a point is picked.
    if (isVideoMode() && operatingPointCard_ && operatingPointCard_->isVisible() && !currentOperatingPoint_.isEmpty())
        payload.insert(QStringLiteral("operating_point"), currentOperatingPoint_);
    return payload;
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
    // The combo's currentData() is one of {"auto", "ltx", "wan", "flux3"}; Auto
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
        familyLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));

        auto *familyLabel = new QLabel(QStringLiteral("Video family"), videoFamilyCard_);
        familyLabel->setStyleSheet(QStringLiteral("color:%1;font-size:11px;background:transparent;border:0;")
            .arg(ThemeManager::instance().css(ThemeManager::Color::TextMid)));
        familyLayout->addWidget(familyLabel, 0, Qt::AlignVCenter);

        // Hidden backing combo (state model) -- not added to the visible layout.
        videoFamilyCombo_ = new ClickOnlyComboBox(videoFamilyCard_);
        videoFamilyCombo_->setEditable(false);
        videoFamilyCombo_->addItem(QStringLiteral("Auto (resolve from checkpoint)"), QStringLiteral("auto"));
        videoFamilyCombo_->addItem(QStringLiteral("LTX"), QStringLiteral("ltx"));
        videoFamilyCombo_->addItem(QStringLiteral("WAN"), QStringLiteral("wan"));
        videoFamilyCombo_->addItem(QStringLiteral("FLUX.3 (BFL API Preview)"), QStringLiteral("flux3"));
        configureComboBox(videoFamilyCombo_);
        videoFamilyCombo_->setVisible(false);

        // Segmented bar: tight rounded container of 3 exclusive, checkable buttons.
        auto *segmented = new QWidget(videoFamilyCard_);
        segmented->setObjectName(QStringLiteral("VideoFamilySegmented"));
        segmented->setStyleSheet(QStringLiteral(
            "#VideoFamilySegmented{background:%1;border:1px solid %2;border-radius:8px;}")
            .arg(rgbaToken(ThemeManager::Color::Surface0, 0.70),
                 ThemeManager::instance().css(ThemeManager::Color::BorderStrong)));
        auto *segLayout = new QHBoxLayout(segmented);
        segLayout->setContentsMargins(2, 2, 2, 2);
        segLayout->setSpacing(2);

        auto *familyGroup = new QButtonGroup(this);
        familyGroup->setExclusive(true);
        const QString segButtonStyle = QStringLiteral(
            "QPushButton{border:1px solid transparent;border-radius:6px;padding:3px 7px;font-size:11px;"
            "color:%1;background:transparent;}"
            "QPushButton:checked{color:%2;background:%3;border:1px solid %4;}")
            .arg(ThemeManager::instance().css(ThemeManager::Color::TextMid),
                 ThemeManager::instance().css(ThemeManager::Color::TextHi),
                 ThemeManager::instance().css(ThemeManager::Color::AccentSubtle),
                 rgbaToken(ThemeManager::Color::Accent, 0.40));
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
        videoFamilyFlux3Button_ = makeFamilyButton(QStringLiteral("F3 API"));
        if (videoFamilyFlux3Button_)
            videoFamilyFlux3Button_->setVisible(false);
        videoFamilyFlux3Button_->setToolTip(QStringLiteral("FLUX.3 hosted paid preview via the Black Forest Labs API (BFL_API_KEY required)."));
        videoFamilyAutoButton_->setChecked(true);

        // USER clicks only (clicked, NOT toggled) drive the backing combo, whose currentIndexChanged
        // fires the SAME handler the dropdown used. No programmatic-set path for the family exists
        // (restore/reset never touch it), so there is no re-fire to guard against.
        connect(videoFamilyAutoButton_, &QPushButton::clicked, this, [this]() { selectComboValue(videoFamilyCombo_, QStringLiteral("auto")); });
        connect(videoFamilyWanButton_, &QPushButton::clicked, this, [this]() { selectComboValue(videoFamilyCombo_, QStringLiteral("wan")); });
        connect(videoFamilyLtxButton_, &QPushButton::clicked, this, [this]() { selectComboValue(videoFamilyCombo_, QStringLiteral("ltx")); });
        connect(videoFamilyFlux3Button_, &QPushButton::clicked, this, [this]() { selectComboValue(videoFamilyCombo_, QStringLiteral("flux3")); });

        familyLayout->addWidget(segmented, 0, Qt::AlignVCenter);
        familyLayout->addStretch(1);

        videoFamilyResolvesLabel_ = new QLabel(videoFamilyCard_);
        videoFamilyResolvesLabel_->setObjectName(QStringLiteral("VideoFamilyResolves"));
        videoFamilyResolvesLabel_->setStyleSheet(QStringLiteral(
            "font-family:'JetBrains Mono',monospace;font-size:10px;color:%1;background:transparent;border:0;")
            .arg(ThemeManager::instance().css(ThemeManager::Color::TextLo)));
        familyLayout->addWidget(videoFamilyResolvesLabel_, 0, Qt::AlignVCenter);

        videoFamilyCard_->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Maximum);
        videoFamilyCard_->setVisible(isVideoMode());
        leftLayout->addWidget(videoFamilyCard_);

        connect(videoFamilyCombo_, qOverload<int>(&QComboBox::currentIndexChanged), this, [this]() {
            updateVideoFamilyUi();
            // The stack-mode UI consults resolvedVideoFamily() to decide
            // whether to show WAN advanced rows, so refresh it too.
            updateVideoStackModeUi();
            updateOperatingPointSelector(); // family changed -> re-render the fast/quality selector
            applyOptimalVideoSamplingDefaults();
            scheduleUiRefresh(0);
        });
    }

    auto *promptCard = createCard(QStringLiteral("PromptCard"));
    auto *promptLayout = new QVBoxLayout(promptCard);
    promptLayout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
    promptLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

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

    // Prompt-row left slot. Only I2I / I2V get a live dropzone. T2I / T2V have no image input —
    // do not render a stub "IMG" chip (it looks like a broken control).
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
        inputChipHint_->setStyleSheet(QStringLiteral("color:%1;font-size:9px;background:transparent;border:0;")
            .arg(ThemeManager::instance().css(ThemeManager::Color::TextMid)));

        inputChipClear_ = new QPushButton(QStringLiteral("×"), inputChipDropzone_);
        inputChipClear_->setObjectName(QStringLiteral("PromptInputClear"));
        inputChipClear_->setGeometry(84 - 21, 3, 18, 18);
        inputChipClear_->setCursor(Qt::PointingHandCursor);
        inputChipClear_->setStyleSheet(QStringLiteral(
            "#PromptInputClear{background:%1;color:%2;border:0;border-radius:5px;font-size:12px;}")
            .arg(rgbaToken(ThemeManager::Color::Surface0, 0.78),
                 ThemeManager::instance().css(ThemeManager::Color::TextHi)));
        inputChipClear_->setVisible(false);
        inputChipClear_->raise();
        connect(inputChipClear_, &QPushButton::clicked, this, [this]() { setInputImagePath(QString()); });

        inputChipDropzone_->setStyleSheet(QStringLiteral(
            "#PromptInputDropzone{border:1px dashed %1;border-radius:9px;background:%2;}")
            .arg(rgbaToken(ThemeManager::Color::Border, 0.30),
                 rgbaToken(ThemeManager::Color::Surface0, 0.30)));
        promptSourceSlot = inputChipDropzone_;
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
    promptRow->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
    if (promptSourceSlot)
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
    negativeRowLayout->setContentsMargins(0, ThemeManager::instance().spacing(ThemeManager::Spacing::Tight), 0, 0);
    negativeRowLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
    auto *negLabel = new QLabel(QStringLiteral("NEG"), negativeRow_);
    negLabel->setFixedWidth(48);
    negLabel->setAlignment(Qt::AlignHCenter | Qt::AlignTop);
    negLabel->setStyleSheet(QStringLiteral(
        "color:%1;font-family:'JetBrains Mono',monospace;font-size:9px;letter-spacing:1px;background:transparent;border:0;")
        .arg(ThemeManager::instance().css(ThemeManager::Color::TextLo)));
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
    inputLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
    inputLayout->addWidget(createSectionTitle(isVideoMode() ? QStringLiteral("Input Keyframe") : QStringLiteral("Input Image"), inputCard_));

    auto *dropFrame = new DropTargetFrame(inputCard_);
    dropFrame->setObjectName(QStringLiteral("InputDropCard"));
    auto *dropLayout = new QVBoxLayout(dropFrame);
    dropLayout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
    dropLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

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
    inputButtons->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
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
    quickControlsLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
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
    samplerSchedulerCardLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
    auto *samplerSchedulerHeader = new QWidget(samplerSchedulerCard);
    auto *samplerSchedulerHeaderLayout = new QHBoxLayout(samplerSchedulerHeader);
    samplerSchedulerHeaderLayout->setContentsMargins(0, 0, 0, 0);
    samplerSchedulerHeaderLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
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
    ltxLaunchLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

    // --- SPRINT MOCKUP PASS 3 DISCLOSURE PROMOTION: LTX disclosure header ---
    auto *ltxLaunchHeader = new QWidget(ltxLaunchOptionsPanel_);
    ltxLaunchHeader->setObjectName(QStringLiteral("LtxLaunchHeader"));  // SPRINT MOCKUP PASS 4 COLLAPSE FIX
    auto *ltxLaunchHeaderLayout = new QHBoxLayout(ltxLaunchHeader);
    ltxLaunchHeaderLayout->setContentsMargins(0, 0, 0, 0);
    ltxLaunchHeaderLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
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
    ltxButtonsRow->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

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
        if (sampling_->stepsSpin())
            sampling_->stepsSpin()->setValue(28);
        if (sampling_->cfgSpin())
            sampling_->cfgSpin()->setValue(7.0);

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
    outputQueueLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
    auto *outputQueueHeader = new QWidget(outputQueueCard);
    auto *outputQueueHeaderLayout = new QHBoxLayout(outputQueueHeader);
    outputQueueHeaderLayout->setContentsMargins(0, 0, 0, 0);
    outputQueueHeaderLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
    outputQueueHeaderLayout->addWidget(createSectionTitle(QStringLiteral("Output / Queue"), outputQueueCard), 1);
    outputQueueLayout->addWidget(outputQueueHeader);
    leftLayout->addWidget(outputQueueCard);

    auto *advancedCard = createCard(QStringLiteral("AdvancedCard"));
    auto *advancedLayout = new QVBoxLayout(advancedCard);
    advancedLayout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
    advancedLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
    auto *advancedHeader = new QWidget(advancedCard);
    advancedHeader->setObjectName(QStringLiteral("AdvancedHeader"));  // SPRINT MOCKUP PASS 4 COLLAPSE FIX
    auto *advancedHeaderLayout = new QHBoxLayout(advancedHeader);
    advancedHeaderLayout->setContentsMargins(0, 0, 0, 0);
    advancedHeaderLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
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

    // The preview AREA is the space a picture may take; the STACK inside it is what the aspect cap
    // shrinks. Both preview controllers fit against the area, never the stack or the label -- the
    // widget the cap constrains cannot also be the measure (preview/AspectCap.h, fitBudget).
    previewArea_ = new QWidget(canvasCard);
    previewArea_->setObjectName(QStringLiteral("PreviewArea"));
    previewArea_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    previewArea_->setMinimumSize(0, 0);
    previewStack_ = new QStackedWidget(previewArea_);
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
        " stop:0 %1, stop:0.62 %2); border:0;")
        .arg(rgbaToken(ThemeManager::Color::Accent, 0.25),
             rgbaToken(ThemeManager::Color::Accent, 0.0)));
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

    canvasEmptyTitle_ = new QLabel(QStringLiteral("Ready when you are."), canvasEmptyState_);
    canvasEmptyTitle_->setObjectName(QStringLiteral("CanvasEmptyTitle"));
    canvasEmptyTitle_->setAlignment(Qt::AlignHCenter);
    canvasEmptyTitle_->setStyleSheet(QStringLiteral(
        "color:%1;font-size:15px;font-weight:600;letter-spacing:0.2px;background:transparent;border:0;")
        .arg(ThemeManager::instance().css(ThemeManager::Color::TextHi)));
    canvasEmptySub_ = new QLabel(
        QStringLiteral("Write a prompt, lock a model, then Generate — results land here."),
        canvasEmptyState_);
    canvasEmptySub_->setObjectName(QStringLiteral("CanvasEmptySub"));
    canvasEmptySub_->setAlignment(Qt::AlignHCenter);
    canvasEmptySub_->setWordWrap(true);
    canvasEmptySub_->setMaximumWidth(360);
    canvasEmptySub_->setStyleSheet(QStringLiteral(
        "color:%1;font-size:12px;background:transparent;border:0;")
        .arg(ThemeManager::instance().css(ThemeManager::Color::TextMid)));
    emptyLayout->addSpacing(14);
    emptyLayout->addWidget(canvasEmptyTitle_, 0, Qt::AlignHCenter);
    emptyLayout->addSpacing(5);
    emptyLayout->addWidget(canvasEmptySub_, 0, Qt::AlignHCenter);
    emptyLayout->addStretch(1);

    // Metric chips (live values, refreshed in updateCanvasEmptyState).
    auto *chipsRow = new QWidget(canvasEmptyState_);
    auto *chipsLayout = new QHBoxLayout(chipsRow);
    chipsLayout->setContentsMargins(0, 0, 0, ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
    chipsLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
    const auto makeChip = [chipsRow, chipsLayout]() {
        auto *chip = new QLabel(chipsRow);
        chip->setObjectName(QStringLiteral("CanvasMetricChip"));
        chip->setStyleSheet(QStringLiteral(
            "font-family:'Cascadia Mono','Consolas',monospace;font-size:10px;color:%1;"
            "border:1px solid %2;border-radius:8px;padding:3px 8px;background:%3;")
            .arg(ThemeManager::instance().css(ThemeManager::Color::TextMid),
                 ThemeManager::instance().css(ThemeManager::Color::Border),
                 ThemeManager::instance().css(ThemeManager::Color::Surface0)));
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

    previewVideoSurface_ = new QLabel(previewVideoPage_);
    previewVideoSurface_->setObjectName(QStringLiteral("PreviewVideoSurface"));
    previewVideoSurface_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    previewVideoSurface_->setMinimumSize(0, 0);
    previewVideoSurface_->setAlignment(Qt::AlignCenter);
    previewVideoSurface_->setScaledContents(false);

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

    previewVideoLayout->addWidget(previewVideoSurface_, 1);
    previewVideoLayout->addWidget(previewVideoTransportBar_, 0);
    previewVideoLayout->addWidget(previewVideoCaptionLabel_, 0);

    previewStack_->addWidget(previewImagePage_);
    previewStack_->addWidget(previewVideoPage_);
    previewStack_->setCurrentWidget(previewImagePage_);

    mediaPreviewController_ = new spellvision::preview::MediaPreviewController(this);
    spellvision::preview::MediaPreviewBindings previewBindings;
    previewBindings.previewStack = previewStack_;
    previewBindings.sizeBudgetWidget = previewArea_;
    previewBindings.imagePage = previewImagePage_;
    previewBindings.videoPage = previewVideoPage_;
    previewBindings.videoSurface = previewVideoSurface_;
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
    imagePreviewBindings.sizeCapWidget = previewStack_;
    imagePreviewBindings.sizeBudgetWidget = previewArea_;
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

    // ErrorPillLabel elides a message to the width the row gives it and keeps the full text one
    // hover or click away; a plain QLabel with a 280px cap cut the error mid-word.
    readinessHintLabel_ = new spellvision::generation::ErrorPillLabel(canvasCard);
    readinessHintLabel_->setObjectName(QStringLiteral("ReadinessHint"));
    readinessHintLabel_->setVisible(false);

    // Simple mode hides these controls but does NOT clear them -- that is the hide-not-delete rule,
    // and it is right: a value set in Advanced must still drive generation. The gap it leaves is
    // that four of those values change the OUTPUT and nothing in Simple reveals them.
    //
    // The worst is a pinned seed. Uncheck Random in Advanced, switch to Simple, and every
    // generation returns the same image with no visible cause and no reachable control -- the user
    // has to guess that Advanced exists. Batch is the same shape (N images per click). Presets do
    // not reset any of the four: applyPreset writes steps/cfg/width/height/sampler/scheduler and
    // touches seed, batch, embeddings and upscale zero times.
    //
    // So it is stated rather than discarded. Naming the override keeps both modes true at once:
    // Advanced still governs, and Simple stops lying about what it is about to do.
    advancedOverrideLabel_ = new QLabel(canvasCard);
    advancedOverrideLabel_->setObjectName(QStringLiteral("AdvancedOverrideHint"));
    advancedOverrideLabel_->setWordWrap(false);
    advancedOverrideLabel_->setMaximumWidth(320);
    advancedOverrideLabel_->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Fixed);
    advancedOverrideLabel_->setVisible(false);

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
        persistWorkspaceSettings();
        WorkerCommandRunner::submit(WorkerCommandRunner::SubmitKind::Generate, buildCommandBindings());
    });
    connect(queueButton_, &QPushButton::clicked, this, [this, buildCommandBindings]() {
        persistWorkspaceSettings();
        WorkerCommandRunner::submit(WorkerCommandRunner::SubmitKind::Queue, buildCommandBindings());
    });
    connect(savePresetButton_, &QPushButton::clicked, this, [this]() { saveSnapshot(); });
    connect(clearButton_, &QPushButton::clicked, this, [this]() { clearForm(); });
    connect(prepLatestForI2IButton_, &QPushButton::clicked, this, &ImageGenerationPage::prepLatestForI2I);
    connect(useLatestT2IButton_, &QPushButton::clicked, this, &ImageGenerationPage::useLatestForI2I);

    auto *actionRow = new QHBoxLayout;
    actionRow->setContentsMargins(0, 0, 0, 0);
    actionRow->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
    // Mockup action row: secondary actions grouped LEFT, Generate pinned FAR RIGHT (violet hero).
    // Same button instances -- pure re-layout, connections untouched. Prep/Use-Last stay (working
    // controls the mockup doesn't show; kept in the left group).
    actionRow->addWidget(queueButton_);
    actionRow->addWidget(savePresetButton_);
    actionRow->addWidget(clearButton_);
    actionRow->addWidget(prepLatestForI2IButton_);
    actionRow->addWidget(useLatestT2IButton_);
    actionRow->addStretch(1);
    actionRow->addWidget(advancedOverrideLabel_, 0, Qt::AlignVCenter);
    actionRow->addWidget(readinessHintLabel_, 0, Qt::AlignVCenter);
    actionRow->addWidget(generateButton_);

    // --- Session outputs strip: a horizontal band of this-mode's outputs, below the preview and above
    // the action row so it's shared across the image + video preview pages. Hidden entirely when empty
    // (rebuildSessionStrip owns visibility). Thumbnails reuse the model-card cache (ModelThumbnailCache).
    sessionThumbs_ = new spellvision::assets::ModelThumbnailCache(this);
    connect(sessionThumbs_, &spellvision::assets::ModelThumbnailCache::thumbnailReady,
            this, [this](const QString &, int) { rebuildSessionStrip(); });

    sessionStrip_ = new QWidget(canvasCard);
    sessionStrip_->setObjectName(QStringLiteral("SessionStrip"));
    auto *sessionStripOuter = new QVBoxLayout(sessionStrip_);
    sessionStripOuter->setContentsMargins(0, 0, 0, 0);
    sessionStripOuter->setSpacing(0);
    auto *sessionStripScroll = new QScrollArea(sessionStrip_);
    sessionStripScroll->setObjectName(QStringLiteral("SessionStripScroll"));
    sessionStripScroll->setWidgetResizable(true);
    sessionStripScroll->setFrameShape(QFrame::NoFrame);
    sessionStripScroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    sessionStripScroll->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    sessionStripScroll->setFixedHeight(104); // ~strip, not a second grid
    auto *sessionStripInner = new QWidget(sessionStripScroll);
    sessionStripLayout_ = new QHBoxLayout(sessionStripInner);
    sessionStripLayout_->setContentsMargins(2, 2, 2, 2);
    sessionStripLayout_->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
    sessionStripLayout_->addStretch(1);
    sessionStripScroll->setWidget(sessionStripInner);
    sessionStripOuter->addWidget(sessionStripScroll);
    sessionStrip_->setVisible(false);

    // A stack whose maximum size hugs the picture (see preview/AspectCap.h) must sit centred in
    // the slot the layout still reserves for it, or a portrait render hangs off the left edge.
    // NOT setAlignment: an aligned layout item is given its size HINT, not the slot, and the
    // preview would collapse to a few pixels -- test_canvas_aspect caught exactly that. Zero-stretch
    // spacers instead: the stack (stretch 1) takes everything until its cap, and only then do the
    // spacers absorb the leftover, equally, which is what centres it.
    auto *previewCentreRow = new QHBoxLayout;
    previewCentreRow->setContentsMargins(0, 0, 0, 0);
    previewCentreRow->setSpacing(0);
    previewCentreRow->addStretch(0);
    previewCentreRow->addWidget(previewStack_, 1);
    previewCentreRow->addStretch(0);
    auto *previewCentreColumn = new QVBoxLayout(previewArea_);
    previewCentreColumn->setContentsMargins(0, 0, 0, 0);
    previewCentreColumn->setSpacing(0);
    previewCentreColumn->addStretch(0);
    previewCentreColumn->addLayout(previewCentreRow, 1);
    previewCentreColumn->addStretch(0);
    canvasLayout->addWidget(previewArea_, 1);
    canvasLayout->addWidget(sessionStrip_, 0);
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
    stackCardLayout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug),
                                        ThemeManager::instance().spacing(ThemeManager::Spacing::Snug),
                                        ThemeManager::instance().spacing(ThemeManager::Spacing::Snug),
                                        ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
    stackCardLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
    stackCard_->setMinimumWidth(0);
    stackCard_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Minimum);

    auto *checkpointValueCard = new QFrame(stackCard_);
    checkpointValueCard->setObjectName(QStringLiteral("InputDropCard"));
    auto *checkpointValueLayout = new QHBoxLayout(checkpointValueCard);
    checkpointValueLayout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
    checkpointValueLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

    selectedModelLabel_ = new QLabel(isVideoMode() ? QStringLiteral("No video model stack selected") : QStringLiteral("No checkpoint selected"), checkpointValueCard);
    selectedModelLabel_->setObjectName(QStringLiteral("SectionBody"));
    selectedModelLabel_->setWordWrap(true);
    checkpointValueLayout->addWidget(selectedModelLabel_, 1);

    browseModelButton_ = new QPushButton(QStringLiteral("Browse"), stackCard_);
    browseModelButton_->setObjectName(QStringLiteral("SecondaryActionButton"));
    clearModelButton_ = new QPushButton(QStringLiteral("Clear"), stackCard_);
    clearModelButton_->setObjectName(QStringLiteral("TertiaryActionButton"));
    refreshModelsButton_ = new QPushButton(QStringLiteral("Refresh"), stackCard_);
    refreshModelsButton_->setObjectName(QStringLiteral("TertiaryActionButton"));
    refreshModelsButton_->setToolTip(QStringLiteral("Re-scan the models folder — picks up files added or removed while the app is running."));
    connect(browseModelButton_, &QPushButton::clicked, this, &ImageGenerationPage::showCheckpointPicker);
    connect(clearModelButton_, &QPushButton::clicked, this, [this]() { setSelectedModel(QString(), QString()); });
    connect(refreshModelsButton_, &QPushButton::clicked, this, &ImageGenerationPage::refreshModelCatalog);

    // Fake workflow presets removed — real workflow drop/load is on the Model Stack.
    // Keep a single internal "Custom" state for draft binding if needed.
    workflowCombo_ = new ClickOnlyComboBox(stackCard_);
    workflowCombo_->setEditable(false);
    workflowCombo_->addItem(QStringLiteral("Cockpit (no workflow graph)"), QStringLiteral("Default Canvas"));
    configureComboBox(workflowCombo_);
    workflowCombo_->setToolTip(
        QStringLiteral("Optional binding only. Load a real Comfy workflow via Drop / Load workflow… below."));

    loraStackContainer_ = new QWidget(stackCard_);
    loraStackLayout_ = new QVBoxLayout(loraStackContainer_);
    loraStackLayout_->setContentsMargins(0, 0, 0, 0);
    loraStackLayout_->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

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
    stackForm->setHorizontalSpacing(8);
    stackForm->setVerticalSpacing(8);
    stackForm->setColumnMinimumWidth(0, 0);
    stackForm->setColumnStretch(0, 0);
    stackForm->setColumnStretch(1, 1);

    int stackRow = 0;
    stackForm->addWidget(new QLabel(isVideoMode() ? QStringLiteral("Model Stack") : QStringLiteral("Checkpoint"), stackCard_), stackRow, 0);
    stackForm->addWidget(checkpointValueCard, stackRow, 1);
    ++stackRow;
    auto *checkpointActions = new QWidget(stackCard_);
    auto *checkpointActionsLayout = new QHBoxLayout(checkpointActions);
    checkpointActionsLayout->setContentsMargins(0, 0, 0, 0);
    checkpointActionsLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
    checkpointActionsLayout->addWidget(browseModelButton_);
    checkpointActionsLayout->addWidget(clearModelButton_);
    checkpointActionsLayout->addWidget(refreshModelsButton_);
    checkpointActionsLayout->addStretch(1);
    stackForm->addWidget(checkpointActions, stackRow, 1);
    ++stackRow;

    videoComponentPanel_ = new QWidget(stackCard_);
    auto *videoComponentLayout = new QVBoxLayout(videoComponentPanel_);
    videoComponentLayout->setContentsMargins(0, 0, 0, 0);
    videoComponentLayout->setSpacing(6);

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

    // Stacked cells (label above field) — two-column grids double-spend width and were the main
    // driver of T2V inspector clipping at restore / half-screen. Wrap label+field so visibility
    // gates (WAN dual-noise / family) hide the whole cell as one layout unit.
    auto addVideoStacked = [videoComponentLayout, this](QWidget *&rowHost, const QString &text, QWidget *field) {
        auto *cell = new QWidget(videoComponentPanel_);
        cell->setMinimumWidth(0);
        cell->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Minimum);
        auto *cellLay = new QVBoxLayout(cell);
        cellLay->setContentsMargins(0, 0, 0, 0);
        cellLay->setSpacing(3);
        auto *lab = new QLabel(text, cell);
        lab->setObjectName(QStringLiteral("CompactFieldLabel"));
        field->setParent(cell);
        field->setMinimumWidth(0);
        field->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
        cellLay->addWidget(lab);
        cellLay->addWidget(field);
        videoComponentLayout->addWidget(cell);
        rowHost = cell;
    };
    QWidget *primaryHost = nullptr;
    QWidget *textHost = nullptr;
    QWidget *vaeHost = nullptr;
    QWidget *visionHost = nullptr;
    addVideoStacked(videoStackModeRow_, QStringLiteral("Stack Mode"), videoStackModeCombo_);
    addVideoStacked(primaryHost, QStringLiteral("Primary"), videoPrimaryModelCombo_);
    addVideoStacked(videoHighNoiseRow_, QStringLiteral("High Noise"), videoHighNoiseModelCombo_);
    addVideoStacked(videoLowNoiseRow_, QStringLiteral("Low Noise"), videoLowNoiseModelCombo_);
    addVideoStacked(textHost, QStringLiteral("Text"), videoTextEncoderCombo_);
    addVideoStacked(vaeHost, QStringLiteral("VAE"), videoVaeCombo_);
    addVideoStacked(visionHost, QStringLiteral("Vision"), videoClipVisionCombo_);
    Q_UNUSED(primaryHost);
    Q_UNUSED(textHost);
    Q_UNUSED(vaeHost);
    Q_UNUSED(visionHost);
    videoComponentPanel_->setVisible(isVideoMode());
    videoComponentPanel_->setMinimumWidth(0);
    videoComponentPanel_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Minimum);

    if (isVideoMode())
    {
        // Full-width under a section title — no side label column burning inspector width.
        componentsRowLabel_ = new QLabel(QStringLiteral("Components"), stackCard_);
        componentsRowLabel_->setObjectName(QStringLiteral("CompactFieldLabel"));
        stackForm->addWidget(componentsRowLabel_, stackRow, 0, 1, 2);
        ++stackRow;
        stackForm->addWidget(videoComponentPanel_, stackRow, 0, 1, 2);
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
    loraActionsLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
    loraActionsLayout->addWidget(addLoraButton_);
    loraActionsLayout->addWidget(clearLorasButton_);
    loraActionsLayout->addStretch(1);
    stackForm->addWidget(loraActions, stackRow, 1);
    ++stackRow;
    stackForm->addWidget(new QLabel(QStringLiteral("Stack Summary"), stackCard_), stackRow, 0, Qt::AlignTop);
    stackForm->addWidget(loraStackSummaryLabel_, stackRow, 1);
    stackToolsLayout_ = new QBoxLayout(QBoxLayout::TopToBottom);
    stackToolsLayout_->setContentsMargins(0, 0, 0, 0);
    stackToolsLayout_->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
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

    loadWorkflowButton_ = new QPushButton(QStringLiteral("Load workflow…"), stackCard_);
    loadWorkflowButton_->setObjectName(QStringLiteral("SecondaryActionButton"));
    loadWorkflowButton_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    connect(loadWorkflowButton_, &QPushButton::clicked, this, &ImageGenerationPage::browseWorkflowFile);
    stackToolsLayout_->addWidget(loadWorkflowButton_);

    runWorkflowButton_ = new QPushButton(QStringLiteral("Run workflow"), stackCard_);
    runWorkflowButton_->setObjectName(QStringLiteral("SecondaryActionButton"));
    runWorkflowButton_->setEnabled(false);
    runWorkflowButton_->setToolTip(QStringLiteral("Import + queue the loaded workflow with the cockpit model/LoRA overrides."));
    connect(runWorkflowButton_, &QPushButton::clicked, this, &ImageGenerationPage::runPendingWorkflow);
    stackToolsLayout_->addWidget(runWorkflowButton_);

    workflowDropFrame_ = new DropTargetFrame(stackCard_);
    workflowDropFrame_->setObjectName(QStringLiteral("WorkflowDropFrame"));
    workflowDropFrame_->setMinimumHeight(44);
    auto *wfDropLay = new QVBoxLayout(workflowDropFrame_);
    wfDropLay->setContentsMargins(8, 6, 8, 6);
    workflowDropLabel_ = new QLabel(QStringLiteral("Drop Comfy workflow .json here to load & run"), workflowDropFrame_);
    workflowDropLabel_->setObjectName(QStringLiteral("WorkflowDropLabel"));
    workflowDropLabel_->setAlignment(Qt::AlignCenter);
    workflowDropLabel_->setWordWrap(true);
    wfDropLay->addWidget(workflowDropLabel_);
    workflowDropFrame_->onFileDropped = [this](const QString &path) { acceptDroppedWorkflow(path); };
    stackToolsLayout_->addWidget(workflowDropFrame_);

    stackCardLayout->addWidget(createSectionTitle(QStringLiteral("Model Stack"), stackCard_));
    stackCardLayout->addLayout(stackForm);
    stackCardLayout->addLayout(stackToolsLayout_);
    rightLayout->addWidget(stackCard_);

    settingsCard_ = createCard(QStringLiteral("OutputCard"));
    auto *settingsCardLayout = new QVBoxLayout(settingsCard_);
    settingsCardLayout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
    settingsCardLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

    sampling_->create(quickControlsCard);

    widthSpin_ = new QSpinBox(quickControlsCard);
    widthSpin_->setRange(0, 8192);
    widthSpin_->setSingleStep(64);
    widthSpin_->setSpecialValueText(QStringLiteral("—"));
    widthSpin_->setValue(0);
    configureSpinBox(widthSpin_);

    heightSpin_ = new QSpinBox(quickControlsCard);
    heightSpin_->setRange(0, 8192);
    heightSpin_->setSingleStep(64);
    heightSpin_->setSpecialValueText(QStringLiteral("—"));
    heightSpin_->setValue(0);
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
        label->setMinimumWidth(48);
        label->setMaximumWidth(72);
        label->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Preferred);
        label->setObjectName(QStringLiteral("CompactFieldLabel"));
        label->setToolTip(labelText);

        field->setParent(rowWidget);
        field->setMinimumWidth(0); // allow shrink at half-screen; Expanding fills the row
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
        field->setMinimumWidth(0);
        field->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

        cellLayout->addWidget(label);
        cellLayout->addWidget(field);
        return cellWidget;
    };

    auto *aspectPresetCombo = new ClickOnlyComboBox(quickControlsCard);
    aspectPresetCombo->addItem(QStringLiteral("Custom"), QString());
    aspectPresetCombo->addItem(QStringLiteral("Portrait 768×1024"), QStringLiteral("768x1024"));
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
    samplerRow_ = makeStackedField(quickControlsCard, QStringLiteral("Image Sampler"), sampling_->samplerCombo());
    schedulerRow_ = makeStackedField(quickControlsCard, QStringLiteral("Image Scheduler"), sampling_->schedulerCombo());
    videoSamplerRow_ = makeStackedField(quickControlsCard, QStringLiteral("Video Sampler"), sampling_->videoSamplerCombo());
    videoSchedulerRow_ = makeStackedField(quickControlsCard, QStringLiteral("Video Scheduler"), sampling_->videoSchedulerCombo());
    // Base mode guard (image-only / video-only). updateDisclosure() then AND-composes the disclosure
    // gate on top of these (Advanced-only), so it can never reveal a row the mode already hides.
    samplerRow_->setVisible(!isVideoMode());
    schedulerRow_->setVisible(!isVideoMode());
    videoSamplerRow_->setVisible(isVideoMode());
    videoSchedulerRow_->setVisible(isVideoMode());
    stepsRow_ = makeStackedField(quickControlsCard, QStringLiteral("Steps"), sampling_->stepsSpin());
    cfgRow_ = makeStackedField(quickControlsCard, QStringLiteral("CFG"), sampling_->cfgSpin());
    seedRow_ = makeStackedField(quickControlsCard, QStringLiteral("Seed"), sampling_->seedSpin());
    if (sampling_->seedRandomCheck() && seedRow_)
    {
        if (auto *rowLayout = qobject_cast<QBoxLayout *>(seedRow_->layout()))
            rowLayout->insertWidget(1, sampling_->seedRandomCheck());
    }
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

    outputFolderLabel_ = new QLabel(QStringLiteral("Not set — Browse…"), outputQueueCard);
    outputFolderLabel_->setObjectName(QStringLiteral("OutputQueueBodyHint"));
    outputFolderLabel_->setWordWrap(true);
    {
        QSettings destSettings;
        const QString savedDest = destSettings.value(QStringLiteral("image_generation/output_folder")).toString().trimmed();
        if (!savedDest.isEmpty() && QDir(savedDest).exists())
            outputFolderLabel_->setText(QDir::toNativeSeparators(savedDest));
    }

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
    outputFolderBrowseButton_ = new QPushButton(QStringLiteral("Browse…"), outputQueueCard);
    outputFolderBrowseButton_->setObjectName(QStringLiteral("OutputQueueBrowse"));
    queueHuntListButton_ = new QPushButton(QStringLiteral("Queue list…"), outputQueueCard);
    queueHuntListButton_->setObjectName(QStringLiteral("OutputQueueHuntList"));
    queueHuntListButton_->setToolTip(QStringLiteral("Queue named jobs from a text file. Each line: stem | seed | prompt"));
    auto *outputFolderRow = new QHBoxLayout();
    outputFolderRow->setContentsMargins(0, 0, 0, 0);
    outputFolderRow->addWidget(outputFolderLabel_, 1);
    outputFolderRow->addWidget(outputFolderBrowseButton_, 0);
    outputFolderRow->addWidget(queueHuntListButton_, 0);
    // A batch-testing tool (stem | seed | prompt files, plate.png salvage), not a user control.
    // Same gate as the hidden rail modes; never visible in a shipped build without the env var.
    queueHuntListButton_->setVisible(spellvision::shell::ShellNavigationController::devToolsVisible());

    outputQueueLayout->addWidget(batchRow_);
    outputQueueLayout->addWidget(prefixRow_);
    outputQueueLayout->addWidget(outputFolderTitle);
    outputQueueLayout->addLayout(outputFolderRow);

    // Embeddings + Upscale (image modes; Advanced-gated in updateDisclosure)
    embeddingRow_ = new QWidget(outputQueueCard);
    embeddingRow_->setObjectName(QStringLiteral("EmbeddingRow"));
    auto *embLay = new QVBoxLayout(embeddingRow_);
    embLay->setContentsMargins(0, 4, 0, 0);
    embLay->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
    embLay->addWidget(new QLabel(QStringLiteral("Embeddings (TI)"), embeddingRow_));
    positiveEmbeddingLabel_ = new QLabel(QStringLiteral("Positive: none"), embeddingRow_);
    positiveEmbeddingLabel_->setWordWrap(true);
    negativeEmbeddingLabel_ = new QLabel(QStringLiteral("Negative: none"), embeddingRow_);
    negativeEmbeddingLabel_->setWordWrap(true);
    embLay->addWidget(positiveEmbeddingLabel_);
    embLay->addWidget(negativeEmbeddingLabel_);
    auto *embBtns = new QHBoxLayout;
    pickPositiveEmbeddingBtn_ = new QPushButton(QStringLiteral("+ Pos"), embeddingRow_);
    pickNegativeEmbeddingBtn_ = new QPushButton(QStringLiteral("+ Neg"), embeddingRow_);
    clearEmbeddingsBtn_ = new QPushButton(QStringLiteral("Clear"), embeddingRow_);
    connect(pickPositiveEmbeddingBtn_, &QPushButton::clicked, this, &ImageGenerationPage::pickPositiveEmbedding);
    connect(pickNegativeEmbeddingBtn_, &QPushButton::clicked, this, &ImageGenerationPage::pickNegativeEmbedding);
    connect(clearEmbeddingsBtn_, &QPushButton::clicked, this, &ImageGenerationPage::clearEmbeddings);
    embBtns->addWidget(pickPositiveEmbeddingBtn_);
    embBtns->addWidget(pickNegativeEmbeddingBtn_);
    embBtns->addWidget(clearEmbeddingsBtn_);
    embLay->addLayout(embBtns);
    outputQueueLayout->addWidget(embeddingRow_);

    upscaleRow_ = new QWidget(outputQueueCard);
    upscaleRow_->setObjectName(QStringLiteral("UpscaleRow"));
    auto *upLay = new QVBoxLayout(upscaleRow_);
    upLay->setContentsMargins(0, 4, 0, 0);
    upLay->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
    upscaleEnableCheck_ = new QCheckBox(QStringLiteral("Post-upscale result"), upscaleRow_);
    upLay->addWidget(upscaleEnableCheck_);
    upscaleMethodCombo_ = new ClickOnlyComboBox(upscaleRow_);
    upscaleMethodCombo_->addItem(QStringLiteral("Lanczos (algorithmic)"), QStringLiteral("lanczos"));
    upscaleMethodCombo_->addItem(QStringLiteral("Nearest"), QStringLiteral("nearest"));
    upscaleMethodCombo_->addItem(QStringLiteral("Bilinear"), QStringLiteral("bilinear"));
    upscaleMethodCombo_->addItem(QStringLiteral("Pixel (Comfy ESRGAN)"), QStringLiteral("pixel"));
    upscaleMethodCombo_->addItem(QStringLiteral("Model / PIL fallback"), QStringLiteral("model"));
    configureComboBox(upscaleMethodCombo_);
    upLay->addWidget(new QLabel(QStringLiteral("Method"), upscaleRow_));
    upLay->addWidget(upscaleMethodCombo_);
    upscaleScaleSpin_ = new QDoubleSpinBox(upscaleRow_);
    upscaleScaleSpin_->setRange(1.0, 4.0);
    upscaleScaleSpin_->setSingleStep(0.5);
    upscaleScaleSpin_->setValue(2.0);
    upscaleScaleSpin_->setDecimals(2);
    upLay->addWidget(new QLabel(QStringLiteral("Scale"), upscaleRow_));
    upLay->addWidget(upscaleScaleSpin_);
    upscaleModelCombo_ = new ClickOnlyComboBox(upscaleRow_);
    upscaleModelCombo_->addItem(QStringLiteral("Auto / first found"), QString());
    configureComboBox(upscaleModelCombo_);
    upLay->addWidget(new QLabel(QStringLiteral("Upscale model"), upscaleRow_));
    upLay->addWidget(upscaleModelCombo_);
    outputQueueLayout->addWidget(upscaleRow_);
    if (isVideoMode()) {
        if (embeddingRow_)
            embeddingRow_->setVisible(false);
        if (upscaleRow_)
            upscaleRow_->setVisible(false);
    }

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

    // Non-blocking LoRA/checkpoint architecture-mismatch warning (item 2). Hidden unless a clear
    // cross-architecture stack is detected; the LoRA is never removed or blocked.
    aiCompatWarningLabel_ = new QLabel(QString(), settingsCard_);
    aiCompatWarningLabel_->setObjectName(QStringLiteral("AiCompatWarning"));
    aiCompatWarningLabel_->setWordWrap(true);
    aiCompatWarningLabel_->setVisible(false);
    aiCompatWarningLabel_->setStyleSheet(QStringLiteral("color:%1;%2")
        .arg(ThemeManager::instance().css(ThemeManager::Color::Warning),
             ThemeManager::instance().fontCss(ThemeManager::Type::Detail)));
    settingsCardLayout->addWidget(aiCompatWarningLabel_);

    // Stack group: small uppercase label + flow row of chips.
    settingsCardLayout->addSpacing(6);
    aiStackGroupLabel_ = new QLabel(QStringLiteral("STACK"), settingsCard_);
    aiStackGroupLabel_->setObjectName(QStringLiteral("AiGroupLabel"));
    settingsCardLayout->addWidget(aiStackGroupLabel_);

    aiStackChipsRow_ = new QWidget(settingsCard_);
    aiStackChipsRow_->setObjectName(QStringLiteral("AiChipsRow"));
    aiStackChipsRow_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Minimum);
    aiStackChipsLayout_ = new QHBoxLayout(aiStackChipsRow_);
    aiStackChipsLayout_->setContentsMargins(0, 2, 0, 0);
    aiStackChipsLayout_->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
    // No trailing stretch — chips pack left and the row can elide instead of forcing inspector width.
    settingsCardLayout->addWidget(aiStackChipsRow_);

    // Components group: video modes only (visibility set in update).
    aiComponentsGroupContainer_ = new QWidget(settingsCard_);
    aiComponentsGroupContainer_->setObjectName(QStringLiteral("AiComponentsGroupContainer"));
    {
        auto *componentsLayout = new QVBoxLayout(aiComponentsGroupContainer_);
        componentsLayout->setContentsMargins(0, ThemeManager::instance().spacing(ThemeManager::Spacing::Tight), 0, 0);
        componentsLayout->setSpacing(2);

        aiComponentsGroupLabel_ = new QLabel(QStringLiteral("COMPONENTS"), aiComponentsGroupContainer_);
        aiComponentsGroupLabel_->setObjectName(QStringLiteral("AiGroupLabel"));
        componentsLayout->addWidget(aiComponentsGroupLabel_);

        aiComponentsChipsRow_ = new QWidget(aiComponentsGroupContainer_);
        aiComponentsChipsRow_->setObjectName(QStringLiteral("AiChipsRow"));
        aiComponentsChipsRow_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Minimum);
        aiComponentsChipsLayout_ = new QHBoxLayout(aiComponentsChipsRow_);
        aiComponentsChipsLayout_->setContentsMargins(0, 2, 0, 0);
        aiComponentsChipsLayout_->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
        componentsLayout->addWidget(aiComponentsChipsRow_);
    }
    settingsCardLayout->addWidget(aiComponentsGroupContainer_);

    // Timing row (video modes only): three metric pairs over a top border.
    aiTimingRow_ = new QFrame(settingsCard_);
    aiTimingRow_->setObjectName(QStringLiteral("AiTimingRow"));
    {
        auto *timingLayout = new QHBoxLayout(aiTimingRow_);
        timingLayout->setContentsMargins(0, ThemeManager::instance().spacing(ThemeManager::Spacing::Tight), 0, 0);
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
    if (QWidget *modelStack = rightScrollArea_->takeWidget()) {
        // Detached from the old 320–460 scroll rail — clear any inherited min width so the
        // adaptive inspector budget can shrink below that floor at half-screen.
        modelStack->setMinimumWidth(0);
        modelStack->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Minimum);
        modelTab->addWidget(modelStack);
    }
    modelTab->addStretch(1);

    // Sampling tab <- steps/cfg + seed/frames/fps (moved out of QuickControls) + sampler card.
    QVBoxLayout *samplingTab = cockpitInspector_->tabContentLayout(CockpitInspector::Sampling);

    // Phase 3b: the Speed (fast/quality) selector sits at the TOP of the Sampling tab -- it DRIVES the
    // steps/cfg/sampler/scheduler/shift below it, so it lives above them. Rendered generically per the
    // resolved video family's shipped operating points (hidden when <=1). Video-only.
    operatingPointCard_ = createCard(QStringLiteral("OperatingPointCard"));
    {
        auto *opLayout = new QHBoxLayout(operatingPointCard_);
        opLayout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug),
                                     ThemeManager::instance().spacing(ThemeManager::Spacing::Tight),
                                     ThemeManager::instance().spacing(ThemeManager::Spacing::Snug),
                                     ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
        opLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
        auto *speedLabel = new QLabel(QStringLiteral("Speed"), operatingPointCard_);
        speedLabel->setObjectName(QStringLiteral("OperatingPointLabel"));
        opLayout->addWidget(speedLabel);
        operatingPointGroup_ = new QButtonGroup(this);
        operatingPointGroup_->setExclusive(true);
        operatingPointButtonRow_ = new QHBoxLayout;
        operatingPointButtonRow_->setContentsMargins(0, 0, 0, 0);
        operatingPointButtonRow_->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
        opLayout->addLayout(operatingPointButtonRow_, 1);
        // USER clicks apply the bundle (buttonClicked, not toggled -- programmatic setChecked won't fire).
        connect(operatingPointGroup_, &QButtonGroup::buttonClicked, this, [this](QAbstractButton *b) {
            applyOperatingPoint(b->property("opName").toString());
        });
    }
    operatingPointCard_->setVisible(false);
    samplingTab->addWidget(operatingPointCard_);

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
    connect(sampling_->samplerCombo(), &QComboBox::currentTextChanged, this, refreshers);
    connect(sampling_->schedulerCombo(), &QComboBox::currentTextChanged, this, refreshers);
    if (sampling_->videoSamplerCombo())
        connect(sampling_->videoSamplerCombo(), &QComboBox::currentTextChanged, this, refreshers);
    if (sampling_->videoSchedulerCombo())
        connect(sampling_->videoSchedulerCombo(), &QComboBox::currentTextChanged, this, refreshers);
    connect(sampling_->stepsSpin(), qOverload<int>(&QSpinBox::valueChanged), this, refreshers);
    connect(sampling_->cfgSpin(), qOverload<double>(&QDoubleSpinBox::valueChanged), this, refreshers);
    connect(sampling_->seedSpin(), qOverload<int>(&QSpinBox::valueChanged), this, refreshers);
    connect(widthSpin_, qOverload<int>(&QSpinBox::valueChanged), this, refreshers);
    connect(heightSpin_, qOverload<int>(&QSpinBox::valueChanged), this, refreshers);
    if (frameCountSpin_)
        connect(frameCountSpin_, qOverload<int>(&QSpinBox::valueChanged), this, refreshers);
    if (fpsSpin_)
        connect(fpsSpin_, qOverload<int>(&QSpinBox::valueChanged), this, refreshers);
    connect(batchSpin_, qOverload<int>(&QSpinBox::valueChanged), this, refreshers);
    connect(outputPrefixEdit_, &QLineEdit::textChanged, this, refreshers);
    if (outputFolderBrowseButton_)
        connect(outputFolderBrowseButton_, &QPushButton::clicked, this, &ImageGenerationPage::chooseOutputFolder);
    if (queueHuntListButton_)
        connect(queueHuntListButton_, &QPushButton::clicked, this, &ImageGenerationPage::queueHuntList);
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

void ImageGenerationPage::scheduleUiRefresh(int delayMs)
{
    if (!uiRefreshTimer_)
    {
        refreshPreview();
        return;
    }

    uiRefreshTimer_->start(qBound(0, delayMs, 250));
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

    // Inspector width budget — critical for T2V/I2V at half-screen / restore sizes.
    // Give the inspector a share of content width but never starve the canvas.
    if (cockpitInspector_) {
        const int contentW = qMax(0, measuredContentWidth());
        int budget = 400;
        if (contentW <= 0) {
            budget = 360; // first layout pass before geometry settles
        } else if (mode == AdaptiveLayoutMode::Compact) {
            // Half-screen / narrow restore: keep canvas majority.
            budget = qBound(280, contentW * 30 / 100, 360);
        } else if (mode == AdaptiveLayoutMode::Medium) {
            budget = qBound(320, contentW * 28 / 100, 400);
        } else {
            budget = qBound(360, contentW * 26 / 100, 460);
        }
        // Leave at least ~400px for the canvas + action row chrome when possible.
        const int canvasFloor = 400;
        if (contentW > canvasFloor + 280)
            budget = qMin(budget, contentW - canvasFloor);
        cockpitInspector_->setWidthBudget(budget);
    }
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

void ImageGenerationPage::showGenerationError(const QString &message)
{
    const QString trimmed = message.trimmed();
    if (trimmed.isEmpty() || !readinessHintLabel_)
        return;

    errorBannerActive_ = true;

    // One-line summary on the pill; full text in the tooltip. Long messages / tracebacks
    // are routed to the log pane by the caller, not crammed into the banner.
    QString oneLine = trimmed;
    const int nl = oneLine.indexOf(QLatin1Char('\n'));
    if (nl >= 0)
        oneLine = oneLine.left(nl).trimmed();
    if (oneLine.size() > 150)
        oneLine = oneLine.left(147) + QStringLiteral("…");

    const auto &tm = ThemeManager::instance();
    // Detach from the ancestor #ReadinessHint rule (which owns color) so a local error
    // style applies — the theme-migration specificity gotcha — then style as an error pill.
    readinessHintLabel_->setObjectName(QString());
    readinessHintLabel_->setStyleSheet(QStringLiteral(
        "color:%1; font-size:11px; font-weight:800; background:%2; "
        "border:1px solid %3; border-radius:11px; padding:6px 10px; min-height:26px;")
        .arg(tm.css(ThemeManager::Color::Error),
             rgbaToken(ThemeManager::Color::Error, 0.14),
             tm.css(ThemeManager::Color::Error)));
    readinessHintLabel_->setMessage(oneLine, trimmed);
    readinessHintLabel_->setVisible(true);
    if (readinessHintLabel_->style())
    {
        readinessHintLabel_->style()->unpolish(readinessHintLabel_);
        readinessHintLabel_->style()->polish(readinessHintLabel_);
    }
}

void ImageGenerationPage::clearGenerationError()
{
    if (!errorBannerActive_)
        return;

    errorBannerActive_ = false;
    if (readinessHintLabel_)
    {
        readinessHintLabel_->clearMessage();
        // Reattach to the shared #ReadinessHint styling + drop the local error style.
        readinessHintLabel_->setStyleSheet(QString());
        readinessHintLabel_->setObjectName(QStringLiteral("ReadinessHint"));
        if (readinessHintLabel_->style())
        {
            readinessHintLabel_->style()->unpolish(readinessHintLabel_);
            readinessHintLabel_->style()->polish(readinessHintLabel_);
        }
    }
    // Restore the normal readiness hint / hidden state.
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

    // Exact, or nothing. The substring fallback was a quiet way to restore a DIFFERENT render:
    // the sampler list holds euler and euler_ancestral, and "contains" matches whichever comes
    // first, so recalling a euler render could select euler_ancestral and reproduce something else.
    // A restore that cannot find its sampler must leave the family default and say so.
    const QString sampler = draft.value(QStringLiteral("sampler")).toString().trimmed();
    if (!sampler.isEmpty() && !selectComboValue(sampling_->samplerCombo(), sampler))
        qWarning("restored render used sampler '%s', which this family does not offer; keeping the "
                 "family default", qPrintable(sampler));

    const QString scheduler = draft.value(QStringLiteral("scheduler")).toString().trimmed();
    if (!scheduler.isEmpty() && !selectComboValue(sampling_->schedulerCombo(), scheduler))
        qWarning("restored render used scheduler '%s', which this family does not offer; keeping "
                 "the family default", qPrintable(scheduler));

    const int steps = draft.value(QStringLiteral("steps")).toInt(0);
    if (steps > 0 && sampling_->stepsSpin())
        sampling_->stepsSpin()->setValue(steps);

    if (draft.contains(QStringLiteral("cfg")) && sampling_->cfgSpin())
        sampling_->cfgSpin()->setValue(draft.value(QStringLiteral("cfg")).toDouble());

    const qlonglong seed = draft.value(QStringLiteral("seed")).toVariant().toLongLong();
    if (seed > 0 && sampling_->seedSpin())
        sampling_->seedSpin()->setValue(static_cast<int>(qMin<qlonglong>(seed, 999999999LL)));

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

void ImageGenerationPage::showEvent(QShowEvent *event)
{
    QWidget::showEvent(event);
    // Phase 7: re-assert the disclosure gate when the page becomes visible. The startup gate (pushed
    // while the page was still hidden) doesn't reliably stick for the reparented model-stack GRID
    // rows (Workflow/Components); re-applying on show fixes it for all gated controls. Idempotent.
    updateDisclosure(advanced_);

    if (isVideoMode()) {
        updateVideoFamilyUi();
        populateVideoComponentControls();
        maybeAutoPopulateVideoComponents();
    }

    // Responsive final cleanup: first show (and return from full-screen) must reflow the inspector
    // budget immediately, then once more after the layout engine settles contentsRect().
    updateAdaptiveLayout();
    QTimer::singleShot(0, this, [this]() {
        if (!isVisible())
            return;
        updateAdaptiveLayout();
    });

    // Runtime model pickup (zero-click layer): on navigate, run a cheap (path,size,
    // mtime) probe and re-scan only when the model tree actually changed since the
    // last scan. Decouples cheap detection from the expensive classifier scan, so
    // hands-off pickup costs ~nothing when nothing changed. Skips while a refresh is
    // in flight; skips before the first scan has established a baseline signature.
    checkCatalogSignatureAsync();
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



QString ImageGenerationPage::currentComboValue(const QComboBox *combo) const
{
    return comboStoredValue(combo);
}

void ImageGenerationPage::applyPresetSampling(const QString &preset, const QString &sampler,
                                              const QString &scheduler)
{
    // A preset owns prompt, steps, cfg and size. Sampling belongs to the family resolver, which is
    // the only thing that knows what this family can actually run -- so a preset may PREFER a
    // sampler and may not impose one.
    //
    // The video presets imposed dpmpp_2m + karras, and karras is not in wan's allow-list at all
    // (simple / sgm_uniform / normal); LTX has no scheduler input whatsoever. selectComboValue
    // returned false in both cases and the return was discarded, so the preset silently did half of
    // what it said. There is no single pair that is legal across wan, ltx and hunyuan, which is the
    // finding -- not a wrong pair, a wrong owner.
    const auto prefer = [&](QComboBox *combo, const QString &value, const char *what) {
        if (!combo || value.isEmpty())
            return;
        if (selectComboValue(combo, value))
            return;
        qWarning("preset '%s' prefers %s '%s', which this family does not offer; keeping the "
                 "family default", qPrintable(preset), what, qPrintable(value));
    };
    prefer(sampling_->samplerCombo(), sampler, "sampler");
    prefer(sampling_->schedulerCombo(), scheduler, "scheduler");
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

void ImageGenerationPage::triggerGenerate()
{
    // Reuse the exact button path (readiness gate, MainWindow submission choke, log visibility). A
    // disabled button click is a no-op, which correctly respects a not-ready state.
    if (generateButton_)
        generateButton_->click();
}

void ImageGenerationPage::randomizeSeed()
{
    if (sampling_->seedSpin())
        sampling_->seedSpin()->setValue(0); // 0 is the spin's special "Random" value
}

void ImageGenerationPage::copyPromptToClipboard()
{
    if (!promptEdit_)
        return;
    if (QClipboard *clip = QGuiApplication::clipboard())
        clip->setText(promptEdit_->toPlainText());
}

void ImageGenerationPage::clearPromptText()
{
    if (promptEdit_)
        promptEdit_->clear();
}

void ImageGenerationPage::clearLoraStack()
{
    // Identical to the "Clear LoRAs" button handler.
    if (loraStackController_)
        loraStackController_->clear();
    else
    {
        loraStack_.clear();
        rebuildLoraStackUi();
        scheduleUiRefresh(0);
    }
}

