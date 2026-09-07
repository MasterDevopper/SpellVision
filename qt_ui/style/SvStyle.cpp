#include "style/SvStyle.h"

#include "ThemeManager.h"

#include <QAbstractButton>
#include <QAbstractItemView>
#include <QApplication>
#include <QLinearGradient>
#include <QPainter>
#include <QPainterPath>
#include <QPlainTextEdit>
#include <QRadialGradient>
#include <QStyleFactory>
#include <QStyleOption>
#include <QStyleOptionButton>
#include <QStyleOptionComboBox>
#include <QStyleOptionFrame>
#include <QStyleOptionHeader>
#include <QStyleOptionProgressBar>
#include <QStyleOptionSlider>
#include <QStyleOptionSpinBox>
#include <QStyleOptionTab>
#include <QStyleOptionToolButton>
#include <QStyleOptionViewItem>
#include <QTextEdit>
#include <QToolButton>
#include <QWidget>

namespace spellvision::style
{
namespace
{
using Color = ThemeManager::Color;

const ThemeManager &theme() { return ThemeManager::instance(); }
QColor tok(Color c) { return theme().color(c); }

QColor withAlpha(QColor c, qreal alpha)
{
    c.setAlphaF(alpha);
    return c;
}

QPainterPath rounded(const QRectF &rect, qreal radius)
{
    QPainterPath path;
    path.addRoundedRect(rect, radius, radius);
    return path;
}

// Inset by half a pixel so a 1 px stroke lands on whole pixels instead of smearing over two.
QRectF strokeRect(const QRect &rect) { return QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5); }

// The object-name map. Deleted at the end of the wave (Task 9) once every site sets its property.
Role roleFromObjectName(const QString &name)
{
    if (name == QLatin1String("PrimaryActionButton") || name == QLatin1String("PrimaryButton")
        || name == QLatin1String("DetailsPrimaryActionButton") || name.endsWith(QLatin1String("PrimaryBtn")))
        return Role::Primary;
    if (name == QLatin1String("SecondaryActionButton") || name == QLatin1String("SecondaryButton")
        || name == QLatin1String("HistoryActionButton") || name == QLatin1String("ModelsActionButton")
        || name == QLatin1String("DetailsSecondaryActionButton") || name == QLatin1String("DetailsActionButton")
        || name == QLatin1String("HomeModuleFrameButton") || name == QLatin1String("ModelCardInspectButton")
        || name.endsWith(QLatin1String("SecondaryBtn")))
        return Role::Secondary;
    if (name == QLatin1String("TertiaryActionButton"))
        return Role::Tertiary;
    if (name == QLatin1String("ModelsDangerButton"))
        return Role::Danger;
    if (name == QLatin1String("InspectorTab") || name == QLatin1String("TitleBarModeButton"))
        return Role::Tab;
    if (name == QLatin1String("ModelsViewToggle") || name == QLatin1String("NegativeToggleButton")
        || name == QLatin1String("AiDetailsToggle") || name == QLatin1String("OperatingPointButton"))
        return Role::Chip;
    if (name == QLatin1String("SideRailButton"))
        return Role::Rail;
    return Role::None;
}

Surface surfaceFromObjectName(const QString &name)
{
    // CanvasCard is the one hero surface (the generation result display); every other *Card /
    // *Surface -- PromptCard included -- is an ordinary panel.
    if (name == QLatin1String("CanvasCard"))
        return Surface::Plate;
    if (name.endsWith(QLatin1String("Card")) || name.endsWith(QLatin1String("Surface")))
        return Surface::Panel;
    return Surface::None;
}

struct ButtonPaint
{
    QColor fill;
    QColor edge;
    QColor text;
    qreal radius = 6;
    bool gradient = false;
};

ButtonPaint buttonPaint(Role role, const QStyleOption *opt)
{
    const bool hover = opt->state & QStyle::State_MouseOver;
    const bool down = opt->state & QStyle::State_Sunken;
    const bool checked = opt->state & QStyle::State_On;
    const bool enabled = opt->state & QStyle::State_Enabled;
    ButtonPaint p;
    p.radius = theme().radiusControl();
    p.text = tok(enabled ? Color::TextHi : Color::TextDisabled);
    switch (role)
    {
    case Role::Primary:
        p.gradient = true;
        p.fill = tok(Color::Accent);
        p.edge = withAlpha(tok(Color::AccentTertiary), 0.35);
        p.text = enabled ? QColor(Qt::white) : withAlpha(QColor(Qt::white), 0.6);
        p.radius = theme().radiusCard();
        if (down) p.fill = tok(Color::AccentActive);
        break;
    case Role::Secondary:
        p.fill = tok(Color::Surface2);
        p.edge = tok(hover ? Color::BorderStrong : Color::Border);
        if (hover) p.fill = p.fill.lighter(106);
        if (down) p.fill = withAlpha(tok(Color::Accent), 0.22);
        break;
    case Role::Tertiary:
        p.fill = hover ? withAlpha(QColor(Qt::white), 0.04) : QColor(0, 0, 0, 0);
        p.edge = hover ? tok(Color::Border) : QColor(0, 0, 0, 0);
        p.text = tok(enabled ? (hover ? Color::TextHi : Color::TextMid) : Color::TextDisabled);
        break;
    case Role::Danger:
        p.fill = withAlpha(tok(Color::Error), hover ? 0.24 : 0.16);
        p.edge = withAlpha(tok(Color::Error), 0.6);
        p.text = tok(Color::Error);
        break;
    case Role::Chip:
        p.fill = checked ? withAlpha(QColor(Qt::white), 0.05) : tok(Color::Surface1);
        p.edge = tok(checked || hover ? Color::BorderStrong : Color::Border);
        p.text = tok(enabled ? (checked ? Color::TextHi : Color::TextMid) : Color::TextDisabled);
        break;
    case Role::Rail:
        p.fill = checked ? withAlpha(QColor(Qt::white), 0.05)
                         : (hover ? withAlpha(QColor(Qt::white), 0.04) : QColor(0, 0, 0, 0));
        p.edge = QColor(0, 0, 0, 0);
        p.text = tok(enabled ? (checked || hover ? Color::TextHi : Color::TextMid) : Color::TextDisabled);
        p.radius = 8;
        break;
    case Role::Tab:
    case Role::None:
        p.fill = QColor(0, 0, 0, 0);
        p.edge = QColor(0, 0, 0, 0);
        p.text = tok(enabled ? (checked || hover ? Color::TextHi : Color::TextMid) : Color::TextDisabled);
        break;
    }
    return p;
}

void paintButtonPanel(Role role, const QStyleOption *opt, QPainter *painter)
{
    const ButtonPaint p = buttonPaint(role, opt);
    painter->save();
    painter->setRenderHint(QPainter::Antialiasing, true);
    const QRectF r = strokeRect(opt->rect);
    if (role == Role::Tab)
    {
        if (opt->state & QStyle::State_On)
        {
            painter->setPen(Qt::NoPen);
            painter->setBrush(tok(Color::Accent));
            painter->drawRoundedRect(QRectF(r.left() + 6, r.bottom() - 2, r.width() - 12, 2), 1, 1);
        }
        painter->restore();
        return;
    }
    if (p.gradient)
    {
        QLinearGradient g(r.topLeft(), r.bottomLeft());
        g.setColorAt(0.0, tok(Color::AccentHover));
        g.setColorAt(1.0, p.fill);
        painter->setBrush(g);
    }
    else
    {
        painter->setBrush(p.fill);
    }
    painter->setPen(p.edge.alpha() > 0 ? QPen(p.edge, 1.0) : QPen(Qt::NoPen));
    painter->drawPath(rounded(r, p.radius));
    if (role == Role::Rail && (opt->state & QStyle::State_On))
    {
        painter->setPen(Qt::NoPen);
        painter->setBrush(tok(Color::Accent));
        painter->drawRoundedRect(QRectF(r.left(), r.top() + 10, 2, r.height() - 20), 1, 1);
    }
    painter->restore();
}

void paintSurface(Surface surface, const QStyleOption *opt, QPainter *painter)
{
    painter->save();
    painter->setRenderHint(QPainter::Antialiasing, true);
    const QRectF r = strokeRect(opt->rect);
    const qreal radius = surface == Surface::Inset ? theme().radiusControl() : theme().radiusCard();
    const QPainterPath path = rounded(r, radius);
    if (surface == Surface::Glass && theme().styleUsesGlass(true))
    {
        painter->setPen(Qt::NoPen);
        painter->setBrush(tok(Color::GlassFill));
        painter->drawPath(path);
        QRadialGradient glow(r.topLeft() + QPointF(r.width() * 0.2, 0), r.width() * 0.6);
        glow.setColorAt(0.0, tok(Color::GlassGlow));
        glow.setColorAt(1.0, QColor(0, 0, 0, 0));
        painter->setBrush(glow);
        painter->drawPath(path);
        painter->setPen(QPen(tok(Color::Border), 1.0));
        painter->setBrush(Qt::NoBrush);
        painter->drawPath(path);
        painter->setPen(QPen(tok(Color::GlassHighlight), 1.0));
        painter->drawLine(QPointF(r.left() + radius, r.top() + 1), QPointF(r.right() - radius, r.top() + 1));
        painter->restore();
        return;
    }
    const bool plate = surface == Surface::Plate || surface == Surface::Glass;
    painter->setBrush(tok(surface == Surface::Inset ? Color::Surface0 : Color::Surface1));
    painter->setPen(QPen(tok(surface == Surface::Inset ? Color::BorderSubtle : Color::Border), 1.0));
    painter->drawPath(path);
    if (plate)
    {
        painter->setPen(QPen(tok(Color::GlassHighlight), 1.0));
        painter->drawLine(QPointF(r.left() + radius, r.top() + 1), QPointF(r.right() - radius, r.top() + 1));
    }
    painter->restore();
}

void paintFieldPanel(const QStyleOption *opt, QPainter *painter)
{
    const bool focus = opt->state & QStyle::State_HasFocus;
    const bool enabled = opt->state & QStyle::State_Enabled;
    painter->save();
    painter->setRenderHint(QPainter::Antialiasing, true);
    painter->setBrush(tok(Color::Surface0));
    painter->setPen(QPen(tok(focus ? Color::AccentHover : (enabled ? Color::Border : Color::BorderSubtle)), 1.0));
    painter->drawPath(rounded(strokeRect(opt->rect), theme().radiusControl()));
    painter->restore();
}

void paintChevron(QPainter *painter, const QRectF &box, bool up, const QColor &color)
{
    painter->save();
    painter->setRenderHint(QPainter::Antialiasing, true);
    painter->setPen(QPen(color, 1.8, Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin));
    const QPointF c = box.center();
    const qreal w = 3.5, h = up ? -2.0 : 2.0;
    painter->drawPolyline(QPolygonF({QPointF(c.x() - w, c.y() - h), QPointF(c.x(), c.y() + h), QPointF(c.x() + w, c.y() - h)}));
    painter->restore();
}

int roleMinHeight(Role role)
{
    switch (role)
    {
    case Role::Primary:   return 34;
    case Role::Secondary: return 30;
    case Role::Tertiary:  return 28;
    case Role::Danger:    return 30;
    case Role::Chip:      return 24;
    case Role::Tab:       return 34;
    case Role::Rail:      return 0;
    case Role::None:      return 28;
    }
    return 28;
}

int roleHPad(Role role)
{
    switch (role)
    {
    case Role::Primary:   return 18;
    case Role::Secondary: return 12;
    case Role::Tertiary:  return 10;
    case Role::Danger:    return 12;
    case Role::Chip:      return 8;
    case Role::Tab:       return 10;
    case Role::Rail:      return 0;
    case Role::None:      return 12;
    }
    return 12;
}
} // namespace

