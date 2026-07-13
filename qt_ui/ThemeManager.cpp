#include "ThemeManager.h"

#include <QSettings>
#include <QApplication>
#include <QDebug>
#include <QFont>
#include <QMetaEnum>
#include <QPalette>
#include <algorithm>
#include <cmath>

namespace
{
QString rgba(const QColor &color, qreal alphaMultiplier = 1.0)
{
    const int alpha = qBound(0, static_cast<int>(color.alphaF() * alphaMultiplier * 255.0), 255);
    return QStringLiteral("rgba(%1,%2,%3,%4)")
        .arg(color.red())
        .arg(color.green())
        .arg(color.blue())
        .arg(alpha);
}

QColor mix(const QColor &a, const QColor &b, qreal t)
{
    t = qBound(0.0, t, 1.0);
    return QColor(
        static_cast<int>(a.red() + (b.red() - a.red()) * t),
        static_cast<int>(a.green() + (b.green() - a.green()) * t),
        static_cast<int>(a.blue() + (b.blue() - a.blue()) * t),
        static_cast<int>(a.alpha() + (b.alpha() - a.alpha()) * t));
}

QColor withAlpha(const QColor &color, qreal alpha)
{
    QColor copy = color;
    copy.setAlphaF(qBound(0.0, alpha, 1.0));
    return copy;
}

qreal weight01(int value)
{
    return qBound(0.0, value / 100.0, 1.0);
}

qreal lerp(qreal a, qreal b, qreal t)
{
    return a + (b - a) * qBound(0.0, t, 1.0);
}
}

ThemeManager &ThemeManager::instance()
{
    static ThemeManager manager;
    return manager;
}

ThemeManager::ThemeManager(QObject *parent)
    : QObject(parent)
{
    load();
    rebuildColorTokens();
    runContrastSelfCheck(); // debug-only; restores the active preset before returning
    // Re-theme the escaping top-level popups (tooltips/menus/message boxes/combo popups) on every
    // theme switch. The initial application is done once from main() (qApp is guaranteed up there).
    connect(this, &ThemeManager::themeChanged, this, &ThemeManager::applyApplicationChrome);
}

qreal ThemeManager::contrastRatio(const QColor &fg, const QColor &bg)
{
    // WCAG relative luminance. sRGB channel -> linear, then 0.2126R+0.7152G+0.0722B.
    const auto lin = [](qreal c) { return c <= 0.03928 ? c / 12.92 : std::pow((c + 0.055) / 1.055, 2.4); };
    const auto lum = [&](const QColor &c) { return 0.2126 * lin(c.redF()) + 0.7152 * lin(c.greenF()) + 0.0722 * lin(c.blueF()); };

    // Composite a translucent foreground over the background first (WCAG assumes opaque colors).
    QColor f = fg;
    if (fg.alpha() < 255)
    {
        const qreal a = fg.alphaF();
        f = QColor::fromRgbF(
            fg.redF() * a + bg.redF() * (1.0 - a),
            fg.greenF() * a + bg.greenF() * (1.0 - a),
            fg.blueF() * a + bg.blueF() * (1.0 - a));
    }
    const qreal lf = lum(f);
    const qreal lb = lum(bg);
    return (std::max(lf, lb) + 0.05) / (std::min(lf, lb) + 0.05);
}

void ThemeManager::runContrastSelfCheck()
{
#ifndef QT_NO_DEBUG
    // Body text must clear WCAG AA 4.5:1; disabled text must stay >= 3:1 (dim, not invisible).
    // Scope: the primary content surfaces Surface0-2. Surface3 is overlays/drawers (a rarer
    // context: muted lands ~4.4:1 there on Obsidian, Ember disabled ~2.8:1 -- accepted edge, not
    // body-critical) and is deliberately not asserted here.
    static const Color kBodyText[] = { Color::TextHi, Color::TextMid, Color::TextLo };
    static const Color kSurfaces[] = { Color::Surface0, Color::Surface1, Color::Surface2 };
    const QMetaEnum me = QMetaEnum::fromType<Color>();
    const QStringList names = presetNames();

    const Preset original = preset_;
    int failures = 0;
    for (int p = 0; p <= static_cast<int>(Preset::Ember); ++p)
    {
        preset_ = static_cast<Preset>(p);
        rebuildColorTokens();
        const QString theme = names.value(p);
        for (const Color tx : kBodyText)
            for (const Color sf : kSurfaces)
            {
                const qreal r = contrastRatio(color(tx), color(sf));
                if (r < 4.5)
                {
                    ++failures;
                    qWarning().noquote() << QStringLiteral("[ThemeManager contrast] %1: body text %2 on %3 = %4:1 (< 4.5 WCAG AA)")
                                                .arg(theme, me.valueToKey(static_cast<int>(tx)), me.valueToKey(static_cast<int>(sf)))
                                                .arg(r, 0, 'f', 2);
                }
            }
        for (const Color sf : kSurfaces)
        {
            const qreal r = contrastRatio(color(Color::TextDisabled), color(sf));
            if (r < 3.0)
            {
                ++failures;
                qWarning().noquote() << QStringLiteral("[ThemeManager contrast] %1: disabled text on %2 = %3:1 (< 3.0)")
                                            .arg(theme, me.valueToKey(static_cast<int>(sf)))
                                            .arg(r, 0, 'f', 2);
            }
        }
    }
    preset_ = original;
    rebuildColorTokens(); // restore the active theme's tokens

    if (failures > 0)
        qWarning().noquote() << QStringLiteral("[ThemeManager contrast] %1 failing pair(s) above -- fix the token(s) in rebuildColorTokens()/the legacy text accessors.").arg(failures);
    Q_ASSERT_X(failures == 0, "ThemeManager::runContrastSelfCheck", "a theme text/surface pair is below its WCAG floor (see qWarning output)");
#endif
}

QStringList ThemeManager::presetNames() const
{
    return {
        QStringLiteral("Arcane Glass"),
        QStringLiteral("Obsidian Studio"),
        QStringLiteral("Neon Forge"),
        QStringLiteral("Ivory Holograph"),
        QStringLiteral("Ember"),
    };
}

int ThemeManager::presetIndex() const
{
    return static_cast<int>(preset_);
}

ThemeManager::Preset ThemeManager::preset() const
{
    return preset_;
}

QString ThemeManager::presetName() const
{
    const QStringList names = presetNames();
    const int index = presetIndex();
    return (index >= 0 && index < names.size()) ? names.at(index) : QStringLiteral("Arcane Glass");
}

bool ThemeManager::usePresetAccent() const
{
    return usePresetAccent_;
}

QColor ThemeManager::accentOverride() const
{
    return accentOverride_;
}

QColor ThemeManager::accentColor() const
{
    return usePresetAccent_ || !accentOverride_.isValid() ? presetAccent() : accentOverride_;
}

QColor ThemeManager::accentSecondary() const
{
    return presetAccentSecondary();
}

QColor ThemeManager::accentTertiary() const
{
    return presetAccentTertiary();
}

ThemeManager::AnimationQuality ThemeManager::animationQuality() const
{
    return animationQuality_;
}

QStringList ThemeManager::animationQualityNames() const
{
    return {QStringLiteral("Minimal"), QStringLiteral("Standard"),
            QStringLiteral("Rich"), QStringLiteral("Lavish")};
}

QString ThemeManager::animationQualityDescription(AnimationQuality quality) const
{
    switch (quality)
    {
    case AnimationQuality::Minimal:
        return QStringLiteral("Static bar, no motion. Lowest CPU/GPU — best for weak hardware or battery.");
    case AnimationQuality::Standard:
        return QStringLiteral("A gentle edge wave. Light motion, low cost.");
    case AnimationQuality::Rich:
        return QStringLiteral("Glowing gradient with a sweeping shimmer. The default premium look.");
    case AnimationQuality::Lavish:
        return QStringLiteral("Rich plus showpiece extras (rising bubbles). Highest cost — opt-in.");
    }
    return QString();
}

int ThemeManager::effectsWeight() const
{
    return effectsWeight_;
}

// --- Spacing Tokens Phase 1: token accessor definitions ---
//
// Constants, not preset-switched: the spacing rhythm and structural
// chrome dimensions are the same across all four themes. Only color
// varies per preset. Values mirror what T2I / Settings already use, so
// Phase 2 migration is a rename, not a reflow.

int ThemeManager::spacing(Spacing token) const
{
    switch (token)
    {
    case Spacing::Hairline: return 4;
    case Spacing::Tight:    return 8;
    case Spacing::Snug:     return 12;
    case Spacing::Card:     return 16;
    case Spacing::Section:  return 24;
    case Spacing::Gutter:   return 32;
    }
    return 16; // Spacing::Card -- safe default if a new token is unhandled.
}

int ThemeManager::chrome(Chrome token) const
{
    switch (token)
    {
    case Chrome::TitleBarHeight:    return 32;
    case Chrome::MenuBarHeight:     return 40;
    case Chrome::ModeRailWidth:     return 76;
    }
    return 32; // safe default.
}

int ThemeManager::fontSize(Type token) const
{
    switch (token)
    {
    case Type::Display:    return 28;
    case Type::Title:      return 20;
    case Type::Heading:    return 16;
    case Type::Subtitle:   return 14;
    case Type::Body:       return 12;
    case Type::BodyStrong: return 12;
    case Type::Detail:     return 11;
    case Type::Label:      return 11;
    case Type::Caption:    return 10;
    case Type::Micro:      return 9;
    }
    return 12; // Type::Body -- safe default.
}

