#pragma once

#include <QFutureWatcher>
#include <QJsonArray>
#include <QWidget>

class QLabel;
class QLineEdit;
class QPushButton;
class QTreeWidget;
class QTreeWidgetItem;

class ModelManagerPage : public QWidget
{
    Q_OBJECT

public:
    explicit ModelManagerPage(QWidget *parent = nullptr);

    void setProjectRoot(const QString &projectRoot);
    void setModelsRoot(const QString &modelsRoot);
    void warmCache();

public slots:
    void refreshInventory();

private slots:
    void updateModelDetails();
    void onRefreshFinished();

private:
    struct ModelEntry
    {
        QString name;
        QString type;
        QString family;
        QString sizeText;
        QString status;
        QString path;
    };

    struct RefreshResult
    {
        QList<ModelEntry> entries;
        QString modelsRoot;
        QString downloadsRoot;
        int downloadCount = 0;
        qint64 checkedAtMs = 0;
    };

    void buildUi();
    void applyEntries(const RefreshResult &result, const QString &sourceLabel);
    RefreshResult scanModelInventory() const;
    void setRefreshBusy(bool busy, const QString &statusText = QString());
    QString resolveModelsRoot() const;
    QString resolveDownloadsRoot() const;
    QString cacheFilePath() const;
    bool loadCache();
    void persistCache(const QList<ModelEntry> &entries, qint64 checkedAtMs) const;
    static QJsonObject entryToJson(const ModelEntry &entry);
    static ModelEntry entryFromJson(const QJsonObject &object);
    static QString detectFamily(const QString &path);
    static QString detectType(const QString &path);

    QString projectRoot_;
    QString explicitModelsRoot_;

    QLabel *summaryLabel_ = nullptr;
    QLabel *downloadsLabel_ = nullptr;
    QLabel *cacheSourceLabel_ = nullptr;
    QLabel *lastCheckedLabel_ = nullptr;
    QLabel *cachePathLabel_ = nullptr;
    QLineEdit *searchModelEdit_ = nullptr;
    QPushButton *refreshButton_ = nullptr;
    QPushButton *openRootButton_ = nullptr;
    QTreeWidget *modelsTree_ = nullptr;
    QLabel *modelDetailsLabel_ = nullptr;
    QFutureWatcher<RefreshResult> *refreshWatcher_ = nullptr;
    bool refreshBusy_ = false;
};
