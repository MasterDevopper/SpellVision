#include "ManagerPage.h"
#include "ThemeManager.h"
#include "shell/RuntimeProfile.h"

#include <QAbstractItemView>
#include <QClipboard>
#include <QComboBox>
#include <QCoreApplication>
#include <QGuiApplication>
#include <QDateTime>
#include <QDesktopServices>
#include <QDir>
#include <QDirIterator>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QHeaderView>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonParseError>
#include <QLabel>
#include <QLineEdit>
#include <QList>
#include <QMessageBox>
#include <QPair>
#include <QProcess>
#include <QProcessEnvironment>
#include <QPushButton>
#include <QSaveFile>
#include <QSettings>
#include <QStandardPaths>
#include <QTableWidget>
#include <QTableWidgetItem>
#include <QTextEdit>
#include <QTimer>
#include <QUrl>
#include <QVBoxLayout>

#include "workers/WorkerSocketClient.h"

#include <memory>
#include <utility>

namespace
{
    constexpr qint64 kManagerStatusCacheFreshMs = 5 * 60 * 1000;
    constexpr qint64 kManagerStatusCacheRetainMs = 7LL * 24 * 60 * 60 * 1000;

    QJsonObject g_managerStatusCache;
    qint64 g_managerStatusCacheAtMs = 0;
    QString g_managerStatusCacheOrigin = QStringLiteral("none");

    QLabel *makeLabel(const QString &objectName, const QString &text = QString())
    {
        auto *label = new QLabel(text);
        label->setObjectName(objectName);
        label->setTextInteractionFlags(Qt::TextSelectableByMouse);
        label->setWordWrap(true);
        return label;
    }

    QPushButton *makeButton(const QString &text)
    {
        auto *button = new QPushButton(text);
        button->setCursor(Qt::PointingHandCursor);
        return button;
    }

    QString lastJsonLine(const QString &stdoutText)
    {
        const QStringList lines = stdoutText.split('\n', Qt::SkipEmptyParts);
        for (auto it = lines.crbegin(); it != lines.crend(); ++it)
        {
            const QString candidate = it->trimmed();
            if (candidate.startsWith('{') && candidate.endsWith('}'))
                return candidate;
        }
        return {};
    }

    QString normalizedPath(const QString &path)
    {
        return QDir::fromNativeSeparators(path.trimmed());
    }

    QString boolText(bool value)
    {
        return value ? QStringLiteral("yes") : QStringLiteral("no");
    }

    QString managerStatusCacheFilePath()
    {
        QString base = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation);
        if (base.isEmpty())
            base = QDir(QCoreApplication::applicationDirPath()).filePath(QStringLiteral("runtime/cache/ui"));

        QDir dir(base);
        dir.mkpath(QStringLiteral("."));
        return dir.filePath(QStringLiteral("manager_status_cache.json"));
    }

    bool hasManagerStatusCache()
    {
        return !g_managerStatusCache.isEmpty();
    }

    bool managerStatusCacheFresh()
    {
        return hasManagerStatusCache()
            && g_managerStatusCacheAtMs > 0
            && (QDateTime::currentMSecsSinceEpoch() - g_managerStatusCacheAtMs) < kManagerStatusCacheFreshMs;
    }

    QString managerStatusDisplaySource(const QString &applySource = QString())
    {
        if (!applySource.trimmed().isEmpty())
            return applySource.trimmed();

        if (!hasManagerStatusCache())
            return QStringLiteral("none");

        if (g_managerStatusCacheOrigin == QStringLiteral("disk"))
            return QStringLiteral("disk");

        if (g_managerStatusCacheOrigin == QStringLiteral("live"))
            return QStringLiteral("memory");

        return QStringLiteral("memory");
    }

    QString managerStatusLastCheckedText()
    {
        if (g_managerStatusCacheAtMs <= 0)
            return QStringLiteral("never");

        return QDateTime::fromMSecsSinceEpoch(g_managerStatusCacheAtMs)
            .toLocalTime()
            .toString(QStringLiteral("yyyy-MM-dd hh:mm:ss AP"));
    }

    void tryLoadManagerStatusCacheFromDisk()
    {
        if (hasManagerStatusCache())
            return;

        QFile file(managerStatusCacheFilePath());
        if (!file.exists() || !file.open(QIODevice::ReadOnly))
            return;

        QJsonParseError parseError{};
        const QJsonDocument doc = QJsonDocument::fromJson(file.readAll(), &parseError);
        file.close();

        if (parseError.error != QJsonParseError::NoError || !doc.isObject())
            return;

        const QJsonObject root = doc.object();
        const qint64 cachedAtMs = static_cast<qint64>(root.value(QStringLiteral("cached_at_ms")).toDouble(0.0));
        const QJsonObject payload = root.value(QStringLiteral("payload")).toObject();
        if (payload.isEmpty())
            return;

        if (cachedAtMs > 0 &&
            (QDateTime::currentMSecsSinceEpoch() - cachedAtMs) > kManagerStatusCacheRetainMs)
        {
            QFile::remove(managerStatusCacheFilePath());
            return;
        }

        g_managerStatusCache = payload;
        g_managerStatusCacheAtMs = cachedAtMs > 0 ? cachedAtMs : QDateTime::currentMSecsSinceEpoch();
        g_managerStatusCacheOrigin = QStringLiteral("disk");
    }

    void storeManagerStatusCache(const QJsonObject &payload)
    {
        if (payload.isEmpty())
            return;

        g_managerStatusCache = payload;
        g_managerStatusCacheAtMs = QDateTime::currentMSecsSinceEpoch();
        g_managerStatusCacheOrigin = QStringLiteral("live");

        QSaveFile file(managerStatusCacheFilePath());
        if (!file.open(QIODevice::WriteOnly))
            return;

        const QJsonObject root{
            {QStringLiteral("cached_at_ms"), static_cast<double>(g_managerStatusCacheAtMs)},
            {QStringLiteral("payload"), payload},
        };
        file.write(QJsonDocument(root).toJson(QJsonDocument::Compact));
        file.commit();
    }
}

