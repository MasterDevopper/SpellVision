from pathlib import Path
import re

root = Path(".")
controller_cpp = root / "qt_ui" / "workers" / "WorkerQueueController.cpp"
doc_path = root / "docs" / "sprints" / "SPRINT15C_PASS24_CONSUME_LTX_REQUEUE_PREVIEW_CONTRACT_README.md"
script_path = root / "scripts" / "refactors" / "apply_sprint15c_pass24_consume_ltx_requeue_preview_contract.py"

text = controller_cpp.read_text(encoding="utf-8")

# Includes.
for include in [
    "#include <QDateTime>",
    "#include <QDir>",
    "#include <QFile>",
    "#include <QFileInfo>",
    "#include <QJsonArray>",
    "#include <QJsonDocument>",
]:
    if include not in text:
        text = text.replace("#include <QTimer>", "#include <QTimer>\n" + include, 1) if "#include <QTimer>" in text else text.replace("#include <QJsonObject>", "#include <QJsonObject>\n" + include, 1) if "#include <QJsonObject>" in text else text.replace("#include \"../QueueManager.h\"", "#include \"../QueueManager.h\"\n\n" + include, 1)

helpers = r'''
namespace
{

QString latestLtxRequeueQueuePreviewContractPath()
{
    return QDir(QStringLiteral("D:/AI_ASSETS/comfy_runtime/spellvision_registry/ui"))
        .filePath(QStringLiteral("latest_ltx_requeue_queue_preview_contract.json"));
}

QJsonObject loadLatestLtxRequeueQueuePreviewContract()
{
    QFile file(latestLtxRequeueQueuePreviewContractPath());
    if (!file.exists())
        return {};

    if (!file.open(QIODevice::ReadOnly))
        return {};

    QJsonParseError error;
    const QJsonDocument document = QJsonDocument::fromJson(file.readAll(), &error);
    if (error.error != QJsonParseError::NoError || !document.isObject())
        return {};

    const QJsonObject contract = document.object();
    if (contract.value(QStringLiteral("type")).toString() != QStringLiteral("spellvision_ltx_requeue_queue_preview_contract"))
        return {};

    if (!contract.value(QStringLiteral("submitted")).toBool(false))
        return {};

    if (!contract.value(QStringLiteral("preview_ready")).toBool(false))
        return {};

    return contract;
}

QString contractString(const QJsonObject &object, const QString &key)
{
    return object.value(key).toString().trimmed();
}

QJsonObject ltxRequeueContractToQueueItem(const QJsonObject &contract)
{
    const QString promptId = contractString(contract, QStringLiteral("prompt_id"));
    const QString outputPath = contractString(contract, QStringLiteral("primary_output_path"));
    const QString metadataPath = contractString(contract, QStringLiteral("primary_metadata_path"));
    const QString filename = contractString(contract, QStringLiteral("primary_filename"));
    const QString state = contractString(contract, QStringLiteral("state"));

    if (promptId.isEmpty() || outputPath.isEmpty())
        return {};

    const QJsonObject preview = contract.value(QStringLiteral("preview")).toObject();
    const QJsonObject history = contract.value(QStringLiteral("history")).toObject();

    QJsonObject progress;
    progress.insert(QStringLiteral("current"), 1);
    progress.insert(QStringLiteral("total"), 1);
    progress.insert(QStringLiteral("percent"), 100.0);
    progress.insert(QStringLiteral("message"), QStringLiteral("LTX requeue output ready"));

    QJsonObject result;
    result.insert(QStringLiteral("ok"), true);
    result.insert(QStringLiteral("output"), outputPath);
    result.insert(QStringLiteral("output_path"), outputPath);
    result.insert(QStringLiteral("primary_output_path"), outputPath);
    result.insert(QStringLiteral("metadata_output"), metadataPath);
    result.insert(QStringLiteral("metadata_path"), metadataPath);
    result.insert(QStringLiteral("primary_metadata_path"), metadataPath);
    result.insert(QStringLiteral("video_family"), QStringLiteral("ltx"));
    result.insert(QStringLiteral("video_backend_type"), QStringLiteral("comfy_prompt_api"));
    result.insert(QStringLiteral("video_task_type"), QStringLiteral("t2v"));
    result.insert(QStringLiteral("video_stack_summary"), QStringLiteral("LTX requeue • ready"));
    result.insert(QStringLiteral("video_validated_backend"), true);
    result.insert(QStringLiteral("preview_ready"), true);
    result.insert(QStringLiteral("queue_ready"), true);
    result.insert(QStringLiteral("history_ready"), true);
    result.insert(QStringLiteral("requeue_supported"), true);
    result.insert(QStringLiteral("source_contract_type"), contract.value(QStringLiteral("type")).toString());
    result.insert(QStringLiteral("source_contract_path"), latestLtxRequeueQueuePreviewContractPath());
    result.insert(QStringLiteral("filename"), filename);
    result.insert(QStringLiteral("preview_label"), preview.value(QStringLiteral("label")).toString(QStringLiteral("LTX Full")));

    QJsonObject item;
    item.insert(QStringLiteral("id"), QStringLiteral("ltx-requeue-preview-%1").arg(promptId));
    item.insert(QStringLiteral("queue_id"), QStringLiteral("ltx-requeue-preview-%1").arg(promptId));
    item.insert(QStringLiteral("command"), QStringLiteral("t2v"));
    item.insert(QStringLiteral("state"), QStringLiteral("completed"));
    item.insert(QStringLiteral("status"), state.isEmpty() ? QStringLiteral("requeue_submitted_completed") : state);
    item.insert(QStringLiteral("prompt"), history.value(QStringLiteral("prompt")).toString(QStringLiteral("LTX requeue output")));
    item.insert(QStringLiteral("model"), history.value(QStringLiteral("model")).toString());
    item.insert(QStringLiteral("created_at"), contract.value(QStringLiteral("created_at")).toString(QDateTime::currentDateTimeUtc().toString(Qt::ISODateWithMs)));
    item.insert(QStringLiteral("updated_at"), QDateTime::currentDateTimeUtc().toString(Qt::ISODateWithMs));
    item.insert(QStringLiteral("source_job_id"), promptId);
    item.insert(QStringLiteral("retry_count"), 0);
    item.insert(QStringLiteral("progress"), progress);
    item.insert(QStringLiteral("result"), result);
    item.insert(QStringLiteral("output_path"), outputPath);
    item.insert(QStringLiteral("metadata_path"), metadataPath);
    item.insert(QStringLiteral("primary_output_path"), outputPath);
    item.insert(QStringLiteral("primary_metadata_path"), metadataPath);
    item.insert(QStringLiteral("video_family"), QStringLiteral("ltx"));
    item.insert(QStringLiteral("video_backend_type"), QStringLiteral("comfy_prompt_api"));
    item.insert(QStringLiteral("video_task_type"), QStringLiteral("t2v"));
    item.insert(QStringLiteral("video_stack_summary"), QStringLiteral("LTX requeue • ready"));
    item.insert(QStringLiteral("preview_ready"), true);
    item.insert(QStringLiteral("queue_ready"), true);
    item.insert(QStringLiteral("history_ready"), true);

    return item;
}

QJsonObject appendLatestLtxRequeuePreviewContractItem(QJsonObject snapshot)
{
    QJsonArray items = snapshot.value(QStringLiteral("items")).toArray();
    const QJsonObject contract = loadLatestLtxRequeueQueuePreviewContract();
    const QJsonObject item = ltxRequeueContractToQueueItem(contract);

    if (item.isEmpty())
        return snapshot;

    const QString itemId = item.value(QStringLiteral("id")).toString();
    for (const QJsonValue &value : items)
    {
        const QJsonObject existing = value.toObject();
        if (existing.value(QStringLiteral("id")).toString() == itemId ||
            existing.value(QStringLiteral("queue_id")).toString() == itemId)
        {
            return snapshot;
        }
    }

    QJsonArray merged;
    merged.append(item);
    for (const QJsonValue &value : items)
        merged.append(value);

    snapshot.insert(QStringLiteral("items"), merged);
    snapshot.insert(QStringLiteral("latest_ltx_requeue_preview_contract_path"), latestLtxRequeueQueuePreviewContractPath());
    snapshot.insert(QStringLiteral("latest_ltx_requeue_preview_prompt_id"), contract.value(QStringLiteral("prompt_id")).toString());
    snapshot.insert(QStringLiteral("latest_ltx_requeue_preview_output_path"), contract.value(QStringLiteral("primary_output_path")).toString());

    return snapshot;
}

} // namespace

'''

