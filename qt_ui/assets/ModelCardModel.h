#pragma once

// Model Library Arc — S1 (design doc 22, Amendment A). The model behind the card grid. Holds one
// Card per model; the delegate reads it, the thumbnail cache feeds it. noteThumbnailReady() maps a
// finished thumbnail (keyed by preview path) back to its row so exactly one card repaints.

#include "ModelIntelSidecar.h"

#include <QAbstractListModel>
#include <QHash>
#include <QSortFilterProxyModel>
#include <QString>
#include <QVector>

namespace spellvision::assets
{

class ModelCardModel : public QAbstractListModel
{
    Q_OBJECT
public:
    enum Role
    {
        StrippedNameRole = Qt::UserRole + 1, // name, extension stripped
        FullNameRole,                        // original filename (tooltip)
        TypeRole,                            // Checkpoint / LoRA / VAE / ... (display label)
        KindRole,                            // W5: the classifier's own kind -- what the tabs filter on
        FamilyRole,                          // wan / sdxl / ...
        PreviewPathRole,                     // image sidecar ("" -> fallback tile)
        NativePathRole,                      // the model file path
        Sha256Role,                          // identity (overlay key)
        ModelValueRole,                      // value the cockpit expects (filename)
        FavoriteRole,                        // SpellVision-owned overlay (S5)
        // W5 Task 2: what the SITE says about this weight.
        SiteBadgeRole,        // "CivitAI" / "HuggingFace" / "" -- where the metadata came from
        QuantisationRole,     // nvfp4 / int8 / fp8 / bf16 -- four Lox variants differ only by this
        IdentificationRole,   // ModelIdentification as an int
        IdentificationCaptionRole, // "" when identified; two different sentences when not
        BlurPreviewRole       // the preview's nsfw level exceeds the setting
    };

    struct Card
    {
        QString strippedName;
        QString fullName;
        QString type;
        // W5: the ten-value kind from `<stem>.spellvision.json`, or the folder fallback. `type`
        // above is its DISPLAY label; the tabs filter on this, so a relabelling never moves a
        // model between tabs.
        QString kind;
        QString family;
        QString previewPath;
        QString nativePath;
        QString sha256;
        QString modelValue;
        bool favorite = false;

        // W5 Task 2. `strippedName` above is what the card PRINTS -- the site's display name when
        // there is one -- and `fullName` stays the filename on disk, because the file is never
        // renamed and the tooltip is where a user checks what a card actually points at.
        QString siteBadge;
        QString quantisation;
        ModelIdentification identification = ModelIdentification::NeverAsked;
        int previewNsfwLevel = 0;
        bool blurPreview = false;

        // Overlay identity: sha256 when present (survives moves), else the path (doc 22 §2.4).
        QString overlayKey() const { return sha256.isEmpty() ? nativePath : sha256; }
    };

    explicit ModelCardModel(QObject *parent = nullptr);

    void setCards(QVector<Card> cards);
    const Card &cardAt(int row) const;
    bool isValidRow(int row) const { return row >= 0 && row < cards_.size(); }
    void setFavorite(int row, bool favorite);

    int rowCount(const QModelIndex &parent = QModelIndex()) const override;
    QVariant data(const QModelIndex &index, int role) const override;

    // Called when a thumbnail for `previewPathKey` has landed — repaints just that row.
    void noteThumbnailReady(const QString &previewPathKey);

private:
    QVector<Card> cards_;
    QHash<QString, int> previewKeyToRow_;
};

// Filters the card grid by a needle across name + type + family (mirrors the tree search),
// plus optional exact Type / Family dropdown filters.
class ModelCardFilterProxy : public QSortFilterProxyModel
{
    Q_OBJECT
public:
    explicit ModelCardFilterProxy(QObject *parent = nullptr);
    void setNeedle(const QString &needle);
    void setFavoritesOnly(bool favoritesOnly);
    void setFamilyFilter(const QString &family); // empty or "All" = no family filter
    // W5: the kind TAB. "all" (or empty) shows everything; every other id shows exactly its own
    // kind, and a kind nothing recognises normalises to "other" -- so no card can fall between
    // two tabs and vanish. This replaced setTypeFilter, whose vocabulary came from a path
    // substring and had no value for an embedding at all.
    void setKindTab(const QString &tabId);

protected:
    bool filterAcceptsRow(int sourceRow, const QModelIndex &sourceParent) const override;

private:
    QString needle_;
    QString kindTabId_;
    QString familyFilter_;
    bool favoritesOnly_ = false;
};

} // namespace spellvision::assets
