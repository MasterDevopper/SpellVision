#include "MainWindow.h"

#include "CommandPaletteDialog.h"
#include "CustomTitleBar.h"
#include "HomePage.h"
#include "ImageGenerationPage.h"
#include "ModePage.h"
#include "QueueFilterProxyModel.h"
#include "QueueManager.h"
#include "QueueTableModel.h"
#include "SettingsPage.h"
#include "ThemeManager.h"
#include "WorkflowImportDialog.h"
#include "WorkflowLibraryPage.h"
#include "shell/MainWindowTrayController.h"
#include "shell/QueueUiPresenter.h"
#include "shell/BottomTelemetryPresenter.h"
#include "workers/WorkerProcessController.h"
#include "workers/WorkerQueueController.h"
#include "workers/WorkerSubmissionPolicy.h"

#include <QAbstractButton>
#include <QAbstractItemView>
#include <QAction>
#include <QCoreApplication>
#include <QDir>
#include <QEventLoop>
#include <QFileInfo>
#include <QFile>
#include <QItemSelectionModel>
#include <QUuid>
#include <QTimer>
#include <QProcessEnvironment>
#include <QProcess>
#include <QSignalBlocker>
#include <QJsonParseError>
#include <QJsonObject>
#include <QJsonDocument>
#include <QJsonArray>
#include <QColorDialog>
#include <QComboBox>
#include <QDateTime>
#include <QDockWidget>
#include <QFrame>
#include <QGridLayout>
#include <QIcon>
#include <QHeaderView>
#include <QHBoxLayout>
#include <QKeySequence>
#include <QLabel>
#include <QLineEdit>
#include <QPainter>
#include <QPainterPath>
#include <QPen>
#include <QMenu>
#include <QMessageBox>
#include <QProgressBar>
#include <QScrollArea>
#include <QPushButton>
#include <QStatusBar>
#include <QTabWidget>
#include <QTableView>
#include <QTextEdit>
#include <QTime>
#include <QToolButton>
#include <QSplitter>
#include <QVBoxLayout>
#include <QWidget>
#include <algorithm>

#ifdef Q_OS_WIN
#include <windows.h>
#include <windowsx.h>
#endif

namespace
{
    QFrame *createPanelFrame(const QString &objectName, QWidget *parent = nullptr)
    {
        auto *frame = new QFrame(parent);
        frame->setObjectName(objectName);
        frame->setFrameShape(QFrame::NoFrame);
        return frame;
    }

    QToolButton *createRailButton(const QString &text, const QString &toolTip, QWidget *parent = nullptr)
    {
        auto *button = new QToolButton(parent);
        button->setObjectName(QStringLiteral("SideRailButton"));
        button->setText(text);
        button->setToolTip(toolTip);
        button->setCheckable(true);
        button->setAutoRaise(true);
        button->setFixedSize(72, 52);
        button->setToolButtonStyle(Qt::ToolButtonTextOnly);
        button->setCursor(Qt::PointingHandCursor);
        return button;
    }

    QFrame *createDockHeaderFrame(const QString &objectName, QWidget *parent = nullptr)
    {
        auto *frame = createPanelFrame(objectName, parent);
        frame->setFixedHeight(34);
        return frame;
    }

    QString defaultManagedComfyRoot(const QString &projectRoot)
    {
        const QString envPath = QString::fromLocal8Bit(qgetenv("SPELLVISION_COMFY")).trimmed();
        if (!envPath.isEmpty())
            return QDir::fromNativeSeparators(QDir(envPath).absolutePath());

        const QString preferred = QStringLiteral("D:/AI_ASSETS/comfy_runtime/ComfyUI");
        if (QDir(preferred).exists())
            return preferred;

        return QDir::fromNativeSeparators(QDir(projectRoot).filePath(QStringLiteral("runtime/comfy/ComfyUI")));
    }

    QString defaultImportedWorkflowsRoot(const QString &projectRoot)
    {
        return QDir(projectRoot).filePath(QStringLiteral("runtime/imported_workflows"));
    }


    QString queueStateDisplay(QueueItemState state)
    {
        switch (state)
        {
        case QueueItemState::Queued:
            return QStringLiteral("Queued");
        case QueueItemState::Preparing:
            return QStringLiteral("Preparing");
        case QueueItemState::Running:
            return QStringLiteral("Running");
        case QueueItemState::Completed:
            return QStringLiteral("Completed");
        case QueueItemState::Failed:
            return QStringLiteral("Failed");
        case QueueItemState::Cancelled:
            return QStringLiteral("Cancelled");
        case QueueItemState::Skipped:
            return QStringLiteral("Skipped");
        case QueueItemState::Unknown:
        default:
            return QStringLiteral("Unknown");
        }
    }

    QStringList brandIconCandidates()
    {
        QStringList starts = {QCoreApplication::applicationDirPath(), QDir::currentPath()};
        QStringList names = {
            QStringLiteral("icons/SpellVision.jpg"),
            QStringLiteral("icons/SpellVision.jpeg"),
            QStringLiteral("icons/SpellVision.png"),
            QStringLiteral("qt_ui/icons/SpellVision.jpg"),
            QStringLiteral("qt_ui/icons/SpellVision.jpeg"),
            QStringLiteral("qt_ui/icons/SpellVision.png"),
            QStringLiteral("SpellVision.jpg"),
            QStringLiteral("SpellVision.jpeg"),
            QStringLiteral("SpellVision.png")};

        QStringList out;
        for (const QString &start : starts)
        {
            QDir dir(start);
            for (int depth = 0; depth < 7; ++depth)
            {
                for (const QString &name : names)
                    out << dir.filePath(name);
                if (!dir.cdUp())
                    break;
            }
        }
        out.removeDuplicates();
        return out;
    }

    QPixmap loadBrandPixmap()
    {
        for (const QString &path : brandIconCandidates())
        {
            if (!QFileInfo::exists(path))
                continue;
            QPixmap pm(path);
            if (!pm.isNull())
                return pm;
        }
        return {};
    }

    QPixmap roundedBrandPixmap(const QSize &size, int radius)
    {
        const QPixmap source = loadBrandPixmap();
        if (source.isNull())
            return {};

        QPixmap scaled = source.scaled(size, Qt::KeepAspectRatioByExpanding, Qt::SmoothTransformation);
        QPixmap out(size);
        out.fill(Qt::transparent);

        QPainter painter(&out);
        painter.setRenderHint(QPainter::Antialiasing, true);
        QPainterPath clipPath;
        clipPath.addRoundedRect(QRectF(0, 0, size.width(), size.height()), radius, radius);
        painter.setClipPath(clipPath);
        painter.drawPixmap(0, 0, scaled);

        painter.setClipping(false);
        QPen border(QColor(QStringLiteral("#7f93dc")));
        border.setWidthF(1.0);
        painter.setPen(border);
        painter.drawRoundedRect(QRectF(0.5, 0.5, size.width() - 1.0, size.height() - 1.0), radius, radius);
        return out;
    }

    QString summarizePrompt(const QString &prompt)
    {
        const QString compact = prompt.simplified();
        if (compact.isEmpty())
            return QStringLiteral("No prompt summary available.");

        return compact.left(220);
    }

    QJsonObject parseLastJsonObjectFromStdout(const QString &allStdout, QString *errorText = nullptr)
    {
        QString lastJsonLine;
        const QStringList lines = allStdout.split('\n', Qt::SkipEmptyParts);
        for (auto it = lines.crbegin(); it != lines.crend(); ++it)
        {
            const QString candidate = it->trimmed();
            if (candidate.startsWith('{') && candidate.endsWith('}'))
            {
                lastJsonLine = candidate;
                break;
            }
        }

        if (lastJsonLine.isEmpty())
        {
            if (errorText)
                *errorText = QStringLiteral("Worker returned no JSON payload.");
            return {};
        }

        QJsonParseError parseError{};
        const QJsonDocument doc = QJsonDocument::fromJson(lastJsonLine.toUtf8(), &parseError);
        if (parseError.error != QJsonParseError::NoError || !doc.isObject())
        {
            if (errorText)
                *errorText = QStringLiteral("Worker returned invalid JSON: %1").arg(lastJsonLine);
            return {};
        }

        return doc.object();
    }
}

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent)
{
    setObjectName(QStringLiteral("MainWindow"));
    setWindowTitle(QStringLiteral("SpellVision"));
    const QPixmap brandWindowIcon = loadBrandPixmap();
    if (!brandWindowIcon.isNull())
        setWindowIcon(QIcon(brandWindowIcon));
    setWindowFlags(Qt::Window | Qt::FramelessWindowHint | Qt::CustomizeWindowHint | Qt::WindowSystemMenuHint | Qt::WindowMinimizeButtonHint | Qt::WindowMaximizeButtonHint | Qt::WindowCloseButtonHint);
    setDockNestingEnabled(true);

    queueManager_ = new QueueManager(this);
    connect(queueManager_, &QueueManager::queueChanged, this, &MainWindow::onQueueChanged);

    workerQueueController_ = new spellvision::workers::WorkerQueueController(this);
    spellvision::workers::WorkerQueueController::Bindings queueBindings;
    queueBindings.queueManager = queueManager_;
    queueBindings.sendRequest = [this](const QJsonObject &request, QString *stderrText, bool *startedOk) {
        return sendWorkerRequest(request, stderrText, startedOk);
    };
    queueBindings.appendLogLine = [this](const QString &text) {
        appendLogLine(text);
    };
    queueBindings.afterQueueSnapshotApplied = [this]() {
        syncGenerationPreviewsFromQueue();
        syncBottomTelemetry();
    };
    workerQueueController_->bind(queueBindings);
    workerQueueController_->startPolling(1800);

    buildShell();
    buildPages();
    buildPersistentDocks();
    buildBottomTelemetryBar();
    switchToMode(QStringLiteral("home"));
    resize(1760, 1020);
}

void MainWindow::buildShell()
{
    titleBar_ = new CustomTitleBar(this);
    titleBar_->setObjectName(QStringLiteral("CustomTitleBar"));
    titleBar_->setWindowTitleText(QString());
    titleBar_->setContextText(QStringLiteral("Home"));

    connect(titleBar_, &CustomTitleBar::menuRequested, this, &MainWindow::showTitleBarMenu);
    connect(titleBar_, &CustomTitleBar::layoutMenuRequested, this, &MainWindow::showLayoutMenu);
    connect(titleBar_, &CustomTitleBar::commandPaletteRequested, this, &MainWindow::showCommandPalette);
    connect(titleBar_, &CustomTitleBar::primarySidebarToggleRequested, this, &MainWindow::togglePrimarySidebar);
    connect(titleBar_, &CustomTitleBar::bottomPanelToggleRequested, this, &MainWindow::toggleBottomPanels);
    connect(titleBar_, &CustomTitleBar::secondarySidebarToggleRequested, this, &MainWindow::toggleDetailsPanel);
    connect(titleBar_, &CustomTitleBar::minimizeRequested, this, &QWidget::showMinimized);
    connect(titleBar_, &CustomTitleBar::maximizeRestoreRequested, this, [this]()
            {
        isMaximized() ? showNormal() : showMaximized();
        if (titleBar_)
            titleBar_->setMaximized(isMaximized()); });
    connect(titleBar_, &CustomTitleBar::closeRequested, this, &QWidget::close);
    connect(titleBar_, &CustomTitleBar::systemMenuRequested, this, &MainWindow::showSystemMenu);

    setMenuWidget(titleBar_);

    auto *commandPaletteAction = new QAction(this);
    commandPaletteAction->setShortcut(QKeySequence(QStringLiteral("Ctrl+Shift+P")));
    addAction(commandPaletteAction);
    connect(commandPaletteAction, &QAction::triggered, this, &MainWindow::showCommandPalette);

    centralShell_ = new QWidget(this);
    auto *shellLayout = new QHBoxLayout(centralShell_);
    shellLayout->setContentsMargins(0, 0, 0, 0);
    shellLayout->setSpacing(0);

    sideRail_ = createSideRail();
    pageStack_ = new QStackedWidget(centralShell_);
    pageStack_->setObjectName(QStringLiteral("MainPageStack"));

    shellLayout->addWidget(sideRail_, 0);
    shellLayout->addWidget(pageStack_, 1);

    setCentralWidget(centralShell_);

    auto applyTheme = [this]()
    {
        setStyleSheet(ThemeManager::instance().shellStyleSheet());
    };
    applyTheme();
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, applyTheme);
}

