#include "QueueFilterProxyModel.h"
#include "QueueTableModel.h"

#include <QAbstractItemModel>

QueueFilterProxyModel::QueueFilterProxyModel(QObject *parent)
    : QSortFilterProxyModel(parent)
{
    setDynamicSortFilter(true);
}

void QueueFilterProxyModel::setTextFilter(const QString &text)
{
    const QString next = text.trimmed().toLower();
    if (textFilter_ == next)
        return;

    textFilter_ = next;
    invalidateFilter();
}

void QueueFilterProxyModel::setStateFilter(const QString &state)
{
    const QString next = state.trimmed().toLower();
    if (stateFilter_ == next)
        return;

    stateFilter_ = next;
    invalidateFilter();
}

void QueueFilterProxyModel::setCommandFilter(const QStringList &commands)
{
    QStringList normalized;
    normalized.reserve(commands.size());

    for (const QString &command : commands)
    {
        const QString value = command.trimmed().toLower();
        if (value.isEmpty())
            continue;

        if (!normalized.contains(value))
            normalized << value;
    }

    normalized.sort();

    if (commandFilter_ == normalized)
        return;

    commandFilter_ = normalized;
    invalidateFilter();
}

void QueueFilterProxyModel::setTerminalOnlyFilter(bool terminalOnly)
{
    if (terminalOnlyFilter_ == terminalOnly)
        return;

    terminalOnlyFilter_ = terminalOnly;
    invalidateFilter();
}

bool QueueFilterProxyModel::filterAcceptsRow(int sourceRow, const QModelIndex &sourceParent) const
{
    if (!sourceModel())
        return true;

    const QModelIndex stateIdx = sourceModel()->index(sourceRow, QueueTableModel::StateColumn, sourceParent);
    const QModelIndex cmdIdx = sourceModel()->index(sourceRow, QueueTableModel::CommandColumn, sourceParent);
    const QModelIndex promptIdx = sourceModel()->index(sourceRow, QueueTableModel::PromptColumn, sourceParent);
    const QModelIndex progressIdx = sourceModel()->index(sourceRow, QueueTableModel::ProgressColumn, sourceParent);
    const QModelIndex statusIdx = sourceModel()->index(sourceRow, QueueTableModel::StatusColumn, sourceParent);
    const QModelIndex idIdx = sourceModel()->index(sourceRow, QueueTableModel::QueueIdColumn, sourceParent);

    const QString stateText = sourceModel()->data(stateIdx, Qt::DisplayRole).toString().trimmed().toLower();
    const QString commandText = sourceModel()->data(cmdIdx, Qt::DisplayRole).toString().trimmed().toLower();

    const bool commandMatch =
        commandFilter_.isEmpty() ||
        commandFilter_.contains(commandText);

    if (!commandMatch)
        return false;

    // Pass 28N:
    // Image workspaces use the queue table as a stable recent-jobs ledger.
    // Preparing/running rows are handled by the main page and bottom state label;
    // inserting/removing them in the expanded table causes the visible tray to breathe.
    if (terminalOnlyFilter_)
    {
        const bool terminal =
            stateText.contains(QStringLiteral("completed")) ||
            stateText.contains(QStringLiteral("failed")) ||
            stateText.contains(QStringLiteral("cancelled")) ||
            stateText.contains(QStringLiteral("canceled")) ||
            stateText.contains(QStringLiteral("skipped"));

        if (!terminal)
            return false;
    }

    const QString rowText =
        commandText + " " +
        sourceModel()->data(promptIdx, Qt::DisplayRole).toString().toLower() + " " +
        sourceModel()->data(progressIdx, Qt::DisplayRole).toString().toLower() + " " +
        sourceModel()->data(statusIdx, Qt::DisplayRole).toString().toLower() + " " +
        sourceModel()->data(idIdx, Qt::DisplayRole).toString().toLower();

    const bool textMatch =
        textFilter_.isEmpty() || rowText.contains(textFilter_);

    const bool stateMatch =
        stateFilter_.isEmpty() ||
        stateFilter_ == "all states" ||
        stateText.contains(stateFilter_);

    return textMatch && stateMatch;
}
