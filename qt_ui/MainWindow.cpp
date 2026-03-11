#include "MainWindow.h"

#include <QProgressBar>
#include <QTimer>
#include <QAction>
#include <QApplication>
#include <QByteArray>
#include <QCheckBox>
#include <QClipboard>
#include <QCloseEvent>
#include <QCoreApplication>
#include <QDateTime>
#include <QDesktopServices>
#include <QDir>
#include <QDockWidget>
#include <QDoubleSpinBox>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QFormLayout>
#include <QGraphicsScene>
#include <QGraphicsView>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QMenu>
#include <QMenuBar>
#include <QMessageBox>
#include <QPixmap>
#include <QProcess>
#include <QProcessEnvironment>
#include <QPushButton>
#include <QRandomGenerator>
#include <QScrollBar>
#include <QSettings>
#include <QSpinBox>
#include <QStandardPaths>
#include <QStatusBar>
#include <QTextEdit>
#include <QToolBar>
#include <QUrl>
#include <QVBoxLayout>
#include <QWidget>
#include <QThread>

extern "C"
{
    const char *spellvision_version();
    int spellvision_queue_count();
    void spellvision_add_dummy_job();
    int spellvision_create_job(const char *task_type, const char *prompt, const char *output_path);
    void spellvision_mark_job_finished(int job_id);
    void spellvision_mark_job_failed(int job_id);
    const char *spellvision_last_job_summary();
}

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent)
{
    setWindowTitle("SpellVision");
    resize(1880, 1060);

    ensureOutputDirs();

    buildMenuBar();
    buildToolBar();
    buildStatusBar();
    buildCentralView();
    buildDocks();
    loadWorkspaceState();

    if (logPanel)
        logPanel->document()->setMaximumBlockCount(5000);
    if (errorPanel)
        errorPanel->document()->setMaximumBlockCount(5000);
    if (queuePanel)
        queuePanel->document()->setMaximumBlockCount(5000);

    outputPathEdit->setText(defaultOutputPath());

    appendLog("SpellVision started.");
    updateBackendStatus(false, "starting");
    ensureWorkerService();
    refreshRustStatus();
    refreshModels();
    refreshHistory();
    refreshGpuInfo();
    updateStatusSummary();

    generationStatusLabel->setText("IDLE");
    generationStatusLabel->setStyleSheet("font-weight: bold; color: #d8d8d8;");
    generationProgressBar->setVisible(false);

    backendPollTimer = new QTimer(this);
    backendPollTimer->setInterval(3000);
    connect(backendPollTimer, &QTimer::timeout, this, &MainWindow::pollBackendHealth);
    backendPollTimer->start();

    QTimer::singleShot(1500, this, [this]()
                       { pollBackendHealth(); });
}

void MainWindow::buildMenuBar()
{
    QMenu *fileMenu = menuBar()->addMenu("&File");
    QMenu *viewMenu = menuBar()->addMenu("&View");
    QMenu *toolsMenu = menuBar()->addMenu("&Tools");
    QMenu *helpMenu = menuBar()->addMenu("&Help");

    actionNewJob = new QAction("Create Dummy Job", this);
    actionGenerateT2I = new QAction("Generate T2I", this);
    actionGenerateI2I = new QAction("Generate I2I", this);
    actionRefreshHistory = new QAction("Refresh History", this);
    actionRefreshModels = new QAction("Refresh Models", this);
    actionRefreshGpu = new QAction("Refresh GPU Info", this);
    actionOpenImage = new QAction("Open Selected Image", this);
    actionOpenFolder = new QAction("Open Image Folder", this);
    actionClearLogs = new QAction("Clear Logs", this);
    actionClearErrors = new QAction("Clear Errors", this);
    actionCopyLogs = new QAction("Copy Logs", this);
    actionExit = new QAction("Exit", this);
    actionAbout = new QAction("About SpellVision", this);

    connect(actionNewJob, &QAction::triggered, this, &MainWindow::createDummyJob);
    connect(actionGenerateT2I, &QAction::triggered, this, &MainWindow::generateTextToImage);
    connect(actionGenerateI2I, &QAction::triggered, this, &MainWindow::generateImageToImage);
    connect(actionRefreshHistory, &QAction::triggered, this, &MainWindow::refreshHistory);
    connect(actionRefreshModels, &QAction::triggered, this, &MainWindow::refreshModels);
    connect(actionRefreshGpu, &QAction::triggered, this, &MainWindow::refreshGpuInfo);
    connect(actionOpenImage, &QAction::triggered, this, &MainWindow::openSelectedImage);
    connect(actionOpenFolder, &QAction::triggered, this, &MainWindow::openSelectedImageFolder);
    connect(actionClearLogs, &QAction::triggered, this, &MainWindow::clearLogs);
    connect(actionClearErrors, &QAction::triggered, this, &MainWindow::clearErrors);
    connect(actionCopyLogs, &QAction::triggered, this, &MainWindow::copyLogs);
    connect(actionExit, &QAction::triggered, this, &QWidget::close);
    connect(actionAbout, &QAction::triggered, this, &MainWindow::showAbout);

    fileMenu->addAction(actionNewJob);
    fileMenu->addAction(actionGenerateT2I);
    fileMenu->addAction(actionGenerateI2I);
    fileMenu->addSeparator();
    fileMenu->addAction(actionOpenImage);
    fileMenu->addAction(actionOpenFolder);
    fileMenu->addSeparator();
    fileMenu->addAction(actionExit);

    toolsMenu->addAction(actionRefreshModels);
    toolsMenu->addAction(actionRefreshHistory);
    toolsMenu->addAction(actionRefreshGpu);
    toolsMenu->addSeparator();
    toolsMenu->addAction(actionClearLogs);
    toolsMenu->addAction(actionClearErrors);
    toolsMenu->addAction(actionCopyLogs);

    helpMenu->addAction(actionAbout);

    viewMenu->addAction("Reset Layout", [this]()
                        {
        removeDockWidget(modelsDock);
        removeDockWidget(lorasDock);
        removeDockWidget(inspectorDock);
        removeDockWidget(queueDock);
        removeDockWidget(logsDock);
        removeDockWidget(errorsDock);
        removeDockWidget(historyDock);
        removeDockWidget(metadataDock);
        removeDockWidget(gpuDock);

        addDockWidget(Qt::LeftDockWidgetArea, historyDock);
        addDockWidget(Qt::LeftDockWidgetArea, modelsDock);
        addDockWidget(Qt::LeftDockWidgetArea, lorasDock);

        addDockWidget(Qt::RightDockWidgetArea, inspectorDock);
        addDockWidget(Qt::RightDockWidgetArea, metadataDock);
        addDockWidget(Qt::RightDockWidgetArea, gpuDock);

        addDockWidget(Qt::BottomDockWidgetArea, queueDock);
        addDockWidget(Qt::BottomDockWidgetArea, logsDock);
        addDockWidget(Qt::BottomDockWidgetArea, errorsDock);

        tabifyDockWidget(historyDock, modelsDock);
        tabifyDockWidget(modelsDock, lorasDock);
        tabifyDockWidget(inspectorDock, metadataDock);
        tabifyDockWidget(metadataDock, gpuDock);
        tabifyDockWidget(queueDock, logsDock);
        tabifyDockWidget(logsDock, errorsDock);

        historyDock->raise();
        inspectorDock->raise();
        queueDock->raise();

        appendLog("Workspace layout reset."); });
}

