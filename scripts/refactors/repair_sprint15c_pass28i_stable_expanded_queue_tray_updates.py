from pathlib import Path
import re

queue_manager_path = Path("qt_ui/QueueManager.cpp")
queue_table_path = Path("qt_ui/QueueTableModel.cpp")
main_window_path = Path("qt_ui/MainWindow.cpp")
script_path = Path("scripts/refactors/repair_sprint15c_pass28i_stable_expanded_queue_tray_updates.py")

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


# ----------------------------------------------------------------------
# 1) QueueManager: stable queue identity + retain terminal completed rows.
# ----------------------------------------------------------------------

if "#include <QSet>" not in queue_manager:
    queue_manager = queue_manager.replace("#include <QJsonValue>", "#include <QJsonValue>\n#include <QSet>", 1)

if "#include <initializer_list>" not in queue_manager:
    queue_manager = queue_manager.replace("#include <QUuid>", "#include <QUuid>\n#include <initializer_list>", 1)

if "firstSnapshotText" not in queue_manager:
    helper = r'''
    QString firstSnapshotText(const QJsonObject &primary,
                              const QJsonObject &secondary,
                              std::initializer_list<const char *> keys)
    {
        for (const char *rawKey : keys)
        {
            const QString key = QString::fromLatin1(rawKey);

            const QString primaryValue = primary.value(key).toString().trimmed();
            if (!primaryValue.isEmpty())
                return primaryValue;

            const QString secondaryValue = secondary.value(key).toString().trimmed();
            if (!secondaryValue.isEmpty())
                return secondaryValue;
        }

        return {};
    }

'''
    queue_manager = queue_manager.replace("}\n\nQueueManager::QueueManager", helper + "}\n\nQueueManager::QueueManager", 1)

old_identity = '''    QueueItem item;
    item.id = obj.value(QStringLiteral("queue_item_id")).toString().trimmed();
    item.command = obj.value(QStringLiteral("command")).toString().trimmed();
    item.prompt = obj.value(QStringLiteral("prompt")).toString();
    item.model = obj.value(QStringLiteral("model")).toString();

    const QJsonObject result = obj.value(QStringLiteral("result")).toObject();'''

new_identity = '''    QueueItem item;
    const QJsonObject result = obj.value(QStringLiteral("result")).toObject();

    // Pass 28I: queue snapshots are not guaranteed to expose queue_item_id.
    // Use all known worker/result identifiers so new generations produce stable rows.
    item.id = firstSnapshotText(obj, result, {"queue_item_id", "id", "job_id", "worker_job_id", "source_job_id", "prompt_id"});
    item.command = obj.value(QStringLiteral("command")).toString().trimmed();
    item.prompt = obj.value(QStringLiteral("prompt")).toString();
    item.model = obj.value(QStringLiteral("model")).toString();'''

if "Use all known worker/result identifiers" not in queue_manager:
    if old_identity not in queue_manager:
        raise SystemExit("Could not patch QueueManager item identity block.")
    queue_manager = queue_manager.replace(old_identity, new_identity, 1)

old_timestamp = '''    item.updatedAt = parseIsoDateTime(timestamps.value(QStringLiteral("updated_at")));

    return item;'''

new_timestamp = '''    item.updatedAt = parseIsoDateTime(timestamps.value(QStringLiteral("updated_at")));

    // Pass 28I: terminal snapshots may replay with updated_at jitter.
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

    return item;'''