SvStyle::SvStyle() : QProxyStyle(QStyleFactory::create(QStringLiteral("Fusion"))) {}

Role SvStyle::roleOf(const QWidget *widget)
{
    if (!widget)
        return Role::None;
    const QString prop = widget->property("svRole").toString();
    if (prop == QLatin1String("primary")) return Role::Primary;
    if (prop == QLatin1String("secondary")) return Role::Secondary;
    if (prop == QLatin1String("tertiary")) return Role::Tertiary;
    if (prop == QLatin1String("danger")) return Role::Danger;
    if (prop == QLatin1String("chip")) return Role::Chip;
    if (prop == QLatin1String("tab")) return Role::Tab;
    if (prop == QLatin1String("rail")) return Role::Rail;
    return roleFromObjectName(widget->objectName());
}

Surface SvStyle::surfaceOf(const QWidget *widget)
{
    if (!widget)
        return Surface::None;
    const QString prop = widget->property("svSurface").toString();
    if (prop == QLatin1String("plate")) return Surface::Plate;
    if (prop == QLatin1String("panel")) return Surface::Panel;
    if (prop == QLatin1String("inset")) return Surface::Inset;
    if (prop == QLatin1String("glass")) return Surface::Glass;
    return surfaceFromObjectName(widget->objectName());
}

