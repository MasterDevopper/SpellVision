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


def patch_manager_header(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    changed = False

    if "#include <functional>" not in text and "#include <QJsonObject>\n" in text:
        text = text.replace("#include <QJsonObject>\n", "#include <QJsonObject>\n#include <functional>\n", 1)
        changed = True

    if "sendWorkerRequestAsync" not in text:
        old = "    QJsonObject sendWorkerRequest(const QJsonObject &request, int timeoutMs = 120000);\n"
        new = old + (
            "    void sendWorkerRequestAsync(const QJsonObject &request,\n"
            "                                int timeoutMs,\n"
            "                                const QString &label,\n"
            "                                std::function<void(const QJsonObject &)> callback);\n"
            "    QJsonObject parseWorkerResponse(const QString &stdoutText, const QString &stderrText) const;\n"
        )
        text, did = replace_once(text, old, new, "ManagerPage.h async declarations")
        changed = changed or did

    if "managerRequestInFlight_" not in text:
        old = "    QTextEdit *logView_ = nullptr;\n"
        new = old + "\n    bool managerRequestInFlight_ = false;\n"
        text, did = replace_once(text, old, new, "ManagerPage.h in-flight field")
        changed = changed or did

    if not changed:
        return False

    backup_once(path, ".pre_sprint13_pass4_async.bak", original)
    path.write_text(text, encoding="utf-8")
    print(f"Patched: {path}")
    return True


ASYNC_HELPERS = r'''
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
    appendLog(QStringLiteral("%1 started in background.").arg(label));

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
        appendLog(QStringLiteral("%1 %2.").arg(label, ok ? QStringLiteral("completed") : QStringLiteral("failed")));

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


def patch_manager_cpp(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    changed = False

    if "#include <QTimer>" not in text and "#include <QTextEdit>\n" in text:
        text = text.replace("#include <QTextEdit>\n", "#include <QTextEdit>\n#include <QTimer>\n", 1)
        changed = True

    if "#include <memory>" not in text and "#include <QVBoxLayout>\n" in text:
        text = text.replace("#include <QVBoxLayout>\n", "#include <QVBoxLayout>\n\n#include <memory>\n#include <utility>\n", 1)
        changed = True
    elif "#include <utility>" not in text and "#include <memory>\n" in text:
        text = text.replace("#include <memory>\n", "#include <memory>\n#include <utility>\n", 1)
        changed = True

    if "QJsonObject ManagerPage::parseWorkerResponse(" not in text:
        anchor = "QJsonObject ManagerPage::sendWorkerRequest("
        if anchor in text:
            text = text.replace(anchor, ASYNC_HELPERS + anchor, 1)
            changed = True
        else:
            print("[skip] sendWorkerRequest anchor not found")

    replacements = [
        (
'''void ManagerPage::setBusy(bool busy)
{
    if (busy)
        QApplication::setOverrideCursor(Qt::WaitCursor);
    else
        QApplication::restoreOverrideCursor();

    for (QPushButton *button : {refreshButton_, installManagerButton_, installSelectedButton_, installMissingVideoButton_, restartRuntimeButton_, openComfyButton_, openCustomNodesButton_})
    {
        if (button)
            button->setEnabled(!busy);
    }
}
''',
'''void ManagerPage::setBusy(bool busy)
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
        refreshButton_->setText(busy ? QStringLiteral("Working...") : QStringLiteral("Detect / Refresh"));

    emit statusMessageChanged(busy ? QStringLiteral("Manager task running in background...")
                                   : QStringLiteral("Manager ready."));
}
''', "setBusy"),
        (
'''void ManagerPage::refreshStatus()
{
    setBusy(true);
    appendLog(QStringLiteral("Refreshing manager and node state..."));
    const QJsonObject payload = sendWorkerRequest({{QStringLiteral("command"), QStringLiteral("comfy_manager_status")}}, 120000);
    applyManagerStatus(payload);
    setBusy(false);
}
''',
'''void ManagerPage::refreshStatus()
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
''', "refreshStatus"),
        (
'''void ManagerPage::installManager()
{
    setBusy(true);
    appendLog(QStringLiteral("Installing or repairing ComfyUI Manager..."));
    QJsonObject payload = sendWorkerRequest({{QStringLiteral("command"), QStringLiteral("install_comfy_manager")}}, 900000);
    appendLog(QString::fromUtf8(QJsonDocument(payload).toJson(QJsonDocument::Compact)));
    setBusy(false);
    refreshStatus();
}
''',
'''void ManagerPage::installManager()
{
    if (managerRequestInFlight_)
    {
        appendLog(QStringLiteral("Another manager task is already running."));
        return;
    }

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
''', "installManager"),
        (
'''void ManagerPage::installSelectedNode()
{
    const QString packageName = selectedPackageName();
    if (packageName.isEmpty())
    {
        appendLog(QStringLiteral("Select a node package first."));
        return;
    }

    setBusy(true);
    appendLog(QStringLiteral("Installing selected package: %1").arg(packageName));
    QJsonObject request{{QStringLiteral("command"), QStringLiteral("install_custom_node")}, {QStringLiteral("package_name"), packageName}, {QStringLiteral("install_method"), selectedInstallMethod()}, {QStringLiteral("repo_url"), selectedRepoUrl()}};
    const QJsonObject payload = sendWorkerRequest(request, 1800000);
    appendLog(QString::fromUtf8(QJsonDocument(payload).toJson(QJsonDocument::Compact)));
    setBusy(false);
    refreshStatus();
}
''',
'''void ManagerPage::installSelectedNode()
{
    const QString packageName = selectedPackageName();
    if (packageName.isEmpty())
    {
        appendLog(QStringLiteral("Select a node package first."));
        return;
    }

    if (managerRequestInFlight_)
    {
        appendLog(QStringLiteral("Another manager task is already running."));
        return;
    }

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
''', "installSelectedNode"),
        (
'''void ManagerPage::installMissingVideoNodes()
{
    setBusy(true);
    appendLog(QStringLiteral("Installing missing recommended video nodes. This may take a while..."));
    const QJsonObject payload = sendWorkerRequest({{QStringLiteral("command"), QStringLiteral("install_recommended_video_nodes")}}, 3600000);
    appendLog(QString::fromUtf8(QJsonDocument(payload).toJson(QJsonDocument::Compact)));
    setBusy(false);
    refreshStatus();
}
''',
'''void ManagerPage::installMissingVideoNodes()
{
    if (managerRequestInFlight_)
    {
        appendLog(QStringLiteral("Another manager task is already running."));
        return;
    }

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
''', "installMissingVideoNodes"),
        (
'''void ManagerPage::restartComfyRuntime()
{
    setBusy(true);
    appendLog(QStringLiteral("Restarting managed Comfy runtime..."));
    const QJsonObject payload = sendWorkerRequest({{QStringLiteral("command"), QStringLiteral("restart_comfy_runtime")}}, 180000);
    appendLog(QString::fromUtf8(QJsonDocument(payload).toJson(QJsonDocument::Compact)));
    setBusy(false);
    refreshStatus();
}
''',
'''void ManagerPage::restartComfyRuntime()
{
    if (managerRequestInFlight_)
    {
        appendLog(QStringLiteral("Another manager task is already running."));
        return;
    }

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
''', "restartComfyRuntime"),
    ]

    for old, new, label in replacements:
        if old in text:
            text = text.replace(old, new, 1)
            changed = True
        else:
            print(f"[skip] pattern not found: {label}")

    if not changed:
        return False

    backup_once(path, ".pre_sprint13_pass4_async.bak", original)
    path.write_text(text, encoding="utf-8")
    print(f"Patched: {path}")
    return True


def patch_main_window_cpp(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text

    if "managerInitialRefreshDone" in text:
        return False

    lines = text.splitlines(keepends=True)
    patched_lines: list[str] = []
    changed = False
    index = 0

    while index < len(lines):
        current = lines[index]
        next_line = lines[index + 1] if index + 1 < len(lines) else ""
        if (
            not changed
            and current.strip() == 'if (modeId == QStringLiteral("managers") && managersPage_)'
            and next_line.strip() == "managersPage_->refreshStatus();"
        ):
            indent = current[: len(current) - len(current.lstrip())]
            newline = "\r\n" if current.endswith("\r\n") else "\n"
            patched_lines.extend([
                f'{indent}// Heavy pages must become visible before they perform worker/process work.{newline}',
                f'{indent}// The Managers page keeps a cached shell and refreshes asynchronously only on first entry;{newline}',
                f'{indent}// later refreshes are explicit via Detect / Refresh.{newline}',
                f'{indent}if (modeId == QStringLiteral("managers") && managersPage_){newline}',
                f'{indent}{{{newline}',
                f'{indent}    static bool managerInitialRefreshDone = false;{newline}',
                f'{indent}    if (!managerInitialRefreshDone){newline}',
                f'{indent}    {{{newline}',
                f'{indent}        managerInitialRefreshDone = true;{newline}',
                f'{indent}        QTimer::singleShot(0, managersPage_, [page = managersPage_](){newline}',
                f'{indent}        {{{newline}',
                f'{indent}            page->refreshStatus();{newline}',
                f'{indent}        }});{newline}',
                f'{indent}    }}{newline}',
                f'{indent}}}{newline}',
            ])
            index += 2
            changed = True
            continue
        patched_lines.append(current)
        index += 1

    if not changed:
        print("[skip] manager page activation refresh block not found")
        return False

    text = "".join(patched_lines)
    backup_once(path, ".pre_sprint13_pass4_async.bak", original)
    path.write_text(text, encoding="utf-8")
    print(f"Patched: {path}")
    return True


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python apply_sprint13_pass4_responsiveness.py <SpellVision project root>")
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
        print("No changes were made. The files may already be patched or have a different shape.")
        return 1

    print("Sprint 13 Pass 4 applied.")
    print("Rebuild/run with: .\\scripts\\dev\\run_ui.ps1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
