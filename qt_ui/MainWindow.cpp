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

#include <QAbstractButton>
#include <QAbstractItemView>
#include <QAction>
#include <QCoreApplication>
#include <QDir>
#include <QFileInfo>
#include <QItemSelectionModel>
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
#include <QProgressBar>
#include <QPushButton>
#include <QStatusBar>
#include <QTableView>
#include <QTextEdit>
#include <QToolButton>
#include <QVBoxLayout>
#include <QWidget>

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
    button->setFixedSize(58, 34);
    button->setCursor(Qt::PointingHandCursor);
    return button;
}

QString queueStateDisplay(QueueItemState state)
{
    switch (state)
    {
    case QueueItemState::Queued: return QStringLiteral("Queued");
    case QueueItemState::Preparing: return QStringLiteral("Preparing");
    case QueueItemState::Running: return QStringLiteral("Running");
    case QueueItemState::Completed: return QStringLiteral("Completed");
    case QueueItemState::Failed: return QStringLiteral("Failed");
    case QueueItemState::Cancelled: return QStringLiteral("Cancelled");
    case QueueItemState::Skipped: return QStringLiteral("Skipped");
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
        QStringLiteral("SpellVision.png")
    };

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
}

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent)
{
    setObjectName(QStringLiteral("MainWindow"));
    setWindowTitle(QStringLiteral("SpellVision"));
    const QPixmap brandWindowIcon = loadBrandPixmap();
    if (!brandWindowIcon.isNull())
        setWindowIcon(QIcon(brandWindowIcon));
    setWindowFlags(Qt::Window
                   | Qt::FramelessWindowHint
                   | Qt::CustomizeWindowHint
                   | Qt::WindowSystemMenuHint
                   | Qt::WindowMinimizeButtonHint
                   | Qt::WindowMaximizeButtonHint
                   | Qt::WindowCloseButtonHint);
    setDockNestingEnabled(true);

    queueManager_ = new QueueManager(this);
    connect(queueManager_, &QueueManager::queueChanged, this, &MainWindow::onQueueChanged);

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
    connect(titleBar_, &CustomTitleBar::maximizeRestoreRequested, this, [this]() {
        isMaximized() ? showNormal() : showMaximized();
        if (titleBar_)
            titleBar_->setMaximized(isMaximized());
    });
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

    auto applyTheme = [this]() {
        setStyleSheet(ThemeManager::instance().shellStyleSheet() + QStringLiteral(
            "QWidget#MainPageStack { background: transparent; }"
            "QStatusBar { background: rgba(7,11,18,0.98); border-top: 1px solid rgba(124,92,255,0.18); min-height: 38px; }"
            "QStatusBar QLabel { color: #c9d8eb; font-size: 11px; padding-left: 4px; padding-right: 4px; }"
            "QSplitter::handle { background: transparent; }"
            "QSplitter::handle:hover { background: rgba(124,92,255,0.12); }"
            "QWidget#SideRail { background: rgba(8, 12, 20, 0.58); border-right: 1px solid rgba(124,92,255,0.10); }"
            "QLabel#SideRailBadge {"
            " background: rgba(255,255,255,0.03);"
            " border: 1px solid rgba(144,156,214,0.24);"
            " border-radius: 15px;"
            " color: #f5f8ff;"
            " padding: 4px 0px;"
            " font-size: 6px;"
            " font-weight: 800;"
            "}"
            "QLabel#SideRailCaption {"
            " color: #7f94b8;"
            " font-size: 7px;"
            " font-weight: 800;"
            " letter-spacing: 0.08em;"
            " padding-top: 6px;"
            " padding-bottom: 4px;"
            "}"
            "QFrame#SideRailDivider { background: rgba(120,138,172,0.16); min-height: 1px; max-height: 1px; border: none; margin-top: 5px; margin-bottom: 5px; }"
            "QToolButton#SideRailButton {"
            " color: #dbe5f5;"
            " border: 1px solid transparent;"
            " border-radius: 12px;"
            " font-size: 9px;"
            " font-weight: 700;"
            " padding: 6px 8px;"
            " text-align: center;"
            " background: transparent;"
            "}"
            "QToolButton#SideRailButton:hover {"
            " background: rgba(255,255,255,0.045);"
            " border-color: rgba(138, 128, 255, 0.18);"
            "}"
            "QToolButton#SideRailButton:checked {"
            " color: #f7fbff;"
            " background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 rgba(122,92,255,0.26), stop:1 rgba(92,182,255,0.13));"
            " border-color: rgba(166, 154, 255, 0.50);"
            "}"
            "QFrame#QueueActiveStrip, QFrame#DetailsSummaryCard, QFrame#DetailsActionCard {"
            " background: rgba(18,25,39,0.92);"
            " border: 1px solid rgba(120,138,172,0.22);"
            " border-radius: 16px;"
            "}"
            "QLabel#QueueActiveEyebrow, QLabel#DetailsEyebrow {"
            " font-size: 11px; font-weight: 700; color: #8fb2ff;"
            "}"
            "QLabel#QueueActiveTitle, QLabel#DetailsTitle {"
            " font-size: 16px; font-weight: 800; color: #f2f6fc;"
            "}"
            "QLabel#QueueActiveBody, QLabel#DetailsBody {"
            " font-size: 11px; color: #9fb0ca;"
            "}"
            "QLabel#DetailsMetaLabel {"
            " font-size: 9px; font-weight: 800; color: #7f95b7; text-transform: uppercase; letter-spacing: 0.08em;"
            "}"
            "QLabel#DetailsMetaValue {"
            " font-size: 11px; font-weight: 700; color: #eef4ff; background: rgba(255,255,255,0.03); border: 1px solid rgba(120,138,172,0.14); border-radius: 9px; padding: 3px 7px;"
            "}"
            "QLabel#DetailsSubTitle {"
            " font-size: 12px; font-weight: 800; color: #eef4ff;"
            "}"
            "QWidget#CustomTitleBar { border-bottom: 1px solid rgba(124,92,255,0.14); }"
            "QPushButton#TitleBarMenuButton { min-height: 24px; padding: 0px 10px; font-size: 11px; font-weight: 700; border-radius: 8px; }"
            "QPushButton#TitleBarMenuButton:hover { background: rgba(255,255,255,0.05); }"
            "QWidget#CustomTitleBar QToolButton { min-width: 22px; min-height: 22px; border-radius: 7px; }"
            "QFrame#TitleBarSearchField { min-height: 24px; border-radius: 8px; }"
            "QLabel#TitleBarSearchText { font-size: 11px; }"
            "QLabel#TitleBarSearchShortcut { font-size: 10px; }"
            "QPushButton#DetailsPrimaryActionButton { min-height: 30px; font-size: 11px; font-weight: 800; }"
            "QPushButton#DetailsSecondaryActionButton { min-height: 28px; font-size: 11px; }"
            "QPushButton#DetailsActionButton { min-height: 30px; border-radius: 10px; font-size: 11px; font-weight: 700; }"
            "QTextEdit#LogsView { background: rgba(11,16,26,0.92); border: 1px solid rgba(120,138,172,0.18); border-radius: 12px; padding: 8px; }"));
    };
    applyTheme();
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, applyTheme);
}


