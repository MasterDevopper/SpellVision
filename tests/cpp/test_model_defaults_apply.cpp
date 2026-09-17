// A model's own published settings land on the cockpit -- in BOTH Simple and Advanced, without
// clobbering a field the model did not mention or a value the user already typed.
//
// The seam that makes this cheap: ImageGenerationPage carries a modelDefaultsProvider_ (a
// synchronous cache read) separate from modelDefaultsFetcher_ (the async worker trigger). With no
// fetcher wired, requestModelDefaults() falls through to applyModelDefaults() directly -- and
// refreshModelDefaults() is the public, synchronous door to that same function, the one
// tests/cpp/test_canvas_size_default.cpp already uses (Task 6) to re-run the appliers without a
// worker, a socket or an event loop. This file drives the page through that door.
//
// Every case below runs on a TextToVideo page rather than the T2I page the owner's real scenario
// (loxsUtopicWorldKrea2_v20Quants) lives on. That is a testability fact, not a scope narrowing: the
// function under test (applyModelDefaults -> applyResolvedSettings) has no mode-specific branch for
// steps/cfg/the caption/the user-edited guard, and setSelectedModel() -- the only thing that assigns
// selectedModelPath_ -- is private, reached in image mode only through a modal picker dialog or a
// catalog-gated handoff (both need a real, scanned disk catalog to succeed). The video primary-model
// combo, by contrast, is a real QComboBox a test can drive through its own public API, and its
// currentIndexChanged handler (ImageGenerationPage.cpp) calls the private setSelectedModel() from
// inside the page's own connected slot -- so this simulates an actual checkpoint pick rather than
// reaching around one. See selectVideoCheckpoint() below.
//
// Six cases, each written to fail against a plausible wrong implementation rather than merely pass
// against the right one:
//
//   1/2. Steps=10 from the model's own published examples lands in BOTH Simple and Advanced. The
//        tempting wrong shortcut is pre-filling only in Simple -- "the user won't change it anyway"
//        reads as a Simple-mode convenience, but the house rule (CLAUDE.md: Advanced reveals in
//        place) says a pre-filled correct number belongs in the control it already sits in,
//        whichever mode is showing it. A plant that returns early on advanced_ passes case 1 and
//        fails case 2.
//   3.   A model whose settings omit `sampler` must not clear the family operating point's concrete
//        sampler choice. This is the OVERLAY contract: applyResolvedSettings only writes a field the
//        answer actually carries, so a plant that clears every field the map does not mention (the
//        mirror image of "OVERLAY, not replacement") fails this one specifically.
//   4.   The caption names WHERE the numbers came from (the model's own CivitAI examples) and how
//        many of them agreed -- not just that a value differs from the family table.
//   5.   A canvas size the user typed survives a later re-application of the model's answer -- the
//        userEditedFields_ guard applyResolvedSettings reads before writing width/height.
//   6.   A provider with nothing to say (worker down, or an unrouted model) leaves the widgets
//        exactly where they were -- it must not zero them out, which is what happens if a plant
//        drops the `steps.isDouble()` / `cfg.isDouble()` guards and writes an undefined QJsonValue's
//        .toInt() (0) straight into the spin boxes.

#include <QtTest>

#include <QComboBox>
#include <QCoreApplication>
#include <QDoubleSpinBox>
#include <QJsonArray>
#include <QJsonObject>
#include <QLabel>
#include <QSettings>
#include <QSpinBox>

#include "ImageGenerationPage.h"
#include "widgets/ElidingLabel.h"

using spellvision::widgets::ElidingLabel;

