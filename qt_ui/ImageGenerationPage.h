#pragma once

#include "assets/ModelStackState.h"

#include <QJsonObject>
#include <QMap>
#include <QVector>
#include <QPixmap>
#include <QSize>
#include <QStringList>
#include <QJsonArray>
#include <QWidget>
#include <QtGlobal>

#include <functional>

class QBoxLayout;
class QHBoxLayout;
class QFrame;
class QCheckBox;
class QComboBox;
class QDoubleSpinBox;
class QLabel;
class QLineEdit;
class QPushButton;
class QSpinBox;
class QTextEdit;
class QResizeEvent;
class QScrollArea;
class QSlider;
class QSplitter;
class QStackedWidget;
class QTimer;
class QToolButton;
class CockpitInspector;

namespace spellvision::preview
{
class MediaPreviewController;
class ImagePreviewController;
}

namespace spellvision::assets
{
class LoraStackController;
class ModelThumbnailCache;
}

namespace spellvision::widgets
{
class DropTargetFrame;
}

class ImageGenerationPage : public QWidget
{
    Q_OBJECT

public:
    enum class Mode
    {
        TextToImage,
        ImageToImage,
        TextToVideo,
        ImageToVideo
    };

    using LoraStackEntry = spellvision::assets::LoraStackEntry;

    explicit ImageGenerationPage(Mode mode, QWidget *parent = nullptr);

    QJsonObject buildRequestPayload() const;
    // Public re-scan hook (worker-ready recovery): the constructor's catalog scan
    // can land before the worker binds :8765, leaving fallback families; MainWindow
    // calls this on the worker down->up edge to repopulate from the classifier.
    // Idempotent (delegates to reloadCatalogs), preserves the selected model.
    void rescanModelCatalog();
    // Runtime model pickup (refresh-on-demand): guarded, busy-stated manual refresh
    // (the "Refresh models" button + the on-navigate dirty-check both route here).
    void refreshModelCatalog();
    // Cheap change-probe of the model tree ((path,size,mtime) hash, no worker call)
    // so the on-navigate dirty-check runs the expensive rescan only on real change.
    // Static + pure (root in, hash out) -> also the headless --catalog-refresh-selftest hook.
    static QString catalogSignature(const QString &root);
    void setPreviewImage(const QString &imagePath, const QString &caption = QString());
    void setBusy(bool busy, const QString &message = QString());
    void applyWorkerMessage(const QJsonObject &payload);
    // Surface a worker/job error inline on the generation page (the action-row banner),
    // so failures + worker-down are visible, not log-pane-only. clearGenerationError()
    // dismisses it and restores the normal readiness hint.
    void showGenerationError(const QString &message);
    void clearGenerationError();
    void setWorkspaceTelemetry(const QString &runtime,
                               const QString &queue,
                               const QString &model,
                               const QString &lora,
                               int progressPercent,
                               const QString &progressText);

    void applyHomeStarter(const QString &title,
                          const QString &subtitle,
                          const QString &sourceLabel);

    void applyWorkflowDraft(const QJsonObject &draft);
    // Component Auto-Population (Doc 19 §6 A2): MainWindow wires this to the worker round-trip
    // (resolve_component_stack -> the A1 engine). Called on model-select to auto-fill + constrain
    // the video stack component combos. Empty return -> combos stay on Auto (worker backstop).
    void setComponentStackResolver(
        std::function<QJsonArray(const QString &primary, const QString &family,
                                 const QString &task, const QJsonObject &choices)> resolver);
    void useImageAsInput(const QString &path);
    // Send-to-generation handoff (doc 22 §3): resolve `value` against this page's catalog and set the
    // checkpoint slot, or add to the LoRA stack. Returns whether a catalog match was found. Unlike
    // applyWorkflowDraft, these have NO side effects on the prompt / sampler / steps / etc.
    bool applyModelHandoff(const QString &value, const QString &display = QString());
    bool applyLoraHandoff(const QString &value, const QString &display = QString(), double weight = 1.0);
    // Append a model/LoRA's trigger words to the prompt (deduped), for send-to-generation.
    void appendTriggerWords(const QStringList &words);
    // Pin the video family bar (Wan/LTX) to match a video handoff so the bar reflects reality
    // immediately instead of Auto-resolving from a not-yet-selected primary. No-op off a video page.
    void pinVideoFamily(const QString &family);
    QString selectedModelValue() const;
    QString selectedLoraValue() const;
    bool workflowDraftCanSubmit() const;
    // Phase 7: app-global Simple/Advanced disclosure mode. Step 1 is plumbing only -- this records
    // the mode (advanced_); later steps gate per-tab controls off it.
    void updateDisclosure(bool advanced);

