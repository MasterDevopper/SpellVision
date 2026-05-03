from pathlib import Path
import re

root = Path(".")
h_path = root / "qt_ui" / "T2VHistoryPage.h"
cpp_path = root / "qt_ui" / "T2VHistoryPage.cpp"
doc_path = root / "docs" / "sprints" / "SPRINT15C_PASS23_LTX_REQUEUE_QUEUE_PREVIEW_CONTRACT_README.md"
script_path = root / "scripts" / "refactors" / "apply_sprint15c_pass23_ltx_requeue_queue_preview_contract.py"

h = h_path.read_text(encoding="utf-8")
cpp = cpp_path.read_text(encoding="utf-8")

# Header: promote signal and helper declarations.
if "ltxRequeuePreviewContractReady" not in h:
    h = h.replace(
        "    void ltxRequeueSubmitted(const QString &promptId, const QString &primaryOutputPath);\n",
        "    void ltxRequeueSubmitted(const QString &promptId, const QString &primaryOutputPath);\n"
        "    void ltxRequeuePreviewContractReady(const QJsonObject &contract);\n",
        1,
    )

if "buildLtxRequeueQueuePreviewContract" not in h:
    h = h.replace(
        "    void focusLatestLtxRequeueOutputAfterRefresh();\n",
        "    void focusLatestLtxRequeueOutputAfterRefresh();\n"
        "    QJsonObject buildLtxRequeueQueuePreviewContract(const QJsonObject &response) const;\n"
        "    void persistLatestLtxRequeueQueuePreviewContract(const QJsonObject &contract) const;\n",
        1,
    )

if "pendingLtxRequeuePreviewContract_" not in h:
    h = h.replace(
        "    QString pendingLtxRequeuePrimaryOutputPath_;\n",
        "    QString pendingLtxRequeuePrimaryOutputPath_;\n"
        "    QJsonObject pendingLtxRequeuePreviewContract_;\n",
        1,
    )

h_path.write_text(h, encoding="utf-8")

# Includes.
for include in [
    "#include <QDateTime>",
    "#include <QSaveFile>",
]:
    if include not in cpp:
        cpp = cpp.replace("#include <QFile>", "#include <QFile>\n" + include, 1)

# Anonymous namespace helpers.
helpers = r'''
QJsonObject firstObjectFromArray(const QJsonArray &array)
{
    for (const QJsonValue &value : array)
    {
        if (value.isObject())
            return value.toObject();
    }

    return {};
}

QString stringFromObjectPath(const QJsonObject &object, const QStringList &keys)
{
    for (const QString &key : keys)
    {
        const QString value = object.value(key).toString();
        if (!value.isEmpty())
            return value;
    }

    return {};
}

qint64 int64FromObjectPath(const QJsonObject &object, const QStringList &keys, qint64 fallback = 0)
{
    for (const QString &key : keys)
    {
        const QJsonValue value = object.value(key);
        if (value.isDouble())
            return static_cast<qint64>(value.toDouble());
    }

    return fallback;
}

QString latestLtxRequeueUiContractPath()
{
    const QString root = QDir(QStringLiteral("D:/AI_ASSETS/comfy_runtime/spellvision_registry/ui")).absolutePath();
    QDir().mkpath(root);
    return QDir(root).filePath(QStringLiteral("latest_ltx_requeue_queue_preview_contract.json"));
}

'''

if "QJsonObject firstObjectFromArray(const QJsonArray &array)" not in cpp:
    namespace_match = re.search(r"namespace\s*\{", cpp)
    if not namespace_match:
        raise SystemExit("Could not find anonymous namespace in T2VHistoryPage.cpp.")
    cpp = cpp[:namespace_match.end()] + "\n" + helpers + cpp[namespace_match.end():]

