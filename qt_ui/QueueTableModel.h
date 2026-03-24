#pragma once

#include <QAbstractTableModel>

class QueueManager;

class QueueTableModel : public QAbstractTableModel
{
    Q_OBJECT

public:
    enum Column
    {
        StateColumn = 0,
        CommandColumn,
        PromptColumn,
        ProgressColumn,
        StatusColumn,
        QueueIdColumn,
        UpdatedAtColumn,
        ColumnCount
    };

    enum Roles
    {
        QueueIdRole = Qt::UserRole + 1,
        ProgressRole,
        StateRole,
        ActiveRole
    };

    explicit QueueTableModel(QueueManager *queueManager, QObject *parent = nullptr);

    int rowCount(const QModelIndex &parent = QModelIndex()) const override;
    int columnCount(const QModelIndex &parent = QModelIndex()) const override;
    QVariant data(const QModelIndex &index, int role = Qt::DisplayRole) const override;
    QVariant headerData(int section, Qt::Orientation orientation, int role) const override;
    void sort(int column, Qt::SortOrder order = Qt::AscendingOrder) override;

private slots:
    void reloadFromManager();

private:
    void rebuildRows();

    QueueManager *queueManager_ = nullptr;
    QVector<int> rowOrder_;
    int sortColumn_ = UpdatedAtColumn;
    Qt::SortOrder sortOrder_ = Qt::DescendingOrder;
};