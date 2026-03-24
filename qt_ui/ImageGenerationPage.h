#pragma once

#include <QJsonObject>
#include <QMap>
#include <QWidget>

class QComboBox;
class QCompleter;
class QDoubleSpinBox;
class QLabel;
class QLineEdit;
class QPushButton;
class QProgressBar;
class QSpinBox;
class QTextEdit;
class QWidget;
class QResizeEvent;

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

protected:
    void resizeEvent(QResizeEvent *event) override;

signals:
    void generateRequested(const QJsonObject &payload);
    void queueRequested(const QJsonObject &payload);
    void openModelsRequested();
    void openWorkflowsRequested();

private:
    void applyTheme();
    void buildUi();
    void reloadCatalogs();
    void applyPreset(const QString &presetName);
    void refreshPreview();
    void refreshStackSummary();
    void setInputImagePath(const QString &path);
    void clearForm();
    void saveSnapshot() const;
    void restoreSnapshot();
    QString modeKey() const;
    QString modeTitle() const;
    bool isImageInputMode() const;
    bool isVideoMode() const;
    bool usesStrengthControl() const;
    QString currentComboValue(const QComboBox *combo) const;
    bool selectComboValue(QComboBox *combo, const QString &value);
    QString resolveLoraValue() const;

    Mode mode_;

    QString modelsRootDir_;
    QMap<QString, QString> loraPathByDisplay_;

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
    QSpinBox *seedSpin_ = nullptr;
    QSpinBox *widthSpin_ = nullptr;
    QSpinBox *heightSpin_ = nullptr;
    QSpinBox *batchSpin_ = nullptr;
    QWidget *denoiseRow_ = nullptr;
    QDoubleSpinBox *denoiseSpin_ = nullptr;
    QLineEdit *outputPrefixEdit_ = nullptr;
    QLabel *outputFolderLabel_ = nullptr;
    QLabel *previewLabel_ = nullptr;
    QLabel *previewSummaryLabel_ = nullptr;
    QLabel *stackSummaryLabel_ = nullptr;
    QLabel *modelsRootLabel_ = nullptr;
    QLabel *headerRuntimeLabel_ = nullptr;
    QLabel *headerQueueLabel_ = nullptr;
    QLabel *headerModelLabel_ = nullptr;
    QLabel *headerLoraLabel_ = nullptr;
    QLabel *headerProgressTextLabel_ = nullptr;
    QProgressBar *headerProgressBar_ = nullptr;
    QString generatedPreviewPath_;
    QString generatedPreviewCaption_;
    bool busy_ = false;
    QString busyMessage_;
    QPushButton *generateButton_ = nullptr;
    QPushButton *queueButton_ = nullptr;
    QPushButton *savePresetButton_ = nullptr;
    QPushButton *clearButton_ = nullptr;
};