QWidget *MainWindow::createSideRail()
{
    auto *rail = new QWidget(this);
    rail->setObjectName(QStringLiteral("SideRail"));
    rail->setFixedWidth(76);

    auto *layout = new QVBoxLayout(rail);
    layout->setContentsMargins(6, 8, 6, 8);
    layout->setSpacing(4);

    auto *badge = new QLabel(QStringLiteral("SV"), rail);
    badge->setObjectName(QStringLiteral("SideRailBadge"));
    badge->setAlignment(Qt::AlignCenter);
    badge->setFixedSize(30, 30);
    const QPixmap railBadge = roundedBrandPixmap(QSize(24, 24), 7);
    if (!railBadge.isNull())
        badge->setPixmap(railBadge);
    layout->addWidget(badge, 0, Qt::AlignHCenter);

    auto *createCaption = new QLabel(QStringLiteral("Create"), rail);
    createCaption->setObjectName(QStringLiteral("SideRailCaption"));
    createCaption->setAlignment(Qt::AlignCenter);
    layout->addWidget(createCaption);

    const struct RailButtonSpec
    {
        QString modeId;
        QString text;
        QString toolTip;
    } createSpecs[] = {
        {QStringLiteral("home"), QStringLiteral("Home"), QStringLiteral("Home")},
        {QStringLiteral("t2i"), QStringLiteral("Create"), QStringLiteral("Text to Image")},
        {QStringLiteral("i2i"), QStringLiteral("Restyle"), QStringLiteral("Image to Image")},
        {QStringLiteral("t2v"), QStringLiteral("Motion"), QStringLiteral("Text to Video")},
        {QStringLiteral("i2v"), QStringLiteral("Animate"), QStringLiteral("Image to Video")}
    };

    for (const RailButtonSpec &spec : createSpecs)
    {
        auto *button = createRailButton(spec.text, spec.toolTip, rail);
        button->setFixedSize(58, 30);
        connect(button, &QToolButton::clicked, this, [this, spec]() { switchToMode(spec.modeId); });
        layout->addWidget(button, 0, Qt::AlignHCenter);
        modeButtons_.insert(spec.modeId, button);
    }

    auto *divider = createPanelFrame(QStringLiteral("SideRailDivider"), rail);
    divider->setFixedHeight(1);
    layout->addWidget(divider);

    auto *manageCaption = new QLabel(QStringLiteral("Manage"), rail);
    manageCaption->setObjectName(QStringLiteral("SideRailCaption"));
    manageCaption->setAlignment(Qt::AlignCenter);
    layout->addWidget(manageCaption);

    const RailButtonSpec manageSpecs[] = {
        {QStringLiteral("workflows"), QStringLiteral("Flows"), QStringLiteral("Workflows")},
        {QStringLiteral("history"), QStringLiteral("History"), QStringLiteral("History")},
        {QStringLiteral("inspiration"), QStringLiteral("Inspire"), QStringLiteral("Inspiration")},
        {QStringLiteral("models"), QStringLiteral("Models"), QStringLiteral("Models")},
        {QStringLiteral("settings"), QStringLiteral("Settings"), QStringLiteral("Settings")}
    };

    for (const RailButtonSpec &spec : manageSpecs)
    {
        auto *button = createRailButton(spec.text, spec.toolTip, rail);
        button->setFixedSize(58, 30);
        connect(button, &QToolButton::clicked, this, [this, spec]() { switchToMode(spec.modeId); });
        layout->addWidget(button, 0, Qt::AlignHCenter);
        modeButtons_.insert(spec.modeId, button);
    }

    layout->addStretch(1);
    return rail;
}

void MainWindow::buildPages()
{
    homePage_ = new HomePage(this);
    workflowsPage_ = new ModePage(
        QStringLiteral("Workflows"),
        QStringLiteral("Imported workflow starters live here, separate from the raw import dialog."),
        {
            QStringLiteral("Drag in JSON, PNG, or WebP workflows and inspect dependency health before launch."),
            QStringLiteral("Treat each workflow as a SpellVision preset with task type, backend type, and required assets."),
            QStringLiteral("Promote frequently used imports to favorites so they flow back into Home.")
        },
        this);
    historyPage_ = new ModePage(
        QStringLiteral("History"),
        QStringLiteral("Review results with a browser on the left and a large preview plus metadata stack on the right."),
        {
            QStringLiteral("Default to successful outputs, with failed and cancelled entries behind a filter toggle."),
            QStringLiteral("Support grouping by day, session, or no grouping."),
            QStringLiteral("Provide rerun, send to I2I, upscale, and copy-prompt actions from the review stack.")
        },
        this);
    inspirationPage_ = new ModePage(
        QStringLiteral("Inspiration"),
        QStringLiteral("A moodboard plus prompt recipe system that sends favorites and starters back into Home."),
        {
            QStringLiteral("Use a top filter bar for fast navigation across local, curated, and future online content."),
            QStringLiteral("Make the prompt immediately editable when an item is selected."),
            QStringLiteral("Support Send to Home Hero, Send to T2I, and Save as Workflow actions.")
        },
        this);
    modelsPage_ = new ModePage(
        QStringLiteral("Models"),
        QStringLiteral("Keep model management adjacent to downloads and managers without cluttering creation pages."),
        {
            QStringLiteral("Surface checkpoints, LoRAs, VAEs, and upscalers with compatibility cues."),
            QStringLiteral("Show dependency health and install state in the library rather than scattering it across pages."),
            QStringLiteral("Reserve space for downloads, manager tools, and future multimodal assets.")
        },
        this);
    settingsPage_ = new SettingsPage(this);

    t2iPage_ = new ImageGenerationPage(ImageGenerationPage::Mode::TextToImage, this);
    i2iPage_ = new ImageGenerationPage(ImageGenerationPage::Mode::ImageToImage, this);
    t2vPage_ = new ModePage(
        QStringLiteral("Text to Video"),
        QStringLiteral("Future motion workspace shell with room for timeline, FPS, and duration tooling."),
        {
            QStringLiteral("Keep the same shell language as image generation while reserving the center for motion-first controls."),
            QStringLiteral("Promote upcoming duration, FPS, and camera-motion controls into a dedicated inspector once the backend lands."),
            QStringLiteral("Maintain workflow launch and queue handoff so long-running motion jobs still feel native inside SpellVision.")
        },
        this);
    i2vPage_ = new ModePage(
        QStringLiteral("Image to Video"),
        QStringLiteral("Motion-from-image shell placeholder that stays aligned with the launcher-first home experience."),
        {
            QStringLiteral("Reserve the hero for source-frame selection, motion prompting, and eventual video-specific stack controls."),
            QStringLiteral("Keep output review, rerun, and send-to-history actions visually consistent with the rest of the workstation."),
            QStringLiteral("Use this as the matched shell until the dedicated I2V generation page is wired to the backend.")
        },
        this);

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

    connect(homePage_, &HomePage::modeRequested, this, &MainWindow::switchToMode);
    connect(homePage_, &HomePage::managerRequested, this, &MainWindow::openManager);

    connectGenerationPage(t2iPage_, QStringLiteral("t2i"));
    connectGenerationPage(i2iPage_, QStringLiteral("i2i"));

    connect(settingsPage_, &SettingsPage::presetChanged, this, [this](const QString &presetName) {
        const int index = ThemeManager::instance().presetNames().indexOf(presetName);
        if (index >= 0)
            ThemeManager::instance().setPresetByIndex(index);
    });
    connect(settingsPage_, &SettingsPage::usePresetAccentChanged, this, [](bool enabled) {
        ThemeManager::instance().setUsePresetAccent(enabled);
    });
    connect(settingsPage_, &SettingsPage::chooseAccentColorRequested, this, [this]() {
        const QColor chosen = QColorDialog::getColor(
            ThemeManager::instance().accentColor(),
            this,
            QStringLiteral("Choose SpellVision Accent"));
        if (!chosen.isValid())
            return;

        ThemeManager::instance().setUsePresetAccent(false);
        ThemeManager::instance().setAccentOverride(chosen);
    });
    connect(settingsPage_, &SettingsPage::effectsWeightChanged, this, [](int value) {
        ThemeManager::instance().setEffectsWeight(value);
    });
    connect(settingsPage_, &SettingsPage::restoreDefaultsRequested, this, []() {
        ThemeManager::instance().setPresetByIndex(0);
        ThemeManager::instance().setUsePresetAccent(true);
        ThemeManager::instance().setEffectsWeight(68);
    });
}

