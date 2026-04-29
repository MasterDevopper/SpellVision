#include "QueueTableModel.h"

#include "QueueManager.h"

#include <QDateTime>
#include <QFont>
#include <QStringList>

#include <algorithm>

QueueTableModel::QueueTableModel(QueueManager *queueManager, QObject *parent)
    : QAbstractTableModel(parent),
      queueManager_(queueManager)
{
    connect(queueManager_, &QueueManager::queueChanged, this, &QueueTableModel::reloadFromManager);
    connect(queueManager_, &QueueManager::queueReset, this, &QueueTableModel::reloadFromManager);
    rebuildRows();
}

int QueueTableModel::rowCount(const QModelIndex &parent) const
{
    return parent.isValid() ? 0 : rowOrder_.size();
}

int QueueTableModel::columnCount(const QModelIndex &parent) const
{
    return parent.isValid() ? 0 : ColumnCount;
}

QVariant QueueTableModel::data(const QModelIndex &index, int role) const
{
    if (!index.isValid() || !queueManager_ || index.row() < 0 || index.row() >= rowOrder_.size())
        return QVariant();

    const QueueItem &item = queueManager_->items().at(rowOrder_.at(index.row()));
    const bool isActive =
        (!queueManager_->activeQueueItemId().isEmpty() &&
         item.id == queueManager_->activeQueueItemId());

    if (role == QueueIdRole)
        return item.id;
    if (role == ProgressRole)
        return item.progressPercent();
    if (role == StateRole)
        return static_cast<int>(item.state);
    if (role == ActiveRole)
        return isActive;

    if (role == Qt::FontRole && isActive)
    {
        QFont font;
        font.setBold(true);
        return font;
    }

    if (role == Qt::TextAlignmentRole)
    {
        return index.column() == ProgressColumn
                   ? QVariant(Qt::AlignCenter)
                   : QVariant(Qt::AlignLeft | Qt::AlignVCenter);
    }

    if (role != Qt::DisplayRole)
        return QVariant();

    switch (index.column())
    {
    case StateColumn:
        switch (item.state)
        {
        case QueueItemState::Queued:
            return QStringLiteral("⏳ queued");
        case QueueItemState::Preparing:
            return QStringLiteral("🛠 preparing");
        case QueueItemState::Running:
            return QStringLiteral("▶ running");
        case QueueItemState::Completed:
            return QStringLiteral("✔ completed");
        case QueueItemState::Failed:
            return QStringLiteral("✖ failed");
        case QueueItemState::Cancelled:
            return QStringLiteral("■ cancelled");
        case QueueItemState::Skipped:
            return QStringLiteral("↷ skipped");
        case QueueItemState::Unknown:
        default:
            return QStringLiteral("• unknown");
        }

    case CommandColumn:
        return item.command;

    case PromptColumn:
        return item.prompt.left(140);

    case VideoColumn:
    {
        const bool isVideo = item.command.compare(QStringLiteral("t2v"), Qt::CaseInsensitive) == 0 ||
                             item.command.compare(QStringLiteral("i2v"), Qt::CaseInsensitive) == 0 ||
                             item.mediaType.compare(QStringLiteral("video"), Qt::CaseInsensitive) == 0;
        if (!isVideo)
            return QStringLiteral("—");

        QStringList parts;
        if (!item.videoFamily.trimmed().isEmpty())
            parts << item.videoFamily.trimmed();
        if (!item.videoResolution.trimmed().isEmpty())
            parts << item.videoResolution.trimmed();
        else if (item.videoWidth > 0 && item.videoHeight > 0)
            parts << QStringLiteral("%1x%2").arg(item.videoWidth).arg(item.videoHeight);
        if (!item.videoDurationLabel.trimmed().isEmpty())
            parts << item.videoDurationLabel.trimmed();
        else if (item.videoFrames > 0 && item.videoFps > 0)
            parts << QStringLiteral("%1f @ %2fps").arg(item.videoFrames).arg(item.videoFps);
        if (!item.videoLowModelName.trimmed().isEmpty() && !item.videoHighModelName.trimmed().isEmpty())
            parts << QStringLiteral("low/high");
        else if (!item.videoStackSummary.trimmed().isEmpty())
            parts << item.videoStackSummary.trimmed();
        return parts.isEmpty() ? QStringLiteral("video") : parts.join(QStringLiteral(" • "));
    }

    case ProgressColumn:
        return item.steps > 0
                   ? QStringLiteral("%1/%2 (%3%)")
                         .arg(item.currentStep)
                         .arg(item.steps)
                         .arg(item.progressPercent())
                   : QStringLiteral("n/a");

    case StatusColumn:
        return item.statusText;

    case QueueIdColumn:
        return item.id;

    case UpdatedAtColumn:
        return item.updatedAt.isValid()
                   ? item.updatedAt.toString(Qt::ISODate)
                   : QStringLiteral("n/a");

    default:
        return QVariant();
    }
}

