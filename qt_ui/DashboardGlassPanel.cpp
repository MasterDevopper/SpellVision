#include "DashboardGlassPanel.h"

#include "DashboardSurfaceTokens.h"
#include "ThemeManager.h"

#include <QLinearGradient>
#include <QPaintEvent>
#include <QPainter>
#include <QPainterPath>
#include <QRadialGradient>

DashboardGlassPanel::DashboardGlassPanel(QWidget *parent)
    : QWidget(parent)
{
    setAttribute(Qt::WA_StyledBackground, false);
    setAutoFillBackground(false);
    // Phase 3: repaint on theme switch. paintEvent re-reads DashboardSurfaceTokens::fromTheme
    // (now canonical tokens) every paint, so a repaint is all that's needed to re-color.
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, [this]() { update(); });
}

DashboardGlassPanel::Variant DashboardGlassPanel::variant() const
{
    return variant_;
}

void DashboardGlassPanel::setVariant(Variant variant)
{
    if (variant_ == variant)
        return;

    variant_ = variant;
    update();
}

int DashboardGlassPanel::cornerRadius() const
{
    return cornerRadius_;
}

void DashboardGlassPanel::setCornerRadius(int radius)
{
    radius = qMax(4, radius);
    if (cornerRadius_ == radius)
        return;

    cornerRadius_ = radius;
    update();
}

qreal DashboardGlassPanel::glowStrength() const
{
    return glowStrength_;
}

void DashboardGlassPanel::setGlowStrength(qreal strength)
{
    strength = qBound(0.0, strength, 2.5);
    if (qFuzzyCompare(glowStrength_, strength))
        return;

    glowStrength_ = strength;
    update();
}

QColor DashboardGlassPanel::accentTint() const
{
    return accentTint_;
}

void DashboardGlassPanel::setAccentTint(const QColor &color)
{
    accentTint_ = color;
    update();
}