QWidget *MainWindow::createSideRail()
{
    auto *rail = new QWidget(this);
    rail->setObjectName(QStringLiteral("SideRail"));
    rail->setFixedWidth(96);

    auto *layout = new QVBoxLayout(rail);
    layout->setContentsMargins(10, 14, 10, 14);
    layout->setSpacing(10);

    auto *badge = new QLabel(QStringLiteral("SV"), rail);
    badge->setObjectName(QStringLiteral("SideRailBadge"));
    badge->setAlignment(Qt::AlignCenter);
    badge->setFixedSize(56, 56);
    const QPixmap railBadge = roundedBrandPixmap(QSize(46, 46), 14);
    if (!railBadge.isNull())
        badge->setPixmap(railBadge);
    layout->addWidget(badge, 0, Qt::AlignHCenter);

    const struct RailButtonSpec
    {
        QString modeId;
        QString text;
        QString toolTip;
    } specs[] = {
        {QStringLiteral("home"), QStringLiteral("Home"), QStringLiteral("Home")},
        {QStringLiteral("t2i"), QStringLiteral("T2I"), QStringLiteral("Text to Image")},
        {QStringLiteral("i2i"), QStringLiteral("I2I"), QStringLiteral("Image to Image")},
        {QStringLiteral("t2v"), QStringLiteral("T2V"), QStringLiteral("Text to Video")},
        {QStringLiteral("i2v"), QStringLiteral("I2V"), QStringLiteral("Image to Video")},
        {QStringLiteral("workflows"), QStringLiteral("Flows"), QStringLiteral("Workflows")},
        {QStringLiteral("history"), QStringLiteral("History"), QStringLiteral("History")},
        {QStringLiteral("inspiration"), QStringLiteral("Inspire"), QStringLiteral("Inspiration")},
        {QStringLiteral("models"), QStringLiteral("Models"), QStringLiteral("Models")},
        {QStringLiteral("settings"), QStringLiteral("Prefs"), QStringLiteral("Settings")}};

    for (const RailButtonSpec &spec : specs)
    {
        auto *button = createRailButton(spec.text, spec.toolTip, rail);
        connect(button, &QToolButton::clicked, this, [this, spec]()
                { switchToMode(spec.modeId); });
        layout->addWidget(button);
        modeButtons_.insert(spec.modeId, button);
    }

    layout->addStretch(1);
    return rail;
}

void MainWindow::buildPages()
{
    homePage_ = new HomePage(this);
    workflowsPage_ = new WorkflowLibraryPage(this);
    workflowsPage_->setProjectRoot(resolveProjectRoot());
    workflowsPage_->setPythonExecutable(resolvePythonExecutable());
    workflowsPage_->setProfilesRoot(defaultImportedWorkflowsRoot(resolveProjectRoot()));
    connect(workflowsPage_, &WorkflowLibraryPage::importWorkflowRequested, this, &MainWindow::openWorkflowImportDialog);
    historyPage_ = new ModePage(
        QStringLiteral("History"),
        QStringLiteral("Review results with a browser on the left and a large preview plus metadata stack on the right."),
        {QStringLiteral("Default to successful outputs, with failed and cancelled entries behind a filter toggle."),
         QStringLiteral("Support grouping by day, session, or no grouping."),
         QStringLiteral("Provide rerun, send to I2I, upscale, and copy-prompt actions from the review stack.")},
        this);
    inspirationPage_ = new ModePage(
        QStringLiteral("Inspiration"),
        QStringLiteral("A moodboard plus prompt recipe system that sends favorites and starters back into Home."),
        {QStringLiteral("Use a top filter bar for fast navigation across local, curated, and future online content."),
         QStringLiteral("Make the prompt immediately editable when an item is selected."),
         QStringLiteral("Support Send to Home Hero, Send to T2I, and Save as Workflow actions.")},
        this);
    modelsPage_ = new ModePage(
        QStringLiteral("Models"),
        QStringLiteral("Keep model management adjacent to downloads and managers without cluttering creation pages."),
        {QStringLiteral("Surface checkpoints, LoRAs, VAEs, and upscalers with compatibility cues."),
         QStringLiteral("Show dependency health and install state in the library rather than scattering it across pages."),
         QStringLiteral("Reserve space for downloads, manager tools, and future multimodal assets.")},
        this);
    settingsPage_ = new SettingsPage(this);

    t2iPage_ = new ImageGenerationPage(ImageGenerationPage::Mode::TextToImage, this);
    i2iPage_ = new ImageGenerationPage(ImageGenerationPage::Mode::ImageToImage, this);
    t2vPage_ = new ImageGenerationPage(ImageGenerationPage::Mode::TextToVideo, this);
    i2vPage_ = new ImageGenerationPage(ImageGenerationPage::Mode::ImageToVideo, this);

    for (QWidget *page : {static_cast<QWidget *>(homePage_),
                          static_cast<QWidget *>(t2iPage_),
                          static_cast<QWidget *>(i2iPage_),
                          static_cast<QWidget *>(t2vPage_),
                          static_cast<QWidget *>(i2vPage_),
                          static_cast<QWidget *>(workflowsPage_),
                          static_cast<QWidget *>(historyPage_),
                          static_cast<QWidget *>(inspirationPage_),
                          static_cast<QWidget *>(modelsPage_),
                          static_cast<QWidget *>(settingsPage_)})
    {
        pageStack_->addWidget(page);
    }

    modePages_.insert(QStringLiteral("home"), homePage_);
    modePages_.insert(QStringLiteral("t2i"), t2iPage_);
    modePages_.insert(QStringLiteral("i2i"), i2iPage_);
    modePages_.insert(QStringLiteral("t2v"), t2vPage_);
    modePages_.insert(QStringLiteral("i2v"), i2vPage_);
    modePages_.insert(QStringLiteral("workflows"), workflowsPage_);
    modePages_.insert(QStringLiteral("history"), historyPage_);
    modePages_.insert(QStringLiteral("inspiration"), inspirationPage_);
    modePages_.insert(QStringLiteral("models"), modelsPage_);
    modePages_.insert(QStringLiteral("settings"), settingsPage_);

    connect(homePage_, &HomePage::modeRequested, this, &MainWindow::switchToMode);
    connect(homePage_, &HomePage::managerRequested, this, &MainWindow::openManager);
    connect(homePage_, &HomePage::launchRequested, this, [this](const QString &modeId,
                                                                const QString &title,
                                                                const QString &subtitle,
                                                                const QString &sourceLabel) {
        handleHomeLaunchRequest(modeId, title, subtitle, sourceLabel);
    });

    connectGenerationPage(t2iPage_, QStringLiteral("t2i"));
    connectGenerationPage(i2iPage_, QStringLiteral("i2i"));
    connectGenerationPage(t2vPage_, QStringLiteral("t2v"));
    connectGenerationPage(i2vPage_, QStringLiteral("i2v"));

    workflowsPage_->refreshProfiles();

    connect(workflowsPage_, &WorkflowLibraryPage::importWorkflowRequested, this, &MainWindow::openWorkflowImportDialog);
    connect(workflowsPage_, &WorkflowLibraryPage::launchWorkflowRequested, this, &MainWindow::launchWorkflowProfile);
    connect(workflowsPage_, &WorkflowLibraryPage::workflowDraftRequested,
            this, &MainWindow::openWorkflowDraft);
}

void MainWindow::buildPersistentDocks()
{
    spellvision::shell::MainWindowTrayController::Bindings trayBindings;
    trayBindings.owner = this;
    trayBindings.createBottomUtilityWidget = [this]() { return createBottomUtilityWidget(); };
    trayBindings.hideNativeDockTitleBar = [this](QDockWidget *dock) { hideNativeDockTitleBar(dock); };
    trayBindings.updateDockChrome = [this]() { updateDockChrome(); };
    trayBindings.queueDock = &queueDock_;
    trayBindings.detailsDock = &detailsDock_;
    trayBindings.logsDock = &logsDock_;

    spellvision::shell::MainWindowTrayController::buildPersistentDocks(trayBindings);
}


void MainWindow::buildBottomTelemetryBar()
{
    spellvision::shell::BottomTelemetryPresenter::BuildBindings bindings;
    bindings.owner = this;
    bindings.statusBar = statusBar();
    bindings.readyLabel = &bottomReadyLabel_;
    bindings.pageLabel = &bottomPageLabel_;
    bindings.runtimeLabel = &bottomRuntimeLabel_;
    bindings.queueLabel = &bottomQueueLabel_;
    bindings.vramLabel = &bottomVramLabel_;
    bindings.modelLabel = &bottomModelLabel_;
    bindings.loraLabel = &bottomLoraLabel_;
    bindings.stateLabel = &bottomStateLabel_;
    bindings.progressBar = &bottomProgressBar_;

    spellvision::shell::BottomTelemetryPresenter::build(bindings);
}


ImageGenerationPage *MainWindow::generationPageForMode(const QString &modeId) const
{
    if (modeId == QStringLiteral("t2i"))
        return t2iPage_;
    if (modeId == QStringLiteral("i2i"))
        return i2iPage_;
    if (modeId == QStringLiteral("t2v"))
        return t2vPage_;
    if (modeId == QStringLiteral("i2v"))
        return i2vPage_;
    return nullptr;
}

void MainWindow::handleHomeLaunchRequest(const QString &modeId,
                                         const QString &title,
                                         const QString &subtitle,
                                         const QString &sourceLabel)
{
    const QString resolvedModeId = modePages_.contains(modeId) ? modeId : QStringLiteral("home");

    if (ImageGenerationPage *page = generationPageForMode(resolvedModeId))
        page->applyHomeStarter(title, subtitle, sourceLabel);

    switchToMode(resolvedModeId);
}

void MainWindow::openWorkflowDraft(const QJsonObject &draft)
{
    QString modeId = draft.value(QStringLiteral("mode_id")).toString().trimmed().toLower();
    const QString mediaType = draft.value(QStringLiteral("media_type")).toString().trimmed().toLower();
    const bool hasInputImage = !draft.value(QStringLiteral("input_image")).toString().trimmed().isEmpty();

    if (modeId.isEmpty() && mediaType == QStringLiteral("image"))
        modeId = hasInputImage ? QStringLiteral("i2i") : QStringLiteral("t2i");
    if (modeId.isEmpty() && mediaType == QStringLiteral("video"))
        modeId = hasInputImage ? QStringLiteral("i2v") : QStringLiteral("t2v");

    if (modeId == QStringLiteral("texttoimage"))
        modeId = QStringLiteral("t2i");
    else if (modeId == QStringLiteral("imagetoimage"))
        modeId = QStringLiteral("i2i");
    else if (modeId == QStringLiteral("texttovideo"))
        modeId = QStringLiteral("t2v");
    else if (modeId == QStringLiteral("imagetovideo"))
        modeId = QStringLiteral("i2v");

    if (!generationPageForMode(modeId) && mediaType == QStringLiteral("video"))
        modeId = hasInputImage ? QStringLiteral("i2v") : QStringLiteral("t2v");
    if (!generationPageForMode(modeId) && mediaType == QStringLiteral("image"))
        modeId = hasInputImage ? QStringLiteral("i2i") : QStringLiteral("t2i");

    ImageGenerationPage *page = generationPageForMode(modeId);
    if (!page)
    {
        QMessageBox::warning(this,
                             QStringLiteral("Workflow Draft"),
                             QStringLiteral("This workflow cannot be opened as an editable draft in the current build."));
        return;
    }

    page->applyWorkflowDraft(draft);
    switchToMode(modeId);

    const QString sourceName = draft.value(QStringLiteral("source_name")).toString().trimmed();
    appendLogLine(QStringLiteral("Workflow draft opened: %1 -> %2")
                      .arg(sourceName.isEmpty() ? QStringLiteral("workflow") : sourceName,
                           modeId.toUpper()));

    if (!page->workflowDraftCanSubmit())
        appendLogLine(QStringLiteral("Draft requires review before submission on %1.")
                          .arg(modeId.toUpper()));
}

void MainWindow::connectGenerationPage(ImageGenerationPage *page, const QString &modeId)
{
    if (!page)
        return;

    connect(page, &ImageGenerationPage::openModelsRequested, this, [this]()
            { switchToMode(QStringLiteral("models")); });
    connect(page, &ImageGenerationPage::openWorkflowsRequested, this, [this]()
            { switchToMode(QStringLiteral("workflows")); });
    connect(page, &ImageGenerationPage::prepForI2IRequested, this, [this](const QString &imagePath) {
        if (!i2iPage_)
            return;

        i2iPage_->useImageAsInput(imagePath);
        switchToMode(QStringLiteral("i2i"));
        appendLogLine(QStringLiteral("Prepared latest image for I2I: %1").arg(imagePath));
    });

    connect(page, &ImageGenerationPage::queueRequested, this, [this, page, modeId](const QJsonObject &payload)
            { submitGenerationRequest(page, modeId, payload, true); });

    connect(page, &ImageGenerationPage::generateRequested, this, [this, page, modeId](const QJsonObject &payload)
            { submitGenerationRequest(page, modeId, payload, false); });
}