QString SvStyle::roleName(Role role)
{
    switch (role)
    {
    case Role::Primary:   return QStringLiteral("primary");
    case Role::Secondary: return QStringLiteral("secondary");
    case Role::Tertiary:  return QStringLiteral("tertiary");
    case Role::Danger:    return QStringLiteral("danger");
    case Role::Chip:      return QStringLiteral("chip");
    case Role::Tab:       return QStringLiteral("tab");
    case Role::Rail:      return QStringLiteral("rail");
    case Role::None:      break;
    }
    return QString();
}

QString SvStyle::surfaceName(Surface surface)
{
    switch (surface)
    {
    case Surface::Plate: return QStringLiteral("plate");
    case Surface::Panel: return QStringLiteral("panel");
    case Surface::Inset: return QStringLiteral("inset");
    case Surface::Glass: return QStringLiteral("glass");
    case Surface::None:  break;
    }
    return QString();
}

void SvStyle::refreshAll()
{
    if (!qApp)
        return;
    QStyle *st = QApplication::style();
    const QWidgetList widgets = QApplication::allWidgets();
    for (QWidget *w : widgets)
    {
        st->unpolish(w);
        st->polish(w);
        w->update();
    }
}

void SvStyle::polish(QWidget *widget)
{
    QProxyStyle::polish(widget);
    if (qobject_cast<QAbstractButton *>(widget) || surfaceOf(widget) != Surface::None)
        widget->setAttribute(Qt::WA_Hover, true);
}