    // Latest-output access + I2I handoff (also used by the command palette's Output / "Use last output"
    // commands, so these are public rather than page-internal).
    QString latestGeneratedOutputPath() const;
    void useLatestForI2I();

    // Command-palette entry points. Thin wrappers around behavior that already existed on the page but
    // was only reachable from a button / clearForm(). No new semantics -- they surface the existing
    // action so the palette can invoke it on the active cockpit.
    void triggerGenerate();        // same submission path as the Generate button (respects readiness)
    void randomizeSeed();          // seed spin -> 0 == "Random" (its special value)
    void copyPromptToClipboard();  // prompt text -> clipboard
    void clearPromptText();        // clear only the prompt field
    void clearLoraStack();         // mirrors the "Clear LoRAs" button

protected:
    void resizeEvent(QResizeEvent *event) override;
    void showEvent(QShowEvent *event) override;

signals:
    void generateRequested(const QJsonObject &payload);
    void queueRequested(const QJsonObject &payload);
    void openModelsRequested();
    void openWorkflowsRequested();
    void prepForI2IRequested(const QString &imagePath);

private:
    enum class AdaptiveLayoutMode
    {
        Wide,
        Medium,
        Compact
    };

    void applyTheme();
    void applyThemeStyling();
    void buildUi();
    void reloadCatalogs();
    void applyPreset(const QString &presetName);
    void setNegativePromptVisible(bool open);
    void openInputImageBrowse();
    void scheduleUiRefresh(int delayMs = 90);
    void schedulePreviewRefresh(int delayMs = 90);
    void refreshPreview();
    void showImagePreviewSurface();
    void showVideoPreviewSurface(const QString &videoPath, const QString &caption = QString());
    void stopVideoPreview();
    void updateVideoTransportUi();
    void updateVideoCaption(const QString &videoPath, const QString &caption = QString());
    void playPreviewVideo();
    void pausePreviewVideo();
    void stopPreviewVideoPlayback();
    void restartPreviewVideo();
    void stepPreviewVideoFrames(int frameDelta);
    void seekPreviewVideo(qint64 positionMs, bool preservePlaybackState);
    void setPreviewPlaybackRate(double rate);
    void handlePreviewMediaStatus(int status);
    QString formatDurationLabel(qint64 milliseconds) const;
    QString formatFileSizeLabel(qint64 bytes) const;
    void updateAdaptiveLayout();
    AdaptiveLayoutMode currentAdaptiveLayoutMode() const;
    int measuredContentWidth() const;
    bool isCompactLayout() const;
    bool isMediumLayout() const;
    void setInputImagePath(const QString &path);
    void clearForm();
    void saveSnapshot();
    void restoreSnapshot();

    void persistLatestGeneratedOutput(const QString &path);
    QString latestGeneratedImagePath() const;
    QString latestGeneratedVideoPath() const;
    void prepLatestForI2I();

    QString modeKey() const;
    QString modeTitle() const;
    bool isImageInputMode() const;
    bool isVideoMode() const;
    bool usesStrengthControl() const;
    QString currentComboValue(const QComboBox *combo) const;
    bool selectComboValue(QComboBox *combo, const QString &value);
    void showCheckpointPicker();
    void showLoraPicker();
    void setSelectedModel(const QString &value, const QString &display = QString());
    void refreshSelectedModelUi();
    QString resolveSelectedModelDisplay(const QString &value) const;
    QString resolveLoraDisplay(const QString &value) const;
    bool trySetSelectedModelByCandidate(const QStringList &candidates);
    bool tryAddLoraByCandidate(const QStringList &candidates, double weight = 1.0, bool enabled = true);
    void addLoraToStack(const QString &value, const QString &display, double weight = 1.0, bool enabled = true);
    void replaceLoraStackEntry(int index);
    void rebuildLoraStackUi();
    QString resolveLoraValue() const;
    QString videoComponentValue(const QComboBox *combo) const;
    QString videoStackModeSelection() const;
    QString suggestedVideoStackMode() const;
    QString effectiveVideoStackMode() const;
    bool usesWanDualNoiseMode() const;
    void setVideoComponentComboValue(QComboBox *combo, const QString &value);
    void populateVideoComponentControls();
    QJsonObject selectedVideoStackForPayload() const;
    void syncVideoComponentControlsFromSelectedStack();
    void applyVideoComponentOverridesToSelectedStack();
    // A2 auto-populate: resolve on model-change, apply to combos, constrain to valid options.
    void resolveAndApplyVideoComponents();
    void maybeAutoPopulateVideoComponents();
    QJsonObject buildVideoComponentChoicesForResolver() const;
    void applyVideoAutoPopulateToCombos();
    void setVideoComboToBasename(QComboBox *combo, const QString &value);
    void constrainVideoComboToValid(QComboBox *combo, const QStringList &validBasenames, const QString &keepValue);
    void updateVideoStackModeUi();