ManagerPage::ManagerPage(QWidget *parent)
    : QWidget(parent)
{
    setObjectName(QStringLiteral("ManagerPage"));

    auto *outer = new QVBoxLayout(this);
    outer->setContentsMargins(22, 22, 22, 22);
    outer->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Card));

    auto *header = new QLabel(QStringLiteral("Managers / Runtime"), this);
    header->setObjectName(QStringLiteral("PageTitle"));
    outer->addWidget(header);

    auto *subtitle = makeLabel(QStringLiteral("PageSubtitle"),
                               QStringLiteral("Install and verify ComfyUI Manager, custom nodes, and dependency repair surfaces before advanced video features are enabled."));
    outer->addWidget(subtitle);

    auto *actions = new QHBoxLayout();
    actions->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
    refreshButton_ = makeButton(QStringLiteral("Detect / Refresh"));
    installManagerButton_ = makeButton(QStringLiteral("Install Manager"));
    installSelectedButton_ = makeButton(QStringLiteral("Install Selected Node"));
    installMissingVideoButton_ = makeButton(QStringLiteral("Install Missing Video Nodes"));
    restartRuntimeButton_ = makeButton(QStringLiteral("Restart Comfy"));
    // Free VRAM is the lighter recovery that Restart used to be the only route to. When Comfy's
    // memory accounting wedges -- it reported 0.1 GB free against an actual 29.8 GB during this
    // build -- unloading the runtimes and dropping the cache fixes it without losing the process,
    // its warm state, or anything queued behind it. Both worker commands have existed all along
    // with nothing in the UI calling them (Doc 49 section 2).
    freeVramButton_ = makeButton(QStringLiteral("Free VRAM"));
    freeVramButton_->setToolTip(QStringLiteral(
        "Unload the image and video runtimes and clear the CUDA cache.\n\n"
        "Try this before Restart Comfy: it recovers wedged VRAM accounting without "
        "restarting the process."));
    chooseComfyRootButton_ = makeButton(QStringLiteral("Choose Comfy Root"));
    chooseModelsRootButton_ = makeButton(QStringLiteral("Choose Models Root"));
    openComfyButton_ = makeButton(QStringLiteral("Open Comfy Root"));
    openCustomNodesButton_ = makeButton(QStringLiteral("Open custom_nodes"));

    for (QPushButton *button : {refreshButton_, installManagerButton_, installSelectedButton_, installMissingVideoButton_, freeVramButton_, restartRuntimeButton_})
        actions->addWidget(button);
    actions->addStretch(1);
    outer->addLayout(actions);

    auto *statusRow = new QHBoxLayout();
    statusRow->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));

    auto *leftStatus = new QWidget(this);
    auto *leftLayout = new QVBoxLayout(leftStatus);
    leftLayout->setContentsMargins(0, 0, 0, 0);
    leftLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

    managerStateLabel_ = makeLabel(QStringLiteral("ManagerStatusLabel"), QStringLiteral("Manager: not checked"));
    runtimeStateLabel_ = makeLabel(QStringLiteral("ManagerStatusLabel"), QStringLiteral("Runtime: not checked"));
    nodeSummaryLabel_ = makeLabel(QStringLiteral("ManagerStatusLabel"), QStringLiteral("Nodes: not checked"));
    cacheSourceLabel_ = makeLabel(QStringLiteral("ManagerStatusLabel"), QStringLiteral("Cache source: none"));
    lastCheckedLabel_ = makeLabel(QStringLiteral("ManagerStatusLabel"), QStringLiteral("Last checked: never"));

    // ComfyUI version row. The installed version comes from /system_stats (previously fetched and
    // discarded); the latest comes from the Comfy-Org releases API. "Update available" is the only
    // state that offers the button -- an unreachable GitHub reads as unknown, never as up to date.
    auto *versionRow = new QHBoxLayout();
    versionRow->setContentsMargins(0, 0, 0, 0);
    versionRow->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
    comfyVersionLabel_ = makeLabel(QStringLiteral("ManagerStatusLabel"), QStringLiteral("ComfyUI: not checked"));
    updateComfyButton_ = makeButton(QStringLiteral("Update ComfyUI…"));
    updateComfyButton_->setVisible(false);
    versionRow->addWidget(comfyVersionLabel_);
    versionRow->addWidget(updateComfyButton_);
    versionRow->addStretch(1);

    // Most workflows name their own packs and need no index at all. This is for the rest: an older
    // export whose nodes carry no properties gives nothing but a class name, and the ComfyUI
    // Registry has no class->pack lookup, so the mapping has to be assembled once from every pack.
    auto *indexRow = new QHBoxLayout();
    indexRow->setContentsMargins(0, 0, 0, 0);
    indexRow->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
    nodeIndexLabel_ = makeLabel(QStringLiteral("ManagerStatusLabel"), QStringLiteral("Node search index: not built"));
    buildNodeIndexButton_ = makeButton(QStringLiteral("Build node index"));
    buildNodeIndexButton_->setToolTip(QStringLiteral(
        "Reads every pack in the ComfyUI Registry once so a workflow that does not name its own "
        "packs can still be resolved. Takes a few minutes, runs in the background, and resumes "
        "where it stopped."));
    indexRow->addWidget(nodeIndexLabel_);
    indexRow->addWidget(buildNodeIndexButton_);
    indexRow->addStretch(1);

    leftLayout->addWidget(managerStateLabel_);
    leftLayout->addWidget(runtimeStateLabel_);
    leftLayout->addLayout(versionRow);
    leftLayout->addLayout(indexRow);
    leftLayout->addWidget(nodeSummaryLabel_);
    leftLayout->addWidget(cacheSourceLabel_);
    leftLayout->addWidget(lastCheckedLabel_);

    auto *rightStatus = new QWidget(this);
    auto *rightLayout = new QVBoxLayout(rightStatus);
    rightLayout->setContentsMargins(0, 0, 0, 0);
    rightLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
    comfyRootLabel_ = makeLabel(QStringLiteral("ManagerPathLabel"), QStringLiteral("Comfy root: unknown"));
    modelsRootLabel_ = makeLabel(QStringLiteral("ManagerPathLabel"), QStringLiteral("Models root: unknown"));
    managerPathLabel_ = makeLabel(QStringLiteral("ManagerPathLabel"), QStringLiteral("Manager path: unknown"));
    cachePathLabel_ = makeLabel(QStringLiteral("ManagerPathLabel"), QStringLiteral("Cache path: unknown"));
    rightLayout->addWidget(comfyRootLabel_);
    rightLayout->addWidget(modelsRootLabel_);
    rightLayout->addWidget(managerPathLabel_);
    rightLayout->addWidget(cachePathLabel_);

    statusRow->addWidget(leftStatus, 1);
    statusRow->addWidget(rightStatus, 2);
    outer->addLayout(statusRow);

    auto *pathActions = new QHBoxLayout();
    pathActions->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
    for (QPushButton *button : {chooseComfyRootButton_, chooseModelsRootButton_, openComfyButton_, openCustomNodesButton_})
        pathActions->addWidget(button);
    pathActions->addStretch(1);
    outer->addLayout(pathActions);

    auto *familyRow = new QHBoxLayout();
    familyRow->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
    familyInstallCombo_ = new QComboBox(this);
    familyInstallCombo_->setMinimumContentsLength(10);
    familyInstallCombo_->addItem(QStringLiteral("Wan"), QStringLiteral("wan"));
    familyInstallCombo_->addItem(QStringLiteral("Flux"), QStringLiteral("flux"));
    familyInstallCombo_->addItem(QStringLiteral("Krea 2"), QStringLiteral("krea2"));
    familyInstallCombo_->addItem(QStringLiteral("Anima"), QStringLiteral("anima"));
    familyInstallCombo_->addItem(QStringLiteral("Hunyuan"), QStringLiteral("hunyuan"));
    familyTaskCombo_ = new QComboBox(this);
    familyTaskCombo_->addItem(QStringLiteral("T2V"), QStringLiteral("t2v"));
    familyTaskCombo_->addItem(QStringLiteral("I2V"), QStringLiteral("i2v"));
    familyTaskCombo_->addItem(QStringLiteral("T2I"), QStringLiteral("t2i"));
    checkFamilyPlanButton_ = makeButton(QStringLiteral("Refresh plan"));
    browseHfButton_ = makeButton(QStringLiteral("Browse Hugging Face"));
    browseCivitaiButton_ = makeButton(QStringLiteral("Browse Civitai"));
    familyRow->addWidget(makeLabel(QStringLiteral("ManagerStatusLabel"), QStringLiteral("Official base files")));
    familyRow->addWidget(familyInstallCombo_);
    familyRow->addWidget(familyTaskCombo_);
    familyRow->addWidget(checkFamilyPlanButton_);
    familyRow->addWidget(browseHfButton_);
    familyRow->addWidget(browseCivitaiButton_);
    familyRow->addStretch(1);
    outer->addLayout(familyRow);
    outer->addWidget(makeLabel(QStringLiteral("ManagerStatusLabel"),
                               QStringLiteral("Downloads go to the models folder you chose. Each Download button fetches that official base file only. Browse Hugging Face or Civitai for custom / modified models.")));

    familySlotsTable_ = new QTableWidget(this);
    familySlotsTable_->setObjectName(QStringLiteral("ManagerNodeTable"));
    familySlotsTable_->setColumnCount(5);
    familySlotsTable_->setHorizontalHeaderLabels({
        QStringLiteral("Slot"),
        QStringLiteral("Action"),
        QStringLiteral("Official base"),
        QStringLiteral("Note"),
        QStringLiteral("")
    });
    familySlotsTable_->horizontalHeader()->setStretchLastSection(true);
    familySlotsTable_->setMaximumHeight(160);
    familySlotsTable_->setSelectionMode(QAbstractItemView::NoSelection);
    outer->addWidget(familySlotsTable_);

    auto *urlRow = new QHBoxLayout();
    urlRow->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
    modelUrlEdit_ = new QLineEdit(this);
    modelUrlEdit_->setPlaceholderText(QStringLiteral("Paste a Hugging Face or Civitai model link"));
    inspectUrlButton_ = makeButton(QStringLiteral("Inspect link"));
    importSelectedButton_ = makeButton(QStringLiteral("Import selected"));
    urlRow->addWidget(modelUrlEdit_, 1);
    urlRow->addWidget(inspectUrlButton_);
    urlRow->addWidget(importSelectedButton_);
    outer->addLayout(urlRow);

    importChoicesTable_ = new QTableWidget(this);
    importChoicesTable_->setObjectName(QStringLiteral("ManagerNodeTable"));
    importChoicesTable_->setColumnCount(6);
    importChoicesTable_->setHorizontalHeaderLabels({
        QStringLiteral("Version"),
        QStringLiteral("File"),
        QStringLiteral("Type"),
        QStringLiteral("Goes to"),
        QStringLiteral("Hints"),
        QStringLiteral("Pair")
    });
    importChoicesTable_->horizontalHeader()->setStretchLastSection(true);
    importChoicesTable_->setMaximumHeight(180);
    importChoicesTable_->setSelectionBehavior(QAbstractItemView::SelectRows);
    importChoicesTable_->setSelectionMode(QAbstractItemView::SingleSelection);
    outer->addWidget(importChoicesTable_);

    nodesTable_ = new QTableWidget(this);
    nodesTable_->setObjectName(QStringLiteral("ManagerNodeTable"));
    nodesTable_->setColumnCount(6);
    nodesTable_->setHorizontalHeaderLabels({
        QStringLiteral("Status"),
        QStringLiteral("Package"),
        QStringLiteral("Method"),
        QStringLiteral("Families"),
        QStringLiteral("Repo"),
        QStringLiteral("Notes")
    });
    nodesTable_->horizontalHeader()->setStretchLastSection(true);
    nodesTable_->horizontalHeader()->setSectionResizeMode(0, QHeaderView::ResizeToContents);
    nodesTable_->horizontalHeader()->setSectionResizeMode(1, QHeaderView::ResizeToContents);
    nodesTable_->horizontalHeader()->setSectionResizeMode(2, QHeaderView::ResizeToContents);
    nodesTable_->horizontalHeader()->setSectionResizeMode(3, QHeaderView::ResizeToContents);
    nodesTable_->setSelectionBehavior(QAbstractItemView::SelectRows);
    nodesTable_->setSelectionMode(QAbstractItemView::SingleSelection);
    nodesTable_->setAlternatingRowColors(true);
    outer->addWidget(nodesTable_, 1);

    logView_ = new QTextEdit(this);
    logView_->setObjectName(QStringLiteral("ManagerLogView"));
    logView_->setReadOnly(true);
    logView_->setMinimumHeight(140);
    outer->addWidget(logView_);

    connect(refreshButton_, &QPushButton::clicked, this, &ManagerPage::refreshStatus);
    connect(installManagerButton_, &QPushButton::clicked, this, &ManagerPage::installManager);
    connect(installSelectedButton_, &QPushButton::clicked, this, &ManagerPage::installSelectedNode);
    connect(installMissingVideoButton_, &QPushButton::clicked, this, &ManagerPage::installMissingVideoNodes);
    connect(restartRuntimeButton_, &QPushButton::clicked, this, &ManagerPage::restartComfyRuntime);
    connect(freeVramButton_, &QPushButton::clicked, this, &ManagerPage::freeRuntimeVram);
    connect(chooseComfyRootButton_, &QPushButton::clicked, this, &ManagerPage::chooseComfyRoot);
    connect(chooseModelsRootButton_, &QPushButton::clicked, this, &ManagerPage::chooseModelsRoot);
    connect(checkFamilyPlanButton_, &QPushButton::clicked, this, &ManagerPage::checkFamilyInstallPlan);
    connect(browseHfButton_, &QPushButton::clicked, this, &ManagerPage::browseHuggingFace);
    connect(browseCivitaiButton_, &QPushButton::clicked, this, &ManagerPage::browseCivitai);
    connect(inspectUrlButton_, &QPushButton::clicked, this, &ManagerPage::inspectPastedModelUrl);
    connect(importSelectedButton_, &QPushButton::clicked, this, &ManagerPage::importSelectedModelChoice);
    connect(openComfyButton_, &QPushButton::clicked, this, &ManagerPage::openComfyRoot);
    connect(openCustomNodesButton_, &QPushButton::clicked, this, &ManagerPage::openCustomNodesRoot);
    connect(updateComfyButton_, &QPushButton::clicked, this, &ManagerPage::onUpdateComfyClicked);
    connect(buildNodeIndexButton_, &QPushButton::clicked, this, &ManagerPage::onBuildNodeIndexClicked);

    comfyRootLabel_->setText(QStringLiteral("Comfy root: %1").arg(currentComfyRoot()));
    modelsRootLabel_->setText(QStringLiteral("Models root: %1").arg(currentModelsRoot()));
}