void MainWindow::submitGenerationRequest(ImageGenerationPage *page, const QString &modeId, const QJsonObject &payload, bool enqueueOnly)
{
    if (!page)
        return;

    const QString taskCommand = workerTaskCommandForMode(modeId);
    if (taskCommand.isEmpty())
    {
        const QString message = QStringLiteral("%1 backend is not wired to the Python worker yet. Start with T2I or I2I first.")
                                    .arg(pageContextForMode(modeId));
        appendLogLine(message);
        page->setBusy(false, message);
        return;
    }

    const bool videoMode = taskCommand == QStringLiteral("t2v") || taskCommand == QStringLiteral("i2v");
    const QString clientBlockReason = payload.value(QStringLiteral("client_readiness_block")).toString().trimmed();
    const QString submitOrigin = payload.value(QStringLiteral("submit_origin")).toString().trimmed();
    if (!clientBlockReason.isEmpty())
    {
        appendLogLine(QStringLiteral("%1 submit reached MainWindow%2 with page readiness note: %3")
                          .arg(modeId.toUpper(),
                               submitOrigin.isEmpty() ? QString() : QStringLiteral(" from %1").arg(submitOrigin),
                               clientBlockReason));
    }

    const bool hasWorkflowBinding = spellvision::workers::WorkerSubmissionPolicy::hasWorkflowBinding(payload);
    const bool hasNativeVideoStack = videoMode && spellvision::workers::WorkerSubmissionPolicy::hasNativeVideoStackPayload(payload);
    const QString modelValue = spellvision::workers::WorkerSubmissionPolicy::resolvedModelValueFromPayload(payload);

    if (videoMode)
    {
        appendLogLine(spellvision::workers::WorkerSubmissionPolicy::videoSubmitLogLine(
            modeId,
            payload,
            modelValue,
            hasNativeVideoStack,
            hasWorkflowBinding));
    }

    if (modelValue.isEmpty() && !(videoMode && (hasWorkflowBinding || hasNativeVideoStack)))
    {
        const QString message = spellvision::workers::WorkerSubmissionPolicy::missingModelMessage(modeId, videoMode);
        appendLogLine(message);
        page->setBusy(false, message);
        return;
    }

    if ((taskCommand == QStringLiteral("i2i") || taskCommand == QStringLiteral("i2v")) &&
        payload.value(QStringLiteral("input_image")).toString().trimmed().isEmpty())
    {
        appendLogLine(QStringLiteral("%1 request blocked: choose an input image first.").arg(modeId.toUpper()));
        return;
    }

    appendLogLine(spellvision::workers::WorkerSubmissionPolicy::acceptedRequestLogLine(
        modeId,
        videoMode,
        hasWorkflowBinding,
        modelValue));

    page->setBusy(true, enqueueOnly ? QStringLiteral("Queueing request…") : QStringLiteral("Submitting generation…"));

    QString stderrText;
    bool startedOk = false;

    const QJsonObject request = buildWorkerGenerationRequest(modeId, payload);
    const QJsonObject response = sendWorkerRequest(request, &stderrText, &startedOk);

    if (!stderrText.trimmed().isEmpty())
        appendLogLine(stderrText.trimmed());

    page->setBusy(false, QString());

    if (!startedOk)
    {
        appendLogLine(QStringLiteral("Failed to start worker_client.py for %1.").arg(modeId.toUpper()));
        return;
    }

    if (response.isEmpty())
    {
        appendLogLine(QStringLiteral("Worker returned no JSON payload for %1.").arg(modeId.toUpper()));
        return;
    }

    const bool ok = response.value(QStringLiteral("ok")).toBool(false);
    const QString errorText = response.value(QStringLiteral("error")).toString().trimmed();
    if (!ok && !errorText.isEmpty())
    {
        appendLogLine(QStringLiteral("%1 request failed: %2").arg(modeId.toUpper(), errorText));
        return;
    }

    applyWorkerQueueResponse(response);
    syncBottomTelemetry();

    const QString queueId = response.value(QStringLiteral("queue_item_id")).toString().trimmed();
    const QString jobId = response.value(QStringLiteral("job_id")).toString().trimmed();
    appendLogLine(QStringLiteral("%1 sent to worker queue%2%3.")
                      .arg(modeId.toUpper(),
                           queueId.isEmpty() ? QString() : QStringLiteral(" • queue=%1").arg(queueId),
                           jobId.isEmpty() ? QString() : QStringLiteral(" • job=%1").arg(jobId)));

    if (!queueDock_ || !queueDock_->isVisible())
        toggleBottomPanels();
}

QJsonObject MainWindow::sendWorkerRequest(const QJsonObject &request, QString *stderrText, bool *startedOk) const
{
    if (stderrText)
        stderrText->clear();
    if (startedOk)
        *startedOk = false;

    const QString projectRoot = resolveProjectRoot();
    const QString pythonExecutable = resolvePythonExecutable();
    const QString workerClient = QDir(projectRoot).filePath(QStringLiteral("python/worker_client.py"));

    spellvision::workers::WorkerProcessController controller;
    spellvision::workers::WorkerProcessController::CommandRequest command;
    command.program = pythonExecutable;
    command.arguments = {workerClient};
    command.workingDirectory = projectRoot;
    command.environment = QProcessEnvironment::systemEnvironment();
    command.payload = request;
    command.closeWriteChannelAfterPayload = true;

    QJsonObject lastJsonMessage;
    QStringList stderrLines;
    QStringList processErrors;
    bool finished = false;
    bool timedOut = false;
    int exitCode = -1;
    QProcess::ExitStatus exitStatus = QProcess::NormalExit;

    QEventLoop loop;
    QTimer timeoutTimer;
    timeoutTimer.setSingleShot(true);

    connect(&controller, &spellvision::workers::WorkerProcessController::stderrLineReceived,
            &loop, [&stderrLines](const QString &line) {
                if (!line.trimmed().isEmpty())
                    stderrLines << line.trimmed();
            });

    connect(&controller, &spellvision::workers::WorkerProcessController::jsonMessageReceived,
            &loop, [&lastJsonMessage](const QJsonObject &message) {
                if (!message.isEmpty())
                    lastJsonMessage = message;
            });

    connect(&controller, &spellvision::workers::WorkerProcessController::processError,
            &loop, [&processErrors](const QString &message) {
                if (!message.trimmed().isEmpty())
                    processErrors << message.trimmed();
            });

    connect(&controller,
            &spellvision::workers::WorkerProcessController::processFinished,
            &loop,
            [&loop, &finished, &exitCode, &exitStatus](int code, QProcess::ExitStatus status) {
                finished = true;
                exitCode = code;
                exitStatus = status;
                loop.quit();
            });

    connect(&timeoutTimer, &QTimer::timeout, &loop, [&controller, &loop, &timedOut, &processErrors]() {
        timedOut = true;
        processErrors << QStringLiteral("Worker process timed out while waiting for a response.");
        controller.kill();
        loop.quit();
    });

    const bool started = controller.start(command);
    if (startedOk)
        *startedOk = started;

    if (!started)
    {
        if (stderrText)
            *stderrText = processErrors.join(QChar('\n'));
        return {};
    }

    if (controller.isRunning())
    {
        timeoutTimer.start(120000);
        loop.exec();
        timeoutTimer.stop();
    }

    if (stderrText)
    {
        QStringList diagnostics = stderrLines;
        diagnostics.append(processErrors);
        diagnostics.removeAll(QString());
        *stderrText = diagnostics.join(QChar('\n'));
    }

    if (timedOut)
        return lastJsonMessage;

    if (finished && exitStatus != QProcess::NormalExit)
        return lastJsonMessage;

    if (finished && exitCode != 0 && lastJsonMessage.isEmpty())
        return {};

    return lastJsonMessage;
}


QString MainWindow::workerTaskCommandForMode(const QString &modeId) const
{
    if (modeId == QStringLiteral("t2i"))
        return QStringLiteral("t2i");
    if (modeId == QStringLiteral("i2i"))
        return QStringLiteral("i2i");
    if (modeId == QStringLiteral("t2v"))
        return QStringLiteral("t2v");
    if (modeId == QStringLiteral("i2v"))
        return QStringLiteral("i2v");
    return QString();
}

QString MainWindow::resolveProjectRoot() const
{
    const QStringList starts = {QCoreApplication::applicationDirPath(), QDir::currentPath()};
    for (const QString &start : starts)
    {
        QDir dir(start);
        for (int depth = 0; depth < 7; ++depth)
        {
            if (QFileInfo::exists(dir.filePath(QStringLiteral("python/worker_client.py"))))
                return dir.absolutePath();
            if (!dir.cdUp())
                break;
        }
    }
    return QDir::currentPath();
}

QString MainWindow::resolvePythonExecutable() const
{
    const QString virtualEnv = QString::fromLocal8Bit(qgetenv("VIRTUAL_ENV")).trimmed();
    if (!virtualEnv.isEmpty())
    {
        const QString fromEnv = QDir(virtualEnv).filePath(QStringLiteral("Scripts/python.exe"));
        if (QFileInfo::exists(fromEnv))
            return fromEnv;
    }

    const QString projectVenv = QDir(resolveProjectRoot()).filePath(QStringLiteral(".venv/Scripts/python.exe"));
    if (QFileInfo::exists(projectVenv))
        return projectVenv;

    return QStringLiteral("python");
}

QJsonObject MainWindow::buildWorkerGenerationRequest(const QString &modeId, const QJsonObject &payload) const
{
    const QString taskCommand = workerTaskCommandForMode(modeId);

    QString outputFolder = payload.value(QStringLiteral("output_folder")).toString().trimmed();
    if (outputFolder.isEmpty())
        outputFolder = QDir(resolveProjectRoot()).filePath(QStringLiteral("output"));

    QDir().mkpath(outputFolder);

    const QString basePrefix = payload.value(QStringLiteral("output_prefix")).toString().trimmed().isEmpty()
                                   ? QStringLiteral("spellvision_render")
                                   : payload.value(QStringLiteral("output_prefix")).toString().trimmed();
    const QString stamp = QDateTime::currentDateTimeUtc().toString(QStringLiteral("yyyyMMdd_HHmmss_zzz"));
    const QString baseName = QStringLiteral("%1_%2_%3").arg(basePrefix, taskCommand, stamp);
    const bool videoOutput = taskCommand == QStringLiteral("t2v") || taskCommand == QStringLiteral("i2v");
    const QString outputPath = QDir(outputFolder).filePath(baseName + (videoOutput ? QStringLiteral(".mp4") : QStringLiteral(".png")));
    const QString metadataPath = QDir(outputFolder).filePath(baseName + QStringLiteral(".json"));

    QJsonObject request;
    request.insert(QStringLiteral("command"), QStringLiteral("enqueue"));
    request.insert(QStringLiteral("task_command"), taskCommand);
    request.insert(QStringLiteral("task_type"), taskCommand);
    request.insert(QStringLiteral("submit_origin"), payload.value(QStringLiteral("submit_origin")).toString());
    request.insert(QStringLiteral("client_readiness_block"), payload.value(QStringLiteral("client_readiness_block")).toString());
    request.insert(QStringLiteral("prompt"), payload.value(QStringLiteral("prompt")).toString());
    request.insert(QStringLiteral("negative_prompt"), payload.value(QStringLiteral("negative_prompt")).toString());
    const QString resolvedModelValue = spellvision::workers::WorkerSubmissionPolicy::resolvedModelValueFromPayload(payload);
    request.insert(QStringLiteral("model"), resolvedModelValue);
    request.insert(QStringLiteral("model_display"), payload.value(QStringLiteral("model_display")).toString());
    request.insert(QStringLiteral("model_family"), payload.value(QStringLiteral("model_family")).toString());
    request.insert(QStringLiteral("model_modality"), payload.value(QStringLiteral("model_modality")).toString());
    request.insert(QStringLiteral("model_role"), payload.value(QStringLiteral("model_role")).toString());
    if (payload.value(QStringLiteral("video_model_stack")).isObject())
        request.insert(QStringLiteral("video_model_stack"), payload.value(QStringLiteral("video_model_stack")).toObject());
    if (payload.value(QStringLiteral("model_stack")).isObject())
        request.insert(QStringLiteral("model_stack"), payload.value(QStringLiteral("model_stack")).toObject());
    if (!payload.value(QStringLiteral("native_video_stack_kind")).toString().trimmed().isEmpty())
        request.insert(QStringLiteral("native_video_stack_kind"), payload.value(QStringLiteral("native_video_stack_kind")).toString());
    request.insert(QStringLiteral("steps"), payload.value(QStringLiteral("steps")).toInt(28));
    request.insert(QStringLiteral("cfg"), payload.value(QStringLiteral("cfg")).toDouble(payload.value(QStringLiteral("cfg_scale")).toDouble(7.0)));
    request.insert(QStringLiteral("seed"), static_cast<qint64>(payload.value(QStringLiteral("seed")).toVariant().toLongLong()));
    request.insert(QStringLiteral("width"), payload.value(QStringLiteral("width")).toInt(1024));
    request.insert(QStringLiteral("height"), payload.value(QStringLiteral("height")).toInt(1024));
    request.insert(QStringLiteral("sampler"), payload.value(QStringLiteral("sampler")).toString());
    request.insert(QStringLiteral("scheduler"), payload.value(QStringLiteral("scheduler")).toString());
    const QString requestProfilePath = QDir::fromNativeSeparators(payload.value(QStringLiteral("workflow_profile_path")).toString());
    const QString requestWorkflowPath = QDir::fromNativeSeparators(payload.value(QStringLiteral("workflow_path")).toString());
    const QString requestCompiledPromptPath = QDir::fromNativeSeparators(payload.value(QStringLiteral("compiled_prompt_path")).toString());
    const bool hasWorkflowBinding = !requestProfilePath.trimmed().isEmpty() ||
                                    !requestWorkflowPath.trimmed().isEmpty() ||
                                    !requestCompiledPromptPath.trimmed().isEmpty();

    request.insert(QStringLiteral("workflow_profile"), payload.value(QStringLiteral("workflow_profile")).toString());
    request.insert(QStringLiteral("workflow_profile_name"), payload.value(QStringLiteral("workflow_draft_source")).toString());
    request.insert(QStringLiteral("profile_path"), requestProfilePath);
    request.insert(QStringLiteral("workflow_path"), requestWorkflowPath);
    request.insert(QStringLiteral("compiled_prompt_path"), requestCompiledPromptPath);
    request.insert(QStringLiteral("workflow_backend"), payload.value(QStringLiteral("workflow_backend")).toString());
    request.insert(QStringLiteral("workflow_media_type"), payload.value(QStringLiteral("workflow_media_type")).toString());
    if (videoOutput && !hasWorkflowBinding)
    {
        request.insert(QStringLiteral("backend_kind"), QStringLiteral("native_video"));
        request.insert(QStringLiteral("runtime"), QStringLiteral("diffusers_video"));
    }
    request.insert(QStringLiteral("output"), QDir::fromNativeSeparators(outputPath));
    request.insert(QStringLiteral("metadata_output"), QDir::fromNativeSeparators(metadataPath));
    request.insert(QStringLiteral("original_output"), QDir::fromNativeSeparators(outputPath));
    request.insert(QStringLiteral("original_metadata_output"), QDir::fromNativeSeparators(metadataPath));

    const QString loraValue = payload.value(QStringLiteral("lora_summary")).toString().trimmed();
    if (!loraValue.isEmpty() && loraValue.compare(QStringLiteral("none"), Qt::CaseInsensitive) != 0)
        request.insert(QStringLiteral("lora"), loraValue);

    if (taskCommand == QStringLiteral("i2i") || taskCommand == QStringLiteral("i2v"))
    {
        request.insert(QStringLiteral("input_image"), payload.value(QStringLiteral("input_image")).toString());
        request.insert(QStringLiteral("strength"), payload.value(QStringLiteral("strength")).toDouble(0.45));
    }

    if (videoOutput)
    {
        request.insert(QStringLiteral("frames"), payload.value(QStringLiteral("frames")).toInt(payload.value(QStringLiteral("num_frames")).toInt(81)));
        request.insert(QStringLiteral("num_frames"), payload.value(QStringLiteral("num_frames")).toInt(payload.value(QStringLiteral("frames")).toInt(81)));
        request.insert(QStringLiteral("fps"), payload.value(QStringLiteral("fps")).toInt(16));
        request.insert(QStringLiteral("duration_seconds"), payload.value(QStringLiteral("duration_seconds")).toDouble(0.0));
        request.insert(QStringLiteral("media_type"), QStringLiteral("video"));
    }

    return request;
}

