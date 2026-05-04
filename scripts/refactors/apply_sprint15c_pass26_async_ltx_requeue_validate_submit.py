from pathlib import Path

root = Path(".")
h_path = root / "qt_ui" / "T2VHistoryPage.h"
cpp_path = root / "qt_ui" / "T2VHistoryPage.cpp"
doc_path = root / "docs" / "sprints" / "SPRINT15C_PASS26_ASYNC_LTX_REQUEUE_VALIDATE_SUBMIT_README.md"
script_path = root / "scripts" / "refactors" / "apply_sprint15c_pass26_async_ltx_requeue_validate_submit.py"

h = h_path.read_text(encoding="utf-8")
cpp = cpp_path.read_text(encoding="utf-8")

def replace_function(text: str, signature: str, replacement: str) -> str:
    start = text.find(signature)
    if start < 0:
        raise SystemExit(f"Could not find function signature: {signature}")

    brace = text.find("{", start)
    if brace < 0:
        raise SystemExit(f"Could not find opening brace for: {signature}")

    depth = 0
    end = None
    in_string = False
    in_char = False
    escaped = False

    for i in range(brace, len(text)):
        ch = text[i]

        if escaped:
            escaped = False
            continue

        if ch == "\\":
            escaped = True
            continue

        if ch == '"' and not in_char:
            in_string = not in_string
            continue

        if ch == "'" and not in_string:
            in_char = not in_char
            continue

        if in_string or in_char:
            continue

        if ch == "{":
            depth += 1
            continue

        if ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end is None:
        raise SystemExit(f"Could not find closing brace for: {signature}")

    return text[:start] + replacement.rstrip() + "\n" + text[end:]


# Header: forward declaration and async process members.
if "class QProcess;" not in h:
    h = h.replace("class QPushButton;\n", "class QPushButton;\nclass QProcess;\n", 1)

if "activeLtxRequeueValidationProcess_" not in h:
    h = h.replace(
        "    QJsonObject pendingLtxRequeuePreviewContract_;\n",
        "    QJsonObject pendingLtxRequeuePreviewContract_;\n"
        "    QProcess *activeLtxRequeueValidationProcess_ = nullptr;\n"
        "    QProcess *activeLtxRequeueSubmitProcess_ = nullptr;\n",
        1,
    )

h_path.write_text(h, encoding="utf-8")


# Anonymous namespace helper for better nested backend diagnostics.
diagnostic_helpers = r'''
QStringList collectLtxRequeueBlockedReasons(const QJsonObject &response)
{
    QStringList reasons;

    const auto appendArray = [&reasons](const QJsonArray &array)
    {
        for (const QJsonValue &value : array)
        {
            if (value.isString())
            {
                const QString text = value.toString().trimmed();
                if (!text.isEmpty())
                    reasons << text;
                continue;
            }

            if (value.isObject())
            {
                const QString compact = QString::fromUtf8(QJsonDocument(value.toObject()).toJson(QJsonDocument::Compact));
                if (!compact.trimmed().isEmpty())
                    reasons << compact;
            }
        }
    };

    appendArray(response.value(QStringLiteral("blocked_submit_reasons")).toArray());
    appendArray(response.value(QStringLiteral("adapter_blocked_submit_reasons")).toArray());

    const QJsonObject gated = response.value(QStringLiteral("gated_submission")).toObject();
    appendArray(gated.value(QStringLiteral("blocked_submit_reasons")).toArray());
    appendArray(gated.value(QStringLiteral("adapter_blocked_submit_reasons")).toArray());

    if (reasons.isEmpty())
        reasons << QStringLiteral("No explicit blocked reason returned.");

    reasons.removeDuplicates();
    return reasons;
}

QString ltxRequeueErrorText(const QJsonObject &response,
                            const QByteArray &standardError = QByteArray(),
                            const QByteArray &standardOutput = QByteArray())
{
    QString error = response.value(QStringLiteral("error")).toString().trimmed();
    if (error.isEmpty())
        error = response.value(QStringLiteral("submit_error")).toString().trimmed();

    const QJsonObject gated = response.value(QStringLiteral("gated_submission")).toObject();
    if (error.isEmpty())
        error = gated.value(QStringLiteral("error")).toString().trimmed();
    if (error.isEmpty())
        error = gated.value(QStringLiteral("submit_error")).toString().trimmed();

    if (error.isEmpty() && !standardError.trimmed().isEmpty())
        error = QString::fromUtf8(standardError.trimmed());

    if (error.isEmpty() && response.isEmpty() && !standardOutput.trimmed().isEmpty())
        error = QString::fromUtf8(standardOutput.trimmed().left(2000));

    return error;
}

'''

