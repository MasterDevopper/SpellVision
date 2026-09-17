// The Runtime page's list of machines, driven with a fake registry and fake probes.
//
// What it replaced was a QLabel holding three hardcoded lines and a health check that read another
// QLabel's TEXT (`runtimeStateLabel_->text().contains("healthy=yes")`). A label is a rendering of a
// fact; reword the caption and the machine silently becomes unhealthy.
//
// Two cases here cannot be proven by looking at a control, and they are the reason this file exists
// rather than a screenshot:
//
//   * an unticked family must not become ticked when the gesture is made. Asserting the checkbox is
//     disabled asserts an appearance -- and the last wave recorded UIA's IsEnabled property lying.
//     So the assertion is on the REGISTRY afterwards.
//   * the local entry cannot be removed. Again asserted as an outcome: the registry still holds it
//     and a reason was produced, not that a button looked greyed.

#include <QtTest>

#include <QCoreApplication>
#include <QHash>
#include <QLabel>
#include <QSettings>
#include <QTemporaryDir>

#include "shell/EndpointPanel.h"
#include "shell/EndpointProbe.h"
#include "shell/EndpointRegistry.h"

using spellvision::shell::Endpoint;
using spellvision::shell::EndpointPanel;
using spellvision::shell::EndpointRegistry;
using spellvision::shell::EndpointStatus;

namespace
{
const char *const kLocalUrl = "http://127.0.0.1:8188";
const char *const kNodeUrl = "http://192.168.1.127:8188";

EndpointStatus online(bool busy, int checkpoints)
{
    EndpointStatus status;
    status.probed = true;
    status.reachable = true;
    status.queueKnown = true;
    status.busy = busy;
    status.modelsKnown = true;
    status.comfyVersion = QStringLiteral("0.34.0");
    status.gpuName = QStringLiteral("NVIDIA GeForce RTX 3090 Ti");
    status.vramTotalGb = 23.9;
    status.vramFreeGb = 21.4;
    for (int index = 0; index < checkpoints; ++index)
        status.checkpoints.append(QStringLiteral("model_%1.safetensors").arg(index));
    return status;
}
} // namespace

class TestEndpointPanel : public QObject
{
    Q_OBJECT

private slots:
    void initTestCase();
    void rowsRenderWhatEachMachineAnswered();
    void anOfflineEndpointReadsOffline();
    void anUnlistedModelCountIsNotZero();
    void anUngatedFamilyCannotBeTicked();
    void aProvenFamilyCanBeUnticked();
    void theLocalEntryCannotBeRemoved();
    void theHonestyLineStays();
    void theFamilyListComesFromTheModelRegistry();

private:
    QTemporaryDir settingsDir_;
    EndpointRegistry twoMachines(QString *nodeId) const;
};

void TestEndpointPanel::initTestCase()
{
    // The panel persists through QSettings on save. Point the whole test at a scratch scope so a
    // run cannot disturb the developer's own endpoint list.
    QVERIFY(settingsDir_.isValid());
    QSettings::setDefaultFormat(QSettings::IniFormat);
    QSettings::setPath(QSettings::IniFormat, QSettings::UserScope, settingsDir_.path());
    QCoreApplication::setOrganizationName(QStringLiteral("DarkDuck"));
    QCoreApplication::setApplicationName(QStringLiteral("SpellVision"));
}

EndpointRegistry TestEndpointPanel::twoMachines(QString *nodeId) const
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

void TestEndpointPanel::rowsRenderWhatEachMachineAnswered()
{
    QString nodeId;
    EndpointPanel panel;
    QHash<QString, EndpointStatus> statuses;
    statuses.insert(EndpointRegistry::localId(), online(false, 41));
    const EndpointRegistry registry = twoMachines(&nodeId);
    statuses.insert(nodeId, online(true, 3));
    panel.setStatusResolver([&statuses](const QString &id) { return statuses.value(id); });
    panel.setRegistry(registry);

    QCOMPARE(panel.rowCount(), 2);
    QCOMPARE(panel.cellText(0, EndpointPanel::LabelColumn), QStringLiteral("This machine"));
    QCOMPARE(panel.cellText(0, EndpointPanel::UrlColumn), QString::fromLatin1(kLocalUrl));
    QCOMPARE(panel.cellText(0, EndpointPanel::StatusColumn), QStringLiteral("online"));
    QCOMPARE(panel.cellText(0, EndpointPanel::VersionColumn), QStringLiteral("0.34.0"));
    QCOMPARE(panel.cellText(0, EndpointPanel::ModelsColumn), QStringLiteral("41"));

    QCOMPARE(panel.cellText(1, EndpointPanel::LabelColumn), QStringLiteral("SpellNode"));
    // A machine that is mid-render is not the same as one that is idle, and it is not offline.
    QCOMPARE(panel.cellText(1, EndpointPanel::StatusColumn), QStringLiteral("rendering"));
    QVERIFY(panel.cellText(1, EndpointPanel::GpuColumn).contains(QStringLiteral("3090 Ti")));
    QCOMPARE(panel.cellText(1, EndpointPanel::FamiliesColumn), QStringLiteral("none yet"));
}

