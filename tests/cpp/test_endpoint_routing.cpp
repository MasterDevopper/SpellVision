// Which machine runs this job, and the refusal that has to come BEFORE the queue.
//
// The shape this exists to prevent is the one the research found in ComfyUI-Distributed: with no
// reachable worker it logs "Falling back to master execution" and runs the job on the master. The
// job succeeds, on the wrong machine, and nothing says so. NetDist's version of the same mistake is
// substituting a black image when the fetch fails. Both are silent substitutions, and a router whose
// failure mode is silent is worse than no router -- the user believes a thing about their render
// that is not true.
//
// So: Auto prefers the free local master, Auto skips a machine that has not answered, and an
// EXPLICIT pick that cannot run the job is refused by name before anything is enqueued. Never a
// queued job that fails twenty minutes later, and never a quiet reroute.

#include <QtTest>

#include <QHash>
#include <QJsonObject>

#include "generation/EndpointRouting.h"
#include "shell/EndpointProbe.h"
#include "shell/EndpointRegistry.h"

using spellvision::generation::EndpointRequest;
using spellvision::generation::RouteDecision;
using spellvision::generation::autoEndpointChoice;
using spellvision::generation::chooseEndpoint;
using spellvision::generation::endpointRefusal;
using spellvision::generation::endpointRequestFromPayload;
using spellvision::shell::Endpoint;
using spellvision::shell::EndpointRegistry;
using spellvision::shell::EndpointStatus;

namespace
{
const char *const kLocalUrl = "http://127.0.0.1:8188";
const char *const kNodeUrl = "http://192.168.1.127:8188";
const char *const kKrea2 = "loxsUtopicWorldKrea2_v20Quants.safetensors";

EndpointRegistry twoMachines(QString *nodeId)
{
    EndpointRegistry registry = EndpointRegistry::defaults(QString::fromLatin1(kLocalUrl));
    Endpoint node;
    node.label = QStringLiteral("SpellNode");
    node.baseUrl = QString::fromLatin1(kNodeUrl);
    registry.upsert(node);
    if (nodeId)
        *nodeId = registry.entries().at(1).id;
    return registry;
}

EndpointStatus online(const QStringList &checkpoints, bool busy = false)
{
    EndpointStatus status;
    status.probed = true;
    status.reachable = true;
    status.queueKnown = true;
    status.busy = busy;
    status.modelsKnown = true;
    status.checkpoints = checkpoints;
    status.checkedAt = QDateTime::currentDateTime();
    return status;
}

EndpointStatus offline(const QString &why)
{
    EndpointStatus status;
    status.probed = true;
    status.reachable = false;
    status.detail = why;
    status.checkedAt = QDateTime::currentDateTime();
    return status;
}

EndpointRequest sdxlKrea2()
{
    EndpointRequest request;
    request.family = QStringLiteral("sdxl");
    request.requiredModels = QStringList{QString::fromLatin1(kKrea2)};
    return request;
}
} // namespace

class TestEndpointRouting : public QObject
{
    Q_OBJECT

private slots:
    void autoPicksTheLocalMasterWhenItIsFree();
    void autoSkipsAnEndpointThatDidNotAnswer();
    void autoNeverWalksOffAnUnprobedLocalMaster();
    void anExplicitPickThatIsOfflineIsRefusedByName();
    void anExplicitPickMissingTheModelIsRefusedByName();
    void anUngatedFamilyIsRefusedByName();
    void aGatedFamilyWithTheModelIsAccepted();
    void theLocalMasterIsNeverGated();
    void aBusyRemoteIsSkippedByAutoButHonouredWhenAskedFor();
    void aRemovedEndpointRefusesRatherThanSilentlyRerouting();
    void thePayloadNamesTheFamilyAndTheCheckpoint();
};

void TestEndpointRouting::autoPicksTheLocalMasterWhenItIsFree()
{
    QString nodeId;
    const EndpointRegistry registry = twoMachines(&nodeId);
    QHash<QString, EndpointStatus> statuses;
    statuses.insert(EndpointRegistry::localId(), online({QString::fromLatin1(kKrea2)}));
    statuses.insert(nodeId, online({QString::fromLatin1(kKrea2)}));

    const RouteDecision decision =
        chooseEndpoint(registry, statuses, autoEndpointChoice(), sdxlKrea2());
    QVERIFY(decision.accepted);
    QCOMPARE(decision.endpointId, EndpointRegistry::localId());
    QVERIFY(decision.isLocal);
}

