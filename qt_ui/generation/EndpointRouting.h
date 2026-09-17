#pragma once

#include <QHash>
#include <QJsonObject>
#include <QString>
#include <QStringList>

#include "shell/EndpointProbe.h"
#include "shell/EndpointRegistry.h"

namespace spellvision::generation
{

// What the job needs, reduced to the two things another machine can fail to have.
struct EndpointRequest
{
    QString family;              // "sdxl" / "wan" / "ltx"; lower case, may be empty
    QStringList requiredModels;  // checkpoint basenames the graph names
};

struct RouteDecision
{
    bool accepted = false;
    QString endpointId;
    QString baseUrl;
    bool isLocal = true;
    QString reason;   // why it was refused, or which endpoint Auto settled on and why
};

// "auto" -- the value the cockpit's Run on combo carries when the user has not chosen a machine.
QString autoEndpointChoice();

// Why this endpoint cannot run this job, or an empty string when it can.
//
// The LOCAL master is never refused here, and that is deliberate: it is the machine the app is
// running on, the worker starts its ComfyUI when it is not up, and a fresh install has no proven
// families at all. Gating entry 0 would mean the app could render nothing until it had already
// rendered something.
//
// For a remote endpoint every unknown is a refusal. "It did not answer" and "it could not list its
// checkpoints" are refusals, not permissions: the whole point of routing a job to another machine
// is that the failure would otherwise arrive twenty minutes later, as a red queue row.
QString endpointRefusal(const shell::Endpoint &endpoint,
                        const shell::EndpointStatus &status,
                        const EndpointRequest &request);

// Auto = the first idle, enabled endpoint in registry order whose capability check passes. The
// local master is entry 0, so a free local machine always wins.
//
// `requestedId` is "", "auto", or an endpoint id. An explicit pick that fails the check is REFUSED
// -- it does not quietly fall back to another machine, because silently running a job somewhere the
// user did not choose is the same class of substitution as swapping a model.
RouteDecision chooseEndpoint(const shell::EndpointRegistry &registry,
                             const QHash<QString, shell::EndpointStatus> &statuses,
                             const QString &requestedId,
                             const EndpointRequest &request);

// The two facts a generation payload carries that another machine can lack.
EndpointRequest endpointRequestFromPayload(const QJsonObject &payload);

// Where the cockpit's Run on pick lives. Per mode, because a T2V routed to the node and a T2I kept
// local is a perfectly ordinary thing to want.
QString runOnSettingsKey(const QString &modeId);
QString persistedRunOnChoice(const QString &modeId);
void persistRunOnChoice(const QString &modeId, const QString &endpointId);

} // namespace spellvision::generation
