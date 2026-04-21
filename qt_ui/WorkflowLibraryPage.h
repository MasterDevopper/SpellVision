#pragma once

#include <functional>

#include <QHash>
#include <QJsonObject>
#include <QSet>
#include <QStringList>
#include <QVector>
#include <QWidget>

class QLabel;
class QPushButton;
class QLineEdit;
class QComboBox;
class QListWidget;
class QListWidgetItem;
class QPlainTextEdit;
class QProcess;

class WorkflowLibraryPage : public QWidget
{
    Q_OBJECT

public:
    explicit WorkflowLibraryPage(QWidget *parent = nullptr);

    void setProjectRoot(const QString &projectRoot);
    void setPythonExecutable(const QString &pythonExecutable);

    void setImportedWorkflowsRoot(const QString &importedWorkflowsRoot);

    // MainWindow compatibility
    void setProfilesRoot(const QString &profilesRoot) { setImportedWorkflowsRoot(profilesRoot); }
    void refreshProfiles() { refreshLibrary(); }

public slots:
    void refreshLibrary();

signals:
    void importWorkflowRequested();
    void launchWorkflowRequested(const QJsonObject &profile);
    void workflowDraftRequested(const QJsonObject &draft);

private slots:
    void onImportClicked();
    void onRefreshClicked();
    void onSearchChanged(const QString &text);
    void onFilterChanged();
    void onCurrentWorkflowChanged(QListWidgetItem *current, QListWidgetItem *previous);
    void onLaunchClicked();
    void onApplyClicked();
    void onRevealFolderClicked();
    void onOpenWorkflowJsonClicked();
    void onRetryDependenciesClicked();
    void onDeleteWorkflowClicked();

private:
    enum class ReadinessState
    {
        Ready,
        Unsupported,
        NeedsCompilation,
        RuntimeOffline,
        MissingDependencies,
        MissingWorkflow,
        NeedsReview
    };

    struct RuntimeProbeResult
    {
        bool ok = false;
        QString message;
    };

    struct RuntimeAssetCatalogResult
    {
        bool ok = false;
        QString message;
        QHash<QString, QSet<QString>> allowedValuesByKey;
        QSet<QString> cataloguedKeys;
    };

    struct WorkflowRecord
    {
        QString displayName;
        QString modeId;
        QString mediaType;
        QString backend;
        QStringList tags;

        QString primaryTask;
        QStringList supportedModes;
        QStringList requiredInputs;
        QStringList optionalInputs;
        QStringList outputKinds;
        QStringList capabilityEvidence;
        QStringList capabilityWarnings;
        QString capabilityVersion;
        double classificationConfidence = 0.0;
        bool capabilityFromGraph = false;

        QString importRoot;
        QString profilePath;
        QString sourceWorkflowPath;
        QString compiledPromptPath;
        QString scanReportPath;

        QString sourceWorkflowFormat = QStringLiteral("unknown");
        QString compiledPromptFormat = QStringLiteral("unknown");
        bool apiPromptCompatible = false;
        bool compiledPromptPresent = false;

        QStringList compileWarnings;
        QString compileError;

        QString launchArtifactPath;
        QString launchArtifactFormat = QStringLiteral("unknown");
        bool launchArtifactValidated = false;
        bool launchArtifactValid = false;
        QStringList launchValidationErrors;
        QStringList launchValidationWarnings;

        bool runtimeAssetValidationAttempted = false;
        bool runtimeAssetValidationPassed = false;
        QString runtimeAssetValidationMessage;
        QStringList missingRuntimeAssets;
        QStringList runtimeAssetWarnings;

        bool reusableDraftPresent = false;
        bool reusableDraftSafeToSubmit = false;
        QString reusableDraftReason;
        QJsonObject reusableDraft;

        QStringList missingCustomNodes;
        QStringList warnings;

        int referencedModelCount = 0;
        int unresolvedDependencyActions = 0;

        bool supportedInCurrentBuild = false;
        bool workflowJsonPresent = false;

        RuntimeProbeResult runtimeProbe;
        ReadinessState readiness = ReadinessState::NeedsReview;
        QString readinessLabel;
        QString readinessReason;
    };

    void buildUi();
    void applyTheme();