namespace
{

// The video "Primary" checkpoint combo, found by the label beside it (ImageGenerationPage.cpp's
// addVideoStacked wraps every video-component field as {QLabel above, field below} in one cell
// widget). No public accessor reaches videoPrimaryModelCombo_ directly.
QComboBox *videoPrimaryModelComboOf(ImageGenerationPage &page)
{
    for (QLabel *label : page.findChildren<QLabel *>())
    {
        if (label->text() != QStringLiteral("Primary"))
            continue;
        if (QWidget *cell = label->parentWidget())
        {
            if (QComboBox *combo = cell->findChild<QComboBox *>())
                return combo;
        }
    }
    return nullptr;
}

// Simulates picking a checkpoint from the video primary-model combo -- the real production trigger
// (ImageGenerationPage.cpp wires this combo's currentIndexChanged to the private setSelectedModel())
// rather than a test reaching around it. Works on an empty combo (Qt auto-selects a freshly added
// first item) and a populated one (explicit setCurrentIndex) alike.
void selectVideoCheckpoint(ImageGenerationPage &page, const QString &path, const QString &display)
{
    QComboBox *combo = videoPrimaryModelComboOf(page);
    QVERIFY2(combo, "primary video model combo not found");
    const int newIndex = combo->count();
    combo->addItem(display, path);
    if (combo->currentIndex() != newIndex)
        combo->setCurrentIndex(newIndex);
}

// SamplingController::create() gives stepsSpin_ the only range(1, 200) QSpinBox on the page (the
// dual-noise high/low/split spins are range(1, 511/512), frames is range(1, 2400), fps range(1,
// 120), the canvas spins are the 8192 ones) -- so the range alone identifies it without a public
// accessor.
QSpinBox *stepsSpinOf(ImageGenerationPage &page)
{
    for (QSpinBox *box : page.findChildren<QSpinBox *>())
    {
        if (box->minimum() == 1 && box->maximum() == 200)
            return box;
    }
    return nullptr;
}

// cfgSpin_ is the only QDoubleSpinBox on the page with one decimal place (the wan shift spins use
// two).
QDoubleSpinBox *cfgSpinOf(ImageGenerationPage &page)
{
    for (QDoubleSpinBox *box : page.findChildren<QDoubleSpinBox *>())
    {
        if (box->decimals() == 1)
            return box;
    }
    return nullptr;
}

// The two canvas spin boxes: range 0..8192 with the em-dash special value, in creation order. Same
// identification trick as tests/cpp/test_canvas_size_default.cpp.
struct CanvasSpins
{
    QSpinBox *width = nullptr;
    QSpinBox *height = nullptr;
};

CanvasSpins canvasSpins(ImageGenerationPage &page)
{
    CanvasSpins spins;
    for (QSpinBox *box : page.findChildren<QSpinBox *>())
    {
        if (box->maximum() != 8192 || box->specialValueText() != QStringLiteral("—"))
            continue;
        if (!spins.width)
            spins.width = box;
        else if (!spins.height)
            spins.height = box;
    }
    return spins;
}

// The honesty caption. Named at its construction site (ImageGenerationPage.cpp) precisely so a test
// does not collide with the OTHER unnamed findChild<ErrorPillLabel*>() the readiness-pill test
// already owns.
ElidingLabel *captionOf(ImageGenerationPage &page)
{
    return page.findChild<ElidingLabel *>(QStringLiteral("ModelDefaultsProvenance"));
}

// The combo that OFFERS a given item -- used to locate whichever sampler/scheduler combo actually
// received a family's option list, without a public accessor to SamplingController's raw pointers.
QComboBox *comboOffering(ImageGenerationPage &page, const QString &data)
{
    for (QComboBox *combo : page.findChildren<QComboBox *>())
    {
        if (combo->findData(data) >= 0)
            return combo;
    }
    return nullptr;
}

// One resolver field: {value, provenance, confidence, n, total}. The shape docs/SPELLVISION_WORKER_
// PROTOCOL.md and python/model_intelligence/recommended.py both use.
QJsonObject entry(const QJsonValue &value, const QString &provenance, int n = 0, int total = 0)
{
    return QJsonObject{
        {QStringLiteral("value"), value},
        {QStringLiteral("provenance"), provenance},
        {QStringLiteral("confidence"), 1.0},
        {QStringLiteral("n"), n},
        {QStringLiteral("total"), total},
    };
}

// The owner's real library, from the task brief: loxsUtopicWorldKrea2_v20Quants publishes steps
// 10 / cfg 1.0 / sampler er_sde / scheduler simple, all at site:image-meta-mode with 10 of 10
// examples agreeing.
QJsonObject krea2Reply()
{
    QJsonObject settings;
    settings.insert(QStringLiteral("steps"), entry(10, QStringLiteral("site:image-meta-mode"), 10, 10));
    settings.insert(QStringLiteral("cfg"), entry(1.0, QStringLiteral("site:image-meta-mode"), 10, 10));
    settings.insert(QStringLiteral("sampler"), entry(QStringLiteral("er_sde"), QStringLiteral("site:image-meta-mode"), 10, 10));
    settings.insert(QStringLiteral("scheduler"), entry(QStringLiteral("simple"), QStringLiteral("site:image-meta-mode"), 10, 10));
    return QJsonObject{
        {QStringLiteral("ok"), true},
        {QStringLiteral("family"), QStringLiteral("krea2")},
        {QStringLiteral("settings"), settings},
        {QStringLiteral("warnings"), QJsonArray()},
    };
}

// A two-point wan table whose default point ("fast") names a CONCRETE sampler -- what case 3 checks
// survives an overlay that says nothing about sampler. Modelled on test_canvas_size_default.cpp's
// familyTable() helper (two points, never one: a single-point family hides the selector and never
// calls applyOperatingPoint at all).
QJsonObject wanOperatingPointTable()
{
    auto point = [](const QString &name, const QString &sampler, const QString &scheduler, int steps, double cfg) {
        QJsonObject params{
            {QStringLiteral("sampler"), sampler},
            {QStringLiteral("scheduler"), scheduler},
            {QStringLiteral("steps"), steps},
            {QStringLiteral("cfg"), cfg},
        };
        return QJsonObject{{QStringLiteral("name"), name}, {QStringLiteral("params"), params}};
    };
    QJsonObject table;
    table.insert(QStringLiteral("default_operating_point"), QStringLiteral("fast"));
    table.insert(QStringLiteral("operating_points"),
                 QJsonArray{point(QStringLiteral("fast"), QStringLiteral("uni_pc"), QStringLiteral("simple"), 14, 4.0),
                            point(QStringLiteral("quality"), QStringLiteral("euler"), QStringLiteral("normal"), 30, 5.0)});
    table.insert(QStringLiteral("samplers"), QJsonArray{QStringLiteral("uni_pc"), QStringLiteral("euler")});
    table.insert(QStringLiteral("schedulers"), QJsonArray{QStringLiteral("simple"), QStringLiteral("normal")});
    return table;
}

const QString kKrea2Path = QStringLiteral("D:/AI_ASSETS/models/checkpoints/loxsUtopicWorldKrea2_v20Quants.safetensors");

} // namespace

