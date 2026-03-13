#pragma once

#include <QMainWindow>
#include <QString>
#include <QJsonObject>

class QAction;
class QCheckBox;
class QCloseEvent;
class QDockWidget;
class QDoubleSpinBox;
class QGraphicsScene;
class QGraphicsView;
class QLabel;
class QLineEdit;
class QListWidget;
class QListWidgetItem;
class QProcess;
class QProgressBar;
class QPushButton;
class QSpinBox;
class QTextEdit;
class QTimer;
class QWidget;

enum class GenerationJobState
{
    Unknown,
    Queued,
    Starting,
    Running,
    Completed,
    Failed,
    Cancelled,
};

class MainWindow : public QMainWindow
{
    Q_OBJECT

public:
    explicit MainWindow(QWidget *parent = nullptr);

protected:
    void closeEvent(QCloseEvent *event) override;

private slots:
    void createDummyJob();
    void generateTextToImage();
    void generateImageToImage();
    void retryLastGeneration();
    void cancelActiveGeneration();
    void browseInputImagePath();
    void browseOutputPath();
    void refreshHistory();
    void refreshModels();
    void refreshGpuInfo();
    void onHistoryItemClicked(QListWidgetItem *item);
    void onModelItemClicked(QListWidgetItem *item);
    void onLoraItemClicked(QListWidgetItem *item);
    void openSelectedImage();
    void openSelectedImageFolder();
    void clearLogs();
    void clearErrors();
    void copyLogs();
    void showAbout();
    void pollBackendHealth();

private:
    void buildMenuBar();
    void buildToolBar();
    void buildStatusBar();
    void buildCentralView();
    void buildInspectorUi();
    void buildDocks();

    QString projectRoot() const;
    QString pythonExecutable() const;
    QString modelsRoot() const;
    QString checkpointsRoot() const;
    QString lorasRoot() const;
    QString outputsRoot() const;
    QString imagesRoot() const;
    QString metadataRoot() const;
    QString defaultOutputPath() const;
    QString imagePathForBatchIndex(int batchIndex) const;
    QString metadataPathForImage(const QString &imagePath) const;

    void ensureOutputDirs() const;
    void updateBackendStatus(bool online, const QString &detail = QString());
    bool pingWorkerService();
    void ensureWorkerService();
    QString sendWorkerRequest(const QString &jsonPayload);

    void startStreamingWorkerRequest(const QJsonObject &payload, const QString &mode);
    void dispatchGenerationPayload(const QJsonObject &payload, const QString &mode, bool markAsRetry = false);
    void handleWorkerEventLine(const QString &line, const QString &mode);
    void handleCanonicalJobUpdate(const QJsonObject &payload, const QString &mode);
    void updateGenerationProgress(int step, int total, int percent, const QString &mode);
    void setRetryAvailable(bool available);
    QString makeRetryOutputPath(const QString &baseOutputPath) const;
    QJsonObject metadataObjectForImage(const QString &imagePath) const;
    QString historyLabelForImage(const QString &imagePath) const;
    GenerationJobState parseJobState(const QString &state) const;
    bool isTerminalJobState(GenerationJobState state) const;
    void applyJobStateUi(GenerationJobState state,
                         const QString &mode,
                         const QString &message = QString(),
                         int progressPercent = -1,
                         int current = -1,
                         int total = -1);
    void finalizeActiveJobFailure(const QString &message, const QString &traceback = QString(), bool cancelled = false);
    void finalizeActiveJobSuccess(const QJsonObject &resultObj, const QString &mode);
    void setGeneratingState(bool generating, const QString &detail = QString());

    void refreshRustStatus(bool logSummary = false);
    void showGeneratedImage(const QString &imagePath);
    void loadMetadataForImage(const QString &imagePath);
    void selectHistoryItemByPath(const QString &imagePath);
    void updatePerfFromJson(const QString &jsonText);
    void updateStatusSummary();

    void appendLog(const QString &message, const QString &category = "info");
    void appendError(const QString &message);
    void appendQueue(const QString &message);

    void loadWorkspaceState();
    void saveWorkspaceState();

    QWidget *centralPanel = nullptr;
    QWidget *inspectorWidget = nullptr;

    QListWidget *modelList = nullptr;
    QListWidget *loraList = nullptr;
    QListWidget *historyList = nullptr;

