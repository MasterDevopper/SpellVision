from __future__ import annotations

from pathlib import Path
import sys


def backup_once(path: Path, suffix: str, original: str) -> None:
    backup = path.with_suffix(path.suffix + suffix)
    if not backup.exists():
        backup.write_text(original, encoding="utf-8")
        print(f"Backup written: {backup}")


def replace_once(text: str, old: str, new: str, label: str) -> tuple[str, bool]:
    if old not in text:
        print(f"[skip] pattern not found: {label}")
        return text, False
    return text.replace(old, new, 1), True


def replace_function(text: str, signature: str, new_function: str, label: str) -> tuple[str, bool]:
    start = text.find(signature)
    if start < 0:
        print(f"[skip] function signature not found: {label}")
        return text, False

    brace_start = text.find("{", start)
    if brace_start < 0:
        print(f"[skip] opening brace not found: {label}")
        return text, False

    depth = 0
    end = brace_start
    while end < len(text):
        ch = text[end]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end += 1
                while end < len(text) and text[end] in " \t\r\n":
                    end += 1
                return text[:start] + new_function.rstrip() + "\n\n" + text[end:], True
        end += 1

    print(f"[skip] closing brace not found: {label}")
    return text, False


def patch_manager_header(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    changed = False

    old = """    QLabel *comfyRootLabel_ = nullptr;
    QLabel *managerPathLabel_ = nullptr;
    QLabel *nodeSummaryLabel_ = nullptr;
"""
    new = """    QLabel *comfyRootLabel_ = nullptr;
    QLabel *managerPathLabel_ = nullptr;
    QLabel *nodeSummaryLabel_ = nullptr;
    QLabel *cacheSourceLabel_ = nullptr;
    QLabel *lastCheckedLabel_ = nullptr;
    QLabel *cachePathLabel_ = nullptr;
"""
    text, did = replace_once(text, old, new, "ManagerPage.h cache labels")
    changed = changed or did

    if not changed:
        return False

    backup_once(path, ".pre_sprint13_pass7_cache_ui.bak", original)
    path.write_text(text, encoding="utf-8")
    print(f"Patched: {path}")
    return True


def patch_manager_cpp(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    changed = False

    old_helpers = """    constexpr qint64 kManagerStatusCacheFreshMs = 5 * 60 * 1000;
    constexpr qint64 kManagerStatusCacheRetainMs = 7LL * 24 * 60 * 60 * 1000;

    QJsonObject g_managerStatusCache;
    qint64 g_managerStatusCacheAtMs = 0;

    QString managerStatusCacheFilePath()
    {
        QString base = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation);
        if (base.isEmpty())
        {
            base = QDir(QCoreApplication::applicationDirPath()).filePath(QStringLiteral("runtime/cache/ui"));
        }

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
        return hasManagerStatusCache() &&
               g_managerStatusCacheAtMs > 0 &&
               (QDateTime::currentMSecsSinceEpoch() - g_managerStatusCacheAtMs) < kManagerStatusCacheFreshMs;
    }

    void tryLoadManagerStatusCacheFromDisk()
    {
        if (hasManagerStatusCache())
            return;

        QFile file(managerStatusCacheFilePath());
        if (!file.exists())
            return;

        if (!file.open(QIODevice::ReadOnly))
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

        QJsonObject root{
            {QStringLiteral("cached_at_ms"), static_cast<double>(g_managerStatusCacheAtMs)},
            {QStringLiteral("payload"), payload},
        };
        file.write(QJsonDocument(root).toJson(QJsonDocument::Compact));
        file.commit();
    }
"""
    new_helpers = """    constexpr qint64 kManagerStatusCacheFreshMs = 5 * 60 * 1000;
    constexpr qint64 kManagerStatusCacheRetainMs = 7LL * 24 * 60 * 60 * 1000;

    QJsonObject g_managerStatusCache;
    qint64 g_managerStatusCacheAtMs = 0;
    QString g_managerStatusCacheOrigin = QStringLiteral("none");

    QString managerStatusCacheFilePath()
    {
        QString base = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation);
        if (base.isEmpty())
        {
            base = QDir(QCoreApplication::applicationDirPath()).filePath(QStringLiteral("runtime/cache/ui"));
        }

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
        return hasManagerStatusCache() &&
               g_managerStatusCacheAtMs > 0 &&
               (QDateTime::currentMSecsSinceEpoch() - g_managerStatusCacheAtMs) < kManagerStatusCacheFreshMs;
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
        if (!file.exists())
            return;

        if (!file.open(QIODevice::ReadOnly))
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

        QJsonObject root{
            {QStringLiteral("cached_at_ms"), static_cast<double>(g_managerStatusCacheAtMs)},
            {QStringLiteral("payload"), payload},
        };
        file.write(QJsonDocument(root).toJson(QJsonDocument::Compact));
        file.commit();
    }
"""
    text, did = replace_once(text, old_helpers, new_helpers, "cache helper block with source/timestamp")
    changed = changed or did

    ctor_old = """    managerStateLabel_ = makeLabel(QStringLiteral("ManagerStatusLabel"), QStringLiteral("Manager: not checked"));
    runtimeStateLabel_ = makeLabel(QStringLiteral("ManagerStatusLabel"), QStringLiteral("Runtime: not checked"));
    nodeSummaryLabel_ = makeLabel(QStringLiteral("ManagerStatusLabel"), QStringLiteral("Nodes: not checked"));
    leftLayout->addWidget(managerStateLabel_);
    leftLayout->addWidget(runtimeStateLabel_);
    leftLayout->addWidget(nodeSummaryLabel_);

    auto *rightStatus = new QWidget(this);
    auto *rightLayout = new QVBoxLayout(rightStatus);
    rightLayout->setContentsMargins(0, 0, 0, 0);
    rightLayout->setSpacing(6);
    comfyRootLabel_ = makeLabel(QStringLiteral("ManagerPathLabel"), QStringLiteral("Comfy root: unknown"));
    managerPathLabel_ = makeLabel(QStringLiteral("ManagerPathLabel"), QStringLiteral("Manager path: unknown"));
    rightLayout->addWidget(comfyRootLabel_);
    rightLayout->addWidget(managerPathLabel_);
"""
    ctor_new = """    managerStateLabel_ = makeLabel(QStringLiteral("ManagerStatusLabel"), QStringLiteral("Manager: not checked"));
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
"""
    text, did = replace_once(text, ctor_old, ctor_new, "constructor status labels")
    changed = changed or did

    warm_new = """void ManagerPage::warmCache()
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
}"""
    text, did = replace_function(text, "void ManagerPage::warmCache()", warm_new, "warmCache UI polish")
    changed = changed or did

    refresh_new = """void ManagerPage::refreshStatus()
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
    {
        if (!hasManagerStatusCache())
            appendLog(QStringLiteral("Manager status is already loading in background."));
        return;
    }

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
}"""
    text, did = replace_function(text, "void ManagerPage::refreshStatus()", refresh_new, "refreshStatus UI polish")
    changed = changed or did

    apply_new = """void ManagerPage::applyManagerStatus(const QJsonObject &payload)
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
        runtimeStateLabel_->setText(QStringLiteral("Runtime: %1 • healthy=%2").arg(runtime.value(QStringLiteral("state")).toString(QStringLiteral("unknown")), boolText(runtime.value(QStringLiteral("healthy")).toBool(false))));
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

        const QList<QPair<int, QString>> cells = {{0, installed ? QStringLiteral("Installed") : QStringLiteral("Missing")}, {1, item.value(QStringLiteral("package_name")).toString()}, {2, item.value(QStringLiteral("install_method")).toString()}, {3, families}, {4, item.value(QStringLiteral("repo_url")).toString()}, {5, item.value(QStringLiteral("notes")).toString()}};
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
        appendLog(QStringLiteral("Manager status refreshed: %1 installed, %2 missing recommended nodes.").arg(installedCount).arg(missingCount));

    emit statusMessageChanged(cacheDisplay ? QStringLiteral("Managers using cached status.")
                                          : QStringLiteral("Managers refreshed."));
}"""
    text, did = replace_function(text, "void ManagerPage::applyManagerStatus(const QJsonObject &payload)", apply_new, "applyManagerStatus cache labels and quieter logs")
    changed = changed or did

    setbusy_new = """void ManagerPage::setBusy(bool busy)
{
    for (QPushButton *button : {refreshButton_, installManagerButton_, installSelectedButton_, installMissingVideoButton_, restartRuntimeButton_})
    {
        if (button)
            button->setEnabled(!busy);
    }

    // Folder actions stay available during long-running manager work.
    if (openComfyButton_)
        openComfyButton_->setEnabled(true);
    if (openCustomNodesButton_)
        openCustomNodesButton_->setEnabled(true);

    if (refreshButton_)
        refreshButton_->setText(busy ? QStringLiteral("Refreshing...") : QStringLiteral("Detect / Refresh"));

    emit statusMessageChanged(busy ? QStringLiteral("Manager task running in background...")
                                   : QStringLiteral("Manager ready."));
}"""
    text, did = replace_function(text, "void ManagerPage::setBusy(bool busy)", setbusy_new, "setBusy label clarity")
    changed = changed or did

    if not changed:
        return False

    backup_once(path, ".pre_sprint13_pass7_cache_ui.bak", original)
    path.write_text(text, encoding="utf-8")
    print(f"Patched: {path}")
    return True


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python apply_sprint13_pass7_manager_cache_ui_polish.py <SpellVision project root>")
        return 2

    root = Path(sys.argv[1]).resolve()
    manager_h = root / "qt_ui" / "ManagerPage.h"
    manager_cpp = root / "qt_ui" / "ManagerPage.cpp"

    missing = [str(path) for path in (manager_h, manager_cpp) if not path.exists()]
    if missing:
        print("Missing required files:")
        for item in missing:
            print(f"  {item}")
        return 1

    changed = False
    changed = patch_manager_header(manager_h) or changed
    changed = patch_manager_cpp(manager_cpp) or changed

    if not changed:
        print("No changes were made. The files may already be patched or differ from the expected shape.")
        return 1

    print()
    print("Sprint 13 Pass 7 applied.")
    print("Rebuild/run with:")
    print("  .\\scripts\\dev\\run_ui.ps1")
    print()
    print("This pass adds cache source / timestamp / cache path UI and reduces cache-related log noise.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