class ModelDefaultsApplyTest : public QObject
{
    Q_OBJECT

private slots:
    void initTestCase()
    {
        // Several codepaths this file drives (ensureCanvasSizeDefault, the construction-time
        // restoreSnapshot()) read QSettings; the test must see an empty store rather than whatever
        // the developer's own machine has saved.
        QCoreApplication::setOrganizationName(QStringLiteral("DarkDuckTest"));
        QCoreApplication::setApplicationName(QStringLiteral("SpellVisionModelDefaultsTest"));
        QSettings settings;
        settings.clear();
        settings.sync();
    }

    void stepsLandInSimpleMode();
    void stepsLandInAdvancedModeToo();
    void anUnmentionedSamplerKeepsTheFamilyOperatingPointsSampler();
    void theCaptionNamesTheProvenanceAndTheAgreementCount();
    void aUserTypedCanvasSurvivesAModelDefaultsRefresh();
    void anEmptyReplyLeavesTheWidgetsAlone();
    void theAnswerIsLookedUpForTheFamilyOnScreen();
    void aHandSetDualNoiseSplitSurvivesASimpleAdvancedToggle();
    void orientationSwapsTheResolvedPairRatherThanReplacingIt();
};

void ModelDefaultsApplyTest::stepsLandInSimpleMode()
{
    ImageGenerationPage page(ImageGenerationPage::Mode::TextToVideo);
    page.setModelDefaultsProvider([](const QString &modelPath, const QString &, const QString &) -> QJsonObject {
        if (modelPath.compare(kKrea2Path, Qt::CaseInsensitive) != 0)
            return {};
        return krea2Reply();
    });

    page.updateDisclosure(false); // Simple
    selectVideoCheckpoint(page, kKrea2Path, QStringLiteral("loxsUtopicWorldKrea2_v20Quants"));
    page.refreshModelDefaults();

    QSpinBox *steps = stepsSpinOf(page);
    QVERIFY2(steps, "steps spin box not found");
    QCOMPARE(steps->value(), 10);

    // A SECOND application, which is what the async reply actually does when it lands after the
    // family point. An implementation that applies once and then considers the model "done" passed
    // every case in this file.
    page.refreshModelDefaults();
    QCOMPARE(steps->value(), 10);
}