QJsonObject MainWindow::buildWorkflowLaunchRequest(const QJsonObject &profile) const
{
    auto firstNonEmpty = [](const QString &a, const QString &b, const QString &fallback = QString())
    {
        const QString aTrimmed = a.trimmed();
        if (!aTrimmed.isEmpty())
            return aTrimmed;
        const QString bTrimmed = b.trimmed();
        if (!bTrimmed.isEmpty())
            return bTrimmed;
        return fallback.trimmed();
    };

    auto slugify = [](QString value)
    {
        value = value.trimmed().toLower();
        QString out;
        bool dashPending = false;

        for (const QChar ch : value)
        {
            if (ch.isLetterOrNumber())
            {
                out.append(ch);
                dashPending = false;
            }
            else if (!out.isEmpty() && !dashPending)
            {
                out.append(QLatin1Char('-'));
                dashPending = true;
            }
        }

        while (out.endsWith(QLatin1Char('-')))
            out.chop(1);

        if (out.isEmpty())
            out = QStringLiteral("workflow");

        return out.left(72);
    };

    const QString projectRoot = resolveProjectRoot();
    const QString profileName = firstNonEmpty(profile.value(QStringLiteral("profile_name")).toString(),
                                              profile.value(QStringLiteral("name")).toString(),
                                              QStringLiteral("Imported Workflow"));
    const QString importSlug = slugify(firstNonEmpty(profile.value(QStringLiteral("import_slug")).toString(), profileName));
    const QString workflowTaskCommand = firstNonEmpty(profile.value(QStringLiteral("task_command")).toString(),
                                                      QStringLiteral("unknown"));
    const QString workflowMediaType = profile.value(QStringLiteral("media_type")).toString().trimmed();
    const QString backendKind = firstNonEmpty(profile.value(QStringLiteral("backend_kind")).toString(),
                                              QStringLiteral("comfy_workflow"));

    const QString profilePath = profile.value(QStringLiteral("profile_path")).toString().trimmed();
    const QString workflowPath = firstNonEmpty(profile.value(QStringLiteral("workflow_path")).toString(),
                                               profile.value(QStringLiteral("workflow_source")).toString());

    QString comfyRoot = QString::fromLocal8Bit(qgetenv("SPELLVISION_COMFY")).trimmed();
    if (comfyRoot.isEmpty())
    {
        const QString preferred = QStringLiteral("D:/AI_ASSETS/comfy_runtime/ComfyUI");
        comfyRoot = QDir(preferred).exists()
                        ? preferred
                        : QDir(projectRoot).filePath(QStringLiteral("runtime/comfy/ComfyUI"));
    }

    const QString outputRoot = QDir(projectRoot).filePath(QStringLiteral("output/workflows/%1").arg(workflowTaskCommand));
    QDir().mkpath(outputRoot);

    const QString stamp = QDateTime::currentDateTimeUtc().toString(QStringLiteral("yyyyMMdd_HHmmss_zzz"));
    const QString baseName = QStringLiteral("%1_%2").arg(importSlug, stamp);
    const bool workflowVideoOutput = workflowMediaType == QStringLiteral("video") ||
                                     workflowTaskCommand == QStringLiteral("t2v") ||
                                     workflowTaskCommand == QStringLiteral("i2v");
    const QString outputPath = QDir(outputRoot).filePath(baseName + (workflowVideoOutput ? QStringLiteral(".mp4") : QStringLiteral(".png")));
    const QString metadataPath = QDir(outputRoot).filePath(baseName + QStringLiteral(".json"));

    QJsonObject request;
    request.insert(QStringLiteral("command"), QStringLiteral("enqueue"));
    request.insert(QStringLiteral("task_command"), QStringLiteral("comfy_workflow"));
    request.insert(QStringLiteral("task_type"), workflowTaskCommand);
    request.insert(QStringLiteral("backend_kind"), backendKind);
    request.insert(QStringLiteral("workflow_profile_name"), profileName);
    request.insert(QStringLiteral("workflow_task_command"), workflowTaskCommand);
    if (!workflowMediaType.isEmpty())
        request.insert(QStringLiteral("workflow_media_type"), workflowMediaType);
    if (!profilePath.isEmpty())
        request.insert(QStringLiteral("profile_path"), QDir::fromNativeSeparators(profilePath));
    if (!workflowPath.isEmpty())
        request.insert(QStringLiteral("workflow_path"), QDir::fromNativeSeparators(workflowPath));
    if (!comfyRoot.isEmpty())
        request.insert(QStringLiteral("comfy_root"), QDir::fromNativeSeparators(comfyRoot));

    request.insert(QStringLiteral("output"), QDir::fromNativeSeparators(outputPath));
    request.insert(QStringLiteral("metadata_output"), QDir::fromNativeSeparators(metadataPath));
    request.insert(QStringLiteral("original_output"), QDir::fromNativeSeparators(outputPath));
    request.insert(QStringLiteral("original_metadata_output"), QDir::fromNativeSeparators(metadataPath));

    return request;
}

void MainWindow::launchWorkflowProfile(const QJsonObject &profile)
{
    const QString profileName = profile.value(QStringLiteral("profile_name")).toString().trimmed().isEmpty()
                                    ? profile.value(QStringLiteral("name")).toString().trimmed()
                                    : profile.value(QStringLiteral("profile_name")).toString().trimmed();

    const QString profilePath = profile.value(QStringLiteral("profile_path")).toString().trimmed();
    const QString workflowPath = profile.value(QStringLiteral("workflow_path")).toString().trimmed().isEmpty()
                                     ? profile.value(QStringLiteral("workflow_source")).toString().trimmed()
                                     : profile.value(QStringLiteral("workflow_path")).toString().trimmed();

    if (profilePath.isEmpty() && workflowPath.isEmpty())
    {
        QMessageBox::warning(
            this,
            QStringLiteral("Workflow Launch"),
            QStringLiteral("The selected workflow does not have a usable profile path or workflow path."));
        return;
    }

    const int missingCustomNodeCount = profile.value(QStringLiteral("metadata")).toObject().value(QStringLiteral("missing_custom_nodes")).toArray().size();

    QString stderrText;
    bool startedOk = false;
    const QJsonObject request = buildWorkflowLaunchRequest(profile);
    const QJsonObject response = sendWorkerRequest(request, &stderrText, &startedOk);

    if (!stderrText.trimmed().isEmpty())
        appendLogLine(stderrText.trimmed());

    if (!startedOk)
    {
        QMessageBox::warning(
            this,
            QStringLiteral("Workflow Launch"),
            QStringLiteral("Failed to start worker_client.py for workflow launch."));
        return;
    }

    if (response.isEmpty())
    {
        QMessageBox::warning(
            this,
            QStringLiteral("Workflow Launch"),
            QStringLiteral("Worker returned no JSON payload for workflow launch."));
        return;
    }

    const bool ok = response.value(QStringLiteral("ok")).toBool(false);
    const QString errorText = response.value(QStringLiteral("error")).toString().trimmed();
    if (!ok && !errorText.isEmpty())
    {
        QMessageBox::warning(
            this,
            QStringLiteral("Workflow Launch"),
            QStringLiteral("Workflow launch failed: %1").arg(errorText));
        return;
    }

    applyWorkerQueueResponse(response);
    pollWorkerQueueStatus();

    const QString queueId = response.value(QStringLiteral("queue_item_id")).toString().trimmed();
    const QString jobId = response.value(QStringLiteral("job_id")).toString().trimmed();

    appendLogLine(QStringLiteral("Workflow queued: %1%2%3%4")
                      .arg(profileName.isEmpty() ? QStringLiteral("Imported Workflow") : profileName,
                           queueId.isEmpty() ? QString() : QStringLiteral(" • queue=%1").arg(queueId),
                           jobId.isEmpty() ? QString() : QStringLiteral(" • job=%1").arg(jobId),
                           missingCustomNodeCount > 0 ? QStringLiteral(" • review dependency warnings") : QString()));

    if (queueDock_)
    {
        queueDock_->show();
        queueDock_->raise();
    }
}

void MainWindow::applyWorkerQueueResponse(const QJsonObject &response)
{
    if (workerQueueController_)
        workerQueueController_->applyWorkerQueueResponse(response);
}


void MainWindow::pollWorkerQueueStatus()
{
    if (workerQueueController_)
        workerQueueController_->pollOnce();
}


void MainWindow::syncGenerationPreviewsFromQueue()
{
    if (!queueManager_)
        return;

    QString latestT2iOutput;
    QString latestI2iOutput;
    QString latestT2vOutput;
    QString latestI2vOutput;

    const QVector<QueueItem> &items = queueManager_->items();
    for (const QueueItem &item : items)
    {
        if (latestT2iOutput.isEmpty() && item.command.compare(QStringLiteral("t2i"), Qt::CaseInsensitive) == 0 && !item.outputPath.trimmed().isEmpty())
            latestT2iOutput = item.outputPath.trimmed();

        if (latestI2iOutput.isEmpty() && item.command.compare(QStringLiteral("i2i"), Qt::CaseInsensitive) == 0 && !item.outputPath.trimmed().isEmpty())
            latestI2iOutput = item.outputPath.trimmed();

        if (latestT2vOutput.isEmpty() && item.command.compare(QStringLiteral("t2v"), Qt::CaseInsensitive) == 0 && !item.outputPath.trimmed().isEmpty())
            latestT2vOutput = item.outputPath.trimmed();

        if (latestI2vOutput.isEmpty() && item.command.compare(QStringLiteral("i2v"), Qt::CaseInsensitive) == 0 && !item.outputPath.trimmed().isEmpty())
            latestI2vOutput = item.outputPath.trimmed();
    }

    if (t2iPage_ && !latestT2iOutput.isEmpty())
        t2iPage_->setPreviewImage(latestT2iOutput);

    if (i2iPage_ && !latestI2iOutput.isEmpty())
        i2iPage_->setPreviewImage(latestI2iOutput);

    if (t2vPage_ && !latestT2vOutput.isEmpty())
        t2vPage_->setPreviewImage(latestT2vOutput, QStringLiteral("Video output ready."));

    if (i2vPage_ && !latestI2vOutput.isEmpty())
        i2vPage_->setPreviewImage(latestI2vOutput, QStringLiteral("Video output ready."));
}

void MainWindow::appendLogLine(const QString &text)
{
    if (!logsView_)
        return;

    const QString timestamp = QTime::currentTime().toString(QStringLiteral("HH:mm:ss"));
    logsView_->append(QStringLiteral("[%1] %2").arg(timestamp, text));
}