void MainWindow::buildToolBar()
{
    QToolBar *toolbar = addToolBar("Main Toolbar");
    toolbar->setObjectName("MainToolbar");
    toolbar->setMovable(false);

    toolbar->addAction(actionNewJob);
    toolbar->addAction(actionGenerateT2I);
    toolbar->addAction(actionGenerateI2I);
    toolbar->addAction(actionRefreshModels);
    toolbar->addAction(actionRefreshHistory);
    toolbar->addAction(actionRefreshGpu);
    toolbar->addAction(actionOpenImage);
    toolbar->addAction(actionOpenFolder);
    toolbar->addSeparator();
    toolbar->addAction(actionClearLogs);
    toolbar->addAction(actionClearErrors);
    toolbar->addAction(actionCopyLogs);
}

void MainWindow::buildStatusBar()
{
    statusBar()->showMessage("Ready");
}

void MainWindow::buildCentralView()
{
    centralPanel = new QWidget(this);
    auto *layout = new QVBoxLayout(centralPanel);

    dashboardTitle = new QLabel("SpellVision — Persistent Worker + T2I / I2I");
    dashboardTitle->setStyleSheet("font-size: 28px; font-weight: bold;");

    rustInfoLabel = new QLabel(QString("Rust Core: %1").arg(QString::fromUtf8(spellvision_version())));
    queueInfoLabel = new QLabel(QString("Queued Jobs: %1").arg(spellvision_queue_count()));

    backendStatusLabel = new QLabel("OFFLINE");
    backendStatusLabel->setStyleSheet("font-weight: bold; color: #ff8080;");

    generationStatusLabel = new QLabel("IDLE");
    generationStatusLabel->setStyleSheet("font-weight: bold; color: #d8d8d8;");

    generationProgressBar = new QProgressBar(this);
    generationProgressBar->setTextVisible(true);
    generationProgressBar->setFormat("Generating...");
    generationProgressBar->setVisible(false);

    auto *statusBox = new QGroupBox("Active Session Status", this);
    auto *statusLayout = new QFormLayout(statusBox);

    activeModelLabel = new QLabel("(none)", statusBox);
    activeLoraLabel = new QLabel("[none]", statusBox);
    perfLabel = new QLabel("Last run: n/a | steps/s: n/a | alloc: n/a | reserved: n/a", statusBox);

    statusLayout->addRow("Backend:", backendStatusLabel);
    statusLayout->addRow("Generation:", generationStatusLabel);
    statusLayout->addRow("Progress:", generationProgressBar);
    statusLayout->addRow("Active Model:", activeModelLabel);
    statusLayout->addRow("Active LoRA:", activeLoraLabel);
    statusLayout->addRow("Performance:", perfLabel);

    auto *quickActionsBox = new QGroupBox("Quick Actions", this);
    auto *quickActionsLayout = new QFormLayout(quickActionsBox);

    jobCountSpin = new QSpinBox(quickActionsBox);
    jobCountSpin->setRange(1, 9999);
    jobCountSpin->setValue(1);

    createJobButton = new QPushButton("Create Dummy Job", quickActionsBox);
    connect(createJobButton, &QPushButton::clicked, this, &MainWindow::createDummyJob);

    autoScrollCheck = new QCheckBox("Auto-scroll logs", quickActionsBox);
    autoScrollCheck->setChecked(true);

    quickActionsLayout->addRow("Jobs to Simulate:", jobCountSpin);
    quickActionsLayout->addRow(createJobButton);
    quickActionsLayout->addRow("", autoScrollCheck);

    auto *previewBox = new QGroupBox("Generated Image Preview", this);
    auto *previewLayout = new QVBoxLayout(previewBox);

    imagePathLabel = new QLabel("No image generated yet.", previewBox);

    auto *previewButtonsWidget = new QWidget(previewBox);
    auto *previewButtonsLayout = new QHBoxLayout(previewButtonsWidget);
    previewButtonsLayout->setContentsMargins(0, 0, 0, 0);

    refreshHistoryButton = new QPushButton("Refresh History", previewButtonsWidget);
    openImageButton = new QPushButton("Open Image", previewButtonsWidget);
    openFolderButton = new QPushButton("Open Folder", previewButtonsWidget);

    connect(refreshHistoryButton, &QPushButton::clicked, this, &MainWindow::refreshHistory);
    connect(openImageButton, &QPushButton::clicked, this, &MainWindow::openSelectedImage);
    connect(openFolderButton, &QPushButton::clicked, this, &MainWindow::openSelectedImageFolder);

    previewButtonsLayout->addWidget(refreshHistoryButton);
    previewButtonsLayout->addWidget(openImageButton);
    previewButtonsLayout->addWidget(openFolderButton);
    previewButtonsLayout->addStretch();

    imageScene = new QGraphicsScene(this);
    imageView = new QGraphicsView(imageScene, previewBox);
    imageView->setMinimumHeight(560);

    previewLayout->addWidget(imagePathLabel);
    previewLayout->addWidget(previewButtonsWidget);
    previewLayout->addWidget(imageView);

    layout->addWidget(dashboardTitle);
    layout->addWidget(rustInfoLabel);
    layout->addWidget(queueInfoLabel);
    layout->addWidget(statusBox);
    layout->addWidget(quickActionsBox);
    layout->addWidget(previewBox);
    layout->addStretch();

    setCentralWidget(centralPanel);
}