if "collectLtxRequeueBlockedReasons" not in cpp:
    namespace_index = cpp.find("namespace\n{")
    if namespace_index < 0:
        namespace_index = cpp.find("namespace {")
    if namespace_index < 0:
        raise SystemExit("Could not find anonymous namespace.")

    brace = cpp.find("{", namespace_index)
    cpp = cpp[:brace + 1] + "\n\n" + diagnostic_helpers + cpp[brace + 1:]


validate_impl = r'''
void T2VHistoryPage::validateSelectedLtxRequeueDraft()
{
    if (activeLtxRequeueValidationProcess_)
    {
        QMessageBox::information(this,
                                 QStringLiteral("Validate Requeue"),
                                 QStringLiteral("A requeue validation is already running."));
        return;
    }

    const VideoHistoryItem *item = selectedItem();
    if (!item)
    {
        QMessageBox::information(this,
                                 QStringLiteral("Prepare Requeue"),
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

    const QString promptId = requeuePromptIdFromRuntimeSummary(item->runtimeSummary);
    const QString slug = safeRequeueSlug(promptId.isEmpty() ? item->promptPreview.left(80) : promptId);
    const QString draftPath = QDir(ltxRequeueDraftRoot()).filePath(QStringLiteral("%1.requeue.json").arg(slug));

    if (!QFileInfo::exists(draftPath))
    {
        QMessageBox::information(this,
                                 QStringLiteral("Validate Requeue"),
                                 QStringLiteral("No requeue draft exists yet for this item.\n\nClick Prepare Requeue first."));
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
    request.insert(QStringLiteral("wait_for_result"), false);
    request.insert(QStringLiteral("capture_metadata"), true);

    QProcess *process = new QProcess(this);
    activeLtxRequeueValidationProcess_ = process;

    validateRequeueButton_->setEnabled(false);
    validateRequeueButton_->setText(QStringLiteral("Validating..."));
    submitRequeueButton_->setEnabled(false);
    validatedRequeueDraftPath_.clear();

    process->setWorkingDirectory(repoRoot);
    process->setProgram(pythonExe);
    process->setArguments({workerClient});

    connect(process, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this,
            [this, process, draftPath](int exitCode, QProcess::ExitStatus exitStatus)
            {
                const QByteArray standardOutput = process->readAllStandardOutput();
                const QByteArray standardError = process->readAllStandardError();

                if (activeLtxRequeueValidationProcess_ == process)
                    activeLtxRequeueValidationProcess_ = nullptr;

                process->deleteLater();

                validateRequeueButton_->setText(QStringLiteral("Validate Requeue"));

                const VideoHistoryItem *currentItem = selectedItem();
                const bool hasSelection = currentItem != nullptr;
                validateRequeueButton_->setEnabled(hasSelection);
                submitRequeueButton_->setEnabled(false);

                QString parseError;
                const QJsonObject response = parseLastJsonObjectFromProcessOutput(standardOutput, &parseError);

                if (response.isEmpty())
                {
                    QMessageBox::warning(this,
                                         QStringLiteral("Validate Requeue"),
                                         QStringLiteral("Could not parse validation response.\n\nExit code: %1\nExit status: %2\n%3\n\nstderr:\n%4\n\nstdout:\n%5")
                                             .arg(exitCode)
                                             .arg(exitStatus == QProcess::NormalExit ? QStringLiteral("normal") : QStringLiteral("crashed"),
                                                  parseError,
                                                  QString::fromUtf8(standardError),
                                                  QString::fromUtf8(standardOutput)));
                    return;
                }

                const bool ok = response.value(QStringLiteral("ok")).toBool(false);
                const bool canSubmit = response.value(QStringLiteral("can_submit")).toBool(false);
                const QString status = response.value(QStringLiteral("submission_status")).toString(QStringLiteral("unknown"));
                const QString mode = response.value(QStringLiteral("execution_mode")).toString(QStringLiteral("dry_run"));

                if (!ok || !canSubmit)
                {
                    const QStringList reasons = collectLtxRequeueBlockedReasons(response);
                    const QString error = ltxRequeueErrorText(response, standardError, standardOutput);

                    QMessageBox::warning(this,
                                         QStringLiteral("Requeue Validation Failed"),
                                         QStringLiteral("LTX requeue draft is not ready for submission.\n\nStatus: %1\nMode: %2\nReasons: %3\nError: %4")
                                             .arg(status, mode, reasons.join(QStringLiteral(", ")), error));
                    return;
                }

                validatedRequeueDraftPath_ = draftPath;
                submitRequeueButton_->setEnabled(true);

                QMessageBox::information(this,
                                         QStringLiteral("Requeue Validation Passed"),
                                         QStringLiteral("LTX requeue draft is ready for gated submission.\n\nStatus: %1\nMode: %2\nDraft:\n%3")
                                             .arg(status, mode, draftPath));
            });

    connect(process, &QProcess::errorOccurred, this,
            [this, process, pythonExe](QProcess::ProcessError error)
            {
                if (activeLtxRequeueValidationProcess_ == process)
                    activeLtxRequeueValidationProcess_ = nullptr;

                validateRequeueButton_->setText(QStringLiteral("Validate Requeue"));
                validateRequeueButton_->setEnabled(selectedItem() != nullptr);
                submitRequeueButton_->setEnabled(false);

                QMessageBox::warning(this,
                                     QStringLiteral("Validate Requeue"),
                                     QStringLiteral("Could not start or run validation worker.\n\nPython: %1\nProcess error: %2\n%3")
                                         .arg(pythonExe)
                                         .arg(static_cast<int>(error))
                                         .arg(QString::fromUtf8(process->readAllStandardError())));

                process->deleteLater();
            });

    process->start();

    if (!process->waitForStarted(10000))
    {
        activeLtxRequeueValidationProcess_ = nullptr;
        validateRequeueButton_->setText(QStringLiteral("Validate Requeue"));
        validateRequeueButton_->setEnabled(selectedItem() != nullptr);
        submitRequeueButton_->setEnabled(false);
        process->deleteLater();

        QMessageBox::warning(this,
                             QStringLiteral("Validate Requeue"),
                             QStringLiteral("Could not start worker client:\n%1").arg(pythonExe));
        return;
    }

    process->write(QJsonDocument(request).toJson(QJsonDocument::Compact));
    process->closeWriteChannel();
}
'''