void ModelDefaultsApplyTest::stepsLandInAdvancedModeToo()
{
    ImageGenerationPage page(ImageGenerationPage::Mode::TextToVideo);
    page.setModelDefaultsProvider([](const QString &modelPath, const QString &, const QString &) -> QJsonObject {
        if (modelPath.compare(kKrea2Path, Qt::CaseInsensitive) != 0)
            return {};
        return krea2Reply();
    });

    // Spec ruling R2.1: applies in BOTH modes, with no advanced_ test anywhere in applyModelDefaults.
    // Advanced set BEFORE the model is selected/refreshed, so a plant that returns early on advanced_
    // (the tempting "pre-filling is a Simple-mode convenience" shortcut) is caught here.
    page.updateDisclosure(true); // Advanced
    selectVideoCheckpoint(page, kKrea2Path, QStringLiteral("loxsUtopicWorldKrea2_v20Quants"));
    page.refreshModelDefaults();

    QSpinBox *steps = stepsSpinOf(page);
    QVERIFY2(steps, "steps spin box not found");
    QCOMPARE(steps->value(), 10);

    page.refreshModelDefaults();
    QCOMPARE(steps->value(), 10);
}

void ModelDefaultsApplyTest::anUnmentionedSamplerKeepsTheFamilyOperatingPointsSampler()
{
    ImageGenerationPage page(ImageGenerationPage::Mode::TextToVideo);

    page.setOperatingPointsProvider([](const QString &) { return wanOperatingPointTable(); });
    page.pinVideoFamily(QStringLiteral("wan"));
    page.updateDisclosure(false);

    // The family operating point set a CONCRETE sampler ("fast" -> uni_pc). This is what the rest
    // of the test checks survives an overlay that says nothing about sampler.
    QComboBox *sampler = comboOffering(page, QStringLiteral("uni_pc"));
    QVERIFY2(sampler, "no combo offers the family operating point's sampler");
    QCOMPARE(sampler->currentData().toString(), QStringLiteral("uni_pc"));

    const QString path = QStringLiteral("D:/AI_ASSETS/models/diffusion_models/wan2.2_t2v_test.safetensors");
    page.setModelDefaultsProvider([path](const QString &modelPath, const QString &, const QString &) -> QJsonObject {
        if (modelPath.compare(path, Qt::CaseInsensitive) != 0)
            return {};
        // This model's own settings say something about steps and DELIBERATELY nothing about
        // sampler -- a plant that clears every field the answer does not mention would blank this
        // combo back to "auto" (or leave it on whatever a naive rewrite picked) instead of leaving
        // the family's uni_pc alone.
        QJsonObject settings;
        settings.insert(QStringLiteral("steps"), entry(20, QStringLiteral("site:image-meta-mode"), 5, 5));
        return QJsonObject{{QStringLiteral("ok"), true}, {QStringLiteral("settings"), settings}};
    });
    selectVideoCheckpoint(page, path, QStringLiteral("wan test checkpoint"));
    page.refreshModelDefaults();

    // BOTH halves. The sampler assertion alone passed against an EMPTY applyModelDefaults() -- it
    // only said a value nothing had touched was still there -- so the test that was meant to prove
    // the overlay writes what it carries and leaves the rest alone was proving the second half of
    // that sentence and not the first.
    QCOMPARE(stepsSpinOf(page)->value(), 20);
    QCOMPARE(sampler->currentData().toString(), QStringLiteral("uni_pc"));

    // Twice. Five of the six cases called this exactly once, so a plant that applies on the FIRST
    // call and short-circuits afterwards -- the shape of a plausible "don't re-apply" optimisation,
    // and the shape of the async arrival this whole path exists for -- passed all of them.
    page.refreshModelDefaults();
    QCOMPARE(stepsSpinOf(page)->value(), 20);
    QCOMPARE(sampler->currentData().toString(), QStringLiteral("uni_pc"));
}

