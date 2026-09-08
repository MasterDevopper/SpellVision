#include "ThemeManager.h"

#include "style/SvStyle.h"

#include <QSettings>
#include <QRegularExpression>
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

// RELATIVE to whatever the palette already chose, unlike withAlpha() which sets an absolute value.
// The style pass needs this: "make this preset's hairline half again as strong" has to work across
// five palettes that each picked a different starting alpha. Passing 1.45 to withAlpha would clamp
// to 1.0 and paint an opaque bar where a hairline belongs.
QColor scaleAlpha(const QColor &color, qreal factor)
{
    QColor copy = color;
    copy.setAlphaF(qBound(0.0, color.alphaF() * factor, 1.0));
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
    const Style originalStyle = style_;
    const QStringList styles = styleNames();
    int failures = 0;
    // Walks style x preset, not just preset: style rewrites material tokens (and could be given a
    // surface tweak later), so checking one style would leave the other pairings unguarded. Text and
    // surface tokens are preset-owned today, so this is cheap insurance rather than duplicated work.
    for (int s = 0; s < styles.size(); ++s)
    for (int p = 0; p <= static_cast<int>(Preset::Ember); ++p)
    {
        style_ = static_cast<Style>(s);
        preset_ = static_cast<Preset>(p);
        rebuildColorTokens();
        const QString theme = QStringLiteral("%1 / %2").arg(names.value(p), styles.value(s));
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
    style_ = originalStyle;
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

ThemeManager::Style ThemeManager::style() const
{
    return style_;
}

QString ThemeManager::panelFillCss(Color base, qreal glassAlpha) const
{
    // The panel background, expressed per material. Glass keeps a little transparency so the ground
    // reads through it; matte and hybrid are fully opaque, because a panel that is 98% opaque is not
    // matte, it is glass nobody notices.
    //
    // Deliberately NOT lightened for matte, even though a lift would separate it further: the
    // startup contrast assert checks text against the Surface TOKENS, so any colour derived here is
    // outside its coverage. Separation comes from Surface0 being deepened in the style pass instead,
    // which the assert does see.
    const QColor base_ = color(base);
    if (style_ == Style::RefinedGlass)
        return rgba(withAlpha(base_, glassAlpha), 1.0);

    QColor solid = base_;
    solid.setAlpha(255);
    return rgba(solid, 1.0);
}

QStringList ThemeManager::styleNames() const
{
    return {QStringLiteral("Refined Glass"), QStringLiteral("Matte Instrument"), QStringLiteral("Hybrid")};
}

QString ThemeManager::styleDescription(Style style) const
{
    switch (style)
    {
    case Style::RefinedGlass:
        return QStringLiteral("Translucent panels lit by one accent source, with platinum hairlines "
                              "for structure. The glass look, without the per-card glow.");
    case Style::MatteInstrument:
        return QStringLiteral("Opaque surfaces, hairline structure, no glow anywhere. Colour is "
                              "reserved for state, so status stays findable. Cheapest to draw.");
    case Style::Hybrid:
        return QStringLiteral("Matte everywhere you work, glass kept for the hero surface only — "
                              "so glass reads as a material with meaning rather than a texture.");
    }
    return QString();
}

bool ThemeManager::styleUsesGlass(bool heroSurface) const
{
    switch (style_)
    {
    case Style::RefinedGlass:    return true;
    case Style::MatteInstrument: return false;
    case Style::Hybrid:          return heroSurface;
    }
    return true;
}

void ThemeManager::setStyle(Style style)
{
    if (style_ == style)
        return;

    style_ = style;
    // Style changes GlassFill/GlassHighlight (matte is opaque), so the tokens must be rebuilt
    // before themeChanged fires or subscribers repaint with the previous material's values.
    rebuildColorTokens();
    save();
    emit themeChanged();
}

void ThemeManager::setStyleByIndex(int index)
{
    if (index < 0 || index >= styleNames().size())
        return;
    setStyle(static_cast<Style>(index));
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
    case Chrome::TitleBarHeight:    return 44;
        case Chrome::MenuBarHeight:     return 40;
        case Chrome::ModeRailWidth:     return 64;
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
    // Three weights, the three Plex ships: 400 read, 500 label, 600 announce. 700 and 800 left
    // with the Segoe era; a heavier weight was the only way Segoe could look intentional.
    switch (token)
    {
    case Type::Display:    return 600;
    case Type::Title:      return 600;
    case Type::Heading:    return 600;
    case Type::Subtitle:   return 500;
    case Type::Body:       return 400;
    case Type::BodyStrong: return 500;
    case Type::Detail:     return 400;
    case Type::Label:      return 500;
    case Type::Caption:    return 500;
    case Type::Micro:      return 500;
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

QFont ThemeManager::numericFont() const
{
    // Tabular figures: every digit the same width, so a status-bar value or a chip does not
    // wobble as it counts. Plex carries the tnum feature; the fallback face may ignore it.
    QFont f = font(Type::Body);
    f.setFeature(QFont::Tag("tnum"), 1);
    return f;
}

QString ThemeManager::fontCss(Type token) const
{
    return QStringLiteral("font-size:%1px;font-weight:%2;").arg(fontSize(token)).arg(fontWeight(token));
}

int ThemeManager::radiusCard() const
{
    // Radius is part of the material, not the palette. Large radii are what make a dense tool read
    // as a consumer app, so the matte instrument is the tightest and glass is allowed the softest.
    switch (style_)
    {
    case Style::MatteInstrument: return 6;
    case Style::Hybrid:          return 8;
    case Style::RefinedGlass:    break;
    }
    return 10; // instrument card, not marketing blob
}

int ThemeManager::radiusControl() const
{
    switch (style_)
    {
    case Style::MatteInstrument: return 4;
    case Style::Hybrid:          return 5;
    case Style::RefinedGlass:    break;
    }
    return 6; // Linear control default
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
    style_ = static_cast<Style>(
        qBound(0, settings.value(QStringLiteral("appearance/surfaceStyle"),
                                 static_cast<int>(Style::RefinedGlass)).toInt(), styleNames().size() - 1));

    // One-time showcase maturity migration: land on ArcaneGlass (the design north star) with a
    // slightly richer effects floor. Users can still switch themes afterward; this only runs once.
    if (!settings.value(QStringLiteral("appearance/showcaseMaturityPass_v1")).toBool()) {
        preset_ = Preset::ArcaneGlass;
        usePresetAccent_ = true;
        accentOverride_ = QColor();
        effectsWeight_ = qMax(effectsWeight_, 74);
        if (animationQuality_ == AnimationQuality::Minimal)
            animationQuality_ = AnimationQuality::Rich;
        settings.setValue(QStringLiteral("appearance/showcaseMaturityPass_v1"), true);
        settings.setValue(QStringLiteral("appearance/themePreset"), static_cast<int>(preset_));
        settings.setValue(QStringLiteral("appearance/usePresetAccent"), usePresetAccent_);
        settings.setValue(QStringLiteral("appearance/effectsWeight"), effectsWeight_);
        settings.setValue(QStringLiteral("ui/animationQuality"), static_cast<int>(animationQuality_));
    }
}

void ThemeManager::save() const
{
    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    settings.setValue(QStringLiteral("appearance/themePreset"), static_cast<int>(preset_));
    settings.setValue(QStringLiteral("appearance/usePresetAccent"), usePresetAccent_);
    settings.setValue(QStringLiteral("appearance/accentOverride"), accentOverride_);
    settings.setValue(QStringLiteral("appearance/effectsWeight"), effectsWeight_);
    settings.setValue(QStringLiteral("ui/animationQuality"), static_cast<int>(animationQuality_));
    settings.setValue(QStringLiteral("appearance/surfaceStyle"), static_cast<int>(style_));
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
    rebuildPresetColorTokens();
    applyStyleToColorTokens();
}

// The MATERIAL pass, applied on top of whichever palette the preset authored. Keeping it separate is
// what makes style x preset a real matrix instead of 15 hand-maintained palettes: a preset owns the
// hues, a style owns translucency, glow and hairline weight, and every pairing composes.
void ThemeManager::applyStyleToColorTokens()
{
    auto put = [this](Color c, const QColor &v) { colorTokens_[static_cast<int>(c)] = v; };
    const QColor surface1 = color(Color::Surface1);
    const QColor accent = color(Color::Accent);

    switch (style_)
    {
    case Style::RefinedGlass:
        // The palette's own glass values already describe this material. One discipline is applied:
        // the accent glow is the ONLY light source, so it is allowed to stay while the neutral
        // highlight is pulled back to a rim rather than a wash.
        put(Color::GlassHighlight, scaleAlpha(color(Color::GlassHighlight), 0.72));
        break;

    case Style::MatteInstrument:
    {
        // Opaque, and no light emitted anywhere. Any surface that reads GlassFill directly gets a
        // solid colour rather than something it would have to composite, and the glow tokens go to
        // fully transparent so a stray call site cannot paint a halo into a matte theme.
        QColor solid = surface1;
        solid.setAlpha(255);
        put(Color::GlassFill, solid);
        put(Color::GlassGlow, QColor(0, 0, 0, 0));
        put(Color::GlassHighlight, QColor(0, 0, 0, 0));
        // Hairlines carry all the structure now, so they have to be readable on their own.
        put(Color::Border, scaleAlpha(color(Color::Border), 1.45));
        put(Color::BorderSubtle, scaleAlpha(color(Color::BorderSubtle), 1.35));
        // Deepen the ground so the elevation step does the work the glow used to. Only Surface0
        // moves, and only AWAY from the text: on a dark theme it darkens, on a light one it
        // lightens. Both directions increase text contrast, so this cannot break the WCAG assert --
        // which matters, because that assert is a Q_ASSERT_X that aborts a Debug build.
        {
            const QColor ground = color(Color::Surface0);
            const bool lightTheme = ground.lightnessF() > 0.5;
            put(Color::Surface0, lightTheme ? ground.lighter(104) : ground.darker(126));
        }
        // Accent tints are decoration in a matte theme; keep only enough for selection.
        put(Color::AccentGlow, QColor(0, 0, 0, 0));
        put(Color::AccentSubtle, withAlpha(accent, 0.08));
        break;
    }

    case Style::Hybrid:
        // Glass tokens stay glass, because the hero surface still uses them. Everything else paints
        // matte from the surface tokens, decided per panel by styleUsesGlass(). The one palette
        // change is a firmer hairline, since most surfaces are now matte and rely on it.
        put(Color::Border, scaleAlpha(color(Color::Border), 1.25));
        put(Color::GlassHighlight, scaleAlpha(color(Color::GlassHighlight), 0.85));
        break;
    }
}

void ThemeManager::rebuildPresetColorTokens()
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
        put(Color::Border, QColor(150, 160, 186, 42));      // platinum hairline — structural device
        put(Color::BorderStrong, QColor(198, 182, 255, 70)); // violet-tinted emphasis (active/focus)
        put(Color::BorderSubtle, QColor(150, 160, 186, 22)); // faint
        put(Color::Success, QColor(QStringLiteral("#34D6E6"))); // ready/online — the only cyan
        put(Color::Warning, QColor(QStringLiteral("#E8B23A")));
        put(Color::Error, QColor(QStringLiteral("#D85D73")));
        put(Color::Info, QColor(QStringLiteral("#4C9AE6")));
        put(Color::GlassFill, QColor(19, 22, 31, 228));      // denser glass body
        put(Color::GlassGlow, QColor(124, 92, 255, 52));
        put(Color::GlassHighlight, QColor(228, 232, 244, 38)); // brighter platinum rim
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

    if (preset_ == Preset::ObsidianStudio)
    {
        // Obsidian Studio — neutral graphite, steel-blue accent. The restrained one: nothing here
        // competes with content, which is what makes it the natural pairing for MatteInstrument.
        //
        // The accent ramp is SOLVED, not picked. Every shade a button can be filled with must keep a
        // white label at >=4.5:1 AND stay >=3:1 against Surface1 so the control is findable. Those
        // two pull in opposite directions, and the earlier candidate #5B8DEF read beautifully on the
        // surface (5.61) while its own label sat at 3.23 -- the exact flaw the design review found in
        // two of the three mockups. The band that satisfies both is narrow; these are inside it.
        put(Color::Surface0, QColor(QStringLiteral("#0B0E13")));
        put(Color::Surface1, QColor(QStringLiteral("#12161D")));
        put(Color::Surface2, QColor(QStringLiteral("#171C25")));
        put(Color::Surface3, QColor(QStringLiteral("#1E242F")));
        put(Color::TextHi, QColor(QStringLiteral("#E6EAF0")));
        put(Color::TextMid, QColor(QStringLiteral("#A2AAB8")));
        put(Color::TextLo, QColor(QStringLiteral("#8B94A4")));
        put(Color::TextDisabled, QColor(QStringLiteral("#6B7382")));
        put(Color::Accent, QColor(QStringLiteral("#3568D0")));        // white label 5.20, surface 3.49
        put(Color::AccentHover, QColor(QStringLiteral("#4171D2")));   // white label 4.65, surface 3.90
        put(Color::AccentActive, QColor(QStringLiteral("#2E5FC2")));  // white label 5.95, surface 3.05
        put(Color::AccentDisabled, QColor(QStringLiteral("#2A3547")));
        put(Color::AccentGlow, QColor(53, 104, 208, 70));
        put(Color::AccentSubtle, QColor(53, 104, 208, 24));
        put(Color::AccentSecondary, QColor(QStringLiteral("#2B4C93")));
        put(Color::AccentTertiary, QColor(QStringLiteral("#A8C4FF")));
        put(Color::Border, QColor(156, 168, 190, 40));
        put(Color::BorderStrong, QColor(168, 196, 255, 68));
        put(Color::BorderSubtle, QColor(156, 168, 190, 20));
        put(Color::Success, QColor(QStringLiteral("#3DD68C")));
        put(Color::Warning, QColor(QStringLiteral("#E8B23A")));
        put(Color::Error, QColor(QStringLiteral("#E5606B")));
        put(Color::Info, QColor(QStringLiteral("#4C9AE6")));
        put(Color::GlassFill, QColor(18, 22, 29, 232));
        put(Color::GlassGlow, QColor(53, 104, 208, 44));
        put(Color::GlassHighlight, QColor(220, 228, 240, 34));
        return;
    }

    if (preset_ == Preset::NeonForge)
    {
        // Neon Forge — deep indigo ground with an electric magenta. The high-energy one; it carries
        // RefinedGlass best because it actually wants a light source.
        //
        // Same solved ramp as Obsidian: the vivid #E040FB stays, but as AccentTertiary/glow where it
        // is never a text background. Using it as a button fill put its own label at 3.34:1.
        put(Color::Surface0, QColor(QStringLiteral("#070A14")));
        put(Color::Surface1, QColor(QStringLiteral("#0E1322")));
        put(Color::Surface2, QColor(QStringLiteral("#141B2E")));
        put(Color::Surface3, QColor(QStringLiteral("#1B243C")));
        put(Color::TextHi, QColor(QStringLiteral("#EAECF7")));
        put(Color::TextMid, QColor(QStringLiteral("#A0A8C4")));
        put(Color::TextLo, QColor(QStringLiteral("#8992B0")));
        put(Color::TextDisabled, QColor(QStringLiteral("#69718F")));
        put(Color::Accent, QColor(QStringLiteral("#B425C1")));        // white label 5.28, surface 3.50
        put(Color::AccentHover, QColor(QStringLiteral("#C428D2")));   // white label 4.58, surface 4.04
        put(Color::AccentActive, QColor(QStringLiteral("#A421B0")));  // white label 6.14, surface 3.02
        put(Color::AccentDisabled, QColor(QStringLiteral("#3A2445")));
        put(Color::AccentGlow, QColor(224, 64, 251, 78));
        put(Color::AccentSubtle, QColor(224, 64, 251, 26));
        put(Color::AccentSecondary, QColor(QStringLiteral("#7A1C93")));
        put(Color::AccentTertiary, QColor(QStringLiteral("#F0A8FF")));
        put(Color::Border, QColor(160, 168, 196, 44));
        put(Color::BorderStrong, QColor(240, 168, 255, 74));
        put(Color::BorderSubtle, QColor(160, 168, 196, 22));
        put(Color::Success, QColor(QStringLiteral("#22E0A0")));
        put(Color::Warning, QColor(QStringLiteral("#FFC53D")));
        put(Color::Error, QColor(QStringLiteral("#FF5470")));
        put(Color::Info, QColor(QStringLiteral("#4CC4FF")));
        put(Color::GlassFill, QColor(14, 19, 34, 226));
        put(Color::GlassGlow, QColor(224, 64, 251, 56));
        put(Color::GlassHighlight, QColor(226, 232, 248, 40));
        return;
    }

    if (preset_ == Preset::IvoryHolograph)
    {
        // Ivory Holograph — the light theme, and the one the derived path served worst, because
        // every relationship inverts: surfaces get LIGHTER as they rise, text darkens, and a glow
        // that reads as light on a dark ground reads as dirt on a pale one. So its glass tokens are
        // a near-white frost with almost no glow, and its hairlines are dark rather than light.
        put(Color::Surface0, QColor(QStringLiteral("#EEF2F9")));
        put(Color::Surface1, QColor(QStringLiteral("#F7FAFF")));
        put(Color::Surface2, QColor(QStringLiteral("#FFFFFF")));
        put(Color::Surface3, QColor(QStringLiteral("#E4EAF6")));
        put(Color::TextHi, QColor(QStringLiteral("#101826")));
        put(Color::TextMid, QColor(QStringLiteral("#3E4C61")));
        put(Color::TextLo, QColor(QStringLiteral("#5A6880")));
        put(Color::TextDisabled, QColor(QStringLiteral("#7A8698")));
        put(Color::Accent, QColor(QStringLiteral("#5A3FD6")));        // white label 6.74
        put(Color::AccentHover, QColor(QStringLiteral("#6E55E4")));   // white label 5.14
        put(Color::AccentActive, QColor(QStringLiteral("#4A32BC")));  // white label 8.49
        put(Color::AccentDisabled, QColor(QStringLiteral("#BDB4E8")));
        put(Color::AccentGlow, QColor(90, 63, 214, 40));
        put(Color::AccentSubtle, QColor(90, 63, 214, 18));
        put(Color::AccentSecondary, QColor(QStringLiteral("#3A2699")));
        put(Color::AccentTertiary, QColor(QStringLiteral("#8B74F0")));
        put(Color::Border, QColor(56, 74, 104, 46));   // dark hairline: light ground inverts this
        put(Color::BorderStrong, QColor(90, 63, 214, 82));
        put(Color::BorderSubtle, QColor(56, 74, 104, 24));
        put(Color::Success, QColor(QStringLiteral("#0F9D6B")));
        put(Color::Warning, QColor(QStringLiteral("#B26A00")));
        put(Color::Error, QColor(QStringLiteral("#C62D42")));
        put(Color::Info, QColor(QStringLiteral("#1B6FD0")));
        put(Color::GlassFill, QColor(247, 250, 255, 236));
        put(Color::GlassGlow, QColor(90, 63, 214, 22));
        put(Color::GlassHighlight, QColor(255, 255, 255, 96));
        return;
    }

    // Fallback: derive from the existing accessors (no preset reaches this today).
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

    // The radii here are the material's, not literals: a popup that escapes the cascade still
    // belongs to the same surface style as the window behind it. ALL of them are radiusControl(),
    // which is what spec S2.4 says ("its radii move to radiusControl()") -- the menu and the combo
    // popup read radiusCard() when this converted, on the argument that a popup is panel-sized.
    // The written rule wins over the per-site read, for the reason the Inset radii were corrected
    // in 095a87c: otherwise the same judgement call is re-litigated every wave.
    QString sheet = QStringLiteral(
        "QToolTip { background:%1; color:%2; border:1px solid %3; border-radius:@rctl@; padding:4px 8px; }"
        "QMenu { background:%4; color:%2; border:1px solid %3; border-radius:@rctl@; padding:4px; }"
        "QMenu::item { padding:5px 22px 5px 20px; border-radius:@rctl@; }"
        "QMenu::item:selected { background:%5; color:%2; }"
        "QMenu::separator { height:1px; background:%3; margin:4px 8px; }"
        "QComboBox QAbstractItemView { background:%4; color:%2; border:1px solid %3; border-radius:@rctl@;"
        " selection-background-color:%5; selection-color:%2; outline:none; padding:2px; }"
        "QMessageBox, QInputDialog { background:%4; }"
        "QMessageBox QLabel, QInputDialog QLabel { color:%2; background:transparent; }"
        "QMessageBox QPushButton, QInputDialog QPushButton { background:%6; color:%2; border:1px solid %3;"
        " border-radius:@rctl@; padding:5px 14px; min-width:72px; }"
        "QMessageBox QPushButton:hover, QInputDialog QPushButton:hover { background:%7; border-color:%8; }")
        .arg(bgTip, text, border, bgMenu, sel, btn, btnHover, btnHoverBorder)
        .replace(QLatin1String("@rctl@"), QString::number(radiusControl()) + QLatin1String("px"));
    assertNoUnresolvedTokens(sheet, QStringLiteral("applicationOverlayStyleSheet"));
    return sheet;
}

void ThemeManager::applyApplicationChrome() const
{
    // Push the themed palette + overlay sheet onto qApp, then re-polish every widget so the proxy
    // style repaints from the new tokens. Called once at startup (from main) and auto-reapplied on
    // themeChanged (wired in the ctor).
    if (!qApp)
        return;
    qApp->setPalette(buildPalette());
    qApp->setStyleSheet(applicationOverlayStyleSheet());
    spellvision::style::SvStyle::refreshAll();
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
    // surfaceA/surfaceB). Feeds the #CustomTitleBar gradient stops (@titleBarEdge@ / @titleBarCenter@) only.
    const bool arcane = (preset_ == Preset::ArcaneGlass);
    const QColor titleBarA = arcane ? mix(mix(color(Color::Surface2), QColor(QStringLiteral("#7E8AB0")), 0.10), accent2, 0.08) : surfaceA;
    const QColor titleBarB = arcane ? mix(mix(color(Color::Surface2), QColor(QStringLiteral("#7E8AB0")), 0.14), accent2, 0.11) : surfaceB;
    const QColor softBorder = withAlpha(borderTok, lerp(0.18, 0.42, w));
    const QColor focus = withAlpha(accent, lerp(0.46, 0.90, w));
    const QColor focusSoft = withAlpha(accent, lerp(0.14, 0.32, w));

    const QString sheet = QStringLiteral(
        "QMainWindow { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 @pageGlow@, stop:0.55 @void@, stop:1 @void@); color: @textHi@; }"
        "QWidget { selection-background-color: @selectionFill@; selection-color: @textHi@; }"

        "#CustomTitleBar {"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 @titleBarEdge@, stop:0.5 @titleBarCenter@, stop:1 @titleBarEdge@);"
        "}"
        // Transition strip below the bar: ramps the bar's center tone (@titleBarCenter@ = titleBarB) down to
        // the page void (@void@ = bg0) so the bar->body edge dissolves -- no hard seam, no hairline.
        "#TitleBarTransitionStrip {"
        " background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 @titleBarCenter@, stop:1 @void@);"
        "}"
        "#SpellVisionTitleLabel { color: transparent; }"
        // The mode breadcrumb is a deliberate VSCode-style element (CustomTitleBar homes it in the
        // layout), so it gets the body text colour. It was "transparent" here, and on the light
        // preset that rendered as a half-visible ghost -- "nage" beside the badge for "Text to
        // Image" -- rather than nothing: an element is either shown with a colour or not shown.
        "#SpellVisionContextLabel { color: @textHi@; }"
        "#SpellVisionLogoBadge {"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 @accent@, stop:0.55 @accentSecondary@, stop:1 @accentTertiary@);"
        " border: 1px solid @badgeEdge@;"
        " border-radius: @rctl@;"
        "}"

        "#CustomTitleBar QPushButton { padding: 2px 8px; @bodystrong@ }"

        "#TitleBarSearchPill {"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 @panelFill@, stop:1 @panelFillRaised@);"
        " border: 1px solid @hairline@; border-radius: @rcard@;"
        "}"
        "#TitleBarSearchPill:hover {"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 @panelFillRaised@, stop:1 @pillHoverFill@);"
        " border-color: @accentEdge@;"
        "}"
        "#TitleBarSearchText { color: @textHi@; @bodystrong@ }"
        "#TitleBarSearchShortcut { color: @textLo@; @label@ }"
        /* Phase 6 Simple/Advanced segmented toggle. The track is Surface::Inset and the two
           buttons are Role::Tab, both set in CustomTitleBar; only the spacing is left here. */
        "#TitleBarModeButton { padding: 2px 11px; @label@ }"

        "#CustomTitleBar QToolButton { padding: 0px; }"
        // The close button is Role::Danger; its hover comes from the Error token, not a literal.

        "#SideRail { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 @railBand@, stop:1 @void@); border-right: 1px solid @hairlineSoft@; }"

        "QHeaderView::section { padding: 8px; }"

        "QMenu { background: @panelFill@; color: @textMid@; border: 1px solid @hairlineFaint@; border-radius: @rcard@; }"
        "QMenu::item { padding: 7px 18px; border-radius: @rctl@; }"
        "QMenu::item:selected { background: @accentWashSoft@; }"

        "QDockWidget { color: @textMid@; }"
        "QDockWidget::title {"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 @panelFill@, stop:1 @panelFillRaised@);"
        " text-align: left; padding: 8px 12px; border-bottom: 1px solid @hairlineFaint@; font-weight: 600;"
        "}"

        "QPushButton { padding: 5px 11px; min-height: 30px; }"

        "QLabel#ShellSectionTitle { @title@ color: @textHi@; }"
        "QStatusBar {"
        " background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 @cardTop@, stop:1 @cardBottom@);"
        " border-top: 1px solid @cardEdge@; min-height: 40px; max-height: 40px; padding: 0px; }"
        "QStatusBar::item { border: none; }"
        "QFrame#BottomTelemetryContainer {"
        " background: transparent; border: none; padding: 0 8px; }"
        "QLabel#BottomReadyLabel {"
        " background: @successBg@; color: @successFg@; border: 1px solid @successBd@; border-radius: @rctl@;"
        " padding: 2px 8px; @label@ font-weight: 600; }"
        "QLabel#BottomPageLabel { color: @textHi@; @label@ font-weight: 600; padding-left: 6px; }"
        "QLabel#BottomBackendLabel, QLabel#BottomQueueLabel, QLabel#BottomVramLabel,"
        "QLabel#BottomModelLabel, QLabel#BottomLoraLabel, QLabel#BottomStateLabel, QLabel#BottomEtaLabel {"
        " color: @textMid@; @detail@ padding: 0 4px; }"
        "QLabel#BottomQueueLabel { color: @textHi@; }"
        "QLabel#BottomStateLabel { color: @textHi@; @label@ }"
        "QStatusBar QLabel { color: @textMid@; @detail@ }"
        "QWidget#MainPageStack { background: transparent; }"
        "QWidget#SideRail { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 @railBase@, stop:0.45 @railBase@, stop:1 @railBase@); border-right: 1px solid @railEdge@; }"
        // No rule for the rail tile at all. Its 5% wash, its 2px accent bar and its label weight
        // are Role::Rail in SvStyle, and createRailButton() gives it a fixed 56x48 and a 10px
        // under-icon label on purpose -- so a font-size or a padding here can only take room away
        // from those labels. The first live run of this sheet, with the old rule's
        // `@label@ padding: 8px 2px`, clipped six of them to "Concep"/"Datase"/"Runtim".
        // The drawer's panels are Surface::Panel, set by createPanelFrame in MainWindow.
        "QLabel#QueueActiveEyebrow, QLabel#DetailsEyebrow { @caption@ color: @accent@; }"
        "QLabel#QueueActiveTitle, QLabel#DetailsTitle { @heading@ color: @textHi@; }"
        "QLabel#QueueActiveBody, QLabel#DetailsBody { @detail@ color: @textMid@; }"
        "QLabel#DetailsMetaLabel { @micro@ color: @textLo@; text-transform: uppercase; letter-spacing: 0.08em; }"
        "QLabel#DetailsMetaValue { @label@ color: @textHi@; background: @cardBottom@; border: 1px solid @cardEdge@; border-radius: @rcard@; padding: 1px 8px; }"
        "QPushButton#DetailsPrimaryActionButton { min-height: 30px; @label@ }"
        "QPushButton#DetailsSecondaryActionButton { min-height: 28px; @label@ }"
        "QPushButton#DetailsActionButton { min-height: 30px; @label@ }"
        "QTextEdit#LogsView { padding: 8px; }"
        /* SPRINT MOCKUP PASS 3 DISCLOSURE PROMOTION */ "QLabel#SectionTitle { @heading@ color: @textHi@; background: transparent; }"
        "QLabel#SectionBody { @body@ color: @textLo@; background: transparent; }"
        "QSplitter::handle { background: transparent; }"
        "QSplitter::handle:hover { background: @accentWashSoft@; }"
        "QScrollArea { background: transparent; border: none; }"
        "QLabel#SideRailCaption { color: @textLo@; @caption@ letter-spacing: 0.08em; }"
        "QLabel#RailSectionHeader { color: @textLo@; @micro@ letter-spacing: 0.16em; padding: 10px 0 4px 0; background: transparent; }"
        /* Studio-layout CockpitInspector (phase 2 scaffold) -- 340px tabbed right column */
        "#CockpitInspector { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 @cardTop@, stop:1 @cardBottom@); border-left: 1px solid @cardEdge@; }"
        "#InspectorTabBar { background: transparent; }"
        "#InspectorTab { padding: 7px 4px; @label@ }"
        "#InspectorPlaceholder { color: @textLo@; @body@ }"
        // No rule for #InspectorReadinessStrip: it is Surface::Inset in CockpitInspector now, and a
        // background here would paint over the surface the style draws.
        "#InspectorReadinessText { color: @textMid@; @label@ }"
        /* Phase 5 activity drawer (queueOverlay_): the solid container fill comes from
           autoFillBackground + an opaque palette (MainWindow), so the drawer is never see-through.
           The header (a QFrame, paints natively) sits on that base in the rail/status tone (@railBand@),
           with a hairline divider (@hairlineFaint@) and the title in textPrimary (@textHi@). */
        "#QueueOverlayHeader { background: @railBand@; border-bottom: 1px solid @hairlineFaint@; }"
        "#QueueOverlayTitle { @subtitle@ color: @textHi@; background: transparent; }"
        "QFrame#SideRailDivider { background: @hairlineFaint@; min-height: 1px; max-height: 1px; border: none; }"

        // The RailButton and ActiveJobCard rules went with the widgets that carried them -- there
        // is no object by either name in the tree. The ActiveJob label rules below are the remains.
        "#ActiveJobTitle { @heading@ color: @textHi@; }"
        "#ActiveJobPrompt { color: @textMid@; @body@ }"
        "#ActiveJobMeta { color: @textLo@; @body@ }"
        "#ActiveJobStatus { color: @textMid@; @body@ }"
        "#ActiveJobBadge { padding: 4px 10px; border-radius: @rcard@; font-weight: 600; }"
        // Phase 6: bottom telemetry chrome moved from local setStyleSheets into the shell
        // stylesheet (reuses existing tokens) so the progress bar + separators switch on
        // themeChanged too -- was a stale blue/violet block.
        "QProgressBar#BottomProgressBar { @micro@ text-align: center; min-height: 14px; max-height: 14px; }"
        "QFrame#BottomTelemetrySeparator { background: @cardEdge@; border: none; min-width: 1px; max-width: 1px; margin: 4px 2px; }"

        // Focus, pressed and disabled are the control's own states, so SvStyle draws them:
        // CE_PushButtonBevel strokes the accent ring on State_HasFocus and buttonPaint() reads
        // State_Sunken and State_Enabled. A sheet rule here would only cover them up.
        // A QLabel is not a control the style owns, so its disabled colour stays.
        "QLabel:disabled { color: @disabledFg@; }"
        
        )
        // Named tokens, not positional arguments. QString::arg resolves a multi-argument call by
        // sorting the DISTINCT placeholder numbers it finds and feeding them in that order, so
        // adding or deleting one %N renumbered every later colour -- the 2026-07-25 lavender void,
        // and again on 2026-07-12 when a progress-bar rule introduced %7 into a sheet whose args
        // were numbered from %8 up. That left 62 placeholders against 61 arguments, so %62 was
        // never substituted, the QMainWindow rule would not parse, and Qt discarded the WHOLE
        // sheet ("Could not parse stylesheet of object MainWindow"). A named token cannot renumber
        // anything and a missing one is caught by assertNoUnresolvedTokens below.
        .replace(QLatin1String("@void@"), bg0.name())  // the page void
        .replace(QLatin1String("@pageGlow@"), rgba(pageGlow, 1.0))  // shell canvas top-glow (QMainWindow gradient)
        .replace(QLatin1String("@textHi@"), color(Color::TextHi).name())
        .replace(QLatin1String("@textMid@"), color(Color::TextMid).name())
        .replace(QLatin1String("@textLo@"), color(Color::TextLo).name())
        .replace(QLatin1String("@accent@"), accent.name())
        .replace(QLatin1String("@accentSecondary@"), accent2.name())
        .replace(QLatin1String("@accentTertiary@"), accent3.name())
        .replace(QLatin1String("@selectionFill@"), rgba(focus, 0.36))  // QWidget selection background
        .replace(QLatin1String("@titleBarEdge@"), rgba(titleBarA, 1.0))  // title-bar band, edge
        .replace(QLatin1String("@titleBarCenter@"), rgba(titleBarB, 1.0))  // title-bar band, centre
        .replace(QLatin1String("@badgeEdge@"), rgba(withAlpha(color(Color::TextHi), preset_ == Preset::IvoryHolograph ? 0.20 : 0.36)))  // logo badge hairline
        .replace(QLatin1String("@panelFill@"), panelFillCss(Color::Surface1))
        .replace(QLatin1String("@panelFillRaised@"), panelFillCss(Color::Surface2))
        .replace(QLatin1String("@hairline@"), rgba(softBorder, 0.95))
        .replace(QLatin1String("@hairlineSoft@"), rgba(softBorder, 0.70))
        .replace(QLatin1String("@hairlineFaint@"), rgba(softBorder, 0.55))
        .replace(QLatin1String("@accentEdge@"), rgba(focus, 1.0))  // focused field border
        .replace(QLatin1String("@accentWashSoft@"), rgba(focusSoft, 1.0))  // pressed / selected wash
        .replace(QLatin1String("@pillHoverFill@"), rgba(mix(color(Color::Surface2), accent2, 0.25), 0.98))  // search pill, hover
        .replace(QLatin1String("@railBand@"), rgba(mix(bg1, color(Color::Surface1), 0.55), 0.98))  // rail / drawer-header band
        .replace(QLatin1String("@railBase@"), rgba(bg0, 0.998))
        .replace(QLatin1String("@railEdge@"), rgba(accent, 0.28))
        .replace(QLatin1String("@cardTop@"), rgba(surfaceB, 1.0))
        .replace(QLatin1String("@cardBottom@"), rgba(bg0, 0.98))  // card bottom / logs / inspector strip
        .replace(QLatin1String("@cardEdge@"), rgba(softBorder, 0.9))
        .replace(QLatin1String("@title@"), fontCss(Type::Title))
        .replace(QLatin1String("@heading@"), fontCss(Type::Heading))
        .replace(QLatin1String("@subtitle@"), fontCss(Type::Subtitle))
        .replace(QLatin1String("@body@"), fontCss(Type::Body))
        .replace(QLatin1String("@bodystrong@"), fontCss(Type::BodyStrong))
        .replace(QLatin1String("@detail@"), fontCss(Type::Detail))
        .replace(QLatin1String("@label@"), fontCss(Type::Label))
        .replace(QLatin1String("@caption@"), fontCss(Type::Caption))
        .replace(QLatin1String("@micro@"), fontCss(Type::Micro))
        .replace(QLatin1String("@successBg@"), rgba(withAlpha(color(Color::Success), 0.14), 1.0))
        .replace(QLatin1String("@successFg@"), color(Color::Success).name())
        .replace(QLatin1String("@successBd@"), rgba(withAlpha(color(Color::Success), 0.40), 1.0))
        // Style-aware geometry: the radius is part of the material, so it is read at build time.
        .replace(QLatin1String("@rcard@"), QString::number(radiusCard()) + QLatin1String("px"))
        .replace(QLatin1String("@rctl@"), QString::number(radiusControl()) + QLatin1String("px"))
        .replace(QLatin1String("@disabledFg@"), color(Color::TextDisabled).name());

    assertNoUnresolvedTokens(sheet, QStringLiteral("shellStyleSheet"));
    return sheet;
}

