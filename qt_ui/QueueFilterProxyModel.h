#pragma once

#include <QSortFilterProxyModel>
#include <QString>
#include <QStringList>
#include <QModelIndex>

class QueueFilterProxyModel : public QSortFilterProxyModel
{
    Q_OBJECT

public:
    explicit QueueFilterProxyModel(QObject *parent = nullptr);

    void setTextFilter(const QString &text);
    void setStateFilter(const QString &state);
    void setCommandFilter(const QStringList &commands);
    void setTerminalOnlyFilter(bool terminalOnly);

protected:
    bool filterAcceptsRow(int sourceRow, const QModelIndex &sourceParent) const override;

private:
    QString textFilter_;
    QString stateFilter_;
    QStringList commandFilter_;
    bool terminalOnlyFilter_ = false;
};