if "appendLatestLtxRequeuePreviewContractItem" not in text:
    # Prefer inserting after includes and before the first method implementation.
    method_marker = "WorkerQueueController::WorkerQueueController"
    index = text.find(method_marker)
    if index < 0:
        raise SystemExit("Could not find WorkerQueueController constructor marker.")
    text = text[:index] + helpers + "\n" + text[index:]

# Route normalized queue snapshots through the LTX contract merger.
text = text.replace(
    "            return queueObject;",
    "            return appendLatestLtxRequeuePreviewContractItem(queueObject);",
    1,
)

text = text.replace(
    "            return snapshotObject;",
    "            return appendLatestLtxRequeuePreviewContractItem(snapshotObject);",
    1,
)

# Patch the direct queue_status/queue_snapshot return if present.
text = text.replace(
    "        return response;",
    "        return appendLatestLtxRequeuePreviewContractItem(response);",
    1,
)

controller_cpp.write_text(text, encoding="utf-8")

doc_path.parent.mkdir(parents=True, exist_ok=True)
doc_path.write_text(
    "# Sprint 15C Pass 24 — Consume LTX Requeue Preview Contract in Queue/Preview Panels\n\n"
    "Consumes the latest LTX requeue queue/preview contract produced by Pass 23.\n\n"
    "Behavior:\n\n"
    "- Reads `D:/AI_ASSETS/comfy_runtime/spellvision_registry/ui/latest_ltx_requeue_queue_preview_contract.json`.\n"
    "- Converts the contract into a normalized completed queue item.\n"
    "- Prepends it to normalized queue snapshots in `WorkerQueueController`.\n"
    "- Lets the existing QueueManager, QueueTableModel, active strip, details panel, and preview/open actions see the latest LTX requeue output without needing to parse the full backend response.\n\n"
    "This pass does not start generation and does not change the requeue submission path. It only consumes the already-published contract in the queue/preview path.\n",
    encoding="utf-8",
)

script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Sprint 15C Pass 24 LTX requeue preview contract consumption.")
