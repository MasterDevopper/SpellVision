#include "generation/UpscaleController.h"

#include "generation/CockpitWidgetKit.h"
#include "widgets/ClickOnlyComboBox.h"

#include <QComboBox>
#include <QDoubleSpinBox>
#include <QLabel>
#include <QSignalBlocker>
#include <QVBoxLayout>
#include <QVariant>
#include <QWidget>

namespace spellvision::generation
{
namespace
{

// The tier's scale factors. Two, because they are the two an intent-level control should offer:
// "twice as big" and "four times as big". Anything else is a number, and a number is Advanced.
constexpr double kScaleX2 = 2.0;
constexpr double kScaleX4 = 4.0;

// The method a tier means. `model` is the only one that adds detail rather than pixels -- see
// tests/test_upscale_render_gate.py, where it measures x8.46 the Laplacian variance of a resample
// at identical dimensions. An intent-level "make it bigger" should mean the good one; the
// resampling filters stay available in Advanced for when a plain resize is what is wanted.
const QString &modelMethod()
{
    static const QString value = QStringLiteral("model");
    return value;
}

int indexForTier(QComboBox *combo, UpscaleController::Tier tier)
{
    if (!combo)
        return -1;
    return combo->findData(static_cast<int>(tier));
}

} // namespace

UpscaleController::UpscaleController(QObject *parent) : QObject(parent) {}

UpscaleController::Settings UpscaleController::settingsForTier(Tier tier)
{
    switch (tier)
    {
    case Tier::Off:
        return {false, QString(), 1.0};
    case Tier::X2:
        return {true, modelMethod(), kScaleX2};
    case Tier::X4:
        return {true, modelMethod(), kScaleX4};
    case Tier::Custom:
    default:
        // Custom describes the controls rather than dictating to them, so it has no settings of its
        // own. Selecting it deliberately changes nothing: it is the name for "whatever is below".
        return {true, QString(), 0.0};
    }
}

UpscaleController::Tier UpscaleController::tierForSettings(bool enabled, const QString &method, double scale)
{
    if (!enabled)
        return Tier::Off;
    if (method.compare(modelMethod(), Qt::CaseInsensitive) != 0)
        return Tier::Custom;
    if (qFuzzyCompare(scale, kScaleX2))
        return Tier::X2;
    if (qFuzzyCompare(scale, kScaleX4))
        return Tier::X4;
    return Tier::Custom;
}

QString UpscaleController::tierLabel(Tier tier)
{
    switch (tier)
    {
    case Tier::Off:
        return QStringLiteral("Off");
    case Tier::X2:
        return QStringLiteral("2× larger");
    case Tier::X4:
        return QStringLiteral("4× larger");
    case Tier::Custom:
    default:
        return QStringLiteral("Custom");
    }
}

void UpscaleController::create(QWidget *parent)
{
    row_ = new QWidget(parent);
    row_->setObjectName(QStringLiteral("UpscaleRow"));
    auto *layout = new QVBoxLayout(row_);
    layout->setContentsMargins(0, 0, 0, 0);

    layout->addWidget(new QLabel(QStringLiteral("Upscale"), row_));
    tierCombo_ = new spellvision::widgets::ClickOnlyComboBox(row_);
    for (const Tier tier : {Tier::Off, Tier::X2, Tier::X4, Tier::Custom})
        tierCombo_->addItem(tierLabel(tier), static_cast<int>(tier));
    configureComboBox(tierCombo_);
    layout->addWidget(tierCombo_);

    // The raw knobs live inside the same card, below the intent. Advanced reveals them where they
    // already are; it never moves the tier somewhere else.
    advancedGroup_ = new QWidget(row_);
    auto *advanced = new QVBoxLayout(advancedGroup_);
    advanced->setContentsMargins(0, 0, 0, 0);

    methodCombo_ = new spellvision::widgets::ClickOnlyComboBox(advancedGroup_);
    methodCombo_->addItem(QStringLiteral("Upscale model (ESRGAN)"), QStringLiteral("model"));
    methodCombo_->addItem(QStringLiteral("Lanczos"), QStringLiteral("lanczos"));
    methodCombo_->addItem(QStringLiteral("Bicubic"), QStringLiteral("bicubic"));
    methodCombo_->addItem(QStringLiteral("Bilinear"), QStringLiteral("bilinear"));
    methodCombo_->addItem(QStringLiteral("Nearest"), QStringLiteral("nearest"));
    configureComboBox(methodCombo_);
    advanced->addWidget(new QLabel(QStringLiteral("Method"), advancedGroup_));
    advanced->addWidget(methodCombo_);

    scaleSpin_ = new QDoubleSpinBox(advancedGroup_);
    scaleSpin_->setRange(1.0, 4.0);
    scaleSpin_->setSingleStep(0.5);
    scaleSpin_->setValue(kScaleX2);
    scaleSpin_->setDecimals(2);
    configureDoubleSpinBox(scaleSpin_);
    advanced->addWidget(new QLabel(QStringLiteral("Scale"), advancedGroup_));
    advanced->addWidget(scaleSpin_);

    modelCombo_ = new spellvision::widgets::ClickOnlyComboBox(advancedGroup_);
    modelCombo_->addItem(QStringLiteral("Auto (generalist)"), QString());
    configureComboBox(modelCombo_);
    advanced->addWidget(new QLabel(QStringLiteral("Upscale model"), advancedGroup_));
    advanced->addWidget(modelCombo_);

    layout->addWidget(advancedGroup_);

    connect(tierCombo_, &QComboBox::currentIndexChanged, this, [this](int) { applyTierToControls(); });
    connect(methodCombo_, &QComboBox::currentIndexChanged, this, [this](int) { refreshTierFromControls(); });
    connect(scaleSpin_, &QDoubleSpinBox::valueChanged, this, [this](double) { refreshTierFromControls(); });

    setAdvanced(false);
}

void UpscaleController::setAdvanced(bool advanced)
{
    if (advancedGroup_)
        advancedGroup_->setVisible(advanced);
}

void UpscaleController::setModelCatalog(const QVector<spellvision::assets::CatalogEntry> &entries)
{
    if (!modelCombo_)
        return;
    const QString current = comboStoredValue(modelCombo_);
    const QSignalBlocker blocker(modelCombo_);
    modelCombo_->clear();
    modelCombo_->addItem(QStringLiteral("Auto (generalist)"), QString());
    for (const spellvision::assets::CatalogEntry &entry : entries)
        modelCombo_->addItem(entry.display, entry.value);
    if (!current.isEmpty())
    {
        const int index = modelCombo_->findData(current);
        if (index >= 0)
            modelCombo_->setCurrentIndex(index);
    }
}

UpscaleController::Tier UpscaleController::tier() const
{
    if (!tierCombo_)
        return Tier::Off;
    return static_cast<Tier>(tierCombo_->currentData().toInt());
}

bool UpscaleController::enabled() const
{
    // Derived, never stored twice. A separate checkbox beside the tier could disagree with it, and
    // whichever the request builder happened to read would be the answer.
    return tier() != Tier::Off;
}

QString UpscaleController::method() const
{
    if (!enabled())
        return QStringLiteral("none");
    return methodCombo_ ? comboStoredValue(methodCombo_) : modelMethod();
}

double UpscaleController::scale() const
{
    return scaleSpin_ ? scaleSpin_->value() : 1.0;
}

QString UpscaleController::model() const
{
    return modelCombo_ ? comboStoredValue(modelCombo_) : QString();
}

void UpscaleController::applyTierToControls()
{
    if (applying_ || !tierCombo_)
        return;
    const Tier chosen = tier();
    if (chosen == Tier::Custom)
        return; // names the controls; does not overwrite them

    const Settings settings = settingsForTier(chosen);
    if (!settings.enabled)
        return; // Off leaves the raw values alone, so turning it back on restores what was there

    applying_ = true;
    if (methodCombo_)
    {
        const int index = methodCombo_->findData(settings.method);
        if (index >= 0)
            methodCombo_->setCurrentIndex(index);
    }
    if (scaleSpin_)
        scaleSpin_->setValue(settings.scale);
    applying_ = false;
}

void UpscaleController::refreshTierFromControls()
{
    if (applying_ || !tierCombo_)
        return;
    if (tier() == Tier::Off)
        return; // editing the knobs while Off does not silently switch it on

    const Tier derived = tierForSettings(true, methodCombo_ ? comboStoredValue(methodCombo_) : QString(),
                                         scaleSpin_ ? scaleSpin_->value() : 0.0);
    const int index = indexForTier(tierCombo_, derived);
    if (index < 0 || index == tierCombo_->currentIndex())
        return;
    applying_ = true;
    tierCombo_->setCurrentIndex(index);
    applying_ = false;
}

} // namespace spellvision::generation