void ModelDefaultsApplyTest::theCaptionNamesTheProvenanceAndTheAgreementCount()
{
    ImageGenerationPage page(ImageGenerationPage::Mode::TextToVideo);
    page.setModelDefaultsProvider([](const QString &modelPath, const QString &, const QString &) -> QJsonObject {
        if (modelPath.compare(kKrea2Path, Qt::CaseInsensitive) != 0)
            return {};
        return krea2Reply();
    });

    selectVideoCheckpoint(page, kKrea2Path, QStringLiteral("loxsUtopicWorldKrea2_v20Quants"));
    page.refreshModelDefaults();

    ElidingLabel *caption = captionOf(page);
    QVERIFY2(caption, "the provenance caption label (ModelDefaultsProvenance) was not found");
    const QString text = caption->fullText();
    QVERIFY2(text.contains(QStringLiteral("CivitAI"), Qt::CaseInsensitive),
             qPrintable(QStringLiteral("caption does not name the model's own examples as the source: %1").arg(text)));
    QVERIFY2(text.contains(QStringLiteral("10 of 10")),
             qPrintable(QStringLiteral("caption does not state the agreement count: %1").arg(text)));
}

void ModelDefaultsApplyTest::aUserTypedCanvasSurvivesAModelDefaultsRefresh()
{
    ImageGenerationPage page(ImageGenerationPage::Mode::TextToVideo);
    const CanvasSpins spins = canvasSpins(page);
    QVERIFY2(spins.width && spins.height, "canvas spin boxes not found");

    const QString path = QStringLiteral("D:/AI_ASSETS/models/diffusion_models/some_other_model.safetensors");
    page.setModelDefaultsProvider([path](const QString &modelPath, const QString &, const QString &) -> QJsonObject {
        if (modelPath.compare(path, Qt::CaseInsensitive) != 0)
            return {};
        QJsonObject settings;
        settings.insert(QStringLiteral("width"), entry(512, QStringLiteral("table:family-operating-point")));
        settings.insert(QStringLiteral("height"), entry(512, QStringLiteral("table:family-operating-point")));
        return QJsonObject{{QStringLiteral("ok"), true}, {QStringLiteral("settings"), settings}};
    });

    selectVideoCheckpoint(page, path, QStringLiteral("some other model"));
    page.refreshModelDefaults();
    QCOMPARE(spins.width->value(), 512);
    QCOMPARE(spins.height->value(), 512);

    // A write from outside the page's own ProgrammaticWrite scope is exactly what a human typing
    // looks like -- this is what markUserEdited() distinguishes it from.
    spins.width->setValue(777);
    spins.height->setValue(555);

    // Re-run the SAME applier the async worker reply's arrival calls when it finally lands (this is
    // the exact scenario Task 8's brief describes: the user types between the model change and the
    // deferred answer showing up).
    page.refreshModelDefaults();

    QCOMPARE(spins.width->value(), 777);
    QCOMPARE(spins.height->value(), 555);
}

void ModelDefaultsApplyTest::anEmptyReplyLeavesTheWidgetsAlone()
{
    ImageGenerationPage page(ImageGenerationPage::Mode::TextToVideo);
    QSpinBox *steps = stepsSpinOf(page);
    QDoubleSpinBox *cfg = cfgSpinOf(page);
    QVERIFY2(steps && cfg, "sampling widgets not found");
    const int stepsBefore = steps->value();
    const double cfgBefore = cfg->value();

    // The worker is down (or this model has nothing published): the provider has no answer for
    // anything.
    page.setModelDefaultsProvider([](const QString &, const QString &, const QString &) -> QJsonObject { return {}; });

    const QString path = QStringLiteral("D:/AI_ASSETS/models/diffusion_models/unknown_model.safetensors");
    selectVideoCheckpoint(page, path, QStringLiteral("unknown model"));
    page.refreshModelDefaults();

    QCOMPARE(steps->value(), stepsBefore);
    QCOMPARE(cfg->value(), cfgBefore);

    // The caption must not claim a source for a model that answered nothing -- refreshModelDefaults-
    // Caption's early return (settings.isEmpty()) is what a plant removing the isDouble()/isEmpty()
    // guards would also tend to remove.
    ElidingLabel *caption = captionOf(page);
    QVERIFY2(caption, "the provenance caption label (ModelDefaultsProvenance) was not found");
    QVERIFY2(caption->fullText().isEmpty(),
             qPrintable(QStringLiteral("caption claims something about a model that answered nothing: %1")
                            .arg(caption->fullText())));

    // Everything above is satisfied by an EMPTY applyModelDefaults(), which is the nature of a
    // negative test and was the hole: two of six cases passed against a stub. So the same page is
    // now given a provider that DOES answer, and the answer has to arrive -- the "leaves it alone"
    // claim only means something once "and otherwise it acts" is proven on the same object.
    page.setModelDefaultsProvider([](const QString &, const QString &, const QString &) -> QJsonObject {
        QJsonObject settings;
        settings.insert(QStringLiteral("steps"), entry(37, QStringLiteral("site:image-meta-mode"), 4, 4));
        return QJsonObject{{QStringLiteral("ok"), true}, {QStringLiteral("settings"), settings}};
    });
    page.refreshModelDefaults();
    QCOMPARE(steps->value(), 37);
}

