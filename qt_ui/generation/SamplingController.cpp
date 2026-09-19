#include "generation/SamplingController.h"

#include "ThemeManager.h"
#include "widgets/ClickOnlyComboBox.h"

#include <QAbstractItemView>
#include <QBrush>
#include <QCheckBox>
#include <QObject>
#include <QComboBox>
#include <QDoubleSpinBox>
#include <QJsonArray>
#include <QRandomGenerator>
#include <QSignalBlocker>
#include <QSizePolicy>
#include <QSpinBox>
#include <QStandardItemModel>
#include <QStringList>
#include <QtGlobal>
#include <QWidget>

namespace spellvision::generation
{
namespace
{

void configureCombo(QComboBox *combo)
{
    if (!combo)
        return;
    combo->setFocusPolicy(Qt::StrongFocus);
    combo->setMaxVisibleItems(18);
    combo->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon);
    combo->setMinimumContentsLength(10);
    combo->setMinimumWidth(0);
    combo->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    if (combo->view())
    {
        combo->view()->setVerticalScrollMode(QAbstractItemView::ScrollPerPixel);
        combo->view()->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
        combo->view()->setTextElideMode(Qt::ElideMiddle);
    }
}

void configureSpin(QSpinBox *spin)
{
    if (!spin)
        return;
    spin->setMinimumWidth(0);
    spin->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
}

void configureDouble(QDoubleSpinBox *spin)
{
    if (!spin)
        return;
    spin->setMinimumWidth(0);
    spin->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
}

QComboBox *makeAutoCombo(QWidget *parent)
{
    auto *combo = new spellvision::widgets::ClickOnlyComboBox(parent);
    combo->addItem(QStringLiteral("Auto / family default"), QStringLiteral("auto"));
    configureCombo(combo);
    return combo;
}

// Sampler and scheduler are built from the same factory and carry the same "auto" entry, so a test
// that finds one by its CONTENTS finds whichever `findChildren` returns first. That is not a
// hypothetical: a row-visibility case written that way passed with the defect planted back in,
// because it was asserting about the wrong combo. Naming them is what makes the assertion land on
// the control it names.
void nameSamplingCombo(QComboBox *combo, const char *name)
{
    if (combo)
        combo->setObjectName(QString::fromUtf8(name));
}

QStringList entryNames(const QJsonArray &values)
{
    QStringList names;
    for (const QJsonValue &value : values)
    {
        const QString name = value.toString().trimmed();
        // "auto" is the placeholder this control writes itself; a table that also named it would
        // produce two, one of which sends the string rather than the sentinel.
        if (name.isEmpty() || name.compare(QLatin1String("auto"), Qt::CaseInsensitive) == 0)
            continue;
        if (!names.contains(name))
            names.append(name);
    }
    return names;
}

// A readable heading rather than a bare rule. `insertSeparator` alone draws a line, and a line does
// not say WHAT is below it -- the ruling is that the continuation is "distinctly separated", which
// a user can only act on if the separation is labelled. Disabled and unselectable, so arrow keys
// step over it and it can never become the value sent.
void appendGroupHeading(QComboBox *combo, const QString &text)
{
    combo->insertSeparator(combo->count());
    combo->addItem(text);
    const int row = combo->count() - 1;
    combo->setItemData(row,
                       QBrush(::ThemeManager::instance().color(::ThemeManager::Color::TextLo)),
                       Qt::ForegroundRole);
    if (auto *model = qobject_cast<QStandardItemModel *>(combo->model()))
    {
        if (QStandardItem *item = model->item(row))
            item->setFlags(item->flags() & ~(Qt::ItemIsEnabled | Qt::ItemIsSelectable));
    }
}

// ONE dropdown, two groups, and the mode decides only how far down it goes.
//
// Simple  : Auto, then `known`.
// Advanced: Auto, then `known`, a labelled separation, then `other`.
//
// The part above the separation is identical in both modes, which is what makes this "Advanced
// reveals in place" (CLAUDE.md S2) rather than a second list: nothing a user already found moves
// when they switch.
//
// AND THE SWITCH NEVER CHANGES THE VALUE. A sampler picked in Advanced that lives in `other` is
// carried into Simple under its own heading and stays selected. Dropping it would silently swap the
// render for one the user did not ask for, with the control showing the replacement as though it
// had always been there -- the hidden output-changing state this codebase ran a whole hardening
// pass against. Showing it, labelled as the outlier it is, is the honest form of the same screen.
void rebuildSamplingCombo(QComboBox *combo, const QJsonArray &known, const QJsonArray &other,
                          const QString &keep, bool advanced, const QString &noun)
{
    if (!combo)
        return;
    const QString current = combo->currentData().toString();
    const QSignalBlocker blocker(combo);
    combo->clear();
    combo->addItem(QStringLiteral("Auto / family default"), QStringLiteral("auto"));

    const QStringList knownNames = entryNames(known);
    for (const QString &name : knownNames)
        combo->addItem(name, name);

    const QStringList otherNames = entryNames(other);
    if (advanced)
    {
        if (!otherNames.isEmpty())
        {
            appendGroupHeading(combo, QStringLiteral("other %1 this build offers").arg(noun));
            for (const QString &name : otherNames)
                combo->addItem(name, name);
        }
    }
    else if (!current.isEmpty() && !knownNames.contains(current) && otherNames.contains(current))
    {
        appendGroupHeading(combo, QStringLiteral("your Advanced choice"));
        combo->addItem(current, current);
    }

    const QString want = current.isEmpty() ? keep : current;
    if (want.isEmpty())
        return;
    const int idx = combo->findData(want);
    if (idx >= 0)
        combo->setCurrentIndex(idx);
}

// The two groups a table carries, with the pre-ruling shape read as "all known good, no remainder"
// so a caller that still hands over the flat list gets exactly the control it had before.
QJsonArray groupOf(const QJsonObject &table, const QString &groupKey, const QString &flatKey)
{
    if (table.contains(groupKey))
        return table.value(groupKey).toArray();
    return table.value(flatKey).toArray();
}

QJsonArray remainderOf(const QJsonObject &table, const QString &groupKey)
{
    return table.contains(groupKey) ? table.value(groupKey).toArray() : QJsonArray();
}

QString comboValue(const QComboBox *combo, const QString &fallback = QStringLiteral("auto"))
{
    if (!combo)
        return fallback;
    const QString data = combo->currentData().toString().trimmed();
    return data.isEmpty() ? combo->currentText().trimmed() : data;
}

} // namespace

