from pathlib import Path
import re

root = Path(".")
history_h = root / "qt_ui" / "T2VHistoryPage.h"
history_cpp = root / "qt_ui" / "T2VHistoryPage.cpp"
doc_path = root / "docs" / "sprints" / "SPRINT15C_PASS17_LTX_REQUEUE_FROM_HISTORY_README.md"
script_path = root / "scripts" / "refactors" / "apply_sprint15c_pass17_ltx_requeue_from_history.py"

h = history_h.read_text(encoding="utf-8")
cpp = history_cpp.read_text(encoding="utf-8")

# Includes.
for include in [
    "#include <QClipboard>",
    "#include <QDir>",
    "#include <QGuiApplication>",
    "#include <QJsonDocument>",
    "#include <QJsonObject>",
    "#include <QMessageBox>",
]:
    if include not in cpp:
        cpp = cpp.replace("#include <QFile>", "#include <QFile>\n" + include, 1)

# Add private methods and button member to header.
if "prepareSelectedLtxRequeueDraft" not in h:
    h = h.replace(
        "    void copyMetadataPath();\n",
        "    void copyMetadataPath();\n"
        "    void prepareSelectedLtxRequeueDraft();\n",
        1,
    )

if "QPushButton *requeueButton_" not in h:
    h = h.replace(
        "    QPushButton *copyMetadataButton_ = nullptr;\n",
        "    QPushButton *copyMetadataButton_ = nullptr;\n"
        "    QPushButton *requeueButton_ = nullptr;\n",
        1,
    )

history_h.write_text(h, encoding="utf-8")

# Helper functions for requeue draft path + safe slug.
helpers = r'''
QString safeRequeueSlug(QString value)
{
    value = value.trimmed();
    if (value.isEmpty())
        value = QStringLiteral("ltx-history-requeue");

    value.replace(QRegularExpression(QStringLiteral("[^A-Za-z0-9_\\-]+")), QStringLiteral("_"));
    value = value.left(96);

    if (value.isEmpty())
        value = QStringLiteral("ltx-history-requeue");

    return value;
}

QString ltxRequeueDraftRoot()
{
    const QProcessEnvironment env = QProcessEnvironment::systemEnvironment();

    const QString explicitPath = env.value(QStringLiteral("SPELLVISION_LTX_REQUEUE_ROOT")).trimmed();
    if (!explicitPath.isEmpty())
        return QDir::fromNativeSeparators(explicitPath);

    const QString runtimeRoot = env.value(QStringLiteral("SPELLVISION_COMFY_RUNTIME_ROOT")).trimmed();
    if (!runtimeRoot.isEmpty())
    {
        return QDir(QDir::fromNativeSeparators(runtimeRoot))
            .filePath(QStringLiteral("spellvision_registry/requeue/ltx"));
    }

    const QString assetRoot = env.value(QStringLiteral("SPELLVISION_ASSET_ROOT")).trimmed();
    if (!assetRoot.isEmpty())
    {
        return QDir(QDir::fromNativeSeparators(assetRoot))
            .filePath(QStringLiteral("comfy_runtime/spellvision_registry/requeue/ltx"));
    }

    return QStringLiteral("D:/AI_ASSETS/comfy_runtime/spellvision_registry/requeue/ltx");
}

QString requeuePromptIdFromRuntimeSummary(const QString &runtimeSummary)
{
    const QString marker = QStringLiteral("requeue-ready");
    const int markerIndex = runtimeSummary.indexOf(marker, 0, Qt::CaseInsensitive);
    if (markerIndex < 0)
        return QString();

    const QString tail = runtimeSummary.mid(markerIndex + marker.size()).trimmed();
    const QString cleaned = tail;
    const QRegularExpression uuidRegex(QStringLiteral("([0-9a-fA-F]{8}\\-[0-9a-fA-F]{4}\\-[0-9a-fA-F]{4}\\-[0-9a-fA-F]{4}\\-[0-9a-fA-F]{12})"));
    const QRegularExpressionMatch match = uuidRegex.match(cleaned);
    if (match.hasMatch())
        return match.captured(1);

    return QString();
}

bool isLtxHistoryItem(const T2VHistoryPage::VideoHistoryItem &item)
{
    return item.runtimeSummary.contains(QStringLiteral("LTX registry"), Qt::CaseInsensitive)
        || item.stackSummary.contains(QStringLiteral("LTX"), Qt::CaseInsensitive)
        || item.lowModelName.contains(QStringLiteral("ltx"), Qt::CaseInsensitive);
}

'''

if "ltxRequeueDraftRoot()" not in cpp:
    namespace_match = re.search(r"namespace\s*\{", cpp)
    if not namespace_match:
        raise SystemExit("Could not find anonymous namespace in T2VHistoryPage.cpp.")
    insert_at = namespace_match.end()
    cpp = cpp[:insert_at] + "\n" + helpers + cpp[insert_at:]

