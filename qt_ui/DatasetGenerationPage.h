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

signals:
    void generateDatasetRequested(const QJsonObject &payload);
    void navigateRequested(const QString &modeId);
    void openModelsRequested();

private:
    void buildUi();
    void applyTheme();
    void generateDataset();
    void updateDatasetPreview();
    QString defaultOutputRoot() const;

    QString projectRoot_;

    QTextEdit *datasetPromptsEdit_ = nullptr;
    QLineEdit *datasetOutputEdit_ = nullptr;
    QSpinBox *imagesPerPromptSpin_ = nullptr;
    QSpinBox *seedStartSpin_ = nullptr;
    QSpinBox *datasetWidthSpin_ = nullptr;
    QSpinBox *datasetHeightSpin_ = nullptr;
    QCheckBox *shufflePromptsCheckBox_ = nullptr;
    QCheckBox *saveMetadataCheckBox_ = nullptr;
    QPushButton *generateDatasetButton_ = nullptr;
    QPushButton *previewDatasetButton_ = nullptr;
    QPushButton *openOutputButton_ = nullptr;
    QLabel *datasetPreviewLabel_ = nullptr;
    QProgressBar *datasetProgress_ = nullptr;
    QLabel *statusLabel_ = nullptr;
};