    void updateDraftCompatibilityUi();
    void updateAssetIntelligenceUi();
    void updatePrimaryActionAvailability();
    void updatePreviewEmptyStateSizing();
    void updateCanvasEmptyState(const QString &message);
    bool hasReadyModelSelection() const;
    bool hasRequiredGenerationInput() const;
    bool hasVideoWorkflowBinding() const;
    QString readinessBlockReason() const;
    void applyActionReadinessStyle(QPushButton *button, bool enabled, const QString &tooltip);
    QString generationPayloadFingerprint(const QJsonObject &payload) const;
    bool shouldBlockDuplicateGenerate(const QJsonObject &payload);
    void lockGenerateSubmissionBriefly(const QString &message = QString());

    Mode mode_;

    QString modelsRootDir_;
    QMap<QString, QString> modelDisplayByValue_;
    QMap<QString, QString> modelFamilyByValue_;
    QMap<QString, QString> modelModalityByValue_;
    QMap<QString, QString> modelRoleByValue_;
    QMap<QString, QString> modelNoteByValue_;
    QMap<QString, QJsonObject> modelStackByValue_;
    QMap<QString, QString> loraDisplayByValue_;
    bool syncingVideoComponentControls_ = false;
    std::function<QJsonArray(const QString &, const QString &, const QString &, const QJsonObject &)> componentStackResolver_;
    QString lastAutoPopulatedModel_;                       // engine runs once per model-change
    QMap<QString, QStringList> videoComponentValidOptions_; // component -> valid basenames (constrains the menu)
    QMap<QString, QString> videoAutoFilledValues_;          // component -> resolved basename (survives re-sync)
    QStringList videoMissingRequiredComponents_;            // T3 required-missing -> readiness panel
    QString selectedModelPath_;
    QString selectedModelDisplay_;
    QVector<LoraStackEntry> loraStack_;
    spellvision::assets::LoraStackController *loraStackController_ = nullptr;
    QTimer *uiRefreshTimer_ = nullptr;
    QTimer *previewResizeTimer_ = nullptr;
    QStackedWidget *previewStack_ = nullptr;
    QWidget *previewImagePage_ = nullptr;
    QWidget *previewVideoPage_ = nullptr;
    spellvision::preview::MediaPreviewController *mediaPreviewController_ = nullptr;
    spellvision::preview::ImagePreviewController *imagePreviewController_ = nullptr;
    QLabel *previewVideoSurface_ = nullptr;
    QLabel *previewVideoCaptionLabel_ = nullptr;
    QWidget *previewVideoTransportBar_ = nullptr;
    QPushButton *previewPlayPauseButton_ = nullptr;
    QPushButton *previewStopButton_ = nullptr;
    QPushButton *previewStepBackButton_ = nullptr;
    QPushButton *previewStepForwardButton_ = nullptr;
    QPushButton *previewRestartButton_ = nullptr;
    QSlider *previewSeekSlider_ = nullptr;
    QLabel *previewTimeLabel_ = nullptr;
    QComboBox *previewSpeedCombo_ = nullptr;
    QCheckBox *previewLoopCheck_ = nullptr;