# Add button creation. Prefer placing after Copy Metadata Path.
if "requeueButton_" not in cpp:
    cpp = cpp.replace(
        "copyMetadataButton_ = new QPushButton(QStringLiteral(\"Copy Metadata Path\"), this);",
        "copyMetadataButton_ = new QPushButton(QStringLiteral(\"Copy Metadata Path\"), this);\n"
        "    requeueButton_ = new QPushButton(QStringLiteral(\"Prepare Requeue\"), this);",
        1,
    )

    # Add to layout after copy metadata where possible.
    cpp = cpp.replace(
        "actionsLayout->addWidget(copyMetadataButton_);",
        "actionsLayout->addWidget(copyMetadataButton_);\n"
        "    actionsLayout->addWidget(requeueButton_);",
        1,
    )

    # Connect button.
    cpp = cpp.replace(
        "connect(copyMetadataButton_, &QPushButton::clicked, this, &T2VHistoryPage::copyMetadataPath);",
        "connect(copyMetadataButton_, &QPushButton::clicked, this, &T2VHistoryPage::copyMetadataPath);\n"
        "    connect(requeueButton_, &QPushButton::clicked, this, &T2VHistoryPage::prepareSelectedLtxRequeueDraft);",
        1,
    )

# If the names/layout differ, perform a more tolerant insertion near Copy Metadata Path references.
if "prepareSelectedLtxRequeueDraft" not in cpp:
    # Put implementation before copyMetadataPath or at end.
    pass

impl = r'''
void T2VHistoryPage::prepareSelectedLtxRequeueDraft()
{
    if (selectedIndex_ < 0 || selectedIndex_ >= filteredItems_.size())
    {
        QMessageBox::information(this,
                                 QStringLiteral("Prepare Requeue"),
                                 QStringLiteral("Select an LTX history row first."));
        return;
    }

    const VideoHistoryItem &item = filteredItems_.at(selectedIndex_);
    if (!isLtxHistoryItem(item))
    {
        QMessageBox::information(this,
                                 QStringLiteral("Prepare Requeue"),
                                 QStringLiteral("This action is currently enabled for LTX registry history rows only."));
        return;
    }

    const QString promptId = requeuePromptIdFromRuntimeSummary(item.runtimeSummary);
    const QString draftRoot = ltxRequeueDraftRoot();
    QDir().mkpath(draftRoot);

    const QString slug = safeRequeueSlug(promptId.isEmpty() ? item.promptPreview.left(80) : promptId);
    const QString draftPath = QDir(draftRoot).filePath(QStringLiteral("%1.requeue.json").arg(slug));

    QJsonObject draft;
    draft.insert(QStringLiteral("type"), QStringLiteral("spellvision_ltx_history_requeue_draft"));
    draft.insert(QStringLiteral("schema_version"), 1);
    draft.insert(QStringLiteral("family"), QStringLiteral("ltx"));
    draft.insert(QStringLiteral("task_type"), QStringLiteral("t2v"));
    draft.insert(QStringLiteral("backend"), QStringLiteral("comfy_prompt_api"));
    draft.insert(QStringLiteral("source"), QStringLiteral("T2VHistoryPage"));
    draft.insert(QStringLiteral("registry_prompt_id"), promptId);
    draft.insert(QStringLiteral("prompt"), item.promptPreview);
    draft.insert(QStringLiteral("model"), item.lowModelName);
    draft.insert(QStringLiteral("stack_summary"), item.stackSummary);
    draft.insert(QStringLiteral("duration"), item.durationLabel);
    draft.insert(QStringLiteral("resolution"), item.resolution);
    draft.insert(QStringLiteral("runtime_summary"), item.runtimeSummary);
    draft.insert(QStringLiteral("source_output_path"), item.outputPath);
    draft.insert(QStringLiteral("source_metadata_path"), item.metadataPath);
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

if "void T2VHistoryPage::prepareSelectedLtxRequeueDraft()" not in cpp:
    copy_match = re.search(r"void\s+T2VHistoryPage::copyMetadataPath\s*\(", cpp)
    if copy_match:
        cpp = cpp[:copy_match.start()] + impl + "\n" + cpp[copy_match.start():]
    else:
        cpp += "\n" + impl

# Tolerant fallback for different button/layout names.
if "Prepare Requeue" not in cpp:
    raise SystemExit("Could not insert Prepare Requeue button wiring. Inspect T2VHistoryPage.cpp button layout.")

history_cpp.write_text(cpp, encoding="utf-8")

doc_path.parent.mkdir(parents=True, exist_ok=True)
doc_path.write_text(
'''# Sprint 15C Pass 17 — LTX Requeue From History

## Goal

Add a safe requeue-from-history bridge for completed LTX records.

## What changed

- T2V History now has a `Prepare Requeue` action.
- The action is limited to LTX registry rows.
- It writes a durable requeue draft JSON under:

`D:\\AI_ASSETS\\comfy_runtime\\spellvision_registry\\requeue\\ltx`

## Why this is safe

This pass does not immediately submit another expensive video generation job. It creates a draft with:

- prompt
- model
- source output path
- source metadata path
- registry prompt id when available
- `safe_to_requeue=true`
- `submit_immediately=false`

## Future pass

A later pass can read this draft, confirm workflow/model readiness, then call the gated LTX Prompt API submission route.
''',
    encoding="utf-8",
)

script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Sprint 15C Pass 17 LTX requeue from history.")
