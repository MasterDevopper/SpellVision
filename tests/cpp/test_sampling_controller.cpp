// The cockpit's sampling row: two ways a control said yes and the value never left it.
//
// 1. A family that offers no samplers left the PREVIOUS family's list on screen. applyFamilyChoices
//    returned early on an empty table, so switching to a family with nothing to offer showed sdxl's
//    five samplers, and picking one sent a name that family has never heard of.
//
// 2. draftSeed() clamped with qMax(1, ...). The spin box had been widened to accept 0 -- 0 is a
//    seed, ComfyUI's KSampler declares it as the minimum, and every builder honours it through
//    resolve_seed -- and this clamp turned every 0 the user typed back into 1 on the way out.
//
// The second is the one the Python sweeps structurally cannot see: the value is corrected inside
// the widget, before any request exists to inspect.
//
// 3. The Doc 62 ruling. ONE dropdown: Simple lists the samplers known good with the model, Advanced
//    lists the same head, a labelled separation, then everything else the build offers. The head is
//    identical in both modes -- that is what makes it "reveals in place" rather than a second list
//    -- and a switch to Simple NEVER changes the selection: an Advanced choice from the tail is
//    carried over under its own heading and stays selected. Silently replacing it would be the
//    hidden output-changing state this codebase ran a hardening pass against, wearing a dropdown.

#include <QtTest>
// QTEST_MAIN builds a QApplication only when the widgets module is visible here; without
// this include it makes a QCoreApplication and the first QWidget aborts before any case runs.
#include <QApplication>
#include <QComboBox>
#include <QCheckBox>
#include <QSpinBox>
#include <QWidget>
#include <QJsonArray>
#include <QJsonObject>

#include "generation/SamplingController.h"

using spellvision::generation::SamplingController;

class SamplingControllerTest : public QObject
{
    Q_OBJECT

private slots:
    void init();
    void cleanup();

    void aFamilyWithNoChoicesClearsTheStaleList();
    void aFamilyWithSamplersButNoSchedulersKeepsItsSamplers();
    void theComboKeepsAutoAndOffersTheFamilysSamplers();
    void aDeliberateChoiceSurvivesAFamilySwitchOnlyIfTheFamilyOffersIt();
    void simpleListsOnlyTheKnownGoodAndAdvancedContinuesPastASeparator();
    void theHeadOfTheListIsIdenticalInBothModes();
    void anAdvancedChoiceSurvivesASwitchToSimpleStillSelectedAndStillVisible();
    void aPreRulingTableStillRendersAsOneFlatList();
    void aStatedSeedOfZeroSurvives();
    void aStatedSeedIsNotOtherwiseAltered();
    void randomSeedsCanIncludeZero();

private:
    QWidget *host_ = nullptr;
    SamplingController *controller_ = nullptr;

    static QJsonObject table(const QStringList &samplers, const QStringList &schedulers,
                             const QString &defaultSampler = QString())
    {
        QJsonArray a, b;
        for (const QString &s : samplers) a.append(s);
        for (const QString &s : schedulers) b.append(s);
        QJsonObject o{{QStringLiteral("samplers"), a}, {QStringLiteral("schedulers"), b}};
        if (!defaultSampler.isEmpty())
            o.insert(QStringLiteral("default_sampler"), defaultSampler);
        return o;
    }

    // What the worker answers since the ruling: the flat list every pre-ruling reader still uses,
    // PLUS the split. The two forms live side by side here deliberately -- one test below feeds the
    // flat-only shape and asserts the control is unchanged by it.
    static QJsonObject grouped(const QStringList &known, const QStringList &other,
                               const QString &defaultSampler = QString())
    {
        QJsonArray k, o, all;
        for (const QString &s : known) { k.append(s); all.append(s); }
        for (const QString &s : other) { o.append(s); all.append(s); }
        QJsonObject t{
            {QStringLiteral("samplers"), all},
            {QStringLiteral("schedulers"), QJsonArray{}},
            {QStringLiteral("known_good_samplers"), k},
            {QStringLiteral("other_samplers"), o},
            {QStringLiteral("known_good_schedulers"), QJsonArray{}},
            {QStringLiteral("other_schedulers"), QJsonArray{}},
        };
        if (!defaultSampler.isEmpty())
            t.insert(QStringLiteral("default_sampler"), defaultSampler);
        return t;
    }

    // The selectable entries, in order, skipping the Auto placeholder and any separator or heading
    // (both of which carry no item data, which is also what stops either from ever being sent).
    QStringList offered(const QComboBox *combo) const
    {
        QStringList names;
        for (int i = 1; i < combo->count(); ++i)
        {
            const QString data = combo->itemData(i).toString();
            if (!data.isEmpty())
                names << data;
        }
        return names;
    }

    int headingCount(const QComboBox *combo) const
    {
        int n = 0;
        for (int i = 0; i < combo->count(); ++i)
        {
            if (combo->itemData(i).toString().isEmpty() && !combo->itemText(i).isEmpty()
                && i > 0)
            {
                ++n;
            }
        }
        return n;
    }
};