    QComboBox *presetCombo_ = nullptr;
    bool advanced_ = false; // Phase 7 disclosure mode (step 1: recorded only, gates nothing yet)
    QTextEdit *promptEdit_ = nullptr;
    QTextEdit *negativePromptEdit_ = nullptr;
    QWidget *negativeRow_ = nullptr;
    QPushButton *negativeToggleButton_ = nullptr;
    QWidget *inputCard_ = nullptr; // retained hidden in i2i/i2v as the inputImageEdit_ backing model
    QLabel *inputDropLabel_ = nullptr;
    QLineEdit *inputImageEdit_ = nullptr;
    // Prompt-row input chip-dropzone (i2i/i2v only) -- a view over inputImageEdit_/setInputImagePath.
    spellvision::widgets::DropTargetFrame *inputChipDropzone_ = nullptr;
    QLabel *inputChipThumb_ = nullptr;
    QLabel *inputChipHint_ = nullptr;
    QPushButton *inputChipClear_ = nullptr;
    QPushButton *inputChipClickCatcher_ = nullptr;
    QLabel *selectedModelLabel_ = nullptr;
    QPushButton *browseModelButton_ = nullptr;
    QPushButton *clearModelButton_ = nullptr;
    QPushButton *refreshModelsButton_ = nullptr;
    // Sprint V Pass 1: VideoFamily separates LTX vs WAN as a first-class
    // user choice. Auto resolves from the currently selected checkpoint via
    // resolvedVideoFamily(); the existing suggestedVideoStackMode() helper
    // already knows how to inspect modelFamilyByValue_ + path hints.
    enum class VideoFamily
    {
        Auto,
        Ltx,
        Wan,
    };

    QWidget *videoFamilyCard_ = nullptr;
    QComboBox *videoFamilyCombo_ = nullptr; // hidden backing state-model; segmented bar is the view
    QPushButton *videoFamilyAutoButton_ = nullptr;
    QPushButton *videoFamilyWanButton_ = nullptr;
    QPushButton *videoFamilyLtxButton_ = nullptr;
    QLabel *videoFamilyResolvesLabel_ = nullptr;

    // Sprint V Pass 1-FIX: family resolution + UI sync helpers.
    // Declared here (after the VideoFamily enum) so the type is in scope.
    VideoFamily videoFamilySelection() const;
    VideoFamily resolvedVideoFamily() const;
    QString resolvedVideoFamilyToken() const;
    void updateVideoFamilyUi();

