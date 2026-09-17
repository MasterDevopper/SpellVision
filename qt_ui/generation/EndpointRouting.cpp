#include "generation/EndpointRouting.h"

#include <QFileInfo>
#include <QSettings>

namespace spellvision::generation
{
namespace
{
QString basename(const QString &value)
{
    return QFileInfo(QString(value).replace(QLatin1Char('\\'), QLatin1Char('/'))).fileName();
}

// Whether the machine is free to take a job right now.
//
// The two sides are deliberately asymmetric. A REMOTE endpoint that has not answered is not idle --
// unknown is never a permission. The LOCAL master is idle unless it is KNOWN to be busy, because
// SpellVision's own queue already serialises its lane and that is exactly how the app behaves today;
// treating an unprobed local master as unavailable would make Auto walk off this machine the first
// time the app started, which is the opposite of what Auto is for.
bool freeToTakeAJob(const shell::Endpoint &endpoint, const shell::EndpointStatus &status)
{
    if (endpoint.isLocal())
        return !(status.probed && status.reachable && status.queueKnown && status.busy);
    return status.idle();
}
} // namespace

QString autoEndpointChoice()
{
    return QStringLiteral("auto");
}

QString endpointRefusal(const shell::Endpoint &endpoint,
                        const shell::EndpointStatus &status,
                        const EndpointRequest &request)
{
    if (!endpoint.enabled)
        return QStringLiteral("%1 is switched off in Runtime.").arg(endpoint.label);
    if (endpoint.isLocal())
        return {};

    if (!status.probed)
    {
        return QStringLiteral("%1 has not answered a health check yet, so SpellVision cannot tell "
                              "whether it can run this. Open Runtime and refresh.")
            .arg(endpoint.label);
    }
    if (!status.reachable)
    {
        const QString why = status.detail.trimmed().isEmpty()
            ? QStringLiteral("no answer")
            : status.detail.trimmed();
        return QStringLiteral("%1 did not answer at %2 (%3).")
            .arg(endpoint.label, endpoint.baseUrl, why);
    }

    const QString family = request.family.trimmed().toLower();
    if (!family.isEmpty() && !endpoint.familiesAllowed.contains(family))
    {
        return QStringLiteral("%1 has not rendered a %2 job yet. Run one there from Runtime first "
                              "-- SpellVision only ticks a family after a real success on that "
                              "machine.")
            .arg(endpoint.label, family.toUpper());
    }

    for (const QString &required : request.requiredModels)
    {
        const QString wanted = basename(required);
        if (wanted.isEmpty())
            continue;
        if (!status.modelsKnown)
        {
            return QStringLiteral("%1 could not list its checkpoints, so SpellVision cannot tell "
                                  "whether it has %2.")
                .arg(endpoint.label, wanted);
        }
        bool present = false;
        for (const QString &have : status.checkpoints)
        {
            if (basename(have).compare(wanted, Qt::CaseInsensitive) == 0)
            {
                present = true;
                break;
            }
        }
        if (!present)
            return QStringLiteral("%1 does not have %2.").arg(endpoint.label, wanted);
    }
    return {};
}

RouteDecision chooseEndpoint(const shell::EndpointRegistry &registry,
                             const QHash<QString, shell::EndpointStatus> &statuses,
                             const QString &requestedId,
                             const EndpointRequest &request)
{
    RouteDecision decision;
    const QString wanted = requestedId.trimmed().isEmpty() ? autoEndpointChoice()
                                                           : requestedId.trimmed();

    if (wanted != autoEndpointChoice())
    {
        const shell::Endpoint *endpoint = registry.find(wanted);
        if (!endpoint)
        {
            // The stored pick names an endpoint that has since been removed. Auto would be the
            // convenient answer and the wrong one: the user asked for a machine, and running the
            // job somewhere else without saying so is the substitution this whole gate exists to
            // prevent.
            decision.reason = QStringLiteral("The machine this page was set to run on is no longer "
                                             "in Runtime. Choose one again.");
            return decision;
        }
        const QString refusal = endpointRefusal(*endpoint, statuses.value(endpoint->id), request);
        if (!refusal.isEmpty())
        {
            decision.endpointId = endpoint->id;
            decision.reason = refusal;
            return decision;
        }
        decision.accepted = true;
        decision.endpointId = endpoint->id;
        decision.baseUrl = endpoint->baseUrl;
        decision.isLocal = endpoint->isLocal();
        decision.reason = QStringLiteral("Running on %1.").arg(endpoint->label);
        return decision;
    }

    for (const shell::Endpoint &endpoint : registry.entries())
    {
        const shell::EndpointStatus status = statuses.value(endpoint.id);
        if (!endpoint.enabled || !freeToTakeAJob(endpoint, status))
            continue;
        if (!endpointRefusal(endpoint, status, request).isEmpty())
            continue;
        decision.accepted = true;
        decision.endpointId = endpoint.id;
        decision.baseUrl = endpoint.baseUrl;
        decision.isLocal = endpoint.isLocal();
        decision.reason = QStringLiteral("Auto chose %1.").arg(endpoint.label);
        return decision;
    }

    // Every machine is busy or unusable. Auto still lands on the local master: a job queued here is
    // what the app has always done, and refusing to render because both boxes are working would be
    // a regression dressed as safety.
    const shell::Endpoint &master = registry.local();
    decision.accepted = true;
    decision.endpointId = master.id;
    decision.baseUrl = master.baseUrl;
    decision.isLocal = true;
    decision.reason = QStringLiteral("Auto queued on %1 -- nothing else was free.").arg(master.label);
    return decision;
}

EndpointRequest endpointRequestFromPayload(const QJsonObject &payload)
{
    EndpointRequest request;
    const QString videoFamily =
        payload.value(QStringLiteral("resolved_native_video_family")).toString().trimmed();
    request.family = videoFamily.isEmpty()
        ? payload.value(QStringLiteral("model_family")).toString().trimmed().toLower()
        : videoFamily.toLower();

    const QString model = payload.value(QStringLiteral("model")).toString().trimmed();
    if (!model.isEmpty())
        request.requiredModels.append(model);
    return request;
}

QString runOnSettingsKey(const QString &modeId)
{
    return QStringLiteral("runtime/runOn/%1").arg(modeId.trimmed().toLower());
}

QString persistedRunOnChoice(const QString &modeId)
{
    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    const QString stored = settings.value(runOnSettingsKey(modeId)).toString().trimmed();
    return stored.isEmpty() ? autoEndpointChoice() : stored;
}

void persistRunOnChoice(const QString &modeId, const QString &endpointId)
{
    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    settings.setValue(runOnSettingsKey(modeId), endpointId.trimmed().isEmpty()
                                                    ? autoEndpointChoice()
                                                    : endpointId.trimmed());
}

} // namespace spellvision::generation