void ManagerPage::setProjectRoot(const QString &projectRoot)
{
    projectRoot_ = normalizedPath(projectRoot);

    // The constructor set these labels before it knew the project root, so the live-root lookup --
    // which reads a file under it -- could not run yet. Refresh now that it can.
    const QString liveRoot = spellvision::shell::resolveLiveComfyRoot(
        projectRoot_, QStringLiteral("127.0.0.1"), 8188);
    const QString configured = configuredComfyRoot();
    if (!liveRoot.isEmpty() && !configured.isEmpty() && liveRoot != configured)
    {
        appendLog(QStringLiteral("Comfy root: using the running instance at %1 (configured root is %2 "
                                 "-- SPELLVISION_COMFY or runtime/comfyRoot is stale).")
                      .arg(liveRoot, configured));
    }

    if (comfyRootLabel_)
        comfyRootLabel_->setText(QStringLiteral("Comfy root: %1").arg(currentComfyRoot()));
}

void ManagerPage::setPythonExecutable(const QString &pythonExecutable)
{
    pythonExecutable_ = pythonExecutable.trimmed();
}

QString ManagerPage::resolveProjectRoot() const
{
    if (!projectRoot_.trimmed().isEmpty())
        return projectRoot_;

    QDir dir(QCoreApplication::applicationDirPath());
    for (int depth = 0; depth < 8; ++depth)
    {
        if (QFileInfo::exists(dir.filePath(QStringLiteral("python/worker_client.py"))))
            return QDir::fromNativeSeparators(dir.absolutePath());
        if (!dir.cdUp())
            break;
    }

    return QDir::fromNativeSeparators(QDir::currentPath());
}

QString ManagerPage::resolvePythonExecutable() const
{
    if (!pythonExecutable_.trimmed().isEmpty() && QFileInfo(pythonExecutable_).isFile())
        return pythonExecutable_;

    const QString venvPython = QDir(resolveProjectRoot()).filePath(QStringLiteral(".venv/Scripts/python.exe"));
    if (QFileInfo(venvPython).isFile())
        return venvPython;

    return QStringLiteral("python");
}