# Add contract builder + persistence implementation before scheduleRefresh.
contract_impl = r'''
QJsonObject T2VHistoryPage::buildLtxRequeueQueuePreviewContract(const QJsonObject &response) const
{
    const QJsonObject spellvisionResult = response.value(QStringLiteral("spellvision_result")).toObject();
    const QJsonObject queueEvent = response.value(QStringLiteral("queue_result_event")).toObject();
    const QJsonObject historyRecord = response.value(QStringLiteral("history_record")).toObject();
    const QJsonObject primaryOutput = response.value(QStringLiteral("primary_output")).toObject();

    QJsonObject resultPrimaryOutput = spellvisionResult.value(QStringLiteral("primary_output")).toObject();
    if (resultPrimaryOutput.isEmpty())
        resultPrimaryOutput = primaryOutput;

    const QJsonArray uiOutputs = response.value(QStringLiteral("ui_outputs")).toArray();
    const QJsonObject firstUiOutput = firstObjectFromArray(uiOutputs);

    QJsonObject output = resultPrimaryOutput;
    if (output.isEmpty())
        output = firstUiOutput;

    const QString promptId = response.value(QStringLiteral("prompt_id")).toString();
    const QString outputPath = stringFromObjectPath(output, {
        QStringLiteral("path"),
        QStringLiteral("preview_path"),
        QStringLiteral("uri"),
    });

    const QString metadataPath = stringFromObjectPath(output, {
        QStringLiteral("metadata_path"),
        QStringLiteral("primary_metadata_path"),
    });

    const QString filename = stringFromObjectPath(output, {
        QStringLiteral("filename"),
    });

    QJsonObject contract;
    contract.insert(QStringLiteral("type"), QStringLiteral("spellvision_ltx_requeue_queue_preview_contract"));
    contract.insert(QStringLiteral("schema_version"), 1);
    contract.insert(QStringLiteral("created_at"), QDateTime::currentDateTimeUtc().toString(Qt::ISODateWithMs));
    contract.insert(QStringLiteral("family"), QStringLiteral("ltx"));
    contract.insert(QStringLiteral("task_type"), QStringLiteral("t2v"));
    contract.insert(QStringLiteral("backend"), QStringLiteral("comfy_prompt_api"));
    contract.insert(QStringLiteral("source"), QStringLiteral("history_requeue_submit"));
    contract.insert(QStringLiteral("prompt_id"), promptId);
    contract.insert(QStringLiteral("state"), response.value(QStringLiteral("submission_status")).toString(QStringLiteral("submitted")));
    contract.insert(QStringLiteral("execution_mode"), response.value(QStringLiteral("execution_mode")).toString(QStringLiteral("submit")));
    contract.insert(QStringLiteral("submitted"), response.value(QStringLiteral("submitted")).toBool(false));
    contract.insert(QStringLiteral("completed"), response.value(QStringLiteral("result_completed")).toBool(false));
    contract.insert(QStringLiteral("queue_ready"), spellvisionResult.value(QStringLiteral("queue_ready")).toBool(!queueEvent.isEmpty()));
    contract.insert(QStringLiteral("history_ready"), spellvisionResult.value(QStringLiteral("history_ready")).toBool(!historyRecord.isEmpty()));
    contract.insert(QStringLiteral("preview_ready"), spellvisionResult.value(QStringLiteral("preview_ready")).toBool(!outputPath.isEmpty()));
    contract.insert(QStringLiteral("primary_output_path"), outputPath);
    contract.insert(QStringLiteral("primary_metadata_path"), metadataPath);
    contract.insert(QStringLiteral("primary_filename"), filename);
    contract.insert(QStringLiteral("output_count"), spellvisionResult.value(QStringLiteral("output_count")).toInt(uiOutputs.size()));
    contract.insert(QStringLiteral("size_bytes"), static_cast<double>(int64FromObjectPath(output, {QStringLiteral("size_bytes")})));
    contract.insert(QStringLiteral("openable"), output.value(QStringLiteral("openable")).toBool(QFileInfo::exists(outputPath)));
    contract.insert(QStringLiteral("animated"), output.value(QStringLiteral("animated")).toBool(true));
    contract.insert(QStringLiteral("send_to_mode"), output.value(QStringLiteral("send_to_mode")).toString(QStringLiteral("t2v")));

    QJsonObject preview;
    preview.insert(QStringLiteral("kind"), output.value(QStringLiteral("kind")).toString(QStringLiteral("video")));
    preview.insert(QStringLiteral("role"), output.value(QStringLiteral("role")).toString(QStringLiteral("full")));
    preview.insert(QStringLiteral("label"), output.value(QStringLiteral("label")).toString(QStringLiteral("LTX Full")));
    preview.insert(QStringLiteral("path"), outputPath);
    preview.insert(QStringLiteral("metadata_path"), metadataPath);
    preview.insert(QStringLiteral("filename"), filename);
    preview.insert(QStringLiteral("exists"), QFileInfo::exists(outputPath));
    preview.insert(QStringLiteral("openable"), output.value(QStringLiteral("openable")).toBool(QFileInfo::exists(outputPath)));
    contract.insert(QStringLiteral("preview"), preview);

    QJsonObject queue;
    queue.insert(QStringLiteral("type"), QStringLiteral("spellvision_queue_result_event"));
    queue.insert(QStringLiteral("prompt_id"), promptId);
    queue.insert(QStringLiteral("state"), queueEvent.value(QStringLiteral("state")).toString(QStringLiteral("completed")));
    queue.insert(QStringLiteral("title"), queueEvent.value(QStringLiteral("title")).toString(QStringLiteral("LTX requeue generation")));
    queue.insert(QStringLiteral("summary"), queueEvent.value(QStringLiteral("summary")).toString(QStringLiteral("LTX requeue output captured")));
    queue.insert(QStringLiteral("primary_output_path"), outputPath);
    queue.insert(QStringLiteral("primary_metadata_path"), metadataPath);
    contract.insert(QStringLiteral("queue"), queue);

    QJsonObject history;
    history.insert(QStringLiteral("type"), QStringLiteral("spellvision_history_record"));
    history.insert(QStringLiteral("prompt_id"), promptId);
    history.insert(QStringLiteral("prompt"), historyRecord.value(QStringLiteral("prompt")).toString());
    history.insert(QStringLiteral("model"), historyRecord.value(QStringLiteral("model")).toString());
    history.insert(QStringLiteral("primary_output_path"), outputPath);
    history.insert(QStringLiteral("primary_metadata_path"), metadataPath);
    contract.insert(QStringLiteral("history"), history);

    contract.insert(QStringLiteral("raw_response_type"), response.value(QStringLiteral("type")).toString());

    return contract;
}

void T2VHistoryPage::persistLatestLtxRequeueQueuePreviewContract(const QJsonObject &contract) const
{
    const QString path = latestLtxRequeueUiContractPath();
    QSaveFile file(path);

    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate))
        return;

    file.write(QJsonDocument(contract).toJson(QJsonDocument::Indented));
    file.commit();
}

'''