void SvStyle::drawPrimitive(PrimitiveElement element, const QStyleOption *option, QPainter *painter,
                            const QWidget *widget) const
{
    switch (element)
    {
    case PE_PanelButtonCommand:
    case PE_PanelButtonTool:
    case PE_PanelButtonBevel:
        paintButtonPanel(roleOf(widget), option, painter);
        return;
    case PE_FrameFocusRect:
        return; // the ring is drawn by the control that has focus (buttons via State_HasFocus below)
    case PE_PanelLineEdit:
        paintFieldPanel(option, painter);
        return;
    case PE_FrameLineEdit:
        return;
    case PE_Frame:
    {
        const Surface surface = surfaceOf(widget);
        if (surface != Surface::None)
        {
            paintSurface(surface, option, painter);
            return;
        }
        // Only the controls that behave like a text field get the dark field panel: a text edit,
        // a plain text edit, or an item view (list/tree/table). A plain QScrollArea (most page
        // content wrappers) and any other bare frame get the hairline-only branch below --
        // otherwise every page scroll area would render a dark field behind the whole page.
        if (qobject_cast<const QTextEdit *>(widget) || qobject_cast<const QPlainTextEdit *>(widget)
            || qobject_cast<const QAbstractItemView *>(widget))
        {
            paintFieldPanel(option, painter);
            return;
        }
        painter->save();
        painter->setRenderHint(QPainter::Antialiasing, true);
        painter->setPen(QPen(tok(Color::Border), 1.0));
        painter->setBrush(Qt::NoBrush);
        painter->drawPath(rounded(strokeRect(option->rect), theme().radiusControl()));
        painter->restore();
        return;
    }
    case PE_IndicatorCheckBox:
    case PE_IndicatorRadioButton:
    {
        const bool on = option->state & State_On;
        const bool radio = element == PE_IndicatorRadioButton;
        painter->save();
        painter->setRenderHint(QPainter::Antialiasing, true);
        const QRectF r = strokeRect(option->rect);
        painter->setBrush(on ? tok(Color::Accent) : tok(Color::Surface0));
        painter->setPen(QPen(tok(on ? Color::Accent : Color::BorderStrong), 1.0));
        if (radio)
            painter->drawEllipse(r);
        else
            painter->drawPath(rounded(r, 4));
        if (on)
        {
            painter->setPen(QPen(Qt::white, 1.8, Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin));
            painter->setBrush(Qt::NoBrush);
            if (radio)
            {
                painter->setBrush(Qt::white);
                painter->setPen(Qt::NoPen);
                painter->drawEllipse(r.center(), 3, 3);
            }
            else
            {
                const QPointF c = r.center();
                painter->drawPolyline(QPolygonF({QPointF(c.x() - 4, c.y()), QPointF(c.x() - 1, c.y() + 3), QPointF(c.x() + 4, c.y() - 3)}));
            }
        }
        painter->restore();
        return;
    }
    case PE_PanelItemViewItem:
    case PE_PanelItemViewRow:
    {
        const bool selected = option->state & State_Selected;
        const bool hover = option->state & State_MouseOver;
        if (!selected && !hover)
            return;
        painter->save();
        painter->setRenderHint(QPainter::Antialiasing, true);
        painter->setPen(Qt::NoPen);
        painter->setBrush(selected ? tok(Color::AccentSubtle) : withAlpha(QColor(Qt::white), 0.04));
        painter->drawPath(rounded(QRectF(option->rect), 4));
        painter->restore();
        return;
    }
    default:
        break;
    }
    QProxyStyle::drawPrimitive(element, option, painter, widget);
}