QWidget *MainWindow::createBottomUtilityWidget()
{
    auto *root = new QWidget(this);
    root->setObjectName(QStringLiteral("BottomUtilityRoot"));
    auto *layout = new QVBoxLayout(root);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(0);

    bottomUtilityHeaderBar_ = createDockHeaderFrame(QStringLiteral("QueueDockHeader"), root);
    auto *headerLayout = new QHBoxLayout(bottomUtilityHeaderBar_);
    headerLayout->setContentsMargins(8, 4, 8, 4);
    headerLayout->setSpacing(6);

    auto makeHeaderButton = [this](const QString &text)
    {
        auto *button = new QToolButton(bottomUtilityHeaderBar_);
        button->setObjectName(QStringLiteral("SecondaryActionButton"));
        button->setText(text);
        button->setCheckable(true);
        button->setAutoRaise(false);
        button->setCursor(Qt::PointingHandCursor);
        button->setToolButtonStyle(Qt::ToolButtonTextOnly);
        button->setMinimumHeight(26);
        return button;
    };

    bottomQueueButton_ = makeHeaderButton(QStringLiteral("Queue"));
    bottomDetailsButton_ = makeHeaderButton(QStringLiteral("Details"));
    bottomLogsButton_ = makeHeaderButton(QStringLiteral("Logs"));

    queueDockStateLabel_ = new QLabel(QStringLiteral("Idle"), bottomUtilityHeaderBar_);
    queueDockStateLabel_->setObjectName(QStringLiteral("DetailsMetaValue"));
    queueDockStateLabel_->setMinimumWidth(34);
    queueDockStateLabel_->setAlignment(Qt::AlignRight | Qt::AlignVCenter);

    queueExpandButton_ = new QToolButton(bottomUtilityHeaderBar_);
    queueExpandButton_->setObjectName(QStringLiteral("SecondaryActionButton"));
    queueExpandButton_->setText(QStringLiteral("Expand"));
    queueExpandButton_->setCheckable(true);
    queueExpandButton_->setChecked(false);
    queueExpandButton_->setAutoRaise(false);
    queueExpandButton_->setCursor(Qt::PointingHandCursor);
    queueExpandButton_->setToolButtonStyle(Qt::ToolButtonTextOnly);
    queueExpandButton_->setMinimumHeight(26);

    headerLayout->addWidget(bottomQueueButton_);
    headerLayout->addWidget(bottomDetailsButton_);
    headerLayout->addWidget(bottomLogsButton_);
    headerLayout->addStretch(1);
    headerLayout->addWidget(queueDockStateLabel_);
    headerLayout->addWidget(queueExpandButton_);
    layout->addWidget(bottomUtilityHeaderBar_);

    queueExpandedContent_ = new QWidget(root);
    auto *expandedLayout = new QHBoxLayout(queueExpandedContent_);
    expandedLayout->setContentsMargins(8, 4, 8, 8);
    expandedLayout->setSpacing(8);

    bottomUtilitySplitter_ = new QSplitter(Qt::Horizontal, queueExpandedContent_);
    bottomUtilitySplitter_->setObjectName(QStringLiteral("BottomUtilitySplitter"));

    auto *queuePane = createQueueWidget();
    queuePane->setParent(bottomUtilitySplitter_);
    bottomUtilitySplitter_->addWidget(queuePane);

    bottomUtilityTabs_ = new QTabWidget(bottomUtilitySplitter_);
    bottomUtilityTabs_->setObjectName(QStringLiteral("BottomUtilityTabs"));
    bottomUtilityTabs_->addTab(createDetailsWidget(), QStringLiteral("Details"));
    bottomUtilityTabs_->addTab(createLogsWidget(), QStringLiteral("Logs"));
    bottomUtilitySplitter_->addWidget(bottomUtilityTabs_);
    bottomUtilitySplitter_->setStretchFactor(0, 4);
    bottomUtilitySplitter_->setStretchFactor(1, 2);

    expandedLayout->addWidget(bottomUtilitySplitter_, 1);
    layout->addWidget(queueExpandedContent_, 1);

    connect(queueExpandButton_, &QToolButton::toggled, this, [this](bool checked)
    {
        queueDockUserExpanded_ = checked;
        bottomUtilityUserExpanded_ = checked;
        if (!checked)
            detailsDockPinnedOpen_ = false;
        applyQueueDockChrome();
        applyBottomUtilityTrayChrome();
    });

    connect(bottomQueueButton_, &QToolButton::clicked, this, [this]()
    {
        detailsDockPinnedOpen_ = false;
        queueDockUserExpanded_ = true;
        bottomUtilityUserExpanded_ = true;
        if (queueDock_)
            queueDock_->show();
        if (bottomUtilityTabs_ && bottomUtilityTabs_->currentIndex() < 0)
            bottomUtilityTabs_->setCurrentIndex(0);
        updateDockChrome();
    });

    connect(bottomDetailsButton_, &QToolButton::clicked, this, [this]()
    {
        detailsDockPinnedOpen_ = true;
        queueDockUserExpanded_ = true;
        bottomUtilityUserExpanded_ = true;
        if (queueDock_)
            queueDock_->show();
        if (bottomUtilityTabs_)
            bottomUtilityTabs_->setCurrentIndex(0);
        updateDockChrome();
    });

    connect(bottomLogsButton_, &QToolButton::clicked, this, [this]()
    {
        detailsDockPinnedOpen_ = false;
        queueDockUserExpanded_ = true;
        bottomUtilityUserExpanded_ = true;
        if (queueDock_)
            queueDock_->show();
        if (bottomUtilityTabs_)
            bottomUtilityTabs_->setCurrentIndex(1);
        updateDockChrome();
    });

    applyQueueDockChrome();
    return root;
}

void MainWindow::hideNativeDockTitleBar(QDockWidget *dock)
{
    if (!dock)
        return;

    auto *emptyTitleBar = new QWidget(dock);
    emptyTitleBar->setFixedHeight(0);
    dock->setTitleBarWidget(emptyTitleBar);
}

bool MainWindow::hasActiveQueueWork() const
{
    if (!queueManager_)
        return false;

    const QVector<QueueItem> &items = queueManager_->items();
    for (const QueueItem &item : items)
    {
        if (item.state == QueueItemState::Running ||
            item.state == QueueItemState::Queued ||
            item.state == QueueItemState::Preparing)
        {
            return true;
        }
    }

    return false;
}

bool MainWindow::isCompactShellWidth() const
{
    return width() < 1580 || (!isMaximized() && width() < 1720);
}

bool MainWindow::isGenerationWorkspaceMode() const
{
    return currentModeId_ == QStringLiteral("t2i") ||
           currentModeId_ == QStringLiteral("i2i") ||
           currentModeId_ == QStringLiteral("t2v") ||
           currentModeId_ == QStringLiteral("i2v");
}

int MainWindow::preferredBottomUtilityExpandedHeight(bool compact) const
{
    const int windowHeight = qMax(height(), 720);
    int target = isGenerationWorkspaceMode() ? static_cast<int>(windowHeight * 0.40)
                                             : static_cast<int>(windowHeight * 0.30);

    if (bottomUtilityTabs_ && bottomUtilityTabs_->currentIndex() == 0)
        target += 28;

    const int minHeight = compact ? 322 : 316;
    const int maxHeight = compact ? 468 : 520;
    return qBound(minHeight, target, maxHeight);
}

void MainWindow::applyQueueDockChrome()
{
    if (!queueDock_)
        return;

    const bool active = hasActiveQueueWork();
    const bool showExpanded = active || queueDockUserExpanded_ || bottomUtilityUserExpanded_ || detailsDockPinnedOpen_;

    if (queueExpandedContent_)
        queueExpandedContent_->setVisible(showExpanded);

    if (queueExpandButton_)
    {
        const QSignalBlocker blocker(queueExpandButton_);
        queueExpandButton_->setChecked(showExpanded);
        queueExpandButton_->setText(showExpanded ? QStringLiteral("Collapse") : QStringLiteral("Expand"));
    }

    if (queueDockStateLabel_)
        queueDockStateLabel_->setText(active ? QStringLiteral("Live") : QStringLiteral("Idle"));

    if (bottomUtilityTabs_)
    {
        if (detailsDockPinnedOpen_)
            bottomUtilityTabs_->setCurrentIndex(0);

        const int currentIndex = bottomUtilityTabs_->currentIndex();

        if (bottomQueueButton_)
        {
            const QSignalBlocker blocker(bottomQueueButton_);
            bottomQueueButton_->setChecked(showExpanded);
        }

        if (bottomDetailsButton_)
        {
            const QSignalBlocker blocker(bottomDetailsButton_);
            bottomDetailsButton_->setChecked(showExpanded && currentIndex == 0);
        }

        if (bottomLogsButton_)
        {
            const QSignalBlocker blocker(bottomLogsButton_);
            bottomLogsButton_->setChecked(showExpanded && currentIndex == 1);
        }
    }

    if (!showExpanded)
    {
        detailsDockPinnedOpen_ = false;
        if (bottomQueueButton_)
        {
            const QSignalBlocker blocker(bottomQueueButton_);
            bottomQueueButton_->setChecked(false);
        }
        if (bottomDetailsButton_)
        {
            const QSignalBlocker blocker(bottomDetailsButton_);
            bottomDetailsButton_->setChecked(false);
        }
        if (bottomLogsButton_)
        {
            const QSignalBlocker blocker(bottomLogsButton_);
            bottomLogsButton_->setChecked(false);
        }
    }
}

void MainWindow::applyBottomUtilityTrayChrome()
{
    if (!queueDock_)
        return;

    const bool active = hasActiveQueueWork();
    const bool expanded = active || queueDockUserExpanded_ || bottomUtilityUserExpanded_ || detailsDockPinnedOpen_;
    const bool compact = isCompactShellWidth();

    int collapsedHeight = isGenerationWorkspaceMode() ? (compact ? 58 : 56) : (compact ? 52 : 50);
    if (bottomUtilityHeaderBar_)
        collapsedHeight = qMax(collapsedHeight, bottomUtilityHeaderBar_->sizeHint().height() + 10);

    const int expandedHeight = preferredBottomUtilityExpandedHeight(compact);
    const int trayHeight = expanded ? expandedHeight : collapsedHeight;

    queueDock_->setMinimumHeight(trayHeight);
    queueDock_->setMaximumHeight(trayHeight);

    if (bottomUtilitySplitter_)
    {
        const int totalWidth = qMax(bottomUtilitySplitter_->width(), width() - 120);
        const bool active = hasActiveQueueWork();
        int detailsWidth = compact ? 560 : 680;
        if (!active && bottomUtilityTabs_ && bottomUtilityTabs_->currentIndex() == 0)
            detailsWidth = compact ? 640 : 780;
        if (bottomUtilityTabs_ && bottomUtilityTabs_->currentIndex() == 1)
            detailsWidth = compact ? 520 : 580;
        detailsWidth = qBound(460, detailsWidth, qMax(520, totalWidth / 2));
        const int queueWidth = qMax(active ? 560 : 500, totalWidth - detailsWidth);
        bottomUtilitySplitter_->setSizes({queueWidth, detailsWidth});
    }
}

void MainWindow::updateDockChrome()
{
    applyQueueDockChrome();
    applyBottomUtilityTrayChrome();
}

QWidget *MainWindow::createQueueWidget()
{
    auto *root = new QWidget(this);
    root->setObjectName(QStringLiteral("QueuePaneRoot"));
    auto *layout = new QVBoxLayout(root);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(10);

    auto *activeStrip = createPanelFrame(QStringLiteral("QueueActiveStrip"), root);
    auto *activeLayout = new QVBoxLayout(activeStrip);
    activeLayout->setContentsMargins(8, 6, 8, 6);
    activeLayout->setSpacing(3);

    auto *eyebrow = new QLabel(QStringLiteral("ACTIVE QUEUE"), activeStrip);
    eyebrow->setObjectName(QStringLiteral("QueueActiveEyebrow"));
    activeQueueTitleLabel_ = new QLabel(QStringLiteral("No active work"), activeStrip);
    activeQueueTitleLabel_->setObjectName(QStringLiteral("QueueActiveTitle"));
    activeQueueSummaryLabel_ = new QLabel(QStringLiteral("Recent jobs will appear here when the queue is idle."), activeStrip);
    activeQueueSummaryLabel_->setObjectName(QStringLiteral("QueueActiveBody"));
    activeQueueSummaryLabel_->setWordWrap(true);

    activeLayout->addWidget(eyebrow);
    activeLayout->addWidget(activeQueueTitleLabel_);
    activeLayout->addWidget(activeQueueSummaryLabel_);

    layout->addWidget(activeStrip);

    queueSearchEdit_ = new QLineEdit(root);
    queueSearchEdit_->setPlaceholderText(QStringLiteral("Search queue by prompt, model, or state"));

    queueStateFilter_ = new QComboBox(root);
    queueStateFilter_->addItems({QStringLiteral("All States"),
                                 QStringLiteral("Queued"),
                                 QStringLiteral("Running"),
                                 QStringLiteral("Completed"),
                                 QStringLiteral("Failed")});

    auto *filtersLayout = new QHBoxLayout;
    filtersLayout->setContentsMargins(0, 0, 0, 0);
    filtersLayout->setSpacing(6);
    filtersLayout->addWidget(queueSearchEdit_, 1);
    filtersLayout->addWidget(queueStateFilter_);
    layout->addLayout(filtersLayout);

    queueTableModel_ = new QueueTableModel(queueManager_, this);
    queueFilterProxyModel_ = new QueueFilterProxyModel(this);
    queueFilterProxyModel_->setSourceModel(queueTableModel_);

    queueTableView_ = new QTableView(root);
    queueTableView_->setModel(queueFilterProxyModel_);
    queueTableView_->setSelectionBehavior(QAbstractItemView::SelectRows);
    queueTableView_->setSelectionMode(QAbstractItemView::SingleSelection);
    queueTableView_->setAlternatingRowColors(true);
    queueTableView_->setSortingEnabled(false);
    queueTableView_->verticalHeader()->setVisible(false);
    queueTableView_->horizontalHeader()->setStretchLastSection(true);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::StateColumn, QHeaderView::ResizeToContents);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::CommandColumn, QHeaderView::ResizeToContents);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::PromptColumn, QHeaderView::Stretch);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::ProgressColumn, QHeaderView::ResizeToContents);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::StatusColumn, QHeaderView::ResizeToContents);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::QueueIdColumn, QHeaderView::ResizeToContents);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::UpdatedAtColumn, QHeaderView::ResizeToContents);

    layout->addWidget(queueTableView_, 1);

    connect(queueSearchEdit_, &QLineEdit::textChanged, this, [this](const QString &text)
            {
        if (queueFilterProxyModel_)
            queueFilterProxyModel_->setTextFilter(text); });

    connect(queueStateFilter_, &QComboBox::currentTextChanged, this, [this](const QString &text)
            {
        if (queueFilterProxyModel_)
            queueFilterProxyModel_->setStateFilter(text); });

    connect(queueTableView_->selectionModel(), &QItemSelectionModel::selectionChanged, this, [this]()
            { updateDetailsPanelForQueueSelection(); });

    return root;
}

