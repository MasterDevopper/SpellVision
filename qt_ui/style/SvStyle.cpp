#include "style/SvStyle.h"

#include "ThemeManager.h"

#include <QAbstractButton>
#include <QAbstractItemView>
#include <QApplication>
#include <QFont>
#include <QFontMetrics>
#include <QLinearGradient>
#include <QPainter>
#include <QPainterPath>
#include <QPalette>
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

// Alpha-composite `top` over `base` and hand back an OPAQUE colour. The accent tint tokens are
// translucent (AccentSubtle is 7-10 % on four of the five presets and 15.7 % on Ember, which is
// alpha 40 rather than the 18-26 the others carry), and a chip's plate is opaque Surface1
// whatever sits behind it -- so blending here is what keeps a checked chip the same distance from
// its unchecked neighbour on a card, in an inset track, or on the bare window. Painted raw, the
// backdrop decides how much selection is worth, which on a dark ground came to 17 levels against
// the 24 this is gated at.
//
// PRECONDITION: `base` must be opaque. The result DISCARDS base's alpha and comes back fully
// opaque, which is right for the one caller -- Surface1 is opaque on all five presets -- and wrong
// the moment someone composites onto a token that is not. Blend onto whatever is behind a
// translucent base first, or give this an alpha-aware sibling.
QColor over(const QColor &base, const QColor &top)
{
    const qreal a = top.alphaF();
    return QColor::fromRgbF(base.redF() * (1.0 - a) + top.redF() * a,
                            base.greenF() * (1.0 - a) + top.greenF() * a,
                            base.blueF() * (1.0 - a) + top.blueF() * a);
}

QPainterPath rounded(const QRectF &rect, qreal radius)
{
    QPainterPath path;
    path.addRoundedRect(rect, radius, radius);
    return path;
}

// Inset by half a pixel so a 1 px stroke lands on whole pixels instead of smearing over two.
QRectF strokeRect(const QRect &rect) { return QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5); }

// A blocked action button is deliberately still ENABLED: applyActionReadinessStyle keeps it
// clickable so the click can report the exact reason instead of feeling dead. So State_Enabled is
// set, :disabled never fires, and this property is the only thing that says "not ready". It used to
// be a stylesheet rule, which is worse than it sounds: the rule set `border-color` with no
// border-style, so it drew no rim at all once the base button rules around it were deleted, and it
// could not round a corner the style had already rounded. A state the style knows is a state the
// style can draw.
bool isReadinessBlocked(const QWidget *widget)
{
    return widget && widget->property("readinessBlocked").toBool();
}

// The label colour AT REST, in one place. paintButtonPanel's switch refines it for hover and
// checked; SvStyle::polish writes this same value into the widget palette, because a label drawn by
// QStyleSheetStyle never reaches CE_PushButtonLabel and would otherwise keep the app default.
QColor labelColorFor(Role role, bool blocked, bool enabled)
{
    // "Not ready" and "off" take the SAME ink, and one token is all the ramp has for it:
    // TextDisabled is defined as the colour of a label that is not live. The white-at-60 % the
    // hero used to take when disabled was a fourth ink nothing else in the app uses, and it read
    // as a lit button seen through fog rather than as an off one.
    if (blocked || !enabled)
        return tok(Color::TextDisabled);
    switch (role)
    {
    case Role::Primary:
        return QColor(Qt::white);
    case Role::Danger:
        return tok(Color::Error);
    case Role::Tertiary:
    case Role::Chip:
    case Role::Rail:
    case Role::Tab:
    case Role::None:
        return tok(Color::TextMid);
    case Role::Secondary:
        break;
    }
    return tok(Color::TextHi);
}

struct ButtonPaint
{
    QColor fill;
    QColor edge;
    QColor text;
    qreal radius = 6;
    bool gradient = false;
};

