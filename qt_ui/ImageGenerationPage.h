#pragma once

#include <QJsonObject>
#include <QMap>
#include <QPixmap>
#include <QSize>
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
    QString resolveLoraValue() const;

    bool loadPreviewPixmapIfNeeded(const QString &path, bool forceReload = false);
    QString buildRenderedPreviewFingerprint(const QString &sourcePath, const QString &summaryText, const QSize &targetSize) const;

    Mode mode_;

    QString modelsRootDir_;
    QMap<QString, QString> loraPathByDisplay_;
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
    QComboBox *modelCombo_ = nullptr;
    QComboBox *workflowCombo_ = nullptr;
    QComboBox *loraCombo_ = nullptr;
    QComboBox *samplerCombo_ = nullptr;
    QComboBox *schedulerCombo_ = nullptr;
    QSpinBox *stepsSpin_ = nullptr;
    QDoubleSpinBox *cfgSpin_ = nullptr;
    QDoubleSpinBox *loraWeightSpin_ = nullptr;
    QSpinBox *seedSpin_ = nullptr;
    QSpinBox *widthSpin_ = nullptr;
    QSpinBox *heightSpin_ = nullptr;
    QSpinBox *batchSpin_ = nullptr;
    QWidget *denoiseRow_ = nullptr;
    QDoubleSpinBox *denoiseSpin_ = nullptr;
    QLineEdit *outputPrefixEdit_ = nullptr;
    QLabel *outputFolderLabel_ = nullptr;
    QLabel *previewLabel_ = nullptr;
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
    bool adaptiveCompact_ = false;
    AdaptiveLayoutMode lastAdaptiveLayoutMode_ = AdaptiveLayoutMode::Wide;

    QString generatedPreviewPath_;
    QString generatedPreviewCaption_;
    bool busy_ = false;
    QString busyMessage_;
};
