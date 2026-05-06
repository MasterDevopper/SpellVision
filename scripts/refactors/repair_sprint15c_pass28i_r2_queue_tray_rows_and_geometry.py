from pathlib import Path
import re

queue_manager_path = Path("qt_ui/QueueManager.cpp")
queue_table_path = Path("qt_ui/QueueTableModel.cpp")
main_window_path = Path("qt_ui/MainWindow.cpp")
script_path = Path("scripts/refactors/repair_sprint15c_pass28i_r2_queue_tray_rows_and_geometry.py")

queue_manager = queue_manager_path.read_text(encoding="utf-8")
queue_table = queue_table_path.read_text(encoding="utf-8")
main_window = main_window_path.read_text(encoding="utf-8")


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

    for index in range(brace, len(text)):
        ch = text[index]

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
                end = index + 1
                break

    if end is None:
        raise SystemExit(f"Could not find closing brace for: {signature}")

    return text[:start] + replacement.rstrip() + "\n" + text[end:]


def function_text(text: str, signature: str) -> str:
    start = text.find(signature)
    if start < 0:
        raise SystemExit(f"Could not find function signature: {signature}")

    brace = text.find("{", start)
    depth = 0
    in_string = False
    in_char = False
    escaped = False

    for index in range(brace, len(text)):
        ch = text[index]

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
                return text[start:index + 1]

    raise SystemExit(f"Could not extract function: {signature}")


# ----------------------------------------------------------------------
# 1) QueueManager: stable row identity and retained completed rows.
# ----------------------------------------------------------------------

if "#include <QSet>" not in queue_manager:
    queue_manager = queue_manager.replace("#include <QJsonValue>", "#include <QJsonValue>\n#include <QSet>", 1)

if "#include <initializer_list>" not in queue_manager:
    queue_manager = queue_manager.replace("#include <QUuid>", "#include <QUuid>\n#include <initializer_list>", 1)

if "QString firstSnapshotText" not in queue_manager:
    helper = r'''
    QString firstSnapshotText(const QJsonObject &primary,
                              const QJsonObject &secondary,
                              std::initializer_list<const char *> keys)
    {
        for (const char *rawKey : keys)
        {
            const QString key = QString::fromLatin1(rawKey);

            const QString fromPrimary = primary.value(key).toString().trimmed();
            if (!fromPrimary.isEmpty())
                return fromPrimary;

            const QString fromSecondary = secondary.value(key).toString().trimmed();
            if (!fromSecondary.isEmpty())
                return fromSecondary;
        }

        return {};
    }

'''
    queue_manager = queue_manager.replace("namespace\n{\n", "namespace\n{\n" + helper, 1)

item_fn = function_text(queue_manager, "QueueItem QueueManager::itemFromSnapshotObject")

if "Use all known worker/result identifiers" not in item_fn:
    old_begin = '''    QueueItem item;
    item.id = obj.value(QStringLiteral("queue_item_id")).toString().trimmed();
    item.command = obj.value(QStringLiteral("command")).toString().trimmed();
    item.prompt = obj.value(QStringLiteral("prompt")).toString();
    item.model = obj.value(QStringLiteral("model")).toString();

    const QJsonObject result = obj.value(QStringLiteral("result")).toObject();'''

    new_begin = '''    QueueItem item;
    const QJsonObject result = obj.value(QStringLiteral("result")).toObject();

    // Pass 28I-R2: queue snapshots are not guaranteed to expose queue_item_id.
    // Use all known worker/result identifiers so new generations produce stable rows.
    item.id = firstSnapshotText(obj, result, {"queue_item_id", "id", "job_id", "worker_job_id", "source_job_id", "prompt_id"});
    item.command = obj.value(QStringLiteral("command")).toString().trimmed();
    item.prompt = obj.value(QStringLiteral("prompt")).toString();
    item.model = obj.value(QStringLiteral("model")).toString();'''

    if old_begin in queue_manager:
        queue_manager = queue_manager.replace(old_begin, new_begin, 1)
    else:
        # Handles prior Pass 28 layout where result was already moved above item.id.
        queue_manager = re.sub(
            r'item\.id\s*=\s*firstSnapshotText\s*\(\s*obj\s*,\s*result\s*,\s*\{[^}]*\}\s*\)\s*;',
            'item.id = firstSnapshotText(obj, result, {"queue_item_id", "id", "job_id", "worker_job_id", "source_job_id", "prompt_id"});',
            queue_manager,
            count=1,
        )

        if "prompt_id" not in function_text(queue_manager, "QueueItem QueueManager::itemFromSnapshotObject"):
            raise SystemExit("Could not repair QueueManager item identity. Dump itemFromSnapshotObject before retrying.")