if "QJsonObject T2VHistoryPage::buildLtxRequeueQueuePreviewContract" not in cpp:
    anchor = "void T2VHistoryPage::focusLatestLtxRequeueOutputAfterRefresh()"
    index = cpp.find(anchor)
    if index < 0:
        raise SystemExit("Could not find focusLatestLtxRequeueOutputAfterRefresh anchor.")
    cpp = cpp[:index] + contract_impl + "\n" + cpp[index:]

# Update scheduleRefreshAfterLtxRequeueSubmit to build/persist/emit the contract.
old = '''    pendingLtxRequeuePromptId_ = promptId;
    pendingLtxRequeuePrimaryOutputPath_ = primaryOutputPath;

    emit ltxRequeueSubmitted(promptId, primaryOutputPath);
'''

new = '''    pendingLtxRequeuePromptId_ = promptId;
    pendingLtxRequeuePrimaryOutputPath_ = primaryOutputPath;
    pendingLtxRequeuePreviewContract_ = buildLtxRequeueQueuePreviewContract(response);

    persistLatestLtxRequeueQueuePreviewContract(pendingLtxRequeuePreviewContract_);

    emit ltxRequeueSubmitted(promptId, primaryOutputPath);
    emit ltxRequeuePreviewContractReady(pendingLtxRequeuePreviewContract_);
'''

if old not in cpp:
    raise SystemExit("Could not find pending requeue assignment block in scheduleRefreshAfterLtxRequeueSubmit.")

cpp = cpp.replace(old, new, 1)

# Clear pending contract once focused.
cpp = cpp.replace(
    "            pendingLtxRequeuePromptId_.clear();\n"
    "            pendingLtxRequeuePrimaryOutputPath_.clear();\n"
    "            return;\n",
    "            pendingLtxRequeuePromptId_.clear();\n"
    "            pendingLtxRequeuePrimaryOutputPath_.clear();\n"
    "            pendingLtxRequeuePreviewContract_ = QJsonObject();\n"
    "            return;\n",
    1,
)

cpp = cpp.replace(
    "            pendingLtxRequeuePromptId_.clear();\n"
    "            pendingLtxRequeuePrimaryOutputPath_.clear();\n"
    "            return;\n",
    "            pendingLtxRequeuePromptId_.clear();\n"
    "            pendingLtxRequeuePrimaryOutputPath_.clear();\n"
    "            pendingLtxRequeuePreviewContract_ = QJsonObject();\n"
    "            return;\n",
    1,
)

# Update modal wording.
cpp = cpp.replace(
    "History and queue views are refreshing. The latest requeue output will be selected when it appears.",
    "History and queue views are refreshing. The latest requeue output will be selected when it appears, and a queue/preview contract has been published.",
    1,
)

cpp_path.write_text(cpp, encoding="utf-8")

doc_path.parent.mkdir(parents=True, exist_ok=True)
doc_path.write_text(
    "# Sprint 15C Pass 23 — Promote LTX Requeue Flow to Queue/Preview Contract\n\n"
    "Promotes successful LTX requeue submissions into a normalized Qt-side queue/preview contract.\n\n"
    "The T2V History page now:\n\n"
    "- Builds `spellvision_ltx_requeue_queue_preview_contract` from the Pass 18/20 response.\n"
    "- Persists the latest contract to `D:/AI_ASSETS/comfy_runtime/spellvision_registry/ui/latest_ltx_requeue_queue_preview_contract.json`.\n"
    "- Emits `ltxRequeuePreviewContractReady(contract)` for future queue/preview consumers.\n"
    "- Keeps the existing `ltxRequeueSubmitted(promptId, primaryOutputPath)` signal for lightweight consumers.\n\n"
    "This pass does not start another generation. It only normalizes and publishes the result that already came back from the guarded requeue submit path.\n",
    encoding="utf-8",
)

script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Sprint 15C Pass 23 LTX requeue queue/preview contract promotion.")
