from pathlib import Path

root = Path(".")
queue_cpp = root / "qt_ui" / "workers" / "WorkerQueueController.cpp"
parser_h = root / "qt_ui" / "workers" / "WorkerResponseParser.h"
parser_cpp = root / "qt_ui" / "workers" / "WorkerResponseParser.cpp"
doc_path = root / "docs" / "sprints" / "SPRINT15C_PASS14_QT_QUEUE_HISTORY_LTX_CONSUMPTION_README.md"
script_path = root / "scripts" / "refactors" / "apply_sprint15c_pass14_qt_ltx_ui_consumption.py"

text = queue_cpp.read_text(encoding="utf-8")

if "ltxRegistryRequest" not in text:
    text = text.replace(
'''namespace spellvision::workers
{

WorkerQueueController::WorkerQueueController(QObject *parent)
''',
'''namespace spellvision::workers
{

namespace
{

QString firstString(const QJsonObject &object, std::initializer_list<const char *> keys)
{
    for (const char *rawKey : keys)
    {
        const QString key = QString::fromLatin1(rawKey);
        const QString value = object.value(key).toString().trimmed();
        if (!value.isEmpty())
            return value;
    }
    return QString();
}

QJsonObject firstObject(const QJsonObject &object, std::initializer_list<const char *> keys)
{
    for (const char *rawKey : keys)
    {
        const QJsonValue value = object.value(QString::fromLatin1(rawKey));
        if (value.isObject())
            return value.toObject();
    }
    return {};
}

QJsonArray firstArray(const QJsonObject &object, std::initializer_list<const char *> keys)
{
    for (const char *rawKey : keys)
    {
        const QJsonValue value = object.value(QString::fromLatin1(rawKey));
        if (value.isArray())
            return value.toArray();
    }
    return {};
}

QJsonObject ltxRegistryRequest()
{
    QJsonObject request;
    request.insert(QStringLiteral("command"), QStringLiteral("ltx_ui_queue_history_contract"));
    request.insert(QStringLiteral("limit"), 20);
    request.insert(QStringLiteral("include_queue"), true);
    request.insert(QStringLiteral("include_history"), true);
    return request;
}

QJsonObject ltxUiItemToQueueSnapshotItem(const QJsonObject &item, int orderIndex)
{
    const QJsonObject primary = firstObject(item, {"primary_output"});
    const QString id = firstString(item, {"id", "prompt_id"});
    const QString taskType = firstString(item, {"task_type", "command"});
    const QString prompt = firstString(item, {"prompt", "summary"});
    const QString model = firstString(item, {"model"});
    const QString state = firstString(item, {"state"});
    const QString outputPath = firstString(item, {"primary_output_path", "path"});
    const QString primaryPath = outputPath.isEmpty() ? firstString(primary, {"path", "preview_path"}) : outputPath;
    const QString metadataPath = firstString(item, {"primary_metadata_path", "metadata_path"});
    const QString primaryMetadataPath = metadataPath.isEmpty() ? firstString(primary, {"metadata_path"}) : metadataPath;
    const QString title = firstString(item, {"title"});
    const QString summary = firstString(item, {"summary"});

    QJsonObject progress;
    progress.insert(QStringLiteral("current"), 1);
    progress.insert(QStringLiteral("total"), 1);
    progress.insert(QStringLiteral("percent"), 100);
    progress.insert(QStringLiteral("message"), QStringLiteral("completed"));

    QJsonObject result;
    result.insert(QStringLiteral("output"), primaryPath);
    result.insert(QStringLiteral("output_path"), primaryPath);
    result.insert(QStringLiteral("video_path"), primaryPath);
    result.insert(QStringLiteral("path"), primaryPath);
    result.insert(QStringLiteral("metadata_output"), primaryMetadataPath);
    result.insert(QStringLiteral("metadata_path"), primaryMetadataPath);
    result.insert(QStringLiteral("video_family"), QStringLiteral("ltx"));
    result.insert(QStringLiteral("video_backend_type"), QStringLiteral("comfy_prompt_api"));
    result.insert(QStringLiteral("video_backend_name"), QStringLiteral("LTX Prompt API"));
    result.insert(QStringLiteral("video_primary_model_name"), model);
    result.insert(QStringLiteral("video_model_stack_summary"), model.isEmpty() ? QStringLiteral("LTX") : model);
    result.insert(QStringLiteral("video_validated_backend"), true);

    QJsonObject out;
    out.insert(QStringLiteral("id"), id.isEmpty() ? QStringLiteral("ltx-registry-%1").arg(orderIndex) : id);
    out.insert(QStringLiteral("job_id"), firstString(item, {"prompt_id"}));
    out.insert(QStringLiteral("worker_job_id"), firstString(item, {"prompt_id"}));
    out.insert(QStringLiteral("command"), taskType.isEmpty() ? QStringLiteral("t2v") : taskType);
    out.insert(QStringLiteral("task_type"), taskType.isEmpty() ? QStringLiteral("t2v") : taskType);
    out.insert(QStringLiteral("media_type"), QStringLiteral("video"));
    out.insert(QStringLiteral("state"), state.isEmpty() ? QStringLiteral("completed") : state);
    out.insert(QStringLiteral("prompt"), prompt);
    out.insert(QStringLiteral("prompt_preview"), prompt.left(220));
    out.insert(QStringLiteral("model"), model);
    out.insert(QStringLiteral("status"), summary.isEmpty() ? title : summary);
    out.insert(QStringLiteral("status_text"), summary.isEmpty() ? title : summary);
    out.insert(QStringLiteral("output"), primaryPath);
    out.insert(QStringLiteral("output_path"), primaryPath);
    out.insert(QStringLiteral("video_path"), primaryPath);
    out.insert(QStringLiteral("metadata_path"), primaryMetadataPath);
    out.insert(QStringLiteral("metadata_output"), primaryMetadataPath);
    out.insert(QStringLiteral("order_index"), orderIndex);
    out.insert(QStringLiteral("progress"), progress);
    out.insert(QStringLiteral("result"), result);
    out.insert(QStringLiteral("source"), QStringLiteral("ltx_ui_queue_history_contract"));
    out.insert(QStringLiteral("outputs"), firstArray(item, {"outputs"}));
    return out;
}

QJsonObject ltxUiContractToQueueSnapshot(const QJsonObject &response)
{
    const QString type = response.value(QStringLiteral("type")).toString().trimmed().toLower();
    if (type != QStringLiteral("spellvision_ltx_ui_queue_history_contract"))
        return {};

    QJsonArray sourceItems = response.value(QStringLiteral("queue_items")).toArray();
    if (sourceItems.isEmpty())
        sourceItems = response.value(QStringLiteral("history_items")).toArray();

    QJsonArray items;
    for (int index = 0; index < sourceItems.size(); ++index)
    {
        const QJsonObject item = sourceItems.at(index).toObject();
        if (item.isEmpty())
            continue;
        items.append(ltxUiItemToQueueSnapshotItem(item, index));
    }

    if (items.isEmpty())
        return {};

    QJsonObject snapshot;
    snapshot.insert(QStringLiteral("type"), QStringLiteral("queue_snapshot"));
    snapshot.insert(QStringLiteral("source"), QStringLiteral("ltx_ui_queue_history_contract"));
    snapshot.insert(QStringLiteral("items"), items);
    return snapshot;
}

} // namespace

WorkerQueueController::WorkerQueueController(QObject *parent)
'''
    )