// --- W2 fix wave: the question is (path, family, mode), not path -------------------------------

void ModelDefaultsApplyTest::theAnswerIsLookedUpForTheFamilyOnScreen()
{
    // The cache MainWindow keeps behind this provider was keyed on the path alone while the answer
    // depends on the family too. Switching the T2V family bar from Auto (resolving wan) to LTX with
    // the same checkpoint re-applied the WAN answer: LTX's own frame count never arrived, for the
    // rest of the session, with nothing on screen saying so. The page half of that fix is that it
    // ASKS with the family it is showing -- a provider given only the path cannot answer correctly
    // however well the cache behind it is keyed.
    ImageGenerationPage page(ImageGenerationPage::Mode::TextToVideo);
    QSpinBox *frames = nullptr;
    for (QSpinBox *box : page.findChildren<QSpinBox *>())
    {
        if (box->toolTip().contains(QStringLiteral("Total frames"), Qt::CaseInsensitive))
            frames = box;
    }
    QVERIFY2(frames, "frame count spin box not found");

    QStringList familiesAsked;
    QStringList modesAsked;
    page.setModelDefaultsProvider([&familiesAsked, &modesAsked](const QString &, const QString &family,
                                                               const QString &mode) -> QJsonObject {
        familiesAsked << family;
        modesAsked << mode;
        QJsonObject settings;
        settings.insert(QStringLiteral("frames"),
                        entry(family == QStringLiteral("ltx") ? 49 : 81,
                              QStringLiteral("table:family-operating-point")));
        return QJsonObject{{QStringLiteral("ok"), true}, {QStringLiteral("settings"), settings}};
    });

    const QString path = QStringLiteral("D:/AI_ASSETS/models/diffusion_models/shared_checkpoint.safetensors");
    page.pinVideoFamily(QStringLiteral("wan"));
    selectVideoCheckpoint(page, path, QStringLiteral("shared checkpoint"));
    page.refreshModelDefaults();
    QCOMPARE(frames->value(), 81);

    // The same weight, the family bar moved. This is the exact production sequence: the combo's
    // handler calls updateOperatingPointSelector(), which asks again for the new family.
    page.pinVideoFamily(QStringLiteral("ltx"));
    page.refreshOperatingPointSelector();
    page.refreshModelDefaults();

    QVERIFY2(familiesAsked.contains(QStringLiteral("ltx")),
             qPrintable(QStringLiteral("the page never asked about ltx; it asked: %1")
                            .arg(familiesAsked.join(QStringLiteral(", ")))));
    QCOMPARE(frames->value(), 49);
    // And the mode travels with it, for the same reason: the same weight on T2V and on I2V is two
    // questions, and one cached answer used to serve both.
    QVERIFY2(modesAsked.contains(QStringLiteral("t2v")),
             qPrintable(QStringLiteral("modes asked: %1").arg(modesAsked.join(QStringLiteral(", ")))));
}

