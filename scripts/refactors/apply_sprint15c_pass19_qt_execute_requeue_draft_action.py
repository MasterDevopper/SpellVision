from pathlib import Path
import re

root = Path(".")
h_path = root / "qt_ui" / "T2VHistoryPage.h"
cpp_path = root / "qt_ui" / "T2VHistoryPage.cpp"
doc_path = root / "docs" / "sprints" / "SPRINT15C_PASS19_QT_EXECUTE_REQUEUE_DRAFT_ACTION_README.md"
script_path = root / "scripts" / "refactors" / "apply_sprint15c_pass19_qt_execute_requeue_draft_action.py"

h = h_path.read_text(encoding="utf-8")
cpp = cpp_path.read_text(encoding="utf-8")

# Header slot/member.
if "validateSelectedLtxRequeueDraft" not in h:
    h = h.replace(
        "    void prepareSelectedLtxRequeueDraft();\n",
        "    void prepareSelectedLtxRequeueDraft();\n"
        "    void validateSelectedLtxRequeueDraft();\n",
        1,
    )

if "QPushButton *validateRequeueButton_" not in h:
    h = h.replace(
        "    QPushButton *requeueButton_ = nullptr;\n",
        "    QPushButton *requeueButton_ = nullptr;\n"
        "    QPushButton *validateRequeueButton_ = nullptr;\n",
        1,
    )

h_path.write_text(h, encoding="utf-8")

# Includes.
for include in [
    "#include <QCoreApplication>",
    "#include <QProcess>",
    "#include <QJsonParseError>",
]:
    if include not in cpp:
        cpp = cpp.replace("#include <QFile>", "#include <QFile>\n" + include, 1)

# Add helpers inside the anonymous namespace. These use helpers from Pass 17:
# ltxRequeueDraftRoot(), safeRequeueSlug(), requeuePromptIdFromRuntimeSummary().
helpers = r'''
QString spellVisionRepoRootForWorkerClient()
{
    const QString current = QDir::currentPath();
    if (QFileInfo::exists(QDir(current).filePath(QStringLiteral("python/worker_client.py"))))
        return current;

    QDir appDir(QCoreApplication::applicationDirPath());
    for (int i = 0; i < 8; ++i)
    {
        if (QFileInfo::exists(appDir.filePath(QStringLiteral("python/worker_client.py"))))
            return appDir.absolutePath();

        if (!appDir.cdUp())
            break;
    }

    return current;
}

QString spellVisionPythonExecutable(const QString &repoRoot)
{
#ifdef Q_OS_WIN
    const QString venvPython = QDir(repoRoot).filePath(QStringLiteral(".venv/Scripts/python.exe"));
#else
    const QString venvPython = QDir(repoRoot).filePath(QStringLiteral(".venv/bin/python"));
#endif

    if (QFileInfo::exists(venvPython))
        return venvPython;

    return QStringLiteral("python");
}

QJsonObject parseLastJsonObjectFromProcessOutput(const QByteArray &output, QString *errorMessage = nullptr)
{
    const QList<QByteArray> lines = output.split('\n');

    for (int i = lines.size() - 1; i >= 0; --i)
    {
        const QByteArray trimmed = lines.at(i).trimmed();
        if (trimmed.isEmpty())
            continue;

        QJsonParseError parseError;
        const QJsonDocument document = QJsonDocument::fromJson(trimmed, &parseError);
        if (parseError.error == QJsonParseError::NoError && document.isObject())
            return document.object();
    }

    QJsonParseError parseError;
    const QJsonDocument document = QJsonDocument::fromJson(output, &parseError);
    if (parseError.error == QJsonParseError::NoError && document.isObject())
        return document.object();

    if (errorMessage)
        *errorMessage = QStringLiteral("Could not parse worker response JSON.");

    return {};
}

QString expectedLtxRequeueDraftPathForItem(const T2VHistoryPage::VideoHistoryItem &item)
{
    const QString promptId = requeuePromptIdFromRuntimeSummary(item.runtimeSummary);
    const QString slug = safeRequeueSlug(promptId.isEmpty() ? item.promptPreview.left(80) : promptId);
    return QDir(ltxRequeueDraftRoot()).filePath(QStringLiteral("%1.requeue.json").arg(slug));
}

'''