void MainWindow::connectGenerationPage(ImageGenerationPage *page, const QString &modeId)
{
    if (!page)
        return;

    connect(page, &ImageGenerationPage::openModelsRequested, this, [this]() { switchToMode(QStringLiteral("models")); });
    connect(page, &ImageGenerationPage::openWorkflowsRequested, this, [this]() { switchToMode(QStringLiteral("workflows")); });

    connect(page, &ImageGenerationPage::queueRequested, this, [this, modeId](const QJsonObject &payload) {
        QueueItem item;
        item.id = QStringLiteral("%1-%2").arg(modeId, QString::number(queueManager_->count() + 1));
        item.command = payload.value(QStringLiteral("mode")).toString().toUpper();
        item.prompt = payload.value(QStringLiteral("prompt")).toString();
        item.model = payload.value(QStringLiteral("model")).toString();
        item.steps = payload.value(QStringLiteral("steps")).toInt(30);
        item.currentStep = 0;
        item.state = QueueItemState::Queued;
        item.statusText = QStringLiteral("queued from workspace");
        item.createdAt = QDateTime::currentDateTimeUtc();
        item.updatedAt = item.createdAt;
        queueManager_->addItem(item);
    });

    connect(page, &ImageGenerationPage::generateRequested, this, [this, modeId](const QJsonObject &payload) {
        QueueItem item;
        item.id = QStringLiteral("%1-run-%2").arg(modeId, QString::number(queueManager_->count() + 1));
        item.command = payload.value(QStringLiteral("mode")).toString().toUpper();
        item.prompt = payload.value(QStringLiteral("prompt")).toString();
        item.model = payload.value(QStringLiteral("model")).toString();
        item.steps = payload.value(QStringLiteral("steps")).toInt(30);
        item.currentStep = qMin(6, item.steps);
        item.state = QueueItemState::Running;
        item.statusText = QStringLiteral("generating");
        item.running = true;
        item.createdAt = QDateTime::currentDateTimeUtc();
        item.startedAt = item.createdAt;
        item.updatedAt = item.createdAt;
        queueManager_->addItem(item);
    });
}

void MainWindow::buildPersistentDocks()
{
    detailsDock_ = new QDockWidget(QStringLiteral("Details"), this);
    detailsDock_->setObjectName(QStringLiteral("DetailsDock"));
    detailsDock_->setAllowedAreas(Qt::RightDockWidgetArea);
    detailsDock_->setWidget(createDetailsWidget());
    addDockWidget(Qt::RightDockWidgetArea, detailsDock_);

    queueDock_ = new QDockWidget(QStringLiteral("Queue"), this);
    queueDock_->setObjectName(QStringLiteral("QueueDock"));
    queueDock_->setAllowedAreas(Qt::BottomDockWidgetArea);
    queueDock_->setWidget(createQueueWidget());
    addDockWidget(Qt::BottomDockWidgetArea, queueDock_);

    logsDock_ = new QDockWidget(QStringLiteral("Logs"), this);
    logsDock_->setObjectName(QStringLiteral("LogsDock"));
    logsDock_->setAllowedAreas(Qt::BottomDockWidgetArea);
    logsDock_->setWidget(createLogsWidget());
    addDockWidget(Qt::BottomDockWidgetArea, logsDock_);

    splitDockWidget(queueDock_, logsDock_, Qt::Horizontal);
    resizeDocks({queueDock_, logsDock_}, {900, 420}, Qt::Horizontal);
    resizeDocks({detailsDock_}, {180}, Qt::Horizontal);
}

void MainWindow::buildBottomTelemetryBar()
{
    auto *bar = statusBar();
    bar->setSizeGripEnabled(false);

    bottomReadyLabel_ = new QLabel(QStringLiteral("READY"), this);
    bottomPageLabel_ = new QLabel(QStringLiteral("SpellVision ready."), this);
    bottomRuntimeLabel_ = new QLabel(QStringLiteral("Runtime: Managed ComfyUI"), this);
    bottomQueueLabel_ = new QLabel(QStringLiteral("Queue: 0 running | 0 pending"), this);
    bottomVramLabel_ = new QLabel(QStringLiteral("VRAM: 0 / 0 GB"), this);
    bottomModelLabel_ = new QLabel(QStringLiteral("Model: none"), this);
    bottomLoraLabel_ = new QLabel(QStringLiteral("LoRA: none"), this);
    bottomStateLabel_ = new QLabel(QStringLiteral("Idle"), this);

    bottomProgressBar_ = new QProgressBar(this);
    bottomProgressBar_->setObjectName(QStringLiteral("BottomTelemetryProgressBar"));
    bottomProgressBar_->setFixedHeight(12);
    bottomProgressBar_->setFixedWidth(164);
    bottomProgressBar_->setTextVisible(false);
    bottomProgressBar_->setRange(0, 100);
    bottomProgressBar_->setValue(0);

    bar->addWidget(bottomReadyLabel_);
    bar->addWidget(new QLabel(QStringLiteral("|"), this));
    bar->addWidget(bottomPageLabel_, 1);

    for (QLabel *label : {bottomRuntimeLabel_, bottomQueueLabel_, bottomVramLabel_, bottomModelLabel_, bottomLoraLabel_, bottomStateLabel_})
    {
        bar->addPermanentWidget(new QLabel(QStringLiteral("|"), this));
        bar->addPermanentWidget(label);
    }
    bar->addPermanentWidget(bottomProgressBar_);
}

