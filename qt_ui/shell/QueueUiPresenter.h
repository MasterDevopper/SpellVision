#pragma once

#include <QStringList>

#include <QString>

#include <functional>

class QAbstractItemModel;
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

// What the bottom bar's "Queue: N" means. N was the row count of the tray's proxy model, which in
// image mode is a TERMINAL-ONLY ledger -- so one failed render read as "Queue: 1", a job the user
// would wait for. Outstanding is queued + preparing + running; failed is reported beside it.
struct QueueTally
{
    int rows = 0;
    int running = 0;      // Running
    int pending = 0;      // Queued + Preparing
    int outstanding = 0;  // running + pending
    int failed = 0;
};

class QueueUiPresenter final
{
public:
    QueueUiPresenter() = delete;

    // Reads the SOURCE model (not the filtered proxy) over the commands a page accepts. An empty
    // command list means every row.
    static QueueTally tallyQueue(const QAbstractItemModel *sourceModel, const QStringList &acceptedCommands);
    static QString queueLabelText(const QueueTally &tally);
    static QString queueLabelToolTip(const QueueTally &tally, bool imageMode);

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