ButtonPaint buttonPaint(Role role, const QStyleOption *opt, const QWidget *widget)
{
    const bool hover = opt->state & QStyle::State_MouseOver;
    const bool down = opt->state & QStyle::State_Sunken;
    const bool checked = opt->state & QStyle::State_On;
    const bool enabled = opt->state & QStyle::State_Enabled;
    const bool blocked = isReadinessBlocked(widget);
    ButtonPaint p;
    p.radius = theme().radiusControl();
    p.text = labelColorFor(role, blocked, enabled);
    // There is no hover/checked LIFT of that colour here any more. Task 9 deleted the chip's
    // `p.text = tok(Color::TextHi)` on the grounds that it never reaches a live label, and the same
    // grounds held for the other four roles that still carried it: ThemeManager always installs the
    // qApp overlay sheet AND shellStyleSheet's bare `QPushButton, QToolButton { padding: 5px 10px;
    // min-height: 30px; }` (ThemeManager.cpp:1422) matches every button under the main window --
    // including a dialog parented to it, since a sheet propagates down the object tree and not the
    // window tree. A matched rule with a box makes QStyleSheetStyle draw the label itself, out of
    // the widget palette, which polish() writes from the REST colour only. Four lines that looked
    // like a hover channel and were not.
    switch (role)
    {
    case Role::Primary:
        p.gradient = true;
        p.fill = tok(Color::Accent);
        p.edge = withAlpha(tok(Color::AccentTertiary), 0.35);
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
        break;
    case Role::Danger:
        p.fill = withAlpha(tok(Color::Error), hover ? 0.24 : 0.16);
        p.edge = withAlpha(tok(Color::Error), 0.6);
        break;
    case Role::Chip:
        // A checked chip has to read on a light ground as well as a dark one. A white veil is a
        // dark-theme idiom -- over Ivory Holograph's near-white Surface1 it moved the plate by
        // four levels, which is not a signal. AccentSubtle is a HUE shift rather than a luminance
        // one, so it survives both grounds, and selection is then carried by two channels: the
        // tint and an accent edge, instead of one hairline.
        p.fill = checked ? over(tok(Color::Surface1), tok(Color::AccentSubtle)) : tok(Color::Surface1);
        p.edge = checked ? tok(Color::Accent) : tok(hover ? Color::BorderStrong : Color::Border);
        break;
    case Role::Rail:
        p.fill = checked ? withAlpha(QColor(Qt::white), 0.05)
                         : (hover ? withAlpha(QColor(Qt::white), 0.04) : QColor(0, 0, 0, 0));
        p.edge = QColor(0, 0, 0, 0);
        p.radius = 8;
        break;
    case Role::Tab:
    case Role::None:
        p.fill = QColor(0, 0, 0, 0);
        p.edge = QColor(0, 0, 0, 0);
        break;
    }
    // Blocked and DISABLED both beat every state above them, pressed included: the control keeps
    // its shape and its radius and loses its light. EVERY role, not only the hero --
    // applyActionReadinessStyle sets the property on Queue as well as Generate, and a Queue that
    // looks ready when it is not is the same lie one size down.
    //
    // The two states are drawn IDENTICALLY, and that is a decision rather than an oversight. They
    // do mean different things -- blocked is "not ready yet" and stays clickable so the click can
    // say why, disabled is "off" and eats the click -- but a second, dimmer tier is not a signal
    // that survives this palette. Measured on Arcane Glass at the alternative 0.22: the hero moves
    // (16, 10, 29) from the 0.35 tier, and every other role moves under four levels in every
    // channel, because a Secondary's fill is opaque Surface2 and the surfaces in this palette sit
    // about fifteen levels apart -- the same measurement that set kDimFill at 0.35 in the first
    // place. A rule visible on one role out of seven is not a rule; the difference between the two
    // states is carried by what happens on the CLICK, which is where the user asks the question.
    //
    // 118 setEnabled sites across the tree ride on this branch. Before it, a disabled Primary
    // painted the full accent gradient and a disabled Chip the full Surface1: the platform style
    // used to grey them and the QProxyStyle did not, which made "off" the one state the app could
    // not say.
    if (blocked || !enabled)
    {
        // One fraction for every role. The brief said halve the alpha for the non-hero roles, and
        // measured that is not a signal: Surface2 at 0.5 over the page ground moved the Secondary
        // centre by (6, 8, 10) -- under the brief's own "more than 10 in a channel" bar, because
        // every surface in this palette sits within about fifteen levels of the next. At the same
        // 0.35 the hero uses, the Secondary moves by 13 in blue and the rule reads as one thing:
        // blocked is the control's own colour at a third.
        constexpr qreal kDimFill = 0.35;
        p.gradient = false;
        if (role == Role::Primary)
        {
            p.fill = withAlpha(tok(Color::Accent), kDimFill);
            p.edge = tok(Color::BorderSubtle);
        }
        else if (p.fill.alpha() == 0)
        {
            // A role that draws no plate while it is LIVE -- tertiary, rail, tab -- must not grow
            // one when it goes off. The branch used to hand it a 0.35 Surface1 plate and a
            // BorderSubtle rim on the grounds that "a transparent role needs something to dim",
            // which was written when only Generate and Queue could reach here. Extending it to
            // every disabled control made that visible, and wrong: captured on Ivory Holograph,
            // the disabled LoRA reorder arrow was the ONLY rimmed control in its row, so the off
            // button was the decorated one and the live ones looked like plain glyphs. Nothing to
            // dim means nothing drawn; the label going to TextDisabled is the entire state.
        }
        else
        {
            p.fill = withAlpha(p.fill, p.fill.alphaF() * kDimFill);
            p.edge = tok(Color::BorderSubtle);
        }
        p.text = tok(Color::TextDisabled);
    }
    return p;
}

