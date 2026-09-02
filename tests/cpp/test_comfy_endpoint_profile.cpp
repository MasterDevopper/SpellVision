// The app could be pointed at another machine's PORT, and never at another machine.
//
// `RuntimeProfile::comfyHost` was a hardcoded 127.0.0.1 that read no environment and no setting,
// while `comfyPort` three lines below it read SPELLVISION_COMFY_PORT. Meanwhile the worker's
// python/comfy_endpoint.py honours COMFY_API_URL and drives a ComfyUI on another host correctly --
// verified end to end against a real second box on 2026-09-01, six checks of six, including a
// 1.28 MB render fetched back over /view.
//
// So the two halves could disagree silently, which is worse than either being wrong alone:
// generation running on the remote node while every Qt probe reported the health, queue depth and
// readiness of a local ComfyUI that was serving nothing. Both would look right.
//
// The C++ resolver is therefore a deliberate copy of the Python precedence chain, and there are two
// tests keeping it one: tests/test_comfy_endpoint_is_one_rule_across_languages.py asserts the C++
// SOURCE names the same variables in the same order, and this file asserts the resolved BEHAVIOUR.
// The Python test cannot run this code and this file cannot import that tuple, so neither is
// redundant -- a source check would pass on a resolver that read the right names and did the wrong
// thing with them.
//
// Environment rather than settings, matching the worker: a per-machine endpoint belongs where the
// launcher can set it, and QSettings would be a second source of truth for one value.

#include <QtTest>

#include "shell/RuntimeProfile.h"

using spellvision::shell::RuntimeProfile;

namespace
{

// Every endpoint variable the resolver reads, cleared, so a leftover value in the developer's own
// environment cannot make a case pass. The bug being tested is precisely "the environment is not
// consulted", so a test that inherited a set variable could report success while reading nothing.
void clearEndpointEnvironment()
{
    for (const char *name : {"COMFY_API_URL", "SPELLVISION_COMFY_URL", "SPELLVISION_COMFY_ENDPOINT",
                             "SPELLVISION_COMFY_HOST", "SPELLVISION_COMFY_PORT"})
        qunsetenv(name);
}

RuntimeProfile profileWith(const char *name, const QByteArray &value)
{
    clearEndpointEnvironment();
    if (name)
        qputenv(name, value);
    return RuntimeProfile::load(QDir::currentPath());
}

}  // namespace

class ComfyEndpointProfileTest : public QObject
{
    Q_OBJECT

private slots:
    void cleanup() { clearEndpointEnvironment(); }

    // --- the default is unchanged ---------------------------------------------------------

    void defaultsToLoopback()
    {
        const RuntimeProfile profile = profileWith(nullptr, {});
        QCOMPARE(profile.comfyHost, QStringLiteral("127.0.0.1"));
        QCOMPARE(profile.comfyPort, quint16(8188));
        QVERIFY(profile.comfyEndpointIsLocal());
    }

    // --- a URL moves the host, which is the regression ------------------------------------

    void urlMovesHostAndPort()
    {
        const RuntimeProfile profile = profileWith("COMFY_API_URL", "http://192.168.1.127:8188");
        QCOMPARE(profile.comfyHost, QStringLiteral("192.168.1.127"));
        QCOMPARE(profile.comfyPort, quint16(8188));
        QVERIFY(!profile.comfyEndpointIsLocal());
    }

    void urlWithANonDefaultPortCarriesIt()
    {
        const RuntimeProfile profile = profileWith("COMFY_API_URL", "http://spellnode:9001");
        QCOMPARE(profile.comfyHost, QStringLiteral("spellnode"));
        QCOMPARE(profile.comfyPort, quint16(9001));
    }

    void aBareHostAndPortIsAccepted()
    {
        // `COMFY_API_URL=otherbox:8188` is the obvious thing to type, and QUrl parses it as scheme
        // "otherbox" with an empty host. The Python resolver makes the same accommodation, so a
        // value that works for the worker must not be silently ignored here.
        const RuntimeProfile profile = profileWith("COMFY_API_URL", "otherbox:8188");
        QCOMPARE(profile.comfyHost, QStringLiteral("otherbox"));
        QCOMPARE(profile.comfyPort, quint16(8188));
    }

    void aTrailingSlashIsTolerated()
    {
        const RuntimeProfile profile = profileWith("COMFY_API_URL", "http://192.168.1.127:8188/");
        QCOMPARE(profile.comfyHost, QStringLiteral("192.168.1.127"));
    }

    // --- every historical name still works ------------------------------------------------

