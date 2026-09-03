#pragma once

#include <QObject>
#include <QString>
#include <QVector>

class QComboBox;
class QDoubleSpinBox;
class QWidget;

namespace spellvision::assets
{
struct CatalogEntry;
}

namespace spellvision::generation
{

// The cockpit's upscale group, owned in one place.
//
// Two things this exists to keep true:
//
// 1. **One source of truth for "is an upscale requested".** There used to be a checkbox AND a
//    method list, so "off" was sayable twice and the two could disagree. The tier IS the switch.
// 2. **Advanced reveals in place.** Simple shows the intent -- Off / 2x / 4x -- and Advanced adds
//    the method, the exact scale and the model *below it, in the same card*, rather than moving the
//    control somewhere else. Setting a tier writes the raw values; editing a raw value renames the
//    tier to Custom. Neither is a second opinion about what was requested: the request builder
//    still reads exactly one set of widgets.
class UpscaleController final : public QObject
{
public:
    enum class Tier
    {
        Off,
        X2,
        X4,
        Custom,
    };

    explicit UpscaleController(QObject *parent = nullptr);

    void create(QWidget *parent);
    QWidget *row() const { return row_; }

    // Advanced reveals the raw knobs; the tier stays put. Simple and Advanced show the same card.
    void setAdvanced(bool advanced);

    void setModelCatalog(const QVector<spellvision::assets::CatalogEntry> &entries);

    // What the request builder reads. `enabled` is derived from the tier, so there is no second
    // switch that can disagree with it.
    bool enabled() const;
    QString method() const;
    double scale() const;
    QString model() const;

    Tier tier() const;

    // Pure, so the mapping is testable without a widget -- which is the half that carries the
    // product decision.
    struct Settings
    {
        bool enabled = false;
        QString method;
        double scale = 1.0;
    };
    static Settings settingsForTier(Tier tier);
    static Tier tierForSettings(bool enabled, const QString &method, double scale);
    static QString tierLabel(Tier tier);

private:
    void applyTierToControls();
    void refreshTierFromControls();

    QWidget *row_ = nullptr;
    QWidget *advancedGroup_ = nullptr;
    QComboBox *tierCombo_ = nullptr;
    QComboBox *methodCombo_ = nullptr;
    QDoubleSpinBox *scaleSpin_ = nullptr;
    QComboBox *modelCombo_ = nullptr;
    bool applying_ = false;
};

} // namespace spellvision::generation