void MainWindow::buildInspectorUi()
{
    inspectorWidget = new QWidget(this);
    auto *layout = new QVBoxLayout(inspectorWidget);

    auto *generatorBox = new QGroupBox("Generation Parameters");
    auto *form = new QFormLayout(generatorBox);

    promptEdit = new QLineEdit();
    promptEdit->setText("A futuristic city at sunset, cinematic lighting");

    negativePromptEdit = new QLineEdit();
    negativePromptEdit->setText("blurry, low quality, distorted");

    modelPathEdit = new QLineEdit();
    modelPathEdit->setText("stabilityai/stable-diffusion-xl-base-1.0");

    loraPathEdit = new QLineEdit();
    loraPathEdit->setPlaceholderText("Optional LoRA path");

    loraScaleSpin = new QDoubleSpinBox();
    loraScaleSpin->setRange(0.0, 2.0);
    loraScaleSpin->setSingleStep(0.05);
    loraScaleSpin->setValue(1.0);

    batchCountSpin = new QSpinBox();
    batchCountSpin->setRange(1, 32);
    batchCountSpin->setValue(1);

    randomizeSeedCheck = new QCheckBox("Randomize seed per batch");
    randomizeSeedCheck->setChecked(true);

    widthSpin = new QSpinBox();
    widthSpin->setRange(256, 2048);
    widthSpin->setSingleStep(64);
    widthSpin->setValue(1024);

    heightSpin = new QSpinBox();
    heightSpin->setRange(256, 2048);
    heightSpin->setSingleStep(64);
    heightSpin->setValue(1024);

    stepsSpin = new QSpinBox();
    stepsSpin->setRange(1, 200);
    stepsSpin->setValue(30);

    cfgSpin = new QDoubleSpinBox();
    cfgSpin->setRange(1.0, 30.0);
    cfgSpin->setSingleStep(0.5);
    cfgSpin->setValue(7.5);

    seedSpin = new QSpinBox();
    seedSpin->setRange(0, 2147483647);
    seedSpin->setValue(42);

    inputImagePathEdit = new QLineEdit();
    browseInputImageButton = new QPushButton("Browse...");
    connect(browseInputImageButton, &QPushButton::clicked, this, &MainWindow::browseInputImagePath);

    auto *inputRow = new QWidget();
    auto *inputRowLayout = new QHBoxLayout(inputRow);
    inputRowLayout->setContentsMargins(0, 0, 0, 0);
    inputRowLayout->addWidget(inputImagePathEdit);
    inputRowLayout->addWidget(browseInputImageButton);

    strengthSpin = new QDoubleSpinBox();
    strengthSpin->setRange(0.05, 1.0);
    strengthSpin->setSingleStep(0.05);
    strengthSpin->setValue(0.6);

    outputPathEdit = new QLineEdit();
    browseOutputButton = new QPushButton("Browse...");
    connect(browseOutputButton, &QPushButton::clicked, this, &MainWindow::browseOutputPath);

    auto *outputRow = new QWidget();
    auto *outputRowLayout = new QHBoxLayout(outputRow);
    outputRowLayout->setContentsMargins(0, 0, 0, 0);
    outputRowLayout->addWidget(outputPathEdit);
    outputRowLayout->addWidget(browseOutputButton);

    generateButton = new QPushButton("Generate Text-to-Image");
    connect(generateButton, &QPushButton::clicked, this, &MainWindow::generateTextToImage);

    generateI2IButton = new QPushButton("Generate Image-to-Image");
    connect(generateI2IButton, &QPushButton::clicked, this, &MainWindow::generateImageToImage);

    form->addRow("Prompt", promptEdit);
    form->addRow("Negative Prompt", negativePromptEdit);
    form->addRow("Model / Repo / Checkpoint", modelPathEdit);
    form->addRow("LoRA", loraPathEdit);
    form->addRow("LoRA Scale", loraScaleSpin);
    form->addRow("Batch Count", batchCountSpin);
    form->addRow("", randomizeSeedCheck);
    form->addRow("Width", widthSpin);
    form->addRow("Height", heightSpin);
    form->addRow("Steps", stepsSpin);
    form->addRow("CFG", cfgSpin);
    form->addRow("Seed", seedSpin);
    form->addRow("Input Image (I2I)", inputRow);
    form->addRow("I2I Strength", strengthSpin);
    form->addRow("Output PNG", outputRow);

    layout->addWidget(generatorBox);
    layout->addWidget(generateButton);
    layout->addWidget(generateI2IButton);
    layout->addStretch();
}

void MainWindow::buildDocks()
{
    modelList = new QListWidget(this);
    connect(modelList, &QListWidget::itemClicked, this, &MainWindow::onModelItemClicked);

    loraList = new QListWidget(this);
    connect(loraList, &QListWidget::itemClicked, this, &MainWindow::onLoraItemClicked);

    buildInspectorUi();

    queuePanel = new QTextEdit(this);
    queuePanel->setReadOnly(true);
    queuePanel->setStyleSheet("font-family: Consolas, monospace; font-size: 12px;");

    logPanel = new QTextEdit(this);
    logPanel->setReadOnly(true);
    logPanel->setStyleSheet("font-family: Consolas, monospace; font-size: 12px;");

    errorPanel = new QTextEdit(this);
    errorPanel->setReadOnly(true);
    errorPanel->setStyleSheet("font-family: Consolas, monospace; font-size: 12px; color: #ffb0b0;");

    historyList = new QListWidget(this);
    connect(historyList, &QListWidget::itemClicked, this, &MainWindow::onHistoryItemClicked);

    metadataPanel = new QTextEdit(this);
    metadataPanel->setReadOnly(true);
    metadataPanel->setPlainText("No metadata loaded.");
    metadataPanel->setStyleSheet("font-family: Consolas, monospace; font-size: 12px;");

    gpuPanel = new QTextEdit(this);
    gpuPanel->setReadOnly(true);
    gpuPanel->setPlainText("No GPU info loaded.");
    gpuPanel->setStyleSheet("font-family: Consolas, monospace; font-size: 12px;");

    modelsDock = new QDockWidget("Model Browser", this);
    modelsDock->setObjectName("ModelsDock");
    modelsDock->setWidget(modelList);
    addDockWidget(Qt::LeftDockWidgetArea, modelsDock);

    lorasDock = new QDockWidget("LoRAs", this);
    lorasDock->setObjectName("LorasDock");
    lorasDock->setWidget(loraList);
    addDockWidget(Qt::LeftDockWidgetArea, lorasDock);

    historyDock = new QDockWidget("History", this);
    historyDock->setObjectName("HistoryDock");
    historyDock->setWidget(historyList);
    addDockWidget(Qt::LeftDockWidgetArea, historyDock);

    tabifyDockWidget(historyDock, modelsDock);
    tabifyDockWidget(modelsDock, lorasDock);

    inspectorDock = new QDockWidget("Inspector", this);
    inspectorDock->setObjectName("InspectorDock");
    inspectorDock->setWidget(inspectorWidget);
    addDockWidget(Qt::RightDockWidgetArea, inspectorDock);

    metadataDock = new QDockWidget("Metadata", this);
    metadataDock->setObjectName("MetadataDock");
    metadataDock->setWidget(metadataPanel);
    addDockWidget(Qt::RightDockWidgetArea, metadataDock);

    gpuDock = new QDockWidget("GPU Monitor", this);
    gpuDock->setObjectName("GpuDock");
    gpuDock->setWidget(gpuPanel);
    addDockWidget(Qt::RightDockWidgetArea, gpuDock);

    tabifyDockWidget(inspectorDock, metadataDock);
    tabifyDockWidget(metadataDock, gpuDock);

    queueDock = new QDockWidget("Queue", this);
    queueDock->setObjectName("QueueDock");
    queueDock->setWidget(queuePanel);
    addDockWidget(Qt::BottomDockWidgetArea, queueDock);

    logsDock = new QDockWidget("Logs", this);
    logsDock->setObjectName("LogsDock");
    logsDock->setWidget(logPanel);
    addDockWidget(Qt::BottomDockWidgetArea, logsDock);

    errorsDock = new QDockWidget("Errors", this);
    errorsDock->setObjectName("ErrorsDock");
    errorsDock->setWidget(errorPanel);
    addDockWidget(Qt::BottomDockWidgetArea, errorsDock);

    tabifyDockWidget(queueDock, logsDock);
    tabifyDockWidget(logsDock, errorsDock);

    historyDock->raise();
    inspectorDock->raise();
    queueDock->raise();
}

