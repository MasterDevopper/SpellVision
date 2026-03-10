#include "MainWindow.h"

#include <QAction>
#include <QCloseEvent>
#include <QDateTime>
#include <QDockWidget>
#include <QDoubleSpinBox>
#include <QFileDialog>
#include <QFileInfo>
#include <QFormLayout>
#include <QGraphicsPixmapItem>
#include <QGraphicsScene>
#include <QGraphicsView>
#include <QGroupBox>
#include <QHBoxLayout>
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
#include <QStatusBar>
#include <QTextEdit>
#include <QToolBar>
#include <QVBoxLayout>
#include <QWidget>
#include <QDir>
#include <QStandardPaths>
#include <QPixmap>

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
    resize(1700, 980);

    buildMenuBar();
    buildToolBar();
    buildStatusBar();
    buildCentralView();
    buildDocks();
    loadWorkspaceState();

    outputPathEdit->setText(defaultOutputPath());

    logMessage("SpellVision started.");
    refreshRustStatus();
}

void MainWindow::buildMenuBar()
{
    QMenu *fileMenu = menuBar()->addMenu("&File");
    QMenu *viewMenu = menuBar()->addMenu("&View");
    QMenu *toolsMenu = menuBar()->addMenu("&Tools");
    QMenu *helpMenu = menuBar()->addMenu("&Help");

    actionNewJob = new QAction("Create Dummy Job", this);
    actionGenerateT2I = new QAction("Generate T2I", this);
    actionExit = new QAction("Exit", this);
    actionAbout = new QAction("About SpellVision", this);

    connect(actionNewJob, &QAction::triggered, this, &MainWindow::createDummyJob);
    connect(actionGenerateT2I, &QAction::triggered, this, &MainWindow::generateTextToImage);
    connect(actionExit, &QAction::triggered, this, &QWidget::close);
    connect(actionAbout, &QAction::triggered, this, &MainWindow::showAbout);

    fileMenu->addAction(actionNewJob);
    fileMenu->addAction(actionGenerateT2I);
    fileMenu->addSeparator();
    fileMenu->addAction(actionExit);

    helpMenu->addAction(actionAbout);

    viewMenu->addAction("Reset Layout", [this]()
                        {
        removeDockWidget(modelsDock);
        removeDockWidget(inspectorDock);
        removeDockWidget(logsDock);

        addDockWidget(Qt::LeftDockWidgetArea, modelsDock);
        addDockWidget(Qt::RightDockWidgetArea, inspectorDock);
        addDockWidget(Qt::BottomDockWidgetArea, logsDock);

        modelsDock->show();
        inspectorDock->show();
        logsDock->show();

        logMessage("Workspace layout reset."); });

    toolsMenu->addAction("Refresh Rust Status", [this]()
                         {
        refreshRustStatus();
        logMessage("Refreshed Rust core status."); });
}

void MainWindow::buildToolBar()
{
    QToolBar *toolbar = addToolBar("Main Toolbar");
    toolbar->setMovable(false);
    toolbar->addAction(actionNewJob);
    toolbar->addAction(actionGenerateT2I);

    QAction *refreshAction = new QAction("Refresh", this);
    connect(refreshAction, &QAction::triggered, this, [this]()
            {
        refreshRustStatus();
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

    dashboardTitle = new QLabel("SpellVision — Sprint 1 Text-to-Image");
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
    imageScene = new QGraphicsScene(this);
    imageView = new QGraphicsView(imageScene, this);
    imageView->setMinimumHeight(500);

    previewLayout->addWidget(imagePathLabel);
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

    modelsDock = new QDockWidget("Model Browser", this);
    modelsDock->setWidget(modelList);
    addDockWidget(Qt::LeftDockWidgetArea, modelsDock);

    inspectorDock = new QDockWidget("Inspector", this);
    inspectorDock->setWidget(inspectorWidget);
    addDockWidget(Qt::RightDockWidgetArea, inspectorDock);

    logsDock = new QDockWidget("Queue + Logs", this);
    logsDock->setWidget(logPanel);
    addDockWidget(Qt::BottomDockWidgetArea, logsDock);
}

void MainWindow::createDummyJob()
{
    const int count = jobCountSpin->value();
    for (int i = 0; i < count; ++i)
    {
        spellvision_add_dummy_job();
    }

    refreshRustStatus();
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

QString MainWindow::defaultOutputPath() const
{
    QString picturesDir = QStandardPaths::writableLocation(QStandardPaths::PicturesLocation);
    if (picturesDir.isEmpty())
    {
        picturesDir = QDir::currentPath();
    }

    QDir dir(picturesDir);
    if (!dir.exists("SpellVisionOutputs"))
    {
        dir.mkpath("SpellVisionOutputs");
    }

    return dir.filePath(QString("SpellVisionOutputs/spellvision_t2i_%1.png")
                            .arg(QDateTime::currentDateTime().toString("yyyyMMdd_hhmmss")));
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

    refreshRustStatus();
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
         << "--output" << outputPath;

    auto *process = new QProcess(this);
    process->setProgram(pythonExecutable());
    process->setArguments(args);
    process->setWorkingDirectory(QDir::currentPath());

    connect(process, &QProcess::readyReadStandardOutput, this, [this, process]()
            {
        const QString text = QString::fromUtf8(process->readAllStandardOutput()).trimmed();
        if (!text.isEmpty()) {
            logMessage(text);
        } });

    connect(process, &QProcess::readyReadStandardError, this, [this, process]()
            {
        const QString text = QString::fromUtf8(process->readAllStandardError()).trimmed();
        if (!text.isEmpty()) {
            logMessage(QString("[worker stderr] %1").arg(text));
        } });

    connect(process, QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished),
            this, [this, process, jobId, outputPath](int exitCode, QProcess::ExitStatus exitStatus)
            {
            if (exitStatus == QProcess::NormalExit && exitCode == 0 && QFileInfo::exists(outputPath)) {
                spellvision_mark_job_finished(jobId);
                refreshRustStatus();
                showGeneratedImage(outputPath);
                logMessage(QString("T2I job #%1 finished successfully.").arg(jobId));
                statusBar()->showMessage("Generation complete", 4000);
                outputPathEdit->setText(defaultOutputPath());
            } else {
                spellvision_mark_job_failed(jobId);
                refreshRustStatus();
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

void MainWindow::refreshRustStatus()
{
    const QString version = QString::fromUtf8(spellvision_version());
    const int jobs = spellvision_queue_count();
    rustInfoLabel->setText("Rust Core: " + version);
    queueInfoLabel->setText(QString("Queued Jobs: %1").arg(jobs));

    const QString summary = QString::fromUtf8(spellvision_last_job_summary());
    logMessage(QString("[rust] %1").arg(summary));
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
}

void MainWindow::showAbout()
{
    QMessageBox::about(
        this,
        "About SpellVision",
        "SpellVision\n\n"
        "Sprint 1 Text-to-Image vertical slice\n"
        "Rust core + Qt 6 Widgets + Python worker\n"
        "Next target: real Diffusers backend.");
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