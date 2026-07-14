#include "ModelOverlayStore.h"

#include <QDir>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSaveFile>
#include <QStandardPaths>

namespace spellvision::assets
{

namespace
{
QString defaultOverlayPath()
{
    QString base = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation);
    if (base.trimmed().isEmpty())
        base = QDir::current().filePath(QStringLiteral("runtime/cache/ui"));
    QDir dir(base);
    dir.mkpath(QStringLiteral("."));
    return dir.filePath(QStringLiteral("model_overlay.json"));
}

QStringList toStringList(const QJsonArray &array)
{
    QStringList out;
    for (const QJsonValue &value : array)
    {
        const QString text = value.toString().trimmed();
        if (!text.isEmpty())
            out << text;
    }
    return out;
}
} // namespace

ModelOverlayStore::ModelOverlayStore(const QString &filePath)
    : filePath_(filePath.trimmed().isEmpty() ? defaultOverlayPath() : filePath.trimmed())
{
    load();
}

ModelOverlay ModelOverlayStore::overlay(const QString &key) const
{
    return overlays_.value(key);
}

bool ModelOverlayStore::isFavorite(const QString &key) const
{
    return overlays_.value(key).favorite;
}

bool ModelOverlayStore::isHidden(const QString &key) const
{
    return overlays_.value(key).hidden;
}

void ModelOverlayStore::setFavorite(const QString &key, bool favorite)
{
    if (key.trimmed().isEmpty())
        return;
    ModelOverlay &o = overlays_[key];
    if (o.favorite == favorite)
        return;
    o.favorite = favorite;
    save();
}

void ModelOverlayStore::setHidden(const QString &key, bool hidden)
{
    if (key.trimmed().isEmpty())
        return;
    ModelOverlay &o = overlays_[key];
    if (o.hidden == hidden)
        return;
    o.hidden = hidden;
    save();
}

void ModelOverlayStore::setUserTags(const QString &key, const QStringList &tags)
{
    if (key.trimmed().isEmpty())
        return;
    overlays_[key].userTags = tags;
    save();
}

void ModelOverlayStore::noteUsed(const QString &key, const QString &mode)
{
    if (key.trimmed().isEmpty())
        return;
    ModelOverlay &o = overlays_[key];
    o.useCount += 1;
    o.lastUsedMode = mode;
    save();
}

QString ModelOverlayStore::workflowProfile(const QString &key) const
{
    return overlays_.value(key).workflowProfile;
}

void ModelOverlayStore::setWorkflowProfile(const QString &key, const QString &profile)
{
    if (key.trimmed().isEmpty())
        return;
    const QString value = profile.trimmed();
    ModelOverlay &o = overlays_[key];
    if (o.workflowProfile == value)
        return;
    o.workflowProfile = value;
    save();
}

void ModelOverlayStore::load()
{
    overlays_.clear();

    QFile file(filePath_);
    if (!file.open(QIODevice::ReadOnly))
        return;

    const QJsonDocument document = QJsonDocument::fromJson(file.readAll());
    if (!document.isObject())
        return;

    const QJsonObject root = document.object().value(QStringLiteral("models")).toObject();
    for (auto it = root.begin(); it != root.end(); ++it)
    {
        const QJsonObject entry = it.value().toObject();
        ModelOverlay o;
        o.favorite = entry.value(QStringLiteral("favorite")).toBool(false);
        o.hidden = entry.value(QStringLiteral("hidden")).toBool(false);
        o.userTags = toStringList(entry.value(QStringLiteral("userTags")).toArray());
        o.lastUsedMode = entry.value(QStringLiteral("lastUsedMode")).toString();
        o.useCount = entry.value(QStringLiteral("useCount")).toInt(0);
        o.workflowProfile = entry.value(QStringLiteral("workflowProfile")).toString();
        overlays_.insert(it.key(), o);
    }
}

void ModelOverlayStore::save() const
{
    QJsonObject models;
    for (auto it = overlays_.constBegin(); it != overlays_.constEnd(); ++it)
    {
        const ModelOverlay &o = it.value();
        // Skip pure-default entries so the file stays lean.
        if (!o.favorite && !o.hidden && o.userTags.isEmpty() && o.lastUsedMode.isEmpty() && o.useCount == 0 &&
            o.workflowProfile.isEmpty())
            continue;

        QJsonObject entry;
        entry.insert(QStringLiteral("favorite"), o.favorite);
        entry.insert(QStringLiteral("hidden"), o.hidden);
        entry.insert(QStringLiteral("userTags"), QJsonArray::fromStringList(o.userTags));
        if (!o.lastUsedMode.isEmpty())
            entry.insert(QStringLiteral("lastUsedMode"), o.lastUsedMode);
        entry.insert(QStringLiteral("useCount"), o.useCount);
        if (!o.workflowProfile.isEmpty())
            entry.insert(QStringLiteral("workflowProfile"), o.workflowProfile);
        models.insert(it.key(), entry);
    }

    QJsonObject root;
    root.insert(QStringLiteral("version"), 1);
    root.insert(QStringLiteral("models"), models);

    QSaveFile file(filePath_);
    if (!file.open(QIODevice::WriteOnly))
        return;
    file.write(QJsonDocument(root).toJson(QJsonDocument::Indented));
    file.commit();
}

} // namespace spellvision::assets