void MainWindow::createDummyJob()
{
    const int count = jobCountSpin->value();
    for (int i = 0; i < count; ++i)
    {
        spellvision_add_dummy_job();
    }
    refreshRustStatus(true);
    appendQueue(QString("Created %1 dummy job(s).").arg(count));
}

QString MainWindow::projectRoot() const
{
    QDir dir(QCoreApplication::applicationDirPath());
    dir.cdUp();
    dir.cdUp();
    return dir.absolutePath();
}

QString MainWindow::pythonExecutable() const
{
#ifdef Q_OS_WIN
    return QDir(projectRoot()).filePath(".venv/Scripts/python.exe");
#else
    return QDir(projectRoot()).filePath(".venv/bin/python");
#endif
}

QString MainWindow::modelsRoot() const { return QDir(projectRoot()).filePath("models"); }
QString MainWindow::checkpointsRoot() const { return QDir(modelsRoot()).filePath("checkpoints"); }
QString MainWindow::lorasRoot() const { return QDir(modelsRoot()).filePath("loras"); }

QString MainWindow::outputsRoot() const
{
    QString documentsDir = QStandardPaths::writableLocation(QStandardPaths::DocumentsLocation);
    if (documentsDir.isEmpty())
        documentsDir = QDir::currentPath();
    return QDir(documentsDir).filePath("SpellVisionOutputs");
}

QString MainWindow::imagesRoot() const { return QDir(outputsRoot()).filePath("t2i/images"); }
QString MainWindow::metadataRoot() const { return QDir(outputsRoot()).filePath("t2i/metadata"); }

void MainWindow::ensureOutputDirs() const
{
    QDir().mkpath(imagesRoot());
    QDir().mkpath(metadataRoot());
    QDir().mkpath(QDir(projectRoot()).filePath("hf_cache"));
}

QString MainWindow::defaultOutputPath() const { return imagePathForBatchIndex(0); }

QString MainWindow::imagePathForBatchIndex(int batchIndex) const
{
    QString base = QDateTime::currentDateTime().toString("yyyyMMdd_hhmmss");
    QString suffix = batchIndex <= 0 ? "" : QString("_b%1").arg(batchIndex + 1, 2, 10, QChar('0'));
    return QDir(imagesRoot()).filePath(QString("spellvision_t2i_%1%2.png").arg(base, suffix));
}

QString MainWindow::metadataPathForImage(const QString &imagePath) const
{
    QFileInfo info(imagePath);
    return QDir(metadataRoot()).filePath(info.completeBaseName() + ".json");
}

void MainWindow::updateBackendStatus(bool online, const QString &detail)
{
    if (!backendStatusLabel)
        return;

    if (online)
    {
        backendStatusLabel->setText(detail.isEmpty() ? "ONLINE" : QString("ONLINE (%1)").arg(detail));
        backendStatusLabel->setStyleSheet("font-weight: bold; color: #8ff7a7;");
        return;
    }

    const QString lower = detail.toLower();

    if (lower.contains("starting") || lower.contains("checking") || lower.contains("warming"))
    {
        backendStatusLabel->setText(QString("STARTING (%1)").arg(detail));
        backendStatusLabel->setStyleSheet("font-weight: bold; color: #ffd27f;");
        return;
    }

    backendStatusLabel->setText(detail.isEmpty() ? "OFFLINE" : QString("OFFLINE (%1)").arg(detail));
    backendStatusLabel->setStyleSheet("font-weight: bold; color: #ff8080;");
}

bool MainWindow::pingWorkerService()
{
    QJsonObject req{{"command", "ping"}};
    const QString response = sendWorkerRequest(QString::fromUtf8(QJsonDocument(req).toJson(QJsonDocument::Compact)));
    const QJsonDocument doc = QJsonDocument::fromJson(response.toUtf8());
    return doc.isObject() && doc.object().value("ok").toBool() && doc.object().value("pong").toBool();
}

