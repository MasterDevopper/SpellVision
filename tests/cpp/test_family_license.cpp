// The licence answer the badge and the generate warn share (Doc 28 section 2: "Non-commercial
// surfaced" -- "Hunyuan and Anima show a badge; commercial-use setting on -> soft warn on generate
// (not a hard block)").
//
// The defect this pins. qt_ui/assets/FamilyLicense.h used to answer with
//
//     return !(hay.contains("anima") || hay.contains("hunyuan"));
//
// -- two family names hardcoded in C++, matched as SUBSTRINGS, against either the family key OR the
// model PATH. That is wrong in both directions and both directions were live:
//
//   * it badged animagineXL / animatediff / an "animation_v3.safetensors" as Non-commercial and
//     raised a warning dialog on models that carry neither restriction. python/model_registry.py's
//     anima spec says in its own comment that its aliases are deliberately narrow because "a bare
//     'anima' substring-collides with animagine/animatediff/animation decoys" -- the C++ copy had
//     exactly the collision the Python side had already designed around;
//   * it answered "commercial use is fine" for any non-commercial family the registry gained after
//     it was written, silently, because an absent badge is indistinguishable from an unneeded one.
//
// So this file never names a family. Every case is derived from the generated table, which
// tests/test_family_license_surfaced.py re-renders from the registry on every pytest run. The decoy
// strings below ARE spelled out, because they are the corpus the old predicate failed on, not a
// list of families.

#include <QtTest>

#include <QSet>
#include <QString>
#include <QStringList>

#include "assets/FamilyLicense.h"
#include "assets/FamilyLicenseTable.h"

using namespace spellvision::assets;
using spellvision::assets::generated::kFamilyLicenseTable;

namespace
{

QStringList nonCommercialKeys()
{
    QStringList keys;
    for (const auto &row : kFamilyLicenseTable)
    {
        if (!row.commercialUse)
            keys << QString::fromUtf8(row.key);
    }
    return keys;
}

QStringList aliasesOf(const char *packed)
{
    const QString s = QString::fromUtf8(packed);
    return s.isEmpty() ? QStringList() : s.split(QLatin1Char('|'), Qt::SkipEmptyParts);
}

} // namespace

class FamilyLicenseTest : public QObject
{
    Q_OBJECT

private slots:
    void theTableReachedTheBinary()
    {
        // An empty table answers "commercially licensed" for every family in the product, and looks
        // exactly like a product with no non-commercial models in it. Doc 50 rule 4: the failure has
        // to be louder than the success is quiet.
        QVERIFY2(familyLicenseRowCount() > 0, "the generated licence table is empty");
        QVERIFY2(!nonCommercialKeys().isEmpty(),
                 "no family in the table is non-commercial -- the registry's licence fields did not "
                 "survive generation, and every badge would be silently absent");
    }

    void everyNonCommercialFamilyBadgesAndExplains()
    {
        for (const QString &key : nonCommercialKeys())
        {
            const FamilyLicense license = familyLicense(key);
            QVERIFY2(license.matched, qPrintable(key + ": not resolvable by its own key"));
            QVERIFY2(!license.commercialUse, qPrintable(key + ": lost its non-commercial answer"));
            QVERIFY2(!familyLicenseBadgeText(key).isEmpty(), qPrintable(key + ": no badge text"));
            // A badge the user cannot act on is a label. The registry carries the reason; it has to
            // reach the surface with the badge.
            QVERIFY2(!license.note.trimmed().isEmpty(),
                     qPrintable(key + ": badged non-commercial with no licence note to show"));
        }
    }

    void everyAliasAnswersLikeItsFamily()
    {
        // resolve_model_capabilities resolves by key then by alias. The Qt copy has to agree, or a
        // model whose classified family came back as an alias would badge differently from the same
        // model classified to the key.
        for (const auto &row : kFamilyLicenseTable)
        {
            const QString key = QString::fromUtf8(row.key);
            for (const QString &alias : aliasesOf(row.aliases))
            {
                const FamilyLicense viaAlias = familyLicense(alias);
                QVERIFY2(viaAlias.matched, qPrintable(alias + ": alias did not resolve"));
                QCOMPARE(viaAlias.commercialUse, row.commercialUse);
                QCOMPARE(familyLicenseBadgeText(alias), familyLicenseBadgeText(key));
            }
        }
    }

