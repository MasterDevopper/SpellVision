#include "MainWindow.h"

#include <QAction>
#include <QCloseEvent>
#include <QDateTime>
#include <QDesktopServices>
#include <QDockWidget>
#include <QDoubleSpinBox>
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
#include <QProcess>
#include <QPushButton>
#include <QSettings>
#include <QSpinBox>
#include <QStandardItemModel>
#include <QStatusBar>
#include <QTextEdit>
#include <QToolBar>
#include <QVBoxLayout>
#include <QWidget>
#include <QDir>
#include <QDirIterator>
#include <QStandardPaths>
#include <QPixmap>
#include <QUrl>
#include <algorithm>

extern "C"
{
    const char *spellvision_version();
    int spellvision_queue_count();
    void spellvision_add_dummy_job();
    int spellvision_create_t2i_job(const char *prompt, const char *output_path);
    void spellvision_mark_job_finished(int job_id);
    void spellvision_mark_job_failed(int job_id);
    const char *spellvision_last_job_summary();
}

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent)
{
    setWindowTitle("SpellVision");
    resize(1750, 1000);

    ensureOutputDirs();

    buildMenuBar();
    buildToolBar();
    buildStatusBar();
    buildCentralView();
    buildDocks();
    loadWorkspaceState();

    outputPathEdit->setText(defaultOutputPath());

    logMessage("SpellVision started.");
    refreshRustStatus();
    refreshHistory();
}

void MainWindow::buildMenuBar()
{
    QMenu *fileMenu = menuBar()->addMenu("&File");
    QMenu *viewMenu = menuBar()->addMenu("&View");
    QMenu *toolsMenu = menuBar()->addMenu("&Tools");
    QMenu *helpMenu = menuBar()->addMenu("&Help");

    actionNewJob = new QAction("Create Dummy Job", this);
    actionGenerateT2I = new QAction("Generate T2I", this);
    actionRefreshHistory = new QAction("Refresh History", this);
    actionOpenImage = new QAction("Open Selected Image", this);
    actionOpenFolder = new QAction("Open Image Folder", this);
    actionExit = new QAction("Exit", this);
    actionAbout = new QAction("About SpellVision", this);

    connect(actionNewJob, &QAction::triggered, this, &MainWindow::createDummyJob);
    connect(actionGenerateT2I, &QAction::triggered, this, &MainWindow::generateTextToImage);
    connect(actionRefreshHistory, &QAction::triggered, this, &MainWindow::refreshHistory);
    connect(actionOpenImage, &QAction::triggered, this, &MainWindow::openSelectedImage);
    connect(actionOpenFolder, &QAction::triggered, this, &MainWindow::openSelectedImageFolder);
    connect(actionExit, &QAction::triggered, this, &QWidget::close);
    connect(actionAbout, &QAction::triggered, this, &MainWindow::showAbout);

    fileMenu->addAction(actionNewJob);
    fileMenu->addAction(actionGenerateT2I);
    fileMenu->addSeparator();
    fileMenu->addAction(actionOpenImage);
    fileMenu->addAction(actionOpenFolder);
    fileMenu->addSeparator();
    fileMenu->addAction(actionExit);

    toolsMenu->addAction(actionRefreshHistory);

    helpMenu->addAction(actionAbout);

    viewMenu->addAction("Reset Layout", [this]()
                        {
        removeDockWidget(modelsDock);
        removeDockWidget(inspectorDock);
        removeDockWidget(logsDock);
        removeDockWidget(historyDock);
        removeDockWidget(metadataDock);

        addDockWidget(Qt::LeftDockWidgetArea, modelsDock);
        addDockWidget(Qt::LeftDockWidgetArea, historyDock);
        addDockWidget(Qt::RightDockWidgetArea, inspectorDock);
        addDockWidget(Qt::RightDockWidgetArea, metadataDock);
        addDockWidget(Qt::BottomDockWidgetArea, logsDock);

        modelsDock->show();
        historyDock->show();
        inspectorDock->show();
        metadataDock->show();
        logsDock->show();

        logMessage("Workspace layout reset."); });

    toolsMenu->addAction("Refresh Rust Status", [this]()
                         {
        refreshRustStatus(true);
        logMessage("Refreshed Rust core status."); });
}

void MainWindow::buildToolBar()
{
    QToolBar *toolbar = addToolBar("Main Toolbar");
    toolbar->setObjectName("MainToolbar");
    toolbar->setMovable(false);
    toolbar->setMovable(false);
    toolbar->addAction(actionNewJob);
    toolbar->addAction(actionGenerateT2I);
    toolbar->addAction(actionRefreshHistory);
    toolbar->addAction(actionOpenImage);
    toolbar->addAction(actionOpenFolder);

    QAction *refreshAction = new QAction("Refresh", this);
    connect(refreshAction, &QAction::triggered, this, [this]()
            {
        refreshRustStatus();
        refreshHistory();
        logMessage("UI refreshed."); });

    toolbar->addAction(refreshAction);
}