int ThemeManager::fontWeight(Type token) const
{
    switch (token)
    {
    case Type::Display:    return 800;
    case Type::Title:      return 800;
    case Type::Heading:    return 800;
    case Type::Subtitle:   return 700;
    case Type::Body:       return 400;
    case Type::BodyStrong: return 600;
    case Type::Detail:     return 400;
    case Type::Label:      return 700;
    case Type::Caption:    return 700;
    case Type::Micro:      return 800;
    }
    return 400; // Type::Body -- safe default.
}

QFont ThemeManager::font(Type token) const
{
    QFont f;
    f.setPixelSize(fontSize(token));
    f.setWeight(static_cast<QFont::Weight>(fontWeight(token)));
    return f;
}

QString ThemeManager::fontCss(Type token) const
{
    return QStringLiteral("font-size:%1px;font-weight:%2;").arg(fontSize(token)).arg(fontWeight(token));
}

int ThemeManager::radiusCard() const
{
    return 14;
}

int ThemeManager::radiusControl() const
{
    return 9;
}

int ThemeManager::radiusPill() const
{
    return 999;
}

void ThemeManager::setPreset(Preset preset)
{
    if (preset_ == preset)
        return;

    preset_ = preset;
    rebuildColorTokens();
    save();
    emit themeChanged();
}

void ThemeManager::setPresetByIndex(int index)
{
    if (index < 0 || index >= presetNames().size())
        return;

    setPreset(static_cast<Preset>(index));
}

void ThemeManager::setUsePresetAccent(bool enabled)
{
    if (usePresetAccent_ == enabled)
        return;

    usePresetAccent_ = enabled;
    rebuildColorTokens();
    save();
    emit themeChanged();
}

void ThemeManager::setAccentOverride(const QColor &color)
{
    if (!color.isValid())
        return;

    accentOverride_ = color;
    usePresetAccent_ = false;
    rebuildColorTokens();
    save();
    emit themeChanged();
}

void ThemeManager::clearAccentOverride()
{
    accentOverride_ = QColor();
    usePresetAccent_ = true;
    rebuildColorTokens();
    save();
    emit themeChanged();
}

void ThemeManager::setEffectsWeight(int weight)
{
    weight = qBound(0, weight, 100);
    if (effectsWeight_ == weight)
        return;

    effectsWeight_ = weight;
    rebuildColorTokens();
    save();
    emit themeChanged();
}

void ThemeManager::setAnimationQuality(AnimationQuality quality)
{
    if (animationQuality_ == quality)
        return;

    // NOT a color change: no rebuildColorTokens, no themeChanged. Consumers (the progress
    // bar; glass later) react to animationQualityChanged. Orthogonal to the theme.
    animationQuality_ = quality;
    save();
    emit animationQualityChanged();
}

void ThemeManager::setAnimationQualityByIndex(int index)
{
    if (index < 0 || index >= animationQualityNames().size())
        return;
    setAnimationQuality(static_cast<AnimationQuality>(index));
}

void ThemeManager::resetToDefaults()
{
    preset_ = Preset::ArcaneGlass;
    usePresetAccent_ = true;
    accentOverride_ = QColor();
    effectsWeight_ = 68;
    rebuildColorTokens();
    save();
    emit themeChanged();
}

void ThemeManager::load()
{
    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    const int presetValue = settings.value(QStringLiteral("appearance/themePreset"), static_cast<int>(Preset::ArcaneGlass)).toInt();
    preset_ = static_cast<Preset>(qBound(0, presetValue, presetNames().size() - 1));
    usePresetAccent_ = settings.value(QStringLiteral("appearance/usePresetAccent"), true).toBool();
    accentOverride_ = settings.value(QStringLiteral("appearance/accentOverride")).value<QColor>();
    effectsWeight_ = qBound(0, settings.value(QStringLiteral("appearance/effectsWeight"), 68).toInt(), 100);
    animationQuality_ = static_cast<AnimationQuality>(
        qBound(0, settings.value(QStringLiteral("ui/animationQuality"),
                                 static_cast<int>(AnimationQuality::Rich)).toInt(), 3));
}

void ThemeManager::save() const
{
    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    settings.setValue(QStringLiteral("appearance/themePreset"), static_cast<int>(preset_));
    settings.setValue(QStringLiteral("appearance/usePresetAccent"), usePresetAccent_);
    settings.setValue(QStringLiteral("appearance/accentOverride"), accentOverride_);
    settings.setValue(QStringLiteral("appearance/effectsWeight"), effectsWeight_);
    settings.setValue(QStringLiteral("ui/animationQuality"), static_cast<int>(animationQuality_));
}

QColor ThemeManager::presetAccent() const
{
    switch (preset_)
    {
    case Preset::ArcaneGlass: return QColor(QStringLiteral("#7C5CFF"));
    case Preset::ObsidianStudio: return QColor(QStringLiteral("#7aa2ff"));
    case Preset::NeonForge: return QColor(QStringLiteral("#34b4ff"));
    case Preset::IvoryHolograph: return QColor(QStringLiteral("#6f52e6")); // darkened from #8f79ff so it clears 4.5:1 as link/label text on the near-white surfaces (was 3.1:1); still violet, and white-on-accent improves too
    case Preset::Ember: return color(Color::Accent);
    }
    return QColor(QStringLiteral("#8b6cff"));
}

QColor ThemeManager::presetAccentSecondary() const
{
    switch (preset_)
    {
    case Preset::ArcaneGlass: return QColor(QStringLiteral("#5B4BD6"));
    case Preset::ObsidianStudio: return QColor(QStringLiteral("#9cb6dd"));
    case Preset::NeonForge: return QColor(QStringLiteral("#d55cff"));
    case Preset::IvoryHolograph: return QColor(QStringLiteral("#79b9ff"));
    case Preset::Ember: return color(Color::AccentSecondary);
    }
    return QColor(QStringLiteral("#6f8cff"));
}

QColor ThemeManager::presetAccentTertiary() const
{
    switch (preset_)
    {
    case Preset::ArcaneGlass: return QColor(QStringLiteral("#C6B6FF"));
    case Preset::ObsidianStudio: return QColor(QStringLiteral("#d7e2f0"));
    case Preset::NeonForge: return QColor(QStringLiteral("#67f4ff"));
    case Preset::IvoryHolograph: return QColor(QStringLiteral("#d9ebff"));
    case Preset::Ember: return color(Color::AccentTertiary);
    }
    return QColor(QStringLiteral("#6fd3ff"));
}

QColor ThemeManager::background0() const
{
    switch (preset_)
    {
    case Preset::ArcaneGlass: return QColor(QStringLiteral("#0A0B12"));
    case Preset::ObsidianStudio: return QColor(QStringLiteral("#0b0f16"));
    case Preset::NeonForge: return QColor(QStringLiteral("#070b12"));
    case Preset::IvoryHolograph: return QColor(QStringLiteral("#eff3fa"));
    case Preset::Ember: return color(Color::Surface0);
    }
    return QColor(QStringLiteral("#0A0B12"));
}

QColor ThemeManager::background1() const
{
    switch (preset_)
    {
    case Preset::ArcaneGlass: return QColor(QStringLiteral("#0D0F18"));
    case Preset::ObsidianStudio: return QColor(QStringLiteral("#141a24"));
    case Preset::NeonForge: return QColor(QStringLiteral("#0d1421"));
    case Preset::IvoryHolograph: return QColor(QStringLiteral("#dfe8f5"));
    case Preset::Ember: return mix(color(Color::Surface0), color(Color::Surface1), 0.5);
    }
    return QColor(QStringLiteral("#0D0F18"));
}

QColor ThemeManager::surface0() const
{
    switch (preset_)
    {
    case Preset::ArcaneGlass: return QColor(QStringLiteral("#13161F"));
    case Preset::ObsidianStudio: return QColor(QStringLiteral("#1b222e"));
    case Preset::NeonForge: return QColor(QStringLiteral("#141b2a"));
    case Preset::IvoryHolograph: return QColor(QStringLiteral("#f6f9fe"));
    case Preset::Ember: return color(Color::Surface1);
    }
    return QColor(QStringLiteral("#13161F"));
}

QColor ThemeManager::surface1() const
{
    switch (preset_)
    {
    case Preset::ArcaneGlass: return QColor(QStringLiteral("#171B27"));
    case Preset::ObsidianStudio: return QColor(QStringLiteral("#252d3a"));
    case Preset::NeonForge: return QColor(QStringLiteral("#1e2740"));
    case Preset::IvoryHolograph: return QColor(QStringLiteral("#ebf1fb"));
    case Preset::Ember: return color(Color::Surface2);
    }
    return QColor(QStringLiteral("#171B27"));
}

QColor ThemeManager::textPrimary() const
{
    if (preset_ == Preset::Ember) return color(Color::TextHi);
    return preset_ == Preset::IvoryHolograph ? QColor(QStringLiteral("#132033")) : QColor(QStringLiteral("#E9EBF4"));
}

QColor ThemeManager::textSecondary() const
{
    if (preset_ == Preset::Ember) return color(Color::TextMid);
    return preset_ == Preset::IvoryHolograph ? QColor(QStringLiteral("#42546d")) : QColor(QStringLiteral("#9DA3B8"));
}

