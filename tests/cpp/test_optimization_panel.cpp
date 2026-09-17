// The Runtime page's optimization panel, driven by a fake ledger and a fake probe.
//
// Why this panel exists, from one morning on this box:
//
//   * ComfyUI was running WITH SageAttention. It died, was relaunched, and came back WITHOUT it.
//     Nothing in the app said so, and renders on either side of that were indistinguishable
//     afterwards.
//   * `sageattention` IS installed in ComfyUI's venv right now, and the running process was
//     launched without the flag. "Installed" and "active" are different facts and the app showed
//     neither.
//
// So the assertions below are about exactly those distinctions, and each one fails against a
// plausible wrong implementation: showing a blank for "not timed", and treating installed as
// active.
//
// No worker, no socket, no ComfyUI: `OptimizationEvidence::rows` is a pure function of one reply.

#include <QtTest>

#include <QJsonArray>
#include <QJsonObject>

#include "shell/OptimizationEvidence.h"

using spellvision::shell::OptimizationEvidence;
using spellvision::shell::OptimizationEvidenceRow;
using spellvision::shell::OptimizationVerdict;

namespace
{

// The catalogue the worker sends, trimmed to the levers these cases need. Shape mirrors
// python/optimization_commands.py::_catalogue.
QJsonArray catalogue()
{
    QJsonArray out;
    out.append(QJsonObject{
        {QStringLiteral("id"), QStringLiteral("sdpa_baseline")},
        {QStringLiteral("label"), QStringLiteral("SDPA (core default, pinned)")},
        {QStringLiteral("kind"), QStringLiteral("launch")},
        {QStringLiteral("status"), QStringLiteral("runnable")},
    });
    out.append(QJsonObject{
        {QStringLiteral("id"), QStringLiteral("sage_attention")},
        {QStringLiteral("label"), QStringLiteral("SageAttention")},
        {QStringLiteral("kind"), QStringLiteral("launch")},
        {QStringLiteral("status"), QStringLiteral("runnable")},
    });
    out.append(QJsonObject{
        {QStringLiteral("id"), QStringLiteral("fast_fp16_accumulation")},
        {QStringLiteral("label"), QStringLiteral("--fast fp16_accumulation")},
        {QStringLiteral("kind"), QStringLiteral("launch")},
        {QStringLiteral("status"), QStringLiteral("runnable")},
    });
    out.append(QJsonObject{
        {QStringLiteral("id"), QStringLiteral("dynamic_vram_off")},
        {QStringLiteral("label"), QStringLiteral("--disable-dynamic-vram")},
        {QStringLiteral("kind"), QStringLiteral("launch")},
        {QStringLiteral("status"), QStringLiteral("runnable")},
    });
    out.append(QJsonObject{
        {QStringLiteral("id"), QStringLiteral("ck_int8_attention")},
        {QStringLiteral("label"), QStringLiteral("Comfy-Kitchen INT8 attention")},
        {QStringLiteral("kind"), QStringLiteral("launch")},
        {QStringLiteral("status"), QStringLiteral("blocked")},
        {QStringLiteral("blocked_reason"), QStringLiteral("normalize_backend accepts only sage and sdpa")},
    });
    return out;
}

// The live-argv block, shaped like optimization_provenance.probe(). `comfy_kitchen` is deliberately
// absent from `packages`: that is the "the probe could not ask" state, distinct from a real false.
QJsonObject probeBlock(const QString &backend, bool sageInstalled)
{
    return QJsonObject{
        {QStringLiteral("comfy_version"), QStringLiteral("0.34.0")},
        {QStringLiteral("comfy_argv"), QJsonArray{QStringLiteral("main.py"), QStringLiteral("--port"),
                                                  QStringLiteral("8188")}},
        {QStringLiteral("attention_backend"), backend},
        {QStringLiteral("fast_flags"), QJsonArray{}},
        {QStringLiteral("dynamic_vram"), true},
        {QStringLiteral("reserve_vram_gb"), QJsonValue()},
        {QStringLiteral("probe_error"), QJsonValue()},
        {QStringLiteral("packages"), QJsonObject{
                                         {QStringLiteral("sageattention"), sageInstalled},
                                         {QStringLiteral("triton"), true},
                                         {QStringLiteral("comfy_aimdo"), QStringLiteral("0.4.15")},
                                     }},
    };
}

// One comparable ledger row: two timings, warm, guard passed, a real delta.
QJsonObject ledgerRow(const QString &lever, double deltaPct)
{
    return QJsonObject{
        {QStringLiteral("lever"), lever},
        {QStringLiteral("family"), QStringLiteral("krea2")},
        {QStringLiteral("mode"), QStringLiteral("t2i")},
        {QStringLiteral("warm"), true},
        {QStringLiteral("seconds"), QJsonArray{120.72, 121.4}},
        {QStringLiteral("mean"), 121.06},
        {QStringLiteral("baseline_mean"), 124.01},
        {QStringLiteral("delta_pct"), deltaPct},
        {QStringLiteral("excluded_from_delta"), false},
        {QStringLiteral("quality"), QJsonObject{{QStringLiteral("status"), QStringLiteral("pass")},
                                                {QStringLiteral("guards"), QJsonArray{QStringLiteral("black_frame")}}}},
    };
}

QJsonObject reply(const QJsonArray &rows, const QJsonObject &provenance)
{
    return QJsonObject{
        {QStringLiteral("type"), QStringLiteral("optimization_results")},
        {QStringLiteral("ok"), true},
        {QStringLiteral("catalogue"), catalogue()},
        {QStringLiteral("rows"), rows},
        {QStringLiteral("provenance"), provenance},
    };
}

OptimizationEvidenceRow rowFor(const QList<OptimizationEvidenceRow> &rows, const QString &leverId)
{
    for (const OptimizationEvidenceRow &row : rows)
    {
        if (row.leverId == leverId)
            return row;
    }
    return {};
}

} // namespace