if "spellVisionRepoRootForWorkerClient()" not in cpp:
    namespace_match = re.search(r"namespace\s*\{", cpp)
    if not namespace_match:
        raise SystemExit("Could not find anonymous namespace in T2VHistoryPage.cpp.")
    cpp = cpp[:namespace_match.end()] + "\n" + helpers + cpp[namespace_match.end():]

# Construct button next to Prepare Requeue.
if "validateRequeueButton_ = new QPushButton(QStringLiteral(\"Validate Requeue\"), details);" not in cpp:
    cpp = cpp.replace(
        "    requeueButton_ = new QPushButton(QStringLiteral(\"Prepare Requeue\"), details);\n"
        "    requeueButton_->setObjectName(QStringLiteral(\"HistoryActionButton\"));\n",
        "    requeueButton_ = new QPushButton(QStringLiteral(\"Prepare Requeue\"), details);\n"
        "    requeueButton_->setObjectName(QStringLiteral(\"HistoryActionButton\"));\n"
        "    validateRequeueButton_ = new QPushButton(QStringLiteral(\"Validate Requeue\"), details);\n"
        "    validateRequeueButton_->setObjectName(QStringLiteral(\"HistoryActionButton\"));\n",
        1,
    )

# Connect button.
if "connect(validateRequeueButton_, &QPushButton::clicked, this, &T2VHistoryPage::validateSelectedLtxRequeueDraft);" not in cpp:
    cpp = cpp.replace(
        "    connect(requeueButton_, &QPushButton::clicked, this, &T2VHistoryPage::prepareSelectedLtxRequeueDraft);\n",
        "    connect(requeueButton_, &QPushButton::clicked, this, &T2VHistoryPage::prepareSelectedLtxRequeueDraft);\n"
        "    connect(validateRequeueButton_, &QPushButton::clicked, this, &T2VHistoryPage::validateSelectedLtxRequeueDraft);\n",
        1,
    )

# Add button to visible action row.
if "copyActions->addWidget(validateRequeueButton_);" not in cpp:
    cpp = cpp.replace(
        "    copyActions->addWidget(requeueButton_);\n",
        "    copyActions->addWidget(requeueButton_);\n"
        "    copyActions->addWidget(validateRequeueButton_);\n",
        1,
    )

# Enable for LTX rows.
if "validateRequeueButton_->setEnabled(selectedItemIsLtx);" not in cpp:
    cpp = cpp.replace(
        "    requeueButton_->setEnabled(selectedItemIsLtx);\n",
        "    requeueButton_->setEnabled(selectedItemIsLtx);\n"
        "    validateRequeueButton_->setEnabled(selectedItemIsLtx);\n",
        1,
    )

# Disable on empty detail state.
if "validateRequeueButton_->setEnabled(false);" not in cpp:
    cpp = cpp.replace(
        "    requeueButton_->setEnabled(false);\n",
        "    requeueButton_->setEnabled(false);\n"
        "    validateRequeueButton_->setEnabled(false);\n",
        1,
    )

