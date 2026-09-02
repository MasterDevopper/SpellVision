// "Queue: N" means outstanding work.
//
// The bottom bar's count was the row count of the tray's proxy model. In image mode that proxy is
// a TERMINAL-ONLY ledger (recent jobs), so the first failed render of the 2026-09-02 screenshot
// pass showed as "Queue: 1" -- a job the user would sit and wait for. The tally now reads the
// source model over the page's accepted commands and separates outstanding from failed.

#include <QtTest>

#include <QStandardItemModel>
#include <QString>
#include <QStringList>

#include "QueueManager.h"
#include "QueueTableModel.h"
#include "shell/QueueUiPresenter.h"

using spellvision::shell::QueueTally;
using spellvision::shell::QueueUiPresenter;

namespace
{

void addRow(QStandardItemModel *model, const QString &command, QueueItemState state)
{
    const int row = model->rowCount();
    model->insertRow(row);
    for (int column = 0; column < model->columnCount(); ++column)
        model->setItem(row, column, new QStandardItem);
    model->setData(model->index(row, QueueTableModel::CommandColumn), command, Qt::DisplayRole);
    model->setData(model->index(row, QueueTableModel::StateColumn), static_cast<int>(state), QueueTableModel::StateRole);
}

const QStringList kImageCommands{QStringLiteral("t2i"), QStringLiteral("txt2img"), QStringLiteral("text_to_image")};

} // namespace

class QueueTallyTest : public QObject
{
    Q_OBJECT

private slots:
    void a_failed_render_is_not_outstanding()
    {
        QStandardItemModel model(0, QueueTableModel::ColumnCount);
        addRow(&model, QStringLiteral("t2i"), QueueItemState::Failed);

        const QueueTally tally = QueueUiPresenter::tallyQueue(&model, kImageCommands);
        QCOMPARE(tally.rows, 1);
        QCOMPARE(tally.outstanding, 0);
        QCOMPARE(tally.failed, 1);
        QCOMPARE(QueueUiPresenter::queueLabelText(tally), QStringLiteral("Queue: 0"));
        QVERIFY(QueueUiPresenter::queueLabelToolTip(tally, true).contains(QStringLiteral("1 failed")));
    }

    void queued_preparing_and_running_are_outstanding_and_terminal_rows_are_not()
    {
        QStandardItemModel model(0, QueueTableModel::ColumnCount);
        addRow(&model, QStringLiteral("t2i"), QueueItemState::Queued);
        addRow(&model, QStringLiteral("t2i"), QueueItemState::Preparing);
        addRow(&model, QStringLiteral("t2i"), QueueItemState::Running);
        addRow(&model, QStringLiteral("t2i"), QueueItemState::Completed);
        addRow(&model, QStringLiteral("t2i"), QueueItemState::Cancelled);
        addRow(&model, QStringLiteral("t2i"), QueueItemState::Skipped);
        addRow(&model, QStringLiteral("t2i"), QueueItemState::Failed);

        const QueueTally tally = QueueUiPresenter::tallyQueue(&model, kImageCommands);
        QCOMPARE(tally.rows, 7);
        QCOMPARE(tally.running, 1);
        QCOMPARE(tally.pending, 2);
        QCOMPARE(tally.outstanding, 3);
        QCOMPARE(tally.failed, 1);
        QCOMPARE(QueueUiPresenter::queueLabelText(tally), QStringLiteral("Queue: 3"));
    }

    void rows_from_other_modes_do_not_count()
    {
        QStandardItemModel model(0, QueueTableModel::ColumnCount);
        addRow(&model, QStringLiteral("t2v"), QueueItemState::Running);
        addRow(&model, QStringLiteral("i2i"), QueueItemState::Failed);
        addRow(&model, QStringLiteral("T2I"), QueueItemState::Queued); // case-insensitive

        const QueueTally tally = QueueUiPresenter::tallyQueue(&model, kImageCommands);
        QCOMPARE(tally.rows, 1);
        QCOMPARE(tally.outstanding, 1);
        QCOMPARE(tally.failed, 0);
    }

    void an_empty_command_list_counts_everything()
    {
        QStandardItemModel model(0, QueueTableModel::ColumnCount);
        addRow(&model, QStringLiteral("t2v"), QueueItemState::Running);
        addRow(&model, QStringLiteral("i2i"), QueueItemState::Failed);

        const QueueTally tally = QueueUiPresenter::tallyQueue(&model, QStringList());
        QCOMPARE(tally.rows, 2);
        QCOMPARE(tally.outstanding, 1);
        QCOMPARE(tally.failed, 1);
    }

    void a_null_model_is_zero()
    {
        const QueueTally tally = QueueUiPresenter::tallyQueue(nullptr, kImageCommands);
        QCOMPARE(tally.rows, 0);
        QCOMPARE(QueueUiPresenter::queueLabelText(tally), QStringLiteral("Queue: 0"));
        QVERIFY(!QueueUiPresenter::queueLabelToolTip(tally, false).contains(QStringLiteral("failed")));
    }
};

QTEST_MAIN(QueueTallyTest)
#include "test_queue_tally.moc"
