// The five stylesheets that asked for 'JetBrains Mono' fell back to a generic monospace on every
// machine because nothing registered a font. This proves the bundled faces register and that the
// app can find them from the build tree.
#include <QtTest>
#include <QApplication>
#include <QFontDatabase>

#include "style/SvFonts.h"

class SvFontsTest : public QObject
{
    Q_OBJECT
private slots:
    void bundled_families_register()
    {
        const QStringList families = spellvision::style::registerBundledFonts();
        QVERIFY2(families.contains(QStringLiteral("IBM Plex Sans")),
                 qPrintable(QStringLiteral("registered: ") + families.join(", ")
                            + QStringLiteral(" from ") + spellvision::style::fontsDirectory()));
        QVERIFY(families.contains(QStringLiteral("IBM Plex Mono")));
        QVERIFY(QFontDatabase::families().contains(QStringLiteral("IBM Plex Sans")));
    }

    void bundled_families_are_the_registered_ones()
    {
        spellvision::style::registerBundledFonts();
        const QStringList bundled = spellvision::style::bundledFamilies();
        QCOMPARE(bundled.size(), 2);
        QVERIFY(bundled.contains(QStringLiteral("IBM Plex Sans")));
        QVERIFY(bundled.contains(QStringLiteral("IBM Plex Mono")));
    }
};

QTEST_MAIN(SvFontsTest)
#include "test_sv_fonts.moc"
