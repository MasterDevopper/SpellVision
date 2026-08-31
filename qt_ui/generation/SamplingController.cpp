#include "generation/SamplingController.h"

#include "widgets/ClickOnlyComboBox.h"

#include <QAbstractItemView>
#include <QCheckBox>
#include <QObject>
#include <QComboBox>
#include <QDoubleSpinBox>
#include <QJsonArray>
#include <QRandomGenerator>
#include <QSignalBlocker>
#include <QSizePolicy>
#include <QSpinBox>
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

void rebuildSamplingCombo(QComboBox *combo, const QJsonArray &values, const QString &keep)
{
    if (!combo)
        return;
    const QString current = combo->currentData().toString();
    const QSignalBlocker blocker(combo);
    combo->clear();
    combo->addItem(QStringLiteral("Auto / family default"), QStringLiteral("auto"));
    for (const QJsonValue &value : values)
    {
        const QString name = value.toString().trimmed();
        if (name.isEmpty() || name.compare(QLatin1String("auto"), Qt::CaseInsensitive) == 0)
            continue;
        combo->addItem(name, name);
    }
    const QString want = current.isEmpty() ? keep : current;
    if (want.isEmpty())
        return;
    const int idx = combo->findData(want);
    if (idx >= 0)
        combo->setCurrentIndex(idx);
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
    const QJsonArray samplers = table.value(QStringLiteral("samplers")).toArray();
    const QJsonArray schedulers = table.value(QStringLiteral("schedulers")).toArray();
    // An empty table used to return early, leaving the PREVIOUS family's samplers on screen. So
    // switching to a family that offers no choice -- cogvideox returns an empty table, and it is
    // right to -- showed sdxl's list, and picking one of those sent a sampler this family has never
    // heard of. Rebuilding with nothing leaves "Auto / family default", which is the honest answer.
    //
    // The two lists are handled independently on purpose: LTX has samplers and DELIBERATELY no
    // schedulers, because both its templates drive sigmas through ManualSigmas. Requiring both to
    // be non-empty would put it back in the stale case it was carved out of.
    QComboBox *sampler = videoMode ? videoSamplerCombo_ : samplerCombo_;
    QComboBox *scheduler = videoMode ? videoSchedulerCombo_ : schedulerCombo_;
    rebuildSamplingCombo(sampler, samplers, table.value(QStringLiteral("default_sampler")).toString());
    rebuildSamplingCombo(scheduler, schedulers, table.value(QStringLiteral("default_scheduler")).toString());
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