SamplingController::SamplingController(QObject *parent)
    : QObject(parent)
{
}

void SamplingController::create(QWidget *parent)
{
    samplerCombo_ = makeAutoCombo(parent);
    schedulerCombo_ = makeAutoCombo(parent);
    nameSamplingCombo(samplerCombo_, "samplingSamplerCombo");
    nameSamplingCombo(schedulerCombo_, "samplingSchedulerCombo");
    videoSamplerCombo_ = makeAutoCombo(parent);
    videoSchedulerCombo_ = makeAutoCombo(parent);

    stepsSpin_ = new QSpinBox(parent);
    stepsSpin_->setRange(1, 200);
    stepsSpin_->setValue(28);
    configureSpin(stepsSpin_);

    cfgSpin_ = new QDoubleSpinBox(parent);
    cfgSpin_->setDecimals(1);
    cfgSpin_->setSingleStep(0.5);
    cfgSpin_->setRange(0.0, 30.0);
    cfgSpin_->setValue(7.0);
    configureDouble(cfgSpin_);

    // Distilled guidance -- the number Flux and Hunyuan-video actually steer with, while their
    // sampler's real CFG is pinned. It had no control at all until 2026-09-18 (Doc 62 3e): the
    // builders read `req["guidance"]` and nothing in qt_ui ever put it there, so a model's
    // published figure was shown in the Models inspector and replaced by the cfg slider at render
    // time.
    //
    // TWO decimals, where cfg has one. That is not cosmetic: a published guidance is routinely 3.5
    // or 2.75, and it also keeps this box distinguishable from cfg for the tests that find these
    // widgets by shape rather than by a private pointer.
    //
    // 0.00 shows as "Auto (follow CFG)" and is the construction value, so the control appears
    // stating exactly what the app did before it existed. The request builder sends `guidance` only
    // above zero, so a user who never touches it changes nothing.
    guidanceSpin_ = new QDoubleSpinBox(parent);
    guidanceSpin_->setDecimals(2);
    guidanceSpin_->setSingleStep(0.25);
    guidanceSpin_->setRange(0.0, 100.0);
    guidanceSpin_->setValue(0.0);
    guidanceSpin_->setSpecialValueText(QStringLiteral("Auto (follow CFG)"));
    guidanceSpin_->setToolTip(QStringLiteral(
        "Distilled guidance for Flux and Hunyuan video -- the value that steers those families, "
        "while their sampler CFG is pinned. Auto follows the CFG box, which is what this app has "
        "always done. Other families ignore it."));
    configureDouble(guidanceSpin_);

    seedSpin_ = new QSpinBox(parent);
    // 0 is a seed. ComfyUI's KSampler declares seed with min 0, every graph builder now honours it
    // (comfy_graph_helpers.resolve_seed), and it is a value people type deliberately -- a minimum
    // of 1 made the one seed most likely to be typed the one seed unreachable.
    //
    // The upper bound was 999999999, below INT_MAX, so recalling a render whose seed was larger
    // clamped it silently and the re-render came back a different image. (A seed above 2^31 still
    // cannot be expressed here at all -- QSpinBox is int -- which is a known limit, not a fix.)
    seedSpin_->setRange(0, 2147483647);
    seedSpin_->setValue(1);
    configureSpin(seedSpin_);
    seedRandomCheck_ = new QCheckBox(QStringLiteral("Random"), parent);
    seedRandomCheck_->setChecked(true);
    seedSpin_->setEnabled(false);
    QObject::connect(seedRandomCheck_, &QCheckBox::toggled, seedSpin_, [this](bool on) {
        if (!seedSpin_)
            return;
        seedSpin_->setEnabled(!on);
        if (on)
            seedSpin_->setValue(1);
    });
}

