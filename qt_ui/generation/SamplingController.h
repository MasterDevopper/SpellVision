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
    // The table carries BOTH groups (`known_good_samplers` / `other_samplers`, and the scheduler
    // pair) since the Doc 62 ruling. A table from before it -- or any caller that only has the flat
    // `samplers` -- is read as "all of these are known good, there is no remainder", which is
    // exactly what this control did before the split existed.
    void applyFamilyChoices(const QJsonObject &table, bool videoMode);
    // Simple lists the known-good group alone; Advanced lists it, then a labelled separation, then
    // the rest of what the build offers. The MODE lives here rather than in every call site because
    // a disclosure toggle must re-render lists that were built under the other mode, and the one
    // rule about what a switch may do to the current selection -- nothing -- then has one home.
    void setAdvanced(bool advanced);
    bool advanced() const { return advanced_; }

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
    // Re-rendered on a disclosure change, so the last table each combo pair was built from is kept
    // rather than asked for again -- the page's provider is a cache read on the image path and a
    // worker round-trip on the model path, and a mode toggle must not depend on either.
    void renderCombos(bool videoMode);

    QJsonObject imageTable_;
    QJsonObject videoTable_;
    bool advanced_ = false;

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