void ThemeManager::assertNoUnresolvedTokens(const QString &sheet, const QString &which)
{
#ifndef QT_NO_DEBUG
    // A token whose .replace() was never added does not fail -- Qt drops the property containing the
    // unparseable value and the rest of the sheet applies, so the symptom is one silently unstyled
    // widget, discovered by eye much later. Same failure shape as the contrast floors, so it gets
    // the same treatment: caught at startup, in Debug, with the offending token named.
    static const QRegularExpression token(QStringLiteral("@[A-Za-z][A-Za-z0-9]*@"));
    const QRegularExpressionMatch m = token.match(sheet);
    if (m.hasMatch())
    {
        qWarning().noquote() << QStringLiteral("[ThemeManager] %1 has an unresolved token %2 -- add a .replace() for it.")
                                    .arg(which, m.captured(0));
        Q_ASSERT_X(false, "ThemeManager::assertNoUnresolvedTokens", "a stylesheet token was never substituted (see qWarning)");
    }
#else
    Q_UNUSED(sheet)
    Q_UNUSED(which)
#endif
}

QString ThemeManager::imageGenerationStyleSheet() const
{
    // Phase 8: derive the IGP cockpit from canonical color() tokens (not legacy accessors) so
    // it switches with the theme. Post-reconcile the tokens match the accessors on ArcaneGlass,
    // so this is identity-preserving there. borderTok reproduces the old borderColor();
    // inputSurface (deferred in phase 2) -> Surface0 (inputs slightly darker, documented correction).
    //
    // Task 5 (the cockpit retreat): the card, prompt-card, canvas, button, field and stepper
    // colours that used to live here are gone with the rules that spent them. What is left is the
    // page ground, the semantic readiness palette, and the two chip fills -- none of which SvStyle
    // draws, because none of them is a control.
    const qreal w = weight01(effectsWeight_);
    const QColor accent = color(Color::Accent);
    const QColor tokSurface0 = color(Color::Surface0);
    const QColor borderTok = mix(color(Color::Surface2), accent, 0.18 + w * 0.24);
    const QColor border = withAlpha(borderTok, lerp(0.28, 0.74, w));
    const QColor input = withAlpha(tokSurface0, preset_ == Preset::IvoryHolograph ? 0.96 : 0.98);
    const QColor tertiaryBorder = withAlpha(border, 0.34);
    // Cockpit canvas top-glow -- same subtle accent lift as the shell/Home/Settings, so the cockpit
    // reads with depth instead of a flat Surface0 fill. Base of the gradient stays Surface0 (@base@).
    const QColor cockpitGlow = mix(tokSurface0, accent, 0.12 + w * 0.05);
    // The readiness dot is a circle: its radius is half its own size. That is geometry, not
    // material, which is why it is computed here instead of read from radiusControl().
    const int dotSize = 10;

    QString style = QStringLiteral(
        "#ImageGenerationPage { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 @pageGlow@, stop:0.5 @base@, stop:1 @base@); }"
        "QWidget#LeftRailContainer { background: transparent; }"
        "QScrollArea#LeftRailScrollArea { background: transparent; border: none; }"
        // No rule for a card here at all. The ten cockpit cards used to be one selector list with a
        // gradient, a rim and a 10px radius, plus two overrides for the prompt card and the canvas.
        // They are kit::setSurface() calls in buildUi now -- the canvas a Glass hero, the prompt card
        // a Plate, the rest Panels -- so the Surface Style setting reaches them. It could not reach
        // a literal.
        "QLabel#SectionTitle { @heading@ color: @textHi@; background: transparent; }"
        "QToolButton#InspectorSectionToggle { padding: 3px 10px; min-width: 62px; min-height: 22px; max-height: 26px; @caption@ }"
        "QLabel#SectionBody { @detail@ color: @textLo@; background: transparent; }"
        "QLabel#CompactFieldLabel { color: @textLo@; @caption@ background: transparent; }"
        // --- SPRINT MOCKUP PASS 2 QUICK CONTROLS STACKED: stacked-label field cells ---
        "QLabel#StackedFieldLabel { color: @textLo@; @label@ background: transparent; padding-bottom: 2px; }"
        "QLabel#ImageGenHint, QLabel#OutputQueueBodyHint { color: @textLo@; @detail@ background: transparent; }"
        "QLabel#OutputQueueBodyLabel { color: @textHi@; @caption@ background: transparent; }"
        "QLabel#AssetIntelligenceBody { color: @textMid@; @detail@ background: transparent; padding-top: 2px; }"
        "QLabel#StackSummary { color: @textMid@; @body@ background: transparent; }"
        "QLabel#PreviewSummary { color: @textLo@; @body@ background: transparent; padding-right: 12px; }"
        "QLabel#ReadinessHint { color: @textLo@; @label@ background: @disabledFill@; border: 1px solid @disabledEdge@; border-radius: @rcard@; padding: 6px 10px; min-height: 26px; }"
        // Shares the readiness hint's shape so the action row keeps one visual language. Muted
        // rather than accented: it reports that Advanced settings are in force, which is
        // information, not a warning -- the user chose those values.
        "QLabel#AdvancedOverrideHint { color: @textLo@; @label@ background: @disabledFill@; border: 1px dashed @disabledEdge@; border-radius: @rcard@; padding: 6px 10px; min-height: 26px; }"
        // The preview label keeps its padding and its type and nothing else: the image sits ON the
        // canvas plate now, instead of inside a second framed box drawn over it.
        "QLabel#PreviewSurface { padding: 18px; @subtitle@ }"
        "QLabel#PreviewSurface[emptyState=\"false\"] { padding: 4px; }"
        // Fields, buttons and steppers: spacing only, and the spin-box arrow well is SvStyle's
        // (CC_SpinBox) rather than two ::up-button/::down-button subcontrol rules.
        "QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox { padding: 5px 8px; min-height: 24px; }"
        "QSpinBox, QDoubleSpinBox { padding-right: 28px; }"
        "QPushButton, QToolButton { padding: 5px 10px; min-height: 30px; }"
        /* Generate is the single colored hero control. Its fill is Role::Primary in SvStyle; what
           is left here is the 40px height that makes it the tallest thing in the action row. */
        "QPushButton#PrimaryActionButton { min-height: 40px; padding: 8px 18px; letter-spacing: 0.02em; }"
        "QPushButton#SecondaryActionButton { min-height: 32px; }"
        "QPushButton#TertiaryActionButton { min-height: 30px; }"
        // No rule for readinessBlocked either. It is a STATE, and a stylesheet could only say it
        // by naming background, border-color and colour on an owned type -- which is how the
        // blocked button ended up with a `border-color` and no border-style, drawing no rim at all.
        // SvStyle::buttonPaint reads the property and dims the hero in place, radius and all.
        // --- SPRINT MOCKUP PASS 1 ASSET INTELLIGENCE: structured AI surface selectors ---
        "QFrame#AiReadinessStrip { background: @readyBg@; border: 1px solid @readyEdge@; border-radius: @rcard@; }"
        "QFrame#AiReadinessStrip[readiness=\"warn\"] { background: @warnBg@; border-color: @warnEdge@; }"
        "QFrame#AiReadinessStrip[readiness=\"block\"] { background: @blockBg@; border-color: @blockEdge@; }"
        "QLabel#AiReadinessDot { background: @readyDot@; border-radius: @dotRadius@; min-width: @dotSize@; max-width: @dotSize@; min-height: @dotSize@; max-height: @dotSize@; }"
        "QLabel#AiReadinessDot[readiness=\"warn\"] { background: @warnDot@; }"
        "QLabel#AiReadinessDot[readiness=\"block\"] { background: @blockDot@; }"
        "QLabel#AiReadinessText { @bodystrong@ color: @textHi@; background: transparent; }"
        "QLabel#AiReadinessSub { @detail@ color: @textLo@; background: transparent; }"
        "QLabel#AiGroupLabel { @caption@ color: @textLo@; background: transparent; }"
        "QLabel#AiChipSet { background: @chipSetFill@; border: 1px solid @chipSetEdge@; border-radius: @rctl@; padding: 2px 8px; color: @textHi@; @detail@ min-height: 18px; }"
        "QLabel#AiChipAuto { background: @fieldFill@; border: 1px dashed @fieldEdge@; border-radius: @rctl@; padding: 2px 8px; color: @textLo@; @detail@ min-height: 18px; }"
        "QFrame#AiTimingRow { background: transparent; border-top: 1px solid @tertiaryEdge@; }"
        "QLabel#AiTimingValue { @subtitle@ color: @textHi@; background: transparent; }"
        "QLabel#AiTimingKey { @caption@ color: @textLo@; background: transparent; }"
        "QToolButton#AiDetailsToggle { padding: 4px 0px; @label@ min-height: 18px; }"
        "QLabel#AiDetailsBody { color: @textMid@; @detail@ background: transparent; padding-top: 4px; }"
        // --- END SPRINT MOCKUP PASS 1 ASSET INTELLIGENCE ---
        /* Live sampling chips under the canvas -- dense instrument readouts */
        "QLabel#CanvasMetricChip { background: @fieldFill@; border: 1px solid @fieldEdge@; border-radius: @rctl@; padding: 3px 8px; color: @textLo@; @caption@ }"
    );

    // Named tokens, not positional arguments: a rule can be deleted without renumbering the
    // colours after it. Every @token@ below is resolved here and asserted resolved before return.
    style.replace(QLatin1String("@base@"), tokSurface0.name())  // page ground
         .replace(QLatin1String("@pageGlow@"), rgba(cockpitGlow, 1.0))  // cockpit canvas top-glow
         .replace(QLatin1String("@textHi@"), color(Color::TextHi).name())
         .replace(QLatin1String("@textLo@"), color(Color::TextLo).name())
         .replace(QLatin1String("@textMid@"), color(Color::TextMid).name())
         .replace(QLatin1String("@fieldFill@"), rgba(input, 1.0))
         .replace(QLatin1String("@fieldEdge@"), rgba(withAlpha(border, 0.95), 1.0))
         .replace(QLatin1String("@tertiaryEdge@"), rgba(tertiaryBorder, 1.0))
         .replace(QLatin1String("@disabledEdge@"), rgba(withAlpha(borderTok, 0.38), 1.0))
         .replace(QLatin1String("@disabledFill@"), rgba(withAlpha(tokSurface0, 1.0), 1.0))
         // Semantic readiness palette -- state, not decoration, so it stays in the sheet.
         .replace(QLatin1String("@readyBg@"), rgba(withAlpha(color(Color::Success), 0.10), 1.0))
         .replace(QLatin1String("@readyEdge@"), rgba(withAlpha(color(Color::Success), 0.34), 1.0))
         .replace(QLatin1String("@readyDot@"), color(Color::Success).name())
         .replace(QLatin1String("@warnBg@"), rgba(withAlpha(color(Color::Warning), 0.10), 1.0))
         .replace(QLatin1String("@warnEdge@"), rgba(withAlpha(color(Color::Warning), 0.34), 1.0))
         .replace(QLatin1String("@warnDot@"), color(Color::Warning).name())
         .replace(QLatin1String("@blockBg@"), rgba(withAlpha(color(Color::Error), 0.10), 1.0))
         .replace(QLatin1String("@blockEdge@"), rgba(withAlpha(color(Color::Error), 0.34), 1.0))
         .replace(QLatin1String("@blockDot@"), color(Color::Error).name())
         .replace(QLatin1String("@chipSetFill@"), rgba(withAlpha(accent, 0.10), 1.0))  // chip when is="set"
         .replace(QLatin1String("@chipSetEdge@"), rgba(withAlpha(accent, 0.42), 1.0))
         // Style-aware geometry: the radius is part of the material, so it is read at build time.
         .replace(QLatin1String("@rcard@"), QString::number(radiusCard()) + QLatin1String("px"))
         .replace(QLatin1String("@rctl@"), QString::number(radiusControl()) + QLatin1String("px"))
         .replace(QLatin1String("@dotSize@"), QString::number(dotSize) + QLatin1String("px"))
         .replace(QLatin1String("@dotRadius@"), QString::number(dotSize / 2) + QLatin1String("px"))
         // Typography: expand the @role@ markers to fontCss(Type::X) (size + weight from the scale).
         .replace(QLatin1String("@heading@"), fontCss(Type::Heading))
         .replace(QLatin1String("@subtitle@"), fontCss(Type::Subtitle))
         .replace(QLatin1String("@body@"), fontCss(Type::Body))
         .replace(QLatin1String("@bodystrong@"), fontCss(Type::BodyStrong))
         .replace(QLatin1String("@detail@"), fontCss(Type::Detail))
         .replace(QLatin1String("@label@"), fontCss(Type::Label))
         .replace(QLatin1String("@caption@"), fontCss(Type::Caption));

    assertNoUnresolvedTokens(style, QStringLiteral("imageGenerationStyleSheet"));
    return style;
}


