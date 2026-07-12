#include "ModelSidecar.h"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonValue>

namespace spellvision::assets
{

namespace
{
// First existing sibling `<base>.<ext>` for ext in `candidates`, else empty.
QString firstExistingSibling(const QString &base, const QStringList &candidates)
{
    for (const QString &ext : candidates)
    {
        const QString path = base + QLatin1Char('.') + ext;
        if (QFileInfo::exists(path))
            return path;
    }
    return QString();
}

QStringList jsonArrayToStringList(const QJsonArray &array)
{
    QStringList out;
    out.reserve(array.size());
    for (const QJsonValue &value : array)
    {
        const QString text = value.toString().trimmed();
        if (!text.isEmpty())
            out << text;
    }
    return out;
}
} // namespace

SidecarSet resolveSidecars(const QString &modelPath)
{
    SidecarSet set;

    const QString trimmed = modelPath.trimmed();
    if (trimmed.isEmpty())
        return set;

    const QFileInfo info(trimmed);
    // Shared-basename base: <dir>/<completeBaseName>. completeBaseName() strips only the final
    // suffix, so "wan2.2_t2v_...scaled.safetensors" -> "wan2.2_t2v_...scaled".
    const QString base = info.dir().filePath(info.completeBaseName());

    set.imagePath = firstExistingSibling(base, {QStringLiteral("png"),
                                                QStringLiteral("jpg"),
                                                QStringLiteral("jpeg"),
                                                QStringLiteral("webp")});
    set.videoPath = firstExistingSibling(base, {QStringLiteral("mp4")});
    set.metadataPath = firstExistingSibling(base, {QStringLiteral("metadata.json"),
                                                   QStringLiteral("json"),
                                                   QStringLiteral("civitai.info")});
    return set;
}

ModelMetadata parseModelMetadata(const QString &metadataPath)
{
    ModelMetadata meta;

    if (metadataPath.trimmed().isEmpty())
        return meta;

    QFile file(metadataPath);
    if (!file.open(QIODevice::ReadOnly))
        return meta;

    QJsonParseError error;
    const QJsonDocument document = QJsonDocument::fromJson(file.readAll(), &error);
    if (error.error != QJsonParseError::NoError || !document.isObject())
        return meta;

    const QJsonObject obj = document.object();

    meta.baseModel = obj.value(QStringLiteral("base_model")).toString().trimmed();
    meta.tags = jsonArrayToStringList(obj.value(QStringLiteral("tags")).toArray());
    meta.description = obj.value(QStringLiteral("modelDescription")).toString().trimmed();
    meta.sha256 = obj.value(QStringLiteral("sha256")).toString().trimmed();
    meta.modelType = obj.value(QStringLiteral("model_type")).toString().trimmed();
    meta.modelName = obj.value(QStringLiteral("model_name")).toString().trimmed();
    meta.previewUrl = obj.value(QStringLiteral("preview_url")).toString().trimmed();

    // CORRECTION #1: trigger words live in civitai.trainedWords, NOT usage_tips (which is "{}" 100%
    // of the time). Fall back to a top-level trainedWords for other scrapers.
    QJsonArray trained = obj.value(QStringLiteral("civitai")).toObject().value(QStringLiteral("trainedWords")).toArray();
    if (trained.isEmpty())
        trained = obj.value(QStringLiteral("trainedWords")).toArray();
    meta.triggerWords = jsonArrayToStringList(trained);

    meta.loaded = true;
    return meta;
}

} // namespace spellvision::assets