submit_impl = r'''
void T2VHistoryPage::submitSelectedLtxRequeueDraft()
{
    if (activeLtxRequeueSubmitProcess_)
    {
        QMessageBox::information(this,
                                 QStringLiteral("Submit Requeue"),
                                 QStringLiteral("A requeue submission is already running."));
        return;
    }

    const VideoHistoryItem *item = selectedItem();
    if (!item)
    {
        QMessageBox::information(this,
                                 QStringLiteral("Submit Requeue"),
                                 QStringLiteral("Select an LTX history row first."));
        return;
    }

    const bool isLtx = item->runtimeSummary.contains(QStringLiteral("LTX registry"), Qt::CaseInsensitive)
        || item->stackSummary.contains(QStringLiteral("LTX"), Qt::CaseInsensitive)
        || item->lowModelName.contains(QStringLiteral("ltx"), Qt::CaseInsensitive);

    if (!isLtx)
    {
        QMessageBox::information(this,
                                 QStringLiteral("Submit Requeue"),
                                 QStringLiteral("This action is currently enabled for LTX registry history rows only."));
        return;
    }

    const QString promptId = requeuePromptIdFromRuntimeSummary(item->runtimeSummary);
    const QString slug = safeRequeueSlug(promptId.isEmpty() ? item->promptPreview.left(80) : promptId);
    const QString draftPath = QDir(ltxRequeueDraftRoot()).filePath(QStringLiteral("%1.requeue.json").arg(slug));

    if (!QFileInfo::exists(draftPath))
    {
        QMessageBox::information(this,
                                 QStringLiteral("Submit Requeue"),
                                 QStringLiteral("No requeue draft exists yet for this item.\n\nClick Prepare Requeue first."));
        return;
    }

    if (validatedRequeueDraftPath_ != draftPath)
    {
        QMessageBox::information(this,
                                 QStringLiteral("Submit Requeue"),
                                 QStringLiteral("Validate this requeue draft before submitting it.\n\nClick Validate Requeue first."));
        return;
    }

    const QMessageBox::StandardButton choice = QMessageBox::question(
        this,
        QStringLiteral("Submit LTX Requeue"),
        QStringLiteral("Submit this LTX requeue draft to Comfy now?\n\nThis can start a GPU-heavy video generation job.\n\nDraft:\n%1")
            .arg(draftPath),
        QMessageBox::Yes | QMessageBox::No,
        QMessageBox::No);

    if (choice != QMessageBox::Yes)
        return;

    const QString repoRoot = spellVisionRepoRootForWorkerClient();
    const QString pythonExe = spellVisionPythonExecutable(repoRoot);
    const QString workerClient = QDir(repoRoot).filePath(QStringLiteral("python/worker_client.py"));

    if (!QFileInfo::exists(workerClient))
    {
        QMessageBox::warning(this,
                             QStringLiteral("Submit Requeue"),
                             QStringLiteral("Could not find worker_client.py from:\n%1").arg(repoRoot));
        return;
    }

    QJsonObject request;
    request.insert(QStringLiteral("command"), QStringLiteral("ltx_requeue_draft_gated_submission"));
    request.insert(QStringLiteral("draft_path"), QDir::toNativeSeparators(draftPath));
    request.insert(QStringLiteral("dry_run"), false);
    request.insert(QStringLiteral("submit_to_comfy"), true);
    request.insert(QStringLiteral("wait_for_result"), false);
    request.insert(QStringLiteral("capture_metadata"), true);

    QProcess *process = new QProcess(this);
    activeLtxRequeueSubmitProcess_ = process;

    requeueButton_->setEnabled(false);
    validateRequeueButton_->setEnabled(false);
    submitRequeueButton_->setEnabled(false);
    submitRequeueButton_->setText(QStringLiteral("Submitting..."));

    process->setWorkingDirectory(repoRoot);
    process->setProgram(pythonExe);
    process->setArguments({workerClient});

    connect(process, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this,
            [this, process, draftPath](int exitCode, QProcess::ExitStatus exitStatus)
            {
                const QByteArray standardOutput = process->readAllStandardOutput();
                const QByteArray standardError = process->readAllStandardError();

                if (activeLtxRequeueSubmitProcess_ == process)
                    activeLtxRequeueSubmitProcess_ = nullptr;

                process->deleteLater();

                requeueButton_->setEnabled(selectedItem() != nullptr);
                validateRequeueButton_->setEnabled(selectedItem() != nullptr);
                submitRequeueButton_->setText(QStringLiteral("Submit Requeue"));
                submitRequeueButton_->setEnabled(validatedRequeueDraftPath_ == draftPath);

                QString parseError;
                const QJsonObject response = parseLastJsonObjectFromProcessOutput(standardOutput, &parseError);

                if (response.isEmpty())
                {
                    QMessageBox::warning(this,
                                         QStringLiteral("Submit Requeue"),
                                         QStringLiteral("Could not parse submission response.\n\nExit code: %1\nExit status: %2\n%3\n\nstderr:\n%4\n\nstdout:\n%5")
                                             .arg(exitCode)
                                             .arg(exitStatus == QProcess::NormalExit ? QStringLiteral("normal") : QStringLiteral("crashed"),
                                                  parseError,
                                                  QString::fromUtf8(standardError),
                                                  QString::fromUtf8(standardOutput)));
                    return;
                }

                const bool ok = response.value(QStringLiteral("ok")).toBool(false);
                const bool submitted = response.value(QStringLiteral("submitted")).toBool(false);
                const QString status = response.value(QStringLiteral("submission_status")).toString(QStringLiteral("unknown"));
                const QString mode = response.value(QStringLiteral("execution_mode")).toString(QStringLiteral("submit"));
                const QString promptIdResult = response.value(QStringLiteral("prompt_id")).toString();
                const QString error = ltxRequeueErrorText(response, standardError, standardOutput);

                if (!ok || !submitted)
                {
                    const QStringList reasons = collectLtxRequeueBlockedReasons(response);

                    QMessageBox::warning(this,
                                         QStringLiteral("Submit Requeue"),
                                         QStringLiteral("Requeue submission did not start.\n\nStatus: %1\nMode: %2\nReasons: %3\nError: %4")
                                             .arg(status, mode, reasons.join(QStringLiteral(", ")), error));
                    return;
                }

                validatedRequeueDraftPath_.clear();
                submitRequeueButton_->setEnabled(false);
                scheduleRefreshAfterLtxRequeueSubmit(response);

                QMessageBox::information(this,
                                         QStringLiteral("Requeue Submitted"),
                                         QStringLiteral("LTX requeue was submitted to Comfy.\n\nStatus: %1\nMode: %2\nPrompt ID: %3\n\nHistory and queue views are refreshing. The latest requeue output will be selected when it appears, and a queue/preview contract has been published.")
                                             .arg(status, mode, promptIdResult));
            });

    connect(process, &QProcess::errorOccurred, this,
            [this, process, pythonExe](QProcess::ProcessError error)
            {
                if (activeLtxRequeueSubmitProcess_ == process)
                    activeLtxRequeueSubmitProcess_ = nullptr;

                requeueButton_->setEnabled(selectedItem() != nullptr);
                validateRequeueButton_->setEnabled(selectedItem() != nullptr);
                submitRequeueButton_->setText(QStringLiteral("Submit Requeue"));
                submitRequeueButton_->setEnabled(false);

                QMessageBox::warning(this,
                                     QStringLiteral("Submit Requeue"),
                                     QStringLiteral("Could not start or run submit worker.\n\nPython: %1\nProcess error: %2\n%3")
                                         .arg(pythonExe)
                                         .arg(static_cast<int>(error))
                                         .arg(QString::fromUtf8(process->readAllStandardError())));

                process->deleteLater();
            });

    process->start();

    if (!process->waitForStarted(10000))
    {
        activeLtxRequeueSubmitProcess_ = nullptr;
        requeueButton_->setEnabled(selectedItem() != nullptr);
        validateRequeueButton_->setEnabled(selectedItem() != nullptr);
        submitRequeueButton_->setText(QStringLiteral("Submit Requeue"));
        submitRequeueButton_->setEnabled(false);
        process->deleteLater();

        QMessageBox::warning(this,
                             QStringLiteral("Submit Requeue"),
                             QStringLiteral("Could not start worker client:\n%1").arg(pythonExe));
        return;
    }

    process->write(QJsonDocument(request).toJson(QJsonDocument::Compact));
    process->closeWriteChannel();
}
'''

