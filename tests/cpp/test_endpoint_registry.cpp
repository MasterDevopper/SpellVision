// The second machine was a string literal.
//
// ManagerPage.cpp:291 printed "192.168.1.127:8188 SpellNode" into a QLabel, :675 probed
// http://192.168.1.127:8188/system_stats with the host spelled again, and :681 then read the health
// of the LOCAL master back out of another label's text with .contains("healthy=yes"). Three copies
// of one fact and the third of them stored in a widget: the app could not be pointed at a different
// machine without a rebuild, and nothing outside that one page could ask what endpoints exist.
//
// This is the registry that replaces them. The cases here are the three that decide whether it can
// be trusted as the single source: a stored list survives a round trip, the local master cannot be
// removed, and a CORRUPT stored value falls back to the default registry rather than to an empty
// one -- an empty registry has no local master, so a damaged setting would leave the app unable to
// render on the machine it is running on, and it would look like a configuration choice.

#include <QtTest>

#include <QDir>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSettings>
#include <QTemporaryDir>

#include "shell/EndpointRegistry.h"

using spellvision::shell::Endpoint;
using spellvision::shell::EndpointRegistry;
using spellvision::shell::endpointUrlIsLocal;
using spellvision::shell::normalizedEndpointUrl;

namespace
{
const char *const kLocalUrl = "http://127.0.0.1:8188";
const char *const kNodeUrl = "http://192.168.1.127:8188";
} // namespace

class TestEndpointRegistry : public QObject
{
    Q_OBJECT

private slots:
    void urlNormalisationMatchesTheResolver();
    void defaultsHoldOnlyTheLocalMaster();
    void aStoredListRoundTrips();
    void theLocalEntryCannotBeRemoved();
    void theLocalEntryCannotBeReAddressedFromTheList();
    void aMalformedStoredValueYieldsTheDefaultRegistry();
    void anEmptyStoredArrayStillHasTheLocalMaster();
    void aDuplicateUrlIsRefusedWithAReason();
    void familiesAreWrittenByTheAppAndOnlyUnticked();

private:
    static QSettings *scratch(QTemporaryDir &dir)
    {
        return new QSettings(QDir(dir.path()).filePath(QStringLiteral("sv.ini")),
                             QSettings::IniFormat);
    }
};

void TestEndpointRegistry::urlNormalisationMatchesTheResolver()
{
    // A bare host:port is what a person types, and QUrl reads it as a SCHEME with no host. Both
    // comfy_endpoint.py and RuntimeProfile::load make this accommodation; a third resolver that
    // did not would reject the address the other two accept.
    QCOMPARE(normalizedEndpointUrl(QStringLiteral("spellnode:8188")),
             QStringLiteral("http://spellnode:8188"));
    QCOMPARE(normalizedEndpointUrl(QStringLiteral("http://spellnode:8188/")),
             QStringLiteral("http://spellnode:8188"));
    QVERIFY(normalizedEndpointUrl(QStringLiteral("   ")).isEmpty());
    QVERIFY(normalizedEndpointUrl(QStringLiteral("http://")).isEmpty());

    // Loopback by ADDRESS, not by string equality -- 127.0.0.2 is loopback too.
    QVERIFY(endpointUrlIsLocal(QString::fromLatin1(kLocalUrl)));
    QVERIFY(endpointUrlIsLocal(QStringLiteral("http://localhost:8188")));
    QVERIFY(endpointUrlIsLocal(QStringLiteral("http://127.0.0.2:8188")));
    QVERIFY(!endpointUrlIsLocal(QString::fromLatin1(kNodeUrl)));
}

void TestEndpointRegistry::defaultsHoldOnlyTheLocalMaster()
{
    const EndpointRegistry registry = EndpointRegistry::defaults(QString::fromLatin1(kLocalUrl));
    QCOMPARE(registry.count(), 1);
    QCOMPARE(registry.local().id, EndpointRegistry::localId());
    QVERIFY(registry.local().isLocal());
    // The master is NOT gated. Gating it would mean a fresh install could render nothing at all.
    QVERIFY(!registry.local().isGated());
}