QColor ThemeManager::textMuted() const
{
    if (preset_ == Preset::Ember) return color(Color::TextLo);
    // Muted text lightened to clear WCAG AA 4.5:1 on the lightest surface it sits on (Surface2):
    // shared dark #646A82 (3.2-2.6:1, failed all dark themes) -> #9096ad; Ivory #6c7d95 (3.7:1)
    // darkened -> #586780. Same blue-grey hue, still clearly dimmer than TextMid. Gated below.
    return preset_ == Preset::IvoryHolograph ? QColor(QStringLiteral("#586780")) : QColor(QStringLiteral("#9096ad"));
}

QColor ThemeManager::borderColor() const
{
    const qreal t = weight01(effectsWeight_);
    return mix(surface1(), accentColor(), 0.18 + t * 0.24);
}

QColor ThemeManager::inputSurface() const
{
    if (preset_ == Preset::Ember) return color(Color::Surface0);
    return preset_ == Preset::IvoryHolograph ? QColor(QStringLiteral("#ffffff")) : QColor(QStringLiteral("#0f1520"));
}

QColor ThemeManager::successColor() const
{
    // The semantic ready/online/success signal. In ArcaneGlass this is the ONLY
    // place cyan lives — the accent roles are all violet, so cyan reads as a
    // distinct status, not a decorative third accent. Other presets keep green.
    switch (preset_)
    {
    case Preset::ArcaneGlass: return QColor(QStringLiteral("#34D6E6"));
    case Preset::ObsidianStudio: return QColor(QStringLiteral("#42c480"));
    case Preset::NeonForge: return QColor(QStringLiteral("#42c480"));
    case Preset::IvoryHolograph: return QColor(QStringLiteral("#42c480"));
    case Preset::Ember: return color(Color::Success);
    }
    return QColor(QStringLiteral("#42c480"));
}

QColor ThemeManager::warningColor() const
{
    if (preset_ == Preset::Ember) return color(Color::Warning);
    return QColor(QStringLiteral("#E8B23A"));
}

QColor ThemeManager::errorColor() const
{
    if (preset_ == Preset::Ember) return color(Color::Error);
    return QColor(QStringLiteral("#d85d73"));
}

// --- Canonical color tokens (Doc 16) ---
//
// Fills colorTokens_ for the active preset. ArcaneGlass and Ember are authored
// explicitly (their full palettes live here); the other three presets derive their
// canonical tokens from the existing per-preset accessors + algorithmic states, so
// switching to them is safe until they get their own art-directed value-sets. The
// ArcaneGlass values here are the authored design values and are the go-forward
// source of truth — the legacy per-preset accessors (surface0()/textPrimary()/...)
// keep the pre-migration values used by not-yet-migrated stylesheet generators, and
// are reconciled to these as later phases migrate each generator.
void ThemeManager::rebuildColorTokens()
{
    auto put = [this](Color c, const QColor &v) { colorTokens_[static_cast<int>(c)] = v; };

    if (preset_ == Preset::ArcaneGlass)
    {
        put(Color::Surface0, QColor(QStringLiteral("#0A0B12")));
        put(Color::Surface1, QColor(QStringLiteral("#13161F")));
        put(Color::Surface2, QColor(QStringLiteral("#171B27")));
        put(Color::Surface3, QColor(QStringLiteral("#1D2230")));
        put(Color::TextHi, QColor(QStringLiteral("#E9EBF4")));
        put(Color::TextMid, QColor(QStringLiteral("#9DA3B8")));
        put(Color::TextLo, QColor(QStringLiteral("#9096ad")));      // was #646A82 (3.2:1 on Surface2, failed AA); lightened to clear 4.5:1
        put(Color::TextDisabled, QColor(QStringLiteral("#666d86"))); // was #454A5E (2.0:1, invisible); lightened to >=3:1, still dimmer than TextLo
        put(Color::Accent, QColor(QStringLiteral("#7C5CFF")));
        put(Color::AccentHover, QColor(QStringLiteral("#9A7DFF")));
        put(Color::AccentActive, QColor(QStringLiteral("#6B4AE8")));
        put(Color::AccentDisabled, QColor(QStringLiteral("#4A4470")));
        put(Color::AccentGlow, QColor(124, 92, 255, 90));
        put(Color::AccentSubtle, QColor(124, 92, 255, 26));
        put(Color::AccentSecondary, QColor(QStringLiteral("#5B4BD6")));
        put(Color::AccentTertiary, QColor(QStringLiteral("#C6B6FF")));
        put(Color::Border, QColor(150, 160, 186, 36));      // ~.14 platinum hairline
        put(Color::BorderStrong, QColor(150, 160, 186, 56)); // ~.22 emphasis
        put(Color::BorderSubtle, QColor(150, 160, 186, 20)); // ~.08 faint
        put(Color::Success, QColor(QStringLiteral("#34D6E6"))); // ready/online — the only cyan
        put(Color::Warning, QColor(QStringLiteral("#E8B23A")));
        put(Color::Error, QColor(QStringLiteral("#D85D73")));
        put(Color::Info, QColor(QStringLiteral("#4C9AE6")));
        put(Color::GlassFill, QColor(19, 22, 31, 220));      // surface1 @ ~.86
        put(Color::GlassGlow, QColor(124, 92, 255, 40));
        put(Color::GlassHighlight, QColor(196, 201, 220, 30)); // platinum top edge
        return;
    }

    if (preset_ == Preset::Ember)
    {
        // Ember — a warm ember/orange-on-navy palette (authored, first-class theme).
        // These token values are the single source of truth; the legacy per-preset
        // accessors return them for Preset::Ember.
        put(Color::Surface0, QColor(QStringLiteral("#081428")));
        put(Color::Surface1, QColor(QStringLiteral("#0E2140")));
        put(Color::Surface2, QColor(QStringLiteral("#143056")));
        put(Color::Surface3, QColor(QStringLiteral("#1B3E6E")));
        put(Color::TextHi, QColor(QStringLiteral("#FFEAC7")));
        put(Color::TextMid, QColor(QStringLiteral("#FFC878")));
        put(Color::TextLo, QColor(QStringLiteral("#C88A3E")));
        put(Color::TextDisabled, QColor(QStringLiteral("#a17d47"))); // was #7A5A2E (2.1:1 on Surface2, invisible); warmer/lighter to >=3:1, still dimmer than the #C88A3E muted
        put(Color::Accent, QColor(QStringLiteral("#FF8A2A")));
        put(Color::AccentHover, QColor(QStringLiteral("#FFB268")));
        put(Color::AccentActive, QColor(QStringLiteral("#E06E14")));
        put(Color::AccentDisabled, QColor(QStringLiteral("#7C5A34")));
        put(Color::AccentGlow, QColor(255, 138, 42, 120));
        put(Color::AccentSubtle, QColor(255, 138, 42, 40));
        put(Color::AccentSecondary, QColor(QStringLiteral("#D0662A"))); // deep ember
        put(Color::AccentTertiary, QColor(QStringLiteral("#FFD9A0")));  // ember highlight
        put(Color::Border, QColor(255, 180, 90, 64));
        put(Color::BorderStrong, QColor(255, 180, 90, 120));
        put(Color::BorderSubtle, QColor(255, 180, 90, 30));
        put(Color::Success, QColor(QStringLiteral("#5CFF9A")));
        put(Color::Warning, QColor(QStringLiteral("#FFD23A")));
        put(Color::Error, QColor(QStringLiteral("#FF556E")));
        put(Color::Info, QColor(QStringLiteral("#35CFFF")));
        put(Color::GlassFill, QColor(14, 33, 64, 224));
        put(Color::GlassGlow, QColor(255, 138, 42, 64));
        put(Color::GlassHighlight, QColor(255, 214, 150, 40));
        return;
    }

    // ObsidianStudio / NeonForge / IvoryHolograph — derive from the existing accessors.
    const QColor acc = accentColor();
    put(Color::Surface0, background0());
    put(Color::Surface1, surface0());
    put(Color::Surface2, surface1());
    put(Color::Surface3, surface1().lighter(112));
    put(Color::TextHi, textPrimary());
    put(Color::TextMid, textSecondary());
    put(Color::TextLo, textMuted());
    put(Color::TextDisabled, withAlpha(textMuted(), 0.78)); // was 0.5 -> composited only ~2.0-2.5:1 (invisible); 0.78 clears >=3:1 on Surface0-2 while staying dimmer than the (now-lightened) muted text
    put(Color::Accent, acc);
    put(Color::AccentHover, acc.lighter(118));
    put(Color::AccentActive, acc.darker(115));
    put(Color::AccentDisabled, mix(acc, surface1(), 0.6));
    put(Color::AccentGlow, withAlpha(acc, 0.35));
    put(Color::AccentSubtle, withAlpha(acc, 0.10));
    put(Color::AccentSecondary, accentSecondary());
    put(Color::AccentTertiary, accentTertiary());
    put(Color::Border, borderColor());
    put(Color::BorderStrong, withAlpha(mix(borderColor(), acc, 0.2), 0.55));
    put(Color::BorderSubtle, withAlpha(borderColor(), 0.28));
    put(Color::Success, successColor());
    put(Color::Warning, warningColor());
    put(Color::Error, errorColor());
    put(Color::Info, QColor(QStringLiteral("#4C9AE6")));
    put(Color::GlassFill, withAlpha(surface0(), 0.86));
    put(Color::GlassGlow, withAlpha(acc, 0.16));
    put(Color::GlassHighlight, QColor(196, 201, 220, 30));
}

