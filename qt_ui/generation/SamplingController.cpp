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
    seedSpin_->setRange(1, 999999999);
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
    if (samplers.isEmpty() && schedulers.isEmpty())
        return;
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
        return static_cast<int>(QRandomGenerator::global()->bounded(1, 2000000000));
    return seedSpin_ ? qMax(1, seedSpin_->value()) : 1;
}

} // namespace spellvision::generation
