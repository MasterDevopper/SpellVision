from pathlib import Path
import re

root = Path(".")
history_h = root / "qt_ui" / "T2VHistoryPage.h"
history_cpp = root / "qt_ui" / "T2VHistoryPage.cpp"

h = history_h.read_text(encoding="utf-8")
cpp = history_cpp.read_text(encoding="utf-8")

# 1) Ensure the slot declaration exists using the actual current method name.
if "prepareSelectedLtxRequeueDraft" not in h:
    if "void copySelectedMetadataPath();" in h:
        h = h.replace(
            "    void copySelectedMetadataPath();\n",
            "    void copySelectedMetadataPath();\n"
            "    void prepareSelectedLtxRequeueDraft();\n",
            1,
        )
    elif "void copyMetadataPath();" in h:
        h = h.replace(
            "    void copyMetadataPath();\n",
            "    void copyMetadataPath();\n"
            "    void prepareSelectedLtxRequeueDraft();\n",
            1,
        )
    else:
        raise SystemExit("Could not find metadata-copy slot in T2VHistoryPage.h.")

# 2) Ensure button member exists using the actual current member name.
if "QPushButton *requeueButton_" not in h:
    if "QPushButton *copyMetadataPathButton_ = nullptr;" in h:
        h = h.replace(
            "    QPushButton *copyMetadataPathButton_ = nullptr;\n",
            "    QPushButton *copyMetadataPathButton_ = nullptr;\n"
            "    QPushButton *requeueButton_ = nullptr;\n",
            1,
        )
    elif "QPushButton *copyMetadataButton_ = nullptr;" in h:
        h = h.replace(
            "    QPushButton *copyMetadataButton_ = nullptr;\n",
            "    QPushButton *copyMetadataButton_ = nullptr;\n"
            "    QPushButton *requeueButton_ = nullptr;\n",
            1,
        )
    else:
        raise SystemExit("Could not find metadata-copy button member in T2VHistoryPage.h.")

history_h.write_text(h, encoding="utf-8")

# 3) Remove invalid anonymous-namespace helper that takes private VideoHistoryItem.
cpp = re.sub(
    r'\n\s*bool\s+isLtxHistoryItem\s*\(\s*const\s+T2VHistoryPage::VideoHistoryItem\s*&\s*item\s*\)\s*\{.*?\n\s*\}\s*\n',
    "\n",
    cpp,
    flags=re.DOTALL,
)

# 4) Wire the button with the actual current button/method names.
if "requeueButton_ = new QPushButton(QStringLiteral(\"Prepare Requeue\"), this);" not in cpp:
    if "copyMetadataPathButton_ = new QPushButton(QStringLiteral(\"Copy Metadata Path\"), this);" in cpp:
        cpp = cpp.replace(
            "copyMetadataPathButton_ = new QPushButton(QStringLiteral(\"Copy Metadata Path\"), this);",
            "copyMetadataPathButton_ = new QPushButton(QStringLiteral(\"Copy Metadata Path\"), this);\n"
            "    requeueButton_ = new QPushButton(QStringLiteral(\"Prepare Requeue\"), this);",
            1,
        )
    elif "copyMetadataButton_ = new QPushButton(QStringLiteral(\"Copy Metadata Path\"), this);" in cpp:
        cpp = cpp.replace(
            "copyMetadataButton_ = new QPushButton(QStringLiteral(\"Copy Metadata Path\"), this);",
            "copyMetadataButton_ = new QPushButton(QStringLiteral(\"Copy Metadata Path\"), this);\n"
            "    requeueButton_ = new QPushButton(QStringLiteral(\"Prepare Requeue\"), this);",
            1,
        )

if "addWidget(requeueButton_)" not in cpp:
    if "actionsLayout->addWidget(copyMetadataPathButton_);" in cpp:
        cpp = cpp.replace(
            "actionsLayout->addWidget(copyMetadataPathButton_);",
            "actionsLayout->addWidget(copyMetadataPathButton_);\n"
            "    actionsLayout->addWidget(requeueButton_);",
            1,
        )
    elif "actionsLayout->addWidget(copyMetadataButton_);" in cpp:
        cpp = cpp.replace(
            "actionsLayout->addWidget(copyMetadataButton_);",
            "actionsLayout->addWidget(copyMetadataButton_);\n"
            "    actionsLayout->addWidget(requeueButton_);",
            1,
        )

