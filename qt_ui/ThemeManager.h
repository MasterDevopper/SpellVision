#pragma once

#include <QColor>
#include <QFont>
#include <QObject>
#include <QPalette>
#include <QStringList>

class ThemeManager : public QObject
{
    Q_OBJECT

public:
    enum class Preset
    {
        ArcaneGlass = 0,
        ObsidianStudio,
        NeonForge,
        IvoryHolograph,
        // Ember — a warm ember/orange-on-navy theme. Began life as the Phase-1
        // switching-proof palette and was promoted to a permanent, first-class theme
        // (kept for its palette). Its canonical color() tokens are authored in
        // rebuildColorTokens(); the legacy per-preset accessors return those tokens for
        // Ember (see the Preset::Ember cases) so not-yet-token-migrated surfaces
        // (e.g. Chain Studio) and the preset-accent system render it correctly too.
        Ember
    };
    Q_ENUM(Preset)

    // How much motion + visual flourish the UI shows. A single GLOBAL tier that animated
    // surfaces read (the bottom progress bar today; glass + more later), so a user on weak
    // hardware turns effects down in one place. Orthogonal to the theme — tier x theme are
    // independent. Tiers are distinct paint/animation PATHS, not one effect dialed down:
    // Minimal runs no timers at all (the cheap floor), higher tiers add motion.
    enum class AnimationQuality
    {
        Minimal = 0,  // static, no timers — weak-hardware / battery floor
        Standard,     // light motion (a gentle edge wave)
        Rich,         // full effects (glow + sweeping shimmer) — the default
        Lavish        // Rich + showpiece extras (rising bubbles / slosh)
    };
    Q_ENUM(AnimationQuality)

    // --- Canonical color tokens (Doc 16) ---
    // The single, named color ramp every widget migrates to. Read via
    // color(Color::X) for paint (QColor) or css(Color::X) for stylesheet strings
    // (#RRGGBB when opaque, rgba(...) when alpha < 255). A theme = one value-set for
    // these tokens; switching swaps the set and emits themeChanged(). Mirrors the
    // spacing(Spacing::X) / chrome(Chrome::X) idiom so call sites read uniformly.
    enum class Color
    {
        Surface0 = 0,   // app background (darkest)
        Surface1,       // panels / cards
        Surface2,       // raised surfaces
        Surface3,       // overlays / drawer
        TextHi,         // primary text
        TextMid,        // secondary text
        TextLo,         // muted text
        TextDisabled,   // disabled text
        Accent,         // hero violet #7C5CFF
        AccentHover,
        AccentActive,
        AccentDisabled,
        AccentGlow,     // accent at low alpha for glows
        AccentSubtle,   // accent at very low alpha for tint fills
        AccentSecondary, // deep violet #5B4BD6 (gradients / secondary emphasis)
        AccentTertiary,  // violet highlight #C6B6FF
        Border,         // hairline
        BorderStrong,   // emphasis / hover
        BorderSubtle,   // faintest
        Success,        // ready/online (cyan in ArcaneGlass)
        Warning,
        Error,
        Info,
        GlassFill,      // translucent panel fill (ArcaneGlass glass identity)
        GlassGlow,      // accent glow over glass
        GlassHighlight, // platinum top-edge highlight
    };
    Q_ENUM(Color)

    // --- Spacing Tokens Phase 1 ---
    // Named-by-role spacing scale. Values are constant across presets
    // (only color changes per theme). Use spacing(Spacing::Card) at call
    // sites instead of literal margins, so a later tuning is one edit.
    enum class Spacing
    {
        Hairline = 0,   // 4px  - icon/label gaps, the smallest seam
        Tight,          // 8px  - control-to-control inside a row
        Snug,           // 12px - label-to-control, intra-card stacking
        Card,           // 16px - card content padding, the default unit
        Section,        // 24px - between major sections within a column
        Gutter,         // 32px - page-level gutters, large separations
    };
    Q_ENUM(Spacing)

