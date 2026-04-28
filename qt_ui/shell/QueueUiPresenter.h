#pragma once

#include <QString>

#include <functional>

class QLabel;
class QLineEdit;
class QComboBox;
class QPushButton;
class QTableView;
class QueueFilterProxyModel;
class QueueManager;
class QueueItem;
enum class QueueItemState;

namespace spellvision::shell
{

class QueueUiPresenter final
{
public:
    QueueUiPresenter() = delete;

    static QString queueStateDisplay(QueueItemState state);
    static QString queueSummaryText(const QueueItem &item);
    static QString selectedQueueId(const QTableView *tableView);

    static void applyFilters(QueueFilterProxyModel *proxyModel,
                             const QString &textFilter,
                             const QString &stateFilter);

    static void connectFilterControls(QLineEdit *searchEdit,
                                      QComboBox *stateFilter,
                                      QueueFilterProxyModel *proxyModel);

    static void connectActionButton(QPushButton *button,
                                    const std::function<void()> &callback);

    static void updateActiveQueueStrip(const QueueManager *queueManager,
                                       QLabel *titleLabel,
                                       QLabel *summaryLabel);
};

} // namespace spellvision::shell