QColor ThemeManager::color(Color token) const
{
    const int index = static_cast<int>(token);
    if (index < 0 || index >= ColorTokenCount)
        return QColor();
    return colorTokens_[index];
}

QString ThemeManager::css(Color token) const
{
    const QColor c = color(token);
    return c.alpha() >= 255 ? c.name(QColor::HexRgb) : rgba(c);
}

QPalette ThemeManager::buildPalette() const
{
    // Themed application palette: every native-drawn widget that ESCAPES the MainWindow stylesheet
    // cascade (message boxes, tooltips, generic dialogs, combo popups, native scrollbars) reads its
    // colors from here instead of Qt's native ~#F0F0F0 grey. Derived from the canonical tokens, so it
    // is dark on the dark themes and LIGHT on Ivory automatically. ToolTipBase/Text theme QToolTip even
    // without a stylesheet; the overlay sheet below only adds the border/radius polish on top.
    QPalette p;
    const QColor s0 = color(Color::Surface0);
    const QColor s1 = color(Color::Surface1);
    const QColor s2 = color(Color::Surface2);
    const QColor txHi = color(Color::TextHi);
    const QColor txLo = color(Color::TextLo);
    const QColor txDis = color(Color::TextDisabled);
    const QColor acc = color(Color::Accent);
    const QColor white(QStringLiteral("#FFFFFF"));

    p.setColor(QPalette::Window, s0);
    p.setColor(QPalette::WindowText, txHi);
    p.setColor(QPalette::Base, s1);
    p.setColor(QPalette::AlternateBase, s2);
    p.setColor(QPalette::Text, txHi);
    p.setColor(QPalette::ToolTipBase, s2);
    p.setColor(QPalette::ToolTipText, txHi);
    p.setColor(QPalette::Button, s1);
    p.setColor(QPalette::ButtonText, txHi);
    p.setColor(QPalette::BrightText, txHi);
    p.setColor(QPalette::PlaceholderText, txLo);
    p.setColor(QPalette::Highlight, acc);
    p.setColor(QPalette::HighlightedText, white);   // white on every theme's saturated accent (>=4.5:1)
    p.setColor(QPalette::Link, acc);
    p.setColor(QPalette::LinkVisited, color(Color::AccentSecondary));

    p.setColor(QPalette::Disabled, QPalette::WindowText, txDis);
    p.setColor(QPalette::Disabled, QPalette::Text, txDis);
    p.setColor(QPalette::Disabled, QPalette::ButtonText, txDis);
    p.setColor(QPalette::Disabled, QPalette::Base, s0);
    p.setColor(QPalette::Disabled, QPalette::Button, s0);
    return p;
}

QString ThemeManager::applicationOverlayStyleSheet() const
{
    // qApp-level sheet: reaches the TOP-LEVEL popups that escape the MainWindow cascade. Kept STRICTLY
    // to the escaping widget TYPES (no bare QWidget/QDialog rule, which would clobber custom-painted
    // surfaces) -- generic dialog/message-box BACKGROUNDS are themed by the palette (Window/Base roles),
    // this only adds the border/radius/hover polish the palette can't express.
    const QString bgTip = css(Color::Surface2);
    const QString text = css(Color::TextHi);
    const QString border = css(Color::Border);
    const QString bgMenu = css(Color::Surface1);
    const QString sel = rgba(withAlpha(color(Color::Accent), 0.32));
    const QString btn = css(Color::Surface2);
    const QString btnHover = rgba(withAlpha(color(Color::Accent), 0.16));
    const QString btnHoverBorder = css(Color::AccentHover);

    return QStringLiteral(
        "QToolTip { background:%1; color:%2; border:1px solid %3; border-radius:6px; padding:4px 8px; }"
        "QMenu { background:%4; color:%2; border:1px solid %3; border-radius:8px; padding:4px; }"
        "QMenu::item { padding:5px 22px 5px 20px; border-radius:5px; }"
        "QMenu::item:selected { background:%5; color:%2; }"
        "QMenu::separator { height:1px; background:%3; margin:4px 8px; }"
        "QComboBox QAbstractItemView { background:%4; color:%2; border:1px solid %3; border-radius:8px;"
        " selection-background-color:%5; selection-color:%2; outline:none; padding:2px; }"
        "QMessageBox, QInputDialog { background:%4; }"
        "QMessageBox QLabel, QInputDialog QLabel { color:%2; background:transparent; }"
        "QMessageBox QPushButton, QInputDialog QPushButton { background:%6; color:%2; border:1px solid %3;"
        " border-radius:6px; padding:5px 14px; min-width:72px; }"
        "QMessageBox QPushButton:hover, QInputDialog QPushButton:hover { background:%7; border-color:%8; }")
        .arg(bgTip, text, border, bgMenu, sel, btn, btnHover, btnHoverBorder);
}

void ThemeManager::applyApplicationChrome() const
{
    // Push the themed palette + overlay sheet onto qApp. Called once at startup (from main) and
    // auto-reapplied on themeChanged (wired in the ctor), so the escaping popups re-theme on a switch.
    if (!qApp)
        return;
    qApp->setPalette(buildPalette());
    qApp->setStyleSheet(applicationOverlayStyleSheet());
}

