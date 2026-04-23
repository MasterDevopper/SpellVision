from __future__ import annotations

from pathlib import Path
import sys


def replace_once(text: str, old: str, new: str, label: str) -> tuple[str, bool]:
    if old not in text:
        print(f"[skip] pattern not found: {label}")
        return text, False
    return text.replace(old, new, 1), True


def patch_manager_header(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text

    if "#include <functional>" not in text:
        text = text.replace("#include <QJsonObject>\n", "#include <QJsonObject>\n#include <functional>\n", 1)

    text, _ = replace_once(
        text,
        "    QJsonObject sendWorkerRequest(const QJsonObject &request, int timeoutMs = 120000);\n",
        (
            "    QJsonObject sendWorkerRequest(const QJsonObject &request, int timeoutMs = 120000);\n"
            "    void sendWorkerRequestAsync(const QJsonObject &request,\n"
            "                                int timeoutMs,\n"
            "                                const QString &label,\n"
            "                                std::function<void(const QJsonObject &)> callback);\n"
            "    QJsonObject parseWorkerResponse(const QString &stdoutText, const QString &stderrText) const;\n"
        ),
        "ManagerPage.h async declarations",
    )

    text, _ = replace_once(
        text,
        "    QTextEdit *logView_ = nullptr;\n",
        "    QTextEdit *logView_ = nullptr;\n\n    bool managerRequestInFlight_ = false;\n",
        "ManagerPage.h request-in-flight field",
    )

    if text == original:
        return False

    backup = path.with_suffix(path.suffix + ".pre_async_manager_fix.bak")
    if not backup.exists():
        backup.write_text(original, encoding="utf-8")
        print(f"Backup written: {backup}")
    path.write_text(text, encoding="utf-8")
    print(f"Patched: {path}")
    return True


def patch_manager_cpp(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text

    if "#include <QTimer>" not in text:
        text = text.replace("#include <QTextEdit>\n", "#include <QTextEdit>\n#include <QTimer>\n", 1)
    if "#include <memory>" not in text:
        text = text.replace("#include <QVBoxLayout>\n", "#include <QVBoxLayout>\n\n#include <memory>\n", 1)

    old_refresh = '''void ManagerPage::refreshStatus()
{
    setBusy(true);
    appendLog(QStringLiteral("Refreshing manager and node state..."));
    const QJsonObject payload = sendWorkerRequest({{QStringLiteral("command"), QStringLiteral("comfy_manager_status")}}, 120000);
    applyManagerStatus(payload);
    setBusy(false);
}
'''

    new_refresh = '''void ManagerPage::refreshStatus()
{
    if (managerRequestInFlight_)
    {
        appendLog(QStringLiteral("Manager refresh already in progress."));
        return;
    }

    appendLog(QStringLiteral("Refreshing manager and node state..."));
    sendWorkerRequestAsync(
        {{QStringLiteral("command"), QStringLiteral("comfy_manager_status")}},
        120000,
        QStringLiteral("manager status"),
        [this](const QJsonObject &payload)
        {
            applyManagerStatus(payload);
        });
}
'''

    text, changed_refresh = replace_once(text, old_refresh, new_refresh, "ManagerPage.cpp async refreshStatus")

    helper_anchor = "void ManagerPage::refreshStatus()\n{"
    helper_code = r'''
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
    if (payload.value(QStringLiteral("type")).toString() == QStringLiteral("client_warning") &&
        payload.value(QStringLiteral("raw")).isObject())
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
    {
        appendLog(QStringLiteral("%1 request already running.").arg(label));
        return;
    }

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

    auto finish = [this, process, completed, callback = std::move(callback)](const QJsonObject &payload) mutable
    {
        if (*completed)
            return;

        *completed = true;
        managerRequestInFlight_ = false;
        setBusy(false);

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

    connect(process, &QProcess::finished, this, [this, process, timeout, finish](int, QProcess::ExitStatus) mutable
    {
        timeout->stop();

        const QString stdoutText = QString::fromUtf8(process->readAllStandardOutput());
        const QString stderrText = QString::fromUtf8(process->readAllStandardError());
        if (!stderrText.trimmed().isEmpty())
            appendLog(QStringLiteral("stderr: %1").arg(stderrText.trimmed()));

        finish(parseWorkerResponse(stdoutText, stderrText));
    });

    connect(process, &QProcess::errorOccurred, this, [python, finish](QProcess::ProcessError error) mutable
    {
        finish({
            {QStringLiteral("ok"), false},
            {QStringLiteral("error"), QStringLiteral("Could not start worker_client.py with %1. QProcess error=%2").arg(python).arg(static_cast<int>(error))},
        });
    });

    timeout->start(timeoutMs);
    process->start(python, {workerClient});
}

'''

    if changed_refresh and helper_code.strip() not in text:
        text = text.replace(helper_anchor, helper_code + "\n" + helper_anchor, 1)

    if text == original:
        return False

    backup = path.with_suffix(path.suffix + ".pre_async_manager_fix.bak")
    if not backup.exists():
        backup.write_text(original, encoding="utf-8")
        print(f"Backup written: {backup}")
    path.write_text(text, encoding="utf-8")
    print(f"Patched: {path}")
    return True


def patch_main_window_cpp(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text

    old = '''    updateModeButtonState(modeId);
    if (modeId == QStringLiteral("managers") && managersPage_)
        managersPage_->refreshStatus();
    updateDetailsPanelForModeContext();
'''

    new = '''    updateModeButtonState(modeId);
    if (modeId == QStringLiteral("managers") && managersPage_)
    {
        static bool managerInitialRefreshDone = false;
        if (!managerInitialRefreshDone)
        {
            managerInitialRefreshDone = true;
            managersPage_->refreshStatus();
        }
    }
    updateDetailsPanelForModeContext();
'''

    text, changed = replace_once(text, old, new, "MainWindow managers first-entry refresh only")
    if not changed:
        return False

    backup = path.with_suffix(path.suffix + ".pre_async_manager_fix.bak")
    if not backup.exists():
        backup.write_text(original, encoding="utf-8")
        print(f"Backup written: {backup}")
    path.write_text(text, encoding="utf-8")
    print(f"Patched: {path}")
    return True


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python apply_sprint13_pass3_manager_async_fix.py <SpellVision project root>")
        return 2

    root = Path(sys.argv[1]).resolve()
    manager_h = root / "qt_ui" / "ManagerPage.h"
    manager_cpp = root / "qt_ui" / "ManagerPage.cpp"
    main_cpp = root / "qt_ui" / "MainWindow.cpp"

    missing = [str(path) for path in (manager_h, manager_cpp, main_cpp) if not path.exists()]
    if missing:
        print("Missing files:")
        for item in missing:
            print(f"  {item}")
        return 1

    changed = False
    changed = patch_manager_header(manager_h) or changed
    changed = patch_manager_cpp(manager_cpp) or changed
    changed = patch_main_window_cpp(main_cpp) or changed

    if not changed:
        print("No changes were made. The files may already be patched or have a different shape.")
        return 1

    print("Done. Rebuild the Qt app. Python py_compile is not needed for this UI-only fix.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