void TestEndpointRouting::autoSkipsAnEndpointThatDidNotAnswer()
{
    QString nodeId;
    EndpointRegistry registry = twoMachines(&nodeId);
    registry.allowFamily(nodeId, QStringLiteral("sdxl"));
    QHash<QString, EndpointStatus> statuses;
    statuses.insert(EndpointRegistry::localId(), online({QString::fromLatin1(kKrea2)}, true));
    statuses.insert(nodeId, offline(QStringLiteral("Host not found")));

    // Local is busy and the node is down. Auto still lands on the master rather than refusing --
    // a queued local job is what the app has always done -- but it must say that is what happened.
    const RouteDecision decision =
        chooseEndpoint(registry, statuses, autoEndpointChoice(), sdxlKrea2());
    QVERIFY(decision.accepted);
    QCOMPARE(decision.endpointId, EndpointRegistry::localId());
    QVERIFY(decision.reason.contains(QStringLiteral("nothing else was free")));

    // With the master free again it is picked outright, and the node is never considered.
    statuses.insert(EndpointRegistry::localId(), online({QString::fromLatin1(kKrea2)}));
    const RouteDecision second =
        chooseEndpoint(registry, statuses, autoEndpointChoice(), sdxlKrea2());
    QCOMPARE(second.endpointId, EndpointRegistry::localId());
}

void TestEndpointRouting::autoNeverWalksOffAnUnprobedLocalMaster()
{
    // No probe has completed. For a REMOTE endpoint that is a refusal; for the master it is the
    // ordinary state on the first frame after launch, and treating it as unavailable would send the
    // very first job of a session to another machine.
    QString nodeId;
    EndpointRegistry registry = twoMachines(&nodeId);
    registry.allowFamily(nodeId, QStringLiteral("sdxl"));
    QHash<QString, EndpointStatus> statuses;
    statuses.insert(nodeId, online({QString::fromLatin1(kKrea2)}));

    const RouteDecision decision =
        chooseEndpoint(registry, statuses, autoEndpointChoice(), sdxlKrea2());
    QVERIFY(decision.accepted);
    QCOMPARE(decision.endpointId, EndpointRegistry::localId());
}

void TestEndpointRouting::anExplicitPickThatIsOfflineIsRefusedByName()
{
    QString nodeId;
    EndpointRegistry registry = twoMachines(&nodeId);
    registry.allowFamily(nodeId, QStringLiteral("sdxl"));
    QHash<QString, EndpointStatus> statuses;
    statuses.insert(EndpointRegistry::localId(), online({QString::fromLatin1(kKrea2)}));
    statuses.insert(nodeId, offline(QStringLiteral("Connection refused")));

    const RouteDecision decision = chooseEndpoint(registry, statuses, nodeId, sdxlKrea2());
    QVERIFY2(!decision.accepted, qPrintable(decision.reason));
    // Refused, not rerouted. The local master is right there and must NOT be substituted.
    QVERIFY(decision.baseUrl.isEmpty());
    QVERIFY(decision.reason.contains(QStringLiteral("SpellNode")));
    QVERIFY(decision.reason.contains(QStringLiteral("Connection refused")));
}

void TestEndpointRouting::anExplicitPickMissingTheModelIsRefusedByName()
{
    QString nodeId;
    EndpointRegistry registry = twoMachines(&nodeId);
    registry.allowFamily(nodeId, QStringLiteral("sdxl"));
    QHash<QString, EndpointStatus> statuses;
    statuses.insert(nodeId, online({QStringLiteral("sd_xl_base_1.0.safetensors")}));

    const RouteDecision decision = chooseEndpoint(registry, statuses, nodeId, sdxlKrea2());
    QVERIFY(!decision.accepted);
    QCOMPARE(decision.reason,
             QStringLiteral("SpellNode does not have %1.").arg(QString::fromLatin1(kKrea2)));

    // And "I could not find out" is a refusal too, not a pass. A listing that did not answer is the
    // state a dead CIFS model share produces, which is exactly when the job would fail late.
    EndpointStatus unlisted = online({});
    unlisted.modelsKnown = false;
    statuses.insert(nodeId, unlisted);
    const RouteDecision unknown = chooseEndpoint(registry, statuses, nodeId, sdxlKrea2());
    QVERIFY(!unknown.accepted);
    QVERIFY(unknown.reason.contains(QStringLiteral("could not list its checkpoints")));
}

void TestEndpointRouting::anUngatedFamilyIsRefusedByName()
{
    // The node has the file and is online. It has never rendered an SDXL job there, so it is not
    // cleared to. "A 24 GB Ampere card probably does SDXL" is a guess, and a guess that is wrong
    // costs a queued job and a red row twenty minutes later.
    QString nodeId;
    const EndpointRegistry registry = twoMachines(&nodeId);
    QHash<QString, EndpointStatus> statuses;
    statuses.insert(nodeId, online({QString::fromLatin1(kKrea2)}));

    const RouteDecision decision = chooseEndpoint(registry, statuses, nodeId, sdxlKrea2());
    QVERIFY2(!decision.accepted, qPrintable(decision.reason));
    QVERIFY(decision.reason.contains(QStringLiteral("SpellNode")));
    QVERIFY(decision.reason.contains(QStringLiteral("SDXL")));

    // Auto must skip it for the same reason rather than routing there.
    statuses.insert(EndpointRegistry::localId(), online({QString::fromLatin1(kKrea2)}, true));
    const RouteDecision automatic =
        chooseEndpoint(registry, statuses, autoEndpointChoice(), sdxlKrea2());
    QCOMPARE(automatic.endpointId, EndpointRegistry::localId());
}