if "prepareSelectedLtxRequeueDraft" not in cpp.split("connect", 1)[-1]:
    if "connect(copyMetadataPathButton_, &QPushButton::clicked, this, &T2VHistoryPage::copySelectedMetadataPath);" in cpp:
        cpp = cpp.replace(
            "connect(copyMetadataPathButton_, &QPushButton::clicked, this, &T2VHistoryPage::copySelectedMetadataPath);",
            "connect(copyMetadataPathButton_, &QPushButton::clicked, this, &T2VHistoryPage::copySelectedMetadataPath);\n"
            "    connect(requeueButton_, &QPushButton::clicked, this, &T2VHistoryPage::prepareSelectedLtxRequeueDraft);",
            1,
        )
    elif "connect(copyMetadataButton_, &QPushButton::clicked, this, &T2VHistoryPage::copyMetadataPath);" in cpp:
        cpp = cpp.replace(
            "connect(copyMetadataButton_, &QPushButton::clicked, this, &T2VHistoryPage::copyMetadataPath);",
            "connect(copyMetadataButton_, &QPushButton::clicked, this, &T2VHistoryPage::copyMetadataPath);\n"
            "    connect(requeueButton_, &QPushButton::clicked, this, &T2VHistoryPage::prepareSelectedLtxRequeueDraft);",
            1,
        )

# 5) Replace the broken implementation with one that uses selectedItem().
impl = r'''
void T2VHistoryPage::prepareSelectedLtxRequeueDraft()
{
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
                                 QStringLiteral("Prepare Requeue"),
                                 QStringLiteral("This action is currently enabled for LTX registry history rows only."));
        return;
    }

    const QString promptId = requeuePromptIdFromRuntimeSummary(item->runtimeSummary);
    const QString draftRoot = ltxRequeueDraftRoot();
    QDir().mkpath(draftRoot);

    const QString slug = safeRequeueSlug(promptId.isEmpty() ? item->promptPreview.left(80) : promptId);
    const QString draftPath = QDir(draftRoot).filePath(QStringLiteral("%1.requeue.json").arg(slug));

    QJsonObject draft;
    draft.insert(QStringLiteral("type"), QStringLiteral("spellvision_ltx_history_requeue_draft"));
    draft.insert(QStringLiteral("schema_version"), 1);
    draft.insert(QStringLiteral("family"), QStringLiteral("ltx"));
    draft.insert(QStringLiteral("task_type"), QStringLiteral("t2v"));
    draft.insert(QStringLiteral("backend"), QStringLiteral("comfy_prompt_api"));
    draft.insert(QStringLiteral("source"), QStringLiteral("T2VHistoryPage"));
    draft.insert(QStringLiteral("registry_prompt_id"), promptId);
    draft.insert(QStringLiteral("prompt"), item->promptPreview);
    draft.insert(QStringLiteral("model"), item->lowModelName);
    draft.insert(QStringLiteral("stack_summary"), item->stackSummary);
    draft.insert(QStringLiteral("duration"), item->durationLabel);
    draft.insert(QStringLiteral("resolution"), item->resolution);
    draft.insert(QStringLiteral("runtime_summary"), item->runtimeSummary);
    draft.insert(QStringLiteral("source_output_path"), item->outputPath);
    draft.insert(QStringLiteral("source_metadata_path"), item->metadataPath);
    draft.insert(QStringLiteral("safe_to_requeue"), true);
    draft.insert(QStringLiteral("submit_immediately"), false);
    draft.insert(QStringLiteral("next_command_hint"), QStringLiteral("ltx_prompt_api_gated_submission"));
    draft.insert(QStringLiteral("note"), QStringLiteral("This is a safe requeue draft. A later pass can turn this into one-click submission after confirming model/workflow readiness."));

    QFile outFile(draftPath);
    if (!outFile.open(QIODevice::WriteOnly | QIODevice::Truncate))
    {
        QMessageBox::warning(this,
                             QStringLiteral("Prepare Requeue"),
                             QStringLiteral("Could not write requeue draft:\n%1").arg(draftPath));
        return;
    }

    outFile.write(QJsonDocument(draft).toJson(QJsonDocument::Indented));
    outFile.close();

    if (QClipboard *clipboard = QGuiApplication::clipboard())
        clipboard->setText(draftPath);

    QMessageBox::information(this,
                             QStringLiteral("LTX Requeue Draft Ready"),
                             QStringLiteral("Created a safe LTX requeue draft and copied its path to the clipboard.\n\n%1").arg(draftPath));
}

'''

pattern = r'\nvoid\s+T2VHistoryPage::prepareSelectedLtxRequeueDraft\s*\(\s*\)\s*\{.*?\n\}\s*\n'
if re.search(pattern, cpp, flags=re.DOTALL):
    cpp = re.sub(pattern, "\n" + impl + "\n", cpp, count=1, flags=re.DOTALL)
else:
    copy_match = re.search(r"void\s+T2VHistoryPage::copySelectedMetadataPath\s*\(", cpp)
    if not copy_match:
        copy_match = re.search(r"void\s+T2VHistoryPage::copyMetadataPath\s*\(", cpp)
    if copy_match:
        cpp = cpp[:copy_match.start()] + impl + "\n" + cpp[copy_match.start():]
    else:
        cpp += "\n" + impl

history_cpp.write_text(cpp, encoding="utf-8")

print("Repaired Sprint 15C Pass 17 T2VHistoryPage requeue integration.")