QString ManagerPage::currentComfyRoot() const
{
    if (!comfyRoot_.trimmed().isEmpty())
        return comfyRoot_;

    // The live instance wins over configuration here, including SPELLVISION_COMFY. Every action on
    // this page -- install Manager, install a custom node, restart Comfy -- only means anything
    // against the ComfyUI that is actually serving :8188. Honouring a configured root that is not
    // the running one does not merely mislabel the page: it installs into a tree nothing reads,
    // and the operation still reports success. configuredComfyRoot() keeps the stated intent
    // visible so the override is reported rather than silent.
    const QString liveRoot = spellvision::shell::resolveLiveComfyRoot(
        resolveProjectRoot(), QStringLiteral("127.0.0.1"), 8188);
    if (!liveRoot.isEmpty())
        return liveRoot;

    return configuredComfyRoot();
}

// What this machine says the Comfy root should be, ignoring what is actually running.
QString ManagerPage::configuredComfyRoot() const
{
    const QString envPath = QString::fromLocal8Bit(qgetenv("SPELLVISION_COMFY")).trimmed();
    if (!envPath.isEmpty())
        return normalizedPath(envPath);

    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    const QString configured = settings.value(QStringLiteral("runtime/comfyRoot")).toString().trimmed();
    const QString preferred = spellvision::shell::resolvePreferredComfyRoot(configured);
    if (!preferred.isEmpty())
        return preferred;

    return {};
}

QString ManagerPage::currentModelsRoot() const
{
    const QString envPath = QString::fromLocal8Bit(qgetenv("SPELLVISION_MODELS")).trimmed();
    if (!envPath.isEmpty())
        return normalizedPath(envPath);

    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    const QString configured = settings.value(QStringLiteral("runtime/modelsRoot")).toString().trimmed();
    if (!configured.isEmpty())
        return normalizedPath(configured);

    return QString();
}

void ManagerPage::setBusy(bool busy)
{
    for (QPushButton *button : {refreshButton_, installManagerButton_, installSelectedButton_, installMissingVideoButton_, freeVramButton_, restartRuntimeButton_, chooseComfyRootButton_, chooseModelsRootButton_, checkFamilyPlanButton_, browseHfButton_, browseCivitaiButton_, inspectUrlButton_, importSelectedButton_})
    {
        if (button)
            button->setEnabled(!busy);
    }

    if (openComfyButton_)
        openComfyButton_->setEnabled(true);
    if (openCustomNodesButton_)
        openCustomNodesButton_->setEnabled(true);

    if (refreshButton_)
        refreshButton_->setText(busy ? QStringLiteral("Refreshing...") : QStringLiteral("Detect / Refresh"));

    emit statusMessageChanged(busy ? QStringLiteral("Manager task running in background...")
                                   : QStringLiteral("Manager ready."));
}

QJsonObject ManagerPage::parseWorkerResponse(const QString &stdoutText, const QString &stderrText) const
{
    const QString jsonLine = lastJsonLine(stdoutText);
    if (jsonLine.isEmpty())
    {
        return {
            {QStringLiteral("ok"), false},
            {QStringLiteral("error"), QStringLiteral("Worker returned no JSON response.")},
            {QStringLiteral("stdout"), stdoutText},
            {QStringLiteral("stderr"), stderrText},
        };
    }

    QJsonParseError parseError{};
    const QJsonDocument doc = QJsonDocument::fromJson(jsonLine.toUtf8(), &parseError);
    if (parseError.error != QJsonParseError::NoError || !doc.isObject())
    {
        return {
            {QStringLiteral("ok"), false},
            {QStringLiteral("error"), QStringLiteral("Could not parse worker JSON response.")},
            {QStringLiteral("raw"), jsonLine},
            {QStringLiteral("stderr"), stderrText},
        };
    }

    QJsonObject payload = doc.object();
    if (payload.value(QStringLiteral("type")).toString() == QStringLiteral("client_warning")
        && payload.value(QStringLiteral("raw")).isObject())
    {
        payload = payload.value(QStringLiteral("raw")).toObject();
    }

    if (!stderrText.trimmed().isEmpty())
        payload.insert(QStringLiteral("stderr"), stderrText.trimmed());

    return payload;
}

void ManagerPage::sendWorkerRequestAsync(const QJsonObject &request,
                                         int timeoutMs,
                                         const QString &label,
                                         std::function<void(const QJsonObject &)> callback)
{
    if (managerRequestInFlight_)
        return;

    managerRequestInFlight_ = true;
    setBusy(true);

    const QString projectRoot = resolveProjectRoot();
    const QString python = resolvePythonExecutable();
    const QString workerClient = QDir(projectRoot).filePath(QStringLiteral("python/worker_client.py"));

    QJsonObject normalized = request;
    normalized.insert(QStringLiteral("comfy_root"), currentComfyRoot());
    normalized.insert(QStringLiteral("python_executable"), python);

    auto completed = std::make_shared<bool>(false);

    // Transport-independent completion bookkeeping: clear the in-flight gate, drop the busy state,
    // log the outcome, hand the payload to the caller -- exactly once. Returns whether this call
    // was the one that reported, so a transport can do its own cleanup only on the real finish.
    auto report = [this, completed, callback = std::move(callback), label](const QJsonObject &payload) mutable
    {
        if (*completed)
            return false;

        *completed = true;
        managerRequestInFlight_ = false;
        setBusy(false);

        const bool ok = payload.value(QStringLiteral("ok")).toBool(false);
        appendLog(QStringLiteral("%1 %2.").arg(label, ok ? QStringLiteral("completed")
                                                         : QStringLiteral("failed")));

        if (callback)
            callback(payload);

        return true;
    };

    // Same native-socket swap MainWindow uses: these are one-shot control commands, so the
    // ~79ms CPython start that worker_client.py costs buys nothing. Every Manager request is a
    // "command", so this branch takes all of them; the QProcess path below stays as the fallback.
    if (spellvision::workers::WorkerSocketClient::canHandle(normalized))
    {
        spellvision::workers::WorkerSocketClient::send(
            this, normalized, timeoutMs,
            [report](const QJsonObject &response, const QString &diagnostics, bool) mutable
            {
                if (response.isEmpty())
                {
                    report(QJsonObject{
                        {QStringLiteral("ok"), false},
                        {QStringLiteral("error"), diagnostics.trimmed().isEmpty()
                                                      ? QStringLiteral("Worker returned no JSON response.")
                                                      : diagnostics.trimmed()},
                    });
                    return;
                }

                // parseWorkerResponse unwraps worker_client.py's client_warning envelope. The
                // socket path never sees one -- the shim is what produced it -- so the payload
                // arrives already unwrapped.
                report(response);
            });
        return;
    }

    auto *process = new QProcess(this);
    process->setWorkingDirectory(projectRoot);
    QProcessEnvironment env = QProcessEnvironment::systemEnvironment();
    env.insert(QStringLiteral("SPELLVISION_WORKER_CLIENT_TIMEOUT_SEC"), QString::number(qMax(120, timeoutMs / 1000)));
    process->setProcessEnvironment(env);

    auto finish = [process, report](const QJsonObject &payload) mutable
    {
        if (report(payload))
            process->deleteLater();
    };

    auto *timeout = new QTimer(process);
    timeout->setSingleShot(true);
    connect(timeout, &QTimer::timeout, this, [process, finish]() mutable
    {
        if (process->state() != QProcess::NotRunning)
        {
            process->kill();
            process->waitForFinished(1000);
        }

        finish({
            {QStringLiteral("ok"), false},
            {QStringLiteral("error"), QStringLiteral("Worker request timed out.")},
        });
    });

    connect(process, &QProcess::started, this, [process, normalized]()
    {
        process->write(QJsonDocument(normalized).toJson(QJsonDocument::Compact));
        process->closeWriteChannel();
    });

    connect(process, &QProcess::finished, this,
            [this, process, timeout, finish](int, QProcess::ExitStatus) mutable
    {
        timeout->stop();

        const QString stdoutText = QString::fromUtf8(process->readAllStandardOutput());
        const QString stderrText = QString::fromUtf8(process->readAllStandardError());
        if (!stderrText.trimmed().isEmpty())
            appendLog(QStringLiteral("stderr: %1").arg(stderrText.trimmed()));

        finish(parseWorkerResponse(stdoutText, stderrText));
    });

    connect(process, &QProcess::errorOccurred, this,
            [python, finish](QProcess::ProcessError error) mutable
    {
        finish({
            {QStringLiteral("ok"), false},
            {QStringLiteral("error"), QStringLiteral("Could not start worker_client.py with %1. QProcess error=%2")
                                         .arg(python)
                                         .arg(static_cast<int>(error))},
        });
    });

    timeout->start(timeoutMs);
    process->start(python, {workerClient});
}