QWidget *MainWindow::createQueueWidget()
{
    auto *wrap = new QWidget(this);
    wrap->setMinimumWidth(188);
    auto *layout = new QVBoxLayout(wrap);
    layout->setContentsMargins(10, 10, 10, 10);
    layout->setSpacing(10);

    auto *activeStrip = createPanelFrame(QStringLiteral("QueueActiveStrip"), wrap);
    auto *activeLayout = new QVBoxLayout(activeStrip);
    activeLayout->setContentsMargins(12, 12, 12, 12);
    activeLayout->setSpacing(4);

    auto *activeEyebrow = new QLabel(QStringLiteral("Active Job"), activeStrip);
    activeEyebrow->setObjectName(QStringLiteral("QueueActiveEyebrow"));
    activeQueueTitleLabel_ = new QLabel(QStringLiteral("No active work"), activeStrip);
    activeQueueTitleLabel_->setObjectName(QStringLiteral("QueueActiveTitle"));
    activeQueueSummaryLabel_ = new QLabel(QStringLiteral("Queue items appear here with drag-ready table controls underneath."), activeStrip);
    activeQueueSummaryLabel_->setWordWrap(true);
    activeQueueSummaryLabel_->setObjectName(QStringLiteral("QueueActiveBody"));

    activeLayout->addWidget(activeEyebrow);
    activeLayout->addWidget(activeQueueTitleLabel_);
    activeLayout->addWidget(activeQueueSummaryLabel_);
    layout->addWidget(activeStrip);

    auto *controlsRow = new QHBoxLayout;
    controlsRow->setContentsMargins(0, 0, 0, 0);
    controlsRow->setSpacing(8);

    queueSearchEdit_ = new QLineEdit(wrap);
    queueSearchEdit_->setPlaceholderText(QStringLiteral("Search queue"));
    queueStateFilter_ = new QComboBox(wrap);
    queueStateFilter_->addItems({
        QStringLiteral("All states"),
        QStringLiteral("queued"),
        QStringLiteral("running"),
        QStringLiteral("completed"),
        QStringLiteral("failed"),
        QStringLiteral("cancelled")
    });

    auto *moveUpButton = new QPushButton(QStringLiteral("Up"), wrap);
    auto *moveDownButton = new QPushButton(QStringLiteral("Down"), wrap);
    auto *duplicateButton = new QPushButton(QStringLiteral("Duplicate"), wrap);
    auto *cancelAllButton = new QPushButton(QStringLiteral("Cancel All"), wrap);

    controlsRow->addWidget(queueSearchEdit_, 1);
    controlsRow->addWidget(queueStateFilter_);
    controlsRow->addWidget(moveUpButton);
    controlsRow->addWidget(moveDownButton);
    controlsRow->addWidget(duplicateButton);
    controlsRow->addWidget(cancelAllButton);
    layout->addLayout(controlsRow);

    queueTableModel_ = new QueueTableModel(queueManager_, this);
    queueFilterProxyModel_ = new QueueFilterProxyModel(this);
    queueFilterProxyModel_->setSourceModel(queueTableModel_);
    queueFilterProxyModel_->setSortRole(Qt::DisplayRole);

    queueTableView_ = new QTableView(wrap);
    queueTableView_->setModel(queueFilterProxyModel_);
    queueTableView_->setSortingEnabled(false);
    queueTableView_->setSelectionBehavior(QAbstractItemView::SelectRows);
    queueTableView_->setSelectionMode(QAbstractItemView::SingleSelection);
    queueTableView_->setAlternatingRowColors(true);
    queueTableView_->setWordWrap(false);
    queueTableView_->verticalHeader()->hide();
    queueTableView_->horizontalHeader()->setStretchLastSection(true);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::StateColumn, QHeaderView::ResizeToContents);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::CommandColumn, QHeaderView::ResizeToContents);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::PromptColumn, QHeaderView::Stretch);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::ProgressColumn, QHeaderView::ResizeToContents);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::StatusColumn, QHeaderView::ResizeToContents);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::QueueIdColumn, QHeaderView::ResizeToContents);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::UpdatedAtColumn, QHeaderView::ResizeToContents);
    layout->addWidget(queueTableView_, 1);

    connect(queueSearchEdit_, &QLineEdit::textChanged, queueFilterProxyModel_, &QueueFilterProxyModel::setTextFilter);
    connect(queueStateFilter_, &QComboBox::currentTextChanged, queueFilterProxyModel_, &QueueFilterProxyModel::setStateFilter);
    connect(queueTableView_->selectionModel(), &QItemSelectionModel::selectionChanged, this, [this]() {
        refreshDetailsPanel();
    });

    const auto selectedId = [this]() -> QString {
        return selectedQueueId();
    };

    connect(moveUpButton, &QPushButton::clicked, this, [this, selectedId]() {
        const QString id = selectedId();
        if (id.isEmpty())
            return;
        queueManager_->moveUp(id);
    });
    connect(moveDownButton, &QPushButton::clicked, this, [this, selectedId]() {
        const QString id = selectedId();
        if (id.isEmpty())
            return;
        queueManager_->moveDown(id);
    });
    connect(duplicateButton, &QPushButton::clicked, this, [this, selectedId]() {
        const QString id = selectedId();
        if (id.isEmpty())
            return;
        queueManager_->duplicate(id);
    });
    connect(cancelAllButton, &QPushButton::clicked, this, [this]() {
        queueManager_->cancelAll();
    });

    return wrap;
}