QWidget *MainWindow::createDetailsWidget()
{
    auto *root = new QWidget(this);
    auto *layout = new QVBoxLayout(root);
    layout->setContentsMargins(12, 12, 12, 12);
    layout->setSpacing(12);

    auto *summaryCard = createPanelFrame(QStringLiteral("DetailsSummaryCard"), root);
    auto *summaryLayout = new QVBoxLayout(summaryCard);
    summaryLayout->setContentsMargins(12, 12, 12, 12);
    summaryLayout->setSpacing(8);

    auto *eyebrow = new QLabel(QStringLiteral("CONTEXT"), summaryCard);
    eyebrow->setObjectName(QStringLiteral("DetailsEyebrow"));

    detailsTitleLabel_ = new QLabel(QStringLiteral("Workspace"), summaryCard);
    detailsTitleLabel_->setObjectName(QStringLiteral("DetailsTitle"));

    detailsBodyLabel_ = new QLabel(QStringLiteral("Use the side rail to move between creation, workflows, and review."), summaryCard);
    detailsBodyLabel_->setObjectName(QStringLiteral("DetailsBody"));
    detailsBodyLabel_->setWordWrap(true);

    summaryLayout->addWidget(eyebrow);
    summaryLayout->addWidget(detailsTitleLabel_);
    summaryLayout->addWidget(detailsBodyLabel_);

    auto *metaGrid = new QGridLayout;
    metaGrid->setHorizontalSpacing(8);
    metaGrid->setVerticalSpacing(8);

    auto makeMetaRow = [&](int row, const QString &labelText, QLabel **valueLabel)
    {
        auto *label = new QLabel(labelText, summaryCard);
        label->setObjectName(QStringLiteral("DetailsMetaLabel"));
        auto *value = new QLabel(QStringLiteral("—"), summaryCard);
        value->setObjectName(QStringLiteral("DetailsMetaValue"));
        value->setWordWrap(true);
        metaGrid->addWidget(label, row, 0);
        metaGrid->addWidget(value, row, 1);
        *valueLabel = value;
    };

    makeMetaRow(0, QStringLiteral("Context"), &detailsContextValueLabel_);
    makeMetaRow(1, QStringLiteral("Selection"), &detailsSelectionValueLabel_);
    makeMetaRow(2, QStringLiteral("Queue"), &detailsQueueValueLabel_);
    makeMetaRow(3, QStringLiteral("Status"), &detailsStatusValueLabel_);

    summaryLayout->addLayout(metaGrid);
    layout->addWidget(summaryCard);

    auto *actionCard = createPanelFrame(QStringLiteral("DetailsActionCard"), root);
    auto *actionLayout = new QVBoxLayout(actionCard);
    actionLayout->setContentsMargins(12, 12, 12, 12);
    actionLayout->setSpacing(8);

    detailsPrimaryActionButton_ = new QPushButton(QStringLiteral("Primary Action"), actionCard);
    detailsPrimaryActionButton_->setObjectName(QStringLiteral("DetailsPrimaryActionButton"));
    detailsSecondaryActionButton_ = new QPushButton(QStringLiteral("Secondary Action"), actionCard);
    detailsSecondaryActionButton_->setObjectName(QStringLiteral("DetailsSecondaryActionButton"));
    detailsTertiaryActionButton_ = new QPushButton(QStringLiteral("Tertiary Action"), actionCard);
    detailsTertiaryActionButton_->setObjectName(QStringLiteral("DetailsActionButton"));

    actionLayout->addWidget(detailsPrimaryActionButton_);
    actionLayout->addWidget(detailsSecondaryActionButton_);
    actionLayout->addWidget(detailsTertiaryActionButton_);

    layout->addWidget(actionCard);
    layout->addStretch(1);

    connect(detailsPrimaryActionButton_, &QPushButton::clicked, this, [this]()
            { triggerDetailsAction(detailsPrimaryActionId_); });
    connect(detailsSecondaryActionButton_, &QPushButton::clicked, this, [this]()
            { triggerDetailsAction(detailsSecondaryActionId_); });
    connect(detailsTertiaryActionButton_, &QPushButton::clicked, this, [this]()
            { triggerDetailsAction(detailsTertiaryActionId_); });

    updateDetailsPanelForModeContext();
    return root;
}

QWidget *MainWindow::createLogsWidget()
{
    auto *root = new QWidget(this);
    auto *layout = new QVBoxLayout(root);
    layout->setContentsMargins(12, 12, 12, 12);
    layout->setSpacing(10);

    auto *card = createPanelFrame(QStringLiteral("ExecutionLogCard"), root);
    auto *cardLayout = new QVBoxLayout(card);
    cardLayout->setContentsMargins(12, 12, 12, 12);
    cardLayout->setSpacing(8);

    auto *title = new QLabel(QStringLiteral("Execution Log"), card);
    title->setObjectName(QStringLiteral("DetailsTitle"));
    logsView_ = new QTextEdit(card);
    logsView_->setObjectName(QStringLiteral("LogsView"));
    logsView_->setReadOnly(true);

    cardLayout->addWidget(title);
    cardLayout->addWidget(logsView_, 1);

    layout->addWidget(card, 1);
    return root;
}

void MainWindow::showTitleBarMenu(const QString &menuId, const QPoint &globalPos)
{
    QMenu menu(this);

    if (menuId == QStringLiteral("file"))
    {
        auto *importWorkflowAction = menu.addAction(QStringLiteral("Import Workflow..."));
        connect(importWorkflowAction, &QAction::triggered, this, &MainWindow::openWorkflowImportDialog);

        menu.addSeparator();

        auto *quitAction = menu.addAction(QStringLiteral("Quit"));
        connect(quitAction, &QAction::triggered, this, &QWidget::close);
    }
    else if (menuId == QStringLiteral("workflows"))
    {
        auto *importWorkflowAction = menu.addAction(QStringLiteral("Import Workflow..."));
        connect(importWorkflowAction, &QAction::triggered, this, &MainWindow::openWorkflowImportDialog);
    }
    else
    {
        menu.addAction(QStringLiteral("No actions"));
    }

    menu.exec(globalPos);
}

void MainWindow::showLayoutMenu(const QPoint &globalPos)
{
    QMenu menu(this);

    auto *toggleQueue = menu.addAction(QStringLiteral("Toggle Bottom Utility"));
    connect(toggleQueue, &QAction::triggered, this, &MainWindow::toggleBottomPanels);

    auto *toggleDetails = menu.addAction(QStringLiteral("Show Details Tray"));
    connect(toggleDetails, &QAction::triggered, this, &MainWindow::toggleDetailsPanel);

    menu.exec(globalPos);
}

void MainWindow::showSystemMenu(const QPoint &globalPos)
{
    QMenu menu(this);

    auto *minimizeAction = menu.addAction(QStringLiteral("Minimize"));
    connect(minimizeAction, &QAction::triggered, this, &QWidget::showMinimized);

    auto *maximizeAction = menu.addAction(isMaximized() ? QStringLiteral("Restore") : QStringLiteral("Maximize"));
    connect(maximizeAction, &QAction::triggered, this, [this]()
            { isMaximized() ? showNormal() : showMaximized(); });

    menu.addSeparator();

    auto *closeAction = menu.addAction(QStringLiteral("Close"));
    connect(closeAction, &QAction::triggered, this, &QWidget::close);

    menu.exec(globalPos);
}

void MainWindow::showCommandPalette()
{
    if (!commandPaletteDialog_)
    {
        commandPaletteDialog_ = new CommandPaletteDialog(this);
        connect(commandPaletteDialog_, &CommandPaletteDialog::commandTriggered, this, &MainWindow::triggerCommand);
    }

    commandPaletteDialog_->setCommands({QStringLiteral("Go to Home"),
                                        QStringLiteral("Open Text to Image"),
                                        QStringLiteral("Open Image to Image"),
                                        QStringLiteral("Open Text to Video"),
                                        QStringLiteral("Open Image to Video"),
                                        QStringLiteral("Open Workflows"),
                                        QStringLiteral("Open History"),
                                        QStringLiteral("Open Inspiration"),
                                        QStringLiteral("Open Models"),
                                        QStringLiteral("Open Settings"),
                                        QStringLiteral("Import Workflow"),
                                        QStringLiteral("Toggle Left Rail"),
                                        QStringLiteral("Toggle Bottom Utility"),
                                        QStringLiteral("Show Details Tray")});

    commandPaletteDialog_->show();
    commandPaletteDialog_->raise();
    commandPaletteDialog_->activateWindow();
}

void MainWindow::triggerCommand(const QString &command)
{
    const QString normalized = command.trimmed().toLower();

    if (normalized.contains(QStringLiteral("home")))
    {
        switchToMode(QStringLiteral("home"));
        return;
    }
    if (normalized.contains(QStringLiteral("text to image")))
    {
        switchToMode(QStringLiteral("t2i"));
        return;
    }
    if (normalized.contains(QStringLiteral("image to image")))
    {
        switchToMode(QStringLiteral("i2i"));
        return;
    }
    if (normalized.contains(QStringLiteral("text to video")))
    {
        switchToMode(QStringLiteral("t2v"));
        return;
    }
    if (normalized.contains(QStringLiteral("image to video")))
    {
        switchToMode(QStringLiteral("i2v"));
        return;
    }
    if (normalized.contains(QStringLiteral("workflows")))
    {
        switchToMode(QStringLiteral("workflows"));
        return;
    }
    if (normalized.contains(QStringLiteral("history")))
    {
        switchToMode(QStringLiteral("history"));
        return;
    }
    if (normalized.contains(QStringLiteral("inspiration")))
    {
        switchToMode(QStringLiteral("inspiration"));
        return;
    }
    if (normalized.contains(QStringLiteral("models")))
    {
        switchToMode(QStringLiteral("models"));
        return;
    }
    if (normalized.contains(QStringLiteral("settings")))
    {
        switchToMode(QStringLiteral("settings"));
        return;
    }
    if (normalized.contains(QStringLiteral("import workflow")))
    {
        openWorkflowImportDialog();
        return;
    }
    if (normalized.contains(QStringLiteral("left rail")))
    {
        togglePrimarySidebar();
        return;
    }
    if (normalized.contains(QStringLiteral("bottom panels")) || normalized.contains(QStringLiteral("bottom utility")))
    {
        toggleBottomPanels();
        return;
    }
    if (normalized.contains(QStringLiteral("details dock")) || normalized.contains(QStringLiteral("details tray")))
    {
        toggleDetailsPanel();
        return;
    }
}

