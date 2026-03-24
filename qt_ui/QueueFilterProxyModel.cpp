#include "QueueFilterProxyModel.h"

#include <QAbstractItemModel>

QueueFilterProxyModel::QueueFilterProxyModel(QObject *parent)
    : QSortFilterProxyModel(parent)
{
    setDynamicSortFilter(true);
}

void QueueFilterProxyModel::setTextFilter(const QString &text)
{
    textFilter_ = text.trimmed().toLower();
    invalidateFilter();
}

void QueueFilterProxyModel::setStateFilter(const QString &state)
{
    stateFilter_ = state.trimmed().toLower();
    invalidateFilter();
}

bool QueueFilterProxyModel::filterAcceptsRow(int sourceRow, const QModelIndex &sourceParent) const
{
    if (!sourceModel())
        return true;

    QModelIndex stateIdx = sourceModel()->index(sourceRow, 0, sourceParent);
    QModelIndex cmdIdx = sourceModel()->index(sourceRow, 1, sourceParent);
    QModelIndex promptIdx = sourceModel()->index(sourceRow, 2, sourceParent);
    QModelIndex statusIdx = sourceModel()->index(sourceRow, 4, sourceParent);
    QModelIndex idIdx = sourceModel()->index(sourceRow, 5, sourceParent);

    const QString stateText =
        sourceModel()->data(stateIdx, Qt::DisplayRole).toString().toLower();

    const QString rowText =
        sourceModel()->data(cmdIdx, Qt::DisplayRole).toString().toLower() + " " +
        sourceModel()->data(promptIdx, Qt::DisplayRole).toString().toLower() + " " +
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