void ManagerPage::warmCache()
{
    tryLoadManagerStatusCacheFromDisk();

    if (hasManagerStatusCache())
    {
        QJsonObject cachedPayload = g_managerStatusCache;
        cachedPayload.insert(QStringLiteral("__spellvision_cache_source"), managerStatusDisplaySource());
        applyManagerStatus(cachedPayload);
        appendLog(QStringLiteral("Using cached manager status (%1).").arg(managerStatusDisplaySource()));
    }

    if (managerRequestInFlight_ || managerStatusCacheFresh())
        return;

    appendLog(hasManagerStatusCache()
                  ? QStringLiteral("Refreshing manager status in background...")
                  : QStringLiteral("Preloading manager and node state in background..."));
    sendWorkerRequestAsync(
        {{QStringLiteral("command"), QStringLiteral("comfy_manager_status")}},
        120000,
        QStringLiteral("manager warm cache"),
        [this](const QJsonObject &payload)
        {
            if (payload.value(QStringLiteral("ok")).toBool(false))
                storeManagerStatusCache(payload);

            if (!hasManagerStatusCache() || payload.value(QStringLiteral("ok")).toBool(false))
            {
                QJsonObject livePayload = payload;
                livePayload.insert(QStringLiteral("__spellvision_cache_source"), QStringLiteral("live"));
                applyManagerStatus(livePayload);
            }
        });
}

void ManagerPage::refreshStatus()
{
    tryLoadManagerStatusCacheFromDisk();

    if (hasManagerStatusCache())
    {
        const QString cacheSource = managerStatusDisplaySource();
        QJsonObject cachedPayload = g_managerStatusCache;
        cachedPayload.insert(QStringLiteral("__spellvision_cache_source"), cacheSource);
        applyManagerStatus(cachedPayload);

        appendLog(managerStatusCacheFresh()
                      ? QStringLiteral("Using cached manager status (%1).").arg(cacheSource)
                      : QStringLiteral("Using cached manager status (%1) while refreshing in background.").arg(cacheSource));

        if (managerStatusCacheFresh())
            return;
    }

    if (managerRequestInFlight_)
        return;

    appendLog(hasManagerStatusCache()
                  ? QStringLiteral("Refreshing manager status in background...")
                  : QStringLiteral("Loading manager and node state in background..."));

    sendWorkerRequestAsync(
        {{QStringLiteral("command"), QStringLiteral("comfy_manager_status")}},
        120000,
        QStringLiteral("manager status"),
        [this](const QJsonObject &payload)
        {
            if (payload.value(QStringLiteral("ok")).toBool(false))
                storeManagerStatusCache(payload);

            if (!hasManagerStatusCache() || payload.value(QStringLiteral("ok")).toBool(false))
            {
                QJsonObject livePayload = payload;
                livePayload.insert(QStringLiteral("__spellvision_cache_source"), QStringLiteral("live"));
                applyManagerStatus(livePayload);
            }
        });
}

void ManagerPage::installManager()
{
    if (managerRequestInFlight_)
        return;

    appendLog(QStringLiteral("Installing or repairing ComfyUI Manager..."));
    sendWorkerRequestAsync(
        {{QStringLiteral("command"), QStringLiteral("install_comfy_manager")}},
        900000,
        QStringLiteral("install manager"),
        [this](const QJsonObject &payload)
        {
            appendLog(QString::fromUtf8(QJsonDocument(payload).toJson(QJsonDocument::Compact)));
            refreshStatus();
        });
}

QString ManagerPage::selectedPackageName() const
{
    if (!nodesTable_ || nodesTable_->currentRow() < 0)
        return {};
    const QTableWidgetItem *item = nodesTable_->item(nodesTable_->currentRow(), 1);
    return item ? item->text().trimmed() : QString();
}

QString ManagerPage::selectedInstallMethod() const
{
    if (!nodesTable_ || nodesTable_->currentRow() < 0)
        return {};
    const QTableWidgetItem *item = nodesTable_->item(nodesTable_->currentRow(), 2);
    return item ? item->text().trimmed() : QString();
}

QString ManagerPage::selectedRepoUrl() const
{
    if (!nodesTable_ || nodesTable_->currentRow() < 0)
        return {};
    const QTableWidgetItem *item = nodesTable_->item(nodesTable_->currentRow(), 4);
    return item ? item->text().trimmed() : QString();
}

void ManagerPage::installSelectedNode()
{
    const QString packageName = selectedPackageName();
    if (packageName.isEmpty())
    {
        appendLog(QStringLiteral("Select a node package first."));
        return;
    }

    if (managerRequestInFlight_)
        return;

    appendLog(QStringLiteral("Installing selected package: %1").arg(packageName));
    QJsonObject request{
        {QStringLiteral("command"), QStringLiteral("install_custom_node")},
        {QStringLiteral("package_name"), packageName},
        {QStringLiteral("install_method"), selectedInstallMethod()},
        {QStringLiteral("repo_url"), selectedRepoUrl()},
    };

    sendWorkerRequestAsync(
        request,
        1800000,
        QStringLiteral("install selected node"),
        [this](const QJsonObject &payload)
        {
            appendLog(QString::fromUtf8(QJsonDocument(payload).toJson(QJsonDocument::Compact)));
            refreshStatus();
        });
}

void ManagerPage::installMissingVideoNodes()
{
    if (managerRequestInFlight_)
        return;

    appendLog(QStringLiteral("Installing missing recommended video nodes. This may take a while..."));
    sendWorkerRequestAsync(
        {{QStringLiteral("command"), QStringLiteral("install_recommended_video_nodes")}},
        3600000,
        QStringLiteral("install missing video nodes"),
        [this](const QJsonObject &payload)
        {
            appendLog(QString::fromUtf8(QJsonDocument(payload).toJson(QJsonDocument::Compact)));
            refreshStatus();
        });
}

void ManagerPage::restartComfyRuntime()
{
    if (managerRequestInFlight_)
        return;

    appendLog(QStringLiteral("Restarting managed Comfy runtime..."));
    sendWorkerRequestAsync(
        {{QStringLiteral("command"), QStringLiteral("restart_comfy_runtime")}},
        180000,
        QStringLiteral("restart Comfy"),
        [this](const QJsonObject &payload)
        {
            appendLog(QString::fromUtf8(QJsonDocument(payload).toJson(QJsonDocument::Compact)));
            refreshStatus();
        });
}

