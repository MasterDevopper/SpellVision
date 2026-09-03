// The upscale group's intent-level tier, and the two rules it has to keep.
//
// 1. **One source of truth for "is an upscale requested".** There used to be a checkbox AND a
//    method list, so "off" was sayable twice, and the request builder read whichever it reached.
//    The tier is now the switch and `enabled()` is derived from it.
//
// 2. **Advanced reveals in place, and reveals nothing that changes the request.** Simple shows
//    Off / 2x / 4x; Advanced adds the method, exact scale and model *below it, in the same card*.
//    Switching between the two must not alter what would be generated -- the defect this project
//    keeps finding in its own disclosure work is hidden output-changing state, not a moved widget.
//
// The mapping half is pure and tested without a widget, because that is where the product decision
// lives: an intent-level "make it bigger" means the upscale MODEL, which measures x8.46 the
// Laplacian variance of a resample at identical dimensions (tests/test_upscale_render_gate.py).

#include <QtTest>

#include <QComboBox>
#include <QDoubleSpinBox>
#include <QWidget>

#include "generation/UpscaleController.h"

using spellvision::generation::UpscaleController;
using Tier = UpscaleController::Tier;

class UpscaleControllerTest : public QObject
{
    Q_OBJECT

private slots:
    void aTierMeansTheModelUpscale();
    void offIsTheOnlyWayToSayOff();
    void settingsRoundTripThroughTheTierName();
    void aResampleOrAnOddScaleIsCustom();
    void choosingATierWritesTheRawControls();
    void editingARawControlRenamesTheTier();
    void theTierSurvivesTheDisclosureFlip();
    void simpleStillOffersTheControl();
};

void UpscaleControllerTest::aTierMeansTheModelUpscale()
{
    const auto x2 = UpscaleController::settingsForTier(Tier::X2);
    QVERIFY(x2.enabled);
    QCOMPARE(x2.method, QStringLiteral("model"));
    QCOMPARE(x2.scale, 2.0);

    const auto x4 = UpscaleController::settingsForTier(Tier::X4);
    QCOMPARE(x4.method, QStringLiteral("model"));
    QCOMPARE(x4.scale, 4.0);
}

void UpscaleControllerTest::offIsTheOnlyWayToSayOff()
{
    QVERIFY(!UpscaleController::settingsForTier(Tier::Off).enabled);
    QCOMPARE(UpscaleController::tierForSettings(false, QStringLiteral("model"), 2.0), Tier::Off);
    // Even a fully-specified model upscale is Off when the switch says so: there is one switch.
    QCOMPARE(UpscaleController::tierForSettings(false, QStringLiteral("model"), 4.0), Tier::Off);
}

void UpscaleControllerTest::settingsRoundTripThroughTheTierName()
{
    for (const Tier tier : {Tier::X2, Tier::X4})
    {
        const auto settings = UpscaleController::settingsForTier(tier);
        QCOMPARE(UpscaleController::tierForSettings(settings.enabled, settings.method, settings.scale), tier);
    }
}

void UpscaleControllerTest::aResampleOrAnOddScaleIsCustom()
{
    QCOMPARE(UpscaleController::tierForSettings(true, QStringLiteral("lanczos"), 2.0), Tier::Custom);
    QCOMPARE(UpscaleController::tierForSettings(true, QStringLiteral("model"), 3.0), Tier::Custom);
    QVERIFY2(UpscaleController::tierLabel(Tier::Custom) == QStringLiteral("Custom"),
             "a state the tiers do not name has to be named something, not silently shown as 2x");
}

void UpscaleControllerTest::choosingATierWritesTheRawControls()
{
    QWidget parent;
    UpscaleController controller;
    controller.create(&parent);

    QComboBox *tierCombo = controller.row()->findChild<QComboBox *>();
    QVERIFY(tierCombo);
    tierCombo->setCurrentIndex(tierCombo->findData(static_cast<int>(Tier::X4)));

    QCOMPARE(controller.tier(), Tier::X4);
    QVERIFY(controller.enabled());
    QCOMPARE(controller.method(), QStringLiteral("model"));
    QCOMPARE(controller.scale(), 4.0);
}

void UpscaleControllerTest::editingARawControlRenamesTheTier()
{
    QWidget parent;
    UpscaleController controller;
    controller.create(&parent);
    controller.setAdvanced(true);

    QComboBox *tierCombo = controller.row()->findChild<QComboBox *>();
    tierCombo->setCurrentIndex(tierCombo->findData(static_cast<int>(Tier::X2)));
    QCOMPARE(controller.tier(), Tier::X2);

    auto *scale = controller.row()->findChild<QDoubleSpinBox *>();
    QVERIFY(scale);
    scale->setValue(3.0);

    QCOMPARE(controller.tier(), Tier::Custom);
    QCOMPARE(controller.scale(), 3.0);
    QVERIFY2(controller.enabled(), "editing a knob must not switch the feature off");
}

void UpscaleControllerTest::theTierSurvivesTheDisclosureFlip()
{
    QWidget parent;
    UpscaleController controller;
    controller.create(&parent);
    controller.setAdvanced(true);

    QComboBox *tierCombo = controller.row()->findChild<QComboBox *>();
    tierCombo->setCurrentIndex(tierCombo->findData(static_cast<int>(Tier::X4)));
    auto *scale = controller.row()->findChild<QDoubleSpinBox *>();
    scale->setValue(2.5);

    const bool wasEnabled = controller.enabled();
    const QString wasMethod = controller.method();
    const double wasScale = controller.scale();
    const QString wasModel = controller.model();

    controller.setAdvanced(false);

    QCOMPARE(controller.enabled(), wasEnabled);
    QCOMPARE(controller.method(), wasMethod);
    QCOMPARE(controller.scale(), wasScale);
    QCOMPARE(controller.model(), wasModel);
}

void UpscaleControllerTest::simpleStillOffersTheControl()
{
    QWidget parent;
    UpscaleController controller;
    controller.create(&parent);
    parent.show();

    controller.setAdvanced(false);
    QVERIFY2(controller.row()->isVisible(),
             "the whole group used to be Advanced-only, so Simple offered no upscale at all");

    QComboBox *tierCombo = controller.row()->findChild<QComboBox *>();
    QVERIFY2(tierCombo && tierCombo->isVisible(), "the intent-level control belongs in Simple");

    // isVisible(), not !isHidden(). The two differ exactly here: setAdvanced hides the GROUP, and
    // isHidden() is a property of the widget itself -- a child of a hidden parent is not visible
    // and is not "hidden". The first version of this assertion used isHidden() and failed on a
    // control the user genuinely could not see.
    auto *scale = controller.row()->findChild<QDoubleSpinBox *>();
    QVERIFY2(scale && !scale->isVisible(), "the raw knobs are what Advanced reveals");

    controller.setAdvanced(true);
    QVERIFY2(scale->isVisible(), "and Advanced reveals them in the same card, not elsewhere");
}

QTEST_MAIN(UpscaleControllerTest)
#include "test_upscale_controller.moc"
