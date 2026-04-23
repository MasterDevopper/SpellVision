#pragma once

#include <QJsonObject>
#include <functional>
#include <QString>
#include <QWidget>

class QLabel;
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
    void refreshStatus();
    void warmCache();

signals:
    void statusMessageChanged(const QString &message);

private slots:
    void installManager();
    void installSelectedNode();
    void installMissingVideoNodes();
    void restartComfyRuntime();
    void openComfyRoot();
    void openCustomNodesRoot();

private:
    QJsonObject sendWorkerRequest(const QJsonObject &request, int timeoutMs = 120000);
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
    QString selectedPackageName() const;
    QString selectedRepoUrl() const;
    QString selectedInstallMethod() const;
    void setBusy(bool busy);

    QString projectRoot_;
    QString pythonExecutable_;
    QString comfyRoot_;

    QLabel *managerStateLabel_ = nullptr;
    QLabel *runtimeStateLabel_ = nullptr;
    QLabel *comfyRootLabel_ = nullptr;
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
    QPushButton *openComfyButton_ = nullptr;
    QPushButton *openCustomNodesButton_ = nullptr;

    QTableWidget *nodesTable_ = nullptr;
    QTextEdit *logView_ = nullptr;

    bool managerRequestInFlight_ = false;
};