void ManagerPage::freeRuntimeVram()
{
    if (managerRequestInFlight_)
        return;

    appendLog(QStringLiteral("Unloading runtimes and clearing the CUDA cache..."));
    sendWorkerRequestAsync(
        {{QStringLiteral("command"), QStringLiteral("unload_all_runtimes")}},
        120000,
        QStringLiteral("unload runtimes"),
        [this](const QJsonObject &payload)
        {
            appendLog(QString::fromUtf8(QJsonDocument(payload).toJson(QJsonDocument::Compact)));
            // Chained rather than parallel: dropping the cache before the runtimes have released
            // their allocations frees the blocks they are still holding, which is the case that
            // leaves the accounting wedged in the first place.
            sendWorkerRequestAsync(
                {{QStringLiteral("command"), QStringLiteral("clear_cuda_cache")}},
                60000,
                QStringLiteral("clear CUDA cache"),
                [this](const QJsonObject &cachePayload)
                {
                    appendLog(QString::fromUtf8(QJsonDocument(cachePayload).toJson(QJsonDocument::Compact)));
                    refreshStatus();
                });
        });
}

void ManagerPage::chooseComfyRoot()
{
    if (!qgetenv("SPELLVISION_COMFY").trimmed().isEmpty())
    {
        QMessageBox::information(
            this,
            QStringLiteral("Comfy Root"),
            QStringLiteral("SPELLVISION_COMFY currently overrides saved runtime settings. Remove that environment override before choosing a folder here."));
        return;
    }

    const QString selected = QFileDialog::getExistingDirectory(
        this,
        QStringLiteral("Choose ComfyUI root"),
        currentComfyRoot());
    if (selected.isEmpty())
        return;

    const QString normalized = normalizedPath(selected);
    if (!QFileInfo(QDir(normalized).filePath(QStringLiteral("main.py"))).isFile())
    {
        QMessageBox::warning(
            this,
            QStringLiteral("Invalid ComfyUI Root"),
            QStringLiteral("Choose the ComfyUI folder that contains main.py."));
        return;
    }

    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    settings.setValue(QStringLiteral("runtime/comfyRoot"), normalized);
    comfyRoot_ = normalized;
    g_managerStatusCache = {};
    g_managerStatusCacheAtMs = 0;
    g_managerStatusCacheOrigin = QStringLiteral("none");
    comfyRootLabel_->setText(QStringLiteral("Comfy root: %1").arg(normalized));
    appendLog(QStringLiteral("Saved ComfyUI root: %1").arg(normalized));
    refreshStatus();
}

void ManagerPage::chooseModelsRoot()
{
    if (!qgetenv("SPELLVISION_MODELS").trimmed().isEmpty())
    {
        QMessageBox::information(
            this,
            QStringLiteral("Models Root"),
            QStringLiteral("SPELLVISION_MODELS currently overrides saved runtime settings. Remove that environment override before choosing a folder here."));
        return;
    }

    const QString selected = QFileDialog::getExistingDirectory(
        this,
        QStringLiteral("Choose models root"),
        currentModelsRoot());
    if (selected.isEmpty())
        return;

    const QString normalized = normalizedPath(selected);
    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    settings.setValue(QStringLiteral("runtime/modelsRoot"), normalized);
    modelsRootLabel_->setText(QStringLiteral("Models root: %1").arg(normalized));
    appendLog(QStringLiteral("Saved models root: %1").arg(normalized));
}

void ManagerPage::openComfyRoot()
{
    QDesktopServices::openUrl(QUrl::fromLocalFile(currentComfyRoot()));
}

void ManagerPage::openCustomNodesRoot()
{
    QDesktopServices::openUrl(QUrl::fromLocalFile(QDir(currentComfyRoot()).filePath(QStringLiteral("custom_nodes"))));
}

void ManagerPage::onBuildNodeIndexClicked()
{
    if (nodeIndexBuilding_)
    {
        // Stopping is safe: the worker persists after every slice and resumes from where it got to.
        nodeIndexBuilding_ = false;
        buildNodeIndexButton_->setText(QStringLiteral("Build node index"));
        appendLog(QStringLiteral("Stopped building the node index. Progress is kept; pressing again resumes."));
        return;
    }
    nodeIndexBuilding_ = true;
    buildNodeIndexButton_->setText(QStringLiteral("Stop"));
    appendLog(QStringLiteral("Building the node search index. This reads every ComfyUI Registry pack once."));
    runNodeIndexSlice();
}

void ManagerPage::runNodeIndexSlice()
{
    if (!nodeIndexBuilding_)
        return;

    // One bounded slice per request rather than one long call: the label climbs while it runs, and
    // a stall shows up as a slice that does not return instead of a frozen page.
    QJsonObject request{
        {QStringLiteral("command"), QStringLiteral("build_node_class_index")},
        {QStringLiteral("budget_sec"), 45},
    };

    sendWorkerRequestAsync(
        request,
        180000,
        QStringLiteral("build node index"),
        [this](const QJsonObject &payload)
        {
            if (!payload.value(QStringLiteral("ok")).toBool(false))
            {
                nodeIndexBuilding_ = false;
                buildNodeIndexButton_->setText(QStringLiteral("Build node index"));
                const QString error = payload.value(QStringLiteral("error")).toString(QStringLiteral("unknown error"));
                nodeIndexLabel_->setText(QStringLiteral("Node search index: could not build"));
                appendLog(QStringLiteral("Node index build failed: %1").arg(error));
                return;
            }

            const int indexed = payload.value(QStringLiteral("packs_indexed")).toInt();
            const int total = payload.value(QStringLiteral("packs_total")).toInt();
            const int classes = payload.value(QStringLiteral("classes_indexed")).toInt();
            const bool complete = payload.value(QStringLiteral("complete")).toBool(false);

            nodeIndexLabel_->setText(complete
                ? QStringLiteral("Node search index: %1 node types from %2 packs").arg(classes).arg(indexed)
                : QStringLiteral("Node search index: %1 / %2 packs • %3 node types").arg(indexed).arg(total).arg(classes));

            if (complete)
            {
                nodeIndexBuilding_ = false;
                buildNodeIndexButton_->setText(QStringLiteral("Rebuild node index"));
                appendLog(QStringLiteral("Node search index complete: %1 node types from %2 packs.").arg(classes).arg(indexed));
                return;
            }
            // Yield to the event loop between slices so the page stays responsive.
            QTimer::singleShot(0, this, &ManagerPage::runNodeIndexSlice);
        });
}

void ManagerPage::onUpdateComfyClicked()
{
    // Doc 25's rule is absolute: the live install is never mutated, and never `git pull`ed. An
    // update is built as a PARALLEL instance on another port, drift-checked and smoke-rendered, and
    // only then cut over -- which keeps rollback at "stop using the new port". So this button
    // discloses the procedure and hands over the exact command rather than silently starting a
    // long, unattended, irreversible operation on the runtime the user is currently generating with.
    const QString script = QDir(resolveProjectRoot()).filePath(QStringLiteral("scripts/dev/setup_comfy_next.ps1"));
    const QString command = QStringLiteral("powershell -ExecutionPolicy Bypass -File \"%1\"").arg(QDir::toNativeSeparators(script));

    QMessageBox box(this);
    box.setWindowTitle(QStringLiteral("Update ComfyUI"));
    box.setIcon(QMessageBox::Information);
    box.setText(QStringLiteral("ComfyUI %1 is available.").arg(latestComfyRelease_));
    box.setInformativeText(QStringLiteral(
        "SpellVision never updates the ComfyUI you are generating with. The update is built as a "
        "separate instance on its own port, with your node packs pinned to the versions you have "
        "now and an isolated Python environment, then checked for node changes and smoke-rendered. "
        "Only after that does SpellVision switch over, so backing out is just switching back.\n\n"
        "Run this to build the update:\n%1").arg(command));
    QPushButton *copyButton = box.addButton(QStringLiteral("Copy command"), QMessageBox::ActionRole);
    QPushButton *notesButton = box.addButton(QStringLiteral("Release notes"), QMessageBox::ActionRole);
    box.addButton(QMessageBox::Close);
    box.exec();

    if (box.clickedButton() == copyButton)
    {
        QGuiApplication::clipboard()->setText(command);
        appendLog(QStringLiteral("Copied the ComfyUI update command to the clipboard."));
    }
    else if (box.clickedButton() == notesButton && !comfyReleaseUrl_.isEmpty())
    {
        QDesktopServices::openUrl(QUrl(comfyReleaseUrl_));
    }
}

