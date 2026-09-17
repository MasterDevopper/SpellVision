#include "ModelIntelSidecar.h"

#include "ModelKindTabs.h"

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
qint64 toI64(const QJsonValue &value)
{
    if (value.isDouble())
        return static_cast<qint64>(value.toDouble());
    return value.toString().toLongLong();
}
} // namespace

QString ModelIntelSource::siteLabel() const
{
    const QString token = site.trimmed().toLower();
    if (token == QStringLiteral("civitai"))
        return QStringLiteral("CivitAI");
    if (token == QStringLiteral("huggingface") || token == QStringLiteral("hf"))
        return QStringLiteral("HuggingFace");
    if (token.isEmpty())
        return QString();
    // An unknown site is named as it names itself rather than dropped: a badge that says a word
    // the user can search for beats no badge at all.
    return site.trimmed();
}

ModelIntelSource ModelIntel::primarySource() const
{
    return sources.isEmpty() ? ModelIntelSource{} : sources.first();
}

QString modelIntelSidecarPath(const QString &modelPath)
{
    const QString trimmed = modelPath.trimmed();
    if (trimmed.isEmpty())
        return QString();
    const QFileInfo info(trimmed);
    // Python's `Path.with_name(path.stem + SUFFIX)` — `stem` strips ONE suffix, which is what
    // completeBaseName() does. `baseName()` would cut at the first dot and miss every weight whose
    // name carries a version ("wan2.2_t2v....safetensors").
    return info.dir().filePath(info.completeBaseName() + QStringLiteral(".spellvision.json"));
}

ModelIntel readModelIntel(const QString &modelPath)
{
    const QString sidecar = modelIntelSidecarPath(modelPath);
    if (sidecar.isEmpty())
        return {};
    QFile file(sidecar);
    if (!file.open(QIODevice::ReadOnly))
        return {};
    return parseModelIntelDocument(file.readAll(), sidecar);
}

ModelIntel parseModelIntelDocument(const QByteArray &json, const QString &sidecarPath)
{
    ModelIntel intel;

    QJsonParseError error{};
    const QJsonDocument document = QJsonDocument::fromJson(json, &error);
    if (error.error != QJsonParseError::NoError || !document.isObject())
        return intel;

    const QJsonObject root = document.object();
    intel.present = true;
    intel.sidecarPath = sidecarPath;
    intel.schema = root.value(QStringLiteral("schema")).toString();

    const QJsonObject identity = root.value(QStringLiteral("identity")).toObject();
    intel.fileName = identity.value(QStringLiteral("file_name")).toString();
    intel.size = toI64(identity.value(QStringLiteral("size")));
    intel.sha256 = identity.value(QStringLiteral("hashes")).toObject()
                       .value(QStringLiteral("sha256")).toString().trimmed();
    // The ten-value vocabulary, and "other" for anything else. The sidecar is written by
    // `model_intelligence.kinds.normalise_kind`, so this normally agrees with what is on disk —
    // but a sidecar from a newer build, or one hand-edited, must not be able to invent a tab.
    intel.kind = ModelKindTabs::normaliseKind(identity.value(QStringLiteral("kind")).toString());
    // The live library really does carry `"family": "unknown"` in sidecars written before
    // `normalise_family` landed. An undetermined family is EMPTY here, so a consumer tests one
    // thing rather than remembering a magic word.
    intel.family = ModelKindTabs::normaliseFamily(identity.value(QStringLiteral("family")).toString());
    intel.baseModel = identity.value(QStringLiteral("base_model")).toString().trimmed();
    intel.quantisation = identity.value(QStringLiteral("quantisation")).toString().trimmed();

    for (const QJsonValue &value : identity.value(QStringLiteral("sources")).toArray())
    {
        if (!value.isObject())
            continue;
        const QJsonObject object = value.toObject();
        ModelIntelSource source;
        source.site = object.value(QStringLiteral("site")).toString().trimmed();
        source.url = object.value(QStringLiteral("url")).toString().trimmed();
        source.modelId = toI64(object.value(QStringLiteral("model_id")));
        source.versionId = toI64(object.value(QStringLiteral("version_id")));
        if (source.site.isEmpty() && source.url.isEmpty())
            continue;
        intel.sources.push_back(source);
    }

    return intel;
}

} // namespace spellvision::assets
