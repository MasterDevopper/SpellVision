#include "ThemeManager.h"

#include <QSettings>

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
}

QStringList ThemeManager::presetNames() const
{
    return {
        QStringLiteral("Arcane Glass"),
        QStringLiteral("Obsidian Studio"),
        QStringLiteral("Neon Forge"),
        QStringLiteral("Ivory Holograph"),
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

int ThemeManager::effectsWeight() const
{
    return effectsWeight_;
}

void ThemeManager::setPreset(Preset preset)
{
    if (preset_ == preset)
        return;

    preset_ = preset;
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
    save();
    emit themeChanged();
}

void ThemeManager::setAccentOverride(const QColor &color)
{
    if (!color.isValid())
        return;

    accentOverride_ = color;
    usePresetAccent_ = false;
    save();
    emit themeChanged();
}

void ThemeManager::clearAccentOverride()
{
    accentOverride_ = QColor();
    usePresetAccent_ = true;
    save();
    emit themeChanged();
}

void ThemeManager::setEffectsWeight(int weight)
{
    weight = qBound(0, weight, 100);
    if (effectsWeight_ == weight)
        return;

    effectsWeight_ = weight;
    save();
    emit themeChanged();
}

void ThemeManager::resetToDefaults()
{
    preset_ = Preset::ArcaneGlass;
    usePresetAccent_ = true;
    accentOverride_ = QColor();
    effectsWeight_ = 68;
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
}

void ThemeManager::save() const
{
    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    settings.setValue(QStringLiteral("appearance/themePreset"), static_cast<int>(preset_));
    settings.setValue(QStringLiteral("appearance/usePresetAccent"), usePresetAccent_);
    settings.setValue(QStringLiteral("appearance/accentOverride"), accentOverride_);
    settings.setValue(QStringLiteral("appearance/effectsWeight"), effectsWeight_);
}

QColor ThemeManager::presetAccent() const
{
    switch (preset_)
    {
    case Preset::ArcaneGlass: return QColor(QStringLiteral("#8b6cff"));
    case Preset::ObsidianStudio: return QColor(QStringLiteral("#7aa2ff"));
    case Preset::NeonForge: return QColor(QStringLiteral("#34b4ff"));
    case Preset::IvoryHolograph: return QColor(QStringLiteral("#8f79ff"));
    }
    return QColor(QStringLiteral("#8b6cff"));
}

QColor ThemeManager::presetAccentSecondary() const
{
    switch (preset_)
    {
    case Preset::ArcaneGlass: return QColor(QStringLiteral("#6f8cff"));
    case Preset::ObsidianStudio: return QColor(QStringLiteral("#9cb6dd"));
    case Preset::NeonForge: return QColor(QStringLiteral("#d55cff"));
    case Preset::IvoryHolograph: return QColor(QStringLiteral("#79b9ff"));
    }
    return QColor(QStringLiteral("#6f8cff"));
}

QColor ThemeManager::presetAccentTertiary() const
{
    switch (preset_)
    {
    case Preset::ArcaneGlass: return QColor(QStringLiteral("#6fd3ff"));
    case Preset::ObsidianStudio: return QColor(QStringLiteral("#d7e2f0"));
    case Preset::NeonForge: return QColor(QStringLiteral("#67f4ff"));
    case Preset::IvoryHolograph: return QColor(QStringLiteral("#d9ebff"));
    }
    return QColor(QStringLiteral("#6fd3ff"));
}

QColor ThemeManager::background0() const
{
    switch (preset_)
    {
    case Preset::ArcaneGlass: return QColor(QStringLiteral("#090d14"));
    case Preset::ObsidianStudio: return QColor(QStringLiteral("#0b0f16"));
    case Preset::NeonForge: return QColor(QStringLiteral("#070b12"));
    case Preset::IvoryHolograph: return QColor(QStringLiteral("#eff3fa"));
    }
    return QColor(QStringLiteral("#090d14"));
}

QColor ThemeManager::background1() const
{
    switch (preset_)
    {
    case Preset::ArcaneGlass: return QColor(QStringLiteral("#101624"));
    case Preset::ObsidianStudio: return QColor(QStringLiteral("#141a24"));
    case Preset::NeonForge: return QColor(QStringLiteral("#0d1421"));
    case Preset::IvoryHolograph: return QColor(QStringLiteral("#dfe8f5"));
    }
    return QColor(QStringLiteral("#101624"));
}

QColor ThemeManager::surface0() const
{
    switch (preset_)
    {
    case Preset::ArcaneGlass: return QColor(QStringLiteral("#171f31"));
    case Preset::ObsidianStudio: return QColor(QStringLiteral("#1b222e"));
    case Preset::NeonForge: return QColor(QStringLiteral("#141b2a"));
    case Preset::IvoryHolograph: return QColor(QStringLiteral("#f6f9fe"));
    }
    return QColor(QStringLiteral("#171f31"));
}

QColor ThemeManager::surface1() const
{
    switch (preset_)
    {
    case Preset::ArcaneGlass: return QColor(QStringLiteral("#20283c"));
    case Preset::ObsidianStudio: return QColor(QStringLiteral("#252d3a"));
    case Preset::NeonForge: return QColor(QStringLiteral("#1e2740"));
    case Preset::IvoryHolograph: return QColor(QStringLiteral("#ebf1fb"));
    }
    return QColor(QStringLiteral("#20283c"));
}

QColor ThemeManager::textPrimary() const
{
    return preset_ == Preset::IvoryHolograph ? QColor(QStringLiteral("#132033")) : QColor(QStringLiteral("#eef4ff"));
}

QColor ThemeManager::textSecondary() const
{
    return preset_ == Preset::IvoryHolograph ? QColor(QStringLiteral("#42546d")) : QColor(QStringLiteral("#c9d8eb"));
}

QColor ThemeManager::textMuted() const
{
    return preset_ == Preset::IvoryHolograph ? QColor(QStringLiteral("#6c7d95")) : QColor(QStringLiteral("#9eb2d0"));
}

QColor ThemeManager::borderColor() const
{
    const qreal t = weight01(effectsWeight_);
    return mix(surface1(), accentColor(), 0.18 + t * 0.24);
}

QColor ThemeManager::inputSurface() const
{
    return preset_ == Preset::IvoryHolograph ? QColor(QStringLiteral("#ffffff")) : QColor(QStringLiteral("#0f1520"));
}

QColor ThemeManager::successColor() const
{
    return QColor(QStringLiteral("#42c480"));
}

QColor ThemeManager::warningColor() const
{
    return QColor(QStringLiteral("#f1bd59"));
}

QColor ThemeManager::errorColor() const
{
    return QColor(QStringLiteral("#d85d73"));
}

QString ThemeManager::shellStyleSheet() const
{
    const qreal w = weight01(effectsWeight_);
    const QColor accent = accentColor();
    const QColor accent2 = presetAccentSecondary();
    const QColor accent3 = presetAccentTertiary();
    const QColor bg0 = background0();
    const QColor bg1 = background1();
    const QColor surfaceA = withAlpha(surface0(), lerp(0.96, 0.84, w));
    const QColor surfaceB = withAlpha(surface1(), lerp(0.98, 0.88, w));
    const QColor border = withAlpha(borderColor(), lerp(0.30, 0.78, w));
    const QColor softBorder = withAlpha(borderColor(), lerp(0.18, 0.42, w));
    const QColor focus = withAlpha(accent, lerp(0.46, 0.90, w));
    const QColor focusSoft = withAlpha(accent, lerp(0.14, 0.32, w));
    const QColor buttonA = withAlpha(accent, lerp(0.14, 0.34, w));
    const QColor buttonB = withAlpha(accent2, lerp(0.10, 0.28, w));
    const QColor buttonHoverA = withAlpha(accent, lerp(0.22, 0.48, w));
    const QColor buttonHoverB = withAlpha(accent2, lerp(0.16, 0.38, w));
    const QColor checkedA = withAlpha(accent, lerp(0.18, 0.34, w));
    const QColor checkedB = withAlpha(accent2, lerp(0.14, 0.28, w));
    const QColor idleFill = withAlpha(textPrimary(), preset_ == Preset::IvoryHolograph ? 0.025 : 0.04);

    return QStringLiteral(
        "QMainWindow { background: %1; color: %2; }"
        "QWidget { selection-background-color: %3; selection-color: %4; }"

        "#CustomTitleBar {"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 %5, stop:0.5 %6, stop:1 %5);"
        " border-bottom: 1px solid %7;"
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
        " border-radius: 7px; font-size: 12px; font-weight: 600;"
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
        "#TitleBarSearchText { color: %4; font-size: 12px; font-weight: 600; }"
        "#TitleBarSearchShortcut { color: %20; font-size: 11px; font-weight: 700; }"

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
        "QLabel#ShellSectionTitle { font-size: 20px; font-weight: 800; color: %4; }"
        "QStatusBar { background: %21; border-top: 1px solid %22; min-height: 38px; }"
        "QStatusBar QLabel { color: %24; font-size: 11px; }"
        "QWidget#MainPageStack { background: transparent; }"
        "QWidget#SideRail { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 rgba(5, 8, 15, 0.998), stop:0.45 rgba(7, 10, 19, 0.992), stop:1 rgba(3, 5, 11, 0.998)); border-right: 1px solid rgba(154,120,255,0.28); }"
        "QToolButton#SideRailButton { color: rgba(227,234,247,0.76); border: 1px solid transparent; border-left: 4px solid transparent; border-radius: 18px; font-size: 12px; font-weight: 800; padding: 10px 8px 10px 8px; text-align: center; background: transparent; }"
        "QToolButton#SideRailButton:hover { color: #fcfdff; background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 rgba(162,122,255,0.24), stop:0.58 rgba(120,104,255,0.16), stop:1 rgba(62,154,255,0.08)); border-color: rgba(152, 140, 255, 0.36); }"
        "QToolButton#SideRailButton:checked { color: #ffffff; background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 rgba(166,124,255,0.54), stop:0.55 rgba(128,104,255,0.34), stop:1 rgba(78,170,255,0.16)); border-color: rgba(228, 220, 255, 0.72); border-left: 4px solid rgba(238, 232, 255, 1.00); }"
        "QFrame#QueueActiveStrip, QFrame#DetailsSummaryCard, QFrame#DetailsActionCard, QFrame#ExecutionLogCard { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 rgba(18,27,44,0.95), stop:1 rgba(10,15,26,0.98)); border: 1px solid rgba(126,146,190,0.26); border-radius: 16px; }"
        "QLabel#QueueActiveEyebrow, QLabel#DetailsEyebrow { font-size: 11px; font-weight: 700; color: #8fb2ff; }"
        "QLabel#QueueActiveTitle, QLabel#DetailsTitle { font-size: 16px; font-weight: 800; color: #f2f6fc; }"
        "QLabel#QueueActiveBody, QLabel#DetailsBody { font-size: 11px; color: #9fb0ca; }"
        "QLabel#DetailsMetaLabel { font-size: 9px; font-weight: 800; color: #7f95b7; text-transform: uppercase; letter-spacing: 0.08em; }"
        "QLabel#DetailsMetaValue { font-size: 11px; font-weight: 700; color: #eef4ff; background: rgba(18,26,44,0.56); border: 1px solid rgba(122,138,176,0.18); border-radius: 8px; padding: 4px 8px; }"
        "QPushButton#DetailsPrimaryActionButton { min-height: 30px; font-size: 11px; font-weight: 800; }"
        "QPushButton#DetailsSecondaryActionButton { min-height: 28px; font-size: 11px; }"
        "QPushButton#DetailsActionButton { min-height: 32px; border-radius: 11px; font-size: 11px; font-weight: 800; }"
        "QTextEdit#LogsView { background: rgba(11,16,26,0.92); border: 1px solid rgba(120,138,172,0.18); border-radius: 12px; padding: 8px; }"
        "QLabel#SectionTitle { font-size: 16px; font-weight: 700; color: %4; background: transparent; }"
        "QLabel#SectionBody { font-size: 12px; color: %20; background: transparent; }"
        "QSplitter::handle { background: transparent; }"
        "QSplitter::handle:hover { background: %14; }"
        "QScrollArea { background: transparent; border: none; }"
        "QLabel#SideRailBadge { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %36, stop:1 %37); color: %4; border: 1px solid %35; border-radius: 18px; padding: 8px 0px; font-size: 12px; font-weight: 900; }"
        "QLabel#SideRailCaption { color: %20; font-size: 10px; font-weight: 700; letter-spacing: 0.08em; }"
        "QFrame#SideRailDivider { background: %27; min-height: 1px; max-height: 1px; border: none; }"

        "#RailButton { background: transparent; color: %24; border: 1px solid transparent; border-radius: 14px; padding: 0px; text-align: center; }"
        "#RailButton:hover { background: %12; border-color: %13; }"
        "#RailButton:checked { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %36, stop:1 %37); border: 1px solid %35; }"

        "#ActiveJobCard {"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %15, stop:1 %16);"
        " border: 1px solid %27; border-radius: 16px;"
        "}"
        "#ActiveJobCard:hover { border: 1px solid %35; }"
        "#ActiveJobTitle { font-size: 18px; font-weight: 800; color: %4; }"
        "#ActiveJobPrompt { color: %24; font-size: 13px; }"
        "#ActiveJobMeta { color: %20; font-size: 12px; }"
        "#ActiveJobStatus { color: %24; font-size: 12px; }"
        "#ActiveJobBadge { padding: 4px 10px; border-radius: 10px; font-weight: 800; }"
        )
        .arg(bg0.name(),
             textPrimary().name(),
             rgba(focus, 0.36),
             textPrimary().name(),
             rgba(surfaceA, 1.0),
             rgba(surfaceB, 1.0),
             rgba(softBorder, 0.95),
             accent.name(),
             accent2.name(),
             accent3.name(),
             rgba(withAlpha(textPrimary(), preset_ == Preset::IvoryHolograph ? 0.20 : 0.36)),
             rgba(idleFill, 1.0),
             rgba(softBorder, 0.85),
             rgba(focusSoft, 1.0),
             rgba(withAlpha(surface0(), 0.98), 1.0),
             rgba(withAlpha(surface1(), 0.98), 1.0),
             rgba(softBorder, 0.95),
             rgba(mix(surface1(), accent2, 0.25), 0.98),
             rgba(focus, 1.0),
             textMuted().name(),
             rgba(mix(bg1, surface0(), 0.55), 0.98),
             rgba(softBorder, 0.70),
             rgba(withAlpha(inputSurface(), 0.98), 1.0),
             textSecondary().name(),
             rgba(softBorder, 1.0),
             rgba(withAlpha(surface0(), 0.98), 1.0),
             rgba(softBorder, 0.55),
             rgba(withAlpha(borderColor(), 0.24), 1.0),
             rgba(idleFill, 0.65),
             rgba(buttonA, 1.0),
             rgba(buttonB, 1.0),
             rgba(withAlpha(focus, lerp(0.34, 0.62, w)), 1.0),
             rgba(buttonHoverA, 1.0),
             rgba(buttonHoverB, 1.0),
             rgba(withAlpha(focus, 0.92), 1.0),
             rgba(checkedA, 1.0),
             rgba(checkedB, 1.0),
             textMuted().name(),
             rgba(withAlpha(borderColor(), 0.20), 1.0),
             rgba(idleFill, 0.55));
}

