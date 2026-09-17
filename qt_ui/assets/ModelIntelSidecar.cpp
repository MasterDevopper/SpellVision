#include "ModelIntelSidecar.h"

#include "ModelKindTabs.h"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonValue>
#include <QRegularExpression>
#include <QSettings>

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

QString ModelIntelRecommendation::caption() const
{
    if (provenance == QStringLiteral("user"))
        return QStringLiteral("you set this");
    if (provenance == QStringLiteral("site:image-meta-mode") && total > 0)
    {
        return QStringLiteral("from %1 of %2 example images on the site")
            .arg(agreeing)
            .arg(total);
    }
    if (provenance == QStringLiteral("site:image-meta-weak") && total > 0)
    {
        // Below the quorum. It is still evidence from this model's author, and saying how thin it
        // is beats either hiding it or presenting it as agreement.
        return QStringLiteral("from only %1 of %2 example images").arg(agreeing).arg(total);
    }
    if (provenance == QStringLiteral("site:trainedWords"))
        return QStringLiteral("the trigger words the site lists");
    if (provenance.startsWith(QStringLiteral("card:")))
        return QStringLiteral("read out of the model card");
    if (provenance == QStringLiteral("table:family-default"))
        return QStringLiteral("a family default, not this model");
    return provenance;
}

bool ModelIntelRecommendation::isFromThisModel() const
{
    return provenance == QStringLiteral("user") || provenance.startsWith(QStringLiteral("site:"))
        || provenance.startsWith(QStringLiteral("card:"));
}

ModelIntelRecommendation ModelIntel::recommendationFor(const QString &field) const
{
    for (const ModelIntelRecommendation &entry : recommended)
    {
        if (entry.field == field)
            return entry;
    }
    return {};
}

QString plainTextFromHtml(const QString &html)
{
    QString text = html;
    text.replace(QRegularExpression(QStringLiteral("<br\\s*/?>"), QRegularExpression::CaseInsensitiveOption),
                 QStringLiteral(" "));
    text.replace(QRegularExpression(QStringLiteral("</p>"), QRegularExpression::CaseInsensitiveOption),
                 QStringLiteral(" "));
    text.remove(QRegularExpression(QStringLiteral("<[^>]*>")));
    // The site's descriptions carry entities, and a user reading "&amp;" in an inspector learns
    // that the app cannot read its own data.
    text.replace(QStringLiteral("&nbsp;"), QStringLiteral(" "));
    text.replace(QStringLiteral("&amp;"), QStringLiteral("&"));
    text.replace(QStringLiteral("&lt;"), QStringLiteral("<"));
    text.replace(QStringLiteral("&gt;"), QStringLiteral(">"));
    text.replace(QStringLiteral("&quot;"), QStringLiteral("\""));
    text.replace(QStringLiteral("&#39;"), QStringLiteral("'"));
    return text.simplified();
}

ModelIdentification ModelIntel::identification() const
{
    if (!present)
        return ModelIdentification::NeverAsked;
    return sources.isEmpty() ? ModelIdentification::NothingFound : ModelIdentification::Identified;
}

ModelIntelImage ModelIntel::coverImage() const
{
    // The user's own picture outranks the site's cover -- that is the whole point of setting one,
    // and a later refresh that reorders the gallery must not quietly demote it.
    for (const ModelIntelImage &image : images)
    {
        if (image.userOverride)
            return image;
    }
    for (const ModelIntelImage &image : images)
    {
        if (image.isCover)
            return image;
    }
    return images.isEmpty() ? ModelIntelImage{} : images.first();
}

QString identificationCaption(ModelIdentification state)
{
    switch (state)
    {
    case ModelIdentification::Identified:
        return QString();
    case ModelIdentification::NothingFound:
        // We asked. The site does not have this file. That is a finished answer, and refreshing
        // again will not change it.
        return QStringLiteral("No match on any site");
    case ModelIdentification::NeverAsked:
        break;
    }
    // Nothing has ever looked. There is an action here, and the caption names it.
    return QStringLiteral("Not identified yet");
}

int nsfwPreviewCeiling()
{
    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    bool ok = false;
    const int configured = settings.value(QStringLiteral("models/nsfwPreviewLevel"), 2).toInt(&ok);
    return ok ? configured : 2;
}