QString ThemeManager::shellStyleSheet() const
{
    // Phase 6: derive the whole shell from canonical color() tokens (not legacy accessors),
    // so the shell switches with the theme. Post-reconcile these tokens hold the same
    // ArcaneGlass values the accessors did, so it's identity-preserving on ArcaneGlass and
    // re-colors on any other theme. borderTok reproduces the old borderColor() from tokens.
    const qreal w = weight01(effectsWeight_);
    const QColor accent = color(Color::Accent);
    const QColor accent2 = color(Color::AccentSecondary);
    const QColor accent3 = color(Color::AccentTertiary);
    const QColor bg0 = color(Color::Surface0);
    const QColor bg1 = color(Color::Surface0); // page tier -> nearest canonical Surface0
    // Shell canvas top-glow: a subtle accent-lifted tone at the top of the QMainWindow gradient so the
    // shell (and the ModePage surfaces that inherit it) reads with depth instead of a flat Surface0 fill.
    // Light on Ivory, deep-violet on the dark themes. Base of the gradient stays bg0, so it is a soft lift.
    const QColor pageGlow = mix(bg0, accent, 0.12 + w * 0.05);
    const QColor surfaceA = withAlpha(color(Color::Surface1), lerp(0.96, 0.84, w));
    const QColor surfaceB = withAlpha(color(Color::Surface2), lerp(0.98, 0.88, w));
    const QColor borderTok = mix(color(Color::Surface2), accent, 0.18 + w * 0.24);
    // ArcaneGlass: elevated violet title-bar band -- anchor to surface2, lift toward the steel
    // structural tone, then a few % violet so it floats ABOVE the body cards (other presets keep
    // surfaceA/surfaceB). Feeds the #CustomTitleBar gradient stops (%5 edge / %6 center) only.
    const bool arcane = (preset_ == Preset::ArcaneGlass);
    const QColor titleBarA = arcane ? mix(mix(color(Color::Surface2), QColor(QStringLiteral("#7E8AB0")), 0.10), accent2, 0.08) : surfaceA;
    const QColor titleBarB = arcane ? mix(mix(color(Color::Surface2), QColor(QStringLiteral("#7E8AB0")), 0.14), accent2, 0.11) : surfaceB;
    const QColor border = withAlpha(borderTok, lerp(0.30, 0.78, w));
    const QColor softBorder = withAlpha(borderTok, lerp(0.18, 0.42, w));
    const QColor focus = withAlpha(accent, lerp(0.46, 0.90, w));
    const QColor focusSoft = withAlpha(accent, lerp(0.14, 0.32, w));
    const QColor buttonA = withAlpha(accent, lerp(0.14, 0.34, w));
    const QColor buttonB = withAlpha(accent2, lerp(0.10, 0.28, w));
    const QColor buttonHoverA = withAlpha(accent, lerp(0.22, 0.48, w));
    const QColor buttonHoverB = withAlpha(accent2, lerp(0.16, 0.38, w));
    const QColor checkedA = withAlpha(accent, lerp(0.18, 0.34, w));
    const QColor checkedB = withAlpha(accent2, lerp(0.14, 0.28, w));
    const QColor idleFill = withAlpha(color(Color::TextHi), preset_ == Preset::IvoryHolograph ? 0.025 : 0.04);

    return QStringLiteral(
        "QMainWindow { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 %62, stop:0.55 %1, stop:1 %1); color: %2; }"
        "QWidget { selection-background-color: %3; selection-color: %4; }"

        "#CustomTitleBar {"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 %5, stop:0.5 %6, stop:1 %5);"
        "}"
        // Transition strip below the bar: ramps the bar's center tone (%6 = titleBarB) down to
        // the page void (%1 = bg0) so the bar->body edge dissolves -- no hard seam, no hairline.
        "#TitleBarTransitionStrip {"
        " background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 %6, stop:1 %1);"
        "}"
        "#SpellVisionTitleLabel { color: transparent; }"
        "#SpellVisionContextLabel { color: transparent; }"
        "#SpellVisionLogoBadge {"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %8, stop:0.55 %9, stop:1 %10);"
        " border: 1px solid %11;"
        " border-radius: 4px;"
        "}"

        "#CustomTitleBar QPushButton {"
        " background: transparent; color: %2; border: 1px solid transparent; padding: 2px 8px;"
        " border-radius: 7px; @bodystrong@"
        "}"
        "#CustomTitleBar QPushButton:hover { background: %12; border-color: %13; }"
        "#CustomTitleBar QPushButton:pressed { background: %14; }"

        "#TitleBarSearchPill {"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 %15, stop:1 %16);"
        " border: 1px solid %17; border-radius: 12px;"
        "}"
        "#TitleBarSearchPill:hover {"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 %16, stop:1 %18);"
        " border-color: %19;"
        "}"
        "#TitleBarSearchText { color: %4; @bodystrong@ }"
        "#TitleBarSearchShortcut { color: %20; @label@ }"
        /* Phase 6 Simple/Advanced segmented toggle -- tokenized inset pill matching the mockup. */
        "#TitleBarModeToggle { background: %23; border: 1px solid %22; border-radius: 9px; }"
        "#TitleBarModeButton { color: %20; background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 2px 11px; @label@ }"
        "#TitleBarModeButton:hover { color: %4; }"
        "#TitleBarModeButton:checked { color: %4; background: %14; border: 1px solid %35; }"

        "#CustomTitleBar QToolButton { background: transparent; border: 1px solid transparent; border-radius: 8px; padding: 0px; }"
        "#CustomTitleBar QToolButton:hover { background: %12; border-color: %13; }"
        "#CustomTitleBar QToolButton:pressed { background: %14; }"
        "#TitleBarCloseButton:hover { background: #c93a45; border-color: rgba(255,255,255,0.10); }"

        "#SideRail { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 %21, stop:1 %1); border-right: 1px solid %22; }"

        "QTextEdit, QPlainTextEdit, QTableView, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {"
        " background: %23; color: %24; border: 1px solid %25; border-radius: 11px;"
        "}"
        "QTextEdit:focus, QPlainTextEdit:focus, QTableView:focus, QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border: 1px solid %19; }"
        "QHeaderView::section { background: %26; color: %24; border: none; border-bottom: 1px solid %27; padding: 8px; font-weight: 600; }"
        "QTableView { gridline-color: %28; alternate-background-color: %29; }"

        "QMenu { background: %26; color: %24; border: 1px solid %27; border-radius: 10px; }"
        "QMenu::item { padding: 7px 18px; border-radius: 6px; }"
        "QMenu::item:selected { background: %14; }"

        "QDockWidget { color: %24; }"
        "QDockWidget::title {"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 %15, stop:1 %16);"
        " text-align: left; padding: 8px 12px; border-bottom: 1px solid %27; font-weight: 700;"
        "}"

        "QPushButton {"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %30, stop:1 %31);"
        " color: %2; border: 1px solid %32; border-radius: 11px; padding: 6px 12px; min-height: 34px; font-weight: 600;"
        "}"
        "QPushButton:hover {"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %33, stop:1 %34);"
        " border-color: %35;"
        "}"
        "QPushButton:pressed { background: %14; }"
        "QPushButton:checked { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %36, stop:1 %37); border-color: %35; }"
        "QPushButton:disabled { color: %38; border-color: %39; background: %40; }"

        "QCheckBox { color: %24; }"
        "QLabel#ShellSectionTitle { @title@ color: %4; }"
        "QStatusBar { background: %21; border-top: 1px solid %22; min-height: 38px; }"
        "QStatusBar QLabel { color: %24; @detail@ }"
        "QWidget#MainPageStack { background: transparent; }"
        "QWidget#SideRail { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 %41, stop:0.45 %41, stop:1 %41); border-right: 1px solid %42; }"
        "QToolButton#SideRailButton { color: %43; border: 1px solid transparent; border-left: 4px solid transparent; border-radius: 16px; @label@ padding: 10px 2px 10px 2px; text-align: center; background: transparent; }"
        "QToolButton#SideRailButton:hover { color: %48; background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 %44, stop:0.58 %45, stop:1 %46); border-color: %47; }"
        "QToolButton#SideRailButton:checked { color: %48; background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 %49, stop:0.55 %50, stop:1 %51); border-color: %52; border-left: 4px solid %53; }"
        "QFrame#QueueActiveStrip, QFrame#DetailsSummaryCard, QFrame#DetailsActionCard, QFrame#ExecutionLogCard { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 %54, stop:1 %55); border: 1px solid %56; border-radius: 16px; }"
        "QLabel#QueueActiveEyebrow, QLabel#DetailsEyebrow { @caption@ color: %57; }"
        "QLabel#QueueActiveTitle, QLabel#DetailsTitle { @heading@ color: %4; }"
        "QLabel#QueueActiveBody, QLabel#DetailsBody { @detail@ color: %58; }"
        "QLabel#DetailsMetaLabel { @micro@ color: %59; text-transform: uppercase; letter-spacing: 0.08em; }"
        "QLabel#DetailsMetaValue { @label@ color: %4; background: %55; border: 1px solid %56; border-radius: 8px; padding: 4px 8px; }"
        "QPushButton#DetailsPrimaryActionButton { min-height: 30px; @label@ }"
        "QPushButton#DetailsSecondaryActionButton { min-height: 28px; @label@ }"
        "QPushButton#DetailsActionButton { min-height: 32px; border-radius: 11px; @label@ }"
        "QTextEdit#LogsView { background: %55; border: 1px solid %56; border-radius: 12px; padding: 8px; }"
        /* SPRINT MOCKUP PASS 3 DISCLOSURE PROMOTION */ "QLabel#SectionTitle { @heading@ color: %4; background: transparent; }"
        "QLabel#SectionBody { @body@ color: %20; background: transparent; }"
        "QSplitter::handle { background: transparent; }"
        "QSplitter::handle:hover { background: %14; }"
        "QScrollArea { background: transparent; border: none; }"
        "QLabel#SideRailBadge { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %36, stop:1 %37); color: %4; border: 1px solid %35; border-radius: 18px; padding: 8px 0px; font-size: 12px; font-weight: 900; }"
        "QLabel#SideRailCaption { color: %20; @caption@ letter-spacing: 0.08em; }"
        "QLabel#RailSectionHeader { color: %20; @micro@ letter-spacing: 0.14em; padding: 7px 0 2px 0; background: transparent; }"
        /* Studio-layout CockpitInspector (phase 2 scaffold) -- 340px tabbed right column */
        "#CockpitInspector { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 %54, stop:1 %55); border-left: 1px solid %56; }"
        "#InspectorTabBar { background: transparent; }"
        "#InspectorTab { background: transparent; color: %61; border: none; border-bottom: 2px solid transparent; padding: 7px 4px; @label@ }"
        "#InspectorTab:hover { color: %4; }"
        "#InspectorTab:checked { color: %48; border-bottom: 2px solid %60; }"
        "#InspectorPlaceholder { color: %59; @body@ }"
        "#InspectorReadinessStrip { background: %55; border-top: 1px solid %56; }"
        "#InspectorReadinessText { color: %58; @label@ }"
        /* Phase 5 activity drawer (queueOverlay_): the solid container fill comes from
           autoFillBackground + an opaque palette (MainWindow), so the drawer is never see-through.
           The header (a QFrame, paints natively) sits on that base in the rail/status tone (%21),
           with a hairline divider (%27) and the title in textPrimary (%4). */
        "#QueueOverlayHeader { background: %21; border-bottom: 1px solid %27; }"
        "#QueueOverlayTitle { @subtitle@ color: %4; background: transparent; }"
        "QFrame#SideRailDivider { background: %27; min-height: 1px; max-height: 1px; border: none; }"

        "#RailButton { background: transparent; color: %24; border: 1px solid transparent; border-radius: 14px; padding: 0px; text-align: center; }"
        "#RailButton:hover { background: %12; border-color: %13; }"
        "#RailButton:checked { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %36, stop:1 %37); border: 1px solid %35; }"

        "#ActiveJobCard {"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %15, stop:1 %16);"
        " border: 1px solid %27; border-radius: 16px;"
        "}"
        "#ActiveJobCard:hover { border: 1px solid %35; }"
        "#ActiveJobTitle { @heading@ color: %4; }"
        "#ActiveJobPrompt { color: %24; @body@ }"
        "#ActiveJobMeta { color: %20; @body@ }"
        "#ActiveJobStatus { color: %24; @body@ }"
        "#ActiveJobBadge { padding: 4px 10px; border-radius: 10px; font-weight: 800; }"
        // Phase 6: bottom telemetry chrome moved from local setStyleSheets into the shell
        // stylesheet (reuses existing tokens) so the progress bar + separators switch on
        // themeChanged too -- was a stale blue/violet block.
        "QProgressBar#BottomProgressBar { border: 1px solid %56; border-radius: 8px; background: %55; color: %2; @micro@ text-align: center; }"
        "QProgressBar#BottomProgressBar::chunk { border-radius: 7px; background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 %7, stop:1 %8); }"
        "QFrame#BottomTelemetrySeparator { background: %56; border: none; }"
        )
        .arg(bg0.name(),
             color(Color::TextHi).name(),
             rgba(focus, 0.36),
             color(Color::TextHi).name(),
             rgba(titleBarA, 1.0),
             rgba(titleBarB, 1.0),
             accent.name(),
             accent2.name(),
             accent3.name(),
             rgba(withAlpha(color(Color::TextHi), preset_ == Preset::IvoryHolograph ? 0.20 : 0.36)),
             rgba(idleFill, 1.0),
             rgba(softBorder, 0.85),
             rgba(focusSoft, 1.0),
             rgba(withAlpha(color(Color::Surface1), 0.98), 1.0),
             rgba(withAlpha(color(Color::Surface2), 0.98), 1.0),
             rgba(softBorder, 0.95),
             rgba(mix(color(Color::Surface2), accent2, 0.25), 0.98),
             rgba(focus, 1.0),
             color(Color::TextLo).name(),
             rgba(mix(bg1, color(Color::Surface1), 0.55), 0.98),
             rgba(softBorder, 0.70),
             rgba(withAlpha(color(Color::Surface0), 0.98), 1.0),
             color(Color::TextMid).name(),
             rgba(softBorder, 1.0),
             rgba(withAlpha(color(Color::Surface1), 0.98), 1.0),
             rgba(softBorder, 0.55),
             rgba(withAlpha(borderTok, 0.24), 1.0),
             rgba(idleFill, 0.65),
             rgba(buttonA, 1.0),
             rgba(buttonB, 1.0),
             rgba(withAlpha(focus, lerp(0.34, 0.62, w)), 1.0),
             rgba(buttonHoverA, 1.0),
             rgba(buttonHoverB, 1.0),
             rgba(withAlpha(focus, 0.92), 1.0),
             rgba(checkedA, 1.0),
             rgba(checkedB, 1.0),
             color(Color::TextLo).name(),
             rgba(withAlpha(borderTok, 0.20), 1.0),
             rgba(idleFill, 0.55),
             // Phase 6 inline sub-widgets (rail buttons, queue/details/inspector cards) --
             // these were the stale-literal CORRECTION class (navy cards + blue labels +
             // violet-blue rail gradients), now on-palette tokens that switch.
             rgba(bg0, 0.998),                 // %41 rail base
             rgba(accent, 0.28),               // %42 rail border
             rgba(color(Color::TextHi), 0.76), // %43 rail idle text
             rgba(accent, 0.24),               // %44 rail hover g0
             rgba(accent2, 0.16),              // %45 rail hover g1
             rgba(accent3, 0.08),              // %46 rail hover g2 (was blue)
             rgba(accent, 0.36),               // %47 rail hover border
             color(Color::TextHi).name(),      // %48 rail active text
             rgba(accent, 0.54),               // %49 rail checked g0
             rgba(accent2, 0.34),              // %50 rail checked g1
             rgba(accent3, 0.16),              // %51 rail checked g2 (was blue)
             rgba(accent3, 0.72),              // %52 rail checked border
             rgba(accent3, 1.0),               // %53 rail checked border-left
             rgba(surfaceB, 1.0),              // %54 card top (was navy)
             rgba(bg0, 0.98),                  // %55 card bottom / logs / inspector strip
             rgba(softBorder, 0.9),            // %56 card borders (was blue-grey)
             accent.name(),                    // %57 eyebrows (was blue #8fb2ff)
             color(Color::TextMid).name(),     // %58 body (was #9fb0ca)
             color(Color::TextLo).name(),      // %59 meta label / placeholder (was #7f95b7)
             color(Color::AccentHover).name(), // %60 inspector checked border (was #9a78ff)
             rgba(color(Color::TextMid), 0.85), // %61 inspector tab idle
             rgba(pageGlow, 1.0)) // %62 shell canvas top-glow (QMainWindow gradient)
        .replace(QLatin1String("@title@"), fontCss(Type::Title))
        .replace(QLatin1String("@heading@"), fontCss(Type::Heading))
        .replace(QLatin1String("@subtitle@"), fontCss(Type::Subtitle))
        .replace(QLatin1String("@body@"), fontCss(Type::Body))
        .replace(QLatin1String("@bodystrong@"), fontCss(Type::BodyStrong))
        .replace(QLatin1String("@detail@"), fontCss(Type::Detail))
        .replace(QLatin1String("@label@"), fontCss(Type::Label))
        .replace(QLatin1String("@caption@"), fontCss(Type::Caption))
        .replace(QLatin1String("@micro@"), fontCss(Type::Micro));
}