void SamplingController::applyFamilyChoices(const QJsonObject &table, bool videoMode)
{
    // An empty table used to return early, leaving the PREVIOUS family's samplers on screen. So
    // switching to a family that offers no choice -- cogvideox returns an empty table, and it is
    // right to -- showed sdxl's list, and picking one of those sent a sampler this family has never
    // heard of. Rebuilding with nothing leaves "Auto / family default", which is the honest answer.
    //
    // The two lists are handled independently on purpose: LTX has samplers and DELIBERATELY no
    // schedulers, because both its templates drive sigmas through ManualSigmas. Requiring both to
    // be non-empty would put it back in the stale case it was carved out of.
    //
    // The table is KEPT, because a disclosure toggle has to rebuild these lists and has no provider
    // of its own to ask.
    (videoMode ? videoTable_ : imageTable_) = table;
    renderCombos(videoMode);
}

void SamplingController::setAdvanced(bool advanced)
{
    if (advanced_ == advanced)
        return;
    advanced_ = advanced;
    // BOTH pairs, not just the one on screen. A page switches between image and video modes without
    // passing through here, so re-rendering only the visible pair would leave the other built under
    // the previous disclosure -- the stale-list defect this control already carries a test for,
    // arriving by a door the test does not watch.
    renderCombos(false);
    renderCombos(true);
}

void SamplingController::renderCombos(bool videoMode)
{
    const QJsonObject &table = videoMode ? videoTable_ : imageTable_;
    QComboBox *sampler = videoMode ? videoSamplerCombo_ : samplerCombo_;
    QComboBox *scheduler = videoMode ? videoSchedulerCombo_ : schedulerCombo_;
    rebuildSamplingCombo(sampler,
                         groupOf(table, QStringLiteral("known_good_samplers"), QStringLiteral("samplers")),
                         remainderOf(table, QStringLiteral("other_samplers")),
                         table.value(QStringLiteral("default_sampler")).toString(),
                         advanced_, QStringLiteral("samplers"));
    rebuildSamplingCombo(scheduler,
                         groupOf(table, QStringLiteral("known_good_schedulers"), QStringLiteral("schedulers")),
                         remainderOf(table, QStringLiteral("other_schedulers")),
                         table.value(QStringLiteral("default_scheduler")).toString(),
                         advanced_, QStringLiteral("schedulers"));
}

QString SamplingController::imageSampler() const
{
    return comboValue(samplerCombo_);
}

QString SamplingController::imageScheduler() const
{
    return comboValue(schedulerCombo_);
}

QString SamplingController::videoSampler() const
{
    return comboValue(videoSamplerCombo_);
}

QString SamplingController::videoScheduler() const
{
    return comboValue(videoSchedulerCombo_);
}

int SamplingController::steps() const
{
    return stepsSpin_ ? stepsSpin_->value() : 0;
}

double SamplingController::cfg() const
{
    return cfgSpin_ ? cfgSpin_->value() : 0.0;
}

double SamplingController::guidance() const
{
    // The floor is the SENTINEL, returned as 0.0 so one caller decides what "Auto" means rather
    // than every reader re-deriving it from the special value text.
    return guidanceSpin_ ? guidanceSpin_->value() : 0.0;
}

int SamplingController::draftSeed() const
{
    if (seedRandomCheck_ && seedRandomCheck_->isChecked())
        return static_cast<int>(QRandomGenerator::global()->bounded(0, 2000000000));
    // NOT qMax(1, ...). The spin box was widened to accept 0 because 0 is a seed -- ComfyUI's
    // KSampler declares it as the minimum and every builder honours it through resolve_seed -- and
    // this clamp then turned every 0 the user typed back into 1 on the way out. The control said
    // yes and the value never left the widget, which is the same defect as the inert sampler
    // dropdown wearing different clothes.
    return seedSpin_ ? qMax(0, seedSpin_->value()) : 0;
}

} // namespace spellvision::generation