void ManagerPage::applyComfyVersionCheck(const QJsonObject &check)
{
    if (!comfyVersionLabel_)
        return;

    const QString status = check.value(QStringLiteral("status")).toString(QStringLiteral("unknown"));
    const QString installed = check.value(QStringLiteral("installed")).toString();
    const QString latest = check.value(QStringLiteral("latest")).toString();
    const bool updateAvailable = check.value(QStringLiteral("update_available")).toBool(false);

    QString text;
    if (status == QStringLiteral("update_available"))
        text = QStringLiteral("ComfyUI %1 • update available → %2").arg(installed, latest);
    else if (status == QStringLiteral("up_to_date"))
        text = QStringLiteral("ComfyUI %1 • up to date").arg(installed);
    else if (status == QStringLiteral("ahead"))
        text = QStringLiteral("ComfyUI %1 • newer than the latest release (%2)").arg(installed, latest);
    else if (!installed.isEmpty())
        text = QStringLiteral("ComfyUI %1 • latest release unknown").arg(installed);
    else
        text = QStringLiteral("ComfyUI: version unknown");

    // The reason is the whole value of the unknown state: "could not reach GitHub" must not read
    // the same as "up to date".
    const QString reason = check.value(QStringLiteral("reason")).toString().trimmed();
    comfyVersionLabel_->setText(text);
    comfyVersionLabel_->setToolTip(reason.isEmpty() ? check.value(QStringLiteral("release_url")).toString() : reason);

    if (updateComfyButton_)
    {
        updateComfyButton_->setVisible(updateAvailable);
        latestComfyRelease_ = latest;
        comfyReleaseUrl_ = check.value(QStringLiteral("release_url")).toString();
    }
}

void ManagerPage::applyManagerStatus(const QJsonObject &payload)
{
    const QString applySource = payload.value(QStringLiteral("__spellvision_cache_source")).toString().trimmed();
    const bool cacheDisplay = !applySource.isEmpty() && applySource != QStringLiteral("live");

    if (!payload.value(QStringLiteral("ok")).toBool(false))
    {
        const QString error = payload.value(QStringLiteral("error")).toString(QStringLiteral("Unknown manager status error."));
        appendLog(QStringLiteral("Manager status failed: %1").arg(error));
        if (managerStateLabel_)
            managerStateLabel_->setText(QStringLiteral("Manager: error"));
        if (cacheSourceLabel_)
            cacheSourceLabel_->setText(QStringLiteral("Cache source: none"));
        if (lastCheckedLabel_)
            lastCheckedLabel_->setText(QStringLiteral("Last checked: never"));
        if (cachePathLabel_)
            cachePathLabel_->setText(QStringLiteral("Cache path: %1").arg(managerStatusCacheFilePath()));
        return;
    }

    const QJsonObject paths = payload.value(QStringLiteral("manager_paths")).toObject();
    comfyRoot_ = normalizedPath(paths.value(QStringLiteral("comfy_root")).toString(currentComfyRoot()));
    const bool managerPresent = paths.value(QStringLiteral("exists")).toBool(false);
    const QJsonObject runtime = payload.value(QStringLiteral("runtime_status")).toObject();
    const QJsonArray recommended = payload.value(QStringLiteral("recommended_nodes")).toArray();

    if (managerStateLabel_)
        managerStateLabel_->setText(QStringLiteral("Manager: %1").arg(managerPresent ? QStringLiteral("installed") : QStringLiteral("missing")));
    if (runtimeStateLabel_)
        runtimeStateLabel_->setText(QStringLiteral("Runtime: %1 • healthy=%2")
                                        .arg(runtime.value(QStringLiteral("state")).toString(QStringLiteral("unknown")),
                                             boolText(runtime.value(QStringLiteral("healthy")).toBool(false))));
    applyComfyVersionCheck(runtime.value(QStringLiteral("version_check")).toObject());
    if (comfyRootLabel_)
        comfyRootLabel_->setText(QStringLiteral("Comfy root: %1").arg(comfyRoot_));
    if (managerPathLabel_)
        managerPathLabel_->setText(QStringLiteral("Manager path: %1").arg(paths.value(QStringLiteral("manager_root")).toString(QStringLiteral("unknown"))));
    if (cacheSourceLabel_)
        cacheSourceLabel_->setText(QStringLiteral("Cache source: %1").arg(managerStatusDisplaySource(applySource)));
    if (lastCheckedLabel_)
        lastCheckedLabel_->setText(QStringLiteral("Last checked: %1").arg(managerStatusLastCheckedText()));
    if (cachePathLabel_)
        cachePathLabel_->setText(QStringLiteral("Cache path: %1").arg(managerStatusCacheFilePath()));

    int installedCount = 0;
    int missingCount = 0;
    nodesTable_->setRowCount(recommended.size());
    for (int row = 0; row < recommended.size(); ++row)
    {
        const QJsonObject item = recommended.at(row).toObject();
        const bool installed = item.value(QStringLiteral("installed")).toBool(false);
        installed ? ++installedCount : ++missingCount;

        QStringList familyParts;
        for (const QJsonValue &value : item.value(QStringLiteral("model_families")).toArray())
            familyParts << value.toString();
        const QString families = familyParts.join(QStringLiteral(", "));

        const QList<QPair<int, QString>> cells = {
            {0, installed ? QStringLiteral("Installed") : QStringLiteral("Missing")},
            {1, item.value(QStringLiteral("package_name")).toString()},
            {2, item.value(QStringLiteral("install_method")).toString()},
            {3, families},
            {4, item.value(QStringLiteral("repo_url")).toString()},
            {5, item.value(QStringLiteral("notes")).toString()},
        };

        for (const auto &cell : cells)
        {
            auto *tableItem = new QTableWidgetItem(cell.second);
            if (cell.first == 0)
                tableItem->setData(Qt::UserRole, installed);
            nodesTable_->setItem(row, cell.first, tableItem);
        }
    }

    if (nodeSummaryLabel_)
        nodeSummaryLabel_->setText(QStringLiteral("Recommended nodes: %1 installed • %2 missing").arg(installedCount).arg(missingCount));

    if (!cacheDisplay)
        appendLog(QStringLiteral("Manager status refreshed: %1 installed, %2 missing recommended nodes.")
                      .arg(installedCount)
                      .arg(missingCount));

    emit statusMessageChanged(cacheDisplay ? QStringLiteral("Managers using cached status.")
                                          : QStringLiteral("Managers refreshed."));
}

void ManagerPage::appendLog(const QString &message)
{
    if (!logView_)
        return;

    const QString stamp = QDateTime::currentDateTime().toString(QStringLiteral("HH:mm:ss"));
    logView_->append(QStringLiteral("[%1] %2").arg(stamp, message));
}

QStringList ManagerPage::presentModelBasenames() const
{
    QStringList names;
    const QString root = currentModelsRoot();
    if (root.isEmpty() || !QDir(root).exists())
        return names;
    QDirIterator it(root, QStringList() << QStringLiteral("*.safetensors") << QStringLiteral("*.sft")
                                        << QStringLiteral("*.ckpt") << QStringLiteral("*.pt")
                                        << QStringLiteral("*.pth") << QStringLiteral("*.bin"),
                    QDir::Files, QDirIterator::Subdirectories);
    while (it.hasNext()) {
        it.next();
        names.append(it.fileName());
    }
    names.removeDuplicates();
    return names;
}