void TestEndpointPanel::anOfflineEndpointReadsOffline()
{
    QString nodeId;
    EndpointPanel panel;
    const EndpointRegistry registry = twoMachines(&nodeId);
    QHash<QString, EndpointStatus> statuses;
    statuses.insert(EndpointRegistry::localId(), online(false, 41));
    EndpointStatus down;
    down.probed = true;
    down.reachable = false;
    down.detail = QStringLiteral("Host not found");
    statuses.insert(nodeId, down);
    panel.setStatusResolver([&statuses](const QString &id) { return statuses.value(id); });
    panel.setRegistry(registry);

    QCOMPARE(panel.cellText(1, EndpointPanel::StatusColumn), QStringLiteral("offline"));

    // And a machine nothing has asked yet reads as that, never as offline and never as online.
    statuses.remove(nodeId);
    panel.refreshRows();
    QCOMPARE(panel.cellText(1, EndpointPanel::StatusColumn), QStringLiteral("not checked"));
}

void TestEndpointPanel::anUnlistedModelCountIsNotZero()
{
    // "Could not list" and "holds none" are opposite facts. A dead CIFS model share produces the
    // first; rendering it as 0 would read as a machine with an empty library, which is a claim.
    QString nodeId;
    EndpointPanel panel;
    const EndpointRegistry registry = twoMachines(&nodeId);
    EndpointStatus unlisted = online(false, 0);
    unlisted.modelsKnown = false;
    QHash<QString, EndpointStatus> statuses;
    statuses.insert(nodeId, unlisted);
    panel.setStatusResolver([&statuses](const QString &id) { return statuses.value(id); });
    panel.setRegistry(registry);
    QCOMPARE(panel.cellText(1, EndpointPanel::ModelsColumn), QStringLiteral("not listed"));

    EndpointStatus empty = online(false, 0);
    statuses.insert(nodeId, empty);
    panel.refreshRows();
    QCOMPARE(panel.cellText(1, EndpointPanel::ModelsColumn), QStringLiteral("0"));
}

void TestEndpointPanel::anUngatedFamilyCannotBeTicked()
{
    QString nodeId;
    EndpointPanel panel;
    panel.setRegistry(twoMachines(&nodeId));
    panel.selectRow(1);
    QCOMPARE(panel.selectedEndpointId(), nodeId);
    QVERIFY(!panel.familyIsTicked(QStringLiteral("sdxl")));

    // The gesture, made. The assertion is on what the registry says afterwards, not on how the
    // control looked.
    QVERIFY(!panel.setFamilyChecked(QStringLiteral("sdxl"), true));
    QVERIFY(!panel.lastRefusal().isEmpty());
    QVERIFY(!panel.familyIsTicked(QStringLiteral("sdxl")));
    QVERIFY(panel.registry().find(nodeId)->familiesAllowed.isEmpty());
    QCOMPARE(panel.cellText(1, EndpointPanel::FamiliesColumn), QStringLiteral("none yet"));
}

void TestEndpointPanel::aProvenFamilyCanBeUnticked()
{
    QString nodeId;
    EndpointPanel panel;
    panel.setRegistry(twoMachines(&nodeId));
    panel.selectRow(1);

    // Only a real render writes one.
    QVERIFY(panel.recordGateRender(nodeId, QStringLiteral("sdxl")));
    QVERIFY(panel.familyIsTicked(QStringLiteral("sdxl")));
    QCOMPARE(panel.cellText(1, EndpointPanel::FamiliesColumn), QStringLiteral("sdxl"));

    // The user may take it away again -- that direction is theirs.
    QVERIFY(panel.setFamilyChecked(QStringLiteral("sdxl"), false));
    QVERIFY(!panel.familyIsTicked(QStringLiteral("sdxl")));
}

void TestEndpointPanel::theLocalEntryCannotBeRemoved()
{
    QString nodeId;
    EndpointPanel panel;
    panel.setRegistry(twoMachines(&nodeId));

    panel.selectRow(0);
    QCOMPARE(panel.selectedEndpointId(), EndpointRegistry::localId());
    QVERIFY(!panel.removeSelected());
    QVERIFY(!panel.lastRefusal().isEmpty());
    QCOMPARE(panel.rowCount(), 2);
    QVERIFY(panel.registry().find(EndpointRegistry::localId()) != nullptr);

    // A remote one goes.
    panel.selectRow(1);
    QVERIFY2(panel.removeSelected(), qPrintable(panel.lastRefusal()));
    QCOMPARE(panel.rowCount(), 1);
}

void TestEndpointPanel::theHonestyLineStays()
{
    EndpointPanel panel;
    QString text;
    for (QLabel *label : panel.findChildren<QLabel *>())
        text += label->text();
    // Two machines are two machines. 32 GB and 24 GB are never 56.
    QVERIFY(text.contains(QStringLiteral("does not pool VRAM")));
    QVERIFY(text.contains(QStringLiteral("Whole jobs only")));

    // And the pack that used to be offered here is gone: it falls back to the master when no worker
    // answers, which is the opposite of what this page promises.
    QVERIFY(!text.contains(QStringLiteral("Distributed")));
}

void TestEndpointPanel::theFamilyListComesFromTheModelRegistry()
{
    // Not a list written in the panel. A hand-kept one goes stale the first time a family lands,
    // and a checklist missing a family is a machine that can never be cleared for it.
    const QStringList families = EndpointPanel::knownFamilies();
    QVERIFY(families.contains(QStringLiteral("sdxl")));
    QVERIFY(families.contains(QStringLiteral("wan")));
    QVERIFY(families.contains(QStringLiteral("ltx")));
    QVERIFY(!families.contains(QStringLiteral("unknown")));

    QString nodeId;
    EndpointPanel panel;
    panel.setRegistry(twoMachines(&nodeId));
    panel.selectRow(1);
    QCOMPARE(panel.familiesShown(), families);
}

QTEST_MAIN(TestEndpointPanel)
#include "test_endpoint_panel.moc"
