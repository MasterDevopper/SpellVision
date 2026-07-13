#pragma once

#include <QFutureWatcher>
#include <QJsonArray>
#include <QModelIndex>
#include <QStringList>
#include <QVector>
#include <QWidget>

class QLabel;
class QLineEdit;
class QPushButton;
class QStackedWidget;
class QTreeWidget;
class QTreeWidgetItem;

namespace spellvision::assets
{
class ModelThumbnailCache;
class ModelCardModel;
class ModelCardFilterProxy;
class ModelCardDelegate;
class ModelCardView;
class ModelOverlayStore;
}

class ModelManagerPage : public QWidget
{
    Q_OBJECT

public:
    explicit ModelManagerPage(QWidget *parent = nullptr);

    void setProjectRoot(const QString &projectRoot);
    void setModelsRoot(const QString &modelsRoot);
    void warmCache();

    // Cross-surface inventory snapshot (command palette "Load model…" / "Add LoRA…"). A lightweight
    // read of whatever is already loaded -- NO rescan. Trigger words are parsed lazily via
    // triggerWordsFor() only for the one model a consumer actually selects (parsing every sidecar
    // up front would be wasteful for a fuzzy-search list).
    struct InventoryItem
    {
        QString name;         // handoff value (what sendModelToGeneration expects)
        QString type;         // "Checkpoint" / "LoRA" / "VAE" / ...
        QString family;       // "sdxl" / "flux" / "wan" / ...
        QString path;
        QString metadataPath; // lazy trigger-word source ("" when absent)
    };
    QVector<InventoryItem> inventorySnapshot() const;
    QStringList triggerWordsFor(const QString &metadataPath) const;

signals:
    // S2 send-to router (doc 22 §3): the card's Load/Add action. MainWindow routes by type + family
    // and auto-populates the trigger words.
    void useModelRequested(const QString &value, const QString &family, const QString &type,
                           const QStringList &triggerWords);

public slots:
    void refreshInventory();

private slots:
    void updateModelDetails();
    void onRefreshFinished();
    void onCardLoadRequested(const QModelIndex &index);
    void onCardInspectRequested(const QModelIndex &index);
    void onCardFavoriteToggled(const QModelIndex &index);
    void setGridViewActive(bool grid);

private:
    struct ModelEntry
    {
        QString name;
        QString type;
        QString family;
        QString sizeText;
        QString status;
        QString path;
        // S0 data layer (doc 22 §2): resolved sidecars + a little cheap metadata for the list.
        QString imagePreviewPath;
        QString videoPreviewPath;
        QString metadataPath;
        QString sha256;    // identity — thumbnail-cache / overlay key
        QString baseModel; // "" or "Unknown" when absent
    };

    struct RefreshResult
    {
        QList<ModelEntry> entries;
        QString modelsRoot;
        QString downloadsRoot;
        int downloadCount = 0;
        qint64 checkedAtMs = 0;
        // S0 coverage counts (verification: should match the recon — ~297 img / 88 mp4 / 399 meta).
        int imagePreviewCount = 0;
        int videoPreviewCount = 0;
        int metadataCount = 0;
    };

    void buildUi();
    void applyThemeStyling();
    void populateGridFromEntries();
    void updateDetailsForRow(int row);
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
    QPushButton *gridToggleButton_ = nullptr;
    QPushButton *listToggleButton_ = nullptr;
    QPushButton *favoritesToggleButton_ = nullptr;
    QStackedWidget *viewStack_ = nullptr;
    QTreeWidget *modelsTree_ = nullptr;
    QLabel *modelDetailsLabel_ = nullptr;
    QLabel *modelTriggersLabel_ = nullptr;
    QPushButton *copyTriggersButton_ = nullptr;
    QLabel *modelDescriptionLabel_ = nullptr;
    QStringList currentTriggerWords_;
    QFutureWatcher<RefreshResult> *refreshWatcher_ = nullptr;
    bool refreshBusy_ = false;

    // S1 card grid (doc 22 Amendment A). Grid is the primary view; the tree stays as a compact-list toggle.
    QVector<ModelEntry> entries_;
    spellvision::assets::ModelThumbnailCache *thumbCache_ = nullptr;
    spellvision::assets::ModelCardModel *cardModel_ = nullptr;
    spellvision::assets::ModelCardFilterProxy *cardProxy_ = nullptr;
    spellvision::assets::ModelCardDelegate *cardDelegate_ = nullptr;
    spellvision::assets::ModelCardView *gridView_ = nullptr;
    spellvision::assets::ModelOverlayStore *overlayStore_ = nullptr;
};
