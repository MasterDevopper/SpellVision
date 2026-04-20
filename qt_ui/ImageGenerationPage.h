#pragma once

#include <QJsonObject>
#include <QMap>
#include <QVector>
#include <QPixmap>
#include <QSize>
#include <QStringList>
#include <QWidget>
#include <QtGlobal>

class QBoxLayout;
class QComboBox;
class QDoubleSpinBox;
class QLabel;
class QLineEdit;
class QPushButton;
class QSpinBox;
class QTextEdit;
class QResizeEvent;
class QScrollArea;
class QSplitter;
class QTimer;
class QToolButton;

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
    void saveSnapshot() const;
    void restoreSnapshot();

    void persistLatestGeneratedOutput(const QString &path);
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
    void updateDraftCompatibilityUi();
    void updateAssetIntelligenceUi();
    void updatePrimaryActionAvailability();
    void updatePreviewEmptyStateSizing();
    bool hasReadyModelSelection() const;
    bool hasRequiredGenerationInput() const;
    QString readinessBlockReason() const;
    void applyActionReadinessStyle(QPushButton *button, bool enabled, const QString &tooltip);

    bool loadPreviewPixmapIfNeeded(const QString &path, bool forceReload = false);
    QString buildRenderedPreviewFingerprint(const QString &sourcePath, const QString &summaryText, const QSize &targetSize) const;

    Mode mode_;

    QString modelsRootDir_;
    QMap<QString, QString> modelDisplayByValue_;
    QMap<QString, QString> loraDisplayByValue_;
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

    QComboBox *presetCombo_ = nullptr;
    QTextEdit *promptEdit_ = nullptr;
    QTextEdit *negativePromptEdit_ = nullptr;
    QWidget *inputCard_ = nullptr;
    QLabel *inputDropLabel_ = nullptr;
    QLineEdit *inputImageEdit_ = nullptr;
    QLabel *selectedModelLabel_ = nullptr;
    QPushButton *browseModelButton_ = nullptr;
    QPushButton *clearModelButton_ = nullptr;
    QComboBox *workflowCombo_ = nullptr;
    QWidget *loraStackContainer_ = nullptr;
    QBoxLayout *loraStackLayout_ = nullptr;
    QLabel *loraStackSummaryLabel_ = nullptr;
    QPushButton *addLoraButton_ = nullptr;
    QPushButton *clearLorasButton_ = nullptr;
    QComboBox *samplerCombo_ = nullptr;
    QComboBox *schedulerCombo_ = nullptr;
    QSpinBox *stepsSpin_ = nullptr;
    QDoubleSpinBox *cfgSpin_ = nullptr;
    QSpinBox *seedSpin_ = nullptr;
    QSpinBox *widthSpin_ = nullptr;
    QSpinBox *heightSpin_ = nullptr;
    QSpinBox *batchSpin_ = nullptr;
    QWidget *denoiseRow_ = nullptr;
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

    QString workflowDraftSource_;
    QStringList workflowDraftWarnings_;
    bool workflowDraftBlocking_ = false;
};