QWidget *MainWindow::createDetailsWidget()
{
    auto *wrap = new QWidget(this);
    wrap->setMinimumWidth(196);
    auto *layout = new QVBoxLayout(wrap);
    layout->setContentsMargins(8, 8, 8, 8);
    layout->setSpacing(8);

    auto *summaryCard = createPanelFrame(QStringLiteral("DetailsSummaryCard"), wrap);
    auto *summaryLayout = new QVBoxLayout(summaryCard);
    summaryLayout->setContentsMargins(10, 10, 10, 10);
    summaryLayout->setSpacing(6);

    auto *eyebrow = new QLabel(QStringLiteral("Inspector"), summaryCard);
    eyebrow->setObjectName(QStringLiteral("DetailsEyebrow"));
    detailsTitleLabel_ = new QLabel(QStringLiteral("Home ready."), summaryCard);
    detailsTitleLabel_->setObjectName(QStringLiteral("DetailsTitle"));
    detailsBodyLabel_ = new QLabel(QStringLiteral("Use this dock for contextual details, queue metadata, and quick routing while you work."), summaryCard);
    detailsBodyLabel_->setWordWrap(true);
    detailsBodyLabel_->setObjectName(QStringLiteral("DetailsBody"));

    auto *metaGrid = new QGridLayout;
    metaGrid->setContentsMargins(0, 2, 0, 0);
    metaGrid->setHorizontalSpacing(10);
    metaGrid->setVerticalSpacing(6);

    auto addMetaRow = [&](int row, const QString &labelText, QLabel **valueLabel) {
        auto *label = new QLabel(labelText, summaryCard);
        label->setObjectName(QStringLiteral("DetailsMetaLabel"));
        auto *value = new QLabel(summaryCard);
        value->setObjectName(QStringLiteral("DetailsMetaValue"));
        value->setWordWrap(true);
        value->setTextInteractionFlags(Qt::TextSelectableByMouse);
        metaGrid->addWidget(label, row, 0, Qt::AlignTop);
        metaGrid->addWidget(value, row, 1, Qt::AlignTop);
        *valueLabel = value;
    };

    addMetaRow(0, QStringLiteral("Context"), &detailsContextValueLabel_);
    addMetaRow(1, QStringLiteral("Selection"), &detailsSelectionValueLabel_);
    addMetaRow(2, QStringLiteral("Queue"), &detailsQueueValueLabel_);
    addMetaRow(3, QStringLiteral("Status"), &detailsStatusValueLabel_);
    metaGrid->setColumnStretch(1, 1);

    summaryLayout->addWidget(eyebrow);
    summaryLayout->addWidget(detailsTitleLabel_);
    summaryLayout->addWidget(detailsBodyLabel_);
    summaryLayout->addLayout(metaGrid);
    layout->addWidget(summaryCard);

    auto *actionsCard = createPanelFrame(QStringLiteral("DetailsActionCard"), wrap);
    auto *actionsLayout = new QVBoxLayout(actionsCard);
    actionsLayout->setContentsMargins(10, 10, 10, 10);
    actionsLayout->setSpacing(6);

    auto *actionsTitle = new QLabel(QStringLiteral("Quick Actions"), actionsCard);
    actionsTitle->setObjectName(QStringLiteral("DetailsSubTitle"));
    actionsLayout->addWidget(actionsTitle);

    detailsPrimaryActionButton_ = new QPushButton(actionsCard);
    detailsSecondaryActionButton_ = new QPushButton(actionsCard);
    detailsTertiaryActionButton_ = new QPushButton(actionsCard);

    detailsPrimaryActionButton_->setObjectName(QStringLiteral("DetailsPrimaryActionButton"));
    detailsSecondaryActionButton_->setObjectName(QStringLiteral("DetailsSecondaryActionButton"));
    detailsTertiaryActionButton_->setObjectName(QStringLiteral("DetailsSecondaryActionButton"));

    for (QPushButton *button : {detailsPrimaryActionButton_, detailsSecondaryActionButton_, detailsTertiaryActionButton_})
    {
        button->setMinimumHeight(28);
        button->setMaximumHeight(32);
        actionsLayout->addWidget(button);
    }
    actionsLayout->addStretch(1);

    connect(detailsPrimaryActionButton_, &QPushButton::clicked, this, [this]() { triggerDetailsAction(detailsPrimaryActionId_); });
    connect(detailsSecondaryActionButton_, &QPushButton::clicked, this, [this]() { triggerDetailsAction(detailsSecondaryActionId_); });
    connect(detailsTertiaryActionButton_, &QPushButton::clicked, this, [this]() { triggerDetailsAction(detailsTertiaryActionId_); });

    layout->addWidget(actionsCard, 0);
    layout->addStretch(1);

    refreshDetailsPanel();
    return wrap;
}



QWidget *MainWindow::createLogsWidget()
{
    auto *wrap = new QWidget(this);
    wrap->setMinimumWidth(188);

    auto *layout = new QVBoxLayout(wrap);
    layout->setContentsMargins(10, 10, 10, 10);
    layout->setSpacing(8);

    auto *card = createPanelFrame(QStringLiteral("LogsPanel"), wrap);
    auto *cardLayout = new QVBoxLayout(card);
    cardLayout->setContentsMargins(10, 10, 10, 10);
    cardLayout->setSpacing(6);

    auto *eyebrow = new QLabel(QStringLiteral("Runtime Log"), card);
    eyebrow->setObjectName(QStringLiteral("DetailsEyebrow"));

    logsView_ = new QTextEdit(card);
    logsView_->setReadOnly(true);
    logsView_->setObjectName(QStringLiteral("LogsView"));
    logsView_->setPlainText(
        QStringLiteral("SpellVision shell initialized.\n")
        + QStringLiteral("Custom title bar active.\n")
        + QStringLiteral("Right dock inspector wired.\n")
        + QStringLiteral("Bottom telemetry bar authoritative."));

    cardLayout->addWidget(eyebrow);
    cardLayout->addWidget(logsView_, 1);
    layout->addWidget(card, 1);

    return wrap;
}

void MainWindow::switchToMode(const QString &modeId)
{
    if (modeId == QStringLiteral("home"))
        pageStack_->setCurrentWidget(homePage_);
    else if (modeId == QStringLiteral("workflows"))
        pageStack_->setCurrentWidget(workflowsPage_);
    else if (modeId == QStringLiteral("history"))
        pageStack_->setCurrentWidget(historyPage_);
    else if (modeId == QStringLiteral("inspiration"))
        pageStack_->setCurrentWidget(inspirationPage_);
    else if (modeId == QStringLiteral("models"))
        pageStack_->setCurrentWidget(modelsPage_);
    else if (modeId == QStringLiteral("settings"))
        pageStack_->setCurrentWidget(settingsPage_);
    else if (modeId == QStringLiteral("t2i"))
        pageStack_->setCurrentWidget(t2iPage_);
    else if (modeId == QStringLiteral("i2i"))
        pageStack_->setCurrentWidget(i2iPage_);
    else if (modeId == QStringLiteral("t2v"))
        pageStack_->setCurrentWidget(t2vPage_);
    else if (modeId == QStringLiteral("i2v"))
        pageStack_->setCurrentWidget(i2vPage_);
    else
        pageStack_->setCurrentWidget(homePage_);

    currentModeId_ = modeId.trimmed().isEmpty() ? QStringLiteral("home") : modeId;
    updateModeButtonState(currentModeId_);
    const QString contextText = pageContextForMode(currentModeId_);
    setBottomPageContext(contextText);
    if (titleBar_)
        titleBar_->setContextText(contextText);
    applyShellStateForMode(currentModeId_);

    if (logsView_)
        logsView_->append(QStringLiteral("Switched to %1.").arg(contextText));

    syncBottomTelemetry();
    refreshDetailsPanel();
}