void MainWindow::ensureWorkerService()
{
    if (workerServiceProcess && workerServiceProcess->state() != QProcess::NotRunning)
    {
        updateBackendStatus(false, "checking");

        for (int i = 0; i < 12; ++i)
        {
            if (pingWorkerService())
            {
                updateBackendStatus(true);
                return;
            }
            QThread::msleep(250);
            QCoreApplication::processEvents();
        }

        updateBackendStatus(false, "starting");
        return;
    }

    const QString pythonPath = pythonExecutable();
    if (!QFileInfo::exists(pythonPath))
    {
        appendError(QString("Python venv not found: %1").arg(pythonPath));
        updateBackendStatus(false, "venv missing");
        return;
    }

    if (workerServiceProcess)
    {
        workerServiceProcess->deleteLater();
        workerServiceProcess = nullptr;
    }

    workerServiceProcess = new QProcess(this);
    workerServiceProcess->setProgram(pythonPath);
    workerServiceProcess->setArguments({QDir(projectRoot()).filePath("python/worker_service.py")});
    workerServiceProcess->setWorkingDirectory(projectRoot());

    QProcessEnvironment env = QProcessEnvironment::systemEnvironment();
    const QString cacheRoot = QDir(projectRoot()).filePath("hf_cache");
    env.insert("HF_HOME", cacheRoot);
    env.insert("HUGGINGFACE_HUB_CACHE", cacheRoot);
    workerServiceProcess->setProcessEnvironment(env);

    connect(workerServiceProcess, &QProcess::readyReadStandardOutput, this, [this]()
            {
        const QString text = QString::fromUtf8(workerServiceProcess->readAllStandardOutput());
        const QStringList lines = text.split('\n', Qt::SkipEmptyParts);
        for (const QString& line : lines)
        {
            appendLog(line.trimmed(), "worker");
        } });

    connect(workerServiceProcess, &QProcess::readyReadStandardError, this, [this]()
            {
        const QString text = QString::fromUtf8(workerServiceProcess->readAllStandardError());
        const QStringList lines = text.split('\n', Qt::SkipEmptyParts);
        for (const QString& line : lines)
        {
            appendError(line.trimmed());
        } });

    connect(workerServiceProcess,
            qOverload<int, QProcess::ExitStatus>(&QProcess::finished),
            this,
            [this](int exitCode, QProcess::ExitStatus)
            {
                appendError(QString("Worker service exited with code %1").arg(exitCode));
                updateBackendStatus(false, "stopped");
            });

    updateBackendStatus(false, "starting");
    workerServiceProcess->start();

    if (!workerServiceProcess->waitForStarted(5000))
    {
        appendError("Worker service failed to start.");
        updateBackendStatus(false, "failed start");
        return;
    }

    // Give torch/diffusers time to import and bind the socket.
    bool online = false;
    for (int i = 0; i < 40; ++i)
    {
        if (pingWorkerService())
        {
            online = true;
            break;
        }

        QThread::msleep(500);
        QCoreApplication::processEvents();
    }

    if (online)
    {
        updateBackendStatus(true);
        appendLog("Worker service started.", "success");
    }
    else
    {
        appendLog("Worker service process started. Waiting for backend warmup...", "warn");
        updateBackendStatus(false, "warming up");

        QTimer::singleShot(3000, this, [this]()
                           { pollBackendHealth(); });
        QTimer::singleShot(6000, this, [this]()
                           { pollBackendHealth(); });
        QTimer::singleShot(10000, this, [this]()
                           { pollBackendHealth(); });
    }
}

QString MainWindow::sendWorkerRequest(const QString &jsonPayload)
{
    const QString pythonPath = pythonExecutable();
    QProcess process;
    process.setProgram(pythonPath);
    process.setArguments({QDir(projectRoot()).filePath("python/worker_client.py")});
    process.setWorkingDirectory(projectRoot());

    QProcessEnvironment env = QProcessEnvironment::systemEnvironment();
    const QString cacheRoot = QDir(projectRoot()).filePath("hf_cache");
    env.insert("HF_HOME", cacheRoot);
    env.insert("HUGGINGFACE_HUB_CACHE", cacheRoot);
    process.setProcessEnvironment(env);

    process.start();
    if (!process.waitForStarted(10000))
    {
        return R"({"ok":false,"error":"worker_client failed to start"})";
    }

    process.write(jsonPayload.toUtf8());
    process.closeWriteChannel();
    process.waitForFinished(600000);

    const QString stderrText = QString::fromUtf8(process.readAllStandardError()).trimmed();
    if (!stderrText.isEmpty())
    {
        const QStringList lines = stderrText.split('\n', Qt::SkipEmptyParts);
        for (const QString &line : lines)
        {
            appendError(line.trimmed());
        }
    }

    return QString::fromUtf8(process.readAllStandardOutput()).trimmed();
}

void MainWindow::generateTextToImage()
{
    ensureWorkerService();
    if (!pingWorkerService())
    {
        appendError("Backend is not available for T2I.");
        updateBackendStatus(false, "offline");
        return;
    }

    updateBackendStatus(true);
    setGeneratingState(true, "T2I");

    const QString outputPath = outputPathEdit->text().trimmed();
    const QString metadataPath = metadataPathForImage(outputPath);

    QJsonObject payload;
    payload["command"] = "t2i";
    payload["task_type"] = "t2i";
    payload["prompt"] = promptEdit->text().trimmed();
    payload["negative_prompt"] = negativePromptEdit->text().trimmed();
    payload["model"] = modelPathEdit->text().trimmed();
    payload["lora"] = loraPathEdit->text().trimmed();
    payload["lora_scale"] = loraScaleSpin->value();
    payload["width"] = widthSpin->value();
    payload["height"] = heightSpin->value();
    payload["steps"] = stepsSpin->value();
    payload["cfg"] = cfgSpin->value();
    payload["seed"] = seedSpin->value();
    payload["output"] = outputPath;
    payload["metadata_output"] = metadataPath;

    const QString response = sendWorkerRequest(QString::fromUtf8(QJsonDocument(payload).toJson(QJsonDocument::Compact)));

    QJsonParseError parseError;
    const QJsonDocument doc = QJsonDocument::fromJson(response.toUtf8(), &parseError);
    if (parseError.error != QJsonParseError::NoError || !doc.isObject())
    {
        appendError("Worker returned invalid JSON response.");
        appendError(response);
        setGeneratingState(false, "FAILED");
        return;
    }

    const QJsonObject obj = doc.object();
    if (!obj.value("ok").toBool())
    {
        appendError(obj.value("error").toString("Unknown T2I error"));
        if (obj.contains("traceback"))
        {
            appendError(obj.value("traceback").toString());
        }
        setGeneratingState(false, "FAILED");
        return;
    }

    currentImagePath = obj.value("output").toString(outputPath);
    showGeneratedImage(currentImagePath);
    loadMetadataForImage(currentImagePath);
    refreshHistory();

    lastGenerationTime = QString::number(obj.value("generation_time_sec").toDouble(), 'f', 2);
    lastStepsPerSec = QString::number(obj.value("steps_per_sec").toDouble(), 'f', 2);
    lastCudaAllocated = QString::number(obj.value("cuda_allocated_gb").toDouble(), 'f', 2);
    lastCudaReserved = QString::number(obj.value("cuda_reserved_gb").toDouble(), 'f', 2);
    updateStatusSummary();

    appendQueue(QString("Finished T2I successfully → %1").arg(QFileInfo(currentImagePath).fileName()));
    setGeneratingState(false, "READY");
}