void TestEndpointRegistry::aStoredListRoundTrips()
{
    QTemporaryDir dir;
    QVERIFY(dir.isValid());
    QScopedPointer<QSettings> settings(scratch(dir));

    EndpointRegistry registry = EndpointRegistry::defaults(QString::fromLatin1(kLocalUrl));
    Endpoint node;
    node.label = QStringLiteral("SpellNode");
    node.baseUrl = QString::fromLatin1(kNodeUrl);
    QString reason;
    QVERIFY2(registry.upsert(node, &reason), qPrintable(reason));
    QVERIFY(registry.allowFamily(registry.entries().at(1).id, QStringLiteral("sdxl")));
    registry.save(*settings);

    const EndpointRegistry reloaded =
        EndpointRegistry::load(*settings, QString::fromLatin1(kLocalUrl));
    QCOMPARE(reloaded.count(), 2);
    QCOMPARE(reloaded.entries().at(0).id, EndpointRegistry::localId());
    QCOMPARE(reloaded.entries().at(1).label, QStringLiteral("SpellNode"));
    QCOMPARE(reloaded.entries().at(1).baseUrl, QString::fromLatin1(kNodeUrl));
    QCOMPARE(reloaded.entries().at(1).familiesAllowed, QStringList{QStringLiteral("sdxl")});
    QVERIFY(reloaded.entries().at(1).isGated());
}

void TestEndpointRegistry::theLocalEntryCannotBeRemoved()
{
    EndpointRegistry registry = EndpointRegistry::defaults(QString::fromLatin1(kLocalUrl));
    Endpoint node;
    node.label = QStringLiteral("SpellNode");
    node.baseUrl = QString::fromLatin1(kNodeUrl);
    QVERIFY(registry.upsert(node));
    const QString nodeId = registry.entries().at(1).id;

    QString reason;
    QVERIFY(!registry.remove(EndpointRegistry::localId(), &reason));
    QVERIFY(!reason.isEmpty());
    QCOMPARE(registry.count(), 2);

    QVERIFY(registry.remove(nodeId));
    QCOMPARE(registry.count(), 1);
    QCOMPARE(registry.local().id, EndpointRegistry::localId());
}

void TestEndpointRegistry::theLocalEntryCannotBeReAddressedFromTheList()
{
    // The local address is the resolver's answer. A stored copy that outlives it is the recorded
    // 2026-07-17 shape: QSettings still named the D:\ rollback tree while :8188 was served from
    // somewhere else, and the Runtime page reported the wrong install and aimed its actions at it.
    EndpointRegistry registry = EndpointRegistry::defaults(QString::fromLatin1(kLocalUrl));
    Endpoint moved = registry.local();
    moved.baseUrl = QString::fromLatin1(kNodeUrl);
    QString reason;
    QVERIFY(!registry.upsert(moved, &reason));
    QVERIFY(!reason.isEmpty());
    QCOMPARE(registry.local().baseUrl, QString::fromLatin1(kLocalUrl));

    // Relabelling it is allowed; that is the user's.
    Endpoint relabelled = registry.local();
    relabelled.label = QStringLiteral("Workstation");
    QVERIFY2(registry.upsert(relabelled, &reason), qPrintable(reason));
    QCOMPARE(registry.local().label, QStringLiteral("Workstation"));
}