void SvStyle::drawControl(ControlElement element, const QStyleOption *option, QPainter *painter,
                          const QWidget *widget) const
{
    switch (element)
    {
    case CE_PushButtonBevel:
        paintButtonPanel(roleOf(widget), option, painter);
        if (option->state & State_HasFocus)
        {
            painter->save();
            painter->setRenderHint(QPainter::Antialiasing, true);
            painter->setPen(QPen(tok(Color::AccentHover), 2.0));
            painter->setBrush(Qt::NoBrush);
            painter->drawPath(rounded(QRectF(option->rect).adjusted(1, 1, -1, -1), buttonPaint(roleOf(widget), option).radius));
            painter->restore();
        }
        return;
    case CE_PushButtonLabel:
    {
        if (const auto *btn = qstyleoption_cast<const QStyleOptionButton *>(option))
        {
            QStyleOptionButton copy = *btn;
            copy.palette.setColor(QPalette::ButtonText, buttonPaint(roleOf(widget), option).text);
            QProxyStyle::drawControl(element, &copy, painter, widget);
            return;
        }
        break;
    }
    case CE_ToolButtonLabel:
    {
        if (const auto *tb = qstyleoption_cast<const QStyleOptionToolButton *>(option))
        {
            QStyleOptionToolButton copy = *tb;
            copy.palette.setColor(QPalette::ButtonText, buttonPaint(roleOf(widget), option).text);
            QProxyStyle::drawControl(element, &copy, painter, widget);
            return;
        }
        break;
    }
    case CE_TabBarTabShape:
    {
        if (option->state & State_Selected)
        {
            painter->save();
            painter->setPen(Qt::NoPen);
            painter->setBrush(tok(Color::Accent));
            const QRect r = option->rect;
            painter->drawRoundedRect(QRectF(r.left() + 6, r.bottom() - 2, r.width() - 12, 2), 1, 1);
            painter->restore();
        }
        return;
    }
    case CE_TabBarTabLabel:
    {
        if (const auto *tab = qstyleoption_cast<const QStyleOptionTab *>(option))
        {
            QStyleOptionTab copy = *tab;
            const bool on = option->state & State_Selected;
            copy.palette.setColor(QPalette::WindowText, tok(on ? Color::TextHi : Color::TextMid));
            QProxyStyle::drawControl(element, &copy, painter, widget);
            return;
        }
        break;
    }
    case CE_ProgressBarGroove:
        painter->save();
        painter->setRenderHint(QPainter::Antialiasing, true);
        painter->setBrush(tok(Color::Surface0));
        painter->setPen(QPen(tok(Color::BorderSubtle), 1.0));
        painter->drawPath(rounded(strokeRect(option->rect), 3));
        painter->restore();
        return;
    case CE_ProgressBarContents:
    {
        if (const auto *pb = qstyleoption_cast<const QStyleOptionProgressBar *>(option))
        {
            const int span = pb->maximum - pb->minimum;
            if (span <= 0)
                return; // indeterminate: GlowProgressBar paints its own phase loop
            const qreal frac = qreal(pb->progress - pb->minimum) / span;
            QRectF r = QRectF(option->rect).adjusted(1, 1, -1, -1);
            r.setWidth(r.width() * frac);
            painter->save();
            painter->setRenderHint(QPainter::Antialiasing, true);
            painter->setPen(Qt::NoPen);
            painter->setBrush(tok(Color::Accent));
            painter->drawPath(rounded(r, 2));
            painter->restore();
            return;
        }
        break;
    }
    case CE_ProgressBarLabel:
        return;
    case CE_HeaderSection:
        painter->save();
        painter->fillRect(option->rect, tok(Color::Surface1));
        painter->setPen(QPen(tok(Color::Border), 1.0));
        painter->drawLine(option->rect.bottomLeft(), option->rect.bottomRight());
        painter->restore();
        return;
    case CE_HeaderLabel:
    {
        if (const auto *hd = qstyleoption_cast<const QStyleOptionHeader *>(option))
        {
            QStyleOptionHeader copy = *hd;
            copy.palette.setColor(QPalette::ButtonText, tok(Color::TextMid));
            QProxyStyle::drawControl(element, &copy, painter, widget);
            return;
        }
        break;
    }
    default:
        break;
    }
    QProxyStyle::drawControl(element, option, painter, widget);
}

