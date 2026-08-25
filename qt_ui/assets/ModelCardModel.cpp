#include "ModelCardModel.h"

namespace spellvision::assets
{

ModelCardModel::ModelCardModel(QObject *parent)
    : QAbstractListModel(parent)
{
}

void ModelCardModel::setCards(QVector<Card> cards)
{
    beginResetModel();
    cards_ = std::move(cards);
    previewKeyToRow_.clear();
    for (int row = 0; row < cards_.size(); ++row)
    {
        const QString &key = cards_.at(row).previewPath;
        if (!key.isEmpty())
            previewKeyToRow_.insert(key, row);
    }
    endResetModel();
}

const ModelCardModel::Card &ModelCardModel::cardAt(int row) const
{
    static const Card empty;
    if (!isValidRow(row))
        return empty;
    return cards_.at(row);
}

int ModelCardModel::rowCount(const QModelIndex &parent) const
{
    if (parent.isValid())
        return 0;
    return cards_.size();
}

QVariant ModelCardModel::data(const QModelIndex &index, int role) const
{
    if (!index.isValid() || !isValidRow(index.row()))
        return {};

    const Card &card = cards_.at(index.row());
    switch (role)
    {
    case Qt::DisplayRole:
    case StrippedNameRole:
        return card.strippedName;
    case Qt::ToolTipRole:
    case FullNameRole:
        return card.fullName;
    case TypeRole:
        return card.type;
    case FamilyRole:
        return card.family;
    case PreviewPathRole:
        return card.previewPath;
    case NativePathRole:
        return card.nativePath;
    case Sha256Role:
        return card.sha256;
    case ModelValueRole:
        return card.modelValue;
    case FavoriteRole:
        return card.favorite;
    default:
        return {};
    }
}

void ModelCardModel::setFavorite(int row, bool favorite)
{
    if (!isValidRow(row) || cards_[row].favorite == favorite)
        return;
    cards_[row].favorite = favorite;
    const QModelIndex idx = index(row);
    emit dataChanged(idx, idx, {FavoriteRole, Qt::DecorationRole});
}

void ModelCardModel::noteThumbnailReady(const QString &previewPathKey)
{
    const auto it = previewKeyToRow_.constFind(previewPathKey);
    if (it == previewKeyToRow_.constEnd())
        return;
    const int row = it.value();
    if (!isValidRow(row))
        return;
    const QModelIndex idx = index(row);
    emit dataChanged(idx, idx, {Qt::DecorationRole, PreviewPathRole});
}

ModelCardFilterProxy::ModelCardFilterProxy(QObject *parent)
    : QSortFilterProxyModel(parent)
{
}

void ModelCardFilterProxy::setNeedle(const QString &needle)
{
    const QString next = needle.trimmed().toLower();
    if (next == needle_)
        return;
    needle_ = next;
    invalidateFilter();
}

void ModelCardFilterProxy::setFavoritesOnly(bool favoritesOnly)
{
    if (favoritesOnly_ == favoritesOnly)
        return;
    favoritesOnly_ = favoritesOnly;
    invalidateFilter();
}

void ModelCardFilterProxy::setTypeFilter(const QString &type)
{
    QString next = type.trimmed();
    if (next.compare(QStringLiteral("All"), Qt::CaseInsensitive) == 0)
        next.clear();
    if (next == typeFilter_)
        return;
    typeFilter_ = next;
    invalidateFilter();
}

void ModelCardFilterProxy::setFamilyFilter(const QString &family)
{
    QString next = family.trimmed();
    if (next.compare(QStringLiteral("All"), Qt::CaseInsensitive) == 0)
        next.clear();
    if (next == familyFilter_)
        return;
    familyFilter_ = next;
    invalidateFilter();
}

bool ModelCardFilterProxy::filterAcceptsRow(int sourceRow, const QModelIndex &sourceParent) const
{
    QAbstractItemModel *src = sourceModel();
    if (!src)
        return true;
    const QModelIndex idx = src->index(sourceRow, 0, sourceParent);

    if (favoritesOnly_ && !idx.data(ModelCardModel::FavoriteRole).toBool())
        return false;

    if (!typeFilter_.isEmpty()) {
        const QString type = idx.data(ModelCardModel::TypeRole).toString();
        if (type.compare(typeFilter_, Qt::CaseInsensitive) != 0)
            return false;
    }

    if (!familyFilter_.isEmpty()) {
        const QString family = idx.data(ModelCardModel::FamilyRole).toString();
        if (family.compare(familyFilter_, Qt::CaseInsensitive) != 0)
            return false;
    }

    if (needle_.isEmpty())
        return true;
    const QString hay = (idx.data(ModelCardModel::StrippedNameRole).toString() + QLatin1Char(' ')
                         + idx.data(ModelCardModel::TypeRole).toString() + QLatin1Char(' ')
                         + idx.data(ModelCardModel::FamilyRole).toString()).toLower();
    return hay.contains(needle_);
}

} // namespace spellvision::assets
