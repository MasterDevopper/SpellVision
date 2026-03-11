#pragma once

#include <QMainWindow>

class QListWidget;
class QListWidgetItem;
class QTextEdit;
class QLabel;
class QSpinBox;
class QPushButton;
class QDockWidget;
class QAction;
class QLineEdit;
class QDoubleSpinBox;
class QGraphicsView;
class QGraphicsScene;
class QCheckBox;
class QCloseEvent;
class QProcess;
class QProgressBar;
class QTimer;

class MainWindow : public QMainWindow
{
    Q_OBJECT

public:
    explicit MainWindow(QWidget *parent = nullptr);
    ~MainWindow() override = default;

protected:
    void closeEvent(QCloseEvent *event) override;

private slots:
    void createDummyJob();
    void generateTextToImage();
    void generateImageToImage();
    void browseOutputPath();
    void browseInputImagePath();
    void showAbout();
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
    void pollBackendHealth();

private:
    void buildMenuBar();
    void buildToolBar();
    void buildStatusBar();
    void buildCentralView();
    void buildDocks();
    void buildInspectorUi();
    void loadWorkspaceState();
    void saveWorkspaceState();

    void appendLog(const QString &message, const QString &category = "info");
    void appendError(const QString &message);
    void appendQueue(const QString &message);

    void refreshRustStatus(bool logSummary = false);
    void showGeneratedImage(const QString &imagePath);
    void updateStatusSummary();
    void updatePerfFromJson(const QString &jsonText);
    void ensureWorkerService();
    QString sendWorkerRequest(const QString &jsonPayload);
    bool pingWorkerService();
    void updateBackendStatus(bool online, const QString &detail = QString());
    void setGeneratingState(bool generating, const QString &detail = QString());

    QString projectRoot() const;
    QString pythonExecutable() const;
    QString modelsRoot() const;
    QString checkpointsRoot() const;
    QString lorasRoot() const;
    QString outputsRoot() const;
    QString imagesRoot() const;
    QString metadataRoot() const;
    QString defaultOutputPath() const;
    QString metadataPathForImage(const QString &imagePath) const;
    QString imagePathForBatchIndex(int batchIndex) const;
    void ensureOutputDirs() const;
    void loadMetadataForImage(const QString &imagePath);
    void selectHistoryItemByPath(const QString &imagePath);

    QWidget *centralPanel = nullptr;

    QListWidget *modelList = nullptr;
    QListWidget *loraList = nullptr;
    QWidget *inspectorWidget = nullptr;
    QTextEdit *logPanel = nullptr;
    QTextEdit *errorPanel = nullptr;
    QTextEdit *queuePanel = nullptr;
    QListWidget *historyList = nullptr;
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
    QProgressBar *generationProgressBar = nullptr;
    QSpinBox *jobCountSpin = nullptr;
    QPushButton *createJobButton = nullptr;

    QLineEdit *promptEdit = nullptr;
    QLineEdit *negativePromptEdit = nullptr;
    QLineEdit *modelPathEdit = nullptr;
    QLineEdit *loraPathEdit = nullptr;
    QDoubleSpinBox *loraScaleSpin = nullptr;
    QSpinBox *batchCountSpin = nullptr;
    QCheckBox *randomizeSeedCheck = nullptr;
    QCheckBox *autoScrollCheck = nullptr;
    QSpinBox *widthSpin = nullptr;
    QSpinBox *heightSpin = nullptr;
    QSpinBox *stepsSpin = nullptr;
    QDoubleSpinBox *cfgSpin = nullptr;
    QSpinBox *seedSpin = nullptr;
    QLineEdit *inputImagePathEdit = nullptr;
    QPushButton *browseInputImageButton = nullptr;
    QDoubleSpinBox *strengthSpin = nullptr;
    QLineEdit *outputPathEdit = nullptr;
    QPushButton *browseOutputButton = nullptr;
    QPushButton *generateButton = nullptr;
    QPushButton *generateI2IButton = nullptr;

    QLabel *imagePathLabel = nullptr;
    QGraphicsView *imageView = nullptr;
    QGraphicsScene *imageScene = nullptr;
    QPushButton *refreshHistoryButton = nullptr;
    QPushButton *openImageButton = nullptr;
    QPushButton *openFolderButton = nullptr;

    QDockWidget *modelsDock = nullptr;
    QDockWidget *lorasDock = nullptr;
    QDockWidget *inspectorDock = nullptr;
    QDockWidget *logsDock = nullptr;
    QDockWidget *errorsDock = nullptr;
    QDockWidget *queueDock = nullptr;
    QDockWidget *historyDock = nullptr;
    QDockWidget *metadataDock = nullptr;
    QDockWidget *gpuDock = nullptr;

    QAction *actionNewJob = nullptr;
    QAction *actionGenerateT2I = nullptr;
    QAction *actionGenerateI2I = nullptr;
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

    QString currentImagePath;
    QString lastGenerationTime;
    QString lastStepsPerSec;
    QString lastCudaAllocated;
    QString lastCudaReserved;

    QProcess *workerServiceProcess = nullptr;
    QTimer *backendPollTimer = nullptr;
    bool isGenerating = false;
};