void MainWindow::openManager(const QString &managerId)
{
    if (managerId == QStringLiteral("workflows"))
    {
        switchToMode(QStringLiteral("workflows"));
        return;
    }
    if (managerId == QStringLiteral("models") || managerId == QStringLiteral("downloads"))
    {
        switchToMode(QStringLiteral("models"));
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

    switchToMode(QStringLiteral("workflows"));
}

void MainWindow::syncBottomTelemetry()
{
    if (!queueManager_)
        return;

    int runningCount = 0;
    int pendingCount = 0;
    int failedCount = 0;
    int progressValue = 0;
    QString stateText = QStringLiteral("Idle");
    QString modelText = QStringLiteral("Model: none");

    QueueItem activeItem;
    bool activeFound = false;

    for (const QueueItem &item : queueManager_->items())
    {
        if (item.state == QueueItemState::Running)
        {
            ++runningCount;
            if (!activeFound)
            {
                activeItem = item;
                activeFound = true;
            }
        }
        if (item.isPendingLike())
            ++pendingCount;
        if (item.state == QueueItemState::Failed)
            ++failedCount;
    }

    if (activeFound)
    {
        progressValue = activeItem.progressPercent();
        stateText = QStringLiteral("%1 • %2").arg(queueStateDisplay(activeItem.state), activeItem.command);
        if (!activeItem.model.trimmed().isEmpty())
            modelText = QStringLiteral("Model: %1").arg(activeItem.model);
    }
    else if (failedCount > 0)
    {
        stateText = QStringLiteral("Attention");
    }

    if (bottomRuntimeLabel_)
        bottomRuntimeLabel_->setText(QStringLiteral("Runtime: Managed ComfyUI"));
    if (bottomQueueLabel_)
        bottomQueueLabel_->setText(QStringLiteral("Queue: %1 running | %2 pending | %3 errors").arg(runningCount).arg(pendingCount).arg(failedCount));
    if (bottomVramLabel_)
        bottomVramLabel_->setText(QStringLiteral("VRAM: 0 / 0 GB"));
    if (bottomModelLabel_)
        bottomModelLabel_->setText(modelText);
    if (bottomLoraLabel_)
        bottomLoraLabel_->setText(QStringLiteral("LoRA: none"));
    if (bottomStateLabel_)
        bottomStateLabel_->setText(stateText);
    if (bottomProgressBar_)
        bottomProgressBar_->setValue(progressValue);

    if (homePage_)
    {
        homePage_->setRuntimeSummary(
            QStringLiteral("Managed ComfyUI"),
            runningCount,
            pendingCount,
            failedCount,
            QStringLiteral("0 / 0 GB"),
            modelText.mid(QStringLiteral("Model: ").size()),
            QStringLiteral("none"),
            stateText,
            progressValue);
    }

    updateActiveQueueStrip();
}

void MainWindow::onQueueChanged()
{
    updateActiveQueueStrip();
    syncBottomTelemetry();
    refreshDetailsPanel();
}

void MainWindow::showTitleBarMenu(const QString &menuId, const QPoint &globalPos)
{
    QMenu menu(this);

    if (menuId == QStringLiteral("file"))
    {
        menu.addAction(QStringLiteral("Command Palette"), this, &MainWindow::showCommandPalette);
        menu.addSeparator();
        menu.addAction(QStringLiteral("Exit"), this, &QWidget::close);
    }
    else if (menuId == QStringLiteral("edit"))
    {
        menu.addAction(QStringLiteral("Command Palette"), this, &MainWindow::showCommandPalette);
    }
    else if (menuId == QStringLiteral("view"))
    {
        menu.addAction(QStringLiteral("Toggle Left Rail"), this, &MainWindow::togglePrimarySidebar);
        menu.addAction(QStringLiteral("Toggle Bottom Panels"), this, &MainWindow::toggleBottomPanels);
        menu.addAction(QStringLiteral("Toggle Details Dock"), this, &MainWindow::toggleDetailsPanel);
    }
    else if (menuId == QStringLiteral("generation"))
    {
        menu.addAction(QStringLiteral("Text to Image"), this, [this]() { switchToMode(QStringLiteral("t2i")); });
        menu.addAction(QStringLiteral("Image to Image"), this, [this]() { switchToMode(QStringLiteral("i2i")); });
        menu.addAction(QStringLiteral("Text to Video"), this, [this]() { switchToMode(QStringLiteral("t2v")); });
        menu.addAction(QStringLiteral("Image to Video"), this, [this]() { switchToMode(QStringLiteral("i2v")); });
    }
    else if (menuId == QStringLiteral("models"))
    {
        menu.addAction(QStringLiteral("Open Models"), this, [this]() { switchToMode(QStringLiteral("models")); });
        menu.addAction(QStringLiteral("Open Settings"), this, [this]() { switchToMode(QStringLiteral("settings")); });
    }
    else if (menuId == QStringLiteral("workflows"))
    {
        menu.addAction(QStringLiteral("Open Workflow Library"), this, [this]() { switchToMode(QStringLiteral("workflows")); });
        menu.addAction(QStringLiteral("Open History"), this, [this]() { switchToMode(QStringLiteral("history")); });
    }
    else if (menuId == QStringLiteral("tools"))
    {
        menu.addAction(QStringLiteral("Queue"), this, [this]() { if (queueDock_) queueDock_->show(); });
        menu.addAction(QStringLiteral("Logs"), this, [this]() { if (logsDock_) logsDock_->show(); });
        menu.addAction(QStringLiteral("Details"), this, [this]() { if (detailsDock_) detailsDock_->show(); });
    }
    else if (menuId == QStringLiteral("help"))
    {
        menu.addAction(QStringLiteral("Home"), this, [this]() { switchToMode(QStringLiteral("home")); });
        menu.addAction(QStringLiteral("Command Palette"), this, &MainWindow::showCommandPalette);
    }

    menu.exec(globalPos);
}

void MainWindow::showLayoutMenu(const QPoint &globalPos)
{
    QMenu menu(this);
    menu.addAction(QStringLiteral("Creation Layout"), this, [this]() {
        if (detailsDock_)
            detailsDock_->show();
        if (queueDock_)
            queueDock_->show();
        if (logsDock_)
            logsDock_->hide();
    });
    menu.addAction(QStringLiteral("Review Layout"), this, [this]() {
        if (detailsDock_)
            detailsDock_->show();
        if (queueDock_)
            queueDock_->show();
        if (logsDock_)
            logsDock_->show();
    });
    menu.addAction(QStringLiteral("Focus Canvas"), this, [this]() {
        if (detailsDock_)
            detailsDock_->hide();
        if (queueDock_)
            queueDock_->hide();
        if (logsDock_)
            logsDock_->hide();
    });
    menu.exec(globalPos);
}

void MainWindow::showSystemMenu(const QPoint &globalPos)
{
#ifdef Q_OS_WIN
    const HWND hwnd = reinterpret_cast<HWND>(winId());
    if (!hwnd)
        return;

    HMENU menu = GetSystemMenu(hwnd, FALSE);
    if (!menu)
        return;

    const UINT command = TrackPopupMenu(
        menu,
        TPM_RETURNCMD | TPM_LEFTALIGN | TPM_TOPALIGN | TPM_RIGHTBUTTON,
        globalPos.x(),
        globalPos.y(),
        0,
        hwnd,
        nullptr);

    if (command != 0)
        PostMessageW(hwnd, WM_SYSCOMMAND, command, 0);
#else
    QMenu menu(this);
    menu.addAction(isMaximized() ? QStringLiteral("Restore") : QStringLiteral("Maximize"), this, [this]() {
        isMaximized() ? showNormal() : showMaximized();
    });
    menu.addAction(QStringLiteral("Minimize"), this, &QWidget::showMinimized);
    menu.addSeparator();
    menu.addAction(QStringLiteral("Close"), this, &QWidget::close);
    menu.exec(globalPos);
#endif
}

void MainWindow::showCommandPalette()
{
    if (!commandPaletteDialog_)
    {
        commandPaletteDialog_ = new CommandPaletteDialog(this);
        connect(commandPaletteDialog_, &CommandPaletteDialog::commandTriggered, this, &MainWindow::triggerCommand);
    }

    commandPaletteDialog_->setCommands({
        QStringLiteral("Go to Home"),
        QStringLiteral("Open Text to Image"),
        QStringLiteral("Open Image to Image"),
        QStringLiteral("Open Text to Video"),
        QStringLiteral("Open Image to Video"),
        QStringLiteral("Open Workflows"),
        QStringLiteral("Open History"),
        QStringLiteral("Open Inspiration"),
        QStringLiteral("Open Models"),
        QStringLiteral("Open Settings"),
        QStringLiteral("Toggle Left Rail"),
        QStringLiteral("Toggle Bottom Panels"),
        QStringLiteral("Toggle Details Dock")
    });

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
    if (normalized.contains(QStringLiteral("left rail")))
    {
        togglePrimarySidebar();
        return;
    }
    if (normalized.contains(QStringLiteral("bottom panels")))
    {
        toggleBottomPanels();
        return;
    }
    if (normalized.contains(QStringLiteral("details dock")))
    {
        toggleDetailsPanel();
        return;
    }
}



bool MainWindow::nativeEvent(const QByteArray &eventType, void *message, qintptr *result)
{
#ifdef Q_OS_WIN
    Q_UNUSED(eventType);

    if (!message)
        return false;

    MSG *msg = static_cast<MSG *>(message);
    if (!msg)
        return false;

    const LONG frameX = GetSystemMetrics(SM_CXSIZEFRAME) + GetSystemMetrics(SM_CXPADDEDBORDER);
    const LONG frameY = GetSystemMetrics(SM_CYSIZEFRAME) + GetSystemMetrics(SM_CXPADDEDBORDER);

    switch (msg->message)
    {
    case WM_NCCALCSIZE:
        if (result)
            *result = 0;
        return true;

    case WM_GETMINMAXINFO:
    {
        auto *mmi = reinterpret_cast<MINMAXINFO *>(msg->lParam);
        if (!mmi)
            break;

        const HMONITOR monitor = MonitorFromWindow(reinterpret_cast<HWND>(winId()), MONITOR_DEFAULTTONEAREST);
        if (!monitor)
            break;

        MONITORINFO monitorInfo{};
        monitorInfo.cbSize = sizeof(MONITORINFO);
        if (!GetMonitorInfoW(monitor, &monitorInfo))
            break;

        const RECT &work = monitorInfo.rcWork;
        const RECT &monitorRect = monitorInfo.rcMonitor;
        mmi->ptMaxPosition.x = work.left - monitorRect.left;
        mmi->ptMaxPosition.y = work.top - monitorRect.top;
        mmi->ptMaxSize.x = work.right - work.left;
        mmi->ptMaxSize.y = work.bottom - work.top;
        if (result)
            *result = 0;
        return true;
    }

    case WM_NCHITTEST:
    {
        if (!result)
            break;

        const POINT globalPoint{GET_X_LPARAM(msg->lParam), GET_Y_LPARAM(msg->lParam)};
        RECT windowRect{};
        if (!GetWindowRect(reinterpret_cast<HWND>(winId()), &windowRect))
            break;

        if (!isMaximized())
        {
            const bool onLeft = globalPoint.x >= windowRect.left && globalPoint.x < windowRect.left + frameX;
            const bool onRight = globalPoint.x < windowRect.right && globalPoint.x >= windowRect.right - frameX;
            const bool onTop = globalPoint.y >= windowRect.top && globalPoint.y < windowRect.top + frameY;
            const bool onBottom = globalPoint.y < windowRect.bottom && globalPoint.y >= windowRect.bottom - frameY;

            if (onTop && onLeft)
            {
                *result = HTTOPLEFT;
                return true;
            }
            if (onTop && onRight)
            {
                *result = HTTOPRIGHT;
                return true;
            }
            if (onBottom && onLeft)
            {
                *result = HTBOTTOMLEFT;
                return true;
            }
            if (onBottom && onRight)
            {
                *result = HTBOTTOMRIGHT;
                return true;
            }
            if (onLeft)
            {
                *result = HTLEFT;
                return true;
            }
            if (onRight)
            {
                *result = HTRIGHT;
                return true;
            }
            if (onTop)
            {
                *result = HTTOP;
                return true;
            }
            if (onBottom)
            {
                *result = HTBOTTOM;
                return true;
            }
        }

        if (titleBar_)
        {
            const QPoint titleLocal = titleBar_->mapFromGlobal(QPoint(globalPoint.x, globalPoint.y));
            if (QRect(QPoint(0, 0), titleBar_->size()).contains(titleLocal) && titleBar_->isDraggableArea(titleLocal))
            {
                *result = HTCAPTION;
                return true;
            }
        }
        break;
    }

    case WM_NCRBUTTONUP:
        if (result && msg->wParam == HTCAPTION)
        {
            showSystemMenu(QPoint(GET_X_LPARAM(msg->lParam), GET_Y_LPARAM(msg->lParam)));
            *result = 0;
            return true;
        }
        break;

    default:
        break;
    }
#else
    Q_UNUSED(eventType);
    Q_UNUSED(message);
    Q_UNUSED(result);
#endif

    return QMainWindow::nativeEvent(eventType, message, result);
}

void MainWindow::changeEvent(QEvent *event)
{
    QMainWindow::changeEvent(event);
    if (titleBar_)
        titleBar_->setMaximized(isMaximized());
}

void MainWindow::togglePrimarySidebar()
{
    if (!sideRail_)
        return;

    sideRail_->setVisible(!sideRail_->isVisible());
}

void MainWindow::toggleBottomPanels()
{
    if (!queueDock_ || !logsDock_)
        return;

    const bool shouldShow = !queueDock_->isVisible() || !logsDock_->isVisible();
    queueDock_->setVisible(shouldShow);
    logsDock_->setVisible(shouldShow);
}

void MainWindow::toggleDetailsPanel()
{
    if (!detailsDock_)
        return;

    detailsDock_->setVisible(!detailsDock_->isVisible());
}

void MainWindow::applyShellStateForMode(const QString &modeId)
{
    const bool isHome = (modeId == QStringLiteral("home"));
    const bool isSettings = (modeId == QStringLiteral("settings"));
    const bool isCreation = (modeId == QStringLiteral("t2i") ||
                             modeId == QStringLiteral("i2i") ||
                             modeId == QStringLiteral("t2v") ||
                             modeId == QStringLiteral("i2v"));

    if (detailsDock_)
        detailsDock_->setVisible(!isSettings);

    if (queueDock_)
        queueDock_->setVisible(!isHome);
    if (logsDock_)
        logsDock_->setVisible(!isHome && !isCreation);

    if (isCreation && queueDock_)
        queueDock_->raise();
    if (isCreation && detailsDock_)
        detailsDock_->raise();
}

void MainWindow::setBottomPageContext(const QString &text)
{
    if (bottomPageLabel_)
        bottomPageLabel_->setText(text);
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
        detailsPrimaryActionButton_->setEnabled(!primaryId.trimmed().isEmpty());
    }
    if (detailsSecondaryActionButton_)
    {
        detailsSecondaryActionButton_->setText(secondaryText);
        detailsSecondaryActionButton_->setVisible(!secondaryText.trimmed().isEmpty());
        detailsSecondaryActionButton_->setEnabled(!secondaryId.trimmed().isEmpty());
    }
    if (detailsTertiaryActionButton_)
    {
        detailsTertiaryActionButton_->setText(tertiaryText);
        detailsTertiaryActionButton_->setVisible(!tertiaryText.trimmed().isEmpty());
        detailsTertiaryActionButton_->setEnabled(!tertiaryId.trimmed().isEmpty());
    }
}