QString ThemeManager::imageGenerationStyleSheet() const
{
    // Phase 8: derive the IGP cockpit from canonical color() tokens (not legacy accessors) so
    // it switches with the theme. Post-reconcile the tokens match the accessors on ArcaneGlass,
    // so this is identity-preserving there. borderTok reproduces the old borderColor();
    // inputSurface (deferred in phase 2) -> Surface0 (inputs slightly darker, documented correction).
    const qreal w = weight01(effectsWeight_);
    const QColor accent = color(Color::Accent);
    const QColor accent2 = color(Color::AccentSecondary);
    const QColor tokSurface0 = color(Color::Surface0);
    const QColor panel0 = withAlpha(color(Color::Surface1), lerp(0.96, 0.84, w));
    const QColor panel1 = withAlpha(color(Color::Surface2), lerp(0.98, 0.88, w));
    const QColor borderTok = mix(color(Color::Surface2), accent, 0.18 + w * 0.24);
    const QColor border = withAlpha(borderTok, lerp(0.28, 0.74, w));
    const QColor input = withAlpha(tokSurface0, preset_ == Preset::IvoryHolograph ? 0.96 : 0.98);
    const QColor focus = withAlpha(accent, lerp(0.60, 0.92, w));
    const QColor subtleBorder = withAlpha(border, 0.78);
    const QColor softSurface = tokSurface0;
    const QColor promptA = withAlpha(mix(panel0, accent, 0.18), 1.0);
    const QColor promptB = withAlpha(mix(panel1, accent2, 0.12), 1.0);
    const QColor canvasA = withAlpha(mix(panel0, accent, 0.10), 1.0);
    const QColor canvasB = withAlpha(mix(panel1, accent2, 0.18), 1.0);
    const QColor secondaryBorder = withAlpha(accent, 0.18);
    const QColor tertiaryFill = withAlpha(border, 0.18);
    const QColor tertiaryBorder = withAlpha(border, 0.34);
    // Cockpit canvas top-glow -- same subtle accent lift as the shell/Home/Settings, so the cockpit
    // reads with depth instead of a flat Surface0 fill. Base of the gradient stays Surface0 (%1).
    const QColor cockpitGlow = mix(tokSurface0, accent, 0.12 + w * 0.05);

    QString style = QStringLiteral(
        "#ImageGenerationPage { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 %46, stop:0.5 %1, stop:1 %1); }"
        "QWidget#LeftRailContainer { background: transparent; }"
        "QScrollArea#LeftRailScrollArea { background: transparent; border: none; }"
        "QFrame#PromptCard, QFrame#InputCard, QFrame#QuickControlsCard, QFrame#SamplerSchedulerCard, QFrame#LtxLaunchOptionsPanel, QFrame#OutputQueueCard, QFrame#AdvancedCard, QFrame#SettingsCard, QFrame#OutputCard, QFrame#CanvasCard {"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %2, stop:1 %3);"
        " border: 1px solid %4; border-radius: 20px; }"
        "QFrame#PromptCard { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %5, stop:1 %6); border: 1px solid %7; }"
        "QFrame#CanvasCard { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %8, stop:1 %9); border: 1px solid %10; }"
        "QFrame#QuickControlsCard, QFrame#SamplerSchedulerCard, QFrame#LtxLaunchOptionsPanel, QFrame#OutputQueueCard, QFrame#AdvancedCard, QFrame#SettingsCard, QFrame#OutputCard { border-color: %11; }"
        "QFrame#InputDropCard { background: %12; border: 1px dashed %7; border-radius: 16px; }"
        "QLabel#SectionTitle { @heading@ color: %13; background: transparent; }"
        "QToolButton#InspectorSectionToggle { background: %28; color: %13; border: 1px solid %29; border-radius: 10px; padding: 3px 10px; min-width: 62px; min-height: 22px; max-height: 26px; @caption@ }"
        "QToolButton#InspectorSectionToggle:hover { background: %23; border-color: %10; }"
        "QLabel#SectionBody { @detail@ color: %14; background: transparent; }"
        "QLabel#CompactFieldLabel { color: %14; @caption@ background: transparent; }"
        // --- SPRINT MOCKUP PASS 2 QUICK CONTROLS STACKED: stacked-label field cells ---
        "QLabel#StackedFieldLabel { color: %14; @label@ background: transparent; padding-bottom: 2px; }"
        "QLabel#ImageGenHint, QLabel#OutputQueueBodyHint { color: %14; @detail@ background: transparent; }"
        "QLabel#OutputQueueBodyLabel { color: %13; @caption@ background: transparent; }"
        "QLabel#AssetIntelligenceBody { color: %15; @detail@ background: transparent; padding-top: 2px; }"
        "QLabel#StackSummary { color: %15; @body@ background: transparent; }"
        "QLabel#PreviewSummary { color: %14; @body@ background: transparent; padding-right: 12px; }"
        "QLabel#ReadinessHint { color: %14; @label@ background: %32; border: 1px solid %31; border-radius: 11px; padding: 6px 10px; min-height: 26px; }"
        "QLabel#PreviewSurface {"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %16, stop:1 %12);"
        " border: 1px dashed %7; border-radius: 22px; color: %15; padding: 18px; @subtitle@ }"
        "QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {"
        " background: %17; color: %15; border: 1px solid %18; border-radius: 10px; padding: 5px 8px; min-height: 24px; }"
        "QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border: 1px solid %7; }"
        "QSpinBox, QDoubleSpinBox { padding-right: 28px; }"
        "QSpinBox::up-button, QDoubleSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 22px; border-left: 1px solid %18; background: %12; border-top-right-radius: 10px; }"
        "QSpinBox::down-button, QDoubleSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 22px; border-left: 1px solid %18; background: %12; border-bottom-right-radius: 10px; }"
        "QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover, QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover { background: %19; }"
        "QPushButton, QToolButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %20, stop:1 %21); color:%13; border:1px solid %22; border-radius: 12px; padding: 6px 10px; min-height: 32px; font-weight: 600; }"
        "QPushButton:hover, QToolButton:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %23, stop:1 %24); border-color: %10; }"
        "QPushButton#PrimaryActionButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %25, stop:1 %26); border: 1px solid %10; border-radius: 13px; min-height: 38px; font-weight: 900; }"
        "QPushButton#SecondaryActionButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %23, stop:1 %21); border: 1px solid %27; border-radius: 12px; min-height: 34px; font-weight: 700; }"
        "QPushButton#TertiaryActionButton { background: %28; border: 1px solid %29; border-radius: 12px; min-height: 32px; font-weight: 700; }"
        "QPushButton:disabled, QPushButton[readinessBlocked=\"true\"] { color: %30; border-color: %31; background: %32; }"
        "QPushButton[readinessBlocked=\"true\"] { font-weight: 800; }"
        "QPushButton#PrimaryActionButton:disabled, QPushButton#PrimaryActionButton[readinessBlocked=\"true\"] { background: %32; border: 1px solid %31; color: %30; }"
        "QPushButton#SecondaryActionButton:disabled, QPushButton#SecondaryActionButton[readinessBlocked=\"true\"] { background: %32; border: 1px solid %31; color: %30; }"
        // --- SPRINT MOCKUP PASS 1 ASSET INTELLIGENCE: structured AI surface selectors ---
        "QFrame#AiReadinessStrip { background: %34; border: 1px solid %35; border-radius: 11px; }"
        "QFrame#AiReadinessStrip[readiness=\"warn\"] { background: %37; border-color: %38; }"
        "QFrame#AiReadinessStrip[readiness=\"block\"] { background: %40; border-color: %41; }"
        "QLabel#AiReadinessDot { background: %36; border-radius: 5px; min-width: 10px; max-width: 10px; min-height: 10px; max-height: 10px; }"
        "QLabel#AiReadinessDot[readiness=\"warn\"] { background: %39; }"
        "QLabel#AiReadinessDot[readiness=\"block\"] { background: %42; }"
        "QLabel#AiReadinessText { @bodystrong@ color: %13; background: transparent; }"
        "QLabel#AiReadinessSub { @detail@ color: %14; background: transparent; }"
        "QLabel#AiGroupLabel { @caption@ color: %14; background: transparent; }"
        "QLabel#AiChipSet { background: %43; border: 1px solid %44; border-radius: 12px; padding: 2px 10px; color: %13; @detail@ min-height: 18px; }"
        "QLabel#AiChipAuto { background: %17; border: 1px dashed %18; border-radius: 12px; padding: 2px 10px; color: %14; @detail@ min-height: 18px; }"
        "QFrame#AiTimingRow { background: transparent; border-top: 1px solid %29; }"
        "QLabel#AiTimingValue { @subtitle@ color: %13; background: transparent; }"
        "QLabel#AiTimingKey { @caption@ color: %14; background: transparent; }"
        "QToolButton#AiDetailsToggle { background: transparent; border-style: none; padding: 4px 0px; color: %45; @label@ min-height: 18px; }"  // SPRINT MOCKUP PASS 1 FIXUP: text-align stripped (unsupported on QToolButton)
        "QToolButton#AiDetailsToggle:hover { color: %10; }"
        "QLabel#AiDetailsBody { color: %15; @detail@ background: transparent; padding-top: 4px; }"
        // --- END SPRINT MOCKUP PASS 1 ASSET INTELLIGENCE ---  // SPRINT MOCKUP PASS 1 FIXUP 2 + SPRINT MOCKUP PASS 1 FIXUP 3
        "QLabel#PreviewSurface[emptyState=\"true\"] { color: %14; border-color: %31; background: %33; }"
        // When a real result is shown, drop the dashed drop-zone frame + heavy padding so the image
        // goes near edge-to-edge (content is the hero); the empty-state keeps its dashed look above.
        "QLabel#PreviewSurface[emptyState=\"false\"] { border: none; padding: 4px; }"
    );

    style = style
        .arg(tokSurface0.name())
        .arg(rgba(panel0, 1.0))
        .arg(rgba(panel1, 1.0))
        .arg(rgba(border, 1.0))
        .arg(rgba(promptA, 1.0))
        .arg(rgba(promptB, 1.0))
        .arg(rgba(focus, 1.0))
        .arg(rgba(canvasA, 1.0))
        .arg(rgba(canvasB, 1.0))
        .arg(rgba(withAlpha(focus, 0.92), 1.0))
        .arg(rgba(subtleBorder, 1.0))
        .arg(rgba(softSurface, 1.0))
        .arg(color(Color::TextHi).name())
        .arg(color(Color::TextLo).name())
        .arg(color(Color::TextMid).name())
        .arg(rgba(withAlpha(mix(panel0, accent, 0.18), 1.0), 1.0))
        .arg(rgba(input, 1.0))
        .arg(rgba(withAlpha(border, 0.95), 1.0))
        .arg(rgba(withAlpha(mix(tokSurface0, accent2, 0.18), 1.0), 1.0))
        .arg(rgba(withAlpha(accent, lerp(0.18, 0.34, w)), 1.0))
        .arg(rgba(withAlpha(accent2, lerp(0.14, 0.28, w)), 1.0))
        .arg(rgba(withAlpha(focus, 0.55), 1.0))
        .arg(rgba(withAlpha(accent, lerp(0.28, 0.48, w)), 1.0))
        .arg(rgba(withAlpha(accent2, lerp(0.22, 0.40, w)), 1.0))
        .arg(rgba(withAlpha(accent, lerp(0.36, 0.58, w)), 1.0))
        .arg(rgba(withAlpha(accent2, lerp(0.28, 0.46, w)), 1.0))
        .arg(rgba(secondaryBorder, 1.0))
        .arg(rgba(tertiaryFill, 1.0))
        .arg(rgba(tertiaryBorder, 1.0))
        .arg(rgba(withAlpha(color(Color::TextLo), 0.78), 1.0))
        .arg(rgba(withAlpha(borderTok, 0.38), 1.0))
        .arg(rgba(withAlpha(tokSurface0, 1.0), 1.0))
        // --- SPRINT MOCKUP PASS 1 FIXUP 4: restore missing %33 arg (was lost when Pass 1 replaced instead of inserted) ---
        .arg(rgba(withAlpha(mix(panel0, tokSurface0, 0.20), 1.0), 1.0))
        // --- SPRINT MOCKUP PASS 1 ASSET INTELLIGENCE: new color slots (34-45) ---
        // 34/35: success-tinted readiness pill (bg, border)
        // 36   : success base for ready dot
        // 37/38: warning-tinted readiness pill (bg, border)
        // 39   : warning base for warn dot
        // 40/41: error-tinted readiness pill (bg, border)
        // 42   : error base for block dot
        // 43/44: accent-tinted chip when is="set" (bg, border)
        // 45   : accent base for AiDetailsToggle text + chip emphasis
        .arg(rgba(withAlpha(color(Color::Success), 0.10), 1.0))
        .arg(rgba(withAlpha(color(Color::Success), 0.34), 1.0))
        .arg(color(Color::Success).name())
        .arg(rgba(withAlpha(color(Color::Warning), 0.10), 1.0))
        .arg(rgba(withAlpha(color(Color::Warning), 0.34), 1.0))
        .arg(color(Color::Warning).name())
        .arg(rgba(withAlpha(color(Color::Error), 0.10), 1.0))
        .arg(rgba(withAlpha(color(Color::Error), 0.34), 1.0))
        .arg(color(Color::Error).name())
        .arg(rgba(withAlpha(accent, 0.10), 1.0))
        .arg(rgba(withAlpha(accent, 0.42), 1.0))
        .arg(accent.name())
        .arg(rgba(cockpitGlow, 1.0)); // %46 cockpit canvas top-glow
        // --- END SPRINT MOCKUP PASS 1 ASSET INTELLIGENCE: new color slots ---

    // Typography: expand the @role@ markers to fontCss(Type::X) (size + weight from the scale).
    style.replace(QLatin1String("@heading@"), fontCss(Type::Heading))
         .replace(QLatin1String("@subtitle@"), fontCss(Type::Subtitle))
         .replace(QLatin1String("@body@"), fontCss(Type::Body))
         .replace(QLatin1String("@bodystrong@"), fontCss(Type::BodyStrong))
         .replace(QLatin1String("@detail@"), fontCss(Type::Detail))
         .replace(QLatin1String("@label@"), fontCss(Type::Label))
         .replace(QLatin1String("@caption@"), fontCss(Type::Caption));
    return style;
}