void DashboardGlassPanel::paintEvent(QPaintEvent *event)
{
    Q_UNUSED(event)

    const DashboardSurfaceTokens tokens = DashboardSurfaceTokens::fromTheme(ThemeManager::instance());

    QColor fillA = tokens.panelBaseA;
    QColor fillB = tokens.panelBaseB;
    QColor border = tokens.borderSoft;
    QColor topGlow = tokens.glowPrimary;
    QColor secondaryGlow = tokens.glowSecondary;
    QColor innerLine = tokens.innerHighlight;
    qreal localGlow = tokens.secondaryGlow * glowStrength_;

    switch (variant_)
    {
    case Variant::Standard:
        break;
    case Variant::Raised:
        fillA = tokens.panelRaisedA;
        fillB = tokens.panelRaisedB;
        border = tokens.borderStrong;
        topGlow = tokens.glowSecondary;
        secondaryGlow = tokens.glowTertiary;
        innerLine = tokens.innerHighlight;
        localGlow = tokens.secondaryGlow * 0.44 * glowStrength_;
        break;
    case Variant::Hero:
        fillA = dashboardMix(tokens.panelRaisedA, tokens.glowPrimary, 0.055);
        fillB = dashboardMix(tokens.panelBaseB, QColor(QStringLiteral("#01040a")), 0.44);
        border = tokens.borderHero;
        topGlow = dashboardMix(tokens.glowPrimary, tokens.glowSecondary, 0.35);
        secondaryGlow = tokens.glowTertiary;
        innerLine = tokens.innerHero;
        localGlow = tokens.heroGlow * 0.96 * glowStrength_;
        break;
    case Variant::Inset:
        fillA = tokens.panelInsetA;
        fillB = tokens.panelInsetB;
        border = dashboardWithAlpha(tokens.borderSoft, 0.84);
        topGlow = dashboardWithAlpha(tokens.glowTertiary, 0.55);
        secondaryGlow = dashboardWithAlpha(tokens.glowPrimary, 0.32);
        innerLine = dashboardWithAlpha(tokens.innerHighlight, 0.8);
        localGlow = tokens.secondaryGlow * 0.40 * glowStrength_;
        break;
    case Variant::Utility:
        fillA = tokens.utilityA;
        fillB = tokens.utilityB;
        border = dashboardWithAlpha(tokens.borderSoft, 0.78);
        topGlow = dashboardWithAlpha(tokens.glowPrimary, 0.42);
        secondaryGlow = dashboardWithAlpha(tokens.glowSecondary, 0.24);
        innerLine = dashboardWithAlpha(tokens.innerHighlight, 0.72);
        localGlow = tokens.utilityGlow * 0.58 * glowStrength_;
        break;
    }

    if (accentTint_.isValid())
    {
        // Phase 5: tint toward the LIVE theme accent (read here, not the stored per-mode
        // value) so it switches with the theme; unified across modes.
        const QColor tint = ThemeManager::instance().color(ThemeManager::Color::Accent);
        const qreal tintMix = variant_ == Variant::Hero ? 0.16 : 0.10;
        fillA = dashboardMix(fillA, tint, tintMix);
        topGlow = dashboardMix(topGlow, tint, 0.24);
    }

    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing, true);
    painter.setPen(Qt::NoPen);

    QRectF bounds = rect();
    bounds.adjust(1.0, 1.0, -1.0, -1.0);

    QPainterPath path;
    path.addRoundedRect(bounds, cornerRadius_, cornerRadius_);

    // Which material this panel is made of under the active style. Hero is the surface Hybrid keeps
    // glass for; every other variant goes matte there.
    const ThemeManager &theme = ThemeManager::instance();
    const bool heroSurface = variant_ == Variant::Hero;
    if (!theme.styleUsesGlass(heroSurface))
    {
        paintMatte(painter, path, bounds, fillA, fillB, border);
        return;
    }
    // --- Refined glass stack ----------------------------------------------
    // Five of the original nine layers are gone: the second (side) radial, the vignette, the
    // decorative drawArc sheen and the rim streak. They were per-card light sources, so ten panels
    // meant ten small suns and the hierarchy flattened into texture. What remains is one accent
    // glow, a body, and hairlines.
    // 1) Soft drop shadow (depth behind the plate)
    {
        QRectF shadowRect = bounds.translated(0.0, 3.0);
        QPainterPath shadowPath;
        shadowPath.addRoundedRect(shadowRect, cornerRadius_, cornerRadius_);
        QColor shadow = QColor(0, 0, 0, variant_ == Variant::Hero ? 90 : 55);
        painter.setOpacity(0.55);
        painter.fillPath(shadowPath, shadow);
        painter.setOpacity(1.0);
    }

    // 2) Translucent body fill (glass fill token when available)
    const QColor glassFill = ThemeManager::instance().color(ThemeManager::Color::GlassFill);
    if (glassFill.isValid() && glassFill.alpha() > 0) {
        fillA = dashboardMix(fillA, glassFill, 0.42);
        fillB = dashboardMix(fillB, glassFill, 0.28);
    }

    QLinearGradient fill(bounds.topLeft(), bounds.bottomRight());
    fill.setColorAt(0.0, fillA);
    fill.setColorAt(0.55, dashboardMix(fillA, fillB, variant_ == Variant::Hero ? 0.28 : 0.40));
    fill.setColorAt(1.0, fillB);
    painter.fillPath(path, fill);

    // 3) Specular top wash (frosted highlight)
    {
        QLinearGradient spec(bounds.topLeft(), QPointF(bounds.left(), bounds.top() + bounds.height() * 0.42));
        const QColor hi = ThemeManager::instance().color(ThemeManager::Color::GlassHighlight);
        spec.setColorAt(0.0, dashboardWithAlpha(hi.isValid() ? hi : QColor(255, 255, 255),
                                                variant_ == Variant::Hero ? 0.16 : 0.10));
        spec.setColorAt(0.55, dashboardWithAlpha(QColor(255, 255, 255), 0.03));
        spec.setColorAt(1.0, Qt::transparent);
        painter.fillPath(path, spec);
    }

    const QRectF heroRect(bounds.left() - bounds.width() * 0.04,
                          bounds.top() - bounds.height() * 0.08,
                          bounds.width() * 0.86,
                          bounds.height() * 0.86);
    QRadialGradient mainGlow(heroRect.center(), heroRect.width() * 0.66);
    mainGlow.setColorAt(0.0, dashboardWithAlpha(topGlow, (variant_ == Variant::Hero ? 0.22 : 0.05) * localGlow));
    mainGlow.setColorAt(0.42, dashboardWithAlpha(secondaryGlow, (variant_ == Variant::Hero ? 0.04 : 0.016) * localGlow));
    mainGlow.setColorAt(1.0, Qt::transparent);
    painter.fillPath(path, mainGlow);

    // (The hero side-glow and the panel vignette used to sit here. Both were removed: the side glow
    // was a second light source on the one surface that already has the main one, and the vignette
    // darkened every card's own bottom edge, which fought the elevation the surface tokens set.)

    // 4) Dual-edge border: outer hairline + inner platinum rim (glass edge)
    painter.setPen(QPen(border, tokens.strokeWidth));
    painter.drawPath(path);

    {
        QPainterPath innerPath;
        QRectF inner = bounds.adjusted(1.2, 1.2, -1.2, -1.2);
        innerPath.addRoundedRect(inner, qMax(2.0, cornerRadius_ - 1.0), qMax(2.0, cornerRadius_ - 1.0));
        const QColor glassHi = ThemeManager::instance().color(ThemeManager::Color::GlassHighlight);
        painter.setPen(QPen(dashboardWithAlpha(glassHi.isValid() ? glassHi : innerLine,
                                               variant_ == Variant::Hero ? 0.22 : 0.12),
                            0.9));
        painter.drawPath(innerPath);
    }

    // (The decorative drawArc sheen and the rim streak used to close this function. An arc of light
    // that corresponds to no real geometry is the single most consumer-skin move in the old stack,
    // and the rim streak repeated the specular wash it sits on top of. Both deleted.)
}