text = text.replace(
'''    return applyWorkerQueueResponse(response);
}

void WorkerQueueController::startPolling(int intervalMs)
''',
'''    bool changed = applyWorkerQueueResponse(response);

    QJsonObject ltxRequest = ltxRegistryRequest();
    QString ltxStderrText;
    bool ltxStartedOk = false;
    const QJsonObject ltxResponse = bindings_.sendRequest(ltxRequest, &ltxStderrText, &ltxStartedOk);

    const QString trimmedLtxStderr = ltxStderrText.trimmed();
    if (!trimmedLtxStderr.isEmpty())
        logLine(trimmedLtxStderr);

    if (ltxStartedOk && !ltxResponse.isEmpty())
        changed = applyWorkerQueueResponse(ltxResponse) || changed;

    return changed;
}

void WorkerQueueController::startPolling(int intervalMs)
''',
1
)

text = text.replace(
'''QJsonObject WorkerQueueController::normalizedQueueSnapshot(const QJsonObject &response) const
{
    if (response.value(QStringLiteral("items")).isArray())
        return response;
''',
'''QJsonObject WorkerQueueController::normalizedQueueSnapshot(const QJsonObject &response) const
{
    const QJsonObject ltxSnapshot = ltxUiContractToQueueSnapshot(response);
    if (!ltxSnapshot.isEmpty())
        return ltxSnapshot;

    if (response.value(QStringLiteral("items")).isArray())
        return response;
''',
1
)

