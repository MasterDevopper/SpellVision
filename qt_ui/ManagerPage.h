#pragma once

#include <QJsonObject>
#include <QString>
#include <QWidget>

#include "shell/EndpointPanel.h"
#include <functional>

class QCheckBox;
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
    // The optimization evidence panel: what is installed, what the RUNNING process was actually
    // launched with, and what has been measured. Three different facts; the app used to show none
    // of them. Its own request, not folded into comfy_manager_status, because it must be able to
    // refresh while a long manager call is in flight.
    void refreshOptimizationEvidence();
    // Unload the runtimes then clear the CUDA cache -- the lighter recovery for
    // wedged VRAM accounting, short of restarting the Comfy process. Cockpit
    // Unload models uses this same path.
    void freeRuntimeVram();

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
    // Renders one row per lever from an `optimization_results` reply. All four columns come from
    // spellvision::shell::OptimizationEvidence, which is where the honesty rules live and where
    // tests/cpp/test_optimization_panel.cpp holds them.
    void applyOptimizationEvidence(const QJsonObject &payload);
    // Renders comfy_runtime_status.version_check. "Could not reach GitHub" must never render the
    // same as "up to date", so the unknown state carries its reason.
    void applyComfyVersionCheck(const QJsonObject &check);
    void onUpdateComfyClicked();
    // Builds the class->pack reverse index in budget-bounded slices, so the UI shows it climbing
    // instead of freezing for the whole build. Resumable worker-side; stopping is not losing work.
    void onBuildNodeIndexClicked();
    void runNodeIndexSlice();
    void appendLog(const QString &message);
    QString resolveProjectRoot() const;
    QString resolvePythonExecutable() const;
    QString currentComfyRoot() const;
    QString configuredComfyRoot() const;
    QString currentModelsRoot() const;
    QString selectedPackageName() const;
    QStringList presentModelBasenames() const;
    void requestFamilyInstall(bool dryRun, const QString &onlyComponent = QString());
    void applyFamilyInstallPayload(const QJsonObject &payload);
    QString selectedRepoUrl() const;
    QString selectedInstallMethod() const;
    void setBusy(bool busy);
    // Re-reads the endpoint registry and asks every enabled endpoint for its own status. Replaces
    // probeSpellNodeWorker(), which probed a host spelled as a C++ literal and then decided the
    // LOCAL master's health by looking for "healthy=yes" inside another QLabel's text.
    void refreshEndpointStatuses();

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
    spellvision::shell::EndpointPanel *endpointPanel_ = nullptr;
    QLabel *cachePathLabel_ = nullptr;
    QLabel *comfyVersionLabel_ = nullptr;
    QPushButton *updateComfyButton_ = nullptr;
    QString latestComfyRelease_;
    QString comfyReleaseUrl_;
    QTableWidget *optimizationTable_ = nullptr;
    QLabel *optimizationSummaryLabel_ = nullptr;
    QPushButton *refreshOptimizationButton_ = nullptr;
    bool optimizationRequestInFlight_ = false;
    QLabel *nodeIndexLabel_ = nullptr;
    QPushButton *buildNodeIndexButton_ = nullptr;
    bool nodeIndexBuilding_ = false;

    QPushButton *refreshButton_ = nullptr;
    QPushButton *installManagerButton_ = nullptr;
    QPushButton *installSelectedButton_ = nullptr;
    QPushButton *installMissingVideoButton_ = nullptr;
    QPushButton *restartRuntimeButton_ = nullptr;
    QPushButton *freeVramButton_ = nullptr;
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
