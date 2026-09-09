#include "WorkerQueueController.h"

#include "../QueueManager.h"
#include "WorkerSocketClient.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonValue>
#include <QPointer>
#include <QTimer>
#include <QFileInfo>
#include <QFile>
#include <QDir>
#include <QDateTime>

namespace spellvision::workers
{

namespace
{

constexpr int kConfirmedLossFailureCount = 3;

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
    const QString stableId = id.isEmpty() ? QStringLiteral("ltx-registry-%1").arg(orderIndex) : id;
    out.insert(QStringLiteral("id"), stableId);
    out.insert(QStringLiteral("queue_item_id"), stableId);
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
    result.insert(QStringLiteral("video_stack_summary"), QStringLiteral("LTX requeue ready"));
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
    const QString contractCreatedAt = contract.value(QStringLiteral("created_at")).toString();
    const QString stableTimestamp = contractCreatedAt.isEmpty()
        ? QStringLiteral("1970-01-01T00:00:00.000Z")
        : contractCreatedAt;

    item.insert(QStringLiteral("created_at"), stableTimestamp);
    item.insert(QStringLiteral("updated_at"), stableTimestamp);
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
    item.insert(QStringLiteral("video_stack_summary"), QStringLiteral("LTX requeue ready"));
    item.insert(QStringLiteral("preview_ready"), true);
    item.insert(QStringLiteral("queue_ready"), true);
    item.insert(QStringLiteral("history_ready"), true);