void MainWindow::triggerDetailsAction(const QString &actionId)
{
    const QString normalized = actionId.trimmed();
    if (normalized.isEmpty())
        return;

    if (normalized.startsWith(QStringLiteral("mode:")))
    {
        switchToMode(normalized.mid(5));
        return;
    }
    if (normalized.startsWith(QStringLiteral("manager:")))
    {
        openManager(normalized.mid(8));
        return;
    }
    if (normalized == QStringLiteral("toggle:queue"))
    {
        if (queueDock_)
        {
            queueDock_->show();
            queueDock_->raise();
        }
        return;
    }
    if (normalized == QStringLiteral("queue:duplicate"))
    {
        const QString id = selectedQueueId();
        if (!id.isEmpty())
            queueManager_->duplicate(id);
        return;
    }
    if (normalized == QStringLiteral("queue:moveup"))
    {
        const QString id = selectedQueueId();
        if (!id.isEmpty())
            queueManager_->moveUp(id);
        return;
    }
}

void MainWindow::refreshDetailsPanel()
{
    if (!detailsTitleLabel_ || !detailsBodyLabel_)
        return;

    if (!selectedQueueId().isEmpty())
    {
        updateDetailsPanelForQueueSelection();
        return;
    }

    updateDetailsPanelForModeContext();
}