void ModelDefaultsApplyTest::aHandSetDualNoiseSplitSurvivesASimpleAdvancedToggle()
{
    // Ruling W2-E3 is one user-edit flag per field the wave writes, and the ledger recorded Task 6
    // as complete against it. applyResolvedSettings writes highNoiseStepsSpin_ / lowNoiseStepsSpin_
    // / splitStepSpin_ from `steps / 2`, and watchForUserEdits() connected none of the three -- so a
    // deliberate asymmetric MoE handoff (20 high / 8 low) was reset to 14 / 14 by the next
    // Simple/Advanced toggle, because `steps` had never been touched and its guard was open.
    ImageGenerationPage page(ImageGenerationPage::Mode::TextToVideo);
    page.setOperatingPointsProvider([](const QString &) { return wanOperatingPointTable(); });
    page.pinVideoFamily(QStringLiteral("wan"));

    // The write under test is gated on usesWanDualNoiseMode(), so the STACK MODE has to be the
    // dual-noise one or applyResolvedSettings never reaches the three spins at all -- and the first
    // version of this test passed against the planted defect for exactly that reason: it asserted
    // that values nothing had touched were unchanged. The Stack Mode combo is the production
    // control, found by the option it offers rather than by a private pointer.
    QComboBox *stackMode = comboOffering(page, QStringLiteral("wan_dual_noise"));
    QVERIFY2(stackMode, "the video Stack Mode combo was not found");
    stackMode->setCurrentIndex(stackMode->findData(QStringLiteral("wan_dual_noise")));
    page.updateDisclosure(true);

    // The dual-noise trio: range(1, 511) or (1, 512), which no other spin box on the page uses.
    QVector<QSpinBox *> split;
    for (QSpinBox *box : page.findChildren<QSpinBox *>())
    {
        if (box->minimum() == 1 && (box->maximum() == 511 || box->maximum() == 512))
            split << box;
    }
    QVERIFY2(split.size() >= 2, "the dual-noise high/low step spins were not found");

    // The page must actually be writing these before the test can claim it stopped. Without this
    // the "survives" assertion is satisfied by a code path that never ran.
    QVERIFY2(split[0]->value() == 14 && split[1]->value() == 14,
             qPrintable(QStringLiteral("the family's 28 steps did not reach the split spins (%1 / %2); "
                                       "this case would pass whatever the guard did")
                            .arg(split[0]->value()).arg(split[1]->value())));

    // A write from outside the page's own ProgrammaticWrite scope is a human typing.
    for (int i = 0; i < split.size(); ++i)
        split[i]->setValue(i == 0 ? 20 : 8);

    page.updateDisclosure(false);
    page.updateDisclosure(true);
    page.refreshOperatingPointSelector();

    QCOMPARE(split[0]->value(), 20);
    QCOMPARE(split[1]->value(), 8);
}

void ModelDefaultsApplyTest::orientationSwapsTheResolvedPairRatherThanReplacingIt()
{
    // Spec 2.2 / plan Task 6 Step 3. The distinction the spec insists on: Portrait must SWAP the
    // pair the model published, not state a literal one. An Aspect preset does the second thing,
    // which is why it could not stand in for this -- it replaces both numbers and then blocks the
    // model's own answer for the rest of the session.
    ImageGenerationPage page(ImageGenerationPage::Mode::TextToVideo);
    const CanvasSpins spins = canvasSpins(page);
    QVERIFY2(spins.width && spins.height, "canvas spin boxes not found");

    QComboBox *orientation = comboOffering(page, QStringLiteral("portrait"));
    QVERIFY2(orientation, "the Simple-mode Orientation combo was not found");

    const QString path = QStringLiteral("D:/AI_ASSETS/models/diffusion_models/wan_orientation.safetensors");
    page.setModelDefaultsProvider([path](const QString &modelPath, const QString &, const QString &) -> QJsonObject {
        if (modelPath.compare(path, Qt::CaseInsensitive) != 0)
            return {};
        QJsonObject settings;
        settings.insert(QStringLiteral("width"), entry(832, QStringLiteral("table:family-operating-point")));
        settings.insert(QStringLiteral("height"), entry(480, QStringLiteral("table:family-operating-point")));
        return QJsonObject{{QStringLiteral("ok"), true}, {QStringLiteral("settings"), settings}};
    });

    page.updateDisclosure(false); // Simple
    selectVideoCheckpoint(page, path, QStringLiteral("wan orientation checkpoint"));
    page.refreshModelDefaults();
    QCOMPARE(spins.width->value(), 832);
    QCOMPARE(spins.height->value(), 480);

    orientation->setCurrentIndex(orientation->findData(QStringLiteral("portrait")));
    QCOMPARE(spins.width->value(), 480);
    QCOMPARE(spins.height->value(), 832);

    // And the model's answer still arrives -- oriented. A Portrait choice that FROZE the canvas
    // (by marking it user-edited) would pass the two lines above and fail here, and that is the
    // difference between an orientation and an aspect preset.
    page.refreshModelDefaults();
    QCOMPARE(spins.width->value(), 480);
    QCOMPARE(spins.height->value(), 832);

    orientation->setCurrentIndex(orientation->findData(QStringLiteral("landscape")));
    QCOMPARE(spins.width->value(), 832);
    QCOMPARE(spins.height->value(), 480);
}

QTEST_MAIN(ModelDefaultsApplyTest)
#include "test_model_defaults_apply.moc"
