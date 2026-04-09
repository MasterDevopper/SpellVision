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
        const qreal tintMix = variant_ == Variant::Hero ? 0.16 : 0.10;
        fillA = dashboardMix(fillA, accentTint_, tintMix);
        topGlow = dashboardMix(topGlow, accentTint_, 0.24);
    }

    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing, true);
    painter.setPen(Qt::NoPen);

    QRectF bounds = rect();
    bounds.adjust(1.0, 1.0, -1.0, -1.0);

    QPainterPath path;
    path.addRoundedRect(bounds, cornerRadius_, cornerRadius_);

    QLinearGradient fill(bounds.topLeft(), bounds.bottomRight());
    fill.setColorAt(0.0, fillA);
    fill.setColorAt(0.60, dashboardMix(fillA, fillB, variant_ == Variant::Hero ? 0.32 : 0.42));
    fill.setColorAt(1.0, fillB);
    painter.fillPath(path, fill);

    const QRectF heroRect(bounds.left() - bounds.width() * 0.04,
                          bounds.top() - bounds.height() * 0.08,
                          bounds.width() * 0.86,
                          bounds.height() * 0.86);
    QRadialGradient mainGlow(heroRect.center(), heroRect.width() * 0.66);
    mainGlow.setColorAt(0.0, dashboardWithAlpha(topGlow, (variant_ == Variant::Hero ? 0.19 : 0.034) * localGlow));
    mainGlow.setColorAt(0.42, dashboardWithAlpha(secondaryGlow, (variant_ == Variant::Hero ? 0.032 : 0.011) * localGlow));
    mainGlow.setColorAt(1.0, Qt::transparent);
    painter.fillPath(path, mainGlow);

    if (variant_ == Variant::Hero)
    {
        QRectF sideFalloff(bounds.right() - bounds.width() * 0.58,
                           bounds.top() + bounds.height() * 0.06,
                           bounds.width() * 0.82,
                           bounds.height() * 0.96);
        QRadialGradient sideGlow(sideFalloff.center(), sideFalloff.width() * 0.72);
        sideGlow.setColorAt(0.0, dashboardWithAlpha(tokens.heroBackdrop, 0.18));
        sideGlow.setColorAt(0.54, dashboardWithAlpha(tokens.glowSecondary, 0.006 * localGlow));
        sideGlow.setColorAt(1.0, Qt::transparent);
        painter.fillPath(path, sideGlow);
    }

    QRectF vignetteRect(bounds.left(), bounds.top() + bounds.height() * 0.18, bounds.width(), bounds.height() * 1.02);
    QLinearGradient vignette(vignetteRect.topLeft(), vignetteRect.bottomLeft());
    vignette.setColorAt(0.0, Qt::transparent);
    vignette.setColorAt(0.54, dashboardWithAlpha(QColor(QStringLiteral("#02050b")), variant_ == Variant::Hero ? 0.24 : 0.17));
    vignette.setColorAt(1.0, dashboardWithAlpha(QColor(QStringLiteral("#02050b")), variant_ == Variant::Hero ? 0.44 : 0.32));
    painter.fillPath(path, vignette);

    painter.setPen(QPen(border, tokens.strokeWidth));
    painter.drawPath(path);

    if (variant_ != Variant::Utility)
    {
        painter.setPen(QPen(dashboardWithAlpha(innerLine, variant_ == Variant::Hero ? 0.12 : 0.06), 0.60));
        QRectF inner = bounds.adjusted(2.0, 2.0, -2.0, -2.0);
        painter.drawArc(inner.adjusted(variant_ == Variant::Hero ? 26.0 : 28.0, 10.0, -inner.width() * (variant_ == Variant::Hero ? 0.28 : 0.32), -inner.height() * 0.82), 16 * 16, variant_ == Variant::Hero ? 94 * 16 : 78 * 16);
    }

    const QRectF rim(bounds.left() + 22.0, bounds.top() + 10.0, bounds.width() - 44.0, 8.0);
    QLinearGradient rimGrad(rim.topLeft(), rim.topRight());
    rimGrad.setColorAt(0.0, Qt::transparent);
    rimGrad.setColorAt(0.18, dashboardWithAlpha(topGlow, (variant_ == Variant::Hero ? 0.10 : 0.028) * localGlow));
    rimGrad.setColorAt(0.68, dashboardWithAlpha(secondaryGlow, (variant_ == Variant::Hero ? 0.04 : 0.014) * localGlow));
    rimGrad.setColorAt(1.0, Qt::transparent);
    painter.setPen(QPen(QBrush(rimGrad), variant_ == Variant::Hero ? 0.62 : 0.38));
    painter.drawLine(rim.topLeft(), rim.topRight());
}
