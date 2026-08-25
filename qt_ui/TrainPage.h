#pragma once

// Train page — launches external LoRA / DreamBooth trainers (Sohya_kk).
// Not a synthetic dataset generator (that's DatasetGenerationPage).

#include <QString>
#include <QWidget>

class QLabel;
class QLineEdit;
class QPushButton;
class QTextEdit;
class QProcess;

class TrainPage : public QWidget
{
    Q_OBJECT

public:
    explicit TrainPage(QWidget *parent = nullptr);

    void setProjectRoot(const QString &root);

signals:
    void navigateRequested(const QString &modeId);
    void openDatasetRequested();

private:
    void buildUi();
    void applyTheme();
    void browseTrainer();
    void launchTrainer();
    void openDataset();
    void appendLog(const QString &line);
    void probeTrainer();
    QString defaultSohyaPath() const;

    QString projectRoot_;
    QLineEdit *pathEdit_ = nullptr;
    QLabel *statusLabel_ = nullptr;
    QPushButton *browseButton_ = nullptr;
    QPushButton *launchButton_ = nullptr;
    QPushButton *datasetButton_ = nullptr;
    QTextEdit *logEdit_ = nullptr;
    QProcess *process_ = nullptr;
};