class OptimizationPanelTest : public QObject
{
    Q_OBJECT

private slots:
    void anActiveLeverWithADeltaFillsAllFourColumns();
    void installedButNotActiveNeverReadsAsABenefit();
    void aLeverWithNoMeasurementSaysNotTimed();
    void notProbedReadsDifferentlyFromNotInstalled();
    void anEmptyLedgerStillRendersEveryLever();
    void aFailedQualityGuardReadsAsBroke();
};

// Case 1. The whole row has an answer: the package is there, the process is running on it, and the
// ledger holds a verified delta for it.
void OptimizationPanelTest::anActiveLeverWithADeltaFillsAllFourColumns()
{
    const auto rows = OptimizationEvidence::rows(
        reply(QJsonArray{ledgerRow(QStringLiteral("sage_attention"), -2.7)},
              probeBlock(QStringLiteral("sage"), true)));

    const OptimizationEvidenceRow sage = rowFor(rows, QStringLiteral("sage_attention"));
    QCOMPARE(sage.installed, QStringLiteral("installed"));
    QCOMPARE(sage.active, QStringLiteral("active"));
    QVERIFY(sage.measuredIsKnown);
    QVERIFY2(sage.measured.contains(QStringLiteral("2.7%")),
             qPrintable(QStringLiteral("measured column was: ") + sage.measured));
    QVERIFY(sage.measured.contains(QStringLiteral("faster")));
    QVERIFY2(sage.measured.contains(QStringLiteral("2 runs")),
             "a delta stands on a number of runs; one timing is not a measurement");
    QCOMPARE(sage.verdictKind, OptimizationVerdict::Used);
    QCOMPARE(sage.verdict, QStringLiteral("used"));

    // Four columns, all of them said something.
    for (const QString &cell : {sage.installed, sage.active, sage.measured, sage.verdict})
        QVERIFY(!cell.trimmed().isEmpty());
}

