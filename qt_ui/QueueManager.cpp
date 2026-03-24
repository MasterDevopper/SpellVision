#include "QueueManager.h"

#include <QJsonValue>
#include <QUuid>

namespace
{
    QString stateToLowerString(QueueItemState state)
    {
        switch (state)
        {
        case QueueItemState::Queued:
            return QStringLiteral("queued");
        case QueueItemState::Preparing:
            return QStringLiteral("preparing");
        case QueueItemState::Running:
            return QStringLiteral("running");
        case QueueItemState::Completed:
            return QStringLiteral("completed");
        case QueueItemState::Failed:
            return QStringLiteral("failed");
        case QueueItemState::Cancelled:
            return QStringLiteral("cancelled");
        case QueueItemState::Skipped:
            return QStringLiteral("skipped");
        case QueueItemState::Unknown:
        default:
            return QStringLiteral("unknown");
        }
    }
}

QueueManager::QueueManager(QObject *parent)
    : QObject(parent)
{
}

const QVector<QueueItem> &QueueManager::items() const
{
    return m_items;
}

int QueueManager::count() const
{
    return m_items.size();
}

bool QueueManager::isPaused() const
{
    return m_paused;
}

QString QueueManager::activeQueueItemId() const
{
    return m_activeQueueItemId;
}

bool QueueManager::contains(const QString &id) const
{
    if (id.trimmed().isEmpty())
        return false;

    return m_indexById.contains(id);
}

int QueueManager::indexOf(const QString &id) const
{
    if (id.trimmed().isEmpty())
        return -1;

    return m_indexById.value(id, -1);
}

QueueItem QueueManager::itemById(const QString &id) const
{
    const int idx = indexOf(id);
    if (idx < 0)
        return QueueItem{};

    return m_items.at(idx);
}

bool QueueManager::addItem(const QueueItem &item)
{
    if (item.id.trimmed().isEmpty())
        return false;

    if (contains(item.id))
        return false;

    QueueItem copy = item;
    copy.orderIndex = m_items.size();

    m_items.append(copy);
    rebuildIndex();

    emit queueItemAdded(copy.id);
    emit queueChanged();
    return true;
}

bool QueueManager::updateItem(const QueueItem &item)
{
    if (item.id.trimmed().isEmpty())
        return false;

    const int idx = indexOf(item.id);
    if (idx < 0)
        return false;

    QueueItem copy = item;
    copy.orderIndex = m_items.at(idx).orderIndex;
    m_items[idx] = copy;

    rebuildIndex();
    emit queueItemUpdated(copy.id);
    emit queueChanged();
    return true;
}

bool QueueManager::upsertItem(const QueueItem &item)
{
    if (item.id.trimmed().isEmpty())
        return false;

    if (contains(item.id))
        return updateItem(item);

    return addItem(item);
}

bool QueueManager::removeItem(const QString &id)
{
    const int idx = indexOf(id);
    if (idx < 0)
        return false;

    m_items.removeAt(idx);

    if (m_activeQueueItemId == id)
        m_activeQueueItemId.clear();

    rebuildIndex();
    emit queueItemRemoved(id);
    emit queueChanged();
    return true;
}

bool QueueManager::clear()
{
    if (m_items.isEmpty() && m_activeQueueItemId.isEmpty() && !m_paused)
        return false;

    m_items.clear();
    m_indexById.clear();
    m_activeQueueItemId.clear();
    m_paused = false;

    emit queueReset();
    emit queueChanged();
    return true;
}

bool QueueManager::moveUp(const QString &id)
{
    const int idx = indexOf(id);
    if (idx <= 0)
        return false;

    m_items.swapItemsAt(idx, idx - 1);
    rebuildIndex();

    emit queueChanged();
    return true;
}

bool QueueManager::moveDown(const QString &id)
{
    const int idx = indexOf(id);
    if (idx < 0 || idx >= m_items.size() - 1)
        return false;

    m_items.swapItemsAt(idx, idx + 1);
    rebuildIndex();

    emit queueChanged();
    return true;
}

bool QueueManager::moveTop(const QString &id)
{
    const int idx = indexOf(id);
    if (idx <= 0)
        return false;

    QueueItem item = m_items.takeAt(idx);
    m_items.prepend(item);
    rebuildIndex();

    emit queueChanged();
    return true;
}

bool QueueManager::moveBottom(const QString &id)
{
    const int idx = indexOf(id);
    if (idx < 0 || idx == m_items.size() - 1)
        return false;

    QueueItem item = m_items.takeAt(idx);
    m_items.append(item);
    rebuildIndex();

    emit queueChanged();
    return true;
}