    void theOlderUrlNamesAreHonoured_data()
    {
        QTest::addColumn<QByteArray>("variable");
        QTest::newRow("SPELLVISION_COMFY_URL") << QByteArray("SPELLVISION_COMFY_URL");
        QTest::newRow("SPELLVISION_COMFY_ENDPOINT") << QByteArray("SPELLVISION_COMFY_ENDPOINT");
    }

    void theOlderUrlNamesAreHonoured()
    {
        QFETCH(QByteArray, variable);
        const RuntimeProfile profile = profileWith(variable.constData(), "http://10.0.0.5:8188");
        QCOMPARE(profile.comfyHost, QStringLiteral("10.0.0.5"));
        QVERIFY(!profile.comfyEndpointIsLocal());
    }

    void theHostVariableAloneStillWorks()
    {
        // The step whose ABSENCE was the bug: the port was read, the host was not.
        const RuntimeProfile profile = profileWith("SPELLVISION_COMFY_HOST", "192.168.1.127");
        QCOMPARE(profile.comfyHost, QStringLiteral("192.168.1.127"));
        QCOMPARE(profile.comfyPort, quint16(8188));
    }

    void theHostAndPortPairCombine()
    {
        clearEndpointEnvironment();
        qputenv("SPELLVISION_COMFY_HOST", "192.168.1.127");
        qputenv("SPELLVISION_COMFY_PORT", "9188");
        const RuntimeProfile profile = RuntimeProfile::load(QDir::currentPath());
        QCOMPARE(profile.comfyHost, QStringLiteral("192.168.1.127"));
        QCOMPARE(profile.comfyPort, quint16(9188));
    }

    // --- order is content -------------------------------------------------------------------

    void aUrlBeatsTheHostPortPair()
    {
        // Matching the Python chain, where a URL match returns immediately. If the pair could
        // override the URL's port, the two resolvers would pick different endpoints from the same
        // environment -- the divergence this whole change exists to remove.
        clearEndpointEnvironment();
        qputenv("COMFY_API_URL", "http://192.168.1.127:8188");
        qputenv("SPELLVISION_COMFY_HOST", "127.0.0.1");
        qputenv("SPELLVISION_COMFY_PORT", "9999");
        const RuntimeProfile profile = RuntimeProfile::load(QDir::currentPath());
        QCOMPARE(profile.comfyHost, QStringLiteral("192.168.1.127"));
        QCOMPARE(profile.comfyPort, quint16(8188));
    }

    void comfyApiUrlBeatsTheOlderNames()
    {
        clearEndpointEnvironment();
        qputenv("COMFY_API_URL", "http://first:8188");
        qputenv("SPELLVISION_COMFY_URL", "http://second:8188");
        qputenv("SPELLVISION_COMFY_ENDPOINT", "http://third:8188");
        const RuntimeProfile profile = RuntimeProfile::load(QDir::currentPath());
        QCOMPARE(profile.comfyHost, QStringLiteral("first"));
    }

    // --- the locality predicate ---------------------------------------------------------------

    void loopbackSpellingsAreAllLocal_data()
    {
        QTest::addColumn<QByteArray>("host");
        QTest::newRow("localhost") << QByteArray("localhost");
        QTest::newRow("127.0.0.1") << QByteArray("127.0.0.1");
        QTest::newRow("127.0.0.2") << QByteArray("127.0.0.2");
        QTest::newRow("0.0.0.0") << QByteArray("0.0.0.0");
    }

    void loopbackSpellingsAreAllLocal()
    {
        QFETCH(QByteArray, host);
        const RuntimeProfile profile = profileWith("SPELLVISION_COMFY_HOST", host);
        QVERIFY2(profile.comfyEndpointIsLocal(), host.constData());
    }

    void aLanAddressIsNotLocal()
    {
        // The one that matters: this is where the output directory, the process and custom_nodes/
        // stop being on this machine.
        const RuntimeProfile profile = profileWith("SPELLVISION_COMFY_HOST", "192.168.1.127");
        QVERIFY(!profile.comfyEndpointIsLocal());
    }

    void aGarbageUrlDoesNotSilentlyRelocateTheEndpoint()
    {
        // An unparseable value must leave the default standing rather than produce an empty host,
        // which would read as local and send install commands at nothing.
        const RuntimeProfile profile = profileWith("COMFY_API_URL", "http://:::::");
        QVERIFY(!profile.comfyHost.isEmpty());
        QVERIFY(profile.comfyEndpointIsLocal());
    }
};

QTEST_MAIN(ComfyEndpointProfileTest)
#include "test_comfy_endpoint_profile.moc"