    // Fixed structural chrome heights/widths the shell currently
    // hard-codes. Centralizing them here means the title bar, menu bar,
    // rail etc. all read from one source. (The bottom telemetry bar sizes
    // itself inline via setFixedHeight in buildBottomTelemetryBar.)
    enum class Chrome
    {
        TitleBarHeight = 0,   // 32px
        MenuBarHeight,        // 40px
        ModeRailWidth,        // 76px
    };
    Q_ENUM(Chrome)

    // --- Typography scale ---
    // The single type ramp: role -> (pixel size, weight). Replaces the ad-hoc font-size/font-weight
    // literals scattered through the stylesheets (14 distinct sizes / 7 weights before this). Read via
    // font(Type::X) for a QFont (QPainter / setFont sites) or fontCss(Type::X) for a stylesheet fragment
    // ("font-size:Npx;font-weight:W;"), mirroring the color()/css() and spacing(Spacing::X) idioms.
    // Sizes/weights are constant across presets (only color changes per theme).
    enum class Type
    {
        Display = 0, // 28 / 800  hero + page titles (unifies the old 28/29/30 drift)
        Title,       // 20 / 800  major section titles
        Heading,     // 16 / 800  card / subsection headings
        Subtitle,    // 14 / 700  preview + secondary headings
        Body,        // 12 / 400  default body copy
        BodyStrong,  // 12 / 600  emphasized body
        Detail,      // 11 / 400  dense secondary body (regular small text)
        Label,       // 11 / 700  buttons / module titles / chips
        Caption,     // 10 / 700  eyebrows / meta
        Micro,       //  9 / 800  tiny letter-spaced eyebrows
    };
    Q_ENUM(Type)

    static ThemeManager &instance();

    QStringList presetNames() const;
    int presetIndex() const;
    Preset preset() const;
    QString presetName() const;

    bool usePresetAccent() const;
    QColor accentOverride() const;
    QColor accentColor() const;
    QColor accentSecondary() const;
    QColor accentTertiary() const;
    int effectsWeight() const;

    AnimationQuality animationQuality() const;
    QStringList animationQualityNames() const;                        // for the Settings selector
    QString animationQualityDescription(AnimationQuality quality) const; // per-tier explanation

    // --- Canonical color-token accessors (Doc 16) ---
    // color() returns the QColor (for QPainter/QPen/QBrush); css() returns a Qt
    // stylesheet color string (#RRGGBB opaque, rgba(r,g,b,a) when translucent).
    QColor color(Color token) const;
    QString css(Color token) const;

    // Application-wide chrome for the top-level widgets that ESCAPE the MainWindow stylesheet cascade
    // (tooltips, menus, message boxes, combo popups, stray dialogs). buildPalette() themes them at the
    // QPalette level (no more native #F0F0F0); applicationOverlayStyleSheet() adds borders/radius/hover.
    // applyApplicationChrome() pushes both onto qApp -- call once from main(); it auto-reapplies on
    // themeChanged (wired in the ctor).
    QPalette buildPalette() const;
    QString applicationOverlayStyleSheet() const;
    void applyApplicationChrome() const;

    // WCAG 2.x relative-luminance contrast ratio (1.0-21.0). If fg carries alpha it is
    // composited over bg first (WCAG is defined for opaque colors). This is the single
    // helper the startup self-check uses; exposed so any surface can verify a pairing.
    static qreal contrastRatio(const QColor &fg, const QColor &bg);

    // --- Spacing Tokens Phase 1: token accessors ---
    // Plain const int accessors, matching the shape of the QColor
    // accessors above. No preset switch -- spacing is theme-invariant.
    int spacing(Spacing token) const;
    int chrome(Chrome token) const;

    // --- Typography accessors ---
    int fontSize(Type token) const;    // pixel size
    int fontWeight(Type token) const;  // numeric weight (400/600/700/800) -- CSS + QFont share the scale
    QFont font(Type token) const;      // a QFont with pixelSize + weight set (QPainter / setFont sites)
    QString fontCss(Type token) const; // "font-size:Npx;font-weight:W;" for stylesheet strings
    int radiusCard() const;
    int radiusControl() const;
    int radiusPill() const;