    return item;
}

QJsonObject appendLatestLtxRequeuePreviewContractItem(QJsonObject snapshot)
{
    // Pass 24 safety gate:
    // Do not inject preview-backed synthetic queue rows during normal queue polling.
    // Queue polling runs globally, including while Home is visible. Injecting a media-backed
    // completed row on every snapshot can cause preview consumers to rebind the same MP4
    // repeatedly, which shows up as FFmpeg probe spam and visible flicker.
    //
    // Later, the Queue/Preview panel should request this explicitly when it is visible.
    bool envParsed = false;
    const int enabled = qEnvironmentVariableIntValue("SPELLVISION_ENABLE_LTX_QUEUE_CONTRACT_PREVIEW", &envParsed);
    if (!envParsed || enabled != 1)
        return snapshot;

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


WorkerQueueController::WorkerQueueController(QObject *parent)
    : QObject(parent),
      pollTimer_(new QTimer(this))
{
    pollTimer_->setInterval(kIdlePollIntervalMs);
    connect(pollTimer_, &QTimer::timeout, this, [this]() {
        pollOnce();
    });
}

void WorkerQueueController::bind(Bindings bindings)
{
    bindings_ = std::move(bindings);
    consecutivePollFailures_ = 0;
    hasSuccessfulPoll_ = false;
    connectivityLost_ = false;
}

QJsonObject WorkerQueueController::buildQueueStatusRequest()
{
    QJsonObject request;
    request.insert(QStringLiteral("command"), QStringLiteral("queue_status"));
    return request;
}

QJsonObject WorkerQueueController::buildSubscribeRequest()
{
    QJsonObject request;
    request.insert(QStringLiteral("command"), QStringLiteral("subscribe"));
    return request;
}

bool WorkerQueueController::applyPushedProgress(const QJsonObject &payload)
{
    if (!bindings_.queueManager)
        return false;
    if (payload.value(QStringLiteral("type")).toString() != QStringLiteral("progress"))
        return false;

    const int step = payload.value(QStringLiteral("step")).toInt(-1);
    const int total = payload.value(QStringLiteral("total")).toInt(-1);
    if (step < 0 || total <= 0)
        return false;

    const QString pushedId = firstString(payload, {"queue_item_id", "job_id", "id"});
    if (pushedId.isEmpty())
        return false;

    QueueItem item = bindings_.queueManager->itemById(pushedId);
    if (item.id.isEmpty())
    {
        for (const QueueItem &candidate : bindings_.queueManager->items())
        {
            if (candidate.workerJobId == pushedId)
            {
                item = candidate;
                break;
            }
        }
    }
    if (item.id.isEmpty())
        return false;

    item.currentStep = step;
    item.steps = total;
    return bindings_.queueManager->updateItem(item);

}

bool WorkerQueueController::applyWorkerQueueResponse(const QJsonObject &response)
{
    if (!bindings_.queueManager)
        return false;

    const QJsonObject snapshot = normalizedQueueSnapshot(response);
    if (snapshot.isEmpty())
        return false;

    consecutivePollFailures_ = 0;
    hasSuccessfulPoll_ = true;
    connectivityLost_ = false;

    const bool changed = bindings_.queueManager->applyQueueSnapshot(snapshot);
    if (changed)
    {
        if (bindings_.afterQueueSnapshotApplied)
            bindings_.afterQueueSnapshotApplied();

        emit queueResponseApplied();
    }

    // Emit after applying the authoritative snapshot so observers that count
    // successful omissions see the just-returned queue, not the previous one.
    emit queuePollSucceeded();

    return changed;
}

bool WorkerQueueController::pollOnce()
{
    if (pollInFlight_)
        return false;
    if (!bindings_.sendRequestAsync)
    {
        notifyPollFailure(QStringLiteral("Worker queue poll skipped: no request sender is bound."));
        return false;
    }

    pollInFlight_ = true;
    const QJsonObject request = bindings_.buildPollRequest
                                    ? bindings_.buildPollRequest()
                                    : buildQueueStatusRequest();
    const QPointer<WorkerQueueController> self(this);
    bindings_.sendRequestAsync(
        request,
        [self](const QJsonObject &response, const QString &stderrText, bool startedOk) {
            if (self)
                self->handlePrimaryPollResponse(response, stderrText, startedOk);
        });
    return true;
}

void WorkerQueueController::handlePrimaryPollResponse(const QJsonObject &response,
                                                      const QString &stderrText,
                                                      bool startedOk)
{
    const auto finishPoll = [this]() {
        pollInFlight_ = false;
    };

    const QString trimmedStderr = stderrText.trimmed();
    if (!trimmedStderr.isEmpty())
        logLine(trimmedStderr);

    if (!startedOk)
    {
        notifyPollFailure(QStringLiteral("Worker queue poll failed: worker_client.py did not start."));
        finishPoll();
        return;
    }

    if (response.isEmpty())
    {
        notifyPollFailure(QStringLiteral("Worker queue poll failed: worker returned no JSON payload."));
        finishPoll();
        return;
    }

    bool changed = applyWorkerQueueResponse(response);

    bool jobInFlight = false;
    if (bindings_.queueManager)
    {
        if (!bindings_.queueManager->activeQueueItemId().trimmed().isEmpty())
        {
            jobInFlight = true;
        }
        else
        {
            for (const QueueItem &item : bindings_.queueManager->items())
            {
                if (!item.isTerminal())
                {
                    jobInFlight = true;
                    break;
                }
            }
        }
    }

    const int interval = jobInFlight ? kActivePollIntervalMs : kIdlePollIntervalMs;
    if (pollTimer_->interval() != interval)
        pollTimer_->setInterval(interval);

    const bool becameIdle = sawJobInFlight_ && !jobInFlight;
    sawJobInFlight_ = jobInFlight;

    // The LTX registry is a SECONDARY source of completed LTX rows. It used to ride every idle
    // tick (~13 ms) so the idle poll cost ~8× the busy poll. Refresh it once when a job finishes,
    // not on every idle tick, and never while a job is in flight (that snapshot has no active
    // row and would flip the bar idle↔running).
    if (becameIdle)
    {
        QJsonObject ltxRequest = ltxRegistryRequest();
        const QPointer<WorkerQueueController> self(this);
        bindings_.sendRequestAsync(
            ltxRequest,
            [self](const QJsonObject &ltxResponse, const QString &ltxStderrText, bool ltxStartedOk) {
                if (!self)
                    return;
                self->pollInFlight_ = false;
                const QString trimmedLtxStderr = ltxStderrText.trimmed();
                if (!trimmedLtxStderr.isEmpty())
                    self->logLine(trimmedLtxStderr);
                if (ltxStartedOk && !ltxResponse.isEmpty())
                    self->applyWorkerQueueResponse(ltxResponse);
            });
        return;
    }

    Q_UNUSED(changed);
    finishPoll();
}

void WorkerQueueController::startPolling(int intervalMs)
{
    const int safeIntervalMs = qMax(250, intervalMs);
    if (pollTimer_->interval() != safeIntervalMs)
        pollTimer_->setInterval(safeIntervalMs);

    if (!pollTimer_->isActive())
        pollTimer_->start();

    if (!subscribeGuard_)
    {
        subscribeGuard_ = new QObject(this);
        WorkerSocketClient::listen(
            subscribeGuard_,
            buildSubscribeRequest(),
            [this](const QJsonObject &frame) { applyPushedProgress(frame); },
            [this]() {
                if (!subscribeGuard_)
                    return;
                subscribeGuard_->deleteLater();
                subscribeGuard_ = nullptr;
            });
    }
}

void WorkerQueueController::stopPolling()
{
    pollTimer_->stop();
    if (subscribeGuard_)
    {
        subscribeGuard_->deleteLater();
        subscribeGuard_ = nullptr;
    }
}

bool WorkerQueueController::isPolling() const
{
    return pollTimer_->isActive();
}

int WorkerQueueController::pollIntervalMs() const
{
    return pollTimer_->interval();
}

void WorkerQueueController::confirmWorkerLost(const QString &message)
{
    if (connectivityLost_)
        return;
    connectivityLost_ = true;

    const QString reason = message.trimmed().isEmpty()
                               ? QStringLiteral("Worker disappeared.")
                               : message.trimmed();
    bool changed = false;
    if (bindings_.queueManager)
        changed = bindings_.queueManager->failNonterminalItems(reason);
    if (changed)
    {
        if (bindings_.afterQueueSnapshotApplied)
            bindings_.afterQueueSnapshotApplied();
        emit queueResponseApplied();
    }
    emit queueConnectivityLost(reason);
}

QJsonObject WorkerQueueController::normalizedQueueSnapshot(const QJsonObject &response) const
{
    const QJsonObject ltxSnapshot = ltxUiContractToQueueSnapshot(response);
    if (!ltxSnapshot.isEmpty())
        return ltxSnapshot;

    if (response.value(QStringLiteral("items")).isArray())
        return appendLatestLtxRequeuePreviewContractItem(response);

    const QJsonValue queueValue = response.value(QStringLiteral("queue"));
    if (queueValue.isObject())
    {
        const QJsonObject queueObject = queueValue.toObject();
        if (queueObject.value(QStringLiteral("items")).isArray())
            return appendLatestLtxRequeuePreviewContractItem(queueObject);
    }

    const QJsonValue snapshotValue = response.value(QStringLiteral("snapshot"));
    if (snapshotValue.isObject())
    {
        const QJsonObject snapshotObject = snapshotValue.toObject();
        if (snapshotObject.value(QStringLiteral("items")).isArray())
            return appendLatestLtxRequeuePreviewContractItem(snapshotObject);
    }

    const QString type = response.value(QStringLiteral("type")).toString().trimmed().toLower();
    if ((type == QStringLiteral("queue_snapshot") || type == QStringLiteral("queue_status")) &&
        response.value(QStringLiteral("items")).isArray())
    {
        return response;
    }

    return {};
}

void WorkerQueueController::logLine(const QString &text) const
{
    if (text.trimmed().isEmpty())
        return;

    if (bindings_.appendLogLine)
        bindings_.appendLogLine(text.trimmed());
}

void WorkerQueueController::notifyPollFailure(const QString &message)
{
    const QString trimmed = message.trimmed();
    if (trimmed.isEmpty())
        return;

    logLine(trimmed);
    emit queuePollFailed(trimmed);
    ++consecutivePollFailures_;
    if (hasSuccessfulPoll_
        && consecutivePollFailures_ >= kConfirmedLossFailureCount)
    {
        confirmWorkerLost(QStringLiteral("Worker disappeared after repeated queue poll failures."));
    }
}

} // namespace spellvision::workers