    QWidget *videoComponentPanel_ = nullptr;
    QWidget *videoStackModeRow_ = nullptr;
    QWidget *videoHighNoiseRow_ = nullptr;
    QWidget *videoLowNoiseRow_ = nullptr;
    QComboBox *videoStackModeCombo_ = nullptr;
    QComboBox *videoPrimaryModelCombo_ = nullptr;
    QComboBox *videoHighNoiseModelCombo_ = nullptr;
    QComboBox *videoLowNoiseModelCombo_ = nullptr;
    QComboBox *videoTextEncoderCombo_ = nullptr;
    QComboBox *videoVaeCombo_ = nullptr;
    QComboBox *videoClipVisionCombo_ = nullptr;
    QComboBox *workflowCombo_ = nullptr;
    QWidget *ltxLaunchOptionsPanel_ = nullptr;
    QLineEdit *ltxPromptApiExportPathEdit_ = nullptr;
    QLineEdit *ltxPrimaryModelNameEdit_ = nullptr;
    QLineEdit *ltxTextEncoderNameEdit_ = nullptr;
    QLineEdit *ltxTextProjectionNameEdit_ = nullptr;
    QLineEdit *ltxAudioVaeNameEdit_ = nullptr;
    QLineEdit *ltxVideoVaeNameEdit_ = nullptr;
    QLineEdit *ltxVisionEncoderNameEdit_ = nullptr;
    QLineEdit *ltxOutputVariantEdit_ = nullptr;
    QLabel *ltxPromptApiHintLabel_ = nullptr;
    QPushButton *ltxBrowsePromptApiButton_ = nullptr;
    QPushButton *ltxUseDefaultPromptApiButton_ = nullptr;
    QPushButton *ltxApplySafeDefaultsButton_ = nullptr;
    QWidget *loraStackContainer_ = nullptr;
    QBoxLayout *loraStackLayout_ = nullptr;
    QLabel *loraStackSummaryLabel_ = nullptr;
    QPushButton *addLoraButton_ = nullptr;
    QPushButton *clearLorasButton_ = nullptr;
    QComboBox *samplerCombo_ = nullptr;
    QComboBox *schedulerCombo_ = nullptr;
    QComboBox *videoSamplerCombo_ = nullptr;
    QComboBox *videoSchedulerCombo_ = nullptr;
    QSpinBox *stepsSpin_ = nullptr;
    QDoubleSpinBox *cfgSpin_ = nullptr;
    QSpinBox *seedSpin_ = nullptr;
    QSpinBox *widthSpin_ = nullptr;
    QSpinBox *heightSpin_ = nullptr;
    QSpinBox *frameCountSpin_ = nullptr;
    QSpinBox *fpsSpin_ = nullptr;
    QSpinBox *batchSpin_ = nullptr;
    QComboBox *wanSplitCombo_ = nullptr;
    QSpinBox *highNoiseStepsSpin_ = nullptr;
    QSpinBox *lowNoiseStepsSpin_ = nullptr;
    QSpinBox *splitStepSpin_ = nullptr;
    QDoubleSpinBox *highNoiseShiftSpin_ = nullptr;
    QDoubleSpinBox *lowNoiseShiftSpin_ = nullptr;
    QCheckBox *enableVaeTilingCheck_ = nullptr;
    // Phase 7 Output-tab rows, gated Advanced-only by updateDisclosure (Preset/Quality stays Simple).
    QWidget *widthRow_ = nullptr;
    QWidget *heightRow_ = nullptr;
    QWidget *batchRow_ = nullptr;
    QWidget *prefixRow_ = nullptr;
    // Phase 7 Sampling-tab rows gated Advanced-only (Aspect + Frames/FPS stay Simple). The video
    // sampler/scheduler also carry an isVideoMode() guard the disclosure gate AND-composes with.
    QWidget *samplerRow_ = nullptr;
    QWidget *schedulerRow_ = nullptr;
    QWidget *videoSamplerRow_ = nullptr;
    QWidget *videoSchedulerRow_ = nullptr;
    QWidget *stepsRow_ = nullptr;
    QWidget *cfgRow_ = nullptr;
    QWidget *seedRow_ = nullptr;
    // Phase 7 Model-tab grid rows gated Advanced-only -- captured inline labels so both grid cells
    // (label + field) hide together and the QGridLayout row collapses (Workflow=D2; Components=video).
    QLabel *workflowRowLabel_ = nullptr;
    QLabel *componentsRowLabel_ = nullptr;
    QWidget *denoiseRow_ = nullptr;
    QWidget *wanSplitRow_ = nullptr;
    QWidget *highNoiseStepsRow_ = nullptr;
    QWidget *lowNoiseStepsRow_ = nullptr;
    QWidget *splitStepRow_ = nullptr;
    QWidget *highNoiseShiftRow_ = nullptr;
    QWidget *lowNoiseShiftRow_ = nullptr;
    QWidget *enableVaeTilingRow_ = nullptr;
    QDoubleSpinBox *denoiseSpin_ = nullptr;
    QLineEdit *outputPrefixEdit_ = nullptr;
    QLabel *outputFolderLabel_ = nullptr;
    QLabel *previewLabel_ = nullptr;
    QStackedWidget *previewImageInnerStack_ = nullptr;
    QWidget *canvasEmptyState_ = nullptr;
    QLabel *canvasEmptyTitle_ = nullptr;
    QLabel *canvasEmptySub_ = nullptr;
    QLabel *canvasEmptyChipDim_ = nullptr;
    QLabel *canvasEmptyChipSteps_ = nullptr;
    QLabel *canvasEmptyChipCfg_ = nullptr;
    QLabel *canvasEmptyChipSeed_ = nullptr;
    QLabel *readinessHintLabel_ = nullptr;
    QLabel *modelsRootLabel_ = nullptr;

    // --- SPRINT MOCKUP PASS 1 ASSET INTELLIGENCE ---
    // Structured asset-intelligence surface that replaces the dense HTML
    // dump (modelsRootLabel_ is kept as the collapsed details body).
    QFrame *aiReadinessStrip_ = nullptr;
    QLabel *aiReadinessDot_ = nullptr;
    QLabel *aiReadinessText_ = nullptr;
    QLabel *aiReadinessSub_ = nullptr;
    QLabel *aiCompatWarningLabel_ = nullptr; // non-blocking LoRA/checkpoint architecture mismatch (item 2)
    QLabel *aiStackGroupLabel_ = nullptr;
    QWidget *aiStackChipsRow_ = nullptr;
    QBoxLayout *aiStackChipsLayout_ = nullptr;
    QWidget *aiComponentsGroupContainer_ = nullptr;
    QLabel *aiComponentsGroupLabel_ = nullptr;
    QWidget *aiComponentsChipsRow_ = nullptr;
    QBoxLayout *aiComponentsChipsLayout_ = nullptr;
    QFrame *aiTimingRow_ = nullptr;
    QLabel *aiTimingFramesValue_ = nullptr;
    QLabel *aiTimingFramesKey_ = nullptr;
    QLabel *aiTimingFpsValue_ = nullptr;
    QLabel *aiTimingFpsKey_ = nullptr;
    QLabel *aiTimingDurationValue_ = nullptr;
    QLabel *aiTimingDurationKey_ = nullptr;
    QToolButton *aiDetailsToggle_ = nullptr;
    bool aiDetailsExpanded_ = false;
    // --- END SPRINT MOCKUP PASS 1 ASSET INTELLIGENCE ---

