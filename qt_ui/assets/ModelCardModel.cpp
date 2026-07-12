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
    default:
        return {};
    }
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

bool ModelCardFilterProxy::filterAcceptsRow(int sourceRow, const QModelIndex &sourceParent) const
{
    if (needle_.isEmpty())
        return true;
    QAbstractItemModel *src = sourceModel();
    if (!src)
        return true;
    const QModelIndex idx = src->index(sourceRow, 0, sourceParent);
    const QString hay = (idx.data(ModelCardModel::StrippedNameRole).toString() + QLatin1Char(' ')
                         + idx.data(ModelCardModel::TypeRole).toString() + QLatin1Char(' ')
                         + idx.data(ModelCardModel::FamilyRole).toString()).toLower();
    return hay.contains(needle_);
}

} // namespace spellvision::assets