void SvStyle::drawComplexControl(ComplexControl control, const QStyleOptionComplex *option,
                                 QPainter *painter, const QWidget *widget) const
{
    switch (control)
    {
    case CC_ComboBox:
    {
        if (const auto *cb = qstyleoption_cast<const QStyleOptionComboBox *>(option))
        {
            paintFieldPanel(option, painter);
            const QRect arrow = subControlRect(CC_ComboBox, cb, SC_ComboBoxArrow, widget);
            paintChevron(painter, QRectF(arrow), false, tok(Color::TextLo));
            if (!cb->editable)
            {
                // Label is drawn by CE_ComboBoxLabel through the base; only the panel and chevron are ours.
                QStyleOptionComboBox copy = *cb;
                copy.palette.setColor(QPalette::Text, tok(Color::TextHi));
                copy.palette.setColor(QPalette::ButtonText, tok(Color::TextHi));
                QProxyStyle::drawControl(CE_ComboBoxLabel, &copy, painter, widget);
            }
            return;
        }
        break;
    }
    case CC_SpinBox:
    {
        if (const auto *sb = qstyleoption_cast<const QStyleOptionSpinBox *>(option))
        {
            paintFieldPanel(option, painter);
            const QRect up = subControlRect(CC_SpinBox, sb, SC_SpinBoxUp, widget);
            const QRect down = subControlRect(CC_SpinBox, sb, SC_SpinBoxDown, widget);
            const bool upOn = sb->activeSubControls & SC_SpinBoxUp && (sb->state & State_Sunken);
            const bool downOn = sb->activeSubControls & SC_SpinBoxDown && (sb->state & State_Sunken);
            paintChevron(painter, QRectF(up), true, tok(upOn ? Color::TextHi : Color::TextLo));
            paintChevron(painter, QRectF(down), false, tok(downOn ? Color::TextHi : Color::TextLo));
            return;
        }
        break;
    }
    case CC_ScrollBar:
    {
        if (const auto *sb = qstyleoption_cast<const QStyleOptionSlider *>(option))
        {
            const QRect slider = subControlRect(CC_ScrollBar, sb, SC_ScrollBarSlider, widget);
            const bool hover = sb->state & State_MouseOver;
            painter->save();
            painter->setRenderHint(QPainter::Antialiasing, true);
            painter->setPen(Qt::NoPen);
            painter->setBrush(tok(hover ? Color::BorderStrong : Color::Border));
            const QRectF r = QRectF(slider).adjusted(2, 2, -2, -2);
            painter->drawRoundedRect(r, 3, 3);
            painter->restore();
            return;
        }
        break;
    }
    case CC_Slider:
    {
        if (const auto *sl = qstyleoption_cast<const QStyleOptionSlider *>(option))
        {
            const QRect groove = subControlRect(CC_Slider, sl, SC_SliderGroove, widget);
            const QRect handle = subControlRect(CC_Slider, sl, SC_SliderHandle, widget);
            painter->save();
            painter->setRenderHint(QPainter::Antialiasing, true);
            const bool horizontal = sl->orientation == Qt::Horizontal;
            QRectF track = horizontal ? QRectF(groove.left(), groove.center().y() - 2, groove.width(), 4)
                                      : QRectF(groove.center().x() - 2, groove.top(), 4, groove.height());
            painter->setPen(QPen(tok(Color::BorderSubtle), 1.0));
            painter->setBrush(tok(Color::Surface0));
            painter->drawRoundedRect(track, 2, 2);
            QRectF filled = track;
            if (horizontal)
                filled.setRight(handle.center().x());
            else
                filled.setTop(handle.center().y());
            painter->setPen(Qt::NoPen);
            painter->setBrush(withAlpha(tok(Color::Accent), 0.55));
            painter->drawRoundedRect(filled, 2, 2);
            painter->setBrush(tok(Color::Surface2));
            painter->setPen(QPen(tok(Color::BorderStrong), 1.0));
            painter->drawEllipse(QRectF(handle).adjusted(1, 1, -1, -1));
            painter->restore();
            return;
        }
        break;
    }
    case CC_ToolButton:
    {
        if (const auto *tb = qstyleoption_cast<const QStyleOptionToolButton *>(option))
        {
            paintButtonPanel(roleOf(widget), option, painter);
            QStyleOptionToolButton label = *tb;
            label.rect = subControlRect(CC_ToolButton, tb, SC_ToolButton, widget);
            drawControl(CE_ToolButtonLabel, &label, painter, widget);
            return;
        }
        break;
    }
    default:
        break;
    }
    QProxyStyle::drawComplexControl(control, option, painter, widget);
}

