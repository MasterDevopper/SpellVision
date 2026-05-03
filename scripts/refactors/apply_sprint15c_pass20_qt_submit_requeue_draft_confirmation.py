from pathlib import Path
import re

root = Path(".")
h_path = root / "qt_ui" / "T2VHistoryPage.h"
cpp_path = root / "qt_ui" / "T2VHistoryPage.cpp"
doc_path = root / "docs" / "sprints" / "SPRINT15C_PASS20_QT_SUBMIT_REQUEUE_DRAFT_CONFIRMATION_README.md"
script_path = root / "scripts" / "refactors" / "apply_sprint15c_pass20_qt_submit_requeue_draft_confirmation.py"

h = h_path.read_text(encoding="utf-8")
cpp = cpp_path.read_text(encoding="utf-8")

# Header slot/member/state.
if "submitSelectedLtxRequeueDraft" not in h:
    h = h.replace(
        "    void validateSelectedLtxRequeueDraft();\n",
        "    void validateSelectedLtxRequeueDraft();\n"
        "    void submitSelectedLtxRequeueDraft();\n",
        1,
    )

if "QPushButton *submitRequeueButton_" not in h:
    h = h.replace(
        "    QPushButton *validateRequeueButton_ = nullptr;\n",
        "    QPushButton *validateRequeueButton_ = nullptr;\n"
        "    QPushButton *submitRequeueButton_ = nullptr;\n",
        1,
    )

if "QString validatedRequeueDraftPath_" not in h:
    # Insert near member fields.
    h = h.replace(
        "    QPushButton *submitRequeueButton_ = nullptr;\n",
        "    QPushButton *submitRequeueButton_ = nullptr;\n"
        "    QString validatedRequeueDraftPath_;\n",
        1,
    )

h_path.write_text(h, encoding="utf-8")

# Construct Submit Requeue button next to Validate Requeue.
if "submitRequeueButton_ = new QPushButton(QStringLiteral(\"Submit Requeue\"), details);" not in cpp:
    cpp = cpp.replace(
        "    validateRequeueButton_ = new QPushButton(QStringLiteral(\"Validate Requeue\"), details);\n"
        "    validateRequeueButton_->setObjectName(QStringLiteral(\"HistoryActionButton\"));\n",
        "    validateRequeueButton_ = new QPushButton(QStringLiteral(\"Validate Requeue\"), details);\n"
        "    validateRequeueButton_->setObjectName(QStringLiteral(\"HistoryActionButton\"));\n"
        "    submitRequeueButton_ = new QPushButton(QStringLiteral(\"Submit Requeue\"), details);\n"
        "    submitRequeueButton_->setObjectName(QStringLiteral(\"HistoryActionButton\"));\n"
        "    submitRequeueButton_->setEnabled(false);\n",
        1,
    )

# Connect Submit Requeue.
if "connect(submitRequeueButton_, &QPushButton::clicked, this, &T2VHistoryPage::submitSelectedLtxRequeueDraft);" not in cpp:
    cpp = cpp.replace(
        "    connect(validateRequeueButton_, &QPushButton::clicked, this, &T2VHistoryPage::validateSelectedLtxRequeueDraft);\n",
        "    connect(validateRequeueButton_, &QPushButton::clicked, this, &T2VHistoryPage::validateSelectedLtxRequeueDraft);\n"
        "    connect(submitRequeueButton_, &QPushButton::clicked, this, &T2VHistoryPage::submitSelectedLtxRequeueDraft);\n",
        1,
    )

# Add to visible action row.
if "copyActions->addWidget(submitRequeueButton_);" not in cpp:
    cpp = cpp.replace(
        "    copyActions->addWidget(validateRequeueButton_);\n",
        "    copyActions->addWidget(validateRequeueButton_);\n"
        "    copyActions->addWidget(submitRequeueButton_);\n",
        1,
    )

# Reset submit state when a new item is selected/rendered.
if "validatedRequeueDraftPath_.clear();" not in cpp:
    cpp = cpp.replace(
        "    validateRequeueButton_->setEnabled(selectedItemIsLtx);\n",
        "    validateRequeueButton_->setEnabled(selectedItemIsLtx);\n"
        "    validatedRequeueDraftPath_.clear();\n"
        "    submitRequeueButton_->setEnabled(false);\n",
        1,
    )

# Disable submit in empty detail state.
if "submitRequeueButton_->setEnabled(false);" not in cpp:
    cpp = cpp.replace(
        "    validateRequeueButton_->setEnabled(false);\n",
        "    validateRequeueButton_->setEnabled(false);\n"
        "    submitRequeueButton_->setEnabled(false);\n",
        1,
    )

# Ensure validation success records the validated draft path and enables Submit.
validation_success_old = '''    QMessageBox::information(this,
                             QStringLiteral("Requeue Validation Passed"),
                             QStringLiteral("LTX requeue draft is ready for gated submission.\\n\\nStatus: %1\\nMode: %2\\nDraft:\\n%3")
                                 .arg(status, mode, draftPath));
}
'''