queue_cpp.write_text(text, encoding="utf-8")

# Make the generic parser understand the new UI contract if it ever flows through WorkerProcessController.
h = parser_h.read_text(encoding="utf-8")
if "LtxUiQueueHistoryContract" not in h:
    h = h.replace(
'''        WorkflowProfiles,
        ClientError
''',
'''        WorkflowProfiles,
        LtxUiQueueHistoryContract,
        ClientError
''',
1
)
parser_h.write_text(h, encoding="utf-8")

cpp = parser_cpp.read_text(encoding="utf-8")
if 'spellvision_ltx_ui_queue_history_contract' not in cpp:
    cpp = cpp.replace(
'''    if (kind == QStringLiteral("workflow_profiles"))
        return MessageKind::WorkflowProfiles;
    if (kind == QStringLiteral("client_error"))
''',
'''    if (kind == QStringLiteral("workflow_profiles"))
        return MessageKind::WorkflowProfiles;
    if (kind == QStringLiteral("spellvision_ltx_ui_queue_history_contract"))
        return MessageKind::LtxUiQueueHistoryContract;
    if (kind == QStringLiteral("client_error"))
''',
1
)
    cpp = cpp.replace(
'''    case MessageKind::WorkflowProfiles: return QStringLiteral("workflow_profiles");
    case MessageKind::ClientError: return QStringLiteral("client_error");
''',
'''    case MessageKind::WorkflowProfiles: return QStringLiteral("workflow_profiles");
    case MessageKind::LtxUiQueueHistoryContract: return QStringLiteral("spellvision_ltx_ui_queue_history_contract");
    case MessageKind::ClientError: return QStringLiteral("client_error");
''',
1
)
parser_cpp.write_text(cpp, encoding="utf-8")

doc_path.parent.mkdir(parents=True, exist_ok=True)
doc_path.write_text(
'''# Sprint 15C Pass 14 — Qt Queue/History LTX Registry Consumption

## Goal

Make the Qt shell consume the Pass 13 LTX UI contract.

## What changed

- `WorkerQueueController` now fetches `ltx_ui_queue_history_contract` after normal `queue_status`.
- The Pass 13 `queue_items` payload is converted into the existing `queue_snapshot` item shape.
- Existing `QueueManager::applyQueueSnapshot()` remains the only queue state mutation path.
- `WorkerResponseParser` recognizes `spellvision_ltx_ui_queue_history_contract`.

## Why this shape

The existing Qt queue path already uses:

- `WorkerQueueController`
- `QueueManager`
- `QueueTableModel`
- `QueueUiPresenter`

This pass avoids raw Comfy parsing and avoids direct registry-file parsing in Qt.

## Expected UI behavior

Completed LTX Prompt API outputs should appear as completed video queue rows with:

- command/task type `t2v`
- family `ltx`
- backend `comfy_prompt_api`
- output video path
- metadata sidecar path
- playback-ready summary

## History note

Pass 13 provides `history_items` in the same contract. This pass lands the queue ingestion first through the existing QueueManager path. A follow-up pass can wire `T2VHistoryPage` directly to the same worker contract or switch it to a shared history model.
''',
    encoding="utf-8",
)

script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Sprint 15C Pass 14 Qt LTX queue/history consumption contract.")
