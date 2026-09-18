#pragma once

#include <QJsonObject>
#include <QObject>
#include <QString>

class QCheckBox;
class QComboBox;
class QDoubleSpinBox;
class QSpinBox;
class QWidget;

namespace spellvision::generation
{

class SamplingController final : public QObject
{
public:
    explicit SamplingController(QObject *parent = nullptr);

    void create(QWidget *parent);
    void applyFamilyChoices(const QJsonObject &table, bool videoMode);

    QComboBox *samplerCombo() const { return samplerCombo_; }
    QComboBox *schedulerCombo() const { return schedulerCombo_; }
    QComboBox *videoSamplerCombo() const { return videoSamplerCombo_; }
    QComboBox *videoSchedulerCombo() const { return videoSchedulerCombo_; }
    QSpinBox *stepsSpin() const { return stepsSpin_; }
    QDoubleSpinBox *cfgSpin() const { return cfgSpin_; }
    // Distilled guidance (FluxGuidance / embedded_guidance_scale), Advanced-only. 0.00 is the
    // "Auto (follow CFG)" sentinel, not a guidance of zero -- see `guidance()`.
    QDoubleSpinBox *guidanceSpin() const { return guidanceSpin_; }
    QSpinBox *seedSpin() const { return seedSpin_; }
    QCheckBox *seedRandomCheck() const { return seedRandomCheck_; }

    QString imageSampler() const;
    QString imageScheduler() const;
    QString videoSampler() const;
    QString videoScheduler() const;
    int steps() const;
    double cfg() const;
    // 0.0 when the box is on Auto, which is what the request builder must NOT send.
    double guidance() const;
    int draftSeed() const;

private:
    QComboBox *samplerCombo_ = nullptr;
    QComboBox *schedulerCombo_ = nullptr;
    QComboBox *videoSamplerCombo_ = nullptr;
    QComboBox *videoSchedulerCombo_ = nullptr;
    QSpinBox *stepsSpin_ = nullptr;
    QDoubleSpinBox *cfgSpin_ = nullptr;
    QDoubleSpinBox *guidanceSpin_ = nullptr;
    QSpinBox *seedSpin_ = nullptr;
    QCheckBox *seedRandomCheck_ = nullptr;
};

} // namespace spellvision::generation