void MainWindow::openWorkflowImportDialog()
{
    if (workflowImportProcess_)
    {
        QMessageBox::information(
            this,
            QStringLiteral("Workflow Import"),
            QStringLiteral("A workflow import is already running. Wait for it to finish before starting another."));
        return;
    }

    WorkflowImportDialog dialog(this);
    const QString projectRoot = resolveProjectRoot();
    dialog.setManagedComfyRoot(defaultManagedComfyRoot(projectRoot));
    dialog.setDefaultDestinationRoot(defaultImportedWorkflowsRoot(projectRoot));

    if (dialog.exec() != QDialog::Accepted)
        return;

    QJsonObject request;
    request.insert(QStringLiteral("command"), QStringLiteral("import_workflow"));
    request.insert(QStringLiteral("source"), dialog.sourcePath());
    request.insert(QStringLiteral("destination_root"), dialog.destinationRoot());

    if (!dialog.profileName().trimmed().isEmpty())
        request.insert(QStringLiteral("profile_name"), dialog.profileName().trimmed());

    if (!dialog.comfyRoot().trimmed().isEmpty())
        request.insert(QStringLiteral("comfy_root"), dialog.comfyRoot().trimmed());

    request.insert(QStringLiteral("auto_apply_node_deps"), dialog.autoApplyNodeDeps());
    request.insert(QStringLiteral("auto_apply_model_deps"), dialog.autoApplyModelDeps());

    const QString pythonExecutable = resolvePythonExecutable();
    const QString workerClient = QDir(projectRoot).filePath(QStringLiteral("python/worker_client.py"));

    auto *process = new QProcess(this);
    workflowImportProcess_ = process;

    process->setProgram(pythonExecutable);
    process->setArguments({workerClient});
    process->setWorkingDirectory(projectRoot);

    QProcessEnvironment env = QProcessEnvironment::systemEnvironment();
    const QString cacheRoot = QDir(projectRoot).filePath(QStringLiteral("hf_cache"));
    env.insert(QStringLiteral("HF_HOME"), cacheRoot);
    env.insert(QStringLiteral("HUGGINGFACE_HUB_CACHE"), cacheRoot);
    process->setProcessEnvironment(env);

    const QByteArray requestBytes = QJsonDocument(request).toJson(QJsonDocument::Compact) + "\n";

    appendLogLine(QStringLiteral("Starting workflow import: %1").arg(QFileInfo(dialog.sourcePath()).fileName()));
    if (bottomReadyLabel_)
        bottomReadyLabel_->setText(QStringLiteral("IMPORTING"));
    if (bottomStateLabel_)
        bottomStateLabel_->setText(QStringLiteral("Workflow import running"));

    connect(process, &QProcess::started, this, [process, requestBytes]()
            {
        process->write(requestBytes);
        process->closeWriteChannel(); });

    connect(process, &QProcess::errorOccurred, this, [this, process](QProcess::ProcessError)
            {
        if (workflowImportProcess_ != process)
        {
            process->deleteLater();
            return;
        }

        const QString stderrText = QString::fromUtf8(process->readAllStandardError()).trimmed();
        workflowImportProcess_ = nullptr;
        process->deleteLater();

        if (bottomReadyLabel_)
            bottomReadyLabel_->setText(QStringLiteral("READY"));
        if (bottomStateLabel_)
            bottomStateLabel_->setText(QStringLiteral("Idle"));

        appendLogLine(stderrText.isEmpty()
                          ? QStringLiteral("Workflow import failed to start.")
                          : QStringLiteral("Workflow import failed to start: %1").arg(stderrText));

        QMessageBox::warning(
            this,
            QStringLiteral("Workflow Import"),
            stderrText.isEmpty()
                ? QStringLiteral("Failed to start worker_client.py for workflow import.")
                : QStringLiteral("Failed to start worker_client.py for workflow import.\n\n%1").arg(stderrText)); });

    connect(process,
            qOverload<int, QProcess::ExitStatus>(&QProcess::finished),
            this,
            [this, process](int exitCode, QProcess::ExitStatus exitStatus)
            {
                if (workflowImportProcess_ != process)
                {
                    process->deleteLater();
                    return;
                }

                const QString stderrText = QString::fromUtf8(process->readAllStandardError()).trimmed();
                const QString stdoutText = QString::fromUtf8(process->readAllStandardOutput()).trimmed();

                workflowImportProcess_ = nullptr;
                process->deleteLater();

                if (bottomReadyLabel_)
                    bottomReadyLabel_->setText(QStringLiteral("READY"));
                if (bottomStateLabel_)
                    bottomStateLabel_->setText(QStringLiteral("Idle"));

                if (!stderrText.isEmpty())
                    appendLogLine(stderrText);

                if (exitStatus != QProcess::NormalExit || exitCode != 0)
                {
                    QMessageBox::warning(
                        this,
                        QStringLiteral("Workflow Import"),
                        stderrText.isEmpty()
                            ? QStringLiteral("Workflow import process exited with code %1.").arg(exitCode)
                            : QStringLiteral("Workflow import process exited with code %1.\n\n%2").arg(exitCode).arg(stderrText));
                    return;
                }

                QString parseErrorText;
                const QJsonObject response = parseLastJsonObjectFromStdout(stdoutText, &parseErrorText);
                if (response.isEmpty())
                {
                    QMessageBox::warning(
                        this,
                        QStringLiteral("Workflow Import"),
                        parseErrorText.isEmpty()
                            ? QStringLiteral("Worker returned no usable JSON payload for workflow import.")
                            : parseErrorText);
                    return;
                }

                showWorkflowImportResult(response, stderrText);
            });

    process->start();
}

void MainWindow::showWorkflowImportResult(const QJsonObject &response, const QString &stderrText)
{
    if (!stderrText.trimmed().isEmpty())
        appendLogLine(stderrText.trimmed());

    if (response.isEmpty())
    {
        QMessageBox::warning(
            this,
            QStringLiteral("Workflow Import"),
            QStringLiteral("Worker returned no JSON payload for workflow import."));
        return;
    }

    const bool ok = response.value(QStringLiteral("ok")).toBool(false);
    const QString inferredTask = response.value(QStringLiteral("inferred_task_command")).toString().trimmed();
    const QString inferredMedia = response.value(QStringLiteral("inferred_media_type")).toString().trimmed();

    const QJsonObject artifacts = response.value(QStringLiteral("artifacts")).toObject();
    const QJsonArray missingCustomNodes = response.value(QStringLiteral("missing_custom_nodes")).toArray();
    const QJsonArray modelReferences = response.value(QStringLiteral("model_references")).toArray();
    const QJsonArray warnings = response.value(QStringLiteral("warnings")).toArray();
    const QJsonArray errors = response.value(QStringLiteral("errors")).toArray();

    QStringList lines;
    lines << QStringLiteral("Import %1").arg(ok ? QStringLiteral("completed.") : QStringLiteral("reported issues."));
    if (!inferredTask.isEmpty())
        lines << QStringLiteral("Task: %1").arg(inferredTask);
    if (!inferredMedia.isEmpty())
        lines << QStringLiteral("Media: %1").arg(inferredMedia);
    if (!artifacts.value(QStringLiteral("import_root")).toString().trimmed().isEmpty())
        lines << QStringLiteral("Import Root: %1").arg(QDir::toNativeSeparators(artifacts.value(QStringLiteral("import_root")).toString().trimmed()));
    if (!artifacts.value(QStringLiteral("workflow_path")).toString().trimmed().isEmpty())
        lines << QStringLiteral("Workflow Path: %1").arg(QDir::toNativeSeparators(artifacts.value(QStringLiteral("workflow_path")).toString().trimmed()));
    if (!artifacts.value(QStringLiteral("profile_path")).toString().trimmed().isEmpty())
        lines << QStringLiteral("Profile Path: %1").arg(QDir::toNativeSeparators(artifacts.value(QStringLiteral("profile_path")).toString().trimmed()));
    if (!artifacts.value(QStringLiteral("scan_report_path")).toString().trimmed().isEmpty())
        lines << QStringLiteral("Scan Report: %1").arg(QDir::toNativeSeparators(artifacts.value(QStringLiteral("scan_report_path")).toString().trimmed()));

    lines << QStringLiteral("Missing Custom Nodes: %1").arg(missingCustomNodes.size());
    lines << QStringLiteral("Model References: %1").arg(modelReferences.size());

    auto joinArray = [](const QJsonArray &array)
    {
        QStringList out;
        for (const QJsonValue &value : array)
            out << value.toString();
        return out;
    };

    QString detailedText;
    if (!warnings.isEmpty())
        detailedText += QStringLiteral("Warnings:\n%1\n\n").arg(joinArray(warnings).join(QStringLiteral("\n")));
    if (!errors.isEmpty())
        detailedText += QStringLiteral("Errors:\n%1\n\n").arg(joinArray(errors).join(QStringLiteral("\n")));

    QMessageBox box(this);
    box.setIcon(ok ? QMessageBox::Information : QMessageBox::Warning);
    box.setWindowTitle(QStringLiteral("Workflow Import"));
    box.setText(lines.join(QStringLiteral("\n")));
    if (!detailedText.trimmed().isEmpty())
        box.setDetailedText(detailedText.trimmed());
    box.exec();

    if (workflowsPage_)
        workflowsPage_->refreshProfiles();

    appendLogLine(QStringLiteral("Workflow import finished • task=%1 • media=%2 • ok=%3")
                      .arg(inferredTask.isEmpty() ? QStringLiteral("unknown") : inferredTask,
                           inferredMedia.isEmpty() ? QStringLiteral("unknown") : inferredMedia,
                           ok ? QStringLiteral("true") : QStringLiteral("false")));
}

void MainWindow::togglePrimarySidebar()
{
    if (!sideRail_)
        return;
    sideRail_->setVisible(!sideRail_->isVisible());
}

void MainWindow::toggleBottomPanels()
{
    if (!queueDock_)
        return;

    if (!queueDock_->isVisible())
        queueDock_->show();

    queueDockUserExpanded_ = !queueDockUserExpanded_;
    bottomUtilityUserExpanded_ = queueDockUserExpanded_;
    if (!queueDockUserExpanded_)
        detailsDockPinnedOpen_ = false;

    updateDockChrome();
}

void MainWindow::toggleDetailsPanel()
{
    if (!queueDock_)
        return;

    if (!queueDock_->isVisible())
        queueDock_->show();

    detailsDockPinnedOpen_ = !detailsDockPinnedOpen_;
    if (detailsDockPinnedOpen_)
    {
        queueDockUserExpanded_ = true;
        bottomUtilityUserExpanded_ = true;
        if (bottomUtilityTabs_)
            bottomUtilityTabs_->setCurrentIndex(0);
    }

    updateDockChrome();
}

void MainWindow::applyShellStateForMode(const QString &modeId)
{
    if (titleBar_)
        titleBar_->setContextText(pageContextForMode(modeId));

    if (bottomPageLabel_)
        bottomPageLabel_->setText(modeId.toUpper());

    updateModeButtonState(modeId);
    updateDetailsPanelForModeContext();
    updateDockChrome();
}

void MainWindow::setBottomPageContext(const QString &text)
{
    if (bottomPageLabel_)
        bottomPageLabel_->setText(text);
}


void MainWindow::syncBottomTelemetry()
{
    spellvision::shell::BottomTelemetryPresenter::SyncBindings bindings;
    bindings.queueManager = queueManager_;
    bindings.currentGenerationPage = generationPageForMode(currentModeId_);
    bindings.currentModeId = currentModeId_;
    bindings.pageContextText = pageContextForMode(currentModeId_);
    bindings.readyLabel = bottomReadyLabel_;
    bindings.pageLabel = bottomPageLabel_;
    bindings.runtimeLabel = bottomRuntimeLabel_;
    bindings.queueLabel = bottomQueueLabel_;
    bindings.vramLabel = bottomVramLabel_;
    bindings.modelLabel = bottomModelLabel_;
    bindings.loraLabel = bottomLoraLabel_;
    bindings.stateLabel = bottomStateLabel_;
    bindings.progressBar = bottomProgressBar_;

    spellvision::shell::BottomTelemetryPresenter::sync(bindings);
}


void MainWindow::switchToMode(const QString &modeId)
{
    const QString resolvedModeId = modePages_.contains(modeId) ? modeId : QStringLiteral("home");
    currentModeId_ = resolvedModeId;

    if (pageStack_)
        pageStack_->setCurrentWidget(modePages_.value(resolvedModeId, homePage_));

    applyShellStateForMode(resolvedModeId);
}

void MainWindow::openManager(const QString &managerId)
{
    if (managerId == QStringLiteral("models"))
    {
        switchToMode(QStringLiteral("models"));
        return;
    }
    if (managerId == QStringLiteral("workflows"))
    {
        switchToMode(QStringLiteral("workflows"));
        return;
    }
    if (managerId == QStringLiteral("inspiration"))
    {
        switchToMode(QStringLiteral("inspiration"));
        return;
    }
    if (managerId == QStringLiteral("history"))
    {
        switchToMode(QStringLiteral("history"));
        return;
    }
    if (managerId == QStringLiteral("settings"))
    {
        switchToMode(QStringLiteral("settings"));
        return;
    }
    if (managerId == QStringLiteral("downloads"))
    {
        switchToMode(QStringLiteral("models"));
        return;
    }
}

void MainWindow::onQueueChanged()
{
    syncBottomTelemetry();
    updateActiveQueueStrip();
    updateDetailsPanelForQueueSelection();
    updateDockChrome();

    if (queueTableView_)
        queueTableView_->viewport()->update();
}

void MainWindow::changeEvent(QEvent *event)
{
    QMainWindow::changeEvent(event);
    if (titleBar_)
        titleBar_->setMaximized(isMaximized());
    updateDockChrome();
}