void ManagerPage::checkFamilyInstallPlan()
{
    requestFamilyInstall(true);
}

void ManagerPage::browseHuggingFace()
{
    QDesktopServices::openUrl(QUrl(QStringLiteral("https://huggingface.co/models")));
}

void ManagerPage::browseCivitai()
{
    QDesktopServices::openUrl(QUrl(QStringLiteral("https://civitai.com/models")));
}

void ManagerPage::downloadFamilyComponent()
{
    auto *button = qobject_cast<QPushButton *>(sender());
    if (!button)
        return;
    const QString component = button->property("component").toString();
    if (component.isEmpty())
        return;
    appendLog(QStringLiteral("Downloading official base for %1 into %2.")
                  .arg(component, currentModelsRoot()));
    requestFamilyInstall(false, component);
}

void ManagerPage::requestFamilyInstall(bool dryRun, const QString &onlyComponent)
{
    if (!familyInstallCombo_ || !familyTaskCombo_)
        return;
    QJsonArray present;
    for (const QString &name : presentModelBasenames())
        present.append(name);
    QJsonObject request{
        {QStringLiteral("command"), dryRun ? QStringLiteral("family_install_plan") : QStringLiteral("apply_family_install_plan")},
        {QStringLiteral("family"), familyInstallCombo_->currentData().toString()},
        {QStringLiteral("task"), familyTaskCombo_->currentData().toString()},
        {QStringLiteral("present_basenames"), present},
        {QStringLiteral("dry_run"), dryRun},
        {QStringLiteral("install_root"), currentModelsRoot()},
    };
    if (!onlyComponent.trimmed().isEmpty())
        request.insert(QStringLiteral("only_components"), QJsonArray{onlyComponent.trimmed()});
    sendWorkerRequestAsync(request, dryRun ? 60000 : 600000,
                           dryRun ? QStringLiteral("family install plan") : QStringLiteral("family fetch"),
                           [this](const QJsonObject &payload) { applyFamilyInstallPayload(payload); });
}

void ManagerPage::applyFamilyInstallPayload(const QJsonObject &payload)
{
    if (!familySlotsTable_)
        return;
    QJsonArray entries = payload.value(QStringLiteral("slots")).toArray();
    if (entries.isEmpty())
        entries = payload.value(QStringLiteral("results")).toArray();
    familySlotsTable_->setRowCount(entries.size());
    for (int row = 0; row < entries.size(); ++row) {
        const QJsonObject entry = entries.at(row).toObject();
        const QString action = entry.value(QStringLiteral("install_action")).toString();
        const QString component = entry.value(QStringLiteral("component")).toString();
        const QString note = entry.value(QStringLiteral("installed_path")).toString().isEmpty()
                                 ? entry.value(QStringLiteral("license_note")).toString()
                                 : entry.value(QStringLiteral("installed_path")).toString();
        familySlotsTable_->setItem(row, 0, new QTableWidgetItem(component));
        familySlotsTable_->setItem(row, 1, new QTableWidgetItem(action));
        familySlotsTable_->setItem(row, 2, new QTableWidgetItem(entry.value(QStringLiteral("fetch_ref")).toString()));
        familySlotsTable_->setItem(row, 3, new QTableWidgetItem(note));
        if (action == QStringLiteral("fetch") && !entry.value(QStringLiteral("fetch_ref")).toString().isEmpty()) {
            auto *download = new QPushButton(QStringLiteral("Download"), familySlotsTable_);
            download->setProperty("component", component);
            connect(download, &QPushButton::clicked, this, &ManagerPage::downloadFamilyComponent);
            familySlotsTable_->setCellWidget(row, 4, download);
        } else {
            familySlotsTable_->setCellWidget(row, 4, nullptr);
        }
    }
    const QJsonArray missing = payload.value(QStringLiteral("missing_required")).toArray();
    const QJsonArray installed = payload.value(QStringLiteral("installed")).toArray();
    appendLog(QStringLiteral("Family plan: %1 slots, %2 missing required, %3 installed. Destination %4.")
                  .arg(entries.size())
                  .arg(missing.size())
                  .arg(installed.size())
                  .arg(currentModelsRoot()));
}

void ManagerPage::inspectPastedModelUrl()
{
    const QString url = modelUrlEdit_ ? modelUrlEdit_->text().trimmed() : QString();
    if (url.isEmpty())
        return;
    appendLog(QStringLiteral("Inspecting %1").arg(url));
    sendWorkerRequestAsync(
        {
            {QStringLiteral("command"), QStringLiteral("inspect_model_url")},
            {QStringLiteral("url"), url},
        },
        60000,
        QStringLiteral("inspect model url"),
        [this](const QJsonObject &payload) {
            lastImportCatalog_ = payload;
            const QJsonArray entries = payload.value(QStringLiteral("choices")).toArray();
            if (!importChoicesTable_)
                return;
            importChoicesTable_->setRowCount(entries.size());
            for (int row = 0; row < entries.size(); ++row) {
                const QJsonObject entry = entries.at(row).toObject();
                const QJsonArray hints = entry.value(QStringLiteral("family_hints")).toArray();
                QStringList hintNames;
                for (const QJsonValue &value : hints)
                    hintNames.append(value.toString());
                const QJsonArray pair = entry.value(QStringLiteral("pair_with")).toArray();
                importChoicesTable_->setItem(row, 0, new QTableWidgetItem(entry.value(QStringLiteral("version_name")).toString()));
                importChoicesTable_->setItem(row, 1, new QTableWidgetItem(entry.value(QStringLiteral("filename")).toString()));
                importChoicesTable_->setItem(row, 2, new QTableWidgetItem(entry.value(QStringLiteral("model_type")).toString()));
                importChoicesTable_->setItem(row, 3, new QTableWidgetItem(entry.value(QStringLiteral("dest_subdir")).toString()));
                importChoicesTable_->setItem(row, 4, new QTableWidgetItem(hintNames.join(QStringLiteral(", "))));
                importChoicesTable_->setItem(row, 5, new QTableWidgetItem(pair.isEmpty() ? QStringLiteral("") : QStringLiteral("high+low")));
                if (importChoicesTable_->item(row, 0))
                    importChoicesTable_->item(row, 0)->setData(Qt::UserRole, entry.value(QStringLiteral("choice_id")).toString());
            }
            appendLog(QStringLiteral("Found %1 files. Pick one version/file. Dual-noise pairs import together.")
                          .arg(entries.size()));
        });
}

void ManagerPage::importSelectedModelChoice()
{
    if (!importChoicesTable_ || lastImportCatalog_.isEmpty())
        return;
    const int row = importChoicesTable_->currentRow();
    if (row < 0 || !importChoicesTable_->item(row, 0))
        return;
    const QString choiceId = importChoicesTable_->item(row, 0)->data(Qt::UserRole).toString();
    if (choiceId.isEmpty())
        return;
    appendLog(QStringLiteral("Importing %1 into %2").arg(choiceId, currentModelsRoot()));
    sendWorkerRequestAsync(
        {
            {QStringLiteral("command"), QStringLiteral("import_model_url")},
            {QStringLiteral("catalog"), lastImportCatalog_},
            {QStringLiteral("choice_ids"), QJsonArray{choiceId}},
            {QStringLiteral("install_root"), currentModelsRoot()},
            {QStringLiteral("include_pairs"), true},
        },
        600000,
        QStringLiteral("import model"),
        [this](const QJsonObject &payload) {
            const QJsonArray installed = payload.value(QStringLiteral("installed")).toArray();
            appendLog(QStringLiteral("Imported %1 file(s). ok=%2")
                          .arg(installed.size())
                          .arg(payload.value(QStringLiteral("ok")).toBool() ? QStringLiteral("true") : QStringLiteral("false")));
        });
}