QString ThemeManager::imageGenerationStyleSheet() const
{
    const qreal w = weight01(effectsWeight_);
    const QColor accent = accentColor();
    const QColor accent2 = presetAccentSecondary();
    const QColor panel0 = withAlpha(surface0(), lerp(0.96, 0.84, w));
    const QColor panel1 = withAlpha(surface1(), lerp(0.98, 0.88, w));
    const QColor border = withAlpha(borderColor(), lerp(0.28, 0.74, w));
    const QColor input = withAlpha(inputSurface(), preset_ == Preset::IvoryHolograph ? 0.96 : 0.98);
    const QColor focus = withAlpha(accent, lerp(0.60, 0.92, w));
    const QColor subtleBorder = withAlpha(border, 0.78);
    const QColor softSurface = withAlpha(mix(inputSurface(), background0(), 0.25), 1.0);
    const QColor promptA = withAlpha(mix(panel0, accent, 0.18), 1.0);
    const QColor promptB = withAlpha(mix(panel1, accent2, 0.12), 1.0);
    const QColor canvasA = withAlpha(mix(panel0, accent, 0.10), 1.0);
    const QColor canvasB = withAlpha(mix(panel1, accent2, 0.18), 1.0);
    const QColor secondaryBorder = withAlpha(accent, 0.18);
    const QColor tertiaryFill = withAlpha(border, 0.18);
    const QColor tertiaryBorder = withAlpha(border, 0.34);

    QString style = QStringLiteral(
        "#ImageGenerationPage { background: %1; }"
        "QWidget#LeftRailContainer { background: transparent; }"
        "QScrollArea#LeftRailScrollArea { background: transparent; border: none; }"
        "QFrame#PromptCard, QFrame#InputCard, QFrame#QuickControlsCard, QFrame#OutputQueueCard, QFrame#AdvancedCard, QFrame#SettingsCard, QFrame#OutputCard, QFrame#CanvasCard {"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %2, stop:1 %3);"
        " border: 1px solid %4; border-radius: 20px; }"
        "QFrame#PromptCard { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %5, stop:1 %6); border: 1px solid %7; }"
        "QFrame#CanvasCard { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %8, stop:1 %9); border: 1px solid %10; }"
        "QFrame#QuickControlsCard, QFrame#OutputQueueCard, QFrame#AdvancedCard, QFrame#SettingsCard, QFrame#OutputCard { border-color: %11; }"
        "QFrame#InputDropCard { background: %12; border: 1px dashed %7; border-radius: 16px; }"
        "QLabel#SectionTitle { font-size: 15px; font-weight: 800; color: %13; background: transparent; }"
        "QToolButton#InspectorSectionToggle { background: %28; color: %13; border: 1px solid %29; border-radius: 10px; padding: 3px 10px; min-width: 62px; min-height: 22px; max-height: 26px; font-size: 10px; font-weight: 800; }"
        "QToolButton#InspectorSectionToggle:hover { background: %23; border-color: %10; }"
        "QLabel#SectionBody { font-size: 11px; color: %14; background: transparent; }"
        "QLabel#CompactFieldLabel { color: %14; font-size: 10px; font-weight: 800; background: transparent; }"
        "QLabel#ImageGenHint, QLabel#OutputQueueBodyHint { color: %14; font-size: 11px; background: transparent; }"
        "QLabel#OutputQueueBodyLabel { color: %13; font-size: 10px; font-weight: 800; background: transparent; }"
        "QLabel#AssetIntelligenceBody { color: %15; font-size: 11px; background: transparent; padding-top: 2px; }"
        "QLabel#StackSummary { color: %15; font-size: 12px; background: transparent; }"
        "QLabel#PreviewSummary { color: %14; font-size: 12px; background: transparent; padding-right: 12px; }"
        "QLabel#ReadinessHint { color: %14; font-size: 11px; font-weight: 800; background: %32; border: 1px solid %31; border-radius: 11px; padding: 6px 10px; min-height: 26px; }"
        "QLabel#PreviewSurface {"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %16, stop:1 %12);"
        " border: 1px dashed %7; border-radius: 22px; color: %15; padding: 18px; font-size: 14px; font-weight: 700; }"
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
        "QLabel#PreviewSurface[emptyState=\"true\"] { color: %14; border-color: %31; background: %33; }"
    );

    style = style
        .arg(background0().name())
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
        .arg(textPrimary().name())
        .arg(textMuted().name())
        .arg(textSecondary().name())
        .arg(rgba(withAlpha(mix(panel0, accent, 0.18), 1.0), 1.0))
        .arg(rgba(input, 1.0))
        .arg(rgba(withAlpha(border, 0.95), 1.0))
        .arg(rgba(withAlpha(mix(inputSurface(), accent2, 0.18), 1.0), 1.0))
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
        .arg(rgba(withAlpha(textMuted(), 0.78), 1.0))
        .arg(rgba(withAlpha(borderColor(), 0.38), 1.0))
        .arg(rgba(withAlpha(mix(inputSurface(), background0(), 0.42), 1.0), 1.0))
        .arg(rgba(withAlpha(mix(panel0, background0(), 0.20), 1.0), 1.0));

    return style;
}