if "terminal snapshots may replay" not in queue_manager:
    if old_timestamp not in queue_manager:
        raise SystemExit("Could not patch QueueManager timestamp block.")
    queue_manager = queue_manager.replace(old_timestamp, new_timestamp, 1)

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

    // Pass 28I:
    // The live worker queue snapshot can drop completed items after they finish.
    // Keep recent terminal rows locally so the expanded queue tray behaves like a
    // useful recent-jobs view instead of losing the generation that just completed.
    int retainedTerminalCount = 0;
    constexpr int kMaxRetainedTerminalRows = 80;

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

        ++retainedTerminalCount;
        if (retainedTerminalCount >= kMaxRetainedTerminalRows)
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
            oldItem.mediaType != newItem.mediaType ||
            oldItem.videoFamily != newItem.videoFamily ||
            oldItem.videoBackendType != newItem.videoBackendType ||
            oldItem.videoBackendName != newItem.videoBackendName ||
            oldItem.videoDurationLabel != newItem.videoDurationLabel ||
            oldItem.videoResolution != newItem.videoResolution ||
            oldItem.videoStackSummary != newItem.videoStackSummary ||
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
        m_activeQueueItemId == activeQueueItemId &&
        m_paused == paused)
    {
        return false;
    }

    m_items = mergedItems;
    m_activeQueueItemId = activeQueueItemId.trimmed();
    m_paused = paused;
    rebuildIndex();

    emit queueReset();
    emit queueChanged();
    return true;
}
'''

queue_manager = replace_function(queue_manager, "bool QueueManager::replaceAllItems", replace_all)
queue_manager_path.write_text(queue_manager, encoding="utf-8")


# ----------------------------------------------------------------------
# 2) QueueTableModel: do not full-reset the table on every progress/status tick.
# ----------------------------------------------------------------------

if "#include <QStringList>" not in queue_table:
    queue_table = queue_table.replace("#include <QFont>", "#include <QFont>\n#include <QStringList>", 1)

old_ctor = '''    connect(queueManager_, &QueueManager::queueChanged, this, &QueueTableModel::reloadFromManager);
    connect(queueManager_, &QueueManager::queueReset, this, &QueueTableModel::reloadFromManager);
    rebuildRows();'''

new_ctor = '''    // Pass 28I: queueChanged is enough. Connecting both queueChanged and
    // queueReset caused two model reloads per snapshot.
    connect(queueManager_, &QueueManager::queueChanged, this, &QueueTableModel::reloadFromManager);
    rebuildRows();'''

if "queueChanged is enough" not in queue_table:
    if old_ctor not in queue_table:
        raise SystemExit("Could not patch QueueTableModel constructor connections.")
    queue_table = queue_table.replace(old_ctor, new_ctor, 1)

reload_replacement = r'''
void QueueTableModel::reloadFromManager()
{
    auto rowIdsForOrder = [this](const QVector<int> &order) {
        QStringList ids;

        if (!queueManager_)
            return ids;

        const QVector<QueueItem> &items = queueManager_->items();
        ids.reserve(order.size());

        for (int rowIndex : order)
        {
            if (rowIndex >= 0 && rowIndex < items.size())
                ids << items.at(rowIndex).id;
        }

        return ids;
    };

    const QVector<int> previousOrder = rowOrder_;
    const QStringList previousIds = rowIdsForOrder(previousOrder);

    rebuildRows();

    const QStringList nextIds = rowIdsForOrder(rowOrder_);

    // Pass 28I:
    // If the visible row identities/order are stable, emit dataChanged instead
    // of resetting the table model. This lets the expanded queue tray update
    // progress/status without breathing, losing scroll, or rebuilding headers.
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
    rebuildRows();
    endResetModel();
}
'''

queue_table = replace_function(queue_table, "void QueueTableModel::reloadFromManager()", reload_replacement)
queue_table_path.write_text(queue_table, encoding="utf-8")


# ----------------------------------------------------------------------
# 3) MainWindow: lock expanded tray table geometry and throttle detail/chrome churn.
# ----------------------------------------------------------------------

# Stable queue table: no ResizeToContents on high-frequency columns.
if "Pass 28I stable queue table geometry" not in main_window:
    table_marker = '''    queueTableView_->setAlternatingRowColors(true);
    queueTableView_->setSortingEnabled(false);'''

    table_replacement = '''    queueTableView_->setAlternatingRowColors(true);

    // Pass 28I stable queue table geometry:
    // ResizeToContents recalculates column widths on every progress/status tick.
    // Keep the table visually stable while still letting the prompt column stretch.
    queueTableView_->setWordWrap(false);
    queueTableView_->setTextElideMode(Qt::ElideRight);
    queueTableView_->setSortingEnabled(false);'''

    if table_marker not in main_window:
        raise SystemExit("Could not find queue table setup marker.")
    main_window = main_window.replace(table_marker, table_replacement, 1)

header_block = '''    queueTableView_->horizontalHeader()->setStretchLastSection(true);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::StateColumn, QHeaderView::ResizeToContents);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::CommandColumn, QHeaderView::ResizeToContents);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::PromptColumn, QHeaderView::Stretch);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::VideoColumn, QHeaderView::ResizeToContents);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::ProgressColumn, QHeaderView::ResizeToContents);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::StatusColumn, QHeaderView::ResizeToContents);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::QueueIdColumn, QHeaderView::ResizeToContents);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::UpdatedAtColumn, QHeaderView::ResizeToContents);'''

header_replacement = '''    queueTableView_->verticalHeader()->setSectionResizeMode(QHeaderView::Fixed);
    queueTableView_->verticalHeader()->setDefaultSectionSize(28);
    queueTableView_->verticalHeader()->setMinimumSectionSize(28);
    queueTableView_->horizontalHeader()->setStretchLastSection(false);
    queueTableView_->horizontalHeader()->setMinimumSectionSize(52);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::StateColumn, QHeaderView::Fixed);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::CommandColumn, QHeaderView::Fixed);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::PromptColumn, QHeaderView::Stretch);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::VideoColumn, QHeaderView::Fixed);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::ProgressColumn, QHeaderView::Fixed);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::StatusColumn, QHeaderView::Fixed);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::QueueIdColumn, QHeaderView::Fixed);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::UpdatedAtColumn, QHeaderView::Fixed);
    queueTableView_->setColumnWidth(QueueTableModel::StateColumn, 118);
    queueTableView_->setColumnWidth(QueueTableModel::CommandColumn, 86);
    queueTableView_->setColumnWidth(QueueTableModel::VideoColumn, 128);
    queueTableView_->setColumnWidth(QueueTableModel::ProgressColumn, 112);
    queueTableView_->setColumnWidth(QueueTableModel::StatusColumn, 220);
    queueTableView_->setColumnWidth(QueueTableModel::QueueIdColumn, 180);
    queueTableView_->setColumnWidth(QueueTableModel::UpdatedAtColumn, 160);'''

if header_block in main_window:
    main_window = main_window.replace(header_block, header_replacement, 1)

# If the current file already had Pass 28I table setup but still has resize-to-contents,
# do a direct cleanup.
main_window = main_window.replace("QHeaderView::ResizeToContents", "QHeaderView::Fixed")

# Keep the active queue strip one-line and fixed height.
if "Pass 28I: active queue strip is a stable single-line summary" not in main_window:
    active_label_marker = '''    activeQueueSummaryLabel_ = new QLabel(QStringLiteral("Recent jobs will appear here when the queue is idle."), activeStrip);'''
    active_label_replacement = '''    activeQueueSummaryLabel_ = new QLabel(QStringLiteral("Recent jobs will appear here when the queue is idle."), activeStrip);
    // Pass 28I: active queue strip is a stable single-line summary.
    activeQueueSummaryLabel_->setWordWrap(false);
    activeQueueSummaryLabel_->setFixedHeight(24);
    activeQueueSummaryLabel_->setTextInteractionFlags(Qt::NoTextInteraction);'''
    if active_label_marker in main_window:
        main_window = main_window.replace(active_label_marker, active_label_replacement, 1)

# Stabilize bottom splitter sizes while expanded.
splitter_pattern = re.compile(
    r'''    if \((?:expanded && )?bottomUtilitySplitter_\)\n    \{\n        const int totalWidth = qMax\(bottomUtilitySplitter_->width\(\), width\(\) - 120\);\n.*?bottomUtilitySplitter_->setSizes\(\{queueWidth, detailsWidth\}\);\n    \}''',
    re.DOTALL,
)

splitter_replacement = '''    if (expanded && bottomUtilitySplitter_)
    {
        const int totalWidth = qMax(bottomUtilitySplitter_->width(), width() - 120);
        const int currentTab = bottomUtilityTabs_ ? bottomUtilityTabs_->currentIndex() : 0;
        const QString splitterKey = QStringLiteral("%1|%2|%3")
            .arg(totalWidth)
            .arg(compact ? 1 : 0)
            .arg(currentTab);

        // Pass 28I:
        // Expanded tray splitter sizes should react to user/layout changes, not
        // every queue progress tick.
        if (bottomUtilitySplitter_->property("svLastQueueSplitterKey").toString() != splitterKey)
        {
            int detailsWidth = compact ? 560 : 680;
            if (currentTab == 0)
                detailsWidth = compact ? 640 : 780;
            if (currentTab == 1)
                detailsWidth = compact ? 520 : 580;
            detailsWidth = qBound(460, detailsWidth, qMax(520, totalWidth / 2));
            const int queueWidth = qMax(500, totalWidth - detailsWidth);
            bottomUtilitySplitter_->setSizes({queueWidth, detailsWidth});
            bottomUtilitySplitter_->setProperty("svLastQueueSplitterKey", splitterKey);
        }
    }'''

main_window, splitter_replacements = splitter_pattern.subn(splitter_replacement, main_window, count=1)
if splitter_replacements == 0 and "svLastQueueSplitterKey" not in main_window:
    raise SystemExit("Could not patch bottom utility splitter sizing block.")

on_queue_changed = r'''
void MainWindow::onQueueChanged()
{
    syncBottomTelemetry();
    updateActiveQueueStrip();

    const bool expanded = queueDockUserExpanded_ || bottomUtilityUserExpanded_ || detailsDockPinnedOpen_;
    const QString selectedId = selectedQueueId();
    const QString detailsKey = QStringLiteral("%1|%2").arg(expanded ? QStringLiteral("expanded") : QStringLiteral("collapsed"), selectedId);

    // Pass 28I:
    // Do not rewrite details text on every queue progress poll. Wrapped labels in
    // the details pane can change height and make the expanded tray breathe.
    if (property("svQueueDetailsKey").toString() != detailsKey)
    {
        setProperty("svQueueDetailsKey", detailsKey);
        updateDetailsPanelForQueueSelection();
    }

    const QString chromeKey = QStringLiteral("%1|%2|%3|%4")
        .arg(hasActiveQueueWork() ? 1 : 0)
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

main_window = replace_function(main_window, "void MainWindow::onQueueChanged()", on_queue_changed)
main_window_path.write_text(main_window, encoding="utf-8")

script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Pass 28I: stable expanded queue tray updates.")