QString ThemeManager::homePageStyleSheet() const
{
    const qreal w = weight01(effectsWeight_);
    // Phase 4: the Home scroll chrome reads the canonical tokens (identity-preserving on
    // ArcaneGlass post-reconcile) so the scrollbar switches with the theme too -- completing
    // the Home surface's generator-styled class.
    const QColor scrollHandle = withAlpha(mix(color(Color::Surface2), color(Color::Accent), 0.26), lerp(0.22, 0.42, w));
    const QColor scrollHover = withAlpha(mix(color(Color::Surface2), color(Color::AccentSecondary), 0.34), lerp(0.32, 0.56, w));

    return QStringLiteral(
        "#HomePage { background: transparent; }"
        "QScrollArea { background: transparent; border: none; }"
        "QScrollBar:vertical { width: 10px; background: transparent; margin: 2px; }"
        "QScrollBar::handle:vertical { background: %1; border-radius: 5px; min-height: 42px; }"
        "QScrollBar::handle:vertical:hover { background: %2; }"
        "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical, QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; height: 0px; }")
        .arg(rgba(scrollHandle, 1.0),
             rgba(scrollHover, 1.0));
}

QString ThemeManager::settingsStyleSheet() const
{
    const qreal w = weight01(effectsWeight_);
    const QColor accent = accentColor();
    const QColor accent2 = presetAccentSecondary();
    const QColor surfaceA = withAlpha(surface0(), lerp(0.96, 0.84, w));
    const QColor surfaceB = withAlpha(surface1(), lerp(0.98, 0.88, w));
    const QColor border = withAlpha(borderColor(), lerp(0.28, 0.78, w));
    const QColor focus = withAlpha(accent, lerp(0.62, 0.94, w));
    const QColor soft = withAlpha(accent, lerp(0.10, 0.24, w));
    // Settings canvas top-glow -- same subtle accent lift as the shell/Home, so the Settings surface
    // reads with depth instead of a flat Surface0 fill. Base of the gradient stays Surface0 (%1).
    const QColor settingsGlow = mix(background0(), accent, 0.12 + w * 0.05);

    return QStringLiteral(
        "#SettingsPage { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 %23, stop:0.5 %1, stop:1 %1); }"
        "#SettingsTitle { @title@ color: %2; }"
        "#SettingsSubtitle { @body@ color: %3; }"
        "#SettingsCard { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %4, stop:1 %5); border: 1px solid %6; border-radius: 20px; }"
        "#SettingsSectionTitle { @heading@ color: %2; }"
        "#SettingsBody { @body@ color: %3; }"
        "#SettingsValueChip { background: %7; color: %2; border: 1px solid %8; border-radius: 10px; padding: 6px 10px; @label@ }"
        "#SettingsPreviewPanel { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %9, stop:1 %10); border: 1px solid %8; border-radius: 18px; }"
        "#SettingsPreviewHeader { color: %2; @subtitle@ }"
        "#SettingsPreviewBody { color: %3; @body@ }"
        "QComboBox, QSlider, QCheckBox, QPushButton { color: %2; }"
        "QComboBox { background: %11; border: 1px solid %8; border-radius: 10px; padding: 6px 8px; min-height: 32px; }"
        "QComboBox:focus { border-color: %12; }"
        "QCheckBox { spacing: 8px; }"
        "QCheckBox::indicator { width: 16px; height: 16px; border-radius: 5px; border: 1px solid %8; background: %13; }"
        "QCheckBox::indicator:checked { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %14, stop:1 %15); border: 1px solid %12; }"
        "QPushButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %16, stop:1 %17); border: 1px solid %18; border-radius: 11px; padding: 7px 12px; min-height: 34px; font-weight: 700; }"
        "QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %19, stop:1 %20); border-color: %12; }"
        "QPushButton:disabled { color: %21; border-color: %22; background: %13; }"
        "QSlider::groove:horizontal { height: 7px; background: %13; border-radius: 4px; }"
        "QSlider::sub-page:horizontal { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 %14, stop:1 %15); border-radius: 4px; }"
        "QSlider::handle:horizontal { width: 14px; margin: -5px 0; border-radius: 7px; background: %12; border: 1px solid rgba(255,255,255,0.15); }")
        .arg(background0().name(),
             textPrimary().name(),
             textMuted().name(),
             rgba(surfaceA, 1.0),
             rgba(surfaceB, 1.0),
             rgba(border, 1.0),
             rgba(withAlpha(textPrimary(), preset_ == Preset::IvoryHolograph ? 0.06 : 0.04), 1.0),
             rgba(withAlpha(border, 0.78), 1.0),
             rgba(withAlpha(surface0(), 0.90), 1.0),
             rgba(withAlpha(mix(surface1(), accent2, 0.10), 0.94), 1.0),
             rgba(withAlpha(inputSurface(), 0.96), 1.0),
             rgba(focus, 1.0),
             rgba(withAlpha(textPrimary(), preset_ == Preset::IvoryHolograph ? 0.09 : 0.06), 1.0),
             accent.name(),
             accent2.name(),
             rgba(withAlpha(accent, lerp(0.16, 0.34, w)), 1.0),
             rgba(withAlpha(accent2, lerp(0.12, 0.28, w)), 1.0),
             rgba(withAlpha(focus, 0.48), 1.0),
             rgba(withAlpha(accent, lerp(0.24, 0.44, w)), 1.0),
             rgba(withAlpha(accent2, lerp(0.18, 0.34, w)), 1.0),
             textMuted().name(),
             rgba(withAlpha(borderColor(), 0.20), 1.0), // %22
             rgba(settingsGlow, 1.0)) // %23 settings canvas top-glow
        // Typography: @role@ markers -> fontCss(Type::X) (size + weight from the scale, in one place).
        .replace(QLatin1String("@title@"), fontCss(Type::Title))
        .replace(QLatin1String("@heading@"), fontCss(Type::Heading))
        .replace(QLatin1String("@subtitle@"), fontCss(Type::Subtitle))
        .replace(QLatin1String("@label@"), fontCss(Type::Label))
        .replace(QLatin1String("@body@"), fontCss(Type::Body));
}

