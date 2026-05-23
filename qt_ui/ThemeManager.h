#pragma once

#include <QColor>
#include <QObject>
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
        IvoryHolograph
    };
    Q_ENUM(Preset)

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
    // hard-codes. Centralizing them here means the title bar, status
    // strip, telemetry bar etc. all read from one source.
    enum class Chrome
    {
        TitleBarHeight = 0,   // 32px
        MenuBarHeight,        // 40px
        StatusStripHeight,    // 24px
        TelemetryBarHeight,   // 30px
        ModeRailWidth,        // 76px
    };
    Q_ENUM(Chrome)

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

    // --- Spacing Tokens Phase 1: token accessors ---
    // Plain const int accessors, matching the shape of the QColor
    // accessors above. No preset switch -- spacing is theme-invariant.
    int spacing(Spacing token) const;
    int chrome(Chrome token) const;
    int radiusCard() const;
    int radiusControl() const;
    int radiusPill() const;

    void setPreset(Preset preset);
    void setPresetByIndex(int index);
    void setUsePresetAccent(bool enabled);
    void setAccentOverride(const QColor &color);
    void clearAccentOverride();
    void setEffectsWeight(int weight);
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

private:
    explicit ThemeManager(QObject *parent = nullptr);

    void load();
    void save() const;

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
};