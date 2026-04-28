#include "QueueUiPresenter.h"

#include "../QueueFilterProxyModel.h"
#include "../QueueManager.h"
#include "../QueueTableModel.h"

#include <QComboBox>
#include <QFileInfo>
#include <QLabel>
#include <QLineEdit>
#include <QPushButton>
#include <QTableView>

namespace spellvision::shell
{

QString QueueUiPresenter::queueStateDisplay(QueueItemState state)
{
    switch (state)
    {
    case QueueItemState::Queued:
        return QStringLiteral("Queued");
    case QueueItemState::Preparing:
        return QStringLiteral("Preparing");
    case QueueItemState::Running:
        return QStringLiteral("Running");
    case QueueItemState::Completed:
        return QStringLiteral("Completed");
    case QueueItemState::Failed:
        return QStringLiteral("Failed");
    case QueueItemState::Cancelled:
        return QStringLiteral("Cancelled");
    case QueueItemState::Skipped:
        return QStringLiteral("Skipped");
    case QueueItemState::Unknown:
    default:
        return QStringLiteral("Unknown");
    }
}

QString QueueUiPresenter::queueSummaryText(const QueueItem &item)
{
    if (item.id.trimmed().isEmpty())
        return QStringLiteral("No active queue item.");

    QStringList parts;

    const QString command = item.command.trimmed().isEmpty()
                                ? QStringLiteral("job")
                                : item.command.trimmed().toUpper();
    parts << command;

    parts << queueStateDisplay(item.state);

    if (item.steps > 0)
        parts << QStringLiteral("%1/%2 steps").arg(item.currentStep).arg(item.steps);
    else if (item.progressPercent() > 0)
        parts << QStringLiteral("%1% complete").arg(item.progressPercent());

    const QString modelName = QFileInfo(item.model).fileName();
    if (!modelName.trimmed().isEmpty())
        parts << modelName.trimmed();

    if (!item.statusText.trimmed().isEmpty())
        parts << item.statusText.trimmed();
    else if (!item.errorText.trimmed().isEmpty())
        parts << item.errorText.trimmed();

    return parts.join(QStringLiteral(" • "));
}

QString QueueUiPresenter::selectedQueueId(const QTableView *tableView)
{
    if (!tableView || !tableView->selectionModel())
        return QString();

    const QModelIndexList selectedRows = tableView->selectionModel()->selectedRows();
    if (selectedRows.isEmpty())
        return QString();

    return selectedRows.first().data(QueueTableModel::QueueIdRole).toString().trimmed();
}

void QueueUiPresenter::applyFilters(QueueFilterProxyModel *proxyModel,
                                    const QString &textFilter,
                                    const QString &stateFilter)
{
    if (!proxyModel)
        return;

    proxyModel->setTextFilter(textFilter);
    proxyModel->setStateFilter(stateFilter);
}

void QueueUiPresenter::connectFilterControls(QLineEdit *searchEdit,
                                             QComboBox *stateFilter,
                                             QueueFilterProxyModel *proxyModel)
{
    if (!proxyModel)
        return;

    if (searchEdit)
    {
        QObject::connect(searchEdit, &QLineEdit::textChanged, proxyModel, [proxyModel, stateFilter](const QString &text) {
            const QString state = stateFilter ? stateFilter->currentText() : QString();
            QueueUiPresenter::applyFilters(proxyModel, text, state);
        });
    }

    if (stateFilter)
    {
        QObject::connect(stateFilter, &QComboBox::currentTextChanged, proxyModel, [proxyModel, searchEdit](const QString &state) {
            const QString text = searchEdit ? searchEdit->text() : QString();
            QueueUiPresenter::applyFilters(proxyModel, text, state);
        });
    }
}

void QueueUiPresenter::connectActionButton(QPushButton *button,
                                           const std::function<void()> &callback)
{
    if (!button || !callback)
        return;

    QObject::connect(button, &QPushButton::clicked, button, [callback]() { callback(); });
}

void QueueUiPresenter::updateActiveQueueStrip(const QueueManager *queueManager,
                                              QLabel *titleLabel,
                                              QLabel *summaryLabel)
{
    if (!titleLabel || !summaryLabel)
        return;

    if (!queueManager || queueManager->count() <= 0)
    {
        titleLabel->setText(QStringLiteral("Queue idle"));
        summaryLabel->setText(QStringLiteral("No active generation jobs."));
        return;
    }

    QueueItem selected;
    const QString activeId = queueManager->activeQueueItemId().trimmed();
    if (!activeId.isEmpty() && queueManager->contains(activeId))
        selected = queueManager->itemById(activeId);

    if (selected.id.trimmed().isEmpty())
    {
        for (const QueueItem &item : queueManager->items())
        {
            if (item.state == QueueItemState::Running || item.state == QueueItemState::Preparing)
            {
                selected = item;
                break;
            }
        }
    }

    if (selected.id.trimmed().isEmpty())
    {
        for (const QueueItem &item : queueManager->items())
        {
            if (item.state == QueueItemState::Queued)
            {
                selected = item;
                break;
            }
        }
    }

    if (selected.id.trimmed().isEmpty())
    {
        const QVector<QueueItem> &items = queueManager->items();
        if (!items.isEmpty())
            selected = items.constLast();
    }

    if (selected.id.trimmed().isEmpty())
    {
        titleLabel->setText(QStringLiteral("Queue idle"));
        summaryLabel->setText(QStringLiteral("No active generation jobs."));
        return;
    }

    const QString titleCommand = selected.command.trimmed().isEmpty()
                                     ? QStringLiteral("Queue item")
                                     : selected.command.trimmed().toUpper();
    titleLabel->setText(QStringLiteral("%1 • %2").arg(titleCommand, queueStateDisplay(selected.state)));
    summaryLabel->setText(queueSummaryText(selected));
}

} // namespace spellvision::shell