    QPushButton *generateButton_ = nullptr;
    QPushButton *queueButton_ = nullptr;
    QPushButton *savePresetButton_ = nullptr;
    QPushButton *clearButton_ = nullptr;
    QPushButton *prepLatestForI2IButton_ = nullptr;
    QPushButton *useLatestT2IButton_ = nullptr;

    QSplitter *contentSplitter_ = nullptr;
    QScrollArea *leftScrollArea_ = nullptr;
    QScrollArea *rightScrollArea_ = nullptr;
    CockpitInspector *cockpitInspector_ = nullptr; // studio-layout right column (phase 2 scaffold)
    QWidget *centerContainer_ = nullptr;
    QWidget *stackCard_ = nullptr;
    QWidget *settingsCard_ = nullptr;
    QPushButton *openModelsButton_ = nullptr;
    QPushButton *openWorkflowsButton_ = nullptr;
    QBoxLayout *stackToolsLayout_ = nullptr;
    QBoxLayout *samplerSchedulerLayout_ = nullptr;
    QBoxLayout *stepsCfgLayout_ = nullptr;
    QBoxLayout *seedBatchLayout_ = nullptr;
    QBoxLayout *sizeLayout_ = nullptr;
    bool adaptiveCompact_ = false;
    AdaptiveLayoutMode lastAdaptiveLayoutMode_ = AdaptiveLayoutMode::Wide;

    QString generatedPreviewPath_;
    QString generatedPreviewCaption_;

    // --- Session outputs strip (in-memory, per-mode, since app launch). NOT the persistent History. ---
    struct SessionOutput
    {
        QString path;        // the output file (image or video)
        QString posterPath;  // thumbnail source: == path for images; an extracted still for video
        bool isVideo = false;
        QString caption;
        // Params captured at generation time, for the hover tooltip.
        QString model;
        int seed = 0;
        int steps = 0;
    };
    void recordSessionOutput(const QString &path, const QString &caption); // append a genuinely-new output
    void rebuildSessionStrip();                                            // repaint the strip from sessionOutputs_
    void selectSessionOutput(const QString &path);                        // click -> load into the preview
    void captureVideoPosterIfNeeded(const QString &videoPath);            // grab first frame -> poster still

    QWidget *sessionStrip_ = nullptr;        // whole strip container (hidden when empty)
    QHBoxLayout *sessionStripLayout_ = nullptr; // holds the thumbnail buttons (newest first)
    spellvision::assets::ModelThumbnailCache *sessionThumbs_ = nullptr;
    QVector<SessionOutput> sessionOutputs_;  // newest first
    QString selectedSessionPath_;            // currently shown in the preview
    bool suppressSessionRecord_ = false;     // true while a strip click re-shows (don't re-record/reorder)

    bool suppressStartupVideoPreviewRestore_ = false;
    bool busy_ = false;
    bool catalogRefreshInFlight_ = false; // churn guard: no stacked rescans on double-click / navigate-during-refresh
    QString lastCatalogSignature_;         // signature of the last full scan; drives the on-navigate dirty-check
    QString busyMessage_;

    // When true, an error is showing on readinessHintLabel_; updatePrimaryActionAvailability
    // must not overwrite the banner with the normal readiness hint until it's cleared.
    bool errorBannerActive_ = false;

    bool generateSubmitLocked_ = false;
    QString lastGenerateFingerprint_;
    qint64 lastGenerateSubmittedAtMs_ = 0;

    QString workflowDraftSource_;
    QString workflowDraftProfilePath_;
    QString workflowDraftWorkflowPath_;
    QString workflowDraftCompiledPromptPath_;
    QString workflowDraftBackend_;
    QString workflowDraftMediaType_;
    QStringList workflowDraftWarnings_;
    bool workflowDraftBlocking_ = false;
};
