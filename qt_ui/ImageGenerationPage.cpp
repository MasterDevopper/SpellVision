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
#include "shell/ModelsLibraryPaths.h"
#include "generation/CockpitInspector.h"
#include "generation/CockpitLayout.h"
#include "generation/SamplingController.h"
#include "generation/UpscaleController.h"
#include "generation/CockpitWidgetKit.h"
#include "ImageGenerationPage_units.h"
#include "workers/WorkerCommandRunner.h"
#include "assets/ModelStackState.h"
#include "assets/LoraStackController.h"
#include "assets/ModelThumbnailCache.h"
#include "assets/CatalogPickerDialog.h"
#include "assets/AssetCatalogScanner.h"
#include "widgets/DropTargetFrame.h"
#include "widgets/ElidingLabel.h"
#include "widgets/ClickOnlyComboBox.h"
#include "widgets/SectionCardWidgets.h"
#include "style/SvKit.h"


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
#include <QDragEnterEvent>
#include <QDropEvent>
#include <QMimeData>
#include <QUrl>
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
using spellvision::kit::setRole;
using spellvision::kit::setSurface;
namespace svstyle = spellvision::style;
namespace kit = spellvision::kit;

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
    // After buildUi, before anything writes into the controls: every write from here on is either
    // the app's (wrapped in ProgrammaticWrite) or the user's, and this is what tells them apart.
    watchForUserEdits();
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

    // Embeddings: Comfy CLIPTextEncode loads TI as embedding:<basename>, not a bare word.
    draft.positiveEmbeddings = positiveEmbeddings_;
    draft.negativeEmbeddings = negativeEmbeddings_;
    if (!positiveEmbeddings_.isEmpty() && promptEdit_) {
        QString p = draft.prompt;
        for (const QString &token : positiveEmbeddings_) {
            const QString bare = QFileInfo(token).completeBaseName();
            if (bare.isEmpty())
                continue;
            const QString marker = QStringLiteral("embedding:") + bare;
            if (p.contains(marker, Qt::CaseInsensitive) || p.contains(bare, Qt::CaseInsensitive))
                continue;
            p = p.isEmpty() ? marker : (p + QStringLiteral(", ") + marker);
        }
        draft.prompt = p;
    }
    if (!negativeEmbeddings_.isEmpty()) {
        QString n = draft.negativePrompt;
        for (const QString &token : negativeEmbeddings_) {
            const QString bare = QFileInfo(token).completeBaseName();
            if (bare.isEmpty())
                continue;
            const QString marker = QStringLiteral("embedding:") + bare;
            if (n.contains(marker, Qt::CaseInsensitive) || n.contains(bare, Qt::CaseInsensitive))
                continue;
            n = n.isEmpty() ? marker : (n + QStringLiteral(", ") + marker);
        }
        draft.negativePrompt = n;
    }

    draft.upscaleEnabled = upscale_ && upscale_->enabled();
    draft.upscaleMethod = upscale_ ? upscale_->method() : QStringLiteral("none");
    if (!draft.upscaleEnabled)
        draft.upscaleMethod = QStringLiteral("none");
    draft.upscaleScale = upscale_ ? upscale_->scale() : 1.0;
    draft.upscaleModel = upscale_ ? upscale_->model() : QString();

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

    draft.batchCount = (advanced_ && batchSpin_) ? batchSpin_->value() : 1;
    draft.outputPrefix = outputPrefixEdit_ ? outputPrefixEdit_->text().trimmed() : QString();
    draft.outputFolder = outputFolderLabel_ ? outputFolderLabel_->text() : QString();
    draft.modelsRoot = modelsRootDir_;
    for (const QString &raw : spellvision::shell::extraModelsRootsFromSettings())
    {
        const QString resolved = spellvision::shell::resolveModelsLibraryRoot(raw);
        const QString root = resolved.isEmpty() ? raw.trimmed() : resolved;
        if (!root.isEmpty() && !draft.extraModelsRoots.contains(root))
            draft.extraModelsRoots.append(root);
    }

    draft.isImageInputMode = isImageInputMode();
    const QString inputPath = inputImageEdit_ ? inputImageEdit_->text().trimmed() : QString();
    if (draft.isImageInputMode || !inputPath.isEmpty())
    {
        draft.inputImage = inputPath;
        draft.denoiseStrength = denoiseSpin_ ? denoiseSpin_->value() : 0.45;
        if (!inputPath.isEmpty())
            draft.isImageInputMode = true;
    }

    QJsonObject payload = GenerationRequestBuilder::build(draft);
    // Phase 3b: send the chosen operating point so the worker resolves the SAME bundle the UI shows.
    // Only when the selector is actually offered (>1 point, visible) and a point is picked.
    if (isVideoMode() && operatingPointCard_ && operatingPointCard_->isVisible() && !currentOperatingPoint_.isEmpty())
        payload.insert(QStringLiteral("operating_point"), currentOperatingPoint_);
    return payload;
}

// Instrument and Workspaces are the arrangement above; Canvas folds the prompt to a line and
// collapses the inspector to a strip of glyphs. The action row needs no move: it is ALREADY the
// canvas card's footer (canvasLayout->addWidget(actionRow_, 0) above, and it was the last item of
// that same layout before task 6 made it a widget), so every layout keeps it there and the C++ test
// asserts the seat in all three rather than a move asserting itself.
void ImageGenerationPage::applyShellLayout(spellvision::shell::ShellLayout::Layout layout)
{
    if (cockpitLayout_)
        cockpitLayout_->applyShellLayout(layout);
}

void ImageGenerationPage::reflowForCurrentGeometry()
{
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

        readinessHintLabel_->setHint(trimmed);
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
        "color:%1; font-size:11px; font-weight:600; background:%2; "
        "border:1px solid %3; border-radius:%4; padding:6px 10px; min-height:26px;")
        .arg(tm.css(ThemeManager::Color::Error),
             rgbaToken(ThemeManager::Color::Error, 0.14),
             tm.css(ThemeManager::Color::Error),
             QString::number(tm.radiusCard()) + QStringLiteral("px")));
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

    if (!isVideoMode() || isImageInputMode())
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

void ImageGenerationPage::acceptDroppedLocalFile(const QString &path)
{
    if (path.endsWith(QStringLiteral(".json"), Qt::CaseInsensitive))
    {
        acceptDroppedWorkflow(path);
        return;
    }
    if (isVideoMode() && !isImageInputMode())
        return;
    setInputImagePath(path);
}

void ImageGenerationPage::dragEnterEvent(QDragEnterEvent *event)
{
    if (!event)
        return;
    const QMimeData *mimeData = event->mimeData();
    if (!mimeData || !mimeData->hasUrls())
    {
        event->ignore();
        return;
    }
    const QList<QUrl> urls = mimeData->urls();
    if (urls.isEmpty() || !urls.first().isLocalFile())
    {
        event->ignore();
        return;
    }
    event->acceptProposedAction();
}

void ImageGenerationPage::dropEvent(QDropEvent *event)
{
    if (!event)
        return;
    const QMimeData *mimeData = event->mimeData();
    if (!mimeData || !mimeData->hasUrls())
    {
        event->ignore();
        return;
    }
    const QList<QUrl> urls = mimeData->urls();
    if (urls.isEmpty() || !urls.first().isLocalFile())
    {
        event->ignore();
        return;
    }
    acceptDroppedLocalFile(urls.first().toLocalFile());
    event->acceptProposedAction();
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

