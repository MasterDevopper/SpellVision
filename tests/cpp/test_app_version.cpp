// "Is an update available" is a numeric comparison of two dotted strings. Get it wrong one way
// and every launch reports a phantom update forever; the other way and no update is ever seen.
// Pure function, table-driven, plus the one fact main() must establish: the app knows its version.

#include <QtTest>

#include <QCoreApplication>

#include "shell/AppVersion.h"

using spellvision::shell::appVersion;
using spellvision::shell::compareVersions;

class AppVersionTest : public QObject
{
    Q_OBJECT

private slots:
    void theBuildDeclaresAVersion()
    {
        // CMake project(VERSION) -> SPELLVISION_VERSION -> here. "0.0.0" is the fallback that
        // means the define was lost; a shipped build must never report it.
        QVERIFY(!appVersion().isEmpty());
        QVERIFY2(appVersion() != QStringLiteral("0.0.0"), "SPELLVISION_VERSION did not reach the binary");
        QVERIFY(appVersion().count(QLatin1Char('.')) >= 2);
    }

    void compare_data()
    {
        QTest::addColumn<QString>("a");
        QTest::addColumn<QString>("b");
        QTest::addColumn<int>("sign");
        QTest::newRow("equal") << "1.0.0" << "1.0.0" << 0;
        QTest::newRow("patch newer") << "1.0.0" << "1.0.1" << -1;
        QTest::newRow("minor newer") << "1.0.9" << "1.1.0" << -1;
        QTest::newRow("major newer") << "1.9.9" << "2.0.0" << -1;
        QTest::newRow("older") << "2.0.0" << "1.9.9" << 1;
        QTest::newRow("leading v") << "1.0.0" << "v1.0.1" << -1;
        QTest::newRow("both v") << "v1.2.0" << "V1.2.0" << 0;
        QTest::newRow("missing component") << "1.2" << "1.2.0" << 0;
        QTest::newRow("missing component newer") << "1.2" << "1.2.1" << -1;
        QTest::newRow("prerelease suffix ignored") << "1.0.0-beta.1" << "1.0.0" << 0;
        QTest::newRow("build suffix ignored") << "1.0.0+build.7" << "1.0.0" << 0;
        QTest::newRow("numeric not lexical") << "1.10.0" << "1.9.0" << 1;
        QTest::newRow("garbage is zero") << "banana" << "0.0.0" << 0;
        QTest::newRow("empty is zero") << "" << "1.0.0" << -1;
    }

    void compare()
    {
        QFETCH(QString, a);
        QFETCH(QString, b);
        QFETCH(int, sign);
        const int got = compareVersions(a, b);
        const int gotSign = got < 0 ? -1 : (got > 0 ? 1 : 0);
        QCOMPARE(gotSign, sign);
        // Antisymmetric, always.
        const int rev = compareVersions(b, a);
        QCOMPARE(rev < 0 ? -1 : (rev > 0 ? 1 : 0), -sign);
    }
};

QTEST_MAIN(AppVersionTest)
#include "test_app_version.moc"