impl = r'''
void T2VHistoryPage::validateSelectedLtxRequeueDraft()
{
    const VideoHistoryItem *item = selectedItem();
    if (!item)
    {
        QMessageBox::information(this,
                                 QStringLiteral("Validate Requeue"),
                                 QStringLiteral("Select an LTX history row first."));
        return;
    }

    const bool isLtx = item->runtimeSummary.contains(QStringLiteral("LTX registry"), Qt::CaseInsensitive)
        || item->stackSummary.contains(QStringLiteral("LTX"), Qt::CaseInsensitive)
        || item->lowModelName.contains(QStringLiteral("ltx"), Qt::CaseInsensitive);

    if (!isLtx)
    {
        QMessageBox::information(this,
                                 QStringLiteral("Validate Requeue"),
                                 QStringLiteral("This action is currently enabled for LTX registry history rows only."));
        return;
    }

    const QString draftPath = expectedLtxRequeueDraftPathForItem(*item);
    if (!QFileInfo::exists(draftPath))
    {
        QMessageBox::information(this,
                                 QStringLiteral("Validate Requeue"),
                                 QStringLiteral("No requeue draft exists yet for this item.\n\nClick Prepare Requeue first, then click Validate Requeue."));
        return;
    }

    const QString repoRoot = spellVisionRepoRootForWorkerClient();
    const QString pythonExe = spellVisionPythonExecutable(repoRoot);
    const QString workerClient = QDir(repoRoot).filePath(QStringLiteral("python/worker_client.py"));

    if (!QFileInfo::exists(workerClient))
    {
        QMessageBox::warning(this,
                             QStringLiteral("Validate Requeue"),
                             QStringLiteral("Could not find worker_client.py from:\n%1").arg(repoRoot));
        return;
    }

    QJsonObject request;
    request.insert(QStringLiteral("command"), QStringLiteral("ltx_requeue_draft_gated_submission"));
    request.insert(QStringLiteral("draft_path"), QDir::toNativeSeparators(draftPath));
    request.insert(QStringLiteral("dry_run"), true);
    request.insert(QStringLiteral("submit_to_comfy"), false);

    QProcess process;
    process.setWorkingDirectory(repoRoot);
    process.setProgram(pythonExe);
    process.setArguments({workerClient});
    process.start();

    if (!process.waitForStarted(10000))
    {
        QMessageBox::warning(this,
                             QStringLiteral("Validate Requeue"),
                             QStringLiteral("Could not start worker client:\n%1").arg(pythonExe));
        return;
    }

    process.write(QJsonDocument(request).toJson(QJsonDocument::Compact));
    process.closeWriteChannel();

    if (!process.waitForFinished(60000))
    {
        process.kill();
        QMessageBox::warning(this,
                             QStringLiteral("Validate Requeue"),
                             QStringLiteral("Timed out waiting for requeue validation."));
        return;
    }

    const QByteArray standardOutput = process.readAllStandardOutput();
    const QByteArray standardError = process.readAllStandardError();

    QString parseError;
    const QJsonObject response = parseLastJsonObjectFromProcessOutput(standardOutput, &parseError);
    if (response.isEmpty())
    {
        QMessageBox::warning(this,
                             QStringLiteral("Validate Requeue"),
                             QStringLiteral("%1\n\nstderr:\n%2\n\nstdout:\n%3")
                                 .arg(parseError, QString::fromUtf8(standardError), QString::fromUtf8(standardOutput)));
        return;
    }

    const bool ok = response.value(QStringLiteral("ok")).toBool(false);
    const bool canSubmit = response.value(QStringLiteral("can_submit")).toBool(false);
    const QString status = response.value(QStringLiteral("submission_status")).toString(QStringLiteral("unknown"));
    const QString mode = response.value(QStringLiteral("execution_mode")).toString(QStringLiteral("dry_run"));
    const QString error = response.value(QStringLiteral("error")).toString();

    if (!ok || !canSubmit)
    {
        const QJsonArray reasons = response.value(QStringLiteral("blocked_submit_reasons")).toArray();
        QStringList reasonText;
        for (const QJsonValue &value : reasons)
            reasonText << value.toString();

        QMessageBox::warning(this,
                             QStringLiteral("Validate Requeue"),
                             QStringLiteral("Requeue validation did not pass.\n\nStatus: %1\nMode: %2\nReasons: %3\nError: %4")
                                 .arg(status, mode, reasonText.join(QStringLiteral(", ")), error));
        return;
    }

    QMessageBox::information(this,
                             QStringLiteral("Requeue Validation Passed"),
                             QStringLiteral("LTX requeue draft is ready for gated submission.\n\nStatus: %1\nMode: %2\nDraft:\n%3")
                                 .arg(status, mode, draftPath));
}

'''

if "void T2VHistoryPage::validateSelectedLtxRequeueDraft()" not in cpp:
    anchor = "void T2VHistoryPage::prepareSelectedLtxRequeueDraft()"
    index = cpp.find(anchor)
    if index < 0:
        raise SystemExit("Could not find prepareSelectedLtxRequeueDraft implementation.")
    cpp = cpp[:index] + impl + "\n" + cpp[index:]

cpp_path.write_text(cpp, encoding="utf-8")

doc_path.parent.mkdir(parents=True, exist_ok=True)
doc_path.write_text(
    "# Sprint 15C Pass 19 — Qt Execute Requeue Draft Action\n\n"
    "Adds a T2V History `Validate Requeue` button for LTX rows.\n\n"
    "The button resolves the Pass 17 `.requeue.json` draft and calls the Pass 18 `ltx_requeue_draft_gated_submission` backend command in dry-run mode.\n\n"
    "This pass does not submit a new LTX job. It validates that the selected draft is ready for gated submission.\n",
    encoding="utf-8",
)

script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Sprint 15C Pass 19 Qt execute requeue draft action.")
