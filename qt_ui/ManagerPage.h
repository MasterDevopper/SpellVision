#pragma once

#include <QJsonObject>
#include <QString>
#include <QWidget>
#include <functional>

class QComboBox;
class QLabel;
class QLineEdit;
class QPushButton;
class QTableWidget;
class QTextEdit;

class ManagerPage : public QWidget
{
    Q_OBJECT

public:
    explicit ManagerPage(QWidget *parent = nullptr);

    void setProjectRoot(const QString &projectRoot);
    void setPythonExecutable(const QString &pythonExecutable);
    void warmCache();

public slots:
    void refreshStatus();

signals:
    void statusMessageChanged(const QString &message);

private slots:
    void installManager();
    void installSelectedNode();
    void installMissingVideoNodes();
    void restartComfyRuntime();
    void chooseComfyRoot();
    void chooseModelsRoot();
    void checkFamilyInstallPlan();
    void browseHuggingFace();
    void browseCivitai();
    void downloadFamilyComponent();
    void inspectPastedModelUrl();
    void importSelectedModelChoice();
    void openComfyRoot();
    void openCustomNodesRoot();

private:
    void sendWorkerRequestAsync(const QJsonObject &request,
                                int timeoutMs,
                                const QString &label,
                                std::function<void(const QJsonObject &)> callback);
    QJsonObject parseWorkerResponse(const QString &stdoutText, const QString &stderrText) const;
    void applyManagerStatus(const QJsonObject &payload);
    void appendLog(const QString &message);
    QString resolveProjectRoot() const;
    QString resolvePythonExecutable() const;
    QString currentComfyRoot() const;
    QString currentModelsRoot() const;
    QString selectedPackageName() const;
    QStringList presentModelBasenames() const;
    void requestFamilyInstall(bool dryRun, const QString &onlyComponent = QString());
    void applyFamilyInstallPayload(const QJsonObject &payload);
    QString selectedRepoUrl() const;
    QString selectedInstallMethod() const;
    void setBusy(bool busy);

    QString projectRoot_;
    QString pythonExecutable_;
    QString comfyRoot_;

    QLabel *managerStateLabel_ = nullptr;
    QLabel *runtimeStateLabel_ = nullptr;
    QLabel *comfyRootLabel_ = nullptr;
    QLabel *modelsRootLabel_ = nullptr;
    QLabel *managerPathLabel_ = nullptr;
    QLabel *nodeSummaryLabel_ = nullptr;
    QLabel *cacheSourceLabel_ = nullptr;
    QLabel *lastCheckedLabel_ = nullptr;
    QLabel *cachePathLabel_ = nullptr;

    QPushButton *refreshButton_ = nullptr;
    QPushButton *installManagerButton_ = nullptr;
    QPushButton *installSelectedButton_ = nullptr;
    QPushButton *installMissingVideoButton_ = nullptr;
    QPushButton *restartRuntimeButton_ = nullptr;
    QPushButton *chooseComfyRootButton_ = nullptr;
    QPushButton *chooseModelsRootButton_ = nullptr;
    QPushButton *openComfyButton_ = nullptr;
    QPushButton *openCustomNodesButton_ = nullptr;
    QComboBox *familyInstallCombo_ = nullptr;
    QComboBox *familyTaskCombo_ = nullptr;
    QPushButton *checkFamilyPlanButton_ = nullptr;
    QPushButton *browseHfButton_ = nullptr;
    QPushButton *browseCivitaiButton_ = nullptr;
    QTableWidget *familySlotsTable_ = nullptr;
    QLineEdit *modelUrlEdit_ = nullptr;
    QPushButton *inspectUrlButton_ = nullptr;
    QPushButton *importSelectedButton_ = nullptr;
    QTableWidget *importChoicesTable_ = nullptr;
    QJsonObject lastImportCatalog_;

    QTableWidget *nodesTable_ = nullptr;
    QTextEdit *logView_ = nullptr;

    bool managerRequestInFlight_ = false;
};
