#pragma once

// Model Library Arc — S1 (design doc 22, Amendment A). The model behind the card grid. Holds one
// Card per model; the delegate reads it, the thumbnail cache feeds it. noteThumbnailReady() maps a
// finished thumbnail (keyed by preview path) back to its row so exactly one card repaints.

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
        TypeRole,                            // Checkpoint / LoRA / VAE / ...
        FamilyRole,                          // wan / sdxl / ...
        PreviewPathRole,                     // image sidecar ("" -> fallback tile)
        NativePathRole,                      // the model file path
        Sha256Role,                          // identity (overlay key)
        ModelValueRole,                      // value the cockpit expects (filename)
        FavoriteRole                         // SpellVision-owned overlay (S5)
    };

    struct Card
    {
        QString strippedName;
        QString fullName;
        QString type;
        QString family;
        QString previewPath;
        QString nativePath;
        QString sha256;
        QString modelValue;
        bool favorite = false;

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

// Filters the card grid by a needle across name + type + family (mirrors the tree search).
class ModelCardFilterProxy : public QSortFilterProxyModel
{
    Q_OBJECT
public:
    explicit ModelCardFilterProxy(QObject *parent = nullptr);
    void setNeedle(const QString &needle);
    void setFavoritesOnly(bool favoritesOnly);

protected:
    bool filterAcceptsRow(int sourceRow, const QModelIndex &sourceParent) const override;

private:
    QString needle_;
    bool favoritesOnly_ = false;
};

} // namespace spellvision::assets