bool MainWindow::nativeEvent(const QByteArray &eventType, void *message, qintptr *result)
{
#ifdef Q_OS_WIN
    Q_UNUSED(eventType);

    MSG *msg = static_cast<MSG *>(message);
    if (!msg || !result)
        return false;

    if (msg->message == WM_NCHITTEST)
    {
        const LONG borderWidth = 8;
        RECT winRect{};
        GetWindowRect(reinterpret_cast<HWND>(winId()), &winRect);

        const long x = GET_X_LPARAM(msg->lParam);
        const long y = GET_Y_LPARAM(msg->lParam);

        const bool resizeWidth = minimumWidth() != maximumWidth();
        const bool resizeHeight = minimumHeight() != maximumHeight();

        if (resizeWidth)
        {
            if (x >= winRect.left && x < winRect.left + borderWidth)
            {
                if (resizeHeight)
                {
                    if (y >= winRect.top && y < winRect.top + borderWidth)
                    {
                        *result = HTTOPLEFT;
                        return true;
                    }
                    if (y <= winRect.bottom && y > winRect.bottom - borderWidth)
                    {
                        *result = HTBOTTOMLEFT;
                        return true;
                    }
                }
                *result = HTLEFT;
                return true;
            }

            if (x < winRect.right && x >= winRect.right - borderWidth)
            {
                if (resizeHeight)
                {
                    if (y >= winRect.top && y < winRect.top + borderWidth)
                    {
                        *result = HTTOPRIGHT;
                        return true;
                    }
                    if (y <= winRect.bottom && y > winRect.bottom - borderWidth)
                    {
                        *result = HTBOTTOMRIGHT;
                        return true;
                    }
                }
                *result = HTRIGHT;
                return true;
            }
        }

        if (resizeHeight)
        {
            if (y >= winRect.top && y < winRect.top + borderWidth)
            {
                *result = HTTOP;
                return true;
            }

            if (y < winRect.bottom && y >= winRect.bottom - borderWidth)
            {
                *result = HTBOTTOM;
                return true;
            }
        }
    }
#else
    Q_UNUSED(eventType);
    Q_UNUSED(message);
    Q_UNUSED(result);
#endif
    return false;
}

void MainWindow::refreshDetailsPanel()
{
    updateDetailsPanelForQueueSelection();
}

void MainWindow::configureDetailsActions(const QString &primaryId,
                                         const QString &primaryText,
                                         const QString &secondaryId,
                                         const QString &secondaryText,
                                         const QString &tertiaryId,
                                         const QString &tertiaryText)
{
    detailsPrimaryActionId_ = primaryId;
    detailsSecondaryActionId_ = secondaryId;
    detailsTertiaryActionId_ = tertiaryId;

    if (detailsPrimaryActionButton_)
    {
        detailsPrimaryActionButton_->setText(primaryText);
        detailsPrimaryActionButton_->setVisible(!primaryText.trimmed().isEmpty());
    }

    if (detailsSecondaryActionButton_)
    {
        detailsSecondaryActionButton_->setText(secondaryText);
        detailsSecondaryActionButton_->setVisible(!secondaryText.trimmed().isEmpty());
    }

    if (detailsTertiaryActionButton_)
    {
        detailsTertiaryActionButton_->setText(tertiaryText);
        detailsTertiaryActionButton_->setVisible(!tertiaryText.trimmed().isEmpty());
    }
}

void MainWindow::triggerDetailsAction(const QString &actionId)
{
    if (actionId.startsWith(QStringLiteral("mode:")))
    {
        switchToMode(actionId.mid(QStringLiteral("mode:").size()));
        return;
    }
    if (actionId.startsWith(QStringLiteral("manager:")))
    {
        openManager(actionId.mid(QStringLiteral("manager:").size()));
        return;
    }
    if (actionId == QStringLiteral("toggle:queue"))
    {
        toggleBottomPanels();
        return;
    }
    if (actionId == QStringLiteral("toggle:details"))
    {
        toggleDetailsPanel();
        return;
    }
}

void MainWindow::updateDetailsPanelForModeContext()
{
    if (!detailsTitleLabel_ || !detailsBodyLabel_ || !queueManager_)
        return;

    const QVector<QueueItem> &items = queueManager_->items();

    int pendingCount = 0;
    int runningCount = 0;
    int failedCount = 0;
    for (const QueueItem &item : items)
    {
        if (item.state == QueueItemState::Running)
            ++runningCount;
        else if (item.state == QueueItemState::Queued || item.state == QueueItemState::Preparing)
            ++pendingCount;
        else if (item.state == QueueItemState::Failed)
            ++failedCount;
    }

    const QString contextText = pageContextForMode(currentModeId_);
    QString selectionText = QStringLiteral("Nothing selected");
    QString bodyText = QStringLiteral("Use the side rail to navigate between creation, workflows, models, and review surfaces.");

    detailsTitleLabel_->setText(currentModeId_.toUpper());

    if (currentModeId_ == QStringLiteral("home"))
    {
        selectionText = QStringLiteral("Launch surface");
        bodyText = QStringLiteral("Home is the production launch deck. Use it to route into creation, workflow imports, models, and review.");
        configureDetailsActions(QStringLiteral("mode:t2i"), QStringLiteral("Open T2I"),
                                QStringLiteral("mode:workflows"), QStringLiteral("Open Workflows"),
                                QStringLiteral("mode:models"), QStringLiteral("Open Models"));
    }
    else if (currentModeId_ == QStringLiteral("t2i") || currentModeId_ == QStringLiteral("i2i"))
    {
        selectionText = currentModeId_ == QStringLiteral("t2i") ? QStringLiteral("Prompt-first canvas") : QStringLiteral("Restyle canvas");
        bodyText = QStringLiteral("Prompt, input, and quick controls stay prioritized in the left inspector. The right rail reports model, LoRA, workflow, and readiness state.");
        configureDetailsActions(QStringLiteral("manager:models"), QStringLiteral("Open Models"),
                                QStringLiteral("manager:workflows"), QStringLiteral("Open Workflows"),
                                QStringLiteral("toggle:queue"), QStringLiteral("Show Queue"));
    }
    else if (currentModeId_ == QStringLiteral("t2v") || currentModeId_ == QStringLiteral("i2v"))
    {
        selectionText = QStringLiteral("Motion workspace");
        bodyText = QStringLiteral("Use this shell to shape motion prompts and keyframes now. Worker execution is still being finished for motion modes, so start with T2I/I2I for live jobs.");
        configureDetailsActions(QStringLiteral("toggle:queue"), QStringLiteral("Show Queue"),
                                QStringLiteral("manager:workflows"), QStringLiteral("Open Workflows"),
                                QStringLiteral("mode:home"), QStringLiteral("Return Home"));
    }
    else if (currentModeId_ == QStringLiteral("workflows"))
    {
        selectionText = QStringLiteral("Workflow library");
        bodyText = QStringLiteral("Review imported starters, inspect dependencies, and flow the best presets back into Home and generation pages.");
        configureDetailsActions(QStringLiteral("manager:models"), QStringLiteral("Open Models"),
                                QStringLiteral("mode:home"), QStringLiteral("Go Home"),
                                QStringLiteral("manager:history"), QStringLiteral("Open History"));
    }
    else if (currentModeId_ == QStringLiteral("history"))
    {
        selectionText = QStringLiteral("Review workspace");
        bodyText = QStringLiteral("Inspect finished work, reroute promising outputs into I2I, and keep queue and workflow context close at hand.");
        configureDetailsActions(QStringLiteral("mode:i2i"), QStringLiteral("Send to I2I"),
                                QStringLiteral("toggle:queue"), QStringLiteral("Show Queue"),
                                QStringLiteral("mode:home"), QStringLiteral("Go Home"));
    }
    else if (currentModeId_ == QStringLiteral("inspiration"))
    {
        selectionText = QStringLiteral("Moodboard");
        bodyText = QStringLiteral("Curated inspiration should route back into Home or directly into prompt-first generation without bloating the shell.");
        configureDetailsActions(QStringLiteral("mode:t2i"), QStringLiteral("Open T2I"),
                                QStringLiteral("manager:workflows"), QStringLiteral("Open Workflows"),
                                QStringLiteral("mode:home"), QStringLiteral("Send to Home"));
    }
    else if (currentModeId_ == QStringLiteral("models"))
    {
        selectionText = QStringLiteral("Model library");
        bodyText = QStringLiteral("Manage checkpoints, LoRAs, and dependencies here while creation pages stay focused on the active stack.");
        configureDetailsActions(QStringLiteral("manager:downloads"), QStringLiteral("Open Downloads"),
                                QStringLiteral("manager:settings"), QStringLiteral("Open Settings"),
                                QStringLiteral("mode:home"), QStringLiteral("Go Home"));
    }
    else if (currentModeId_ == QStringLiteral("settings"))
    {
        selectionText = QStringLiteral("Preferences");
        bodyText = QStringLiteral("Tune appearance, workspace behavior, and integrations without pushing configuration controls into creation pages.");
        configureDetailsActions(QStringLiteral("manager:models"), QStringLiteral("Open Models"),
                                QStringLiteral("mode:home"), QStringLiteral("Go Home"),
                                QStringLiteral("manager:workflows"), QStringLiteral("Open Workflows"));
    }

    detailsBodyLabel_->setText(bodyText);
    if (detailsContextValueLabel_)
        detailsContextValueLabel_->setText(contextText);
    if (detailsSelectionValueLabel_)
        detailsSelectionValueLabel_->setText(selectionText);
    if (detailsQueueValueLabel_)
        detailsQueueValueLabel_->setText(QStringLiteral("%1 running • %2 pending").arg(runningCount).arg(pendingCount));
    if (detailsStatusValueLabel_)
        detailsStatusValueLabel_->setText(failedCount > 0 ? QStringLiteral("%1 errors need review").arg(failedCount) : QStringLiteral("Ready"));
}

QString MainWindow::pageContextForMode(const QString &modeId) const
{
    if (modeId == QStringLiteral("home"))
        return QStringLiteral("Home ready.");
    if (modeId == QStringLiteral("t2i"))
        return QStringLiteral("Text to Image ready.");
    if (modeId == QStringLiteral("i2i"))
        return QStringLiteral("Image to Image ready.");
    if (modeId == QStringLiteral("t2v"))
        return QStringLiteral("Text to Video ready.");
    if (modeId == QStringLiteral("i2v"))
        return QStringLiteral("Image to Video ready.");
    if (modeId == QStringLiteral("workflows"))
        return QStringLiteral("Workflows ready.");
    if (modeId == QStringLiteral("history"))
        return QStringLiteral("History ready.");
    if (modeId == QStringLiteral("inspiration"))
        return QStringLiteral("Inspiration ready.");
    if (modeId == QStringLiteral("models"))
        return QStringLiteral("Models ready.");
    if (modeId == QStringLiteral("settings"))
        return QStringLiteral("Settings ready.");
    return QStringLiteral("Ready.");
}

void MainWindow::updateModeButtonState(const QString &modeId)
{
    for (auto it = modeButtons_.begin(); it != modeButtons_.end(); ++it)
    {
        if (!it.value())
            continue;

        it.value()->setChecked(it.key() == modeId);
    }
}

void MainWindow::updateActiveQueueStrip()
{

    spellvision::shell::QueueUiPresenter::updateActiveQueueStrip(
        queueManager_,
        activeQueueTitleLabel_,
        activeQueueSummaryLabel_);
}

QString MainWindow::selectedQueueId() const
{

    return spellvision::shell::QueueUiPresenter::selectedQueueId(queueTableView_);
}

void MainWindow::updateDetailsPanelForQueueSelection()
{
    if (!detailsTitleLabel_ || !detailsBodyLabel_ || !queueManager_)
        return;

    const QString id = selectedQueueId();
    if (id.isEmpty())
    {
        updateDetailsPanelForModeContext();
        return;
    }

    const QueueItem item = queueManager_->itemById(id);
    detailsTitleLabel_->setText(QStringLiteral("%1 • %2").arg(item.command, queueStateDisplay(item.state)));

    QString bodyText = QStringLiteral("%1\nModel: %2")
                           .arg(summarizePrompt(item.prompt))
                           .arg(item.model.trimmed().isEmpty() ? QStringLiteral("none") : item.model);
    if (!item.statusText.trimmed().isEmpty())
        bodyText += QStringLiteral("\nStatus note: %1").arg(item.statusText);
    detailsBodyLabel_->setText(bodyText);

    if (detailsContextValueLabel_)
        detailsContextValueLabel_->setText(pageContextForMode(currentModeId_));
    if (detailsSelectionValueLabel_)
        detailsSelectionValueLabel_->setText(item.command);
    if (detailsQueueValueLabel_)
        detailsQueueValueLabel_->setText(item.id);
    if (detailsStatusValueLabel_)
        detailsStatusValueLabel_->setText(QStringLiteral("%1 • %2%%")
                                              .arg(queueStateDisplay(item.state))
                                              .arg(item.progressPercent()));

    if (item.isTerminal())
    {
        configureDetailsActions(QStringLiteral("queue:duplicate"), QStringLiteral("Duplicate Job"),
                                QStringLiteral("mode:i2i"), QStringLiteral("Send to I2I"),
                                QStringLiteral("manager:history"), QStringLiteral("Open History"));
    }
    else
    {
        configureDetailsActions(QStringLiteral("queue:moveup"), QStringLiteral("Move Up"),
                                QStringLiteral("queue:duplicate"), QStringLiteral("Duplicate Job"),
                                QStringLiteral("toggle:queue"), QStringLiteral("Focus Queue"));
    }
}