void TestEndpointRouting::aGatedFamilyWithTheModelIsAccepted()
{
    QString nodeId;
    EndpointRegistry registry = twoMachines(&nodeId);
    registry.allowFamily(nodeId, QStringLiteral("sdxl"));
    QHash<QString, EndpointStatus> statuses;
    statuses.insert(nodeId, online({QStringLiteral("other.safetensors"),
                                    QString::fromLatin1(kKrea2)}));

    const RouteDecision decision = chooseEndpoint(registry, statuses, nodeId, sdxlKrea2());
    QVERIFY2(decision.accepted, qPrintable(decision.reason));
    QCOMPARE(decision.baseUrl, QString::fromLatin1(kNodeUrl));
    QVERIFY(!decision.isLocal);
}

void TestEndpointRouting::theLocalMasterIsNeverGated()
{
    // A fresh install has proven no families anywhere. If entry 0 were gated the app could render
    // nothing at all until it had already rendered something.
    const EndpointRegistry registry = EndpointRegistry::defaults(QString::fromLatin1(kLocalUrl));
    const EndpointStatus nothingKnown;
    QCOMPARE(endpointRefusal(registry.local(), nothingKnown, sdxlKrea2()), QString());
}

void TestEndpointRouting::aBusyRemoteIsSkippedByAutoButHonouredWhenAskedFor()
{
    QString nodeId;
    EndpointRegistry registry = twoMachines(&nodeId);
    registry.allowFamily(nodeId, QStringLiteral("sdxl"));
    QHash<QString, EndpointStatus> statuses;
    statuses.insert(EndpointRegistry::localId(), online({QString::fromLatin1(kKrea2)}, true));
    statuses.insert(nodeId, online({QString::fromLatin1(kKrea2)}, true));

    // Auto wants a FREE machine, and neither is; it falls back to the master's queue.
    const RouteDecision automatic =
        chooseEndpoint(registry, statuses, autoEndpointChoice(), sdxlKrea2());
    QCOMPARE(automatic.endpointId, EndpointRegistry::localId());

    // An explicit pick of a busy machine is not a refusal -- the worker keeps one queue lane per
    // endpoint, so it waits there. Refusing would make "run on SpellNode" mean "run on SpellNode
    // only if it happens to be idle this second".
    const RouteDecision explicitPick = chooseEndpoint(registry, statuses, nodeId, sdxlKrea2());
    QVERIFY2(explicitPick.accepted, qPrintable(explicitPick.reason));
    QCOMPARE(explicitPick.baseUrl, QString::fromLatin1(kNodeUrl));
}

void TestEndpointRouting::aRemovedEndpointRefusesRatherThanSilentlyRerouting()
{
    const EndpointRegistry registry = EndpointRegistry::defaults(QString::fromLatin1(kLocalUrl));
    const QHash<QString, EndpointStatus> statuses;
    const RouteDecision decision =
        chooseEndpoint(registry, statuses, QStringLiteral("spellnode"), sdxlKrea2());
    QVERIFY(!decision.accepted);
    QVERIFY(!decision.reason.isEmpty());
}

void TestEndpointRouting::thePayloadNamesTheFamilyAndTheCheckpoint()
{
    QJsonObject image;
    image.insert(QStringLiteral("model_family"), QStringLiteral("SDXL"));
    image.insert(QStringLiteral("model"), QStringLiteral("D:/AI_ASSETS/models/checkpoints/")
                                              + QString::fromLatin1(kKrea2));
    const EndpointRequest fromImage = endpointRequestFromPayload(image);
    QCOMPARE(fromImage.family, QStringLiteral("sdxl"));
    QCOMPARE(fromImage.requiredModels.size(), 1);

    // A video job's family is the RESOLVED one, not the checkpoint's -- the worker routes by
    // resolved_native_video_family and the gate has to agree with it.
    QJsonObject video;
    video.insert(QStringLiteral("model_family"), QStringLiteral("wan_video"));
    video.insert(QStringLiteral("resolved_native_video_family"), QStringLiteral("LTX"));
    QCOMPARE(endpointRequestFromPayload(video).family, QStringLiteral("ltx"));
}

QTEST_MAIN(TestEndpointRouting)
#include "test_endpoint_routing.moc"