int SvStyle::pixelMetric(PixelMetric metric, const QStyleOption *option, const QWidget *widget) const
{
    switch (metric)
    {
    case PM_ScrollBarExtent:         return 8;
    case PM_ScrollBarSliderMin:      return 24;
    case PM_ButtonShiftHorizontal:   return 0;
    case PM_ButtonShiftVertical:     return 0;
    case PM_DefaultFrameWidth:       return 1;
    case PM_ButtonMargin:            return 12;
    case PM_IndicatorWidth:          return 16;
    case PM_IndicatorHeight:         return 16;
    case PM_ExclusiveIndicatorWidth: return 16;
    case PM_ExclusiveIndicatorHeight:return 16;
    case PM_TabBarTabVSpace:         return 8;
    case PM_SliderThickness:         return 16;
    case PM_SliderLength:            return 14;
    case PM_FocusFrameHMargin:       return 2;
    case PM_ButtonIconSize:          return 16;
    default:                         break;
    }
    return QProxyStyle::pixelMetric(metric, option, widget);
}

QSize SvStyle::sizeFromContents(ContentsType type, const QStyleOption *option, const QSize &contents,
                                const QWidget *widget) const
{
    QSize size = QProxyStyle::sizeFromContents(type, option, contents, widget);
    switch (type)
    {
    case CT_PushButton:
    {
        const Role role = roleOf(widget);
        size.setHeight(qMax(size.height(), roleMinHeight(role)));
        size.setWidth(contents.width() + 2 * roleHPad(role));
        return size;
    }
    case CT_ToolButton:
    {
        const Role role = roleOf(widget);
        if (role == Role::Rail)
            return size; // the rail tile is fixed 56x48 by MainWindow; do not fight it
        size.setHeight(qMax(size.height(), roleMinHeight(role)));
        size.setWidth(contents.width() + 2 * roleHPad(role));
        return size;
    }
    case CT_LineEdit:
    case CT_ComboBox:
    case CT_SpinBox:
        size.setHeight(qMax(size.height(), 28));
        return size;
    default:
        break;
    }
    return size;
}

} // namespace spellvision::style