QVariant QueueTableModel::headerData(int section, Qt::Orientation orientation, int role) const
{
    if (orientation != Qt::Horizontal || role != Qt::DisplayRole)
        return QAbstractTableModel::headerData(section, orientation, role);

    switch (section)
    {
    case StateColumn:
        return QStringLiteral("State");
    case CommandColumn:
        return QStringLiteral("Command");
    case PromptColumn:
        return QStringLiteral("Prompt");
    case VideoColumn:
        return QStringLiteral("Video");
    case ProgressColumn:
        return QStringLiteral("Progress");
    case StatusColumn:
        return QStringLiteral("Status");
    case QueueIdColumn:
        return QStringLiteral("Queue ID");
    case UpdatedAtColumn:
        return QStringLiteral("Updated");
    default:
        return QVariant();
    }
}

void QueueTableModel::sort(int column, Qt::SortOrder order)
{
    sortColumn_ = column;
    sortOrder_ = order;

    beginResetModel();
    rebuildRows();
    endResetModel();
}

void QueueTableModel::reloadFromManager()
{
    beginResetModel();
    rebuildRows();
    endResetModel();
}

void QueueTableModel::rebuildRows()
{
    rowOrder_.clear();
    if (!queueManager_)
        return;

    const QVector<QueueItem> &items = queueManager_->items();
    rowOrder_.reserve(items.size());
    for (int i = 0; i < items.size(); ++i)
        rowOrder_.append(i);

    const QString activeId = queueManager_->activeQueueItemId();

    std::stable_sort(
        rowOrder_.begin(),
        rowOrder_.end(),
        [&](int lhsIdx, int rhsIdx)
        {
            const QueueItem &lhs = items.at(lhsIdx);
            const QueueItem &rhs = items.at(rhsIdx);

            const bool lhsActive = (!activeId.isEmpty() && lhs.id == activeId);
            const bool rhsActive = (!activeId.isEmpty() && rhs.id == activeId);
            if (lhsActive != rhsActive)
                return lhsActive;

            auto cmpStr = [&](const QString &a, const QString &b)
            {
                return sortOrder_ == Qt::AscendingOrder
                           ? a.localeAwareCompare(b) < 0
                           : a.localeAwareCompare(b) > 0;
            };

            auto cmpInt = [&](int a, int b)
            {
                return sortOrder_ == Qt::AscendingOrder ? a < b : a > b;
            };

            auto cmpDate = [&](const QDateTime &a, const QDateTime &b)
            {
                return sortOrder_ == Qt::AscendingOrder ? a < b : a > b;
            };

            switch (sortColumn_)
            {
            case StateColumn:
                return cmpInt(static_cast<int>(lhs.state), static_cast<int>(rhs.state));
            case CommandColumn:
                return cmpStr(lhs.command, rhs.command);
            case PromptColumn:
                return cmpStr(lhs.prompt, rhs.prompt);
            case VideoColumn:
                return cmpStr(lhs.videoDurationLabel + lhs.videoResolution + lhs.videoStackSummary,
                              rhs.videoDurationLabel + rhs.videoResolution + rhs.videoStackSummary);
            case ProgressColumn:
                return cmpInt(lhs.progressPercent(), rhs.progressPercent());
            case StatusColumn:
                return cmpStr(lhs.statusText, rhs.statusText);
            case QueueIdColumn:
                return cmpStr(lhs.id, rhs.id);
            case UpdatedAtColumn:
            default:
                return cmpDate(lhs.updatedAt, rhs.updatedAt);
            }
        });
}