void MainWindow::generateImageToImage()
{
    ensureWorkerService();
    if (!pingWorkerService())
    {
        appendError("Backend is not available for I2I.");
        updateBackendStatus(false, "offline");
        return;
    }

    const QString inputImagePath = inputImagePathEdit->text().trimmed();
    if (inputImagePath.isEmpty() || !QFileInfo::exists(inputImagePath))
    {
        appendError("Input image does not exist for I2I.");
        return;
    }

    updateBackendStatus(true);
    setGeneratingState(true, "I2I");

    const QString outputPath = outputPathEdit->text().trimmed();
    const QString metadataPath = metadataPathForImage(outputPath);

    QJsonObject payload;
    payload["command"] = "i2i";
    payload["task_type"] = "i2i";
    payload["prompt"] = promptEdit->text().trimmed();
    payload["negative_prompt"] = negativePromptEdit->text().trimmed();
    payload["model"] = modelPathEdit->text().trimmed();
    payload["lora"] = loraPathEdit->text().trimmed();
    payload["lora_scale"] = loraScaleSpin->value();
    payload["steps"] = stepsSpin->value();
    payload["cfg"] = cfgSpin->value();
    payload["seed"] = seedSpin->value();
    payload["input_image"] = inputImagePath;
    payload["strength"] = strengthSpin->value();
    payload["output"] = outputPath;
    payload["metadata_output"] = metadataPath;

    const QString response = sendWorkerRequest(QString::fromUtf8(QJsonDocument(payload).toJson(QJsonDocument::Compact)));

    QJsonParseError parseError;
    const QJsonDocument doc = QJsonDocument::fromJson(response.toUtf8(), &parseError);
    if (parseError.error != QJsonParseError::NoError || !doc.isObject())
    {
        appendError("Worker returned invalid JSON response.");
        appendError(response);
        setGeneratingState(false, "FAILED");
        return;
    }

    const QJsonObject obj = doc.object();
    if (!obj.value("ok").toBool())
    {
        appendError(obj.value("error").toString("Unknown I2I error"));
        if (obj.contains("traceback"))
        {
            appendError(obj.value("traceback").toString());
        }
        setGeneratingState(false, "FAILED");
        return;
    }

    currentImagePath = obj.value("output").toString(outputPath);
    showGeneratedImage(currentImagePath);
    loadMetadataForImage(currentImagePath);
    refreshHistory();

    lastGenerationTime = QString::number(obj.value("generation_time_sec").toDouble(), 'f', 2);
    lastStepsPerSec = QString::number(obj.value("steps_per_sec").toDouble(), 'f', 2);
    lastCudaAllocated = QString::number(obj.value("cuda_allocated_gb").toDouble(), 'f', 2);
    lastCudaReserved = QString::number(obj.value("cuda_reserved_gb").toDouble(), 'f', 2);
    updateStatusSummary();

    appendQueue(QString("Finished I2I successfully → %1").arg(QFileInfo(currentImagePath).fileName()));
    setGeneratingState(false, "READY");
}

void MainWindow::browseInputImagePath()
{
    const QString path = QFileDialog::getOpenFileName(this, "Choose Input Image", "", "Images (*.png *.jpg *.jpeg *.webp)");
    if (!path.isEmpty())
    {
        inputImagePathEdit->setText(path);
        appendLog(QString("Selected input image: %1").arg(path), "worker");
    }
}

void MainWindow::browseOutputPath()
{
    const QString path = QFileDialog::getSaveFileName(
        this,
        "Choose Output PNG",
        outputPathEdit->text().isEmpty() ? defaultOutputPath() : outputPathEdit->text(),
        "PNG Image (*.png)");
    if (!path.isEmpty())
    {
        outputPathEdit->setText(path);
        appendLog(QString("Selected output path: %1").arg(path), "worker");
    }
}

void MainWindow::refreshRustStatus(bool logSummary)
{
    rustInfoLabel->setText("Rust Core: " + QString::fromUtf8(spellvision_version()));
    queueInfoLabel->setText(QString("Queued Jobs: %1").arg(spellvision_queue_count()));

    if (logSummary)
    {
        appendQueue(QString("[rust] %1").arg(QString::fromUtf8(spellvision_last_job_summary())));
    }
}

void MainWindow::showGeneratedImage(const QString &imagePath)
{
    imageScene->clear();
    QPixmap pixmap(imagePath);
    if (pixmap.isNull())
    {
        imagePathLabel->setText("Failed to load generated image.");
        return;
    }
    imageScene->addPixmap(pixmap);
    imageView->fitInView(imageScene->itemsBoundingRect(), Qt::KeepAspectRatio);
    imagePathLabel->setText(QString("Latest image: %1").arg(imagePath));
    currentImagePath = imagePath;
    loadMetadataForImage(imagePath);
}

void MainWindow::refreshHistory()
{
    historyList->clear();

    QDir dir(imagesRoot());
    QFileInfoList entries = dir.entryInfoList(QStringList() << "*.png", QDir::Files, QDir::Time);
    for (const QFileInfo &info : entries)
    {
        auto *item = new QListWidgetItem(info.fileName());
        item->setData(Qt::UserRole, info.absoluteFilePath());
        item->setToolTip(info.absoluteFilePath());
        historyList->addItem(item);
    }

    appendLog(QString("History refreshed. Found %1 image(s).").arg(entries.size()));
}