void SamplingControllerTest::init()
{
    host_ = new QWidget;
    controller_ = new SamplingController(host_);
    controller_->create(host_);
}

void SamplingControllerTest::cleanup()
{
    delete host_;
    host_ = nullptr;
    controller_ = nullptr;
}

void SamplingControllerTest::aFamilyWithNoChoicesClearsTheStaleList()
{
    controller_->applyFamilyChoices(table({"euler", "dpmpp_2m", "ddim"}, {"normal", "karras"}), false);
    QVERIFY(controller_->samplerCombo()->count() > 1);

    // cogvideox returns an empty table, and it is right to: the family is unrouted and has no
    // sampler to offer. Showing the previous family's list is worse than showing none.
    controller_->applyFamilyChoices(table({}, {}), false);
    QCOMPARE(controller_->samplerCombo()->count(), 1);  // "Auto / family default" only
    QCOMPARE(controller_->samplerCombo()->itemData(0).toString(), QStringLiteral("auto"));
}

void SamplingControllerTest::aFamilyWithSamplersButNoSchedulersKeepsItsSamplers()
{
    // LTX. Its schedulers tuple is deliberately empty -- both templates drive sigmas through
    // ManualSigmas -- so treating "either list empty" as "no table" would strand it.
    controller_->applyFamilyChoices(table({"euler", "dpmpp_2m"}, {"normal"}), false);
    controller_->applyFamilyChoices(
        table({"euler_ancestral_cfg_pp", "euler_cfg_pp", "euler"}, {}), false);

    QCOMPARE(controller_->samplerCombo()->count(), 4);   // auto + three
    QCOMPARE(controller_->schedulerCombo()->count(), 1); // auto only
}

void SamplingControllerTest::theComboKeepsAutoAndOffersTheFamilysSamplers()
{
    // "Auto / family default" stays selected, and that is right: the concrete default belongs to
    // the worker's resolver, so the cockpit showing a name would be a second place for it to live.
    // What the combo must do is OFFER the family's samplers -- and offer only those.
    controller_->applyFamilyChoices(
        table({"euler", "euler_ancestral", "dpmpp_2m", "dpmpp_2m_sde", "ddim"},
              {"normal", "karras"}, QStringLiteral("dpmpp_2m")), false);

    QCOMPARE(controller_->imageSampler(), QStringLiteral("auto"));
    QCOMPARE(controller_->samplerCombo()->count(), 6);  // auto + five
    QVERIFY(controller_->samplerCombo()->findData(QStringLiteral("dpmpp_2m")) > 0);
    QVERIFY(controller_->samplerCombo()->findData(QStringLiteral("res_multistep")) < 0);
}

void SamplingControllerTest::aDeliberateChoiceSurvivesAFamilySwitchOnlyIfTheFamilyOffersIt()
{
    controller_->applyFamilyChoices(
        table({"euler", "dpmpp_2m", "ddim"}, {"normal", "karras"}), false);
    controller_->samplerCombo()->setCurrentIndex(
        controller_->samplerCombo()->findData(QStringLiteral("dpmpp_2m")));
    QCOMPARE(controller_->imageSampler(), QStringLiteral("dpmpp_2m"));

    // Same sampler offered by the next family: keep it, the user asked for it.
    controller_->applyFamilyChoices(table({"euler", "dpmpp_2m"}, {"simple"}), false);
    QCOMPARE(controller_->imageSampler(), QStringLiteral("dpmpp_2m"));

    // Not offered by the next family: fall back to auto rather than send a name this family has
    // never heard of, which is what the stale list used to make possible.
    controller_->applyFamilyChoices(table({"res_multistep", "euler"}, {"simple"}), false);
    QCOMPARE(controller_->imageSampler(), QStringLiteral("auto"));
}

void SamplingControllerTest::simpleListsOnlyTheKnownGoodAndAdvancedContinuesPastASeparator()
{
    const QStringList known{QStringLiteral("er_sde"), QStringLiteral("euler")};
    const QStringList other{QStringLiteral("heun"), QStringLiteral("lms")};

    controller_->setAdvanced(false);
    controller_->applyFamilyChoices(grouped(known, other, QStringLiteral("er_sde")), false);
    QCOMPARE(offered(controller_->samplerCombo()), known);
    QCOMPARE(headingCount(controller_->samplerCombo()), 0);

    controller_->setAdvanced(true);
    QCOMPARE(offered(controller_->samplerCombo()), known + other);
    // ONE separation, and it is readable -- a bare line does not say what is below it.
    QCOMPARE(headingCount(controller_->samplerCombo()), 1);
    bool labelled = false;
    for (int i = 0; i < controller_->samplerCombo()->count(); ++i)
    {
        if (controller_->samplerCombo()->itemText(i).contains(QStringLiteral("other samplers")))
            labelled = true;
    }
    QVERIFY(labelled);
}