QString ThemeManager::homePageStyleSheet() const
{
    // The four scrollbar rules are gone: SvStyle::drawComplexControl draws that control (an 8px
    // extent, a rounded Border handle that lifts to BorderStrong on hover, no arrows), so a sheet
    // rule here could only paint a second one over it -- and did, at a 10px width the style does
    // not use and a literal 5px radius that never read the material.
    const QString sheet = QStringLiteral(
        "#HomePage { background: transparent; }"
        "QScrollArea { background: transparent; border: none; }");
    assertNoUnresolvedTokens(sheet, QStringLiteral("homePageStyleSheet"));
    return sheet;
}

QString ThemeManager::settingsStyleSheet() const
{
    const qreal w = weight01(effectsWeight_);
    const QColor accent = accentColor();
    const QColor border = withAlpha(borderColor(), lerp(0.28, 0.78, w));
    // Settings canvas top-glow -- same subtle accent lift as the shell/Home, so the Settings surface
    // reads with depth instead of a flat Surface0 fill. Base of the gradient stays Surface0.
    const QColor settingsGlow = mix(background0(), accent, 0.12 + w * 0.05);

    // Named tokens, not positional arguments. This sheet was 23 arguments deep, which is exactly
    // the shape that renumbered every colour after a deleted rule (Doc 32); the retreat below
    // deletes eleven rules, so it converts first.
    QString sheet = QStringLiteral(
        "#SettingsPage { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 @glow@, stop:0.5 @bg0@, stop:1 @bg0@); }"
        "#SettingsTitle { @title@ color: @hi@; }"
        "#SettingsSubtitle { @body@ color: @mid@; }"
        // No card rule and no preview-panel rule: both frames are Surface::Panel, set in
        // SettingsPage, so the style draws them at the material's card radius.
        "#SettingsSectionTitle { @heading@ color: @hi@; }"
        "#SettingsBody { @body@ color: @mid@; }"
        // A QLabel wearing a chip, not a control: the style has no hook on it, so it keeps its paint.
        "#SettingsValueChip { background: @chipFill@; color: @hi@; border: 1px solid @chipEdge@;"
        " border-radius: @rctl@; padding: 6px 10px; @label@ }"
        "#SettingsPreviewHeader { color: @hi@; @subtitle@ }"
        "#SettingsPreviewBody { color: @mid@; @body@ }"
        // Combos, check indicators, sliders and buttons are SvStyle's, states included. What is
        // left is the room they take up. The Settings page is where the Surface Style setting is
        // chosen, so it is the last place that should be painting its own controls.
        "QComboBox { padding: 6px 8px; min-height: 34px; }"
        "QCheckBox { spacing: 8px; }"
        "QPushButton { padding: 7px 12px; min-height: 34px; }");

    sheet.replace(QLatin1String("@bg0@"), background0().name())
         .replace(QLatin1String("@glow@"), rgba(settingsGlow, 1.0))
         .replace(QLatin1String("@hi@"), textPrimary().name())
         .replace(QLatin1String("@mid@"), textMuted().name())
         .replace(QLatin1String("@chipFill@"), rgba(withAlpha(textPrimary(), preset_ == Preset::IvoryHolograph ? 0.06 : 0.04), 1.0))
         .replace(QLatin1String("@chipEdge@"), rgba(withAlpha(border, 0.78), 1.0))
         .replace(QLatin1String("@rctl@"), QString::number(radiusControl()) + QLatin1String("px"))
         // Typography: @role@ markers -> fontCss(Type::X) (size + weight from the scale, in one place).
         .replace(QLatin1String("@title@"), fontCss(Type::Title))
         .replace(QLatin1String("@heading@"), fontCss(Type::Heading))
         .replace(QLatin1String("@subtitle@"), fontCss(Type::Subtitle))
         .replace(QLatin1String("@label@"), fontCss(Type::Label))
         .replace(QLatin1String("@body@"), fontCss(Type::Body));

    assertNoUnresolvedTokens(sheet, QStringLiteral("settingsStyleSheet"));
    return sheet;
}

