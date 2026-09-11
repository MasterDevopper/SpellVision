#pragma once

// Train page — launches external LoRA / DreamBooth trainers (Sohya_kk).
// Not a synthetic dataset generator (that's DatasetGenerationPage).
// Simple: family + last Dataset folder + hardware-smart rank/batch.
// Advanced reveals rank/batch in place. Dual-PC recipes stay fail-closed until T6.

#include <QString>
#include <QWidget>

class QComboBox;
class QLabel;
class QLineEdit;
class QPushButton;
class QSpinBox;
class QTextEdit;
class QProcess;
class QWidget;

class TrainPage : public QWidget
{
    Q_OBJECT

public:
    explicit TrainPage(QWidget *parent = nullptr);

    void setProjectRoot(const QString &root);
    void updateDisclosure(bool advanced);

signals:
    void navigateRequested(const QString &modeId);
    void openDatasetRequested();

private:
    void buildUi();
    void applyTheme();
    void browseTrainer();
    void browseDataset();
    void launchTrainer();
    void openDataset();
    void appendLog(const QString &line);
    void probeTrainer();
    void refreshHardwareDefaults();
    void applyFamilyPreset();
    void writeRecipeSidecar() const;
    QString defaultSohyaPath() const;
    QString lastDatasetRoot() const;

    QString projectRoot_;
    bool advanced_ = false;

    QLineEdit *pathEdit_ = nullptr;
    QComboBox *familyCombo_ = nullptr;
    QLineEdit *datasetEdit_ = nullptr;
    QPushButton *datasetBrowseButton_ = nullptr;
    QWidget *advancedBlock_ = nullptr;
    QSpinBox *rankSpin_ = nullptr;
    QSpinBox *batchSpin_ = nullptr;
    QLabel *statusLabel_ = nullptr;
    QLabel *hardwareDefaultsLabel_ = nullptr;
    QPushButton *browseButton_ = nullptr;
    QPushButton *launchButton_ = nullptr;
    QPushButton *datasetButton_ = nullptr;
    QTextEdit *logEdit_ = nullptr;
    QProcess *process_ = nullptr;
};