validation_success_new = '''    validatedRequeueDraftPath_ = draftPath;
    submitRequeueButton_->setEnabled(true);

    QMessageBox::information(this,
                             QStringLiteral("Requeue Validation Passed"),
                             QStringLiteral("LTX requeue draft is ready for gated submission.\\n\\nStatus: %1\\nMode: %2\\nDraft:\\n%3")
                                 .arg(status, mode, draftPath));
}
'''

if validation_success_old in cpp and "validatedRequeueDraftPath_ = draftPath;" not in cpp:
    cpp = cpp.replace(validation_success_old, validation_success_new, 1)

# Add submit implementation before prepareSelectedLtxRequeueDraft.
impl = r'''
void T2VHistoryPage::submitSelectedLtxRequeueDraft()
{
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

    QProcess process;
    process.setWorkingDirectory(repoRoot);
    process.setProgram(pythonExe);
    process.setArguments({workerClient});
    process.start();

    if (!process.waitForStarted(10000))
    {
        QMessageBox::warning(this,
                             QStringLiteral("Submit Requeue"),
                             QStringLiteral("Could not start worker client:\n%1").arg(pythonExe));
        return;
    }

    process.write(QJsonDocument(request).toJson(QJsonDocument::Compact));
    process.closeWriteChannel();

    if (!process.waitForFinished(120000))
    {
        process.kill();
        QMessageBox::warning(this,
                             QStringLiteral("Submit Requeue"),
                             QStringLiteral("Timed out waiting for requeue submission response."));
        return;
    }

    const QByteArray standardOutput = process.readAllStandardOutput();
    const QByteArray standardError = process.readAllStandardError();

    QString parseError;
    const QJsonObject response = parseLastJsonObjectFromProcessOutput(standardOutput, &parseError);
    if (response.isEmpty())
    {
        QMessageBox::warning(this,
                             QStringLiteral("Submit Requeue"),
                             QStringLiteral("%1\n\nstderr:\n%2\n\nstdout:\n%3")
                                 .arg(parseError, QString::fromUtf8(standardError), QString::fromUtf8(standardOutput)));
        return;
    }

    const bool ok = response.value(QStringLiteral("ok")).toBool(false);
    const bool submitted = response.value(QStringLiteral("submitted")).toBool(false);
    const QString status = response.value(QStringLiteral("submission_status")).toString(QStringLiteral("unknown"));
    const QString mode = response.value(QStringLiteral("execution_mode")).toString(QStringLiteral("submit"));
    const QString promptIdResult = response.value(QStringLiteral("prompt_id")).toString();
    const QString error = response.value(QStringLiteral("error")).toString(response.value(QStringLiteral("submit_error")).toString());

    if (!ok || !submitted)
    {
        const QJsonArray reasons = response.value(QStringLiteral("blocked_submit_reasons")).toArray();
        QStringList reasonText;
        for (const QJsonValue &value : reasons)
            reasonText << value.toString();

        QMessageBox::warning(this,
                             QStringLiteral("Submit Requeue"),
                             QStringLiteral("Requeue submission did not start.\n\nStatus: %1\nMode: %2\nReasons: %3\nError: %4")
                                 .arg(status, mode, reasonText.join(QStringLiteral(", ")), error));
        return;
    }

    QMessageBox::information(this,
                             QStringLiteral("Requeue Submitted"),
                             QStringLiteral("LTX requeue was submitted to Comfy.\n\nStatus: %1\nMode: %2\nPrompt ID: %3")
                                 .arg(status, mode, promptIdResult));
}

'''

if "void T2VHistoryPage::submitSelectedLtxRequeueDraft()" not in cpp:
    anchor = "void T2VHistoryPage::prepareSelectedLtxRequeueDraft()"
    index = cpp.find(anchor)
    if index < 0:
        raise SystemExit("Could not find prepareSelectedLtxRequeueDraft implementation.")
    cpp = cpp[:index] + impl + "\n" + cpp[index:]

cpp_path.write_text(cpp, encoding="utf-8")

doc_path.parent.mkdir(parents=True, exist_ok=True)
doc_path.write_text(
    "# Sprint 15C Pass 20 — Qt Submit Requeue Draft With Confirmation\n\n"
    "Adds a guarded `Submit Requeue` button to T2V History LTX rows.\n\n"
    "The button remains disabled until `Validate Requeue` succeeds for the selected draft.\n\n"
    "Submission asks for confirmation, then calls `ltx_requeue_draft_gated_submission` with `submit_to_comfy=true` and `dry_run=false`.\n\n"
    "The UI does not wait for the full video result in this pass; it only confirms that the job was submitted.\n",
    encoding="utf-8",
)

script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Sprint 15C Pass 20 Qt submit requeue draft confirmation.")