void MainWindow::refreshModels()
{
    modelList->clear();
    loraList->clear();

    QDir ckptDir(checkpointsRoot());
    QStringList filters{"*.safetensors", "*.ckpt", "*.pt", "*.bin"};
    QFileInfoList modelEntries = ckptDir.exists() ? ckptDir.entryInfoList(filters, QDir::Files, QDir::Name) : QFileInfoList();
    for (const QFileInfo &info : modelEntries)
    {
        auto *item = new QListWidgetItem(QString("[ckpt] %1").arg(info.fileName()));
        item->setData(Qt::UserRole, info.absoluteFilePath());
        item->setToolTip(info.absoluteFilePath());
        modelList->addItem(item);
    }
    modelList->addItem("[repo] stabilityai/stable-diffusion-xl-base-1.0");

    QDir loraDir(lorasRoot());
    QFileInfoList loraEntries = loraDir.exists() ? loraDir.entryInfoList(QStringList() << "*.safetensors" << "*.bin", QDir::Files, QDir::Name) : QFileInfoList();
    auto *noneItem = new QListWidgetItem("[none]");
    noneItem->setData(Qt::UserRole, "");
    loraList->addItem(noneItem);
    for (const QFileInfo &info : loraEntries)
    {
        auto *item = new QListWidgetItem(QString("[lora] %1").arg(info.fileName()));
        item->setData(Qt::UserRole, info.absoluteFilePath());
        item->setToolTip(info.absoluteFilePath());
        loraList->addItem(item);
    }

    appendLog(QString("Model scan complete. Found %1 checkpoint(s), %2 LoRA(s).")
                  .arg(modelEntries.size())
                  .arg(loraEntries.size()));
}

void MainWindow::refreshGpuInfo()
{
    const QString pythonPath = pythonExecutable();
    if (!QFileInfo::exists(pythonPath))
    {
        gpuPanel->setPlainText(QString("Python venv not found:\n%1").arg(pythonPath));
        appendError(QString("Python venv not found: %1").arg(pythonPath));
        return;
    }

    QProcess process;
    process.setProgram(pythonPath);
    process.setArguments({QDir(projectRoot()).filePath("python/gpu_info.py")});
    process.setWorkingDirectory(projectRoot());
    process.start();
    process.waitForFinished(10000);

    QString stdoutText = QString::fromUtf8(process.readAllStandardOutput()).trimmed();
    QString stderrText = QString::fromUtf8(process.readAllStandardError()).trimmed();

    if (!stderrText.isEmpty())
    {
        appendError(QString("[gpu stderr] %1").arg(stderrText));
    }

    if (stdoutText.isEmpty())
    {
        gpuPanel->setPlainText("No GPU info returned.");
        appendLog("GPU info refresh returned no data.", "warn");
        return;
    }

    gpuPanel->setPlainText(stdoutText);
    appendLog("GPU info refreshed.");
}

void MainWindow::onHistoryItemClicked(QListWidgetItem *item)
{
    if (!item)
        return;
    const QString imagePath = item->data(Qt::UserRole).toString();
    if (!imagePath.isEmpty())
    {
        showGeneratedImage(imagePath);
        appendLog(QString("Loaded history image: %1").arg(QFileInfo(imagePath).fileName()), "worker");
    }
}

void MainWindow::onModelItemClicked(QListWidgetItem *item)
{
    if (!item)
        return;
    QString value = item->data(Qt::UserRole).toString();
    if (value.isEmpty())
    {
        const QString text = item->text();
        value = text.startsWith("[repo] ") ? text.mid(7) : text;
    }
    modelPathEdit->setText(value);
    activeModelLabel->setText(value);
    updateStatusSummary();
    appendLog(QString("Selected model: %1").arg(value), "worker");
}

void MainWindow::onLoraItemClicked(QListWidgetItem *item)
{
    if (!item)
        return;
    const QString value = item->data(Qt::UserRole).toString();
    loraPathEdit->setText(value);
    activeLoraLabel->setText(value.isEmpty() ? "[none]" : QString("%1 (scale %2)").arg(value).arg(loraScaleSpin->value()));
    updateStatusSummary();
    appendLog(QString("Selected LoRA: %1").arg(value.isEmpty() ? "[none]" : value), "worker");
}

void MainWindow::openSelectedImage()
{
    QString path = currentImagePath;
    if (path.isEmpty() && historyList->currentItem())
    {
        path = historyList->currentItem()->data(Qt::UserRole).toString();
    }

    if (path.isEmpty())
    {
        QMessageBox::information(this, "No Image Selected", "Select or generate an image first.");
        return;
    }

    QDesktopServices::openUrl(QUrl::fromLocalFile(path));
    appendLog(QString("Opened image: %1").arg(path), "worker");
}

void MainWindow::openSelectedImageFolder()
{
    QString path = currentImagePath;
    if (path.isEmpty() && historyList->currentItem())
    {
        path = historyList->currentItem()->data(Qt::UserRole).toString();
    }

    if (path.isEmpty())
    {
        path = imagesRoot();
    }
    else
    {
        path = QFileInfo(path).absolutePath();
    }

    QDesktopServices::openUrl(QUrl::fromLocalFile(path));
    appendLog(QString("Opened folder: %1").arg(path), "worker");
}

void MainWindow::loadMetadataForImage(const QString &imagePath)
{
    const QString metadataPath = metadataPathForImage(imagePath);
    QFile file(metadataPath);
    if (!file.exists())
    {
        metadataPanel->setPlainText(QString("No metadata found for:\n%1").arg(imagePath));
        return;
    }
    if (!file.open(QIODevice::ReadOnly))
    {
        metadataPanel->setPlainText(QString("Failed to open metadata:\n%1").arg(metadataPath));
        return;
    }
    const QByteArray bytes = file.readAll();
    file.close();
    metadataPanel->setPlainText(QString::fromUtf8(bytes));
}

void MainWindow::selectHistoryItemByPath(const QString &imagePath)
{
    for (int i = 0; i < historyList->count(); ++i)
    {
        QListWidgetItem *item = historyList->item(i);
        if (item && item->data(Qt::UserRole).toString() == imagePath)
        {
            historyList->setCurrentItem(item);
            break;
        }
    }
}

void MainWindow::updatePerfFromJson(const QString &jsonText)
{
    const QJsonDocument doc = QJsonDocument::fromJson(jsonText.toUtf8());
    if (!doc.isObject())
        return;

    const QJsonObject o = doc.object();
    if (!o.value("ok").toBool())
        return;

    lastGenerationTime = QString::number(o.value("generation_time_sec").toDouble()) + " s";
    lastStepsPerSec = QString::number(o.value("steps_per_sec").toDouble());
    lastCudaAllocated = QString::number(o.value("cuda_allocated_gb").toDouble()) + " GB";
    lastCudaReserved = QString::number(o.value("cuda_reserved_gb").toDouble()) + " GB";
    updateStatusSummary();

    appendLog(QString("cache_hit=%1").arg(o.value("cache_hit").toBool() ? "true" : "false"), "worker");
    appendLog(QString("generation_time_sec=%1").arg(o.value("generation_time_sec").toDouble()), "success");
    appendLog(QString("steps_per_sec=%1").arg(o.value("steps_per_sec").toDouble()), "success");
    appendLog(QString("cuda_allocated_gb=%1").arg(o.value("cuda_allocated_gb").toDouble()), "success");
    appendLog(QString("cuda_reserved_gb=%1").arg(o.value("cuda_reserved_gb").toDouble()), "success");
}

