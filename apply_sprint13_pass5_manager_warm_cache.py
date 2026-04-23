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

    if "void warmCache();" not in text:
        old = "    void refreshStatus();\n"
        new = old + "    void warmCache();\n"
        text, did = replace_once(text, old, new, "ManagerPage.h warmCache declaration")
        changed = changed or did

    if not changed:
        return False

    backup_once(path, ".pre_sprint13_pass5_warmcache.bak", original)
    path.write_text(text, encoding="utf-8")
    print(f"Patched: {path}")
    return True


CACHE_HELPERS = r'''
    constexpr qint64 kManagerStatusCacheFreshMs = 5 * 60 * 1000;

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

WARM_CACHE_FUNCTION = r'''
void ManagerPage::warmCache()
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
}
'''

REFRESH_FUNCTION = r'''
void ManagerPage::refreshStatus()
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
}
'''


def patch_manager_cpp(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    changed = False

    if "kManagerStatusCacheFreshMs" not in text:
        marker = "    QString boolText(bool value)\n    {\n        return value ? QStringLiteral(\"yes\") : QStringLiteral(\"no\");\n    }\n"
        if marker in text:
            text = text.replace(marker, marker + CACHE_HELPERS, 1)
            changed = True
        else:
            print("[skip] cache helper marker not found")

    if "void ManagerPage::warmCache()" not in text:
        anchor = "QString ManagerPage::resolveProjectRoot() const\n"
        index = text.find(anchor)
        if index >= 0:
            # insert after setPythonExecutable function if possible
            set_py_sig = "void ManagerPage::setPythonExecutable(const QString &pythonExecutable)\n"
            set_index = text.find(set_py_sig)
            if set_index >= 0:
                brace_start = text.find("{", set_index)
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
                            text = text[:end] + WARM_CACHE_FUNCTION + "\n" + text[end:]
                            changed = True
                            break
                    end += 1
            else:
                print("[skip] setPythonExecutable function not found for warmCache insert")

    text, did = replace_function(text, "void ManagerPage::refreshStatus()", REFRESH_FUNCTION, "ManagerPage.cpp refreshStatus cache-aware")
    changed = changed or did

    if not changed:
        return False

    backup_once(path, ".pre_sprint13_pass5_warmcache.bak", original)
    path.write_text(text, encoding="utf-8")
    print(f"Patched: {path}")
    return True


def patch_main_window_cpp(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    changed = False

    startup_block = (
        "    switchToMode(QStringLiteral(\"home\"));\n"
        "    resize(1760, 1020);\n"
    )
    startup_new = (
        "    switchToMode(QStringLiteral(\"home\"));\n"
        "    QTimer::singleShot(1500, this, [this]()\n"
        "    {\n"
        "        if (managersPage_)\n"
        "            managersPage_->warmCache();\n"
        "    });\n"
        "    resize(1760, 1020);\n"
    )
    if "managersPage_->warmCache();" not in text:
        text, did = replace_once(text, startup_block, startup_new, "MainWindow startup warm cache")
        changed = changed or did

    pass3_old = (
        "    updateModeButtonState(modeId);\n"
        "    if (modeId == QStringLiteral(\"managers\") && managersPage_)\n"
        "        managersPage_->refreshStatus();\n"
        "    updateDetailsPanelForModeContext();\n"
    )
    pass3_new = (
        "    updateModeButtonState(modeId);\n"
        "    // Manager state is preloaded in the background after startup and refreshed on demand.\n"
        "    updateDetailsPanelForModeContext();\n"
    )
    if "Manager state is preloaded in the background after startup" not in text:
        text, did = replace_once(text, pass3_old, pass3_new, "MainWindow remove click-triggered managers refresh (pass3)")
        changed = changed or did

    pass4_old = (
        "    updateModeButtonState(modeId);\n"
        "    if (modeId == QStringLiteral(\"managers\") && managersPage_)\n"
        "    {\n"
        "        static bool managerInitialRefreshDone = false;\n"
        "        if (!managerInitialRefreshDone)\n"
        "        {\n"
        "            managerInitialRefreshDone = true;\n"
        "            QTimer::singleShot(0, managersPage_, [page = managersPage_]()\n"
        "            {\n"
        "                page->refreshStatus();\n"
        "            });\n"
        "        }\n"
        "    }\n"
        "    updateDetailsPanelForModeContext();\n"
    )
    pass4_new = (
        "    updateModeButtonState(modeId);\n"
        "    // Manager state is preloaded in the background after startup and refreshed on demand.\n"
        "    updateDetailsPanelForModeContext();\n"
    )
    if "managerInitialRefreshDone" in text:
        text, did = replace_once(text, pass4_old, pass4_new, "MainWindow remove click-triggered managers refresh (pass4)")
        changed = changed or did

    if not changed:
        return False

    backup_once(path, ".pre_sprint13_pass5_warmcache.bak", original)
    path.write_text(text, encoding="utf-8")
    print(f"Patched: {path}")
    return True


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python apply_sprint13_pass5_manager_warm_cache.py <SpellVision project root>")
        return 2

    root = Path(sys.argv[1]).resolve()
    files = {
        "ManagerPage.h": root / "qt_ui" / "ManagerPage.h",
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
    changed = patch_manager_header(files["ManagerPage.h"]) or changed
    changed = patch_manager_cpp(files["ManagerPage.cpp"]) or changed
    changed = patch_main_window_cpp(files["MainWindow.cpp"]) or changed

    if not changed:
        print("No changes were made. The files may already be patched or differ from the expected shape.")
        return 1

    print()
    print("Sprint 13 Pass 5 applied.")
    print("Rebuild/run with:")
    print("  .\\scripts\\dev\\run_ui.ps1")
    print()
    print("This pass adds in-memory startup warm cache and stale-result reuse for Managers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
