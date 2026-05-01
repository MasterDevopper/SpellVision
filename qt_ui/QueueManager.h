#pragma once

#include <QObject>
#include <QDateTime>
#include <QHash>
#include <QJsonArray>
#include <QJsonObject>
#include <QString>
#include <QStringList>
#include <QVector>
#include <QtGlobal>

enum class QueueItemState
{
    Queued,
    Preparing,
    Running,
    Completed,
    Failed,
    Cancelled,
    Skipped,
    Unknown
};

struct QueueItem
{
    QString id;
    QString command;
    QString prompt;
    QString model;

    QString outputPath;
    QString metadataPath;
    QString workerJobId;
    QString sourceJobId;
    QString statusText;
    QString errorText;

    QString mediaType;
    QString videoFamily;
    QString videoBackendType;
    QString videoBackendName;
    QString videoDurationLabel;
    QString videoResolution;
    QString videoStackSummary;
    QString videoLowModelName;
    QString videoHighModelName;
    QString videoPrimaryModelName;

    QString runtimeTransition;
    QString runtimeTarget;
    QString runtimePrevious;
    QString runtimeNotesSummary;
    QString imageCacheKeyBeforeRuntime;
    QString videoRuntimeSignatureBefore;
    QString videoWarmReuseSource;
    QString videoRuntimeAffinitySignature;

    int videoFrames = 0;
    int videoFps = 0;
    int videoWidth = 0;
    int videoHeight = 0;

    bool videoValidatedBackend = false;
    bool imageCacheActiveBeforeRuntime = false;
    bool imageCacheUnloadedBeforeVideo = false;
    bool videoRuntimeReused = false;
    bool videoWarmReuseCandidate = false;
    bool videoRuntimeCacheUpdated = false;

    int steps = 0;
    int currentStep = 0;
    int priority = 1;
    int orderIndex = 0;
    int retryCount = 0;

    bool running = false;
    bool completed = false;
    bool failed = false;
    bool cancelled = false;
    bool warmReuseCandidate = false;

    QueueItemState state = QueueItemState::Unknown;

    QDateTime createdAt;
    QDateTime startedAt;
    QDateTime finishedAt;
    QDateTime updatedAt;

    int progressPercent() const
    {
        if (steps <= 0)
            return 0;

        return qBound(0, static_cast<int>((100.0 * currentStep) / steps), 100);
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

    const QVector<QueueItem> &items() const;
    int count() const;
    bool isPaused() const;
    QString activeQueueItemId() const;

    bool contains(const QString &id) const;
    int indexOf(const QString &id) const;
    QueueItem itemById(const QString &id) const;

    bool addItem(const QueueItem &item);
    bool updateItem(const QueueItem &item);
    bool upsertItem(const QueueItem &item);
    bool removeItem(const QString &id);
    bool clear();

    bool moveUp(const QString &id);
    bool moveDown(const QString &id);
    bool moveTop(const QString &id);
    bool moveBottom(const QString &id);
    bool duplicate(const QString &id, QString *newId = nullptr);
    bool cancelAll();

    bool applyQueueSnapshot(const QJsonObject &snapshot);
    bool applyQueueSnapshotItems(const QJsonArray &itemsArray,
                                 const QString &activeQueueItemId,
                                 bool paused);

signals:
    void queueChanged();
    void queueItemAdded(const QString &id);
    void queueItemRemoved(const QString &id);
    void queueItemUpdated(const QString &id);
    void queueReset();

private:
    static QueueItemState stateFromString(const QString &value);
    static QDateTime parseIsoDateTime(const QJsonValue &value);
    static QueueItem itemFromSnapshotObject(const QJsonObject &obj, int orderIndex);

    bool replaceAllItems(const QVector<QueueItem> &newItems,
                         const QString &activeQueueItemId,
                         bool paused);

    void rebuildIndex();

private:
    QVector<QueueItem> m_items;
    QHash<QString, int> m_indexById;
    bool m_paused = false;
    QString m_activeQueueItemId;
};