void paintButtonPanel(Role role, const QStyleOption *opt, QPainter *painter, const QWidget *widget)
{
    const ButtonPaint p = buttonPaint(role, opt, widget);
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

// One focus ring, used by both button paths. A push button and a tool button that look the same
// have to signal keyboard focus the same way, and until now only the push button did: the tool
// buttons -- the whole activity rail, the title-bar chrome, every chip -- showed nothing at all.
void paintFocusRing(Role role, const QStyleOption *opt, QPainter *painter, const QWidget *widget)
{
    if (!(opt->state & QStyle::State_HasFocus))
        return;
    painter->save();
    painter->setRenderHint(QPainter::Antialiasing, true);
    painter->setPen(QPen(tok(Color::AccentHover), 2.0));
    painter->setBrush(Qt::NoBrush);
    painter->drawPath(rounded(QRectF(opt->rect).adjusted(1, 1, -1, -1), buttonPaint(role, opt, widget).radius));
    painter->restore();
}

void paintSurface(Surface surface, const QStyleOption *opt, QPainter *painter)
{
    painter->save();
    painter->setRenderHint(QPainter::Antialiasing, true);
    const QRectF r = strokeRect(opt->rect);
    const qreal radius = surface == Surface::Inset ? theme().radiusControl() : theme().radiusCard();
    const QPainterPath path = rounded(r, radius);
    // Which surfaces are "hero" is the material axis's whole hinge: Refined glasses everything,
    // Matte glasses nothing, and Hybrid glasses the hero surfaces only -- which is what the
    // material is FOR. Asking with a hardcoded true was asking the one question whose answer is
    // the same for Refined and Hybrid, which is why the two rendered within 0.0006 of each other.
    // Inset stays out of it: a recessed field is not a lit surface in any material.
    const bool hero = surface == Surface::Glass || surface == Surface::Plate;
    if (surface != Surface::Inset && theme().styleUsesGlass(hero))
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

// A button label's weight is part of what the button IS, so the style sets it rather than a
// stylesheet: the shell sheet's generic `QPushButton { font-weight: 600 }` put one weight on every
// button in the app, hero and quiet alike, and went with the retreat in Task 4. Primary is the only
// control allowed the 600 on the Plex ramp; every other role is the 500 the type scale uses for a
// label. Returns the font it set so the caller can keep the option's metrics in step with it.
QFont applyLabelWeight(QPainter *painter, Role role)
{
    QFont label = painter->font();
    label.setWeight(role == Role::Primary ? QFont::DemiBold : QFont::Medium);
    painter->setFont(label);
    return label;
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
    return Role::None;
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
    return Surface::None;
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

    // The role's label colour also goes into the widget PALETTE, and that is not belt-and-braces.
    // With the qApp overlay sheet active Qt wraps this style in QStyleSheetStyle, which draws a
    // button's label itself instead of routing CE_PushButtonLabel here -- measured: a blocked
    // Generate and a ready one came back the same 233,235,248. QStyleSheetStyle honours
    // ButtonText/Text whenever no rule sets `color`, so this is the one channel that reaches it.
    // kit::setRole and applyActionReadinessStyle both repolish, so the palette follows the role and
    // the blocked state without anyone having to remember to set it.
    if (auto *button = qobject_cast<QAbstractButton *>(widget))
    {
        const Role role = roleOf(button);
        const bool blocked = isReadinessBlocked(button);
        if (role != Role::None || blocked)
        {
            // Ask for the ENABLED colour deliberately, not button->isEnabled(): polish runs once at
            // construction and setEnabled() does not repolish, so a palette written from the live
            // enabled state would freeze whichever state the widget happened to be in that
            // instant. Both states go in instead, and the group Qt looks up then tracks the widget.
            const QColor label = labelColorFor(role, blocked, /*enabled=*/true);
            const QColor off = labelColorFor(role, blocked, /*enabled=*/false);
            QPalette pal = button->palette();
            if (pal.color(QPalette::ButtonText) != label || pal.color(QPalette::Text) != label
                || pal.color(QPalette::Disabled, QPalette::ButtonText) != off)
            {
                pal.setColor(QPalette::ButtonText, label);
                pal.setColor(QPalette::Text, label);
                // The two-argument setColor writes ALL THREE colour groups -- Active, Inactive AND
                // Disabled -- so the line above just put the ENABLED ink in the group
                // QCommonStyle::drawItemText reads for a disabled widget, and a disabled button's
                // label came back the live colour. The Disabled group has to be written after it,
                // explicitly, or the fill dims underneath a label that still looks lit.
                pal.setColor(QPalette::Disabled, QPalette::ButtonText, off);
                pal.setColor(QPalette::Disabled, QPalette::Text, off);
                button->setPalette(pal);
            }
        }
    }
}

void SvStyle::drawPrimitive(PrimitiveElement element, const QStyleOption *option, QPainter *painter,
                            const QWidget *widget) const
{
    switch (element)
    {
    case PE_PanelButtonCommand:
    case PE_PanelButtonTool:
    case PE_PanelButtonBevel:
        paintButtonPanel(roleOf(widget), option, painter, widget);
        return;
    case PE_FrameFocusRect:
        // Qt's generic dotted rect is never drawn. The ring belongs to the control that has focus,
        // and paintFocusRing() gives it to both: push buttons through CE_PushButtonBevel and tool
        // buttons through CC_ToolButton, at the same pen, inset and role radius.
        return;
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
        paintButtonPanel(roleOf(widget), option, painter, widget);
        paintFocusRing(roleOf(widget), option, painter, widget);
        return;
    case CE_PushButtonLabel:
    {
        if (const auto *btn = qstyleoption_cast<const QStyleOptionButton *>(option))
        {
            const Role role = roleOf(widget);
            QStyleOptionButton copy = *btn;
            copy.palette.setColor(QPalette::ButtonText, buttonPaint(role, option, widget).text);
            const QFont saved = painter->font();
            copy.fontMetrics = QFontMetrics(applyLabelWeight(painter, role));
            QProxyStyle::drawControl(element, &copy, painter, widget);
            painter->setFont(saved);
            return;
        }
        break;
    }
    case CE_ToolButtonLabel:
    {
        if (const auto *tb = qstyleoption_cast<const QStyleOptionToolButton *>(option))
        {
            const Role role = roleOf(widget);
            QStyleOptionToolButton copy = *tb;
            copy.palette.setColor(QPalette::ButtonText, buttonPaint(role, option, widget).text);
            const QFont saved = painter->font();
            copy.fontMetrics = QFontMetrics(applyLabelWeight(painter, role));
            QProxyStyle::drawControl(element, &copy, painter, widget);
            painter->setFont(saved);
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
            {
                // INDETERMINATE. What stood here was `return; // GlowProgressBar paints its own
                // phase loop`, and it was false in both halves: GlowProgressBar derives from
                // QWidget, not QProgressBar, so it never reaches this code path at all (nor did
                // the `QProgressBar#BottomProgressBar` shell rule ever match it), and the widgets
                // that DO arrive here indeterminate -- DatasetGenerationPage's bar while the worker
                // queues, and the Character, Comic and Concept studio bars -- were handed a static
                // empty groove by that early return.
                //
                // The moving chunk comes from the BASE style rather than a timer of ours, which is
                // what the review asked for: Fusion's CE_ProgressBarContents owns a
                // QProgressStyleAnimation keyed on option->styleObject, and THAT animation is what
                // repaints the widget -- an indeterminate QProgressBar does not repaint itself, so
                // a phase read off the clock at paint time would sit frozen wherever the last
                // unrelated repaint left it. A timer living in the style would be the same
                // machinery in a second copy. All we add is the palette, so the busy chunk is the
                // accent and its ground is Surface0 instead of Fusion's own blue.
                // Half-strength accent, not the full one. Measured: the base fills the WHOLE groove
                // with Highlight and slides a lighter band through it, so a full-strength Accent
                // reads as a bar at 100 % -- the opposite of "we do not know how far along this is".
                // Composited over Surface0 rather than left translucent, because the base derives
                // its own lighter and darker variants from this colour and an alpha would compound.
                QStyleOptionProgressBar copy = *pb;
                copy.palette.setColor(QPalette::Highlight,
                                      over(tok(Color::Surface0), withAlpha(tok(Color::Accent), 0.5)));
                copy.palette.setColor(QPalette::HighlightedText, tok(Color::TextHi));
                copy.palette.setColor(QPalette::Base, tok(Color::Surface0));
                copy.palette.setColor(QPalette::Window, tok(Color::Surface0));
                if (pb->styleObject)
                {
                    QProxyStyle::drawControl(element, &copy, painter, widget);
                    return;
                }
                // No styleObject is no animation target (a hand-built option), and starting an
                // animation against a null target would leave a phase running with nothing to
                // repaint. Draw the band statically instead of drawing nothing.
                painter->save();
                painter->setRenderHint(QPainter::Antialiasing, true);
                painter->setPen(Qt::NoPen);
                painter->setBrush(withAlpha(tok(Color::Accent), 0.35));
                painter->drawPath(rounded(QRectF(option->rect).adjusted(1, 1, -1, -1), 2));
                painter->restore();
                return;
            }
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
    {
        // This used to return unconditionally, which suppressed the percentage QProgressBar shows
        // by DEFAULT -- and of the five live bars only three (Character, Comic, Concept) ask for
        // that with setTextVisible(false). Dataset's and Video's never did: they lost their
        // readout to a style decision nobody made. So the widget's own answer is honoured, and the
        // ink comes from the token ramp rather than the app palette, which is the only reason this
        // case still exists at all.
        if (const auto *pb = qstyleoption_cast<const QStyleOptionProgressBar *>(option))
        {
            if (!pb->textVisible || pb->text.isEmpty())
                return;
            painter->save();
            painter->setPen(tok(Color::TextHi));
            painter->drawText(option->rect, pb->textAlignment | Qt::AlignVCenter, pb->text);
            painter->restore();
            return;
        }
        return;
    }
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
            paintButtonPanel(roleOf(widget), option, painter, widget);
            paintFocusRing(roleOf(widget), option, painter, widget);
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
