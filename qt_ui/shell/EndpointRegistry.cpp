#include "shell/EndpointRegistry.h"

#include <QHostAddress>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonValue>
#include <QSettings>
#include <QUrl>

namespace spellvision::shell
{
namespace
{
const char *const kLocalId = "local";
const char *const kSettingsKey = "runtime/endpoints";

QString slug(const QString &label)
{
    QString out;
    for (const QChar ch : label.toLower())
    {
        if (ch.isLetterOrNumber())
            out.append(ch);
        else if (!out.isEmpty() && !out.endsWith(QLatin1Char('-')))
            out.append(QLatin1Char('-'));
    }
    while (out.endsWith(QLatin1Char('-')))
        out.chop(1);
    return out;
}

Endpoint endpointFromJson(const QJsonObject &object)
{
    Endpoint endpoint;
    endpoint.id = object.value(QStringLiteral("id")).toString().trimmed();
    endpoint.label = object.value(QStringLiteral("label")).toString().trimmed();
    endpoint.baseUrl = normalizedEndpointUrl(object.value(QStringLiteral("base_url")).toString());
    endpoint.enabled = object.value(QStringLiteral("enabled")).toBool(true);
    const QJsonArray families = object.value(QStringLiteral("families_allowed")).toArray();
    for (const QJsonValue &value : families)
    {
        const QString family = value.toString().trimmed().toLower();
        if (!family.isEmpty() && !endpoint.familiesAllowed.contains(family))
            endpoint.familiesAllowed.append(family);
    }
    return endpoint;
}
} // namespace

QString normalizedEndpointUrl(const QString &raw)
{
    QString text = raw.trimmed();
    if (text.isEmpty())
        return {};
    // Scheme FIRST, then the trailing slashes. The other order turns a bare "http://" into "http:",
    // which then looks schemeless, gets a second "http://" glued on and comes back as the valid-ish
    // "http://http:" -- an address nothing is listening at, accepted as though it were one.
    //
    // `spellnode:8188` is the obvious thing to type and QUrl reads it as scheme "spellnode" with
    // no host. Same accommodation comfy_endpoint.py and RuntimeProfile::load both make.
    if (!text.contains(QStringLiteral("://")))
        text.prepend(QStringLiteral("http://"));
    while (text.endsWith(QLatin1Char('/')))
        text.chop(1);
    const QUrl url(text);
    if (!url.isValid() || url.host().isEmpty())
        return {};
    return text;
}

bool endpointUrlIsLocal(const QString &url)
{
    const QUrl parsed(normalizedEndpointUrl(url));
    const QString host = parsed.host().trimmed().toLower();
    if (host.isEmpty() || host == QStringLiteral("localhost") || host == QStringLiteral("0.0.0.0")
        || host == QStringLiteral("::1"))
        return true;
    return QHostAddress(host).isLoopback();
}

bool Endpoint::isLocal() const
{
    return endpointUrlIsLocal(baseUrl);
}

QString EndpointRegistry::localId()
{
    return QString::fromLatin1(kLocalId);
}

QString EndpointRegistry::settingsKey()
{
    return QString::fromLatin1(kSettingsKey);
}

EndpointRegistry EndpointRegistry::defaults(const QString &localBaseUrl)
{
    Endpoint master;
    master.id = localId();
    master.label = QStringLiteral("This machine");
    master.baseUrl = normalizedEndpointUrl(localBaseUrl);
    master.enabled = true;
    EndpointRegistry registry;
    registry.entries_.append(master);
    return registry;
}

EndpointRegistry EndpointRegistry::fromJson(const QJsonArray &stored, const QString &localBaseUrl)
{
    EndpointRegistry registry = defaults(localBaseUrl);
    QStringList seenIds{registry.local().id};
    QStringList seenUrls{registry.local().baseUrl};

    for (const QJsonValue &value : stored)
    {
        if (!value.isObject())
            continue;
        Endpoint endpoint = endpointFromJson(value.toObject());
        if (endpoint.id == localId())
        {
            // The local master's ADDRESS belongs to the resolver, not to the stored copy -- the
            // 2026-07-17 cutover is the recorded case of a stored value outliving the thing it
            // described. Its label and its proven families are the user's, and survive.
            if (!endpoint.label.isEmpty())
                registry.entries_[0].label = endpoint.label;
            registry.entries_[0].familiesAllowed = endpoint.familiesAllowed;
            registry.entries_[0].enabled = true;
            continue;
        }
        if (endpoint.baseUrl.isEmpty())
            continue;
        if (endpoint.id.isEmpty())
        {
            endpoint.id = registry.proposeId(
                endpoint.label.isEmpty() ? QUrl(endpoint.baseUrl).host() : endpoint.label);
        }
        if (seenIds.contains(endpoint.id) || seenUrls.contains(endpoint.baseUrl))
            continue;
        if (endpoint.label.trimmed().isEmpty())
            endpoint.label = QUrl(endpoint.baseUrl).host();
        seenIds.append(endpoint.id);
        seenUrls.append(endpoint.baseUrl);
        registry.entries_.append(endpoint);
    }
    return registry;
}

EndpointRegistry EndpointRegistry::load(QSettings &settings, const QString &localBaseUrl)
{
    const QVariant raw = settings.value(settingsKey());
    if (!raw.isValid())
        return defaults(localBaseUrl);
    QJsonParseError error{};
    const QJsonDocument document = QJsonDocument::fromJson(raw.toString().toUtf8(), &error);
    if (error.error != QJsonParseError::NoError || !document.isArray())
        return defaults(localBaseUrl);
    return fromJson(document.array(), localBaseUrl);
}

EndpointRegistry EndpointRegistry::load(const QString &localBaseUrl)
{
    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    return load(settings, localBaseUrl);
}

QJsonArray EndpointRegistry::toJson() const
{
    QJsonArray array;
    for (const Endpoint &endpoint : entries_)
    {
        QJsonArray families;
        for (const QString &family : endpoint.familiesAllowed)
            families.append(family);
        array.append(QJsonObject{
            {QStringLiteral("id"), endpoint.id},
            {QStringLiteral("label"), endpoint.label},
            {QStringLiteral("base_url"), endpoint.baseUrl},
            {QStringLiteral("enabled"), endpoint.enabled},
            {QStringLiteral("families_allowed"), families},
        });
    }
    return array;
}

void EndpointRegistry::save(QSettings &settings) const
{
    settings.setValue(settingsKey(),
                      QString::fromUtf8(QJsonDocument(toJson()).toJson(QJsonDocument::Compact)));
}

void EndpointRegistry::save() const
{
    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    save(settings);
}

int EndpointRegistry::indexOf(const QString &id) const
{
    for (int index = 0; index < entries_.size(); ++index)
    {
        if (entries_.at(index).id == id)
            return index;
    }
    return -1;
}

const Endpoint *EndpointRegistry::find(const QString &id) const
{
    const int index = indexOf(id);
    return index < 0 ? nullptr : &entries_.at(index);
}

QString EndpointRegistry::proposeId(const QString &label) const
{
    QString base = slug(label);
    if (base.isEmpty())
        base = QStringLiteral("endpoint");
    if (base == localId())
        base = base + QStringLiteral("-2");
    QString candidate = base;
    int suffix = 2;
    while (indexOf(candidate) >= 0)
        candidate = QStringLiteral("%1-%2").arg(base).arg(suffix++);
    return candidate;
}

bool EndpointRegistry::upsert(const Endpoint &endpoint, QString *reason)
{
    const QString url = normalizedEndpointUrl(endpoint.baseUrl);
    if (url.isEmpty())
    {
        if (reason)
        {
            *reason = QStringLiteral("%1 is not an address SpellVision can reach.")
                          .arg(endpoint.baseUrl.trimmed());
        }
        return false;
    }
    const int existing = indexOf(endpoint.id);
    for (int index = 0; index < entries_.size(); ++index)
    {
        if (index == existing)
            continue;
        if (entries_.at(index).baseUrl == url)
        {
            if (reason)
            {
                *reason = QStringLiteral("%1 already answers at %2. One machine, one entry -- two "
                                         "entries would let SpellVision run two jobs on it at once.")
                              .arg(entries_.at(index).label, url);
            }
            return false;
        }
    }
    if (existing == 0 && url != entries_.at(0).baseUrl)
    {
        if (reason)
        {
            *reason = QStringLiteral("This machine's ComfyUI address comes from the runtime "
                                     "settings, not from this list.");
        }
        return false;
    }

    Endpoint stored = endpoint;
    stored.baseUrl = url;
    if (stored.label.trimmed().isEmpty())
        stored.label = QUrl(url).host();
    if (existing >= 0)
    {
        // Proven families are an outcome, never an input. Whoever edits a label must not be able to
        // hand an endpoint a family it has not rendered.
        stored.familiesAllowed = entries_.at(existing).familiesAllowed;
        entries_[existing] = stored;
        return true;
    }
    if (stored.id.trimmed().isEmpty() || stored.id == localId())
        stored.id = proposeId(stored.label);
    stored.familiesAllowed.clear();
    entries_.append(stored);
    return true;
}

bool EndpointRegistry::remove(const QString &id, QString *reason)
{
    if (id == localId())
    {
        if (reason)
            *reason = QStringLiteral("This machine cannot be removed.");
        return false;
    }
    const int index = indexOf(id);
    if (index <= 0)
    {
        if (reason)
            *reason = QStringLiteral("There is no endpoint with that id.");
        return false;
    }
    entries_.removeAt(index);
    return true;
}

bool EndpointRegistry::setEnabled(const QString &id, bool enabled)
{
    const int index = indexOf(id);
    if (index < 0)
        return false;
    entries_[index].enabled = enabled;
    return true;
}

bool EndpointRegistry::allowFamily(const QString &id, const QString &family)
{
    const int index = indexOf(id);
    const QString token = family.trimmed().toLower();
    if (index < 0 || token.isEmpty())
        return false;
    if (entries_.at(index).familiesAllowed.contains(token))
        return false;
    entries_[index].familiesAllowed.append(token);
    return true;
}

bool EndpointRegistry::disallowFamily(const QString &id, const QString &family)
{
    const int index = indexOf(id);
    const QString token = family.trimmed().toLower();
    if (index < 0)
        return false;
    return entries_[index].familiesAllowed.removeAll(token) > 0;
}

} // namespace spellvision::shell
