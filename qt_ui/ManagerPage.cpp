#include "ManagerPage.h"

#include <QAbstractItemView>
#include <QCoreApplication>
#include <QDateTime>
#include <QDesktopServices>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QHeaderView>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonParseError>
#include <QLabel>
#include <QList>
#include <QPair>
#include <QProcess>
#include <QPushButton>
#include <QSaveFile>
#include <QStandardPaths>
#include <QTableWidget>
#include <QTableWidgetItem>
#include <QTextEdit>
#include <QTimer>
#include <QUrl>
#include <QVBoxLayout>

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
    outer->setSpacing(14);

    auto *header = new QLabel(QStringLiteral("Managers / Runtime"), this);
    header->setObjectName(QStringLiteral("PageTitle"));
    outer->addWidget(header);

    auto *subtitle = makeLabel(QStringLiteral("PageSubtitle"),
                               QStringLiteral("Install and verify ComfyUI Manager, custom nodes, and dependency repair surfaces before advanced video features are enabled."));
    outer->addWidget(subtitle);

    auto *actions = new QHBoxLayout();
    actions->setSpacing(10);
    refreshButton_ = makeButton(QStringLiteral("Detect / Refresh"));
    installManagerButton_ = makeButton(QStringLiteral("Install Manager"));
    installSelectedButton_ = makeButton(QStringLiteral("Install Selected Node"));
    installMissingVideoButton_ = makeButton(QStringLiteral("Install Missing Video Nodes"));
    restartRuntimeButton_ = makeButton(QStringLiteral("Restart Comfy"));
    openComfyButton_ = makeButton(QStringLiteral("Open Comfy Root"));
    openCustomNodesButton_ = makeButton(QStringLiteral("Open custom_nodes"));

    for (QPushButton *button : {refreshButton_, installManagerButton_, installSelectedButton_, installMissingVideoButton_, restartRuntimeButton_, openComfyButton_, openCustomNodesButton_})
        actions->addWidget(button);
    actions->addStretch(1);
    outer->addLayout(actions);

    auto *statusRow = new QHBoxLayout();
    statusRow->setSpacing(12);

    auto *leftStatus = new QWidget(this);
    auto *leftLayout = new QVBoxLayout(leftStatus);
    leftLayout->setContentsMargins(0, 0, 0, 0);
    leftLayout->setSpacing(6);

    managerStateLabel_ = makeLabel(QStringLiteral("ManagerStatusLabel"), QStringLiteral("Manager: not checked"));
    runtimeStateLabel_ = makeLabel(QStringLiteral("ManagerStatusLabel"), QStringLiteral("Runtime: not checked"));
    nodeSummaryLabel_ = makeLabel(QStringLiteral("ManagerStatusLabel"), QStringLiteral("Nodes: not checked"));
    cacheSourceLabel_ = makeLabel(QStringLiteral("ManagerStatusLabel"), QStringLiteral("Cache source: none"));
    lastCheckedLabel_ = makeLabel(QStringLiteral("ManagerStatusLabel"), QStringLiteral("Last checked: never"));
    leftLayout->addWidget(managerStateLabel_);
    leftLayout->addWidget(runtimeStateLabel_);
    leftLayout->addWidget(nodeSummaryLabel_);
    leftLayout->addWidget(cacheSourceLabel_);
    leftLayout->addWidget(lastCheckedLabel_);

    auto *rightStatus = new QWidget(this);
    auto *rightLayout = new QVBoxLayout(rightStatus);
    rightLayout->setContentsMargins(0, 0, 0, 0);
    rightLayout->setSpacing(6);
    comfyRootLabel_ = makeLabel(QStringLiteral("ManagerPathLabel"), QStringLiteral("Comfy root: unknown"));
    managerPathLabel_ = makeLabel(QStringLiteral("ManagerPathLabel"), QStringLiteral("Manager path: unknown"));
    cachePathLabel_ = makeLabel(QStringLiteral("ManagerPathLabel"), QStringLiteral("Cache path: unknown"));
    rightLayout->addWidget(comfyRootLabel_);
    rightLayout->addWidget(managerPathLabel_);
    rightLayout->addWidget(cachePathLabel_);

    statusRow->addWidget(leftStatus, 1);
    statusRow->addWidget(rightStatus, 2);
    outer->addLayout(statusRow);

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
    connect(openComfyButton_, &QPushButton::clicked, this, &ManagerPage::openComfyRoot);
    connect(openCustomNodesButton_, &QPushButton::clicked, this, &ManagerPage::openCustomNodesRoot);
}

void ManagerPage::setProjectRoot(const QString &projectRoot)
{
    projectRoot_ = normalizedPath(projectRoot);
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
    if (!pythonExecutable_.trimmed().isEmpty() && QFileInfo::exists(pythonExecutable_))
        return pythonExecutable_;

    const QString venvPython = QDir(resolveProjectRoot()).filePath(QStringLiteral(".venv/Scripts/python.exe"));
    if (QFileInfo::exists(venvPython))
        return venvPython;

    return QStringLiteral("python");
}

QString ManagerPage::currentComfyRoot() const
{
    if (!comfyRoot_.trimmed().isEmpty())
        return comfyRoot_;

    const QString envPath = QString::fromLocal8Bit(qgetenv("SPELLVISION_COMFY")).trimmed();
    if (!envPath.isEmpty())
        return normalizedPath(envPath);

    const QString preferred = QStringLiteral("D:/AI_ASSETS/comfy_runtime/ComfyUI");
    if (QDir(preferred).exists())
        return preferred;

    return normalizedPath(QDir(resolveProjectRoot()).filePath(QStringLiteral("runtime/comfy/ComfyUI")));
}

void ManagerPage::setBusy(bool busy)
{
    for (QPushButton *button : {refreshButton_, installManagerButton_, installSelectedButton_, installMissingVideoButton_, restartRuntimeButton_})
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

    auto *process = new QProcess(this);
    process->setWorkingDirectory(projectRoot);

    auto completed = std::make_shared<bool>(false);

    auto finish = [this, process, completed, callback = std::move(callback), label](const QJsonObject &payload) mutable
    {
        if (*completed)
            return;

        *completed = true;
        managerRequestInFlight_ = false;
        setBusy(false);

        const bool ok = payload.value(QStringLiteral("ok")).toBool(false);
        appendLog(QStringLiteral("%1 %2.").arg(label, ok ? QStringLiteral("completed")
                                                         : QStringLiteral("failed")));

        if (callback)
            callback(payload);

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

void ManagerPage::openComfyRoot()
{
    QDesktopServices::openUrl(QUrl::fromLocalFile(currentComfyRoot()));
}

void ManagerPage::openCustomNodesRoot()
{
    QDesktopServices::openUrl(QUrl::fromLocalFile(QDir(currentComfyRoot()).filePath(QStringLiteral("custom_nodes"))));
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
