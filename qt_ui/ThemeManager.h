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
    QString accentSwatchStyle() const;
    QString accentGradientStyle() const;
    QString settingsPreviewCardStyle() const;
    QString settingsPreviewChipStyle(bool active = false) const;
    QString settingsPreviewButtonStyle(bool primary = false) const;

    // --- Compatibility Layer ---
    // Keep these wrappers so older UI files compile without forcing a full refactor.
    QColor surface0Color() const { return surface0(); }
    QColor surface1Color() const { return surface1(); }

    QColor textPrimaryColor() const { return textPrimary(); }
    QColor textSecondaryColor() const { return textSecondary(); }
    QColor textMutedColor() const { return textMuted(); }

    QColor borderToneColor() const { return borderColor(); }

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