QString ThemeManager::homePageStyleSheet() const
{
    const qreal w = weight01(effectsWeight_);
    const QColor scrollHandle = withAlpha(mix(surface1(), accentColor(), 0.26), lerp(0.22, 0.42, w));
    const QColor scrollHover = withAlpha(mix(surface1(), accentSecondary(), 0.34), lerp(0.32, 0.56, w));

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

    return QStringLiteral(
        "#SettingsPage { background: %1; }"
        "#SettingsTitle { font-size: 18px; font-weight: 800; color: %2; }"
        "#SettingsSubtitle { font-size: 12px; color: %3; }"
        "#SettingsCard { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %4, stop:1 %5); border: 1px solid %6; border-radius: 20px; }"
        "#SettingsSectionTitle { font-size: 16px; font-weight: 800; color: %2; }"
        "#SettingsBody { font-size: 11px; color: %3; }"
        "#SettingsValueChip { background: %7; color: %2; border: 1px solid %8; border-radius: 10px; padding: 6px 10px; font-size: 11px; font-weight: 700; }"
        "#SettingsPreviewPanel { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %9, stop:1 %10); border: 1px solid %8; border-radius: 18px; }"
        "#SettingsPreviewHeader { color: %2; font-size: 14px; font-weight: 800; }"
        "#SettingsPreviewBody { color: %3; font-size: 11px; }"
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
             rgba(withAlpha(borderColor(), 0.20), 1.0));
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