// Case 2. The live case on this box: sageattention IS installed, the running process was launched
// without the flag. Three separate things must not happen -- "active" must not claim it, the
// verdict must not be "used", and the historical delta must not be shown as a benefit the user is
// currently getting.
void OptimizationPanelTest::installedButNotActiveNeverReadsAsABenefit()
{
    const auto rows = OptimizationEvidence::rows(
        reply(QJsonArray{ledgerRow(QStringLiteral("sage_attention"), -18.0)},
              probeBlock(QStringLiteral("sdpa"), /*sageInstalled=*/true)));

    const OptimizationEvidenceRow sage = rowFor(rows, QStringLiteral("sage_attention"));

    // Installed still reads installed -- that fact is true and is not the one in dispute.
    QCOMPARE(sage.installed, QStringLiteral("installed"));

    // Active is read from the argv, and the argv says sdpa.
    QVERIFY(sage.activeKnown);
    QVERIFY2(!sage.activeNow, "the running process was launched on sdpa; sage is not active");
    QVERIFY2(sage.active.startsWith(QStringLiteral("not active")),
             qPrintable(QStringLiteral("active column was: ") + sage.active));
    QVERIFY2(sage.active.contains(QStringLiteral("sdpa")),
             "saying what IS running is what makes 'not active' actionable");

    // The verdict is the headline, and it is not a benefit.
    QCOMPARE(sage.verdictKind, OptimizationVerdict::Skipped);
    QCOMPARE(sage.verdict, QStringLiteral("skipped -- installed, not active"));
    QVERIFY2(!sage.verdict.contains(QStringLiteral("used")),
             "installed-but-not-active must never render as used");

    // And the measurement, which IS real, must not stand beside an inactive lever as though the
    // user were getting it. A bare "-18.0% faster" here is the benefit claim this wave exists to
    // stop publishing.
    QVERIFY(sage.measuredIsKnown);
    QVERIFY2(sage.measured.contains(QStringLiteral("not active now")),
             qPrintable(QStringLiteral("measured column was: ") + sage.measured));

    // The baseline in the same reply IS active, so the two rows must disagree -- if they read the
    // same, the panel is not reading the argv at all.
    const OptimizationEvidenceRow sdpa = rowFor(rows, QStringLiteral("sdpa_baseline"));
    QCOMPARE(sdpa.verdictKind, OptimizationVerdict::Used);
    QVERIFY(sdpa.active != sage.active);
}

// Case 3. No verified row for this lever. "not timed" in words -- never a blank, which looks like
// zero, and never "0%", which is a claim nobody measured.
void OptimizationPanelTest::aLeverWithNoMeasurementSaysNotTimed()
{
    const auto rows = OptimizationEvidence::rows(
        reply(QJsonArray{ledgerRow(QStringLiteral("sage_attention"), -2.7)},
              probeBlock(QStringLiteral("sage"), true)));

    const OptimizationEvidenceRow fast = rowFor(rows, QStringLiteral("fast_fp16_accumulation"));
    QVERIFY2(!fast.measured.trimmed().isEmpty(),
             "a blank measured cell reads as zero; say 'not timed' instead");
    QCOMPARE(fast.measured, OptimizationEvidence::notTimedText());
    QCOMPARE(fast.measured, QStringLiteral("not timed"));
    QVERIFY(!fast.measuredIsKnown);
    QVERIFY2(!fast.measured.contains(QStringLiteral("0%")),
             "0% is a measurement nobody took");
    QVERIFY2(!fast.measured.contains(QStringLiteral("0.0")),
             "no number may appear where nothing was measured");

    // A recorded-but-excluded row is still not a measurement, and must still say so rather than
    // disappearing into the same blank.
    QJsonObject excluded = ledgerRow(QStringLiteral("fast_fp16_accumulation"), 0.0);
    excluded.insert(QStringLiteral("excluded_from_delta"), true);
    excluded.insert(QStringLiteral("delta_pct"), QJsonValue());
    excluded.insert(QStringLiteral("exclusions"),
                    QJsonArray{QStringLiteral("only one timed run")});

    const auto withExcluded = OptimizationEvidence::rows(
        reply(QJsonArray{excluded}, probeBlock(QStringLiteral("sdpa"), true)));
    const OptimizationEvidenceRow fastExcluded =
        rowFor(withExcluded, QStringLiteral("fast_fp16_accumulation"));
    QVERIFY(!fastExcluded.measuredIsKnown);
    QVERIFY2(fastExcluded.measured.contains(OptimizationEvidence::notTimedText()),
             qPrintable(QStringLiteral("measured column was: ") + fastExcluded.measured));
    QVERIFY2(fastExcluded.measured.contains(QStringLiteral("1 recorded")),
             "a row that was recorded and excluded is not the same as no row at all");
}

