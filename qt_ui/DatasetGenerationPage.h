#pragma once

#include <QJsonObject>
#include <QWidget>

class QCheckBox;
class QLabel;
class QLineEdit;
class QProgressBar;
class QPushButton;
class QSpinBox;
class QTextEdit;

// Dataset generator — expands a prompt list into many T2I queue jobs via worker
// command "generate_dataset" (see worker_service.QueueManager.enqueue_dataset).
// Optional model fields are merged from the live T2I cockpit when empty.
class DatasetGenerationPage : public QWidget
{
    Q_OBJECT

public:
    explicit DatasetGenerationPage(QWidget *parent = nullptr);

    void setProjectRoot(const QString &root);
    void setBusy(bool busy, const QString &message = QString());
    void applyQueueAck(const QJsonObject &ack);
    void updateDisclosure(bool advanced);

    // The canvas the T2I cockpit is currently set to. The shell pushes it in; the page only
    // displays and reports it. Simple mode hides the width/height spins, so without this the page
    // had no canvas to state and no way for a Simple user to state one -- Generate refused on a
    // form that offered no control to satisfy it. Pass 0/0 when the cockpit has no canvas either.
    void setInheritedCanvas(int width, int height);

signals:
    void generateDatasetRequested(const QJsonObject &payload);
    void navigateRequested(const QString &modeId);
    void openModelsRequested();

private:
    void buildUi();
    void applyTheme();
    void generateDataset();
    void updateDatasetPreview();
    void updateCanvasCaption();
    QString defaultOutputRoot() const;

    QString projectRoot_;

    QTextEdit *datasetPromptsEdit_ = nullptr;
    QLineEdit *datasetOutputEdit_ = nullptr;
    QSpinBox *imagesPerPromptSpin_ = nullptr;
    QSpinBox *seedStartSpin_ = nullptr;
    QSpinBox *datasetWidthSpin_ = nullptr;
    QSpinBox *datasetHeightSpin_ = nullptr;
    QWidget *advancedBlock_ = nullptr;
    QLabel *canvasCaptionLabel_ = nullptr;
    int inheritedWidth_ = 0;
    int inheritedHeight_ = 0;
    QCheckBox *shufflePromptsCheckBox_ = nullptr;
    QCheckBox *saveMetadataCheckBox_ = nullptr;
    QPushButton *generateDatasetButton_ = nullptr;
    QPushButton *previewDatasetButton_ = nullptr;
    QPushButton *openOutputButton_ = nullptr;
    QLabel *datasetPreviewLabel_ = nullptr;
    QProgressBar *datasetProgress_ = nullptr;
    QLabel *statusLabel_ = nullptr;
};