if "terminal snapshots may replay with updated_at jitter" not in queue_manager:
    queue_manager = queue_manager.replace(
        '''    item.updatedAt = parseIsoDateTime(timestamps.value(QStringLiteral("updated_at")));

    return item;''',
        '''    item.updatedAt = parseIsoDateTime(timestamps.value(QStringLiteral("updated_at")));

    // Pass 28I-R2: terminal snapshots may replay with updated_at jitter.
    // Normalize terminal updatedAt so the table does not churn on every poll.
    if (item.isTerminal())
    {
        if (item.finishedAt.isValid())
            item.updatedAt = item.finishedAt;
        else if (item.startedAt.isValid())
            item.updatedAt = item.startedAt;
        else if (item.createdAt.isValid())
            item.updatedAt = item.createdAt;
    }

    return item;''',
        1,
    )

replace_all = r'''
bool QueueManager::replaceAllItems(const QVector<QueueItem> &newItems,
                                   const QString &activeQueueItemId,
                                   bool paused)
{
    QVector<QueueItem> mergedItems = newItems;
    QSet<QString> seenIds;

    for (const QueueItem &item : mergedItems)
    {
        const QString id = item.id.trimmed();
        if (!id.isEmpty())
            seenIds.insert(id);
    }

    // Pass 28I-R2:
    // Worker queue snapshots may drop completed jobs after they finish. Keep
    // recent terminal rows locally so the expanded queue tray remains useful.
    constexpr int kMaxRetainedTerminalRows = 80;
    int retainedTerminalRows = 0;

    for (const QueueItem &oldItem : m_items)
    {
        const QString id = oldItem.id.trimmed();
        if (id.isEmpty())
            continue;

        if (!oldItem.isTerminal())
            continue;

        if (seenIds.contains(id))
            continue;

        mergedItems.append(oldItem);
        seenIds.insert(id);

        ++retainedTerminalRows;
        if (retainedTerminalRows >= kMaxRetainedTerminalRows)
            break;
    }

    auto sameItem = [](const QueueItem &oldItem, const QueueItem &newItem) {
        const bool bothTerminal = oldItem.isTerminal() && newItem.isTerminal();

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
            oldItem.retryCount != newItem.retryCount ||
            oldItem.running != newItem.running ||
            oldItem.completed != newItem.completed ||
            oldItem.failed != newItem.failed ||
            oldItem.cancelled != newItem.cancelled ||
            oldItem.warmReuseCandidate != newItem.warmReuseCandidate ||
            oldItem.state != newItem.state)
        {
            return false;
        }

        if (bothTerminal)
            return true;

        return oldItem.createdAt == newItem.createdAt &&
               oldItem.startedAt == newItem.startedAt &&
               oldItem.finishedAt == newItem.finishedAt &&
               oldItem.updatedAt == newItem.updatedAt;
    };

    bool changed = false;

    if (m_items.size() != mergedItems.size())
    {
        changed = true;
    }
    else
    {
        for (int i = 0; i < m_items.size(); ++i)
        {
            if (!sameItem(m_items.at(i), mergedItems.at(i)))
            {
                changed = true;
                break;
            }
        }
    }

    if (!changed &&
        m_activeQueueItemId == activeQueueItemId.trimmed() &&
        m_paused == paused)
    {
        return false;
    }

    m_items = mergedItems;
    m_activeQueueItemId = activeQueueItemId.trimmed();
    m_paused = paused;
    rebuildIndex();

    // Snapshot refreshes should update the table without forcing a full reset.
    emit queueChanged();
    return true;
}
'''

queue_manager = replace_function(queue_manager, "bool QueueManager::replaceAllItems", replace_all)
queue_manager_path.write_text(queue_manager, encoding="utf-8")


# ----------------------------------------------------------------------
# 2) QueueTableModel: update stable rows without full resets.
# ----------------------------------------------------------------------

if "#include <QStringList>" not in queue_table:
    queue_table = queue_table.replace("#include <QFont>", "#include <QFont>\n#include <QStringList>", 1)

queue_table = queue_table.replace(
    "    connect(queueManager_, &QueueManager::queueReset, this, &QueueTableModel::reloadFromManager);\n",
    "",
)

if "Pass 28I-R2: queueChanged is enough" not in queue_table:
    queue_table = queue_table.replace(
        "    connect(queueManager_, &QueueManager::queueChanged, this, &QueueTableModel::reloadFromManager);\n",
        "    // Pass 28I-R2: queueChanged is enough for snapshot refreshes.\n    connect(queueManager_, &QueueManager::queueChanged, this, &QueueTableModel::reloadFromManager);\n",
        1,
    )