    void setPreset(Preset preset);
    void setPresetByIndex(int index);
    void setUsePresetAccent(bool enabled);
    void setAccentOverride(const QColor &color);
    void clearAccentOverride();
    void setEffectsWeight(int weight);
    void setAnimationQuality(AnimationQuality quality);
    void setAnimationQualityByIndex(int index);
    void resetToDefaults();

    QString shellStyleSheet() const;
    QString imageGenerationStyleSheet() const;
    QString settingsStyleSheet() const;
    QString homePageStyleSheet() const;
    QString accentSwatchStyle() const;
    QString accentGradientStyle() const;
    QString settingsPreviewCardStyle() const;
    QString settingsPreviewChipStyle(bool active = false) const;
    QString settingsPreviewButtonStyle(bool primary = false) const;
    QString modePageStyleSheet() const;

    // --- Compatibility Layer ---
    // Keep these wrappers so older UI files compile without forcing a full refactor.
    QColor surface0Color() const { return surface0(); }
    QColor surface1Color() const { return surface1(); }

    QColor textPrimaryColor() const { return textPrimary(); }
    QColor textSecondaryColor() const { return textSecondary(); }
    QColor textMutedColor() const { return textMuted(); }

    QColor borderToneColor() const { return borderColor(); }

    // --- PASS 7B THEME EXPOSE STATUS COLORS ---
    // Status colors exposed via compat-layer wrappers. Required
    // by ChainRailWidget's status dots; same pattern that already
    // exposes surface0/surface1/text*/border.
    QColor successColorPublic() const { return successColor(); }
    QColor warningColorPublic() const { return warningColor(); }
    QColor errorColorPublic()   const { return errorColor(); }

    // --- PASS 7B POLISH FIXUP THEME AND U8 ---
    // Background tier colors — one tier deeper than surface0/1.
    // Used by ChainStudioPage as its page background so the
    // surface1 cards (panels) actually contrast against the page.
    // Hierarchy: background0 < background1 < surface0 < surface1.
    QColor background0Color() const { return background0(); }
    QColor background1Color() const { return background1(); }

signals:
    void themeChanged();
    void animationQualityChanged();

private:
    explicit ThemeManager(QObject *parent = nullptr);

    void load();
    void save() const;

    // Recompute the cached canonical color-token set for the active preset. Called
    // whenever the theme mutates (preset/accent/effects), before themeChanged() fires,
    // so subscribers reading color()/css() see fresh values.
    void rebuildColorTokens();

    // Debug-only startup gate: walks every preset and asserts each text-token x surface-token
    // pair the theme actually uses clears its WCAG floor (body text 4.5:1, disabled 3.0:1), so a
    // future hand-picked hex can't silently reintroduce an unreadable pair. No-op in release.
    void runContrastSelfCheck();

    QColor presetAccent() const;
    QColor presetAccentSecondary() const;
    QColor presetAccentTertiary() const;
    QColor background0() const;
    QColor background1() const;
    QColor surface0() const;
    QColor surface1() const;
    QColor textPrimary() const;
    QColor textSecondary() const;
    QColor textMuted() const;
    QColor borderColor() const;
    QColor inputSurface() const;
    QColor successColor() const;
    QColor warningColor() const;
    QColor errorColor() const;

    Preset preset_ = Preset::ArcaneGlass;
    bool usePresetAccent_ = true;
    QColor accentOverride_;
    int effectsWeight_ = 68;
    AnimationQuality animationQuality_ = AnimationQuality::Rich;

    // Cached canonical color tokens for the active preset, indexed by int(Color).
    // Rebuilt by rebuildColorTokens() on every theme mutation.
    static constexpr int ColorTokenCount = static_cast<int>(Color::GlassHighlight) + 1;
    QColor colorTokens_[ColorTokenCount];
};