void SamplingControllerTest::theHeadOfTheListIsIdenticalInBothModes()
{
    const QStringList known{QStringLiteral("dpmpp_2m"), QStringLiteral("euler"),
                            QStringLiteral("ddim")};
    const QStringList other{QStringLiteral("heun"), QStringLiteral("lms")};

    controller_->setAdvanced(false);
    controller_->applyFamilyChoices(grouped(known, other, QStringLiteral("dpmpp_2m")), false);
    const QStringList simple = offered(controller_->samplerCombo());

    controller_->setAdvanced(true);
    const QStringList advanced = offered(controller_->samplerCombo());

    // Not merely the same SET -- the same prefix, in the same order. Muscle memory has to survive
    // the upgrade: an entry the user already found must not move when Advanced grows the list.
    QCOMPARE(advanced.mid(0, simple.size()), simple);
    QCOMPARE(controller_->samplerCombo()->itemData(1).toString(), QStringLiteral("dpmpp_2m"));
}

void SamplingControllerTest::anAdvancedChoiceSurvivesASwitchToSimpleStillSelectedAndStillVisible()
{
    controller_->setAdvanced(true);
    controller_->applyFamilyChoices(
        grouped({QStringLiteral("er_sde"), QStringLiteral("euler")},
                {QStringLiteral("heun"), QStringLiteral("lms")}, QStringLiteral("er_sde")), false);
    controller_->samplerCombo()->setCurrentIndex(
        controller_->samplerCombo()->findData(QStringLiteral("heun")));
    QCOMPARE(controller_->imageSampler(), QStringLiteral("heun"));

    controller_->setAdvanced(false);

    // STILL SELECTED -- the render must not change because a disclosure checkbox moved.
    QCOMPARE(controller_->imageSampler(), QStringLiteral("heun"));
    // STILL VISIBLE -- and marked, rather than sitting in the known-good head pretending it was
    // always there. Dropping it from the list while leaving it selected would be the same lie.
    QVERIFY(controller_->samplerCombo()->findData(QStringLiteral("heun")) > 0);
    QCOMPARE(headingCount(controller_->samplerCombo()), 1);
    // The rest of the tail does NOT come with it: Simple is still Simple.
    QVERIFY(controller_->samplerCombo()->findData(QStringLiteral("lms")) < 0);

    controller_->setAdvanced(true);
    QCOMPARE(controller_->imageSampler(), QStringLiteral("heun"));
    QVERIFY(controller_->samplerCombo()->findData(QStringLiteral("lms")) > 0);
}

void SamplingControllerTest::aPreRulingTableStillRendersAsOneFlatList()
{
    // A table with no groups -- a worker that predates the ruling, or any of this file's other
    // cases -- is read as "all of these are known good, there is no remainder". Without that, every
    // such table would render as an empty Simple dropdown, which is the outcome the fallback in
    // family_sampling_choices exists to prevent, reintroduced on the other side of the wire.
    controller_->setAdvanced(false);
    controller_->applyFamilyChoices(table({QStringLiteral("euler"), QStringLiteral("dpmpp_2m")},
                                          {QStringLiteral("normal")}), false);
    QCOMPARE(offered(controller_->samplerCombo()),
             QStringList({QStringLiteral("euler"), QStringLiteral("dpmpp_2m")}));
    QCOMPARE(headingCount(controller_->samplerCombo()), 0);

    controller_->setAdvanced(true);
    QCOMPARE(offered(controller_->samplerCombo()),
             QStringList({QStringLiteral("euler"), QStringLiteral("dpmpp_2m")}));
    QCOMPARE(headingCount(controller_->samplerCombo()), 0);
}

void SamplingControllerTest::aStatedSeedOfZeroSurvives()
{
    controller_->seedRandomCheck()->setChecked(false);
    controller_->seedSpin()->setValue(0);
    QCOMPARE(controller_->seedSpin()->value(), 0);  // the widget accepts it
    QCOMPARE(controller_->draftSeed(), 0);          // and so does what leaves the widget
}

void SamplingControllerTest::aStatedSeedIsNotOtherwiseAltered()
{
    controller_->seedRandomCheck()->setChecked(false);
    for (int seed : {1, 42, 999999999, 2147483647})
    {
        controller_->seedSpin()->setValue(seed);
        QCOMPARE(controller_->draftSeed(), seed);
    }
}

void SamplingControllerTest::randomSeedsCanIncludeZero()
{
    // Not a distribution test -- only that the range starts where a seed starts. A lower bound of 1
    // is the same off-by-one as the clamp, and it is how "0 is a seed" quietly stops being true.
    controller_->seedRandomCheck()->setChecked(true);
    for (int i = 0; i < 200; ++i)
        QVERIFY(controller_->draftSeed() >= 0);
}

QTEST_MAIN(SamplingControllerTest)
#include "test_sampling_controller.moc"