// Case 4. "The probe could not ask" and "the probe asked and found nothing" are different states.
// Collapsing them is what let two knowable package versions read as unknowable for a whole task.
void OptimizationPanelTest::notProbedReadsDifferentlyFromNotInstalled()
{
    const auto rows = OptimizationEvidence::rows(
        reply(QJsonArray{}, probeBlock(QStringLiteral("sdpa"), /*sageInstalled=*/false)));

    // sageattention: asked, and the answer was no.
    const OptimizationEvidenceRow sage = rowFor(rows, QStringLiteral("sage_attention"));
    QCOMPARE(sage.installed, OptimizationEvidence::notInstalledText());
    QCOMPARE(sage.installed, QStringLiteral("not installed"));
    QVERIFY2(sage.installedProbed, "false means the probe ran and found nothing");
    QVERIFY(!sage.installedPresent);

    // comfy_kitchen: never in the packages block at all, so nobody asked.
    const OptimizationEvidenceRow ck = rowFor(rows, QStringLiteral("ck_int8_attention"));
    QCOMPARE(ck.installed, OptimizationEvidence::notProbedText());
    QCOMPARE(ck.installed, QStringLiteral("not probed"));
    QVERIFY2(!ck.installedProbed, "an absent key means the question was never asked");

    QVERIFY2(ck.installed != sage.installed,
             "'could not ask' must not render with the same words as 'asked and found absent'");
    QVERIFY(OptimizationEvidence::notProbedText() != OptimizationEvidence::notInstalledText());
}

// Case 5. An empty ledger is the normal state, not an error state. Every lever still gets a row --
// a lever nobody has measured vanishing from the table is the invisibility this panel removes.
void OptimizationPanelTest::anEmptyLedgerStillRendersEveryLever()
{
    const auto rows =
        OptimizationEvidence::rows(reply(QJsonArray{}, probeBlock(QStringLiteral("sdpa"), true)));

    QCOMPARE(rows.size(), catalogue().size());
    for (const OptimizationEvidenceRow &row : rows)
    {
        QVERIFY(!row.label.trimmed().isEmpty());
        QVERIFY2(!row.measured.trimmed().isEmpty(),
                 qPrintable(QStringLiteral("empty measured cell on ") + row.leverId));
        QCOMPARE(row.measured, OptimizationEvidence::notTimedText());
        QVERIFY(!row.measuredIsKnown);
        QVERIFY2(!row.verdict.trimmed().isEmpty(),
                 qPrintable(QStringLiteral("empty verdict on ") + row.leverId));
    }

    // The blocked lever still renders, and says why it cannot be measured rather than reading as
    // an untried option.
    const OptimizationEvidenceRow ck = rowFor(rows, QStringLiteral("ck_int8_attention"));
    QCOMPARE(ck.verdictKind, OptimizationVerdict::Blocked);
    QVERIFY(ck.toolTip.contains(QStringLiteral("normalize_backend")));
}

// A lever that is faster and wrong is not a win. A failed guard outranks the number.
void OptimizationPanelTest::aFailedQualityGuardReadsAsBroke()
{
    QJsonObject broken = ledgerRow(QStringLiteral("sage_attention"), -30.0);
    broken.insert(QStringLiteral("excluded_from_delta"), true);
    broken.insert(QStringLiteral("delta_pct"), QJsonValue());
    broken.insert(QStringLiteral("quality"),
                  QJsonObject{{QStringLiteral("status"), QStringLiteral("fail")},
                              {QStringLiteral("guards"), QJsonArray{QStringLiteral("black_frame")}}});

    const auto rows = OptimizationEvidence::rows(
        reply(QJsonArray{broken}, probeBlock(QStringLiteral("sage"), true)));

    const OptimizationEvidenceRow sage = rowFor(rows, QStringLiteral("sage_attention"));
    QCOMPARE(sage.verdictKind, OptimizationVerdict::Broke);
    QVERIFY2(!sage.measuredIsKnown, "an excluded row is not a delta, however large it looks");
    QVERIFY2(!sage.measured.contains(QStringLiteral("30")),
             "a number from an excluded row must not reach the panel");
}

QTEST_MAIN(OptimizationPanelTest)
#include "test_optimization_panel.moc"
