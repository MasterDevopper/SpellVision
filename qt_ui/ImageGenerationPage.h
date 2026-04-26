#pragma once

#include <QJsonObject>
#include <QMap>
#include <QVector>
#include <QPixmap>
#include <QSize>
#include <QStringList>
#include <QWidget>
#include <QtGlobal>
#include <QMediaPlayer> // 🔥 REQUIRED

class QAudioOutput;
class QBoxLayout;
class QCheckBox;
class QComboBox;
class QDoubleSpinBox;
class QLabel;
class QLineEdit;
class QMediaPlayer;
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
class QVideoWidget;

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

    struct LoraStackEntry
    {
        QString display;
        QString value;
        double weight = 1.0;
        bool enabled = true;
    };

    explicit ImageGenerationPage(Mode mode, QWidget *parent = nullptr);

    QJsonObject buildRequestPayload() const;
    void setPreviewImage(const QString &imagePath, const QString &caption = QString());
    void setBusy(bool busy, const QString &message = QString());
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
    void useImageAsInput(const QString &path);
    QString selectedModelValue() const;
    QString selectedLoraValue() const;
    bool workflowDraftCanSubmit() const;

protected:
    void resizeEvent(QResizeEvent *event) override;

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
    void buildUi();
    void reloadCatalogs();
    void applyPreset(const QString &presetName);
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
    void applyAdaptiveSplitterSizes(AdaptiveLayoutMode mode);
    void applyRightPanelReflow(AdaptiveLayoutMode mode);
    void setRightControlsVisible(bool visible);
    AdaptiveLayoutMode currentAdaptiveLayoutMode() const;
    int measuredContentWidth() const;
    int measuredRightRailWidth() const;
    bool isCompactLayout() const;
    bool isMediumLayout() const;
    void setInputImagePath(const QString &path);
    void clearForm();
    void saveSnapshot();
    void restoreSnapshot();

    void persistLatestGeneratedOutput(const QString &path);
    QString latestGeneratedImagePath() const;
    QString latestGeneratedVideoPath() const;
    QString latestGeneratedOutputPath() const;
    void prepLatestForI2I();
    void useLatestForI2I();

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
    void updateVideoStackModeUi();
    void updateDraftCompatibilityUi();
    void updateAssetIntelligenceUi();
    void updatePrimaryActionAvailability();
    void updatePreviewEmptyStateSizing();
    bool hasReadyModelSelection() const;
    bool hasRequiredGenerationInput() const;
    bool hasVideoWorkflowBinding() const;
    QString readinessBlockReason() const;
    void applyActionReadinessStyle(QPushButton *button, bool enabled, const QString &tooltip);
    QString generationPayloadFingerprint(const QJsonObject &payload) const;
    bool shouldBlockDuplicateGenerate(const QJsonObject &payload);
    void lockGenerateSubmissionBriefly(const QString &message = QString());

    bool loadPreviewPixmapIfNeeded(const QString &path, bool forceReload = false);
    QString buildRenderedPreviewFingerprint(const QString &sourcePath, const QString &summaryText, const QSize &targetSize) const;

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
    QString selectedModelPath_;
    QString selectedModelDisplay_;
    QVector<LoraStackEntry> loraStack_;
    QSize lastPreviewTargetSize_{};
    QTimer *uiRefreshTimer_ = nullptr;
    QTimer *previewResizeTimer_ = nullptr;
    QString cachedPreviewSourcePath_;
    QPixmap cachedPreviewPixmap_;
    qint64 cachedPreviewLastModifiedMs_ = -1;
    qint64 cachedPreviewFileSize_ = -1;
    QString lastRenderedPreviewFingerprint_;
    QStackedWidget *previewStack_ = nullptr;
    QWidget *previewImagePage_ = nullptr;
    QWidget *previewVideoPage_ = nullptr;
    QMediaPlayer *previewVideoPlayer_ = nullptr;
    QAudioOutput *previewAudioOutput_ = nullptr;
    QVideoWidget *previewVideoWidget_ = nullptr;
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
    QString currentPreviewVideoPath_;
    QString currentPreviewVideoCaption_;
    qint64 currentPreviewVideoFileSize_ = -1;
    qint64 currentPreviewVideoModifiedMs_ = -1;
    bool previewSeekInternalUpdate_ = false;
    bool previewSeekDragging_ = false;
    bool previewUserPaused_ = false;
    bool previewUserStopped_ = false;
    qint64 previewLastKnownDurationMs_ = 0;

    QComboBox *presetCombo_ = nullptr;
    QTextEdit *promptEdit_ = nullptr;
    QTextEdit *negativePromptEdit_ = nullptr;
    QWidget *inputCard_ = nullptr;
    QLabel *inputDropLabel_ = nullptr;
    QLineEdit *inputImageEdit_ = nullptr;
    QLabel *selectedModelLabel_ = nullptr;
    QPushButton *browseModelButton_ = nullptr;
    QPushButton *clearModelButton_ = nullptr;
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
    QWidget *denoiseRow_ = nullptr;
    QWidget *wanSplitRow_ = nullptr;
    QWidget *highNoiseStepsRow_ = nullptr;
    QWidget *lowNoiseStepsRow_ = nullptr;
    QWidget *splitStepRow_ = nullptr;
    QWidget *highNoiseShiftRow_ = nullptr;
    QWidget *lowNoiseShiftRow_ = nullptr;
    QWidget *enableVaeTilingRow_ = nullptr;
    QToolButton *outputQueueToggleButton_ = nullptr;
    QToolButton *advancedToggleButton_ = nullptr;
    QDoubleSpinBox *denoiseSpin_ = nullptr;
    QLineEdit *outputPrefixEdit_ = nullptr;
    QLabel *outputFolderLabel_ = nullptr;
    QLabel *previewLabel_ = nullptr;
    QLabel *readinessHintLabel_ = nullptr;
    QLabel *modelsRootLabel_ = nullptr;

    QPushButton *generateButton_ = nullptr;
    QPushButton *queueButton_ = nullptr;
    QPushButton *savePresetButton_ = nullptr;
    QPushButton *clearButton_ = nullptr;
    QPushButton *prepLatestForI2IButton_ = nullptr;
    QPushButton *useLatestT2IButton_ = nullptr;

    QSplitter *contentSplitter_ = nullptr;
    QScrollArea *leftScrollArea_ = nullptr;
    QScrollArea *rightScrollArea_ = nullptr;
    QWidget *centerContainer_ = nullptr;
    QWidget *stackCard_ = nullptr;
    QWidget *settingsCard_ = nullptr;
    QPushButton *toggleControlsButton_ = nullptr;
    QPushButton *openModelsButton_ = nullptr;
    QPushButton *openWorkflowsButton_ = nullptr;
    QBoxLayout *stackToolsLayout_ = nullptr;
    QBoxLayout *samplerSchedulerLayout_ = nullptr;
    QBoxLayout *stepsCfgLayout_ = nullptr;
    QBoxLayout *seedBatchLayout_ = nullptr;
    QBoxLayout *sizeLayout_ = nullptr;
    bool rightControlsVisible_ = true;
    bool outputQueueForceOpen_ = false;
    bool advancedForceOpen_ = false;
    bool adaptiveCompact_ = false;
    AdaptiveLayoutMode lastAdaptiveLayoutMode_ = AdaptiveLayoutMode::Wide;

    QString generatedPreviewPath_;
    QString generatedPreviewCaption_;
    bool busy_ = false;
    QString busyMessage_;

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