cpp = replace_function(cpp, "void T2VHistoryPage::validateSelectedLtxRequeueDraft()", validate_impl)
cpp = replace_function(cpp, "void T2VHistoryPage::submitSelectedLtxRequeueDraft()", submit_impl)

cpp_path.write_text(cpp, encoding="utf-8")

doc_path.parent.mkdir(parents=True, exist_ok=True)
doc_path.write_text(
    "# Sprint 15C Pass 26 — Async LTX Requeue Validate/Submit Worker Calls\n\n"
    "Moves LTX requeue validation and submission off the UI thread.\n\n"
    "Changes:\n\n"
    "- `Validate Requeue` now starts an owned `QProcess` and returns immediately.\n"
    "- `Submit Requeue` now starts an owned `QProcess` and returns immediately after confirmation.\n"
    "- Buttons are disabled while validation/submission is running.\n"
    "- Buttons show `Validating...` and `Submitting...` state text.\n"
    "- Nested `blocked_submit_reasons`, `adapter_blocked_submit_reasons`, `submit_error`, stdout, and stderr are surfaced in failure dialogs.\n"
    "- The existing guarded `Prepare → Validate → Submit` flow remains intact.\n\n"
    "This pass removes the short UI freeze caused by synchronous `waitForFinished()` calls while preserving the backend gated submission contract.\n",
    encoding="utf-8",
)

script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Sprint 15C Pass 26 async LTX requeue validate/submit worker calls.")
