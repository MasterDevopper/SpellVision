#pragma once

#include <QSortFilterProxyModel>
#include <QString>
#include <QModelIndex>

class QueueFilterProxyModel : public QSortFilterProxyModel
{
    Q_OBJECT

public:
    explicit QueueFilterProxyModel(QObject *parent = nullptr);

    void setTextFilter(const QString &text);
    void setStateFilter(const QString &state);

protected:
    bool filterAcceptsRow(int sourceRow, const QModelIndex &sourceParent) const override;

private:
    QString textFilter_;
    QString stateFilter_;
};