void MainWindow::updateDetailsPanelForModeContext()
{
    if (!detailsTitleLabel_ || !detailsBodyLabel_)
        return;

    int runningCount = 0;
    int pendingCount = 0;
    int failedCount = 0;
    if (queueManager_)
    {
        for (const QueueItem &item : queueManager_->items())
        {
            if (item.state == QueueItemState::Running)
                ++runningCount;
            if (item.isPendingLike())
                ++pendingCount;
            if (item.state == QueueItemState::Failed)
                ++failedCount;
        }
    }

    const QString contextText = pageContextForMode(currentModeId_);
    detailsTitleLabel_->setText(contextText);

    QString selectionText = QStringLiteral("Workspace");
    QString bodyText = QStringLiteral("Use this dock for contextual details, queue metadata, and quick routing while you work.");

    if (currentModeId_ == QStringLiteral("home"))
    {
        selectionText = QStringLiteral("Launcher");
        bodyText = QStringLiteral("Home is focused on launch surfaces, workflow previews, and discovery rails rather than telemetry.");
        configureDetailsActions(QStringLiteral("mode:t2i"), QStringLiteral("Open T2I"),
                                QStringLiteral("manager:workflows"), QStringLiteral("Open Workflows"),
                                QStringLiteral("manager:history"), QStringLiteral("Open History"));
    }
    else if (currentModeId_ == QStringLiteral("t2i") || currentModeId_ == QStringLiteral("i2i"))
    {
        selectionText = currentModeId_ == QStringLiteral("t2i") ? QStringLiteral("Prompt-first canvas") : QStringLiteral("Restyle canvas");
        bodyText = QStringLiteral("Keep the model stack visible, use the queue for long jobs, and route dependencies through models and workflows.");
        configureDetailsActions(QStringLiteral("manager:models"), QStringLiteral("Open Models"),
                                QStringLiteral("manager:workflows"), QStringLiteral("Open Workflows"),
                                QStringLiteral("toggle:queue"), QStringLiteral("Show Queue"));
    }
    else if (currentModeId_ == QStringLiteral("t2v") || currentModeId_ == QStringLiteral("i2v"))
    {
        selectionText = QStringLiteral("Motion workspace");
        bodyText = QStringLiteral("Use this shell as the matched motion placeholder while queue, workflows, and history stay available at the shell level.");
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
    if (!activeQueueTitleLabel_ || !activeQueueSummaryLabel_ || !queueManager_)
        return;

    QueueItem activeItem;
    bool found = false;

    for (const QueueItem &item : queueManager_->items())
    {
        if (item.state == QueueItemState::Running)
        {
            activeItem = item;
            found = true;
            break;
        }
    }

    if (!found)
    {
        for (const QueueItem &item : queueManager_->items())
        {
            if (item.isPendingLike())
            {
                activeItem = item;
                found = true;
                break;
            }
        }
    }

    if (!found)
    {
        activeQueueTitleLabel_->setText(QStringLiteral("No active work"));
        activeQueueSummaryLabel_->setText(QStringLiteral("Queue items appear here with grouped controls and a table-first body below."));
        return;
    }

    activeQueueTitleLabel_->setText(QStringLiteral("%1 • %2").arg(activeItem.command, queueStateDisplay(activeItem.state)));
    activeQueueSummaryLabel_->setText(QStringLiteral("%1\nProgress: %2%%    Queue ID: %3")
                                          .arg(summarizePrompt(activeItem.prompt))
                                          .arg(activeItem.progressPercent())
                                          .arg(activeItem.id));
}

QString MainWindow::selectedQueueId() const
{
    if (!queueTableView_ || !queueFilterProxyModel_)
        return QString();

    const QModelIndex proxyIndex = queueTableView_->currentIndex();
    if (!proxyIndex.isValid())
        return QString();

    const QModelIndex proxyRowIndex = proxyIndex.sibling(proxyIndex.row(), 0);
    if (!proxyRowIndex.isValid())
        return QString();

    const QModelIndex sourceIndex = queueFilterProxyModel_->mapToSource(proxyRowIndex);
    if (!sourceIndex.isValid())
        return QString();

    return queueTableModel_->data(sourceIndex, QueueTableModel::QueueIdRole).toString();
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
