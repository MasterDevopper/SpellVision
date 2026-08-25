#pragma once

// Gen3D — Image-to-3D cockpit.
// Generation runs ONLY through ComfyUI (worker enqueue / workflow launch).
// External spike QProcess is intentionally disabled (system-crash risk).

#include <QJsonObject>
#include <QString>
#include <QStringList>
#include <QVector>
#include <QWidget>

class QComboBox;
class QLabel;
class QLineEdit;
class QListWidget;
class QPushButton;
class QTextEdit;

class Gen3DPage : public QWidget
{
    Q_OBJECT

public:
    explicit Gen3DPage(QWidget *parent = nullptr);

    void setProjectRoot(const QString &root);
    void setInputImage(const QString &path);
    void updateDisclosure(bool advanced);
    void setBusy(bool busy, const QString &message = QString());
    void setResultMesh(const QString &path, const QString &caption = QString());
    // Profiles from WorkflowLibraryPage::importedWorkflowLaunchProfiles()
    void setAvailableWorkflows(const QVector<QJsonObject> &profiles);

signals:
    void navigateRequested(const QString &modeId);
    void openModelsRequested();
    void openWorkflowsRequested();
    // MainWindow launches via Comfy workflow / worker — never local QProcess.
    void comfyGenerateRequested(const QJsonObject &request);

private:
    enum class Backend { Pixal3D = 0, Trellis2 = 1 };

    struct AngleSlot {
        QString path;
        QString angle; // front|back|left|right|three_quarter|top|custom
    };

    void buildUi();
    void applyTheme();
    void probeComfyPath();
    void browsePrimary();
    void addAngleImage();
    void removeSelectedAngle();
    void rebuildAngleList();
    void onBackendChanged();
    void runGenerate();
    void appendLog(const QString &line);
    Backend currentBackend() const;
    QString defaultOutDir() const;
    QJsonObject buildComfyRequest() const;

    QString projectRoot_;
    bool advanced_ = false;
    bool busy_ = false;
    bool comfyReachable_ = false;

    QLabel *statusLabel_ = nullptr;
    QLabel *toolLabel_ = nullptr;
    QLineEdit *primaryEdit_ = nullptr;
    QLineEdit *outTagEdit_ = nullptr;
    QComboBox *backendCombo_ = nullptr;
    QComboBox *workflowCombo_ = nullptr;
    QComboBox *resCombo_ = nullptr;
    QWidget *multiViewBlock_ = nullptr;
    QListWidget *angleList_ = nullptr;
    QComboBox *angleCombo_ = nullptr;
    QPushButton *browseButton_ = nullptr;
    QPushButton *addAngleButton_ = nullptr;
    QPushButton *removeAngleButton_ = nullptr;
    QPushButton *generateButton_ = nullptr;
    QPushButton *openOutButton_ = nullptr;
    QPushButton *openFlowsButton_ = nullptr;
    QTextEdit *logEdit_ = nullptr;
    QLabel *resultLabel_ = nullptr;

    QVector<AngleSlot> angleSlots_;
    QVector<QJsonObject> workflowProfiles_;
};