void MainWindow::buildStatusBar()
{
    statusBar()->showMessage("Ready");
}

void MainWindow::buildCentralView()
{
    centralPanel = new QWidget(this);
    auto *layout = new QVBoxLayout(centralPanel);

    dashboardTitle = new QLabel("SpellVision — Sprint 2 History + Preview");
    dashboardTitle->setStyleSheet("font-size: 26px; font-weight: bold;");

    rustInfoLabel = new QLabel(QString("Rust Core: %1").arg(QString::fromUtf8(spellvision_version())));
    queueInfoLabel = new QLabel(QString("Queued Jobs: %1").arg(spellvision_queue_count()));

    auto *quickActions = new QGroupBox("Quick Actions");
    auto *quickLayout = new QFormLayout(quickActions);

    jobCountSpin = new QSpinBox();
    jobCountSpin->setRange(1, 9999);
    jobCountSpin->setValue(1);

    createJobButton = new QPushButton("Create Dummy Job");
    connect(createJobButton, &QPushButton::clicked, this, &MainWindow::createDummyJob);

    quickLayout->addRow("Jobs to Simulate:", jobCountSpin);
    quickLayout->addRow(createJobButton);

    auto *previewBox = new QGroupBox("Generated Image Preview");
    auto *previewLayout = new QVBoxLayout(previewBox);

    imagePathLabel = new QLabel("No image generated yet.");

    auto *previewButtons = new QWidget();
    auto *previewButtonsLayout = new QHBoxLayout(previewButtons);
    previewButtonsLayout->setContentsMargins(0, 0, 0, 0);

    refreshHistoryButton = new QPushButton("Refresh History");
    openImageButton = new QPushButton("Open Image");
    openFolderButton = new QPushButton("Open Folder");

    connect(refreshHistoryButton, &QPushButton::clicked, this, &MainWindow::refreshHistory);
    connect(openImageButton, &QPushButton::clicked, this, &MainWindow::openSelectedImage);
    connect(openFolderButton, &QPushButton::clicked, this, &MainWindow::openSelectedImageFolder);

    previewButtonsLayout->addWidget(refreshHistoryButton);
    previewButtonsLayout->addWidget(openImageButton);
    previewButtonsLayout->addWidget(openFolderButton);
    previewButtonsLayout->addStretch();

    imageScene = new QGraphicsScene(this);
    imageView = new QGraphicsView(imageScene, this);
    imageView->setMinimumHeight(540);

    previewLayout->addWidget(imagePathLabel);
    previewLayout->addWidget(previewButtons);
    previewLayout->addWidget(imageView);

    layout->addWidget(dashboardTitle);
    layout->addWidget(rustInfoLabel);
    layout->addWidget(queueInfoLabel);
    layout->addWidget(quickActions);
    layout->addWidget(previewBox);
    layout->addStretch();

    setCentralWidget(centralPanel);
}

void MainWindow::buildInspectorUi()
{
    inspectorWidget = new QWidget(this);
    auto *layout = new QVBoxLayout(inspectorWidget);

    auto *generatorBox = new QGroupBox("Text-to-Image Parameters");
    auto *form = new QFormLayout(generatorBox);

    promptEdit = new QLineEdit();
    promptEdit->setText("A futuristic city at sunset, cinematic lighting");

    negativePromptEdit = new QLineEdit();
    negativePromptEdit->setText("blurry, low quality, distorted");

    modelPathEdit = new QLineEdit();
    modelPathEdit->setText("stub-model");

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

    form->addRow("Prompt", promptEdit);
    form->addRow("Negative Prompt", negativePromptEdit);
    form->addRow("Model", modelPathEdit);
    form->addRow("Width", widthSpin);
    form->addRow("Height", heightSpin);
    form->addRow("Steps", stepsSpin);
    form->addRow("CFG", cfgSpin);
    form->addRow("Seed", seedSpin);
    form->addRow("Output PNG", outputRow);

    layout->addWidget(generatorBox);
    layout->addWidget(generateButton);
    layout->addStretch();
}