QString ThemeManager::accentSwatchStyle() const
{
    const QColor accent = accentColor();
    const QColor accent2 = presetAccentSecondary();
    return QStringLiteral(
        "background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 %1, stop:1 %2);"
        "border: 1px solid %3;"
        "border-radius: 12px;")
        .arg(accent.name(),
             accent2.name(),
             rgba(withAlpha(accent, 0.58), 1.0));
}

QString ThemeManager::accentGradientStyle() const
{
    const QColor accent = accentColor();
    const QColor accent2 = presetAccentSecondary();
    const QColor accent3 = presetAccentTertiary();
    return QStringLiteral(
        "background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 %1, stop:0.52 %2, stop:1 %3);"
        "border: 1px solid %4;"
        "border-radius: 14px;")
        .arg(accent.name(),
             accent2.name(),
             accent3.name(),
             rgba(withAlpha(accent, 0.52), 1.0));
}

QString ThemeManager::settingsPreviewCardStyle() const
{
    const qreal w = weight01(effectsWeight_);
    const QColor border = withAlpha(borderColor(), lerp(0.30, 0.72, w));
    return QStringLiteral(
        "background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %1, stop:1 %2);"
        "border: 1px solid %3; border-radius: 18px;")
        .arg(rgba(withAlpha(surface0(), 0.90), 1.0),
             rgba(withAlpha(mix(surface1(), accentSecondary(), 0.10), 0.94), 1.0),
             rgba(border, 1.0));
}

QString ThemeManager::settingsPreviewChipStyle(bool active) const
{
    const qreal w = weight01(effectsWeight_);
    const QColor fill = active ? withAlpha(accentColor(), lerp(0.18, 0.34, w))
                               : withAlpha(textPrimary(), preset_ == Preset::IvoryHolograph ? 0.06 : 0.04);
    const QColor border = active ? withAlpha(accentColor(), lerp(0.48, 0.86, w))
                                 : withAlpha(borderColor(), 0.42);
    return QStringLiteral(
        "background:%1; color:%2; border:1px solid %3; border-radius:10px; padding:4px 10px; font-weight:700;")
        .arg(rgba(fill, 1.0), textPrimary().name(), rgba(border, 1.0));
}

QString ThemeManager::settingsPreviewButtonStyle(bool primary) const
{
    const qreal w = weight01(effectsWeight_);
    const QColor a = primary ? withAlpha(accentColor(), lerp(0.24, 0.42, w))
                             : withAlpha(textPrimary(), preset_ == Preset::IvoryHolograph ? 0.06 : 0.04);
    const QColor b = primary ? withAlpha(accentSecondary(), lerp(0.18, 0.34, w))
                             : withAlpha(surface1(), 0.80);
    const QColor border = primary ? withAlpha(accentColor(), lerp(0.52, 0.90, w))
                                  : withAlpha(borderColor(), 0.48);
    return QStringLiteral(
        "background:qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %1, stop:1 %2);"
        "color:%3; border:1px solid %4; border-radius:11px; padding:6px 12px; font-weight:700;")
        .arg(rgba(a, 1.0), rgba(b, 1.0), textPrimary().name(), rgba(border, 1.0));
}

QString ThemeManager::modePageStyleSheet() const
{
    return shellStyleSheet();
}