void TestEndpointRegistry::aMalformedStoredValueYieldsTheDefaultRegistry()
{
    QTemporaryDir dir;
    QVERIFY(dir.isValid());
    QScopedPointer<QSettings> settings(scratch(dir));

    for (const QString &damaged : {QStringLiteral("{not json"),
                                   QStringLiteral("{\"id\": \"local\"}"),
                                   QStringLiteral("\"\""),
                                   QStringLiteral("17")})
    {
        settings->setValue(EndpointRegistry::settingsKey(), damaged);
        const EndpointRegistry registry =
            EndpointRegistry::load(*settings, QString::fromLatin1(kLocalUrl));
        QVERIFY2(registry.count() == 1,
                 qPrintable(QStringLiteral("stored %1 gave %2 entries")
                                .arg(damaged)
                                .arg(registry.count())));
        QCOMPARE(registry.local().id, EndpointRegistry::localId());
        QCOMPARE(registry.local().baseUrl, QString::fromLatin1(kLocalUrl));
    }

    // An array whose members are junk keeps the master and drops only the junk.
    settings->setValue(EndpointRegistry::settingsKey(),
                       QStringLiteral("[3, \"x\", {\"label\": \"nowhere\"}]"));
    const EndpointRegistry registry =
        EndpointRegistry::load(*settings, QString::fromLatin1(kLocalUrl));
    QCOMPARE(registry.count(), 1);
    QCOMPARE(registry.local().baseUrl, QString::fromLatin1(kLocalUrl));
}

void TestEndpointRegistry::anEmptyStoredArrayStillHasTheLocalMaster()
{
    const EndpointRegistry registry =
        EndpointRegistry::fromJson(QJsonArray(), QString::fromLatin1(kLocalUrl));
    QCOMPARE(registry.count(), 1);
    QCOMPARE(registry.local().id, EndpointRegistry::localId());
}

void TestEndpointRegistry::aDuplicateUrlIsRefusedWithAReason()
{
    // python/worker_queue keys its lanes on the endpoint URL, so two entries for one machine would
    // be two lanes and that box would be handed two concurrent jobs. Keying lanes on `id` would not
    // have fixed it -- two entries have two ids either way -- so the refusal lives where the
    // duplicate is created.
    EndpointRegistry registry = EndpointRegistry::defaults(QString::fromLatin1(kLocalUrl));
    Endpoint node;
    node.label = QStringLiteral("SpellNode");
    node.baseUrl = QString::fromLatin1(kNodeUrl);
    QVERIFY(registry.upsert(node));

    Endpoint again;
    again.label = QStringLiteral("SpellNode again");
    again.baseUrl = QStringLiteral("http://192.168.1.127:8188/");  // same machine, trailing slash
    QString reason;
    QVERIFY(!registry.upsert(again, &reason));
    QVERIFY(reason.contains(QStringLiteral("SpellNode")));
    QCOMPARE(registry.count(), 2);
}

void TestEndpointRegistry::familiesAreWrittenByTheAppAndOnlyUnticked()
{
    EndpointRegistry registry = EndpointRegistry::defaults(QString::fromLatin1(kLocalUrl));
    Endpoint node;
    node.label = QStringLiteral("SpellNode");
    node.baseUrl = QString::fromLatin1(kNodeUrl);
    // A family stated on the way IN must not survive: a checklist a user can fill in is a claim
    // about another machine that nothing measured.
    node.familiesAllowed = QStringList{QStringLiteral("wan")};
    QVERIFY(registry.upsert(node));
    const QString nodeId = registry.entries().at(1).id;
    QVERIFY(registry.entries().at(1).familiesAllowed.isEmpty());

    // Editing the entry cannot smuggle one in either.
    Endpoint edited = registry.entries().at(1);
    edited.label = QStringLiteral("SpellNode (3090 Ti)");
    edited.familiesAllowed = QStringList{QStringLiteral("ltx")};
    QVERIFY(registry.upsert(edited));
    QVERIFY(registry.entries().at(1).familiesAllowed.isEmpty());

    // Only a proven render writes one, and the user may take it away again.
    QVERIFY(registry.allowFamily(nodeId, QStringLiteral("SDXL")));
    QCOMPARE(registry.entries().at(1).familiesAllowed, QStringList{QStringLiteral("sdxl")});
    QVERIFY(!registry.allowFamily(nodeId, QStringLiteral("sdxl")));  // idempotent
    QVERIFY(registry.disallowFamily(nodeId, QStringLiteral("sdxl")));
    QVERIFY(registry.entries().at(1).familiesAllowed.isEmpty());
    QVERIFY(!registry.disallowFamily(nodeId, QStringLiteral("sdxl")));
}

QTEST_MAIN(TestEndpointRegistry)
#include "test_endpoint_registry.moc"
