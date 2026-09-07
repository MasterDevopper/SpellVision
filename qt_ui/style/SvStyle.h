#pragma once

#include <QProxyStyle>
#include <QString>

class QPainter;
class QWidget;

namespace spellvision::style
{

// What a control IS, independent of what it is named. Read from the widget property "svRole"
// (a string: primary, secondary, tertiary, danger, chip, tab, rail); during the migration also
// inferred from today's object names so unmigrated pages draw correctly before their code changes.
enum class Role { None, Primary, Secondary, Tertiary, Danger, Chip, Tab, Rail };

// What a frame IS. Property "svSurface": plate, panel, inset, glass.
enum class Surface { None, Plate, Panel, Inset, Glass };

// The one place SpellVision draws a control. A QProxyStyle over Fusion that reads ThemeManager at
// draw time -- it caches nothing, so a preset or material switch is refreshAll() and a repaint.
class SvStyle final : public QProxyStyle
{
    Q_OBJECT
public:
    SvStyle();

    static Role roleOf(const QWidget *widget);
    static Surface surfaceOf(const QWidget *widget);
    static QString roleName(Role role);
    static QString surfaceName(Surface surface);

    // unpolish + polish + update over every widget. Connected to ThemeManager::themeChanged
    // through applyApplicationChrome().
    static void refreshAll();

    void polish(QWidget *widget) override;
    void drawPrimitive(PrimitiveElement element, const QStyleOption *option, QPainter *painter,
                       const QWidget *widget) const override;
    void drawControl(ControlElement element, const QStyleOption *option, QPainter *painter,
                     const QWidget *widget) const override;
    void drawComplexControl(ComplexControl control, const QStyleOptionComplex *option,
                            QPainter *painter, const QWidget *widget) const override;
    int pixelMetric(PixelMetric metric, const QStyleOption *option,
                    const QWidget *widget) const override;
    QSize sizeFromContents(ContentsType type, const QStyleOption *option, const QSize &contents,
                           const QWidget *widget) const override;
};

} // namespace spellvision::style