    void scanImportedWorkflows();
    WorkflowRecord loadWorkflowRecord(const QString &profilePath) const;
    void updateRuntimeState(WorkflowRecord &record) const;
    void validateRuntimeAssets(WorkflowRecord &record) const;
    void classifyWorkflow(WorkflowRecord &record) const;
    void applyCapabilityReport(WorkflowRecord &record, const QJsonObject &capability) const;
    bool ensureCompiledPrompt(WorkflowRecord &record) const;
    void buildReusableDraft(WorkflowRecord &record) const;

    void rebuildFilters();
    void rebuildList();
    bool matchesFilters(const WorkflowRecord &record) const;

    void updateSummary();
    void updateDetailsPanel();
    void clearDetailsPanel();
    int currentWorkflowIndex() const;
    QJsonObject sendWorkerCommand(const QJsonObject &request, int timeoutMs, QString *stderrText = nullptr) const;

    using WorkerCommandFinishedHandler = std::function<void(const QJsonObject &response, const QString &stderrText)>;
    void setWorkflowLifecycleBusy(bool busy, const QString &statusText = QString());
    void startWorkflowLifecycleCommand(const QJsonObject &request,
                                       const QString &busyText,
                                       const QString &timeoutText,
                                       int timeoutMs,
                                       WorkerCommandFinishedHandler finishedHandler);

    QString readinessFilterKey(ReadinessState state) const;
    QString workflowListLine(const WorkflowRecord &record) const;
    QString workflowSummaryText(const WorkflowRecord &record) const;
    QString workflowDetailsText(const WorkflowRecord &record) const;

    static QString normalizedModeId(const QString &value);
    static QString safeObjectString(const QJsonObject &object, const QStringList &keys);
    static QStringList safeObjectStringList(const QJsonObject &object, const QStringList &keys);
    static int safeObjectInt(const QJsonObject &object, const QStringList &keys, int fallback = 0);
    static QString resolvePossiblyRelativePath(const QString &root, const QString &candidate);
    static bool isVideoMode(const QString &modeId, const QString &mediaType);
    static bool isImageMode(const QString &modeId, const QString &mediaType);
    static QString detectWorkflowFormat(const QJsonObject &object);
    static QString assetCatalogKey(const QString &classType, const QString &inputName);
    static QStringList assetInputNamesForClassType(const QString &classType);
    static bool validateApiPromptObject(
        const QJsonObject &prompt,
        QStringList *errors,
        QStringList *warnings);

    static QJsonObject compileUiGraphToApiPrompt(
        const QJsonObject &graph,
        QStringList *warnings,
        QString *errorText);

    RuntimeProbeResult probeComfyRuntime() const;
    RuntimeAssetCatalogResult fetchComfyAssetCatalog() const;

private:
    QString projectRoot_;
    QString pythonExecutable_;
    QString importedWorkflowsRoot_;
    QString comfyEndpoint_ = QStringLiteral("http://127.0.0.1:8188");

    QVector<WorkflowRecord> workflows_;

    QLabel *titleLabel_ = nullptr;
    QLabel *summaryLabel_ = nullptr;

    QPushButton *importButton_ = nullptr;
    QPushButton *refreshButton_ = nullptr;

    QLineEdit *searchEdit_ = nullptr;
    QComboBox *taskFilter_ = nullptr;
    QComboBox *backendFilter_ = nullptr;
    QComboBox *readinessFilter_ = nullptr;

    QListWidget *workflowList_ = nullptr;

    QLabel *detailTitleLabel_ = nullptr;
    QLabel *detailMetaLabel_ = nullptr;
    QLabel *detailStatusLabel_ = nullptr;
    QPlainTextEdit *detailText_ = nullptr;

    QPushButton *launchButton_ = nullptr;
    QPushButton *applyButton_ = nullptr;
    QPushButton *revealFolderButton_ = nullptr;
    QPushButton *openWorkflowJsonButton_ = nullptr;
    QPushButton *retryDependenciesButton_ = nullptr;
    QPushButton *deleteWorkflowButton_ = nullptr;

    QProcess *workflowLifecycleProcess_ = nullptr;
    WorkerCommandFinishedHandler workflowLifecycleFinishedHandler_;
    bool workflowLifecycleBusy_ = false;
};