void MainWindow::buildDocks()
{
    modelList = new QListWidget(this);
    modelList->addItem("stub-model");
    modelList->addItem("future-sdxl-placeholder");
    modelList->addItem("flux-placeholder");
    modelList->addItem("wan-video-placeholder");
    modelList->addItem("trellis2-placeholder");

    buildInspectorUi();

    logPanel = new QTextEdit(this);
    logPanel->setReadOnly(true);

    historyList = new QListWidget(this);
    connect(historyList, &QListWidget::itemClicked, this, &MainWindow::onHistoryItemClicked);

    metadataPanel = new QTextEdit(this);
    metadataPanel->setReadOnly(true);
    metadataPanel->setPlainText("No metadata loaded.");

    modelsDock = new QDockWidget("Model Browser", this);
    modelsDock->setObjectName("ModelsDock");
    modelsDock->setWidget(modelList);
    addDockWidget(Qt::LeftDockWidgetArea, modelsDock);

    historyDock = new QDockWidget("History", this);
    historyDock->setObjectName("HistoryDock");
    historyDock->setWidget(historyList);
    addDockWidget(Qt::LeftDockWidgetArea, historyDock);
    tabifyDockWidget(modelsDock, historyDock);

    inspectorDock = new QDockWidget("Inspector", this);
    inspectorDock->setObjectName("InspectorDock");
    inspectorDock->setWidget(inspectorWidget);
    addDockWidget(Qt::RightDockWidgetArea, inspectorDock);

    metadataDock = new QDockWidget("Metadata", this);
    metadataDock->setObjectName("MetadataDock");
    metadataDock->setWidget(metadataPanel);
    addDockWidget(Qt::RightDockWidgetArea, metadataDock);
    tabifyDockWidget(inspectorDock, metadataDock);

    logsDock = new QDockWidget("Queue + Logs", this);
    logsDock->setObjectName("LogsDock");
    logsDock->setWidget(logPanel);
    addDockWidget(Qt::BottomDockWidgetArea, logsDock);

    modelsDock->raise();
    inspectorDock->raise();
}

void MainWindow::createDummyJob()
{
    const int count = jobCountSpin->value();
    for (int i = 0; i < count; ++i)
    {
        spellvision_add_dummy_job();
    }

    refreshRustStatus(true);
    statusBar()->showMessage(QString("Created %1 dummy job(s)").arg(count), 3000);
    logMessage(QString("Created %1 dummy job(s).").arg(count));
}

QString MainWindow::pythonExecutable() const
{
#ifdef Q_OS_WIN
    return "python";
#else
    return "python3";
#endif
}

QString MainWindow::outputsRoot() const
{
    QString documentsDir = QStandardPaths::writableLocation(QStandardPaths::DocumentsLocation);
    if (documentsDir.isEmpty())
    {
        documentsDir = QDir::currentPath();
    }
    return QDir(documentsDir).filePath("SpellVisionOutputs");
}

QString MainWindow::imagesRoot() const
{
    return QDir(outputsRoot()).filePath("t2i/images");
}

QString MainWindow::metadataRoot() const
{
    return QDir(outputsRoot()).filePath("t2i/metadata");
}

void MainWindow::ensureOutputDirs() const
{
    QDir().mkpath(imagesRoot());
    QDir().mkpath(metadataRoot());
}

QString MainWindow::defaultOutputPath() const
{
    return QDir(imagesRoot()).filePath(QString("spellvision_t2i_%1.png").arg(QDateTime::currentDateTime().toString("yyyyMMdd_hhmmss")));
}

QString MainWindow::metadataPathForImage(const QString &imagePath) const
{
    QFileInfo info(imagePath);
    return QDir(metadataRoot()).filePath(info.completeBaseName() + ".json");
}