reload = r'''
void QueueTableModel::reloadFromManager()
{
    auto idsForOrder = [this](const QVector<int> &order) {
        QStringList ids;

        if (!queueManager_)
            return ids;

        const QVector<QueueItem> &items = queueManager_->items();
        ids.reserve(order.size());

        for (int sourceRow : order)
        {
            if (sourceRow >= 0 && sourceRow < items.size())
                ids << items.at(sourceRow).id;
        }

        return ids;
    };

    const QVector<int> previousOrder = rowOrder_;
    const QStringList previousIds = idsForOrder(previousOrder);

    rebuildRows();

    const QVector<int> nextOrder = rowOrder_;
    const QStringList nextIds = idsForOrder(nextOrder);

    // Pass 28I-R2:
    // Stable row identities should update cells, not reset headers/scroll/layout.
    if (previousIds == nextIds)
    {
        if (!rowOrder_.isEmpty())
        {
            emit dataChanged(index(0, 0),
                             index(rowOrder_.size() - 1, ColumnCount - 1),
                             {Qt::DisplayRole, Qt::FontRole, Qt::TextAlignmentRole,
                              QueueIdRole, ProgressRole, StateRole, ActiveRole});
        }
        return;
    }

    rowOrder_ = previousOrder;
    beginResetModel();
    rowOrder_ = nextOrder;
    endResetModel();
}
'''

queue_table = replace_function(queue_table, "void QueueTableModel::reloadFromManager", reload)
queue_table_path.write_text(queue_table, encoding="utf-8")


# ----------------------------------------------------------------------
# 3) MainWindow: stable expanded queue tray geometry.
# ----------------------------------------------------------------------

if "Pass 28I-R2 stable queue table geometry" not in main_window:
    main_window = main_window.replace(
        '''    queueTableView_->setAlternatingRowColors(true);
    queueTableView_->setSortingEnabled(false);''',
        '''    queueTableView_->setAlternatingRowColors(true);

    // Pass 28I-R2 stable queue table geometry:
    // No ResizeToContents or wrapping on high-frequency progress/status updates.
    queueTableView_->setWordWrap(false);
    queueTableView_->setTextElideMode(Qt::ElideRight);
    queueTableView_->setSortingEnabled(false);''',
        1,
    )

# Make every existing ResizeToContents in this queue-table setup fixed.
main_window = main_window.replace("QHeaderView::ResizeToContents", "QHeaderView::Fixed")

if "verticalHeader()->setDefaultSectionSize(28)" not in main_window:
    marker = "    queueTableView_->horizontalHeader()->setStretchLastSection"
    index = main_window.find(marker)
    if index >= 0:
        insert = '''    queueTableView_->verticalHeader()->setSectionResizeMode(QHeaderView::Fixed);
    queueTableView_->verticalHeader()->setDefaultSectionSize(28);
    queueTableView_->verticalHeader()->setMinimumSectionSize(28);
'''
        main_window = main_window[:index] + insert + main_window[index:]

if "Pass 28I-R2: active queue strip is a stable single-line summary" not in main_window:
    marker = '''    activeQueueSummaryLabel_ = new QLabel(QStringLiteral("Recent jobs will appear here when the queue is idle."), activeStrip);'''
    if marker in main_window:
        main_window = main_window.replace(
            marker,
            marker + '''
    // Pass 28I-R2: active queue strip is a stable single-line summary.
    activeQueueSummaryLabel_->setWordWrap(false);
    activeQueueSummaryLabel_->setFixedHeight(24);
    activeQueueSummaryLabel_->setTextInteractionFlags(Qt::NoTextInteraction);''',
            1,
        )

# Throttle queue details/chrome work, but always let the table update.
on_queue_changed = r'''
void MainWindow::onQueueChanged()
{
    syncBottomTelemetry();
    updateActiveQueueStrip();

    const bool expanded = queueDockUserExpanded_ || bottomUtilityUserExpanded_ || detailsDockPinnedOpen_;
    const QString selectedId = selectedQueueId();

    const QString detailsKey = QStringLiteral("%1|%2")
        .arg(expanded ? QStringLiteral("expanded") : QStringLiteral("collapsed"), selectedId);

    // Pass 28I-R2:
    // Details text can wrap and resize the expanded tray. Only rewrite it when
    // selection/expanded state changes, not on every queue progress poll.
    if (property("svQueueDetailsKey").toString() != detailsKey)
    {
        setProperty("svQueueDetailsKey", detailsKey);
        updateDetailsPanelForQueueSelection();
    }

    const QString chromeKey = QStringLiteral("%1|%2|%3")
        .arg(queueDockUserExpanded_ ? 1 : 0)
        .arg(bottomUtilityUserExpanded_ ? 1 : 0)
        .arg(detailsDockPinnedOpen_ ? 1 : 0);

    if (property("svQueueChromeKey").toString() != chromeKey)
    {
        setProperty("svQueueChromeKey", chromeKey);
        updateDockChrome();
    }

    if (queueTableView_)
        queueTableView_->viewport()->update();
}
'''

main_window = replace_function(main_window, "void MainWindow::onQueueChanged", on_queue_changed)

main_window_path.write_text(main_window, encoding="utf-8")
script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Pass 28I-R2: queue rows update and expanded tray geometry is stabilized.")