QString ThemeManager::accentGradientStyle() const
{
    const QColor accent = accentColor();
    const QColor accent2 = presetAccentSecondary();
    const QColor accent3 = presetAccentTertiary();
    return QStringLiteral(
        "background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 %1, stop:0.52 %2, stop:1 %3);"
        "border: 1px solid %4;"
        "border-radius: %5;")
        .arg(accent.name(),
             accent2.name(),
             accent3.name(),
             rgba(withAlpha(accent, 0.52), 1.0),
             QString::number(radiusCard()) + QStringLiteral("px"));
}

QString ThemeManager::settingsPreviewChipStyle(bool active) const
{
    const qreal w = weight01(effectsWeight_);
    const QColor fill = active ? withAlpha(accentColor(), lerp(0.18, 0.34, w))
                               : withAlpha(textPrimary(), preset_ == Preset::IvoryHolograph ? 0.06 : 0.04);
    const QColor border = active ? withAlpha(accentColor(), lerp(0.48, 0.86, w))
                                 : withAlpha(borderColor(), 0.42);
    // A QLabel standing in for a chip, so the style has no hook on it -- but the radius is the
    // material's and the weight is on the 400/500/600 ramp, as it would be if it were a real one.
    return QStringLiteral(
        "background:%1; color:%2; border:1px solid %3; border-radius:%4; padding:4px 10px; font-weight:600;")
        .arg(rgba(fill, 1.0), textPrimary().name(), rgba(border, 1.0),
             QString::number(radiusControl()) + QStringLiteral("px"));
}

QString ThemeManager::modePageStyleSheet() const
{
    return shellStyleSheet();
}