void MainWindow::generateTextToImage()
{
    const QString prompt = promptEdit->text().trimmed();
    const QString negativePrompt = negativePromptEdit->text().trimmed();
    const QString modelPath = modelPathEdit->text().trimmed();
    const QString outputPath = outputPathEdit->text().trimmed();

    if (prompt.isEmpty())
    {
        QMessageBox::warning(this, "Missing Prompt", "Please enter a prompt.");
        return;
    }

    if (outputPath.isEmpty())
    {
        QMessageBox::warning(this, "Missing Output Path", "Please choose an output path.");
        return;
    }

    QFileInfo outputInfo(outputPath);
    QDir().mkpath(outputInfo.absolutePath());

    const QByteArray promptUtf8 = prompt.toUtf8();
    const QByteArray outputUtf8 = outputPath.toUtf8();

    const int jobId = spellvision_create_t2i_job(promptUtf8.constData(), outputUtf8.constData());
    if (jobId < 0)
    {
        QMessageBox::critical(this, "Job Error", "Failed to create T2I job in Rust core.");
        return;
    }

    refreshRustStatus(true);
    logMessage(QString("Created T2I job #%1").arg(jobId));
    statusBar()->showMessage(QString("Running T2I job #%1").arg(jobId), 3000);

    const QString scriptPath = QDir(QDir::currentPath()).filePath("python/t2i_worker.py");

    QStringList args;
    args << scriptPath
         << "--prompt" << prompt
         << "--negative-prompt" << negativePrompt
         << "--model" << modelPath
         << "--width" << QString::number(widthSpin->value())
         << "--height" << QString::number(heightSpin->value())
         << "--steps" << QString::number(stepsSpin->value())
         << "--cfg" << QString::number(cfgSpin->value())
         << "--seed" << QString::number(seedSpin->value())
         << "--output" << outputPath
         << "--metadata-output" << metadataPathForImage(outputPath);

    auto *process = new QProcess(this);
    process->setProgram(pythonExecutable());
    process->setArguments(args);
    process->setWorkingDirectory(QDir::currentPath());

    connect(process, &QProcess::readyReadStandardOutput, this, [this, process]()
            {
        const QString text = QString::fromUtf8(process->readAllStandardOutput()).trimmed();
        if (!text.isEmpty()) {
            const QStringList lines = text.split('\n', Qt::SkipEmptyParts);
            for (const QString& line : lines) {
                logMessage(line.trimmed());
            }
        } });

    connect(process, &QProcess::readyReadStandardError, this, [this, process]()
            {
        const QString text = QString::fromUtf8(process->readAllStandardError()).trimmed();
        if (!text.isEmpty()) {
            const QStringList lines = text.split('\n', Qt::SkipEmptyParts);
            for (const QString& line : lines) {
                logMessage(QString("[worker stderr] %1").arg(line.trimmed()));
            }
        } });

    connect(process, QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished),
            this, [this, process, jobId, outputPath](int exitCode, QProcess::ExitStatus exitStatus)
            {
            if (exitStatus == QProcess::NormalExit && exitCode == 0 && QFileInfo::exists(outputPath)) {
                spellvision_mark_job_finished(jobId);
                refreshRustStatus(true);
                refreshHistory();
                showGeneratedImage(outputPath);
                selectHistoryItemByPath(outputPath);
                logMessage(QString("T2I job #%1 finished successfully.").arg(jobId));
                statusBar()->showMessage("Generation complete", 4000);
                outputPathEdit->setText(defaultOutputPath());
            } else {
                spellvision_mark_job_failed(jobId);
                refreshRustStatus(true);
                logMessage(QString("T2I job #%1 failed.").arg(jobId));
                QMessageBox::critical(this, "Generation Failed",
                    QString("Python worker failed.\nExit code: %1").arg(exitCode));
            }
            process->deleteLater(); });

    process->start();
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
    }
}

void MainWindow::refreshRustStatus(bool logSummary)
{
    const QString version = QString::fromUtf8(spellvision_version());
    const int jobs = spellvision_queue_count();
    rustInfoLabel->setText("Rust Core: " + version);
    queueInfoLabel->setText(QString("Queued Jobs: %1").arg(jobs));

    if (logSummary)
    {
        const QString summary = QString::fromUtf8(spellvision_last_job_summary());
        logMessage(QString("[rust] %1").arg(summary));
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

    logMessage(QString("History refreshed. Found %1 image(s).").arg(entries.size()));
}

void MainWindow::onHistoryItemClicked(QListWidgetItem *item)
{
    if (!item)
    {
        return;
    }

    const QString imagePath = item->data(Qt::UserRole).toString();
    if (!imagePath.isEmpty())
    {
        showGeneratedImage(imagePath);
        statusBar()->showMessage("Loaded history image", 2000);
    }
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

    const QJsonDocument doc = QJsonDocument::fromJson(bytes);
    if (!doc.isObject())
    {
        metadataPanel->setPlainText(QString("Invalid metadata JSON:\n%1").arg(metadataPath));
        return;
    }

    metadataPanel->setPlainText(QString::fromUtf8(
        QJsonDocument(doc.object()).toJson(QJsonDocument::Indented)));
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

void MainWindow::showAbout()
{
    QMessageBox::about(
        this,
        "About SpellVision",
        "SpellVision\n\n"
        "Sprint 2 History + Preview\n"
        "Rust core + Qt 6 Widgets + Python worker\n"
        "Next target: real model backend and richer job browser.");
}

void MainWindow::logMessage(const QString &message)
{
    const QString timestamp = QDateTime::currentDateTime().toString("yyyy-MM-dd hh:mm:ss");
    logPanel->append(QString("[%1] %2").arg(timestamp, message));
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
    QMainWindow::closeEvent(event);
}