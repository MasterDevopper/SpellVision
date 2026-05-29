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


def patch_manager_cpp(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    changed = False

    include_anchor = "#include <QTimer>\n"
    if "#include <QStandardPaths>" not in text and include_anchor in text:
        text = text.replace(
            include_anchor,
            include_anchor + "#include <QCoreApplication>\n#include <QFile>\n#include <QSaveFile>\n#include <QStandardPaths>\n",
            1,
        )
        changed = True

    old_helpers = '''    constexpr qint64 kManagerStatusCacheFreshMs = 5 * 60 * 1000;

    QJsonObject g_managerStatusCache;
    qint64 g_managerStatusCacheAtMs = 0;

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

    void storeManagerStatusCache(const QJsonObject &payload)
    {
        if (payload.isEmpty())
            return;

        g_managerStatusCache = payload;
        g_managerStatusCacheAtMs = QDateTime::currentMSecsSinceEpoch();
    }
'''
    new_helpers = '''    constexpr qint64 kManagerStatusCacheFreshMs = 5 * 60 * 1000;
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
    }

    void storeManagerStatusCache(const QJsonObject &payload)
    {
        if (payload.isEmpty())
            return;

        g_managerStatusCache = payload;
        g_managerStatusCacheAtMs = QDateTime::currentMSecsSinceEpoch();

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
'''
    text, did = replace_once(text, old_helpers, new_helpers, "disk-backed cache helpers")
    changed = changed or did

    warm_cache = r'''void ManagerPage::warmCache()
{
    if (managerRequestInFlight_ || managerStatusCacheFresh())
        return;

    appendLog(QStringLiteral("Preloading manager and node state in background..."));
    sendWorkerRequestAsync(
        {{QStringLiteral("command"), QStringLiteral("comfy_manager_status")}},
        120000,
        QStringLiteral("manager warm cache"),
        [this](const QJsonObject &payload)
        {
            if (payload.value(QStringLiteral("ok")).toBool(false))
                storeManagerStatusCache(payload);

            if (!hasManagerStatusCache() || payload.value(QStringLiteral("ok")).toBool(false))
                applyManagerStatus(payload);
        });
}'''
    new_warm_cache = r'''void ManagerPage::warmCache()
{
    tryLoadManagerStatusCacheFromDisk();

    if (hasManagerStatusCache())
        applyManagerStatus(g_managerStatusCache);

    if (managerRequestInFlight_ || managerStatusCacheFresh())
        return;

    appendLog(QStringLiteral("Preloading manager and node state in background..."));
    sendWorkerRequestAsync(
        {{QStringLiteral("command"), QStringLiteral("comfy_manager_status")}},
        120000,
        QStringLiteral("manager warm cache"),
        [this](const QJsonObject &payload)
        {
            if (payload.value(QStringLiteral("ok")).toBool(false))
                storeManagerStatusCache(payload);

            if (!hasManagerStatusCache() || payload.value(QStringLiteral("ok")).toBool(false))
                applyManagerStatus(payload);
        });
}'''
    text, did = replace_function(text, "void ManagerPage::warmCache()", new_warm_cache, "warmCache disk preload")
    changed = changed or did

    refresh = r'''void ManagerPage::refreshStatus()
{
    if (hasManagerStatusCache())
    {
        applyManagerStatus(g_managerStatusCache);
        appendLog(QStringLiteral("Showing cached manager status%1")
                      .arg(managerStatusCacheFresh()
                               ? QStringLiteral(" (fresh).")
                               : QStringLiteral(" (stale while refreshing).")));

        if (managerStatusCacheFresh())
            return;
    }

    if (managerRequestInFlight_)
    {
        appendLog(QStringLiteral("Manager refresh already in progress."));
        return;
    }

    appendLog(hasManagerStatusCache()
                  ? QStringLiteral("Refreshing manager and node state in background...")
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
                applyManagerStatus(payload);
        });
}'''
    new_refresh = r'''void ManagerPage::refreshStatus()
{
    tryLoadManagerStatusCacheFromDisk();

    if (hasManagerStatusCache())
    {
        applyManagerStatus(g_managerStatusCache);
        appendLog(QStringLiteral("Showing cached manager status%1")
                      .arg(managerStatusCacheFresh()
                               ? QStringLiteral(" (fresh).")
                               : QStringLiteral(" (stale while refreshing).")));

        if (managerStatusCacheFresh())
            return;
    }

    if (managerRequestInFlight_)
    {
        appendLog(QStringLiteral("Manager refresh already in progress."));
        return;
    }

    appendLog(hasManagerStatusCache()
                  ? QStringLiteral("Refreshing manager and node state in background...")
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
                applyManagerStatus(payload);
        });
}'''
    text, did = replace_function(text, "void ManagerPage::refreshStatus()", new_refresh, "refreshStatus disk preload")
    changed = changed or did

    if not changed:
        return False

    backup_once(path, ".pre_sprint13_pass6_diskcache.bak", original)
    path.write_text(text, encoding="utf-8")
    print(f"Patched: {path}")
    return True


def patch_main_window_cpp(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    changed = False

    old = '''    updateModeButtonState(modeId);
    // Manager state is preloaded in the background after startup and refreshed on demand.
    updateDetailsPanelForModeContext();
'''
    new = '''    updateModeButtonState(modeId);
    // Manager state is preloaded in the background after startup. Opening Manage is now cache-first and nonblocking.
    if (modeId == QStringLiteral("managers") && managersPage_)
        managersPage_->refreshStatus();
    updateDetailsPanelForModeContext();
'''
    text, did = replace_once(text, old, new, "MainWindow cache-first managers activation")
    changed = changed or did

    if not changed:
        return False

    backup_once(path, ".pre_sprint13_pass6_diskcache.bak", original)
    path.write_text(text, encoding="utf-8")
    print(f"Patched: {path}")
    return True


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python apply_sprint13_pass6_manager_disk_cache.py <SpellVision project root>")
        return 2

    root = Path(sys.argv[1]).resolve()
    files = {
        "ManagerPage.cpp": root / "qt_ui" / "ManagerPage.cpp",
        "MainWindow.cpp": root / "qt_ui" / "MainWindow.cpp",
    }

    missing = [name for name, path in files.items() if not path.exists()]
    if missing:
        print("Missing required files:")
        for name in missing:
            print(f"  {name}")
        return 1

    changed = False
    changed = patch_manager_cpp(files["ManagerPage.cpp"]) or changed
    changed = patch_main_window_cpp(files["MainWindow.cpp"]) or changed

    if not changed:
        print("No changes were made. The files may already be patched or differ from the expected shape.")
        return 1

    print()
    print("Sprint 13 Pass 6 applied.")
    print("Rebuild/run with:")
    print("  .\\scripts\\dev\\run_ui.ps1")
    print()
    print("This pass persists Manager cache to disk across app restarts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
