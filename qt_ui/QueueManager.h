#pragma once

#include <QObject>
#include <QString>
#include <QVector>
#include <QDateTime>
#include <QtGlobal>

enum class QueueItemState
{
    Queued,
    Preparing,
    Running,
    Completed,
    Failed,
    Cancelled,
    Skipped
};

struct QueueItem
{
    QString id;
    QString command;
    QString prompt;
    QString model;

    QString output_path;
    QString metadata_path;
    QString worker_job_id;
    QString source_job_id;
    QString status_text;

    int steps = 0;
    int current_step = 0;

    int priority = 1;
    int order_index = 0;
    int retry_count = 0;

    bool running = false;
    bool completed = false;
    bool failed = false;
    bool cancelled = false;

    QueueItemState state = QueueItemState::Queued;

    QDateTime created_at = QDateTime::currentDateTimeUtc();
    QDateTime started_at;
    QDateTime finished_at;

    int progressPercent() const
    {
        if (steps <= 0)
            return 0;

        return qBound(0, static_cast<int>((100.0 * current_step) / steps), 100);
    }

    bool isTerminal() const
    {
        return state == QueueItemState::Completed ||
               state == QueueItemState::Failed ||
               state == QueueItemState::Cancelled ||
               state == QueueItemState::Skipped;
    }

    bool isPendingLike() const
    {
        return state == QueueItemState::Queued ||
               state == QueueItemState::Preparing;
    }
};

class QueueManager : public QObject
{
    Q_OBJECT

public:
    explicit QueueManager(QObject *parent = nullptr);

    QVector<QueueItem> items;
    bool paused = false;

    void addItem(const QueueItem &item);
    void removeItem(QString id);

    void moveUp(QString id);
    void moveDown(QString id);

    void moveTop(QString id);
    void moveBottom(QString id);

    void duplicate(QString id);
    void cancelAll();

signals:
    void queueChanged();
};