void DashboardGlassPanel::paintMatte(QPainter &painter,
                                     const QPainterPath &path,
                                     const QRectF &bounds,
                                     const QColor &fillA,
                                     const QColor &fillB,
                                     const QColor &border) const
{
    // Matte instrument: opaque body, one hairline, nothing emitted. Depth is the surface token step
    // plus the border -- the same way Linear, Figma and Resolve get it. Two paint operations against
    // the glass path's nine, and no gradient allocation on the common case.
    const ThemeManager &theme = ThemeManager::instance();

    QColor body = fillA;
    body.setAlpha(255);

    if (variant_ == Variant::Hero || variant_ == Variant::Raised)
    {
        // The only gradient matte allows: a barely-there vertical step so a raised plate reads as
        // raised rather than as a differently-coloured rectangle. Two stops, ~4% apart.
        QColor foot = fillB;
        foot.setAlpha(255);
        QLinearGradient step(bounds.topLeft(), bounds.bottomLeft());
        step.setColorAt(0.0, body.lighter(variant_ == Variant::Hero ? 106 : 103));
        step.setColorAt(1.0, foot);
        painter.fillPath(path, step);
    }
    else
    {
        painter.fillPath(path, body);
    }

    // Selection/accent tint stays, because in a matte theme it is the ONLY thing colour is spent on.
    if (accentTint_.isValid())
    {
        const QColor tint = theme.color(ThemeManager::Color::AccentSubtle);
        if (tint.alpha() > 0)
            painter.fillPath(path, tint);
    }

    QColor line = border;
    if (variant_ == Variant::Hero)
        line = theme.color(ThemeManager::Color::BorderStrong);
    painter.setPen(QPen(line, 1.0));
    painter.setBrush(Qt::NoBrush);
    painter.drawPath(path);
}