bool QueueManager::duplicate(const QString &id, QString *newId)
{
    const int idx = indexOf(id);
    if (idx < 0)
        return false;

    QueueItem copy = m_items.at(idx);
    copy.id = QUuid::createUuid().toString(QUuid::WithoutBraces);
    copy.workerJobId.clear();
    copy.sourceJobId = id;
    copy.statusText = QStringLiteral("duplicated");
    copy.errorText.clear();
    copy.currentStep = 0;
    copy.retryCount = 0;
    copy.running = false;
    copy.completed = false;
    copy.failed = false;
    copy.cancelled = false;
    copy.warmReuseCandidate = false;
    copy.state = QueueItemState::Queued;
    copy.createdAt = QDateTime::currentDateTimeUtc();
    copy.startedAt = QDateTime();
    copy.finishedAt = QDateTime();
    copy.updatedAt = copy.createdAt;
    copy.orderIndex = m_items.size();

    m_items.append(copy);
    rebuildIndex();

    if (newId != nullptr)
        *newId = copy.id;

    emit queueItemAdded(copy.id);
    emit queueChanged();
    return true;
}

bool QueueManager::cancelAll()
{
    if (m_items.isEmpty())
        return false;

    bool changed = false;
    const QDateTime now = QDateTime::currentDateTimeUtc();

    for (QueueItem &item : m_items)
    {
        if (item.isTerminal())
            continue;

        item.state = QueueItemState::Cancelled;
        item.statusText = QStringLiteral("cancelled");
        item.errorText = QStringLiteral("Queue item cancelled.");
        item.cancelled = true;
        item.running = false;
        item.finishedAt = now;
        item.updatedAt = now;
        changed = true;
    }

    m_activeQueueItemId.clear();
    m_paused = false;

    if (!changed)
        return false;

    rebuildIndex();
    emit queueChanged();
    return true;
}

bool QueueManager::applyQueueSnapshot(const QJsonObject &snapshot)
{
    if (snapshot.isEmpty())
        return false;

    const QJsonValue itemsValue = snapshot.value(QStringLiteral("items"));
    if (!itemsValue.isArray())
        return false;

    return applyQueueSnapshotItems(
        itemsValue.toArray(),
        snapshot.value(QStringLiteral("active_queue_item_id")).toString(),
        snapshot.value(QStringLiteral("queue_paused")).toBool(false));
}

bool QueueManager::applyQueueSnapshotItems(const QJsonArray &itemsArray,
                                           const QString &activeQueueItemId,
                                           bool paused)
{
    QVector<QueueItem> newItems;
    newItems.reserve(itemsArray.size());

    int order = 0;
    for (const QJsonValue &value : itemsArray)
    {
        if (!value.isObject())
            continue;

        newItems.append(itemFromSnapshotObject(value.toObject(), order));
        ++order;
    }

    return replaceAllItems(newItems, activeQueueItemId, paused);
}

QueueItemState QueueManager::stateFromString(const QString &value)
{
    const QString normalized = value.trimmed().toLower();

    if (normalized == QStringLiteral("queued"))
        return QueueItemState::Queued;
    if (normalized == QStringLiteral("preparing"))
        return QueueItemState::Preparing;
    if (normalized == QStringLiteral("running"))
        return QueueItemState::Running;
    if (normalized == QStringLiteral("completed"))
        return QueueItemState::Completed;
    if (normalized == QStringLiteral("failed"))
        return QueueItemState::Failed;
    if (normalized == QStringLiteral("cancelled"))
        return QueueItemState::Cancelled;
    if (normalized == QStringLiteral("skipped"))
        return QueueItemState::Skipped;

    return QueueItemState::Unknown;
}

QDateTime QueueManager::parseIsoDateTime(const QJsonValue &value)
{
    if (!value.isString())
        return QDateTime();

    const QDateTime dt = QDateTime::fromString(value.toString(), Qt::ISODate);
    if (!dt.isValid())
        return QDateTime();

    return dt.toUTC();
}