bool previewShouldBlur(int imageNsfwLevel, int ceiling)
{
    // A level of 0 is CivitAI's "not rated", not "safe". Treating an unrated picture as safe is
    // the failure mode with a cost, so only a positive level that exceeds the ceiling blurs -- and
    // a ceiling below zero (a user who wants everything blurred) still catches it.
    return imageNsfwLevel > ceiling;
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

    const QJsonObject display = root.value(QStringLiteral("display")).toObject();
    const QJsonObject name = display.value(QStringLiteral("name")).toObject();
    intel.displayName = name.value(QStringLiteral("value")).toString().trimmed();
    intel.displayNameIsUserOverride = name.value(QStringLiteral("user_override")).toBool();
    intel.descriptionHtml = display.value(QStringLiteral("description_html")).toObject()
                                .value(QStringLiteral("value")).toString();
    intel.creator = display.value(QStringLiteral("creator")).toString().trimmed();
    const QJsonObject license = display.value(QStringLiteral("license")).toObject();
    intel.licenseName = license.value(QStringLiteral("name")).toString().trimmed();
    // `allowCommercialUse` is a LIST on CivitAI ("RentCivit", "Image", "Sell"...), not a bool.
    // Reading it as a bool is how this field would silently become "false" for a model that
    // permits everything.
    const QJsonValue commercial = license.value(QStringLiteral("allowCommercialUse"));
    if (commercial.isArray())
    {
        for (const QJsonValue &value : commercial.toArray())
        {
            const QString term = value.toString().trimmed();
            if (!term.isEmpty())
                intel.licenseCommercialUse << term;
        }
    }
    else if (commercial.isString())
    {
        const QString term = commercial.toString().trimmed();
        if (!term.isEmpty())
            intel.licenseCommercialUse << term;
    }
    const auto tristate = [&license](const char *key) {
        const QJsonValue value = license.value(QLatin1String(key));
        return value.isBool() ? (value.toBool() ? 1 : 0) : -1;
    };
    intel.licenseAllowsDerivatives = tristate("allowDerivatives");
    intel.licenseAllowsNoCredit = tristate("allowNoCredit");
    intel.licenseAllowsDifferentLicense = tristate("allowDifferentLicense");
    const QJsonValue nsfw = display.value(QStringLiteral("nsfw_level"));
    intel.nsfwLevel = nsfw.isDouble() ? nsfw.toInt() : -1;

    const QJsonObject triggers = display.value(QStringLiteral("trigger_words")).toObject();
    intel.triggerWordsAreUserOverride = triggers.value(QStringLiteral("user_override")).toBool();
    for (const QJsonValue &value : triggers.value(QStringLiteral("value")).toArray())
    {
        const QString word = value.toString().trimmed();
        if (!word.isEmpty())
            intel.triggerWords << word;
    }

    for (const QJsonValue &value : display.value(QStringLiteral("images")).toArray())
    {
        if (!value.isObject())
            continue;
        const QJsonObject object = value.toObject();
        ModelIntelImage image;
        image.originUrl = object.value(QStringLiteral("origin_url")).toString();
        // Written by Python as a native Windows path. Normalising here means every consumer --
        // QPixmap, the thumbnail cache, QFileInfo -- gets one spelling.
        image.localPath = QDir::fromNativeSeparators(
            object.value(QStringLiteral("local_path")).toString());
        image.width = object.value(QStringLiteral("width")).toInt();
        image.height = object.value(QStringLiteral("height")).toInt();
        image.nsfwLevel = object.value(QStringLiteral("nsfw_level")).toInt();
        image.isCover = object.value(QStringLiteral("is_cover")).toBool();
        image.userOverride = object.value(QStringLiteral("user_override")).toBool();
        if (image.localPath.isEmpty() && image.originUrl.isEmpty())
            continue;
        intel.images.push_back(image);
    }

    const QJsonObject recommended = root.value(QStringLiteral("recommended")).toObject();
    for (auto it = recommended.constBegin(); it != recommended.constEnd(); ++it)
    {
        const QJsonObject entry = it.value().toObject();
        if (entry.isEmpty())
            continue;
        ModelIntelRecommendation recommendation;
        recommendation.field = it.key();
        const QJsonValue value = entry.value(QStringLiteral("value"));
        if (value.isDouble())
        {
            const double number = value.toDouble();
            recommendation.value = (number == static_cast<double>(static_cast<qint64>(number)))
                ? QString::number(static_cast<qint64>(number))
                : QString::number(number, 'g', 4);
        }
        else if (value.isBool())
        {
            recommendation.value = value.toBool() ? QStringLiteral("true") : QStringLiteral("false");
        }
        else
        {
            recommendation.value = value.toString();
        }
        recommendation.provenance = entry.value(QStringLiteral("provenance")).toString();
        recommendation.confidence = entry.value(QStringLiteral("confidence")).toDouble(1.0);
        recommendation.agreeing = entry.value(QStringLiteral("n")).toInt();
        recommendation.total = entry.value(QStringLiteral("total")).toInt();
        if (recommendation.value.isEmpty())
            continue;
        intel.recommended.push_back(recommendation);
    }

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