void MainWindow::updateStatusSummary()
{
    QString perf = "Last run: ";
    perf += lastGenerationTime.isEmpty() ? "n/a" : lastGenerationTime;
    perf += " | steps/s: ";
    perf += lastStepsPerSec.isEmpty() ? "n/a" : lastStepsPerSec;
    perf += " | alloc: ";
    perf += lastCudaAllocated.isEmpty() ? "n/a" : lastCudaAllocated;
    perf += " | reserved: ";
    perf += lastCudaReserved.isEmpty() ? "n/a" : lastCudaReserved;
    perfLabel->setText(perf);
}

void MainWindow::appendLog(const QString &message, const QString &category)
{
    if (!logPanel)
        return;

    const QString timestamp = QDateTime::currentDateTime().toString("yyyy-MM-dd hh:mm:ss");
    QString color = "#d8d8d8";
    if (category == "worker")
        color = "#7ec8ff";
    else if (category == "rust")
        color = "#d6a8ff";
    else if (category == "success")
        color = "#8ff7a7";
    else if (category == "warn")
        color = "#ffd27f";

    logPanel->append(QString("<span style='color:%1;'>[%2] %3</span>")
                         .arg(color, timestamp, message.toHtmlEscaped()));

    if (autoScrollCheck && autoScrollCheck->isChecked())
    {
        auto *sb = logPanel->verticalScrollBar();
        sb->setValue(sb->maximum());
    }
}

void MainWindow::appendError(const QString &message)
{
    if (!errorPanel)
        return;

    const QString timestamp = QDateTime::currentDateTime().toString("yyyy-MM-dd hh:mm:ss");
    errorPanel->append(QString("<span style='color:#ff9a9a;'>[%1] %2</span>")
                           .arg(timestamp, message.toHtmlEscaped()));

    if (autoScrollCheck && autoScrollCheck->isChecked())
    {
        auto *sb = errorPanel->verticalScrollBar();
        sb->setValue(sb->maximum());
    }
}

void MainWindow::appendQueue(const QString &message)
{
    if (!queuePanel)
        return;

    const QString timestamp = QDateTime::currentDateTime().toString("yyyy-MM-dd hh:mm:ss");
    queuePanel->append(QString("<span style='color:#c7f0ff;'>[%1] %2</span>")
                           .arg(timestamp, message.toHtmlEscaped()));

    if (autoScrollCheck && autoScrollCheck->isChecked())
    {
        auto *sb = queuePanel->verticalScrollBar();
        sb->setValue(sb->maximum());
    }
}

void MainWindow::clearLogs()
{
    if (logPanel)
        logPanel->clear();
    appendLog("Logs cleared.", "warn");
}

void MainWindow::clearErrors()
{
    if (errorPanel)
        errorPanel->clear();
    appendLog("Errors cleared.", "warn");
}

void MainWindow::copyLogs()
{
    QString combined;
    combined += "=== Queue ===\n" + (queuePanel ? queuePanel->toPlainText() : QString()) + "\n\n";
    combined += "=== Logs ===\n" + (logPanel ? logPanel->toPlainText() : QString()) + "\n\n";
    combined += "=== Errors ===\n" + (errorPanel ? errorPanel->toPlainText() : QString()) + "\n";
    QApplication::clipboard()->setText(combined);
    statusBar()->showMessage("Copied queue/log/error panels to clipboard", 2500);
    appendLog("Copied logs to clipboard.", "worker");
}

void MainWindow::showAbout()
{
    QMessageBox::about(this, "About SpellVision",
                       "SpellVision\n\nPersistent worker backend with T2I and I2I.");
}

void MainWindow::loadWorkspaceState()
{
    QSettings settings("Dark Duck Studio", "SpellVision");
    restoreGeometry(settings.value("mainWindow/geometry").toByteArray());
    restoreState(settings.value("mainWindow/state").toByteArray());
}

void MainWindow::saveWorkspaceState()
{
    QSettings settings("Dark Duck Studio", "SpellVision");
    settings.setValue("mainWindow/geometry", saveGeometry());
    settings.setValue("mainWindow/state", saveState());
}

void MainWindow::closeEvent(QCloseEvent *event)
{
    saveWorkspaceState();
    if (workerServiceProcess && workerServiceProcess->state() != QProcess::NotRunning)
    {
        workerServiceProcess->kill();
        workerServiceProcess->waitForFinished(2000);
    }
    QMainWindow::closeEvent(event);
}

void MainWindow::setGeneratingState(bool generating, const QString &detail)
{
    isGenerating = generating;

    if (generateButton)
        generateButton->setEnabled(!generating);
    if (generateI2IButton)
        generateI2IButton->setEnabled(!generating);
    if (createJobButton)
        createJobButton->setEnabled(!generating);

    if (!generationStatusLabel || !generationProgressBar)
        return;

    if (generating)
    {
        const QString mode = detail.isEmpty() ? "GENERATING" : QString("GENERATING (%1)").arg(detail);
        generationStatusLabel->setText(mode);
        generationStatusLabel->setStyleSheet("font-weight: bold; color: #7ec8ff;");
        generationProgressBar->setRange(0, 0);
        generationProgressBar->setFormat(mode);
        generationProgressBar->setVisible(true);
        statusBar()->showMessage(mode);
    }
    else
    {
        generationStatusLabel->setText(detail.isEmpty() ? "IDLE" : detail);
        generationStatusLabel->setStyleSheet("font-weight: bold; color: #d8d8d8;");
        generationProgressBar->setRange(0, 100);
        generationProgressBar->setValue(0);
        generationProgressBar->setFormat("Ready");
        generationProgressBar->setVisible(false);
        statusBar()->showMessage("Ready");
    }
}

void MainWindow::pollBackendHealth()
{
    if (isGenerating)
    {
        return;
    }

    if (!workerServiceProcess || workerServiceProcess->state() == QProcess::NotRunning)
    {
        updateBackendStatus(false, "stopped");
        return;
    }

    if (pingWorkerService())
    {
        updateBackendStatus(true);
    }
    else
    {
        updateBackendStatus(false, "warming up");
    }
}