QueueItem QueueManager::itemFromSnapshotObject(const QJsonObject &obj, int orderIndex)
{
    QueueItem item;
    item.id = obj.value(QStringLiteral("queue_item_id")).toString().trimmed();
    item.command = obj.value(QStringLiteral("command")).toString().trimmed();
    item.prompt = obj.value(QStringLiteral("prompt")).toString();
    item.model = obj.value(QStringLiteral("model")).toString();

    item.outputPath = obj.value(QStringLiteral("output")).toString();
    item.metadataPath = obj.value(QStringLiteral("metadata_output")).toString();
    item.workerJobId = obj.value(QStringLiteral("worker_job_id")).toString();
    item.sourceJobId = obj.value(QStringLiteral("source_job_id")).toString();
    item.retryCount = obj.value(QStringLiteral("retry_count")).toInt(0);
    item.orderIndex = orderIndex;
    item.warmReuseCandidate = obj.value(QStringLiteral("warm_reuse_candidate")).toBool(false);

    const QJsonObject progress = obj.value(QStringLiteral("progress")).toObject();
    item.currentStep = progress.value(QStringLiteral("current")).toInt(0);
    item.steps = progress.value(QStringLiteral("total")).toInt(0);
    item.statusText = progress.value(QStringLiteral("message")).toString();

    const QJsonObject error = obj.value(QStringLiteral("error")).toObject();
    item.errorText = error.value(QStringLiteral("message")).toString();

    item.state = stateFromString(obj.value(QStringLiteral("state")).toString());
    item.running = (item.state == QueueItemState::Preparing || item.state == QueueItemState::Running);
    item.completed = (item.state == QueueItemState::Completed);
    item.failed = (item.state == QueueItemState::Failed);
    item.cancelled = (item.state == QueueItemState::Cancelled || item.state == QueueItemState::Skipped);

    const QJsonObject timestamps = obj.value(QStringLiteral("timestamps")).toObject();
    item.createdAt = parseIsoDateTime(timestamps.value(QStringLiteral("created_at")));
    item.startedAt = parseIsoDateTime(timestamps.value(QStringLiteral("started_at")));
    item.finishedAt = parseIsoDateTime(timestamps.value(QStringLiteral("finished_at")));
    item.updatedAt = parseIsoDateTime(timestamps.value(QStringLiteral("updated_at")));

    return item;
}

bool QueueManager::replaceAllItems(const QVector<QueueItem> &newItems,
                                   const QString &activeQueueItemId,
                                   bool paused)
{
    bool changed = false;

    if (m_items.size() != newItems.size())
    {
        changed = true;
    }
    else
    {
        for (int i = 0; i < m_items.size(); ++i)
        {
            const QueueItem &oldItem = m_items.at(i);
            const QueueItem &newItem = newItems.at(i);

            if (oldItem.id != newItem.id ||
                oldItem.command != newItem.command ||
                oldItem.prompt != newItem.prompt ||
                oldItem.model != newItem.model ||
                oldItem.outputPath != newItem.outputPath ||
                oldItem.metadataPath != newItem.metadataPath ||
                oldItem.workerJobId != newItem.workerJobId ||
                oldItem.sourceJobId != newItem.sourceJobId ||
                oldItem.statusText != newItem.statusText ||
                oldItem.errorText != newItem.errorText ||
                oldItem.steps != newItem.steps ||
                oldItem.currentStep != newItem.currentStep ||
                oldItem.priority != newItem.priority ||
                oldItem.orderIndex != newItem.orderIndex ||
                oldItem.retryCount != newItem.retryCount ||
                oldItem.running != newItem.running ||
                oldItem.completed != newItem.completed ||
                oldItem.failed != newItem.failed ||
                oldItem.cancelled != newItem.cancelled ||
                oldItem.warmReuseCandidate != newItem.warmReuseCandidate ||
                oldItem.state != newItem.state ||
                oldItem.createdAt != newItem.createdAt ||
                oldItem.startedAt != newItem.startedAt ||
                oldItem.finishedAt != newItem.finishedAt ||
                oldItem.updatedAt != newItem.updatedAt)
            {
                changed = true;
                break;
            }
        }
    }

    if (!changed &&
        m_activeQueueItemId == activeQueueItemId &&
        m_paused == paused)
    {
        return false;
    }

    m_items = newItems;
    m_activeQueueItemId = activeQueueItemId.trimmed();
    m_paused = paused;
    rebuildIndex();

    emit queueReset();
    emit queueChanged();
    return true;
}

void QueueManager::rebuildIndex()
{
    m_indexById.clear();

    for (int i = 0; i < m_items.size(); ++i)
    {
        m_items[i].orderIndex = i;
        if (!m_items[i].id.trimmed().isEmpty())
            m_indexById.insert(m_items[i].id, i);
    }
}