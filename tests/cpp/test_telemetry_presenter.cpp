// The bottom bar says what is true of the page you are looking at.
//
// "Model:" showed the last-run model on 2026-09-02. The cause was not two writers (there is one,
// and it already reads the current page) but a writer that was never CALLED on a page change:
// syncBottomTelemetry hung off submits and queue movement, and the queue route is change-gated, so
// an idle app kept whatever the bar held when the queue last moved.
//
// The page NAME did have three writers -- modeId.toUpper(), pageContextForMode(), and a
// setBottomPageContext setter -- which is why it read "T2I" or "Text to Image" depending on
// whether the queue had moved since the mode switch.
//
// These are pure functions, so this needs no window.

#include <QtTest>

#include "shell/ShellNavigationController.h"
#include "shell/TelemetryPresenter.h"

using spellvision::shell::ShellNavigationController;
using spellvision::shell::TelemetryChip;
using spellvision::shell::TelemetryPresenter;

class TelemetryPresenterTest : public QObject
{
    Q_OBJECT

private slots:
    void thePageNameHasOneSource();
    void aChosenAssetShowsItsBasename();
    void aPageWithASlotAndNoChoiceSaysSoInWords();
    void aPageWithNoSlotShowsNoChip();
    void everyRailModeGetsAnAnswer();
};

void TelemetryPresenterTest::thePageNameHasOneSource()
{
    // Same answer as the title-bar breadcrumb, for every mode -- not a second spelling of it.
    for (const auto &spec : ShellNavigationController::railButtonSpecs())
    {
        QCOMPARE(TelemetryPresenter::pageLabelText(spec.modeId),
                 ShellNavigationController::pageContextForMode(spec.modeId));
    }
}

void TelemetryPresenterTest::aChosenAssetShowsItsBasename()
{
    const QString path = QStringLiteral("D:/AI_ASSETS/models/checkpoints/juggernautXL_v9.safetensors");
    const TelemetryChip chip = TelemetryPresenter::assetChip(QStringLiteral("Model"), true, path);
    QVERIFY(chip.visible);
    QCOMPARE(chip.text, QStringLiteral("Model: juggernautXL_v9"));
    // The bar is ~160px wide; the path it stands for is in the tooltip.
    QCOMPARE(chip.toolTip, path);
}

void TelemetryPresenterTest::aPageWithASlotAndNoChoiceSaysSoInWords()
{
    const TelemetryChip chip = TelemetryPresenter::assetChip(QStringLiteral("Model"), true, QString());
    QVERIFY(chip.visible);
    QCOMPARE(chip.text, QStringLiteral("Model: not selected"));
    QVERIFY2(!chip.text.contains(QStringLiteral("none")),
             "\"none\" is the string a page with no model slot used to show -- the two states must read differently");
}

void TelemetryPresenterTest::aPageWithNoSlotShowsNoChip()
{
    // Flows, History, Runtime, Settings. "Model: none" there is a false statement about the user's
    // choices, and it is indistinguishable from a generation page where nothing is chosen.
    const TelemetryChip chip = TelemetryPresenter::assetChip(QStringLiteral("Model"), false, QString());
    QVERIFY(!chip.visible);
    QVERIFY(chip.text.isEmpty());
}

void TelemetryPresenterTest::everyRailModeGetsAnAnswer()
{
    // Derived from the rail, so a mode added later is covered without editing this test.
    const auto specs = ShellNavigationController::railButtonSpecs();
    QVERIFY(!specs.isEmpty());
    for (const auto &spec : specs)
    {
        const QString label = TelemetryPresenter::pageLabelText(spec.modeId);
        QVERIFY2(!label.trimmed().isEmpty(), qPrintable(QStringLiteral("mode %1 has no page label").arg(spec.modeId)));
    }
}

QTEST_MAIN(TelemetryPresenterTest)
#include "test_telemetry_presenter.moc"