    QTextEdit *queuePanel = nullptr;
    QTextEdit *logPanel = nullptr;
    QTextEdit *errorPanel = nullptr;
    QTextEdit *metadataPanel = nullptr;
    QTextEdit *gpuPanel = nullptr;

    QLabel *dashboardTitle = nullptr;
    QLabel *rustInfoLabel = nullptr;
    QLabel *queueInfoLabel = nullptr;
    QLabel *backendStatusLabel = nullptr;
    QLabel *generationStatusLabel = nullptr;
    QLabel *activeModelLabel = nullptr;
    QLabel *activeLoraLabel = nullptr;
    QLabel *perfLabel = nullptr;
    QLabel *imagePathLabel = nullptr;

    QProgressBar *generationProgressBar = nullptr;

    QSpinBox *jobCountSpin = nullptr;
    QSpinBox *batchCountSpin = nullptr;
    QSpinBox *widthSpin = nullptr;
    QSpinBox *heightSpin = nullptr;
    QSpinBox *stepsSpin = nullptr;
    QSpinBox *seedSpin = nullptr;

    QDoubleSpinBox *cfgSpin = nullptr;
    QDoubleSpinBox *strengthSpin = nullptr;
    QDoubleSpinBox *loraScaleSpin = nullptr;

    QCheckBox *autoScrollCheck = nullptr;
    QCheckBox *randomizeSeedCheck = nullptr;

    QLineEdit *promptEdit = nullptr;
    QLineEdit *negativePromptEdit = nullptr;
    QLineEdit *modelPathEdit = nullptr;
    QLineEdit *loraPathEdit = nullptr;
    QLineEdit *inputImagePathEdit = nullptr;
    QLineEdit *outputPathEdit = nullptr;

    QPushButton *createJobButton = nullptr;
    QPushButton *generateButton = nullptr;
    QPushButton *generateI2IButton = nullptr;
    QPushButton *retryGenerationButton = nullptr;
    QPushButton *cancelGenerationButton = nullptr;
    QPushButton *browseInputImageButton = nullptr;
    QPushButton *browseOutputButton = nullptr;
    QPushButton *refreshHistoryButton = nullptr;
    QPushButton *openImageButton = nullptr;
    QPushButton *openFolderButton = nullptr;

    QGraphicsScene *imageScene = nullptr;
    QGraphicsView *imageView = nullptr;

    QDockWidget *modelsDock = nullptr;
    QDockWidget *lorasDock = nullptr;
    QDockWidget *historyDock = nullptr;
    QDockWidget *inspectorDock = nullptr;
    QDockWidget *metadataDock = nullptr;
    QDockWidget *gpuDock = nullptr;
    QDockWidget *queueDock = nullptr;
    QDockWidget *logsDock = nullptr;
    QDockWidget *errorsDock = nullptr;

    QAction *actionNewJob = nullptr;
    QAction *actionGenerateT2I = nullptr;
    QAction *actionGenerateI2I = nullptr;
    QAction *actionRetryGeneration = nullptr;
    QAction *actionCancelGeneration = nullptr;
    QAction *actionRefreshHistory = nullptr;
    QAction *actionRefreshModels = nullptr;
    QAction *actionRefreshGpu = nullptr;
    QAction *actionOpenImage = nullptr;
    QAction *actionOpenFolder = nullptr;
    QAction *actionClearLogs = nullptr;
    QAction *actionClearErrors = nullptr;
    QAction *actionCopyLogs = nullptr;
    QAction *actionExit = nullptr;
    QAction *actionAbout = nullptr;

    QProcess *workerServiceProcess = nullptr;
    QProcess *activeWorkerClientProcess = nullptr;
    QTimer *backendPollTimer = nullptr;

    QString currentImagePath;
    QString lastGenerationTime;
    QString lastStepsPerSec;
    QString lastCudaAllocated;
    QString lastCudaReserved;
    QString activeJobMode;
    QString activeOutputPath;
    QString activeWorkerJobId;
    int activeJobId = -1;
    bool isGenerating = false;
    bool activeWorkerStreamReachedTerminal = false;
    bool retryAvailable = false;
    GenerationJobState currentJobState = GenerationJobState::Unknown;
    QJsonObject lastGenerationPayload;
    QString lastGenerationMode;
    QString lastCompletedOrCancelledWorkerJobId;
};