    void lookupIsCaseAndWhitespaceTolerant()
    {
        // The studios read their family out of a project.json a user can edit by hand.
        for (const QString &key : nonCommercialKeys())
        {
            QVERIFY(!familyLicenseBadgeText(key.toUpper()).isEmpty());
            QVERIFY(!familyLicenseBadgeText(QStringLiteral("  %1  ").arg(key)).isEmpty());
        }
    }

    void decoysThatMerelyContainAFamilyNameAreNotBadged_data()
    {
        QTest::addColumn<QString>("needle");
        // The corpus the substring predicate failed on. Each of these contains a non-commercial
        // family name as a substring and is not that family.
        QTest::newRow("animagine") << "animagine";
        QTest::newRow("animagineXL_v31") << "animagineXL_v31";
        QTest::newRow("animatediff") << "animatediff";
        QTest::newRow("animation") << "animation";
        QTest::newRow("a model path") << "D:/AI_ASSETS/models/checkpoints/animagineXL_v31.safetensors";
        QTest::newRow("hunyuan as a prefix of a word") << "hunyuandit";
    }

    void decoysThatMerelyContainAFamilyNameAreNotBadged()
    {
        QFETCH(QString, needle);
        const FamilyLicense license = familyLicense(needle);
        QVERIFY2(!license.matched,
                 qPrintable(needle + ": matched a family it only shares letters with"));
        QVERIFY2(license.commercialUse,
                 qPrintable(needle + ": badged non-commercial by substring, the exact defect this "
                                     "table replaced"));
        QVERIFY(familyLicenseBadgeText(needle).isEmpty());
    }

    void anUnknownFamilyTakesTheRegistrysAnswerNotOneWrittenHere()
    {
        // The C++ side carries no default of its own: an unrecognised family falls back to the
        // registry's own "unknown" row, the way resolve_model_capabilities does. Asserting the
        // fallback ROW rather than a literal true is the point -- if the registry ever makes
        // "unknown" non-commercial, this keeps agreeing with it instead of contradicting it.
        const FamilyLicense fallback = familyLicense(QStringLiteral("a family that does not exist"));
        QVERIFY(!fallback.matched);
        const FamilyLicense unknownRow = familyLicense(
            QString::fromUtf8(spellvision::assets::generated::kFamilyLicenseFallbackKey));
        QVERIFY2(unknownRow.matched, "the generated table lost its fallback row");
        QCOMPARE(fallback.commercialUse, unknownRow.commercialUse);
        QCOMPARE(fallback.key, unknownRow.key);
    }

    void theGateNeverBlocks()
    {
        // Doc 28: soft warn, never a hard block. LicenseGate has two states and neither is a block,
        // so this asserts the reachable behaviour rather than the type: over every family in the
        // table, under both settings, the answer is one of exactly two values -- and the only one
        // that stops a render is the user's own answer to the dialog, which lives in MainWindow.
        for (const auto &row : kFamilyLicenseTable)
        {
            const QString key = QString::fromUtf8(row.key);
            for (bool declared : {false, true})
            {
                const LicenseGate gate = licenseGateFor(key, declared);
                QVERIFY(gate == LicenseGate::Proceed || gate == LicenseGate::WarnThenProceed);
            }
            // Setting off -> never a warn, whatever the licence says. The setting is the user's
            // declaration, and a warn that ignores it is a warn nobody can turn off.
            QCOMPARE(licenseGateFor(key, false), LicenseGate::Proceed);
            // Setting on -> warn exactly when the registry says non-commercial. Not "sometimes",
            // not "for the two families someone remembered".
            QCOMPARE(licenseGateFor(key, true),
                     row.commercialUse ? LicenseGate::Proceed : LicenseGate::WarnThenProceed);
        }
    }

    void anEmptyFamilyNeverWarns()
    {
        // A page that has not resolved a family yet must not raise a licence dialog on every
        // generate. Empty is "no answer", and no answer is not "non-commercial".
        QCOMPARE(licenseGateFor(QString(), true), LicenseGate::Proceed);
        QCOMPARE(licenseGateFor(QStringLiteral("   "), true), LicenseGate::Proceed);
        QVERIFY(familyLicenseBadgeText(QString()).isEmpty());
    }
};

QTEST_GUILESS_MAIN(FamilyLicenseTest)
#include "test_family_license.moc"
